"""Validation et extraction des identifiants de vidéos YouTube."""

import re
from urllib.parse import parse_qs, urlsplit

_VIDEO_ID_RE = re.compile(r"^[A-Za-z0-9_-]{11}$")

_YOUTUBE_HOSTS = frozenset({
    "youtu.be",
    "youtube.com",
    "www.youtube.com",
    "m.youtube.com",
    "music.youtube.com",
    "youtube-nocookie.com",
    "www.youtube-nocookie.com",
})

_PATH_PREFIXES = ("/shorts/", "/embed/", "/live/", "/v/")


def is_valid_video_id(value: str) -> bool:
    """Retourne True si *value* est un identifiant YouTube valide."""
    return isinstance(value, str) and _VIDEO_ID_RE.fullmatch(value) is not None


def extract_video_id(text: str) -> str | None:
    """Extrait un identifiant YouTube d'un identifiant brut ou d'une URL."""
    if not isinstance(text, str):
        return None

    value = text.strip()
    if is_valid_video_id(value):
        return value

    try:
        parts = urlsplit(value)
    except ValueError:
        return None

    if parts.scheme not in ("http", "https"):
        return None

    host = parts.hostname
    if host not in _YOUTUBE_HOSTS:
        return None

    path = parts.path.rstrip("/")

    if host == "youtu.be":
        candidate = path.lstrip("/")
        return candidate if is_valid_video_id(candidate) else None

    if path == "/watch":
        candidate = parse_qs(parts.query).get("v", [None])[0]
        return candidate if is_valid_video_id(candidate) else None

    for prefix in _PATH_PREFIXES:
        if path.startswith(prefix):
            candidate = path[len(prefix):]
            return candidate if is_valid_video_id(candidate) else None

    return None
