from __future__ import annotations

import pytest

from campusguard.ui.screen_fit import base_font_pt, compute_fit


@pytest.mark.parametrize(
    "w,h",
    [(1280, 680), (1366, 728), (1440, 800), (1536, 816), (1920, 1040), (2560, 1400), (3440, 1400), (1024, 700), (800, 600)],
)
def test_window_always_fits_inside_the_screen(w, h):
    fit = compute_fit(w, h)
    assert fit.width <= w and fit.height <= h
    assert fit.min_width <= fit.width and fit.min_height <= fit.height
    assert fit.min_width <= w and fit.min_height <= h


def test_small_laptops_maximise_big_screens_do_not():
    assert compute_fit(1366, 728).maximize
    assert compute_fit(1280, 680).maximize
    assert not compute_fit(1920, 1040).maximize
    assert not compute_fit(2560, 1400).maximize


def test_ultrawide_is_not_stretched():
    fit = compute_fit(3440, 1400)
    assert fit.width / fit.height <= 1.86


def test_base_font_tiers():
    assert base_font_pt(1366, 728) == 9
    assert base_font_pt(1920, 1040) == 10
    assert base_font_pt(2560, 1400) == 11


def test_never_exceeds_caps():
    fit = compute_fit(7680, 4320)
    assert fit.width <= 1920 and fit.height <= 1200
