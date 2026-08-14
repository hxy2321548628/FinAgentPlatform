from typing import cast
from uuid import uuid4

import pytest
from pydantic import ValidationError

from agent.config import (
    MAX_SYSTEM_PROMPT_LENGTH,
    AgentConfig,
    AgentConfigRequest,
    effective_config,
)


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


def test_a_snapshot_carries_the_reference_and_the_prompt_it_resolved_to() -> None:
    """快照里三样都在：谁的、哪一版、那一版的原文。只看输出的话分不清引用生效了没有。"""
    agent_id = uuid4().hex

    snapshot = AgentConfig(system_prompt="每句以喵开头", agent_id=agent_id, agent_version=2)

    assert snapshot.model_dump(exclude_none=True) == {
        "system_prompt": "每句以喵开头",
        "agent_id": agent_id,
        "agent_version": 2,
    }


def test_picking_an_agent_and_writing_a_prompt_are_mutually_exclusive() -> None:
    """同时给两样时，哪一样生效只能靠约定 —— 而约定错了的表现是「今天这个 agent 不太灵」。"""
    with pytest.raises(ValidationError):
        AgentConfigRequest(system_prompt="自己写的", agent_id=uuid4().hex)


def test_either_source_alone_is_fine() -> None:
    assert AgentConfigRequest(system_prompt="自己写的").agent_id is None
    assert AgentConfigRequest(agent_id=uuid4().hex).system_prompt is None
    assert AgentConfigRequest().model_dump(exclude_none=True) == {}


def test_a_request_cannot_pin_a_version_itself() -> None:
    """版本由平台在提交那一刻定，不是使用者能指的 —— 否则谁都能钉在一个早已撤下的版本上。"""
    with pytest.raises(ValidationError):
        AgentConfigRequest.model_validate({"agent_version": 1})


def test_a_run_inherits_the_thread_default_when_it_overrides_nothing() -> None:
    configured: dict[str, object] = {"system_prompt": "每句以喵开头"}

    assert effective_config(thread_config=configured, override=None).model_dump(exclude_none=True) == configured


def test_a_run_override_replaces_the_whole_thread_default() -> None:
    effective = effective_config(
        thread_config={"system_prompt": "thread"},
        override=AgentConfigRequest(system_prompt="run"),
    )

    assert effective.model_dump(exclude_none=True) == {"system_prompt": "run"}


def test_an_explicit_empty_override_clears_the_thread_default() -> None:
    """`None` 是「这一轮没覆盖」，空对象是「整块改回平台默认」—— 两种语义不能合并。"""
    effective = effective_config(thread_config={"system_prompt": "thread"}, override=AgentConfigRequest())

    assert effective.model_dump(exclude_none=True) == {}


def test_a_thread_default_may_hold_an_agent_reference() -> None:
    """会话默认里存着 agent_id 时，每一轮都按它去解析 —— 撤回共享之后下一次提问就该报错。"""
    agent_id = uuid4().hex

    effective = effective_config(thread_config={"agent_id": agent_id}, override=None)

    assert effective.agent_id == agent_id
    assert effective.agent_version is None


def test_a_dirty_legacy_thread_config_is_rejected_rather_than_ignored() -> None:
    """当成空配置放过的话，一个配错的会话会安静地按平台默认跑下去。"""
    with pytest.raises(ValidationError):
        effective_config(thread_config={"model": "legacy"}, override=None)


def test_a_falsy_non_object_thread_config_is_not_treated_as_the_default() -> None:
    with pytest.raises(ValidationError):
        effective_config(thread_config=cast(dict[str, object], []), override=None)
