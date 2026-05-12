"""Unit tests for src/core/video_to_gif.py"""

import sys
from unittest.mock import patch, MagicMock
import pytest

from src.core.video_to_gif import (
    get_ffmpeg_install_info,
    find_ffmpeg,
    is_ffmpeg_available,
    VideoConversionError,
    get_video_info,
)


# ---------------------------------------------------------------------------
# get_ffmpeg_install_info
# ---------------------------------------------------------------------------

class TestGetFfmpegInstallInfo:
    """get_ffmpeg_install_info always returns a dict with expected keys."""

    REQUIRED_KEYS = {"platform", "method", "command", "url", "note"}

    def test_returns_dict_with_required_keys(self):
        info = get_ffmpeg_install_info()
        assert self.REQUIRED_KEYS == info.keys()

    def test_windows_info(self):
        with patch.object(sys, "platform", "win32"):
            info = get_ffmpeg_install_info()
        assert info["platform"] == "Windows"
        assert "winget" in info["command"].lower()
        assert info["command"]  # non-empty

    def test_macos_info(self):
        with patch.object(sys, "platform", "darwin"):
            info = get_ffmpeg_install_info()
        assert info["platform"] == "macOS"
        assert "brew" in info["command"]

    def test_linux_info_fallback(self):
        """On a non-specific Linux distro the command should still be non-empty."""
        mock_distro = MagicMock()
        mock_distro.id.return_value = "unknown_distro"
        with patch.object(sys, "platform", "linux"), \
             patch.dict("sys.modules", {"distro": mock_distro}):
            info = get_ffmpeg_install_info()
        assert info["platform"] == "Linux"
        assert info["command"]  # non-empty fallback

    def test_linux_ubuntu_command(self):
        mock_distro = MagicMock()
        mock_distro.id.return_value = "ubuntu"
        with patch.object(sys, "platform", "linux"), \
             patch.dict("sys.modules", {"distro": mock_distro}):
            info = get_ffmpeg_install_info()
        assert "apt" in info["command"]

    def test_linux_fedora_command(self):
        mock_distro = MagicMock()
        mock_distro.id.return_value = "fedora"
        with patch.object(sys, "platform", "linux"), \
             patch.dict("sys.modules", {"distro": mock_distro}):
            info = get_ffmpeg_install_info()
        assert "dnf" in info["command"]

    def test_linux_arch_command(self):
        mock_distro = MagicMock()
        mock_distro.id.return_value = "arch"
        with patch.object(sys, "platform", "linux"), \
             patch.dict("sys.modules", {"distro": mock_distro}):
            info = get_ffmpeg_install_info()
        assert "pacman" in info["command"]


# ---------------------------------------------------------------------------
# find_ffmpeg / is_ffmpeg_available
# ---------------------------------------------------------------------------

class TestFindFfmpeg:

    def test_returns_path_when_found_on_process_path(self):
        with patch("shutil.which", return_value="/usr/bin/ffmpeg"):
            result = find_ffmpeg()
        assert result == "/usr/bin/ffmpeg"

    def test_returns_none_when_not_found(self):
        with patch("shutil.which", return_value=None), \
             patch("src.core.video_to_gif._windows_registry_path", return_value=""):
            result = find_ffmpeg()
        assert result is None

    def test_is_ffmpeg_available_true(self):
        with patch("src.core.video_to_gif.find_ffmpeg", return_value="/usr/bin/ffmpeg"):
            assert is_ffmpeg_available() is True

    def test_is_ffmpeg_available_false(self):
        with patch("src.core.video_to_gif.find_ffmpeg", return_value=None):
            assert is_ffmpeg_available() is False


# ---------------------------------------------------------------------------
# get_video_info – graceful fallback when ffmpeg absent
# ---------------------------------------------------------------------------

class TestGetVideoInfo:

    def test_returns_error_dict_when_ffmpeg_missing(self, tmp_path):
        """get_video_info returns a dict with an 'error' key when ffmpeg is absent."""
        fake_video = tmp_path / "clip.mp4"
        fake_video.write_bytes(b"\x00" * 16)

        with patch("src.core.video_to_gif.find_ffmpeg", return_value=None):
            info = get_video_info(str(fake_video))

        assert isinstance(info, dict)
        assert "error" in info
        assert info["width"] == 0
        assert info["height"] == 0
