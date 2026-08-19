"""探出主模型的真实上下文上限。

**为什么要探**：压缩阈值现在是从模型 profile 推出来的 —— profile 报
`max_input_tokens=1000000`、触发线 `('fraction', 0.85)`，即 85 万 token 才压。
如果真实上限远小于这个数，那条线永远够不着，压缩机制等于从未生效过，
而症状只是「今天怎么这么贵」或者一次莫名其妙的失败。

**探针要能证伪**（P12 的教训：第一版探针用 --dry-run 对比，两个配置都「成功」，
分辨不出真相）。这里的做法是二分：每一档都真发一次请求，记下它是成功、被模型拒、
还是被网关拒 —— **后两者必须分开**，否则量到的可能是网关的限制而不是模型的。

用法：
    set -a && . docker/.env && set +a
    src/.venv/bin/python script/probe_context_limit.py
"""

import os
import sys

import httpx

# **先试一次 profile 声称的上限**：被拒的请求不计费，而这一次就能回答
# 「那个 100 万是不是假的」—— A1 最要紧的结论就是它
PROFILE_CLAIM_TOKEN = 1_000_000
# 然后从小往大倍增。**不二分**：二分会先试中间那档，万一真实上限很大，
# 那一次成功就烧掉几十万 token 的钱；倍增里成功的那些累计约等于最后一档，便宜一个数量级
START_TOKEN = 8_000
GROWTH = 2
CEILING_TOKEN = 2_000_000
# 中文一个字约一个 token，用重复的短句拼长文；不用随机串是为了别把 tokenizer 的
# 行为差异混进来
FILLER = "衡量组合风险要看年化波动率。"
TIMEOUT_SECOND = 120.0


def probe(client: httpx.Client, *, model: str, token: int) -> tuple[bool, str]:
    """发一次指定规模的请求，返回（过没过，怎么回事）。"""
    body = FILLER * max(token // len(FILLER), 1)
    try:
        response = client.post(
            "/chat/completions",
            json={
                "model": model,
                "messages": [{"role": "user", "content": body}, {"role": "user", "content": "只回一个字：好"}],
            },
        )
    except httpx.TimeoutException:
        return False, "超时（既不是模型拒也不是网关拒，这一档不作数）"
    if response.is_success:
        return True, "过"
    # **模型拒与网关拒必须分开**：前者是真实上限，后者只是这条路上的一道闸
    text = response.text[:200].replace("\n", " ")
    source = "模型" if response.status_code == 400 else f"网关/其它（HTTP {response.status_code}）"
    return False, f"{source}：{text}"


def main() -> int:
    """二分探出上限，把每一档的结果打出来。"""
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    base = os.environ.get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")
    model = os.environ.get("MODEL_MAIN", "deepseek-v4-pro")
    if not key:
        print("缺 DEEPSEEK_API_KEY", file=sys.stderr)
        return 2

    with httpx.Client(base_url=base, timeout=TIMEOUT_SECOND, headers={"Authorization": f"Bearer {key}"}) as client:
        # 第一发就打 profile 声称的那个数。过了说明 profile 没骗人，
        # 被拒（不计费）就当场证明那条 85% 的触发线永远够不着
        claimed, why = probe(client, model=model, token=PROFILE_CLAIM_TOKEN)
        print(f"{PROFILE_CLAIM_TOKEN:>9} token（profile 声称）：{why}")
        if claimed:
            print("\nprofile 没骗人，压缩阈值按它推出来的数是成立的 —— A1 只需把它钉成显式常量")
            return 0

        passed, last_why = 0, ""
        size = START_TOKEN
        while size <= CEILING_TOKEN:
            ok, why = probe(client, model=model, token=size)
            print(f"{size:>9} token：{why}")
            if not ok:
                last_why = why
                break
            passed, size = size, size * GROWTH

    if not passed:
        print(f"\n{START_TOKEN} token 都过不了（{last_why}）—— 探针或凭据有问题，别把这个当成模型的上限")
        return 1
    print(f"\n真实上限落在 {passed} 与 {size} token 之间")
    print(f"profile 声称 {PROFILE_CLAIM_TOKEN}，实测差 {PROFILE_CLAIM_TOKEN // max(size, 1)} 倍以上")
    print("把下界写进平台常量，压缩阈值按它的比例定 —— 不要再用 profile 推出来的那个数")
    return 0


if __name__ == "__main__":
    sys.exit(main())
