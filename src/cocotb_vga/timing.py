"""VGA timing parameter definitions and common presets.

All values are expressed in pixel-clock cycles (horizontal) and lines
(vertical). The simulation time base is irrelevant: the capture logic only
counts sampled clock cycles, so any clock period works as long as the design
produces one pixel per sampled cycle (see ``clk_div`` in
:class:`cocotb_vga.VGACapture` for designs that divide their input clock).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional


@dataclass(frozen=True)
class VGATiming:
    """A VGA mode described by its active area, porches and sync pulses.

    ``hsync_active`` / ``vsync_active`` give the logic level of an *asserted*
    sync pulse (0 for the classic negative-polarity 640x480@60 mode).
    """

    name: str
    h_active: int
    h_front: int
    h_sync: int
    h_back: int
    v_active: int
    v_front: int
    v_sync: int
    v_back: int
    hsync_active: int = 0
    vsync_active: int = 0
    pixel_clock_hz: Optional[float] = None

    @property
    def h_total(self) -> int:
        return self.h_active + self.h_front + self.h_sync + self.h_back

    @property
    def v_total(self) -> int:
        return self.v_active + self.v_front + self.v_sync + self.v_back

    @property
    def h_sync_start(self) -> int:
        """Horizontal position (0 = first active pixel) where hsync asserts."""
        return self.h_active + self.h_front

    @property
    def h_sync_end(self) -> int:
        return self.h_sync_start + self.h_sync

    @property
    def v_sync_start(self) -> int:
        """Line number (0 = first active line) where vsync asserts."""
        return self.v_active + self.v_front

    @property
    def v_sync_end(self) -> int:
        return self.v_sync_start + self.v_sync

    @property
    def cycles_per_frame(self) -> int:
        return self.h_total * self.v_total

    @property
    def refresh_hz(self) -> Optional[float]:
        if self.pixel_clock_hz is None:
            return None
        return self.pixel_clock_hz / self.cycles_per_frame

    def describe(self) -> str:
        refresh = f", {self.refresh_hz:.2f} Hz" if self.refresh_hz else ""
        return (
            f"{self.name}: {self.h_active}x{self.v_active} active, "
            f"{self.h_total}x{self.v_total} total"
            f" (h: {self.h_active}+{self.h_front}+{self.h_sync}+{self.h_back},"
            f" v: {self.v_active}+{self.v_front}+{self.v_sync}+{self.v_back})"
            f"{refresh}"
        )


#: Standard 640x480@60 (25.175 MHz pixel clock, negative sync polarity).
#: This is the mode used by Tiny Tapeout VGA projects (usually with a 25 MHz
#: or 25.2 MHz clock, which monitors accept just fine).
VGA_640x480_60 = VGATiming(
    name="640x480@60",
    h_active=640, h_front=16, h_sync=96, h_back=48,
    v_active=480, v_front=10, v_sync=2, v_back=33,
    hsync_active=0, vsync_active=0,
    pixel_clock_hz=25_175_000,
)

#: Standard 800x600@60 (40 MHz pixel clock, positive sync polarity).
SVGA_800x600_60 = VGATiming(
    name="800x600@60",
    h_active=800, h_front=40, h_sync=128, h_back=88,
    v_active=600, v_front=1, v_sync=4, v_back=23,
    hsync_active=1, vsync_active=1,
    pixel_clock_hz=40_000_000,
)

#: Tiny non-standard mode for fast self-tests: 4180 cycles per frame instead
#: of 420000. Must match the parameter overrides in the self-test Makefiles.
TOY_64x48 = VGATiming(
    name="toy-64x48",
    h_active=64, h_front=2, h_sync=4, h_back=6,
    v_active=48, v_front=2, v_sync=2, v_back=3,
    hsync_active=0, vsync_active=0,
)
