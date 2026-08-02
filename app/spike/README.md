# spike — P0 探针

一次性验证代码，用来回答[架构文档 §11](../../doc/01design/01architecture.md) 列的 P0 探针问题。
**结论看 [FINDINGS.md](./FINDINGS.md)**，本文件只讲怎么跑。

跑完这批探针后 `spike/` 就可以删掉 —— 它的产出是结论，不是代码。唯一值得留下的是
`docker_sandbox.py` 的思路（不是实现），它验证了 `SandboxBackendProtocol` 怎么接。

## 前置

- 仓库根有 `.env`（照 `.env.example` 填 `DEEPSEEK_API_KEY` 等）
- `app/.venv` 已装好依赖
- Docker 可用（探针 2、3 要跑容器）

## 跑

```bash
cd app/spike

../.venv/bin/python probe1_api_surface.py          # 不花钱，纯静态核对 API
../.venv/bin/python probe3_write_idempotency.py    # 不花钱，会拉/建镜像
../.venv/bin/python probe4_interrupt_toolcallid.py # 约 5k token
../.venv/bin/python probe2_stream_dump.py --quick  # 约 6k token，只抓 StreamPart 结构
../.venv/bin/python probe2_stream_dump.py          # 约 31 万 token，跑完整分析
```

最后一条是完整验收 case（持仓 CSV → 按行业算年化波动率 → 出图），一次约 31 万 token，
不要反复跑。只需要事件结构的话用 `--quick`。

## 各探针回答什么

| 脚本 | 回答的问题 | 对应文档 |
|---|---|---|
| `probe1_api_surface.py` | 设计文档对 DeepAgents API 的假设是否成立 | 03agent-design §2/§3/§4、ADR-0016 |
| `probe2_stream_dump.py` | DeepAgents 实际吐什么流式结构；一次分析花多少 token、几轮 | 架构 §5.2、§6.4；03agent-design §5.2、§7.3 |
| `probe3_write_idempotency.py` | `write_file` 是覆盖还是报错；`edit`/`delete` 重放什么行为 | 03agent-design §3.3 |
| `probe4_interrupt_toolcallid.py` | `tool_call_id` 在 interrupt 恢复前后是否稳定 | ADR-0014、架构 §5.6、§10.2 |

## 文件

- `_common.py` — 读 `.env`、准备 workspace、把任意对象转成可 JSON 结构
- `docker_sandbox.py` — 最小 Docker 沙箱后端。**不是 P1 的加固实现**，没有 gVisor、没有资源限制、
  没有网络白名单、没有磁盘配额。唯一目的是让 LLM 生成的代码不在宿主机上跑。
  单独执行会构建镜像并自测：`../.venv/bin/python docker_sandbox.py`
- `Dockerfile.sandbox` — spike 镜像，预装 pandas/numpy/matplotlib + 中文字体
- `out/` — 所有探针输出（JSON 结论、流式 chunk、agent 的 workspace）。不进版本库
