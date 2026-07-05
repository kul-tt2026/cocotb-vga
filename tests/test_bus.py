import pytest

from cocotb_vga import TinyVGA, VGASignals, expand_channel


class FakeSignal:
    """Duck-typed stand-in for a cocotb handle."""

    def __init__(self, value=0, width=1):
        self.value = value
        self._width = width

    def __len__(self):
        return self._width


class Unresolvable:
    def __int__(self):
        raise ValueError("contains x/z")


def test_expand_channel():
    assert [expand_channel(v, 1) for v in range(2)] == [0, 255]
    assert [expand_channel(v, 2) for v in range(4)] == [0, 85, 170, 255]
    assert expand_channel(15, 4) == 255
    assert expand_channel(255, 8) == 255
    assert expand_channel(0x3FF, 10) == 255  # top 8 bits of a wide channel


def test_tinyvga_decoding():
    sig = FakeSignal(width=8)
    bus = TinyVGA(sig)

    sig.value = 0b0000_0001  # R1 set -> red = 0b10 -> 170
    assert bus.sample() == (0, 0, 170, 0, 0)

    sig.value = 0b0001_0000  # R0 set -> red = 0b01 -> 85
    assert bus.sample() == (0, 0, 85, 0, 0)

    sig.value = 0b1000_1000  # hsync + vsync, black
    assert bus.sample() == (1, 1, 0, 0, 0)

    sig.value = 0b0111_0111  # full white, syncs low
    assert bus.sample() == (0, 0, 255, 255, 255)


def test_tinyvga_unresolvable_returns_none():
    sig = FakeSignal(Unresolvable(), width=8)
    assert TinyVGA(sig).sample() is None


def test_vgasignals_decoding():
    hs, vs = FakeSignal(1), FakeSignal(0)
    r, g, b = FakeSignal(3, width=2), FakeSignal(0, width=2), FakeSignal(1, width=2)
    bus = VGASignals(hsync=hs, vsync=vs, red=r, green=g, blue=b)
    assert bus.sample() == (1, 0, 255, 0, 85)

    g.value = Unresolvable()
    assert bus.sample() is None


def test_vgasignals_width_override():
    bus = VGASignals(hsync=FakeSignal(0), vsync=FakeSignal(0),
                     red=FakeSignal(7, width=8), green=FakeSignal(0),
                     blue=FakeSignal(0), red_width=3)
    assert bus.sample() == (0, 0, 255, 0, 0)
