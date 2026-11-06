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
        self.dirs = []
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
        self.dirs.append(tmpdir)
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

def test_fallback_480_uses_fresh_temp_directory(tmp_path, monkeypatch):
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
    assert len(fake.dirs) == 2
    assert fake.dirs[0] != fake.dirs[1]
    assert seen[0] != seen[1]

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
