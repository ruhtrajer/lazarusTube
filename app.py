"""Application Flask de LazarusTube.

Le module expose :func:`create_app`, une fabrique qui construit la
configuration, les services (cache, jobs, yt-dlp) et les routes. Les tests
injectent leurs dépendances via ``overrides`` plutôt que de toucher au réseau.
"""

import logging
import os
import shutil
from dataclasses import fields, replace
from types import SimpleNamespace

from flask import (
    Flask,
    Response,
    abort,
    jsonify,
    redirect,
    render_template,
    request,
    url_for,
)

from cache import (
    MediaCache,
    MetaCache,
    SearchCache,
    StreamRegistry,
    ThumbCache,
    fetch_thumbnail,
)
from config import Config, load_config
from ids import extract_video_id, is_valid_video_id
from jobs import ForceRefused, JobRegistry
from streaming import range_response
from ytdlp import YtDlp, YtDlpError

_LOG = logging.getLogger(__name__)

_EMPTY_QUERY = "Veuillez saisir un terme de recherche."
_INVALID_ID = "Identifiant vidéo invalide."
_BUSY_STREAM = "Cette vidéo est en cours de lecture."
_NOT_PREPARED = "Vidéo non préparée."


def format_duration(value) -> str:
    """Formate une durée en secondes (``1:02:03`` / ``12:34`` / ``""``)."""
    try:
        seconds = int(value)
    except (TypeError, ValueError):
        return ""
    if seconds <= 0:
        return ""
    minutes, seconds = divmod(seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours > 0:
        return "%d:%02d:%02d" % (hours, minutes, seconds)
    return "%d:%02d" % (minutes, seconds)


def _compact_number(value: float) -> str:
    """Formate un nombre avec au plus une décimale et une virgule française."""
    text = "%.1f" % value
    if text.endswith(".0"):
        text = text[:-2]
    return text.replace(".", ",")


def format_views(count) -> str:
    """Formate un nombre de vues (``1,2 M`` / ``45 k`` / ``""``)."""
    try:
        views = int(count)
    except (TypeError, ValueError):
        return ""
    if views < 0:
        return ""
    if views >= 1_000_000:
        return _compact_number(views / 1_000_000.0) + " M"
    if views >= 1_000:
        return _compact_number(views / 1_000.0) + " k"
    return str(views)


def create_app(overrides: dict | None = None) -> Flask:
    """Construit et configure l'application Flask.

    ``overrides`` accepte les champs de :class:`config.Config` (appliqués via
    ``dataclasses.replace``) ainsi que les clés de service ``"ytdlp"`` et
    ``"thumbs_fetcher"``.
    """
    overrides = dict(overrides or {})
    config_names = {field.name for field in fields(Config)}
    config_overrides = {
        name: value for name, value in overrides.items() if name in config_names
    }
    cfg = replace(load_config(), **config_overrides)

    level = getattr(logging, str(cfg.log_level).upper(), logging.INFO)
    logging.basicConfig(level=level)

    streams = StreamRegistry()
    media = MediaCache(
        cfg.cache_dir,
        cfg.max_cache_bytes,
        cfg.max_cache_age,
        streams,
    )
    thumbs = ThumbCache(
        root=os.path.join(cfg.cache_dir, "thumbs"),
        max_bytes=cfg.thumb_cache_bytes,
        fetcher=overrides.get("thumbs_fetcher", fetch_thumbnail),
    )
    search_cache = SearchCache(ttl=cfg.search_ttl)
    meta = MetaCache(media)

    if "ytdlp" in overrides:
        ytdlp = overrides["ytdlp"]
    else:
        ytdlp = YtDlp(
            bin=cfg.ytdlp_bin,
            node_bin=cfg.node_bin,
            ffmpeg_bin=cfg.ffmpeg_bin,
            request_timeout=cfg.request_timeout,
            download_timeout=cfg.download_timeout,
            log=_LOG.warning,
        )

    jobs = JobRegistry(
        media,
        ytdlp,
        streams,
        max_concurrent=cfg.max_concurrent_downloads,
        max_height=cfg.max_height,
        log=_LOG.warning,
    )

    services = SimpleNamespace(
        config=cfg,
        media=media,
        streams=streams,
        thumbs=thumbs,
        search_cache=search_cache,
        meta=meta,
        ytdlp=ytdlp,
        jobs=jobs,
    )

    # Le cache peut être absent ou non inscriptible : l'application démarre
    # quand même, et /healthz signale l'anomalie.
    try:
        media.ensure_dirs()
    except OSError:
        _LOG.warning("Impossible de créer les dossiers du cache.", exc_info=True)
    try:
        media.clean_tmp()
    except OSError:
        _LOG.warning("Impossible de nettoyer les téléchargements temporaires.", exc_info=True)
    try:
        media.evict()
    except OSError:
        _LOG.warning("Impossible d'évincer les anciens médias.", exc_info=True)

    app = Flask(__name__)
    app.extensions["lazarus"] = services
    app.jinja_env.filters["duration"] = format_duration
    app.jinja_env.filters["views"] = format_views

    @app.route("/")
    def index():
        return render_template("index.html", query="", results=None, error=None)

    @app.route("/search")
    def search():
        query = (request.args.get("q") or "").strip()[: cfg.max_query_length]
        if not query:
            return render_template(
                "index.html", query="", results=None, error=_EMPTY_QUERY
            )

        video_id = extract_video_id(query)
        if video_id is not None:
            return redirect(url_for("watch", v=video_id))

        refresh = request.args.get("refresh") == "1"
        results = None if refresh else search_cache.get(query)
        if results is None:
            try:
                results = ytdlp.search(query, limit=cfg.search_limit)
            except YtDlpError as exc:
                return render_template(
                    "index.html", query=query, results=None, error=exc.user_message
                )
            search_cache.put(query, results)

        rendered = []
        for result in results or []:
            if not isinstance(result, dict):
                continue
            result_id = result.get("id")
            if not is_valid_video_id(result_id):
                continue
            meta.put(result_id, dict(result))
            item = dict(result)
            item["thumb_url"] = url_for("thumb", video_id=result_id)
            rendered.append(item)

        return render_template(
            "index.html", query=query, results=rendered, error=None
        )

    @app.route("/watch")
    def watch():
        video_id = (request.args.get("v") or "").strip()
        if not is_valid_video_id(video_id):
            abort(400)
        video_meta = meta.get(video_id) or {}
        return render_template(
            "watch.html",
            video_id=video_id,
            meta=video_meta,
            live_status=video_meta.get("live_status"),
        )

    @app.route("/api/prepare", methods=["POST"])
    def api_prepare():
        video_id = (request.args.get("v") or "").strip()
        if not is_valid_video_id(video_id):
            return jsonify({"error": _INVALID_ID}), 400

        retry = request.args.get("retry") == "1"
        force = request.args.get("force") == "1"
        try:
            snapshot = jobs.start(video_id, retry=retry, force=force)
        except ForceRefused:
            return jsonify({"error": _BUSY_STREAM}), 409

        status = 200 if snapshot.get("state") in ("ready", "error") else 202
        return jsonify(snapshot), status

    @app.route("/api/status")
    def api_status():
        video_id = (request.args.get("v") or "").strip()
        if not is_valid_video_id(video_id):
            return jsonify({"error": _INVALID_ID}), 400
        return jsonify(jobs.status(video_id))

    @app.route("/stream")
    def stream():
        video_id = (request.args.get("v") or "").strip()
        if not is_valid_video_id(video_id):
            return Response(_INVALID_ID, status=400, mimetype="text/plain")
        if not media.has(video_id):
            return Response(_NOT_PREPARED, status=425, mimetype="text/plain")

        media.touch(video_id)
        return range_response(
            media.media_path(video_id),
            request.headers.get("Range"),
            streams,
            head=request.method == "HEAD",
        )

    @app.route("/thumb/<video_id>.jpg")
    def thumb(video_id):
        size = request.args.get("size", "mq")
        if not is_valid_video_id(video_id) or size not in ("mq", "hq"):
            abort(404)
        data = thumbs.get(video_id, size)
        if data is None:
            abort(404)
        return Response(data, mimetype="image/jpeg")

    @app.route("/healthz")
    def healthz():
        checks = {
            "ytdlp": shutil.which(cfg.ytdlp_bin) is not None,
            "ffmpeg": shutil.which(cfg.ffmpeg_bin) is not None,
            "ffprobe": shutil.which(cfg.ffprobe_bin) is not None,
            "node": shutil.which(cfg.node_bin or "node") is not None,
            "cache": media.writable(),
        }
        if all(checks.values()):
            return jsonify({"status": "ok", "checks": checks})
        return jsonify({"status": "degraded", "checks": checks}), 503

    def _error_response(code: int, message: str):
        if request.path.startswith("/api/"):
            return jsonify({"error": message}), code
        return (
            render_template("errors/%d.html" % code, message=message),
            code,
        )

    @app.errorhandler(400)
    def bad_request(_error):
        return _error_response(400, "Requête invalide.")

    @app.errorhandler(404)
    def not_found(_error):
        return _error_response(404, "Page introuvable.")

    @app.errorhandler(500)
    def server_error(_error):
        return _error_response(500, "Erreur interne du serveur.")

    @app.after_request
    def add_headers(response):
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["X-Frame-Options"] = "SAMEORIGIN"

        path = request.path
        if path.startswith("/static/"):
            response.headers["Cache-Control"] = "public, max-age=604800"
        elif path.startswith("/api/") or path == "/stream":
            response.headers["Cache-Control"] = "no-store"
        elif response.mimetype == "text/html":
            response.headers["Cache-Control"] = "no-cache"
        return response

    return app


if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=3616, debug=False, threaded=True)
