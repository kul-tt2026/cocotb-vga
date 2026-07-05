import numpy as np
import pytest

from cocotb_vga import Frame, FrameMismatchError


def make_frame(fill=(10, 20, 30)):
    data = np.zeros((8, 16, 3), np.uint8)
    data[:] = fill
    return Frame(data, index=0)


def test_save_and_reload_roundtrip(tmp_path):
    frame = make_frame()
    path = frame.save(tmp_path / "f.png")
    frame.assert_matches(path)


def test_save_scaled(tmp_path):
    from PIL import Image

    frame = make_frame()
    path = frame.save(tmp_path / "f.png", scale=4)
    with Image.open(path) as img:
        assert img.size == (64, 32)


def test_assert_matches_accepts_tolerance():
    a = make_frame((100, 100, 100))
    b = make_frame((102, 100, 98))
    a.assert_matches(b.data, tolerance=2)
    with pytest.raises(FrameMismatchError, match="pixels differ"):
        a.assert_matches(b.data, tolerance=1)


def test_assert_matches_writes_diff_image(tmp_path):
    a = make_frame()
    other = a.data.copy()
    other[3, 5] = (200, 0, 0)
    diff_path = tmp_path / "diff.png"
    with pytest.raises(FrameMismatchError, match=r"x=5, y=3"):
        a.assert_matches(other, diff_path=diff_path)
    assert diff_path.exists()


def test_shape_mismatch_message():
    a = make_frame()
    with pytest.raises(FrameMismatchError, match="shape mismatch"):
        a.assert_matches(np.zeros((4, 4, 3), np.uint8))
