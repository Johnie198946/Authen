# Requirements Document

## Introduction

本功能为统一身份认证平台新增验证码认证能力，包括：邮箱验证码发送、邮箱验证码登录、手机验证码登录、邮箱验证码注册（替代原有的验证链接方式），以及前端登录/注册页面的多方式切换支持。

现有系统已具备短信验证码发送（`POST /api/v1/auth/send-sms`）、手机号注册（含验证码校验）、密码登录等能力。本需求在此基础上扩展验证码认证的完整链路。

## Glossary

- **Auth_Service**: 认证服务后端（FastAPI），运行在端口 8001，负责用户注册、登录、Token 管理
- **Email_Service**: 邮件发送服务，基于 SMTP，支持模板渲染，位于 `services/notification/email_service.py`
- **SMS_Service**: 短信发送服务，支持阿里云/腾讯云，位于 `services/notification/sms_service.py`
- **Redis_Store**: Redis 缓存，用于存储验证码及其过期时间
- **Verification_Code**: 6 位数字验证码，存储在 Redis 中，有效期 5 分钟
- **Login_Page**: 前端登录页面组件，位于 `admin-ui/src/pages/Login.tsx`
- **Register_Page**: 前端注册页面组件
- **API_Client**: 前端 API 调用层，位于 `admin-ui/src/api/client.ts`

## Requirements

### Requirement 1: 邮箱验证码发送

**User Story:** As a 用户, I want to 通过邮箱接收验证码, so that 我可以使用邮箱验证码进行登录或注册。

#### Acceptance Criteria

1. WHEN a valid email address is submitted to the send-email-code endpoint, THE Auth_Service SHALL generate a 6-digit Verification_Code and store it in Redis_Store with key pattern `email_code:{email}` and a 300-second TTL
2. WHEN a Verification_Code is generated for an email address, THE Auth_Service SHALL invoke Email_Service to send the Verification_Code to the specified email address
3. WHEN a send-email-code request is received for an email address that already has an unexpired Verification_Code in Redis_Store, THE Auth_Service SHALL overwrite the existing code with a new Verification_Code
4. IF the email address format is invalid, THEN THE Auth_Service SHALL return HTTP 400 with a descriptive error message
5. IF Email_Service fails to send the email, THEN THE Auth_Service SHALL return HTTP 500 with an error message indicating the send failure
6. WHEN running in DEBUG mode, THE Auth_Service SHALL include the Verification_Code in the response body for development testing

### Requirement 2: 手机验证码登录

**User Story:** As a 用户, I want to 使用手机号和验证码直接登录, so that 我不需要记住密码就能登录系统。

#### Acceptance Criteria

1. WHEN a valid phone number and matching Verification_Code are submitted to the phone-code login endpoint, THE Auth_Service SHALL authenticate the user and return access_token, refresh_token, and sso_session_token
2. WHEN a phone-code login is successful, THE Auth_Service SHALL reset the user's failed_login_attempts to 0 and update last_login_at
3. WHEN a phone-code login is successful, THE Auth_Service SHALL delete the used Verification_Code from Redis_Store
4. IF the submitted Verification_Code does not match the stored code or has expired, THEN THE Auth_Service SHALL return HTTP 401 with error message "验证码无效或已过期"
5. IF no user account exists with the submitted phone number, THEN THE Auth_Service SHALL return HTTP 401 with error message "用户不存在"
6. WHILE the user account status is "locked", THE Auth_Service SHALL reject phone-code login and return HTTP 403 with the remaining lock duration
7. WHILE the user account status is "pending_verification", THE Auth_Service SHALL reject phone-code login and return HTTP 403 with error message "账号未激活"

### Requirement 3: 邮箱验证码登录

**User Story:** As a 用户, I want to 使用邮箱和验证码直接登录, so that 我不需要记住密码就能登录系统。

#### Acceptance Criteria

1. WHEN a valid email address and matching Verification_Code are submitted to the email-code login endpoint, THE Auth_Service SHALL authenticate the user and return access_token, refresh_token, and sso_session_token
2. WHEN an email-code login is successful, THE Auth_Service SHALL reset the user's failed_login_attempts to 0 and update last_login_at
3. WHEN an email-code login is successful, THE Auth_Service SHALL delete the used Verification_Code from Redis_Store
4. IF the submitted Verification_Code does not match the stored code or has expired, THEN THE Auth_Service SHALL return HTTP 401 with error message "验证码无效或已过期"
5. IF no user account exists with the submitted email address, THEN THE Auth_Service SHALL return HTTP 401 with error message "用户不存在"
6. WHILE the user account status is "locked", THE Auth_Service SHALL reject email-code login and return HTTP 403 with the remaining lock duration
7. WHILE the user account status is "pending_verification", THE Auth_Service SHALL reject email-code login and return HTTP 403 with error message "账号未激活"

### Requirement 4: 邮箱验证码注册

**User Story:** As a 新用户, I want to 使用邮箱验证码完成注册, so that 我不需要点击验证链接就能快速激活账号。

#### Acceptance Criteria

1. WHEN a valid email, username, password, and matching Verification_Code are submitted to the email registration endpoint, THE Auth_Service SHALL create a new user with status "active"
2. WHEN email-code registration is successful, THE Auth_Service SHALL delete the used Verification_Code from Redis_Store
3. IF the submitted Verification_Code does not match the stored code for the email or has expired, THEN THE Auth_Service SHALL return HTTP 400 with error message "验证码无效或已过期"
4. IF the email address is already registered, THEN THE Auth_Service SHALL return HTTP 409 with error message "邮箱已被注册"
5. IF the username is already taken, THEN THE Auth_Service SHALL return HTTP 409 with error message "用户名已被使用"
6. IF the password does not meet strength requirements, THEN THE Auth_Service SHALL return HTTP 400 with a descriptive error message

### Requirement 5: 前端登录页面多方式支持

**User Story:** As a 用户, I want to 在登录页面切换不同的登录方式, so that 我可以选择最方便的方式登录。

#### Acceptance Criteria

1. THE Login_Page SHALL display three login method tabs: "密码登录", "手机验证码登录", "邮箱验证码登录"
2. WHEN the "密码登录" tab is selected, THE Login_Page SHALL display identifier and password input fields (preserving existing behavior)
3. WHEN the "手机验证码登录" tab is selected, THE Login_Page SHALL display phone number input and verification code input with a "发送验证码" button
4. WHEN the "邮箱验证码登录" tab is selected, THE Login_Page SHALL display email input and verification code input with a "发送验证码" button
5. WHEN the "发送验证码" button is clicked for phone login, THE Login_Page SHALL call the send-sms endpoint and start a 60-second countdown timer disabling the button
6. WHEN the "发送验证码" button is clicked for email login, THE Login_Page SHALL call the send-email-code endpoint and start a 60-second countdown timer disabling the button
7. WHEN a verification code login form is submitted, THE Login_Page SHALL call the corresponding login endpoint and handle the response identically to password login (store tokens, navigate to dashboard or change-password)
8. IF the phone number or email format is invalid, THEN THE Login_Page SHALL display a validation error before sending the request

### Requirement 6: 前端注册页面支持

**User Story:** As a 新用户, I want to 在注册页面选择邮箱或手机号注册, so that 我可以使用验证码快速完成注册。

#### Acceptance Criteria

1. THE Register_Page SHALL display two registration method tabs: "邮箱注册" and "手机注册"
2. WHEN the "邮箱注册" tab is selected, THE Register_Page SHALL display email, username, password, confirm password, and verification code fields with a "发送验证码" button
3. WHEN the "手机注册" tab is selected, THE Register_Page SHALL display phone number, username, password, confirm password, and verification code fields with a "发送验证码" button
4. WHEN the "发送验证码" button is clicked, THE Register_Page SHALL call the corresponding send-code endpoint and start a 60-second countdown timer disabling the button
5. WHEN registration is submitted with valid data, THE Register_Page SHALL call the corresponding registration endpoint and navigate to the login page on success
6. IF the password and confirm password fields do not match, THEN THE Register_Page SHALL display a validation error "两次密码输入不一致"
7. THE Login_Page SHALL include a link to the Register_Page, and THE Register_Page SHALL include a link to the Login_Page

### Requirement 7: 验证码发送频率限制

**User Story:** As a 系统管理员, I want to 限制验证码发送频率, so that 系统不会被恶意请求滥用。

#### Acceptance Criteria

1. WHEN a send-code request is received, THE Auth_Service SHALL check Redis_Store for a rate-limit key with pattern `code_rate:{type}:{target}` where type is "email" or "sms" and target is the email or phone number
2. IF a rate-limit key exists (indicating a code was sent within the last 60 seconds), THEN THE Auth_Service SHALL return HTTP 429 with error message "发送过于频繁，请60秒后重试"
3. WHEN a Verification_Code is successfully generated, THE Auth_Service SHALL set a rate-limit key in Redis_Store with a 60-second TTL

### Requirement 8: API_Client 扩展

**User Story:** As a 前端开发者, I want to 在 API_Client 中添加验证码相关的 API 方法, so that 前端组件可以方便地调用新的认证接口。

#### Acceptance Criteria

1. THE API_Client SHALL expose a `sendEmailCode(email: string)` method that calls `POST /api/v1/auth/send-email-code`
2. THE API_Client SHALL expose a `sendSmsCode(phone: string)` method that calls `POST /api/v1/auth/send-sms`
3. THE API_Client SHALL expose a `loginWithPhoneCode(phone: string, code: string)` method that calls `POST /api/v1/auth/login/phone-code`
4. THE API_Client SHALL expose a `loginWithEmailCode(email: string, code: string)` method that calls `POST /api/v1/auth/login/email-code`
5. THE API_Client SHALL expose a `registerWithEmailCode(email: string, username: string, password: string, code: string)` method that calls `POST /api/v1/auth/register/email`
