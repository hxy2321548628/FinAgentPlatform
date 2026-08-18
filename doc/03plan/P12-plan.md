# P12 实施计划：沙箱开放出网，agent 自己装包

这一期只做一件事：**让 agent 缺库时能自己装上，而不是直接卡死**。它推翻的是 [P1 §2.2](./P1-plan.md) 的「沙箱保持 `--network=none`」—— 那条当时就写好了重估触发条件，本次由使用方直接提出放开。

范围比字面小一层：**只放开 Python 包，不放开系统包**。三个决策点在开工前拍板（见 §2），走的都是代价最小的那条。

### 版本历史

| 日期 | 变更 |
|---|---|
| 2026-08-18 | 初稿。开工前五处实测全部完成，**一处推翻了「改个网络配置就行」的初始预期**（§2.1），一处抓出会静默失效的索引源（§2.3） |

---

## 1. 边界

**做**：沙箱出网、agent 用 `pip` 装 Python 包、包落在 workspace、提示词同步告诉它这件事。

**不做**：

| 不做的 | 为什么 |
|---|---|
| `apt-get` 装系统包 | 要 root 就得拆掉 `--read-only` / `cap-drop` / `no-new-privileges` 三条加固；而容器 per-thread 可抛弃，装了随销毁就没，**付出全部安全代价换不到持久性** |
| iptables 白名单 bridge | 规则要跟着动态创建的容器走，配错无症状；挡的攻击不在威胁模型内。论证见 [ADR-0017](../01design/adr/0017-sandbox-network-and-package-install.md) |
| 自建 devpi / 内网 pypi 镜像 | 多一个要运维的服务，公网镜像源已经够快（§2.3） |
| 跨会话共享 site-packages | 一个会话装的包被另一个会话加载 —— 在跑不可信代码的地方开会话间投毒通路 |

**加固清单一条未动。** `--read-only`、`--cap-drop=ALL`、`no-new-privileges`、非 root、gVisor、5 GB XFS 配额全部原样。

---

## 2. 开工前实测与本期定案

### 2.1 「开个网就行」不成立 —— 真正卡住 P1 的是可写可执行路径

P1 当时的原话是「要支持装包，得先给出一条可写且可执行的路径，那是对加固清单的实质放松」。这句话**只对了一半**：路径确实是关键，但**给出它并不需要放松加固清单**。

`--read-only` 让 `pip` 只能装到 `HOME`，而 `HOME=/tmp` 是 512 MB 且 `noexec` 的 tmpfs —— 装得下的包跑不起来，跑得起来的包装不下。**答案是 workspace**：它是 bind mount，可写、没有 `noexec`、随会话持久，且本来就被 5 GB XFS 配额兜着。

> **实测（2026-08-18）**：与生产完全同款的加固参数下，`PYTHONUSERBASE=/workspace/.local` + `pip install --user statsmodels` 装出 185 MB，`scipy/linalg/_fblas.cpython-313-x86_64-linux-gnu.so` 从 workspace 正常加载，OLS 跑出结果。**因此本期不碰 `ALWAYS_ON_ARGUMENT` 任何一条。**

### 2.2 `PIP_USER=1` 不是便利，是堵失败路径

不设的话，漏写 `--user` 的 `pip install` 会去装只读 rootfs；报错后 agent 多半改去装 `/tmp`，而那儿 `noexec` —— 装完照样跑不起来，且**第二次失败的报错不指向落点**。设上之后，`pip install 包名` 直接就是对的。

判据因此**刻意不加 `--user`**：验的就是落点有没有被纠正过来。

### 2.3 uv 完全忽略 `PIP_INDEX_URL` —— 两个变量都要给

> **实测**：给一个无效的 `PIP_INDEX_URL`，`uv pip install` **照样成功**（说明它走的默认官方源）；给无效的 `UV_INDEX_URL` 才失败。`pip` 则只认前者。
>
> 第一版探针用 `--dry-run` 对比两个变量，**两个都「成功」** —— 那个判据分辨不出它到底用了哪个源，换成无效 URL 才照出来。

少给一个的症状**只是慢**，不报错：agent 用 `uv pip` 时悄悄退回官方源。

### 2.4 镜像源是可用性前提，不是优化

> **实测**：直连 pypi.org **83 KB/s**，statsmodels 一套（45 MB）花 **9 分 51 秒** —— 直接撞上单次执行的 wall-clock 超时。换清华源后 scikit-learn 一套 **14 秒**。

因此 `SANDBOX_INDEX_URL` 默认给清华源，而不是留空走官方源。

### 2.5 apt 确实无解，且报错还算清楚

> **实测**：`apt-get install jq` → `Could not open lock file /var/lib/dpkg/lock-frontend ... are you root?`

报错指向 root，但 agent 仍会为此浪费轮次，**因此提示词里显式写明不要试**（与字体那条同一个道理）。

---

## 3. 验收标准

| 编号 | 判据 | 状态 |
|---|---|---|
| **P12①** | 沙箱能自己装包，且包落在 workspace 里、import 得起来 | **通过**（2026-08-18） |

判据走**真实 broker 起的真实沙箱**，不自己 `docker run` —— 要验的正是平台交给沙箱的那组环境变量，自己拼容器就把它们绕开了。**落点必须一起验**：装进 `/tmp` 也会「装成功」，换成带原生扩展的包才会在 import 时炸，而报错不指向落点。

判据总数 61 → **62**，免费的 42 → **43**（这条不要 LLM 也不要 root）。

---

## 4. 任务分解

| 步骤 | 改动 | 验证 |
|---|---|---|
| 1 | 测试先行：改掉断言零出网的两条，新增可执行性 / 出网 / 装包三条 | 红（`USER_BASE` 未定义） |
| 2 | `container.py`：默认网络转 bridge，注入五个环境变量 | `container_test.py` 37 条全绿 |
| 3 | `pool.py` / `config.py` / `broker/runtime.py`：把 `index_url` 穿下去 | `make` 全绿 |
| 4 | `prompt.py`：告诉 agent 能装什么、装不了什么 | 提示词判据改为验 `pip install` 与 `apt-get` |
| 5 | `sandbox.Dockerfile`：PATH 加 user bin，头部注释改掉「不是给沙箱开网」 | 重建镜像 |
| 6 | 文档与 ADR-0017；`verify.sh` 补 P12① | 部署后实跑 |

---

## 5. 回归关系

**打穿的历史判据两处，都已改**：

- `container_test.py::test_the_sandbox_has_no_network` —— 断言的正是本期要放开的东西，替换为出网判据；
- `verify.sh` 的 `P6②` `offline_pip` —— 提示词契约里「公网」那条不再成立，改验 `pip install` 与 `apt-get` 两个词。

**`verify.sh` 里两处硬编码的 `--network=none`** 也一并改成 bridge（配额组起沙箱用）—— 它们验的是配额，与网络无关，但留着就是与实现不一致的第二个真相源。

**反证做过两次**（判据本身会不会假过）：

1. 把网络调回 `none`，装包 exit 1 —— 证明装包判据确实在测网络；
2. `SANDBOX_NETWORK=none` 下容器照常起得来 —— 退路仍然通。

---

## 6. 待决事项

无。三个决策点（装包范围、网络范围、安装路径）开工前已拍板。

---

## 7. 实施记录

**门禁**：`make` 双端全绿。`container_test.py` 37 条通过，新增三条**确认是 PASSED 而非 SKIPPED**（联网用例在连不上 pypi 时记 skip，不假红也不假绿）。

**部署后实测**（`make rebuild` 起栈后，走真实 broker）：

```
环境: PIP_USER=1 BASE=/workspace/.local | IDX=…tuna…/simple | UV=…tuna…/simple
装 statsmodels: exit 0
import: exit 0  /workspace/.local/lib/python3.13/site-packages/scipy/linalg/__init__.py
```

**`P12①` 初版是坏的，部署后才照出来**：`POST /threads` 只开目录、不起容器，漏了 `POST /threads/{id}/sandbox` 这一步，`execute` 一律报「该会话当前没有运行中的沙箱」—— 而那个红**看着像装包失败**。已在判据里补上申请与归还，并就地注明原因。

**`.env` 未改**：那台机器的 `.env` 里没有 `SANDBOX_NETWORK`，走代码默认值即新行为；`.env.example` 已更新，含两项新配置与各自的代价说明。
