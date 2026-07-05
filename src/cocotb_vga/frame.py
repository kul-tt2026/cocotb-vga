"""Captured frame container with save/compare helpers."""

from __future__ import annotations

from pathlib import Path
from typing import Optional, Union

import numpy as np
from PIL import Image


class FrameMismatchError(AssertionError):
    """Raised by :meth:`Frame.assert_matches` when pixels differ."""


class Frame:
    """One complete captured frame.

    ``data`` is a ``(height, width, 3)`` uint8 RGB array, ``index`` counts
    complete frames since the capture started, and ``end_cycle`` is the
    sampled pixel-clock cycle at which the frame completed.
    """

    def __init__(self, data: np.ndarray, index: int, end_cycle: Optional[int] = None):
        self.data = data
        self.index = index
        self.end_cycle = end_cycle

    @property
    def width(self) -> int:
        return self.data.shape[1]

    @property
    def height(self) -> int:
        return self.data.shape[0]

    def to_image(self, scale: int = 1) -> Image.Image:
        """Convert to a PIL image, optionally integer-upscaled (nearest
        neighbor) so small test frames remain inspectable."""
        img = Image.fromarray(self.data, "RGB")
        if scale > 1:
            img = img.resize((self.width * scale, self.height * scale), Image.NEAREST)
        return img

    def save(self, path: Union[str, Path], scale: int = 1) -> Path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        self.to_image(scale=scale).save(path)
        return path

    def assert_matches(self, expected, *, tolerance: int = 0,
                       diff_path: Union[str, Path, None] = None) -> None:
        """Compare against a golden reference and raise on mismatch.

        ``expected`` may be another :class:`Frame`, a numpy array, a PIL
        image, or a path to an image file. ``tolerance`` is the maximum
        allowed absolute difference per channel. On mismatch, if
        ``diff_path`` is given, a side-by-side image
        (captured | expected | mismatch mask) is saved there to make the
        failure easy to inspect.
        """
        if isinstance(expected, Frame):
            exp = expected.data
        elif isinstance(expected, np.ndarray):
            exp = expected
        elif isinstance(expected, Image.Image):
            exp = np.asarray(expected.convert("RGB"))
        else:
            exp = np.asarray(Image.open(expected).convert("RGB"))

        if exp.shape != self.data.shape:
            raise FrameMismatchError(
                f"frame {self.index}: shape mismatch: captured "
                f"{self.data.shape[1]}x{self.data.shape[0]}, expected "
                f"{exp.shape[1]}x{exp.shape[0]}"
            )

        diff = np.abs(self.data.astype(np.int16) - exp.astype(np.int16))
        bad = diff.max(axis=2) > tolerance
        n_bad = int(bad.sum())
        if n_bad == 0:
            return

        ys, xs = np.nonzero(bad)
        x0, y0 = int(xs[0]), int(ys[0])
        note = ""
        if diff_path is not None:
            marker = np.zeros_like(self.data)
            marker[..., 0] = np.where(bad, 255, 0)
            gap = np.full((self.height, 2, 3), 128, np.uint8)
            side = np.concatenate([self.data, gap, exp, gap, marker], axis=1)
            note = f"; diff image: {Frame(side, self.index).save(diff_path)}"
        raise FrameMismatchError(
            f"frame {self.index}: {n_bad}/{bad.size} pixels differ "
            f"(max |delta| = {int(diff.max())}, tolerance = {tolerance}); first "
            f"mismatch at (x={x0}, y={y0}): captured "
            f"{tuple(int(v) for v in self.data[y0, x0])}, expected "
            f"{tuple(int(v) for v in exp[y0, x0])}{note}"
        )
