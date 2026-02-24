import { useEffect, useState, useCallback } from 'react';
import {
  Card, Descriptions, Tag, Button, Space, Switch, Input, InputNumber,
  Checkbox, message, Popconfirm, Typography, Spin, Divider, Tree, Radio,
} from 'antd';
import { ArrowLeftOutlined, CopyOutlined, KeyOutlined, SaveOutlined } from '@ant-design/icons';
import { applicationApi, orgApi, subApi } from '../../api/services';
import { useAuth } from '../../store/AuthContext';
import type { DataNode } from 'antd/es/tree';

const { Paragraph } = Typography;

interface ApplicationDetailProps {
  appId: string;
  onBack: () => void;
}

const ALL_LOGIN_METHODS = ['email', 'phone', 'wechat', 'alipay', 'google', 'apple'] as const;
const OAUTH_METHODS = new Set(['wechat', 'alipay', 'google', 'apple']);

const ALL_SCOPES = [
  'user:read', 'user:write',
  'auth:login', 'auth:register',
  'role:read', 'role:write',
  'org:read', 'org:write',
] as const;

const METHOD_LABELS: Record<string, string> = {
  email: '邮箱登录',
  phone: '手机登录',
  wechat: '微信登录',
  alipay: '支付宝登录',
  google: 'Google 登录',
  apple: 'Apple 登录',
};

interface LoginMethodState {
  method: string;
  is_enabled: boolean;
  client_id: string;
  client_secret: string;
}

export default function ApplicationDetail({ appId, onBack }: ApplicationDetailProps) {
  const { state } = useAuth();
  const userId = state.user?.id || '';

  const [loading, setLoading] = useState(true);
  const [app, setApp] = useState<any>(null);

  // Login methods
  const [loginMethods, setLoginMethods] = useState<LoginMethodState[]>([]);
  const [savingMethods, setSavingMethods] = useState(false);

  // Scopes
  const [scopes, setScopes] = useState<string[]>([]);
  const [savingScopes, setSavingScopes] = useState(false);

  // Rate limit
  const [rateLimit, setRateLimit] = useState<number>(60);
  const [savingRate, setSavingRate] = useState(false);

  // Secret reset
  const [secretModal, setSecretModal] = useState(false);
  const [newSecret, setNewSecret] = useState('');

  // Organizations
  const [orgTreeData, setOrgTreeData] = useState<DataNode[]>([]);
  const [selectedOrgs, setSelectedOrgs] = useState<string[]>([]);
  const [savingOrgs, setSavingOrgs] = useState(false);

  // Subscription plan
  const [plans, setPlans] = useState<{ id: string; name: string; duration_days: number; price: number }[]>([]);
  const [selectedPlanId, setSelectedPlanId] = useState<string>('');
  const [savingPlan, setSavingPlan] = useState(false);

  // ===== Fetch data =====
  const fetchApp = useCallback(async () => {
    try {
      const { data } = await applicationApi.get(appId, userId);
      setApp(data);
      setRateLimit(data.rate_limit ?? 60);
    } catch {
      message.error('获取应用详情失败');
    }
  }, [appId, userId]);

  const fetchLoginMethods = useCallback(async () => {
    try {
      const { data } = await applicationApi.getLoginMethods(appId, userId);
      const methods = data.login_methods || data.methods || [];
      const stateMap = new Map<string, any>();
      for (const m of methods) {
        stateMap.set(m.method, m);
      }
      setLoginMethods(
        ALL_LOGIN_METHODS.map((method) => {
          const existing = stateMap.get(method);
          return {
            method,
            is_enabled: existing?.is_enabled ?? false,
            client_id: existing?.client_id || existing?.oauth_config?.client_id || '',
            client_secret: '',
          };
        }),
      );
    } catch {
      message.error('获取登录方式失败');
      setLoginMethods(
        ALL_LOGIN_METHODS.map((method) => ({
          method,
          is_enabled: false,
          client_id: '',
          client_secret: '',
        })),
      );
    }
  }, [appId, userId]);

  const fetchScopes = useCallback(async () => {
    try {
      const { data } = await applicationApi.getScopes(appId, userId);
      setScopes(data.scopes || []);
    } catch {
      message.error('获取权限范围失败');
    }
  }, [appId, userId]);

  const fetchOrganizations = useCallback(async () => {
    try {
      const [treeRes, bindingRes] = await Promise.all([
        orgApi.tree(),
        applicationApi.getOrganizations(appId, userId),
      ]);
      const toTreeData = (nodes: any[]): DataNode[] =>
        nodes.map((n: any) => ({
          key: n.id,
          title: n.name,
          children: n.children?.length ? toTreeData(n.children) : undefined,
        }));
      setOrgTreeData(toTreeData(treeRes.data));
      setSelectedOrgs(bindingRes.data.organization_ids || []);
    } catch {
      // org service may not be running
    }
  }, [appId, userId]);

  const fetchSubscriptionPlan = useCallback(async () => {
    try {
      const [plansRes, bindingRes] = await Promise.all([
        subApi.listPlans(),
        applicationApi.getSubscriptionPlan(appId, userId),
      ]);
      setPlans(plansRes.data);
      setSelectedPlanId(bindingRes.data.plan_id || '');
    } catch {
      // subscription service may not be running
    }
  }, [appId, userId]);

  useEffect(() => {
    if (!userId) return;
    setLoading(true);
    Promise.all([fetchApp(), fetchLoginMethods(), fetchScopes(), fetchOrganizations(), fetchSubscriptionPlan()]).finally(() =>
      setLoading(false),
    );
  }, [fetchApp, fetchLoginMethods, fetchScopes, fetchOrganizations, fetchSubscriptionPlan, userId]);

  // ===== Login methods handlers =====
  const handleMethodToggle = (method: string, checked: boolean) => {
    setLoginMethods((prev) =>
      prev.map((m) => (m.method === method ? { ...m, is_enabled: checked } : m)),
    );
  };

  const handleOAuthField = (method: string, field: 'client_id' | 'client_secret', value: string) => {
    setLoginMethods((prev) =>
      prev.map((m) => (m.method === method ? { ...m, [field]: value } : m)),
    );
  };

  const saveLoginMethods = async () => {
    setSavingMethods(true);
    try {
      const payload = loginMethods.map((m) => {
        const item: any = { method: m.method, is_enabled: m.is_enabled };
        if (OAUTH_METHODS.has(m.method) && m.is_enabled) {
          if (m.client_id) item.client_id = m.client_id;
          if (m.client_secret) item.client_secret = m.client_secret;
        }
        return item;
      });
      await applicationApi.updateLoginMethods(appId, { login_methods: payload } as any, userId);
      message.success('登录方式已更新');
      await fetchLoginMethods();
    } catch (err: any) {
      message.error(err.response?.data?.detail || '更新登录方式失败');
    } finally {
      setSavingMethods(false);
    }
  };

  // ===== Scopes handlers =====
  const saveScopes = async () => {
    setSavingScopes(true);
    try {
      await applicationApi.updateScopes(appId, { scopes }, userId);
      message.success('权限范围已更新');
    } catch (err: any) {
      message.error(err.response?.data?.detail || '更新权限范围失败');
    } finally {
      setSavingScopes(false);
    }
  };

  // ===== Rate limit handlers =====
  const saveRateLimit = async () => {
    setSavingRate(true);
    try {
      await applicationApi.update(appId, { rate_limit: rateLimit }, userId);
      message.success('限流配置已更新');
      await fetchApp();
    } catch (err: any) {
      message.error(err.response?.data?.detail || '更新限流配置失败');
    } finally {
      setSavingRate(false);
    }
  };

  // ===== Reset secret =====
  const handleResetSecret = async () => {
    try {
      const { data } = await applicationApi.resetSecret(appId, userId);
      setNewSecret(data.app_secret);
      setSecretModal(true);
      message.success('密钥已重置');
    } catch (err: any) {
      message.error(err.response?.data?.detail || '重置密钥失败');
    }
  };

  // ===== Organizations handlers =====
  const saveOrganizations = async () => {
    setSavingOrgs(true);
    try {
      await applicationApi.updateOrganizations(appId, { organization_ids: selectedOrgs }, userId);
      message.success('组织架构配置已更新');
    } catch (err: any) {
      message.error(err.response?.data?.detail || '更新组织架构失败');
    } finally {
      setSavingOrgs(false);
    }
  };

  // ===== Subscription plan handlers =====
  const saveSubscriptionPlan = async () => {
    setSavingPlan(true);
    try {
      await applicationApi.updateSubscriptionPlan(appId, { plan_id: selectedPlanId || null }, userId);
      message.success('订阅计划配置已更新');
    } catch (err: any) {
      message.error(err.response?.data?.detail || '更新订阅计划失败');
    } finally {
      setSavingPlan(false);
    }
  };

  if (loading) {
    return (
      <div style={{ textAlign: 'center', padding: 80 }}>
        <Spin size="large" />
      </div>
    );
  }

  return (
    <div>
      {/* Header with back button */}
      <div style={{ marginBottom: 16 }}>
        <Button icon={<ArrowLeftOutlined />} onClick={onBack} style={{ marginRight: 12 }}>
          返回列表
        </Button>
      </div>

      {/* Basic info */}
      <Card title="基本信息" style={{ marginBottom: 16 }}>
        <Descriptions column={2} bordered size="small">
          <Descriptions.Item label="应用名称">{app?.name || '-'}</Descriptions.Item>
          <Descriptions.Item label="状态">
            <Tag color={app?.status === 'active' ? 'green' : 'red'}>
              {app?.status === 'active' ? '启用' : '禁用'}
            </Tag>
          </Descriptions.Item>
          <Descriptions.Item label="App ID">
            <Paragraph copyable={{ icon: <CopyOutlined /> }} style={{ marginBottom: 0 }}>
              {app?.app_id || appId}
            </Paragraph>
          </Descriptions.Item>
          <Descriptions.Item label="创建时间">
            {app?.created_at ? new Date(app.created_at).toLocaleString() : '-'}
          </Descriptions.Item>
          <Descriptions.Item label="描述" span={2}>
            {app?.description || '暂无描述'}
          </Descriptions.Item>
        </Descriptions>
      </Card>

      {/* Login methods */}
      <Card
        title="登录方式配置"
        style={{ marginBottom: 16 }}
        extra={
          <Button type="primary" icon={<SaveOutlined />} loading={savingMethods} onClick={saveLoginMethods}>
            保存
          </Button>
        }
      >
        {loginMethods.map((m) => (
          <div key={m.method} style={{ marginBottom: 16 }}>
            <Space align="center" style={{ marginBottom: OAUTH_METHODS.has(m.method) && m.is_enabled ? 8 : 0 }}>
              <Switch
                checked={m.is_enabled}
                onChange={(checked) => handleMethodToggle(m.method, checked)}
              />
              <span style={{ fontWeight: 500 }}>{METHOD_LABELS[m.method] || m.method}</span>
              {OAUTH_METHODS.has(m.method) && <Tag color="blue">OAuth</Tag>}
            </Space>
            {OAUTH_METHODS.has(m.method) && m.is_enabled && (
              <div style={{ marginLeft: 48, marginTop: 8 }}>
                <Space direction="vertical" style={{ width: '100%', maxWidth: 480 }}>
                  <Input
                    addonBefore="Client ID"
                    placeholder="请输入 Client ID"
                    value={m.client_id}
                    onChange={(e) => handleOAuthField(m.method, 'client_id', e.target.value)}
                  />
                  <Input.Password
                    addonBefore="Client Secret"
                    placeholder="留空则不修改"
                    value={m.client_secret}
                    onChange={(e) => handleOAuthField(m.method, 'client_secret', e.target.value)}
                  />
                </Space>
              </div>
            )}
            {m.method !== ALL_LOGIN_METHODS[ALL_LOGIN_METHODS.length - 1] && <Divider style={{ margin: '12px 0' }} />}
          </div>
        ))}
      </Card>

      {/* Scope permissions */}
      <Card
        title="权限范围配置"
        style={{ marginBottom: 16 }}
        extra={
          <Button type="primary" icon={<SaveOutlined />} loading={savingScopes} onClick={saveScopes}>
            保存
          </Button>
        }
      >
        <Checkbox.Group
          value={scopes}
          onChange={(values) => setScopes(values as string[])}
          style={{ width: '100%' }}
        >
          <Space wrap size={[24, 12]}>
            {ALL_SCOPES.map((scope) => (
              <Checkbox key={scope} value={scope}>
                {scope}
              </Checkbox>
            ))}
          </Space>
        </Checkbox.Group>
      </Card>

      {/* Rate limit */}
      <Card
        title="限流配置"
        style={{ marginBottom: 16 }}
        extra={
          <Button type="primary" icon={<SaveOutlined />} loading={savingRate} onClick={saveRateLimit}>
            保存
          </Button>
        }
      >
        <Space align="center">
          <span>每分钟请求限制：</span>
          <InputNumber
            min={1}
            max={100000}
            value={rateLimit}
            onChange={(v) => setRateLimit(v ?? 60)}
            style={{ width: 160 }}
            addonAfter="次/分钟"
          />
        </Space>
      </Card>

      {/* Organizations */}
      <Card
        title="组织架构配置"
        style={{ marginBottom: 16 }}
        extra={
          <Button type="primary" icon={<SaveOutlined />} loading={savingOrgs} onClick={saveOrganizations}>
            保存
          </Button>
        }
      >
        {orgTreeData.length > 0 ? (
          <Tree
            checkable
            checkedKeys={selectedOrgs}
            onCheck={(checked) => setSelectedOrgs((Array.isArray(checked) ? checked : checked.checked) as string[])}
            treeData={orgTreeData}
            defaultExpandAll
          />
        ) : (
          <span style={{ color: '#999' }}>暂无组织数据</span>
        )}
      </Card>

      {/* Subscription plan */}
      <Card
        title="订阅计划配置"
        style={{ marginBottom: 16 }}
        extra={
          <Button type="primary" icon={<SaveOutlined />} loading={savingPlan} onClick={saveSubscriptionPlan}>
            保存
          </Button>
        }
      >
        <Radio.Group value={selectedPlanId} onChange={(e) => setSelectedPlanId(e.target.value)} style={{ width: '100%' }}>
          <Space direction="vertical" style={{ width: '100%' }}>
            <Radio value="">不绑定订阅计划</Radio>
            {plans.map((plan) => (
              <Radio key={plan.id} value={plan.id}>
                <Space>
                  <span>{plan.name}</span>
                  <Tag color="blue">{plan.duration_days}天</Tag>
                  <Tag color="green">¥{plan.price}</Tag>
                </Space>
              </Radio>
            ))}
          </Space>
        </Radio.Group>
      </Card>

      {/* Danger zone */}
      <Card title="危险操作" style={{ marginBottom: 16, borderColor: '#ff4d4f' }}>
        <Space direction="vertical">
          <div>
            <span style={{ marginRight: 12 }}>重置应用密钥（旧密钥将立即失效）：</span>
            <Popconfirm
              title="确定重置密钥？"
              description="重置后旧密钥将立即失效，使用旧密钥的三方系统将无法访问。"
              onConfirm={handleResetSecret}
              okText="确定重置"
              cancelText="取消"
              okButtonProps={{ danger: true }}
            >
              <Button danger icon={<KeyOutlined />}>
                重置 App Secret
              </Button>
            </Popconfirm>
          </div>
        </Space>
      </Card>

      {/* Secret display modal */}
      {secretModal && (
        <div
          style={{
            position: 'fixed', top: 0, left: 0, right: 0, bottom: 0,
            background: 'rgba(0,0,0,0.45)', zIndex: 1000,
            display: 'flex', alignItems: 'center', justifyContent: 'center',
          }}
        >
          <Card
            title="新密钥"
            style={{ width: 520 }}
            extra={<Button type="primary" onClick={() => setSecretModal(false)}>我已保存</Button>}
          >
            <div style={{ marginBottom: 16, color: '#ff4d4f', fontWeight: 'bold' }}>
              ⚠️ 请妥善保存以下密钥，关闭后将无法再次查看！
            </div>
            <div>
              <div style={{ color: '#666', marginBottom: 4 }}>App Secret:</div>
              <Paragraph copyable style={{ marginBottom: 0, wordBreak: 'break-all' }}>
                {newSecret}
              </Paragraph>
            </div>
          </Card>
        </div>
      )}
    </div>
  );
}
