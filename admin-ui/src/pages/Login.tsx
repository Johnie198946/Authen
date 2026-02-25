import { useState } from 'react';
import { Form, Input, Button, Card, message, Typography, Tabs } from 'antd';
import { UserOutlined, LockOutlined, PhoneOutlined, MailOutlined, SafetyOutlined } from '@ant-design/icons';
import { useNavigate, Link } from 'react-router-dom';
import { useAuth } from '../store/AuthContext';
import { authApi } from '../api/client';
import { useCountdown } from '../hooks/useCountdown';

const { Title } = Typography;

export default function Login() {
  const [passwordLoading, setPasswordLoading] = useState(false);
  const [phoneLoading, setPhoneLoading] = useState(false);
  const [emailLoading, setEmailLoading] = useState(false);
  const [phoneSending, setPhoneSending] = useState(false);
  const [emailSending, setEmailSending] = useState(false);
  const { dispatch } = useAuth();
  const navigate = useNavigate();
  const phoneCountdown = useCountdown(60);
  const emailCountdown = useCountdown(60);
  const [passwordForm] = Form.useForm();
  const [phoneForm] = Form.useForm();
  const [emailForm] = Form.useForm();

  const handleLoginSuccess = (data: any) => {
    dispatch({ type: 'LOGIN_SUCCESS', payload: data });
    message.success('登录成功');
    if (data.user.requires_password_change) {
      navigate('/change-password');
    } else {
      navigate('/');
    }
  };

  const onPasswordLogin = async (values: { identifier: string; password: string }) => {
    setPasswordLoading(true);
    try {
      const { data } = await authApi.login(values.identifier, values.password);
      handleLoginSuccess(data);
    } catch (err: any) {
      message.error(err.response?.data?.detail || '登录失败');
    } finally {
      setPasswordLoading(false);
    }
  };

  const handleSendSmsCode = async () => {
    try {
      await phoneForm.validateFields(['phone']);
    } catch {
      return;
    }
    const phone = phoneForm.getFieldValue('phone');
    setPhoneSending(true);
    try {
      await authApi.sendSmsCode(phone);
      message.success('验证码已发送');
      phoneCountdown.start();
    } catch (err: any) {
      message.error(err.response?.data?.detail || '发送失败');
    } finally {
      setPhoneSending(false);
    }
  };

  const handleSendEmailCode = async () => {
    try {
      await emailForm.validateFields(['email']);
    } catch {
      return;
    }
    const email = emailForm.getFieldValue('email');
    setEmailSending(true);
    try {
      await authApi.sendEmailCode(email);
      message.success('验证码已发送');
      emailCountdown.start();
    } catch (err: any) {
      message.error(err.response?.data?.detail || '发送失败');
    } finally {
      setEmailSending(false);
    }
  };

  const onPhoneCodeLogin = async (values: { phone: string; code: string }) => {
    setPhoneLoading(true);
    try {
      const { data } = await authApi.loginWithPhoneCode(values.phone, values.code);
      handleLoginSuccess(data);
    } catch (err: any) {
      message.error(err.response?.data?.detail || '登录失败');
    } finally {
      setPhoneLoading(false);
    }
  };

  const onEmailCodeLogin = async (values: { email: string; code: string }) => {
    setEmailLoading(true);
    try {
      const { data } = await authApi.loginWithEmailCode(values.email, values.code);
      handleLoginSuccess(data);
    } catch (err: any) {
      message.error(err.response?.data?.detail || '登录失败');
    } finally {
      setEmailLoading(false);
    }
  };

  const tabItems = [
    {
      key: 'password',
      label: '密码登录',
      children: (
        <Form form={passwordForm} onFinish={onPasswordLogin} size="large">
          <Form.Item name="identifier" rules={[{ required: true, message: '请输入邮箱或手机号' }]}>
            <Input prefix={<UserOutlined />} placeholder="邮箱或手机号" />
          </Form.Item>
          <Form.Item name="password" rules={[{ required: true, message: '请输入密码' }]}>
            <Input.Password prefix={<LockOutlined />} placeholder="密码" />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={passwordLoading} block>
              登录
            </Button>
          </Form.Item>
        </Form>
      ),
    },
    {
      key: 'phone',
      label: '手机验证码登录',
      children: (
        <Form form={phoneForm} onFinish={onPhoneCodeLogin} size="large">
          <Form.Item
            name="phone"
            rules={[
              { required: true, message: '请输入手机号' },
              { pattern: /^1\d{10}$/, message: '请输入有效的手机号' },
            ]}
          >
            <Input prefix={<PhoneOutlined />} placeholder="手机号" />
          </Form.Item>
          <Form.Item name="code" rules={[{ required: true, message: '请输入验证码' }]}>
            <Input
              prefix={<SafetyOutlined />}
              placeholder="验证码"
              suffix={
                <Button
                  type="link"
                  size="small"
                  disabled={phoneCountdown.isCounting}
                  loading={phoneSending}
                  onClick={handleSendSmsCode}
                  style={{ padding: 0 }}
                >
                  {phoneCountdown.isCounting ? `${phoneCountdown.countdown}秒后重发` : '发送验证码'}
                </Button>
              }
            />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={phoneLoading} block>
              登录
            </Button>
          </Form.Item>
        </Form>
      ),
    },
    {
      key: 'email',
      label: '邮箱验证码登录',
      children: (
        <Form form={emailForm} onFinish={onEmailCodeLogin} size="large">
          <Form.Item
            name="email"
            rules={[
              { required: true, message: '请输入邮箱' },
              { type: 'email', message: '请输入有效的邮箱地址' },
            ]}
          >
            <Input prefix={<MailOutlined />} placeholder="邮箱" />
          </Form.Item>
          <Form.Item name="code" rules={[{ required: true, message: '请输入验证码' }]}>
            <Input
              prefix={<SafetyOutlined />}
              placeholder="验证码"
              suffix={
                <Button
                  type="link"
                  size="small"
                  disabled={emailCountdown.isCounting}
                  loading={emailSending}
                  onClick={handleSendEmailCode}
                  style={{ padding: 0 }}
                >
                  {emailCountdown.isCounting ? `${emailCountdown.countdown}秒后重发` : '发送验证码'}
                </Button>
              }
            />
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={emailLoading} block>
              登录
            </Button>
          </Form.Item>
        </Form>
      ),
    },
  ];

  return (
    <div style={{ display: 'flex', justifyContent: 'center', alignItems: 'center', minHeight: '100vh', background: '#f0f2f5' }}>
      <Card style={{ width: 420 }}>
        <Title level={3} style={{ textAlign: 'center', marginBottom: 24 }}>
          统一身份认证平台
        </Title>
        <Tabs defaultActiveKey="password" items={tabItems} centered />
        <div style={{ textAlign: 'center', marginTop: 8 }}>
          <Link to="/register">还没有账号？立即注册</Link>
        </div>
      </Card>
    </div>
  );
}
