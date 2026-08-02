"""探针公用：读 .env、准备 workspace、落盘输出。

spike 是一次性验证代码，跑完即弃（见 doc/01design/01architecture.md §11 P0 探针）。
刻意不引入新依赖，.env 用十几行手写解析，不装 python-dotenv。
"""

from __future__ import annotations

import json
import os
import shutil
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[2]
SPIKE_DIR = Path(__file__).resolve().parent
OUT_DIR = SPIKE_DIR / "out"


def drop_socks_proxy() -> None:
    """剥掉 socks 代理变量。

    开发机上设了 ALL_PROXY=socks://…，而 httpx 不认 socks 方案（除非装 httpx[socks]），
    ChatDeepSeek 构造时会直接报错。api.deepseek.com 实测可直连，剥掉即可。
    这是开发机环境问题，与平台部署无关 —— 内网服务器上不会有这些变量。
    """
    for name in ("ALL_PROXY", "all_proxy"):
        os.environ.pop(name, None)


def load_env() -> None:
    """把仓库根的 .env 读进 os.environ，已存在的变量不覆盖。"""
    drop_socks_proxy()
    env_file = REPO_ROOT / ".env"
    if not env_file.exists():
        raise SystemExit(f"找不到 {env_file}，请先从 .env.example 复制并填值")
    for raw in env_file.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        os.environ.setdefault(key.strip(), value.strip().strip("\"'"))


def require(name: str) -> str:
    value = os.environ.get(name)
    if not value:
        raise SystemExit(f"环境变量 {name} 未设置")
    return value


def fresh_workspace(name: str) -> Path:
    """给探针准备一个干净的 workspace 目录。"""
    path = OUT_DIR / name / "workspace"
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True)
    return path


def write_out(name: str, filename: str, content: str) -> Path:
    path = OUT_DIR / name / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def jsonable(obj: Any, depth: int = 0, max_depth: int = 12) -> Any:
    """尽力把任意对象转成可 JSON 序列化的结构，供 dump 流式事件用。

    max_depth 要够深：AIMessage.tool_calls 与 usage_metadata 嵌在第 7～9 层，
    截浅了正好把回填 §5.2 事件 payload 最需要的字段切掉。
    """
    if depth > max_depth:
        return f"<深度截断 {type(obj).__name__}>"
    if obj is None or isinstance(obj, (bool, int, float)):
        return obj
    if isinstance(obj, str):
        return obj if len(obj) <= 600 else obj[:600] + f"…<共 {len(obj)} 字符>"
    if isinstance(obj, dict):
        return {str(k): jsonable(v, depth + 1, max_depth) for k, v in obj.items()}
    if isinstance(obj, (list, tuple, set)):
        return [jsonable(v, depth + 1, max_depth) for v in obj]
    if hasattr(obj, "model_dump"):
        try:
            return {"__type__": type(obj).__name__, **jsonable(obj.model_dump(), depth + 1, max_depth)}
        except Exception:  # noqa: BLE001 - dump 失败退回 repr，不该中断探针
            pass
    if hasattr(obj, "__dict__"):
        return {"__type__": type(obj).__name__, **jsonable(vars(obj), depth + 1, max_depth)}
    return f"<{type(obj).__name__}> {obj!r}"[:600]


def dump_jsonl(name: str, filename: str, rows: list[Any]) -> Path:
    path = OUT_DIR / name / filename
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8") as fh:
        for row in rows:
            fh.write(json.dumps(jsonable(row), ensure_ascii=False) + "\n")
    return path


def section(title: str) -> None:
    print(f"\n{'=' * 72}\n{title}\n{'=' * 72}")


def verdict(claim: str, ok: bool | None, detail: str) -> dict[str, Any]:
    """打印并返回一条「文档断言 vs 实际」的核对结果。

    ok=None 表示「不是对错问题，只是观测到的事实」。
    """
    mark = {True: "✅", False: "❌", None: "ℹ️ "}[ok]
    print(f"{mark} {claim}\n     {detail}")
    return {"claim": claim, "ok": ok, "detail": detail}
