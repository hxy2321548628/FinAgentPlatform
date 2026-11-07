"""MCP 连接凭据适配，不修改目录中的用户配置。"""

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


def connection_auth(url: str, credential: str | None) -> tuple[str, dict[str, str] | None]:
    """Tushare 使用 token 查询参数，其他服务沿用 Authorization 认证。"""
    parts = urlsplit(url)
    if parts.scheme == "https" and parts.netloc == "api.tushare.pro" and parts.path in ("/mcp", "/mcp/"):
        query = parse_qsl(parts.query, keep_blank_values=True)
        # 用户已经提供 token 时原样使用，不覆盖其密钥，也不另发 Authorization。
        if any(key == "token" and value for key, value in query):
            return url, None
        if credential:
            query = [(key, value) for key, value in query if key != "token"]
            query.append(("token", credential))
            return urlunsplit(parts._replace(query=urlencode(query))), None
        return url, None
    return url, None if credential is None else {"Authorization": credential}


def redact_token(message: str) -> str:
    """从日志文本中隐藏 URL 查询参数中的 token。"""
    import re

    return re.sub(r"([?&]token=)[^&\s\"'<>]+", r"\1[REDACTED]", message, flags=re.IGNORECASE)
