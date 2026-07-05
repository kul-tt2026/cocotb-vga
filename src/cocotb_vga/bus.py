"""Signal-binding adapters: turn DUT handles into per-cycle VGA samples.

A *bus* object only needs a ``sample()`` method returning either

* ``(hs, vs, r, g, b)`` — sync levels as 0/1 and colors scaled to 8 bit, or
* ``None`` — when a signal is unresolvable (``x``/``z``), e.g. before reset.

The adapters read plain ``handle.value`` attributes, so they work with both
cocotb 1.x (BinaryValue) and 2.x (LogicArray) and can be unit-tested with
fake signal objects.
"""

from __future__ import annotations


def expand_channel(value: int, width: int) -> int:
    """Scale a ``width``-bit color channel value to 8 bits (0..255).

    Uses the standard replication-equivalent scaling ``v * 255 // (2^w - 1)``
    so full scale maps to 255 exactly (e.g. 2-bit values map to
    0, 85, 170, 255). Channels wider than 8 bits keep their top 8 bits.
    """
    if width <= 0:
        raise ValueError("channel width must be >= 1")
    if width >= 8:
        return value >> (width - 8)
    return (value * 255) // ((1 << width) - 1)


class TinyVGA:
    """The Tiny Tapeout `TinyVGA Pmod <https://github.com/mole99/tiny-vga>`_
    pinout, packed on a single 8-bit output (``uo_out``):

    ====  ======
    bit   signal
    ====  ======
    0     R1 (msb)
    1     G1 (msb)
    2     B1 (msb)
    3     VSync
    4     R0 (lsb)
    5     G0 (lsb)
    6     B0 (lsb)
    7     HSync
    ====  ======

    Equivalent to the Verilog
    ``assign uo_out = {hsync, b[0], g[0], r[0], vsync, b[1], g[1], r[1]};``
    used by the TT VGA playground.
    """

    def __init__(self, signal):
        self._signal = signal
        lut = []
        for v in range(256):
            r = (((v >> 0) & 1) << 1) | ((v >> 4) & 1)
            g = (((v >> 1) & 1) << 1) | ((v >> 5) & 1)
            b = (((v >> 2) & 1) << 1) | ((v >> 6) & 1)
            lut.append((
                (v >> 7) & 1,           # hsync level
                (v >> 3) & 1,           # vsync level
                expand_channel(r, 2),
                expand_channel(g, 2),
                expand_channel(b, 2),
            ))
        self._lut = lut

    def sample(self):
        try:
            return self._lut[int(self._signal.value)]
        except ValueError:
            return None  # x/z on the bus


class VGASignals:
    """Generic adapter for designs with separate hsync/vsync/r/g/b signals.

    Channel widths are taken from ``len(signal)`` and can be overridden with
    ``red_width``/``green_width``/``blue_width`` (useful when a channel is a
    slice of a wider bus).
    """

    def __init__(self, *, hsync, vsync, red, green, blue,
                 red_width=None, green_width=None, blue_width=None):
        self._hsync = hsync
        self._vsync = vsync
        self._channels = []
        for sig, width in ((red, red_width), (green, green_width), (blue, blue_width)):
            w = width if width is not None else len(sig)
            lut = tuple(expand_channel(v, w) for v in range(1 << w))
            self._channels.append((sig, lut))

    def sample(self):
        try:
            hs = int(self._hsync.value)
            vs = int(self._vsync.value)
            rgb = tuple(lut[int(sig.value)] for sig, lut in self._channels)
        except ValueError:
            return None  # x/z on at least one signal
        return (hs, vs) + rgb
