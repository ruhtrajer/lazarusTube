# lazarusTube — Refonte P0/P1 + quick wins P2 — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rendre lazarusTube fiable et agréable sur iPad 2 / iOS 9 : préparation visible, formats réellement décodables, résultats illustrés, page de lecture complète, reprise/historique/favoris.

**Architecture:** Refonte structurée autour de `create_app()` et de services injectés dans `app.extensions["lazarus"]`. Les téléchargements passent par un registre de jobs en mémoire (états `idle/queued/downloading/ready/error`), publient atomiquement un MP4 validé + un sidecar JSON, et `/stream` sert tout fichier validé indépendamment du registre. Le front reste en ES5, sans build, avec `base.html`, un CSS partagé et des scripts par page.

**Tech Stack:** Python 3.11, Flask 3, waitress, requests, yt-dlp (non épinglé), ffmpeg/ffprobe, node, pytest, Docker.

**Spec:** `docs/superpowers/specs/2026-11-05-lazarustube-refonte-design.md`

## Global Constraints

- **iOS 9 / Safari 9 strict** : JS ES5 uniquement. Interdits : `const`, `let`, flèches, templates literals, `fetch`, `async`/`await`, classes, modules, `NodeList.forEach`, `Element.closest`.
- **CSS Safari 9** : pas de Grid, variables CSS, `position: sticky`, `gap`, `aspect-ratio`, `clamp()`, `:focus-visible`. Utiliser flex préfixé `-webkit-` ou `inline-block`, `-webkit-line-clamp`, animations `-webkit-`.
- **Vidéo** : H.264 `avc1` + AAC `m4a`, ≤ 720p, ≤ 30 fps, level ≤ 4.1, `yuv420p`, AAC-LC. `playsinline` + `webkit-playsinline`. Pas d'autoplay.
- **Concurrence** : 3 appareils maximum en lecture simultanée ; waitress `--threads=16`.
- **Réseau** : HTTP simple, port 3616, pas de TLS.
- **Cache** : 5 Gio / 7 jours par défaut ; 2 téléchargements simultanés ; miniatures 200 Mio / 30 jours.
- **Messages** : interface et erreurs utilisateur en français ; jamais de stack trace ni de sortie yt-dlp brute côté client.
- **Sécurité** : IDs validés avant tout appel yt-dlp ; `subprocess` avec liste d'arguments ; aucun `shell=True` ; aucune URL arbitraire.
- **Tests** : pytest, aucun réseau, aucun vrai téléchargement. `requirements-dev.txt` = `pytest`.
- **Commits** : un commit par tâche, message en français, préfixe conventionnel (`feat:`, `fix:`, `test:`, `docs:`, `chore:`).

## File Structure

| Fichier | Responsabilité |
|---|---|
| `config.py` | `Config` figée + `load_config(env)` ; seule lecture des variables d'environnement |
| `ids.py` | `is_valid_video_id`, `extract_video_id` |
| `formats.py` | `format_selector`, `FORMAT_SELECTOR*`, `validate_mp4`, `FormatError` |
| `streaming.py` | `parse_range`, `RangeNotSatisfiable`, `range_response` |
| `cache.py` | `MediaCache`, `SearchCache`, `MetaCache`, `ThumbCache`, `StreamRegistry` |
| `ytdlp.py` | `YtDlp.search/download`, `YtDlpError`, `LiveNotSupported` |
| `jobs.py` | `JobRegistry.start/status`, machine à états, sémaphore, fallback 480p |
| `app.py` | `create_app(overrides)`, routes, filtres, erreurs, en-têtes |
| `templates/` | `base.html`, `index.html`, `watch.html`, `library.html`, `errors/*.html` |
| `static/css/app.css` | design system Safari 9 |
| `static/js/app.js` | namespace `Lazarus`, helpers XHR/storage/format |
| `static/js/search.js` | recherches récentes + état de chargement |
| `static/js/watch.js` | préparation, polling, lecteur, reprise, favoris, historique |
| `static/js/library.js` | rendu historique / favoris |
| `tests/` | `conftest.py`, `test_config.py`, `test_ids.py`, `test_formats.py`, `test_streaming.py`, `test_cache.py`, `test_ytdlp.py`, `test_jobs.py`, `test_routes.py`, `test_js_es5.py` |

## Review Focus

Ces cinq cas ne sont pas évidents dans la spec et casseraient l'usage réel ; chacun est couvert par un test dans la tâche qui possède le code.

1. **Reprise après pause, rechargement de page ou redémarrage serveur** : la page de lecture doit retrouver le titre depuis le sidecar et proposer la position sauvegardée, sans retélécharger un fichier déjà prêt. Tests : Tâche 7 (job `ready` reconstruit), Tâche 8 (`/watch` relit le sidecar), Tâche 11 (reprise JS).
2. **URL directe vers un direct ou une premiere** : `/watch` puis `/api/prepare` doivent aboutir à une erreur claire avant tout téléchargement long. Tests : Tâche 6 (`before_dl` tue le processus), Tâche 7 (état `error`, aucun fichier publié).
3. **Vidéo disponible seulement en 720p60 ou VP9** : la validation doit refuser le fichier, le job doit retenter en 480p, puis échouer avec « Format incompatible avec cet appareil » — jamais un écran noir. Tests : Tâche 2 (validation), Tâche 7 (fallback).
4. **Range Safari suffixe (`bytes=-500`) ou invalide (`bytes=999999-`, `bytes=abc`)** : suffixe correct en 206, invalide en 416 avec `Content-Range: bytes */<size>`, multi-range en 200 complet. Tests : Tâche 3.
5. **Échec de miniature** : `/thumb/<id>.jpg` doit répondre 404 sans bloquer la page, et le cache négatif doit éviter de marteler i.ytimg.com. Tests : Tâche 5 (cache négatif), Tâche 8 (route 404), Tâche 9 (placeholder CSS).

---

### Task 1: Configuration et identifiants YouTube

**Files:**
- Create: `config.py`, `ids.py`, `requirements-dev.txt`
- Test: `tests/test_config.py`, `tests/test_ids.py`

**Interfaces:**
- Produces:
  - `config.Config` (dataclass figée) avec `cache_dir: str`, `max_cache_bytes: int`, `max_cache_age: int`, `max_concurrent_downloads: int`, `search_ttl: int`, `search_limit: int`, `max_height: int`, `request_timeout: int`, `download_timeout: int`, `log_level: str`, `ytdlp_bin: str`, `ffmpeg_bin: str`, `ffprobe_bin: str`, `node_bin: str | None`, `thumb_cache_bytes: int`, `max_query_length: int`.
  - `config.load_config(env: dict | None = None) -> Config` (lit `os.environ` si `env is None`).
  - `ids.is_valid_video_id(value: str) -> bool`
  - `ids.extract_video_id(text: str) -> str | None`

- [ ] **Step 1: Écrire les tests qui échouent**

```python
# tests/test_ids.py
import pytest
from ids import extract_video_id, is_valid_video_id

@pytest.mark.parametrize("value,expected", [
    ("dQw4w9WgXcQ", True),
    ("y-JqH1M4Ya8", True),
    ("abc", False),
    ("dQw4w9WgXc", False),          # 10 caractères
    ("dQw4w9WgXcQQ", False),        # 12 caractères
    ("dQw4w9Wg!cQ", False),
    ("", False),
    (None, False),
])
def test_is_valid_video_id(value, expected):
    assert is_valid_video_id(value) is expected

@pytest.mark.parametrize("text,expected", [
    ("dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("  dQw4w9WgXcQ  ", "dQw4w9WgXcQ"),
    ("https://youtu.be/dQw4w9WgXcQ?t=42", "dQw4w9WgXcQ"),
    ("https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=PL1", "dQw4w9WgXcQ"),
    ("https://m.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://music.youtube.com/watch?v=dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://www.youtube-nocookie.com/embed/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://www.youtube.com/shorts/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://www.youtube.com/live/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://www.youtube.com/v/dQw4w9WgXcQ", "dQw4w9WgXcQ"),
    ("https://example.com/watch?v=dQw4w9WgXcQ", None),
    ("jazz français", None),
    ("", None),
])
def test_extract_video_id(text, expected):
    assert extract_video_id(text) == expected
```

```python
# tests/test_config.py
import os
from config import load_config

def test_defaults(monkeypatch, tmp_path):
    for name in list(os.environ):
        if name.startswith("LAZARUS_"):
            monkeypatch.delenv(name)
    monkeypatch.setenv("LAZARUS_CACHE_DIR", str(tmp_path))
    cfg = load_config()
    assert cfg.cache_dir == str(tmp_path)
    assert cfg.max_cache_bytes == 5368709120
    assert cfg.max_cache_age == 604800
    assert cfg.max_concurrent_downloads == 2
    assert cfg.search_ttl == 600
    assert cfg.search_limit == 10
    assert cfg.max_height == 720
    assert cfg.request_timeout == 30
    assert cfg.download_timeout == 1800
    assert cfg.thumb_cache_bytes == 209715200
    assert cfg.max_query_length == 200

def test_overrides():
    cfg = load_config({"LAZARUS_MAX_CACHE_BYTES": "1000",
                       "LAZARUS_MAX_CONCURRENT_DOWNLOADS": "1",
                       "LAZARUS_NODE_BIN": "/usr/bin/node"})
    assert cfg.max_cache_bytes == 1000
    assert cfg.max_concurrent_downloads == 1
    assert cfg.node_bin == "/usr/bin/node"

def test_invalid_int_falls_back_to_default():
    cfg = load_config({"LAZARUS_MAX_CACHE_BYTES": "beaucoup"})
    assert cfg.max_cache_bytes == 5368709120
```

- [ ] **Step 2: Lancer les tests pour vérifier l'échec**

Run: `pytest tests/test_ids.py tests/test_config.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'ids'` / `config`).

- [ ] **Step 3: Implémenter `ids.py` et `config.py`**

`ids.py` : regex `^[A-Za-z0-9_-]{11}$` ; `is_valid_video_id` retourne `False` si la valeur n'est pas une chaîne ; `extract_video_id` retire les espaces, accepte un ID brut, puis analyse l'URL avec `urllib.parse.urlsplit`. Hôtes acceptés : `youtu.be`, `youtube.com`, `www.youtube.com`, `m.youtube.com`, `music.youtube.com`, `youtube-nocookie.com`, `www.youtube-nocookie.com`. Chemins : `/watch` (paramètre `v`), `/shorts/<id>`, `/embed/<id>`, `/live/<id>`, `/v/<id>`. Ignorer `list` et `t`. Toute autre URL ou texte → `None`. Ne jamais construire d'URL yt-dlp à partir de l'entrée brute.

`config.py` : `Config` en `@dataclass(frozen=True)`. `load_config` lit chaque variable via un helper `_int(name, default)` qui retombe sur le défaut si la valeur est absente ou non entière. `node_bin` = `LAZARUS_NODE_BIN` si défini, sinon `shutil.which("node")`. Défauts : ceux de la table §17 de la spec ; `cache_dir` = `os.path.join(tempfile.gettempdir(), "lazarus_cache")`.

- [ ] **Step 4: Relancer les tests**

Run: `pytest tests/test_ids.py tests/test_config.py -v`
Expected: PASS (tous les cas).

- [ ] **Step 5: Commit**

Créer `requirements-dev.txt` avec `pytest` sur une ligne.

```bash
git add config.py ids.py requirements-dev.txt tests/test_config.py tests/test_ids.py
git commit -m "feat: configuration et validation des identifiants YouTube"
```

---

### Task 2: Sélecteur de format et validation ffprobe

**Files:**
- Create: `formats.py`
- Test: `tests/test_formats.py`

**Interfaces:**
- Consumes: rien.
- Produces:
  - `formats.FormatError(Exception)` avec un attribut `user_message: str`.
  - `formats.format_selector(max_height: int = 720) -> str`
  - `formats.FORMAT_SELECTOR: str` (= `format_selector(720)`)
  - `formats.FORMAT_SELECTOR_FALLBACK: str` (= `format_selector(480)`)
  - `formats.validate_mp4(path: str | os.PathLike, ffprobe_bin: str = "ffprobe") -> None` — lève `FormatError` si le fichier n'est pas décodable par l'iPad 2.

- [ ] **Step 1: Écrire les tests qui échouent**

```python
# tests/test_formats.py
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
```

- [ ] **Step 2: Lancer le test pour vérifier l'échec**

Run: `pytest tests/test_formats.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'formats'`).

- [ ] **Step 3: Implémenter `formats.py`**

`format_selector(h)` retourne exactement :

```
bv*[height<=H][fps<=30][vcodec^=avc1]+ba[ext=m4a]
/b[height<=H][fps<=30][ext=mp4][vcodec^=avc1]
/b[height<=H][fps<=30][ext=mp4]
```

`validate_mp4` :
1. `os.path.getsize` dans un `try/except OSError` → `FormatError("Fichier vidéo introuvable.")` ; taille 0 → `FormatError("Fichier vidéo vide.")`.
2. `subprocess.run([ffprobe_bin, "-v", "error", "-show_entries", "stream=codec_name,codec_type,profile,level,pix_fmt,avg_frame_rate", "-of", "json", path], capture_output=True, text=True, timeout=30)`.
3. returncode ≠ 0 ou JSON invalide → `FormatError("Impossible de vérifier la vidéo.")`.
4. Exiger une piste vidéo `h264`, profil dans `{"Baseline", "Main", "High"}`, `level <= 41`, `avg_frame_rate` parsé (`num/den`, division par zéro → refus) `<= 30`, `pix_fmt == "yuv420p"`.
5. Exiger une piste audio `aac` avec profil absent ou `LC`.
6. Sinon `FormatError("Format incompatible avec cet appareil.")`.

- [ ] **Step 4: Relancer le test**

Run: `pytest tests/test_formats.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add formats.py tests/test_formats.py
git commit -m "feat: sélection 720p30 H.264 et validation ffprobe"
```

---

### Task 3: Réponses HTTP Range pour Safari 9

**Files:**
- Create: `streaming.py`
- Test: `tests/test_streaming.py`

**Interfaces:**
- Consumes: rien (le registre est duck-typé : `begin(path)` / `end(path)`).
- Produces:
  - `streaming.RangeNotSatisfiable(Exception)` avec `size: int`.
  - `streaming.parse_range(header: str | None, size: int) -> tuple[int, int] | None` — `None` = réponse 200 complète ; lève `RangeNotSatisfiable` pour un range invalide.
  - `streaming.range_response(path: str, range_header: str | None, registry=None, head: bool = False) -> flask.Response` — 200/206/416, blocs de 64 Kio, appelle `registry.begin(path)` / `registry.end(path)`.

- [ ] **Step 1: Écrire les tests qui échouent**

```python
# tests/test_streaming.py
import pytest
from flask import Flask
from streaming import RangeNotSatisfiable, parse_range, range_response

@pytest.mark.parametrize("header,expected", [
    (None, None),
    ("", None),
    ("bytes=0-99", (0, 99)),
    ("bytes=100-", (100, 999)),
    ("bytes=-100", (900, 999)),
    ("bytes=0-0", (0, 0)),
    ("bytes=0-9999", (0, 999)),          # fin bornée à size-1
    ("bytes=0-10,20-30", None),          # multi-range -> 200 complet
])
def test_parse_range_valid(header, expected):
    assert parse_range(header, 1000) == expected

@pytest.mark.parametrize("header", [
    "bytes=1000-",       # start >= size
    "bytes=2000-3000",
    "bytes=500-100",     # start > end
    "bytes=-0",
    "bytes=-",           # ni début ni fin
    "bytes=abc",
    "items=0-10",
])
def test_parse_range_invalid_raises(header):
    with pytest.raises(RangeNotSatisfiable) as exc:
        parse_range(header, 1000)
    assert exc.value.size == 1000

@pytest.fixture
def client():
    app = Flask(__name__)
    return app.test_client()

@pytest.fixture
def media(tmp_path):
    p = tmp_path / "v.mp4"
    p.write_bytes(bytes(range(256)) * 4)   # 1024 octets
    return str(p)

class Registry:
    def __init__(self):
        self.events = []
    def begin(self, path):
        self.events.append(("begin", path))
    def end(self, path):
        self.events.append(("end", path))

def test_suffix_range_returns_206(client, media):
    reg = Registry()
    with client.application.test_request_context("/stream", headers={"Range": "bytes=-100"}):
        resp = range_response(media, "bytes=-100", reg)
        assert resp.status_code == 206
        assert resp.headers["Content-Range"] == "bytes 924-1023/1024"
        assert resp.headers["Content-Length"] == "100"
        assert resp.headers["Accept-Ranges"] == "bytes"
        body = b"".join(resp.response)
        assert len(body) == 100
    assert reg.events[0][0] == "begin" and reg.events[-1][0] == "end"

def test_invalid_range_returns_416(client, media):
    with client.application.test_request_context("/stream", headers={"Range": "bytes=999999-"}):
        resp = range_response(media, "bytes=999999-")
        assert resp.status_code == 416
        assert resp.headers["Content-Range"] == "bytes */1024"

def test_head_has_headers_without_body(client, media):
    with client.application.test_request_context("/stream", method="HEAD"):
        resp = range_response(media, None, head=True)
        assert resp.status_code == 200
        assert resp.headers["Content-Length"] == "1024"
        assert resp.get_data() == b""

def test_missing_file_returns_404(client, tmp_path):
    with client.application.test_request_context("/stream"):
        assert range_response(str(tmp_path / "absent.mp4"), None).status_code == 404
```

- [ ] **Step 2: Lancer le test pour vérifier l'échec**

Run: `pytest tests/test_streaming.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'streaming'`).

- [ ] **Step 3: Implémenter `streaming.py`**

Règles de `parse_range` : header absent/vide → `None` ; virgule → `None` ; sinon exiger `^bytes=(\d*)-(\d*)$` ; les deux bornes vides → `RangeNotSatisfiable` ; `start > end` → `RangeNotSatisfiable` ; `start >= size` → `RangeNotSatisfiable` ; suffixe `-N` avec N=0 → `RangeNotSatisfiable`, sinon `(max(0, size-N), size-1)` ; `end` borné à `size-1`. `size <= 0` → `RangeNotSatisfiable`.

`range_response` : `os.path.getsize` (OSError → 404) ; `parse_range` dans un `try/except RangeNotSatisfiable` → 416 + `Content-Range: bytes */<size>` ; générateur `_iter_file(path, start, length)` lisant 64 Kio ; en-têtes `Accept-Ranges`, `Content-Length`, `Content-Type: video/mp4`, `Cache-Control: no-store`, `Content-Range` en 206. `head=True` → `Response(b"", status=..., headers=...)`. Si `registry` fourni, appeler `begin` avant la réponse et `end` dans un `finally` du générateur (utiliser `stream_with_context` si nécessaire, sinon un générateur qui ferme via `try/finally`).

- [ ] **Step 4: Relancer le test**

Run: `pytest tests/test_streaming.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add streaming.py tests/test_streaming.py
git commit -m "feat: réponses Range 200/206/416 compatibles Safari 9"
```

---

### Task 4: Cache média, caches mémoire et registre de flux

**Files:**
- Create: `cache.py`
- Test: `tests/test_cache.py`

**Interfaces:**
- Consumes: rien.
- Produces:
  - `cache.StreamRegistry()` : `begin(path: str) -> None`, `end(path: str) -> None`, `is_active(path: str) -> bool` (thread-safe).
  - `cache.MediaCache(root: str, max_bytes: int, max_age: int, registry: StreamRegistry)` — expose les attributs `root: str` et `registry: StreamRegistry` :
    - `ensure_dirs() -> None` (crée `media/` et `tmp/`)
    - `media_path(video_id) -> str`, `meta_path(video_id) -> str`
    - `has(video_id) -> bool` (fichier présent, taille > 0)
    - `publish(video_id, tmp_path, meta: dict) -> str` (publication atomique MP4 puis sidecar)
    - `read_meta(video_id) -> dict | None`
    - `touch(video_id) -> None`
    - `delete(video_id) -> bool` (refuse si le fichier est actif)
    - `evict() -> None`
    - `clean_tmp(max_age: int = 3600) -> None`
    - `writable() -> bool`, `free_bytes() -> int`
  - `cache.SearchCache(ttl: int = 600, max_entries: int = 100, clock=time.time)` : `get(key) -> list | None`, `put(key, results) -> None`.
  - `cache.MetaCache(media: MediaCache, ttl: int = 3600, max_entries: int = 200, clock=time.time)` : `get(video_id) -> dict | None`, `put(video_id, meta) -> None`.

- [ ] **Step 1: Écrire les tests qui échouent**

```python
# tests/test_cache.py
import json
import os
import time
from cache import MediaCache, MetaCache, SearchCache, StreamRegistry

def make_media(tmp_path, max_bytes=10_000, max_age=604800):
    reg = StreamRegistry()
    return MediaCache(str(tmp_path), max_bytes, max_age, reg), reg

def write_tmp(tmp_path, name="dl.mp4", data=b"video"):
    p = tmp_path / name
    p.write_bytes(data)
    return str(p)

def test_publish_writes_mp4_and_sidecar_atomically(tmp_path):
    media, _ = make_media(tmp_path)
    media.ensure_dirs()
    final = media.publish("dQw4w9WgXcQ", write_tmp(tmp_path), {"title": "T", "duration": 3})
    assert final == media.media_path("dQw4w9WgXcQ")
    assert media.has("dQw4w9WgXcQ")
    sidecar = json.loads(open(media.meta_path("dQw4w9WgXcQ")).read())
    assert sidecar["title"] == "T"
    assert "cached_at" in sidecar

def test_meta_survives_new_instance(tmp_path):
    media, _ = make_media(tmp_path)
    media.ensure_dirs()
    media.publish("dQw4w9WgXcQ", write_tmp(tmp_path), {"title": "Persistant"})
    restarted, _ = make_media(tmp_path)
    assert restarted.read_meta("dQw4w9WgXcQ")["title"] == "Persistant"

def test_evicts_oldest_by_size_but_keeps_active(tmp_path):
    media, reg = make_media(tmp_path, max_bytes=250)
    media.ensure_dirs()
    for vid in ("aaaaaaaaaaa", "bbbbbbbbbbb", "ccccccccccc"):
        media.publish(vid, write_tmp(tmp_path, vid + ".mp4", b"x" * 100), {"title": vid})
    old = time.time() - 1000
    os.utime(media.media_path("aaaaaaaaaaa"), (old, old))
    os.utime(media.media_path("bbbbbbbbbbb"), (old + 10, old + 10))
    reg.begin(media.media_path("aaaaaaaaaaa"))     # le plus ancien est en lecture
    media.evict()
    assert media.has("aaaaaaaaaaa")                # protégé
    assert not media.has("bbbbbbbbbbb")            # évincé
    assert not os.path.exists(media.meta_path("bbbbbbbbbbb"))

def test_evicts_by_age(tmp_path):
    media, _ = make_media(tmp_path, max_age=10)
    media.ensure_dirs()
    media.publish("aaaaaaaaaaa", write_tmp(tmp_path), {"title": "A"})
    old = time.time() - 100
    os.utime(media.media_path("aaaaaaaaaaa"), (old, old))
    media.evict()
    assert not media.has("aaaaaaaaaaa")

def test_delete_refuses_active_file(tmp_path):
    media, reg = make_media(tmp_path)
    media.ensure_dirs()
    media.publish("aaaaaaaaaaa", write_tmp(tmp_path), {"title": "A"})
    reg.begin(media.media_path("aaaaaaaaaaa"))
    assert media.delete("aaaaaaaaaaa") is False
    reg.end(media.media_path("aaaaaaaaaaa"))
    assert media.delete("aaaaaaaaaaa") is True

def test_search_cache_ttl_and_lru():
    now = [1000.0]
    cache = SearchCache(ttl=10, max_entries=2, clock=lambda: now[0])
    cache.put("a", [1])
    assert cache.get("a") == [1]
    now[0] += 11
    assert cache.get("a") is None
    cache.put("b", [2]); cache.put("c", [3]); cache.put("d", [4])
    assert cache.get("b") is None and cache.get("d") == [4]

def test_meta_cache_reads_sidecar_and_expires(tmp_path):
    now = [1000.0]
    media, _ = make_media(tmp_path)
    media.ensure_dirs()
    media.publish("aaaaaaaaaaa", write_tmp(tmp_path), {"title": "Disque"})
    meta = MetaCache(media, ttl=10, clock=lambda: now[0])
    assert meta.get("aaaaaaaaaaa")["title"] == "Disque"
    now[0] += 11
    assert meta.get("aaaaaaaaaaa")["title"] == "Disque"   # relu du disque
    meta.put("aaaaaaaaaaa", {"title": "Mémoire"})
    assert meta.get("aaaaaaaaaaa")["title"] == "Mémoire"
```

- [ ] **Step 2: Lancer le test pour vérifier l'échec**

Run: `pytest tests/test_cache.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'cache'`).

- [ ] **Step 3: Implémenter `cache.py`**

`StreamRegistry` : `threading.Lock` + `dict[str, int]` ; `end` ne descend pas sous 0.

`MediaCache` : créer les dossiers dans `ensure_dirs()` (appelée au démarrage). `publish` écrit le sidecar dans un fichier temporaire du même dossier puis `os.replace` ; `os.replace(tmp_path, media_path)` ; `os.utime(media_path)` ; ordre MP4 puis sidecar. Le sidecar contient `meta` + `"cached_at": time.time()`. `read_meta` tolère JSON invalide → `None`. `evict` : lister `media/*.mp4`, trier par `st_mtime` croissant, total = somme des tailles ; supprimer tant que `total > max_bytes` ou `now - mtime > max_age`, en sautant `registry.is_active(path)`. Supprimer le sidecar avec le MP4. `free_bytes` = `shutil.disk_usage(root).free`. `writable` = création/suppression d'un fichier `.probe` dans `root` avec `try/except OSError`.

`SearchCache` : `OrderedDict`, `get` vérifie l'expiration (`clock() - ts <= ttl`), `move_to_end` sur hit ; `put` supprime la plus ancienne clé au-delà de `max_entries`.

`MetaCache` : `OrderedDict` mémoire avec horodatage ; sur miss mémoire, `media.read_meta` ; un hit disque est remis en mémoire (sans réécrire le fichier).

- [ ] **Step 4: Relancer le test**

Run: `pytest tests/test_cache.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add cache.py tests/test_cache.py
git commit -m "feat: cache média atomique, caches mémoire et registre de flux"
```

---

### Task 5: Cache disque des miniatures

**Files:**
- Create: `cache.py` (ajout `ThumbCache` et `fetch_thumbnail`)
- Test: `tests/test_cache.py` (ajout des tests `ThumbCache`)

**Interfaces:**
- Consumes: rien.
- Produces:
  - `cache.fetch_thumbnail(video_id: str, size: str) -> bytes | None` — `size` ∈ `{"mq", "hq"}` ; `requests.get` sur `https://i.ytimg.com/vi/<id>/mqdefault.jpg` (ou `hqdefault.jpg`), timeout 10, `Content-Type` `image/*`, taille ≤ 200 Kio.
  - `cache.ThumbCache(root: str, max_bytes: int, ttl: int = 2592000, negative_ttl: int = 300, fetcher=fetch_thumbnail, clock=time.time)` :
    - `get(video_id: str, size: str = "mq") -> bytes | None`
    - `evict() -> None`

- [ ] **Step 1: Écrire les tests qui échouent**

```python
# tests/test_cache.py (à la suite)
from cache import ThumbCache

JPEG = b"\xff\xd8\xff\xe0" + b"x" * 100

def test_thumb_cache_hit_avoids_refetch(tmp_path):
    calls = []
    def fetcher(vid, size):
        calls.append((vid, size))
        return JPEG
    now = [1000.0]
    tc = ThumbCache(str(tmp_path), 1_000_000, fetcher=fetcher, clock=lambda: now[0])
    assert tc.get("aaaaaaaaaaa") == JPEG
    assert tc.get("aaaaaaaaaaa") == JPEG
    assert calls == [("aaaaaaaaaaa", "mq")]
    assert (tmp_path / "aaaaaaaaaaa-mq.jpg").exists()

def test_thumb_failure_is_negatively_cached(tmp_path):
    calls = []
    def fetcher(vid, size):
        calls.append(vid)
        return None
    now = [1000.0]
    tc = ThumbCache(str(tmp_path), 1_000_000, fetcher=fetcher, clock=lambda: now[0])
    assert tc.get("aaaaaaaaaaa") is None
    assert tc.get("aaaaaaaaaaa") is None
    assert calls == ["aaaaaaaaaaa"]
    now[0] += 301
    tc.get("aaaaaaaaaaa")
    assert calls == ["aaaaaaaaaaa", "aaaaaaaaaaa"]

def test_thumb_rejects_non_jpeg_and_oversize(tmp_path):
    tc = ThumbCache(str(tmp_path), 1_000_000, fetcher=lambda v, s: b"<html>")
    assert tc.get("aaaaaaaaaaa") is None
    big = b"\xff\xd8" + b"x" * 204800
    tc2 = ThumbCache(str(tmp_path), 1_000_000, fetcher=lambda v, s: big)
    assert tc2.get("bbbbbbbbbbb") is None
    assert not list(tmp_path.glob("*.jpg"))

def test_thumb_eviction_by_size(tmp_path):
    tc = ThumbCache(str(tmp_path), 250, fetcher=lambda v, s: JPEG)
    tc.get("aaaaaaaaaaa"); tc.get("bbbbbbbbbbb"); tc.get("ccccccccccc")
    assert len(list(tmp_path.glob("*.jpg"))) <= 2

def test_thumb_rejects_unknown_size(tmp_path):
    import pytest
    tc = ThumbCache(str(tmp_path), 1000, fetcher=lambda v, s: JPEG)
    with pytest.raises(ValueError):
        tc.get("aaaaaaaaaaa", "xl")
```

- [ ] **Step 2: Lancer les tests pour vérifier l'échec**

Run: `pytest tests/test_cache.py -k thumb -v`
Expected: FAIL (`ImportError: cannot import name 'ThumbCache'`).

- [ ] **Step 3: Implémenter `ThumbCache` et `fetch_thumbnail` dans `cache.py`**

`get` : valider `size` ; lire `<root>/<id>-<size>.jpg` si mtime dans le TTL → bytes ; si négatif en mémoire et non expiré → `None` ; sinon appeler `fetcher` ; si `None`, enregistrer le négatif avec `clock()` ; sinon vérifier `len <= 204800` et `data[:2] == b"\xff\xd8"`, écrire via fichier temporaire + `os.replace`, appeler `evict()`, retourner les bytes. `evict` : même logique LRU que `MediaCache` sur `*.jpg` avec `max_bytes`. `fetch_thumbnail` : `requests.get` avec `headers={"User-Agent": "lazarusTube/1.0"}`, `timeout=10` ; status 200 ; `Content-Type` commence par `image/` ; taille ≤ 200 Kio ; `except requests.RequestException: return None`.

- [ ] **Step 4: Relancer les tests**

Run: `pytest tests/test_cache.py -k thumb -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add cache.py tests/test_cache.py
git commit -m "feat: proxy de miniatures avec cache disque et cache négatif"
```

---

### Task 6: Wrapper yt-dlp (recherche, métadonnées précoces, téléchargement)

**Files:**
- Create: `ytdlp.py`
- Test: `tests/test_ytdlp.py`

**Interfaces:**
- Consumes: `formats.format_selector(max_height)`, `ids.is_valid_video_id`.
- Produces:
  - `ytdlp.YtDlpError(Exception)` avec `user_message: str`.
  - `ytdlp.LiveNotSupported(YtDlpError)`.
  - `ytdlp.YtDlp(bin="yt-dlp", node_bin=None, ffmpeg_bin="ffmpeg", request_timeout=30, download_timeout=1800, log=None)` :
    - `search(query: str, limit: int = 10) -> list[dict]` — chaque dict : `id`, `title`, `duration`, `channel`, `view_count`, `live_status`.
    - `download(video_id: str, tmpdir: str, on_progress=None, on_meta=None, max_height: int = 720) -> str` — retourne le chemin du MP4 produit dans `tmpdir`.
  - Constante `META_PREFIX = "LAZARUS_META "`.

- [ ] **Step 1: Écrire les tests qui échouent**

```python
# tests/test_ytdlp.py
import os
import stat
import pytest
from ytdlp import LiveNotSupported, YtDlp, YtDlpError

def fake_bin(tmp_path, body):
    p = tmp_path / "fake-ytdlp"
    p.write_text("#!/usr/bin/env python3\n" + body)
    p.chmod(p.stat().st_mode | stat.S_IEXEC)
    return str(p)

SEARCH_BODY = """
import json
print(json.dumps({"id": "dQw4w9WgXcQ", "title": "T", "duration": 10,
                  "channel": "C", "view_count": 5, "live_status": None}))
print(json.dumps({"id": "trop-court", "title": "Ignore"}))
"""

def test_search_parses_json_lines_and_skips_invalid_ids(tmp_path):
    yt = YtDlp(bin=fake_bin(tmp_path, SEARCH_BODY))
    results = yt.search("jazz", limit=5)
    assert results == [{"id": "dQw4w9WgXcQ", "title": "T", "duration": 10,
                        "channel": "C", "view_count": 5, "live_status": None}]

def test_search_failure_raises_french_message(tmp_path):
    yt = YtDlp(bin=fake_bin(tmp_path, "import sys; sys.stderr.write('ERROR: secret'); sys.exit(1)"))
    with pytest.raises(YtDlpError) as exc:
        yt.search("jazz")
    assert exc.value.user_message == "Recherche impossible pour le moment."
    assert "secret" not in exc.value.user_message

DOWNLOAD_BODY = """
import sys, os
args = sys.argv[1:]
out = args[args.index("-o") + 1]
path = out.replace("%(id)s", "dQw4w9WgXcQ").replace("%(ext)s", "mp4")
open(path, "wb").write(b"x" * 2048)
print('LAZARUS_META {"id": "dQw4w9WgXcQ", "title": "T", "live_status": null}')
print("[download]  50.0% of 1MiB")
"""

def test_download_emits_meta_progress_and_returns_mp4(tmp_path):
    metas, progresses = [], []
    yt = YtDlp(bin=fake_bin(tmp_path, DOWNLOAD_BODY), download_timeout=10)
    work = tmp_path / "work"; work.mkdir()
    path = yt.download("dQw4w9WgXcQ", str(work), on_progress=progresses.append,
                       on_meta=metas.append)
    assert os.path.basename(path).startswith("dQw4w9WgXcQ")
    assert os.path.getsize(path) == 2048
    assert metas[0]["title"] == "T"
    assert progresses == [50.0]

def test_live_aborts_before_download(tmp_path):
    body = """
import sys, time
print('LAZARUS_META {"id": "dQw4w9WgXcQ", "live_status": "is_live"}', flush=True)
time.sleep(30)
"""
    def on_meta(meta):
        raise LiveNotSupported("Ce direct n'est pas disponible.")
    yt = YtDlp(bin=fake_bin(tmp_path, body), download_timeout=10)
    work = tmp_path / "work"; work.mkdir()
    with pytest.raises(LiveNotSupported):
        yt.download("dQw4w9WgXcQ", str(work), on_meta=on_meta)

def test_timeout_kills_process_and_raises(tmp_path):
    yt = YtDlp(bin=fake_bin(tmp_path, "import time; time.sleep(30)"), download_timeout=0.5)
    work = tmp_path / "work"; work.mkdir()
    with pytest.raises(YtDlpError) as exc:
        yt.download("dQw4w9WgXcQ", str(work))
    assert "trop de temps" in exc.value.user_message

def test_missing_output_raises(tmp_path):
    yt = YtDlp(bin=fake_bin(tmp_path, "print('[download] 100.0%')"), download_timeout=10)
    work = tmp_path / "work"; work.mkdir()
    with pytest.raises(YtDlpError):
        yt.download("dQw4w9WgXcQ", str(work))
```

- [ ] **Step 2: Lancer les tests pour vérifier l'échec**

Run: `pytest tests/test_ytdlp.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'ytdlp'`).

- [ ] **Step 3: Implémenter `ytdlp.py`**

`search` : `[bin, "--flat-playlist", "--dump-json", "--no-warnings"] + self._js_args() + ["ytsearch%d:%s" % (limit, query)]` via `subprocess.run(capture_output=True, text=True, timeout=request_timeout + 30)`. Chaque ligne JSON : ignorer si `is_valid_video_id(id)` est faux ; normaliser `channel` = `data.get("channel") or data.get("uploader") or ""` ; `duration` = `data.get("duration") or 0` ; `view_count` = `data.get("view_count")` ; `live_status` = `data.get("live_status")`. Returncode ≠ 0 et aucune ligne → `YtDlpError("Recherche impossible pour le moment.")`.

`_js_args()` : si `node_bin` → `["--js-runtimes", "node:" + node_bin]`, sinon `[]`.

`download` :
- `out_tmpl = os.path.join(tmpdir, "%(id)s.%(ext)s")`.
- Args exacts : `-f format_selector(max_height)`, `--merge-output-format mp4`, `--postprocessor-args ffmpeg:-movflags +faststart`, `--no-playlist`, `--no-warnings`, `--newline`, `--progress`, `--no-simulate`, `--retries 3`, `--fragment-retries 3`, `--socket-timeout 15`, `--concurrent-fragments 4`, `--print`, `before_dl:LAZARUS_META {"id":%(id)j,"title":%(title)j,"channel":%(channel)j,"duration":%(duration)j,"view_count":%(view_count)j,"live_status":%(live_status)j}`, `-o out_tmpl`, URL `https://www.youtube.com/watch?v=<id>`.
- `subprocess.Popen(..., stdout=PIPE, stderr=STDOUT, text=True, start_new_session=True)`.
- `threading.Timer(download_timeout, _kill)` avec `_kill` = `os.killpg(os.getpgid(proc.pid), signal.SIGKILL)` protégé par `try/except`; `timer.daemon = True`.
- Lire `proc.stdout` ligne par ligne ; sur `LAZARUS_META ` parser le JSON et appeler `on_meta(meta)` ; si `on_meta` lève, tuer le groupe, `proc.wait()`, relancer l'exception ; sur `[download]` et `(\d+(?:\.\d+)?)%` appeler `on_progress(float)` (arrondi à 1 décimale) ; conserver les 20 dernières lignes pour le log.
- `proc.wait()` ; annuler le timer ; timeout → `YtDlpError("Le téléchargement a pris trop de temps.")` ; code ≠ 0 → `YtDlpError("Impossible de préparer cette vidéo.")` avec log tronqué à 500 caractères.
- Chercher le plus gros `*.mp4` dans `tmpdir` ; absent → `YtDlpError("Impossible de préparer cette vidéo.")`.

- [ ] **Step 4: Relancer les tests**

Run: `pytest tests/test_ytdlp.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add ytdlp.py tests/test_ytdlp.py
git commit -m "feat: wrapper yt-dlp avec métadonnées précoces, timeout et refus des directs"
```

---

### Task 7: Registre de jobs, fallback 480p et reprise après redémarrage

**Files:**
- Create: `jobs.py`
- Test: `tests/test_jobs.py`

**Interfaces:**
- Consumes: `MediaCache` (`root`, `has`, `publish`, `read_meta`, `evict`, `free_bytes`, `delete`, `media_path`), `StreamRegistry.is_active`, `YtDlp.download`, `formats.validate_mp4` / `FormatError`, `YtDlpError` / `LiveNotSupported`.
- Produces:
  - `jobs.ForceRefused(Exception)`.
  - `jobs.JobRegistry(media, ytdlp, streams, max_concurrent=2, max_height=720, clock=time.time, log=None)` :
    - `start(video_id: str, retry: bool = False, force: bool = False) -> dict`
    - `status(video_id: str) -> dict`
    - `cleanup(max_age: int = 3600) -> None`
  - Snapshot dict : `{"id", "state", "progress", "downloaded_bytes", "total_bytes", "error", "meta"}`. `state` ∈ `idle|queued|downloading|ready|error`, `progress = -1.0` si inconnu, `meta` toujours un dict.

- [ ] **Step 1: Écrire les tests qui échouent**

```python
# tests/test_jobs.py
import threading
import time
import pytest
from cache import MediaCache, StreamRegistry
from formats import FormatError
from jobs import ForceRefused, JobRegistry
from ytdlp import LiveNotSupported, YtDlpError

class FakeYtDlp:
    def __init__(self):
        self.calls = []
        self.error = None
        self.meta = {"title": "T", "channel": "C", "duration": 10}
        self.gate = threading.Event()
        self.gate.set()
        self.active = 0
        self.max_active = 0
        self.lock = threading.Lock()
    def download(self, video_id, tmpdir, on_progress=None, on_meta=None, max_height=720):
        with self.lock:
            self.active += 1
            self.max_active = max(self.max_active, self.active)
        self.calls.append(max_height)
        try:
            self.gate.wait(5)
            if on_meta:
                on_meta(dict(self.meta))
            if self.error:
                raise self.error
            path = tmpdir + "/" + video_id + ".mp4"
            open(path, "wb").write(b"x" * 2048)
            if on_progress:
                on_progress(100.0)
            return path
        finally:
            with self.lock:
                self.active -= 1

def make(tmp_path, fake=None, validate=None, **kw):
    fake = fake or FakeYtDlp()
    media = MediaCache(str(tmp_path), 10_000_000, 604800, StreamRegistry())
    media.ensure_dirs()
    reg = JobRegistry(media, fake, media.registry, **kw)
    return reg, media, fake

def wait_state(reg, vid, states, timeout=5):
    deadline = time.time() + timeout
    while time.time() < deadline:
        snap = reg.status(vid)
        if snap["state"] in states:
            return snap
        time.sleep(0.01)
    raise AssertionError(reg.status(vid))

def test_idle_snapshot_for_unknown_id(tmp_path):
    reg, _, _ = make(tmp_path)
    assert reg.status("dQw4w9WgXcQ") == {
        "id": "dQw4w9WgXcQ", "state": "idle", "progress": -1.0,
        "downloaded_bytes": 0, "total_bytes": 0, "error": None, "meta": {}}

def test_start_downloads_validates_and_publishes(tmp_path, monkeypatch):
    import jobs
    monkeypatch.setattr(jobs, "validate_mp4", lambda path: None)
    reg, media, fake = make(tmp_path)
    snap = reg.start("dQw4w9WgXcQ")
    assert snap["state"] in ("queued", "downloading")
    snap = wait_state(reg, "dQw4w9WgXcQ", ("ready", "error"))
    assert snap["state"] == "ready" and snap["progress"] == 100.0
    assert media.has("dQw4w9WgXcQ")
    assert media.read_meta("dQw4w9WgXcQ")["title"] == "T"
    assert fake.calls == [720]

def test_restart_ready_from_sidecar_without_download(tmp_path):
    reg, media, fake = make(tmp_path)
    media.publish("dQw4w9WgXcQ", _tmp_file(tmp_path), {"title": "Disque"})
    snap = reg.start("dQw4w9WgXcQ")
    assert snap["state"] == "ready"
    assert snap["meta"]["title"] == "Disque"
    assert fake.calls == []

def _tmp_file(tmp_path):
    p = tmp_path / "src.mp4"; p.write_bytes(b"x" * 10); return str(p)

def test_retries_480_after_format_error(tmp_path, monkeypatch):
    import jobs
    seen = []
    def validate(path):
        seen.append(path)
        if len(seen) == 1:
            raise FormatError("Format incompatible avec cet appareil.")
    monkeypatch.setattr(jobs, "validate_mp4", validate)
    reg, media, fake = make(tmp_path)
    reg.start("dQw4w9WgXcQ")
    snap = wait_state(reg, "dQw4w9WgXcQ", ("ready", "error"))
    assert snap["state"] == "ready"
    assert fake.calls == [720, 480]

def test_double_format_failure_reports_clear_error(tmp_path, monkeypatch):
    import jobs
    monkeypatch.setattr(jobs, "validate_mp4", lambda p: (_ for _ in ()).throw(FormatError("x")))
    reg, media, fake = make(tmp_path)
    reg.start("dQw4w9WgXcQ")
    snap = wait_state(reg, "dQw4w9WgXcQ", ("ready", "error"))
    assert snap["state"] == "error"
    assert snap["error"] == "Format incompatible avec cet appareil."
    assert not media.has("dQw4w9WgXcQ")

def test_live_is_error_and_nothing_published(tmp_path):
    fake = FakeYtDlp()
    fake.meta = {"title": "Live", "live_status": "is_live"}
    reg, media, _ = make(tmp_path, fake=fake)
    reg.start("dQw4w9WgXcQ")
    snap = wait_state(reg, "dQw4w9WgXcQ", ("ready", "error"))
    assert snap["state"] == "error"
    assert snap["error"] == "Les directs ne sont pas disponibles."
    assert not media.has("dQw4w9WgXcQ")

def test_error_then_retry(tmp_path, monkeypatch):
    import jobs
    monkeypatch.setattr(jobs, "validate_mp4", lambda p: None)
    fake = FakeYtDlp(); fake.error = YtDlpError("Vidéo indisponible.")
    reg, _, _ = make(tmp_path, fake=fake)
    reg.start("dQw4w9WgXcQ")
    snap = wait_state(reg, "dQw4w9WgXcQ", ("ready", "error"))
    assert snap["state"] == "error"
    fake.error = None
    reg.start("dQw4w9WgXcQ", retry=True)
    assert wait_state(reg, "dQw4w9WgXcQ", ("ready", "error"))["state"] == "ready"

def test_concurrency_limit(tmp_path, monkeypatch):
    import jobs
    monkeypatch.setattr(jobs, "validate_mp4", lambda p: None)
    fake = FakeYtDlp(); fake.gate.clear()
    reg, _, _ = make(tmp_path, fake=fake, max_concurrent=2)
    for vid in ("aaaaaaaaaaa", "bbbbbbbbbbb", "ccccccccccc"):
        reg.start(vid)
    time.sleep(0.2)
    assert fake.max_active == 2
    assert reg.status("ccccccccccc")["state"] == "queued"
    fake.gate.set()
    for vid in ("aaaaaaaaaaa", "bbbbbbbbbbb", "ccccccccccc"):
        wait_state(reg, vid, ("ready", "error"))

def test_force_refused_while_stream_active(tmp_path):
    reg, media, _ = make(tmp_path)
    media.publish("dQw4w9WgXcQ", _tmp_file(tmp_path), {"title": "T"})
    media.registry.begin(media.media_path("dQw4w9WgXcQ"))
    with pytest.raises(ForceRefused):
        reg.start("dQw4w9WgXcQ", force=True)

def test_cleanup_removes_finished_jobs(tmp_path):
    now = [1000.0]
    reg, media, fake = make(tmp_path, clock=lambda: now[0])
    media.publish("dQw4w9WgXcQ", _tmp_file(tmp_path), {"title": "T"})
    reg.start("dQw4w9WgXcQ")
    now[0] += 7200
    reg.cleanup(max_age=3600)
    assert reg.status("dQw4w9WgXcQ")["state"] == "idle"
```

- [ ] **Step 2: Lancer les tests pour vérifier l'échec**

Run: `pytest tests/test_jobs.py -v`
Expected: FAIL (`ModuleNotFoundError: No module named 'jobs'`).

- [ ] **Step 3: Implémenter `jobs.py`**

Structure interne : dataclass `Job` (`video_id`, `state`, `progress`, `downloaded_bytes`, `total_bytes`, `error`, `meta`, `finished_at`) ; `JobRegistry` garde `_jobs: dict[str, Job]`, un `RLock`, un `Semaphore(max_concurrent)`, un verrou par vidéo (`dict[str, Lock]` + verrou global).

`start` (sous verrou) :
1. `force=True` **d'abord** : si `streams.is_active(media.media_path(id))` → `ForceRefused` ; sinon `media.delete(id)`.
2. Fichier final présent → créer/écraser un job `ready` (`progress=100.0`, `meta=media.read_meta(id) or {}`, `finished_at=clock()`), retourner le snapshot.
3. Job existant `queued`/`downloading` → snapshot.
4. Job existant `error` et `retry=False` → snapshot.
5. Créer un job `queued` (`progress=-1.0`, `meta={}`), lancer un thread daemon `_run(job)` et retourner le snapshot.

`_run` :
1. `with self._semaphore:` ; re-vérifier le fichier final (un autre job a pu le produire) → `ready`.
2. Vérifier `media.free_bytes() < 500 * 1024 * 1024` → erreur « Espace disque insuffisant. ».
3. `tmpdir = tempfile.mkdtemp(prefix=video_id + "-", dir=os.path.join(media.root, "tmp"))`.
4. `on_meta` : mettre à jour `job.meta` avec les clés non nulles ; si `live_status` ∈ `{"is_live", "is_upcoming"}` → lever `LiveNotSupported("Les directs ne sont pas disponibles.")`.
5. `path = ytdlp.download(id, tmpdir, on_progress=_progress, on_meta=_meta, max_height=self.max_height)`.
6. `validate_mp4(path)` ; sur `FormatError` : `path = ytdlp.download(..., max_height=480)` puis re-valider ; second échec → `FormatError("Format incompatible avec cet appareil.")`.
7. `media.publish(id, path, job.meta)` ; `job.state="ready"`, `progress=100.0` ; `media.evict()`.
8. Exceptions : `LiveNotSupported` → message exact ; `FormatError` → `user_message` ; `YtDlpError` → `user_message` ; `Exception` → « Impossible de préparer cette vidéo. » + log `exc_info=True`.
9. `finally` : `shutil.rmtree(tmpdir, ignore_errors=True)`, `job.finished_at = clock()`, `cleanup()`.

`_progress` : ignorer les valeurs < 0 ou > 100 ; mettre à jour `progress` et les octets si disponibles ; limitation à ~4 Hz via `clock()`.

`status` : snapshot profond (copie du meta). `cleanup` : supprimer les jobs dont `finished_at` est non nul et `clock() - finished_at > max_age`, et si plus de 200 jobs, supprimer les plus anciens terminés.

- [ ] **Step 4: Relancer les tests**

Run: `pytest tests/test_jobs.py -v`
Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add jobs.py tests/test_jobs.py
git commit -m "feat: registre de jobs avec progression, fallback 480p et reprise"
```

---

### Task 8: `create_app()`, API de préparation et lecture P0

**Files:**
- Modify: `app.py` (réécriture complète)
- Create: `templates/watch.html` (version P0 minimale), `templates/errors/400.html`, `templates/errors/404.html`, `templates/errors/500.html`, `static/js/app.js` (helpers de base), `static/js/watch.js` (version P0 minimale)
- Modify: `templates/index.html` (remplacer `video.thumbnail` par `video.thumb_url` ; le reste de la refonte arrive en Tâche 9)
- Test: `tests/conftest.py`, `tests/test_routes.py`

**Interfaces:**
- Consumes: tous les modules précédents.
- Produces:
  - `app.create_app(overrides: dict | None = None) -> Flask`. `overrides` accepte les champs de `Config` (remplacés via `dataclasses.replace`) **et** les clés de service `"ytdlp"` et `"thumbs_fetcher"` injectées dans les objets construits.
  - `app.extensions["lazarus"]` : `SimpleNamespace` avec `config`, `media`, `streams`, `thumbs`, `search_cache`, `meta`, `ytdlp`, `jobs`.
  - Filtres Jinja : `duration(seconds) -> str` (`1:02:03` / `12:34` / `""`), `views(count) -> str` (`1,2 M` / `45 k` / `""`).
  - Routes : `/`, `/search`, `/watch`, `POST /api/prepare`, `GET /api/status`, `/stream`, `/thumb/<video_id>.jpg`, `/healthz`.

- [ ] **Step 1: Écrire les tests qui échouent**

```python
# tests/conftest.py
import threading
import pytest
from app import create_app

class FakeYtDlp:
    def __init__(self):
        self.search_calls = []
        self.results = [{"id": "dQw4w9WgXcQ", "title": "Titre", "duration": 125,
                         "channel": "Chaîne", "view_count": 1200000, "live_status": None}]
        self.search_error = None
        self.gate = threading.Event()
    def search(self, query, limit=10):
        self.search_calls.append((query, limit))
        if self.search_error:
            raise self.search_error
        return list(self.results)
    def download(self, video_id, tmpdir, on_progress=None, on_meta=None, max_height=720):
        self.gate.wait(5)
        raise RuntimeError("pas de vrai téléchargement dans les tests")

@pytest.fixture
def fake_ytdlp():
    return FakeYtDlp()

@pytest.fixture
def app(tmp_path, fake_ytdlp):
    return create_app({"cache_dir": str(tmp_path), "ytdlp": fake_ytdlp,
                       "thumbs_fetcher": lambda vid, size: None})

@pytest.fixture
def client(app):
    return app.test_client()

@pytest.fixture
def services(app):
    return app.extensions["lazarus"]
```

```python
# tests/test_routes.py
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
```

- [ ] **Step 2: Lancer les tests pour vérifier l'échec**

Run: `pytest tests/test_routes.py -v`
Expected: FAIL (routes et `create_app` absentes ; `import app` échoue ou les statuts ne correspondent pas).

- [ ] **Step 3: Implémenter `app.py` et les gabarits P0**

`create_app` : construire `Config` via `load_config()`, appliquer les champs présents dans `overrides`, construire `StreamRegistry`, `MediaCache(cfg.cache_dir, ...)`, `ThumbCache(..., fetcher=overrides.get("thumbs_fetcher", fetch_thumbnail))`, `SearchCache`, `MetaCache`, `YtDlp(...)`, `JobRegistry(...)`. `media.ensure_dirs()` ; `media.clean_tmp()` et `media.evict()` dans un `try/except OSError` (démarrage tolérant). Configurer `logging` une seule fois (`basicConfig(level=cfg.log_level)`).

Routes (voir §7 de la spec) :
- `/search` : `q` trimmé et tronqué à `max_query_length` ; vide → index avec `error="Veuillez saisir un terme de recherche."` ; `extract_video_id(q)` → `redirect(url_for("watch", v=video_id))` ; `refresh=1` contourne `SearchCache` ; ajouter `thumb_url=url_for("thumb", video_id=r["id"])` à chaque résultat ; `meta.put` ; erreurs `YtDlpError` → `error=exc.user_message`.
- `/watch` : ID invalide → `abort(400)` ; `meta=meta.get(id) or {}` ; `render_template("watch.html", video_id=..., meta=..., live_status=meta.get("live_status"))`.
- `/api/prepare` : JSON d'erreur `{"error": "Identifiant vidéo invalide."}` ; `retry=request.args.get("retry") == "1"`, idem `force` ; `ForceRefused` → 409 `{"error": "Cette vidéo est en cours de lecture."}` ; statut 200 si `state in ("ready", "error")`, sinon 202.
- `/api/status` : ID invalide → 400 JSON ; sinon 200 snapshot.
- `/stream` : ID invalide → 400 texte ; `media.has` faux → 425 texte « Vidéo non préparée. » ; `media.touch` ; `range_response(path, request.headers.get("Range"), streams, head=request.method == "HEAD")`.
- `/thumb/<video_id>.jpg` : ID invalide ou `size` hors `{"mq", "hq"}` → 404 ; `thumbs.get` ; `None` → 404 ; sinon `Response(data, mimetype="image/jpeg")`.
- `/healthz` : `shutil.which` sur `ytdlp_bin`, `ffmpeg_bin`, `ffprobe_bin`, `node_bin or "node"` + `media.writable()` ; 200 `{"status": "ok"}` ou 503 `{"status": "degraded", "checks": {...}}`.
- Erreurs 400/404/500 : JSON pour `request.path.startswith("/api/")`, sinon `render_template("errors/<code>.html")`.
- `after_request` : `X-Content-Type-Options: nosniff`, `X-Frame-Options: SAMEORIGIN` ; `Cache-Control: no-cache` pour HTML, `no-store` pour `/api/` et `/stream`, `public, max-age=604800` pour `/static/`.
- Supprimer `/check`.
- `__main__` : `create_app().run(host="0.0.0.0", port=3616, debug=False, threaded=True)`.

`templates/watch.html` P0 : document autonome, `<body data-video-id="{{ video_id }}">`, titre `{{ meta.title or "Lecture" }}`, `<video id="player" controls playsinline webkit-playsinline preload="metadata">`, zone `#status` `aria-live="polite"`, bouton `#retry` caché. `static/js/watch.js` P0 : POST `/api/prepare?v=`, puis `setInterval` 1500 ms sur `/api/status?v=` ; à `ready`, `player.src = "/stream?v=" + encodeURIComponent(id)` ; à `error`, afficher `error` avec `textContent` (jamais `innerHTML`) et montrer `#retry` ; `retry` relance avec `retry=1`. `static/js/app.js` : `window.Lazarus = { xhr: function(method, url, done) {...}, formatTime: ..., storage: {get,set,remove} }` en ES5 pur, `try/catch` sur `localStorage`.

- [ ] **Step 4: Relancer les tests**

Run: `pytest tests/test_routes.py -v`
Expected: PASS.

- [ ] **Step 5: Vérifier manuellement le démarrage local**

Run: `LAZARUS_CACHE_DIR=/tmp/lazarus-dev python app.py` puis `curl -s http://127.0.0.1:3616/healthz`
Expected: `{"status":"ok",...}` ; arrêter avec Ctrl-C.

- [ ] **Step 6: Commit**

```bash
git add app.py templates/watch.html templates/index.html templates/errors static/js/app.js static/js/watch.js tests/conftest.py tests/test_routes.py
git commit -m "feat: create_app, API prepare/status, stream gaté et page de lecture P0"
```

---

### Task 9: Shell commun, design system et accueil illustré

**Files:**
- Create: `templates/base.html`, `templates/index.html` (remplace l'ancien), `static/css/app.css`, `static/js/search.js`
- Modify: `app.py` (contexte de `/` et `/search`, filtre `views`, version des assets), `static/js/app.js` (helpers `formatViews`, `formatDuration`, `escapeHtml` si nécessaire)
- Test: `tests/test_routes.py` (ajouts), `tests/test_js_es5.py`

**Interfaces:**
- Consumes: routes et services de la Tâche 8.
- Produces:
  - `templates/base.html` avec les blocs `title`, `content`, `scripts` ; variables `active_page` (`"home"`, `"history"`, `"favorites"`).
  - `index.html` reçoit `query: str`, `results: list | None`, `error: str | None`, `refresh_url: str | None`.
  - `static/js/search.js` : sur `submit`, désactive le bouton, remplace son texte par « Recherche… », ajoute la requête à `lazarus.v1.searches` ; au chargement, rend les chips des recherches récentes dans `#recent-searches` et les supprime si le champ est vide.
  - `app.css` : design system complet décrit ci-dessous.

- [ ] **Step 1: Écrire les tests qui échouent**

```python
# tests/test_routes.py (ajouts)
def test_pages_share_shell_and_ios_meta(client):
    html = client.get("/").get_data(as_text=True)
    assert '/static/css/app.css' in html
    assert '/static/js/app.js' in html
    assert 'apple-touch-icon' in html
    assert 'user-scalable=no' not in html
    assert 'href="/history"' in html and 'href="/favorites"' in html

def test_search_page_shows_card_metadata(client):
    html = client.get("/search?q=jazz").get_data(as_text=True)
    assert 'class="card"' in html
    assert 'class="card-thumb"' in html
    assert 'alt=""' in html
    assert "Chaîne" in html
    assert "1,2 M" in html
    assert "2:05" in html
    assert 'class="badge-duration"' in html

def test_search_page_has_loading_hook_and_recent_searches(client):
    html = client.get("/").get_data(as_text=True)
    assert 'id="recent-searches"' in html
    assert 'id="search-submit"' in html
    assert '/static/js/search.js' in html

def test_empty_results_message(client, services):
    services.ytdlp.results = []
    html = client.get("/search?q=inconnu").get_data(as_text=True)
    assert "Aucun résultat" in html

def test_search_error_has_retry_link(client, services):
    services.ytdlp.search_error = YtDlpError("Recherche impossible pour le moment.")
    html = client.get("/search?q=jazz").get_data(as_text=True)
    assert "Réessayer" in html
    assert "refresh=1" in html
```

```python
# tests/test_js_es5.py
import pathlib
import re

JS_DIR = pathlib.Path(__file__).resolve().parents[1] / "static" / "js"
FORBIDDEN = [r"=>", r"\bconst\s", r"\blet\s", r"\basync\s", r"\bawait\s", r"`", r"\bfetch\s*\("]

def test_js_files_are_es5():
    files = sorted(JS_DIR.glob("*.js"))
    assert files, "aucun fichier JS trouvé"
    for path in files:
        source = path.read_text(encoding="utf-8")
        for pattern in FORBIDDEN:
            assert not re.search(pattern, source), "%s contient %s" % (path.name, pattern)
```

- [ ] **Step 2: Lancer les tests pour vérifier l'échec**

Run: `pytest tests/test_routes.py -k "shell or card or loading or empty or retry_link" tests/test_js_es5.py -v`
Expected: FAIL (gabarits et `search.js` absents, assertions de shell fausses).

- [ ] **Step 3: Implémenter `base.html`, `index.html`, `app.css` et `search.js`**

`base.html` : `<!DOCTYPE html>`, `<html lang="fr">`, viewport `width=device-width, initial-scale=1` **sans** `user-scalable=no`, meta iOS (`apple-mobile-web-app-capable`, `apple-mobile-web-app-title=LazarusTube`, `apple-mobile-web-app-status-bar-style=default`), `apple-touch-icon`, `link rel="icon"`, `app.css?v={{ asset_version }}`, header avec logo + nav (`<a class="nav-link{% if active_page == 'history' %} active{% endif %}" ...>`), `<main class="container">{% block content %}`, footer, scripts `app.js?v={{ asset_version }}` puis `{% block scripts %}`.

`index.html` : hero de recherche (`<form action="/search" method="get" id="search-form">`, `label` masqué, `input name="q" type="search" value="{{ query }}"`, bouton `id="search-submit"`), aide « Colle un lien YouTube ou cherche des mots… », `#recent-searches`, zone d'erreur, si `results is not None` : titre « Résultats pour « q » », compteur, lien Actualiser ; grille `.results` ; carte :

```html
<a class="card" href="{{ url_for('watch', v=result.id) }}">
  <div class="card-thumb">
    <img src="{{ result.thumb_url }}" alt="" width="320" height="180" loading="lazy">
    {% if result.duration %}<span class="badge-duration">{{ result.duration|duration }}</span>{% endif %}
    {% if result.live_status %}<span class="badge-live">Direct</span>{% endif %}
  </div>
  <div class="card-body">
    <h3 class="card-title">{{ result.title }}</h3>
    <p class="card-meta">{{ result.channel }}{% if result.view_count %} · {{ result.view_count|views }} vues{% endif %}</p>
  </div>
</a>
```

Si `results == []` : « Aucun résultat pour « q ». Essaie d'autres mots-clés. ». Si `error` : bloc `.alert` + lien « Réessayer » vers `refresh_url`.

`app.css` : commentaire de palette en tête, puis :
- Reset minimal (`box-sizing`, marges), `body` fond `#F4F8F9`, texte `#1B3A5A`, police `-apple-system, "Helvetica Neue", Arial, sans-serif`, `font-size: 16px`, `line-height: 1.45`.
- `.container { max-width: 1000px; margin: 0 auto; padding: 16px; }`.
- Header blanc, bordure `#DCE6EA`, flex (`display: -webkit-box; display: -webkit-flex; display: flex;`), logo `height: 40px; width: auto`, nav liens 44 px de haut, actif `border-bottom: 3px solid #3EADBA`.
- Champ de recherche 100 %, hauteur 52 px, bordure, focus `outline: 3px solid #3EADBA`, police 16 px ; bouton bleu `#175071`, texte blanc, min 44×44.
- `.results` : `font-size: 0` sur le conteneur + `.card { display: inline-block; width: 48%; margin: 0 4% 20px 0; vertical-align: top; font-size: 16px; }` et `.card:nth-child(2n) { margin-right: 0; }` (compatible Safari 9). Sous 700 px : `width: 100%; margin-right: 0;`.
- `.card` blanc, bordure, rayon 10 px, ombre légère, `color: inherit; text-decoration: none`.
- `.card-thumb { position: relative; background: #1B3A5A; }` ; image `display: block; width: 100%; height: auto;` ; fallback CSS `.card-thumb::before` triangle play centré, visible seulement si l'image échoue (via `img` masquée par `onerror` en JS ou fond visible autour de l'image).
- `.badge-duration` en bas à droite, fond `rgba(14,26,36,.85)`, blanc, `font-size: 13px`, padding 2 px 6 px, rayon 4 px.
- `.badge-live` corail `#CF6957`, haut à gauche.
- `.card-title` 16 px, `display: -webkit-box; -webkit-line-clamp: 2; -webkit-box-orient: vertical; overflow: hidden;` ; `.card-meta` 14 px `#62788A`.
- `.alert` fond `#FDECEA`, bord `#F2B8B5`, texte `#8A1C17`.
- `.spinner` : carré 16 px, bordure 2 px, `-webkit-animation: spin .8s linear infinite`, `@-webkit-keyframes spin`.
- `#recent-searches` chips `inline-block`, 44 px de haut, fond blanc, bordure.
- Footer 13 px `#62788A`.

`search.js` : IIFE ES5, `document.getElementById`, `addEventListener` ; lit `lazarus.v1.searches` via `Lazarus.storage.get`, tronque à 8 ; chips = `<a>` avec `href="/search?q=" + encodeURIComponent(q)` et `textContent` ; le formulaire ajoute la requête puis laisse la navigation se faire ; si `localStorage` échoue, ne rien casser.

`app.py` : ajouter le filtre `views` (`>= 1_000_000` → `"1,2 M"` avec virgule décimale, `>= 1_000` → `"45 k"`, sinon nombre brut), exposer `asset_version` (mtime de `static/css/app.css`, arrondi à l'entier) et `active_page` dans le contexte de `/` et `/search`. `/search` calcule `refresh_url = url_for("search", q=query, refresh=1)`.

- [ ] **Step 4: Relancer les tests**

Run: `pytest tests/test_routes.py tests/test_js_es5.py -v`
Expected: PASS.

- [ ] **Step 5: Vérification visuelle locale**

Run: `LAZARUS_CACHE_DIR=/tmp/lazarus-dev python app.py` puis ouvrir `http://127.0.0.1:3616/` et `/search?q=jazz`.
Expected: deux colonnes à 1024 px, une sous 700 px, aucune barre horizontale, miniatures visibles, focus visible au clavier.

- [ ] **Step 6: Commit**

```bash
git add app.py templates/base.html templates/index.html static/css/app.css static/js/app.js static/js/search.js tests/test_routes.py tests/test_js_es5.py
git commit -m "feat: shell commun, design system et accueil en grille avec miniatures"
```

---

### Task 10: Page de lecture soignée (poster, progression, erreurs)

**Files:**
- Modify: `templates/watch.html` (version complète), `static/js/watch.js`, `static/css/app.css`
- Test: `tests/test_routes.py` (ajouts), `tests/test_js_es5.py` (couvre déjà `watch.js`)

**Interfaces:**
- Consumes: `base.html`, `/api/prepare`, `/api/status`, `/stream`, `/thumb/<id>.jpg?size=hq`, `meta`.
- Produces:
  - `watch.html` : bloc `content` avec `a.back`, `.player-wrap` contenant `<video id="player" poster="/thumb/{{ video_id }}.jpg?size=hq" controls playsinline webkit-playsinline preload="metadata">`, `#prepare-overlay` (`.progress-track` > `#progress-fill`, `#progress-label`, `#prepare-text`), `#error-box` (message + `#retry`), `.video-info` (`h1#video-title`, `p#video-meta`), `#youtube-link`.
  - `watch.js` : `prepare()`, `poll()`, `showError(message)`, `setReady()` ; polling 1500 ms ; arrêt du polling sur `ready`/`error` et sur `pagehide`.

- [ ] **Step 1: Écrire les tests qui échouent**

```python
# tests/test_routes.py (ajouts)
def test_watch_has_poster_overlay_and_player(client):
    html = client.get("/watch?v=dQw4w9WgXcQ").get_data(as_text=True)
    assert 'id="player"' in html
    assert 'playsinline' in html and 'webkit-playsinline' in html
    assert 'poster="/thumb/dQw4w9WgXcQ.jpg?size=hq"' in html
    assert 'id="prepare-overlay"' in html
    assert 'id="progress-fill"' in html
    assert 'aria-live="polite"' in html
    assert 'id="retry"' in html
    assert 'href="https://www.youtube.com/watch?v=dQw4w9WgXcQ"' in html

def test_watch_uses_sidecar_metadata(client, services, tmp_path):
    services.media.publish("dQw4w9WgXcQ", _tmp(tmp_path),
                           {"title": "Titre", "channel": "Chaîne", "duration": 125,
                            "view_count": 1200000})
    html = client.get("/watch?v=dQw4w9WgXcQ").get_data(as_text=True)
    assert "Titre" in html and "Chaîne" in html and "1,2 M" in html and "2:05" in html

def test_watch_without_meta_has_placeholders(client):
    html = client.get("/watch?v=dQw4w9WgXcQ").get_data(as_text=True)
    assert "Préparation de la vidéo" in html
```

- [ ] **Step 2: Lancer les tests pour vérifier l'échec**

Run: `pytest tests/test_routes.py -k watch -v`
Expected: FAIL (gabarit P0 sans poster ni overlay).

- [ ] **Step 3: Implémenter le gabarit et le script**

`watch.html` étend `base.html` (`active_page="home"`), titre `meta.title or "Lecture"`. Structure exacte de la spec §11 : retour, lecteur sombre (`#0E1A24`), overlay centré avec barre turquoise, `h1#video-title` = `{{ meta.title or "Préparation de la vidéo" }}`, `p#video-meta` = `{{ meta.channel }}{% if meta.view_count %} · {{ meta.view_count|views }} vues{% endif %}{% if meta.duration %} · {{ meta.duration|duration }}{% endif %}`, boutons (favori/±10/plein écran ajoutés en Tâche 11), lien `href="https://www.youtube.com/watch?v={{ video_id }}"` `target="_blank" rel="noopener"`. Le poster est exactement `poster="/thumb/{{ video_id }}.jpg?size=hq"`.

`watch.js` :
- `var id = document.body.getAttribute("data-video-id");`
- `prepare(retry)` : `Lazarus.xhr("POST", "/api/prepare?v=" + encodeURIComponent(id) + (retry ? "&retry=1" : ""), callback)` ; si `state === "ready"` → `setReady()` ; si `error` → `showError` ; sinon démarrer `poll()`.
- `poll()` : `setInterval` 1500 ms ; `GET /api/status` ; mettre à jour `progress-fill.style.width` (`progress < 0` → largeur 0 + texte « Préparation… ») ; `progress-label.textContent = Math.round(progress) + " %"` ; à `ready`, `clearInterval` + `setReady()` ; à `error`, `clearInterval` + `showError(snap.error)`.
- `setReady()` : masquer l'overlay (`className = "hidden"`), `player.src = "/stream?v=" + encodeURIComponent(id)` ; ne pas appeler `play()`.
- `showError(message)` : masquer l'overlay, remplir `#error-text`, montrer `#error-box` et `#retry`.
- `#retry.onclick` → cacher l'erreur, remettre l'overlay, `prepare(true)`.
- Mettre à jour le titre/méta depuis `snap.meta` si le sidecar était vide.
- `window.addEventListener("pagehide", stopPolling)`.

CSS : `.player-wrap { position: relative; background: #0E1A24; }`, `video { display: block; width: 100%; height: auto; background: #0E1A24; }`, overlay absolu (`position: absolute; top: 0; right: 0; bottom: 0; left: 0;`) fond `rgba(14,26,36,.82)`, texte blanc ; `.progress-track` 260 px max, 6 px, fond `#2C3E4C`, rayon 3 px ; `#progress-fill` turquoise, `width: 0`, `-webkit-transition: width .3s linear` ; `.hidden { display: none; }` ; `.video-info` blanc, bordure, rayon 10 px, padding 16 px ; `.back` 44 px.

- [ ] **Step 4: Relancer les tests**

Run: `pytest tests/test_routes.py tests/test_js_es5.py -v`
Expected: PASS.

- [ ] **Step 5: Vérification manuelle de la progression**

Run: `LAZARUS_CACHE_DIR=/tmp/lazarus-dev python app.py` puis ouvrir une vidéo non cachée.
Expected: page immédiate, overlay + pourcentage qui avancent, lecteur disponible à la fin ; couper le réseau pendant le téléchargement → message d'erreur + « Réessayer ».

- [ ] **Step 6: Commit**

```bash
git add templates/watch.html static/js/watch.js static/css/app.css tests/test_routes.py
git commit -m "feat: page de lecture avec poster, progression et reprise sur erreur"
```

---

### Task 11: Reprise, favoris, historique, ±10 s et plein écran

**Files:**
- Modify: `templates/watch.html` (boutons et barre de reprise), `static/js/watch.js`, `static/js/app.js`, `static/css/app.css`
- Test: `tests/test_routes.py` (ajouts), `tests/test_js_es5.py` (ajouts)

**Interfaces:**
- Consumes: `Lazarus.storage`, `Lazarus.formatTime`, métadonnées de `watch.html`.
- Produces (clés `localStorage`) :
  - `lazarus.v1.resume` : `{ "<id>": {"t": seconds, "d": duration, "ts": epoch_ms} }`, max 50.
  - `lazarus.v1.history` : `[{"id","title","channel","duration","view_count","ts"}]`, max 50, dédupliqué, plus récent en tête.
  - `lazarus.v1.favorites` : même structure, max 200.
  - `lazarus.v1.searches` : déjà gérée en Tâche 9.

- [ ] **Step 1: Écrire les tests qui échouent**

```python
# tests/test_routes.py (ajouts)
def test_watch_has_library_controls(client):
    html = client.get("/watch?v=dQw4w9WgXcQ").get_data(as_text=True)
    for element_id in ('id="favorite"', 'id="back-10"', 'id="forward-10"',
                       'id="fullscreen"', 'id="resume-bar"', 'id="resume-yes"',
                       'id="resume-no"'):
        assert element_id in html

def test_watch_has_metadata_dataset_for_storage(client, services, tmp_path):
    services.media.publish("dQw4w9WgXcQ", _tmp(tmp_path),
                           {"title": "Titre", "channel": "Chaîne", "duration": 125,
                            "view_count": 1200000})
    html = client.get("/watch?v=dQw4w9WgXcQ").get_data(as_text=True)
    assert 'data-title="Titre"' in html
    assert 'data-channel="Chaîne"' in html
    assert 'data-duration="125"' in html
    assert 'data-view-count="1200000"' in html
```

```python
# tests/test_js_es5.py (ajouts)
WATCH_JS = JS_DIR / "watch.js"

def test_watch_js_declares_storage_contract():
    source = WATCH_JS.read_text(encoding="utf-8")
    assert "lazarus.v1.resume" in source
    assert "lazarus.v1.history" in source
    assert "lazarus.v1.favorites" in source
    assert "webkitEnterFullscreen" in source

def test_watch_js_has_no_innerhtml_with_metadata():
    source = WATCH_JS.read_text(encoding="utf-8")
    assert "innerHTML" not in source
```

- [ ] **Step 2: Lancer les tests pour vérifier l'échec**

Run: `pytest tests/test_routes.py -k library_controls tests/test_js_es5.py -v`
Expected: FAIL (boutons absents, clés de stockage absentes).

- [ ] **Step 3: Implémenter les contrôles et la logique ES5**

`watch.html` : sur `<body>` ou `.video-info`, ajouter `data-video-id`, `data-title`, `data-channel`, `data-duration`, `data-view-count` (valeurs échappées par Jinja). Boutons `.action` 44 px : `#favorite` (« ♡ Favori », `aria-pressed="false"`), `#back-10` (« −10 s »), `#forward-10` (« +10 s »), `#fullscreen` (« Plein écran »). `#resume-bar` cachée : « Reprendre à <span id="resume-time"> » + `#resume-yes` / `#resume-no`.

`watch.js` (ajouts) :
- `storage` helpers dans `app.js` : `Lazarus.storage.get(key, fallback)`, `.set(key, value)` (sur quota : supprimer l'entrée la plus ancienne du tableau et réessayer une fois), `.remove(key)` ; tout en `try/catch`.
- Reprise : sur `timeupdate`, si `currentTime > 5` et `< duration - 10`, écrire au plus toutes les 5 s ; à `loadedmetadata`, si une entrée existe, afficher `#resume-bar` avec `Lazarus.formatTime(t)` ; `#resume-yes` → `player.currentTime = t`, cacher ; `#resume-no` → supprimer l'entrée ; sur `ended` → supprimer l'entrée.
- Favoris : `#favorite` lit `lazarus.v1.favorites` au chargement ; bascule l'entrée (métadonnées du dataset), met à jour `textContent` (« ♡ Favori » / « ♥ Favori ») et `aria-pressed`.
- Historique : sur le premier événement `play`, ajouter/mettre à jour l'entrée (déduplication par id, tête de liste, max 50).
- `#back-10` / `#forward-10` : `player.currentTime = Math.max(0, player.currentTime - 10)` / `Math.min(duration || player.duration, ... + 10)`.
- `#fullscreen` : `if (player.webkitEnterFullscreen) { player.webkitEnterFullscreen(); } else if (player.requestFullscreen) { player.requestFullscreen(); }`.
- Erreur du lecteur sur un fichier `ready` : sur `player.error`, relancer `prepare()` en conservant `var resumeAt = player.currentTime`, puis dans `loadedmetadata` restaurer `currentTime` si `resumeAt > 0`.
- Ne jamais utiliser `innerHTML` avec des données issues de `localStorage` ou de l'API.

CSS : `.actions` flex préfixé, boutons blancs bordés, `#favorite[aria-pressed="true"]` corail ; `#resume-bar` fond blanc, bordure turquoise, boutons 44 px.

- [ ] **Step 4: Relancer les tests**

Run: `pytest tests/test_routes.py tests/test_js_es5.py -v`
Expected: PASS.

- [ ] **Step 5: Vérification manuelle sur iPad / Safari 9**

Checklist : lire 30 s, recharger la page → « Reprendre à … » ; reprise et recommencer ; favori puis `/favorites` (après Tâche 12) ; ±10 s ; plein écran ; historique après retour accueil ; mode privé (localStorage indisponible) → aucune erreur visible.

- [ ] **Step 6: Commit**

```bash
git add templates/watch.html static/js/watch.js static/js/app.js static/css/app.css tests/test_routes.py tests/test_js_es5.py
git commit -m "feat: reprise, favoris, historique et contrôles de lecture"
```

---

### Task 12: Bibliothèque historique et favoris

**Files:**
- Create: `templates/library.html`, `static/js/library.js`
- Modify: `app.py` (routes `/history` et `/favorites`), `static/css/app.css`
- Test: `tests/test_routes.py` (ajouts), `tests/test_js_es5.py` (ajouts)

**Interfaces:**
- Consumes: `base.html`, `lazarus.v1.history`, `lazarus.v1.favorites`, `/thumb/<id>.jpg?size=mq`.
- Produces:
  - `GET /history` et `GET /favorites` → `library.html` avec `kind` (`"history"` / `"favorites"`), `active_page`, `title`.
  - `library.js` : lit `document.getElementById("library").getAttribute("data-kind")`, rend `#library-grid`, gère `#library-empty`, `#clear-library`.

- [ ] **Step 1: Écrire les tests qui échouent**

```python
# tests/test_routes.py (ajouts)
def test_history_page_shell(client):
    html = client.get("/history").get_data(as_text=True)
    assert 'data-kind="history"' in html
    assert "Historique" in html
    assert 'id="library-grid"' in html
    assert 'id="library-empty"' in html
    assert 'id="clear-library"' in html
    assert '/static/js/library.js' in html
    assert 'class="nav-link active"' in html

def test_favorites_page_shell(client):
    html = client.get("/favorites").get_data(as_text=True)
    assert 'data-kind="favorites"' in html
    assert "Favoris" in html
    assert 'id="library-grid"' in html
```

```python
# tests/test_js_es5.py (ajouts)
LIBRARY_JS = JS_DIR / "library.js"

def test_library_js_uses_safe_dom_and_storage():
    source = LIBRARY_JS.read_text(encoding="utf-8")
    assert "lazarus.v1.history" in source
    assert "lazarus.v1.favorites" in source
    assert "createElement" in source
    assert "textContent" in source
    assert "innerHTML" not in source
    assert "confirm(" in source
```

- [ ] **Step 2: Lancer les tests pour vérifier l'échec**

Run: `pytest tests/test_routes.py -k "history_page or favorites_page" tests/test_js_es5.py -v`
Expected: FAIL (routes 404, `library.js` absent).

- [ ] **Step 3: Implémenter les routes, le gabarit et le script**

`app.py` : deux routes qui rendent `library.html` avec `kind="history"` / `"favorites"`, `active_page` correspondant et `title`.

`library.html` : étend `base.html` ; `<main id="library" class="container" data-kind="{{ kind }}">` ; titre + compteur `#library-count` ; bouton `#clear-library` (« Vider ») ; `#library-empty` avec « Aucune vidéo pour le moment » + lien accueil ; `#library-grid.results` ; script `library.js`.

`library.js` (IIFE ES5) :
- `kind` depuis `data-kind` ; clé = `lazarus.v1.history` ou `lazarus.v1.favorites`.
- `render()` : vider la grille avec `while (grid.firstChild) { grid.removeChild(grid.firstChild); }` ; si liste vide → montrer `#library-empty`, cacher `#clear-library` ; sinon construire chaque carte avec `document.createElement` (`a.card` href `/watch?v=`, `.card-thumb` + `img` src `/thumb/<id>.jpg?size=mq` + `alt=""`, `.card-title` via `textContent`, `.card-meta`), et un bouton `.card-remove` (« Retirer ») qui supprime l'entrée et réécrit le stockage.
- `#clear-library` → `confirm("Vider tout l'historique ?")` / `confirm("Vider tous les favoris ?")`, puis écrire `[]`.
- Utiliser `Lazarus.storage` ; aucune exception visible si `localStorage` est indisponible (afficher l'état vide).

CSS : `.card-remove` 44 px, texte corail, fond transparent ; `#library-count` 14 px `#62788A` ; `#library-empty` carte blanche centrée.

- [ ] **Step 4: Relancer les tests**

Run: `pytest tests/test_routes.py tests/test_js_es5.py -v`
Expected: PASS.

- [ ] **Step 5: Vérification manuelle**

Lire deux vidéos, ouvrir `/history` → deux cartes, plus récente en tête ; retirer une carte ; vider ; mettre une vidéo en favori puis ouvrir `/favorites`.

- [ ] **Step 6: Commit**

```bash
git add app.py templates/library.html static/js/library.js static/css/app.css tests/test_routes.py tests/test_js_es5.py
git commit -m "feat: pages historique et favoris"
```

---

### Task 13: Assets, Docker, waitress et documentation

**Files:**
- Create: `static/img/logo.png`, `static/img/apple-touch-icon.png`, `static/img/favicon.png`, `.dockerignore`
- Modify: `requirements.txt`, `Dockerfile`, `docker-compose.yml`, `README.md`, `templates/base.html` (chemins d'assets si nécessaire)
- Test: vérifications de commandes (pas de nouveau test pytest)

**Interfaces:**
- Consumes: `logoLazarusTube.png` (1408×768 RGBA).
- Produces: image Docker lançant `waitress-serve --threads=16 --call app:create_app`, volume `/cache`, healthcheck `/healthz`.

- [ ] **Step 1: Générer les assets**

```bash
mkdir -p static/img
convert logoLazarusTube.png -resize 352x192 static/img/logo.png
convert logoLazarusTube.png -resize 132x132 -background '#F4F8F9' -alpha remove -alpha off \
  -gravity center -extent 152x152 static/img/apple-touch-icon.png
convert logoLazarusTube.png -resize 32x32 static/img/favicon.png
```

- [ ] **Step 2: Vérifier les dimensions**

Run: `identify static/img/logo.png static/img/apple-touch-icon.png static/img/favicon.png`
Expected: `352x192`, `152x152`, `32x32`.

- [ ] **Step 3: Mettre à jour les dépendances et le déploiement**

`requirements.txt` :

```
flask==3.0.3
requests==2.32.3
waitress==3.0.2
yt-dlp
```

`requirements-dev.txt` existe déjà (Tâche 1) et contient `pytest`.

`Dockerfile` : conserver `ffmpeg`, `ca-certificates`, `nodejs` ; `CMD ["waitress-serve", "--listen=0.0.0.0:3616", "--threads=16", "--call", "app:create_app"]`.

`docker-compose.yml` :

```yaml
services:
  lazaratus:
    build: .
    container_name: lazaratus-tube
    ports:
      - "3616:3616"
    restart: unless-stopped
    environment:
      - LAZARUS_CACHE_DIR=/cache
      - LAZARUS_MAX_CACHE_BYTES=5368709120
      - LAZARUS_MAX_CONCURRENT_DOWNLOADS=2
      - LAZARUS_LOG_LEVEL=INFO
    volumes:
      - lazarus-cache:/cache
    healthcheck:
      test: ["CMD", "python", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:3616/healthz').read()"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 20s

volumes:
  lazarus-cache:
```

`.dockerignore` : `.git`, `__pycache__`, `*.pyc`, `.pytest_cache`, `tests`, `docs`, `logoLazarusTube.png`, `.DS_Store`.

`README.md` : remplacer le contenu par les sections : présentation et cible iPad 2 / iOS 9 ; lancement local (`python app.py`, port 3616) ; Docker Compose ; variables d'environnement (table §17) ; architecture des modules ; cache et volume ; tests (`pytest`) ; dépannage yt-dlp (mise à jour, anti-bot, node) ; limites connues (3 lectures simultanées, pas de HTTPS, pas d'autoplay).

- [ ] **Step 4: Vérifier la configuration Docker**

Run: `docker compose config -q`
Expected: aucune sortie, code 0.

- [ ] **Step 5: Construire et démarrer l'image**

Run: `docker compose build && docker compose up -d && sleep 5 && curl -s http://127.0.0.1:3616/healthz && docker compose down`
Expected: build OK, healthcheck `{"status":"ok",...}`.

- [ ] **Step 6: Commit**

```bash
git add static/img requirements.txt requirements-dev.txt Dockerfile docker-compose.yml .dockerignore README.md templates/base.html
git commit -m "chore: assets, waitress, volume de cache et documentation"
```

---

### Task 14: Garde-fous Safari 9 et vérification finale

**Files:**
- Modify: `tests/test_js_es5.py` (garde CSS + gabarits), `README.md` (section vérification si nécessaire)
- Create: `docs/manual-test-ios9.md`

**Interfaces:**
- Consumes: tout le projet.
- Produces: suite de tests complète et checklist manuelle iPad.

- [ ] **Step 1: Ajouter les tests de garde**

```python
# tests/test_js_es5.py (ajouts)
CSS = pathlib.Path(__file__).resolve().parents[1] / "static" / "css" / "app.css"
TEMPLATES = pathlib.Path(__file__).resolve().parents[1] / "templates"

FORBIDDEN_CSS = [
    r"display\s*:\s*grid", r"var\s*\(\s*--", r"position\s*:\s*sticky",
    r"(?<![-a-z])gap\s*:", r"aspect-ratio", r"clamp\s*\(", r":focus-visible",
]

def test_css_is_safari9_compatible():
    source = CSS.read_text(encoding="utf-8")
    for pattern in FORBIDDEN_CSS:
        assert not re.search(pattern, source), "CSS interdit : " + pattern

def test_templates_do_not_disable_zoom():
    for path in TEMPLATES.rglob("*.html"):
        source = path.read_text(encoding="utf-8")
        assert "user-scalable=no" not in source, path.name

def test_video_tags_are_ios9_ready():
    source = (TEMPLATES / "watch.html").read_text(encoding="utf-8")
    assert "playsinline" in source
    assert "webkit-playsinline" in source
    assert "autoplay" not in source
```

- [ ] **Step 2: Lancer toute la suite**

Run: `pytest -q`
Expected: PASS, 0 échec.

- [ ] **Step 3: Vérifier la compilation Python**

Run: `python -m compileall -q app.py config.py ids.py formats.py streaming.py cache.py ytdlp.py jobs.py`
Expected: code 0, aucune sortie.

- [ ] **Step 4: Smoke test local des routes**

Run:
```bash
LAZARUS_CACHE_DIR=/tmp/lazarus-smoke python app.py &
sleep 2
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:3616/
curl -s -o /dev/null -w "%{http_code}\n" http://127.0.0.1:3616/healthz
curl -s -o /dev/null -w "%{http_code}\n" "http://127.0.0.1:3616/stream?v=dQw4w9WgXcQ"
curl -s -o /dev/null -w "%{http_code}\n" "http://127.0.0.1:3616/check?v=dQw4w9WgXcQ"
kill %1
```
Expected: `200`, `200`, `425`, `404`.

- [ ] **Step 5: Écrire la checklist manuelle**

`docs/manual-test-ios9.md` : reprendre la liste §15 de la spec (recherche, miniatures, lecture, seek, pause/reprise, reprise de position, historique, favoris, URL collée, ID invalide, erreur + retry, vidéo longue, 720p, cache vidé, redémarrage du conteneur, mode privé) avec une case à cocher par item et une colonne « résultat ».

- [ ] **Step 6: Commit**

```bash
git add tests/test_js_es5.py docs/manual-test-ios9.md README.md
git commit -m "test: garde-fous Safari 9 et checklist de vérification iPad"
```

---

## Self-Review

**Couverture de la spec :** chaque section est portée par une tâche — §5 architecture (Tâches 1–8), §6 flux (7–12), §7 API (8), §8 machine à états (7), §9 formats (2, 6, 7), §10 cache (4, 5), §11 design (9–12), §12 P2 (9, 11, 12), §13 erreurs (8), §14 sécurité (1, 2, 6, 8), §15 tests (toutes), §17 Docker (13), §18 critères (14).

**Cohérence des interfaces :** `MediaCache` expose `root` (utilisé par `JobRegistry`), `registry` (utilisé par les tests et `jobs`), et les méthodes listées en Tâche 4 ; `ThumbCache.fetcher` est remplaçable (utilisé par `test_thumb_serves_jpeg`) ; `YtDlp.download(max_height=...)` correspond au fallback de la Tâche 7 ; `create_app` accepte `ytdlp` et `thumbs_fetcher` dans `overrides` (Tâche 8).

**Review Focus :** reprise/redémarrage (Tâches 7, 8, 11), directs (6, 7), 720p60/VP9 (2, 7), Range suffixe/invalide (3), échec de miniature (5, 8, 9).
