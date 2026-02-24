import React, { useEffect } from 'react';
import { Form, InputNumber } from 'antd';
import type { FormInstance } from 'antd';

export interface RateLimitStepProps {
  data: number;
  onChange: (value: number) => void;
  formRef: React.RefObject<FormInstance>;
}

const RateLimitStep: React.FC<RateLimitStepProps> = ({ data, onChange, formRef }) => {
  const [form] = Form.useForm();

  useEffect(() => {
    if (formRef && 'current' in formRef) {
      (formRef as React.MutableRefObject<FormInstance>).current = form;
    }
  }, [form, formRef]);

  useEffect(() => {
    form.setFieldsValue({ rateLimit: data });
  }, [data, form]);

  const handleValuesChange = (_: unknown, allValues: { rateLimit: number }) => {
    if (allValues.rateLimit != null) {
      onChange(allValues.rateLimit);
    }
  };

  return (
    <Form form={form} layout="vertical" onValuesChange={handleValuesChange}>
      <Form.Item
        name="rateLimit"
        label="每分钟请求限制"
        rules={[
          { required: true, message: '请输入限流值' },
          {
            type: 'number',
            min: 1,
            max: 100000,
            message: '限流值必须在 1 到 100000 之间',
          },
        ]}
      >
        <InputNumber min={1} max={100000} style={{ width: '100%' }} />
      </Form.Item>
    </Form>
  );
};

export default RateLimitStep;
