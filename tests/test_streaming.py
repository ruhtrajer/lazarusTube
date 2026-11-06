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

def test_head_missing_file_has_no_body(client, tmp_path):
    with client.application.test_request_context("/stream", method="HEAD"):
        resp = range_response(str(tmp_path / "absent.mp4"), None, head=True)
        assert resp.status_code == 404
        assert resp.headers["Content-Length"] == "20"
        assert resp.get_data() == b""

def test_head_invalid_range_has_no_body(client, media):
    with client.application.test_request_context("/stream", method="HEAD"):
        resp = range_response(media, "bytes=999999-", head=True)
        assert resp.status_code == 416
        assert resp.headers["Content-Range"] == "bytes */1024"
        assert resp.headers["Content-Length"] == "24"
        assert resp.get_data() == b""

def test_closing_unstarted_response_calls_registry_end_once(client, media):
    reg = Registry()
    with client.application.test_request_context("/stream"):
        resp = range_response(media, "bytes=0-99", reg)
        assert reg.events == [("begin", media)]
        resp.close()
        resp.close()
    assert reg.events == [("begin", media), ("end", media)]

