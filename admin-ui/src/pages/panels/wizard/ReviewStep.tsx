import React, { useEffect, useState } from 'react';
import { Descriptions, Tag, Typography } from 'antd';
import type { WizardData } from './types';
import { METHOD_LABELS, OAUTH_METHODS } from './types';
import { orgApi, subApi, roleApi, permissionApi } from '../../../api/services';

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
  const { basicInfo, loginMethods, scopes, rateLimit, organizations, subscriptionPlanId, autoProvision } = wizardData;
  const enabledMethods = loginMethods.filter((m) => m.is_enabled);
  const hasEnabledMethods = enabledMethods.length > 0;
  const hasScopes = scopes.length > 0;

  const [orgNames, setOrgNames] = useState<Map<string, string>>(new Map());
  const [planName, setPlanName] = useState<string>('');
  const [roleNames, setRoleNames] = useState<Map<string, string>>(new Map());
  const [permissionNames, setPermissionNames] = useState<Map<string, string>>(new Map());

  useEffect(() => {
    if (organizations.length > 0 || autoProvision.organizationId) {
      orgApi.tree().then((res) => setOrgNames(flattenOrgs(res.data))).catch(() => {});
    }
  }, [organizations, autoProvision.organizationId]);

  useEffect(() => {
    if (subscriptionPlanId || autoProvision.subscriptionPlanId) {
      subApi.listPlans().then((res) => {
        const plan = res.data.find((p: { id: string }) => p.id === subscriptionPlanId);
        if (plan) setPlanName(plan.name);
      }).catch(() => {});
    }
  }, [subscriptionPlanId, autoProvision.subscriptionPlanId]);

  useEffect(() => {
    if (autoProvision.roleIds.length > 0) {
      roleApi.list().then((res) => {
        const map = new Map<string, string>();
        res.data.forEach((r: { id: string; name: string }) => map.set(r.id, r.name));
        setRoleNames(map);
      }).catch(() => {});
    }
  }, [autoProvision.roleIds]);

  useEffect(() => {
    if (autoProvision.permissionIds.length > 0) {
      permissionApi.list().then((res) => {
        const map = new Map<string, string>();
        res.data.forEach((p: { id: string; name: string }) => map.set(p.id, p.name));
        setPermissionNames(map);
      }).catch(() => {});
    }
  }, [autoProvision.permissionIds]);

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

      <Descriptions.Item label="自动配置">
        {autoProvision.enabled ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 4 }}>
            <Tag color="green">已启用</Tag>
            {autoProvision.roleIds.length > 0 && (
              <div>
                <Text type="secondary">角色：</Text>
                {autoProvision.roleIds.map((id) => (
                  <Tag key={id}>{roleNames.get(id) || id}</Tag>
                ))}
              </div>
            )}
            {autoProvision.permissionIds.length > 0 && (
              <div>
                <Text type="secondary">权限：</Text>
                {autoProvision.permissionIds.map((id) => (
                  <Tag key={id}>{permissionNames.get(id) || id}</Tag>
                ))}
              </div>
            )}
            {autoProvision.organizationId && (
              <div>
                <Text type="secondary">组织：</Text>
                <Tag color="cyan">{orgNames.get(autoProvision.organizationId) || autoProvision.organizationId}</Tag>
              </div>
            )}
            {autoProvision.subscriptionPlanId && (
              <div>
                <Text type="secondary">订阅计划：</Text>
                <Tag color="purple">{autoProvision.subscriptionPlanId}</Tag>
              </div>
            )}
          </div>
        ) : (
          <Text type="secondary">未启用</Text>
        )}
      </Descriptions.Item>
    </Descriptions>
  );
};

export default ReviewStep;
