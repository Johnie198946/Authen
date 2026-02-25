import { useEffect, useState, useRef } from 'react';
import {
  Card, Table, Tabs, Tag, Button, Space, Modal, Form, Input, message,
  Popconfirm, Alert, Divider, Row, Col, Typography,
} from 'antd';
import {
  PlusOutlined, ReloadOutlined, EditOutlined, DeleteOutlined,
  EyeOutlined, CodeOutlined,
} from '@ant-design/icons';
import { templateApi } from '../../api/services';

const { TextArea } = Input;
const { Text } = Typography;

const SYSTEM_TEMPLATES = [
  'email_verification',
  'password_reset',
  'subscription_reminder',
  'email_verification_code',
];

interface TemplateItem {
  id: string;
  name: string;
  type: string;
  subject?: string;
  content: string;
  variables?: Record<string, string>;
  created_at: string;
  updated_at: string;
}

export default function MessageTemplatePanel() {
  const [templates, setTemplates] = useState<TemplateItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [activeTab, setActiveTab] = useState('email');
  const [editModal, setEditModal] = useState(false);
  const [previewModal, setPreviewModal] = useState(false);
  const [editingTemplate, setEditingTemplate] = useState<TemplateItem | null>(null);
  const [form] = Form.useForm();
  const [saving, setSaving] = useState(false);
  const [previewVars, setPreviewVars] = useState<Record<string, string>>({});
  const contentRef = useRef<any>(null);

  const fetchTemplates = async () => {
    setLoading(true);
    try {
      const { data } = await templateApi.list();
      const list = data.templates || [];
      setTemplates(Array.isArray(list) ? list : []);
    } catch {
      message.error('获取模板列表失败');
    }
    setLoading(false);
  };

  useEffect(() => { fetchTemplates(); }, []);

  const filteredTemplates = templates.filter(t => t.type === activeTab);

  const isSystemTemplate = (name: string) => SYSTEM_TEMPLATES.includes(name);

  const openCreate = () => {
    setEditingTemplate(null);
    form.resetFields();
    form.setFieldsValue({ type: activeTab });
    setEditModal(true);
  };

  const openEdit = (tpl: TemplateItem) => {
    setEditingTemplate(tpl);
    form.setFieldsValue({
      name: tpl.name,
      type: tpl.type,
      subject: tpl.subject || '',
      content: tpl.content,
      variables: tpl.variables ? JSON.stringify(tpl.variables, null, 2) : '{}',
    });
    setEditModal(true);
  };

  const openPreview = (tpl: TemplateItem) => {
    setEditingTemplate(tpl);
    const vars: Record<string, string> = {};
    if (tpl.variables) {
      Object.keys(tpl.variables).forEach(k => { vars[k] = ''; });
    }
    setPreviewVars(vars);
    setPreviewModal(true);
  };

  const handleSave = async () => {
    try {
      const values = await form.validateFields();
      let variables: Record<string, string> | undefined;
      if (values.variables) {
        try {
          variables = JSON.parse(values.variables);
        } catch {
          message.error('变量说明必须是有效的 JSON 格式');
          return;
        }
      }
      setSaving(true);
      const payload: any = {
        content: values.content,
        variables,
      };
      if (editingTemplate) {
        if (values.subject !== undefined) payload.subject = values.subject;
        await templateApi.update(editingTemplate.id, payload);
        message.success('模板更新成功');
      } else {
        payload.name = values.name;
        payload.type = values.type || activeTab;
        if (values.subject) payload.subject = values.subject;
        await templateApi.create(payload);
        message.success('模板创建成功');
      }
      setEditModal(false);
      form.resetFields();
      fetchTemplates();
    } catch (err: any) {
      if (err.response?.data?.detail) message.error(err.response.data.detail);
    } finally {
      setSaving(false);
    }
  };

  const handleDelete = async (id: string) => {
    try {
      await templateApi.delete(id);
      message.success('模板已删除');
      fetchTemplates();
    } catch (err: any) {
      message.error(err.response?.data?.detail || '删除失败');
    }
  };

  const insertVariable = (varName: string) => {
    const textarea = contentRef.current?.resizableTextArea?.textArea;
    if (!textarea) return;
    const start = textarea.selectionStart;
    const end = textarea.selectionEnd;
    const currentContent = form.getFieldValue('content') || '';
    const insertion = `{{ ${varName} }}`;
    const newContent = currentContent.substring(0, start) + insertion + currentContent.substring(end);
    form.setFieldsValue({ content: newContent });
    // Restore cursor position after insertion
    setTimeout(() => {
      textarea.focus();
      const newPos = start + insertion.length;
      textarea.setSelectionRange(newPos, newPos);
    }, 0);
  };

  const renderPreview = () => {
    if (!editingTemplate) return '';
    let result = editingTemplate.content;
    Object.entries(previewVars).forEach(([key, value]) => {
      const regex = new RegExp(`\\{\\{\\s*${key}\\s*\\}\\}`, 'g');
      result = result.replace(regex, value || `[${key}]`);
    });
    return result;
  };

  const currentEditType = editingTemplate?.type || form.getFieldValue('type') || activeTab;

  const getVariablesFromForm = (): Record<string, string> => {
    try {
      const raw = form.getFieldValue('variables');
      return raw ? JSON.parse(raw) : {};
    } catch {
      return editingTemplate?.variables || {};
    }
  };

  const columns = [
    {
      title: '模板名称', dataIndex: 'name', key: 'name',
      render: (v: string) => (
        <Space>
          <Tag color="blue">{v}</Tag>
          {isSystemTemplate(v) && <Tag color="orange">内置</Tag>}
        </Space>
      ),
    },
    ...(activeTab === 'email' ? [{
      title: '邮件主题', dataIndex: 'subject', key: 'subject',
      render: (v: string) => v || '-',
    }] : []),
    {
      title: '变量', dataIndex: 'variables', key: 'variables',
      render: (v: Record<string, string>) => {
        if (!v || Object.keys(v).length === 0) return '-';
        return (
          <Space wrap>
            {Object.keys(v).map(k => <Tag key={k} color="geekblue">{`{{ ${k} }}`}</Tag>)}
          </Space>
        );
      },
    },
    {
      title: '更新时间', dataIndex: 'updated_at', key: 'updated_at',
      render: (v: string) => v ? new Date(v).toLocaleString() : '-',
    },
    {
      title: '操作', key: 'actions', width: 220,
      render: (_: any, record: TemplateItem) => (
        <Space size="small">
          <Button size="small" icon={<EyeOutlined />} onClick={() => openPreview(record)}>预览</Button>
          <Button size="small" icon={<EditOutlined />} onClick={() => openEdit(record)}>编辑</Button>
          {!isSystemTemplate(record.name) && (
            <Popconfirm title="确定删除该模板？" onConfirm={() => handleDelete(record.id)} okText="确定" cancelText="取消">
              <Button size="small" danger icon={<DeleteOutlined />}>删除</Button>
            </Popconfirm>
          )}
        </Space>
      ),
    },
  ];

  return (
    <>
      <Card
        title="消息模板管理"
        extra={
          <Space>
            <Tag color="blue">{filteredTemplates.length} 个模板</Tag>
            <Button icon={<ReloadOutlined />} onClick={fetchTemplates}>刷新</Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={openCreate}>新建模板</Button>
          </Space>
        }
      >
        <Tabs
          activeKey={activeTab}
          onChange={setActiveTab}
          items={[
            { key: 'email', label: '邮件模板' },
            { key: 'sms', label: '短信模板' },
          ]}
        />
        <Table
          columns={columns}
          dataSource={filteredTemplates}
          rowKey="id"
          loading={loading}
          pagination={{ pageSize: 10 }}
        />
        {filteredTemplates.length === 0 && !loading && (
          <div style={{ textAlign: 'center', padding: 24, color: '#999' }}>
            暂无{activeTab === 'email' ? '邮件' : '短信'}模板，点击"新建模板"创建
          </div>
        )}
      </Card>

      {/* Edit / Create Modal */}
      <Modal
        title={editingTemplate ? `编辑模板: ${editingTemplate.name}` : '新建模板'}
        open={editModal}
        onCancel={() => setEditModal(false)}
        onOk={handleSave}
        confirmLoading={saving}
        okText="保存"
        cancelText="取消"
        width={720}
      >
        {currentEditType === 'sms' && (
          <Alert
            type="warning"
            showIcon
            message="短信模板审核提示"
            description="如果使用阿里云/腾讯云短信服务，编辑此模板后还需在对应云厂商控制台申请并审核短信模板（template_code/template_id），审核通过后方可正常发送。"
            style={{ marginBottom: 16 }}
          />
        )}
        <Form form={form} layout="vertical">
          {!editingTemplate && (
            <>
              <Form.Item name="name" label="模板名称" rules={[{ required: true, message: '请输入模板名称' }]}>
                <Input placeholder="如：welcome_email、order_notification" />
              </Form.Item>
              <Form.Item name="type" label="模板类型" hidden>
                <Input />
              </Form.Item>
            </>
          )}
          {currentEditType === 'email' && (
            <Form.Item name="subject" label="邮件主题">
              <Input placeholder="如：验证您的邮箱 - {{ app_name }}" />
            </Form.Item>
          )}
          <Form.Item name="content" label="模板内容" rules={[{ required: true, message: '请输入模板内容' }]}>
            <TextArea ref={contentRef} rows={8} placeholder="支持 Jinja2 语法，如 {{ variable_name }}" />
          </Form.Item>

          {/* Variable insertion helper */}
          <div style={{ marginBottom: 16 }}>
            <Text strong><CodeOutlined /> 可用变量（点击插入）：</Text>
            <div style={{ marginTop: 8 }}>
              {Object.entries(getVariablesFromForm()).length > 0 ? (
                <Space wrap>
                  {Object.entries(getVariablesFromForm()).map(([varName, desc]) => (
                    <Tag
                      key={varName}
                      color="processing"
                      style={{ cursor: 'pointer' }}
                      onClick={() => insertVariable(varName)}
                      title={desc}
                    >
                      {`{{ ${varName} }}`}
                    </Tag>
                  ))}
                </Space>
              ) : (
                <Text type="secondary">请在下方变量说明中定义变量</Text>
              )}
            </div>
          </div>

          <Form.Item
            name="variables"
            label="变量说明（JSON 格式）"
            rules={[{
              validator: (_, value) => {
                if (!value) return Promise.resolve();
                try { JSON.parse(value); return Promise.resolve(); }
                catch { return Promise.reject('请输入有效的 JSON 格式'); }
              },
            }]}
          >
            <TextArea rows={4} placeholder='{"verification_code": "验证码", "app_name": "应用名称"}' />
          </Form.Item>
        </Form>
      </Modal>

      {/* Preview Modal */}
      <Modal
        title={`模板预览: ${editingTemplate?.name || ''}`}
        open={previewModal}
        onCancel={() => setPreviewModal(false)}
        footer={<Button onClick={() => setPreviewModal(false)}>关闭</Button>}
        width={720}
      >
        {editingTemplate && (
          <>
            {editingTemplate.variables && Object.keys(editingTemplate.variables).length > 0 && (
              <>
                <Divider titlePlacement="left">示例变量值</Divider>
                <Row gutter={[16, 8]}>
                  {Object.entries(editingTemplate.variables).map(([varName, desc]) => (
                    <Col span={12} key={varName}>
                      <Form.Item label={`${varName}（${desc}）`} style={{ marginBottom: 8 }}>
                        <Input
                          placeholder={`输入 ${varName} 的示例值`}
                          value={previewVars[varName] || ''}
                          onChange={e => setPreviewVars(prev => ({ ...prev, [varName]: e.target.value }))}
                        />
                      </Form.Item>
                    </Col>
                  ))}
                </Row>
              </>
            )}
            <Divider titlePlacement="left">渲染预览</Divider>
            {editingTemplate.type === 'email' && editingTemplate.subject && (
              <div style={{ marginBottom: 8 }}>
                <Text strong>主题：</Text>
                <Text>{(() => {
                  let subj = editingTemplate.subject || '';
                  Object.entries(previewVars).forEach(([k, v]) => {
                    subj = subj.replace(new RegExp(`\\{\\{\\s*${k}\\s*\\}\\}`, 'g'), v || `[${k}]`);
                  });
                  return subj;
                })()}</Text>
              </div>
            )}
            <Card
              size="small"
              style={{ background: '#fafafa', minHeight: 120 }}
            >
              {editingTemplate.type === 'email' ? (
                <div dangerouslySetInnerHTML={{ __html: renderPreview() }} />
              ) : (
                <pre style={{ whiteSpace: 'pre-wrap', margin: 0 }}>{renderPreview()}</pre>
              )}
            </Card>
          </>
        )}
      </Modal>
    </>
  );
}
