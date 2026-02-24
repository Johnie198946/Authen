import React, { useEffect } from 'react';
import { Form, Input } from 'antd';
import type { FormInstance } from 'antd';

export interface BasicInfoStepProps {
  data: { name: string; description: string };
  onChange: (data: { name: string; description: string }) => void;
  formRef: React.RefObject<FormInstance>;
}

const BasicInfoStep: React.FC<BasicInfoStepProps> = ({ data, onChange, formRef }) => {
  const [form] = Form.useForm();

  useEffect(() => {
    if (formRef && 'current' in formRef) {
      (formRef as React.MutableRefObject<FormInstance>).current = form;
    }
  }, [form, formRef]);

  useEffect(() => {
    form.setFieldsValue(data);
  }, [data, form]);

  const handleValuesChange = (_: unknown, allValues: { name: string; description: string }) => {
    onChange({ name: allValues.name || '', description: allValues.description || '' });
  };

  return (
    <Form form={form} layout="vertical" onValuesChange={handleValuesChange}>
      <Form.Item
        name="name"
        label="应用名称"
        rules={[
          { required: true, message: '请输入应用名称' },
          {
            validator: (_, value) => {
              if (value && value.trim().length === 0) {
                return Promise.reject(new Error('应用名称不能为纯空白字符'));
              }
              return Promise.resolve();
            },
          },
        ]}
      >
        <Input placeholder="请输入应用名称" />
      </Form.Item>
      <Form.Item name="description" label="应用描述">
        <Input.TextArea placeholder="请输入应用描述（可选）" rows={3} />
      </Form.Item>
    </Form>
  );
};

export default BasicInfoStep;
