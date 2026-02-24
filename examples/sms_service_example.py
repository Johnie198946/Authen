"""
短信服务使用示例

演示如何使用短信服务发送验证码和通知短信。
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from services.notification.sms_service import sms_service
from shared.notification_publisher import publish_verification_sms, publish_sms_notification


def example_direct_sms():
    """示例：直接使用SMS服务发送短信"""
    print("=== 直接使用SMS服务示例 ===")
    print("注意：需要先在数据库中配置短信服务")
    
    # 发送验证码短信
    success = sms_service.send_verification_sms(
        to_phone="+8613800138000",
        verification_code="123456"
    )
    
    if success:
        print("✓ 验证码短信发送成功")
    else:
        print("✗ 验证码短信发送失败")
    
    print()


def example_custom_sms():
    """示例：发送自定义短信"""
    print("=== 自定义短信示例 ===")
    
    # 发送自定义内容的短信
    success = sms_service.send_sms(
        to_phone="+8613800138000",
        content="【统一认证平台】您的账号在新设备上登录，如非本人操作请及时修改密码。"
    )
    
    if success:
        print("✓ 自定义短信发送成功")
    else:
        print("✗ 自定义短信发送失败")
    
    print()


def example_template_sms():
    """示例：使用模板发送短信"""
    print("=== 模板短信示例 ===")
    
    # 使用模板发送短信
    success = sms_service.send_sms(
        to_phone="+8613800138000",
        content="",  # 内容将从模板获取
        template_name="sms_verification",
        template_variables={
            'code': '654321'
        }
    )
    
    if success:
        print("✓ 模板短信发送成功")
    else:
        print("✗ 模板短信发送失败")
    
    print()


def example_queue_sms():
    """示例：通过消息队列发送短信"""
    print("=== 消息队列短信示例 ===")
    print("注意：需要启动RabbitMQ和通知服务消费者")
    
    # 发布验证短信到消息队列
    success = publish_verification_sms(
        to="+8613800138000",
        verification_code="789012"
    )
    
    if success:
        print("✓ 短信已发布到消息队列")
    else:
        print("✗ 短信发布失败")
    
    print()


def example_batch_sms():
    """示例：批量发送短信"""
    print("=== 批量发送短信示例 ===")
    
    phone_numbers = [
        "+8613800138000",
        "+8613800138001",
        "+8613800138002"
    ]
    
    success_count = 0
    for phone in phone_numbers:
        success = publish_sms_notification(
            to=phone,
            content="【统一认证平台】系统维护通知：我们将在今晚22:00-23:00进行系统维护，期间服务可能暂时不可用。"
        )
        if success:
            success_count += 1
    
    print(f"✓ 成功发布 {success_count}/{len(phone_numbers)} 条短信到消息队列")
    print()


def example_error_handling():
    """示例：错误处理"""
    print("=== 错误处理示例 ===")
    
    # 尝试发送到无效手机号
    success = sms_service.send_sms(
        to_phone="invalid_phone",
        content="测试短信"
    )
    
    if not success:
        print("✓ 正确处理了无效手机号")
    
    # 尝试发送空内容
    success = sms_service.send_sms(
        to_phone="+8613800138000",
        content=""
    )
    
    if not success:
        print("✓ 正确处理了空内容")
    
    print()


def print_configuration_guide():
    """打印配置指南"""
    print("=" * 60)
    print("短信服务配置指南")
    print("=" * 60)
    print()
    print("在使用短信服务之前，需要完成以下配置：")
    print()
    print("1. 在阿里云或腾讯云开通短信服务")
    print("2. 创建短信签名和模板")
    print("3. 在数据库中配置云服务信息")
    print("4. 运行初始化脚本创建短信模板")
    print()
    print("详细配置步骤请参考：")
    print("  services/notification/SMS_CONFIG_GUIDE.md")
    print()
    print("初始化短信模板：")
    print("  python scripts/init_sms_templates.py")
    print()
    print("=" * 60)
    print()


if __name__ == "__main__":
    print_configuration_guide()
    
    print("选择要运行的示例：")
    print("1. 直接使用SMS服务")
    print("2. 发送自定义短信")
    print("3. 使用模板发送短信")
    print("4. 通过消息队列发送短信")
    print("5. 批量发送短信")
    print("6. 错误处理示例")
    print("7. 运行所有示例")
    print()
    
    choice = input("请输入选项 (1-7): ").strip()
    
    if choice == "1":
        example_direct_sms()
    elif choice == "2":
        example_custom_sms()
    elif choice == "3":
        example_template_sms()
    elif choice == "4":
        example_queue_sms()
    elif choice == "5":
        example_batch_sms()
    elif choice == "6":
        example_error_handling()
    elif choice == "7":
        example_direct_sms()
        example_custom_sms()
        example_template_sms()
        example_queue_sms()
        example_batch_sms()
        example_error_handling()
    else:
        print("无效的选项")
