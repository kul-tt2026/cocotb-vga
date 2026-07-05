"""cocotb-vga: capture VGA output from a cocotb simulation into image files.

Typical use in a Tiny Tapeout testbench::

    from cocotb_vga import VGACapture, TinyVGA, VGA_640x480_60

    cap = VGACapture(dut.clk, TinyVGA(dut.uo_out), VGA_640x480_60,
                     out_dir="output", name="myproject").start()
    frames = await cap.wait_for_frames(2)
    cap.stop()
    cap.check_timing(require_frames=2)   # raises on sync-timing violations
    cap.save_gif()                       # output/myproject.gif
    frames[0].assert_matches("golden.png")
"""

from .assembler import FrameAssembler, VGATimingError
from .bus import TinyVGA, VGASignals, expand_channel
from .capture import VGACapture, VGACaptureTimeout
from .frame import Frame, FrameMismatchError
from .timing import SVGA_800x600_60, TOY_64x48, VGA_640x480_60, VGATiming
from .video import save_gif, save_mp4

__version__ = "0.1.0"


def verilog_dir() -> str:
    """Directory holding the bundled Verilog sources (``dummy_vga.v``)."""
    from importlib.resources import files

    return str(files("cocotb_vga") / "verilog")


__all__ = [
    "Frame",
    "FrameAssembler",
    "FrameMismatchError",
    "SVGA_800x600_60",
    "TOY_64x48",
    "TinyVGA",
    "VGACapture",
    "VGACaptureTimeout",
    "VGASignals",
    "VGATiming",
    "VGATimingError",
    "VGA_640x480_60",
    "expand_channel",
    "save_gif",
    "save_mp4",
    "verilog_dir",
]
