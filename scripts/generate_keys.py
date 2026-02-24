"""
生成RSA密钥对用于JWT签名
"""
from cryptography.hazmat.primitives.asymmetric import rsa
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.backends import default_backend
import os


def generate_rsa_keys():
    """生成RSA密钥对"""
    # 生成私钥
    private_key = rsa.generate_private_key(
        public_exponent=65537,
        key_size=2048,
        backend=default_backend()
    )
    
    # 序列化私钥
    private_pem = private_key.private_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PrivateFormat.PKCS8,
        encryption_algorithm=serialization.NoEncryption()
    )
    
    # 生成公钥
    public_key = private_key.public_key()
    
    # 序列化公钥
    public_pem = public_key.public_bytes(
        encoding=serialization.Encoding.PEM,
        format=serialization.PublicFormat.SubjectPublicKeyInfo
    )
    
    # 创建keys目录
    os.makedirs('keys', exist_ok=True)
    
    # 保存私钥
    with open('keys/private_key.pem', 'wb') as f:
        f.write(private_pem)
    
    # 保存公钥
    with open('keys/public_key.pem', 'wb') as f:
        f.write(public_pem)
    
    print("RSA密钥对生成成功！")
    print("私钥: keys/private_key.pem")
    print("公钥: keys/public_key.pem")


if __name__ == "__main__":
    generate_rsa_keys()
