import { useEffect, useState, useCallback } from 'react';
import {
  Card, Tabs, Button, Form, Input, InputNumber, Switch, Select, Space,
  message, Popconfirm, Tag, Typography, Alert, Steps, Divider, Spin, Modal,
  Empty,
} from 'antd';
import {
  MailOutlined, MessageOutlined, DeleteOutlined,
  ExperimentOutlined, SaveOutlined,
  QuestionCircleOutlined,
} from '@ant-design/icons';
import { cloudServiceApi } from '../../api/services';

const { Text } = Typography;

// ==================== 提供商预设 ====================

interface ProviderPreset {
  key: string;
  label: string;
  fields: FieldDef[];
  guide: React.ReactNode;
  defaults?: Record<string, any>;
}

interface FieldDef {
  name: string;
  label: string;
  type: 'text' | 'password' | 'number' | 'switch';
  required?: boolean;
  placeholder?: string;
  tooltip?: string;
}

const EMAIL_PROVIDERS: ProviderPreset[] = [
  {
    key: 'aliyun',
    label: '阿里云邮件推送',
    defaults: { smtp_host: 'smtpdm.aliyun.com', smtp_port: 465, use_ssl: true, use_tls: false },
    fields: [
      { name: 'smtp_host', label: 'SMTP 地址', type: 'text', required: true, placeholder: 'smtpdm.aliyun.com' },
      { name: 'smtp_port', label: 'SMTP 端口', type: 'number', required: true, placeholder: '465' },
      { name: 'username', label: '发信地址', type: 'text', required: true, placeholder: '如 noreply@mail.yourdomain.com', tooltip: '在阿里云邮件推送控制台 → 发信地址 中创建' },
      { name: 'password', label: 'SMTP 密码', type: 'password', required: true, placeholder: '设置发信地址时生成的 SMTP 密码', tooltip: '注意：这不是阿里云账号密码，是发信地址的 SMTP 密码' },
      { name: 'use_ssl', label: '使用 SSL', type: 'switch' },
      { name: 'use_tls', label: '使用 TLS', type: 'switch' },
    ],
    guide: <AliyunEmailGuide />,
  },
  {
    key: 'tencent',
    label: '腾讯企业邮 / QQ邮箱',
    defaults: { smtp_host: 'smtp.exmail.qq.com', smtp_port: 465, use_ssl: true, use_tls: false },
    fields: [
      { name: 'smtp_host', label: 'SMTP 地址', type: 'text', required: true, placeholder: 'smtp.exmail.qq.com' },
      { name: 'smtp_port', label: 'SMTP 端口', type: 'number', required: true, placeholder: '465' },
      { name: 'username', label: '邮箱账号', type: 'text', required: true, placeholder: '如 noreply@yourdomain.com' },
      { name: 'password', label: '授权码/密码', type: 'password', required: true, placeholder: 'SMTP 授权码' },
      { name: 'use_ssl', label: '使用 SSL', type: 'switch' },
      { name: 'use_tls', label: '使用 TLS', type: 'switch' },
    ],
    guide: <GenericSmtpGuide provider="腾讯企业邮" host="smtp.exmail.qq.com" port={465} />,
  },
  {
    key: 'custom_smtp',
    label: '自定义 SMTP',
    defaults: { smtp_port: 587, use_ssl: false, use_tls: true },
    fields: [
      { name: 'smtp_host', label: 'SMTP 地址', type: 'text', required: true, placeholder: 'smtp.example.com' },
      { name: 'smtp_port', label: 'SMTP 端口', type: 'number', required: true, placeholder: '587' },
      { name: 'username', label: '用户名', type: 'text', required: true },
      { name: 'password', label: '密码', type: 'password', required: true },
      { name: 'use_ssl', label: '使用 SSL', type: 'switch' },
      { name: 'use_tls', label: '使用 TLS', type: 'switch' },
    ],
    guide: <GenericSmtpGuide provider="自定义 SMTP" host="smtp.example.com" port={587} />,
  },
];

const SMS_PROVIDERS: ProviderPreset[] = [
  {
    key: 'aliyun',
    label: '阿里云短信',
    defaults: {},
    fields: [
      { name: 'access_key_id', label: 'AccessKey ID', type: 'text', required: true, tooltip: '在阿里云 RAM 控制台创建' },
      { name: 'access_key_secret', label: 'AccessKey Secret', type: 'password', required: true },
      { name: 'sign_name', label: '短信签名', type: 'text', required: true, placeholder: '如：你的公司名', tooltip: '需在阿里云短信控制台申请并审核通过' },
    ],
    guide: <AliyunSmsGuide />,
  },
  {
    key: 'tencent',
    label: '腾讯云短信',
    defaults: {},
    fields: [
      { name: 'secret_id', label: 'SecretId', type: 'text', required: true },
      { name: 'secret_key', label: 'SecretKey', type: 'password', required: true },
      { name: 'sdk_app_id', label: '短信应用 ID', type: 'text', required: true, tooltip: '在腾讯云短信控制台 → 应用管理中获取' },
      { name: 'sign_name', label: '短信签名', type: 'text', required: true },
    ],
    guide: <TencentSmsGuide />,
  },
];

// ==================== 引导组件 ====================

function AliyunEmailGuide() {
  const stepStyle: React.CSSProperties = { fontSize: 13, lineHeight: 1.8 };
  return (
    <div style={stepStyle}>
      <Steps
        direction="vertical"
        size="small"
        current={-1}
        items={[
          {
            title: '开通阿里云邮件推送服务',
            description: (
              <div>
                <div>登录 <a href="https://www.aliyun.com/product/directmail" target="_blank" rel="noreferrer">阿里云邮件推送</a>，开通服务（免费额度：每日 200 封）</div>
              </div>
            ),
          },
          {
            title: '配置发信域名',
            description: (
              <div>
                <div>进入控制台 → <Text strong>发信域名</Text> → 新建域名</div>
                <div>按提示在你的 DNS 服务商处添加 SPF、MX、CNAME 记录</div>
                <div>等待域名验证通过（通常几分钟到几小时）</div>
              </div>
            ),
          },
          {
            title: '创建发信地址',
            description: (
              <div>
                <div>控制台 → <Text strong>发信地址</Text> → 新建发信地址</div>
                <div>填写发信地址（如 <Text code>noreply@mail.yourdomain.com</Text>）</div>
                <div>点击 <Text strong>设置 SMTP 密码</Text>，记录生成的密码</div>
                <Alert
                  type="warning"
                  showIcon
                  style={{ marginTop: 8 }}
                  message="SMTP 密码只显示一次，请务必保存。如果忘记需要重新设置。"
                />
              </div>
            ),
          },
          {
            title: '填写配置',
            description: (
              <div>
                <div>将以下信息填入右侧表单：</div>
                <ul style={{ paddingLeft: 20, margin: '4px 0' }}>
                  <li>SMTP 地址：<Text code>smtpdm.aliyun.com</Text></li>
                  <li>SMTP 端口：<Text code>465</Text>（SSL）或 <Text code>80</Text>（非加密）</li>
                  <li>发信地址：你创建的发信地址</li>
                  <li>SMTP 密码：上一步设置的密码</li>
                  <li>开启 SSL：<Text code>是</Text></li>
                </ul>
              </div>
            ),
          },
          {
            title: '验证配置',
            description: '保存后点击「测试发送」按钮，输入收件邮箱验证是否配置成功',
          },
        ]}
      />
    </div>
  );
}

function GenericSmtpGuide({ provider, host, port }: { provider: string; host: string; port: number }) {
  return (
    <div style={{ fontSize: 13, lineHeight: 1.8 }}>
      <Steps
        direction="vertical"
        size="small"
        current={-1}
        items={[
          {
            title: `获取 ${provider} SMTP 信息`,
            description: (
              <div>
                <div>在 {provider} 管理后台找到 SMTP 设置</div>
                <div>默认地址：<Text code>{host}</Text>，端口：<Text code>{port}</Text></div>
              </div>
            ),
          },
          {
            title: '获取授权码',
            description: `在邮箱设置中开启 SMTP 服务，获取授权码（部分服务商需要单独生成）`,
          },
          {
            title: '填写并保存',
            description: '将 SMTP 地址、端口、账号、授权码填入右侧表单，保存后测试发送',
          },
        ]}
      />
    </div>
  );
}

function AliyunSmsGuide() {
  return (
    <div style={{ fontSize: 13, lineHeight: 1.8 }}>
      <Steps
        direction="vertical"
        size="small"
        current={-1}
        items={[
          {
            title: '开通阿里云短信服务',
            description: (
              <div>
                登录 <a href="https://www.aliyun.com/product/sms" target="_blank" rel="noreferrer">阿里云短信服务</a>，开通服务
              </div>
            ),
          },
          {
            title: '申请短信签名',
            description: (
              <div>
                <div>控制台 → <Text strong>国内消息</Text> → <Text strong>签名管理</Text> → 添加签名</div>
                <div>签名内容通常为公司名或产品名，需审核通过</div>
              </div>
            ),
          },
          {
            title: '创建 AccessKey',
            description: (
              <div>
                <div>进入 <a href="https://ram.console.aliyun.com/manage/ak" target="_blank" rel="noreferrer">RAM 控制台</a> → AccessKey 管理</div>
                <div>建议创建子账号并仅授予 <Text code>AliyunDysmsFullAccess</Text> 权限</div>
                <Alert
                  type="warning"
                  showIcon
                  style={{ marginTop: 8 }}
                  message="AccessKey Secret 只显示一次，请务必保存"
                />
              </div>
            ),
          },
          {
            title: '填写配置',
            description: '将 AccessKey ID、AccessKey Secret、短信签名填入右侧表单',
          },
        ]}
      />
    </div>
  );
}

function TencentSmsGuide() {
  return (
    <div style={{ fontSize: 13, lineHeight: 1.8 }}>
      <Steps
        direction="vertical"
        size="small"
        current={-1}
        items={[
          {
            title: '开通腾讯云短信服务',
            description: (
              <div>
                登录 <a href="https://cloud.tencent.com/product/sms" target="_blank" rel="noreferrer">腾讯云短信</a>，开通服务
              </div>
            ),
          },
          {
            title: '创建短信应用并申请签名',
            description: (
              <div>
                <div>控制台 → <Text strong>应用管理</Text> → 创建应用，记录 <Text strong>SDK AppID</Text></div>
                <div>然后在 <Text strong>签名管理</Text> 中申请签名</div>
              </div>
            ),
          },
          {
            title: '获取 API 密钥',
            description: (
              <div>
                进入 <a href="https://console.cloud.tencent.com/cam/capi" target="_blank" rel="noreferrer">API 密钥管理</a>，获取 SecretId 和 SecretKey
              </div>
            ),
          },
          {
            title: '填写配置',
            description: '将 SecretId、SecretKey、SDK AppID、短信签名填入右侧表单',
          },
        ]}
      />
    </div>
  );
}

// ==================== 配置表单 ====================

interface ConfigItem {
  id: string;
  service_type: string;
  provider: string;
  config: Record<string, any>;
  is_active: boolean;
  created_at: string;
  updated_at: string;
}

function ConfigForm({
  preset,
  serviceType,
  existing,
  onSaved,
  onCancel,
}: {
  preset: ProviderPreset;
  serviceType: string;
  existing?: ConfigItem;
  onSaved: () => void;
  onCancel: () => void;
}) {
  const [form] = Form.useForm();
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);
  const [testModal, setTestModal] = useState(false);
  const [testEmail, setTestEmail] = useState('');

  useEffect(() => {
    if (existing) {
      form.setFieldsValue(existing.config);
    } else if (preset.defaults) {
      form.setFieldsValue(preset.defaults);
    }
  }, [existing, preset, form]);

  const handleSave = async () => {
    try {
      const values = await form.validateFields();
      setSaving(true);
      if (existing) {
        await cloudServiceApi.update(existing.id, { config: values });
        message.success('配置已更新');
      } else {
        await cloudServiceApi.create({
          service_type: serviceType,
          provider: preset.key === 'custom_smtp' ? 'custom' : preset.key,
          config: values,
          is_active: true,
        });
        message.success('配置已创建');
      }
      onSaved();
    } catch (err: any) {
      if (err.response?.data?.detail) {
        message.error(err.response.data.detail);
      }
    } finally {
      setSaving(false);
    }
  };

  const handleTest = async () => {
    if (serviceType === 'email') {
      setTestModal(true);
      return;
    }
    // SMS test would go here
    if (!existing) {
      message.warning('请先保存配置后再测试');
      return;
    }
    setTesting(true);
    try {
      const { data } = await cloudServiceApi.test(existing.id);
      if (data.success) {
        message.success(data.message);
      } else {
        message.error(data.message);
      }
    } catch (err: any) {
      message.error(err.response?.data?.detail || '测试失败');
    } finally {
      setTesting(false);
    }
  };

  const handleTestEmail = async () => {
    if (!existing) {
      message.warning('请先保存配置后再测试');
      setTestModal(false);
      return;
    }
    if (!testEmail) {
      message.warning('请输入收件邮箱');
      return;
    }
    setTesting(true);
    try {
      const { data } = await cloudServiceApi.test(existing.id, {
        to_email: testEmail,
        subject: '测试邮件 - 统一认证平台',
        body: '这是一封测试邮件，用于验证邮件服务配置是否正确。如果您收到此邮件，说明配置成功。',
      });
      if (data.success) {
        message.success('测试邮件已发送，请检查收件箱');
      } else {
        message.error(data.message);
      }
    } catch (err: any) {
      message.error(err.response?.data?.detail || '测试发送失败');
    } finally {
      setTesting(false);
      setTestModal(false);
    }
  };

  return (
    <div style={{ display: 'flex', gap: 24 }}>
      {/* 左侧引导 */}
      <div style={{ flex: '0 0 380px', maxHeight: 600, overflow: 'auto' }}>
        <Card size="small" title={<><QuestionCircleOutlined style={{ marginRight: 6 }} />配置指引</>}>
          {preset.guide}
        </Card>
      </div>

      {/* 右侧表单 */}
      <div style={{ flex: 1 }}>
        <Card
          size="small"
          title={existing ? `编辑 ${preset.label} 配置` : `新建 ${preset.label} 配置`}
          extra={
            <Space>
              {existing && (
                <Button
                  icon={<ExperimentOutlined />}
                  loading={testing}
                  onClick={handleTest}
                >
                  测试发送
                </Button>
              )}
              <Button onClick={onCancel}>取消</Button>
              <Button type="primary" icon={<SaveOutlined />} loading={saving} onClick={handleSave}>
                保存
              </Button>
            </Space>
          }
        >
          <Form form={form} layout="vertical" style={{ maxWidth: 480 }}>
            {preset.fields.map((f) => (
              <Form.Item
                key={f.name}
                name={f.name}
                label={f.label}
                rules={f.required ? [{ required: true, message: `请输入${f.label}` }] : undefined}
                tooltip={f.tooltip}
                valuePropName={f.type === 'switch' ? 'checked' : 'value'}
              >
                {f.type === 'password' ? (
                  <Input.Password placeholder={f.placeholder} />
                ) : f.type === 'number' ? (
                  <InputNumber placeholder={f.placeholder} style={{ width: '100%' }} />
                ) : f.type === 'switch' ? (
                  <Switch />
                ) : (
                  <Input placeholder={f.placeholder} />
                )}
              </Form.Item>
            ))}
          </Form>
        </Card>
      </div>

      <Modal
        title="发送测试邮件"
        open={testModal}
        onCancel={() => setTestModal(false)}
        onOk={handleTestEmail}
        confirmLoading={testing}
        okText="发送"
      >
        <div style={{ marginBottom: 12 }}>输入收件邮箱地址，系统将发送一封测试邮件：</div>
        <Input
          placeholder="test@example.com"
          value={testEmail}
          onChange={(e) => setTestEmail(e.target.value)}
        />
      </Modal>
    </div>
  );
}

// ==================== 配置列表 ====================

function ConfigList({
  configs,
  providers,
  serviceType,
  loading,
  onEdit,
  onDelete,
  onToggle,
}: {
  configs: ConfigItem[];
  providers: ProviderPreset[];
  serviceType: string;
  loading: boolean;
  onEdit: (config: ConfigItem) => void;
  onDelete: (id: string) => void;
  onToggle: (id: string, active: boolean) => void;
}) {
  if (loading) return <Spin />;
  if (configs.length === 0) {
    return (
      <Empty
        description={`暂未配置${serviceType === 'email' ? '邮件' : '短信'}服务`}
        image={Empty.PRESENTED_IMAGE_SIMPLE}
      />
    );
  }

  return (
    <Space direction="vertical" style={{ width: '100%' }}>
      {configs.map((cfg) => {
        const preset = providers.find((p) => p.key === cfg.provider) || providers.find((p) => p.key === 'custom_smtp');
        return (
          <Card
            key={cfg.id}
            size="small"
            title={
              <Space>
                {serviceType === 'email' ? <MailOutlined /> : <MessageOutlined />}
                <span>{preset?.label || cfg.provider}</span>
                <Tag color={cfg.is_active ? 'green' : 'default'}>{cfg.is_active ? '已启用' : '已禁用'}</Tag>
              </Space>
            }
            extra={
              <Space>
                <Switch
                  size="small"
                  checked={cfg.is_active}
                  onChange={(checked) => onToggle(cfg.id, checked)}
                />
                <Button size="small" onClick={() => onEdit(cfg)}>编辑</Button>
                <Popconfirm title="确定删除此配置？" onConfirm={() => onDelete(cfg.id)}>
                  <Button size="small" danger icon={<DeleteOutlined />} />
                </Popconfirm>
              </Space>
            }
          >
            <div style={{ fontSize: 13, color: '#666' }}>
              {serviceType === 'email' && (
                <>
                  <span>SMTP: {cfg.config.smtp_host}:{cfg.config.smtp_port}</span>
                  <Divider type="vertical" />
                  <span>账号: {cfg.config.username || cfg.config.from_email || '-'}</span>
                </>
              )}
              {serviceType === 'sms' && (
                <>
                  <span>签名: {cfg.config.sign_name || '-'}</span>
                  {cfg.config.access_key_id && (
                    <>
                      <Divider type="vertical" />
                      <span>AK: {cfg.config.access_key_id?.slice(0, 8)}***</span>
                    </>
                  )}
                  {cfg.config.secret_id && (
                    <>
                      <Divider type="vertical" />
                      <span>SecretId: {cfg.config.secret_id?.slice(0, 8)}***</span>
                    </>
                  )}
                </>
              )}
              <Divider type="vertical" />
              <span>更新: {new Date(cfg.updated_at).toLocaleString()}</span>
            </div>
          </Card>
        );
      })}
    </Space>
  );
}

// ==================== 主面板 ====================

function ServiceTab({
  serviceType,
  providers,
}: {
  serviceType: 'email' | 'sms';
  providers: ProviderPreset[];
}) {
  const [configs, setConfigs] = useState<ConfigItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [editing, setEditing] = useState<{ preset: ProviderPreset; existing?: ConfigItem } | null>(null);
  const [addingProvider, setAddingProvider] = useState(false);

  const fetchConfigs = useCallback(async () => {
    setLoading(true);
    try {
      const { data } = await cloudServiceApi.list(serviceType);
      setConfigs(data.configs || []);
    } catch {
      // service may not be running
    } finally {
      setLoading(false);
    }
  }, [serviceType]);

  useEffect(() => { fetchConfigs(); }, [fetchConfigs]);

  const handleEdit = (cfg: ConfigItem) => {
    const preset = providers.find((p) => p.key === cfg.provider) || providers[providers.length - 1];
    setEditing({ preset, existing: cfg });
  };

  const handleDelete = async (id: string) => {
    try {
      await cloudServiceApi.delete(id);
      message.success('配置已删除');
      fetchConfigs();
    } catch (err: any) {
      message.error(err.response?.data?.detail || '删除失败');
    }
  };

  const handleToggle = async (id: string, active: boolean) => {
    try {
      await cloudServiceApi.update(id, { is_active: active });
      message.success(active ? '已启用' : '已禁用');
      fetchConfigs();
    } catch (err: any) {
      message.error(err.response?.data?.detail || '操作失败');
    }
  };

  const handleAddProvider = (preset: ProviderPreset) => {
    setEditing({ preset });
    setAddingProvider(false);
  };

  if (editing) {
    return (
      <ConfigForm
        preset={editing.preset}
        serviceType={serviceType}
        existing={editing.existing}
        onSaved={() => { setEditing(null); fetchConfigs(); }}
        onCancel={() => setEditing(null)}
      />
    );
  }

  return (
    <div>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Text type="secondary">
          {serviceType === 'email'
            ? '配置邮件服务后，平台将通过该服务发送验证码、密码重置、订阅提醒等邮件'
            : '配置短信服务后，平台将通过该服务发送手机验证码等短信'}
        </Text>
        <Select
          placeholder={`添加${serviceType === 'email' ? '邮件' : '短信'}服务`}
          style={{ width: 200 }}
          open={addingProvider}
          onDropdownVisibleChange={setAddingProvider}
          value={undefined}
          options={providers.map((p) => ({ label: p.label, value: p.key }))}
          onSelect={(key) => {
            const preset = providers.find((p) => p.key === key);
            if (preset) handleAddProvider(preset);
          }}
        />
      </div>

      <ConfigList
        configs={configs}
        providers={providers}
        serviceType={serviceType}
        loading={loading}
        onEdit={handleEdit}
        onDelete={handleDelete}
        onToggle={handleToggle}
      />
    </div>
  );
}

export default function CloudServicePanel() {
  return (
    <Card title="云服务配置" style={{ minHeight: 400 }}>
      <Alert
        type="info"
        showIcon
        style={{ marginBottom: 16 }}
        message="在此配置邮件和短信服务，平台将使用这些配置自动发送验证码、通知等消息。只需填入云厂商提供的 API 凭证即可。"
      />
      <Tabs
        items={[
          {
            key: 'email',
            label: <><MailOutlined /> 邮件服务</>,
            children: <ServiceTab serviceType="email" providers={EMAIL_PROVIDERS} />,
          },
          {
            key: 'sms',
            label: <><MessageOutlined /> 短信服务</>,
            children: <ServiceTab serviceType="sms" providers={SMS_PROVIDERS} />,
          },
        ]}
      />
    </Card>
  );
}
