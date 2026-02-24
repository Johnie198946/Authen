import React, { useEffect, useState } from 'react';
import { Radio, Spin, Empty, Typography, Space, Tag } from 'antd';
import { subApi } from '../../../api/services';

const { Text } = Typography;

export interface SubscriptionStepProps {
  data: string;
  onChange: (planId: string) => void;
}

interface Plan {
  id: string;
  name: string;
  description?: string;
  duration_days: number;
  price: number;
}

const SubscriptionStep: React.FC<SubscriptionStepProps> = ({ data, onChange }) => {
  const [plans, setPlans] = useState<Plan[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    subApi.listPlans()
      .then((res) => setPlans(res.data))
      .catch(() => setPlans([]))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <Spin />;
  if (!plans.length) return <Empty description="暂无订阅计划，请先在订阅管理中创建" />;

  return (
    <div>
      <Text type="secondary" style={{ marginBottom: 12, display: 'block' }}>
        为该应用选择默认订阅计划（可选）
      </Text>
      <Radio.Group value={data} onChange={(e) => onChange(e.target.value)} style={{ width: '100%' }}>
        <Space direction="vertical" style={{ width: '100%' }}>
          <Radio value="">
            <Text>不绑定订阅计划</Text>
          </Radio>
          {plans.map((plan) => (
            <Radio key={plan.id} value={plan.id}>
              <Space>
                <Text>{plan.name}</Text>
                <Tag color="blue">{plan.duration_days}天</Tag>
                <Tag color="green">¥{plan.price}</Tag>
              </Space>
              {plan.description && (
                <div style={{ paddingLeft: 24 }}>
                  <Text type="secondary">{plan.description}</Text>
                </div>
              )}
            </Radio>
          ))}
        </Space>
      </Radio.Group>
    </div>
  );
};

export default SubscriptionStep;
