"""平台配置的唯一入口。

外部配置一律从这里读，业务代码不直接调 `os.getenv`。
"""

from functools import lru_cache
from pathlib import Path

from pydantic import Field, SecretStr
from pydantic_settings import BaseSettings, SettingsConfigDict

# .env 在仓库根而不在 app/，且门禁（cwd=app/）与 uvicorn（cwd 不定）的工作目录并不一致，
# 因此按本文件位置解析成绝对路径 —— 相对路径或向上搜索都会在某种场景下静默读到别的文件。
REPO_ROOT = Path(__file__).resolve().parent.parent
ENV_FILE = REPO_ROOT / ".env"


class Settings(BaseSettings):
    """平台运行所需的外部配置。

    缺必填项时构造即抛 `ValidationError`，让进程在启动时失败，
    而不是等到第一次调模型才炸。
    """

    model_config = SettingsConfigDict(
        env_file=ENV_FILE,
        env_file_encoding="utf-8",
        # .env 里可能有部署脚本用的其他变量，多出来的键不该让平台起不来
        extra="ignore",
        # get_settings() 让全进程共用一个实例，冻结它才不构成可变全局状态
        frozen=True,
    )

    deepseek_api_key: SecretStr = Field(description="DeepSeek API 凭据。无默认值，缺失即启动失败")
    deepseek_base_url: str = Field(
        default="https://api.deepseek.com",
        description="DeepSeek API 地址",
    )
    model_main: str = Field(
        default="deepseek-v4-pro",
        description="主模型，承担多步推理与代码生成",
    )
    model_aux: str = Field(
        default="deepseek-v4-flash",
        description="辅助模型，承担意图分类等轻量调用",
    )


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """返回全进程共享的配置实例。

    缓存的作用不只是省一次文件读取：配置在首次调用时校验一次，
    校验失败就是启动失败，不会出现「一半请求成功一半炸」的中间状态。
    """
    return Settings()
