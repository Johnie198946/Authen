"""
加密工具模块
"""
import hashlib
import secrets
import json
import base64
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
from cryptography.hazmat.backends import default_backend
import os


def hash_password(password: str) -> str:
    """
    使用SHA256加密密码（简化版本，生产环境应使用bcrypt）
    
    Args:
        password: 明文密码
        
    Returns:
        加密后的密码哈希
    """
    # 生成盐值
    salt = secrets.token_hex(16)
    # 组合密码和盐值进行哈希
    pwd_hash = hashlib.sha256((password + salt).encode()).hexdigest()
    # 返回格式：salt$hash
    return f"{salt}${pwd_hash}"


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """
    验证密码
    
    Args:
        plain_password: 明文密码
        hashed_password: 加密后的密码哈希
        
    Returns:
        密码是否匹配
    """
    try:
        # 分离盐值和哈希值
        salt, pwd_hash = hashed_password.split('$')
        # 使用相同的盐值计算哈希
        computed_hash = hashlib.sha256((plain_password + salt).encode()).hexdigest()
        # 比较哈希值
        return computed_hash == pwd_hash
    except:
        return False


def get_encryption_key() -> bytes:
    """
    获取加密密钥
    
    从环境变量获取加密密钥，如果不存在则生成一个新的
    
    Returns:
        加密密钥
    """
    # 从环境变量获取密钥
    key_str = os.getenv("ENCRYPTION_KEY")
    
    if not key_str:
        # 如果没有设置，使用默认密钥（仅用于开发环境）
        # 生产环境必须设置ENCRYPTION_KEY环境变量
        key_str = "default-encryption-key-for-development-only"
    
    # 使用PBKDF2从密钥字符串派生Fernet密钥
    kdf = PBKDF2HMAC(
        algorithm=hashes.SHA256(),
        length=32,
        salt=b'unified-auth-platform',  # 固定盐值
        iterations=100000,
        backend=default_backend()
    )
    key = base64.urlsafe_b64encode(kdf.derive(key_str.encode()))
    return key


def encrypt_config(config_data: dict) -> str:
    """
    加密配置数据
    
    Args:
        config_data: 配置数据字典
        
    Returns:
        加密后的配置字符串
    """
    # 将配置转换为JSON字符串
    config_json = json.dumps(config_data)
    
    # 获取加密密钥
    key = get_encryption_key()
    fernet = Fernet(key)
    
    # 加密数据
    encrypted_data = fernet.encrypt(config_json.encode())
    
    # 返回base64编码的加密数据
    return base64.urlsafe_b64encode(encrypted_data).decode()


def decrypt_config(encrypted_config: str) -> dict:
    """
    解密配置数据
    
    Args:
        encrypted_config: 加密的配置字符串
        
    Returns:
        解密后的配置数据字典
    """
    try:
        # 解码base64
        encrypted_data = base64.urlsafe_b64decode(encrypted_config.encode())
        
        # 获取加密密钥
        key = get_encryption_key()
        fernet = Fernet(key)
        
        # 解密数据
        decrypted_data = fernet.decrypt(encrypted_data)
        
        # 解析JSON
        config_data = json.loads(decrypted_data.decode())
        
        return config_data
    except Exception as e:
        raise ValueError(f"解密配置失败: {str(e)}")
