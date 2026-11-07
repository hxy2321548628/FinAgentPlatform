# Tushare MCP 共享凭据配置与迁移

## 新增一个 MCP 的通用流程

1. 确认服务地址、传输协议、认证方式、工具清单、数据外发和费用；API、worker 容器均需能访问服务。
2. 无认证服务不填凭据。共享账号的密钥由管理员保存到服务器环境文件的 `MCP_CREDENTIALS` JSON 中，保留已有条目。当前没有用户私有密钥保险箱，共享额度也不按用户分账。
3. 普通服务的值是整个 `Authorization` 请求头，例如 `Bearer 实际密钥`；Tushare 使用原始 token。其他自定义请求头、查询参数或 OAuth 认证需要单独适配，不能直接套用 Tushare 规则。
4. 修改环境文件后重新创建 API、worker，使两者加载新凭据；只改密钥不需要重建镜像。
5. 在平台“申请添加 MCP”中填写不含密钥的服务 URL、协议、凭据键名和所需工具清单，等待管理员审批并测试连接。
6. 在智能体中选用该服务，实际调用一次目标工具；获取工具清单不能代替权限、配额与数据查询验证。

Tushare 新申请示例：URL 为 `https://api.tushare.pro/mcp/`，协议为 `streamable_http`（界面显示 Streamable HTTP），平台凭据键名为 `tushare`，工具按需填 `stock_basic`、`daily` 等。密钥不要填写到 URL 或智能体提示词中。

## 已完成

学院服务器 API 与 worker 已部署镜像 finagent/backend:tushare-token-20261107。后端支持将凭据键名对应的原始 Tushare token 编码到连接 URL 的 token 查询参数；其他服务仍使用 Authorization 认证。用户 URL 已有非空 token 时保留用户值，不被环境变量覆盖。进程日志中的 URL token 会脱敏。

服务器现有 tushare 记录已迁移为不带 token 的 URL 并绑定 tushare 凭据键；工具清单、原服务 ID 和智能体引用保持不变。环境文件 /etc/finagent/platform.env 已添加并加载真实共享 token，其他凭据保留。针对认证、实际 SSE/Streamable HTTP 连接配置和日志脱敏的测试通过，API/worker 已启动，匿名访问 API 返回预期的未登录响应。已获取 268 个工具，并成功调用 daily 查询 000001.SZ 在 2026-11-06 的日线；首次遇到 DNS 解析失败，重试成功。

## 管理员填写密钥

打开服务器文件：

```bash
nano /etc/finagent/platform.env
```

找到 MCP_CREDENTIALS，保留现有其他键值，只填写 tushare 对应的值。若对象中只有这一个条目，形式如下（仅为格式示例）：

```dotenv
MCP_CREDENTIALS='{"tushare":"真实的Tushare token"}'
```

token 不加 Bearer，不填写 DEEPSEEK_API_KEY，也不要将真实值提交到 Git。保存后重新创建 API 与 worker：

```bash
cd /opt/finagent/current/app
docker compose -p finagent-platform --env-file /etc/finagent/platform.env -f docker/compose.yml -f docker/release.yml up -d --no-deps --no-build --pull never --force-recreate api worker
```

这会短暂中断接口与正在运行的任务。

Compose 会解析 dotenv 的外层引号，`docker run --env-file` 行为不同，不要直接用后者验证上述带外层单引号的 JSON。平台凭据适配和 URL 日志脱敏不代表所有事件或日志字段都有通用密钥过滤能力。

## 现有服务如何切换

管理员填写共享 token 并验证凭据加载后，先由服务所有者确认是否同意全平台共享此账号的额度。然后将现有 tushare 服务的 URL 改为 https://api.tushare.pro/mcp/，credential_key 改为 tushare，传输方式使用 streamable_http。保留该记录的 ID、名称、状态、工具清单及智能体引用。

当前后台没有现有 MCP 的编辑接口或编辑按钮，因此这项原记录迁移需要管理员通过服务器完成；不能让用户在 UI 中寻找不存在的编辑入口。实施前应备份该记录，仅修改确认的服务 ID，且在真实 token 已填好后再执行。本次已在填写真实凭据并验证连接成功后执行迁移，保留原服务 ID。

如需全程通过现有 UI 自助完成，可另行申请一个不同名称的共享 MCP，填写上述无密钥地址、凭据键名 tushare、streamable_http 和所需工具清单；管理员审批测试通过后，用户在智能体中改选新 MCP。待所有使用者完成迁移，再经确认停用旧服务。

## 可转达给用户

1. 本次已将原 Tushare 服务迁移为平台共享凭据，原服务 ID 和智能体引用保持不变。
2. 关闭旧详情弹窗并刷新页面，无需重新创建智能体或重新申请 MCP。
3. 迁移后服务详情里应只有不含 token 的地址，并显示已关联平台凭据。
4. 再提交一次实际数据查询，例如明确指定交易日的 000001 日线查询。测试连接成功只证明能获取工具清单，接口权限和配额需要实际查询确认。
5. 先前暴露在目录或截图中的旧 token，迁移确认完成后由持有人轮换。

## 后续发布

生产 release.yml 中 api/worker 已引用本次镜像。服务器 src 下也已同步连接逻辑和日志脱敏代码。正式发布时需要保留这些源码修改；仅保留当前服务器的手工补丁不能保证下一份发布包仍包含功能。原源码、日志模块、release.yml 和环境配置备份在 /opt/finagent/mcp-token-fix-* 的受限目录中，旧后端镜像保留为 finagent/backend:before-tushare-20261107。
