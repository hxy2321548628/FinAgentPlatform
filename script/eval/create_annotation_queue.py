"""建人工抽检用的标注队列。

**一次要建全**：Langfuse 的标注队列**建了不能改也不能删**，事后想加一项只能另开一个队列。
因此先把三项 score config 建出来，拿到 id 再建队列。

三项的分工：
- `cjk_ok`：中文有没有乱码。**这一项定案就是不做自动判定** —— OCR 自己会误判，
  等于给尺子再加一层噪声；
- `pass_fail`：这条产出人看着行不行，用来给 judge 校准（人机符合率）；
- `open_coding`：**写观察，不写诊断**。error-analysis 的第一步是描述行为，
  一上来就写「因为模型没理解」会把后面的聚类带偏。

用法：
    set -a && . docker/.env && set +a
    LANGFUSE_BASE_URL=http://localhost:3000 src/.venv/bin/python script/eval/create_annotation_queue.py
"""

import os
import sys
from typing import Any

import httpx

QUEUE_NAME = "zuel-eval-人工抽检"
QUEUE_DESCRIPTION = "每轮评估抽 10% 的产出人工过一遍：乱码、整体成败、开放编码"
CONFIGS: tuple[dict[str, Any], ...] = (
    {"name": "cjk_ok", "dataType": "BOOLEAN"},
    {
        "name": "pass_fail",
        "dataType": "CATEGORICAL",
        "categories": [{"label": "pass", "value": 1}, {"label": "fail", "value": 0}],
    },
    {"name": "open_coding", "dataType": "CATEGORICAL", "categories": [{"label": "见评论", "value": 0}]},
)


def main() -> int:
    """建三项 score config 与一个队列，返回进程退出码。"""
    host = os.environ.get("LANGFUSE_BASE_URL", "")
    auth = (os.environ.get("LANGFUSE_PUBLIC_KEY", ""), os.environ.get("LANGFUSE_SECRET_KEY", ""))
    if not (host and all(auth)):
        print("缺 LANGFUSE_BASE_URL / LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY", file=sys.stderr)
        return 2

    with httpx.Client(base_url=host, auth=auth, timeout=30.0) as client:
        existing = {one["name"]: one["id"] for one in client.get("/api/public/score-configs").json()["data"]}
        ids: list[str] = []
        for config in CONFIGS:
            name = str(config["name"])
            if name in existing:
                print(f"  = {name}（已存在，沿用）")
                ids.append(existing[name])
                continue
            response = client.post("/api/public/score-configs", json=config)
            if response.is_error:
                print(f"建 {name} 失败：{response.status_code} {response.text[:200]}", file=sys.stderr)
                return 1
            ids.append(str(response.json()["id"]))
            print(f"  + {name}")

        queues = client.get("/api/public/annotation-queues").json()["data"]
        found = next((one for one in queues if one["name"] == QUEUE_NAME), None)
        if found:
            print(f"队列已存在，不重复建（建了也改不了）：{found['id']}")
            return 0
        created = client.post(
            "/api/public/annotation-queues",
            json={"name": QUEUE_NAME, "description": QUEUE_DESCRIPTION, "scoreConfigIds": ids},
        )
        if created.is_error:
            print(f"建队列失败：{created.status_code} {created.text[:200]}", file=sys.stderr)
            return 1
        print(f"队列已建：{created.json()['id']}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
