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
