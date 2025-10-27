import os
from pathlib import Path
from unittest import mock

import pytest

from src.core.gif_optimizer import (
    optimize_gif_lossy,
    GifOptimizationError,
    is_gifsicle_available,
)


@pytest.fixture()
def sample_gif(make_temp_gif):
    return make_temp_gif(frames=4, size=(12, 10), durations=(80, 90, 100, 110))


def test_optimize_fallback_pillow_when_no_gifsicle(tmp_path, sample_gif):
    src = sample_gif
    out = tmp_path / "out.gif"

    with mock.patch("src.core.gif_optimizer.is_gifsicle_available", return_value=False):
        result = optimize_gif_lossy(src, output_path=str(out), lossy=100, colors=64)

    assert Path(result).exists()
    # Ensure it produced a GIF and not empty
    assert Path(result).stat().st_size > 0


def test_optimize_with_gifsicle_calls_cli_when_available(tmp_path, sample_gif):
    src = sample_gif
    out = tmp_path / "out2.gif"

    # Mock subprocess.run to simulate gifsicle success and also create the temp output
    with mock.patch("src.core.gif_optimizer.is_gifsicle_available", return_value=True), \
         mock.patch("subprocess.run") as m_run, \
         mock.patch("tempfile.TemporaryDirectory") as m_tmpdir:
        # Create a deterministic temp dir and ensure expected temp file exists
        tmpdir_path = tmp_path / "_tmp"
        tmpdir_path.mkdir()
        class _Tmp:
            def __enter__(self_inner):
                return str(tmpdir_path)
            def __exit__(self_inner, exc_type, exc, tb):
                return False
        m_tmpdir.return_value = _Tmp()
        # After calling optimize, our code will write to tmpdir/out2.gif.tmp
        # Prepare by creating that file after the subprocess mock "runs"
        def _run_side_effect(cmd, check=True, stdout=None, stderr=None):
            tmp_out = tmpdir_path / (out.name + ".tmp")
            tmp_out.write_bytes(b"GIF89a")
            return mock.Mock(returncode=0, stdout=b"", stderr=b"")
        m_run.side_effect = _run_side_effect

        result = optimize_gif_lossy(src, output_path=str(out), lossy=120, colors=128)

    assert Path(result) == out
    assert m_run.called
    # Verify command contains lossy and colors flags
    args, kwargs = m_run.call_args
    cmd = args[0]
    assert any(str(part).startswith("--lossy=") for part in cmd)
    assert "--colors" in cmd and "128" in cmd


def test_overwrite_in_place(tmp_path, sample_gif):
    src = Path(sample_gif)
    orig_size = src.stat().st_size
    with mock.patch("src.core.gif_optimizer.is_gifsicle_available", return_value=False):
        result = optimize_gif_lossy(str(src), output_path=None, lossy=60, colors=None, overwrite=True)
    # Same path replaced
    assert result == str(src)
    assert src.exists()
    assert src.stat().st_size > 0
    # Size may change; simply ensure it's still a file


def test_error_on_missing_input(tmp_path):
    with pytest.raises(GifOptimizationError):
        optimize_gif_lossy(str(tmp_path / "missing.gif"), output_path=None)


def test_gifsicle_error_bubbles_as_exception(tmp_path, sample_gif):
    src = sample_gif
    with mock.patch("src.core.gif_optimizer.is_gifsicle_available", return_value=True), \
         mock.patch("subprocess.run", side_effect=Exception("boom")):
        with pytest.raises(GifOptimizationError):
            optimize_gif_lossy(src, output_path=str(tmp_path / "x.gif"), lossy=200)


