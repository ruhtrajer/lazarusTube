"""Sélection de format yt-dlp et validation ffprobe pour l'iPad 2."""

import json
import os
import subprocess

_MAX_LEVEL = 41
_MAX_FPS = 30.0
_VIDEO_CODEC = "h264"
_VIDEO_PROFILES = frozenset({"Baseline", "Main", "High"})
_PIX_FMT = "yuv420p"
_AUDIO_CODEC = "aac"
_AUDIO_PROFILE = "LC"


class FormatError(Exception):
    """Fichier vidéo absent, vide, illisible ou incompatible avec l'appareil."""

    def __init__(self, user_message: str) -> None:
        super().__init__(user_message)
        self.user_message = user_message


def format_selector(max_height: int = 720) -> str:
    """Construit le sélecteur yt-dlp limité à *max_height* et 30 fps."""
    return (
        f"bv*[height<={max_height}][fps<=30][vcodec^=avc1]+ba[ext=m4a]"
        f"/b[height<={max_height}][fps<=30][ext=mp4][vcodec^=avc1]"
        f"/b[height<={max_height}][fps<=30][ext=mp4]"
    )


FORMAT_SELECTOR = format_selector(720)
FORMAT_SELECTOR_FALLBACK = format_selector(480)


def _parse_fps(value: object) -> float | None:
    """Convertit un ``avg_frame_rate`` ffprobe (« num/den ») en nombre."""
    if not isinstance(value, str):
        return None
    try:
        num_text, den_text = value.split("/", 1)
        num = float(num_text)
        den = float(den_text)
    except ValueError:
        return None
    if den == 0:
        return None
    fps = num / den
    if fps <= 0:
        return None
    return fps


def _video_ok(stream: dict) -> bool:
    """Vérifie qu'une piste vidéo est décodable par l'iPad 2."""
    if stream.get("codec_name") != _VIDEO_CODEC:
        return False
    if stream.get("profile") not in _VIDEO_PROFILES:
        return False
    level = stream.get("level")
    if not isinstance(level, int) or level > _MAX_LEVEL:
        return False
    if stream.get("pix_fmt") != _PIX_FMT:
        return False
    fps = _parse_fps(stream.get("avg_frame_rate"))
    return fps is not None and fps <= _MAX_FPS


def _audio_ok(stream: dict) -> bool:
    """Vérifie qu'une piste audio est de l'AAC-LC (profil absent toléré)."""
    if stream.get("codec_name") != _AUDIO_CODEC:
        return False
    profile = stream.get("profile")
    return profile is None or profile == _AUDIO_PROFILE


def validate_mp4(
    path: str | os.PathLike, ffprobe_bin: str = "ffprobe"
) -> None:
    """Lève ``FormatError`` si *path* n'est pas un MP4 lisible par l'iPad 2."""
    try:
        size = os.path.getsize(path)
    except OSError:
        raise FormatError("Fichier vidéo introuvable.") from None
    if size == 0:
        raise FormatError("Fichier vidéo vide.")

    try:
        result = subprocess.run(
            [
                ffprobe_bin,
                "-v",
                "error",
                "-show_entries",
                "stream=codec_name,codec_type,profile,level,pix_fmt,avg_frame_rate",
                "-of",
                "json",
                os.fspath(path),
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
    except (OSError, subprocess.SubprocessError):
        raise FormatError("Impossible de vérifier la vidéo.") from None

    if result.returncode != 0:
        raise FormatError("Impossible de vérifier la vidéo.")

    try:
        payload = json.loads(result.stdout)
    except (TypeError, ValueError):
        raise FormatError("Impossible de vérifier la vidéo.") from None

    if not isinstance(payload, dict):
        raise FormatError("Impossible de vérifier la vidéo.")

    streams = payload.get("streams")
    if not isinstance(streams, list):
        streams = []

    video = next(
        (
            stream
            for stream in streams
            if isinstance(stream, dict) and stream.get("codec_type") == "video"
        ),
        None,
    )
    audio = next(
        (
            stream
            for stream in streams
            if isinstance(stream, dict) and stream.get("codec_type") == "audio"
        ),
        None,
    )

    if video is None or audio is None:
        raise FormatError("Format incompatible avec cet appareil.")
    if not _video_ok(video) or not _audio_ok(audio):
        raise FormatError("Format incompatible avec cet appareil.")
