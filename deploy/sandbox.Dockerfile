# 沙箱镜像：LLM 生成的代码在这里执行。
#
# **本镜像不含 P1 的加固措施**（gVisor、只读 rootfs、网络白名单、资源限制、磁盘配额）。
# 隔离强度目前只有一层容器边界，P0 已把加固登记为 P1 不可跳过项。
#
# 预装科学计算栈与中文字体，是因为容器零出网：agent 装不上任何东西，
# 缺什么都只能白跑几轮再放弃。
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

ENV UV_SYSTEM_PYTHON=1 \
    MPLBACKEND=Agg \
    PYTHONDONTWRITEBYTECODE=1

RUN uv pip install --system --no-cache pandas numpy matplotlib

# 中文字体。缺了不会报错，只会让图上的中文变成方框，而 agent 看不到自己画的图，
# 会反复尝试 pip install / apt-cache search 去找字体 —— 零出网下这些必然全部失败。
RUN apt-get update \
 && apt-get install -y --no-install-recommends fonts-noto-cjk \
 && rm -rf /var/lib/apt/lists/*

# 把中文字体配成 matplotlib 默认。只装字体不改配置，agent 仍要自己写 rcParams 才能
# 画出中文，而它并不知道装了哪一款 —— 于是继续白跑。unicode_minus 关掉是因为
# CJK 字体没有 U+2212，负号会渲染成方框。
RUN MPLRC="$(python -c 'import matplotlib, pathlib; print(pathlib.Path(matplotlib.get_data_path()) / "matplotlibrc")')" \
 && sed -i 's/^#font.sans-serif:.*/font.sans-serif: Noto Sans CJK SC, DejaVu Sans/' "$MPLRC" \
 && sed -i 's/^#axes.unicode_minus:.*/axes.unicode_minus: False/' "$MPLRC"

WORKDIR /workspace
