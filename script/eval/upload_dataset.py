"""把评估集上传到 Langfuse。

**幂等**：item id 固定，重跑是 upsert 而不是造一批重复题 —— 评估集会反复改，
每改一次多一份副本的话，跑出来的分数就没法跟上一批比。

**地址必须显式给**：`docker/.env` 里的 `LANGFUSE_BASE_URL` 是 `host.docker.internal`
（给容器用的名字），宿主机上解析不了。在宿主机跑这个脚本要指到 localhost。

用法：
    set -a && . docker/.env && set +a
    LANGFUSE_BASE_URL=http://localhost:3000 src/.venv/bin/python script/eval/upload_dataset.py
"""

import json
import os
import sys
from pathlib import Path

from langfuse import Langfuse

DATASET_FILE = Path(__file__).with_name("dataset.json")
ID_PREFIX = "zuel-eval-v1-"


def main() -> int:
    """建数据集并逐条 upsert，返回进程退出码。"""
    host = os.environ.get("LANGFUSE_BASE_URL", "")
    public_key = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
    secret_key = os.environ.get("LANGFUSE_SECRET_KEY", "")
    if not (host and public_key and secret_key):
        print("缺 LANGFUSE_BASE_URL / LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY", file=sys.stderr)
        return 2

    spec = json.loads(DATASET_FILE.read_text(encoding="utf-8"))
    client = Langfuse(public_key=public_key, secret_key=secret_key, host=host)

    client.create_dataset(name=spec["dataset"], description=spec["description"])
    print(f"数据集 {spec['dataset']} 已就绪（已存在则原样保留）")

    for item in spec["items"]:
        created = client.create_dataset_item(
            dataset_name=spec["dataset"],
            id=f"{ID_PREFIX}{item['id']}",
            input=item["input"],
            expected_output=item["expected_output"],
            metadata=item["metadata"],
        )
        probe = item["metadata"]["probe"]
        print(f"  ✓ {item['id']:<24} probe={probe:<14} id={created.id}")

    print(f"共 {len(spec['items'])} 题")
    return 0


if __name__ == "__main__":
    sys.exit(main())
