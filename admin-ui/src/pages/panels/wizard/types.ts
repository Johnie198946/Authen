// Shared types and constants for the App Config Wizard

export interface LoginMethodConfig {
  method: string;
  is_enabled: boolean;
  client_id: string;
  client_secret: string;
}

export interface AutoProvisionData {
  enabled: boolean;
  roleIds: string[];
  permissionIds: string[];
  organizationId?: string;
  subscriptionPlanId?: string;
}

export interface WizardData {
  basicInfo: {
    name: string;
    description: string;
  };
  loginMethods: LoginMethodConfig[];
  scopes: string[];
  rateLimit: number;
  organizations: string[];
  subscriptionPlanId: string;
  autoProvision: AutoProvisionData;
}

export interface WizardStep {
  title: string;
  key: string;
}

export const INITIAL_WIZARD_DATA: WizardData = {
  basicInfo: { name: '', description: '' },
  loginMethods: [
    { method: 'email', is_enabled: false, client_id: '', client_secret: '' },
    { method: 'phone', is_enabled: false, client_id: '', client_secret: '' },
    { method: 'wechat', is_enabled: false, client_id: '', client_secret: '' },
    { method: 'alipay', is_enabled: false, client_id: '', client_secret: '' },
    { method: 'google', is_enabled: false, client_id: '', client_secret: '' },
    { method: 'apple', is_enabled: false, client_id: '', client_secret: '' },
  ],
  scopes: [],
  rateLimit: 60,
  organizations: [],
  subscriptionPlanId: '',
  autoProvision: {
    enabled: false,
    roleIds: [],
    permissionIds: [],
    organizationId: undefined,
    subscriptionPlanId: undefined,
  },
};

export const WIZARD_STEPS = [
  { title: '基本信息', key: 'basicInfo' },
  { title: '登录方式', key: 'loginMethods' },
  { title: '权限范围', key: 'scopes' },
  { title: '限流配置', key: 'rateLimit' },
  { title: '组织架构', key: 'organizations' },
  { title: '订阅计划', key: 'subscriptionPlan' },
  { title: '自动配置', key: 'autoProvision' },
  { title: '确认创建', key: 'review' },
] as const;

export const ALL_LOGIN_METHODS = ['email', 'phone', 'wechat', 'alipay', 'google', 'apple'] as const;

export const OAUTH_METHODS = new Set(['wechat', 'alipay', 'google', 'apple']);

export const ALL_SCOPES = [
  'user:read', 'user:write', 'auth:login', 'auth:register',
  'role:read', 'role:write', 'org:read', 'org:write',
] as const;

export const METHOD_LABELS: Record<string, string> = {
  email: '邮箱登录',
  phone: '手机登录',
  wechat: '微信登录',
  alipay: '支付宝登录',
  google: 'Google 登录',
  apple: 'Apple 登录',
};
