"""Pure-Python VGA frame reconstruction from a per-cycle sample stream.

This module contains no cocotb dependency so the reconstruction and timing
checks can be unit-tested without a simulator; :class:`cocotb_vga.VGACapture`
is a thin cocotb wrapper around :class:`FrameAssembler`.

Reconstruction model
--------------------

One sample is processed per pixel-clock cycle. A horizontal position counter
``h`` (0 = first active pixel) free-runs modulo ``h_total`` and is resynced on
every hsync leading edge (which by definition sits at
``h_active + h_front``). A line counter ``v`` increments whenever ``h``
wraps. Vertical lock happens at the first vsync leading edge.

Designs differ in how they align vsync: some toggle it when their line
counter wraps at the start of the active line (typical
``if (hcnt == H_TOTAL-1) vcnt <= vcnt + 1`` code), others align vsync
transitions to hsync leading edges (as VESA specifies). Both are accepted:
after the initial lock the vertical position is advanced purely by hsync,
and vsync edges are only *checked* to land on line ``v_sync_start`` or
``v_sync_start - 1``.

Timing checks performed on every sync pulse (all in pixel-clock cycles):

* ``hsync_period`` — distance between hsync leading edges == ``h_total``
* ``hsync_width`` — hsync pulse width == ``h_sync``
* ``vsync_period`` — distance between vsync leading edges == ``h_total * v_total``
* ``vsync_width`` — vsync pulse width == ``h_total * v_sync``
* ``vsync_alignment`` — vsync edge lands on the expected line
"""

from __future__ import annotations

from typing import Callable, Optional

import numpy as np

from .frame import Frame
from .timing import VGATiming


class VGATimingError(AssertionError):
    """Raised by :meth:`FrameAssembler.check_timing` on timing violations."""


class FrameAssembler:
    def __init__(self, timing: VGATiming, *,
                 on_frame: Optional[Callable[[Frame], None]] = None,
                 on_error: Optional[Callable[[str], None]] = None,
                 keep_frames: bool = True,
                 max_recorded_errors: int = 8):
        self.timing = timing
        self.on_frame = on_frame
        self.on_error = on_error
        self.keep_frames = keep_frames
        self.max_recorded_errors = max_recorded_errors

        self.frames: list[Frame] = []
        self.error_counts: dict[str, int] = {}
        self.recorded_errors: list[tuple[int, str, int, int]] = []

        self.cycles = 0
        self.hsync_edges = 0
        self.vsync_edges = 0
        self.unresolved_samples = 0
        self.unresolved_pixels = 0
        self.locked = False

        self._h: Optional[int] = None
        self._v: Optional[int] = None
        self._prev_hs: Optional[bool] = None
        self._prev_vs: Optional[bool] = None
        self._collecting = False
        self._emitted = 0
        self._last_hs_assert: Optional[int] = None
        self._last_vs_assert: Optional[int] = None
        self._buf = np.zeros((timing.v_active, timing.h_active, 3), np.uint8)

    @property
    def frame_count(self) -> int:
        return self._emitted

    def _error(self, cycle: int, kind: str, expected: int, measured: int) -> None:
        first = kind not in self.error_counts
        self.error_counts[kind] = self.error_counts.get(kind, 0) + 1
        if len(self.recorded_errors) < self.max_recorded_errors:
            self.recorded_errors.append((cycle, kind, expected, measured))
        if first and self.on_error is not None:
            self.on_error(
                f"{kind} at cycle {cycle}: expected {expected}, measured "
                f"{measured} (further {kind} errors counted silently)"
            )

    def process(self, sample) -> Optional[Frame]:
        """Feed one pixel-clock sample; returns a Frame when one completes.

        ``sample`` is ``(hs, vs, r, g, b)`` (sync levels 0/1, colors 0..255)
        or ``None`` for an unresolvable (x/z) cycle.
        """
        t = self.timing
        cycle = self.cycles
        self.cycles = cycle + 1
        completed = None

        if sample is None:
            self.unresolved_samples += 1
            hs, vs, rgb = self._prev_hs, self._prev_vs, None
        else:
            hs_raw, vs_raw, r, g, b = sample
            hs = hs_raw == t.hsync_active
            vs = vs_raw == t.vsync_active
            rgb = (r, g, b)

        hs_edge = (hs is True) and (self._prev_hs is False)
        hs_deassert = (hs is False) and (self._prev_hs is True)
        vs_edge = (vs is True) and (self._prev_vs is False)
        vs_deassert = (vs is False) and (self._prev_vs is True)
        self._prev_hs = hs
        self._prev_vs = vs

        # Horizontal sync: measure, then resync the position counter.
        if hs_edge:
            self.hsync_edges += 1
            if self._last_hs_assert is not None:
                period = cycle - self._last_hs_assert
                if period != t.h_total:
                    self._error(cycle, "hsync_period", t.h_total, period)
            self._last_hs_assert = cycle
            self._h = t.h_sync_start
        elif hs_deassert and self._last_hs_assert is not None:
            width = cycle - self._last_hs_assert
            if width != t.h_sync:
                self._error(cycle, "hsync_width", t.h_sync, width)

        if vs_edge:
            self.vsync_edges += 1
            if self._last_vs_assert is not None:
                period = cycle - self._last_vs_assert
                if period != t.cycles_per_frame:
                    self._error(cycle, "vsync_period", t.cycles_per_frame, period)
            self._last_vs_assert = cycle
        elif vs_deassert and self._last_vs_assert is not None:
            width = cycle - self._last_vs_assert
            if width != t.h_total * t.v_sync:
                self._error(cycle, "vsync_width", t.h_total * t.v_sync, width)

        # Pixel placement.
        if self._h is not None and self._v is not None:
            if self._h < t.h_active and self._v < t.v_active:
                if rgb is None:
                    self.unresolved_pixels += 1
                else:
                    self._buf[self._v, self._h] = rgb

        # Advance position; a vertical wrap completes a frame.
        if self._h is not None:
            self._h += 1
            if self._h == t.h_total:
                self._h = 0
                if self._v is not None:
                    self._v += 1
                    if self._v == t.v_total:
                        self._v = 0
                        if self._collecting:
                            completed = self._emit(cycle)
                        self._collecting = True

        # Vertical lock / alignment check. After the initial lock the line
        # counter free-runs on hsync wraps; vsync edges only validate it.
        if vs_edge:
            if self._v is None:
                # vsync coincident with an hsync edge => the design aligns
                # vsync to hsync (VESA style), which is one line earlier in
                # active-line numbering than counter-wrap alignment.
                self._v = t.v_sync_start - 1 if hs_edge else t.v_sync_start
                self.locked = True
            elif self._v not in (t.v_sync_start, t.v_sync_start - 1):
                self._error(cycle, "vsync_alignment", t.v_sync_start, self._v)
                self._v = t.v_sync_start
                self._collecting = False  # position was wrong: discard frame

        return completed

    def _emit(self, cycle: int) -> Frame:
        frame = Frame(self._buf.copy(), index=self._emitted, end_cycle=cycle)
        self._emitted += 1
        self._buf[:] = 0
        if self.keep_frames:
            self.frames.append(frame)
        if self.on_frame is not None:
            self.on_frame(frame)
        return frame

    def report(self) -> str:
        t = self.timing
        lines = [
            f"VGA capture report ({t.describe()})",
            f"  cycles sampled:     {self.cycles}",
            f"  hsync edges:        {self.hsync_edges}",
            f"  vsync edges:        {self.vsync_edges}",
            f"  locked:             {self.locked}",
            f"  complete frames:    {self._emitted}",
            f"  unresolved samples: {self.unresolved_samples}"
            f" ({self.unresolved_pixels} in the active area)",
        ]
        if not self.error_counts:
            lines.append("  timing errors:      none")
        else:
            lines.append("  timing errors:")
            for kind, count in sorted(self.error_counts.items()):
                examples = ", ".join(
                    f"cycle {c}: expected {e}, measured {m}"
                    for c, k, e, m in self.recorded_errors if k == kind
                )
                lines.append(f"    {kind}: {count}x ({examples})")
        return "\n".join(lines)

    def check_timing(self, *, require_frames: int = 1,
                     allow_unresolved_pixels: int = 0,
                     ignore: tuple = ()) -> None:
        """Raise :class:`VGATimingError` if the capture saw timing problems.

        ``ignore`` lists error kinds (e.g. ``("vsync_alignment",)``) to
        tolerate. ``allow_unresolved_pixels`` permits x/z pixels inside the
        active area (they render black).
        """
        problems = []
        if not self.locked:
            problems.append(
                "never locked to vsync"
                + (" (no hsync edges seen either)" if self.hsync_edges == 0 else "")
            )
        if self._emitted < require_frames:
            problems.append(
                f"only {self._emitted} complete frame(s) captured, "
                f"expected at least {require_frames}"
            )
        for kind, count in sorted(self.error_counts.items()):
            if kind not in ignore:
                problems.append(f"{count}x {kind}")
        if self.unresolved_pixels > allow_unresolved_pixels:
            problems.append(
                f"{self.unresolved_pixels} unresolved (x/z) pixels in the active area"
            )
        if problems:
            raise VGATimingError(
                "VGA timing check failed: " + "; ".join(problems) + "\n" + self.report()
            )
