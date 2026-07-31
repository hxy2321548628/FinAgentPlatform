# ADR-0011：认证用 HttpOnly Cookie + Redis Session，不用 OAuth2 / JWT

| 项 | 值 |
|---|---|
| 状态 | 已接受 |
| 日期 | 2026-07-31 |
| 决策人 | hxy |
| 主文档关联 | §7.2.2 认证方式 |

## 背景

[ADR-0010](./0010-self-hosted-accounts-rbac.md) 决定自建账号体系后，需要选择会话凭据的承载方式。

## 决策

**HttpOnly + `SameSite=Lax` Cookie 承载会话 id，session 数据存 Redis。**

| 项 | 取值 |
|---|---|
| 有效期 | 7 天滑动过期 |
| 多端登录 | 允许并存 |

## 理由

**为什么不是 OAuth2**：OAuth2 解决的是「**第三方应用**代表用户访问资源」的授权委托问题。这里没有第三方 —— 账号自建，前端与后端同属一个系统。硬套 OAuth2 等于自己同时扮演 authorization server、resource server、client 三个角色，为一个不存在的问题引入三套概念。

> 一个容易混淆的点：FastAPI 的 `OAuth2PasswordBearer` 只是借用了 OAuth2 password grant 的**表单格式**，用它并不等于实现了 OAuth2。若需求本来就是「登录拿个 token」，那要的从来不是 OAuth2。

**为什么是 Session 而不是 JWT**：

- **可主动失效** —— 管理员禁用账号、调整配额、强制下线都能立即生效。JWT 做不到，要再补 refresh token + 黑名单，复杂度反而更高。**这是决定性理由**
- JWT 的核心收益是无状态、便于水平扩展，这一条在「单机、几百用户」（§2.2）下价值为零
- Redis 已是必需组件（§6.1），Session 零新增依赖
- HttpOnly + SameSite 使凭据不暴露给 JS，天然规避 XSS 窃取

## 被放弃的备选

| 备选 | 放弃理由 |
|---|---|
| **OAuth2** | 无第三方应用场景，纯粹为不存在的问题引入复杂度 |
| **JWT（含 refresh token）** | 无法主动失效；为补救要加黑名单，复杂度超过 Session；无状态的收益在单机下为零 |
| **HTTP Basic** | 无法登出，凭据每次请求都传输 |

## 后果

**正面**：
- 管理员操作（禁用账号、改配额）立即生效
- 零新增依赖
- 前端不需要管理 token 的刷新与过期

**代价**：
- **Cookie 无法设置 `Secure` 标志** —— [ADR-0012](./0012-plain-http-intranet.md) 决定走 HTTP，凭据在内网链路上明文传输，同网段抓包即可窃取会话。已按 §7.1 威胁模型接受，记入 §10.2
- **SSE 必须显式携带凭据** —— 前端用 `@microsoft/fetch-event-source`（见 [ADR-0007](./0007-sse-over-websocket.md) 的代价），它默认**不带** cookie，须配置 `credentials: 'include'`，否则 SSE 请求会 401
- 网关多副本时 session 共享依赖 Redis 可用性 —— Redis 故障会导致全员掉线
- 若将来要把 API 开放给第三方，需要另加一套机制

## 重新评估的触发条件

- 出现第三方应用需要代表用户访问本平台 API
- 平台开放到内网之外（届时 `Secure` 标志与 CSRF 防护都要重新设计）
- 网关需要跨机部署且不希望依赖共享 Redis
