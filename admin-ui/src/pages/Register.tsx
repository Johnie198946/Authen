import { useState } from 'react';
import { Form, Input, Button, Card, message, Typography, Tabs } from 'antd';
import { MailOutlined, PhoneOutlined, UserOutlined, LockOutlined, SafetyOutlined } from '@ant-design/icons';
import { useNavigate, Link } from 'react-router-dom';
import { authApi } from '../api/client';
import { useCountdown } from '../hooks/useCountdown';

const { Title } = Typography;

export default function Register() {
  const [emailLoading, setEmailLoading] = useState(false);
  const [phoneLoading, setPhoneLoading] = useState(false);
  const [emailSending, setEmailSending] = useState(false);
  const [phoneSending, setPhoneSending] = useState(false);
  const navigate = useNavigate();
  const emailCountdown = useCountdown(60);
  const phoneCountdown = useCountdown(60);
  const [emailForm] = Form.useForm();
  const [phoneForm] = Form.useForm();

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

  const onEmailRegister = async (values: { email: string; username: string; password: string; code: string }) => {
    setEmailLoading(true);
    try {
      await authApi.registerWithEmailCode(values.email, values.username, values.password, values.code);
      message.success('注册成功');
      navigate('/login');
    } catch (err: any) {
      message.error(err.response?.data?.detail || '注册失败');
    } finally {
      setEmailLoading(false);
    }
  };

  const onPhoneRegister = async (values: { phone: string; username: string; password: string; code: string }) => {
    setPhoneLoading(true);
    try {
      await authApi.registerWithPhoneCode(values.phone, values.username, values.password, values.code);
      message.success('注册成功');
      navigate('/login');
    } catch (err: any) {
      message.error(err.response?.data?.detail || '注册失败');
    } finally {
      setPhoneLoading(false);
    }
  };

  const codeInput = (countdown: ReturnType<typeof useCountdown>, sending: boolean, onSend: () => void) => (
    <Input
      prefix={<SafetyOutlined />}
      placeholder="验证码"
      suffix={
        <Button
          type="link"
          size="small"
          disabled={countdown.isCounting}
          loading={sending}
          onClick={onSend}
          style={{ padding: 0 }}
        >
          {countdown.isCounting ? `${countdown.countdown}秒后重发` : '发送验证码'}
        </Button>
      }
    />
  );

  const passwordRules = [
    { required: true, message: '请输入密码' },
    { min: 8, message: '密码长度不少于8位' },
  ];

  const confirmPasswordRules = (formInstance: ReturnType<typeof Form.useForm>[0]) => [
    { required: true, message: '请确认密码' },
    {
      validator(_: any, value: string) {
        if (!value || formInstance.getFieldValue('password') === value) {
          return Promise.resolve();
        }
        return Promise.reject(new Error('两次密码输入不一致'));
      },
    },
  ];

  const tabItems = [
    {
      key: 'email',
      label: '邮箱注册',
      children: (
        <Form form={emailForm} onFinish={onEmailRegister} size="large">
          <Form.Item
            name="email"
            rules={[
              { required: true, message: '请输入邮箱' },
              { type: 'email', message: '请输入有效的邮箱地址' },
            ]}
          >
            <Input prefix={<MailOutlined />} placeholder="邮箱" />
          </Form.Item>
          <Form.Item name="username" rules={[{ required: true, message: '请输入用户名' }]}>
            <Input prefix={<UserOutlined />} placeholder="用户名" />
          </Form.Item>
          <Form.Item name="password" rules={passwordRules}>
            <Input.Password prefix={<LockOutlined />} placeholder="密码" />
          </Form.Item>
          <Form.Item name="confirmPassword" dependencies={['password']} rules={confirmPasswordRules(emailForm)}>
            <Input.Password prefix={<LockOutlined />} placeholder="确认密码" />
          </Form.Item>
          <Form.Item name="code" rules={[{ required: true, message: '请输入验证码' }]}>
            {codeInput(emailCountdown, emailSending, handleSendEmailCode)}
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={emailLoading} block>
              注册
            </Button>
          </Form.Item>
        </Form>
      ),
    },
    {
      key: 'phone',
      label: '手机注册',
      children: (
        <Form form={phoneForm} onFinish={onPhoneRegister} size="large">
          <Form.Item
            name="phone"
            rules={[
              { required: true, message: '请输入手机号' },
              { pattern: /^1\d{10}$/, message: '请输入有效的手机号' },
            ]}
          >
            <Input prefix={<PhoneOutlined />} placeholder="手机号" />
          </Form.Item>
          <Form.Item name="username" rules={[{ required: true, message: '请输入用户名' }]}>
            <Input prefix={<UserOutlined />} placeholder="用户名" />
          </Form.Item>
          <Form.Item name="password" rules={passwordRules}>
            <Input.Password prefix={<LockOutlined />} placeholder="密码" />
          </Form.Item>
          <Form.Item name="confirmPassword" dependencies={['password']} rules={confirmPasswordRules(phoneForm)}>
            <Input.Password prefix={<LockOutlined />} placeholder="确认密码" />
          </Form.Item>
          <Form.Item name="code" rules={[{ required: true, message: '请输入验证码' }]}>
            {codeInput(phoneCountdown, phoneSending, handleSendSmsCode)}
          </Form.Item>
          <Form.Item>
            <Button type="primary" htmlType="submit" loading={phoneLoading} block>
              注册
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
          注册账号
        </Title>
        <Tabs defaultActiveKey="email" items={tabItems} centered />
        <div style={{ textAlign: 'center', marginTop: 8 }}>
          <Link to="/login">已有账号？立即登录</Link>
        </div>
      </Card>
    </div>
  );
}
