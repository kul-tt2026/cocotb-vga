"""cocotb monitor that samples VGA signals and assembles frames."""

from __future__ import annotations

import logging
from pathlib import Path
from typing import Optional, Union

from cocotb import start_soon
from cocotb.triggers import ClockCycles, Event, FallingEdge, First, RisingEdge

from .assembler import FrameAssembler
from .frame import Frame
from .timing import VGATiming
from .video import save_gif, save_mp4


class VGACaptureTimeout(Exception):
    """Raised when the expected number of frames does not arrive in time."""


class VGACapture:
    """Background monitor turning VGA signals into :class:`Frame` objects.

    Parameters
    ----------
    clock:
        The pixel clock handle (e.g. ``dut.clk``).
    bus:
        A signal adapter, e.g. :class:`cocotb_vga.TinyVGA` or
        :class:`cocotb_vga.VGASignals`.
    timing:
        The expected :class:`cocotb_vga.VGATiming`.
    out_dir:
        If given, every completed frame is saved there as
        ``{name}_{index:04d}.png`` (scaled by ``png_scale``).
    sample_edge:
        ``"falling"`` (default) samples mid-cycle, safely after outputs
        registered on the rising edge have settled; use ``"rising"`` only if
        your design updates its outputs on the falling edge.
    clk_div / clk_phase:
        For designs that emit one pixel every ``clk_div`` input clocks
        (e.g. a 50 MHz design with an internal /2 pixel clock), sample every
        ``clk_div``-th edge, offset by ``clk_phase``.
    """

    def __init__(self, clock, bus, timing: VGATiming, *,
                 out_dir: Union[str, Path, None] = None,
                 name: str = "vga",
                 sample_edge: str = "falling",
                 clk_div: int = 1,
                 clk_phase: int = 0,
                 save_frames: bool = True,
                 png_scale: int = 1,
                 keep_frames: bool = True):
        if sample_edge not in ("rising", "falling"):
            raise ValueError("sample_edge must be 'rising' or 'falling'")
        if not (0 <= clk_phase < clk_div):
            raise ValueError("clk_phase must be in [0, clk_div)")
        self.timing = timing
        self.name = name
        self.out_dir = Path(out_dir) if out_dir is not None else None
        self.log = logging.getLogger(f"cocotb.vga.{name}")
        self._clock = clock
        self._bus = bus
        self._sample_edge = sample_edge
        self._clk_div = clk_div
        self._clk_phase = clk_phase
        self._save_frames = save_frames
        self._png_scale = png_scale
        self._frame_event = Event()
        self._task = None
        self.assembler = FrameAssembler(
            timing,
            on_frame=self._on_frame,
            on_error=lambda msg: self.log.warning("VGA timing: %s", msg),
            keep_frames=keep_frames,
        )
        if self.out_dir is not None:
            self.out_dir.mkdir(parents=True, exist_ok=True)

    # -- monitor -------------------------------------------------------------

    def start(self) -> "VGACapture":
        if self._task is not None:
            raise RuntimeError("capture already started")
        self.log.info("VGA capture started (%s)", self.timing.describe())
        self._task = start_soon(self._run())
        return self

    def stop(self) -> None:
        if self._task is not None:
            cancel = getattr(self._task, "cancel", None) or self._task.kill
            cancel()
            self._task = None

    async def _run(self):
        edge_cls = FallingEdge if self._sample_edge == "falling" else RisingEdge
        edge = edge_cls(self._clock)
        sample = self._bus.sample
        process = self.assembler.process
        if self._clk_div == 1:
            while True:
                await edge
                process(sample())
        else:
            n = 0
            while True:
                await edge
                if n == self._clk_phase:
                    process(sample())
                n = (n + 1) % self._clk_div

    def _on_frame(self, frame: Frame) -> None:
        if self._save_frames and self.out_dir is not None:
            path = frame.save(self.out_dir / f"{self.name}_{frame.index:04d}.png",
                              scale=self._png_scale)
            self.log.info("captured frame %d -> %s", frame.index, path)
        else:
            self.log.info("captured frame %d", frame.index)
        self._frame_event.set()

    # -- results -------------------------------------------------------------

    @property
    def frames(self) -> list:
        return self.assembler.frames

    @property
    def frame_count(self) -> int:
        return self.assembler.frame_count

    async def wait_for_frames(self, count: int,
                              max_cycles: Optional[int] = None) -> list:
        """Wait until ``count`` complete frames have been captured in total.

        ``max_cycles`` bounds the wait in pixel-clock cycles and defaults to
        two frame periods beyond what is still missing. Raises
        :class:`VGACaptureTimeout` with a diagnosis on expiry.
        """
        asm = self.assembler
        if max_cycles is None:
            missing = max(0, count - asm.frame_count)
            max_cycles = (missing + 2) * self.timing.cycles_per_frame
        deadline = asm.cycles + max_cycles
        tick = max(1, self.timing.h_total * 4)
        while asm.frame_count < count:
            if asm.cycles >= deadline:
                raise VGACaptureTimeout(self._diagnose(count))
            self._frame_event.clear()
            await First(self._frame_event.wait(), ClockCycles(self._clock, tick))
        return list(asm.frames[:count]) if asm.keep_frames else []

    def _diagnose(self, count: int) -> str:
        asm = self.assembler
        if asm.hsync_edges == 0 and asm.vsync_edges == 0:
            hint = ("no sync activity at all - check the pin mapping, reset, "
                    "and that the design is actually driving the outputs")
        elif asm.vsync_edges == 0:
            hint = "hsync toggles but vsync never asserted"
        elif not asm.locked:
            hint = "sync edges seen but never locked"
        else:
            hint = ("frames arrive slower than the timing spec predicts - "
                    "check h/v totals or use clk_div if the design divides "
                    "its clock")
        return (f"timed out waiting for {count} frame(s): {hint}\n" + asm.report())

    def check_timing(self, **kwargs) -> None:
        """See :meth:`FrameAssembler.check_timing`."""
        self.assembler.check_timing(**kwargs)

    def report(self) -> str:
        return self.assembler.report()

    # -- exports -------------------------------------------------------------

    def save_gif(self, path: Union[str, Path, None] = None, *,
                 duration_ms: int = 100, scale: Optional[int] = None) -> Path:
        if path is None:
            if self.out_dir is None:
                raise ValueError("no path given and no out_dir configured")
            path = self.out_dir / f"{self.name}.gif"
        return save_gif(self.frames, path, duration_ms=duration_ms,
                        scale=self._png_scale if scale is None else scale)

    def save_mp4(self, path: Union[str, Path, None] = None, *,
                 fps: Optional[float] = None, scale: Optional[int] = None) -> Path:
        if path is None:
            if self.out_dir is None:
                raise ValueError("no path given and no out_dir configured")
            path = self.out_dir / f"{self.name}.mp4"
        if fps is None:
            fps = self.timing.refresh_hz or 30.0
        return save_mp4(self.frames, path, fps=fps,
                        scale=self._png_scale if scale is None else scale)
