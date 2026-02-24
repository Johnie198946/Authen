# 短信服务配置指南

本指南说明如何配置阿里云和腾讯云短信服务。

## 阿里云短信服务配置

### 1. 获取AccessKey

1. 登录[阿里云控制台](https://ram.console.aliyun.com/manage/ak)
2. 创建AccessKey ID和AccessKey Secret
3. 保存好这两个密钥（Secret只显示一次）

### 2. 创建短信签名

1. 进入[短信服务控制台](https://dysms.console.aliyun.com/)
2. 点击"国内消息" -> "签名管理" -> "添加签名"
3. 填写签名名称（如：统一认证平台）
4. 选择签名来源和用途
5. 提交审核（通常1-2个工作日）

### 3. 创建短信模板

1. 在短信服务控制台，点击"模板管理" -> "添加模板"
2. 创建以下模板：

**验证码模板示例：**
- 模板名称：验证码通知
- 模板内容：`您的验证码是: ${code}，15分钟内有效。请勿泄露给他人。`
- 模板类型：验证码
- 提交审核后获得模板CODE（如：SMS_123456789）

**登录通知模板示例：**
- 模板名称：登录通知
- 模板内容：`您的账号在新设备上登录，登录时间: ${login_time}，如非本人操作请及时修改密码。`
- 模板类型：通知
- 提交审核后获得模板CODE

### 4. 在数据库中配置

使用以下SQL插入配置：

```sql
INSERT INTO cloud_service_configs (id, service_type, provider, config, is_active, created_at, updated_at)
VALUES (
    gen_random_uuid(),
    'sms',
    'aliyun',
    '{
        "access_key_id": "YOUR_ACCESS_KEY_ID",
        "access_key_secret": "YOUR_ACCESS_KEY_SECRET",
        "sign_name": "统一认证平台",
        "endpoint": "dysmsapi.aliyuncs.com"
    }'::jsonb,
    true,
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
);
```

### 5. 更新短信模板CODE

运行初始化脚本后，更新模板CODE：

```sql
UPDATE message_templates
SET variables = jsonb_set(variables, '{template_code}', '"SMS_123456789"')
WHERE name = 'sms_verification';
```

## 腾讯云短信服务配置

### 1. 获取密钥

1. 登录[腾讯云控制台](https://console.cloud.tencent.com/cam/capi)
2. 创建SecretId和SecretKey
3. 保存好这两个密钥

### 2. 创建短信应用

1. 进入[短信控制台](https://console.cloud.tencent.com/smsv2)
2. 点击"应用管理" -> "创建应用"
3. 填写应用名称
4. 创建后获得SDK AppID

### 3. 创建短信签名

1. 在短信控制台，点击"国内短信" -> "签名管理" -> "创建签名"
2. 填写签名内容（如：统一认证平台）
3. 选择签名类型和用途
4. 提交审核（通常1-2个工作日）

### 4. 创建短信模板

1. 在短信控制台，点击"正文模板管理" -> "创建正文模板"
2. 创建以下模板：

**验证码模板示例：**
- 模板名称：验证码通知
- 模板内容：`您的验证码是: {1}，15分钟内有效。请勿泄露给他人。`
- 模板类型：验证码类
- 提交审核后获得模板ID（如：123456）

**注意：** 腾讯云模板使用 {1}, {2}, {3} 作为变量占位符

### 5. 在数据库中配置

使用以下SQL插入配置：

```sql
INSERT INTO cloud_service_configs (id, service_type, provider, config, is_active, created_at, updated_at)
VALUES (
    gen_random_uuid(),
    'sms',
    'tencent',
    '{
        "secret_id": "YOUR_SECRET_ID",
        "secret_key": "YOUR_SECRET_KEY",
        "sdk_app_id": "YOUR_SDK_APP_ID",
        "sign_name": "统一认证平台",
        "endpoint": "sms.tencentcloudapi.com"
    }'::jsonb,
    true,
    CURRENT_TIMESTAMP,
    CURRENT_TIMESTAMP
);
```

### 6. 更新短信模板ID

运行初始化脚本后，更新模板ID：

```sql
UPDATE message_templates
SET variables = jsonb_set(variables, '{template_id}', '"123456"')
WHERE name = 'sms_verification';
```

## 测试短信发送

### 使用Python脚本测试

```python
from services.notification.sms_service import sms_service

# 测试发送验证码
success = sms_service.send_verification_sms(
    to_phone="+8613800138000",
    verification_code="123456"
)

print(f"发送结果: {'成功' if success else '失败'}")
```

### 使用消息队列测试

```python
from shared.notification_publisher import publish_verification_sms

# 发布验证短信到消息队列
success = publish_verification_sms(
    to="+8613800138000",
    verification_code="123456"
)

print(f"发布结果: {'成功' if success else '失败'}")
```

## 常见问题

### 1. 短信发送失败

**可能原因：**
- AccessKey/SecretKey配置错误
- 短信签名未审核通过或配置错误
- 短信模板未审核通过或配置错误
- 手机号格式不正确
- 账户余额不足

**解决方法：**
- 检查日志中的错误信息
- 验证云服务商控制台中的配置
- 确保手机号包含国家码（如+86）
- 检查账户余额

### 2. 模板变量不匹配

**阿里云：**
- 模板变量使用 `${variable}` 格式
- 传递参数时使用字典：`{"code": "123456"}`

**腾讯云：**
- 模板变量使用 `{1}`, `{2}` 格式
- 传递参数时使用数组：`["123456"]`
- 参数顺序必须与模板中的序号对应

### 3. 签名验证失败

**阿里云：**
- 检查时间戳是否正确（UTC时间）
- 检查签名算法实现是否正确
- 检查参数编码是否符合规范

**腾讯云：**
- 检查TC3-HMAC-SHA256签名算法
- 检查请求头中的时间戳
- 检查Authorization头格式

## 安全建议

1. **密钥安全：**
   - 不要将密钥硬编码在代码中
   - 使用环境变量或密钥管理服务
   - 定期轮换密钥

2. **访问控制：**
   - 为短信服务创建专用的子账号
   - 只授予必要的权限（最小权限原则）
   - 启用MFA多因素认证

3. **监控告警：**
   - 监控短信发送量和失败率
   - 设置异常告警（如突然大量发送）
   - 定期审查发送日志

4. **防刷机制：**
   - 限制同一手机号的发送频率
   - 实现图形验证码
   - 监控IP地址和设备指纹

## 费用说明

### 阿里云
- 验证码短信：约0.045元/条
- 通知短信：约0.045元/条
- 按量付费，无最低消费

### 腾讯云
- 验证码短信：约0.045元/条
- 通知短信：约0.045元/条
- 可购买套餐包享受优惠

**建议：**
- 开发测试环境使用少量充值
- 生产环境根据实际需求购买套餐包
- 设置费用告警避免超支
