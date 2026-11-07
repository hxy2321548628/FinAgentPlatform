"""验证凭据不会覆盖用户 URL，且旧服务认证保持兼容。"""

import unittest
from urllib.parse import parse_qs, urlsplit

from app.agent.mcp_auth import connection_auth


class ConnectionAuthTest(unittest.TestCase):
    def test_tushare_encodes_secret_and_preserves_query(self) -> None:
        url, headers = connection_auth("https://api.tushare.pro/mcp/?a=1&token=", "a+b&c=?#")
        self.assertEqual(parse_qs(urlsplit(url).query), {"a": ["1"], "token": ["a+b&c=?#"]})
        self.assertIsNone(headers)

    def test_user_token_is_not_overwritten(self) -> None:
        url = "https://api.tushare.pro/mcp/?token=user-token"
        self.assertEqual(connection_auth(url, "admin-token"), (url, None))

    def test_existing_header_auth_is_preserved(self) -> None:
        url = "https://example.com/mcp"
        self.assertEqual(connection_auth(url, "Bearer demo"), (url, {"Authorization": "Bearer demo"}))

    def test_no_credential_and_endpoint_boundaries(self) -> None:
        for url in ("https://api.tushare.pro/mcp/", "https://example.com/mcp"):
            self.assertEqual(connection_auth(url, None), (url, None))
        for url in (
            "http://api.tushare.pro/mcp/",
            "https://api.tushare.pro.evil/mcp/",
            "https://api.tushare.pro/other",
        ):
            self.assertEqual(connection_auth(url, "demo"), (url, {"Authorization": "demo"}))

    def test_actual_connection_uses_query_for_both_transports(self) -> None:
        from app.agent.mcp import McpTarget, _connection

        for transport in ("sse", "streamable_http"):
            target = McpTarget("test", "test", "https://api.tushare.pro/mcp/", transport, "demo+token", [], True, None)
            connection = _connection(target)
            assert connection["transport"] == "sse" or connection["transport"] == "streamable_http"
            self.assertEqual(parse_qs(urlsplit(connection["url"]).query), {"token": ["demo+token"]})
            self.assertIsNone(connection["headers"])
            self.assertEqual(target.url, "https://api.tushare.pro/mcp/")


class LogRedactionTest(unittest.TestCase):
    def test_url_token_is_redacted_in_logs(self) -> None:
        import logging

        from log import JsonFormatter

        record = logging.LogRecord(
            "httpx", logging.INFO, "", 0, "request https://api.tushare.pro/mcp/?token=demo-secret&x=1", (), None
        )
        output = JsonFormatter().format(record)
        self.assertNotIn("demo-secret", output)
        self.assertIn("[REDACTED]", output)


if __name__ == "__main__":
    unittest.main()
