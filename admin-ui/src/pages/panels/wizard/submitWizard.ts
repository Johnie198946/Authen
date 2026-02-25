import { applicationApi } from '../../../api/services';
import type { WizardData } from './types';

export interface SubmitResult {
  appId: string;
  appSecret: string;
  warning?: string;
}

/**
 * Orchestrates the sequential API calls to create and configure an application.
 *
 * 1. Create application → get app_id & app_secret
 * 2. Configure login methods
 * 3. Configure scopes
 * 4. Conditionally update rate_limit (only if ≠ 60)
 * 5. Configure organization bindings
 * 6. Configure subscription plan binding
 *
 * On create failure: throws the error (caller handles display).
 * On post-create failure: returns result with warning flag.
 */
export async function submitWizard(
  data: WizardData,
  userId: string
): Promise<SubmitResult> {
  // Step 1: Create the application
  let appId: string;
  let appSecret: string;

  try {
    const createRes = await applicationApi.create(
      { name: data.basicInfo.name, description: data.basicInfo.description || undefined },
      userId
    );
    appId = createRes.data.app_id;
    appSecret = createRes.data.app_secret;
  } catch (err: any) {
    if (err.message?.includes('Network Error')) {
      throw new Error('网络连接异常，请检查网络后重试');
    }
    const backendMsg = err.response?.data?.detail;
    throw new Error(backendMsg || err.message || '创建应用失败');
  }

  // Steps 2-6: Post-create configuration (failures return warning, not throw)
  try {
    await applicationApi.updateLoginMethods(
      appId,
      { login_methods: data.loginMethods },
      userId
    );

    await applicationApi.updateScopes(
      appId,
      { scopes: data.scopes },
      userId
    );

    if (data.rateLimit !== 60) {
      await applicationApi.update(
        appId,
        { rate_limit: data.rateLimit },
        userId
      );
    }

    if (data.organizations.length > 0) {
      await applicationApi.updateOrganizations(
        appId,
        { organization_ids: data.organizations },
        userId
      );
    }

    if (data.subscriptionPlanId) {
      await applicationApi.updateSubscriptionPlan(
        appId,
        { plan_id: data.subscriptionPlanId },
        userId
      );
    }

    // Auto-provision configuration
    if (data.autoProvision.enabled) {
      await applicationApi.updateAutoProvision(
        appId,
        {
          is_enabled: true,
          role_ids: data.autoProvision.roleIds,
          permission_ids: data.autoProvision.permissionIds,
          organization_id: data.autoProvision.organizationId,
          subscription_plan_id: data.autoProvision.subscriptionPlanId,
        },
        userId
      );
    }
  } catch (err: any) {
    return {
      appId,
      appSecret,
      warning: '应用已创建，但部分配置未成功，请前往详情页手动完成配置',
    };
  }

  return { appId, appSecret };
}
