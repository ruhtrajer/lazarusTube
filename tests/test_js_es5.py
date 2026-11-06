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
