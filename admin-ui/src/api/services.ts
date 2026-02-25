import axios from 'axios';

const USER_API = 'http://localhost:8003/api/v1';
const PERM_API = 'http://localhost:8004/api/v1';
const ORG_API = 'http://localhost:8005/api/v1';
const SUB_API = 'http://localhost:8006/api/v1';
const ADMIN_API = 'http://localhost:8007/api/v1';

// Attach token to all axios requests from this module
axios.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Handle 401/403 responses by clearing stale session
axios.interceptors.response.use(
  (response) => response,
  (error) => {
    const status = error.response?.status;
    if (status === 401 || status === 403) {
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
      localStorage.removeItem('user');
      window.location.href = '/login';
    }
    return Promise.reject(error);
  }
);

// ===== 用户 =====
export const userApi = {
  list: (page = 1, pageSize = 20, search?: string) =>
    axios.get(`${USER_API}/users`, { params: { page, page_size: pageSize, search } }),
  get: (id: string) => axios.get(`${USER_API}/users/${id}`),
  create: (data: { username: string; email?: string; phone?: string; password: string }) =>
    axios.post(`${USER_API}/users`, data),
  update: (id: string, data: { username?: string; email?: string; phone?: string; status?: string }) =>
    axios.put(`${USER_API}/users/${id}`, data),
  delete: (id: string) => axios.delete(`${USER_API}/users/${id}`),
  resetPassword: (id: string) => axios.post(`${USER_API}/users/${id}/reset-password`),
};

// ===== 角色 =====
export const roleApi = {
  list: () => axios.get(`${PERM_API}/roles`),
  create: (data: { name: string; description?: string }) => axios.post(`${PERM_API}/roles`, data),
  update: (id: string, data: { name: string; description?: string }) => axios.put(`${PERM_API}/roles/${id}`, data),
  delete: (id: string) => axios.delete(`${PERM_API}/roles/${id}`),
  getPermissions: (roleId: string) => axios.get(`${PERM_API}/roles/${roleId}/permissions`),
  assignPermissions: (roleId: string, permissionIds: string[]) =>
    axios.post(`${PERM_API}/roles/${roleId}/permissions`, permissionIds),
  removePermission: (roleId: string, permId: string) =>
    axios.delete(`${PERM_API}/roles/${roleId}/permissions/${permId}`),
};

// ===== 权限 =====
export const permissionApi = {
  list: () => axios.get(`${PERM_API}/permissions`),
  create: (data: { name: string; resource: string; action: string; description?: string }) =>
    axios.post(`${PERM_API}/permissions`, data),
  update: (id: string, data: { name: string; resource: string; action: string; description?: string }) =>
    axios.put(`${PERM_API}/permissions/${id}`, data),
  delete: (id: string) => axios.delete(`${PERM_API}/permissions/${id}`),
};

// ===== 用户-角色关联 =====
export const userRoleApi = {
  getUserRoles: (userId: string) => axios.get(`${PERM_API}/users/${userId}/roles`),
  assignRoles: (userId: string, roleIds: string[]) =>
    axios.post(`${PERM_API}/users/${userId}/roles`, { role_ids: roleIds }),
  removeRole: (userId: string, roleId: string) =>
    axios.delete(`${PERM_API}/users/${userId}/roles/${roleId}`),
  getUserPermissions: (userId: string) => axios.get(`${PERM_API}/users/${userId}/permissions`),
};

// ===== 组织 =====
export const orgApi = {
  tree: () => axios.get(`${ORG_API}/organizations/tree`),
  create: (data: { name: string; parent_id?: string }) => axios.post(`${ORG_API}/organizations`, data),
  update: (id: string, data: { name: string }) => axios.put(`${ORG_API}/organizations/${id}`, data),
  delete: (id: string) => axios.delete(`${ORG_API}/organizations/${id}`),
  getUsers: (orgId: string) => axios.get(`${ORG_API}/organizations/${orgId}/users`),
  assignUsers: (orgId: string, userIds: string[]) =>
    axios.post(`${ORG_API}/organizations/${orgId}/users`, userIds),
  removeUser: (orgId: string, userId: string) =>
    axios.delete(`${ORG_API}/organizations/${orgId}/users/${userId}`),
};

// ===== 订阅 =====
export const subApi = {
  listPlans: () => axios.get(`${SUB_API}/subscriptions/plans`),
  createPlan: (data: { name: string; description?: string; duration_days: number; price: number }) =>
    axios.post(`${SUB_API}/subscriptions/plans`, data),
  updatePlan: (id: string, data: { name: string; description?: string; duration_days: number; price: number }) =>
    axios.put(`${SUB_API}/subscriptions/plans/${id}`, data),
  deletePlan: (id: string) => axios.delete(`${SUB_API}/subscriptions/plans/${id}`),
  getUserSub: (userId: string) => axios.get(`${SUB_API}/users/${userId}/subscription`),
  createSub: (userId: string, data: { plan_id: string; auto_renew?: boolean }) =>
    axios.post(`${SUB_API}/users/${userId}/subscription`, data),
  cancelSub: (userId: string) => axios.delete(`${SUB_API}/users/${userId}/subscription`),
};

// ===== 应用管理 =====
export const applicationApi = {
  // CRUD
  list: (userId: string) =>
    axios.get(`${ADMIN_API}/admin/applications`, { params: { user_id: userId } }),
  get: (appId: string, userId: string) =>
    axios.get(`${ADMIN_API}/admin/applications/${appId}`, { params: { user_id: userId } }),
  create: (data: { name: string; description?: string }, userId: string) =>
    axios.post(`${ADMIN_API}/admin/applications`, data, { params: { user_id: userId } }),
  update: (appId: string, data: { name?: string; description?: string; rate_limit?: number }, userId: string) =>
    axios.put(`${ADMIN_API}/admin/applications/${appId}`, data, { params: { user_id: userId } }),
  delete: (appId: string, userId: string) =>
    axios.delete(`${ADMIN_API}/admin/applications/${appId}`, { params: { user_id: userId } }),

  // 凭证管理
  resetSecret: (appId: string, userId: string) =>
    axios.post(`${ADMIN_API}/admin/applications/${appId}/reset-secret`, null, { params: { user_id: userId } }),

  // 状态管理
  updateStatus: (appId: string, data: { status: string }, userId: string) =>
    axios.put(`${ADMIN_API}/admin/applications/${appId}/status`, data, { params: { user_id: userId } }),

  // 登录方式配置
  getLoginMethods: (appId: string, userId: string) =>
    axios.get(`${ADMIN_API}/admin/applications/${appId}/login-methods`, { params: { user_id: userId } }),
  updateLoginMethods: (appId: string, data: { login_methods: Array<{ method: string; is_enabled: boolean; client_id?: string; client_secret?: string }> }, userId: string) =>
    axios.put(`${ADMIN_API}/admin/applications/${appId}/login-methods`, data, { params: { user_id: userId } }),

  // Scope 配置
  getScopes: (appId: string, userId: string) =>
    axios.get(`${ADMIN_API}/admin/applications/${appId}/scopes`, { params: { user_id: userId } }),
  updateScopes: (appId: string, data: { scopes: string[] }, userId: string) =>
    axios.put(`${ADMIN_API}/admin/applications/${appId}/scopes`, data, { params: { user_id: userId } }),

  // 组织架构绑定
  getOrganizations: (appId: string, userId: string) =>
    axios.get(`${ADMIN_API}/admin/applications/${appId}/organizations`, { params: { user_id: userId } }),
  updateOrganizations: (appId: string, data: { organization_ids: string[] }, userId: string) =>
    axios.put(`${ADMIN_API}/admin/applications/${appId}/organizations`, data, { params: { user_id: userId } }),

  // 订阅计划绑定
  getSubscriptionPlan: (appId: string, userId: string) =>
    axios.get(`${ADMIN_API}/admin/applications/${appId}/subscription-plan`, { params: { user_id: userId } }),
  updateSubscriptionPlan: (appId: string, data: { plan_id: string | null }, userId: string) =>
    axios.put(`${ADMIN_API}/admin/applications/${appId}/subscription-plan`, data, { params: { user_id: userId } }),

  // 自动配置
  getAutoProvision: (appId: string, userId: string) =>
    axios.get(`${ADMIN_API}/admin/applications/${appId}/auto-provision`, { params: { user_id: userId } }),
  updateAutoProvision: (appId: string, data: { role_ids?: string[]; permission_ids?: string[]; organization_id?: string; subscription_plan_id?: string; is_enabled: boolean }, userId: string) =>
    axios.put(`${ADMIN_API}/admin/applications/${appId}/auto-provision`, data, { params: { user_id: userId } }),
  deleteAutoProvision: (appId: string, userId: string) =>
    axios.delete(`${ADMIN_API}/admin/applications/${appId}/auto-provision`, { params: { user_id: userId } }),

  // Webhook 密钥重置
  resetWebhookSecret: (appId: string) =>
    axios.post(`${ADMIN_API}/admin/applications/${appId}/reset-webhook-secret`),

  // Webhook 事件日志查询
  getWebhookEvents: (params: {
    app_id?: string;
    event_type?: string;
    status?: string;
    start_time?: string;
    end_time?: string;
    page?: number;
    page_size?: number;
  }) =>
    axios.get(`${ADMIN_API}/admin/webhook-events`, { params }),
};


// ===== 云服务配置 =====
export const cloudServiceApi = {
  list: (serviceType?: string) =>
    axios.get(`${ADMIN_API}/admin/cloud-services`, { params: { service_type: serviceType } }),
  create: (data: { service_type: string; provider: string; config: Record<string, any>; is_active?: boolean }, skipValidation = true) =>
    axios.post(`${ADMIN_API}/admin/cloud-services`, data, { params: { skip_validation: skipValidation } }),
  update: (configId: string, data: { config?: Record<string, any>; is_active?: boolean }, skipValidation = true) =>
    axios.put(`${ADMIN_API}/admin/cloud-services/${configId}`, data, { params: { skip_validation: skipValidation } }),
  delete: (configId: string) =>
    axios.delete(`${ADMIN_API}/admin/cloud-services/${configId}`),
  test: (configId: string, data?: Record<string, any>) =>
    axios.post(`${ADMIN_API}/admin/cloud-services/${configId}/test`, data),
};


// ===== 配额管理 =====
export const quotaApi = {
  overview: (sortBy?: string) =>
    axios.get(`${ADMIN_API}/admin/quota/overview`, { params: { sort_by: sortBy } }),
  detail: (appId: string) =>
    axios.get(`${ADMIN_API}/admin/quota/${appId}`),
  override: (appId: string, data: { request_quota?: number; token_quota?: number }) =>
    axios.put(`${ADMIN_API}/admin/quota/${appId}/override`, data),
  reset: (appId: string) =>
    axios.post(`${ADMIN_API}/admin/quota/${appId}/reset`),
  history: (appId: string, params?: { start_time?: string; end_time?: string; page?: number; page_size?: number }) =>
    axios.get(`${ADMIN_API}/admin/quota/${appId}/history`, { params }),
};

// ===== 消息模板 =====
export const templateApi = {
  list: (templateType?: string) =>
    axios.get(`${ADMIN_API}/admin/templates`, { params: { template_type: templateType } }),
  get: (id: string) =>
    axios.get(`${ADMIN_API}/admin/templates/${id}`),
  create: (data: { name: string; type: string; subject?: string; content: string; variables?: Record<string, string> }) =>
    axios.post(`${ADMIN_API}/admin/templates`, data),
  update: (id: string, data: { name?: string; subject?: string; content?: string; variables?: Record<string, string> }) =>
    axios.put(`${ADMIN_API}/admin/templates/${id}`, data),
  delete: (id: string) =>
    axios.delete(`${ADMIN_API}/admin/templates/${id}`),
};
