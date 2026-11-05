import json
import os
import tempfile
import pytest
import formats
from formats import FormatError, format_selector, validate_mp4

def _probe(monkeypatch, payload):
    fd, path = tempfile.mkstemp(suffix=".mp4")
    os.write(fd, b"x")
    os.close(fd)
    class R:
        returncode = 0
        stdout = json.dumps(payload)
        stderr = ""
    monkeypatch.setattr(formats.subprocess, "run", lambda *a, **k: R())
    return path

def _streams(video=None, audio=None):
    return {"streams": [s for s in (video, audio) if s]}

VIDEO_OK = {"codec_type": "video", "codec_name": "h264", "profile": "High",
            "level": 41, "pix_fmt": "yuv420p", "avg_frame_rate": "30/1"}
AUDIO_OK = {"codec_type": "audio", "codec_name": "aac", "profile": "LC"}

def test_selector_contains_device_constraints():
    for selector in (format_selector(720), formats.FORMAT_SELECTOR_FALLBACK):
        assert "height<=720" in selector or "height<=480" in selector
        assert "fps<=30" in selector
        assert "avc1" in selector
        assert "m4a" in selector

def test_accepts_h264_high_41_30fps_aac_lc(monkeypatch):
    validate_mp4(_probe(monkeypatch, _streams(VIDEO_OK, AUDIO_OK)))

@pytest.mark.parametrize("video", [
    {"codec_type": "video", "codec_name": "vp9", "profile": "Profile 0",
     "level": 41, "pix_fmt": "yuv420p", "avg_frame_rate": "30/1"},
    dict(VIDEO_OK, avg_frame_rate="60/1"),          # 720p60
    dict(VIDEO_OK, level=42),                        # High 4.2
    dict(VIDEO_OK, pix_fmt="yuv420p10le"),
    dict(VIDEO_OK, profile="High 4:4:4 Predictive"),
])
def test_rejects_video_not_decodable_by_a5(monkeypatch, video):
    with pytest.raises(FormatError):
        validate_mp4(_probe(monkeypatch, _streams(video, AUDIO_OK)))

def test_rejects_missing_or_non_aac_audio(monkeypatch):
    with pytest.raises(FormatError):
        validate_mp4(_probe(monkeypatch, _streams(VIDEO_OK)))
    with pytest.raises(FormatError):
        validate_mp4(_probe(monkeypatch, _streams(
            VIDEO_OK, {"codec_type": "audio", "codec_name": "opus"})))

def test_rejects_empty_file(monkeypatch, tmp_path):
    p = tmp_path / "empty.mp4"
    p.write_bytes(b"")
    with pytest.raises(FormatError):
        validate_mp4(str(p))

def test_rejects_ffprobe_failure(monkeypatch, tmp_path):
    p = tmp_path / "v.mp4"
    p.write_bytes(b"x")
    class R:
        returncode = 1
        stdout = ""
        stderr = "boom"
    monkeypatch.setattr(formats.subprocess, "run", lambda *a, **k: R())
    with pytest.raises(FormatError):
        validate_mp4(str(p))
