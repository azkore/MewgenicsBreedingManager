"""Stat resolution for scoring — base, total, or total+mutation modes."""

import re

_MUT_STAT_RE = re.compile(r'([+-]?\d+)\s+(STR|CON|INT|DEX|SPD|LCK|CHA)')


def get_mutation_stat_bonuses(cat) -> dict[str, int]:
    """Return {stat_name: total_delta} from visual mutation detail fields."""
    bonuses: dict[str, int] = {}
    for entry in getattr(cat, 'visual_mutation_entries', []) or []:
        detail = entry.get('detail', '') or ''
        for match in _MUT_STAT_RE.finditer(detail):
            delta = int(match.group(1))
            stat = match.group(2)
            bonuses[stat] = bonuses.get(stat, 0) + delta
    return bonuses


def get_cat_stats(cat, use_current: bool, add_mutation_stats: bool = False) -> dict[str, int]:
    """Return the stat dict to use for scoring.

    use_current=True  -> total_stats (base + modifiers/injuries)
    use_current=False -> base_stats
    add_mutation_stats -> parse mutation detail fields and add on top
    """
    if use_current:
        source = getattr(cat, 'total_stats', None) or getattr(cat, 'base_stats', {}) or {}
    else:
        source = getattr(cat, 'base_stats', {}) or {}

    if not add_mutation_stats:
        return source

    bonuses = get_mutation_stat_bonuses(cat)
    if not bonuses:
        return source
    result = dict(source)
    for stat, delta in bonuses.items():
        if stat in result:
            result[stat] = result[stat] + delta
    return result
