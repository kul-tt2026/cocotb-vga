# cocotb-vga

Capture VGA output from a [cocotb](https://www.cocotb.org/) simulation into
PNG frames, animated GIFs and MP4s — with cycle-accurate sync-timing checks
and golden-image comparison. Built for [Tiny Tapeout](https://tinytapeout.com)
VGA projects, but works with any design that outputs VGA-style signals.

```
DUT VGA pins ──► TinyVGA / VGASignals ──► VGACapture ──► frame_0000.png
   (hsync, vsync, r, g, b)                    │          frame_0001.png ...
                                              │          anim.gif / anim.mp4
                                              └── timing checks (sync period,
                                                  pulse width, alignment)
```

## Quickstart (Tiny Tapeout project)

```python
import cocotb
from cocotb.clock import Clock
from cocotb_vga import VGACapture, TinyVGA, VGA_640x480_60

@cocotb.test()
async def test_vga(dut):
    cocotb.start_soon(Clock(dut.clk, 40, "ns").start())  # ~25 MHz pixel clock
    dut.rst_n.value = 0
    ...

    cap = VGACapture(dut.clk, TinyVGA(dut.uo_out), VGA_640x480_60,
                     out_dir="output", name="myproject").start()
    frames = await cap.wait_for_frames(2)   # blocks until 2 complete frames
    cap.stop()

    cap.check_timing(require_frames=2)      # raises VGATimingError on violations
    cap.save_gif()                          # output/myproject.gif
    frames[0].assert_matches("golden.png")  # golden-image regression (optional)
```

Every completed frame is also saved automatically to
`out_dir/{name}_{index:04d}.png`, so after a run you can just open the PNGs.

## Signal binding

**`TinyVGA(dut.uo_out)`** — the [TinyVGA Pmod](https://github.com/mole99/tiny-vga)
pinout used by Tiny Tapeout VGA projects:

| uo_out bit | 0  | 1  | 2  | 3  | 4  | 5  | 6  | 7  |
|------------|----|----|----|----|----|----|----|----|
| signal     | R1 | G1 | B1 | VS | R0 | G0 | B0 | HS |

**`VGASignals(hsync=..., vsync=..., red=..., green=..., blue=...)`** — separate
signals of any width; channels are scaled to 8 bit with
`v * 255 // (2**width - 1)` (so 2-bit values map to 0, 85, 170, 255).

## Timings

Presets: `VGA_640x480_60` (800×525 total, negative sync — what TT VGA designs
use), `SVGA_800x600_60` (positive sync), `TOY_64x48` (tiny mode for fast
tests). Custom modes are a dataclass away:

```python
from cocotb_vga import VGATiming
mode = VGATiming("my-mode", h_active=320, h_front=8, h_sync=48, h_back=24,
                 v_active=240, v_front=5, v_sync=1, v_back=17)
```

The simulation clock period is irrelevant — the capture counts cycles, one
pixel per sampled clock edge. If your design divides its input clock (e.g.
50 MHz in, 25 MHz pixel clock), pass `clk_div=2`. Sampling defaults to the
**falling** edge so outputs registered on the rising edge are stable; pass
`sample_edge="rising"` for falling-edge designs.

## What the checker verifies

* `hsync_period` — hsync leading edges exactly `h_total` cycles apart
* `hsync_width` / `vsync_width` — sync pulse widths match the spec
* `vsync_period` — exactly `h_total * v_total` cycles per frame
* `vsync_alignment` — vsync asserts on the expected line. Both common
  conventions are accepted: vsync toggling when the line counter wraps
  (`if (hcnt == H_TOTAL-1) vcnt <= vcnt+1;` style) *and* VESA-style vsync
  aligned to hsync leading edges.
* unresolved (`x`/`z`) pixels inside the active area are counted and fail
  `check_timing()` (pre-reset x/z is fine and ignored).

`cap.report()` returns a human-readable summary; `cap.check_timing()` raises
with that summary attached. `wait_for_frames()` times out with a diagnosis
("no sync activity", "hsync but no vsync", ...) instead of hanging.

## Self-test with the bundled dummy generator

The package ships `verilog/dummy_vga.v`, a parameterized pattern generator
(8 color bars shifting one position per frame) whose expected image is known
pixel-exactly (`cocotb_vga.pattern`). The self-test captures its output
through both signal adapters and compares every pixel:

```sh
pip install -e .[dev]
make -C sim                          # fast 64x48 toy geometry (~seconds)
make -C sim VGA_SELFTEST_TIMING=vga  # one real 640x480@60 frame (~minutes)
```

Frames, GIF and diff images land in `sim/vga_out/`. Reuse the same self-test
from another repo by pointing a Makefile at
`$(python -c 'import cocotb_vga; print(cocotb_vga.verilog_dir())')/dummy_vga.v`
with `COCOTB_TEST_MODULES = cocotb_vga.selftest`.

## Unit tests

The frame reconstruction and timing checks are pure Python
(`FrameAssembler`), tested without a simulator:

```sh
pytest
```

## Video export

`save_gif()` always works (Pillow). `save_mp4()` uses imageio
(`pip install cocotb-vga[video]`) or an `ffmpeg` binary on PATH, and falls
back with a helpful error — GIF is the dependency-free default.

## Requirements

Python ≥ 3.9, numpy, Pillow, cocotb ≥ 1.9 (tested with cocotb 2.0 / Icarus
Verilog). Not published on PyPI — install from source or a git submodule:

```sh
pip install -e path/to/cocotb-vga
```

## License

Apache-2.0
