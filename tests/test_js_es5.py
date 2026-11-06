import pathlib
import re

JS_DIR = pathlib.Path(__file__).resolve().parents[1] / "static" / "js"
WATCH_JS = JS_DIR / "watch.js"
LIBRARY_JS = JS_DIR / "library.js"
CSS = pathlib.Path(__file__).resolve().parents[1] / "static" / "css" / "app.css"
TEMPLATES = pathlib.Path(__file__).resolve().parents[1] / "templates"
FORBIDDEN = [r"=>", r"\bconst\s", r"\blet\s", r"\basync\s", r"\bawait\s", r"`", r"\bfetch\s*\("]
FORBIDDEN_CSS = [
    r"display\s*:\s*grid",
    r"var\s*\(\s*--",
    r"position\s*:\s*sticky",
    r"(?<![-a-z])gap\s*:",
    r"aspect-ratio",
    r"clamp\s*\(",
    r":focus-visible",
]

def test_js_files_are_es5():
    files = sorted(JS_DIR.glob("*.js"))
    assert files, "aucun fichier JS trouvé"
    for path in files:
        source = path.read_text(encoding="utf-8")
        for pattern in FORBIDDEN:
            assert not re.search(pattern, source), "%s contient %s" % (path.name, pattern)

def test_watch_js_declares_storage_contract():
    source = WATCH_JS.read_text(encoding="utf-8")
    assert "lazarus.v1.resume" in source
    assert "lazarus.v1.history" in source
    assert "lazarus.v1.favorites" in source
    assert "webkitEnterFullscreen" in source

def test_watch_js_has_no_innerhtml_with_metadata():
    source = WATCH_JS.read_text(encoding="utf-8")
    assert "innerHTML" not in source

def test_watch_js_player_error_guard_not_reset_on_metadata():
    # Le garde anti-boucle ne doit pas être réarmé par loadedmetadata,
    # sinon un flux corrompu boucle indéfiniment sur /api/prepare.
    source = WATCH_JS.read_text(encoding="utf-8")
    start = source.find("function onLoadedMetadata()")
    assert start != -1
    end = source.find("function onEnded()", start)
    assert end != -1
    assert "errorRetried = false" not in source[start:end]

def test_library_js_uses_safe_dom_and_storage():
    source = LIBRARY_JS.read_text(encoding="utf-8")
    assert "lazarus.v1.history" in source
    assert "lazarus.v1.favorites" in source
    assert "createElement" in source
    assert "textContent" in source
    assert "innerHTML" not in source
    assert "confirm(" in source


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
