import { useEffect, useState, useCallback } from 'react';
import { Card, Table, Input, DatePicker, Space, Tag, message } from 'antd';
import { ReloadOutlined, LineChartOutlined, TableOutlined } from '@ant-design/icons';
import type { ColumnsType } from 'antd/es/table';
import axios from 'axios';
import dayjs from 'dayjs';
import type { Dayjs } from 'dayjs';

const { RangePicker } = DatePicker;
const ADMIN_API = 'http://localhost:8007/api/v1';

interface HistoryItem {
  id: string;
  billing_cycle_start: string;
  billing_cycle_end: string;
  request_quota_limit: number;
  request_quota_used: number;
  token_quota_limit: number;
  token_quota_used: number;
  reset_type: string;
  created_at: string;
}

interface HistoryResponse {
  items: HistoryItem[];
  total: number;
  page: number;
  page_size: number;
}

/* ---------- Simple SVG Line Chart ---------- */

interface ChartPoint { label: string; requestUsed: number; tokenUsed: number }

function SimpleLineChart({ data }: { data: ChartPoint[] }) {
  if (data.length === 0) {
    return <div style={{ textAlign: 'center', color: '#999', padding: 40 }}>暂无数据</div>;
  }

  const W = 700;
  const H = 300;
  const PAD = { top: 30, right: 30, bottom: 60, left: 70 };
  const innerW = W - PAD.left - PAD.right;
  const innerH = H - PAD.top - PAD.bottom;

  const maxReq = Math.max(...data.map((d) => d.requestUsed), 1);
  const maxTok = Math.max(...data.map((d) => d.tokenUsed), 1);

  const xStep = data.length > 1 ? innerW / (data.length - 1) : 0;

  const toReqY = (v: number) => PAD.top + innerH - (v / maxReq) * innerH;
  const toTokY = (v: number) => PAD.top + innerH - (v / maxTok) * innerH;
  const toX = (i: number) => PAD.left + i * xStep;

  const reqPoints = data.map((d, i) => `${toX(i)},${toReqY(d.requestUsed)}`).join(' ');
  const tokPoints = data.map((d, i) => `${toX(i)},${toTokY(d.tokenUsed)}`).join(' ');

  return (
    <div style={{ overflowX: 'auto' }}>
      <svg width={W} height={H} style={{ display: 'block', margin: '0 auto' }}>
        {/* Grid lines */}
        {[0, 0.25, 0.5, 0.75, 1].map((r) => {
          const y = PAD.top + innerH * (1 - r);
          return (
            <line key={r} x1={PAD.left} y1={y} x2={PAD.left + innerW} y2={y} stroke="#f0f0f0" />
          );
        })}

        {/* Request line (blue) */}
        <polyline points={reqPoints} fill="none" stroke="#1677ff" strokeWidth={2} />
        {data.map((d, i) => (
          <circle key={`r${i}`} cx={toX(i)} cy={toReqY(d.requestUsed)} r={3} fill="#1677ff">
            <title>请求: {d.requestUsed}</title>
          </circle>
        ))}

        {/* Token line (green) */}
        <polyline points={tokPoints} fill="none" stroke="#52c41a" strokeWidth={2} />
        {data.map((d, i) => (
          <circle key={`t${i}`} cx={toX(i)} cy={toTokY(d.tokenUsed)} r={3} fill="#52c41a">
            <title>Token: {d.tokenUsed}</title>
          </circle>
        ))}

        {/* X-axis labels */}
        {data.map((d, i) => (
          <text
            key={`xl${i}`}
            x={toX(i)}
            y={H - PAD.bottom + 18}
            textAnchor="middle"
            fontSize={10}
            fill="#666"
            transform={`rotate(-30, ${toX(i)}, ${H - PAD.bottom + 18})`}
          >
            {d.label}
          </text>
        ))}

        {/* Y-axis labels (request) */}
        {[0, 0.5, 1].map((r) => (
          <text
            key={`yr${r}`}
            x={PAD.left - 8}
            y={PAD.top + innerH * (1 - r) + 4}
            textAnchor="end"
            fontSize={10}
            fill="#1677ff"
          >
            {Math.round(maxReq * r)}
          </text>
        ))}

        {/* Legend */}
        <rect x={PAD.left} y={6} width={12} height={12} fill="#1677ff" rx={2} />
        <text x={PAD.left + 16} y={16} fontSize={11} fill="#333">请求次数</text>
        <rect x={PAD.left + 90} y={6} width={12} height={12} fill="#52c41a" rx={2} />
        <text x={PAD.left + 106} y={16} fontSize={11} fill="#333">Token 消耗</text>
      </svg>
    </div>
  );
}

/* ---------- Main Panel ---------- */

type ViewMode = 'table' | 'chart';

export default function QuotaHistoryPanel() {
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(false);
  const [page, setPage] = useState(1);
  const [pageSize] = useState(20);
  const [appId, setAppId] = useState('');
  const [dateRange, setDateRange] = useState<[Dayjs | null, Dayjs | null] | null>(null);
  const [viewMode, setViewMode] = useState<ViewMode>('table');

  const fetchData = useCallback(
    async (p = page) => {
      if (!appId.trim()) {
        setItems([]);
        setTotal(0);
        return;
      }
      setLoading(true);
      try {
        const params: Record<string, unknown> = { page: p, page_size: pageSize };
        if (dateRange?.[0]) params.start_time = dateRange[0].toISOString();
        if (dateRange?.[1]) params.end_time = dateRange[1].toISOString();

        const { data } = await axios.get<HistoryResponse>(
          `${ADMIN_API}/admin/quota/${encodeURIComponent(appId.trim())}/history`,
          { params },
        );
        setItems(data.items || []);
        setTotal(data.total || 0);
      } catch {
        message.error('获取配额使用历史失败');
      }
      setLoading(false);
    },
    [appId, dateRange, page, pageSize],
  );

  useEffect(() => {
    if (appId.trim()) fetchData();
  }, [fetchData]); // eslint-disable-line react-hooks/exhaustive-deps

  const handlePageChange = (p: number) => {
    setPage(p);
    fetchData(p);
  };

  const handleSearch = () => {
    setPage(1);
    fetchData(1);
  };

  /* ---------- Table columns ---------- */

  const columns: ColumnsType<HistoryItem> = [
    {
      title: '计费周期',
      key: 'billing_cycle',
      width: 220,
      render: (_: unknown, r: HistoryItem) => {
        const fmt = (v: string) => (v ? dayjs(v).format('YYYY-MM-DD') : '-');
        return `${fmt(r.billing_cycle_start)} ~ ${fmt(r.billing_cycle_end)}`;
      },
    },
    {
      title: '请求上限',
      dataIndex: 'request_quota_limit',
      key: 'request_quota_limit',
      width: 110,
      render: (v: number) => (v === -1 ? '无限制' : v.toLocaleString()),
    },
    {
      title: '请求已用',
      dataIndex: 'request_quota_used',
      key: 'request_quota_used',
      width: 110,
      render: (v: number) => v.toLocaleString(),
    },
    {
      title: 'Token 上限',
      dataIndex: 'token_quota_limit',
      key: 'token_quota_limit',
      width: 110,
      render: (v: number) => (v === -1 ? '无限制' : v.toLocaleString()),
    },
    {
      title: 'Token 已用',
      dataIndex: 'token_quota_used',
      key: 'token_quota_used',
      width: 110,
      render: (v: number) => v.toLocaleString(),
    },
    {
      title: '重置类型',
      dataIndex: 'reset_type',
      key: 'reset_type',
      width: 100,
      render: (v: string) => (
        <Tag color={v === 'auto' ? 'blue' : 'orange'}>{v === 'auto' ? '自动' : '手动'}</Tag>
      ),
    },
    {
      title: '记录时间',
      dataIndex: 'created_at',
      key: 'created_at',
      width: 180,
      render: (v: string) => (v ? dayjs(v).format('YYYY-MM-DD HH:mm:ss') : '-'),
    },
  ];

  /* ---------- Chart data ---------- */

  const chartData: ChartPoint[] = [...items]
    .sort((a, b) => (a.billing_cycle_start > b.billing_cycle_start ? 1 : -1))
    .map((r) => ({
      label: r.billing_cycle_start ? dayjs(r.billing_cycle_start).format('MM-DD') : '-',
      requestUsed: r.request_quota_used,
      tokenUsed: r.token_quota_used,
    }));

  /* ---------- Render ---------- */

  return (
    <Card
      title="配额使用历史"
      extra={
        <Space>
          <a
            onClick={() => setViewMode(viewMode === 'table' ? 'chart' : 'table')}
            style={{ cursor: 'pointer' }}
          >
            <Space>
              {viewMode === 'table' ? <LineChartOutlined /> : <TableOutlined />}
              {viewMode === 'table' ? '图表' : '表格'}
            </Space>
          </a>
          <a onClick={handleSearch} style={{ cursor: 'pointer' }}>
            <Space>
              <ReloadOutlined />
              刷新
            </Space>
          </a>
        </Space>
      }
    >
      {/* Filters */}
      <Space style={{ marginBottom: 16 }} wrap>
        <Input
          placeholder="输入应用 ID"
          value={appId}
          onChange={(e) => setAppId(e.target.value)}
          onPressEnter={handleSearch}
          style={{ width: 280 }}
          allowClear
        />
        <RangePicker
          value={dateRange as [Dayjs, Dayjs] | null}
          onChange={(vals) => setDateRange(vals as [Dayjs | null, Dayjs | null] | null)}
        />
        <Tag color="blue">{total} 条记录</Tag>
      </Space>

      {/* Content */}
      {viewMode === 'table' ? (
        <Table
          columns={columns}
          dataSource={items}
          rowKey="id"
          loading={loading}
          pagination={{
            current: page,
            total,
            pageSize,
            showTotal: (t) => `共 ${t} 条`,
            onChange: handlePageChange,
          }}
          size="middle"
          scroll={{ x: 940 }}
        />
      ) : (
        <SimpleLineChart data={chartData} />
      )}
    </Card>
  );
}
