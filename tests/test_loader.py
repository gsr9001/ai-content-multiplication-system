import pytest

from content_engine import loader
from content_engine.loader import LoaderError, clean_text, load_source


def write(tmp_path, name, content, mode="w"):
    p = tmp_path / name
    if isinstance(content, bytes):
        p.write_bytes(content)
    else:
        p.write_text(content, encoding="utf-8", newline="")
    return p


def test_loads_normal_file(tmp_path):
    p = write(tmp_path, "a.md", "word " * 300)
    src = load_source(p)
    assert src.word_count == 300
    assert src.warnings == []
    assert src.path == p


def test_accepts_txt_and_uppercase_suffix(tmp_path):
    assert load_source(write(tmp_path, "a.txt", "word " * 250)).word_count == 250
    assert load_source(write(tmp_path, "B.MD", "word " * 250)).word_count == 250


def test_missing_file(tmp_path):
    with pytest.raises(LoaderError, match="not found"):
        load_source(tmp_path / "nope.md")


def test_directory_is_not_a_file(tmp_path):
    with pytest.raises(LoaderError, match="not found"):
        load_source(tmp_path)


def test_wrong_extension(tmp_path):
    with pytest.raises(LoaderError, match="Unsupported file type"):
        load_source(write(tmp_path, "a.pdf", "word " * 300))


@pytest.mark.parametrize("content", ["", "   \n\n\t \n"])
def test_empty_or_blank_file(tmp_path, content):
    with pytest.raises(LoaderError, match="empty"):
        load_source(write(tmp_path, "a.md", content))


def test_too_large(tmp_path, monkeypatch):
    monkeypatch.setattr(loader, "MAX_BYTES", 100)
    with pytest.raises(LoaderError, match="too large"):
        load_source(write(tmp_path, "a.md", "x" * 101))


def test_invalid_utf8(tmp_path):
    with pytest.raises(LoaderError, match="UTF-8"):
        load_source(write(tmp_path, "a.md", b"\xff\xfe\x00bad\x80"))


def test_short_input_warns(tmp_path):
    src = load_source(write(tmp_path, "a.md", "just a few words"))
    assert len(src.warnings) == 1 and "short" in src.warnings[0]


def test_long_input_warns(tmp_path, monkeypatch):
    monkeypatch.setattr(loader, "LONG_WORDS", 300)
    src = load_source(write(tmp_path, "a.md", "word " * 400))
    assert any("very long" in w for w in src.warnings)


def test_strips_bom_and_normalizes_newlines(tmp_path):
    raw = b"\xef\xbb\xbfLine one\r\nLine two\rLine three\n"
    src = load_source(write(tmp_path, "a.md", raw))
    assert src.text == "Line one\nLine two\nLine three"


def test_clean_text_collapses_blank_runs_and_trailing_space():
    assert clean_text("a  \n\n\n\n\nb\t\n") == "a\n\nb"


def test_clean_text_removes_control_chars_keeps_unicode():
    assert clean_text("café\x00 \x07ok — \U0001F600") == "café ok — \U0001F600"
