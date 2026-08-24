"""在 Langfuse 创建 P15 pairwise rubric 并锁定 production 版本。"""

import os
import sys

import dotenv
from langfuse import Langfuse
from pairwise import PROMPT_NAME

RUBRIC = """你是金融数据分析评审。比较两份对同一问题的答复，判断哪份的分析质量更好。

只考察：结论是否有证据和数值支撑；数据处理、方法与口径是否正确可复核；
结论、证据与局限是否分得清。不根据长度、排版、文风或先后位置加分。
实质质量相当，或各有优劣但无法分出高下时，必须选 tie。

题目：
{{question}}

答复 A：
{{answer_a}}

答复 B：
{{answer_b}}

输出标签映射：A 对应 {{label_a}}，B 对应 {{label_b}}。
只能输出一个标签：baseline、candidate 或 tie。不要输出 JSON、代码围栏、解释或其他文字。
"""


def main() -> int:
    """创建或更新 pairwise rubric。"""
    dotenv.load_dotenv()
    required = ("LANGFUSE_BASE_URL", "LANGFUSE_PUBLIC_KEY", "LANGFUSE_SECRET_KEY")
    missing = [name for name in required if not os.environ.get(name)]
    if missing:
        print(f"缺环境变量：{' / '.join(missing)}", file=sys.stderr)
        return 2
    client = Langfuse(
        public_key=os.environ["LANGFUSE_PUBLIC_KEY"],
        secret_key=os.environ["LANGFUSE_SECRET_KEY"],
        host=os.environ["LANGFUSE_BASE_URL"],
    )
    created = client.create_prompt(
        name=PROMPT_NAME, prompt=RUBRIC, labels=["production"], type="text"
    )
    print(
        f"pairwise rubric 已就绪：{PROMPT_NAME} v{created.version}（标签 production）"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
