import logging
import pickle
import socket
from pathlib import Path

import pytest

from content_engine.config import ConfigError, Secret, load_config

FAKE_KEY = "sk-test-FAKE-1234567890"
ROOT = Path(__file__).resolve().parent.parent


@pytest.fixture
def project(tmp_path):
    (tmp_path / "config").mkdir()
    for name in ("settings.yaml", "brand_voice.yaml"):
        (tmp_path / "config" / name).write_text(
            (ROOT / "config" / name).read_text(encoding="utf-8"), encoding="utf-8"
        )
    return tmp_path


def test_loads_from_env_file(project):
    (project / ".env").write_text(f"OPENAI_API_KEY={FAKE_KEY}\n")
    cfg = load_config(project, env={})
    assert cfg.api_key.reveal() == FAKE_KEY
    assert cfg.settings.counts.tweets == 10
    assert cfg.brand_voice.name


def test_real_env_var_overrides_env_file(project):
    (project / ".env").write_text("OPENAI_API_KEY=from-file\n")
    cfg = load_config(project, env={"OPENAI_API_KEY": FAKE_KEY})
    assert cfg.api_key.reveal() == FAKE_KEY


@pytest.mark.parametrize("content", [None, "", "OPENAI_API_KEY=\n", "OPENAI_API_KEY=   \n"])
def test_missing_or_empty_key(project, content):
    if content is not None:
        (project / ".env").write_text(content)
    with pytest.raises(ConfigError, match="missing or empty"):
        load_config(project, env={})


def test_malformed_yaml(project):
    (project / ".env").write_text(f"OPENAI_API_KEY={FAKE_KEY}\n")
    (project / "config" / "settings.yaml").write_text("model: [unclosed\n")
    with pytest.raises(ConfigError, match="not valid YAML"):
        load_config(project, env={})


def test_invalid_settings_value(project):
    (project / ".env").write_text(f"OPENAI_API_KEY={FAKE_KEY}\n")
    (project / "config" / "settings.yaml").write_text("model: gpt\ntemperature: 99\n")
    with pytest.raises(ConfigError, match="temperature"):
        load_config(project, env={})


def test_missing_config_file(project):
    (project / "config" / "brand_voice.yaml").unlink()
    with pytest.raises(ConfigError, match="not found"):
        load_config(project, env={"OPENAI_API_KEY": FAKE_KEY})


def test_secret_never_appears_in_text(project, caplog):
    (project / ".env").write_text(f"OPENAI_API_KEY={FAKE_KEY}\n")
    caplog.set_level(logging.DEBUG)
    cfg = load_config(project, env={})
    for text in (repr(cfg), str(cfg), repr(cfg.api_key), str(cfg.api_key), f"{cfg.api_key}"):
        assert FAKE_KEY not in text
    assert FAKE_KEY not in caplog.text


def test_secret_not_in_error_messages(project):
    (project / ".env").write_text(f"OPENAI_API_KEY={FAKE_KEY}\n")
    (project / "config" / "settings.yaml").write_text("model: gpt\ntemperature: 99\n")
    with pytest.raises(ConfigError) as exc:
        load_config(project, env={})
    assert FAKE_KEY not in str(exc.value)


def test_secret_cannot_be_pickled():
    with pytest.raises(TypeError):
        pickle.dumps(Secret(FAKE_KEY))


def test_network_is_blocked():
    with pytest.raises(RuntimeError, match="blocked"):
        socket.create_connection(("example.com", 80))
