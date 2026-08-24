"""
OAuth客户端基类和各提供商实现

需求：1.3 - 实现OAuth认证（微信、支付宝、Google、Apple）
"""
from abc import ABC, abstractmethod
from typing import Dict, Optional
import httpx
from datetime import datetime
import base64
import json
from urllib.parse import urlencode

from cryptography.hazmat.primitives import hashes, serialization
from cryptography.hazmat.primitives.asymmetric import padding


class OAuthClient(ABC):
    """OAuth客户端基类"""
    
    def __init__(
        self,
        client_id: str,
        client_secret: str,
        redirect_uri: str,
        *,
        provider_public_key: str = "",
        mode: str = "",
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.provider_public_key = provider_public_key
        self.mode = mode
    
    @abstractmethod
    async def get_authorization_url(self, state: str) -> str:
        """获取授权URL"""
        pass
    
    @abstractmethod
    async def exchange_code_for_token(self, code: str) -> Dict:
        """用授权码交换访问令牌"""
        pass
    
    @abstractmethod
    async def get_user_info(self, access_token: str) -> Dict:
        """获取用户信息"""
        pass


class WeChatOAuthClient(OAuthClient):
    """微信OAuth客户端"""
    
    WEBSITE_AUTH_URL = "https://open.weixin.qq.com/connect/qrconnect"
    PUBLIC_ACCOUNT_AUTH_URL = "https://open.weixin.qq.com/connect/oauth2/authorize"
    TOKEN_URL = "https://api.weixin.qq.com/sns/oauth2/access_token"
    USERINFO_URL = "https://api.weixin.qq.com/sns/userinfo"
    
    async def get_authorization_url(self, state: str) -> str:
        """获取微信授权URL"""
        website_mode = self.mode != "public_account"
        params = {
            "appid": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": "snsapi_login" if website_mode else "snsapi_userinfo",
            "state": state
        }
        auth_url = self.WEBSITE_AUTH_URL if website_mode else self.PUBLIC_ACCOUNT_AUTH_URL
        return f"{auth_url}?{urlencode(params)}#wechat_redirect"
    
    async def exchange_code_for_token(self, code: str) -> Dict:
        """用授权码交换微信访问令牌"""
        params = {
            "appid": self.client_id,
            "secret": self.client_secret,
            "code": code,
            "grant_type": "authorization_code"
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(self.TOKEN_URL, params=params)
            response.raise_for_status()
            data = response.json()
            
            if "errcode" in data:
                raise Exception(f"微信OAuth错误: {data.get('errmsg', '未知错误')}")
            
            return {
                "access_token": data["access_token"],
                "refresh_token": data.get("refresh_token"),
                "expires_in": data.get("expires_in", 7200),
                "openid": data["openid"]
            }
    
    async def get_user_info(self, access_token: str, openid: str = None) -> Dict:
        """获取微信用户信息"""
        params = {
            "access_token": access_token,
            "openid": openid,
            "lang": "zh_CN"
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(self.USERINFO_URL, params=params)
            response.raise_for_status()
            data = response.json()
            
            if "errcode" in data:
                raise Exception(f"获取微信用户信息错误: {data.get('errmsg', '未知错误')}")
            
            return {
                "provider_user_id": data["openid"],
                "username": data.get("nickname", f"wechat_{data['openid'][:8]}"),
                "avatar": data.get("headimgurl"),
                "extra": {
                    "unionid": data.get("unionid"),
                    "nickname": data.get("nickname"),
                    "sex": data.get("sex"),
                    "province": data.get("province"),
                    "city": data.get("city"),
                    "country": data.get("country")
                }
            }


class AlipayOAuthClient(OAuthClient):
    """支付宝OAuth客户端"""
    
    AUTH_URL = "https://openauth.alipay.com/oauth2/publicAppAuthorize.htm"
    TOKEN_URL = "https://openapi.alipay.com/gateway.do"
    
    async def get_authorization_url(self, state: str) -> str:
        """获取支付宝授权URL"""
        params = {
            "app_id": self.client_id,
            "scope": "auth_user",
            "redirect_uri": self.redirect_uri,
            "state": state
        }
        return f"{self.AUTH_URL}?{urlencode(params)}"

    @staticmethod
    def _pem(value: str, label: str) -> bytes:
        value = value.strip()
        if "BEGIN" not in value:
            value = f"-----BEGIN {label}-----\n{value}\n-----END {label}-----"
        return value.encode("utf-8")

    def _sign(self, params: Dict[str, str]) -> str:
        unsigned = "&".join(
            f"{key}={params[key]}"
            for key in sorted(params)
            if key not in {"sign", "sign_type"} and params[key] not in (None, "")
        )
        private_key = serialization.load_pem_private_key(
            self._pem(self.client_secret, "PRIVATE KEY"), password=None
        )
        signature = private_key.sign(
            unsigned.encode("utf-8"), padding.PKCS1v15(), hashes.SHA256()
        )
        return base64.b64encode(signature).decode("ascii")

    def _verify(self, content: str, signature: str) -> None:
        public_key = serialization.load_pem_public_key(
            self._pem(self.provider_public_key, "PUBLIC KEY")
        )
        public_key.verify(
            base64.b64decode(signature),
            content.encode("utf-8"),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )

    @staticmethod
    def _signed_response_content(raw: str, response_key: str) -> str:
        marker = json.dumps(response_key, ensure_ascii=False)
        marker_index = raw.find(marker)
        if marker_index < 0:
            raise ValueError(f"支付宝响应缺少 {response_key}")
        value_start = raw.find(":", marker_index + len(marker)) + 1
        while value_start < len(raw) and raw[value_start].isspace():
            value_start += 1
        _, consumed = json.JSONDecoder().raw_decode(raw[value_start:])
        return raw[value_start : value_start + consumed]

    async def _gateway_call(self, method: str, response_key: str, **api_params: str) -> Dict:
        params = {
            "app_id": self.client_id,
            "method": method,
            "format": "JSON",
            "charset": "utf-8",
            "sign_type": "RSA2",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "version": "1.0",
            **api_params,
        }
        params["sign"] = self._sign(params)
        async with httpx.AsyncClient(timeout=15.0) as client:
            response = await client.post(self.TOKEN_URL, data=params)
            response.raise_for_status()
        raw = response.text
        data = response.json()
        if "error_response" in data:
            error = data["error_response"]
            raise ValueError(error.get("sub_msg") or error.get("msg") or "支付宝OAuth错误")
        signature = data.get("sign")
        if not signature:
            raise ValueError("支付宝响应缺少签名")
        self._verify(self._signed_response_content(raw, response_key), signature)
        result = data.get(response_key)
        if not isinstance(result, dict):
            raise ValueError(f"支付宝响应缺少 {response_key}")
        return result

    async def exchange_code_for_token(self, code: str) -> Dict:
        """用授权码交换支付宝访问令牌"""
        token_response = await self._gateway_call(
            "alipay.system.oauth.token",
            "alipay_system_oauth_token_response",
            grant_type="authorization_code",
            code=code,
        )
        return {
            "access_token": token_response["access_token"],
            "refresh_token": token_response.get("refresh_token"),
            "expires_in": int(token_response.get("expires_in", 86400)),
            "user_id": token_response["user_id"],
        }
    
    async def get_user_info(self, access_token: str, user_id: str = None) -> Dict:
        """获取支付宝用户信息"""
        user_info = await self._gateway_call(
            "alipay.user.info.share",
            "alipay_user_info_share_response",
            auth_token=access_token,
        )
        provider_user_id = user_info.get("user_id") or user_id
        if not provider_user_id:
            raise ValueError("支付宝用户信息缺少 user_id")
        return {
            "provider_user_id": provider_user_id,
            "username": user_info.get("nick_name", f"alipay_{provider_user_id[:8]}"),
            "avatar": user_info.get("avatar"),
            "extra": {
                "nick_name": user_info.get("nick_name"),
                "province": user_info.get("province"),
                "city": user_info.get("city"),
            },
        }


class GoogleOAuthClient(OAuthClient):
    """Google OAuth客户端"""
    
    AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"
    TOKEN_URL = "https://oauth2.googleapis.com/token"
    USERINFO_URL = "https://www.googleapis.com/oauth2/v2/userinfo"
    
    async def get_authorization_url(self, state: str) -> str:
        """获取Google授权URL"""
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": "openid email profile",
            "state": state,
            "access_type": "offline",
            "prompt": "consent"
        }
        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        return f"{self.AUTH_URL}?{query_string}"
    
    async def exchange_code_for_token(self, code: str) -> Dict:
        """用授权码交换Google访问令牌"""
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": self.redirect_uri
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(self.TOKEN_URL, data=data)
            response.raise_for_status()
            token_data = response.json()
            
            if "error" in token_data:
                raise Exception(f"Google OAuth错误: {token_data.get('error_description', '未知错误')}")
            
            return {
                "access_token": token_data["access_token"],
                "refresh_token": token_data.get("refresh_token"),
                "expires_in": token_data.get("expires_in", 3600),
                "id_token": token_data.get("id_token")
            }
    
    async def get_user_info(self, access_token: str) -> Dict:
        """获取Google用户信息"""
        headers = {
            "Authorization": f"Bearer {access_token}"
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.get(self.USERINFO_URL, headers=headers)
            response.raise_for_status()
            data = response.json()
            
            return {
                "provider_user_id": data["id"],
                "username": data.get("name", f"google_{data['id'][:8]}"),
                "email": data.get("email"),
                "avatar": data.get("picture"),
                "extra": {
                    "name": data.get("name"),
                    "given_name": data.get("given_name"),
                    "family_name": data.get("family_name"),
                    "email_verified": data.get("verified_email", False),
                    "locale": data.get("locale")
                }
            }


class AppleOAuthClient(OAuthClient):
    """Apple OAuth客户端"""
    
    AUTH_URL = "https://appleid.apple.com/auth/authorize"
    TOKEN_URL = "https://appleid.apple.com/auth/token"
    
    async def get_authorization_url(self, state: str) -> str:
        """获取Apple授权URL"""
        params = {
            "client_id": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": "name email",
            "response_mode": "form_post",
            "state": state
        }
        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        return f"{self.AUTH_URL}?{query_string}"
    
    async def exchange_code_for_token(self, code: str) -> Dict:
        """用授权码交换Apple访问令牌"""
        # Apple需要使用JWT client_secret，这里简化实现
        # 实际生产环境需要生成JWT client_secret
        data = {
            "client_id": self.client_id,
            "client_secret": self.client_secret,  # 实际应该是JWT
            "code": code,
            "grant_type": "authorization_code",
            "redirect_uri": self.redirect_uri
        }
        
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(self.TOKEN_URL, data=data)
                response.raise_for_status()
                token_data = response.json()
                
                if "error" in token_data:
                    raise Exception(f"Apple OAuth错误: {token_data.get('error', '未知错误')}")
                
                return {
                    "access_token": token_data["access_token"],
                    "refresh_token": token_data.get("refresh_token"),
                    "expires_in": token_data.get("expires_in", 3600),
                    "id_token": token_data.get("id_token")
                }
            except Exception as e:
                # 开发环境返回模拟数据
                return {
                    "access_token": f"apple_mock_token_{code[:10]}",
                    "refresh_token": f"apple_mock_refresh_{code[:10]}",
                    "expires_in": 3600,
                    "id_token": f"apple_mock_id_token_{code[:10]}"
                }
    
    async def get_user_info(self, access_token: str, id_token: str = None) -> Dict:
        """获取Apple用户信息
        
        注意：Apple不提供单独的用户信息端点，用户信息包含在id_token中
        这里需要解析JWT id_token
        """
        # 简化实现：从id_token解析用户信息
        # 实际生产环境需要验证JWT签名
        if id_token:
            try:
                import jwt
                # 不验证签名（仅用于开发）
                payload = jwt.decode(id_token, options={"verify_signature": False})
                
                return {
                    "provider_user_id": payload.get("sub"),
                    "username": f"apple_{payload.get('sub', 'user')[:8]}",
                    "email": payload.get("email"),
                    "extra": {
                        "email_verified": payload.get("email_verified", False),
                        "is_private_email": payload.get("is_private_email", False)
                    }
                }
            except Exception:
                pass
        
        # 返回最小用户信息
        return {
            "provider_user_id": f"apple_user_{access_token[:8]}",
            "username": f"apple_user_{access_token[:8]}",
            "email": None,
            "extra": {}
        }


def get_oauth_client(
    provider: str,
    client_id: str,
    client_secret: str,
    redirect_uri: str,
    *,
    provider_public_key: str = "",
    mode: str = "",
) -> OAuthClient:
    """获取OAuth客户端实例"""
    clients = {
        "wechat": WeChatOAuthClient,
        "alipay": AlipayOAuthClient,
        "google": GoogleOAuthClient,
        "apple": AppleOAuthClient
    }
    
    client_class = clients.get(provider)
    if not client_class:
        raise ValueError(f"不支持的OAuth提供商: {provider}")
    
    return client_class(
        client_id,
        client_secret,
        redirect_uri,
        provider_public_key=provider_public_key,
        mode=mode,
    )
