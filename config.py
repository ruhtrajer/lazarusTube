"""Configuration de LazarusTube, lue depuis l'environnement."""

import os
import shutil
import tempfile
from dataclasses import dataclass


@dataclass(frozen=True)
class Config:
    """Configuration immuable de l'application."""

    cache_dir: str
    max_cache_bytes: int
    max_cache_age: int
    max_concurrent_downloads: int
    search_ttl: int
    search_limit: int
    max_height: int
    request_timeout: int
    download_timeout: int
    log_level: str
    ytdlp_bin: str
    ffmpeg_bin: str
    ffprobe_bin: str
    node_bin: str | None
    thumb_cache_bytes: int
    max_query_length: int


def _int(env: dict, name: str, default: int) -> int:
    """Lit *name* dans *env* et retombe sur *default* si absent ou invalide."""
    value = env.get(name)
    if value is None:
        return default
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


def load_config(env: dict | None = None) -> Config:
    """Construit la configuration depuis *env* (ou ``os.environ``)."""
    if env is None:
        env = os.environ

    cache_dir = env.get("LAZARUS_CACHE_DIR")
    if not cache_dir:
        cache_dir = os.path.join(tempfile.gettempdir(), "lazarus_cache")

    node_bin = env.get("LAZARUS_NODE_BIN")
    if node_bin is None:
        node_bin = shutil.which("node")

    return Config(
        cache_dir=cache_dir,
        max_cache_bytes=_int(env, "LAZARUS_MAX_CACHE_BYTES", 5368709120),
        max_cache_age=_int(env, "LAZARUS_MAX_CACHE_AGE", 604800),
        max_concurrent_downloads=_int(env, "LAZARUS_MAX_CONCURRENT_DOWNLOADS", 2),
        search_ttl=_int(env, "LAZARUS_SEARCH_TTL", 600),
        search_limit=_int(env, "LAZARUS_SEARCH_LIMIT", 10),
        max_height=_int(env, "LAZARUS_MAX_HEIGHT", 720),
        request_timeout=_int(env, "LAZARUS_REQUEST_TIMEOUT", 30),
        download_timeout=_int(env, "LAZARUS_DOWNLOAD_TIMEOUT", 1800),
        log_level=env.get("LAZARUS_LOG_LEVEL", "INFO"),
        ytdlp_bin=env.get("LAZARUS_YTDLP_BIN", "yt-dlp"),
        ffmpeg_bin=env.get("LAZARUS_FFMPEG_BIN", "ffmpeg"),
        ffprobe_bin=env.get("LAZARUS_FFPROBE_BIN", "ffprobe"),
        node_bin=node_bin,
        thumb_cache_bytes=_int(env, "LAZARUS_THUMB_CACHE_BYTES", 209715200),
        max_query_length=_int(env, "LAZARUS_MAX_QUERY_LENGTH", 200),
    )
