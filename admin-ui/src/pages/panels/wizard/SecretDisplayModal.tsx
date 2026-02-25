import { Modal, Button, Typography, Divider, Collapse } from 'antd';

const { Paragraph, Text } = Typography;

interface SecretDisplayModalProps {
  open: boolean;
  appId: string;
  appSecret: string;
  onClose: () => void;
}

const GATEWAY_BASE = '/api/v1/gateway';

function IntegrationGuideContent({ appId }: { appId: string }) {
  const base = GATEWAY_BASE;
  const codeBlock: React.CSSProperties = {
    background: '#f5f5f5', padding: 10, borderRadius: 6,
    fontSize: 12, whiteSpace: 'pre-wrap', wordBreak: 'break-all',
    lineHeight: 1.6, margin: '6px 0 12px',
  };
  const sectionTitle: React.CSSProperties = {
    fontWeight: 600, fontSize: 13, margin: '12px 0 6px',
  };

  return (
    <Typography style={{ fontSize: 13 }}>
      <div style={sectionTitle}>一、认证方式</div>
      <Text type="secondary">注册/登录端点使用应用凭证，用户端点使用 Bearer Token：</Text>
      <pre style={codeBlock}>
{`# 应用凭证认证（注册、登录）
X-App-Id: ${appId}
X-App-Secret: <上方的 App Secret>
Content-Type: application/json

# Bearer Token 认证（用户信息、角色管理）
Authorization: Bearer <登录后获得的 access_token>`}
      </pre>

      <div style={sectionTitle}>二、用户注册</div>
      <pre style={codeBlock}>
{`# 邮箱注册 (需 Scope: auth:register, 登录方式: email)
POST ${base}/auth/register/email
{"email":"user@example.com","password":"SecurePass123"}

# 手机注册 (需 Scope: auth:register, 登录方式: phone)
POST ${base}/auth/register/phone
{"phone":"+8613800138000","verification_code":"123456","password":"SecurePass123"}`}
      </pre>

      <div style={sectionTitle}>三、用户登录</div>
      <pre style={codeBlock}>
{`# 密码登录 (需 Scope: auth:login)
POST ${base}/auth/login
{"identifier":"user@example.com","password":"SecurePass123"}

# 响应:
{"access_token":"eyJ...","refresh_token":"eyJ...","token_type":"bearer"}

# OAuth 登录 (需 Scope: auth:login)
POST ${base}/auth/oauth/{provider}
{"code":"oauth_authorization_code"}

# Token 刷新 (需 Scope: auth:login)
POST ${base}/auth/refresh
{"refresh_token":"eyJ..."}`}
      </pre>

      <div style={sectionTitle}>四、用户信息</div>
      <pre style={codeBlock}>
{`# 查询用户 (需 Scope: user:read, Bearer Token)
GET ${base}/users/{user_id}

# 修改密码 (需 Scope: user:write, Bearer Token)
POST ${base}/auth/change-password
{"old_password":"OldPass","new_password":"NewPass"}`}
      </pre>

      <div style={sectionTitle}>五、角色与权限管理</div>
      <pre style={codeBlock}>
{`# 查询用户角色 (需 Scope: role:read, Bearer Token)
GET ${base}/users/{user_id}/roles

# 查询用户权限 (需 Scope: role:read, Bearer Token)
GET ${base}/users/{user_id}/permissions

# 检查权限 (需 Scope: role:read, Bearer Token)
POST ${base}/users/{user_id}/permissions/check
{"permission":"article:edit"}

# 分配角色 (需 Scope: role:write, Bearer Token)
POST ${base}/users/{user_id}/roles
{"role_ids":["<role_uuid>"]}

# 移除角色 (需 Scope: role:write, Bearer Token)
DELETE ${base}/users/{user_id}/roles/{role_id}`}
      </pre>

      <div style={sectionTitle}>六、cURL 示例</div>
      <pre style={codeBlock}>
{`# 登录
curl -X POST http://localhost:8008${base}/auth/login \\
  -H "X-App-Id: ${appId}" \\
  -H "X-App-Secret: <your_secret>" \\
  -H "Content-Type: application/json" \\
  -d '{"identifier":"user@example.com","password":"SecurePass123"}'

# 查询角色
curl http://localhost:8008${base}/users/{user_id}/roles \\
  -H "Authorization: Bearer <access_token>"`}
      </pre>

      <div style={sectionTitle}>七、配额管理 API</div>
      <Text type="secondary">查询当前应用的大模型配额使用情况（需 Bearer Token 认证）：</Text>
      <pre style={codeBlock}>
{`# cURL 示例
curl http://localhost:8008/api/v1/quota/usage \\
  -H "X-App-Id: ${appId}" \\
  -H "Authorization: Bearer <access_token>"

# 响应示例:
{
  "request_quota_limit": 10000,
  "request_quota_used": 3500,
  "request_quota_remaining": 6500,
  "token_quota_limit": 1000000,
  "token_quota_used": 250000,
  "token_quota_remaining": 750000,
  "billing_cycle_start": "2024-01-01T00:00:00Z",
  "billing_cycle_end": "2024-01-31T00:00:00Z",
  "billing_cycle_reset": "2024-01-31T00:00:00Z"
}`}
      </pre>
      <pre style={codeBlock}>
{`# Python 示例
import requests

resp = requests.get(
    "http://localhost:8008/api/v1/quota/usage",
    headers={
        "X-App-Id": "${appId}",
        "Authorization": "Bearer <access_token>",
    },
)
data = resp.json()
print(f"请求配额: {data['request_quota_used']}/{data['request_quota_limit']}")
print(f"Token 配额: {data['token_quota_used']}/{data['token_quota_limit']}")`}
      </pre>

      <div style={sectionTitle}>八、Scope 权限范围说明</div>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12 }}>
        <thead>
          <tr style={{ background: '#fafafa' }}>
            <th style={{ border: '1px solid #f0f0f0', padding: '6px 8px', textAlign: 'left' }}>Scope</th>
            <th style={{ border: '1px solid #f0f0f0', padding: '6px 8px', textAlign: 'left' }}>说明</th>
          </tr>
        </thead>
        <tbody>
          {[
            ['auth:register', '用户注册'],
            ['auth:login', '登录、OAuth、Token 刷新'],
            ['user:read', '查询用户信息'],
            ['user:write', '修改密码'],
            ['role:read', '查询角色/权限、权限检查'],
            ['role:write', '分配/移除角色'],
          ].map(([scope, desc]) => (
            <tr key={scope}>
              <td style={{ border: '1px solid #f0f0f0', padding: '6px 8px' }}><code>{scope}</code></td>
              <td style={{ border: '1px solid #f0f0f0', padding: '6px 8px' }}>{desc}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <div style={sectionTitle}>九、错误码</div>
      <table style={{ width: '100%', borderCollapse: 'collapse', fontSize: 12, marginBottom: 8 }}>
        <thead>
          <tr style={{ background: '#fafafa' }}>
            <th style={{ border: '1px solid #f0f0f0', padding: '6px 8px', textAlign: 'left' }}>error_code</th>
            <th style={{ border: '1px solid #f0f0f0', padding: '6px 8px', textAlign: 'left' }}>HTTP</th>
            <th style={{ border: '1px solid #f0f0f0', padding: '6px 8px', textAlign: 'left' }}>说明</th>
          </tr>
        </thead>
        <tbody>
          {[
            ['invalid_credentials', '401', '凭证无效'],
            ['app_disabled', '403', '应用已禁用'],
            ['token_expired', '401', 'Token 已过期'],
            ['insufficient_scope', '403', '缺少 Scope'],
            ['user_not_bound', '403', '用户不属于该应用'],
            ['rate_limit_exceeded', '429', '请求频率超限'],
            ['request_quota_exceeded', '429', '请求次数配额已耗尽'],
            ['token_quota_exceeded', '429', 'Token 配额已耗尽'],
          ].map(([code, http, desc]) => (
            <tr key={code}>
              <td style={{ border: '1px solid #f0f0f0', padding: '6px 8px' }}><code>{code}</code></td>
              <td style={{ border: '1px solid #f0f0f0', padding: '6px 8px' }}>{http}</td>
              <td style={{ border: '1px solid #f0f0f0', padding: '6px 8px' }}>{desc}</td>
            </tr>
          ))}
        </tbody>
      </table>

      <div style={sectionTitle}>十、注意事项</div>
      <ul style={{ fontSize: 12, paddingLeft: 20, marginBottom: 0 }}>
        <li>app_secret 只能在服务端使用，禁止在前端暴露</li>
        <li>请在管理后台配置所需的 Scope 和登录方式后再对接</li>
        <li>每个响应包含 X-RateLimit-* 限流头和 request_id 追踪字段</li>
        <li>大模型 API 响应包含 X-Quota-* 配额头，可据此监控配额使用情况</li>
        <li>角色分配等操作为幂等操作，重复调用不会产生副作用</li>
      </ul>
    </Typography>
  );
}

export default function SecretDisplayModal({ open, appId, appSecret, onClose }: SecretDisplayModalProps) {
  return (
    <Modal
      title="应用密钥"
      open={open}
      onCancel={onClose}
      width={720}
      footer={[
        <Button key="ok" type="primary" onClick={onClose}>
          我已保存
        </Button>,
      ]}
    >
      <div style={{ marginBottom: 16, color: '#ff4d4f', fontWeight: 'bold' }}>
        ⚠️ 请妥善保存以下密钥，关闭后将无法再次查看！
      </div>
      <div style={{ marginBottom: 12 }}>
        <div style={{ color: '#666', marginBottom: 4 }}>App ID:</div>
        <Paragraph copyable style={{ marginBottom: 0 }}>
          {appId}
        </Paragraph>
      </div>
      <div>
        <div style={{ color: '#666', marginBottom: 4 }}>App Secret:</div>
        <Paragraph copyable style={{ marginBottom: 0, wordBreak: 'break-all' }}>
          {appSecret}
        </Paragraph>
      </div>

      <Divider />

      <Collapse
        items={[{
          key: 'guide',
          label: '📄 API 对接说明（点击展开）',
          children: <IntegrationGuideContent appId={appId} />,
        }]}
      />
    </Modal>
  );
}
