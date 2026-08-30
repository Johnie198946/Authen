"""
短信发送服务

实现短信API调用、模板渲染和重试机制。
支持阿里云和腾讯云短信服务。
支持从数据库读取云服务配置和短信模板。
"""
import logging
import json
import hmac
import hashlib
import os
import time
from datetime import datetime
from typing import Dict, Any, Optional
import httpx
from jinja2 import Template, TemplateError
from sqlalchemy.orm import Session
from shared.database import get_db
from shared.models.system import CloudServiceConfig, MessageTemplate

logger = logging.getLogger(__name__)


class AliyunSMSClient:
    """阿里云短信客户端"""
    
    def __init__(self, config: Dict[str, Any], sdk_client=None, request_factory=None):
        """
        初始化阿里云短信客户端
        
        Args:
            config: 阿里云短信配置
                - access_key_id: AccessKey ID
                - access_key_secret: AccessKey Secret
                - sign_name: 短信签名
                - endpoint: API端点（默认：dysmsapi.aliyuncs.com）
                - region_id: 地域（默认：cn-qingdao）
        """
        self.access_key_id = config.get('access_key_id')
        self.access_key_secret = config.get('access_key_secret')
        self.sign_name = config.get('sign_name')
        self.endpoint = config.get('endpoint', 'dysmsapi.aliyuncs.com')
        self.region_id = config.get('region_id', 'cn-qingdao')
        
        if not all([self.access_key_id, self.access_key_secret, self.sign_name]):
            raise ValueError("阿里云短信配置不完整")
        self.sdk_client = sdk_client or self._create_sdk_client()
        self.request_factory = request_factory or self._load_request_factory()

    def _create_sdk_client(self):
        """使用阿里云 V2 SDK 创建线程安全的 SendSms 客户端。"""
        from alibabacloud_dysmsapi20170525.client import (
            Client as Dysmsapi20170525Client,
        )
        from alibabacloud_tea_openapi import models as open_api_models

        config = open_api_models.Config(
            access_key_id=self.access_key_id,
            access_key_secret=self.access_key_secret,
            region_id=self.region_id,
        )
        config.endpoint = self.endpoint
        return Dysmsapi20170525Client(config)

    @staticmethod
    def _load_request_factory():
        from alibabacloud_dysmsapi20170525 import (
            models as dysmsapi_20170525_models,
        )

        return dysmsapi_20170525_models.SendSmsRequest

    @staticmethod
    def _domestic_phone(phone_number: str) -> str:
        """国内 SendSms 模板使用 11 位大陆手机号。"""
        compact = phone_number.strip().replace(" ", "").replace("-", "")
        if compact.startswith("+86"):
            compact = compact[3:]
        elif compact.startswith("0086"):
            compact = compact[4:]
        return compact

    @staticmethod
    def _masked_phone(phone_number: str) -> str:
        compact = AliyunSMSClient._domestic_phone(phone_number)
        return f"*******{compact[-4:]}" if len(compact) >= 4 else "*******"
    
    def send_sms(
        self,
        phone_number: str,
        template_code: str,
        template_param: Optional[Dict[str, str]] = None
    ) -> bool:
        """
        发送短信
        
        Args:
            phone_number: 手机号码
            template_code: 短信模板CODE
            template_param: 模板参数
            
        Returns:
            发送是否成功
        """
        try:
            request = self.request_factory(
                phone_numbers=self._domestic_phone(phone_number),
                sign_name=self.sign_name,
                template_code=template_code,
                template_param=json.dumps(template_param or {}, ensure_ascii=False),
            )
            response = self.sdk_client.send_sms(request)
            body = response.body
            response_code = getattr(body, "code", None)

            if response_code == 'OK':
                logger.info(
                    "阿里云短信发送成功: %s",
                    self._masked_phone(phone_number),
                )
                return True

            logger.error(
                "阿里云短信发送失败: code=%s request_id=%s",
                response_code,
                getattr(body, "request_id", None),
            )
            return False
        except Exception as e:
            logger.error("阿里云短信发送异常: %s", type(e).__name__)
            return False


class TencentSMSClient:
    """腾讯云短信客户端"""
    
    def __init__(self, config: Dict[str, Any]):
        """
        初始化腾讯云短信客户端
        
        Args:
            config: 腾讯云短信配置
                - secret_id: SecretId
                - secret_key: SecretKey
                - sdk_app_id: 短信应用ID
                - sign_name: 短信签名
                - endpoint: API端点（默认：sms.tencentcloudapi.com）
        """
        self.secret_id = config.get('secret_id')
        self.secret_key = config.get('secret_key')
        self.sdk_app_id = config.get('sdk_app_id')
        self.sign_name = config.get('sign_name')
        self.endpoint = config.get('endpoint', 'sms.tencentcloudapi.com')
        
        if not all([self.secret_id, self.secret_key, self.sdk_app_id, self.sign_name]):
            raise ValueError("腾讯云短信配置不完整")
    
    def _generate_signature(self, payload: str, timestamp: int) -> str:
        """
        生成腾讯云API签名（TC3-HMAC-SHA256）
        
        Args:
            payload: 请求体
            timestamp: 时间戳
            
        Returns:
            签名字符串
        """
        # 日期（用于凭证范围）
        date = datetime.utcfromtimestamp(timestamp).strftime('%Y-%m-%d')
        
        # 拼接规范请求串
        http_request_method = "POST"
        canonical_uri = "/"
        canonical_querystring = ""
        canonical_headers = f"content-type:application/json\nhost:{self.endpoint}\n"
        signed_headers = "content-type;host"
        hashed_request_payload = hashlib.sha256(payload.encode('utf-8')).hexdigest()
        
        canonical_request = (
            f"{http_request_method}\n"
            f"{canonical_uri}\n"
            f"{canonical_querystring}\n"
            f"{canonical_headers}\n"
            f"{signed_headers}\n"
            f"{hashed_request_payload}"
        )
        
        # 拼接待签名字符串
        algorithm = "TC3-HMAC-SHA256"
        credential_scope = f"{date}/sms/tc3_request"
        hashed_canonical_request = hashlib.sha256(canonical_request.encode('utf-8')).hexdigest()
        
        string_to_sign = (
            f"{algorithm}\n"
            f"{timestamp}\n"
            f"{credential_scope}\n"
            f"{hashed_canonical_request}"
        )
        
        # 计算签名
        def _hmac_sha256(key: bytes, msg: str) -> bytes:
            return hmac.new(key, msg.encode('utf-8'), hashlib.sha256).digest()
        
        secret_date = _hmac_sha256(f"TC3{self.secret_key}".encode('utf-8'), date)
        secret_service = _hmac_sha256(secret_date, "sms")
        secret_signing = _hmac_sha256(secret_service, "tc3_request")
        signature = hmac.new(
            secret_signing,
            string_to_sign.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        return signature
    
    def send_sms(
        self,
        phone_number: str,
        template_id: str,
        template_param: Optional[list] = None
    ) -> bool:
        """
        发送短信
        
        Args:
            phone_number: 手机号码（需要包含国家码，如+86）
            template_id: 短信模板ID
            template_param: 模板参数列表
            
        Returns:
            发送是否成功
        """
        try:
            # 确保手机号包含国家码
            if not phone_number.startswith('+'):
                phone_number = f"+86{phone_number}"
            
            # 构造请求体
            timestamp = int(time.time())
            payload = {
                "PhoneNumberSet": [phone_number],
                "SmsSdkAppId": self.sdk_app_id,
                "SignName": self.sign_name,
                "TemplateId": template_id,
                "TemplateParamSet": template_param or []
            }
            
            payload_str = json.dumps(payload)
            
            # 生成签名
            signature = self._generate_signature(payload_str, timestamp)
            
            # 构造请求头
            date = datetime.utcfromtimestamp(timestamp).strftime('%Y-%m-%d')
            authorization = (
                f"TC3-HMAC-SHA256 "
                f"Credential={self.secret_id}/{date}/sms/tc3_request, "
                f"SignedHeaders=content-type;host, "
                f"Signature={signature}"
            )
            
            headers = {
                "Authorization": authorization,
                "Content-Type": "application/json",
                "Host": self.endpoint,
                "X-TC-Action": "SendSms",
                "X-TC-Version": "2021-01-11",
                "X-TC-Timestamp": str(timestamp),
                "X-TC-Region": "ap-guangzhou"
            }
            
            # 发送请求
            url = f"https://{self.endpoint}/"
            
            with httpx.Client(timeout=30.0) as client:
                response = client.post(url, headers=headers, content=payload_str)
                response.raise_for_status()
                
                result = response.json()
                
                # 检查响应
                if 'Response' in result:
                    response_data = result['Response']
                    if 'Error' in response_data:
                        logger.error(f"腾讯云短信发送失败: {response_data['Error']}")
                        return False
                    else:
                        logger.info(f"腾讯云短信发送成功: {phone_number}")
                        return True
                else:
                    logger.error(f"腾讯云短信响应格式异常: {result}")
                    return False
                    
        except httpx.HTTPError as e:
            logger.error(f"腾讯云短信API请求失败: {e}")
            return False
        except Exception as e:
            logger.error(f"腾讯云短信发送异常: {e}")
            return False


class SMSService:
    """短信发送服务"""
    
    def __init__(self):
        """初始化短信服务"""
        self.sms_config = None
        self.sms_client = None
        self.load_sms_config()

    @staticmethod
    def _environment_config() -> Optional[tuple[str, Dict[str, Any]]]:
        """从部署环境加载短信配置，避免把 AccessKey 存入源码或数据库。"""
        provider = os.getenv("SMS_PROVIDER", "").strip().lower()
        if provider != "aliyun":
            return None

        config = {
            "access_key_id": os.getenv("ALIBABA_CLOUD_ACCESS_KEY_ID", "").strip(),
            "access_key_secret": os.getenv(
                "ALIBABA_CLOUD_ACCESS_KEY_SECRET", ""
            ).strip(),
            "sign_name": os.getenv("ALIYUN_SMS_SIGN_NAME", "").strip(),
            "template_code": os.getenv("ALIYUN_SMS_TEMPLATE_CODE", "").strip(),
            "region_id": os.getenv("ALIYUN_SMS_REGION_ID", "cn-qingdao").strip(),
            "endpoint": os.getenv(
                "ALIYUN_SMS_ENDPOINT", "dysmsapi.aliyuncs.com"
            ).strip(),
        }
        if not all(
            config[key]
            for key in ("access_key_id", "access_key_secret", "sign_name")
        ):
            logger.error("阿里云短信环境变量配置不完整")
            return None
        return provider, config

    def _configure_client(self, provider: str, config: Dict[str, Any]) -> bool:
        self.sms_config = config
        if provider == 'aliyun':
            self.sms_client = AliyunSMSClient(config)
            logger.info("成功加载阿里云短信配置")
        elif provider == 'tencent':
            self.sms_client = TencentSMSClient(config)
            logger.info("成功加载腾讯云短信配置")
        else:
            logger.error("不支持的短信服务提供商: %s", provider)
            return False
        return True
    
    def load_sms_config(self) -> bool:
        """
        从数据库加载短信配置
        
        Returns:
            是否成功加载配置
        """
        try:
            db = next(get_db())
            try:
                # 查询活跃的短信服务配置
                config = db.query(CloudServiceConfig).filter(
                    CloudServiceConfig.service_type == 'sms',
                    CloudServiceConfig.is_active == True
                ).first()
                
                if config:
                    return self._configure_client(
                        config.provider.lower(), config.config
                    )
            finally:
                db.close()
        except Exception as e:
            logger.warning("数据库短信配置不可用: %s", type(e).__name__)

        environment_config = self._environment_config()
        if environment_config:
            provider, config = environment_config
            return self._configure_client(provider, config)

        logger.warning("未找到活跃的短信服务配置")
        return False
    
    def get_template(self, template_name: str, db: Session) -> Optional[MessageTemplate]:
        """
        从数据库获取短信模板
        
        Args:
            template_name: 模板名称
            db: 数据库会话
            
        Returns:
            短信模板对象，如果不存在则返回None
        """
        try:
            template = db.query(MessageTemplate).filter(
                MessageTemplate.name == template_name,
                MessageTemplate.type == 'sms'
            ).first()
            return template
        except Exception as e:
            logger.error(f"获取短信模板失败: {e}")
            return None
    
    def render_template(self, template_content: str, variables: Dict[str, Any]) -> str:
        """
        渲染短信模板
        
        Args:
            template_content: 模板内容
            variables: 模板变量
            
        Returns:
            渲染后的内容
            
        Raises:
            TemplateError: 模板渲染失败
        """
        try:
            template = Template(template_content)
            return template.render(**variables)
        except TemplateError as e:
            logger.error(f"模板渲染失败: {e}")
            raise
    
    def send_sms(
        self,
        to_phone: str,
        content: str,
        template_name: Optional[str] = None,
        template_variables: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        发送短信
        
        Args:
            to_phone: 收件人手机号
            content: 短信内容（如果使用模板，此参数可为空）
            template_name: 可选的模板名称
            template_variables: 模板变量
            
        Returns:
            发送是否成功
        """
        # 如果没有配置，尝试重新加载
        if not self.sms_client:
            if not self.load_sms_config():
                logger.error("无法发送短信：未配置短信服务")
                return False
        
        try:
            # 如果指定了模板，使用模板渲染
            rendered_content = content
            template_code = None
            template_id = None
            
            if template_name:
                db = next(get_db())
                try:
                    template = self.get_template(template_name, db)
                    if template:
                        # 渲染模板内容
                        rendered_content = self.render_template(
                            template.content,
                            template_variables or {}
                        )
                        
                        # 获取云服务模板ID（如果有）
                        if template.variables:
                            template_code = template.variables.get('template_code')
                            template_id = template.variables.get('template_id')
                        
                        logger.info(f"使用模板 '{template_name}' 渲染短信")
                    else:
                        logger.warning(f"模板 '{template_name}' 不存在，使用原始内容")
                finally:
                    db.close()
            
            # 根据不同的云服务提供商发送短信
            if isinstance(self.sms_client, AliyunSMSClient):
                # 阿里云需要模板CODE
                if not template_code and self.sms_config:
                    template_code = self.sms_config.get('template_code')
                if not template_code:
                    logger.error("阿里云短信需要模板CODE")
                    return False
                
                # 将模板变量转换为阿里云格式
                template_param = template_variables or {}
                
                return self.sms_client.send_sms(
                    phone_number=to_phone,
                    template_code=template_code,
                    template_param=template_param
                )
                
            elif isinstance(self.sms_client, TencentSMSClient):
                # 腾讯云需要模板ID
                if not template_id:
                    logger.error("腾讯云短信需要模板ID")
                    return False
                
                # 将模板变量转换为腾讯云格式（数组）
                template_param = []
                if template_variables:
                    # 按照模板中的顺序提取参数值
                    template_param = list(template_variables.values())
                
                return self.sms_client.send_sms(
                    phone_number=to_phone,
                    template_id=template_id,
                    template_param=template_param
                )
            else:
                logger.error("未知的短信服务提供商")
                return False
                
        except TemplateError as e:
            logger.error(f"模板渲染错误: {e}")
            return False
        except Exception as e:
            logger.error(f"短信发送失败: {e}")
            return False
    
    def send_verification_sms(self, to_phone: str, verification_code: str) -> bool:
        """
        发送验证短信
        
        Args:
            to_phone: 收件人手机号
            verification_code: 验证码
            
        Returns:
            发送是否成功
        """
        return self.send_sms(
            to_phone=to_phone,
            content="",  # 将从模板获取
            template_name="sms_verification",
            template_variables={
                'code': verification_code
            }
        )


# 全局短信服务实例
sms_service = SMSService()
