import React, { useEffect } from 'react';
import { Form, Switch, Input, Space } from 'antd';
import type { FormInstance } from 'antd';
import type { LoginMethodConfig } from './types';
import { METHOD_LABELS, OAUTH_METHODS, ALL_LOGIN_METHODS } from './types';

export interface LoginMethodsStepProps {
  data: LoginMethodConfig[];
  onChange: (data: LoginMethodConfig[]) => void;
  formRef: React.RefObject<FormInstance>;
}

const LoginMethodsStep: React.FC<LoginMethodsStepProps> = ({ data, onChange, formRef }) => {
  const [form] = Form.useForm();

  useEffect(() => {
    if (formRef && 'current' in formRef) {
      (formRef as React.MutableRefObject<FormInstance>).current = form;
    }
  }, [form, formRef]);

  useEffect(() => {
    const values: Record<string, unknown> = {};
    data.forEach((item) => {
      values[`${item.method}_enabled`] = item.is_enabled;
      values[`${item.method}_client_id`] = item.client_id;
      values[`${item.method}_client_secret`] = item.client_secret;
    });
    form.setFieldsValue(values);
  }, [data, form]);

  const findMethod = (method: string) => data.find((m) => m.method === method);

  const updateMethod = (method: string, patch: Partial<LoginMethodConfig>) => {
    const updated = data.map((m) => (m.method === method ? { ...m, ...patch } : m));
    onChange(updated);
  };

  const handleToggle = (method: string, checked: boolean) => {
    const patch: Partial<LoginMethodConfig> = { is_enabled: checked };
    if (!checked && OAUTH_METHODS.has(method)) {
      // Clear validation errors when disabling
      form.setFields([
        { name: `${method}_client_id`, errors: [] },
      ]);
    }
    updateMethod(method, patch);
  };

  return (
    <Form
      form={form}
      layout="vertical"
      validateTrigger={[]}
    >
      <Space direction="vertical" style={{ width: '100%' }} size="middle">
        {ALL_LOGIN_METHODS.map((method) => {
          const config = findMethod(method);
          const isEnabled = config?.is_enabled ?? false;
          const isOAuth = OAUTH_METHODS.has(method);

          return (
            <div key={method}>
              <Form.Item
                name={`${method}_enabled`}
                valuePropName="checked"
                style={{ marginBottom: isEnabled && isOAuth ? 8 : 0 }}
              >
                <Switch
                  checked={isEnabled}
                  onChange={(checked) => handleToggle(method, checked)}
                />
                <span style={{ marginLeft: 8 }}>{METHOD_LABELS[method]}</span>
              </Form.Item>

              {isOAuth && isEnabled && (
                <>
                  <Form.Item
                    name={`${method}_client_id`}
                    label="Client ID"
                    rules={[{ required: true, message: `请输入${METHOD_LABELS[method]}的 Client ID` }]}
                    style={{ marginBottom: 8 }}
                  >
                    <Input
                      placeholder="请输入 Client ID"
                      onChange={(e) => updateMethod(method, { client_id: e.target.value })}
                    />
                  </Form.Item>
                  <Form.Item
                    name={`${method}_client_secret`}
                    label="Client Secret"
                    style={{ marginBottom: 0 }}
                  >
                    <Input.Password
                      placeholder="请输入 Client Secret（可选）"
                      onChange={(e) => updateMethod(method, { client_secret: e.target.value })}
                    />
                  </Form.Item>
                </>
              )}
            </div>
          );
        })}
      </Space>
    </Form>
  );
};

export default LoginMethodsStep;
