import React, { useEffect, useState } from 'react';
import { Tree, Spin, Empty, Typography } from 'antd';
import { orgApi } from '../../../api/services';
import type { DataNode } from 'antd/es/tree';

const { Text } = Typography;

export interface OrganizationStepProps {
  data: string[];
  onChange: (orgIds: string[]) => void;
}

interface OrgNode {
  id: string;
  name: string;
  children?: OrgNode[];
}

function toTreeData(nodes: OrgNode[]): DataNode[] {
  return nodes.map((n) => ({
    key: n.id,
    title: n.name,
    children: n.children?.length ? toTreeData(n.children) : undefined,
  }));
}

const OrganizationStep: React.FC<OrganizationStepProps> = ({ data, onChange }) => {
  const [treeData, setTreeData] = useState<DataNode[]>([]);
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    setLoading(true);
    orgApi.tree()
      .then((res) => setTreeData(toTreeData(res.data)))
      .catch(() => setTreeData([]))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <Spin />;
  if (!treeData.length) return <Empty description="暂无组织数据，请先在组织管理中创建" />;

  return (
    <div>
      <Text type="secondary" style={{ marginBottom: 12, display: 'block' }}>
        选择该应用可访问的组织节点（可多选）
      </Text>
      <Tree
        checkable
        checkedKeys={data}
        onCheck={(checked) => onChange((Array.isArray(checked) ? checked : checked.checked) as string[])}
        treeData={treeData}
        defaultExpandAll
      />
    </div>
  );
};

export default OrganizationStep;
