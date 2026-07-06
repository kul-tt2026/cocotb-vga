"""The reference color-bar test pattern.

8 vertical bars (2 bits per channel) that shift one bar position every
frame, so animation is visible in exported GIFs/MP4s and frame ordering
can be asserted. Bar 7 is dark teal rather than black so it remains
distinguishable from blanking.

Used by the library's unit tests (via :func:`synthetic_stream`) and by
example designs that implement this pattern in hardware to demonstrate
pixel-exact verification (bar index = ``x * 8 // h_active``, plus a frame
counter, mod 8).
"""

from __future__ import annotations

from typing import Iterator, Optional

import numpy as np

from .bus import expand_channel
from .timing import VGATiming

#: (r, g, b) with 2 bits per channel, indexed by bar number.
BAR_COLORS_RGB222 = [
    (3, 3, 3),  # white
    (3, 3, 0),  # yellow
    (0, 3, 3),  # cyan
    (0, 3, 0),  # green
    (3, 0, 3),  # magenta
    (3, 0, 0),  # red
    (0, 0, 3),  # blue
    (0, 1, 1),  # dark teal
]


def bar_color(x: int, h_active: int, phase: int) -> tuple:
    """2-bit (r, g, b) of the pattern at active pixel column ``x``."""
    return BAR_COLORS_RGB222[((x * 8) // h_active + phase) % 8]


def expected_frame(timing: VGATiming, phase: int = 0) -> np.ndarray:
    """The full expected active-area image as (v_active, h_active, 3) uint8."""
    x = np.arange(timing.h_active)
    bars = ((x * 8) // timing.h_active + phase) % 8
    colors = np.array(
        [[expand_channel(c, 2) for c in rgb] for rgb in BAR_COLORS_RGB222],
        np.uint8,
    )
    row = colors[bars]
    return np.repeat(row[np.newaxis, :, :], timing.v_active, axis=0)


def detect_phase(frame_data: np.ndarray, timing: VGATiming) -> Optional[int]:
    """Which pattern phase (0..7) a captured frame corresponds to, or None."""
    for phase in range(8):
        if np.array_equal(frame_data, expected_frame(timing, phase)):
            return phase
    return None


def synthetic_stream(timing: VGATiming, n_frames: int, *,
                     start_phase: int = 0,
                     start_h: int = 0,
                     start_v: int = 0,
                     vsync_on_hsync: bool = False,
                     unresolved_prefix: int = 0) -> Iterator:
    """Model of a VGA scan-out of the reference pattern, yielding
    per-cycle samples for unit tests.

    ``vsync_on_hsync`` switches from counter-wrap-aligned vsync (the naive
    FPGA style) to vsync transitions aligned with hsync leading edges (the
    VESA style); the reconstructed image must be identical for both.
    """
    t = timing
    for _ in range(unresolved_prefix):
        yield None
    h = start_h % t.h_total
    v = start_v % t.v_total
    phase = start_phase % 8
    for _ in range(n_frames * t.cycles_per_frame):
        hs_on = t.h_sync_start <= h < t.h_sync_end
        if vsync_on_hsync:
            v_prime = (v + 1) if h >= t.h_sync_start else v
            vs_on = t.v_sync_start <= (v_prime % t.v_total) < t.v_sync_end
        else:
            vs_on = t.v_sync_start <= v < t.v_sync_end
        hs = t.hsync_active if hs_on else 1 - t.hsync_active
        vs = t.vsync_active if vs_on else 1 - t.vsync_active
        if h < t.h_active and v < t.v_active:
            r, g, b = (expand_channel(c, 2) for c in bar_color(h, t.h_active, phase))
        else:
            r = g = b = 0
        yield (hs, vs, r, g, b)
        h += 1
        if h == t.h_total:
            h = 0
            v += 1
            if v == t.v_total:
                v = 0
                phase = (phase + 1) % 8
