# 本次服务器部署记录

- 服务器：Ubuntu 24.04.4 / x86_64，202.114.239.42。
- 已部署版本：20261012T145413838654Z。
- 入口：http://202.114.239.42/ 。UU 远程虚拟机浏览器已实测首页正常显示。
- systemd：FinAgentPlatform.service，已 enable；安装启动返回成功。
- 六个服务：api、worker、broker、nginx、postgres、redis 均 Up；postgres/redis healthy。
- worker 日志显示开始运行；Langfuse 未配置，因此不上传追踪。
- gVisor：runsc release-20260914.0；通过实际沙箱镜像运行 Python，输出 4。
- workspace：/var/lib/finagent/sandbox，来自 30 GiB XFS loop 镜像；Project quota Accounting/Enforcement 均 ON，fstab 已配置。
- 配置：/etc/finagent/platform.env；密码和 API 密钥由用户在服务器填写，未写入本地记录。
- 数据：/var/lib/finagent；版本：/opt/finagent/releases；当前入口：/opt/finagent/current。

## 下载故障与修正

Docker Hub 请求超时，Docker 官方 Amazon ECR 仓库可访问。已下载 docker:27-cli、nginx:1.27-alpine、node:24-bookworm-slim、postgres:16-alpine、redis:7-alpine 并本地标记为项目原名。已将服务器安装副本的数据库拉取步骤改为 `compose pull --policy missing postgres redis`，并从该安装副本继续部署。本地 install.sh 已同步修正，并添加 preload-ecr.sh；旧上传包中的 install.sh 不含此修正，后续发布请用本地新生成的包。

## 运维

```bash
systemctl start FinAgentPlatform.service
systemctl stop FinAgentPlatform.service
systemctl restart FinAgentPlatform.service
systemctl status FinAgentPlatform.service
journalctl -u FinAgentPlatform.service -n 100 --no-pager
bash /opt/finagent/current/linux/control.sh status
bash /opt/finagent/current/linux/control.sh logs worker
```

本次验证了首页、API 就绪、六个服务、worker 初始化、gVisor Python 执行和 XFS 配额启用。未进行真实模型分析、完整 broker 会话流程、宿主机重启或更新回滚实测；不将这些记为已通过。当前为 HTTP 试运行，尚未配置域名和 TLS。
