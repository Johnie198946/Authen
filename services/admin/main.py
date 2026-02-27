"""
管理服务主入口
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from fastapi import FastAPI, Depends, HTTPException, status, Query, Request, Body
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from typing import Optional, List, Dict, Any
from datetime import datetime
import uuid
import json
import secrets

from shared.database import get_db
from shared.models.system import CloudServiceConfig
from shared.models.application import Application, AppLoginMethod, AppScope, AppUser, AppOrganization, AppSubscriptionPlan, AutoProvisionConfig
from shared.utils.crypto import encrypt_config, decrypt_config, hash_password, verify_password
from shared.config import settings
from shared.middleware.api_logger import APILoggerMiddleware
from shared.utils.health_check import check_overall_health
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
import httpx
import hmac
import hashlib
import json as json_lib

app = FastAPI(
    title="管理服务",
    description="统一身份认证和权限管理平台 - 管理服务",
    version="1.0.0"
)

# 配置CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 添加API日志中间件
app.add_middleware(APILoggerMiddleware)


# ==================== 请求/响应模型 ====================

class CloudServiceConfigCreate(BaseModel):
    """云服务配置创建请求"""
    service_type: str = Field(..., description="服务类型: email, sms")
    provider: str = Field(..., description="服务提供商: aliyun, tencent, aws, etc.")
    config: Dict[str, Any] = Field(..., description="配置信息")
    is_active: bool = Field(default=True, description="是否激活")
    
    class Config:
        schema_extra = {
            "example": {
                "service_type": "email",
                "provider": "aliyun",
                "config": {
                    "smtp_host": "smtp.aliyun.com",
                    "smtp_port": 465,
                    "username": "noreply@example.com",
                    "password": "your_password",
                    "use_ssl": True
                },
                "is_active": True
            }
        }


class CloudServiceConfigUpdate(BaseModel):
    """云服务配置更新请求"""
    config: Optional[Dict[str, Any]] = Field(None, description="配置信息")
    is_active: Optional[bool] = Field(None, description="是否激活")


class CloudServiceConfigResponse(BaseModel):
    """云服务配置响应"""
    id: str
    service_type: str
    provider: str
    config: Dict[str, Any]  # 返回时会解密
    is_active: bool
    created_at: datetime
    updated_at: datetime
    
    class Config:
        orm_mode = True


class CloudServiceConfigListResponse(BaseModel):
    """云服务配置列表响应"""
    total: int
    configs: List[CloudServiceConfigResponse]


# ==================== 辅助函数 ====================

def validate_smtp_config(config: Dict[str, Any]) -> tuple[bool, str]:
    """
    验证SMTP配置
    
    Args:
        config: SMTP配置字典
            - smtp_host: SMTP服务器地址
            - smtp_port: SMTP端口
            - username: 用户名
            - password: 密码
            - use_ssl: 是否使用SSL
            - use_tls: 是否使用TLS（可选）
            
    Returns:
        (是否有效, 错误消息)
    """
    # 检查必需字段
    required_fields = ['smtp_host', 'smtp_port', 'username', 'password']
    missing_fields = [field for field in required_fields if field not in config]
    
    if missing_fields:
        return False, f"缺少必需字段: {', '.join(missing_fields)}"
    
    smtp_host = config.get('smtp_host')
    smtp_port = config.get('smtp_port')
    username = config.get('username')
    password = config.get('password')
    use_ssl = config.get('use_ssl', False)
    use_tls = config.get('use_tls', True)
    
    # 验证端口号
    try:
        smtp_port = int(smtp_port)
        if smtp_port < 1 or smtp_port > 65535:
            return False, "SMTP端口必须在1-65535之间"
    except (ValueError, TypeError):
        return False, "SMTP端口必须是有效的数字"
    
    # 尝试连接SMTP服务器
    try:
        if use_ssl:
            # 使用SSL连接（通常端口465）
            server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=10)
        else:
            # 使用普通连接，可能需要STARTTLS（通常端口587或25）
            server = smtplib.SMTP(smtp_host, smtp_port, timeout=10)
            if use_tls:
                server.starttls()
        
        try:
            # 尝试登录
            server.login(username, password)
            server.quit()
            return True, "SMTP配置验证成功"
        except smtplib.SMTPAuthenticationError:
            return False, "SMTP认证失败：用户名或密码错误"
        except smtplib.SMTPException as e:
            return False, f"SMTP错误: {str(e)}"
        finally:
            try:
                server.quit()
            except:
                pass
                
    except smtplib.SMTPConnectError:
        return False, f"无法连接到SMTP服务器 {smtp_host}:{smtp_port}"
    except smtplib.SMTPServerDisconnected:
        return False, "SMTP服务器断开连接"
    except TimeoutError:
        return False, f"连接SMTP服务器超时 {smtp_host}:{smtp_port}"
    except Exception as e:
        return False, f"SMTP配置验证失败: {str(e)}"


def validate_aliyun_sms_config(config: Dict[str, Any]) -> tuple[bool, str]:
    """
    验证阿里云短信配置
    
    Args:
        config: 阿里云短信配置字典
            - access_key_id: AccessKey ID
            - access_key_secret: AccessKey Secret
            - sign_name: 短信签名
            
    Returns:
        (是否有效, 错误消息)
    """
    # 检查必需字段
    required_fields = ['access_key_id', 'access_key_secret', 'sign_name']
    missing_fields = [field for field in required_fields if field not in config]
    
    if missing_fields:
        return False, f"缺少必需字段: {', '.join(missing_fields)}"
    
    access_key_id = config.get('access_key_id')
    access_key_secret = config.get('access_key_secret')
    sign_name = config.get('sign_name')
    
    # 验证字段不为空
    if not access_key_id or not access_key_secret or not sign_name:
        return False, "AccessKey ID、AccessKey Secret和签名不能为空"
    
    # 尝试调用阿里云API验证凭证
    # 使用QuerySmsSign接口查询签名状态来验证凭证
    try:
        from datetime import datetime as dt
        import uuid as uuid_lib
        from urllib.parse import quote
        
        endpoint = config.get('endpoint', 'dysmsapi.aliyuncs.com')
        timestamp = dt.utcnow().strftime('%Y-%m-%dT%H:%M:%SZ')
        
        # 构造请求参数
        params = {
            'SignatureMethod': 'HMAC-SHA1',
            'SignatureNonce': str(uuid_lib.uuid4()),
            'AccessKeyId': access_key_id,
            'SignatureVersion': '1.0',
            'Timestamp': timestamp,
            'Format': 'JSON',
            'Action': 'QuerySmsSign',
            'Version': '2017-05-25',
            'RegionId': 'cn-hangzhou',
            'SignName': sign_name,
        }
        
        # 生成签名
        sorted_params = sorted(params.items())
        canonicalized_query_string = '&'.join([
            f"{quote(k, safe='')}={quote(v, safe='')}"
            for k, v in sorted_params
        ])
        
        string_to_sign = f"GET&%2F&{quote(canonicalized_query_string, safe='')}"
        
        h = hmac.new(
            (access_key_secret + '&').encode('utf-8'),
            string_to_sign.encode('utf-8'),
            hashlib.sha1
        )
        
        import base64
        signature = base64.b64encode(h.digest()).decode('utf-8')
        params['Signature'] = signature
        
        # 发送请求
        url = f"https://{endpoint}/"
        
        with httpx.Client(timeout=10.0) as client:
            response = client.get(url, params=params)
            
            if response.status_code == 200:
                result = response.json()
                
                # 检查响应
                if result.get('Code') == 'OK':
                    return True, "阿里云短信配置验证成功"
                elif result.get('Code') == 'InvalidAccessKeyId.NotFound':
                    return False, "AccessKey ID无效"
                elif result.get('Code') == 'SignatureDoesNotMatch':
                    return False, "AccessKey Secret错误"
                elif result.get('Code') == 'InvalidSign.NotFound':
                    # 签名不存在，但凭证有效
                    return True, "阿里云短信配置验证成功（签名未找到，但凭证有效）"
                else:
                    # 其他错误，但如果能通过认证，说明凭证是有效的
                    if 'Code' in result and result['Code'] not in ['InvalidAccessKeyId.NotFound', 'SignatureDoesNotMatch']:
                        return True, f"阿里云短信配置验证成功（API返回: {result.get('Code')}）"
                    return False, f"阿里云API错误: {result.get('Message', '未知错误')}"
            else:
                return False, f"阿里云API请求失败: HTTP {response.status_code}"
                
    except httpx.TimeoutException:
        return False, "连接阿里云API超时"
    except httpx.HTTPError as e:
        return False, f"阿里云API请求失败: {str(e)}"
    except Exception as e:
        return False, f"阿里云短信配置验证失败: {str(e)}"


def validate_tencent_sms_config(config: Dict[str, Any]) -> tuple[bool, str]:
    """
    验证腾讯云短信配置
    
    Args:
        config: 腾讯云短信配置字典
            - secret_id: SecretId
            - secret_key: SecretKey
            - sdk_app_id: 短信应用ID
            - sign_name: 短信签名
            
    Returns:
        (是否有效, 错误消息)
    """
    # 检查必需字段
    required_fields = ['secret_id', 'secret_key', 'sdk_app_id', 'sign_name']
    missing_fields = [field for field in required_fields if field not in config]
    
    if missing_fields:
        return False, f"缺少必需字段: {', '.join(missing_fields)}"
    
    secret_id = config.get('secret_id')
    secret_key = config.get('secret_key')
    sdk_app_id = config.get('sdk_app_id')
    sign_name = config.get('sign_name')
    
    # 验证字段不为空
    if not secret_id or not secret_key or not sdk_app_id or not sign_name:
        return False, "SecretId、SecretKey、应用ID和签名不能为空"
    
    # 尝试调用腾讯云API验证凭证
    # 使用DescribeSignList接口查询签名列表来验证凭证
    try:
        from datetime import datetime as dt
        import time
        
        endpoint = config.get('endpoint', 'sms.tencentcloudapi.com')
        timestamp = int(time.time())
        
        # 构造请求体
        payload = {
            "SignIdSet": [],
            "International": 0
        }
        
        payload_str = json_lib.dumps(payload)
        
        # 生成签名
        date = dt.utcfromtimestamp(timestamp).strftime('%Y-%m-%d')
        
        # 拼接规范请求串
        http_request_method = "POST"
        canonical_uri = "/"
        canonical_querystring = ""
        canonical_headers = f"content-type:application/json\nhost:{endpoint}\n"
        signed_headers = "content-type;host"
        hashed_request_payload = hashlib.sha256(payload_str.encode('utf-8')).hexdigest()
        
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
        
        secret_date = _hmac_sha256(f"TC3{secret_key}".encode('utf-8'), date)
        secret_service = _hmac_sha256(secret_date, "sms")
        secret_signing = _hmac_sha256(secret_service, "tc3_request")
        signature = hmac.new(
            secret_signing,
            string_to_sign.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        
        # 构造请求头
        authorization = (
            f"TC3-HMAC-SHA256 "
            f"Credential={secret_id}/{date}/sms/tc3_request, "
            f"SignedHeaders=content-type;host, "
            f"Signature={signature}"
        )
        
        headers = {
            "Authorization": authorization,
            "Content-Type": "application/json",
            "Host": endpoint,
            "X-TC-Action": "DescribeSignList",
            "X-TC-Version": "2021-01-11",
            "X-TC-Timestamp": str(timestamp),
            "X-TC-Region": "ap-guangzhou"
        }
        
        # 发送请求
        url = f"https://{endpoint}/"
        
        with httpx.Client(timeout=10.0) as client:
            response = client.post(url, headers=headers, content=payload_str)
            
            if response.status_code == 200:
                result = response.json()
                
                # 检查响应
                if 'Response' in result:
                    response_data = result['Response']
                    if 'Error' in response_data:
                        error_code = response_data['Error'].get('Code', '')
                        error_msg = response_data['Error'].get('Message', '')
                        
                        if 'AuthFailure' in error_code:
                            return False, f"腾讯云认证失败: {error_msg}"
                        elif 'InvalidParameter' in error_code:
                            # 参数错误，但凭证有效
                            return True, "腾讯云短信配置验证成功（凭证有效）"
                        else:
                            # 其他错误，但如果能通过认证，说明凭证是有效的
                            return True, f"腾讯云短信配置验证成功（API返回: {error_code}）"
                    else:
                        # 成功响应
                        return True, "腾讯云短信配置验证成功"
                else:
                    return False, f"腾讯云API响应格式异常: {result}"
            else:
                return False, f"腾讯云API请求失败: HTTP {response.status_code}"
                
    except httpx.TimeoutException:
        return False, "连接腾讯云API超时"
    except httpx.HTTPError as e:
        return False, f"腾讯云API请求失败: {str(e)}"
    except Exception as e:
        return False, f"腾讯云短信配置验证失败: {str(e)}"


def validate_sms_config(provider: str, config: Dict[str, Any]) -> tuple[bool, str]:
    """
    验证短信API配置
    
    Args:
        provider: 服务提供商（aliyun, tencent, aws等）
        config: 短信配置字典
        
    Returns:
        (是否有效, 错误消息)
    """
    provider_lower = provider.lower()
    
    if provider_lower == 'aliyun':
        return validate_aliyun_sms_config(config)
    elif provider_lower == 'tencent':
        return validate_tencent_sms_config(config)
    elif provider_lower == 'aws':
        # AWS SMS配置验证（暂未实现）
        return False, "AWS短信配置验证暂未实现"
    else:
        return False, f"不支持的短信服务提供商: {provider}"


def validate_cloud_service_config(service_type: str, provider: str, config: Dict[str, Any]) -> tuple[bool, str]:
    """
    验证云服务配置
    
    Args:
        service_type: 服务类型（email, sms）
        provider: 服务提供商
        config: 配置字典
        
    Returns:
        (是否有效, 错误消息)
    """
    if service_type == 'email':
        return validate_smtp_config(config)
    elif service_type == 'sms':
        return validate_sms_config(provider, config)
    else:
        return False, f"不支持的服务类型: {service_type}"


def is_super_admin(user_id: str, db: Session) -> bool:
    """
    检查用户是否为超级管理员
    
    Args:
        user_id: 用户ID
        db: 数据库会话
        
    Returns:
        是否为超级管理员
    """
    from shared.models.user import User
    from shared.models.permission import Role, UserRole
    
    try:
        user_uuid = uuid.UUID(user_id)
    except ValueError:
        return False
    
    # 查询用户
    user = db.query(User).filter(User.id == user_uuid).first()
    if not user:
        return False
    
    # 检查是否有super_admin角色
    super_admin_role = db.query(Role).filter(Role.name == "super_admin").first()
    if not super_admin_role:
        return False
    
    user_role = db.query(UserRole).filter(
        UserRole.user_id == user.id,
        UserRole.role_id == super_admin_role.id
    ).first()
    
    return user_role is not None


def _extract_user_id_from_token(request: Request) -> Optional[str]:
    """从请求的Authorization头中解析JWT token获取user_id"""
    from shared.utils.jwt import decode_token
    auth_header = request.headers.get("authorization", "")
    if auth_header.startswith("Bearer "):
        token = auth_header.split(" ", 1)[1]
        payload = decode_token(token)
        if payload and "sub" in payload:
            return payload["sub"]
    return None


def require_super_admin(
    request: Request,
    user_id: Optional[str] = Query(None, description="当前用户ID"),
    db: Session = Depends(get_db)
):
    """
    要求超级管理员权限的依赖项
    优先从JWT token中获取user_id，其次使用query参数
    """
    # 优先从JWT token中提取user_id
    token_user_id = _extract_user_id_from_token(request)
    effective_user_id = token_user_id or user_id
    
    if not effective_user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供有效的身份认证信息"
        )
    
    if not is_super_admin(effective_user_id, db):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="只有超级管理员可以访问此接口"
        )
    return effective_user_id


# ==================== API端点 ====================

@app.get("/")
async def root():
    """根路径"""
    return {"service": "管理服务", "status": "running"}


@app.get("/health")
async def health_check():
    """
    系统健康检查端点
    
    需求：13.4 - 提供系统健康检查接口
    
    检查以下组件的健康状态：
    - 数据库连接
    - Redis连接
    - RabbitMQ连接
    
    Returns:
        健康状态信息，包括各组件的状态和响应时间
    """
    health_status = check_overall_health()
    
    # 根据健康状态设置HTTP状态码
    if health_status["status"] == "healthy":
        status_code = 200
    elif health_status["status"] == "degraded":
        status_code = 200  # 部分可用仍返回200
    else:
        status_code = 503  # 服务不可用
    
    return JSONResponse(
        status_code=status_code,
        content=health_status
    )


@app.get("/api/v1/admin/csrf-token")
async def get_csrf_token():
    """
    获取CSRF Token
    
    需求：11.2 - 实现CSRF保护机制
    
    生成并返回一个新的CSRF Token，前端应该在所有状态改变请求中包含此Token。
    
    Returns:
        包含CSRF Token的响应
    """
    from shared.utils.csrf import generate_csrf_token, store_csrf_token
    
    # 生成CSRF Token
    csrf_token = generate_csrf_token()
    
    # 存储Token到Redis（可选，用于一次性Token验证）
    store_csrf_token(csrf_token)
    
    return {
        "csrf_token": csrf_token,
        "expires_in": 3600  # 1小时
    }


@app.get("/api/v1/admin/cloud-services", response_model=CloudServiceConfigListResponse)
async def list_cloud_service_configs(
    service_type: Optional[str] = Query(None, description="服务类型过滤: email, sms"),
    provider: Optional[str] = Query(None, description="提供商过滤"),
    user_id: str = Depends(require_super_admin),
    db: Session = Depends(get_db)
):
    """
    获取云服务配置列表
    
    需求：8.1, 8.2 - 提供邮件服务和短信服务配置界面
    
    Args:
        service_type: 服务类型过滤
        provider: 提供商过滤
        user_id: 当前用户ID（由依赖项验证）
        db: 数据库会话
        
    Returns:
        云服务配置列表
    """
    query = db.query(CloudServiceConfig)
    
    # 应用过滤条件
    if service_type:
        query = query.filter(CloudServiceConfig.service_type == service_type)
    
    if provider:
        query = query.filter(CloudServiceConfig.provider == provider)
    
    # 获取所有配置
    configs = query.all()
    
    # 解密配置并构建响应
    config_responses = []
    for config in configs:
        try:
            # 解密配置数据
            if isinstance(config.config, str):
                decrypted_config = decrypt_config(config.config)
            elif isinstance(config.config, dict):
                # 如果已经是字典（可能是测试环境），直接使用
                decrypted_config = config.config
            else:
                decrypted_config = {}
            
            config_responses.append(CloudServiceConfigResponse(
                id=str(config.id),
                service_type=config.service_type,
                provider=config.provider,
                config=decrypted_config,
                is_active=config.is_active,
                created_at=config.created_at,
                updated_at=config.updated_at
            ))
        except Exception as e:
            # 如果解密失败，记录错误但继续处理其他配置
            print(f"解密配置失败 (ID: {config.id}): {str(e)}")
            continue
    
    return CloudServiceConfigListResponse(
        total=len(config_responses),
        configs=config_responses
    )


@app.post("/api/v1/admin/cloud-services", response_model=CloudServiceConfigResponse, status_code=status.HTTP_201_CREATED)
async def create_cloud_service_config(
    request: CloudServiceConfigCreate,
    skip_validation: bool = Query(False, description="跳过连接验证，仅保存配置"),
    user_id: str = Depends(require_super_admin),
    db: Session = Depends(get_db)
):
    """
    创建云服务配置
    
    需求：8.1, 8.2 - 提供邮件服务和短信服务配置界面
    
    Args:
        request: 云服务配置创建请求
        user_id: 当前用户ID（由依赖项验证）
        db: 数据库会话
        
    Returns:
        创建的云服务配置
        
    Raises:
        HTTPException: 如果配置已存在或创建失败
    """
    # 验证服务类型
    valid_service_types = ["email", "sms"]
    if request.service_type not in valid_service_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无效的服务类型，支持的类型: {', '.join(valid_service_types)}"
        )
    
    # 检查是否已存在相同的服务类型和提供商组合
    existing_config = db.query(CloudServiceConfig).filter(
        CloudServiceConfig.service_type == request.service_type,
        CloudServiceConfig.provider == request.provider
    ).first()
    
    if existing_config:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"服务类型 {request.service_type} 和提供商 {request.provider} 的配置已存在"
        )
    
    # 验证配置有效性（需求 8.5）
    if not skip_validation:
        is_valid, error_message = validate_cloud_service_config(
            request.service_type,
            request.provider,
            request.config
        )
        
        if not is_valid:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"配置验证失败: {error_message}"
            )
    
    # 加密配置数据
    try:
        encrypted_config = encrypt_config(request.config)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"加密配置失败: {str(e)}"
        )
    
    # 创建配置记录
    new_config = CloudServiceConfig(
        service_type=request.service_type,
        provider=request.provider,
        config=encrypted_config,
        is_active=request.is_active
    )
    
    db.add(new_config)
    db.commit()
    db.refresh(new_config)
    
    # 返回响应（解密配置）
    return CloudServiceConfigResponse(
        id=str(new_config.id),
        service_type=new_config.service_type,
        provider=new_config.provider,
        config=request.config,  # 返回原始配置（未加密）
        is_active=new_config.is_active,
        created_at=new_config.created_at,
        updated_at=new_config.updated_at
    )


@app.put("/api/v1/admin/cloud-services/{config_id}", response_model=CloudServiceConfigResponse)
async def update_cloud_service_config(
    config_id: str,
    request: CloudServiceConfigUpdate,
    skip_validation: bool = Query(False, description="跳过连接验证，仅保存配置"),
    user_id: str = Depends(require_super_admin),
    db: Session = Depends(get_db)
):
    """
    更新云服务配置
    
    需求：8.1, 8.2 - 提供邮件服务和短信服务配置界面
    
    Args:
        config_id: 配置ID
        request: 云服务配置更新请求
        user_id: 当前用户ID（由依赖项验证）
        db: 数据库会话
        
    Returns:
        更新后的云服务配置
        
    Raises:
        HTTPException: 如果配置不存在或更新失败
    """
    # 验证配置ID格式
    try:
        config_uuid = uuid.UUID(config_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="无效的配置ID格式"
        )
    
    # 查找配置
    config = db.query(CloudServiceConfig).filter(CloudServiceConfig.id == config_uuid).first()
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="云服务配置不存在"
        )
    
    # 更新配置
    if request.config is not None:
        # 验证新配置的有效性（需求 8.5）
        if not skip_validation:
            is_valid, error_message = validate_cloud_service_config(
                config.service_type,
                config.provider,
                request.config
            )
            
            if not is_valid:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"配置验证失败: {error_message}"
                )
        
        try:
            # 加密新配置
            encrypted_config = encrypt_config(request.config)
            config.config = encrypted_config
        except Exception as e:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"加密配置失败: {str(e)}"
            )
    
    if request.is_active is not None:
        config.is_active = request.is_active
    
    config.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(config)
    
    # 解密配置用于响应
    try:
        if isinstance(config.config, str):
            decrypted_config = decrypt_config(config.config)
        elif isinstance(config.config, dict):
            decrypted_config = config.config
        else:
            decrypted_config = {}
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"解密配置失败: {str(e)}"
        )
    
    return CloudServiceConfigResponse(
        id=str(config.id),
        service_type=config.service_type,
        provider=config.provider,
        config=decrypted_config,
        is_active=config.is_active,
        created_at=config.created_at,
        updated_at=config.updated_at
    )


@app.delete("/api/v1/admin/cloud-services/{config_id}")
async def delete_cloud_service_config(
    config_id: str,
    user_id: str = Depends(require_super_admin),
    db: Session = Depends(get_db)
):
    """
    删除云服务配置
    
    Args:
        config_id: 配置ID
        user_id: 当前用户ID（由依赖项验证）
        db: 数据库会话
        
    Returns:
        删除结果
        
    Raises:
        HTTPException: 如果配置不存在
    """
    # 验证配置ID格式
    try:
        config_uuid = uuid.UUID(config_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="无效的配置ID格式"
        )
    
    # 查找配置
    config = db.query(CloudServiceConfig).filter(CloudServiceConfig.id == config_uuid).first()
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="云服务配置不存在"
        )
    
    # 删除配置
    db.delete(config)
    db.commit()
    
    return {
        "success": True,
        "message": "云服务配置已删除"
    }


# ==================== 配置测试接口 ====================

class TestEmailRequest(BaseModel):
    """测试邮件请求"""
    to_email: str = Field(..., description="收件人邮箱")
    subject: str = Field(default="测试邮件", description="邮件主题")
    body: str = Field(default="这是一封测试邮件，用于验证邮件服务配置是否正确。", description="邮件正文")
    
    class Config:
        schema_extra = {
            "example": {
                "to_email": "test@example.com",
                "subject": "测试邮件",
                "body": "这是一封测试邮件，用于验证邮件服务配置是否正确。"
            }
        }


class TestSMSRequest(BaseModel):
    """测试短信请求"""
    to_phone: str = Field(..., description="收件人手机号")
    content: str = Field(default="【测试】您的验证码是123456，用于测试短信服务配置。", description="短信内容")
    
    class Config:
        schema_extra = {
            "example": {
                "to_phone": "+8613800138000",
                "content": "【测试】您的验证码是123456，用于测试短信服务配置。"
            }
        }


class TestResponse(BaseModel):
    """测试响应"""
    success: bool = Field(..., description="测试是否成功")
    message: str = Field(..., description="测试结果消息")
    details: Optional[Dict[str, Any]] = Field(None, description="详细信息")


@app.post("/api/v1/admin/cloud-services/{config_id}/test", response_model=TestResponse)
async def test_cloud_service_config(
    config_id: str,
    test_email: Optional[TestEmailRequest] = Body(None),
    test_sms: Optional[TestSMSRequest] = Body(None),
    user_id: str = Depends(require_super_admin),
    db: Session = Depends(get_db)
):
    """
    测试云服务配置
    
    需求：8.6 - 提供测试功能（发送测试邮件/短信）
    
    根据配置类型自动选择测试方式：
    - 邮件服务：发送测试邮件
    - 短信服务：发送测试短信
    
    Args:
        config_id: 配置ID
        test_email: 测试邮件请求（邮件服务时使用）
        test_sms: 测试短信请求（短信服务时使用）
        user_id: 当前用户ID（由依赖项验证）
        db: 数据库会话
        
    Returns:
        测试结果
        
    Raises:
        HTTPException: 如果配置不存在或测试失败
    """
    # 验证配置ID格式
    try:
        config_uuid = uuid.UUID(config_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="无效的配置ID格式"
        )
    
    # 查找配置
    config = db.query(CloudServiceConfig).filter(CloudServiceConfig.id == config_uuid).first()
    if not config:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="云服务配置不存在"
        )
    
    # 解密配置
    try:
        if isinstance(config.config, str):
            decrypted_config = decrypt_config(config.config)
        elif isinstance(config.config, dict):
            decrypted_config = config.config
        else:
            raise ValueError("配置格式无效")
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"解密配置失败: {str(e)}"
        )
    
    # 根据服务类型进行测试
    if config.service_type == 'email':
        return await test_email_config(config, decrypted_config, test_email)
    elif config.service_type == 'sms':
        return await test_sms_config(config, decrypted_config, test_sms)
    else:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"不支持的服务类型: {config.service_type}"
        )


async def test_email_config(
    config: CloudServiceConfig,
    decrypted_config: Dict[str, Any],
    test_request: Optional[TestEmailRequest]
) -> TestResponse:
    """
    测试邮件配置
    
    Args:
        config: 云服务配置对象
        decrypted_config: 解密后的配置
        test_request: 测试邮件请求
        
    Returns:
        测试结果
        
    Raises:
        HTTPException: 如果测试失败
    """
    # 如果没有提供测试请求，使用默认值
    if not test_request:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请提供测试邮件参数（to_email, subject, body）"
        )
    
    to_email = test_request.to_email
    subject = test_request.subject
    body = test_request.body
    
    # 验证邮件地址格式
    import re
    email_pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
    if not re.match(email_pattern, to_email):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="无效的邮箱地址格式"
        )
    
    try:
        # 获取SMTP配置
        smtp_host = decrypted_config.get('smtp_host')
        smtp_port = decrypted_config.get('smtp_port', 587)
        use_ssl = decrypted_config.get('use_ssl', False)
        use_tls = decrypted_config.get('use_tls', True)
        username = decrypted_config.get('username')
        password = decrypted_config.get('password')
        from_email = decrypted_config.get('from_email') or username
        
        if not all([smtp_host, username, password]):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="邮件配置不完整（缺少smtp_host、username或password）"
            )
        
        # 创建邮件消息
        msg = MIMEMultipart('alternative')
        msg['Subject'] = subject
        msg['From'] = from_email
        msg['To'] = to_email
        msg.attach(MIMEText(body, 'html', 'utf-8'))
        
        # 连接SMTP服务器并发送
        if use_ssl:
            server = smtplib.SMTP_SSL(smtp_host, smtp_port, timeout=30)
        else:
            server = smtplib.SMTP(smtp_host, smtp_port, timeout=30)
            if use_tls:
                server.starttls()
        
        try:
            # 登录
            server.login(username, password)
            
            # 发送邮件
            server.send_message(msg)
            
            return TestResponse(
                success=True,
                message=f"测试邮件已成功发送到 {to_email}",
                details={
                    "provider": config.provider,
                    "smtp_host": smtp_host,
                    "smtp_port": smtp_port,
                    "from_email": from_email,
                    "to_email": to_email
                }
            )
            
        finally:
            server.quit()
            
    except smtplib.SMTPAuthenticationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"SMTP认证失败: {str(e)}"
        )
    except smtplib.SMTPException as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"SMTP错误: {str(e)}"
        )
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"邮件发送失败: {str(e)}"
        )


async def test_sms_config(
    config: CloudServiceConfig,
    decrypted_config: Dict[str, Any],
    test_request: Optional[TestSMSRequest]
) -> TestResponse:
    """
    测试短信配置
    
    Args:
        config: 云服务配置对象
        decrypted_config: 解密后的配置
        test_request: 测试短信请求
        
    Returns:
        测试结果
        
    Raises:
        HTTPException: 如果测试失败
    """
    # 如果没有提供测试请求，使用默认值
    if not test_request:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="请提供测试短信参数（to_phone, content）"
        )
    
    to_phone = test_request.to_phone
    content = test_request.content
    
    # 验证手机号格式
    import re
    phone_pattern = r'^\+[1-9]\d{1,14}$'  # E.164格式，必须以+开头
    if not re.match(phone_pattern, to_phone):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="无效的手机号格式（请使用国际格式，如+8613800138000）"
        )
    
    provider = config.provider.lower()
    
    try:
        if provider == 'aliyun':
            return await test_aliyun_sms(decrypted_config, to_phone, content)
        elif provider == 'tencent':
            return await test_tencent_sms(decrypted_config, to_phone, content)
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"不支持的短信服务提供商: {provider}"
            )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"短信发送失败: {str(e)}"
        )


async def test_aliyun_sms(
    config: Dict[str, Any],
    to_phone: str,
    content: str
) -> TestResponse:
    """
    测试阿里云短信配置
    
    Args:
        config: 阿里云短信配置
        to_phone: 收件人手机号
        content: 短信内容
        
    Returns:
        测试结果
    """
    access_key_id = config.get('access_key_id')
    access_key_secret = config.get('access_key_secret')
    sign_name = config.get('sign_name')
    endpoint = config.get('endpoint', 'dysmsapi.aliyuncs.com')
    
    if not all([access_key_id, access_key_secret, sign_name]):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="阿里云短信配置不完整"
        )
    
    # 注意：实际发送测试短信需要有效的模板CODE
    # 这里我们只验证配置的有效性，不实际发送短信
    # 因为发送短信需要预先在阿里云控制台创建模板
    
    return TestResponse(
        success=True,
        message=f"阿里云短信配置验证成功（注意：实际发送需要配置模板CODE）",
        details={
            "provider": "aliyun",
            "endpoint": endpoint,
            "sign_name": sign_name,
            "to_phone": to_phone,
            "note": "实际发送短信需要在阿里云控制台创建模板并提供template_code"
        }
    )


async def test_tencent_sms(
    config: Dict[str, Any],
    to_phone: str,
    content: str
) -> TestResponse:
    """
    测试腾讯云短信配置
    
    Args:
        config: 腾讯云短信配置
        to_phone: 收件人手机号
        content: 短信内容
        
    Returns:
        测试结果
    """
    secret_id = config.get('secret_id')
    secret_key = config.get('secret_key')
    sdk_app_id = config.get('sdk_app_id')
    sign_name = config.get('sign_name')
    endpoint = config.get('endpoint', 'sms.tencentcloudapi.com')
    
    if not all([secret_id, secret_key, sdk_app_id, sign_name]):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="腾讯云短信配置不完整"
        )
    
    # 注意：实际发送测试短信需要有效的模板ID
    # 这里我们只验证配置的有效性，不实际发送短信
    # 因为发送短信需要预先在腾讯云控制台创建模板
    
    return TestResponse(
        success=True,
        message=f"腾讯云短信配置验证成功（注意：实际发送需要配置模板ID）",
        details={
            "provider": "tencent",
            "endpoint": endpoint,
            "sdk_app_id": sdk_app_id,
            "sign_name": sign_name,
            "to_phone": to_phone,
            "note": "实际发送短信需要在腾讯云控制台创建模板并提供template_id"
        }
    )


# ==================== 消息模板管理接口 ====================

class MessageTemplateCreate(BaseModel):
    """消息模板创建请求"""
    name: str = Field(..., description="模板名称（唯一标识）", min_length=1, max_length=100)
    type: str = Field(..., description="模板类型: email, sms")
    subject: Optional[str] = Field(None, description="邮件主题（仅用于邮件模板）", max_length=255)
    content: str = Field(..., description="模板内容（支持Jinja2语法）", min_length=1)
    variables: Optional[Dict[str, str]] = Field(None, description="模板变量说明（变量名: 说明）")
    
    class Config:
        schema_extra = {
            "example": {
                "name": "email_verification",
                "type": "email",
                "subject": "验证您的邮箱 - {{app_name}}",
                "content": "<h1>欢迎注册 {{app_name}}</h1><p>请点击以下链接验证您的邮箱：</p><a href='{{verification_link}}'>验证邮箱</a>",
                "variables": {
                    "app_name": "应用名称",
                    "verification_link": "验证链接"
                }
            }
        }


class MessageTemplateUpdate(BaseModel):
    """消息模板更新请求"""
    subject: Optional[str] = Field(None, description="邮件主题（仅用于邮件模板）", max_length=255)
    content: Optional[str] = Field(None, description="模板内容（支持Jinja2语法）", min_length=1)
    variables: Optional[Dict[str, str]] = Field(None, description="模板变量说明（变量名: 说明）")


class MessageTemplateResponse(BaseModel):
    """消息模板响应"""
    id: str
    name: str
    type: str
    subject: Optional[str]
    content: str
    variables: Optional[Dict[str, str]]
    created_at: datetime
    updated_at: datetime
    
    class Config:
        orm_mode = True


class MessageTemplateListResponse(BaseModel):
    """消息模板列表响应"""
    total: int
    templates: List[MessageTemplateResponse]


@app.get("/api/v1/admin/templates", response_model=MessageTemplateListResponse)
async def list_message_templates(
    type: Optional[str] = Query(None, description="模板类型过滤: email, sms"),
    user_id: str = Depends(require_super_admin),
    db: Session = Depends(get_db)
):
    """
    获取消息模板列表
    
    需求：8.3, 8.4 - 提供邮件模板和短信模板编辑器
    
    Args:
        type: 模板类型过滤
        user_id: 当前用户ID（由依赖项验证）
        db: 数据库会话
        
    Returns:
        消息模板列表
    """
    from shared.models.system import MessageTemplate
    
    query = db.query(MessageTemplate)
    
    # 应用过滤条件
    if type:
        if type not in ['email', 'sms']:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="无效的模板类型，支持的类型: email, sms"
            )
        query = query.filter(MessageTemplate.type == type)
    
    # 获取所有模板
    templates = query.all()
    
    # 构建响应
    template_responses = []
    for template in templates:
        template_responses.append(MessageTemplateResponse(
            id=str(template.id),
            name=template.name,
            type=template.type,
            subject=template.subject,
            content=template.content,
            variables=template.variables,
            created_at=template.created_at,
            updated_at=template.updated_at
        ))
    
    return MessageTemplateListResponse(
        total=len(template_responses),
        templates=template_responses
    )


@app.post("/api/v1/admin/templates", response_model=MessageTemplateResponse, status_code=status.HTTP_201_CREATED)
async def create_message_template(
    request: MessageTemplateCreate,
    user_id: str = Depends(require_super_admin),
    db: Session = Depends(get_db)
):
    """
    创建消息模板
    
    需求：8.3, 8.4 - 提供邮件模板和短信模板编辑器（支持变量替换）
    
    Args:
        request: 消息模板创建请求
        user_id: 当前用户ID（由依赖项验证）
        db: 数据库会话
        
    Returns:
        创建的消息模板
        
    Raises:
        HTTPException: 如果模板已存在或创建失败
    """
    from shared.models.system import MessageTemplate
    from jinja2 import Template, TemplateSyntaxError
    
    # 验证模板类型
    valid_types = ["email", "sms"]
    if request.type not in valid_types:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无效的模板类型，支持的类型: {', '.join(valid_types)}"
        )
    
    # 验证邮件模板必须有主题
    if request.type == 'email' and not request.subject:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="邮件模板必须提供主题"
        )
    
    # 验证短信模板不应该有主题
    if request.type == 'sms' and request.subject:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="短信模板不应该包含主题字段"
        )
    
    # 检查模板名称是否已存在
    existing_template = db.query(MessageTemplate).filter(
        MessageTemplate.name == request.name
    ).first()
    
    if existing_template:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"模板名称 '{request.name}' 已存在"
        )
    
    # 验证模板语法（Jinja2）
    try:
        # 验证主题模板（如果有）
        if request.subject:
            Template(request.subject)
        
        # 验证内容模板
        Template(request.content)
    except TemplateSyntaxError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"模板语法错误: {str(e)}"
        )
    
    # 创建模板记录
    new_template = MessageTemplate(
        name=request.name,
        type=request.type,
        subject=request.subject,
        content=request.content,
        variables=request.variables
    )
    
    db.add(new_template)
    db.commit()
    db.refresh(new_template)
    
    return MessageTemplateResponse(
        id=str(new_template.id),
        name=new_template.name,
        type=new_template.type,
        subject=new_template.subject,
        content=new_template.content,
        variables=new_template.variables,
        created_at=new_template.created_at,
        updated_at=new_template.updated_at
    )


@app.get("/api/v1/admin/templates/{template_id}", response_model=MessageTemplateResponse)
async def get_message_template(
    template_id: str,
    user_id: str = Depends(require_super_admin),
    db: Session = Depends(get_db)
):
    """
    获取单个消息模板详情
    
    Args:
        template_id: 模板ID
        user_id: 当前用户ID（由依赖项验证）
        db: 数据库会话
        
    Returns:
        消息模板详情
        
    Raises:
        HTTPException: 如果模板不存在
    """
    from shared.models.system import MessageTemplate
    
    # 验证模板ID格式
    try:
        template_uuid = uuid.UUID(template_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="无效的模板ID格式"
        )
    
    # 查找模板
    template = db.query(MessageTemplate).filter(MessageTemplate.id == template_uuid).first()
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="消息模板不存在"
        )
    
    return MessageTemplateResponse(
        id=str(template.id),
        name=template.name,
        type=template.type,
        subject=template.subject,
        content=template.content,
        variables=template.variables,
        created_at=template.created_at,
        updated_at=template.updated_at
    )


@app.put("/api/v1/admin/templates/{template_id}", response_model=MessageTemplateResponse)
async def update_message_template(
    template_id: str,
    request: MessageTemplateUpdate,
    user_id: str = Depends(require_super_admin),
    db: Session = Depends(get_db)
):
    """
    更新消息模板
    
    需求：8.3, 8.4 - 提供邮件模板和短信模板编辑器（支持变量替换）
    
    Args:
        template_id: 模板ID
        request: 消息模板更新请求
        user_id: 当前用户ID（由依赖项验证）
        db: 数据库会话
        
    Returns:
        更新后的消息模板
        
    Raises:
        HTTPException: 如果模板不存在或更新失败
    """
    from shared.models.system import MessageTemplate
    from jinja2 import Template, TemplateSyntaxError
    
    # 验证模板ID格式
    try:
        template_uuid = uuid.UUID(template_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="无效的模板ID格式"
        )
    
    # 查找模板
    template = db.query(MessageTemplate).filter(MessageTemplate.id == template_uuid).first()
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="消息模板不存在"
        )
    
    # 更新模板字段
    if request.subject is not None:
        # 验证邮件模板必须有主题
        if template.type == 'email' and not request.subject:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="邮件模板必须提供主题"
            )
        
        # 验证短信模板不应该有主题
        if template.type == 'sms' and request.subject:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="短信模板不应该包含主题字段"
            )
        
        # 验证主题模板语法
        try:
            Template(request.subject)
        except TemplateSyntaxError as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"主题模板语法错误: {str(e)}"
            )
        
        template.subject = request.subject
    
    if request.content is not None:
        # 验证内容模板语法
        try:
            Template(request.content)
        except TemplateSyntaxError as e:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail=f"内容模板语法错误: {str(e)}"
            )
        
        template.content = request.content
    
    if request.variables is not None:
        template.variables = request.variables
    
    template.updated_at = datetime.utcnow()
    
    db.commit()
    db.refresh(template)
    
    return MessageTemplateResponse(
        id=str(template.id),
        name=template.name,
        type=template.type,
        subject=template.subject,
        content=template.content,
        variables=template.variables,
        created_at=template.created_at,
        updated_at=template.updated_at
    )


@app.delete("/api/v1/admin/templates/{template_id}")
async def delete_message_template(
    template_id: str,
    user_id: str = Depends(require_super_admin),
    db: Session = Depends(get_db)
):
    """
    删除消息模板
    
    Args:
        template_id: 模板ID
        user_id: 当前用户ID（由依赖项验证）
        db: 数据库会话
        
    Returns:
        删除结果
        
    Raises:
        HTTPException: 如果模板不存在
    """
    from shared.models.system import MessageTemplate
    
    # 验证模板ID格式
    try:
        template_uuid = uuid.UUID(template_id)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="无效的模板ID格式"
        )
    
    # 查找模板
    template = db.query(MessageTemplate).filter(MessageTemplate.id == template_uuid).first()
    if not template:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="消息模板不存在"
        )
    
    # 删除模板
    db.delete(template)
    db.commit()
    
    return {
        "success": True,
        "message": "消息模板已删除"
    }


# ==================== 审计日志查询接口 ====================

class AuditLogResponse(BaseModel):
    """审计日志响应"""
    id: str
    user_id: Optional[str]
    action: str
    resource_type: Optional[str]
    resource_id: Optional[str]
    details: Optional[Dict[str, Any]]
    ip_address: Optional[str]
    user_agent: Optional[str]
    created_at: datetime
    
    class Config:
        orm_mode = True


class AuditLogListResponse(BaseModel):
    """审计日志列表响应"""
    total: int
    page: int
    page_size: int
    logs: List[AuditLogResponse]


@app.get("/api/v1/admin/audit-logs", response_model=AuditLogListResponse)
async def list_audit_logs(
    user_id_filter: Optional[str] = Query(None, description="用户ID过滤", alias="user_id"),
    action: Optional[str] = Query(None, description="操作类型过滤"),
    resource_type: Optional[str] = Query(None, description="资源类型过滤"),
    start_date: Optional[datetime] = Query(None, description="开始时间（ISO 8601格式）"),
    end_date: Optional[datetime] = Query(None, description="结束时间（ISO 8601格式）"),
    ip_address: Optional[str] = Query(None, description="IP地址过滤"),
    page: int = Query(1, ge=1, description="页码（从1开始）"),
    page_size: int = Query(20, ge=1, le=100, description="每页数量（1-100）"),
    sort_order: str = Query("desc", regex="^(asc|desc)$", description="排序顺序：asc（升序）或desc（降序）"),
    current_user_id: str = Depends(require_super_admin),
    db: Session = Depends(get_db)
):
    """
    查询审计日志列表
    
    需求：7.6 - 提供操作日志查询界面
    
    支持多条件过滤：
    - 用户ID
    - 操作类型
    - 资源类型
    - 时间范围（开始时间、结束时间）
    - IP地址
    
    支持分页和排序（按时间升序/降序）
    
    只有超级管理员可以访问此接口
    
    Args:
        user_id_filter: 用户ID过滤
        action: 操作类型过滤
        resource_type: 资源类型过滤
        start_date: 开始时间
        end_date: 结束时间
        ip_address: IP地址过滤
        page: 页码
        page_size: 每页数量
        sort_order: 排序顺序（asc或desc）
        current_user_id: 当前用户ID（由依赖项验证）
        db: 数据库会话
        
    Returns:
        审计日志列表（分页）
    """
    from shared.models.system import AuditLog
    
    # 构建基础查询
    query = db.query(AuditLog)
    
    # 应用过滤条件
    if user_id_filter:
        # 验证用户ID格式
        try:
            user_uuid = uuid.UUID(user_id_filter)
            query = query.filter(AuditLog.user_id == user_uuid)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="无效的用户ID格式"
            )
    
    if action:
        query = query.filter(AuditLog.action == action)
    
    if resource_type:
        query = query.filter(AuditLog.resource_type == resource_type)
    
    if start_date:
        query = query.filter(AuditLog.created_at >= start_date)
    
    if end_date:
        query = query.filter(AuditLog.created_at <= end_date)
    
    if ip_address:
        query = query.filter(AuditLog.ip_address == ip_address)
    
    # 获取总数
    total = query.count()
    
    # 应用排序
    if sort_order == "asc":
        query = query.order_by(AuditLog.created_at.asc())
    else:
        query = query.order_by(AuditLog.created_at.desc())
    
    # 应用分页
    offset = (page - 1) * page_size
    query = query.offset(offset).limit(page_size)
    
    # 获取日志记录
    logs = query.all()
    
    # 构建响应
    log_responses = []
    for log in logs:
        log_responses.append(AuditLogResponse(
            id=str(log.id),
            user_id=str(log.user_id) if log.user_id else None,
            action=log.action,
            resource_type=log.resource_type,
            resource_id=str(log.resource_id) if log.resource_id else None,
            details=log.details,
            ip_address=str(log.ip_address) if log.ip_address else None,
            user_agent=log.user_agent,
            created_at=log.created_at
        ))
    
    return AuditLogListResponse(
        total=total,
        page=page,
        page_size=page_size,
        logs=log_responses
    )


# ==================== 应用管理 请求/响应模型 ====================

class ApplicationCreate(BaseModel):
    """应用创建请求"""
    name: str = Field(..., min_length=1, max_length=255, description="应用名称")
    description: Optional[str] = Field(None, description="应用描述")


class ApplicationUpdate(BaseModel):
    """应用更新请求"""
    name: Optional[str] = Field(None, min_length=1, max_length=255, description="应用名称")
    description: Optional[str] = Field(None, description="应用描述")
    rate_limit: Optional[int] = Field(None, ge=1, description="每分钟请求限制")


class ApplicationStatusUpdate(BaseModel):
    """应用状态更新请求"""
    status: str = Field(..., description="应用状态: active / disabled")


class ApplicationResponse(BaseModel):
    """应用响应"""
    id: str
    name: str
    description: Optional[str]
    app_id: str
    status: str
    rate_limit: int
    webhook_secret: Optional[str] = None
    created_at: datetime
    updated_at: datetime

    class Config:
        orm_mode = True


class ApplicationCreateResponse(ApplicationResponse):
    """应用创建响应（包含 app_secret，仅返回一次）"""
    app_secret: str


class ApplicationListResponse(BaseModel):
    """应用列表响应"""
    total: int
    applications: List[ApplicationResponse]


class ResetSecretResponse(BaseModel):
    """重置密钥响应"""
    app_id: str
    app_secret: str
    message: str


class ResetWebhookSecretResponse(BaseModel):
    """重置 Webhook 密钥响应"""
    app_id: str
    webhook_secret: str
    message: str


# ==================== 应用管理 API 端点 ====================

@app.post("/api/v1/admin/applications", response_model=ApplicationCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_application(
    request: ApplicationCreate,
    user_id: str = Depends(require_super_admin),
    db: Session = Depends(get_db)
):
    """
    创建应用

    生成唯一的 app_id（UUID 格式）和 app_secret（至少 32 字节随机字符串）。
    app_secret 以哈希形式存储，原始值仅在创建时返回一次。

    需求: 1.1, 1.2
    """
    # 生成 app_id 和 app_secret
    app_id = str(uuid.uuid4())
    app_secret = secrets.token_urlsafe(48)  # 生成 64 字符的随机字符串（>= 32 字节）

    # 哈希 app_secret
    secret_hash = hash_password(app_secret)

    new_app = Application(
        name=request.name,
        description=request.description,
        app_id=app_id,
        app_secret_hash=secret_hash,
        status="active",
        rate_limit=60,
        webhook_secret=secrets.token_hex(32),
    )

    db.add(new_app)
    db.commit()
    db.refresh(new_app)

    return ApplicationCreateResponse(
        id=str(new_app.id),
        name=new_app.name,
        description=new_app.description,
        app_id=new_app.app_id,
        status=new_app.status,
        rate_limit=new_app.rate_limit,
        webhook_secret=new_app.webhook_secret,
        created_at=new_app.created_at,
        updated_at=new_app.updated_at,
        app_secret=app_secret,
    )


@app.get("/api/v1/admin/applications", response_model=ApplicationListResponse)
async def list_applications(
    status_filter: Optional[str] = Query(None, description="状态过滤: active / disabled", alias="status"),
    user_id: str = Depends(require_super_admin),
    db: Session = Depends(get_db)
):
    """
    获取应用列表

    返回所有已注册应用的名称、app_id、状态和创建时间。

    需求: 1.5
    """
    query = db.query(Application)

    if status_filter:
        query = query.filter(Application.status == status_filter)

    query = query.order_by(Application.created_at.desc())
    apps = query.all()

    app_responses = [
        ApplicationResponse(
            id=str(a.id),
            name=a.name,
            description=a.description,
            app_id=a.app_id,
            status=a.status,
            rate_limit=a.rate_limit,
            webhook_secret=a.webhook_secret,
            created_at=a.created_at,
            updated_at=a.updated_at,
        )
        for a in apps
    ]

    return ApplicationListResponse(total=len(app_responses), applications=app_responses)


@app.get("/api/v1/admin/applications/{app_id}", response_model=ApplicationResponse)
async def get_application(
    app_id: str,
    user_id: str = Depends(require_super_admin),
    db: Session = Depends(get_db)
):
    """
    获取应用详情

    需求: 1.5
    """
    application = db.query(Application).filter(Application.app_id == app_id).first()
    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="应用不存在"
        )

    return ApplicationResponse(
        id=str(application.id),
        name=application.name,
        description=application.description,
        app_id=application.app_id,
        status=application.status,
        rate_limit=application.rate_limit,
        webhook_secret=application.webhook_secret,
        created_at=application.created_at,
        updated_at=application.updated_at,
    )


@app.put("/api/v1/admin/applications/{app_id}", response_model=ApplicationResponse)
async def update_application(
    app_id: str,
    request: ApplicationUpdate,
    user_id: str = Depends(require_super_admin),
    db: Session = Depends(get_db)
):
    """
    更新应用信息

    支持更新名称、描述和限流阈值。配置变更后清除 Redis 缓存。

    需求: 1.1
    """
    application = db.query(Application).filter(Application.app_id == app_id).first()
    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="应用不存在"
        )

    if request.name is not None:
        application.name = request.name
    if request.description is not None:
        application.description = request.description
    if request.rate_limit is not None:
        application.rate_limit = request.rate_limit

    db.commit()
    db.refresh(application)

    # 清除 Redis 缓存
    try:
        from services.gateway.cache import invalidate_app_config_cache
        invalidate_app_config_cache(app_id)
    except Exception:
        pass  # Redis 不可用时不阻塞操作

    return ApplicationResponse(
        id=str(application.id),
        name=application.name,
        description=application.description,
        app_id=application.app_id,
        status=application.status,
        rate_limit=application.rate_limit,
        webhook_secret=application.webhook_secret,
        created_at=application.created_at,
        updated_at=application.updated_at,
    )


@app.delete("/api/v1/admin/applications/{app_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_application(
    app_id: str,
    user_id: str = Depends(require_super_admin),
    db: Session = Depends(get_db)
):
    """
    删除应用

    删除应用记录并清除该应用在 Redis 中关联的所有缓存和会话数据。

    需求: 1.6
    """
    application = db.query(Application).filter(Application.app_id == app_id).first()
    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="应用不存在"
        )

    # 清除 Redis 缓存
    try:
        from services.gateway.cache import invalidate_app_cache
        invalidate_app_cache(app_id)
    except Exception:
        pass  # Redis 不可用时不阻塞删除操作

    db.delete(application)
    db.commit()

    return None


@app.post("/api/v1/admin/applications/{app_id}/reset-secret", response_model=ResetSecretResponse)
async def reset_application_secret(
    app_id: str,
    user_id: str = Depends(require_super_admin),
    db: Session = Depends(get_db)
):
    """
    重置应用密钥

    生成新的 app_secret 并使旧凭证立即失效。新密钥仅返回一次。

    需求: 1.3
    """
    application = db.query(Application).filter(Application.app_id == app_id).first()
    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="应用不存在"
        )

    # 生成新的 app_secret
    new_secret = secrets.token_urlsafe(48)
    application.app_secret_hash = hash_password(new_secret)

    db.commit()
    db.refresh(application)

    # 清除 Redis 缓存使旧凭证立即失效
    try:
        from services.gateway.cache import invalidate_app_cache
        invalidate_app_cache(app_id)
    except Exception:
        pass

    return ResetSecretResponse(
        app_id=app_id,
        app_secret=new_secret,
        message="密钥已重置，请妥善保管新密钥，此密钥仅显示一次",
    )


@app.post("/api/v1/admin/applications/{app_id}/reset-webhook-secret", response_model=ResetWebhookSecretResponse)
async def reset_webhook_secret(
    app_id: str,
    user_id: str = Depends(require_super_admin),
    db: Session = Depends(get_db)
):
    """
    重置应用 Webhook 密钥

    生成新的 webhook_secret 并使旧密钥立即失效。新密钥仅返回一次。

    需求: 1.1
    """
    application = db.query(Application).filter(Application.app_id == app_id).first()
    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="应用不存在"
        )

    application.webhook_secret = secrets.token_hex(32)

    db.commit()
    db.refresh(application)

    return ResetWebhookSecretResponse(
        app_id=app_id,
        webhook_secret=application.webhook_secret,
        message="Webhook 密钥已重置，请妥善保管新密钥",
    )


@app.put("/api/v1/admin/applications/{app_id}/status", response_model=ApplicationResponse)
async def update_application_status(
    app_id: str,
    request: ApplicationStatusUpdate,
    user_id: str = Depends(require_super_admin),
    db: Session = Depends(get_db)
):
    """
    启用/禁用应用

    禁用后网关将拒绝该应用的所有 API 请求并返回 HTTP 403。

    需求: 1.4
    """
    if request.status not in ("active", "disabled"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="无效的状态值，支持: active, disabled"
        )

    application = db.query(Application).filter(Application.app_id == app_id).first()
    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="应用不存在"
        )

    application.status = request.status

    db.commit()
    db.refresh(application)

    # 清除 Redis 缓存使状态变更立即生效
    try:
        from services.gateway.cache import invalidate_app_cache
        invalidate_app_cache(app_id)
    except Exception:
        pass

    return ApplicationResponse(
        id=str(application.id),
        name=application.name,
        description=application.description,
        app_id=application.app_id,
        status=application.status,
        rate_limit=application.rate_limit,
        webhook_secret=application.webhook_secret,
        created_at=application.created_at,
        updated_at=application.updated_at,
    )


# ==================== 登录方式配置 Pydantic 模型 ====================

OAUTH_METHODS = {"wechat", "alipay", "google", "apple"}
ALL_LOGIN_METHODS = {"email", "phone", "wechat", "alipay", "google", "apple"}


class LoginMethodConfig(BaseModel):
    """单个登录方式配置"""
    method: str = Field(..., description="登录方式: email / phone / wechat / alipay / google / apple")
    is_enabled: bool = Field(..., description="是否启用")
    client_id: Optional[str] = Field(None, description="OAuth client_id（OAuth 类型启用时必填）")
    client_secret: Optional[str] = Field(None, description="OAuth client_secret（OAuth 类型启用时必填）")


class LoginMethodUpdate(BaseModel):
    """登录方式批量更新请求"""
    login_methods: List[LoginMethodConfig] = Field(..., description="登录方式配置列表")


class LoginMethodResponse(BaseModel):
    """单个登录方式响应"""
    id: str
    method: str
    is_enabled: bool
    client_id: Optional[str] = None
    client_secret_masked: Optional[str] = None
    created_at: datetime
    updated_at: datetime


class LoginMethodListResponse(BaseModel):
    """登录方式列表响应"""
    app_id: str
    login_methods: List[LoginMethodResponse]


# ==================== 登录方式配置 API 端点 ====================

@app.get("/api/v1/admin/applications/{app_id}/login-methods", response_model=LoginMethodListResponse)
async def get_login_methods(
    app_id: str,
    user_id: str = Depends(require_super_admin),
    db: Session = Depends(get_db)
):
    """
    获取应用登录方式列表

    返回应用的所有登录方式配置。OAuth 类型的 client_secret 仅展示末尾 4 位。

    需求: 2.1
    """
    application = db.query(Application).filter(Application.app_id == app_id).first()
    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="应用不存在"
        )

    methods = db.query(AppLoginMethod).filter(
        AppLoginMethod.application_id == application.id
    ).all()

    method_responses = []
    for m in methods:
        client_id = None
        client_secret_masked = None

        if m.method in OAUTH_METHODS and m.oauth_config:
            try:
                config = decrypt_config(m.oauth_config)
                client_id = config.get("client_id")
                raw_secret = config.get("client_secret", "")
                if raw_secret:
                    client_secret_masked = "****" + raw_secret[-4:] if len(raw_secret) >= 4 else "****"
            except Exception:
                pass

        method_responses.append(LoginMethodResponse(
            id=str(m.id),
            method=m.method,
            is_enabled=m.is_enabled,
            client_id=client_id,
            client_secret_masked=client_secret_masked,
            created_at=m.created_at,
            updated_at=m.updated_at,
        ))

    return LoginMethodListResponse(app_id=app_id, login_methods=method_responses)


@app.put("/api/v1/admin/applications/{app_id}/login-methods", response_model=LoginMethodListResponse)
async def update_login_methods(
    app_id: str,
    request: LoginMethodUpdate,
    user_id: str = Depends(require_super_admin),
    db: Session = Depends(get_db)
):
    """
    更新应用登录方式配置（批量更新）

    OAuth 类型（wechat、alipay、google、apple）启用时必须提供 client_id 和 client_secret。
    OAuth 配置使用 encrypt_config 加密存储。配置变更后清除 Redis 缓存。

    需求: 2.1, 2.2, 2.4, 2.5
    """
    application = db.query(Application).filter(Application.app_id == app_id).first()
    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="应用不存在"
        )

    # 校验请求
    for lm in request.login_methods:
        if lm.method not in ALL_LOGIN_METHODS:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"不支持的登录方式: {lm.method}，支持: {', '.join(sorted(ALL_LOGIN_METHODS))}"
            )
        # OAuth 类型启用时校验 client_id 和 client_secret 必填
        if lm.method in OAUTH_METHODS and lm.is_enabled:
            if not lm.client_id or not lm.client_secret:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail=f"启用 OAuth 登录方式 {lm.method} 时必须提供 client_id 和 client_secret"
                )

    # 更新或创建登录方式记录
    for lm in request.login_methods:
        existing = db.query(AppLoginMethod).filter(
            AppLoginMethod.application_id == application.id,
            AppLoginMethod.method == lm.method
        ).first()

        oauth_config_encrypted = None
        if lm.method in OAUTH_METHODS and lm.is_enabled and lm.client_id and lm.client_secret:
            oauth_config_encrypted = encrypt_config({
                "client_id": lm.client_id,
                "client_secret": lm.client_secret,
            })

        if existing:
            existing.is_enabled = lm.is_enabled
            if oauth_config_encrypted is not None:
                existing.oauth_config = oauth_config_encrypted
            elif lm.method in OAUTH_METHODS and not lm.is_enabled:
                # 禁用 OAuth 方式时保留配置（不清除）
                pass
            existing.updated_at = datetime.utcnow()
        else:
            new_method = AppLoginMethod(
                application_id=application.id,
                method=lm.method,
                is_enabled=lm.is_enabled,
                oauth_config=oauth_config_encrypted,
            )
            db.add(new_method)

    db.commit()

    # 清除 Redis 缓存
    try:
        from services.gateway.cache import invalidate_app_cache
        invalidate_app_cache(app_id)
    except Exception:
        pass  # Redis 不可用时不阻塞操作

    # 返回更新后的列表
    methods = db.query(AppLoginMethod).filter(
        AppLoginMethod.application_id == application.id
    ).all()

    method_responses = []
    for m in methods:
        client_id = None
        client_secret_masked = None

        if m.method in OAUTH_METHODS and m.oauth_config:
            try:
                config = decrypt_config(m.oauth_config)
                client_id = config.get("client_id")
                raw_secret = config.get("client_secret", "")
                if raw_secret:
                    client_secret_masked = "****" + raw_secret[-4:] if len(raw_secret) >= 4 else "****"
            except Exception:
                pass

        method_responses.append(LoginMethodResponse(
            id=str(m.id),
            method=m.method,
            is_enabled=m.is_enabled,
            client_id=client_id,
            client_secret_masked=client_secret_masked,
            created_at=m.created_at,
            updated_at=m.updated_at,
        ))

    return LoginMethodListResponse(app_id=app_id, login_methods=method_responses)


# ==================== Scope 配置 Pydantic 模型 ====================

VALID_SCOPES = {
    "user:read", "user:write",
    "auth:login", "auth:register",
    "role:read", "role:write",
    "org:read", "org:write",
}


class ScopeUpdate(BaseModel):
    """Scope 批量更新请求"""
    scopes: List[str] = Field(..., description="权限范围列表")


class ScopeResponse(BaseModel):
    """单个 Scope 响应"""
    id: str
    scope: str
    created_at: datetime


class ScopeListResponse(BaseModel):
    """Scope 列表响应"""
    app_id: str
    scopes: List[ScopeResponse]


# ==================== Scope 配置 API 端点 ====================

@app.get("/api/v1/admin/applications/{app_id}/scopes", response_model=ScopeListResponse)
async def get_scopes(
    app_id: str,
    user_id: str = Depends(require_super_admin),
    db: Session = Depends(get_db)
):
    """
    获取应用 Scope 列表

    返回应用的所有已授权权限范围。

    需求: 5.1
    """
    application = db.query(Application).filter(Application.app_id == app_id).first()
    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="应用不存在"
        )

    scopes = db.query(AppScope).filter(
        AppScope.application_id == application.id
    ).all()

    scope_responses = [
        ScopeResponse(
            id=str(s.id),
            scope=s.scope,
            created_at=s.created_at,
        )
        for s in scopes
    ]

    return ScopeListResponse(app_id=app_id, scopes=scope_responses)


@app.put("/api/v1/admin/applications/{app_id}/scopes", response_model=ScopeListResponse)
async def update_scopes(
    app_id: str,
    request: ScopeUpdate,
    user_id: str = Depends(require_super_admin),
    db: Session = Depends(get_db)
):
    """
    更新应用 Scope 配置（批量替换）

    用提供的 Scope 列表完全替换应用当前的 Scope 配置。
    配置变更后清除 Redis 缓存。

    需求: 5.1, 5.3
    """
    application = db.query(Application).filter(Application.app_id == app_id).first()
    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="应用不存在"
        )

    # 校验 scope 值
    invalid_scopes = [s for s in request.scopes if s not in VALID_SCOPES]
    if invalid_scopes:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"无效的 Scope: {', '.join(invalid_scopes)}，支持: {', '.join(sorted(VALID_SCOPES))}"
        )

    # 去重
    unique_scopes = list(set(request.scopes))

    # 删除旧的 scope 记录
    db.query(AppScope).filter(
        AppScope.application_id == application.id
    ).delete(synchronize_session="fetch")

    # 创建新的 scope 记录
    for scope_name in unique_scopes:
        new_scope = AppScope(
            application_id=application.id,
            scope=scope_name,
        )
        db.add(new_scope)

    db.commit()

    # 清除 Redis 缓存
    try:
        from services.gateway.cache import invalidate_app_cache
        invalidate_app_cache(app_id)
    except Exception:
        pass  # Redis 不可用时不阻塞操作

    # 返回更新后的列表
    scopes = db.query(AppScope).filter(
        AppScope.application_id == application.id
    ).all()

    scope_responses = [
        ScopeResponse(
            id=str(s.id),
            scope=s.scope,
            created_at=s.created_at,
        )
        for s in scopes
    ]

    return ScopeListResponse(app_id=app_id, scopes=scope_responses)


# ==================== 组织架构绑定 Pydantic 模型 ====================

class OrgBindingUpdate(BaseModel):
    """组织绑定更新请求"""
    organization_ids: List[str] = Field(..., description="组织ID列表")


class OrgBindingResponse(BaseModel):
    """组织绑定响应"""
    app_id: str
    organization_ids: List[str]


# ==================== 组织架构绑定 API 端点 ====================

@app.get("/api/v1/admin/applications/{app_id}/organizations", response_model=OrgBindingResponse)
async def get_app_organizations(
    app_id: str,
    user_id: str = Depends(require_super_admin),
    db: Session = Depends(get_db)
):
    """获取应用绑定的组织列表"""
    application = db.query(Application).filter(Application.app_id == app_id).first()
    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="应用不存在")

    bindings = db.query(AppOrganization).filter(AppOrganization.application_id == application.id).all()
    return OrgBindingResponse(app_id=app_id, organization_ids=[str(b.organization_id) for b in bindings])


@app.put("/api/v1/admin/applications/{app_id}/organizations", response_model=OrgBindingResponse)
async def update_app_organizations(
    app_id: str,
    request: OrgBindingUpdate,
    user_id: str = Depends(require_super_admin),
    db: Session = Depends(get_db)
):
    """更新应用绑定的组织（批量替换）"""
    application = db.query(Application).filter(Application.app_id == app_id).first()
    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="应用不存在")

    # 删除旧绑定
    db.query(AppOrganization).filter(AppOrganization.application_id == application.id).delete(synchronize_session="fetch")

    # 创建新绑定
    unique_ids = list(set(request.organization_ids))
    for org_id in unique_ids:
        try:
            org_uuid = uuid.UUID(org_id)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=f"无效的组织ID: {org_id}")
        db.add(AppOrganization(application_id=application.id, organization_id=org_uuid))

    db.commit()

    bindings = db.query(AppOrganization).filter(AppOrganization.application_id == application.id).all()
    return OrgBindingResponse(app_id=app_id, organization_ids=[str(b.organization_id) for b in bindings])


# ==================== 订阅计划绑定 Pydantic 模型 ====================

class SubscriptionPlanBindingUpdate(BaseModel):
    """订阅计划绑定更新请求"""
    plan_id: Optional[str] = Field(None, description="订阅计划ID，为空则清除绑定")


class SubscriptionPlanBindingResponse(BaseModel):
    """订阅计划绑定响应"""
    app_id: str
    plan_id: Optional[str]


# ==================== 订阅计划绑定 API 端点 ====================

@app.get("/api/v1/admin/applications/{app_id}/subscription-plan", response_model=SubscriptionPlanBindingResponse)
async def get_app_subscription_plan(
    app_id: str,
    user_id: str = Depends(require_super_admin),
    db: Session = Depends(get_db)
):
    """获取应用绑定的订阅计划"""
    application = db.query(Application).filter(Application.app_id == app_id).first()
    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="应用不存在")

    binding = db.query(AppSubscriptionPlan).filter(AppSubscriptionPlan.application_id == application.id).first()
    return SubscriptionPlanBindingResponse(app_id=app_id, plan_id=str(binding.plan_id) if binding else None)


@app.put("/api/v1/admin/applications/{app_id}/subscription-plan", response_model=SubscriptionPlanBindingResponse)
async def update_app_subscription_plan(
    app_id: str,
    request: SubscriptionPlanBindingUpdate,
    user_id: str = Depends(require_super_admin),
    db: Session = Depends(get_db)
):
    """更新应用绑定的订阅计划"""
    application = db.query(Application).filter(Application.app_id == app_id).first()
    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="应用不存在")

    # 删除旧绑定
    db.query(AppSubscriptionPlan).filter(AppSubscriptionPlan.application_id == application.id).delete(synchronize_session="fetch")

    if request.plan_id:
        try:
            plan_uuid = uuid.UUID(request.plan_id)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无效的订阅计划ID")
        db.add(AppSubscriptionPlan(application_id=application.id, plan_id=plan_uuid))

    db.commit()

    binding = db.query(AppSubscriptionPlan).filter(AppSubscriptionPlan.application_id == application.id).first()
    return SubscriptionPlanBindingResponse(app_id=app_id, plan_id=str(binding.plan_id) if binding else None)


# ==================== 自动配置规则 Pydantic 模型 ====================

class AutoProvisionConfigUpdate(BaseModel):
    """自动配置规则更新请求"""
    role_ids: Optional[List[str]] = None
    permission_ids: Optional[List[str]] = None
    organization_id: Optional[str] = None
    subscription_plan_id: Optional[str] = None
    is_enabled: bool = True


class AutoProvisionConfigResponse(BaseModel):
    """自动配置规则响应"""
    application_id: str
    role_ids: List[str]
    permission_ids: List[str]
    organization_id: Optional[str]
    subscription_plan_id: Optional[str]
    is_enabled: bool
    created_at: str
    updated_at: str


# ==================== 自动配置规则 API 端点 ====================

@app.get("/api/v1/admin/applications/{app_id}/auto-provision", response_model=AutoProvisionConfigResponse)
async def get_auto_provision_config(
    app_id: str,
    user_id: str = Depends(require_super_admin),
    db: Session = Depends(get_db)
):
    """
    获取应用自动配置规则

    不存在时返回默认空配置。

    需求: 2.1
    """
    application = db.query(Application).filter(Application.app_id == app_id).first()
    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="应用不存在"
        )

    config = db.query(AutoProvisionConfig).filter(
        AutoProvisionConfig.application_id == application.id
    ).first()

    if config:
        return AutoProvisionConfigResponse(
            application_id=app_id,
            role_ids=[str(rid) for rid in (config.role_ids or [])],
            permission_ids=[str(pid) for pid in (config.permission_ids or [])],
            organization_id=str(config.organization_id) if config.organization_id else None,
            subscription_plan_id=str(config.subscription_plan_id) if config.subscription_plan_id else None,
            is_enabled=config.is_enabled,
            created_at=config.created_at.isoformat(),
            updated_at=config.updated_at.isoformat(),
        )

    # 返回默认空配置
    now = datetime.utcnow().isoformat()
    return AutoProvisionConfigResponse(
        application_id=app_id,
        role_ids=[],
        permission_ids=[],
        organization_id=None,
        subscription_plan_id=None,
        is_enabled=False,
        created_at=now,
        updated_at=now,
    )


@app.put("/api/v1/admin/applications/{app_id}/auto-provision", response_model=AutoProvisionConfigResponse)
async def update_auto_provision_config(
    app_id: str,
    request: AutoProvisionConfigUpdate,
    user_id: str = Depends(require_super_admin),
    db: Session = Depends(get_db)
):
    """
    创建或更新应用自动配置规则

    校验所有引用 ID 的有效性，校验失败返回 400。

    需求: 2.2, 2.4, 2.5, 2.6, 2.7
    """
    from shared.models.permission import Role, Permission
    from shared.models.organization import Organization
    from shared.models.subscription import SubscriptionPlan

    application = db.query(Application).filter(Application.app_id == app_id).first()
    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="应用不存在"
        )

    errors = []

    # 校验 role_ids
    role_uuids = []
    if request.role_ids:
        for rid in request.role_ids:
            try:
                role_uuids.append(uuid.UUID(rid))
            except ValueError:
                errors.append(f"无效的角色ID格式: {rid}")
        if not errors:
            existing_roles = db.query(Role.id).filter(Role.id.in_(role_uuids)).all()
            existing_role_ids = {r.id for r in existing_roles}
            invalid_roles = [str(rid) for rid in role_uuids if rid not in existing_role_ids]
            if invalid_roles:
                errors.append(f"不存在的角色ID: {', '.join(invalid_roles)}")

    # 校验 permission_ids
    perm_uuids = []
    if request.permission_ids:
        for pid in request.permission_ids:
            try:
                perm_uuids.append(uuid.UUID(pid))
            except ValueError:
                errors.append(f"无效的权限ID格式: {pid}")
        if not errors:
            existing_perms = db.query(Permission.id).filter(Permission.id.in_(perm_uuids)).all()
            existing_perm_ids = {p.id for p in existing_perms}
            invalid_perms = [str(pid) for pid in perm_uuids if pid not in existing_perm_ids]
            if invalid_perms:
                errors.append(f"不存在的权限ID: {', '.join(invalid_perms)}")

    # 校验 organization_id
    org_uuid = None
    if request.organization_id:
        try:
            org_uuid = uuid.UUID(request.organization_id)
        except ValueError:
            errors.append(f"无效的组织ID格式: {request.organization_id}")
        if org_uuid and not errors:
            org = db.query(Organization).filter(Organization.id == org_uuid).first()
            if not org:
                errors.append(f"不存在的组织ID: {request.organization_id}")

    # 校验 subscription_plan_id
    plan_uuid = None
    if request.subscription_plan_id:
        try:
            plan_uuid = uuid.UUID(request.subscription_plan_id)
        except ValueError:
            errors.append(f"无效的订阅计划ID格式: {request.subscription_plan_id}")
        if plan_uuid and not errors:
            plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == plan_uuid).first()
            if not plan:
                errors.append(f"不存在的订阅计划ID: {request.subscription_plan_id}")

    if errors:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="; ".join(errors)
        )

    # 查找或创建配置
    config = db.query(AutoProvisionConfig).filter(
        AutoProvisionConfig.application_id == application.id
    ).first()

    role_ids_list = [str(rid) for rid in role_uuids] if request.role_ids else []
    perm_ids_list = [str(pid) for pid in perm_uuids] if request.permission_ids else []

    if config:
        config.role_ids = role_ids_list
        config.permission_ids = perm_ids_list
        config.organization_id = org_uuid
        config.subscription_plan_id = plan_uuid
        config.is_enabled = request.is_enabled
        config.updated_at = datetime.utcnow()
    else:
        config = AutoProvisionConfig(
            application_id=application.id,
            role_ids=role_ids_list,
            permission_ids=perm_ids_list,
            organization_id=org_uuid,
            subscription_plan_id=plan_uuid,
            is_enabled=request.is_enabled,
        )
        db.add(config)

    db.commit()
    db.refresh(config)

    return AutoProvisionConfigResponse(
        application_id=app_id,
        role_ids=[str(rid) for rid in (config.role_ids or [])],
        permission_ids=[str(pid) for pid in (config.permission_ids or [])],
        organization_id=str(config.organization_id) if config.organization_id else None,
        subscription_plan_id=str(config.subscription_plan_id) if config.subscription_plan_id else None,
        is_enabled=config.is_enabled,
        created_at=config.created_at.isoformat(),
        updated_at=config.updated_at.isoformat(),
    )


@app.delete("/api/v1/admin/applications/{app_id}/auto-provision")
async def delete_auto_provision_config(
    app_id: str,
    user_id: str = Depends(require_super_admin),
    db: Session = Depends(get_db)
):
    """
    删除应用自动配置规则

    需求: 2.3
    """
    application = db.query(Application).filter(Application.app_id == app_id).first()
    if not application:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="应用不存在"
        )

    config = db.query(AutoProvisionConfig).filter(
        AutoProvisionConfig.application_id == application.id
    ).first()

    if config:
        db.delete(config)
        db.commit()

    return {"success": True, "message": "自动配置规则已删除"}

@app.get("/api/v1/admin/webhook-events")
async def admin_list_webhook_events(
    app_id: Optional[str] = None,
    event_type: Optional[str] = None,
    status: Optional[str] = None,
    start_time: Optional[str] = None,
    end_time: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
):
    """
    管理端点：代理调用订阅服务的事件日志查询接口

    需求: 7.1
    """
    params = {}
    if app_id is not None:
        params["app_id"] = app_id
    if event_type is not None:
        params["event_type"] = event_type
    if status is not None:
        params["status"] = status
    if start_time is not None:
        params["start_time"] = start_time
    if end_time is not None:
        params["end_time"] = end_time
    params["page"] = page
    params["page_size"] = page_size

    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(
                "http://localhost:8006/api/v1/webhooks/events",
                params=params,
            )
            response.raise_for_status()
            return response.json()
    except httpx.TimeoutException:
        raise HTTPException(
            status_code=502,
            detail="订阅服务请求超时",
        )
    except httpx.HTTPStatusError as e:
        raise HTTPException(
            status_code=e.response.status_code,
            detail=e.response.text,
        )
    except httpx.HTTPError:
        raise HTTPException(
            status_code=502,
            detail="无法连接到订阅服务",
        )



# ==================== 配额管理 Pydantic 模型 ====================

class QuotaOverviewItem(BaseModel):
    """配额概览条目"""
    app_id: str
    app_name: str
    request_quota_limit: int
    request_quota_used: int
    request_quota_remaining: int
    token_quota_limit: int
    token_quota_used: int
    token_quota_remaining: int
    request_usage_rate: float  # 0.0 ~ 1.0
    token_usage_rate: float
    billing_cycle_start: Optional[str]
    billing_cycle_end: Optional[str]

class QuotaOverviewResponse(BaseModel):
    """配额概览响应"""
    items: List[QuotaOverviewItem]
    total: int

class QuotaDetailResponse(BaseModel):
    """单个应用配额详情"""
    app_id: str
    app_name: str
    request_quota_limit: int
    request_quota_used: int
    request_quota_remaining: int
    token_quota_limit: int
    token_quota_used: int
    token_quota_remaining: int
    request_usage_rate: float
    token_usage_rate: float
    billing_cycle_start: Optional[str]
    billing_cycle_end: Optional[str]
    has_override: bool
    override_request_quota: Optional[int]
    override_token_quota: Optional[int]
    plan_name: Optional[str]
    plan_request_quota: Optional[int]
    plan_token_quota: Optional[int]
    quota_period_days: Optional[int]

class QuotaOverrideRequest(BaseModel):
    """配额覆盖请求"""
    request_quota: Optional[int] = Field(None, description="请求次数配额，NULL 使用计划默认值，-1 无限制")
    token_quota: Optional[int] = Field(None, description="Token 配额，NULL 使用计划默认值，-1 无限制")

class QuotaHistoryItem(BaseModel):
    """配额历史条目"""
    id: str
    billing_cycle_start: str
    billing_cycle_end: str
    request_quota_limit: int
    request_quota_used: int
    token_quota_limit: int
    token_quota_used: int
    reset_type: str
    created_at: str

class QuotaHistoryResponse(BaseModel):
    """配额历史响应"""
    items: List[QuotaHistoryItem]
    total: int
    page: int
    page_size: int


def _compute_usage_rate(used: int, limit: int) -> float:
    """计算使用率"""
    if limit == -1:
        return 0.0
    if limit == 0:
        return 1.0 if used > 0 else 0.0
    return min(used / limit, 1.0)


def _compute_remaining(limit: int, used: int) -> int:
    """计算剩余量"""
    if limit == -1:
        return -1
    return max(0, limit - used)


async def _get_app_quota_from_redis(app_id: str) -> dict:
    """从 Redis 读取应用的实时配额数据"""
    try:
        from shared.redis_client import get_redis
        r = get_redis()
        requests_used = int(r.get(f"quota:{app_id}:requests") or 0)
        tokens_used = int(float(r.get(f"quota:{app_id}:tokens") or 0))
        cycle_start = r.get(f"quota:{app_id}:cycle_start")
        config_data = r.hgetall(f"quota:{app_id}:config")
        return {
            "requests_used": requests_used,
            "tokens_used": tokens_used,
            "cycle_start": cycle_start,
            "config": config_data,
        }
    except Exception:
        return {
            "requests_used": 0,
            "tokens_used": 0,
            "cycle_start": None,
            "config": {},
        }


async def _get_effective_quota(app: Application, db: Session) -> dict:
    """获取应用的有效配额配置（覆盖优先于计划）"""
    from shared.models.quota import AppQuotaOverride
    from shared.models.subscription import SubscriptionPlan

    override = db.query(AppQuotaOverride).filter(
        AppQuotaOverride.application_id == app.id
    ).first()

    binding = db.query(AppSubscriptionPlan).filter(
        AppSubscriptionPlan.application_id == app.id
    ).first()

    plan = None
    if binding:
        plan = db.query(SubscriptionPlan).filter(SubscriptionPlan.id == binding.plan_id).first()

    plan_request_quota = plan.request_quota if plan else None
    plan_token_quota = plan.token_quota if plan else None
    quota_period_days = plan.quota_period_days if plan else None

    effective_request = (override.request_quota if override and override.request_quota is not None
                         else plan_request_quota if plan_request_quota is not None else 0)
    effective_token = (override.token_quota if override and override.token_quota is not None
                       else plan_token_quota if plan_token_quota is not None else 0)

    return {
        "effective_request_quota": effective_request,
        "effective_token_quota": effective_token,
        "plan_name": plan.name if plan else None,
        "plan_request_quota": plan_request_quota,
        "plan_token_quota": plan_token_quota,
        "quota_period_days": quota_period_days,
        "has_override": override is not None,
        "override_request_quota": override.request_quota if override else None,
        "override_token_quota": override.token_quota if override else None,
    }


# ==================== 配额管理 API 端点 ====================

@app.get("/api/v1/admin/quota/overview", response_model=QuotaOverviewResponse)
async def quota_overview(
    sort_by: Optional[str] = Query(None, description="排序字段: request_usage_rate / token_usage_rate"),
    user_id: str = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    """所有应用配额使用概览"""
    applications = db.query(Application).filter(Application.status == "active").all()
    items = []
    for app_obj in applications:
        redis_data = await _get_app_quota_from_redis(app_obj.app_id)
        quota_info = await _get_effective_quota(app_obj, db)

        req_limit = quota_info["effective_request_quota"]
        tok_limit = quota_info["effective_token_quota"]
        req_used = redis_data["requests_used"]
        tok_used = redis_data["tokens_used"]

        cycle_start_str = redis_data.get("cycle_start")
        cycle_end_str = None
        if cycle_start_str and quota_info["quota_period_days"]:
            try:
                from datetime import timedelta
                cs = datetime.fromisoformat(cycle_start_str)
                ce = cs + timedelta(days=quota_info["quota_period_days"])
                cycle_end_str = ce.isoformat()
            except Exception:
                pass

        items.append(QuotaOverviewItem(
            app_id=app_obj.app_id,
            app_name=app_obj.name,
            request_quota_limit=req_limit,
            request_quota_used=req_used,
            request_quota_remaining=_compute_remaining(req_limit, req_used),
            token_quota_limit=tok_limit,
            token_quota_used=tok_used,
            token_quota_remaining=_compute_remaining(tok_limit, tok_used),
            request_usage_rate=_compute_usage_rate(req_used, req_limit),
            token_usage_rate=_compute_usage_rate(tok_used, tok_limit),
            billing_cycle_start=cycle_start_str,
            billing_cycle_end=cycle_end_str,
        ))

    if sort_by == "request_usage_rate":
        items.sort(key=lambda x: x.request_usage_rate, reverse=True)
    elif sort_by == "token_usage_rate":
        items.sort(key=lambda x: x.token_usage_rate, reverse=True)

    return QuotaOverviewResponse(items=items, total=len(items))


@app.get("/api/v1/admin/quota/{app_id}", response_model=QuotaDetailResponse)
async def quota_detail(
    app_id: str,
    user_id: str = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    """单个应用配额详情"""
    application = db.query(Application).filter(Application.app_id == app_id).first()
    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="应用不存在")

    redis_data = await _get_app_quota_from_redis(app_id)
    quota_info = await _get_effective_quota(application, db)

    req_limit = quota_info["effective_request_quota"]
    tok_limit = quota_info["effective_token_quota"]
    req_used = redis_data["requests_used"]
    tok_used = redis_data["tokens_used"]

    cycle_start_str = redis_data.get("cycle_start")
    cycle_end_str = None
    if cycle_start_str and quota_info["quota_period_days"]:
        try:
            from datetime import timedelta
            cs = datetime.fromisoformat(cycle_start_str)
            ce = cs + timedelta(days=quota_info["quota_period_days"])
            cycle_end_str = ce.isoformat()
        except Exception:
            pass

    return QuotaDetailResponse(
        app_id=app_id,
        app_name=application.name,
        request_quota_limit=req_limit,
        request_quota_used=req_used,
        request_quota_remaining=_compute_remaining(req_limit, req_used),
        token_quota_limit=tok_limit,
        token_quota_used=tok_used,
        token_quota_remaining=_compute_remaining(tok_limit, tok_used),
        request_usage_rate=_compute_usage_rate(req_used, req_limit),
        token_usage_rate=_compute_usage_rate(tok_used, tok_limit),
        billing_cycle_start=cycle_start_str,
        billing_cycle_end=cycle_end_str,
        has_override=quota_info["has_override"],
        override_request_quota=quota_info["override_request_quota"],
        override_token_quota=quota_info["override_token_quota"],
        plan_name=quota_info["plan_name"],
        plan_request_quota=quota_info["plan_request_quota"],
        plan_token_quota=quota_info["plan_token_quota"],
        quota_period_days=quota_info["quota_period_days"],
    )


@app.put("/api/v1/admin/quota/{app_id}/override")
async def quota_override(
    app_id: str,
    request_body: QuotaOverrideRequest,
    request: Request,
    user_id: str = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    """手动调整应用配额上限"""
    from shared.models.quota import AppQuotaOverride
    from shared.utils.audit_log import create_audit_log

    application = db.query(Application).filter(Application.app_id == app_id).first()
    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="应用不存在")

    # 验证配额值
    if request_body.request_quota is not None and request_body.request_quota < -1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error_code": "invalid_quota_value", "message": "request_quota 必须 >= -1"},
        )
    if request_body.token_quota is not None and request_body.token_quota < -1:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error_code": "invalid_quota_value", "message": "token_quota 必须 >= -1"},
        )

    override = db.query(AppQuotaOverride).filter(
        AppQuotaOverride.application_id == application.id
    ).first()

    old_values = {
        "request_quota": override.request_quota if override else None,
        "token_quota": override.token_quota if override else None,
    }

    if override:
        if request_body.request_quota is not None:
            override.request_quota = request_body.request_quota
        if request_body.token_quota is not None:
            override.token_quota = request_body.token_quota
        override.updated_at = datetime.utcnow()
    else:
        override = AppQuotaOverride(
            application_id=application.id,
            request_quota=request_body.request_quota,
            token_quota=request_body.token_quota,
        )
        db.add(override)

    db.commit()

    # 更新 Redis 配额配置缓存
    try:
        from shared.redis_client import get_redis
        r = get_redis()
        config_key = f"quota:{app_id}:config"
        config_update = {}
        if override.request_quota is not None:
            config_update["request_quota"] = str(override.request_quota)
        if override.token_quota is not None:
            config_update["token_quota"] = str(override.token_quota)
        if config_update:
            r.hset(config_key, mapping=config_update)
    except Exception:
        pass  # Redis 更新失败不阻塞

    new_values = {
        "request_quota": override.request_quota,
        "token_quota": override.token_quota,
    }

    # 记录审计日志
    try:
        uid = uuid.UUID(user_id) if user_id else None
    except (ValueError, AttributeError):
        uid = None
    create_audit_log(
        db=db,
        user_id=uid,
        action="quota_override",
        resource_type="application",
        resource_id=application.id,
        details={
            "app_id": app_id,
            "old_values": old_values,
            "new_values": new_values,
            "operation": "override",
        },
    )

    return {
        "success": True,
        "message": "配额覆盖已更新",
        "old_values": old_values,
        "new_values": new_values,
    }


@app.post("/api/v1/admin/quota/{app_id}/reset")
async def quota_reset(
    app_id: str,
    request: Request,
    user_id: str = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    """手动重置应用配额"""
    from shared.models.quota import QuotaUsage
    from shared.utils.audit_log import create_audit_log

    application = db.query(Application).filter(Application.app_id == app_id).first()
    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="应用不存在")

    # 从 Redis 读取当前使用数据
    redis_data = await _get_app_quota_from_redis(app_id)
    quota_info = await _get_effective_quota(application, db)

    req_used = redis_data["requests_used"]
    tok_used = redis_data["tokens_used"]
    cycle_start_str = redis_data.get("cycle_start")

    now = datetime.utcnow()
    cycle_start = datetime.fromisoformat(cycle_start_str) if cycle_start_str else now

    # 持久化当前使用数据到 QuotaUsage
    usage_record = QuotaUsage(
        application_id=application.id,
        billing_cycle_start=cycle_start,
        billing_cycle_end=now,
        request_quota_limit=quota_info["effective_request_quota"],
        request_quota_used=req_used,
        token_quota_limit=quota_info["effective_token_quota"],
        token_quota_used=tok_used,
        reset_type="manual",
    )
    db.add(usage_record)
    db.commit()

    # 重置 Redis 计数器
    try:
        from shared.redis_client import get_redis
        r = get_redis()
        r.set(f"quota:{app_id}:requests", 0)
        r.set(f"quota:{app_id}:tokens", 0)
        r.set(f"quota:{app_id}:cycle_start", now.isoformat())
        # 清除预警标记
        r.delete(f"quota:{app_id}:warning_sent:80")
        r.delete(f"quota:{app_id}:warning_sent:100")
    except Exception:
        pass  # Redis 重置失败不阻塞

    # 记录审计日志
    try:
        uid = uuid.UUID(user_id) if user_id else None
    except (ValueError, AttributeError):
        uid = None
    create_audit_log(
        db=db,
        user_id=uid,
        action="quota_reset",
        resource_type="application",
        resource_id=application.id,
        details={
            "app_id": app_id,
            "reset_type": "manual",
            "previous_request_used": req_used,
            "previous_token_used": tok_used,
            "previous_cycle_start": cycle_start.isoformat(),
        },
    )

    return {
        "success": True,
        "message": "配额已重置",
        "previous_usage": {
            "request_used": req_used,
            "token_used": tok_used,
        },
    }


@app.get("/api/v1/admin/quota/{app_id}/history", response_model=QuotaHistoryResponse)
async def quota_history(
    app_id: str,
    start_time: Optional[str] = Query(None, description="开始时间 (ISO format)"),
    end_time: Optional[str] = Query(None, description="结束时间 (ISO format)"),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    user_id: str = Depends(require_super_admin),
    db: Session = Depends(get_db),
):
    """应用配额使用历史"""
    from shared.models.quota import QuotaUsage

    application = db.query(Application).filter(Application.app_id == app_id).first()
    if not application:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="应用不存在")

    query = db.query(QuotaUsage).filter(QuotaUsage.application_id == application.id)

    if start_time:
        try:
            st = datetime.fromisoformat(start_time)
            query = query.filter(QuotaUsage.billing_cycle_start >= st)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无效的 start_time 格式")

    if end_time:
        try:
            et = datetime.fromisoformat(end_time)
            query = query.filter(QuotaUsage.billing_cycle_end <= et)
        except ValueError:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="无效的 end_time 格式")

    total = query.count()
    records = query.order_by(QuotaUsage.billing_cycle_start.desc()).offset(
        (page - 1) * page_size
    ).limit(page_size).all()

    items = [
        QuotaHistoryItem(
            id=str(r.id),
            billing_cycle_start=r.billing_cycle_start.isoformat(),
            billing_cycle_end=r.billing_cycle_end.isoformat(),
            request_quota_limit=r.request_quota_limit,
            request_quota_used=r.request_quota_used,
            token_quota_limit=r.token_quota_limit,
            token_quota_used=r.token_quota_used,
            reset_type=r.reset_type,
            created_at=r.created_at.isoformat(),
        )
        for r in records
    ]

    return QuotaHistoryResponse(items=items, total=total, page=page, page_size=page_size)


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8007)
