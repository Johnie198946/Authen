import { useEffect, useState } from 'react';
import { Card, Table, Tag, Button, Space, Modal, Form, Input, Select, message, Popconfirm } from 'antd';
import { PlusOutlined, ReloadOutlined, EditOutlined, DeleteOutlined } from '@ant-design/icons';
import { permissionApi } from '../../api/services';

export default function PermissionsPanel() {
  const [permissions, setPermissions] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [editModal, setEditModal] = useState(false);
  const [editingPerm, setEditingPerm] = useState<any>(null);
  const [form] = Form.useForm();
  const [saving, setSaving] = useState(false);

  const fetchPermissions = async () => {
    setLoading(true);
    try {
      const { data } = await permissionApi.list();
      setPermissions(Array.isArray(data) ? data : []);
    } catch { message.error('获取权限列表失败'); }
    setLoading(false);
  };

  useEffect(() => { fetchPermissions(); }, []);

  const openCreate = () => { setEditingPerm(null); form.resetFields(); setEditModal(true); };
  const openEdit = (perm: any) => {
    setEditingPerm(perm);
    form.setFieldsValue({ resource: perm.resource, action: perm.action, description: perm.description });
    setEditModal(true);
  };

  const handleSave = async () => {
    try {
      const values = await form.validateFields();
      setSaving(true);
      const name = `${values.resource}:${values.action}`;
      if (editingPerm) {
        await permissionApi.update(editingPerm.id, { ...values, name });
        message.success('权限更新成功');
      } else {
        await permissionApi.create({ ...values, name });
        message.success('权限创建成功');
      }
      setEditModal(false);
      form.resetFields();
      fetchPermissions();
    } catch (err: any) {
      if (err.response?.data?.detail) message.error(err.response.data.detail);
    } finally { setSaving(false); }
  };

  const handleDelete = async (id: string) => {
    try { await permissionApi.delete(id); message.success('权限已删除'); fetchPermissions(); }
    catch (err: any) { message.error(err.response?.data?.detail || '删除失败'); }
  };

  const resourceStats = permissions.reduce((acc: Record<string, number>, p: any) => {
    acc[p.resource] = (acc[p.resource] || 0) + 1;
    return acc;
  }, {});

  const columns = [
    { title: '权限名称', dataIndex: 'name', key: 'name', render: (v: string) => <Tag color="purple">{v}</Tag> },
    { title: '资源', dataIndex: 'resource', key: 'resource', render: (v: string) => <Tag>{v}</Tag>,
      filters: Object.keys(resourceStats).map(r => ({ text: `${r} (${resourceStats[r]})`, value: r })),
      onFilter: (value: any, record: any) => record.resource === value },
    { title: '操作类型', dataIndex: 'action', key: 'action',
      render: (v: string) => {
        const colors: Record<string, string> = { create: 'green', read: 'blue', update: 'orange', delete: 'red' };
        return <Tag color={colors[v] || 'default'}>{v}</Tag>;
      }},
    { title: '描述', dataIndex: 'description', key: 'description', render: (v: string) => v || '-' },
    { title: '操作', key: 'actions', width: 160, render: (_: any, record: any) => (
      <Space size="small">
        <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(record)}>编辑</Button>
        <Popconfirm title="确定删除该权限？被角色使用的权限无法删除。" onConfirm={() => handleDelete(record.id)} okText="确定" cancelText="取消">
          <Button size="small" danger icon={<DeleteOutlined />}>删除</Button>
        </Popconfirm>
      </Space>
    )},
  ];

  return (
    <>
      <Card title="权限管理" extra={
        <Space>
          <Tag color="blue">{permissions.length} 个权限</Tag>
          <Button icon={<ReloadOutlined />} onClick={fetchPermissions}>刷新</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>新建权限</Button>
        </Space>
      }>
        <Table columns={columns} dataSource={permissions} rowKey="id" loading={loading}
          pagination={{ pageSize: 15, showTotal: (t) => `共 ${t} 条` }} />
      </Card>

      <Modal title={editingPerm ? '编辑权限' : '新建权限'} open={editModal} onCancel={() => setEditModal(false)}
        onOk={handleSave} confirmLoading={saving} okText="保存" cancelText="取消">
        <Form form={form} layout="vertical">
          <Form.Item name="resource" label="资源" rules={[{ required: true, message: '请输入资源名' }]}>
            <Input placeholder="如：user, role, organization" />
          </Form.Item>
          <Form.Item name="action" label="操作" rules={[{ required: true, message: '请选择操作类型' }]}>
            <Select placeholder="选择操作类型" options={[
              { value: 'create', label: '创建 (create)' },
              { value: 'read', label: '查看 (read)' },
              { value: 'update', label: '更新 (update)' },
              { value: 'delete', label: '删除 (delete)' },
            ]} />
          </Form.Item>
          <Form.Item name="description" label="描述"><Input placeholder="权限描述" /></Form.Item>
        </Form>
      </Modal>
    </>
  );
}
