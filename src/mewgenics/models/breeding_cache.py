"""Breeding cache: pre-computed ancestry / risk data shared across all views."""
import json
import os
import hashlib
from typing import Optional

from PySide6.QtCore import QThread, Signal

from save_parser import (
    Cat,
    risk_percent, shared_ancestor_counts,
    _ancestor_depths, _build_ancestor_contribs_batch,
    _kinship, _combined_malady_chance,
)
from mewgenics.utils.paths import _breeding_cache_path


def _breeding_cache_fingerprint(cat: 'Cat') -> tuple:
    """Return the fields that affect breeding cache validity."""
    parent_a = getattr(cat, "parent_a", None)
    parent_b = getattr(cat, "parent_b", None)
    return (
        getattr(cat, "db_key", None),
        getattr(parent_a, "db_key", None) if parent_a is not None else None,
        getattr(parent_b, "db_key", None) if parent_b is not None else None,
        getattr(cat, "status", None),
        getattr(cat, "gender", None),
    )


def _breeding_save_signature(cats: list['Cat']) -> str:
    """Stable fingerprint of the save content relevant to breeding cache data."""
    def _sort_key(cat: 'Cat') -> tuple[int, str]:
        try:
            db_key = int(getattr(cat, "db_key", 0))
        except (TypeError, ValueError):
            db_key = 0
        return db_key, str(getattr(cat, "unique_id", "") or "")

    payload = [_breeding_cache_fingerprint(cat) for cat in sorted(cats, key=_sort_key)]
    raw = json.dumps(payload, separators=(",", ":"), ensure_ascii=False)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class BreedingCache:
    """Pre-computed ancestry / risk data shared across all views."""

    def __init__(self):
        self.ready = False
        # Per-cat data  (keyed by db_key)
        self.ancestor_contribs: dict[int, dict['Cat', float]] = {}  # {ancestor: sum(0.5^d)}
        self.ancestor_depths: dict[int, dict['Cat', int]] = {}
        # Pairwise data  (keyed by (min_key, max_key))
        self.risk_pct: dict[tuple[int, int], float] = {}
        self.shared_counts: dict[tuple[int, int], tuple[int, int]] = {}
        # Save-file pedigree COI memo table keyed by the same normalized pair key.
        self.pedigree_coi_memos: dict[tuple[int, int], float] = {}
        # Cat lookup
        self._cats_by_key: dict[int, 'Cat'] = {}

    # ── disk persistence ──

    _CACHE_VERSION = 8  # bump to invalidate stale disk caches

    def save_to_disk(self, save_path: str, save_signature: str = ""):
        """Persist pairwise results alongside the save file."""
        data = {
            "version": self._CACHE_VERSION,
            "save_mtime": os.path.getmtime(save_path),
            "save_signature": save_signature,
            "risk": {f"{a},{b}": v for (a, b), v in self.risk_pct.items()},
            "shared": {f"{a},{b}": list(v) for (a, b), v in self.shared_counts.items()},
        }
        try:
            with open(_breeding_cache_path(save_path), "w") as f:
                json.dump(data, f)
        except OSError:
            pass

    @staticmethod
    def load_from_disk(save_path: str, expected_signature: Optional[str] = None) -> Optional['BreedingCache']:
        """Load persisted pairwise data if the save file still matches."""
        cp = _breeding_cache_path(save_path)
        if not os.path.exists(cp):
            return None
        try:
            with open(cp, "r") as f:
                data = json.load(f)
            if data.get("version") != BreedingCache._CACHE_VERSION:
                return None  # old format, recompute
            if expected_signature is not None:
                if data.get("save_signature") != expected_signature:
                    return None  # save content changed, cache is stale
            else:
                if abs(data.get("save_mtime", 0) - os.path.getmtime(save_path)) > 0.5:
                    return None  # legacy fallback for older callers
            cache = BreedingCache()
            for k, v in data.get("risk", {}).items():
                a, b = k.split(",")
                cache.risk_pct[(int(a), int(b))] = float(v)
            for k, v in data.get("shared", {}).items():
                a, b = k.split(",")
                cache.shared_counts[(int(a), int(b))] = (int(v[0]), int(v[1]))
            # Mark as partially ready — pairwise data available, per-cat data needs recomputation
            cache.ready = True
            return cache
        except (OSError, ValueError, KeyError, json.JSONDecodeError):
            return None

    # ── public helpers ──

    @staticmethod
    def _pair_key(a_key: int, b_key: int) -> tuple[int, int]:
        return (a_key, b_key) if a_key < b_key else (b_key, a_key)

    def _memoized_risk_pct(self, a_key: int, b_key: int) -> Optional[float]:
        coi = self.pedigree_coi_memos.get(self._pair_key(a_key, b_key))
        if coi is None:
            return None
        return max(0.0, min(100.0, _combined_malady_chance(coi) * 100.0))

    def get_risk(self, a: 'Cat', b: 'Cat') -> float:
        pk = self._pair_key(a.db_key, b.db_key)
        cached = self.risk_pct.get(pk)
        if cached is not None:
            return cached
        memo_risk = self._memoized_risk_pct(a.db_key, b.db_key)
        if memo_risk is not None:
            return memo_risk
        if not self.ready:
            return risk_percent(a, b)
        return 0.0

    def get_shared(self, a: 'Cat', b: 'Cat', recent_depth: int = 3) -> tuple[int, int]:
        if not self.ready:
            return shared_ancestor_counts(a, b, recent_depth=recent_depth)
        return self.shared_counts.get(self._pair_key(a.db_key, b.db_key), (0, 0))

    def get_ancestor_depths_for(self, cat: 'Cat', max_depth: int = 8) -> dict['Cat', int]:
        if not self.ready:
            return _ancestor_depths(cat, max_depth=max_depth)
        return self.ancestor_depths.get(cat.db_key, {})


class BreedingCacheWorker(QThread):
    """Computes the full BreedingCache off the main thread."""
    progress = Signal(int, int)   # (current, total)
    phase1_ready = Signal(object)   # emits cache after phase 1 (ancestry only, no pairwise risk yet)
    finished_cache = Signal(object)  # emits the BreedingCache

    def __init__(self, cats: list['Cat'], save_path: str = "",
                 existing_pairwise: Optional['BreedingCache'] = None,
                 prev_cache: Optional['BreedingCache'] = None,
                 prev_parent_keys: Optional[dict[int, tuple]] = None,
                 save_signature: Optional[str] = None,
                 pedigree_coi_memos: Optional[dict[tuple[int, int], float]] = None,
                 parent=None):
        super().__init__(parent)
        self._cats = cats
        self._save_path = save_path
        self._existing = existing_pairwise  # disk-loaded cache with pairwise data only
        self._prev_cache = prev_cache       # previous in-memory cache for incremental update
        self._prev_parent_keys = prev_parent_keys or {}  # db_key -> (pa_key, pb_key) from prev load
        self._save_signature = save_signature or ""
        self._pedigree_coi_memos = dict(pedigree_coi_memos or {})

    @staticmethod
    def _parent_key_tuple(cat: 'Cat') -> tuple:
        pa = cat.parent_a.db_key if cat.parent_a is not None else None
        pb = cat.parent_b.db_key if cat.parent_b is not None else None
        return (pa, pb)

    def run(self):
        alive = [c for c in self._cats if c.status != "Gone"]
        n = len(alive)

        # Early exit if already superseded before we even start
        if self.isInterruptionRequested():
            return
        memo_table = dict(self._pedigree_coi_memos)

        has_pairwise = (
            self._existing is not None
            and self._existing.ready
            and len(self._existing.risk_pct) > 0
        )

        if has_pairwise:
            # Disk cache hit: pairwise data already loaded; only rebuild per-cat
            # ancestry (depths + contribs) for display / future incremental use.
            cache = self._existing
            cache.pedigree_coi_memos = memo_table
            cache._cats_by_key = {c.db_key: c for c in alive}
            self.progress.emit(0, n)
            batch = _build_ancestor_contribs_batch(alive)
            cache.ancestor_contribs.update(batch)
            for cat in alive:
                cache.ancestor_depths[cat.db_key] = _ancestor_depths(cat, max_depth=8)
            cache.ready = True
            self.progress.emit(n, n)
            self.finished_cache.emit(cache)
            return

        # ── Incremental mode: reuse unchanged cats from prev in-memory cache ──
        prev = self._prev_cache
        unchanged_keys: set[int] = set()
        alive_keys = {c.db_key for c in alive}
        if prev is not None and prev.ready and len(prev.risk_pct) > 0:
            for cat in alive:
                k = cat.db_key
                old_parents = self._prev_parent_keys.get(k)
                new_parents = self._parent_key_tuple(cat)
                if old_parents == new_parents and k in prev.ancestor_contribs:
                    unchanged_keys.add(k)
        else:
            prev = None

        changed_keys = alive_keys - unchanged_keys
        cache = BreedingCache()
        cache.pedigree_coi_memos = memo_table
        cache._cats_by_key = {c.db_key: c for c in alive}

        # ── Phase 1: per-cat ancestry (batch-memoized) ──
        # Reuse unchanged contribs / depths from prev
        if prev is not None:
            for k in unchanged_keys:
                cache.ancestor_contribs[k] = prev.ancestor_contribs[k]
                cache.ancestor_depths[k] = prev.ancestor_depths[k]

        # Count breedable pairs for progress (skip same-sex)
        def _can_possibly_breed(a: 'Cat', b: 'Cat') -> bool:
            ga, gb = a.gender, b.gender
            return not (ga == gb and ga != "?")

        n_phase2 = sum(
            1 for i in range(n) for j in range(i + 1, n)
            if alive[i].db_key not in unchanged_keys or alive[j].db_key not in unchanged_keys
            if _can_possibly_breed(alive[i], alive[j])
        )
        total_steps = max(1, n + n_phase2)
        self.progress.emit(0, total_steps)

        cats_to_compute = [c for c in alive if c.db_key in changed_keys]
        if cats_to_compute:
            # Include all alive cats so memo can traverse through unchanged parents
            batch = _build_ancestor_contribs_batch(alive)
            for cat in cats_to_compute:
                cache.ancestor_contribs[cat.db_key] = batch[cat.db_key]
                cache.ancestor_depths[cat.db_key] = _ancestor_depths(cat, max_depth=8)

        self.progress.emit(n, total_steps)

        # Emit phase1_ready so Mating Pair Search / main table become usable now
        cache.ready = True  # ancestry complete; risk_pct still empty for dirty pairs
        self.phase1_ready.emit(cache)

        # ── Phase 2: pairwise risk + shared (skip same-sex, reuse unchanged) ──
        if self.isInterruptionRequested():
            return

        # Use path-based COI (with overlap exclusion) for correct results in
        # heavily inbred colonies.  Kinship is O(ancestor pairs) with memo
        # shared across all pair computations — orders of magnitude faster than
        # path enumeration for deep, inbred pedigrees.
        kinship_memo: dict[tuple[int, int], float] = {}

        pairs_to_compute = []
        for i in range(n):
            a = alive[i]
            for j in range(i + 1, n):
                b = alive[j]
                if not _can_possibly_breed(a, b):
                    continue
                if a.db_key in unchanged_keys and b.db_key in unchanged_keys:
                    pk = cache._pair_key(a.db_key, b.db_key)
                    old_risk = prev.risk_pct.get(pk) if prev else None
                    old_shared = prev.shared_counts.get(pk) if prev else None
                    if old_risk is not None and old_shared is not None:
                        cache.risk_pct[pk] = old_risk
                        cache.shared_counts[pk] = old_shared
                        continue
                pairs_to_compute.append((i, j))

        step = n
        for i, j in pairs_to_compute:
            if self.isInterruptionRequested():
                return
            a = alive[i]
            b = alive[j]
            pk = cache._pair_key(a.db_key, b.db_key)

            memo_risk = cache._memoized_risk_pct(a.db_key, b.db_key)
            if memo_risk is not None:
                cache.risk_pct[pk] = memo_risk
            else:
                raw = _kinship(a, b, kinship_memo)
                cache.risk_pct[pk] = max(0.0, min(100.0, _combined_malady_chance(raw) * 100.0))

            da = cache.ancestor_depths.get(a.db_key, {})
            db_depths = cache.ancestor_depths.get(b.db_key, {})
            common = set(da.keys()) & set(db_depths.keys())
            if common:
                recent = sum(1 for anc in common if da[anc] <= 3 and db_depths[anc] <= 3)
                cache.shared_counts[pk] = (len(common), recent)
            else:
                cache.shared_counts[pk] = (0, 0)

            step += 1
            if step % 200 == 0:
                self.progress.emit(step, total_steps)

        self.progress.emit(total_steps, total_steps)
        if self._save_path:
            cache.save_to_disk(self._save_path, self._save_signature)
        self.finished_cache.emit(cache)
