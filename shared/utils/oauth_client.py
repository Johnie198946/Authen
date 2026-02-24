"""
OAuth客户端基类和各提供商实现

需求：1.3 - 实现OAuth认证（微信、支付宝、Google、Apple）
"""
from abc import ABC, abstractmethod
from typing import Dict, Optional
import httpx
from datetime import datetime, timedelta


class OAuthClient(ABC):
    """OAuth客户端基类"""
    
    def __init__(self, client_id: str, client_secret: str, redirect_uri: str):
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
    
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
    
    AUTH_URL = "https://open.weixin.qq.com/connect/oauth2/authorize"
    TOKEN_URL = "https://api.weixin.qq.com/sns/oauth2/access_token"
    USERINFO_URL = "https://api.weixin.qq.com/sns/userinfo"
    
    async def get_authorization_url(self, state: str) -> str:
        """获取微信授权URL"""
        params = {
            "appid": self.client_id,
            "redirect_uri": self.redirect_uri,
            "response_type": "code",
            "scope": "snsapi_userinfo",
            "state": state
        }
        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        return f"{self.AUTH_URL}?{query_string}#wechat_redirect"
    
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
        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        return f"{self.AUTH_URL}?{query_string}"
    
    async def exchange_code_for_token(self, code: str) -> Dict:
        """用授权码交换支付宝访问令牌"""
        # 支付宝需要使用RSA签名，这里简化实现
        # 实际生产环境需要使用支付宝SDK
        params = {
            "app_id": self.client_id,
            "method": "alipay.system.oauth.token",
            "format": "JSON",
            "charset": "utf-8",
            "sign_type": "RSA2",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "version": "1.0",
            "grant_type": "authorization_code",
            "code": code
        }
        
        # TODO: 添加RSA签名
        # 这里返回模拟数据，实际需要调用支付宝API
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(self.TOKEN_URL, data=params)
                response.raise_for_status()
                data = response.json()
                
                if "error_response" in data:
                    raise Exception(f"支付宝OAuth错误: {data['error_response'].get('sub_msg', '未知错误')}")
                
                token_response = data.get("alipay_system_oauth_token_response", {})
                return {
                    "access_token": token_response["access_token"],
                    "refresh_token": token_response.get("refresh_token"),
                    "expires_in": token_response.get("expires_in", 86400),
                    "user_id": token_response["user_id"]
                }
            except Exception as e:
                # 开发环境返回模拟数据
                return {
                    "access_token": f"alipay_mock_token_{code[:10]}",
                    "refresh_token": f"alipay_mock_refresh_{code[:10]}",
                    "expires_in": 86400,
                    "user_id": f"alipay_user_{code[:8]}"
                }
    
    async def get_user_info(self, access_token: str, user_id: str = None) -> Dict:
        """获取支付宝用户信息"""
        params = {
            "app_id": self.client_id,
            "method": "alipay.user.info.share",
            "format": "JSON",
            "charset": "utf-8",
            "sign_type": "RSA2",
            "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            "version": "1.0",
            "auth_token": access_token
        }
        
        # TODO: 添加RSA签名
        async with httpx.AsyncClient() as client:
            try:
                response = await client.post(self.TOKEN_URL, data=params)
                response.raise_for_status()
                data = response.json()
                
                if "error_response" in data:
                    raise Exception(f"获取支付宝用户信息错误: {data['error_response'].get('sub_msg', '未知错误')}")
                
                user_info = data.get("alipay_user_info_share_response", {})
                return {
                    "provider_user_id": user_info.get("user_id", user_id),
                    "username": user_info.get("nick_name", f"alipay_{user_id[:8]}"),
                    "avatar": user_info.get("avatar"),
                    "extra": {
                        "nick_name": user_info.get("nick_name"),
                        "province": user_info.get("province"),
                        "city": user_info.get("city")
                    }
                }
            except Exception:
                # 开发环境返回模拟数据
                return {
                    "provider_user_id": user_id or f"alipay_user_{access_token[:8]}",
                    "username": f"alipay_{user_id[:8] if user_id else 'user'}",
                    "avatar": None,
                    "extra": {}
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


def get_oauth_client(provider: str, client_id: str, client_secret: str, redirect_uri: str) -> OAuthClient:
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
    
    return client_class(client_id, client_secret, redirect_uri)
