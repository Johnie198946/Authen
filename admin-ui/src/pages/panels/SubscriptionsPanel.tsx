import { useEffect, useState } from 'react';
import { Card, Table, Tag, Button, Space, Modal, Form, Input, InputNumber, Tooltip, message, Popconfirm } from 'antd';
import { PlusOutlined, ReloadOutlined, EditOutlined, DeleteOutlined, InfoCircleOutlined } from '@ant-design/icons';
import { subApi } from '../../api/services';

export default function SubscriptionsPanel() {
  const [plans, setPlans] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [editModal, setEditModal] = useState(false);
  const [editingPlan, setEditingPlan] = useState<any>(null);
  const [form] = Form.useForm();
  const [saving, setSaving] = useState(false);

  const fetchPlans = async () => {
    setLoading(true);
    try {
      const { data } = await subApi.listPlans();
      setPlans(Array.isArray(data) ? data : []);
    } catch { message.error('获取订阅计划失败'); }
    setLoading(false);
  };

  useEffect(() => { fetchPlans(); }, []);

  const openCreate = () => { setEditingPlan(null); form.resetFields(); setEditModal(true); };
  const openEdit = (plan: any) => {
    setEditingPlan(plan);
    form.setFieldsValue({
      name: plan.name, description: plan.description, duration_days: plan.duration_days, price: plan.price,
      request_quota: plan.request_quota ?? -1, token_quota: plan.token_quota ?? -1, quota_period_days: plan.quota_period_days ?? 30,
    });
    setEditModal(true);
  };

  const handleSave = async () => {
    try {
      const values = await form.validateFields();
      setSaving(true);
      if (editingPlan) {
        await subApi.updatePlan(editingPlan.id, values);
        message.success('订阅计划更新成功');
      } else {
        await subApi.createPlan(values);
        message.success('订阅计划创建成功');
      }
      setEditModal(false);
      form.resetFields();
      fetchPlans();
    } catch (err: any) {
      if (err.response?.data?.detail) message.error(err.response.data.detail);
    } finally { setSaving(false); }
  };

  const handleDelete = async (id: string) => {
    try { await subApi.deletePlan(id); message.success('订阅计划已停用'); fetchPlans(); }
    catch (err: any) { message.error(err.response?.data?.detail || '删除失败'); }
  };

  const renderQuota = (v: number) => v === -1 ? <Tag color="green">无限制</Tag> : v?.toLocaleString() ?? '-';

  const columns = [
    { title: '计划名称', dataIndex: 'name', key: 'name', render: (v: string) => <Tag color="blue">{v}</Tag> },
    { title: '描述', dataIndex: 'description', key: 'description', render: (v: string) => v || '-' },
    { title: '时长（天）', dataIndex: 'duration_days', key: 'duration_days' },
    { title: '价格', dataIndex: 'price', key: 'price', render: (v: number) => v != null ? `¥${v.toFixed(2)}` : '-' },
    { title: '请求配额', dataIndex: 'request_quota', key: 'request_quota', render: renderQuota },
    { title: 'Token 配额', dataIndex: 'token_quota', key: 'token_quota', render: renderQuota },
    { title: '配额周期（天）', dataIndex: 'quota_period_days', key: 'quota_period_days', render: (v: number) => v ?? '-' },
    { title: '状态', dataIndex: 'is_active', key: 'is_active',
      render: (v: boolean) => <Tag color={v ? 'green' : 'default'}>{v ? '启用' : '停用'}</Tag> },
    { title: '操作', key: 'actions', width: 160, render: (_: any, record: any) => (
      <Space size="small">
        <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(record)}>编辑</Button>
        <Popconfirm title="确定停用该计划？有活跃订阅的计划无法停用。" onConfirm={() => handleDelete(record.id)} okText="确定" cancelText="取消">
          <Button size="small" danger icon={<DeleteOutlined />}>停用</Button>
        </Popconfirm>
      </Space>
    )},
  ];

  return (
    <>
      <Card title="订阅管理" extra={
        <Space>
          <Tag color="blue">{plans.length} 个计划</Tag>
          <Button icon={<ReloadOutlined />} onClick={fetchPlans}>刷新</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>新建计划</Button>
        </Space>
      }>
        <Table columns={columns} dataSource={plans} rowKey="id" loading={loading} pagination={{ pageSize: 10 }} />
        {plans.length === 0 && !loading && (
          <div style={{ textAlign: 'center', padding: 24, color: '#999' }}>暂无订阅计划，点击"新建计划"创建第一个</div>
        )}
      </Card>

      <Modal title={editingPlan ? '编辑订阅计划' : '新建订阅计划'} open={editModal} onCancel={() => setEditModal(false)}
        onOk={handleSave} confirmLoading={saving} okText="保存" cancelText="取消">
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="计划名称" rules={[{ required: true, message: '请输入计划名称' }]}>
            <Input placeholder="如：基础版、专业版、企业版" />
          </Form.Item>
          <Form.Item name="description" label="描述">
            <Input.TextArea placeholder="计划描述" rows={2} />
          </Form.Item>
          <Form.Item name="duration_days" label="时长（天）" rules={[{ required: true, message: '请输入时长' }]}>
            <InputNumber min={1} max={3650} style={{ width: '100%' }} placeholder="如：30, 90, 365" />
          </Form.Item>
          <Form.Item name="price" label="价格（元）" rules={[{ required: true, message: '请输入价格' }]}>
            <InputNumber min={0} precision={2} style={{ width: '100%' }} placeholder="如：99.00" />
          </Form.Item>
          <Form.Item name="request_quota" label={<Space>请求配额<Tooltip title="每个计费周期内允许的最大请求次数，-1 表示无限制"><InfoCircleOutlined /></Tooltip></Space>}
            rules={[{ type: 'number', min: -1, message: '请求配额必须 >= -1' }]} initialValue={-1}>
            <InputNumber min={-1} style={{ width: '100%' }} placeholder="-1 表示无限制" />
          </Form.Item>
          {form.getFieldValue('request_quota') === -1 && <div style={{ marginTop: -16, marginBottom: 8, color: '#52c41a', fontSize: 12 }}>当前设置：无限制</div>}
          <Form.Item name="token_quota" label={<Space>Token 配额<Tooltip title="每个计费周期内允许的最大 Token 消耗量，-1 表示无限制"><InfoCircleOutlined /></Tooltip></Space>}
            rules={[{ type: 'number', min: -1, message: 'Token 配额必须 >= -1' }]} initialValue={-1}>
            <InputNumber min={-1} style={{ width: '100%' }} placeholder="-1 表示无限制" />
          </Form.Item>
          {form.getFieldValue('token_quota') === -1 && <div style={{ marginTop: -16, marginBottom: 8, color: '#52c41a', fontSize: 12 }}>当前设置：无限制</div>}
          <Form.Item name="quota_period_days" label={<Space>配额周期（天）<Tooltip title="配额重置的计费周期天数"><InfoCircleOutlined /></Tooltip></Space>}
            rules={[{ type: 'number', min: 1, message: '配额周期必须 >= 1 天' }]} initialValue={30}>
            <InputNumber min={1} max={365} style={{ width: '100%' }} placeholder="默认 30 天" />
          </Form.Item>
        </Form>
      </Modal>
    </>
  );
}
