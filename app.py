import subprocess
import json
import shlex

from flask import (
    Flask,
    request,
    render_template,
    redirect,
    url_for,
    Response,
    abort,
)
import requests

app = Flask(__name__)

YT_DLP_BIN = "yt-dlp"
REQUEST_TIMEOUT = 30

STREAM_FORMATS = [
    "best[ext=mp4][vcodec^=avc1]",
    "best[ext=mp4]",
    "best",
]


def run_yt_dlp(args):
    cmd = [YT_DLP_BIN] + args
    try:
        proc = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            universal_newlines=True,
        )
        out, err = proc.communicate(timeout=REQUEST_TIMEOUT + 30)
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


def get_direct_url(video_id):
    url = "https://www.youtube.com/watch?v=" + video_id
    last_error = None
    for fmt in STREAM_FORMATS:
        out, err = run_yt_dlp(["-g", "-f", fmt, url])
        if out:
            lines = [line.strip() for line in out.splitlines() if line.strip()]
            if lines:
                return lines[0], None
        last_error = err
    if last_error:
        return None, last_error
    return None, "Aucun flux compatible n'a été trouvé pour cette vidéo."


def search_videos(query, limit=10):
    search_url = "ytsearch%d:%s" % (limit, query)
    out, err = run_yt_dlp(
        ["--flat-playlist", "--dump-json", search_url]
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


@app.route("/stream")
def stream():
    video_id = (request.args.get("v") or "").strip()
    if not video_id:
        abort(400)

    media_url, err = get_direct_url(video_id)
    if not media_url:
        return Response(
            "Flux indisponible : " + (err or "erreur inconnue"),
            status=502,
            mimetype="text/plain",
        )

    headers = {}
    range_header = request.headers.get("Range")
    if range_header:
        headers["Range"] = range_header

    try:
        upstream = requests.get(
            media_url,
            headers=headers,
            stream=True,
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException as exc:
        return Response(
            "Impossible de récupérer le flux : " + str(exc),
            status=502,
            mimetype="text/plain",
        )

    status = upstream.status_code
    excluded = {"transfer-encoding", "connection", "content-encoding"}
    resp_headers = {}
    for key, value in upstream.headers.items():
        if key.lower() in excluded:
            continue
        resp_headers[key] = value

    def generate():
        try:
            for chunk in upstream.iter_content(chunk_size=64 * 1024):
                if chunk:
                    yield chunk
        finally:
            upstream.close()

    return Response(
        generate(),
        status=status,
        headers=resp_headers,
        direct_passthrough=True,
    )


@app.errorhandler(400)
def bad_request(e):
    return "Requête invalide", 400


@app.errorhandler(404)
def not_found(e):
    return "Page introuvable", 404


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000, debug=False, threaded=True)
