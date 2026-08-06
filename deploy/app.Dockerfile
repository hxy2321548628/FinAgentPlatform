# api 与 broker 共用的镜像。两者是同一份代码的两个入口，差别只在 command。
#
# **这个镜像不含 docker CLI 的使用权** —— broker 靠挂进去的 docker.sock 操作容器，
# api 容器不挂那个 socket，因此就算装了 CLI 也无处可用（ADR-0004）。
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

# broker 要调 docker CLI 起沙箱、调 xfs_quota 设配额。api 用不到，但两者共用镜像 ——
# 边界靠「有没有挂 docker.sock」划，不靠「装没装 CLI」，后者拦不住真想绕的人。
#
# **CLI 从官方镜像里取，不用 apt 的 docker.io**：bookworm 那个包是 API 1.41 的老客户端，
# 而宿主机守护进程要求 ≥1.44，症状是 broker 一启动就
# 「client version 1.41 is too old」。版本钉死，升级靠改这一行。
COPY --from=docker:27-cli /usr/local/bin/docker /usr/local/bin/docker

RUN apt-get update \
 && apt-get install -y --no-install-recommends xfsprogs \
 && rm -rf /var/lib/apt/lists/*

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

# 依赖单独一层：改业务代码不必重装依赖
COPY app/pyproject.toml app/uv.lock ./
RUN uv sync --locked --no-install-project --no-dev

COPY app/ ./

ENV PATH="/app/.venv/bin:$PATH"

# 入口由 compose 的 command 指定：api 是 api.app:app，broker 是 broker.app:app
