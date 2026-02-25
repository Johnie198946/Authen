"""
内部服务路由器

封装 httpx.AsyncClient 对下游微服务的 HTTP 调用，统一超时和错误处理。

行为:
  - 统一超时: 10 秒
  - 下游不可用 (连接失败/超时): 返回 503 service_unavailable
  - 下游返回非预期错误格式: 返回 502 upstream_error
  - 隐藏内部微服务实现细节

需求: 8.2, 9.2, 9.4
"""
import httpx
from typing import Any, Dict, Optional


# 下游微服务地址映射
DEFAULT_SERVICE_URLS = {
    "auth": "http://localhost:8001",
    "sso": "http://localhost:8002",
    "user": "http://localhost:8003",
    "permission": "http://localhost:8004",
    "llm": "http://localhost:8010",
}

# 统一超时（秒）
DEFAULT_TIMEOUT = 10.0


class ServiceRouter:
    """
    内部服务路由器，封装对下游微服务的 HTTP 调用。

    使用 httpx.AsyncClient 发起异步请求，统一处理超时和错误。
    """

    def __init__(
        self,
        services: Optional[Dict[str, str]] = None,
        timeout: float = DEFAULT_TIMEOUT,
        client: Optional[httpx.AsyncClient] = None,
    ):
        """
        Args:
            services: 服务名称到 URL 的映射，默认使用 DEFAULT_SERVICE_URLS
            timeout: 请求超时时间（秒），默认 10 秒
            client: 可选的 httpx.AsyncClient 实例（用于测试注入）
        """
        self.services = services or dict(DEFAULT_SERVICE_URLS)
        self.timeout = timeout
        self.client = client or httpx.AsyncClient(timeout=timeout)

    async def forward(
        self,
        service: str,
        method: str,
        path: str,
        **kwargs: Any,
    ) -> dict:
        """
        转发请求到下游微服务，统一错误处理。

        Args:
            service: 目标服务名称（auth/sso/user/permission）
            method: HTTP 方法（GET/POST/PUT/DELETE）
            path: 请求路径（如 /api/v1/auth/login）
            **kwargs: 传递给 httpx 的额外参数（json, headers, params 等）

        Returns:
            下游服务的 JSON 响应字典

        Raises:
            dict: 包含 status_code 和 body 的错误响应（通过 ServiceRouterError）
        """
        base_url = self.services.get(service)
        if not base_url:
            return {
                "status_code": 502,
                "body": {
                    "error_code": "upstream_error",
                    "message": "未知的下游服务",
                },
            }

        url = f"{base_url}{path}"

        try:
            response = await self.client.request(method, url, **kwargs)
        except (httpx.ConnectError, httpx.ConnectTimeout):
            # 下游服务不可用（连接失败）
            return {
                "status_code": 503,
                "body": {
                    "error_code": "service_unavailable",
                    "message": "下游服务暂时不可用，请稍后重试",
                },
            }
        except httpx.TimeoutException:
            # 请求超时
            return {
                "status_code": 503,
                "body": {
                    "error_code": "service_unavailable",
                    "message": "下游服务响应超时，请稍后重试",
                },
            }
        except httpx.HTTPError:
            # 其他 HTTP 传输错误
            return {
                "status_code": 502,
                "body": {
                    "error_code": "upstream_error",
                    "message": "下游服务通信异常",
                },
            }

        # 解析下游响应
        return self._parse_response(response)

    def _parse_response(self, response: httpx.Response) -> dict:
        """
        解析下游服务的 HTTP 响应。

        成功响应直接透传 JSON；错误响应转换为统一格式，隐藏内部细节。

        Args:
            response: httpx.Response 对象

        Returns:
            包含 status_code 和 body 的字典
        """
        try:
            body = response.json()
        except (ValueError, TypeError):
            # 下游返回非 JSON 格式
            if response.status_code >= 400:
                return {
                    "status_code": 502,
                    "body": {
                        "error_code": "upstream_error",
                        "message": "下游服务返回了非预期的响应格式",
                    },
                }
            # 成功但非 JSON（不太常见，兜底处理）
            return {
                "status_code": response.status_code,
                "body": {"data": response.text},
            }

        # 成功响应直接透传
        if response.status_code < 400:
            return {
                "status_code": response.status_code,
                "body": body,
            }

        # 错误响应：检查是否符合预期格式
        if isinstance(body, dict) and "detail" in body:
            # FastAPI 标准错误格式，转换为统一格式
            # 5xx 错误隐藏内部细节，4xx 错误可透传业务信息
            if response.status_code >= 500:
                message = "下游服务内部错误"
            else:
                message = body.get("detail", "下游服务返回错误")
            return {
                "status_code": response.status_code,
                "body": {
                    "error_code": body.get("error_code", "upstream_error"),
                    "message": message,
                },
            }

        if isinstance(body, dict) and "error_code" in body and "message" in body:
            # 已经是统一格式，直接透传
            return {
                "status_code": response.status_code,
                "body": {
                    "error_code": body["error_code"],
                    "message": body["message"],
                },
            }

        # 非预期的错误格式 → 502
        return {
            "status_code": 502,
            "body": {
                "error_code": "upstream_error",
                "message": "下游服务返回了非预期的错误格式",
            },
        }

    async def close(self):
        """关闭 HTTP 客户端连接池"""
        await self.client.aclose()


# 模块级单例（延迟初始化）
_router_instance: Optional[ServiceRouter] = None


def get_service_router() -> ServiceRouter:
    """
    获取 ServiceRouter 单例实例。

    Returns:
        ServiceRouter 实例
    """
    global _router_instance
    if _router_instance is None:
        _router_instance = ServiceRouter()
    return _router_instance
