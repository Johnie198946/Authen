"""
配置SMTP邮件服务

此脚本用于在数据库中配置SMTP邮件服务。
支持多种邮件服务提供商（Gmail, Outlook, 阿里云, 腾讯云等）。
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.database import get_db
from shared.models.system import CloudServiceConfig
import uuid


# 常见邮件服务提供商的SMTP配置模板
SMTP_PROVIDERS = {
    "gmail": {
        "smtp_host": "smtp.gmail.com",
        "smtp_port": 587,
        "use_ssl": False,
        "use_tls": True,
        "description": "Gmail (需要开启应用专用密码)"
    },
    "outlook": {
        "smtp_host": "smtp-mail.outlook.com",
        "smtp_port": 587,
        "use_ssl": False,
        "use_tls": True,
        "description": "Outlook/Hotmail"
    },
    "aliyun": {
        "smtp_host": "smtpdm.aliyun.com",
        "smtp_port": 465,
        "use_ssl": True,
        "use_tls": False,
        "description": "阿里云邮件推送"
    },
    "tencent": {
        "smtp_host": "smtp.qq.com",
        "smtp_port": 465,
        "use_ssl": True,
        "use_tls": False,
        "description": "腾讯企业邮箱"
    },
    "163": {
        "smtp_host": "smtp.163.com",
        "smtp_port": 465,
        "use_ssl": True,
        "use_tls": False,
        "description": "网易163邮箱"
    },
    "custom": {
        "smtp_host": "",
        "smtp_port": 587,
        "use_ssl": False,
        "use_tls": True,
        "description": "自定义SMTP服务器"
    }
}


def list_providers():
    """列出所有支持的邮件服务提供商"""
    print("\n支持的邮件服务提供商：")
    print("-" * 50)
    for key, config in SMTP_PROVIDERS.items():
        print(f"{key:12} - {config['description']}")
    print("-" * 50)


def configure_smtp(provider: str, username: str, password: str, from_email: str = None, custom_host: str = None):
    """
    配置SMTP服务
    
    Args:
        provider: 服务提供商（gmail, outlook, aliyun等）
        username: SMTP用户名
        password: SMTP密码
        from_email: 发件人邮箱（可选，默认使用username）
        custom_host: 自定义SMTP主机（仅当provider为custom时使用）
    """
    if provider not in SMTP_PROVIDERS:
        print(f"错误：不支持的提供商 '{provider}'")
        list_providers()
        return False
    
    # 获取提供商配置模板
    template = SMTP_PROVIDERS[provider].copy()
    
    # 如果是自定义提供商，需要指定主机
    if provider == "custom":
        if not custom_host:
            print("错误：自定义提供商需要指定 smtp_host")
            return False
        template["smtp_host"] = custom_host
    
    # 构建配置
    config = {
        "smtp_host": template["smtp_host"],
        "smtp_port": template["smtp_port"],
        "use_ssl": template["use_ssl"],
        "use_tls": template["use_tls"],
        "username": username,
        "password": password,
        "from_email": from_email or username
    }
    
    # 保存到数据库
    db = next(get_db())
    try:
        # 检查是否已存在配置
        existing = db.query(CloudServiceConfig).filter(
            CloudServiceConfig.service_type == 'email',
            CloudServiceConfig.provider == provider
        ).first()
        
        if existing:
            # 更新现有配置
            existing.config = config
            existing.is_active = True
            print(f"✓ 更新现有的 {provider} SMTP配置")
        else:
            # 创建新配置
            new_config = CloudServiceConfig(
                id=uuid.uuid4(),
                service_type='email',
                provider=provider,
                config=config,
                is_active=True
            )
            db.add(new_config)
            print(f"✓ 创建新的 {provider} SMTP配置")
        
        # 将其他邮件配置设为非活跃
        db.query(CloudServiceConfig).filter(
            CloudServiceConfig.service_type == 'email',
            CloudServiceConfig.provider != provider
        ).update({"is_active": False})
        
        db.commit()
        
        print("\n配置详情：")
        print(f"  提供商: {provider}")
        print(f"  SMTP主机: {config['smtp_host']}")
        print(f"  SMTP端口: {config['smtp_port']}")
        print(f"  使用SSL: {config['use_ssl']}")
        print(f"  使用TLS: {config['use_tls']}")
        print(f"  用户名: {config['username']}")
        print(f"  发件人: {config['from_email']}")
        print("\n✓ SMTP配置保存成功！")
        
        return True
        
    except Exception as e:
        print(f"\n✗ 配置失败: {e}")
        db.rollback()
        return False
    finally:
        db.close()


def interactive_configure():
    """交互式配置SMTP"""
    print("\n=== SMTP邮件服务配置 ===\n")
    
    list_providers()
    
    provider = input("\n请选择提供商: ").strip().lower()
    if provider not in SMTP_PROVIDERS:
        print(f"错误：不支持的提供商 '{provider}'")
        return
    
    print(f"\n配置 {SMTP_PROVIDERS[provider]['description']}")
    print("-" * 50)
    
    custom_host = None
    if provider == "custom":
        custom_host = input("SMTP主机地址: ").strip()
    
    username = input("SMTP用户名: ").strip()
    password = input("SMTP密码: ").strip()
    from_email = input(f"发件人邮箱 (留空使用 {username}): ").strip()
    
    if not username or not password:
        print("错误：用户名和密码不能为空")
        return
    
    # 确认配置
    print("\n请确认以下配置：")
    print(f"  提供商: {provider}")
    if custom_host:
        print(f"  SMTP主机: {custom_host}")
    print(f"  用户名: {username}")
    print(f"  密码: {'*' * len(password)}")
    print(f"  发件人: {from_email or username}")
    
    confirm = input("\n确认配置？(y/n): ").strip().lower()
    if confirm != 'y':
        print("已取消配置")
        return
    
    # 执行配置
    configure_smtp(provider, username, password, from_email or None, custom_host)


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='配置SMTP邮件服务')
    parser.add_argument('--provider', help='邮件服务提供商')
    parser.add_argument('--username', help='SMTP用户名')
    parser.add_argument('--password', help='SMTP密码')
    parser.add_argument('--from-email', help='发件人邮箱')
    parser.add_argument('--custom-host', help='自定义SMTP主机（仅用于custom提供商）')
    parser.add_argument('--list', action='store_true', help='列出支持的提供商')
    
    args = parser.parse_args()
    
    if args.list:
        list_providers()
        return
    
    if args.provider and args.username and args.password:
        # 命令行模式
        configure_smtp(
            args.provider,
            args.username,
            args.password,
            args.from_email,
            args.custom_host
        )
    else:
        # 交互式模式
        interactive_configure()


if __name__ == "__main__":
    main()
