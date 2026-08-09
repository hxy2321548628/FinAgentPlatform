from pathlib import Path

import pytest
from pydantic import ValidationError

from config import Settings, get_settings

# 用例只应受自己设的值影响，因此每次都先把这几个变量从进程环境里清掉。
# 开发机的 shell 里可能已 export 过同名变量，不清会让默认值用例假绿。
ENV_VAR_NAME = ("DEEPSEEK_API_KEY", "DEEPSEEK_BASE_URL", "MODEL_MAIN", "MODEL_AUX")


@pytest.fixture
def clean_env(monkeypatch: pytest.MonkeyPatch) -> None:
    for name in ENV_VAR_NAME:
        monkeypatch.delenv(name, raising=False)


def test_missing_api_key_fails_at_construction(clean_env: None) -> None:
    with pytest.raises(ValidationError):
        Settings(_env_file=None)


def test_api_key_read_from_environment(clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-fake-for-test")

    settings = Settings(_env_file=None)

    assert settings.deepseek_api_key.get_secret_value() == "sk-fake-for-test"


def test_only_api_key_given_others_fall_back_to_defaults(clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-fake-for-test")

    settings = Settings(_env_file=None)

    assert settings.deepseek_base_url == "https://api.deepseek.com"
    assert settings.model_main == "deepseek-v4-pro"
    assert settings.model_aux == "deepseek-v4-flash"


def test_environment_overrides_defaults(clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-fake-for-test")
    monkeypatch.setenv("MODEL_MAIN", "deepseek-v4-flash")

    settings = Settings(_env_file=None)

    assert settings.model_main == "deepseek-v4-flash"


def test_env_file_resolves_to_repo_root_not_app_dir() -> None:
    repo_root = Path(__file__).resolve().parent.parent.parent

    assert Settings.model_config["env_file"] == repo_root / ".env"


def test_get_settings_returns_the_same_instance(clean_env: None, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DEEPSEEK_API_KEY", "sk-fake-for-test")
    get_settings.cache_clear()

    first = get_settings()
    second = get_settings()

    assert first is second

    get_settings.cache_clear()
