"""Self-test: run the capture library against the bundled dummy_vga generator.

Point a cocotb Makefile at ``dummy_vga.v`` (see ``sim/Makefile`` in this
repository) with::

    COCOTB_TOPLEVEL     = dummy_vga
    COCOTB_TEST_MODULES = cocotb_vga.selftest

Both the generic per-signal adapter and the TinyVGA packed-bus adapter are
exercised; captured frames must match the expected color-bar pattern
pixel-exactly and pass the sync-timing checks.

Environment variables:

* ``VGA_SELFTEST_TIMING``: ``toy`` (default, 64x48, seconds) or ``vga``
  (full 640x480@60; the dummy's default parameters). Must match the
  parameter overrides the Makefile passes to the simulator.
* ``VGA_SELFTEST_FRAMES``: frames to capture (default: 4 for toy, 1 for vga).
* ``VGA_SELFTEST_OUT``: output directory (default ``vga_out``).
"""

from __future__ import annotations

import os
from pathlib import Path

import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles

from . import TOY_64x48, VGA_640x480_60, TinyVGA, VGACapture, VGASignals
from .pattern import detect_phase, expected_frame


def _config():
    mode = os.environ.get("VGA_SELFTEST_TIMING", "toy")
    timing = {"toy": TOY_64x48, "vga": VGA_640x480_60}[mode]
    default_frames = 4 if mode == "toy" else 1
    n_frames = int(os.environ.get("VGA_SELFTEST_FRAMES", default_frames))
    out_dir = Path(os.environ.get("VGA_SELFTEST_OUT", "vga_out"))
    png_scale = 8 if mode == "toy" else 1
    return timing, n_frames, out_dir, png_scale


async def _reset(dut):
    clock = Clock(dut.clk, 40, "ns")  # ~25 MHz; the period is irrelevant
    cocotb.start_soon(clock.start())
    dut.rst_n.value = 0
    await ClockCycles(dut.clk, 5)
    dut.rst_n.value = 1


async def _capture_and_check(dut, bus, label):
    timing, n_frames, out_dir, png_scale = _config()
    cap = VGACapture(dut.clk, bus, timing, out_dir=out_dir, name=label,
                     png_scale=png_scale).start()
    frames = await cap.wait_for_frames(n_frames)
    cap.stop()
    cap.check_timing(require_frames=n_frames)

    # The generator's frame counter keeps running between tests, so find
    # which pattern phase the first captured frame corresponds to, then
    # require every frame to advance by exactly one bar - this checks pixel
    # placement and frame ordering with zero tolerance.
    phase = detect_phase(frames[0].data, timing)
    assert phase is not None, (
        f"first captured frame does not match any rotation of the expected "
        f"pattern; inspect the PNGs in {out_dir}/"
    )
    for i, frame in enumerate(frames):
        frame.assert_matches(expected_frame(timing, phase + i),
                             diff_path=out_dir / f"{label}_diff.png")

    gif = cap.save_gif(duration_ms=200)
    dut._log.info("animation written to %s", gif)
    try:
        mp4 = cap.save_mp4(fps=10)
        dut._log.info("video written to %s", mp4)
    except RuntimeError as e:
        dut._log.info("mp4 export skipped: %s", e)
    dut._log.info("%s", cap.report())


@cocotb.test()
async def selftest_tinyvga(dut):
    """Capture via the packed TinyVGA Pmod bus (uo_out)."""
    await _reset(dut)
    await _capture_and_check(dut, TinyVGA(dut.uo_out), "tinyvga")


@cocotb.test()
async def selftest_generic_signals(dut):
    """Capture via separate hsync/vsync/r/g/b signals."""
    await _reset(dut)
    bus = VGASignals(hsync=dut.hsync, vsync=dut.vsync,
                     red=dut.r, green=dut.g, blue=dut.b)
    await _capture_and_check(dut, bus, "generic")
