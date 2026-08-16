#!/usr/bin/env bash
# 给 Langfuse 注册本平台用的模型单价。**可重跑**：同名模型再注册一次，它按
# 「custom 优先、startTime 新的优先」取用，不会把旧的弄坏。
#
# 为什么要这一步：Langfuse 内置了 100 个模型的价格，**里面一个 deepseek 都没有**。
# 缺价格时它照常收 token、照常返回 200，只是 total_cost 恒为 0 —— 那个 0 不报错，
# 于是「这个月花了多少钱」这个问题在界面上永远是零。
#
# 单价从仓库根的 .env 读，不写死在这里：它会变，而改一个脚本比改一份文档更容易漏。
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
if [[ -z "${MODEL_MAIN_INPUT_PRICE:-}" || -z "${MODEL_MAIN_OUTPUT_PRICE:-}" ]]; then
  cat >&2 <<'MESSAGE'
MODEL_MAIN_INPUT_PRICE / MODEL_MAIN_OUTPUT_PRICE 没配，跳过注册。

它们是每 1 个 token 的 USD 单价（不是每百万）。按 DeepSeek 官方价目填，例如
每百万 input token 收 $0.27 就写 0.00000027。填好后重跑本脚本。
MESSAGE
  exit 2
fi

register() {
  local model="$1" input="$2" output="$3"
  echo "注册 $model：input=$input output=$output（USD / token）"
  curl -sS -u "$LANGFUSE_PUBLIC_KEY:$LANGFUSE_SECRET_KEY" \
    -X POST "${LANGFUSE_BASE_URL%/}/api/public/models" \
    -H 'Content-Type: application/json' \
    -d "$(cat <<JSON
{
  "modelName": "$model",
  "matchPattern": "(?i)^$model\$",
  "unit": "TOKENS",
  "inputPrice": $input,
  "outputPrice": $output
}
JSON
)" | head -c 400
  echo
}

register "${MODEL_MAIN:-deepseek-v4-pro}" "$MODEL_MAIN_INPUT_PRICE" "$MODEL_MAIN_OUTPUT_PRICE"

if [[ -n "${MODEL_AUX_INPUT_PRICE:-}" && -n "${MODEL_AUX_OUTPUT_PRICE:-}" ]]; then
  register "${MODEL_AUX:-deepseek-v4-flash}" "$MODEL_AUX_INPUT_PRICE" "$MODEL_AUX_OUTPUT_PRICE"
else
  echo "辅模型单价没配，只注册了主模型"
fi

echo
echo "核对方式（新产生的 generation 才会带上费用，历史的不会重算）："
echo "  在 Langfuse 里跑一次分析，然后看 Usage 页面的 Cost 一列"
