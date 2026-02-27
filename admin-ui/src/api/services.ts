import client from './client';

// All requests go through Vite proxy via relative URLs
// Proxy rules in vite.config.ts route to the correct microservice
// Interceptors (token attach + 401 redirect) are handled in client.ts

// ===== 用户 =====
export const userApi = {
  list: (page = 1, pageSize = 20, search?: string) =>
    client.get('/users', { params: { page, page_size: pageSize, search } }),
  get: (id: string) => client.get(`/users/${id}`),
  create: (data: { username: string; email?: string; phone?: string; password: string }) =>
    client.post('/users', data),
  update: (id: string, data: { username?: string; email?: string; phone?: string; status?: string }) =>
    client.put(`/users/${id}`, data),
  delete: (id: string) => client.delete(`/users/${id}`),
  resetPassword: (id: string) => client.post(`/users/${id}/reset-password`),
};

// ===== 角色 =====
export const roleApi = {
  list: () => client.get('/roles'),
  create: (data: { name: string; description?: string }) => client.post('/roles', data),
  update: (id: string, data: { name: string; description?: string }) => client.put(`/roles/${id}`, data),
  delete: (id: string) => client.delete(`/roles/${id}`),
  getPermissions: (roleId: string) => client.get(`/roles/${roleId}/permissions`),
  assignPermissions: (roleId: string, permissionIds: string[]) =>
    client.post(`/roles/${roleId}/permissions`, permissionIds),
  removePermission: (roleId: string, permId: string) =>
    client.delete(`/roles/${roleId}/permissions/${permId}`),
};

// ===== 权限 =====
export const permissionApi = {
  list: () => client.get('/permissions'),
  create: (data: { name: string; resource: string; action: string; description?: string }) =>
    client.post('/permissions', data),
  update: (id: string, data: { name: string; resource: string; action: string; description?: string }) =>
    client.put(`/permissions/${id}`, data),
  delete: (id: string) => client.delete(`/permissions/${id}`),
};

// ===== 用户-角色关联 =====
export const userRoleApi = {
  getUserRoles: (userId: string) => client.get(`/users/${userId}/roles`),
  assignRoles: (userId: string, roleIds: string[]) =>
    client.post(`/users/${userId}/roles`, { role_ids: roleIds }),
  removeRole: (userId: string, roleId: string) =>
    client.delete(`/users/${userId}/roles/${roleId}`),
  getUserPermissions: (userId: string) => client.get(`/users/${userId}/permissions`),
};

// ===== 组织 =====
export const orgApi = {
  tree: () => client.get('/organizations/tree'),
  create: (data: { name: string; parent_id?: string }) => client.post('/organizations', data),
  update: (id: string, data: { name: string }) => client.put(`/organizations/${id}`, data),
  delete: (id: string) => client.delete(`/organizations/${id}`),
  getUsers: (orgId: string) => client.get(`/organizations/${orgId}/users`),
  assignUsers: (orgId: string, userIds: string[]) =>
    client.post(`/organizations/${orgId}/users`, userIds),
  removeUser: (orgId: string, userId: string) =>
    client.delete(`/organizations/${orgId}/users/${userId}`),
};

// ===== 订阅 =====
export const subApi = {
  listPlans: () => client.get('/subscriptions/plans'),
  createPlan: (data: { name: string; description?: string; duration_days: number; price: number }) =>
    client.post('/subscriptions/plans', data),
  updatePlan: (id: string, data: { name: string; description?: string; duration_days: number; price: number }) =>
    client.put(`/subscriptions/plans/${id}`, data),
  deletePlan: (id: string) => client.delete(`/subscriptions/plans/${id}`),
  getUserSub: (userId: string) => client.get(`/users/${userId}/subscription`),
  createSub: (userId: string, data: { plan_id: string; auto_renew?: boolean }) =>
    client.post(`/users/${userId}/subscription`, data),
  cancelSub: (userId: string) => client.delete(`/users/${userId}/subscription`),
};

// ===== 应用管理 =====
export const applicationApi = {
  // CRUD
  list: (userId: string) =>
    client.get('/admin/applications', { params: { user_id: userId } }),
  get: (appId: string, userId: string) =>
    client.get(`/admin/applications/${appId}`, { params: { user_id: userId } }),
  create: (data: { name: string; description?: string }, userId: string) =>
    client.post('/admin/applications', data, { params: { user_id: userId } }),
  update: (appId: string, data: { name?: string; description?: string; rate_limit?: number }, userId: string) =>
    client.put(`/admin/applications/${appId}`, data, { params: { user_id: userId } }),
  delete: (appId: string, userId: string) =>
    client.delete(`/admin/applications/${appId}`, { params: { user_id: userId } }),

  // 凭证管理
  resetSecret: (appId: string, userId: string) =>
    client.post(`/admin/applications/${appId}/reset-secret`, null, { params: { user_id: userId } }),

  // 状态管理
  updateStatus: (appId: string, data: { status: string }, userId: string) =>
    client.put(`/admin/applications/${appId}/status`, data, { params: { user_id: userId } }),

  // 登录方式配置
  getLoginMethods: (appId: string, userId: string) =>
    client.get(`/admin/applications/${appId}/login-methods`, { params: { user_id: userId } }),
  updateLoginMethods: (appId: string, data: { login_methods: Array<{ method: string; is_enabled: boolean; client_id?: string; client_secret?: string }> }, userId: string) =>
    client.put(`/admin/applications/${appId}/login-methods`, data, { params: { user_id: userId } }),

  // Scope 配置
  getScopes: (appId: string, userId: string) =>
    client.get(`/admin/applications/${appId}/scopes`, { params: { user_id: userId } }),
  updateScopes: (appId: string, data: { scopes: string[] }, userId: string) =>
    client.put(`/admin/applications/${appId}/scopes`, data, { params: { user_id: userId } }),

  // 组织架构绑定
  getOrganizations: (appId: string, userId: string) =>
    client.get(`/admin/applications/${appId}/organizations`, { params: { user_id: userId } }),
  updateOrganizations: (appId: string, data: { organization_ids: string[] }, userId: string) =>
    client.put(`/admin/applications/${appId}/organizations`, data, { params: { user_id: userId } }),

  // 订阅计划绑定
  getSubscriptionPlan: (appId: string, userId: string) =>
    client.get(`/admin/applications/${appId}/subscription-plan`, { params: { user_id: userId } }),
  updateSubscriptionPlan: (appId: string, data: { plan_id: string | null }, userId: string) =>
    client.put(`/admin/applications/${appId}/subscription-plan`, data, { params: { user_id: userId } }),

  // 自动配置
  getAutoProvision: (appId: string, userId: string) =>
    client.get(`/admin/applications/${appId}/auto-provision`, { params: { user_id: userId } }),
  updateAutoProvision: (appId: string, data: { role_ids?: string[]; permission_ids?: string[]; organization_id?: string; subscription_plan_id?: string; is_enabled: boolean }, userId: string) =>
    client.put(`/admin/applications/${appId}/auto-provision`, data, { params: { user_id: userId } }),
  deleteAutoProvision: (appId: string, userId: string) =>
    client.delete(`/admin/applications/${appId}/auto-provision`, { params: { user_id: userId } }),

  // Webhook 密钥重置
  resetWebhookSecret: (appId: string) =>
    client.post(`/admin/applications/${appId}/reset-webhook-secret`),

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
    client.get(`/admin/webhook-events`, { params }),
};


// ===== 云服务配置 =====
export const cloudServiceApi = {
  list: (serviceType?: string) =>
    client.get(`/admin/cloud-services`, { params: { service_type: serviceType } }),
  create: (data: { service_type: string; provider: string; config: Record<string, any>; is_active?: boolean }, skipValidation = true) =>
    client.post(`/admin/cloud-services`, data, { params: { skip_validation: skipValidation } }),
  update: (configId: string, data: { config?: Record<string, any>; is_active?: boolean }, skipValidation = true) =>
    client.put(`/admin/cloud-services/${configId}`, data, { params: { skip_validation: skipValidation } }),
  delete: (configId: string) =>
    client.delete(`/admin/cloud-services/${configId}`),
  test: (configId: string, data?: Record<string, any>) =>
    client.post(`/admin/cloud-services/${configId}/test`, data),
};


// ===== 配额管理 =====
export const quotaApi = {
  overview: (sortBy?: string) =>
    client.get(`/admin/quota/overview`, { params: { sort_by: sortBy } }),
  detail: (appId: string) =>
    client.get(`/admin/quota/${appId}`),
  override: (appId: string, data: { request_quota?: number; token_quota?: number }) =>
    client.put(`/admin/quota/${appId}/override`, data),
  reset: (appId: string) =>
    client.post(`/admin/quota/${appId}/reset`),
  history: (appId: string, params?: { start_time?: string; end_time?: string; page?: number; page_size?: number }) =>
    client.get(`/admin/quota/${appId}/history`, { params }),
};

// ===== 消息模板 =====
export const templateApi = {
  list: (templateType?: string) =>
    client.get(`/admin/templates`, { params: { template_type: templateType } }),
  get: (id: string) =>
    client.get(`/admin/templates/${id}`),
  create: (data: { name: string; type: string; subject?: string; content: string; variables?: Record<string, string> }) =>
    client.post(`/admin/templates`, data),
  update: (id: string, data: { name?: string; subject?: string; content?: string; variables?: Record<string, string> }) =>
    client.put(`/admin/templates/${id}`, data),
  delete: (id: string) =>
    client.delete(`/admin/templates/${id}`),
};
