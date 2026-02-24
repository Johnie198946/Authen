import { useEffect, useState } from 'react';
import { Card, Table, Tag, Button, Space, Input, Modal, Form, Select, message, Popconfirm, Drawer, Descriptions, Tabs } from 'antd';
import { PlusOutlined, ReloadOutlined, EditOutlined, DeleteOutlined, KeyOutlined, ApartmentOutlined, CrownOutlined, LockOutlined } from '@ant-design/icons';
import { userApi, roleApi, userRoleApi, orgApi, subApi } from '../../api/services';

export default function UsersPanel() {
  const [users, setUsers] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [search, setSearch] = useState('');
  const [editModal, setEditModal] = useState(false);
  const [editingUser, setEditingUser] = useState<any>(null);
  const [form] = Form.useForm();
  const [saving, setSaving] = useState(false);
  // 详情抽屉
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [selectedUser, setSelectedUser] = useState<any>(null);
  const [detailRoles, setDetailRoles] = useState<any[]>([]);
  const [detailPerms, setDetailPerms] = useState<any[]>([]);
  const [detailLoading, setDetailLoading] = useState(false);
  // 角色分配
  const [roleModal, setRoleModal] = useState(false);
  const [allRoles, setAllRoles] = useState<any[]>([]);
  const [userRoles, setUserRoles] = useState<string[]>([]);
  const [roleLoading, setRoleLoading] = useState(false);
  // 组织分配
  const [orgModal, setOrgModal] = useState(false);
  const [allOrgs, setAllOrgs] = useState<any[]>([]);
  const [orgLoading, setOrgLoading] = useState(false);
  const [selectedOrgId, setSelectedOrgId] = useState<string | undefined>();
  // 订阅管理
  const [subModal, setSubModal] = useState(false);
  const [plans, setPlans] = useState<any[]>([]);
  const [userSub, setUserSub] = useState<any>(null);
  const [subLoading, setSubLoading] = useState(false);
  const [subForm] = Form.useForm();

  const fetchUsers = async (p = page, s = search) => {
    setLoading(true);
    try {
      const { data } = await userApi.list(p, 10, s || undefined);
      setUsers(data.users || []);
      setTotal(data.total || 0);
    } catch { message.error('获取用户列表失败'); }
    setLoading(false);
  };

  useEffect(() => { fetchUsers(); }, []);

  // ===== 新建/编辑 =====
  const openCreate = () => { setEditingUser(null); form.resetFields(); setEditModal(true); };
  const openEdit = (user: any) => {
    setEditingUser(user);
    form.setFieldsValue({ username: user.username, email: user.email, phone: user.phone, status: user.status });
    setEditModal(true);
  };
  const handleSave = async () => {
    try {
      const values = await form.validateFields();
      setSaving(true);
      if (editingUser) {
        await userApi.update(editingUser.id, values);
        message.success('用户更新成功');
      } else {
        await userApi.create(values);
        message.success('用户创建成功');
      }
      setEditModal(false);
      fetchUsers();
    } catch (err: any) {
      if (err.response?.data?.detail) message.error(err.response.data.detail);
    } finally { setSaving(false); }
  };
  const handleDelete = async (id: string) => {
    try { await userApi.delete(id); message.success('用户已删除'); fetchUsers(); }
    catch (err: any) { message.error(err.response?.data?.detail || '删除失败'); }
  };
  const handleResetPassword = async (user: any) => {
    try { await userApi.resetPassword(user.id); message.success(`${user.username} 的密码已重置为 123456`); }
    catch (err: any) { message.error(err.response?.data?.detail || '重置失败'); }
  };

  // ===== 详情抽屉（含角色、权限信息）=====
  const openDetail = async (user: any) => {
    setSelectedUser(user);
    setDrawerOpen(true);
    setDetailLoading(true);
    try {
      const [rolesRes, permsRes] = await Promise.all([
        userRoleApi.getUserRoles(user.id),
        userRoleApi.getUserPermissions(user.id),
      ]);
      setDetailRoles(rolesRes.data || []);
      setDetailPerms(permsRes.data?.permissions || []);
    } catch { setDetailRoles([]); setDetailPerms([]); }
    setDetailLoading(false);
  };

  // ===== 角色管理 =====
  const openRoleModal = async (user: any) => {
    setSelectedUser(user);
    setRoleLoading(true);
    setRoleModal(true);
    try {
      const [rolesRes, userRolesRes] = await Promise.all([roleApi.list(), userRoleApi.getUserRoles(user.id)]);
      setAllRoles(rolesRes.data || []);
      setUserRoles((userRolesRes.data || []).map((r: any) => r.role_id));
    } catch { message.error('获取角色信息失败'); }
    setRoleLoading(false);
  };
  const handleRoleSave = async () => {
    if (!selectedUser) return;
    setRoleLoading(true);
    try {
      const { data: currentRoles } = await userRoleApi.getUserRoles(selectedUser.id);
      const currentIds = (currentRoles || []).map((r: any) => r.role_id);
      const toAdd = userRoles.filter((id: string) => !currentIds.includes(id));
      const toRemove = currentIds.filter((id: string) => !userRoles.includes(id));
      if (toAdd.length > 0) await userRoleApi.assignRoles(selectedUser.id, toAdd);
      for (const rid of toRemove) await userRoleApi.removeRole(selectedUser.id, rid);
      message.success('角色更新成功');
      setRoleModal(false);
    } catch (err: any) { message.error(err.response?.data?.detail || '角色更新失败'); }
    setRoleLoading(false);
  };

  // ===== 组织管理 =====
  const flattenOrgs = (nodes: any[], result: any[] = [], prefix = ''): any[] => {
    for (const n of nodes) {
      result.push({ ...n, displayName: prefix + n.name });
      if (n.children?.length) flattenOrgs(n.children, result, prefix + n.name + ' / ');
    }
    return result;
  };
  const openOrgModal = async (user: any) => {
    setSelectedUser(user);
    setOrgLoading(true);
    setOrgModal(true);
    setSelectedOrgId(undefined);
    try {
      const { data } = await orgApi.tree();
      setAllOrgs(flattenOrgs(data || []));
    } catch { message.error('获取组织信息失败'); }
    setOrgLoading(false);
  };
  const handleOrgAssign = async () => {
    if (!selectedUser || !selectedOrgId) { message.warning('请选择组织'); return; }
    setOrgLoading(true);
    try {
      await orgApi.assignUsers(selectedOrgId, [selectedUser.id]);
      message.success('已分配到组织');
      setOrgModal(false);
    } catch (err: any) { message.error(err.response?.data?.detail || '分配失败'); }
    setOrgLoading(false);
  };

  // ===== 订阅管理 =====
  const openSubModal = async (user: any) => {
    setSelectedUser(user);
    setSubLoading(true);
    setSubModal(true);
    subForm.resetFields();
    try {
      const [plansRes, subRes] = await Promise.all([subApi.listPlans(), subApi.getUserSub(user.id)]);
      setPlans(plansRes.data || []);
      const sub = subRes.data?.subscription !== undefined ? subRes.data : (subRes.data?.id ? subRes.data : null);
      setUserSub(sub?.subscription === null ? null : sub);
    } catch { setUserSub(null); }
    setSubLoading(false);
  };
  const handleSubCreate = async () => {
    if (!selectedUser) return;
    try {
      const values = await subForm.validateFields();
      setSubLoading(true);
      await subApi.createSub(selectedUser.id, { plan_id: values.plan_id, auto_renew: values.auto_renew ?? true });
      message.success('订阅创建成功');
      const subRes = await subApi.getUserSub(selectedUser.id);
      setUserSub(subRes.data?.subscription === null ? null : subRes.data);
    } catch (err: any) { message.error(err.response?.data?.detail || '创建订阅失败'); }
    setSubLoading(false);
  };
  const handleSubCancel = async () => {
    if (!selectedUser) return;
    setSubLoading(true);
    try {
      await subApi.cancelSub(selectedUser.id);
      message.success('订阅已取消自动续费');
      const subRes = await subApi.getUserSub(selectedUser.id);
      setUserSub(subRes.data?.subscription === null ? null : subRes.data);
    } catch (err: any) { message.error(err.response?.data?.detail || '取消失败'); }
    setSubLoading(false);
  };

  const columns = [
    { title: '用户名', dataIndex: 'username', key: 'username',
      render: (v: string, r: any) => <a onClick={() => openDetail(r)}>{v}</a> },
    { title: '邮箱', dataIndex: 'email', key: 'email', render: (v: string) => v || '-' },
    { title: '手机号', dataIndex: 'phone', key: 'phone', render: (v: string) => v || '-' },
    { title: '状态', dataIndex: 'status', key: 'status', render: (s: string) => {
      const map: Record<string, string> = { active: 'green', locked: 'red', pending_verification: 'orange' };
      return <Tag color={map[s] || 'default'}>{s === 'active' ? '正常' : s === 'locked' ? '锁定' : s === 'pending_verification' ? '待验证' : s}</Tag>;
    }},
    { title: '创建时间', dataIndex: 'created_at', key: 'created_at',
      render: (v: string) => v ? new Date(v).toLocaleString() : '-' },
    { title: '操作', key: 'actions', width: 380, render: (_: any, record: any) => (
      <Space size="small" wrap>
        <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(record)}>编辑</Button>
        <Button size="small" icon={<KeyOutlined />} onClick={() => openRoleModal(record)}>角色</Button>
        <Button size="small" icon={<ApartmentOutlined />} onClick={() => openOrgModal(record)}>组织</Button>
        <Button size="small" icon={<CrownOutlined />} onClick={() => openSubModal(record)}>订阅</Button>
        <Popconfirm title={`确定重置 ${record.username} 的密码为 123456？`} onConfirm={() => handleResetPassword(record)} okText="确定" cancelText="取消">
          <Button size="small" icon={<LockOutlined />}>重置密码</Button>
        </Popconfirm>
        <Popconfirm title="确定删除该用户？" onConfirm={() => handleDelete(record.id)} okText="确定" cancelText="取消">
          <Button size="small" danger icon={<DeleteOutlined />}>删除</Button>
        </Popconfirm>
      </Space>
    )},
  ];

  return (
    <>
      <Card title="用户管理" extra={
        <Space>
          <Input.Search placeholder="搜索用户名/邮箱/手机" allowClear style={{ width: 240 }}
            onSearch={(v) => { setSearch(v); setPage(1); fetchUsers(1, v); }} />
          <Button icon={<ReloadOutlined />} onClick={() => fetchUsers()}>刷新</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>新建用户</Button>
        </Space>
      }>
        <Table columns={columns} dataSource={users} rowKey="id" loading={loading}
          pagination={{ current: page, total, pageSize: 10, showTotal: (t) => `共 ${t} 条`,
            onChange: (p) => { setPage(p); fetchUsers(p); } }} />
      </Card>

      {/* 新建/编辑弹窗 */}
      <Modal title={editingUser ? '编辑用户' : '新建用户'} open={editModal}
        onCancel={() => setEditModal(false)} onOk={handleSave} confirmLoading={saving} okText="保存" cancelText="取消">
        <Form form={form} layout="vertical">
          <Form.Item name="username" label="用户名" rules={[{ required: true, message: '请输入用户名' }]}>
            <Input placeholder="请输入用户名" />
          </Form.Item>
          <Form.Item name="email" label="邮箱" rules={editingUser ? [] : [{ required: true, message: '邮箱或手机至少填一个' }]}>
            <Input placeholder="请输入邮箱" />
          </Form.Item>
          <Form.Item name="phone" label="手机号"><Input placeholder="请输入手机号" /></Form.Item>
          {!editingUser && (
            <Form.Item name="password" label="密码" rules={[{ required: true, message: '请输入密码' }, { min: 8, message: '密码至少8位' }]}>
              <Input.Password placeholder="请输入密码（至少8位）" />
            </Form.Item>
          )}
          {editingUser && (
            <Form.Item name="status" label="状态">
              <Select options={[
                { value: 'active', label: '正常' },
                { value: 'locked', label: '锁定' },
                { value: 'pending_verification', label: '待验证' },
              ]} />
            </Form.Item>
          )}
        </Form>
      </Modal>

      {/* 用户详情抽屉 */}
      <Drawer title="用户详情" open={drawerOpen} onClose={() => setDrawerOpen(false)} width={520}>
        {selectedUser && (
          <Tabs items={[
            { key: 'info', label: '基本信息', children: (
              <Descriptions column={1} bordered size="small">
                <Descriptions.Item label="ID">{selectedUser.id}</Descriptions.Item>
                <Descriptions.Item label="用户名">{selectedUser.username}</Descriptions.Item>
                <Descriptions.Item label="邮箱">{selectedUser.email || '-'}</Descriptions.Item>
                <Descriptions.Item label="手机号">{selectedUser.phone || '-'}</Descriptions.Item>
                <Descriptions.Item label="状态"><Tag color={selectedUser.status === 'active' ? 'green' : 'red'}>{selectedUser.status}</Tag></Descriptions.Item>
                <Descriptions.Item label="创建时间">{selectedUser.created_at ? new Date(selectedUser.created_at).toLocaleString() : '-'}</Descriptions.Item>
                <Descriptions.Item label="最后登录">{selectedUser.last_login_at ? new Date(selectedUser.last_login_at).toLocaleString() : '从未登录'}</Descriptions.Item>
              </Descriptions>
            )},
            { key: 'roles', label: `角色 (${detailRoles.length})`, children: detailLoading ? <div>加载中...</div> : (
              detailRoles.length > 0 ? (
                <Space wrap>{detailRoles.map((r: any) => <Tag key={r.role_id} color="blue">{r.role_name}</Tag>)}</Space>
              ) : <div style={{ color: '#999' }}>暂无角色</div>
            )},
            { key: 'perms', label: `权限 (${detailPerms.length})`, children: detailLoading ? <div>加载中...</div> : (
              detailPerms.length > 0 ? (
                <Space wrap size={[4, 8]}>{detailPerms.map((p: any) => <Tag key={p.id} color="purple">{p.name}</Tag>)}</Space>
              ) : <div style={{ color: '#999' }}>暂无权限</div>
            )},
          ]} />
        )}
      </Drawer>

      {/* 角色分配弹窗 */}
      <Modal title={`分配角色 - ${selectedUser?.username || ''}`} open={roleModal}
        onCancel={() => setRoleModal(false)} onOk={handleRoleSave} confirmLoading={roleLoading}
        okText="保存" cancelText="取消" width={500}>
        <div style={{ marginBottom: 8, color: '#666' }}>勾选要分配给该用户的角色：</div>
        <Select mode="multiple" style={{ width: '100%' }} placeholder="选择角色" value={userRoles}
          onChange={setUserRoles} loading={roleLoading}
          options={allRoles.map((r: any) => ({
            value: r.id, label: `${r.name}${r.description ? ` (${r.description})` : ''}`,
            disabled: r.is_system_role && r.name === 'super_admin',
          }))} />
      </Modal>

      {/* 组织分配弹窗 */}
      <Modal title={`分配组织 - ${selectedUser?.username || ''}`} open={orgModal}
        onCancel={() => setOrgModal(false)} onOk={handleOrgAssign} confirmLoading={orgLoading}
        okText="分配" cancelText="取消">
        <div style={{ marginBottom: 8, color: '#666' }}>选择要将用户分配到的组织：</div>
        <Select style={{ width: '100%' }} placeholder="选择组织" value={selectedOrgId}
          onChange={setSelectedOrgId} loading={orgLoading}
          options={allOrgs.map((o: any) => ({ value: o.id, label: o.displayName }))} />
      </Modal>

      {/* 订阅管理弹窗 */}
      <Modal title={`订阅管理 - ${selectedUser?.username || ''}`} open={subModal}
        onCancel={() => setSubModal(false)} footer={null} width={520}>
        {subLoading ? <div>加载中...</div> : (
          <>
            {userSub && userSub.id ? (
              <Card size="small" title="当前订阅" style={{ marginBottom: 16 }}>
                <Descriptions column={1} size="small">
                  <Descriptions.Item label="状态"><Tag color={userSub.status === 'active' ? 'green' : 'red'}>{userSub.status}</Tag></Descriptions.Item>
                  <Descriptions.Item label="开始时间">{new Date(userSub.start_date).toLocaleString()}</Descriptions.Item>
                  <Descriptions.Item label="到期时间">{new Date(userSub.end_date).toLocaleString()}</Descriptions.Item>
                  <Descriptions.Item label="自动续费">{userSub.auto_renew ? '是' : '否'}</Descriptions.Item>
                </Descriptions>
                {userSub.status === 'active' && userSub.auto_renew && (
                  <Popconfirm title="确定取消自动续费？" onConfirm={handleSubCancel} okText="确定" cancelText="取消">
                    <Button danger style={{ marginTop: 8 }}>取消自动续费</Button>
                  </Popconfirm>
                )}
              </Card>
            ) : (
              <Card size="small" title="当前无活跃订阅" style={{ marginBottom: 16 }}>
                <Form form={subForm} layout="vertical">
                  <Form.Item name="plan_id" label="选择订阅计划" rules={[{ required: true, message: '请选择计划' }]}>
                    <Select placeholder="选择订阅计划"
                      options={plans.map((p: any) => ({ value: p.id, label: `${p.name} - ¥${p.price} / ${p.duration_days}天` }))} />
                  </Form.Item>
                  <Form.Item name="auto_renew" label="自动续费" initialValue={true}>
                    <Select options={[{ value: true, label: '是' }, { value: false, label: '否' }]} />
                  </Form.Item>
                  <Button type="primary" onClick={handleSubCreate} loading={subLoading}>创建订阅</Button>
                </Form>
                {plans.length === 0 && <div style={{ color: '#999', marginTop: 8 }}>暂无可用订阅计划，请先在订阅管理中创建</div>}
              </Card>
            )}
          </>
        )}
      </Modal>
    </>
  );
}
