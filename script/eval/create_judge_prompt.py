"""把判分 rubric 托管到 Langfuse 的 prompt 管理里。

**为什么放 Langfuse 而不是写死在脚本里**：改 rubric 不必重新部署，且它自带版本号 ——
每一批分数记下用的是第几版，半年后还能重跑出同一个分。
代价是 rubric 不进 git、代码评审看不到它变了，因此**结果 JSON 里必须记版本号**。

**rubric 按金融分析这个领域本身该有的东西写，不抄系统提示词的措辞** ——
抄了的话，P15 改提示词就等于同时改了考卷和答案，分数涨了说明不了任何事。

用法：
    set -a && . docker/.env && set +a
    LANGFUSE_BASE_URL=http://localhost:3000 src/.venv/bin/python script/eval/create_judge_prompt.py
"""

import os
import sys
import dotenv

from langfuse import Langfuse

dotenv.load_dotenv()

PROMPT_NAME = "judge-rubric"
RUBRIC = """你是金融数据分析的评审。下面是一位分析助手对用户提问的完整答复。
按「分析思路是否站得住」这一个维度打 1 到 5 分，只看这一个维度，不看排版是否好看、不看篇幅长短。

评分标准：
5 分：给出了明确结论且有数值支撑；说明了数据是怎么处理的（缺失值、异常值如何判定与处置）；
     所用方法与口径交代清楚（例如年化按什么频率折算）；并指出了结论的适用范围或局限。
4 分：结论有数值支撑，数据处理与方法口径基本交代清楚，但没有提及局限或方法选择的理由。
3 分：有结论也有数字，但数据怎么来的、怎么处理的一笔带过，读者无法复核。
2 分：只有结论没有支撑，或给出的数字与所问的问题对不上。
1 分：答非所问，或没有实质分析。

只输出一行 JSON，不要任何解释性文字：
{"score": <1-5 的整数>, "reason": "<不超过五十字，指出扣分或给分的具体依据>"}

教师的提问：
{{question}}

分析助手的答复：
{{answer}}
"""


def main() -> int:
    """建（或更新）rubric prompt 并打上 production 标签。"""
    host = os.environ.get("LANGFUSE_BASE_URL", "")
    public_key = os.environ.get("LANGFUSE_PUBLIC_KEY", "")
    secret_key = os.environ.get("LANGFUSE_SECRET_KEY", "")
    if not (host and public_key and secret_key):
        print(
            "缺 LANGFUSE_BASE_URL / LANGFUSE_PUBLIC_KEY / LANGFUSE_SECRET_KEY",
            file=sys.stderr,
        )
        return 2

    client = Langfuse(public_key=public_key, secret_key=secret_key, host=host)
    # **必须打 production 标签**：`get_prompt(name)` 默认取的就是它，
    # 只打 latest 的 prompt 会 404，而报错里才看得出它找的是哪个标签
    created = client.create_prompt(
        name=PROMPT_NAME, prompt=RUBRIC, labels=["production"], type="text"
    )
    print(f"rubric 已就绪：{PROMPT_NAME} v{created.version}（标签 production）")
    print("评估结果里要记下这个版本号 —— 不然半年后不知道这批分是哪一版打的")
    return 0


if __name__ == "__main__":
    main()
