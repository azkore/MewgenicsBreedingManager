import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("PySide6")

_proj_root = Path(__file__).resolve().parents[1]
_src_dir = _proj_root / "src"
sys.path.insert(0, str(_src_dir))
sys.path.insert(0, str(_proj_root))

import mewgenics.utils.tags as tags


def test_cat_tag_labels_keep_game_tag_first(monkeypatch):
    monkeypatch.setattr(
        tags,
        "_GAME_TAG_DEFS",
        [
            {
                "id": "game_1",
                "name": "Sorbet",
                "color": "#123456",
                "image_path": "",
                "tooltip": "",
                "source": "game",
            }
        ],
        raising=False,
    )
    monkeypatch.setattr(
        tags,
        "_TAG_DEFS",
        [
            {"id": "tag_b", "name": "Beta", "color": "#222222", "image_path": ""},
            {"id": "tag_a", "name": "Alpha", "color": "#111111", "image_path": ""},
        ],
        raising=False,
    )

    cat = SimpleNamespace(name_tag="game_1", tags=["tag_b", "tag_a"])

    assert tags._cat_tag_labels(cat) == ["Sorbet", "Beta", "Alpha"]


def test_import_tag_image_copies_into_managed_folder(tmp_path, monkeypatch):
    source = tmp_path / "source-icon.png"
    source.write_bytes(b"fake image bytes")
    asset_dir = tmp_path / "tag_assets"
    monkeypatch.setattr(
        tags,
        "_tag_asset_dir",
        lambda: (asset_dir.mkdir(parents=True, exist_ok=True) or asset_dir),
        raising=False,
    )

    copied = tags._import_tag_image(str(source), "tag_1")

    copied_path = Path(copied)
    assert copied_path.parent == asset_dir
    assert copied_path.exists()
    assert copied_path.read_bytes() == source.read_bytes()
