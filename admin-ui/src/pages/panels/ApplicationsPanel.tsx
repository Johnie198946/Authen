import { useEffect, useState } from 'react';
import { Card, Table, Tag, Button, Space, message, Popconfirm, Typography } from 'antd';
import { PlusOutlined, ReloadOutlined, DeleteOutlined, CopyOutlined, SettingOutlined } from '@ant-design/icons';
import { applicationApi } from '../../api/services';
import { useAuth } from '../../store/AuthContext';
import ApplicationDetail from './ApplicationDetail';
import AppConfigWizard from './wizard/AppConfigWizard';
import SecretDisplayModal from './wizard/SecretDisplayModal';

const { Paragraph } = Typography;

export default function ApplicationsPanel() {
  const { state } = useAuth();
  const userId = state.user?.id || '';

  const [apps, setApps] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);

  // 向导
  const [wizardOpen, setWizardOpen] = useState(false);

  // 显示 secret
  const [secretModal, setSecretModal] = useState(false);
  const [secretInfo, setSecretInfo] = useState<{ appId: string; appSecret: string }>({ appId: '', appSecret: '' });

  // 详情页
  const [detailAppId, setDetailAppId] = useState<string | null>(null);

  const fetchApps = async () => {
    setLoading(true);
    try {
      const { data } = await applicationApi.list(userId);
      setApps(data.applications || data || []);
    } catch {
      message.error('获取应用列表失败');
    }
    setLoading(false);
  };

  useEffect(() => {
    if (userId) fetchApps();
  }, [userId]);

  // ===== 状态切换 =====
  const handleToggleStatus = async (record: any) => {
    const newStatus = record.status === 'active' ? 'disabled' : 'active';
    try {
      await applicationApi.updateStatus(record.app_id, { status: newStatus }, userId);
      message.success(`应用已${newStatus === 'active' ? '启用' : '禁用'}`);
      fetchApps();
    } catch (err: any) {
      message.error(err.response?.data?.detail || '操作失败');
    }
  };

  // ===== 删除应用 =====
  const handleDelete = async (appId: string) => {
    try {
      await applicationApi.delete(appId, userId);
      message.success('应用已删除');
      fetchApps();
    } catch (err: any) {
      message.error(err.response?.data?.detail || '删除失败');
    }
  };

  // ===== 重置密钥 =====
  const handleResetSecret = async (appId: string) => {
    try {
      const { data } = await applicationApi.resetSecret(appId, userId);
      setSecretInfo({ appId, appSecret: data.app_secret });
      setSecretModal(true);
      message.success('密钥已重置');
    } catch (err: any) {
      message.error(err.response?.data?.detail || '重置失败');
    }
  };

  const columns = [
    {
      title: '应用名称',
      dataIndex: 'name',
      key: 'name',
      render: (v: string, record: any) => (
        <a onClick={() => setDetailAppId(record.app_id)}>{v}</a>
      ),
    },
    {
      title: 'App ID',
      dataIndex: 'app_id',
      key: 'app_id',
      render: (v: string) => (
        <Paragraph copyable={{ icon: <CopyOutlined /> }} style={{ marginBottom: 0 }}>
          {v}
        </Paragraph>
      ),
    },
    {
      title: '状态',
      dataIndex: 'status',
      key: 'status',
      render: (s: string) => (
        <Tag color={s === 'active' ? 'green' : 'red'}>
          {s === 'active' ? '启用' : '禁用'}
        </Tag>
      ),
    },
    {
      title: '限流 (次/分)',
      dataIndex: 'rate_limit',
      key: 'rate_limit',
      render: (v: number) => v ?? 60,
    },
    {
      title: '创建时间',
      dataIndex: 'created_at',
      key: 'created_at',
      render: (v: string) => (v ? new Date(v).toLocaleString() : '-'),
    },
    {
      title: '操作',
      key: 'actions',
      width: 300,
      render: (_: any, record: any) => (
        <Space size="small" wrap>
          <Button size="small" icon={<SettingOutlined />} onClick={() => setDetailAppId(record.app_id)}>
            配置
          </Button>
          <Button size="small" onClick={() => handleToggleStatus(record)}>
            {record.status === 'active' ? '禁用' : '启用'}
          </Button>
          <Popconfirm
            title="重置后旧密钥将立即失效，确定重置？"
            onConfirm={() => handleResetSecret(record.app_id)}
            okText="确定"
            cancelText="取消"
          >
            <Button size="small">重置密钥</Button>
          </Popconfirm>
          <Popconfirm
            title="确定删除该应用？关联数据将被清除。"
            onConfirm={() => handleDelete(record.app_id)}
            okText="确定"
            cancelText="取消"
          >
            <Button size="small" danger icon={<DeleteOutlined />}>
              删除
            </Button>
          </Popconfirm>
        </Space>
      ),
    },
  ];

  return (
    <>
      {detailAppId ? (
        <ApplicationDetail
          appId={detailAppId}
          onBack={() => { setDetailAppId(null); fetchApps(); }}
        />
      ) : (
      <Card
        title="应用管理"
        extra={
          <Space>
            <Button icon={<ReloadOutlined />} onClick={fetchApps}>
              刷新
            </Button>
            <Button type="primary" icon={<PlusOutlined />} onClick={() => setWizardOpen(true)}>
              新建应用
            </Button>
          </Space>
        }
      >
        <Table
          columns={columns}
          dataSource={apps}
          rowKey="app_id"
          loading={loading}
          pagination={{ pageSize: 10, showTotal: (t) => `共 ${t} 条` }}
        />
      </Card>
      )}

      {/* 应用配置向导 */}
      <AppConfigWizard
        open={wizardOpen}
        onClose={() => setWizardOpen(false)}
        onSuccess={(info) => {
          setSecretInfo(info);
          setSecretModal(true);
          fetchApps();
        }}
        userId={userId}
      />

      {/* 密钥展示弹窗 */}
      <SecretDisplayModal
        open={secretModal}
        appId={secretInfo.appId}
        appSecret={secretInfo.appSecret}
        onClose={() => setSecretModal(false)}
      />
    </>
  );
}
