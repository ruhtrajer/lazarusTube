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
