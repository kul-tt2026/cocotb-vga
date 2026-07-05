from cocotb_vga import SVGA_800x600_60, TOY_64x48, VGA_640x480_60


def test_vga_totals():
    t = VGA_640x480_60
    assert t.h_total == 800
    assert t.v_total == 525
    assert t.cycles_per_frame == 420_000
    assert abs(t.refresh_hz - 59.94) < 0.01
    assert t.h_sync_start == 656
    assert t.h_sync_end == 752
    assert t.v_sync_start == 490
    assert t.v_sync_end == 492


def test_svga_polarity():
    assert SVGA_800x600_60.hsync_active == 1
    assert SVGA_800x600_60.vsync_active == 1
    assert SVGA_800x600_60.h_total == 1056
    assert SVGA_800x600_60.v_total == 628


def test_toy_mode_is_small():
    assert TOY_64x48.cycles_per_frame == 76 * 55
    assert TOY_64x48.refresh_hz is None
    assert "toy" in TOY_64x48.describe()
