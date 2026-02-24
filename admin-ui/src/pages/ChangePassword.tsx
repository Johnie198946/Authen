import { useState } from 'react';
import { Form, Input, Button, Card, message, Typography } from 'antd';
import { LockOutlined } from '@ant-design/icons';
import { useNavigate } from 'react-router-dom';
import { useAuth } from '../store/AuthContext';
import { authApi } from '../api/client';

const { Title, Text } = Typography;

export default function ChangePassword() {
  const [loading, setLoading] = useState(false);
  const { state, dispatch } = useAuth();
  const navigate = useNavigate();

  const onFinish = async (values: { old_password: string; new_password: string }) => {
    if (!state.user) {
      message.error('用户信息丢失，请重新登录');
      navigate('/login');
      return;
    }
    setLoading(true);
    try {
      await authApi.changePassword(state.user.id, values.old_password, values.new_password);
      message.success('密码修改成功，请重新登录');
      dispatch({ type: 'LOGOUT' });
      navigate('/login');
    } catch (err: any) {
      const detail = err.response?.data?.detail;
      if (err.response?.status === 401) {
        message.error(detail || '旧密码不正确');
      } else {
        message.error(detail || '密码修改失败');
      }
    } finally {
      setLoading(false);
    }
  };

  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh', background: '#f0f2f5' }}>
      <Card style={{ width: 420 }}>
        <Title level={3} style={{ textAlign: 'center' }}>修改密码</Title>
        <Text type="warning" style={{ display: 'block', textAlign: 'center', marginBottom: 24 }}>
          首次登录需要修改默认密码
        </Text>
        <Form onFinish={onFinish} size="large">
          <Form.Item name="old_password" rules={[{ required: true, message: '请输入旧密码' }]}>
            <Input.Password prefix={<LockOutlined />} placeholder="旧密码" />
          </Form.Item>
          <Form.Item name="new_password" rules={[
            { required: true, message: '请输入新密码' },
            { min: 8, message: '密码至少8位' },
          ]}>
            <Input.Password prefix={<LockOutlined />} placeholder="新密码（至少8位，含大小写字母和数字）" />
          </Form.Item>
          <Form.Item name="confirm" dependencies={['new_password']} rules={[
            { required: true, message: '请确认新密码' },
            ({ getFieldValue }) => ({
              validator(_, value) {
                if (!value || getFieldValue('new_password') === value) return Promise.resolve();
                return Promise.reject(new Error('两次密码不一致'));
              },
            }),
          ]}>
            <Input.Password prefix={<LockOutlined />} placeholder="确认新密码" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={loading} block>确认修改</Button>
          </Form.Item>
        </Form>
      </Card>
    </div>
  );
}
