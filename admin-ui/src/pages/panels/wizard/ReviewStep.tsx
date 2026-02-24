import React, { useEffect, useState } from 'react';
import { Descriptions, Tag, Typography } from 'antd';
import type { WizardData } from './types';
import { METHOD_LABELS, OAUTH_METHODS } from './types';
import { orgApi, subApi } from '../../../api/services';

const { Text } = Typography;

export interface ReviewStepProps {
  wizardData: WizardData;
}

interface OrgNode {
  id: string;
  name: string;
  children?: OrgNode[];
}

function flattenOrgs(nodes: OrgNode[]): Map<string, string> {
  const map = new Map<string, string>();
  const walk = (list: OrgNode[]) => {
    for (const n of list) {
      map.set(n.id, n.name);
      if (n.children) walk(n.children);
    }
  };
  walk(nodes);
  return map;
}

const ReviewStep: React.FC<ReviewStepProps> = ({ wizardData }) => {
  const { basicInfo, loginMethods, scopes, rateLimit, organizations, subscriptionPlanId } = wizardData;
  const enabledMethods = loginMethods.filter((m) => m.is_enabled);
  const hasEnabledMethods = enabledMethods.length > 0;
  const hasScopes = scopes.length > 0;

  const [orgNames, setOrgNames] = useState<Map<string, string>>(new Map());
  const [planName, setPlanName] = useState<string>('');

  useEffect(() => {
    if (organizations.length > 0) {
      orgApi.tree().then((res) => setOrgNames(flattenOrgs(res.data))).catch(() => {});
    }
  }, [organizations]);

  useEffect(() => {
    if (subscriptionPlanId) {
      subApi.listPlans().then((res) => {
        const plan = res.data.find((p: { id: string }) => p.id === subscriptionPlanId);
        if (plan) setPlanName(plan.name);
      }).catch(() => {});
    }
  }, [subscriptionPlanId]);

  return (
    <Descriptions column={1} bordered size="small">
      <Descriptions.Item label="应用名称">{basicInfo.name || '-'}</Descriptions.Item>
      <Descriptions.Item label="应用描述">{basicInfo.description || '-'}</Descriptions.Item>

      <Descriptions.Item label="登录方式">
        {hasEnabledMethods ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {enabledMethods.map((m) => (
              <div key={m.method}>
                <Tag>{METHOD_LABELS[m.method] ?? m.method}</Tag>
                {OAUTH_METHODS.has(m.method) && (
                  <div style={{ marginTop: 4, paddingLeft: 8 }}>
                    <Text type="secondary">Client ID: {m.client_id}</Text>
                    <br />
                    <Text type="secondary">Client Secret: ****</Text>
                  </div>
                )}
              </div>
            ))}
          </div>
        ) : (
          <Text type="secondary">未配置</Text>
        )}
      </Descriptions.Item>

      <Descriptions.Item label="权限范围">
        {hasScopes ? (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
            {scopes.map((scope) => (
              <Tag key={scope}>{scope}</Tag>
            ))}
          </div>
        ) : (
          <Text type="secondary">未配置</Text>
        )}
      </Descriptions.Item>

      <Descriptions.Item label="限流配置">{rateLimit} 次/分钟</Descriptions.Item>

      <Descriptions.Item label="组织架构">
        {organizations.length > 0 ? (
          <div style={{ display: 'flex', flexWrap: 'wrap', gap: 4 }}>
            {organizations.map((id) => (
              <Tag key={id} color="cyan">{orgNames.get(id) || id}</Tag>
            ))}
          </div>
        ) : (
          <Text type="secondary">未配置</Text>
        )}
      </Descriptions.Item>

      <Descriptions.Item label="订阅计划">
        {subscriptionPlanId ? (
          <Tag color="purple">{planName || subscriptionPlanId}</Tag>
        ) : (
          <Text type="secondary">未配置</Text>
        )}
      </Descriptions.Item>
    </Descriptions>
  );
};

export default ReviewStep;
