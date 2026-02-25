import { useEffect, useState } from 'react';
import { Layout, Menu, Card, Row, Col, Statistic, Button, Typography, message } from 'antd';
import {
  UserOutlined, SafetyOutlined, ApartmentOutlined,
  CrownOutlined, AuditOutlined, LogoutOutlined, DashboardOutlined,
  TeamOutlined, AppstoreOutlined, CloudOutlined,
  FundOutlined, HistoryOutlined, MailOutlined,
} from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../store/AuthContext';
import axios from 'axios';
import UsersPanel from './panels/UsersPanel';
import RolesPanel from './panels/RolesPanel';
import PermissionsPanel from './panels/PermissionsPanel';
import OrganizationsPanel from './panels/OrganizationsPanel';
import SubscriptionsPanel from './panels/SubscriptionsPanel';
import ApplicationsPanel from './panels/ApplicationsPanel';
import CloudServicePanel from './panels/CloudServicePanel';
import QuotaMonitorPanel from './panels/QuotaMonitorPanel';
import QuotaHistoryPanel from './panels/QuotaHistoryPanel';
import MessageTemplatePanel from './panels/MessageTemplatePanel';

const { Header, Sider, Content } = Layout;
const { Title } = Typography;

function OverviewPanel() {
  const [health, setHealth] = useState<any>(null);
  useEffect(() => {
    axios.get('http://localhost:8001/health').then(r => setHealth(r.data)).catch(() => {});
  }, []);
  return (
    <>
      <Row gutter={[16, 16]}>
        <Col span={6}><Card><Statistic title="系统状态" value={health?.status || '检查中...'} styles={{ content: { color: health?.status === 'healthy' ? '#3f8600' : '#cf1322' } }} /></Card></Col>
        <Col span={6}><Card><Statistic title="数据库" value={health?.components?.database?.status || '-'} /></Card></Col>
        <Col span={6}><Card><Statistic title="Redis" value={health?.components?.redis?.status || '-'} /></Card></Col>
        <Col span={6}><Card><Statistic title="RabbitMQ" value={health?.components?.rabbitmq?.status || '-'} /></Card></Col>
      </Row>
      <Card style={{ marginTop: 16 }} title="服务端口">
        <Row gutter={[16, 8]}>
          {[
            { name: '认证服务', port: 8001 }, { name: 'SSO服务', port: 8002 },
            { name: '用户服务', port: 8003 }, { name: '权限服务', port: 8004 },
            { name: '组织服务', port: 8005 }, { name: '订阅服务', port: 8006 },
            { name: '管理服务', port: 8007 }, { name: '网关服务', port: 8008 },
          ].map(s => (
            <Col span={6} key={s.port}>
              <Card size="small"><Statistic title={s.name} value={`localhost:${s.port}`} styles={{ content: { fontSize: 14 } }} /></Card>
            </Col>
          ))}
        </Row>
      </Card>
    </>
  );
}

function AuditPanel() {
  return <Card title="审计日志"><Typography.Text type="secondary">审计日志功能开发中...</Typography.Text></Card>;
}

export default function Dashboard() {
  const { state, dispatch } = useAuth();
  const navigate = useNavigate();
  const [currentPage, setCurrentPage] = useState('dashboard');

  const handleLogout = () => {
    dispatch({ type: 'LOGOUT' });
    message.success('已登出');
    navigate('/login');
  };

  const renderContent = () => {
    switch (currentPage) {
      case 'users': return <UsersPanel />;
      case 'roles': return <RolesPanel />;
      case 'permissions': return <PermissionsPanel />;
      case 'organizations': return <OrganizationsPanel />;
      case 'subscriptions': return <SubscriptionsPanel />;
      case 'audit': return <AuditPanel />;
      case 'applications': return <ApplicationsPanel />;
      case 'cloud-services': return <CloudServicePanel />;
      case 'quota-monitor': return <QuotaMonitorPanel />;
      case 'quota-history': return <QuotaHistoryPanel />;
      case 'message-templates': return <MessageTemplatePanel />;
      default: return <OverviewPanel />;
    }
  };

  return (
    <Layout style={{ minHeight: '100vh' }}>
      <Sider theme="dark" width={200}>
        <div style={{ color: '#fff', padding: '16px 12px', fontSize: 15, fontWeight: 'bold', textAlign: 'center' }}>
          统一认证管理
        </div>
        <Menu theme="dark" mode="inline" selectedKeys={[currentPage]}
          onClick={({ key }) => setCurrentPage(key)}
          items={[
            { key: 'dashboard', icon: <DashboardOutlined />, label: '仪表盘' },
            { key: 'users', icon: <UserOutlined />, label: '用户管理' },
            { key: 'roles', icon: <SafetyOutlined />, label: '角色管理' },
            { key: 'permissions', icon: <CrownOutlined />, label: '权限管理' },
            { key: 'organizations', icon: <ApartmentOutlined />, label: '组织架构' },
            { key: 'subscriptions', icon: <TeamOutlined />, label: '订阅管理' },
            { key: 'audit', icon: <AuditOutlined />, label: '审计日志' },
            { key: 'applications', icon: <AppstoreOutlined />, label: '应用管理' },
            { key: 'cloud-services', icon: <CloudOutlined />, label: '云服务配置' },
            { key: 'quota-monitor', icon: <FundOutlined />, label: '配额监控' },
            { key: 'quota-history', icon: <HistoryOutlined />, label: '配额历史' },
            { key: 'message-templates', icon: <MailOutlined />, label: '消息模板' },
          ]} />
      </Sider>
      <Layout>
        <Header style={{ background: '#fff', padding: '0 24px', display: 'flex', justifyContent: 'space-between', alignItems: 'center' }}>
          <Title level={4} style={{ margin: 0 }}>管理控制台</Title>
          <div>
            <span style={{ marginRight: 16 }}>欢迎, {state.user?.username || 'admin'}</span>
            <Button icon={<LogoutOutlined />} onClick={handleLogout}>登出</Button>
          </div>
        </Header>
        <Content style={{ margin: 16, overflow: 'auto' }}>
          {renderContent()}
        </Content>
      </Layout>
    </Layout>
  );
}
