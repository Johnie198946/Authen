import React, { useState, useRef, useCallback } from 'react';
import { Drawer, Steps, Button, Space, message } from 'antd';
import type { FormInstance } from 'antd';
import BasicInfoStep from './BasicInfoStep';
import LoginMethodsStep from './LoginMethodsStep';
import ScopesStep from './ScopesStep';
import RateLimitStep from './RateLimitStep';
import OrganizationStep from './OrganizationStep';
import SubscriptionStep from './SubscriptionStep';
import ReviewStep from './ReviewStep';
import { submitWizard } from './submitWizard';
import { INITIAL_WIZARD_DATA, WIZARD_STEPS } from './types';
import type { WizardData } from './types';

export interface AppConfigWizardProps {
  open: boolean;
  onClose: () => void;
  onSuccess: (secretInfo: { appId: string; appSecret: string }) => void;
  userId: string;
}

const LAST_STEP = WIZARD_STEPS.length - 1;

const AppConfigWizard: React.FC<AppConfigWizardProps> = ({ open, onClose, onSuccess, userId }) => {
  const [currentStep, setCurrentStep] = useState(0);
  const [wizardData, setWizardData] = useState<WizardData>({ ...INITIAL_WIZARD_DATA });
  const [loading, setLoading] = useState(false);

  const basicInfoFormRef = useRef<FormInstance>(null) as React.RefObject<FormInstance>;
  const loginMethodsFormRef = useRef<FormInstance>(null) as React.RefObject<FormInstance>;
  const rateLimitFormRef = useRef<FormInstance>(null) as React.RefObject<FormInstance>;

  const getFormRefForStep = useCallback((step: number): React.RefObject<FormInstance> | null => {
    switch (step) {
      case 0: return basicInfoFormRef;
      case 1: return loginMethodsFormRef;
      case 3: return rateLimitFormRef;
      default: return null;
    }
  }, []);

  const resetState = useCallback(() => {
    setCurrentStep(0);
    setWizardData({
      ...INITIAL_WIZARD_DATA,
      loginMethods: INITIAL_WIZARD_DATA.loginMethods.map((m) => ({ ...m })),
      scopes: [],
      organizations: [],
      subscriptionPlanId: '',
    });
    setLoading(false);
  }, []);

  const handleClose = useCallback(() => {
    resetState();
    onClose();
  }, [resetState, onClose]);

  const validateCurrentStep = async (): Promise<boolean> => {
    const formRef = getFormRefForStep(currentStep);
    if (!formRef?.current) return true;
    try {
      await formRef.current.validateFields();
      return true;
    } catch {
      return false;
    }
  };

  const handleNext = async () => {
    const valid = await validateCurrentStep();
    if (valid) {
      setCurrentStep((prev) => Math.min(prev + 1, LAST_STEP));
    }
  };

  const handlePrev = () => {
    setCurrentStep((prev) => Math.max(prev - 1, 0));
  };

  const handleSubmit = async () => {
    setLoading(true);
    try {
      const result = await submitWizard(wizardData, userId);
      if (result.warning) {
        message.warning(result.warning);
      }
      onSuccess({ appId: result.appId, appSecret: result.appSecret });
      resetState();
      onClose();
    } catch (err: any) {
      message.error(err.message || '创建应用失败');
    } finally {
      setLoading(false);
    }
  };

  const handleStepClick = (step: number) => {
    if (step < currentStep) {
      setCurrentStep(step);
    }
  };

  const renderStepContent = () => {
    switch (currentStep) {
      case 0:
        return (
          <BasicInfoStep
            data={wizardData.basicInfo}
            onChange={(basicInfo) => setWizardData((prev) => ({ ...prev, basicInfo }))}
            formRef={basicInfoFormRef}
          />
        );
      case 1:
        return (
          <LoginMethodsStep
            data={wizardData.loginMethods}
            onChange={(loginMethods) => setWizardData((prev) => ({ ...prev, loginMethods }))}
            formRef={loginMethodsFormRef}
          />
        );
      case 2:
        return (
          <ScopesStep
            data={wizardData.scopes}
            onChange={(scopes) => setWizardData((prev) => ({ ...prev, scopes }))}
          />
        );
      case 3:
        return (
          <RateLimitStep
            data={wizardData.rateLimit}
            onChange={(rateLimit) => setWizardData((prev) => ({ ...prev, rateLimit }))}
            formRef={rateLimitFormRef}
          />
        );
      case 4:
        return (
          <OrganizationStep
            data={wizardData.organizations}
            onChange={(organizations) => setWizardData((prev) => ({ ...prev, organizations }))}
          />
        );
      case 5:
        return (
          <SubscriptionStep
            data={wizardData.subscriptionPlanId}
            onChange={(subscriptionPlanId) => setWizardData((prev) => ({ ...prev, subscriptionPlanId }))}
          />
        );
      case 6:
        return <ReviewStep wizardData={wizardData} />;
      default:
        return null;
    }
  };

  const stepsItems = WIZARD_STEPS.map((step, index) => ({
    title: step.title,
    disabled: index > currentStep,
    style: index < currentStep ? { cursor: 'pointer' } : undefined,
  }));

  return (
    <Drawer
      title="新建应用"
      open={open}
      onClose={handleClose}
      width={720}
      destroyOnClose
      footer={
        <div style={{ display: 'flex', justifyContent: 'flex-end' }}>
          <Space>
            {currentStep > 0 && (
              <Button onClick={handlePrev}>上一步</Button>
            )}
            {currentStep < LAST_STEP && (
              <Button type="primary" onClick={handleNext}>下一步</Button>
            )}
            {currentStep === LAST_STEP && (
              <Button type="primary" loading={loading} onClick={handleSubmit}>
                确认创建
              </Button>
            )}
          </Space>
        </div>
      }
    >
      <Steps
        current={currentStep}
        items={stepsItems}
        onChange={handleStepClick}
        style={{ marginBottom: 24 }}
        size="small"
      />
      {renderStepContent()}
    </Drawer>
  );
};

export default AppConfigWizard;
