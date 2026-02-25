import React, { useEffect, useState } from 'react';
import { Switch, Select, Radio, Space, Spin, Typography, TreeSelect, Tag } from 'antd';
import { roleApi, permissionApi, orgApi, subApi } from '../../../api/services';
import type { AutoProvisionData } from './types';

const { Text } = Typography;

export interface AutoProvisionStepProps {
  data: AutoProvisionData;
  onChange: (data: AutoProvisionData) => void;
}

interface OrgNode {
  id: string;
  name: string;
  children?: OrgNode[];
}

interface TreeNode {
  value: string;
  title: string;
  children?: TreeNode[];
}

function toTreeSelectData(nodes: OrgNode[]): TreeNode[] {
  return nodes.map((n) => ({
    value: n.id,
    title: n.name,
    children: n.children?.length ? toTreeSelectData(n.children) : undefined,
  }));
}

const AutoProvisionStep: React.FC<AutoProvisionStepProps> = ({ data, onChange }) => {
  const [roles, setRoles] = useState<{ id: string; name: string }[]>([]);
  const [permissions, setPermissions] = useState<{ id: string; name: string }[]>([]);
  const [orgTree, setOrgTree] = useState<TreeNode[]>([]);
  const [plans, setPlans] = useState<{ id: string; name: string; duration_days: number; price: number }[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    Promise.all([
      roleApi.list().then((r) => r.data).catch(() => []),
      permissionApi.list().then((r) => r.data).catch(() => []),
      orgApi.tree().then((r) => toTreeSelectData(r.data)).catch(() => []),
      subApi.listPlans().then((r) => r.data).catch(() => []),
    ]).then(([r, p, o, s]) => {
      setRoles(r);
      setPermissions(p);
      setOrgTree(o);
      setPlans(s);
    }).finally(() => setLoading(false));
  }, []);

  const update = (partial: Partial<AutoProvisionData>) => {
    onChange({ ...data, ...partial });
  };

  if (loading) return <Spin />;

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 20 }}>
      <Text type="secondary">
        启用后，通过该应用注册的新用户将自动获得以下角色、权限、组织和订阅配置。
      </Text>

      <div>
        <span style={{ marginRight: 12 }}>启用自动配置：</span>
        <Switch checked={data.enabled} onChange={(v) => update({ enabled: v })} />
      </div>

      <div>
        <div style={{ marginBottom: 4 }}>角色：</div>
        <Select
          mode="multiple"
          placeholder="选择角色"
          value={data.roleIds}
          onChange={(v) => update({ roleIds: v })}
          style={{ width: '100%' }}
          options={roles.map((r) => ({ label: r.name, value: r.id }))}
        />
      </div>

      <div>
        <div style={{ marginBottom: 4 }}>权限：</div>
        <Select
          mode="multiple"
          placeholder="选择权限"
          value={data.permissionIds}
          onChange={(v) => update({ permissionIds: v })}
          style={{ width: '100%' }}
          options={permissions.map((p) => ({ label: p.name, value: p.id }))}
        />
      </div>

      <div>
        <div style={{ marginBottom: 4 }}>组织：</div>
        {orgTree.length > 0 ? (
          <TreeSelect
            placeholder="选择组织"
            value={data.organizationId}
            onChange={(v) => update({ organizationId: v || undefined })}
            treeData={orgTree}
            allowClear
            style={{ width: '100%' }}
            treeDefaultExpandAll
          />
        ) : (
          <Text type="secondary">暂无组织数据</Text>
        )}
      </div>

      <div>
        <div style={{ marginBottom: 4 }}>订阅计划：</div>
        {plans.length > 0 ? (
          <Radio.Group
            value={data.subscriptionPlanId || ''}
            onChange={(e) => update({ subscriptionPlanId: e.target.value || undefined })}
          >
            <Space direction="vertical">
              <Radio value="">不绑定订阅计划</Radio>
              {plans.map((plan) => (
                <Radio key={plan.id} value={plan.id}>
                  <Space>
                    <span>{plan.name}</span>
                    <Tag color="blue">{plan.duration_days}天</Tag>
                    <Tag color="green">¥{plan.price}</Tag>
                  </Space>
                </Radio>
              ))}
            </Space>
          </Radio.Group>
        ) : (
          <Text type="secondary">暂无订阅计划</Text>
        )}
      </div>
    </div>
  );
};

export default AutoProvisionStep;
