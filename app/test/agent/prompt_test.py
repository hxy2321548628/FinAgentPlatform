"""提示词里几条硬约束的回归测试。

这些不是文风：每一条都对应实现或部署上的一个前提，删掉任何一条都会让 agent 白跑几轮，
而那种失败不会让任何测试变红 —— 只会表现成 token 账单变高。
"""

from agent.prompt import SYSTEM_PROMPT
from sandbox.backend import OUTPUT_DIR
from sandbox.path import SANDBOX_ROOT


def test_the_prompt_names_the_working_directory() -> None:
    assert SANDBOX_ROOT in SYSTEM_PROMPT


def test_the_prompt_names_the_artifact_directory() -> None:
    """产物判定只认这一个目录，agent 存到别处就等于产物丢失。"""
    assert f"{SANDBOX_ROOT}/{OUTPUT_DIR}/" in SYSTEM_PROMPT


def test_the_prompt_requires_writing_a_file_before_executing() -> None:
    assert "write_file" in SYSTEM_PROMPT
    assert "execute" in SYSTEM_PROMPT


def test_the_prompt_states_there_is_no_public_network() -> None:
    """沙箱零出网，不说清楚 agent 会反复尝试联网取数据。"""
    assert "公网" in SYSTEM_PROMPT


def test_the_prompt_forbids_hunting_for_chinese_fonts() -> None:
    """实测到的第一个真实失败模式：agent 为找中文字体跑了一轮 pip 与 apt，在零出网的沙箱里必然全败。"""
    assert "字体" in SYSTEM_PROMPT
    assert "rcParams" in SYSTEM_PROMPT
