"""提示词里几条硬约束的回归测试。

这些不是文风：每一条都对应实现或部署上的一个前提，删掉任何一条都会让 agent 白跑几轮，
而那种失败不会让任何测试变红 —— 只会表现成 token 账单变高。
"""

from app.agent.config import AgentConfig
from app.agent.prompt import ANALYSIS_SEGMENT, ENVIRONMENT_SEGMENT, ROLE_SEGMENT, SYSTEM_PROMPT, compose_prompt
from app.sandbox.path import OUTPUT_DIR, SANDBOX_ROOT


def test_the_prompt_names_the_working_directory() -> None:
    assert SANDBOX_ROOT in SYSTEM_PROMPT


def test_the_prompt_names_the_artifact_directory() -> None:
    """产物判定只认这一个目录，agent 存到别处就等于产物丢失。"""
    assert f"{SANDBOX_ROOT}/{OUTPUT_DIR}/" in SYSTEM_PROMPT


def test_the_prompt_requires_writing_a_file_before_executing() -> None:
    assert "write_file" in SYSTEM_PROMPT
    assert "execute" in SYSTEM_PROMPT


def test_the_prompt_tells_the_agent_how_to_install_packages() -> None:
    """不说清楚就白白浪费轮次：agent 猜不到装的包会留在会话里，也猜不到不用加 --user。"""
    assert "pip install" in SYSTEM_PROMPT


def test_the_prompt_rules_out_installing_system_packages() -> None:
    """容器里没有 root，apt 必然失败。不写明，agent 会拿它试上几轮才放弃。"""
    assert "apt-get" in SYSTEM_PROMPT


def test_the_prompt_routes_file_removal_through_the_delete_tool() -> None:
    """删除要教师点头，而 `execute` 里的 `rm` 同样会被拦下来。

    不写这条，agent 会自己选 `rm`（2026-08-18 实测四次全选了它），于是每一次删除
    都要多跑一轮审批往返 —— 闸门拦得住，但白花一次等待。
    """
    assert "delete" in ENVIRONMENT_SEGMENT
    assert "rm" in ENVIRONMENT_SEGMENT


def test_the_prompt_forbids_hunting_for_chinese_fonts() -> None:
    """实测到的第一个真实失败模式：agent 为找中文字体跑了一轮 pip 与 apt 去搜。

    开网之后 pip 那半边不再必然失败，但字体本来就装好了，找字体仍然是纯浪费轮次。
    """
    assert "字体" in SYSTEM_PROMPT
    assert "rcParams" in SYSTEM_PROMPT


def test_the_prompt_specifies_the_artifact_citation_format() -> None:
    """前端按 Markdown 图片语法渲染产物（doc/02visual/04 M3）。

    没有这条，图表只出现在文件面板里，对话答复看不到。路径必须相对 /workspace，
    前端只放行 outputs/ 前缀。
    """
    assert "Markdown 图片语法" in SYSTEM_PROMPT
    assert "![各行业年化波动率](outputs/volatility_chart.png)" in SYSTEM_PROMPT


def test_the_default_prompt_is_composed_from_all_platform_segments() -> None:
    assert compose_prompt(AgentConfig()) == SYSTEM_PROMPT
    assert ROLE_SEGMENT in SYSTEM_PROMPT
    assert ANALYSIS_SEGMENT in SYSTEM_PROMPT
    assert ENVIRONMENT_SEGMENT in SYSTEM_PROMPT


def test_a_custom_prompt_replaces_only_the_role_segment() -> None:
    custom = "你是一只认真做金融分析的猫。"

    prompt = compose_prompt(AgentConfig(system_prompt=custom))

    assert custom in prompt
    assert ROLE_SEGMENT not in prompt
    assert ANALYSIS_SEGMENT in prompt
    assert ENVIRONMENT_SEGMENT in prompt


def test_the_environment_contract_is_always_last() -> None:
    custom = "把图保存到当前目录。"

    prompt = compose_prompt(AgentConfig(system_prompt=custom))

    assert prompt.index(custom) < prompt.index(ANALYSIS_SEGMENT) < prompt.index(ENVIRONMENT_SEGMENT)
    assert prompt.endswith(ENVIRONMENT_SEGMENT)
