import { useEffect, useState } from 'react';
import { Card, Table, Tag, Button, Space, Modal, Form, Input, message, Popconfirm, Select, Drawer, Descriptions } from 'antd';
import { PlusOutlined, ReloadOutlined, EditOutlined, DeleteOutlined, KeyOutlined, EyeOutlined } from '@ant-design/icons';
import { roleApi, permissionApi } from '../../api/services';

export default function RolesPanel() {
  const [roles, setRoles] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [editModal, setEditModal] = useState(false);
  const [editingRole, setEditingRole] = useState<any>(null);
  const [form] = Form.useForm();
  const [saving, setSaving] = useState(false);
  // 权限分配
  const [permModal, setPermModal] = useState(false);
  const [allPerms, setAllPerms] = useState<any[]>([]);
  const [rolePerms, setRolePerms] = useState<string[]>([]);
  const [permLoading, setPermLoading] = useState(false);
  const [selectedRole, setSelectedRole] = useState<any>(null);
  // 角色详情抽屉
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [drawerRole, setDrawerRole] = useState<any>(null);
  const [drawerPerms, setDrawerPerms] = useState<any[]>([]);
  const [drawerLoading, setDrawerLoading] = useState(false);

  const fetchRoles = async () => {
    setLoading(true);
    try {
      const { data } = await roleApi.list();
      setRoles(Array.isArray(data) ? data : []);
    } catch { message.error('获取角色列表失败'); }
    setLoading(false);
  };

  useEffect(() => { fetchRoles(); }, []);

  const openCreate = () => { setEditingRole(null); form.resetFields(); setEditModal(true); };
  const openEdit = (role: any) => {
    setEditingRole(role);
    form.setFieldsValue({ name: role.name, description: role.description });
    setEditModal(true);
  };
  const handleSave = async () => {
    try {
      const values = await form.validateFields();
      setSaving(true);
      if (editingRole) {
        await roleApi.update(editingRole.id, values);
        message.success('角色更新成功');
      } else {
        await roleApi.create(values);
        message.success('角色创建成功');
      }
      setEditModal(false);
      fetchRoles();
    } catch (err: any) {
      if (err.response?.data?.detail) message.error(err.response.data.detail);
    } finally { setSaving(false); }
  };
  const handleDelete = async (id: string) => {
    try { await roleApi.delete(id); message.success('角色已删除'); fetchRoles(); }
    catch (err: any) { message.error(err.response?.data?.detail || '删除失败'); }
  };

  // ===== 查看角色详情 =====
  const openDrawer = async (role: any) => {
    setDrawerRole(role);
    setDrawerOpen(true);
    setDrawerLoading(true);
    try {
      const { data } = await roleApi.getPermissions(role.id);
      setDrawerPerms(Array.isArray(data) ? data : []);
    } catch { setDrawerPerms([]); }
    setDrawerLoading(false);
  };

  // ===== 权限分配（加载已有权限）=====
  const openPermModal = async (role: any) => {
    setSelectedRole(role);
    setPermLoading(true);
    setPermModal(true);
    try {
      const [permsRes, rolePermsRes] = await Promise.all([
        permissionApi.list(),
        roleApi.getPermissions(role.id),
      ]);
      setAllPerms(Array.isArray(permsRes.data) ? permsRes.data : []);
      const existingIds = (Array.isArray(rolePermsRes.data) ? rolePermsRes.data : []).map((p: any) => p.id);
      setRolePerms(existingIds);
    } catch { message.error('获取权限信息失败'); }
    setPermLoading(false);
  };
  const handlePermSave = async () => {
    if (!selectedRole) return;
    setPermLoading(true);
    try {
      // 获取当前角色已有权限
      const { data: currentPerms } = await roleApi.getPermissions(selectedRole.id);
      const currentIds = (Array.isArray(currentPerms) ? currentPerms : []).map((p: any) => p.id);
      // 需要添加的
      const toAdd = rolePerms.filter(id => !currentIds.includes(id));
      // 需要移除的
      const toRemove = currentIds.filter((id: string) => !rolePerms.includes(id));
      if (toAdd.length > 0) await roleApi.assignPermissions(selectedRole.id, toAdd);
      for (const pid of toRemove) await roleApi.removePermission(selectedRole.id, pid);
      message.success('权限更新成功');
      setPermModal(false);
    } catch (err: any) { message.error(err.response?.data?.detail || '权限更新失败'); }
    setPermLoading(false);
  };

  // 按资源分组权限
  const permGroups = allPerms.reduce((acc: Record<string, any[]>, p: any) => {
    const key = p.resource || '其他';
    if (!acc[key]) acc[key] = [];
    acc[key].push(p);
    return acc;
  }, {});

  const columns = [
    { title: '角色名', dataIndex: 'name', key: 'name',
      render: (v: string, r: any) => <a onClick={() => openDrawer(r)}><Tag color="blue">{v}</Tag></a> },
    { title: '描述', dataIndex: 'description', key: 'description', render: (v: string) => v || '-' },
    { title: '类型', dataIndex: 'is_system_role', key: 'is_system_role',
      render: (v: boolean) => v ? <Tag color="volcano">系统角色</Tag> : <Tag color="green">自定义</Tag> },
    { title: '操作', key: 'actions', width: 320, render: (_: any, record: any) => (
      <Space size="small">
        <Button size="small" icon={<EyeOutlined />} onClick={() => openDrawer(record)}>查看权限</Button>
        <Button size="small" icon={<KeyOutlined />} onClick={() => openPermModal(record)}>分配权限</Button>
        <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(record)} disabled={record.is_system_role}>编辑</Button>
        <Popconfirm title="确定删除该角色？" onConfirm={() => handleDelete(record.id)} okText="确定" cancelText="取消">
          <Button size="small" danger icon={<DeleteOutlined />} disabled={record.is_system_role}>删除</Button>
        </Popconfirm>
      </Space>
    )},
  ];

  // 按资源分组抽屉中的权限
  const drawerPermGroups = drawerPerms.reduce((acc: Record<string, any[]>, p: any) => {
    const key = p.resource || '其他';
    if (!acc[key]) acc[key] = [];
    acc[key].push(p);
    return acc;
  }, {});

  return (
    <>
      <Card title="角色管理" extra={
        <Space>
          <Button icon={<ReloadOutlined />} onClick={fetchRoles}>刷新</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>新建角色</Button>
        </Space>
      }>
        <Table columns={columns} dataSource={roles} rowKey="id" loading={loading} pagination={{ pageSize: 10 }} />
      </Card>

      <Modal title={editingRole ? '编辑角色' : '新建角色'} open={editModal}
        onCancel={() => setEditModal(false)} onOk={handleSave} confirmLoading={saving} okText="保存" cancelText="取消">
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="角色名" rules={[{ required: true, message: '请输入角色名' }]}>
            <Input placeholder="如：editor, viewer" />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea placeholder="角色描述" rows={3} />
          </Form.Item>
        </Form>
      </Modal>

      {/* 角色详情抽屉 */}
      <Drawer title={`角色详情 - ${drawerRole?.name || ''}`} open={drawerOpen} onClose={() => setDrawerOpen(false)} width={480}>
        {drawerRole && (
          <>
            <Descriptions column={1} bordered size="small" style={{ marginBottom: 16 }}>
              <Descriptions.Item label="角色名">{drawerRole.name}</Descriptions.Item>
              <Descriptions.Item label="描述">{drawerRole.description || '-'}</Descriptions.Item>
              <Descriptions.Item label="类型">{drawerRole.is_system_role ? '系统角色' : '自定义角色'}</Descriptions.Item>
            </Descriptions>
            <Card size="small" title={`权限列表 (${drawerPerms.length})`} loading={drawerLoading}>
              {drawerPerms.length > 0 ? (
                Object.entries(drawerPermGroups).map(([resource, perms]) => (
                  <div key={resource} style={{ marginBottom: 12 }}>
                    <div style={{ fontWeight: 500, marginBottom: 4, color: '#333' }}>{resource}</div>
                    <Space wrap size={[4, 4]}>
                      {(perms as any[]).map((p: any) => {
                        const colors: Record<string, string> = { create: 'green', read: 'blue', update: 'orange', delete: 'red' };
                        return <Tag key={p.id} color={colors[p.action] || 'default'}>{p.action}</Tag>;
                      })}
                    </Space>
                  </div>
                ))
              ) : <div style={{ color: '#999' }}>暂无权限</div>}
            </Card>
          </>
        )}
      </Drawer>

      {/* 权限分配弹窗 */}
      <Modal title={`分配权限 - ${selectedRole?.name || ''}`} open={permModal}
        onCancel={() => setPermModal(false)} onOk={handlePermSave} confirmLoading={permLoading}
        okText="保存" cancelText="取消" width={600}>
        <div style={{ marginBottom: 12, color: '#666' }}>选择要分配给该角色的权限（支持增量更新，取消勾选会移除权限）：</div>
        <Select mode="multiple" style={{ width: '100%' }} placeholder="选择权限" value={rolePerms}
          onChange={setRolePerms} loading={permLoading} optionFilterProp="label" maxTagCount={10}
          options={allPerms.map((p: any) => ({
            value: p.id,
            label: `${p.name} (${p.description || p.resource + ':' + p.action})`,
          }))} />
        {Object.keys(permGroups).length > 0 && (
          <div style={{ marginTop: 12 }}>
            <div style={{ color: '#999', fontSize: 12, marginBottom: 4 }}>快速选择（按资源分组）：</div>
            <Space wrap>
              {Object.entries(permGroups).map(([resource, perms]) => (
                <Button key={resource} size="small" type="dashed"
                  onClick={() => setRolePerms(prev => {
                    const ids = (perms as any[]).map((p: any) => p.id);
                    const merged = new Set([...prev, ...ids]);
                    return Array.from(merged);
                  })}>
                  全选 {resource}
                </Button>
              ))}
              <Button size="small" type="dashed" danger onClick={() => setRolePerms([])}>清空全部</Button>
            </Space>
          </div>
        )}
      </Modal>
    </>
  );
}
