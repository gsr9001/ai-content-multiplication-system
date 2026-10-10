"""Load and validate configuration: API key, settings, brand voice."""

import os
from collections.abc import Mapping
from pathlib import Path

import yaml
from dotenv import dotenv_values
from pydantic import BaseModel, ConfigDict, Field, ValidationError

KEY_NAME = "OPENAI_API_KEY"


class ConfigError(Exception):
    """A problem with configuration. Messages never contain secret values."""


class Secret:
    """Holds a secret; str/repr never reveal it. Call .reveal() only to use it."""

    __slots__ = ("_value",)

    def __init__(self, value: str) -> None:
        self._value = value

    def reveal(self) -> str:
        return self._value

    def __repr__(self) -> str:
        return "Secret(***)"

    __str__ = __repr__

    def __reduce__(self):
        raise TypeError("Secret cannot be pickled")


class Counts(BaseModel):
    model_config = ConfigDict(extra="forbid")
    linkedin_posts: int = Field(5, ge=1)
    tweets: int = Field(10, ge=1)
    newsletter_sections: int = Field(3, ge=1)
    substack_notes: int = Field(3, ge=1)
    youtube_scripts: int = Field(2, ge=1)


class Settings(BaseModel):
    model_config = ConfigDict(extra="forbid")
    model: str = Field(min_length=1)
    temperature: float = Field(0.7, ge=0, le=2)
    max_transport_retries: int = Field(3, ge=0, le=10)
    max_validation_retries: int = Field(1, ge=0, le=3)
    counts: Counts = Counts()


class BrandVoice(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1)
    tone: str = Field(min_length=1)
    audience: str = Field(min_length=1)
    do: list[str] = []
    dont: list[str] = []
    sample_phrases: list[str] = []


class Config:
    def __init__(self, api_key: Secret, settings: Settings, brand_voice: BrandVoice) -> None:
        self.api_key = api_key
        self.settings = settings
        self.brand_voice = brand_voice

    def __repr__(self) -> str:
        return f"Config(model={self.settings.model!r}, voice={self.brand_voice.name!r}, api_key=***)"


def _load_yaml(path: Path, model: type[BaseModel]) -> BaseModel:
    if not path.is_file():
        raise ConfigError(f"Config file not found: {path}")
    try:
        data = yaml.safe_load(path.read_text(encoding="utf-8"))
    except yaml.YAMLError:
        raise ConfigError(f"{path.name} is not valid YAML.") from None
    if not isinstance(data, dict):
        raise ConfigError(f"{path.name} must contain a YAML mapping of settings.")
    try:
        return model.model_validate(data)
    except ValidationError as exc:
        problems = "; ".join(
            f"{'.'.join(str(p) for p in e['loc'])}: {e['msg']}" for e in exc.errors()
        )
        raise ConfigError(f"Invalid {path.name}: {problems}") from None


def load_api_key(project_root: Path, env: Mapping[str, str] | None = None) -> Secret:
    """Real environment variable wins over .env. Never echoes the value."""
    env = os.environ if env is None else env
    value = env.get(KEY_NAME) or dotenv_values(project_root / ".env").get(KEY_NAME)
    value = (value or "").strip()
    if not value:
        raise ConfigError(f"{KEY_NAME} is missing or empty. Set it in .env (see .env.example).")
    return Secret(value)


def load_config(
    project_root: Path,
    env: Mapping[str, str] | None = None,
    voice_path: Path | None = None,
) -> Config:
    root = Path(project_root)
    settings = _load_yaml(root / "config" / "settings.yaml", Settings)
    voice = _load_yaml(voice_path or root / "config" / "brand_voice.yaml", BrandVoice)
    return Config(load_api_key(root, env), settings, voice)
