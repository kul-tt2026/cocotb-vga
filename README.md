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

**`TinyVGA(dut.uo_out)`** — the [Tiny VGA Pmod](https://github.com/mole99/tiny-vga)
pinout used by Tiny Tapeout VGA projects. On the TT board, `uo_out[0..3]`
drive Pmod pins 1–4 and `uo_out[4..7]` drive Pmod pins 7–10, so the spec's
pin table maps to:

| uo_out bit | 0  | 1  | 2  | 3  | 4  | 5  | 6  | 7  |
|------------|----|----|----|----|----|----|----|----|
| Pmod pin   | 1  | 2  | 3  | 4  | 7  | 8  | 9  | 10 |
| signal     | R1 | G1 | B1 | VS | R0 | G0 | B0 | HS |

R1/G1/B1 are the most significant color bits, R0/G0/B0 the least
significant, per the Tiny VGA spec.

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

## Testing

The frame reconstruction and timing checks are pure Python
(`FrameAssembler`), tested without a simulator against synthetic scan-out
streams of a reference color-bar pattern (`cocotb_vga.pattern`):

```sh
pip install -e .[dev]
pytest
```

`cocotb_vga.pattern` also gives you `expected_frame()` / `detect_phase()`
so a design that renders the reference pattern in hardware can be verified
pixel-exactly end-to-end.

## Performance and progress

The monitor samples every pixel-clock cycle from Python, which costs on the
order of 100 µs per cycle under Icarus + cocotb — a full 640×480@60 frame is
420,000 cycles, so expect **one to a few minutes per frame** of wall-clock
time. The capture logs a progress line every 100k cycles
(`progress_cycles=`, 0 to disable) and announces the expected cycle count in
`wait_for_frames()`, so a silent simulation means a stopped simulation, not
a slow one.

Icarus tip: pressing Ctrl-C does **not** kill `vvp` — it pauses the
simulation into an interactive `>` prompt until you type `cont` (resume) or
`finish` (quit). Add `SIM_ARGS += -n` to your cocotb Makefile to make
Ctrl-C terminate the simulation instead.

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
