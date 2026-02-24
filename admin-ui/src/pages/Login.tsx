import { useState } from 'react';
import { Form, Input, Button, Card, message, Typography } from 'antd';
import { UserOutlined, LockOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../store/AuthContext';
import { authApi } from '../api/client';

const { Title } = Typography;

export default function Login() {
  const [loading, setLoading] = useState(false);
  const { dispatch } = useAuth();
  const navigate = useNavigate();

  const onFinish = async (values: { identifier: string; password: string }) => {
    setLoading(true);
    try {
      const { data } = await authApi.login(values.identifier, values.password);
      dispatch({ type: 'LOGIN_SUCCESS', payload: data });
      message.success('登录成功');
      if (data.user.requires_password_change) {
        navigate('/change-password');
      } else {
        navigate('/');
      }
    } catch (err: any) {
      message.error(err.response?.data?.detail || '登录失败');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh', background: '#f0f2f5' }}>
      <Card style={{ width: 400 }}>
        <Title level={3} style={{ textAlign: 'center', marginBottom: 32 }}>
          统一身份认证平台
        </Title>
        <Form onFinish={onFinish} size="large">
          <Form.Item name="identifier" rules={[{ required: true, message: '请输入邮箱或手机号' }]}>
            <Input prefix={<UserOutlined />} placeholder="邮箱或手机号" />
          </Form.Item>
          <Form.Item name="password" rules={[{ required: true, message: '请输入密码' }]}>
            <Input.Password prefix={<LockOutlined />} placeholder="密码" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={loading} block>
              登录
            </Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  );
}
