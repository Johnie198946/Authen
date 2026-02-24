"""
通知服务集成示例

演示如何在其他服务中使用通知服务发送邮件和短信
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.notification_publisher import (
    publish_email_notification,
    publish_sms_notification,
    publish_verification_email,
    publish_verification_sms,
    publish_subscription_expiry_reminder
)


def example_email_registration():
    """示例：邮箱注册发送验证邮件"""
    print("=== 邮箱注册示例 ===")
    
    # 用户注册时生成验证码
    verification_code = "123456"
    user_email = "newuser@example.com"
    username = "newuser"
    
    # 发送验证邮件
    success = publish_verification_email(
        to=user_email,
        verification_code=verification_code,
        username=username
    )
    
    if success:
        print(f"✓ 验证邮件已发送到队列: {user_email}")
    else:
        print(f"✗ 验证邮件发送失败")
    
    print()


def example_phone_registration():
    """示例：手机注册发送验证短信"""
    print("=== 手机注册示例 ===")
    
    # 用户注册时生成验证码
    verification_code = "654321"
    phone_number = "+8613800138000"
    
    # 发送验证短信
    success = publish_verification_sms(
        to=phone_number,
        verification_code=verification_code
    )
    
    if success:
        print(f"✓ 验证短信已发送到队列: {phone_number}")
    else:
        print(f"✗ 验证短信发送失败")
    
    print()


def example_subscription_reminder():
    """示例：订阅到期提醒"""
    print("=== 订阅到期提醒示例 ===")
    
    # 检测到订阅即将到期
    user_email = "subscriber@example.com"
    username = "subscriber"
    days_remaining = 7
    plan_name = "Premium Plan"
    
    # 发送到期提醒
    success = publish_subscription_expiry_reminder(
        to=user_email,
        username=username,
        days_remaining=days_remaining,
        plan_name=plan_name
    )
    
    if success:
        print(f"✓ 到期提醒已发送到队列: {user_email}")
        print(f"  订阅计划: {plan_name}")
        print(f"  剩余天数: {days_remaining}")
    else:
        print(f"✗ 到期提醒发送失败")
    
    print()


def example_custom_email():
    """示例：自定义邮件通知"""
    print("=== 自定义邮件通知示例 ===")
    
    # 发送自定义邮件
    success = publish_email_notification(
        to="admin@example.com",
        subject="系统告警",
        body="检测到异常登录行为，请及时处理。",
        template="security_alert",
        alert_type="suspicious_login",
        ip_address="192.168.1.100",
        timestamp="2024-01-15 10:30:00"
    )
    
    if success:
        print(f"✓ 自定义邮件已发送到队列")
    else:
        print(f"✗ 自定义邮件发送失败")
    
    print()


def example_custom_sms():
    """示例：自定义短信通知"""
    print("=== 自定义短信通知示例 ===")
    
    # 发送自定义短信
    success = publish_sms_notification(
        to="+8613800138000",
        content="【统一认证平台】您的账号在新设备上登录，如非本人操作请及时修改密码。",
        template="security_alert",
        alert_type="new_device_login"
    )
    
    if success:
        print(f"✓ 自定义短信已发送到队列")
    else:
        print(f"✗ 自定义短信发送失败")
    
    print()


def example_batch_notifications():
    """示例：批量发送通知"""
    print("=== 批量通知示例 ===")
    
    # 批量发送订阅到期提醒
    users = [
        {"email": "user1@example.com", "username": "user1", "plan": "Basic Plan", "days": 7},
        {"email": "user2@example.com", "username": "user2", "plan": "Premium Plan", "days": 5},
        {"email": "user3@example.com", "username": "user3", "plan": "Enterprise Plan", "days": 3},
    ]
    
    success_count = 0
    for user in users:
        success = publish_subscription_expiry_reminder(
            to=user["email"],
            username=user["username"],
            days_remaining=user["days"],
            plan_name=user["plan"]
        )
        if success:
            success_count += 1
    
    print(f"✓ 批量发送完成: {success_count}/{len(users)} 成功")
    print()


def example_error_handling():
    """示例：错误处理"""
    print("=== 错误处理示例 ===")
    
    # 尝试发送邮件（可能失败）
    try:
        success = publish_email_notification(
            to="test@example.com",
            subject="测试",
            body="测试邮件"
        )
        
        if success:
            print("✓ 邮件发送成功")
        else:
            print("✗ 邮件发送失败，但程序继续运行")
            # 可以记录日志、发送告警等
            
    except Exception as e:
        print(f"✗ 发生异常: {e}")
        # 异常处理逻辑
    
    print()


def main():
    """运行所有示例"""
    print("=" * 60)
    print("通知服务集成示例")
    print("=" * 60)
    print()
    
    print("注意：这些示例会将消息发送到RabbitMQ队列。")
    print("请确保：")
    print("1. RabbitMQ服务正在运行")
    print("2. 通知服务消费者正在运行（python3 services/notification/main.py）")
    print()
    
    input("按Enter键继续...")
    print()
    
    # 运行各个示例
    example_email_registration()
    example_phone_registration()
    example_subscription_reminder()
    example_custom_email()
    example_custom_sms()
    example_batch_notifications()
    example_error_handling()
    
    print("=" * 60)
    print("所有示例执行完成！")
    print("请查看通知服务消费者的日志以确认消息处理情况。")
    print("=" * 60)


if __name__ == "__main__":
    main()
