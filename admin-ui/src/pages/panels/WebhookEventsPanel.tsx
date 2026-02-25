import { useEffect, useState, useCallback } from 'react';
import { Table, Tag, Select, Space, Modal, Descriptions, message, Typography } from 'antd';
import { ReloadOutlined } from '@ant-design/icons';
import { applicationApi } from '../../api/services';

const { Text } = Typography;

interface WebhookEventsPanelProps {
  appId: string;
}

const STATUS_OPTIONS = [
  { value: '', label: '全部状态' },
  { value: 'success', label: '成功' },
  { value: 'failed', label: '失败' },
  { value: 'duplicate', label: '重复' },
  { value: 'pending', label: '处理中' },
];

const STATUS_COLOR: Record<string, string> = {
  success: 'green',
  failed: 'red',
  duplicate: 'gold',
  pending: 'default',
};

const STATUS_LABEL: Record<string, string> = {
  success: '成功',
  failed: '失败',
  duplicate: '重复',
  pending: '处理中',
};

export default function WebhookEventsPanel({ appId }: WebhookEventsPanelProps) {
  const [events, setEvents] = useState<any[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(10);
  const [statusFilter, setStatusFilter] = useState('');
  const [detailModal, setDetailModal] = useState(false);
  const [selectedEvent, setSelectedEvent] = useState<any>(null);

  const fetchEvents = useCallback(async (p = page, status = statusFilter) => {
    setLoading(true);
    try {
      const params: Record<string, any> = {
        app_id: appId,
        page: p,
        page_size: pageSize,
      };
      if (status) params.status = status;
      const { data } = await applicationApi.getWebhookEvents(params);
      setEvents(data.events || data.items || []);
      setTotal(data.total || 0);
    } catch {
      message.error('获取 Webhook 事件日志失败');
    }
    setLoading(false);
  }, [appId, page, pageSize, statusFilter]);

  useEffect(() => {
    fetchEvents();
  }, [fetchEvents]);

  const handleStatusChange = (value: string) => {
    setStatusFilter(value);
    setPage(1);
    fetchEvents(1, value);
  };

  const handlePageChange = (p: number) => {
    setPage(p);
    fetchEvents(p);
  };

  const openDetail = (record: any) => {
    setSelectedEvent(record);
    setDetailModal(true);
  };

  const columns = [
    {
      title: '事件ID',
      dataIndex: 'event_id',
      key: 'event_id',
      ellipsis: true,
      width: 200,
      render: (v: string, record: any) => (
        <a onClick={() => openDetail(record)}>{v}</a>
      ),
    },
    {
      title: '事件类型',
      dataIndex: 'event_type',
      key: 'event_type',
      width: 180,
      render: (v: string) => <Tag>{v}</Tag>,
    },
    {
      title: '处理状态',
      dataIndex: 'status',
      key: 'status',
      width: 100,
      render: (s: string) => (
        <Tag color={STATUS_COLOR[s] || 'default'}>
          {STATUS_LABEL[s] || s}
        </Tag>
      ),
    },
    {
      title: '处理时间',
      dataIndex: 'processed_at',
      key: 'processed_at',
      width: 180,
      render: (v: string) => v ? new Date(v).toLocaleString() : '-',
    },
  ];

  return (
    <>
      <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
        <Select
          value={statusFilter}
          onChange={handleStatusChange}
          options={STATUS_OPTIONS}
          style={{ width: 160 }}
        />
        <a onClick={() => fetchEvents()} style={{ cursor: 'pointer' }}>
          <Space>
            <ReloadOutlined />
            刷新
          </Space>
        </a>
      </div>

      <Table
        columns={columns}
        dataSource={events}
        rowKey="event_id"
        loading={loading}
        pagination={{
          current: page,
          total,
          pageSize,
          showTotal: (t) => `共 ${t} 条`,
          onChange: handlePageChange,
        }}
        onRow={(record) => ({
          onClick: () => openDetail(record),
          style: { cursor: 'pointer' },
        })}
        size="small"
      />

      <Modal
        title="事件详情"
        open={detailModal}
        onCancel={() => setDetailModal(false)}
        footer={null}
        width={640}
      >
        {selectedEvent && (
          <Descriptions column={1} bordered size="small">
            <Descriptions.Item label="事件ID">{selectedEvent.event_id}</Descriptions.Item>
            <Descriptions.Item label="事件类型">
              <Tag>{selectedEvent.event_type}</Tag>
            </Descriptions.Item>
            <Descriptions.Item label="处理状态">
              <Tag color={STATUS_COLOR[selectedEvent.status] || 'default'}>
                {STATUS_LABEL[selectedEvent.status] || selectedEvent.status}
              </Tag>
            </Descriptions.Item>
            <Descriptions.Item label="处理时间">
              {selectedEvent.processed_at ? new Date(selectedEvent.processed_at).toLocaleString() : '-'}
            </Descriptions.Item>
            <Descriptions.Item label="创建时间">
              {selectedEvent.created_at ? new Date(selectedEvent.created_at).toLocaleString() : '-'}
            </Descriptions.Item>
            <Descriptions.Item label="请求体摘要">
              {selectedEvent.request_summary ? (
                <pre style={{ margin: 0, maxHeight: 200, overflow: 'auto', fontSize: 12 }}>
                  {typeof selectedEvent.request_summary === 'string'
                    ? selectedEvent.request_summary
                    : JSON.stringify(selectedEvent.request_summary, null, 2)}
                </pre>
              ) : (
                <Text type="secondary">无</Text>
              )}
            </Descriptions.Item>
            <Descriptions.Item label="响应摘要">
              {selectedEvent.response_summary ? (
                <pre style={{ margin: 0, maxHeight: 200, overflow: 'auto', fontSize: 12 }}>
                  {typeof selectedEvent.response_summary === 'string'
                    ? selectedEvent.response_summary
                    : JSON.stringify(selectedEvent.response_summary, null, 2)}
                </pre>
              ) : (
                <Text type="secondary">无</Text>
              )}
            </Descriptions.Item>
            {selectedEvent.error_message && (
              <Descriptions.Item label="错误信息">
                <Text type="danger">{selectedEvent.error_message}</Text>
              </Descriptions.Item>
            )}
          </Descriptions>
        )}
      </Modal>
    </>
  );
}
