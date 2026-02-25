import { useEffect, useState, useCallback, useRef } from 'react';
import {
  Card,
  Table,
  Progress,
  Select,
  Space,
  Tag,
  Button,
  Modal,
  InputNumber,
  Form,
  Descriptions,
  message,
} from 'antd';
import { ReloadOutlined, EditOutlined, UndoOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import axios from 'axios';

const ADMIN_API = 'http://localhost:8007/api/v1';

interface QuotaOverviewItem {
  app_id: string;
  app_name: string;
  request_quota_limit: number;
  request_quota_used: number;
  request_quota_remaining: number;
  token_quota_limit: number;
  token_quota_used: number;
  token_quota_remaining: number;
  request_usage_rate: number;
  token_usage_rate: number;
  billing_cycle_start: string;
  billing_cycle_end: string;
}

type SortField = 'request_usage_rate' | 'token_usage_rate';

const SORT_OPTIONS: { value: SortField; label: string }[] = [
  { value: 'request_usage_rate', label: '按请求使用率排序' },
  { value: 'token_usage_rate', label: '按 Token 使用率排序' },
];

const AUTO_REFRESH_INTERVAL = 30_000;

function formatQuota(used: number, limit: number): string {
  if (limit === -1) return `${used} / 无限制`;
  return `${used} / ${limit}`;
}

function formatQuotaLimit(limit: number): string {
  return limit === -1 ? '无限制' : String(limit);
}

export default function QuotaMonitorPanel() {
  const [items, setItems] = useState<QuotaOverviewItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [sortBy, setSortBy] = useState<SortField>('request_usage_rate');
  const timerRef = useRef<ReturnType<typeof setInterval> | null>(null);

  // Override modal state
  const [overrideVisible, setOverrideVisible] = useState(false);
  const [overrideTarget, setOverrideTarget] = useState<QuotaOverviewItem | null>(null);
  const [overrideLoading, setOverrideLoading] = useState(false);
  const [overrideForm] = Form.useForm();

  // Reset modal state
  const [resetVisible, setResetVisible] = useState(false);
  const [resetTarget, setResetTarget] = useState<QuotaOverviewItem | null>(null);
  const [resetLoading, setResetLoading] = useState(false);

  const fetchData = useCallback(async (sort: SortField = sortBy) => {
    setLoading(true);
    try {
      const { data } = await axios.get(`${ADMIN_API}/admin/quota/overview`, {
        params: { sort_by: sort },
      });
      setItems(data.items || []);
    } catch {
      message.error('获取配额概览失败');
    }
    setLoading(false);
  }, [sortBy]);

  // Initial fetch + auto-refresh
  useEffect(() => {
    fetchData();
    timerRef.current = setInterval(() => fetchData(), AUTO_REFRESH_INTERVAL);
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, [fetchData]);

  const handleSortChange = (value: SortField) => {
    setSortBy(value);
    fetchData(value);
  };

  // --- Override handlers ---
  const openOverrideModal = (record: QuotaOverviewItem) => {
    setOverrideTarget(record);
    overrideForm.setFieldsValue({
      request_quota: record.request_quota_limit,
      token_quota: record.token_quota_limit,
    });
    setOverrideVisible(true);
  };

  const handleOverrideSubmit = async () => {
    try {
      const values = await overrideForm.validateFields();
      setOverrideLoading(true);
      await axios.put(`${ADMIN_API}/admin/quota/${overrideTarget!.app_id}/override`, {
        request_quota: values.request_quota,
        token_quota: values.token_quota,
      });
      message.success('配额调整成功');
      setOverrideVisible(false);
      fetchData();
    } catch (err: any) {
      if (err?.response) {
        message.error(err.response.data?.detail || '配额调整失败');
      }
    } finally {
      setOverrideLoading(false);
    }
  };

  // --- Reset handlers ---
  const openResetModal = (record: QuotaOverviewItem) => {
    setResetTarget(record);
    setResetVisible(true);
  };

  const handleResetConfirm = async () => {
    try {
      setResetLoading(true);
      await axios.post(`${ADMIN_API}/admin/quota/${resetTarget!.app_id}/reset`);
      message.success('配额重置成功');
      setResetVisible(false);
      fetchData();
    } catch (err: any) {
      message.error(err?.response?.data?.detail || '配额重置失败');
    } finally {
      setResetLoading(false);
    }
  };

  // Form values for comparison display
  const overrideFormValues = Form.useWatch([], overrideForm);

  const columns: ColumnsType<QuotaOverviewItem> = [
    {
      title: '应用名称',
      dataIndex: 'app_name',
      key: 'app_name',
      width: 160,
    },
    {
      title: '请求次数使用率',
      key: 'request_usage',
      width: 260,
      sorter: (a, b) => a.request_usage_rate - b.request_usage_rate,
      defaultSortOrder: sortBy === 'request_usage_rate' ? 'descend' : undefined,
      render: (_: unknown, record: QuotaOverviewItem) => {
        const rate = record.request_usage_rate;
        const status = rate >= 100 ? 'exception' : undefined;
        return (
          <Space direction="vertical" size={0} style={{ width: '100%' }}>
            <Progress
              percent={Math.min(rate, 100)}
              status={status}
              strokeColor={rate >= 80 && rate < 100 ? '#faad14' : undefined}
              size="small"
              format={() => `${rate.toFixed(1)}%`}
            />
            <span style={{ fontSize: 12, color: '#999' }}>
              {formatQuota(record.request_quota_used, record.request_quota_limit)}
            </span>
          </Space>
        );
      },
    },
    {
      title: 'Token 使用率',
      key: 'token_usage',
      width: 260,
      sorter: (a, b) => a.token_usage_rate - b.token_usage_rate,
      defaultSortOrder: sortBy === 'token_usage_rate' ? 'descend' : undefined,
      render: (_: unknown, record: QuotaOverviewItem) => {
        const rate = record.token_usage_rate;
        const status = rate >= 100 ? 'exception' : undefined;
        return (
          <Space direction="vertical" size={0} style={{ width: '100%' }}>
            <Progress
              percent={Math.min(rate, 100)}
              status={status}
              strokeColor={rate >= 80 && rate < 100 ? '#faad14' : undefined}
              size="small"
              format={() => `${rate.toFixed(1)}%`}
            />
            <span style={{ fontSize: 12, color: '#999' }}>
              {formatQuota(record.token_quota_used, record.token_quota_limit)}
            </span>
          </Space>
        );
      },
    },
    {
      title: '计费周期',
      key: 'billing_cycle',
      width: 200,
      render: (_: unknown, record: QuotaOverviewItem) => {
        const start = record.billing_cycle_start
          ? new Date(record.billing_cycle_start).toLocaleDateString()
          : '-';
        const end = record.billing_cycle_end
          ? new Date(record.billing_cycle_end).toLocaleDateString()
          : '-';
        return `${start} ~ ${end}`;
      },
    },
    {
      title: '重置时间',
      dataIndex: 'billing_cycle_end',
      key: 'reset_time',
      width: 180,
      render: (v: string) => (v ? new Date(v).toLocaleString() : '-'),
    },
    {
      title: '操作',
      key: 'actions',
      width: 200,
      render: (_: unknown, record: QuotaOverviewItem) => (
        <Space>
          <Button
            type="link"
            size="small"
            icon={<EditOutlined />}
            onClick={() => openOverrideModal(record)}
          >
            调整配额
          </Button>
          <Button
            type="link"
            size="small"
            danger
            icon={<UndoOutlined />}
            onClick={() => openResetModal(record)}
          >
            重置配额
          </Button>
        </Space>
      ),
    },
  ];

  return (
    <Card
      title="配额监控"
      extra={
        <Space>
          <Select
            value={sortBy}
            onChange={handleSortChange}
            options={SORT_OPTIONS}
            style={{ width: 180 }}
          />
          <Tag color="blue">{items.length} 个应用</Tag>
          <a onClick={() => fetchData()} style={{ cursor: 'pointer' }}>
            <Space>
              <ReloadOutlined />
              刷新
            </Space>
          </a>
        </Space>
      }
    >
      <Table
        columns={columns}
        dataSource={items}
        rowKey="app_id"
        loading={loading}
        pagination={{ pageSize: 10, showTotal: (t) => `共 ${t} 条` }}
        size="middle"
      />

      {/* 调整配额对话框 */}
      <Modal
        title={`调整配额 - ${overrideTarget?.app_name ?? ''}`}
        open={overrideVisible}
        onOk={handleOverrideSubmit}
        onCancel={() => setOverrideVisible(false)}
        confirmLoading={overrideLoading}
        okText="确认调整"
        cancelText="取消"
        destroyOnClose
        width={560}
      >
        {overrideTarget && (
          <>
            <Descriptions
              title="当前配额"
              column={2}
              size="small"
              bordered
              style={{ marginBottom: 16 }}
            >
              <Descriptions.Item label="请求次数上限">
                {formatQuotaLimit(overrideTarget.request_quota_limit)}
              </Descriptions.Item>
              <Descriptions.Item label="Token 上限">
                {formatQuotaLimit(overrideTarget.token_quota_limit)}
              </Descriptions.Item>
            </Descriptions>

            <Form form={overrideForm} layout="vertical" preserve={false}>
              <Form.Item
                name="request_quota"
                label="新请求次数上限"
                rules={[
                  { required: true, message: '请输入请求次数上限' },
                  {
                    type: 'number',
                    min: -1,
                    message: '值必须 >= -1（-1 表示无限制）',
                  },
                ]}
                extra="-1 表示无限制"
              >
                <InputNumber style={{ width: '100%' }} precision={0} />
              </Form.Item>
              <Form.Item
                name="token_quota"
                label="新 Token 上限"
                rules={[
                  { required: true, message: '请输入 Token 上限' },
                  {
                    type: 'number',
                    min: -1,
                    message: '值必须 >= -1（-1 表示无限制）',
                  },
                ]}
                extra="-1 表示无限制"
              >
                <InputNumber style={{ width: '100%' }} precision={0} />
              </Form.Item>
            </Form>

            {/* Comparison: before → after */}
            {overrideFormValues && (
              <Descriptions
                title="调整对比"
                column={1}
                size="small"
                bordered
              >
                <Descriptions.Item label="请求次数上限">
                  {formatQuotaLimit(overrideTarget.request_quota_limit)}
                  {' → '}
                  {overrideFormValues.request_quota != null
                    ? formatQuotaLimit(overrideFormValues.request_quota)
                    : '-'}
                </Descriptions.Item>
                <Descriptions.Item label="Token 上限">
                  {formatQuotaLimit(overrideTarget.token_quota_limit)}
                  {' → '}
                  {overrideFormValues.token_quota != null
                    ? formatQuotaLimit(overrideFormValues.token_quota)
                    : '-'}
                </Descriptions.Item>
              </Descriptions>
            )}
          </>
        )}
      </Modal>

      {/* 重置配额对话框 */}
      <Modal
        title={`重置配额 - ${resetTarget?.app_name ?? ''}`}
        open={resetVisible}
        onOk={handleResetConfirm}
        onCancel={() => setResetVisible(false)}
        confirmLoading={resetLoading}
        okText="确认重置"
        okButtonProps={{ danger: true }}
        cancelText="取消"
        width={480}
      >
        {resetTarget && (
          <>
            <p>
              确定要重置应用 <strong>{resetTarget.app_name}</strong> 的配额计数器吗？
              重置后当前已使用量将归零，此操作不可撤销。
            </p>
            <Descriptions column={1} size="small" bordered>
              <Descriptions.Item label="当前请求次数已使用">
                {formatQuota(resetTarget.request_quota_used, resetTarget.request_quota_limit)}
                （使用率 {resetTarget.request_usage_rate.toFixed(1)}%）
              </Descriptions.Item>
              <Descriptions.Item label="当前 Token 已使用">
                {formatQuota(resetTarget.token_quota_used, resetTarget.token_quota_limit)}
                （使用率 {resetTarget.token_usage_rate.toFixed(1)}%）
              </Descriptions.Item>
              <Descriptions.Item label="计费周期">
                {resetTarget.billing_cycle_start
                  ? new Date(resetTarget.billing_cycle_start).toLocaleDateString()
                  : '-'}
                {' ~ '}
                {resetTarget.billing_cycle_end
                  ? new Date(resetTarget.billing_cycle_end).toLocaleDateString()
                  : '-'}
              </Descriptions.Item>
            </Descriptions>
          </>
        )}
      </Modal>
    </Card>
  );
}
