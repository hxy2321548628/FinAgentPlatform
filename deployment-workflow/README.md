# main 源码 + CICD 工具部署

`main` 保存业务源码，`CICD` 保存本目录和 GitHub Actions。部署时使用 `origin/main` 的 Git 归档，既不切换 CICD 工作目录，也不需要预先下载发布包。每个发布包记录实际的 main 提交 SHA；源码和部署工具分开取材。

## 获取两个分支

```bash
git clone --branch CICD git@github.com:hxy2321548628/FinAgentPlatform.git
cd FinAgentPlatform
git fetch origin main:refs/remotes/origin/main
```

不需要 SSH 写权限的服务器也可以用 HTTPS 克隆公开仓库；私有仓库使用只读 deploy key 或自己的 Git 凭据，工具不包含凭据。

## Windows 本地打包，再通过堡垒机上传

需要 Python 3.11+、Git。仓库根目录 PowerShell：

```powershell
git fetch origin main:refs/remotes/origin/main
.\deployment-workflow\build.ps1
# 本机有 Docker Linux 引擎时，生成完整 linux/amd64 镜像包：
.\deployment-workflow\build.ps1 -WithImages
# 按实际打包源码运行 make 门禁；要求 make、uv、Node 24、pnpm 11：
.\deployment-workflow\build.ps1 -RunChecks -WithImages
# 指定另一提交，便于复现历史版本：
.\deployment-workflow\build.ps1 -Ref <提交SHA>
```

Python 通用入口（Windows/Linux）：

```bash
python deployment-workflow/package.py --ref origin/main
python deployment-workflow/verify-package.py
```

输出为 `deployment-workflow/dist/` 中的 tar.gz 和 .sha256，不提交 Git。`--ref` 只打包该提交已跟踪的文件，忽略当前工作目录的未提交改动；省略 --ref 才使用当前 checkout 文件。部署目录、凭据、运行数据、node_modules 和虚拟环境不进入业务源码包。Docker 基础标签沿用 main，依赖使用 main 锁文件。

## Linux 从 Git 直接部署 main

Ubuntu 24.04 x86_64，以 root 执行。已经有 XFS + prjquota 数据盘时：

```bash
bash deployment-workflow/linux/deploy-main.sh --ecr
```

没有 XFS 数据盘、需要在现有 ext4 上试运行时：

```bash
bash deployment-workflow/linux/deploy-main.sh --trial-xfs --ecr
```

入口会依次：拉取 main → 生成发布包 → 安装 Docker/Compose/gVisor 等基础软件 → 可选准备 30 GiB XFS loop 文件 → 可选从 Docker 官方 ECR 预加载镜像 → 构建业务/前端/沙箱镜像 → 安装 systemd 服务 → 检查首页和 API。

`--trial-xfs` 要求至少 40 GiB 可用空间，预分配 30 GiB，固定挂载 `/var/lib/finagent/sandbox`，启用 project quota 并写入 fstab；不改分区、不重新格式化已有镜像，目录非空时拒绝覆盖挂载。loop 只适合试运行，全部会话共享 30 GiB。生产环境应使用真正的 XFS 数据盘。

`--ecr` 适用于 Docker Hub 超时而 public.ecr.aws 可达的机器；来源是 Docker 的官方 ECR 发布仓库。仍要求 ghcr.io、Python/npm/Debian 软件源可访问。gVisor 注册可能重启 Docker，在维护窗口执行。

### 首次运行填写配置

第一次会生成 `/etc/finagent/platform.env` 并退出，这是预期行为：

```bash
nano /etc/finagent/platform.env
```

填写 `DEEPSEEK_API_KEY`、`ADMIN_PASSWORD`，确认模型 ID 在你的 API 上可用，再重跑同一部署入口。`ADMIN_PASSWORD` 在认证段落，仅用于首次创建管理员。配置文件权限 600；数据库密码随机生成，初始化后不要仅通过改配置更改数据库密码。脚本不打印凭据，不把 .env 当 shell 脚本执行。

已有 XFS 挂载和配置时，同一命令可以部署后续 main 更新；镜像下载或构建失败保留配置和数据。

## 服务器无法从 Git 拉取时：传包部署

在可联网的本机按上面命令打包，上传包和校验文件，服务器执行（用实际版本替换占位符）：

```bash
cd /root/finagent-upload
sha256sum -c FinAgentPlatform-<版本>.tar.gz.sha256
tar -xzf FinAgentPlatform-<版本>.tar.gz
bash <版本>/linux/preflight.sh
bash <版本>/linux/bootstrap.sh
# 仅试运行、缺少 XFS 数据盘时：
bash <版本>/linux/setup-trial-xfs.sh
# 源码包且 Docker Hub 不可达时：
bash <版本>/linux/preload-ecr.sh
bash <版本>/linux/install.sh "$PWD/<版本>"
```

首次生成配置后填写密钥/密码，再重跑最后一条。源码包在服务器联网构建；`-WithImages` 包自带业务、前端、沙箱、Postgres、Redis 镜像，服务器导入后启动不拉取或构建。离线镜像包仍要求运维预装 Docker、Compose、runsc、python3 和 xfsprogs；模型调用仍需模型服务网络。

## 启停与访问

```bash
systemctl start FinAgentPlatform.service
systemctl stop FinAgentPlatform.service
systemctl restart FinAgentPlatform.service
systemctl status FinAgentPlatform.service
journalctl -u FinAgentPlatform.service -n 100 --no-pager
bash /opt/finagent/current/linux/control.sh status
bash /opt/finagent/current/linux/control.sh logs worker
```

访问 `http://<服务器IP>/`，账号 admin，密码为自行配置值。默认 HTTP_PORT=80，网络/防火墙需允许访问；不自动配置域名、TLS 或修改防火墙。服务开机等待 workspace 挂载，每次启动现查配额设备。systemd active 表示启动编排成功，持续健康看容器状态。worker 停机排空最多等待 30 分钟；stop 停六个服务，动态沙箱由 broker 生命周期管理。

## 更新、备份、回滚

配置在 `/etc/finagent`，数据在 `/var/lib/finagent`，版本在 `/opt/finagent/releases`，当前入口为 `/opt/finagent/current`。更新先构建，再停机备份 Postgres 到 `/var/backups/finagent/pre-<版本>.sql`，然后切换版本并启动；存在停机窗口。SQL 备份不含 Redis、workspace、Skill，完整灾备需要另外备份文件数据。

启动失败时数据库可能已迁移，不自动回滚数据库。确认迁移向后兼容后才运行：

```bash
bash /opt/finagent/current/linux/rollback.sh --schema-compatible
```

非兼容迁移由运维在维护窗口恢复数据库并处理更新后产生的数据。

## GitHub Actions

推送 CICD 或向 main 发 PR，会检查 shell、部署打包测试，并在实际 main 源码上执行统一 `make sync-locked` 和 `make all`；成功后生成 main 源码发布包并上传 artifact。Actions 的手动入口可以选 with_images=true 生成 Linux 镜像包；不保存服务器 SSH 凭据、不自动穿过堡垒机部署。业务 main 更新后可在 CICD 手动运行，或本地重新 fetch main 后打包/直接部署。

依赖 Docker 官方镜像 ECR 来源说明：https://aws.amazon.com/blogs/containers/docker-official-images-now-available-on-amazon-elastic-container-registry-public/
Docker 安装：https://docs.docker.com/engine/install/ubuntu/
gVisor 安装：https://gvisor.dev/docs/user_guide/install/
