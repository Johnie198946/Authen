"""
初始化短信模板

该脚本在数据库中创建默认的短信模板。
"""
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from shared.database import get_db
from shared.models.system import MessageTemplate


def init_sms_templates():
    """初始化短信模板"""
    db = next(get_db())
    
    try:
        # 短信验证码模板
        verification_template = db.query(MessageTemplate).filter(
            MessageTemplate.name == 'sms_verification'
        ).first()
        
        if not verification_template:
            verification_template = MessageTemplate(
                name='sms_verification',
                type='sms',
                content='【统一认证平台】您的验证码是: {{ code }}，15分钟内有效。请勿泄露给他人。',
                variables={
                    'code': '验证码',
                    # 阿里云模板CODE（需要在阿里云控制台创建模板后填写）
                    'template_code': 'SMS_123456789',
                    # 腾讯云模板ID（需要在腾讯云控制台创建模板后填写）
                    'template_id': '123456'
                }
            )
            db.add(verification_template)
            print("✓ 创建短信验证码模板")
        else:
            print("- 短信验证码模板已存在")
        
        # 登录通知模板
        login_notification_template = db.query(MessageTemplate).filter(
            MessageTemplate.name == 'sms_login_notification'
        ).first()
        
        if not login_notification_template:
            login_notification_template = MessageTemplate(
                name='sms_login_notification',
                type='sms',
                content='【统一认证平台】您的账号在新设备上登录，登录时间: {{ login_time }}，如非本人操作请及时修改密码。',
                variables={
                    'login_time': '登录时间',
                    'template_code': 'SMS_987654321',
                    'template_id': '654321'
                }
            )
            db.add(login_notification_template)
            print("✓ 创建登录通知模板")
        else:
            print("- 登录通知模板已存在")
        
        # 订阅到期提醒模板
        subscription_reminder_template = db.query(MessageTemplate).filter(
            MessageTemplate.name == 'sms_subscription_reminder'
        ).first()
        
        if not subscription_reminder_template:
            subscription_reminder_template = MessageTemplate(
                name='sms_subscription_reminder',
                type='sms',
                content='【统一认证平台】您的{{ plan_name }}订阅将在{{ days }}天后到期，请及时续费。',
                variables={
                    'plan_name': '订阅计划名称',
                    'days': '剩余天数',
                    'template_code': 'SMS_111222333',
                    'template_id': '789012'
                }
            )
            db.add(subscription_reminder_template)
            print("✓ 创建订阅到期提醒模板")
        else:
            print("- 订阅到期提醒模板已存在")
        
        db.commit()
        print("\n短信模板初始化完成！")
        print("\n注意：")
        print("1. 请在阿里云或腾讯云控制台创建对应的短信模板")
        print("2. 将模板CODE/ID更新到数据库中的message_templates表")
        print("3. 模板内容需要与云服务商审核通过的模板一致")
        
    except Exception as e:
        db.rollback()
        print(f"初始化短信模板失败: {e}")
        raise
    finally:
        db.close()


if __name__ == "__main__":
    init_sms_templates()
