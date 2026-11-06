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
