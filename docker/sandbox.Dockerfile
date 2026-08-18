# 沙箱镜像：LLM 生成的代码在这里执行。
#
# 加固不在镜像里，而在容器创建参数上（gVisor、只读 rootfs、资源限制），
# 见 app/sandbox/container.py 的 Hardening。镜像只负责「跑得起来」。
#
# 沙箱自 P12 起可以出网装包（装到 workspace，见 container.py 的 USER_BASE），
# 但**预装仍然有意义**：科学计算栈每个会话各装一遍要几分钟且各吃一份 5g 配额，
# 而中文字体根本不是 pip 能装的。常用的库仍应加进本文件重新构建。
FROM ghcr.io/astral-sh/uv:python3.13-bookworm-slim

# PATH 里的 /workspace/.local/bin 对应 container.py 的 USER_BASE：agent 装的包若带
# 命令行入口（black、jupyter 之类），不加这条就是 command not found，且不指向原因。
ENV UV_SYSTEM_PYTHON=1 \
    MPLBACKEND=Agg \
    PYTHONDONTWRITEBYTECODE=1 \
    PATH=/workspace/.local/bin:$PATH

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
