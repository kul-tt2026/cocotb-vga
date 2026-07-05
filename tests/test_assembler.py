"""Unit tests for the frame assembler, using the synthetic sample stream
(a pure-Python model of dummy_vga.v). No simulator needed."""

import numpy as np
import pytest

from cocotb_vga import FrameAssembler, TOY_64x48, VGATiming, VGATimingError
from cocotb_vga.pattern import detect_phase, expected_frame, synthetic_stream

from dataclasses import replace


def run(assembler, stream):
    for sample in stream:
        assembler.process(sample)
    return assembler


def assert_clean_pattern(asm, timing, min_frames):
    asm.check_timing(require_frames=min_frames)
    phase = detect_phase(asm.frames[0].data, timing)
    assert phase is not None, "frame 0 does not match any pattern rotation"
    for i, frame in enumerate(asm.frames):
        frame.assert_matches(expected_frame(timing, phase + i))


def test_reconstruction_from_mid_blanking():
    t = TOY_64x48
    asm = run(FrameAssembler(t), synthetic_stream(t, 5, start_h=17, start_v=50, start_phase=3))
    assert asm.locked
    assert asm.frame_count >= 3
    assert not asm.error_counts
    assert asm.unresolved_samples == 0
    assert_clean_pattern(asm, t, 3)


def test_reconstruction_from_mid_active_discards_partial_frame():
    t = TOY_64x48
    asm = run(FrameAssembler(t), synthetic_stream(t, 5, start_h=30, start_v=10))
    # The frame that was already in progress at lock time must not be
    # emitted as a (partial) frame: every emitted frame is complete.
    assert_clean_pattern(asm, t, 3)


def test_vsync_aligned_to_hsync_edges():
    """VESA-style vsync (transitions on hsync leading edges) reconstructs
    identically and raises no alignment errors."""
    t = TOY_64x48
    asm = run(FrameAssembler(t), synthetic_stream(t, 5, vsync_on_hsync=True, start_v=49, start_h=70))
    assert not asm.error_counts
    assert_clean_pattern(asm, t, 3)


def test_vsync_alignment_agrees_between_conventions():
    """Both vsync alignments must place the image identically."""
    t = TOY_64x48
    a = run(FrameAssembler(t), synthetic_stream(t, 4, start_v=50))
    b = run(FrameAssembler(t), synthetic_stream(t, 4, start_v=50, vsync_on_hsync=True))
    pa = detect_phase(a.frames[0].data, t)
    pb = detect_phase(b.frames[0].data, t)
    assert pa is not None and pb is not None
    np.testing.assert_array_equal(a.frames[0].data, expected_frame(t, pa))
    np.testing.assert_array_equal(b.frames[0].data, expected_frame(t, pb))


def test_unresolved_prefix_is_tolerated():
    t = TOY_64x48
    asm = run(FrameAssembler(t), synthetic_stream(t, 4, unresolved_prefix=1000, start_v=20))
    assert asm.unresolved_samples == 1000
    assert asm.unresolved_pixels == 0  # all pre-lock, none in the active area
    assert_clean_pattern(asm, t, 2)


def test_positive_sync_polarity():
    t = replace(TOY_64x48, name="toy-positive", hsync_active=1, vsync_active=1)
    asm = run(FrameAssembler(t), synthetic_stream(t, 4, start_v=50))
    assert not asm.error_counts
    assert_clean_pattern(asm, t, 2)


def test_wrong_line_length_is_detected():
    """Generate with a longer back porch than the checker expects."""
    good = TOY_64x48
    bad = replace(good, name="toy-bad", h_back=good.h_back + 2)
    asm = run(FrameAssembler(good), synthetic_stream(bad, 4, start_v=50))
    assert asm.error_counts.get("hsync_period", 0) > 0
    with pytest.raises(VGATimingError, match="hsync_period"):
        asm.check_timing(require_frames=0)


def test_wrong_sync_width_is_detected():
    good = TOY_64x48
    bad = replace(good, name="toy-bad", h_sync=good.h_sync + 1, h_back=good.h_back - 1)
    asm = run(FrameAssembler(good), synthetic_stream(bad, 4, start_v=50))
    assert asm.error_counts.get("hsync_width", 0) > 0


def test_wrong_frame_height_is_detected():
    good = TOY_64x48
    bad = replace(good, name="toy-bad", v_back=good.v_back + 1)
    asm = run(FrameAssembler(good), synthetic_stream(bad, 4, start_v=50))
    assert asm.error_counts.get("vsync_period", 0) > 0


def test_never_locked_reported():
    t = TOY_64x48
    asm = FrameAssembler(t)
    for _ in range(3 * t.cycles_per_frame):
        asm.process(None)
    assert not asm.locked
    with pytest.raises(VGATimingError, match="never locked"):
        asm.check_timing()
    assert "never locked" not in asm.report()  # report itself is neutral


def test_report_and_error_callback():
    messages = []
    good = TOY_64x48
    bad = replace(good, name="toy-bad", h_back=good.h_back + 2)
    asm = FrameAssembler(good, on_error=messages.append)
    run(asm, synthetic_stream(bad, 3, start_v=50))
    assert messages, "on_error callback should fire on the first error"
    assert "hsync_period" in asm.report()
