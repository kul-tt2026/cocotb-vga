"""Assemble captured frames into animated GIF (no extra deps) or MP4."""

from __future__ import annotations

import shutil
import subprocess
import tempfile
from pathlib import Path
from typing import Sequence, Union

import numpy as np


def _images(frames, scale: int):
    return [f.to_image(scale=scale) for f in frames]


def save_gif(frames: Sequence, path: Union[str, Path], *,
             duration_ms: int = 100, scale: int = 1, loop: int = 0) -> Path:
    """Save frames as an animated GIF (always available, via Pillow)."""
    if not frames:
        raise ValueError("no frames to save")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    imgs = _images(frames, scale)
    imgs[0].save(path, save_all=True, append_images=imgs[1:],
                 duration=duration_ms, loop=loop)
    return path


def save_mp4(frames: Sequence, path: Union[str, Path], *,
             fps: float = 30.0, scale: int = 1) -> Path:
    """Save frames as an MP4 via imageio (``pip install cocotb-vga[video]``)
    or, failing that, an ``ffmpeg`` binary on PATH. Raises RuntimeError if
    neither is available (``save_gif`` always works)."""
    if not frames:
        raise ValueError("no frames to save")
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    # yuv420p (the broadly playable pixel format) needs even dimensions.
    arrays = [np.asarray(f.to_image(scale=scale)) for f in frames]
    h, w = arrays[0].shape[:2]
    pad_h, pad_w = h % 2, w % 2
    if pad_h or pad_w:
        arrays = [np.pad(a, ((0, pad_h), (0, pad_w), (0, 0)), mode="edge")
                  for a in arrays]

    try:
        import imageio.v3 as iio
        iio.imwrite(path, arrays, fps=fps, codec="libx264",
                    pixelformat="yuv420p", plugin="pyav")
        return path
    except Exception:
        pass
    try:
        import imageio
        writer = imageio.get_writer(path, fps=fps, codec="libx264",
                                    pixelformat="yuv420p")
        for a in arrays:
            writer.append_data(a)
        writer.close()
        return path
    except ImportError:
        pass

    ffmpeg = shutil.which("ffmpeg")
    if ffmpeg is None:
        raise RuntimeError(
            "MP4 export needs either `pip install cocotb-vga[video]` or an "
            "ffmpeg binary on PATH; use save_gif() as a dependency-free "
            "alternative"
        )
    with tempfile.TemporaryDirectory() as tmp:
        from PIL import Image
        for i, a in enumerate(arrays):
            Image.fromarray(a).save(Path(tmp) / f"f_{i:06d}.png")
        subprocess.run(
            [ffmpeg, "-y", "-loglevel", "error", "-framerate", str(fps),
             "-i", str(Path(tmp) / "f_%06d.png"),
             "-pix_fmt", "yuv420p", str(path)],
            check=True,
        )
    return path
