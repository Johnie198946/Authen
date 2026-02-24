import axios from 'axios';

const USER_API = 'http://localhost:8003/api/v1';
const PERM_API = 'http://localhost:8004/api/v1';
const ORG_API = 'http://localhost:8005/api/v1';
const SUB_API = 'http://localhost:8006/api/v1';
const ADMIN_API = 'http://localhost:8007/api/v1';

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
};
