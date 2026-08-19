"""评估集用的平台客户端。

**走教师真正走的那条路**：登录、建会话、上传数据、提交提问、等它跑完。
不直接调装配层 —— 最贵的那些 bug（沙箱没申请、broker 少个环境变量、地址填成 localhost）
全都发生在装配层之外，绕过去的评估集一条都照不出来。

**等待用轮询而不是订阅 SSE**：评估只关心跑完之后的结果，而 `/replay` 一次就能取回
全部事件；拿长连接去读一份不再变化的历史，断线还要重连，重连还要过频率闸。
"""

import time
from pathlib import Path
from typing import Any

import httpx

# 一次分析最长等多久。真实分析实测几分钟，大数据那题会更久
RUN_TIMEOUT_SECOND = 1800
POLL_INTERVAL_SECOND = 5
# 审批闸门：评估集里有题故意去撞它，没人批的话 run 会一直挂着。
# **决策要覆盖全部待确认调用** —— 只批第一个是 422，而那个红看着像 agent 没做好
APPROVE = "approve"
FINAL_STATUS = frozenset({"succeeded", "failed", "cancelled"})


class PlatformError(RuntimeError):
    """平台接口没按预期响应。"""


def _decision_for(action: dict[str, Any]) -> str:
    """这个调用该回什么决策。

    **评估一律放行** —— 要测的是 agent 做得对不对，不是教师会不会拦；
    但工具只允许别的决策时（例如只能改参数）就按它允许的来。
    """
    allowed = [str(one) for one in action.get("allowed_decisions") or []]
    if not allowed or APPROVE in allowed:
        return APPROVE
    return allowed[0]


class PlatformClient:
    """一个登录态下的平台会话。

    Args:
        base_url: 平台地址，指向 nginx 那一层。
        client: 已建好的 httpx 客户端，由调用方负责关闭。
    """

    def __init__(self, *, base_url: str, client: httpx.Client) -> None:
        self._base = base_url.rstrip("/")
        self._client = client

    def login(self, *, name: str, password: str) -> str:
        """登录并把 cookie 留在客户端里，返回用户标识。

        字段是 `name` 不是 `username` —— 平台的登录接口认前者。
        写错了是 422，而报错指向请求体，不指向账号。
        """
        self._post("/api/auth/login", json={"name": name, "password": password})
        return str(self._get("/api/auth/me")["id"])

    def create_thread(self) -> str:
        """建一个新会话，返回它的标识。"""
        return str(self._post("/api/threads")["id"])

    def upload(self, thread_id: str, path: Path) -> None:
        """把一份数据文件传进会话的工作目录。"""
        with path.open("rb") as handle:
            response = self._client.post(
                f"{self._base}/api/threads/{thread_id}/files",
                files={"file": (path.name, handle)},
            )
        if response.is_error:
            raise PlatformError(f"上传 {path.name} 失败：{response.status_code} {response.text[:200]}")

    def submit(self, thread_id: str, question: str) -> str:
        """提交一次分析，返回 run 标识。"""
        return str(self._post(f"/api/threads/{thread_id}/runs", json={"content": question})["id"])

    def wait(self, run_id: str) -> tuple[str, int]:
        """等到 run 进终态，**中途停在审批上就批准**。

        Returns:
            终态状态与本次批准的次数。批准次数为零而题目本该撞闸门时，
            说明那道题没走到要测的路上 —— 判据据此记「未验」。
        """
        approvals = 0
        deadline = time.monotonic() + RUN_TIMEOUT_SECOND
        while time.monotonic() < deadline:
            status = str(self._get(f"/api/runs/{run_id}")["status"])
            if status in FINAL_STATUS:
                return status, approvals
            if status == "waiting_approval":
                approvals += int(self._approve_all(run_id))
            time.sleep(POLL_INTERVAL_SECOND)
        raise PlatformError(f"run {run_id} 超过 {RUN_TIMEOUT_SECOND} 秒仍未结束")

    def _approve_all(self, run_id: str) -> bool:
        """批准这一次中断里的**每一个**待确认调用，返回是否真的批了。

        一次中断可能停下不止一个调用（实测 E05 那题停了 2 个），而平台要求决策覆盖
        全部 —— 少一个就是 422。**事件还没落进日志时先不批**，下一轮轮询再来，
        比拿着空列表硬发一次要好。
        """
        actions = self._pending_actions(run_id)
        if not actions:
            return False
        decisions = [
            {"index": int(one.get("index", position)), "type": _decision_for(one)}
            for position, one in enumerate(actions)
        ]
        self._post(f"/api/runs/{run_id}/approve", json={"decisions": decisions})
        return True

    def _pending_actions(self, run_id: str) -> list[dict[str, Any]]:
        """取最后一次中断里待确认的调用。"""
        for event in reversed(self.replay(run_id)):
            if event.get("type") == "interrupt":
                return list((event.get("data") or {}).get("actions") or [])
        return []

    def replay(self, run_id: str) -> list[dict[str, Any]]:
        """取回一个 run 的全部事件。"""
        items = self._get(f"/api/runs/{run_id}/replay")["items"]
        return [one["event"] for one in items]

    def files(self, thread_id: str) -> list[dict[str, Any]]:
        """列出会话工作目录下的全部文件与目录。"""
        return list(self._get(f"/api/threads/{thread_id}/files")["entries"])

    def _get(self, path: str) -> dict[str, Any]:
        response = self._client.get(f"{self._base}{path}")
        if response.is_error:
            raise PlatformError(f"GET {path} → {response.status_code} {response.text[:200]}")
        return dict(response.json())

    def _post(self, path: str, *, json: dict[str, Any] | None = None) -> dict[str, Any]:
        response = self._client.post(f"{self._base}{path}", json=json)
        if response.is_error:
            raise PlatformError(f"POST {path} → {response.status_code} {response.text[:200]}")
        return dict(response.json()) if response.content else {}
