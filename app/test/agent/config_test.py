import pytest
from pydantic import ValidationError

from agent.config import MAX_SYSTEM_PROMPT_LENGTH, AgentConfig


def test_an_empty_config_means_platform_defaults() -> None:
    assert AgentConfig().model_dump(exclude_none=True) == {}


def test_a_prompt_at_the_limit_is_accepted() -> None:
    prompt = "角" * MAX_SYSTEM_PROMPT_LENGTH

    assert AgentConfig(system_prompt=prompt).system_prompt == prompt


def test_a_prompt_over_the_limit_is_rejected() -> None:
    with pytest.raises(ValidationError):
        AgentConfig(system_prompt="角" * (MAX_SYSTEM_PROMPT_LENGTH + 1))


def test_an_unknown_field_is_rejected() -> None:
    with pytest.raises(ValidationError):
        AgentConfig.model_validate({"skills": ["not-yet-supported"]})
