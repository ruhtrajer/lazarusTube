import json
import pytest
from cache import StreamRegistry
from ytdlp import YtDlpError

def test_index_renders_search_form(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert b'action="/search"' in resp.data

def test_search_renders_results_and_derived_thumbnail(client, services):
    resp = client.get("/search?q=jazz")
    assert resp.status_code == 200
    assert b"Titre" in resp.data
    assert b"/thumb/dQw4w9WgXcQ.jpg" in resp.data
    assert services.ytdlp.search_calls == [("jazz", 10)]

def test_search_uses_cache_then_refresh(client, services):
    client.get("/search?q=jazz")
    client.get("/search?q=jazz")
    assert len(services.ytdlp.search_calls) == 1
    client.get("/search?q=jazz&refresh=1")
    assert len(services.ytdlp.search_calls) == 2

def test_search_error_is_french(client, services):
    services.ytdlp.search_error = YtDlpError("Recherche impossible pour le moment.")
    resp = client.get("/search?q=jazz")
    assert resp.status_code == 200
    assert "Recherche impossible".encode() in resp.data

def test_search_youtube_url_redirects_to_watch(client):
    resp = client.get("/search?q=https://youtu.be/dQw4w9WgXcQ")
    assert resp.status_code == 302
    assert resp.headers["Location"].endswith("/watch?v=dQw4w9WgXcQ")

def test_watch_invalid_id_returns_400(client):
    assert client.get("/watch?v=abc").status_code == 400

def test_watch_reads_meta_from_sidecar_after_restart(client, services, tmp_path):
    services.media.publish("dQw4w9WgXcQ", _tmp(tmp_path), {"title": "Titre disque"})
    resp = client.get("/watch?v=dQw4w9WgXcQ")
    assert resp.status_code == 200
    assert "Titre disque".encode() in resp.data

def _tmp(tmp_path):
    p = tmp_path / "src.mp4"; p.write_bytes(b"x" * 10); return str(p)

def test_status_unknown_is_idle(client):
    resp = client.get("/api/status?v=dQw4w9WgXcQ")
    assert resp.status_code == 200
    assert resp.get_json()["state"] == "idle"

def test_status_invalid_id_is_400_json(client):
    resp = client.get("/api/status?v=abc")
    assert resp.status_code == 400
    assert "error" in resp.get_json()

def test_prepare_invalid_id_is_400_json(client):
    assert client.post("/api/prepare?v=abc").status_code == 400

def test_prepare_ready_file_is_200(client, services, tmp_path):
    services.media.publish("dQw4w9WgXcQ", _tmp(tmp_path), {"title": "T"})
    resp = client.post("/api/prepare?v=dQw4w9WgXcQ")
    assert resp.status_code == 200
    assert resp.get_json()["state"] == "ready"

def test_prepare_starts_job_with_202(client, services):
    resp = client.post("/api/prepare?v=dQw4w9WgXcQ")
    assert resp.status_code == 202
    assert resp.get_json()["state"] in ("queued", "downloading")

def test_stream_without_file_is_425(client):
    assert client.get("/stream?v=dQw4w9WgXcQ").status_code == 425

def test_stream_serves_validated_file_without_job(client, services, tmp_path):
    services.media.publish("dQw4w9WgXcQ", _tmp(tmp_path), {"title": "T"})
    resp = client.get("/stream?v=dQw4w9WgXcQ", headers={"Range": "bytes=0-4"})
    assert resp.status_code == 206
    assert resp.headers["Content-Type"] == "video/mp4"

def test_stream_invalid_id_is_400(client):
    assert client.get("/stream?v=abc").status_code == 400

def test_thumb_returns_404_when_unavailable(client):
    assert client.get("/thumb/dQw4w9WgXcQ.jpg").status_code == 404

def test_thumb_serves_jpeg(client, app):
    app.extensions["lazarus"].thumbs.fetcher = lambda vid, size: b"\xff\xd8\xff" + b"x" * 10
    resp = client.get("/thumb/dQw4w9WgXcQ.jpg?size=hq")
    assert resp.status_code == 200
    assert resp.headers["Content-Type"].startswith("image/jpeg")

def test_thumb_invalid_id_is_404(client):
    assert client.get("/thumb/abc.jpg").status_code == 404

def test_check_route_is_gone(client):
    assert client.get("/check?v=dQw4w9WgXcQ").status_code == 404

def test_healthz_ok(client, monkeypatch):
    monkeypatch.setattr("app.shutil.which", lambda name: "/usr/bin/" + name)
    assert client.get("/healthz").status_code == 200

def test_api_error_is_json(client):
    resp = client.get("/api/status?v=abc")
    assert resp.headers["Content-Type"].startswith("application/json")

def test_security_and_cache_headers(client):
    html = client.get("/")
    assert html.headers["X-Content-Type-Options"] == "nosniff"
    assert html.headers["X-Frame-Options"] == "SAMEORIGIN"
    assert "no-cache" in html.headers["Cache-Control"]
    api = client.get("/api/status?v=dQw4w9WgXcQ")
    assert api.headers["Cache-Control"] == "no-store"

def test_search_query_is_truncated_to_200_chars(client, services):
    client.get("/search?q=" + "a" * 300)
    assert len(services.ytdlp.search_calls[0][0]) == 200

def test_prepare_force_conflict_is_409(client, services, tmp_path):
    services.media.publish("dQw4w9WgXcQ", _tmp(tmp_path), {"title": "T"})
    path = services.media.media_path("dQw4w9WgXcQ")
    services.streams.begin(path)
    try:
        resp = client.post("/api/prepare?v=dQw4w9WgXcQ&force=1")
        assert resp.status_code == 409
        assert "error" in resp.get_json()
    finally:
        services.streams.end(path)
