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
