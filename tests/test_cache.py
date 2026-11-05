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


def test_registry_end_never_goes_negative():
    reg = StreamRegistry()
    reg.end("x")
    assert reg.is_active("x") is False
    reg.begin("x")
    reg.begin("x")
    reg.end("x")
    assert reg.is_active("x") is True
    reg.end("x")
    reg.end("x")
    assert reg.is_active("x") is False


def test_has_rejects_empty_and_missing_files(tmp_path):
    media, _ = make_media(tmp_path)
    media.ensure_dirs()
    assert media.has("aaaaaaaaaaa") is False
    with open(media.media_path("aaaaaaaaaaa"), "wb"):
        pass
    assert media.has("aaaaaaaaaaa") is False


def test_read_meta_tolerates_invalid_json(tmp_path):
    media, _ = make_media(tmp_path)
    media.ensure_dirs()
    with open(media.meta_path("aaaaaaaaaaa"), "w", encoding="utf-8") as handle:
        handle.write("{not json")
    assert media.read_meta("aaaaaaaaaaa") is None


def test_touch_updates_mtime(tmp_path):
    media, _ = make_media(tmp_path)
    media.ensure_dirs()
    media.publish("aaaaaaaaaaa", write_tmp(tmp_path), {"title": "A"})
    old = time.time() - 1000
    os.utime(media.media_path("aaaaaaaaaaa"), (old, old))
    media.touch("aaaaaaaaaaa")
    assert os.stat(media.media_path("aaaaaaaaaaa")).st_mtime > old


def test_clean_tmp_removes_only_old_entries(tmp_path):
    media, _ = make_media(tmp_path)
    media.ensure_dirs()
    tmp_dir = os.path.join(media.root, "tmp")
    old_file = os.path.join(tmp_dir, "old.mp4")
    new_file = os.path.join(tmp_dir, "new.mp4")
    old_dir = os.path.join(tmp_dir, "old-dir")
    with open(old_file, "wb") as handle:
        handle.write(b"x")
    with open(new_file, "wb") as handle:
        handle.write(b"x")
    os.makedirs(old_dir)
    old = time.time() - 7200
    os.utime(old_file, (old, old))
    os.utime(old_dir, (old, old))
    media.clean_tmp(max_age=3600)
    assert not os.path.exists(old_file)
    assert not os.path.exists(old_dir)
    assert os.path.exists(new_file)


def test_writable_and_free_bytes(tmp_path):
    media, _ = make_media(tmp_path)
    media.ensure_dirs()
    assert media.writable() is True
    assert media.free_bytes() > 0
    assert not os.path.exists(os.path.join(media.root, ".probe"))


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
