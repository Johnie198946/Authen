# Implementation Plan: 应用配置向导 (App Config Wizard)

## Overview

将 `ApplicationsPanel.tsx` 中的简单"新建应用"弹窗替换为五步向导（Drawer 形式），依次完成基本信息、登录方式、权限范围、限流配置、确认创建。使用 React + TypeScript + Ant Design 6.3.0 实现，Vitest + React Testing Library + fast-check 进行测试。

## Tasks

- [x] 1. Set up testing infrastructure and shared types
  - [x] 1.1 Install test dependencies and configure Vitest
    - Add `vitest`, `@testing-library/react`, `@testing-library/jest-dom`, `@testing-library/user-event`, `fast-check`, `jsdom` as devDependencies in `admin-ui/package.json`
    - Create `admin-ui/vitest.config.ts` with jsdom environment and React plugin
    - Add `"test": "vitest --run"` script to `package.json`
    - _Requirements: N/A (infrastructure)_

  - [x] 1.2 Create shared types and constants file
    - Create `admin-ui/src/pages/panels/wizard/types.ts`
    - Define `LoginMethodConfig`, `WizardData`, `WizardStep` interfaces
    - Define `INITIAL_WIZARD_DATA`, `WIZARD_STEPS`, `ALL_LOGIN_METHODS`, `OAUTH_METHODS`, `ALL_SCOPES`, `METHOD_LABELS` constants
    - Extract these from the design document data model section
    - _Requirements: 2.1, 3.1, 4.1, 5.2_

- [x] 2. Implement step components
  - [x] 2.1 Implement BasicInfoStep component
    - Create `admin-ui/src/pages/panels/wizard/BasicInfoStep.tsx`
    - Render Ant Design Form with required name field and optional description field
    - Expose `formRef` for parent to trigger `validateFields()` on "下一步"
    - Name field: required, whitespace-only validation
    - _Requirements: 2.1, 2.2, 2.3, 2.4_

  - [ ]* 2.2 Write property test for BasicInfoStep validation
    - Create `admin-ui/src/__tests__/wizard/basicInfoStep.property.test.tsx`
    - **Property 2: 应用名称验证**
    - Use fast-check to generate arbitrary strings; verify empty/whitespace-only strings block next step, non-empty strings allow it
    - **Validates: Requirements 2.3, 2.4**

  - [x] 2.3 Implement LoginMethodsStep component
    - Create `admin-ui/src/pages/panels/wizard/LoginMethodsStep.tsx`
    - Render six login method Switch toggles with labels (reuse `METHOD_LABELS` from types)
    - Show/hide Client ID and Client Secret inputs when OAuth methods are toggled
    - Validate that enabled OAuth methods have non-empty Client ID on "下一步"
    - Allow proceeding with no methods enabled
    - _Requirements: 3.1, 3.2, 3.3, 3.4, 3.5_

  - [ ]* 2.4 Write property test for OAuth toggle visibility
    - Create `admin-ui/src/__tests__/wizard/loginMethodsStep.property.test.tsx`
    - **Property 3: OAuth 开关可见性联动**
    - Use fast-check to generate arbitrary OAuth method + enabled/disabled state; verify input area visibility matches enabled state
    - **Validates: Requirements 3.2, 3.3**

  - [ ]* 2.5 Write property test for OAuth Client ID validation
    - Add to `admin-ui/src/__tests__/wizard/loginMethodsStep.property.test.tsx`
    - **Property 4: OAuth Client ID 必填验证**
    - Use fast-check to generate enabled OAuth methods with empty Client ID; verify validation blocks next step
    - **Validates: Requirements 3.4**

  - [x] 2.6 Implement ScopesStep component
    - Create `admin-ui/src/pages/panels/wizard/ScopesStep.tsx`
    - Render Checkbox.Group with all eight scopes
    - Call `onChange` with selected scopes array
    - No required fields — allow proceeding with empty selection
    - _Requirements: 4.1, 4.2, 4.3_

  - [ ]* 2.7 Write property test for scopes selection sync
    - Create `admin-ui/src/__tests__/wizard/scopesStep.property.test.tsx`
    - **Property 5: 权限范围选择状态同步**
    - Use fast-check to generate arbitrary subsets of the 8 scopes; verify WizardData.scopes matches exactly
    - **Validates: Requirements 4.3**

  - [x] 2.8 Implement RateLimitStep component
    - Create `admin-ui/src/pages/panels/wizard/RateLimitStep.tsx`
    - Render InputNumber with min=1, max=100000, default=60
    - Expose `formRef` for parent validation
    - _Requirements: 5.1, 5.2, 5.3, 5.4_

  - [ ]* 2.9 Write property test for rate limit range validation
    - Create `admin-ui/src/__tests__/wizard/rateLimitStep.property.test.tsx`
    - **Property 6: 限流值范围验证**
    - Use fast-check to generate arbitrary integers; verify values in [1, 100000] are accepted, values outside are rejected
    - **Validates: Requirements 5.3, 5.4**

  - [x] 2.10 Implement ReviewStep component
    - Create `admin-ui/src/pages/panels/wizard/ReviewStep.tsx`
    - Read-only display of all WizardData fields
    - Show OAuth Client Secret masked (e.g., `****`)
    - Show "未配置" when no login methods enabled or no scopes selected
    - _Requirements: 6.1, 6.2, 6.3, 6.4_

  - [ ]* 2.11 Write property test for ReviewStep data completeness
    - Create `admin-ui/src/__tests__/wizard/reviewStep.property.test.tsx`
    - **Property 7: 确认步骤数据完整性**
    - Use fast-check to generate arbitrary valid WizardData; verify rendered output contains all expected fields
    - **Validates: Requirements 6.1, 6.2**

- [x] 3. Checkpoint - Ensure all step components work
  - Ensure all tests pass, ask the user if questions arise.

- [x] 4. Implement API orchestration and SecretDisplayModal
  - [x] 4.1 Implement submitWizard orchestration function
    - Create `admin-ui/src/pages/panels/wizard/submitWizard.ts`
    - Implement sequential API calls: create → updateLoginMethods → updateScopes → conditionally update rate_limit
    - Use `applicationApi` from `admin-ui/src/api/services.ts`
    - Return `{ appId, appSecret }` on success
    - Distinguish create failure vs. post-create configuration failure
    - On create failure: throw error with backend message
    - On post-create failure: return success result with warning flag
    - _Requirements: 8.1, 8.2, 8.3, 10.1, 10.2, 10.3_

  - [ ]* 4.2 Write property test for API orchestration
    - Create `admin-ui/src/__tests__/wizard/submitWizard.property.test.ts`
    - **Property 10: API 编排正确性**
    - Use fast-check to generate arbitrary valid WizardData; mock applicationApi; verify call order and that rate_limit API is called iff value ≠ 60
    - **Validates: Requirements 8.1, 8.2, 8.3**

  - [ ]* 4.3 Write property test for error message fidelity
    - Add to `admin-ui/src/__tests__/wizard/submitWizard.property.test.ts`
    - **Property 11: 错误信息展示保真**
    - Use fast-check to generate arbitrary error message strings; verify they are passed through unchanged
    - **Validates: Requirements 10.1, 10.2**

  - [x] 4.4 Implement SecretDisplayModal component
    - Create `admin-ui/src/pages/panels/wizard/SecretDisplayModal.tsx`
    - Display App ID and App Secret with copy buttons
    - Show warning: "请妥善保存以下密钥，关闭后将无法再次查看！"
    - "我已保存" button to close
    - _Requirements: 9.1, 9.2, 9.3, 9.4_

- [x] 5. Implement main wizard component and navigation
  - [x] 5.1 Implement AppConfigWizard main component
    - Create `admin-ui/src/pages/panels/wizard/AppConfigWizard.tsx`
    - Render Ant Design Drawer with Steps indicator
    - Manage `currentStep` and `wizardData` state (initialized from `INITIAL_WIZARD_DATA`)
    - Render the correct step component based on `currentStep`
    - Wire step data changes to `wizardData` state updates
    - Implement "上一步" / "下一步" / "确认创建" navigation buttons
    - Hide "上一步" on step 0, show "确认创建" on last step
    - Trigger form validation on "下一步" for steps with formRef
    - Allow clicking completed (previous) steps in the step indicator to jump back
    - Block clicking future steps in the step indicator
    - On close/cancel: reset all state to initial values
    - On submit: call `submitWizard`, handle loading state, handle errors
    - On success: call `onSuccess` with secret info, close drawer
    - On post-create config failure: show warning message, still call `onSuccess`
    - _Requirements: 1.1, 1.2, 1.3, 7.1, 7.2, 7.3, 7.4, 7.5, 7.6, 8.4, 8.5, 10.1, 10.2, 10.3_

  - [ ]* 5.2 Write property test for wizard state reset on close
    - Create `admin-ui/src/__tests__/wizard/appConfigWizard.property.test.tsx`
    - **Property 1: 关闭向导重置状态**
    - Use fast-check to generate arbitrary WizardData; simulate filling data then closing; verify state resets to INITIAL_WIZARD_DATA
    - **Validates: Requirements 1.3**

  - [ ]* 5.3 Write property test for step navigation state preservation
    - Add to `admin-ui/src/__tests__/wizard/appConfigWizard.property.test.tsx`
    - **Property 8: 步骤导航状态保持**
    - Use fast-check to generate arbitrary WizardData and step N > 0; simulate "上一步"; verify all data preserved
    - **Validates: Requirements 7.4, 7.5**

  - [ ]* 5.4 Write property test for step indicator navigation constraints
    - Add to `admin-ui/src/__tests__/wizard/appConfigWizard.property.test.tsx`
    - **Property 9: 步骤指示器导航约束**
    - Use fast-check to generate current step N and target step M; verify M < N allows jump, M > N blocks jump
    - **Validates: Requirements 7.6**

- [x] 6. Checkpoint - Ensure wizard component and navigation work
  - Ensure all tests pass, ask the user if questions arise.

- [x] 7. Integrate wizard into ApplicationsPanel
  - [x] 7.1 Replace simple create modal with wizard in ApplicationsPanel
    - Modify `admin-ui/src/pages/panels/ApplicationsPanel.tsx`
    - Remove the existing `createModal` state, `Form.useForm()`, `handleCreate`, and the simple `<Modal>` for creating apps
    - Add `wizardOpen` state and wire "新建应用" button to open `AppConfigWizard`
    - On wizard success: set `secretInfo`, open `SecretDisplayModal`, call `fetchApps()`
    - Replace the existing inline secret modal with the new `SecretDisplayModal` component
    - Import `AppConfigWizard` and `SecretDisplayModal` from `./wizard/`
    - _Requirements: 1.1, 8.5, 9.1_

  - [ ]* 7.2 Write unit tests for ApplicationsPanel integration
    - Create `admin-ui/src/__tests__/wizard/applicationsPanel.test.tsx`
    - Test: clicking "新建应用" opens the wizard Drawer
    - Test: wizard displays five step titles
    - Test: closing wizard resets state
    - _Requirements: 1.1, 1.2, 1.3_

- [x] 8. Final checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.

## Notes

- Tasks marked with `*` are optional and can be skipped for faster MVP
- The design uses TypeScript throughout — all implementation uses TypeScript + React + Ant Design 6.3.0
- All API endpoints already exist; no backend changes needed
- `applicationApi` in `admin-ui/src/api/services.ts` provides all required methods
- UI labels are in Chinese, consistent with the existing admin panel
- Property tests validate the 11 correctness properties defined in the design document
- Checkpoints ensure incremental validation at key milestones
