import { useEffect, useState } from 'react';
import { Card, Tree, Button, Space, Modal, Form, Input, Select, message, Popconfirm, List, Empty, Spin } from 'antd';
import { PlusOutlined, ReloadOutlined, EditOutlined, DeleteOutlined, UserOutlined, UserAddOutlined } from '@ant-design/icons';
import { orgApi, userApi } from '../../api/services';

export default function OrganizationsPanel() {
  const [treeData, setTreeData] = useState<any[]>([]);
  const [loading, setLoading] = useState(false);
  const [selectedOrg, setSelectedOrg] = useState<any>(null);
  // 新建/编辑
  const [editModal, setEditModal] = useState(false);
  const [editingOrg, setEditingOrg] = useState<any>(null);
  const [form] = Form.useForm();
  const [saving, setSaving] = useState(false);
  const [flatOrgs, setFlatOrgs] = useState<any[]>([]);
  // 组织用户
  const [orgUsers, setOrgUsers] = useState<any[]>([]);
  const [userLoading, setUserLoading] = useState(false);
  // 添加用户
  const [addUserModal, setAddUserModal] = useState(false);
  const [allUsers, setAllUsers] = useState<any[]>([]);
  const [selectedUserIds, setSelectedUserIds] = useState<string[]>([]);

  const buildTreeNodes = (nodes: any[]): any[] => {
    return nodes.map((n: any) => ({
      key: n.id,
      title: `${n.name} (层级${n.level})`,
      children: n.children?.length ? buildTreeNodes(n.children) : [],
      raw: n,
    }));
  };

  const flatten = (nodes: any[], result: any[] = []): any[] => {
    for (const n of nodes) {
      result.push(n);
      if (n.children?.length) flatten(n.children, result);
    }
    return result;
  };

  const fetchTree = async () => {
    setLoading(true);
    try {
      const { data } = await orgApi.tree();
      const nodes = Array.isArray(data) ? data : [];
      setTreeData(buildTreeNodes(nodes));
      setFlatOrgs(flatten(nodes));
    } catch { message.error('获取组织树失败'); }
    setLoading(false);
  };

  useEffect(() => { fetchTree(); }, []);

  const onSelectNode = async (keys: any[], info: any) => {
    if (keys.length === 0) { setSelectedOrg(null); return; }
    const org = info.node.raw;
    setSelectedOrg(org);
    // 加载组织用户
    setUserLoading(true);
    try {
      const { data } = await orgApi.getUsers(org.id);
      const userIds: string[] = data.user_ids || [];
      if (userIds.length > 0) {
        // 获取用户详情
        const userDetails = await Promise.all(userIds.map(async (uid: string) => {
          try {
            const { data: u } = await userApi.get(uid);
            return u;
          } catch { return { id: uid, username: uid, email: '-' }; }
        }));
        setOrgUsers(userDetails);
      } else {
        setOrgUsers([]);
      }
    } catch { setOrgUsers([]); }
    setUserLoading(false);
  };

  // 新建组织
  const openCreate = (parentId?: string) => {
    setEditingOrg(null);
    form.resetFields();
    if (parentId) form.setFieldsValue({ parent_id: parentId });
    setEditModal(true);
  };
  const openEdit = () => {
    if (!selectedOrg) return;
    setEditingOrg(selectedOrg);
    form.setFieldsValue({ name: selectedOrg.name });
    setEditModal(true);
  };
  const handleSave = async () => {
    try {
      const values = await form.validateFields();
      setSaving(true);
      if (editingOrg) {
        await orgApi.update(editingOrg.id, { name: values.name });
        message.success('组织更新成功');
      } else {
        await orgApi.create({ name: values.name, parent_id: values.parent_id || undefined });
        message.success('组织创建成功');
      }
      setEditModal(false);
      fetchTree();
    } catch (err: any) {
      if (err.response?.data?.detail) message.error(err.response.data.detail);
    } finally { setSaving(false); }
  };
  const handleDeleteOrg = async () => {
    if (!selectedOrg) return;
    try {
      await orgApi.delete(selectedOrg.id);
      message.success('组织已删除');
      setSelectedOrg(null);
      setOrgUsers([]);
      fetchTree();
    } catch (err: any) { message.error(err.response?.data?.detail || '删除失败'); }
  };

  // 添加用户到组织
  const openAddUser = async () => {
    setAddUserModal(true);
    setSelectedUserIds([]);
    try {
      const { data } = await userApi.list(1, 100);
      setAllUsers(data.users || []);
    } catch { message.error('获取用户列表失败'); }
  };
  const handleAddUsers = async () => {
    if (!selectedOrg || selectedUserIds.length === 0) { message.warning('请选择用户'); return; }
    try {
      await orgApi.assignUsers(selectedOrg.id, selectedUserIds);
      message.success('用户已添加到组织');
      setAddUserModal(false);
      // 刷新用户列表
      onSelectNode([selectedOrg.id], { node: { raw: selectedOrg } });
    } catch (err: any) { message.error(err.response?.data?.detail || '添加失败'); }
  };
  const handleRemoveUser = async (userId: string) => {
    if (!selectedOrg) return;
    try {
      await orgApi.removeUser(selectedOrg.id, userId);
      message.success('用户已从组织移除');
      setOrgUsers(prev => prev.filter(u => u.id !== userId));
    } catch (err: any) { message.error(err.response?.data?.detail || '移除失败'); }
  };

  return (
    <>
      <Card title="组织架构" extra={
        <Space>
          <Button icon={<ReloadOutlined />} onClick={fetchTree}>刷新</Button>
          <Button type="primary" icon={<PlusOutlined />} onClick={() => openCreate()}>新建根组织</Button>
        </Space>
      }>
        <div style={{ display: 'flex', gap: 24 }}>
          {/* 左侧：组织树 */}
          <div style={{ width: 360, minHeight: 400, borderRight: '1px solid #f0f0f0', paddingRight: 16 }}>
            <Spin spinning={loading}>
              {treeData.length > 0 ? (
                <Tree treeData={treeData} onSelect={onSelectNode} defaultExpandAll blockNode
                  selectedKeys={selectedOrg ? [selectedOrg.id] : []} />
              ) : (
                <Empty description="暂无组织，请创建" />
              )}
            </Spin>
          </div>
          {/* 右侧：组织详情 + 用户 */}
          <div style={{ flex: 1 }}>
            {selectedOrg ? (
              <>
                <div style={{ marginBottom: 16, display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
                  <div>
                    <h3 style={{ margin: 0 }}>{selectedOrg.name}</h3>
                    <div style={{ color: '#999', fontSize: 12 }}>路径: {selectedOrg.path} | 层级: {selectedOrg.level}</div>
                  </div>
                  <Space>
                    <Button size="small" icon={<PlusOutlined />} onClick={() => openCreate(selectedOrg.id)}>添加子组织</Button>
                    <Button size="small" icon={<EditOutlined />} onClick={openEdit}>编辑</Button>
                    <Popconfirm title="确定删除该组织？（不能有子节点）" onConfirm={handleDeleteOrg} okText="确定" cancelText="取消">
                      <Button size="small" danger icon={<DeleteOutlined />}>删除</Button>
                    </Popconfirm>
                  </Space>
                </div>
                <Card size="small" title={`组织成员 (${orgUsers.length})`}
                  extra={<Button size="small" icon={<UserAddOutlined />} onClick={openAddUser}>添加成员</Button>}>
                  <Spin spinning={userLoading}>
                    {orgUsers.length > 0 ? (
                      <List size="small" dataSource={orgUsers} renderItem={(u: any) => (
                        <List.Item actions={[
                          <Popconfirm title="确定移除该成员？" onConfirm={() => handleRemoveUser(u.id)} okText="确定" cancelText="取消">
                            <Button size="small" danger type="link">移除</Button>
                          </Popconfirm>
                        ]}>
                          <List.Item.Meta title={u.username} description={u.email || u.phone || '-'} avatar={<UserOutlined />} />
                        </List.Item>
                      )} />
                    ) : <Empty description="暂无成员" image={Empty.PRESENTED_IMAGE_SIMPLE} />}
                  </Spin>
                </Card>
              </>
            ) : (
              <div style={{ textAlign: 'center', padding: 60, color: '#999' }}>← 请在左侧选择一个组织节点</div>
            )}
          </div>
        </div>
      </Card>

      {/* 新建/编辑组织弹窗 */}
      <Modal title={editingOrg ? '编辑组织' : '新建组织'} open={editModal}
        onCancel={() => setEditModal(false)} onOk={handleSave} confirmLoading={saving} okText="保存" cancelText="取消">
        <Form form={form} layout="vertical">
          <Form.Item name="name" label="组织名称" rules={[{ required: true, message: '请输入组织名称' }]}>
            <Input placeholder="请输入组织名称" />
          </Form.Item>
          {!editingOrg && (
            <Form.Item name="parent_id" label="父组织（可选）">
              <Select allowClear placeholder="选择父组织（留空则为根组织）"
                options={flatOrgs.map((o: any) => ({ value: o.id, label: `${'　'.repeat(o.level)}${o.name}` }))} />
            </Form.Item>
          )}
        </Form>
      </Modal>

      {/* 添加用户弹窗 */}
      <Modal title={`添加成员到 ${selectedOrg?.name || ''}`} open={addUserModal}
        onCancel={() => setAddUserModal(false)} onOk={handleAddUsers} okText="添加" cancelText="取消">
        <Select mode="multiple" style={{ width: '100%' }} placeholder="搜索并选择用户"
          value={selectedUserIds} onChange={setSelectedUserIds} optionFilterProp="label" showSearch
          options={allUsers.map((u: any) => ({
            value: u.id,
            label: `${u.username} (${u.email || u.phone || '-'})`,
          }))} />
      </Modal>
    </>
  );
}
