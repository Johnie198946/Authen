# 通知服务 - 邮件发送功能

## 概述

通知服务实现了完整的SMTP邮件发送功能，支持：
- ✅ SMTP邮件发送（支持SSL/TLS）
- ✅ 邮件模板渲染（使用Jinja2）
- ✅ 发送失败重试机制
- ✅ 从数据库读取云服务配置
- ✅ 支持多种邮件服务提供商

## 功能特性

### 1. SMTP邮件发送

支持通过SMTP协议发送邮件，兼容主流邮件服务提供商：
- Gmail
- Outlook/Hotmail
- 阿里云邮件推送
- 腾讯企业邮箱
- 网易163邮箱
- 自定义SMTP服务器

### 2. 邮件模板渲染

使用Jinja2模板引擎渲染邮件内容：
- 支持HTML邮件
- 支持变量替换
- 支持条件语句和循环
- 模板存储在数据库中，便于管理

### 3. 发送失败重试

消息队列消费者实现了重试机制：
- 最多重试3次
- 每次重试间隔60秒
- 重试失败后记录日志

## 配置SMTP服务

### 方法1：使用配置脚本（推荐）

#### 交互式配置
```bash
python3 scripts/configure_smtp.py
```

按照提示选择邮件服务提供商并输入配置信息。

#### 命令行配置
```bash
# Gmail示例
python3 scripts/configure_smtp.py \
  --provider gmail \
  --username your-email@gmail.com \
  --password your-app-password \
  --from-email noreply@yourdomain.com

# 阿里云示例
python3 scripts/configure_smtp.py \
  --provider aliyun \
  --username your-aliyun-email@example.com \
  --password your-password

# 自定义SMTP服务器
python3 scripts/configure_smtp.py \
  --provider custom \
  --custom-host smtp.yourserver.com \
  --username your-username \
  --password your-password
```

### 方法2：直接在数据库中配置

在 `cloud_service_configs` 表中插入配置：

```sql
INSERT INTO cloud_service_configs (id, service_type, provider, config, is_active)
VALUES (
  gen_random_uuid(),
  'email',
  'gmail',
  '{
    "smtp_host": "smtp.gmail.com",
    "smtp_port": 587,
    "use_ssl": false,
    "use_tls": true,
    "username": "your-email@gmail.com",
    "password": "your-app-password",
    "from_email": "noreply@yourdomain.com"
  }'::jsonb,
  true
);
```

## 初始化邮件模板

运行以下脚本创建默认邮件模板：

```bash
python3 scripts/init_email_templates.py
```

这将创建以下模板：
- `email_verification` - 邮箱验证模板
- `password_reset` - 密码重置模板
- `subscription_reminder` - 订阅到期提醒模板

## 使用邮件服务

### 在代码中使用

```python
from services.notification.email_service import email_service

# 发送简单邮件
email_service.send_email(
    to_email='user@example.com',
    subject='Welcome',
    body='<h1>Welcome to our platform!</h1>',
    html=True
)

# 使用模板发送邮件
email_service.send_email(
    to_email='user@example.com',
    subject='',  # 将从模板获取
    body='',  # 将从模板获取
    template_name='email_verification',
    template_variables={
        'email': 'user@example.com',
        'verification_link': 'https://example.com/verify?token=abc123'
    }
)

# 使用便捷方法
email_service.send_verification_email(
    to_email='user@example.com',
    verification_link='https://example.com/verify?token=abc123'
)
```

### 通过消息队列发送

发送消息到RabbitMQ队列：

```python
import pika
import json

connection = pika.BlockingConnection(
    pika.URLParameters('amqp://authuser:authpass123@localhost:5672')
)
channel = connection.channel()

# 发送邮件消息
message = {
    'type': 'email',
    'to': 'user@example.com',
    'subject': 'Test Email',
    'body': '<h1>Hello!</h1>',
    'html': True
}

channel.basic_publish(
    exchange='',
    routing_key='notifications.email',
    body=json.dumps(message),
    properties=pika.BasicProperties(delivery_mode=2)  # 持久化
)

connection.close()
```

使用模板：

```python
message = {
    'type': 'email',
    'to': 'user@example.com',
    'template': 'email_verification',
    'template_variables': {
        'email': 'user@example.com',
        'verification_link': 'https://example.com/verify?token=abc123'
    }
}
```

## 邮件模板管理

### 模板结构

邮件模板存储在 `message_templates` 表中，包含以下字段：
- `name` - 模板名称（唯一）
- `type` - 模板类型（email或sms）
- `subject` - 邮件主题（支持变量）
- `content` - 邮件正文（支持HTML和变量）
- `variables` - 模板变量说明

### 模板语法

使用Jinja2模板语法：

```html
<!-- 变量替换 -->
Hello {{ username }}!

<!-- 条件语句 -->
{% if is_premium %}
  <p>You are a premium member!</p>
{% else %}
  <p>Upgrade to premium for more features.</p>
{% endif %}

<!-- 循环 -->
<ul>
{% for item in items %}
  <li>{{ item }}</li>
{% endfor %}
</ul>
```

### 创建自定义模板

```python
from shared.database import get_db
from shared.models.system import MessageTemplate
import uuid

db = next(get_db())

template = MessageTemplate(
    id=uuid.uuid4(),
    name='custom_notification',
    type='email',
    subject='Important Notification',
    content='''
    <html>
    <body>
        <h1>Hello {{ name }}</h1>
        <p>{{ message }}</p>
    </body>
    </html>
    ''',
    variables={
        'name': 'User name',
        'message': 'Notification message'
    }
)

db.add(template)
db.commit()
db.close()
```

## 常见问题

### Gmail配置

Gmail需要使用"应用专用密码"而不是账号密码：

1. 启用两步验证
2. 访问 https://myaccount.google.com/apppasswords
3. 生成应用专用密码
4. 使用该密码配置SMTP

### 阿里云邮件推送

1. 在阿里云控制台创建邮件推送服务
2. 配置发信域名并验证
3. 创建发信地址
4. 使用SMTP密码（不是控制台密码）

### 测试邮件发送

```python
from services.notification.email_service import email_service

# 测试配置是否正确
result = email_service.send_email(
    to_email='your-test-email@example.com',
    subject='Test Email',
    body='This is a test email.',
    html=False
)

if result:
    print("✓ 邮件发送成功")
else:
    print("✗ 邮件发送失败，请检查日志")
```

## 运行通知服务

启动消息队列消费者：

```bash
python3 services/notification/main.py
```

服务将监听以下队列：
- `notifications.email` - 邮件队列
- `notifications.sms` - 短信队列
- `notifications.retry` - 重试队列

## 监控和日志

邮件发送的所有操作都会记录日志：

```
2024-01-01 10:00:00 - notification - INFO - 收到消息: {'type': 'email', 'to': 'user@example.com', ...}
2024-01-01 10:00:00 - notification - INFO - 发送邮件到 user@example.com, 主题: Welcome
2024-01-01 10:00:01 - notification - INFO - 邮件发送成功: user@example.com
```

失败时会记录详细错误：

```
2024-01-01 10:00:00 - notification - ERROR - SMTP认证失败: (535, b'Authentication failed')
2024-01-01 10:00:00 - notification - WARNING - 消息处理失败，准备重试
```

## 性能优化

1. **连接池**：考虑使用SMTP连接池减少连接开销
2. **批量发送**：对于大量邮件，考虑批量发送
3. **异步处理**：使用消息队列异步处理邮件发送
4. **限流**：避免触发邮件服务商的发送限制

## 安全建议

1. **加密存储**：数据库中的密码应该加密存储
2. **使用TLS/SSL**：始终使用加密连接
3. **限制发送频率**：防止被用于垃圾邮件
4. **验证收件人**：确保收件人邮箱有效
5. **SPF/DKIM配置**：配置域名的SPF和DKIM记录提高送达率

## 相关文件

- `services/notification/email_service.py` - 邮件服务实现
- `services/notification/main.py` - 消息队列消费者
- `scripts/configure_smtp.py` - SMTP配置脚本
- `scripts/init_email_templates.py` - 模板初始化脚本
- `tests/test_email_service.py` - 单元测试

## 验证需求

此实现满足以下需求：
- **需求 1.1** - 邮箱注册验证邮件发送
- **需求 3.6** - 订阅到期提醒邮件发送
- **需求 8.1, 8.2** - 云服务配置管理
- **需求 8.3, 8.4** - 邮件模板管理
