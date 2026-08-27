import os
import re
import subprocess
import json
import tempfile
import time
import threading

from flask import (
    Flask,
    request,
    render_template,
    redirect,
    url_for,
    Response,
    abort,
)

app = Flask(__name__)

YT_DLP_BIN = "yt-dlp"
REQUEST_TIMEOUT = 30
DOWNLOAD_TIMEOUT = 1800

CACHE_DIR = os.path.join(tempfile.gettempdir(), "lazarus_cache")
try:
    os.makedirs(CACHE_DIR, exist_ok=True)
except OSError:
    pass

# yt-dlp a besoin d'un runtime JS (node) pour décoder les signatures YouTube.
YT_DLP_EXTRA = ["--js-runtimes", "node"]

# Format unique tenté : flux combiné si disponible, sinon fusion vidéo+audio.
# Le résultat est toujours un MP4 local (voir download_to_file), ce qui évite
# de proxyfier en direct les flux YouTube (souvent limités/throttlés côté
# serveur et responsables de lectures qui se figent).
DOWNLOAD_FORMAT = (
    "best[ext=mp4][vcodec^=avc1]"
    "/best[ext=mp4]"
    "/bestvideo[ext=mp4][vcodec^=avc1]+bestaudio[ext=m4a]"
    "/bestvideo+bestaudio"
    "/best"
)


def run_yt_dlp(args, timeout=REQUEST_TIMEOUT + 30):
    cmd = [YT_DLP_BIN] + args
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
        )
        out, err = proc.communicate(timeout=timeout)
    except subprocess.TimeoutExpired:
        try:
            proc.kill()
        except Exception:
            pass
        return None, "yt-dlp a expiré (timeout)."
    except FileNotFoundError:
        return None, "yt-dlp n'est pas installé dans le conteneur."
    if proc.returncode != 0:
        return None, (err or "yt-dlp a échoué.").strip()
    return out, None


def clean_cache(max_age=3600):
    try:
        now = time.time()
        for name in os.listdir(CACHE_DIR):
            path = os.path.join(CACHE_DIR, name)
            try:
                if now - os.path.getmtime(path) > max_age:
                    os.remove(path)
            except OSError:
                pass
    except OSError:
        pass


_media_locks = {}
_media_locks_guard = threading.Lock()


def _media_lock(video_id):
    with _media_locks_guard:
        if video_id not in _media_locks:
            _media_locks[video_id] = threading.Lock()
        return _media_locks[video_id]


def download_to_file(video_id):
    # Télécharge (et fusionne si besoin) la vidéo en un MP4 local, puis renvoie
    # son chemin. Renvoie None en cas d'échec. Le fichier est mis en cache pour
    # les lectures suivantes (lecture fiable, sans coupures).
    # Le verrou évite deux téléchargements concurrents pour la même vidéo.
    with _media_lock(video_id):
        clean_cache()
        safe_id = re.sub(r"[^A-Za-z0-9_-]", "", video_id)
        final_path = os.path.join(CACHE_DIR, safe_id + ".mp4")
        if os.path.exists(final_path) and os.path.getsize(final_path) > 0:
            return final_path

        url = "https://www.youtube.com/watch?v=" + video_id
        out_tmpl = os.path.join(CACHE_DIR, safe_id + ".%(ext)s")
        args = [
            "-f", DOWNLOAD_FORMAT,
            "--merge-output-format", "mp4",
            # faststart : place le moov en tête -> lecture progressive et seek
            # possibles sur Safari iOS 9.
            "--postprocessor-args", "ffmpeg:-movflags +faststart",
            "--no-playlist",
            "-o", out_tmpl,
        ] + YT_DLP_EXTRA + [url]
        out, err = run_yt_dlp(args, timeout=DOWNLOAD_TIMEOUT)
        if os.path.exists(final_path) and os.path.getsize(final_path) > 0:
            return final_path
        # Recherche d'un fichier mp4 résiduel si le nom diffère.
        for name in os.listdir(CACHE_DIR):
            if name.startswith(safe_id) and name.endswith(".mp4"):
                p = os.path.join(CACHE_DIR, name)
                if os.path.getsize(p) > 0:
                    return p
        if err:
            return None
        return None


def resolve_media(video_id):
    path = download_to_file(video_id)
    if path:
        return {"type": "file", "path": path}, None
    return None, "Flux indisponible (vidéo ou audio introuvable)."


def search_videos(query, limit=10):
    search_url = "ytsearch%d:%s" % (limit, query)
    out, err = run_yt_dlp(
        ["--flat-playlist", "--dump-json"] + YT_DLP_EXTRA + [search_url]
    )
    if err and not out:
        return None, err
    results = []
    if out:
        for line in out.splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except ValueError:
                continue
            results.append({
                "id": data.get("id", ""),
                "title": data.get("title", "Sans titre"),
                "duration": data.get("duration") or data.get("duration_string") or "",
                "thumbnail": data.get("thumbnail", ""),
            })
    return results, None


def format_duration(value):
    try:
        secs = int(value)
    except (TypeError, ValueError):
        return ""
    if secs <= 0:
        return ""
    m, s = divmod(secs, 60)
    h, m = divmod(m, 60)
    if h > 0:
        return "%d:%02d:%02d" % (h, m, s)
    return "%d:%02d" % (m, s)


app.jinja_env.filters["duration"] = format_duration


@app.route("/")
def index():
    return render_template("index.html", query="", results=None, error=None)


@app.route("/search")
def search():
    query = (request.args.get("q") or "").strip()
    if not query:
        return render_template(
            "index.html", query="", results=[], error="Veuillez saisir un terme de recherche."
        )
    results, err = search_videos(query)
    if err:
        return render_template(
            "index.html", query=query, results=None, error=err
        )
    return render_template(
        "index.html", query=query, results=results, error=None
    )


@app.route("/watch")
def watch():
    video_id = (request.args.get("v") or "").strip()
    if not video_id:
        return redirect(url_for("index"))
    return render_template("watch.html", video_id=video_id, error=None)


@app.route("/check")
def check():
    video_id = (request.args.get("v") or "").strip()
    if not video_id:
        return ("", 400)
    # Prépare la lecture : lance le téléchargement en arrière-plan afin que le
    # flux soit prêt (ou en cours) quand la lecture démarre. Les erreurs réelles
    # sont remontées par l'élément <video> côté client.
    threading.Thread(
        target=download_to_file, args=(video_id,), daemon=True
    ).start()
    return ("", 200)


def serve_file_with_range(path):
    try:
        size = os.path.getsize(path)
    except OSError:
        return Response("Fichier introuvable.", status=500, mimetype="text/plain")

    range_header = request.headers.get("Range")
    match = None
    if range_header:
        match = re.match(r"bytes=(\d*)-(\d*)", range_header.strip())

    if match:
        start_raw, end_raw = match.group(1), match.group(2)
        start = int(start_raw) if start_raw else 0
        end = int(end_raw) if end_raw else size - 1
        if start >= size:
            return Response(
                "Range invalide",
                status=416,
                headers={"Content-Range": "bytes */%d" % size},
            )
        if end >= size:
            end = size - 1
        length = end - start + 1

        def generate_range():
            with open(path, "rb") as f:
                f.seek(start)
                remaining = length
                while remaining > 0:
                    chunk = f.read(min(64 * 1024, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk

        headers = {
            "Content-Range": "bytes %d-%d/%d" % (start, end, size),
            "Accept-Ranges": "bytes",
            "Content-Length": str(length),
            "Content-Type": "video/mp4",
        }
        return Response(generate_range(), status=206, headers=headers)

    def generate_full():
        with open(path, "rb") as f:
            while True:
                chunk = f.read(64 * 1024)
                if not chunk:
                    break
                yield chunk

    headers = {
        "Accept-Ranges": "bytes",
        "Content-Length": str(size),
        "Content-Type": "video/mp4",
    }
    return Response(generate_full(), status=200, headers=headers)


@app.route("/stream")
def stream():
    video_id = (request.args.get("v") or "").strip()
    if not video_id:
        abort(400)

    media, err = resolve_media(video_id)
    if not media:
        return Response(
            "Flux indisponible : " + (err or "erreur inconnue"),
            status=502,
            mimetype="text/plain",
        )

    if media["type"] == "file":
        return serve_file_with_range(media["path"])

    return Response(
        "Flux non géré : " + str(media),
        status=500,
        mimetype="text/plain",
    )


@app.errorhandler(400)
def bad_request(e):
    return "Requête invalide", 400


@app.errorhandler(404)
def not_found(e):
    return "Page introuvable", 404


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=3616, debug=False, threaded=True)
