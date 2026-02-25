# Implementation Plan: 验证码认证 (Verification Code Auth)

## Overview

在现有 Auth Service 和 Admin UI 基础上，增量实现验证码认证全链路：后端新增邮箱验证码发送、验证码登录（手机/邮箱）、修改邮箱注册为验证码方式、频率限制；前端重构登录页面为多 Tab 切换、新增注册页面、扩展 API Client。

## Tasks

- [x] 1. 后端验证码基础设施与邮箱验证码发送
  - [x] 1.1 添加辅助函数和请求模型
    - 在 `services/auth/main.py` 中新增 `SendEmailCodeRequest`、`PhoneCodeLoginRequest`、`EmailCodeLoginRequest` 请求模型
    - 新增辅助函数：`generate_verification_code()`、`check_rate_limit()`、`set_rate_limit()`、`store_verification_code()`、`verify_and_delete_code()`
    - 修改 `EmailRegisterRequest` 添加 `verification_code` 字段
    - _Requirements: 1.1, 7.1, 7.3_

  - [x] 1.2 实现 `POST /api/v1/auth/send-email-code` 端点
    - 校验邮箱格式，无效返回 400
    - 检查频率限制（`code_rate:email:{email}`），被限制返回 429
    - 生成 6 位验证码，存储到 Redis（`email_code:{email}`，TTL=300s）
    - 设置频率限制 key（TTL=60s）
    - 调用 EmailService 发送验证码邮件
    - DEBUG 模式下在响应中包含验证码
    - 邮件发送失败返回 500
    - _Requirements: 1.1, 1.2, 1.3, 1.4, 1.5, 1.6, 7.1, 7.2, 7.3_

  - [x] 1.3 为现有 `POST /api/v1/auth/send-sms` 端点添加频率限制
    - 在 `send_sms_code` 函数中添加 `check_rate_limit` 和 `set_rate_limit` 调用
    - 被限制时返回 429
    - _Requirements: 7.1, 7.2, 7.3_

  - [ ]* 1.4 编写邮箱验证码发送的属性测试
    - **Property 1: Verification code is always 6 digits and stored correctly**
    - **Property 2: Invalid email addresses are rejected**
    - **Property 10: Rate limiting prevents rapid code sending**
    - 在 `tests/test_verification_code_properties.py` 中使用 Hypothesis 实现
    - **Validates: Requirements 1.1, 1.4, 7.1, 7.2, 7.3**

  - [ ]* 1.5 编写邮箱验证码发送的单元测试
    - 在 `tests/test_verification_code_auth.py` 中测试：发送成功流程、DEBUG 模式响应包含验证码、邮件发送失败返回 500、频率限制边界
    - _Requirements: 1.1, 1.2, 1.5, 1.6, 7.2_

- [x] 2. 验证码登录端点（手机 + 邮箱）
  - [x] 2.1 实现 `POST /api/v1/auth/login/phone-code` 端点
    - 从 Redis 获取 `sms_code:{phone}` 并验证
    - 验证码不匹配/过期返回 401（"验证码无效或已过期"）
    - 用户不存在返回 401（"用户不存在"）
    - 账号锁定返回 403（含剩余锁定时间）
    - 账号未激活返回 403（"账号未激活"）
    - 验证成功：重置 failed_login_attempts、更新 last_login_at、删除验证码、返回 LoginResponse
    - _Requirements: 2.1, 2.2, 2.3, 2.4, 2.5, 2.6, 2.7_

  - [x] 2.2 实现 `POST /api/v1/auth/login/email-code` 端点
    - 从 Redis 获取 `email_code:{email}` 并验证
    - 错误处理逻辑与手机验证码登录一致
    - 验证成功：重置 failed_login_attempts、更新 last_login_at、删除验证码、返回 LoginResponse
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5, 3.6, 3.7_

  - [ ]* 2.3 编写验证码登录的属性测试
    - **Property 3: Successful verification code login returns tokens and updates user state**
    - **Property 4: Verification codes are single-use**
    - **Property 5: Non-matching or expired codes are rejected**
    - **Property 6: Non-existent users are rejected for code login**
    - **Property 7: Account status enforcement for code login**
    - 在 `tests/test_verification_code_properties.py` 中使用 Hypothesis 实现
    - **Validates: Requirements 2.1–2.7, 3.1–3.7**

  - [ ]* 2.4 编写验证码登录的单元测试
    - 在 `tests/test_verification_code_auth.py` 中测试手机/邮箱验证码登录的成功和各种失败场景
    - _Requirements: 2.1–2.7, 3.1–3.7_

- [x] 3. Checkpoint - 后端验证码发送与登录
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. 邮箱验证码注册
  - [x] 4.1 修改 `POST /api/v1/auth/register/email` 端点
    - 将现有邮箱注册从验证链接方式改为验证码方式
    - 接收 `verification_code` 字段，从 Redis 验证 `email_code:{email}`
    - 验证码不匹配/过期返回 400（"验证码无效或已过期"）
    - 邮箱已注册返回 409（"邮箱已被注册"）
    - 用户名已使用返回 409（"用户名已被使用"）
    - 密码强度不足返回 400
    - 注册成功：创建用户（status='active'）、删除验证码
    - _Requirements: 4.1, 4.2, 4.3, 4.4, 4.5, 4.6_

  - [ ]* 4.2 编写邮箱验证码注册的属性测试
    - **Property 8: Email registration creates active user and deletes code**
    - **Property 9: Registration uniqueness constraints**
    - 在 `tests/test_verification_code_properties.py` 中使用 Hypothesis 实现
    - **Validates: Requirements 4.1, 4.2, 4.4, 4.5**

  - [ ]* 4.3 编写邮箱验证码注册的单元测试
    - 在 `tests/test_verification_code_auth.py` 中测试注册成功、各种错误场景
    - _Requirements: 4.1–4.6_

- [x] 5. Checkpoint - 后端全部端点完成
  - Ensure all tests pass, ask the user if questions arise.

- [x] 6. 前端 API Client 扩展与 useCountdown Hook
  - [x] 6.1 扩展 `admin-ui/src/api/client.ts`
    - 在 `authApi` 对象中新增 `sendEmailCode`、`sendSmsCode`、`loginWithPhoneCode`、`loginWithEmailCode`、`registerWithEmailCode` 方法
    - _Requirements: 8.1, 8.2, 8.3, 8.4, 8.5_

  - [x] 6.2 创建 `admin-ui/src/hooks/useCountdown.ts`
    - 实现 `useCountdown(seconds: number = 60)` Hook，返回 `{ countdown, isCounting, start }`
    - 使用 `setInterval` + `useEffect` 清理，供登录和注册页面复用
    - _Requirements: 5.5, 5.6, 6.4_

- [x] 7. 前端登录页面重构
  - [x] 7.1 重构 `admin-ui/src/pages/Login.tsx` 为多 Tab 登录
    - 使用 Ant Design `Tabs` 组件实现三个 Tab：密码登录、手机验证码登录、邮箱验证码登录
    - 密码登录 Tab 保留现有逻辑
    - 手机验证码 Tab：手机号输入 + 验证码输入 + 发送验证码按钮（60 秒倒计时）
    - 邮箱验证码 Tab：邮箱输入 + 验证码输入 + 发送验证码按钮（60 秒倒计时）
    - 表单验证：手机号/邮箱格式校验，无效时显示错误阻止发送
    - 登录成功后处理逻辑与密码登录一致（存储 token、导航到 dashboard 或 change-password）
    - 添加注册页面链接
    - _Requirements: 5.1, 5.2, 5.3, 5.4, 5.5, 5.6, 5.7, 5.8, 6.7_

  - [ ]* 7.2 编写 Login 页面单元测试
    - 使用 Vitest + React Testing Library 测试：三个 Tab 渲染和切换、发送验证码倒计时、表单验证、登录成功导航
    - _Requirements: 5.1–5.8_

- [x] 8. 前端注册页面
  - [x] 8.1 创建 `admin-ui/src/pages/Register.tsx`
    - 使用 Ant Design `Tabs` 组件实现两个 Tab：邮箱注册、手机注册
    - 邮箱注册 Tab：邮箱 + 用户名 + 密码 + 确认密码 + 验证码 + 发送验证码按钮
    - 手机注册 Tab：手机号 + 用户名 + 密码 + 确认密码 + 验证码 + 发送验证码按钮
    - 密码不匹配时显示 "两次密码输入不一致"
    - 注册成功后导航到登录页面
    - 添加登录页面链接
    - _Requirements: 6.1, 6.2, 6.3, 6.4, 6.5, 6.6, 6.7_

  - [x] 8.2 在路由中注册 Register 页面
    - 在应用路由配置中添加 `/register` 路由指向 `Register.tsx`
    - _Requirements: 6.7_

  - [ ]* 8.3 编写 Register 页面单元测试
    - 使用 Vitest + React Testing Library 测试：两个 Tab 渲染和切换、密码不匹配验证、发送验证码倒计时、注册成功导航
    - **Property 11: Password mismatch validation**
    - _Requirements: 6.1–6.7_

- [x] 9. Final checkpoint - 全部功能完成
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- 后端使用 Python (FastAPI + pytest + Hypothesis)，前端使用 TypeScript (React + Vitest)
- 属性测试在 `tests/test_verification_code_properties.py`，单元测试在 `tests/test_verification_code_auth.py`
- 每个属性测试须注释引用设计文档中的 Property 编号
- Checkpoints 确保增量验证，避免后期集成问题
