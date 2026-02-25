import { useMemo } from 'react';
import { Typography, Alert } from 'antd';

const { Title, Paragraph, Text } = Typography;

interface IntegrationGuideProps {
  appId: string;
  appName: string;
  scopes: string[];
  loginMethods: { method: string; is_enabled: boolean }[];
  rateLimit: number;
  gatewayBaseUrl?: string;
}

const SCOPE_DESCRIPTIONS: Record<string, string> = {
  'auth:register': '用户注册（邮箱注册、手机注册）',
  'auth:login': '用户登录（密码登录、OAuth 登录、Token 刷新）',
  'user:read': '读取用户信息',
  'user:write': '修改用户信息（修改密码）',
  'role:read': '读取角色/权限（查询用户角色、权限、权限检查）',
  'role:write': '管理角色（分配角色、移除角色）',
  'org:read': '读取组织信息',
  'org:write': '管理组织',
};

export default function IntegrationGuide({
  appId,
  appName,
  scopes,
  loginMethods,
  rateLimit,
  gatewayBaseUrl = 'http://localhost:8008',
}: IntegrationGuideProps) {
  const enabledMethods = useMemo(
    () => loginMethods.filter((m) => m.is_enabled).map((m) => m.method),
    [loginMethods],
  );

  const hasScope = (s: string) => scopes.includes(s);
  const base = `${gatewayBaseUrl}/api/v1/gateway`;

  return (
    <Typography>
      <Title level={4}>应用「{appName}」API 对接说明</Title>

      <Alert
        type="info"
        showIcon
        message="所有 API 请求必须通过网关访问，不允许直接调用内部微服务。"
        style={{ marginBottom: 16 }}
      />


      {/* ===== 基本信息 ===== */}
      <Title level={5}>一、基本信息</Title>
      <pre style={{ background: '#f5f5f5', padding: 12, borderRadius: 6, fontSize: 13 }}>
{`网关地址:  ${gatewayBaseUrl}
API 版本:  v1
基础路径:  /api/v1/gateway
App ID:    ${appId}
限流配置:  ${rateLimit} 次/分钟`}
      </pre>

      {/* ===== 已授权 Scope ===== */}
      <Title level={5}>二、已授权的权限范围（Scope）</Title>
      {scopes.length === 0 ? (
        <Alert type="warning" message="当前应用未配置任何 Scope，无法调用任何 API。请先在「权限范围配置」中勾选所需 Scope。" showIcon />
      ) : (
        <table style={{ width: '100%', borderCollapse: 'collapse', marginBottom: 16, fontSize: 13 }}>
          <thead>
            <tr style={{ background: '#fafafa' }}>
              <th style={{ border: '1px solid #f0f0f0', padding: '8px 12px', textAlign: 'left' }}>Scope</th>
              <th style={{ border: '1px solid #f0f0f0', padding: '8px 12px', textAlign: 'left' }}>说明</th>
            </tr>
          </thead>
          <tbody>
            {scopes.map((s) => (
              <tr key={s}>
                <td style={{ border: '1px solid #f0f0f0', padding: '8px 12px' }}><code>{s}</code></td>
                <td style={{ border: '1px solid #f0f0f0', padding: '8px 12px' }}>{SCOPE_DESCRIPTIONS[s] || s}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}

      {/* ===== 已启用登录方式 ===== */}
      <Title level={5}>三、已启用的登录方式</Title>
      {enabledMethods.length === 0 ? (
        <Alert type="warning" message="当前应用未启用任何登录方式。" showIcon />
      ) : (
        <Paragraph>
          {enabledMethods.map((m) => (
            <code key={m} style={{ marginRight: 8, padding: '2px 8px', background: '#f5f5f5', borderRadius: 4 }}>{m}</code>
          ))}
        </Paragraph>
      )}

      {/* ===== 认证机制 ===== */}
      <Title level={5}>四、认证机制</Title>

      <Paragraph strong>方式一：应用凭证认证（用于注册、登录等端点）</Paragraph>
      <pre style={{ background: '#f5f5f5', padding: 12, borderRadius: 6, fontSize: 13 }}>
{`X-App-Id: ${appId}
X-App-Secret: <your_app_secret>
Content-Type: application/json`}
      </pre>

      <Paragraph strong>方式二：Bearer Token 认证（用于用户信息、角色管理等端点）</Paragraph>
      <pre style={{ background: '#f5f5f5', padding: 12, borderRadius: 6, fontSize: 13 }}>
{`Authorization: Bearer <access_token>`}
      </pre>
      <Paragraph type="secondary">
        用户登录成功后获得 access_token，Token 中已包含 app_id，网关会自动验证用户与应用的绑定关系。
      </Paragraph>

      {/* ===== API 端点 ===== */}
      <Title level={5}>五、可用 API 端点</Title>


      {/* 注册 */}
      {hasScope('auth:register') && (
        <>
          <Paragraph strong>用户注册</Paragraph>
          {enabledMethods.includes('email') && (
            <div style={{ marginBottom: 12 }}>
              <Text code>POST {base}/auth/register/email</Text>
              <pre style={{ background: '#f5f5f5', padding: 12, borderRadius: 6, fontSize: 13, marginTop: 4 }}>
{`# 请求头: X-App-Id + X-App-Secret
# 请求体:
{
  "email": "user@example.com",
  "password": "SecurePass123",
  "nickname": "用户昵称"
}

# cURL 示例:
curl -X POST ${base}/auth/register/email \\
  -H "X-App-Id: ${appId}" \\
  -H "X-App-Secret: <your_app_secret>" \\
  -H "Content-Type: application/json" \\
  -d '{"email":"user@example.com","password":"SecurePass123"}'`}
              </pre>
            </div>
          )}
          {enabledMethods.includes('phone') && (
            <div style={{ marginBottom: 12 }}>
              <Text code>POST {base}/auth/register/phone</Text>
              <pre style={{ background: '#f5f5f5', padding: 12, borderRadius: 6, fontSize: 13, marginTop: 4 }}>
{`# 请求头: X-App-Id + X-App-Secret
# 请求体:
{
  "phone": "+8613800138000",
  "verification_code": "123456",
  "password": "SecurePass123"
}`}
              </pre>
            </div>
          )}
        </>
      )}

      {/* 登录 */}
      {hasScope('auth:login') && (
        <>
          <Paragraph strong>用户登录</Paragraph>
          <div style={{ marginBottom: 12 }}>
            <Text code>POST {base}/auth/login</Text>
            <pre style={{ background: '#f5f5f5', padding: 12, borderRadius: 6, fontSize: 13, marginTop: 4 }}>
{`# 请求头: X-App-Id + X-App-Secret
# 请求体 (identifier 可以是邮箱或手机号):
{
  "identifier": "user@example.com",
  "password": "SecurePass123"
}

# 成功响应:
{
  "access_token": "eyJhbGciOiJIUzI1NiIs...",
  "refresh_token": "eyJhbGciOiJIUzI1NiIs...",
  "token_type": "bearer"
}

# cURL 示例:
curl -X POST ${base}/auth/login \\
  -H "X-App-Id: ${appId}" \\
  -H "X-App-Secret: <your_app_secret>" \\
  -H "Content-Type: application/json" \\
  -d '{"identifier":"user@example.com","password":"SecurePass123"}'`}
            </pre>
          </div>

          {/* OAuth */}
          {enabledMethods.some((m) => ['wechat', 'alipay', 'google', 'apple'].includes(m)) && (
            <div style={{ marginBottom: 12 }}>
              <Text code>POST {base}/auth/oauth/{'{'}<Text type="secondary">provider</Text>{'}'}</Text>
              <Paragraph type="secondary" style={{ marginTop: 4 }}>
                支持的 provider: {enabledMethods.filter((m) => ['wechat', 'alipay', 'google', 'apple'].includes(m)).join(', ')}
              </Paragraph>
              <pre style={{ background: '#f5f5f5', padding: 12, borderRadius: 6, fontSize: 13 }}>
{`# 请求头: X-App-Id + X-App-Secret
# 请求体:
{ "code": "oauth_authorization_code" }`}
              </pre>
            </div>
          )}

          {/* Token 刷新 */}
          <div style={{ marginBottom: 12 }}>
            <Text code>POST {base}/auth/refresh</Text>
            <pre style={{ background: '#f5f5f5', padding: 12, borderRadius: 6, fontSize: 13, marginTop: 4 }}>
{`# 请求头: X-App-Id + X-App-Secret
# 请求体:
{ "refresh_token": "eyJhbGciOiJIUzI1NiIs..." }`}
            </pre>
          </div>
        </>
      )}


      {/* 用户信息 */}
      {hasScope('user:read') && (
        <>
          <Paragraph strong>用户信息</Paragraph>
          <div style={{ marginBottom: 12 }}>
            <Text code>GET {base}/users/{'{'}<Text type="secondary">user_id</Text>{'}'}</Text>
            <pre style={{ background: '#f5f5f5', padding: 12, borderRadius: 6, fontSize: 13, marginTop: 4 }}>
{`# 请求头: Authorization: Bearer <access_token>`}
            </pre>
          </div>
        </>
      )}

      {hasScope('user:write') && (
        <div style={{ marginBottom: 12 }}>
          <Paragraph strong>修改密码</Paragraph>
          <Text code>POST {base}/auth/change-password</Text>
          <pre style={{ background: '#f5f5f5', padding: 12, borderRadius: 6, fontSize: 13, marginTop: 4 }}>
{`# 请求头: Authorization: Bearer <access_token>
# 请求体:
{
  "old_password": "OldPass123",
  "new_password": "NewPass456"
}`}
          </pre>
        </div>
      )}

      {/* 角色与权限 */}
      {(hasScope('role:read') || hasScope('role:write')) && (
        <>
          <Paragraph strong>角色与权限管理</Paragraph>

          {hasScope('role:read') && (
            <>
              <div style={{ marginBottom: 12 }}>
                <Text code>GET {base}/users/{'{'}<Text type="secondary">user_id</Text>{'}'}/roles</Text>
                <Paragraph type="secondary" style={{ margin: '4px 0 0' }}>查询用户角色</Paragraph>
              </div>
              <div style={{ marginBottom: 12 }}>
                <Text code>GET {base}/users/{'{'}<Text type="secondary">user_id</Text>{'}'}/permissions</Text>
                <Paragraph type="secondary" style={{ margin: '4px 0 0' }}>查询用户所有权限</Paragraph>
              </div>
              <div style={{ marginBottom: 12 }}>
                <Text code>POST {base}/users/{'{'}<Text type="secondary">user_id</Text>{'}'}/permissions/check</Text>
                <pre style={{ background: '#f5f5f5', padding: 12, borderRadius: 6, fontSize: 13, marginTop: 4 }}>
{`# 请求头: Authorization: Bearer <access_token>
# 请求体:
{ "permission": "article:edit" }

# 响应:
{ "has_permission": true }`}
                </pre>
              </div>
            </>
          )}

          {hasScope('role:write') && (
            <>
              <div style={{ marginBottom: 12 }}>
                <Text code>POST {base}/users/{'{'}<Text type="secondary">user_id</Text>{'}'}/roles</Text>
                <Paragraph type="secondary" style={{ margin: '4px 0 0' }}>为用户分配角色（幂等操作）</Paragraph>
                <pre style={{ background: '#f5f5f5', padding: 12, borderRadius: 6, fontSize: 13, marginTop: 4 }}>
{`# 请求头: Authorization: Bearer <access_token>
# 请求体:
{ "role_ids": ["<role_uuid_1>", "<role_uuid_2>"] }

# cURL 示例:
curl -X POST ${base}/users/{user_id}/roles \\
  -H "Authorization: Bearer <access_token>" \\
  -H "Content-Type: application/json" \\
  -d '{"role_ids":["role_uuid_1","role_uuid_2"]}'`}
                </pre>
              </div>
              <div style={{ marginBottom: 12 }}>
                <Text code>DELETE {base}/users/{'{'}<Text type="secondary">user_id</Text>{'}'}/roles/{'{'}<Text type="secondary">role_id</Text>{'}'}</Text>
                <Paragraph type="secondary" style={{ margin: '4px 0 0' }}>移除用户角色</Paragraph>
              </div>
            </>
          )}
        </>
      )}

      {/* ===== 错误处理 ===== */}
      <Title level={5}>六、统一错误响应格式</Title>
      <pre style={{ background: '#f5f5f5', padding: 12, borderRadius: 6, fontSize: 13 }}>
{`{
  "error_code": "insufficient_scope",
  "message": "应用未被授予所需的权限范围: role:write",
  "request_id": "7c9e6679-7425-40de-944b-e07fc1f90ae7"
}`}
      </pre>

      <table style={{ width: '100%', borderCollapse: 'collapse', marginBottom: 16, fontSize: 13 }}>
        <thead>
          <tr style={{ background: '#fafafa' }}>
            <th style={{ border: '1px solid #f0f0f0', padding: '8px 12px', textAlign: 'left' }}>error_code</th>
            <th style={{ border: '1px solid #f0f0f0', padding: '8px 12px', textAlign: 'left' }}>HTTP</th>
            <th style={{ border: '1px solid #f0f0f0', padding: '8px 12px', textAlign: 'left' }}>说明</th>
          </tr>
        </thead>
        <tbody>
          {[
            ['invalid_credentials', '401', 'app_id 或 app_secret 无效'],
            ['app_disabled', '403', '应用已被禁用'],
            ['token_expired', '401', 'access_token 已过期，需刷新'],
            ['invalid_token', '401', 'access_token 格式无效'],
            ['login_method_disabled', '400', '该登录方式未启用'],
            ['insufficient_scope', '403', '应用缺少所需的 Scope'],
            ['user_not_bound', '403', '用户不属于该应用'],
            ['rate_limit_exceeded', '429', '请求频率超限'],
            ['request_quota_exceeded', '429', '请求次数配额已耗尽'],
            ['token_quota_exceeded', '429', 'Token 配额已耗尽'],
            ['quota_not_configured', '403', '应用未配置配额计划'],
            ['service_unavailable', '503', '服务暂时不可用'],
          ].map(([code, http, desc]) => (
            <tr key={code}>
              <td style={{ border: '1px solid #f0f0f0', padding: '8px 12px' }}><code>{code}</code></td>
              <td style={{ border: '1px solid #f0f0f0', padding: '8px 12px' }}>{http}</td>
              <td style={{ border: '1px solid #f0f0f0', padding: '8px 12px' }}>{desc}</td>
            </tr>
          ))}
        </tbody>
      </table>

      {/* ===== 配额管理 API ===== */}
      <Title level={5}>八、配额管理 API</Title>
      <Paragraph>
        如果您的应用绑定了包含大模型配额的订阅计划，可以通过以下端点查询当前配额使用情况。
        所有大模型 API 响应中也会自动包含配额相关的响应头。
      </Paragraph>

      <Paragraph strong>查询配额使用情况</Paragraph>
      <Text code>GET {gatewayBaseUrl}/api/v1/quota/usage</Text>
      <pre style={{ background: '#f5f5f5', padding: 12, borderRadius: 6, fontSize: 13, marginTop: 4 }}>
{`# 请求头: Bearer Token 认证（登录后获取的 access_token）
# cURL 示例:
curl -X GET ${gatewayBaseUrl}/api/v1/quota/usage \\
  -H "X-App-Id: ${appId}" \\
  -H "Authorization: Bearer <access_token>"

# 成功响应 (HTTP 200):
{
  "request_quota_limit": 10000,
  "request_quota_used": 3500,
  "request_quota_remaining": 6500,
  "token_quota_limit": 1000000,
  "token_quota_used": 425000,
  "token_quota_remaining": 575000,
  "billing_cycle_start": "2024-01-01T00:00:00Z",
  "billing_cycle_end": "2024-01-31T00:00:00Z",
  "billing_cycle_reset": "2024-01-31T00:00:00Z"
}

# Python 示例:
import requests

resp = requests.get(
    "${gatewayBaseUrl}/api/v1/quota/usage",
    headers={
        "X-App-Id": "${appId}",
        "Authorization": "Bearer <access_token>"
    }
)
print(resp.json())`}
      </pre>

      <Paragraph strong style={{ marginTop: 16 }}>配额相关响应头</Paragraph>
      <Paragraph type="secondary">
        所有大模型 API（<code>/api/v1/gateway/llm/*</code>）的响应中会自动包含以下响应头，
        您可以据此在客户端实现配额监控和预警逻辑。
      </Paragraph>
      <table style={{ width: '100%', borderCollapse: 'collapse', marginBottom: 16, fontSize: 13 }}>
        <thead>
          <tr style={{ background: '#fafafa' }}>
            <th style={{ border: '1px solid #f0f0f0', padding: '8px 12px', textAlign: 'left' }}>响应头</th>
            <th style={{ border: '1px solid #f0f0f0', padding: '8px 12px', textAlign: 'left' }}>说明</th>
            <th style={{ border: '1px solid #f0f0f0', padding: '8px 12px', textAlign: 'left' }}>示例值</th>
          </tr>
        </thead>
        <tbody>
          {([
            ['X-Quota-Request-Limit', '当前计费周期内允许的最大请求次数，-1 表示无限制', '10000'],
            ['X-Quota-Request-Remaining', '当前计费周期内剩余的请求次数', '6500'],
            ['X-Quota-Request-Reset', '请求次数配额重置的 Unix 时间戳（秒）', '1706659200'],
            ['X-Quota-Token-Limit', '当前计费周期内允许的最大 Token 消耗量，-1 表示无限制', '1000000'],
            ['X-Quota-Token-Remaining', '当前计费周期内剩余的 Token 额度', '575000'],
            ['X-Quota-Token-Reset', 'Token 配额重置的 Unix 时间戳（秒）', '1706659200'],
            ['X-Quota-Warning', '配额预警标识：approaching_limit（使用率超过 80%）或 exhausted（配额已耗尽）', 'approaching_limit'],
          ] as [string, string, string][]).map(([header, desc, example]) => (
            <tr key={header}>
              <td style={{ border: '1px solid #f0f0f0', padding: '8px 12px' }}><code>{header}</code></td>
              <td style={{ border: '1px solid #f0f0f0', padding: '8px 12px' }}>{desc}</td>
              <td style={{ border: '1px solid #f0f0f0', padding: '8px 12px' }}><code>{example}</code></td>
            </tr>
          ))}
        </tbody>
      </table>

      <Paragraph type="secondary">
        <Text strong>提示</Text>：当 <code>X-Quota-Warning</code> 值为 <code>approaching_limit</code> 时，
        建议提醒用户升级订阅计划或优化用量；当值为 <code>exhausted</code> 时，后续请求将返回 HTTP 429 错误。
        配额在每个计费周期结束时自动重置，您可以通过 <code>X-Quota-Request-Reset</code> 和 <code>X-Quota-Token-Reset</code> 获取重置时间。
      </Paragraph>

      {/* ===== 注意事项 ===== */}
      <Title level={5}>九、注意事项</Title>
      <ul style={{ fontSize: 13 }}>
        <li><Text strong>安全</Text>：app_secret 只能在服务端使用，禁止在前端代码或客户端中暴露</li>
        <li><Text strong>限流</Text>：当前应用限流为 {rateLimit} 次/分钟，每个响应包含 X-RateLimit-* 头</li>
        <li><Text strong>用户绑定</Text>：通过网关注册的用户会自动绑定到本应用，Bearer Token 端点会验证绑定关系</li>
        <li><Text strong>Token 刷新</Text>：access_token 过期后使用 refresh_token 刷新，避免频繁登录</li>
        <li><Text strong>幂等性</Text>：角色分配、用户注册等操作均为幂等操作，重复调用不会产生副作用</li>
        <li><Text strong>自动配置</Text>：如果启用了用户自动配置，新注册用户会自动获得预设的角色、权限、组织和订阅</li>
        <li><Text strong>配额管理</Text>：大模型 API 请求受配额限制，请关注响应头中的 X-Quota-* 字段，在配额即将耗尽时及时升级订阅计划</li>
      </ul>
    </Typography>
  );
}
