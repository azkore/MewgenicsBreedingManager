"""Tests for WhatsNewDialog and OnboardingDialog."""
import sys
from pathlib import Path

import pytest

pytest.importorskip("PySide6")

_proj_root = Path(__file__).resolve().parents[1]
_src_dir = _proj_root / "src"
sys.path.insert(0, str(_src_dir))
sys.path.insert(0, str(_proj_root))

from PySide6.QtWidgets import QApplication

from mewgenics.dialogs import WhatsNewDialog, OnboardingDialog

# Ensure a QApplication exists (needed for widget instantiation).
_app = QApplication.instance() or QApplication(sys.argv)


class TestWhatsNewDialog:
    def test_instantiates(self):
        dialog = WhatsNewDialog()
        assert dialog.windowTitle().startswith("What's New")

    def test_custom_version(self):
        dialog = WhatsNewDialog(version="99.0.0")
        assert "99.0.0" in dialog.windowTitle()

    def test_custom_highlights(self):
        dialog = WhatsNewDialog(highlights=["Feature A", "Feature B"])
        # Dialog should still instantiate without error
        assert dialog is not None


class TestOnboardingDialog:
    def test_instantiates(self):
        dialog = OnboardingDialog()
        assert dialog.windowTitle() == "Getting Started"

    def test_has_7_pages(self):
        dialog = OnboardingDialog()
        assert dialog._stack.count() == 7

    def test_navigation_next(self):
        dialog = OnboardingDialog()
        assert dialog._stack.currentIndex() == 0
        dialog._next_page()
        assert dialog._stack.currentIndex() == 1

    def test_navigation_back(self):
        dialog = OnboardingDialog()
        dialog._next_page()
        dialog._next_page()
        assert dialog._stack.currentIndex() == 2
        dialog._previous_page()
        assert dialog._stack.currentIndex() == 1

    def test_back_at_first_page_stays(self):
        dialog = OnboardingDialog()
        dialog._previous_page()
        assert dialog._stack.currentIndex() == 0

    def test_page_label_updates(self):
        dialog = OnboardingDialog()
        assert "1 of 7" in dialog._page_label.text()
        dialog._next_page()
        assert "2 of 7" in dialog._page_label.text()
