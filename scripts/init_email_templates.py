"""
初始化邮件模板

创建默认的邮件模板，包括：
- 邮箱验证模板
- 密码重置模板
- 订阅到期提醒模板
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.database import get_db
from shared.models.system import MessageTemplate
import uuid


def create_email_verification_template(db):
    """创建邮箱验证模板"""
    template = MessageTemplate(
        id=uuid.uuid4(),
        name="email_verification",
        type="email",
        subject="验证您的邮箱地址",
        content="""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
        .container { max-width: 600px; margin: 0 auto; padding: 20px; }
        .header { background-color: #4CAF50; color: white; padding: 20px; text-align: center; }
        .content { padding: 20px; background-color: #f9f9f9; }
        .button { display: inline-block; padding: 12px 24px; background-color: #4CAF50; color: white; text-decoration: none; border-radius: 4px; margin: 20px 0; }
        .footer { text-align: center; padding: 20px; font-size: 12px; color: #666; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>欢迎注册统一身份认证平台</h1>
        </div>
        <div class="content">
            <p>您好，</p>
            <p>感谢您注册我们的服务。请点击下面的按钮验证您的邮箱地址：</p>
            <p style="text-align: center;">
                <a href="{{ verification_link }}" class="button">验证邮箱</a>
            </p>
            <p>或者复制以下链接到浏览器中打开：</p>
            <p style="word-break: break-all; color: #666;">{{ verification_link }}</p>
            <p>如果您没有注册我们的服务，请忽略此邮件。</p>
        </div>
        <div class="footer">
            <p>此邮件由系统自动发送，请勿回复。</p>
            <p>&copy; 2024 统一身份认证平台. All rights reserved.</p>
        </div>
    </div>
</body>
</html>
        """,
        variables={
            "email": "收件人邮箱",
            "verification_link": "验证链接"
        }
    )
    
    # 检查是否已存在
    existing = db.query(MessageTemplate).filter(
        MessageTemplate.name == "email_verification"
    ).first()
    
    if existing:
        print("邮箱验证模板已存在，跳过创建")
        return existing
    
    db.add(template)
    db.commit()
    print("✓ 创建邮箱验证模板")
    return template


def create_password_reset_template(db):
    """创建密码重置模板"""
    template = MessageTemplate(
        id=uuid.uuid4(),
        name="password_reset",
        type="email",
        subject="重置您的密码",
        content="""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
        .container { max-width: 600px; margin: 0 auto; padding: 20px; }
        .header { background-color: #FF9800; color: white; padding: 20px; text-align: center; }
        .content { padding: 20px; background-color: #f9f9f9; }
        .button { display: inline-block; padding: 12px 24px; background-color: #FF9800; color: white; text-decoration: none; border-radius: 4px; margin: 20px 0; }
        .footer { text-align: center; padding: 20px; font-size: 12px; color: #666; }
        .warning { background-color: #fff3cd; border-left: 4px solid #ffc107; padding: 10px; margin: 15px 0; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>密码重置请求</h1>
        </div>
        <div class="content">
            <p>您好，</p>
            <p>我们收到了重置您账号密码的请求。请点击下面的按钮重置密码：</p>
            <p style="text-align: center;">
                <a href="{{ reset_link }}" class="button">重置密码</a>
            </p>
            <p>或者复制以下链接到浏览器中打开：</p>
            <p style="word-break: break-all; color: #666;">{{ reset_link }}</p>
            <div class="warning">
                <strong>安全提示：</strong>
                <ul>
                    <li>此链接将在24小时后失效</li>
                    <li>如果您没有请求重置密码，请忽略此邮件</li>
                    <li>请勿将此链接分享给他人</li>
                </ul>
            </div>
        </div>
        <div class="footer">
            <p>此邮件由系统自动发送，请勿回复。</p>
            <p>&copy; 2024 统一身份认证平台. All rights reserved.</p>
        </div>
    </div>
</body>
</html>
        """,
        variables={
            "email": "收件人邮箱",
            "reset_link": "重置链接"
        }
    )
    
    # 检查是否已存在
    existing = db.query(MessageTemplate).filter(
        MessageTemplate.name == "password_reset"
    ).first()
    
    if existing:
        print("密码重置模板已存在，跳过创建")
        return existing
    
    db.add(template)
    db.commit()
    print("✓ 创建密码重置模板")
    return template


def create_subscription_reminder_template(db):
    """创建订阅到期提醒模板"""
    template = MessageTemplate(
        id=uuid.uuid4(),
        name="subscription_reminder",
        type="email",
        subject="您的订阅即将到期",
        content="""
<!DOCTYPE html>
<html>
<head>
    <meta charset="UTF-8">
    <style>
        body { font-family: Arial, sans-serif; line-height: 1.6; color: #333; }
        .container { max-width: 600px; margin: 0 auto; padding: 20px; }
        .header { background-color: #2196F3; color: white; padding: 20px; text-align: center; }
        .content { padding: 20px; background-color: #f9f9f9; }
        .button { display: inline-block; padding: 12px 24px; background-color: #2196F3; color: white; text-decoration: none; border-radius: 4px; margin: 20px 0; }
        .footer { text-align: center; padding: 20px; font-size: 12px; color: #666; }
        .info-box { background-color: #e3f2fd; border-left: 4px solid #2196F3; padding: 15px; margin: 15px 0; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>订阅到期提醒</h1>
        </div>
        <div class="content">
            <p>您好，</p>
            <p>您的订阅即将到期，请及时续费以继续享受服务。</p>
            <div class="info-box">
                <p><strong>订阅计划：</strong>{{ plan_name }}</p>
                <p><strong>到期日期：</strong>{{ expiry_date }}</p>
            </div>
            <p>为了不影响您的使用，建议您尽快续费。</p>
            <p style="text-align: center;">
                <a href="https://auth.example.com/subscription" class="button">立即续费</a>
            </p>
            <p>如果您已经续费，请忽略此邮件。</p>
        </div>
        <div class="footer">
            <p>此邮件由系统自动发送，请勿回复。</p>
            <p>&copy; 2024 统一身份认证平台. All rights reserved.</p>
        </div>
    </div>
</body>
</html>
        """,
        variables={
            "email": "收件人邮箱",
            "plan_name": "订阅计划名称",
            "expiry_date": "到期日期"
        }
    )
    
    # 检查是否已存在
    existing = db.query(MessageTemplate).filter(
        MessageTemplate.name == "subscription_reminder"
    ).first()
    
    if existing:
        print("订阅到期提醒模板已存在，跳过创建")
        return existing
    
    db.add(template)
    db.commit()
    print("✓ 创建订阅到期提醒模板")
    return template


def main():
    """主函数"""
    print("开始初始化邮件模板...")
    
    db = next(get_db())
    try:
        create_email_verification_template(db)
        create_password_reset_template(db)
        create_subscription_reminder_template(db)
        
        print("\n✓ 邮件模板初始化完成！")
        
    except Exception as e:
        print(f"\n✗ 初始化失败: {e}")
        db.rollback()
        raise
    finally:
        db.close()


if __name__ == "__main__":
    main()
