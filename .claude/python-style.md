<!-- .claude/python-style.md -->

# 代码风格指南（Python）

技术宪法的落地细则，只讲"怎么写"。与宪法冲突时以宪法为准。

---

## 一、命名

- **单数名词**：包 / 模块 / 文件名一律单数（`model/user.py`，非 `models/users.py`）。
- **snake_case**：变量、函数、模块名小写下划线（`get_user_by_id`，非 `getUserById`）。
- **PascalCase**：类名大驼峰（`UserService`、`UserCreate`）。
- **UPPER_CASE**：模块级常量全大写下划线（`MAX_RETRY = 3`），定义在文件顶部；关键参数 / 魔法数字不硬编码进函数体。
- **测试文件**：统一 `{module}_test.py`。

---

## 二、类型注解

- **公开签名必带注解**：参数与返回值都要标类型。
- **禁止 `Any`**：用具体类型、`Optional[X]` 或泛型表达，不以 `Any` 兜底。
- **精确容器**：写 `list[User]`、`dict[str, int]`，不留裸 `list` / `dict`。

---

## 三、文档字符串（PEP 257 / Google Style）

- **简洁清晰**：首行是一句话摘要，以句号结尾；多行时摘要与正文之间空一行。
- **写"做什么"而非"怎么做"**：仅当实现细节对使用者至关重要时才提及。
- **与代码同步更新**：过时的文档比没有更糟。
- **适用范围**：模块 / 类 / 公开函数（及方法）均遵循 PEP 257。
- **模块**：文件顶部一段 docstring，说明该模块的职责与边界。
- **类**：说明其抽象与用途；`__init__` 的参数在类 docstring 或 `__init__` 二选一说明。
- **公开函数 / 方法必写**；私有（`_` 前缀）按需。
- **按需分节（Google Style）**：用 `Args:` / `Returns:` / `Raises:` / `Examples:`，无内容不占位。

  ```python
  def get_user_by_id(user_id: int) -> Optional[User]:
      """根据 ID 获取用户，不存在时返回 None。

      Args:
          user_id: 用户唯一标识。

      Returns:
          找到的 User，否则 None。

      Raises:
          ValueError: user_id 小于 1。
      """
  ```

---

## 四、注释

- **注释置于代码上方**：单独成行；禁止行尾注释（如 `x = 1  # 说明`）。
- **回答"为什么"而非"是什么"**：说明意图、权衡与坑，而非复述代码在做什么。
- **代码自解释优先，注释是补充**：能用命名与结构表达清楚的，就不写注释。
- **不写显而易见的注释**：零信息注释（如 `i += 1  # 自增`）一律删除。
- **保持上下文相关、拒绝过时**：注释随代码同步更新，宁可删除也不留过时误导的注释。
- **不引用外部文档**：注释与 docstring 均不写 doc 引用；必要信息就地说清，避免文档迁移 / 改名后失效。

---

## 五、Pydantic 模型

- **结构化数据用 BaseModel**：入参 / 出参 / 配置由模型承载，不用裸 dict 传递。
- **字段带约束与说明**：`Field(..., min_length=1, description="...")`。
- **分层复用**：`Base` → `Create` / `Response` 继承，杜绝字段重复。

---

## 六、配置与环境变量

- **集中到 Settings**：用 `pydantic_settings.BaseSettings` 统一读取，从 `.env` 加载。
- **禁止散落读取**：业务代码不直接 `os.getenv`，一律走 Settings。
- **密钥不入库**：`.env` 不提交，仓库只保留 `.env.example` 作模板。
- **引入第三方库**: 使用`uv add`, 不使用`uv pip install`, 安装包应该显示记录依赖再`pyproject.toml`文件中