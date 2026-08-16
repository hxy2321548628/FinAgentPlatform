#!/usr/bin/env bash
# 给 Langfuse 注册本平台用的模型单价。**可重跑**：同名模型再注册一次，它按
# 「custom 优先、startTime 新的优先」取用，不会把旧的弄坏。
#
# 为什么要这一步：Langfuse 内置了 100 个模型的价格，**里面一个 deepseek 都没有**。
# 缺价格时它照常收 token、照常返回 200，只是 total_cost 恒为 0 —— 那个 0 不报错，
# 于是「这个月花了多少钱」这个问题在界面上永远是零。
#
# **四个用量键都要定价，少一个就系统性地少算。** 实测一条 GENERATION 报的是
#   {'input':22, 'output':292, 'input_cache_read':3584, 'output_reasoning':36}
# 四个键互不重叠，加起来正好等于 total。其中**缓存命中占了九成的量** ——
# 只定 input/output 的话，算出来的费用连零头都不到。
# **反过来 `total` 一定不能定价**：它与那四个重叠，定了就是把每一笔算两遍。
#
# `output_reasoning` 与 `output` 同价：DeepSeek 把推理 token 按输出计费，
# 是 Langfuse 的 SDK 把它从 output 里拆出来单列的。
#
# **单价的单位是「每百万 token 的人民币」**，与 DeepSeek 价目表上的数字一模一样，
# 抄的时候不用换算 —— 换算在下面做。Langfuse 界面上的货币符号固定是 $，
# 那一栏要当人民币读；这是明知的取舍，换算成美元的话汇率一动数字就悄悄偏了。
#
# 用法：
#   bash deploy/register-model-price.sh
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ENV_FILE="$ROOT/.env"

if [[ ! -f "$ENV_FILE" ]]; then
  echo "找不到 $ENV_FILE" >&2
  exit 1
fi

# shellcheck disable=SC1090
set -a && source "$ENV_FILE" && set +a

for name in LANGFUSE_BASE_URL LANGFUSE_PUBLIC_KEY LANGFUSE_SECRET_KEY; do
  if [[ -z "${!name:-}" ]]; then
    echo "$name 没配，Langfuse 都没接，无从注册价格" >&2
    exit 1
  fi
done

# **没配单价就退出，不要用占位数字注册。** 一个编出来的价格会算出一个看着
# 像模像样的费用，而那比显示 0 更难发现错 —— 0 至少一眼就知道没数据
if [[ -z "${MODEL_MAIN_PRICE_INPUT:-}" || -z "${MODEL_MAIN_PRICE_OUTPUT:-}" || -z "${MODEL_MAIN_PRICE_CACHED:-}" ]]; then
  cat >&2 <<'MESSAGE'
主模型的三个单价没配齐，跳过注册。

要的是 MODEL_MAIN_PRICE_INPUT / MODEL_MAIN_PRICE_CACHED / MODEL_MAIN_PRICE_OUTPUT，
单位是**每百万 token 的人民币**，照 DeepSeek 价目表原样抄即可。填好后重跑本脚本。
MESSAGE
  exit 2
fi

# **宿主机上跑这个脚本时 .env 里那个地址是给容器用的。** api 与 worker 在容器里，
# 它们够 Langfuse 要走 host.docker.internal；而这里在宿主机上，那个名字解析不过去。
# 症状是 502 而不是「连不上」，最不像配置问题
BASE="${LANGFUSE_ADMIN_URL:-${LANGFUSE_BASE_URL}}"
BASE="${BASE%/}"

# 每百万人民币 → 每 token。bash 不做浮点，交给 awk
per_token() {
  awk -v v="$1" 'BEGIN { printf "%.12f", v / 1000000 }'
}

register() {
  local model="$1" input="$2" cached="$3" output="$4" payload response
  echo "注册 $model：input=$input cached=$cached output=$output（元 / 百万 token）"
  payload="$(jq -nc \
    --arg model "$model" \
    --argjson input "$(per_token "$input")" \
    --argjson cached "$(per_token "$cached")" \
    --argjson output "$(per_token "$output")" \
    '{
      modelName: $model,
      matchPattern: ("(?i)^" + $model + "$"),
      unit: "TOKENS",
      pricingTiers: [{
        name: "Standard",
        isDefault: true,
        priority: 0,
        conditions: [],
        prices: {
          input: $input,
          input_cache_read: $cached,
          output: $output,
          output_reasoning: $output
        }
      }]
    }')"
  response="$(curl -sS -u "$LANGFUSE_PUBLIC_KEY:$LANGFUSE_SECRET_KEY" \
    -X POST "$BASE/api/public/models" \
    -H 'Content-Type: application/json' -d "$payload")"
  # **要回读 id 才算成功。** 这个接口对着不认识的字段也回 200，
  # 而「注册过了但一个键都没定上」与「没注册」在界面上是同一个 0
  if ! jq -e '.id' <<<"$response" >/dev/null 2>&1; then
    echo "  ❌ 没注册上：$(head -c 300 <<<"$response")" >&2
    return 1
  fi
  echo "  ✅ id=$(jq -r '.id' <<<"$response")  已定价的键：$(jq -r '.pricingTiers[0].prices | keys | join(", ")' <<<"$response")"
}

register "${MODEL_MAIN:-deepseek-v4-pro}" \
  "$MODEL_MAIN_PRICE_INPUT" "$MODEL_MAIN_PRICE_CACHED" "$MODEL_MAIN_PRICE_OUTPUT"

if [[ -n "${MODEL_AUX_PRICE_INPUT:-}" && -n "${MODEL_AUX_PRICE_OUTPUT:-}" && -n "${MODEL_AUX_PRICE_CACHED:-}" ]]; then
  register "${MODEL_AUX:-deepseek-v4-flash}" \
    "$MODEL_AUX_PRICE_INPUT" "$MODEL_AUX_PRICE_CACHED" "$MODEL_AUX_PRICE_OUTPUT"
else
  echo "辅模型单价没配齐，只注册了主模型"
fi

echo
echo "核对方式：**跑一次新的分析再看**。价格只作用于此后产生的 generation，"
echo "历史那些的 total_cost 不会重算 —— 看着还是 0 是正常的，不是没注册上。"
