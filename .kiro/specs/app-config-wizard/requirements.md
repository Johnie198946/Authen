# 需求文档：应用配置向导 (App Config Wizard)

## 简介

当前管理后台创建应用时仅收集名称和描述，用户需要在创建后进入详情页分别配置登录方式、权限范围和限流策略，每项配置都需要单独保存。本功能将"新建应用"流程替换为一站式多步向导（Step Wizard），在一个流程中完成所有配置，最终一次性提交创建。

## 术语表

- **Wizard（向导）**: 多步骤表单组件，引导用户按顺序完成应用创建的全部配置
- **Step_Indicator（步骤指示器）**: 向导顶部的步骤条，展示当前所处步骤及整体进度
- **Basic_Info_Step（基本信息步骤）**: 向导第一步，收集应用名称和描述
- **Login_Methods_Step（登录方式步骤）**: 向导第二步，配置应用支持的登录方式
- **OAuth_Method（OAuth 登录方式）**: 需要提供 Client ID 和 Client Secret 的第三方社交登录方式（微信、支付宝、Google、Apple）
- **Scopes_Step（权限范围步骤）**: 向导第三步，选择应用可访问的 API 权限范围
- **Rate_Limit_Step（限流配置步骤）**: 向导第四步，设置应用的请求频率限制
- **Review_Step（确认步骤）**: 向导第五步，展示所有配置的汇总信息供用户确认
- **Wizard_State（向导状态）**: 向导内部维护的包含所有步骤数据的聚合状态对象
- **Secret_Display（密钥展示）**: 创建成功后展示 App ID 和 App Secret 的界面

## 需求

### 需求 1：向导入口替换

**用户故事：** 作为管理员，我希望点击"新建应用"按钮后打开多步向导而非简单弹窗，以便在一个流程中完成所有配置。

#### 验收标准

1. WHEN 用户点击"新建应用"按钮, THE Wizard SHALL 以抽屉（Drawer）或模态框（Modal）形式打开，替代当前仅包含名称和描述的简单弹窗
2. WHEN Wizard 打开时, THE Step_Indicator SHALL 展示全部五个步骤的标题，并高亮当前步骤
3. WHEN 用户关闭 Wizard（点击取消或关闭按钮）, THE Wizard SHALL 清空所有已填写的数据并关闭

### 需求 2：基本信息步骤

**用户故事：** 作为管理员，我希望在向导第一步填写应用名称和描述，以便定义应用的基本信息。

#### 验收标准

1. THE Basic_Info_Step SHALL 提供应用名称输入框和应用描述输入框
2. THE Basic_Info_Step SHALL 将应用名称标记为必填项
3. WHEN 用户未填写应用名称并尝试进入下一步, THE Basic_Info_Step SHALL 展示验证错误提示并阻止步骤跳转
4. WHEN 用户填写了有效的应用名称, THE Wizard SHALL 允许用户进入下一步

### 需求 3：登录方式配置步骤

**用户故事：** 作为管理员，我希望在向导第二步配置应用支持的登录方式，以便控制终端用户的认证渠道。

#### 验收标准

1. THE Login_Methods_Step SHALL 展示以下六种登录方式的开关控件：邮箱登录、手机登录、微信登录、支付宝登录、Google 登录、Apple 登录
2. WHEN 用户启用一个 OAuth_Method, THE Login_Methods_Step SHALL 展开该方式的 Client ID 和 Client Secret 输入区域
3. WHEN 用户禁用一个已启用的 OAuth_Method, THE Login_Methods_Step SHALL 收起该方式的 OAuth 配置输入区域
4. WHEN 用户启用一个 OAuth_Method 但未填写 Client ID 并尝试进入下一步, THE Login_Methods_Step SHALL 展示验证错误提示并阻止步骤跳转
5. THE Login_Methods_Step SHALL 允许用户不启用任何登录方式直接进入下一步（登录方式为可选配置）

### 需求 4：权限范围配置步骤

**用户故事：** 作为管理员，我希望在向导第三步选择应用可访问的 API 权限范围，以便实施最小权限原则。

#### 验收标准

1. THE Scopes_Step SHALL 以复选框组形式展示以下八个权限范围：user:read、user:write、auth:login、auth:register、role:read、role:write、org:read、org:write
2. THE Scopes_Step SHALL 允许用户不选择任何权限范围直接进入下一步（权限范围为可选配置）
3. WHEN 用户勾选或取消勾选权限范围, THE Wizard_State SHALL 实时更新已选择的权限范围列表

### 需求 5：限流配置步骤

**用户故事：** 作为管理员，我希望在向导第四步设置应用的请求频率限制，以便保护后端服务不被过度调用。

#### 验收标准

1. THE Rate_Limit_Step SHALL 提供一个数值输入控件用于设置每分钟请求限制
2. THE Rate_Limit_Step SHALL 将默认值设为 60 次/分钟
3. THE Rate_Limit_Step SHALL 将输入范围限制在 1 至 100000 之间
4. WHEN 用户输入的值超出有效范围, THE Rate_Limit_Step SHALL 展示验证错误提示并阻止步骤跳转

### 需求 6：确认与汇总步骤

**用户故事：** 作为管理员，我希望在最终提交前查看所有配置的汇总信息，以便确认无误后再创建应用。

#### 验收标准

1. THE Review_Step SHALL 以只读方式展示以下信息：应用名称、应用描述、已启用的登录方式列表、已选择的权限范围列表、限流配置值
2. WHEN 已启用的登录方式中包含 OAuth_Method, THE Review_Step SHALL 展示该方式的 Client ID（Client Secret 以掩码形式展示）
3. WHEN 用户未配置任何登录方式, THE Review_Step SHALL 在登录方式区域展示"未配置"提示
4. WHEN 用户未选择任何权限范围, THE Review_Step SHALL 在权限范围区域展示"未配置"提示

### 需求 7：步骤导航

**用户故事：** 作为管理员，我希望在向导中自由地前进和后退，以便在提交前修改任意步骤的配置。

#### 验收标准

1. THE Wizard SHALL 在每个步骤底部提供"上一步"和"下一步"按钮
2. WHEN 用户处于第一步, THE Wizard SHALL 隐藏"上一步"按钮
3. WHEN 用户处于最后一步, THE Wizard SHALL 将"下一步"按钮替换为"确认创建"按钮
4. WHEN 用户点击"上一步"按钮, THE Wizard SHALL 返回上一步骤并保留该步骤之前填写的所有数据
5. WHEN 用户从后续步骤返回到之前的步骤, THE Wizard_State SHALL 保留所有步骤已填写的数据不丢失
6. THE Step_Indicator SHALL 允许用户点击已完成的步骤直接跳转（仅限当前步骤之前的步骤）

### 需求 8：提交与 API 调用编排

**用户故事：** 作为管理员，我希望点击"确认创建"后系统自动按顺序调用所有必要的 API，以便一次性完成应用的创建和配置。

#### 验收标准

1. WHEN 用户点击"确认创建"按钮, THE Wizard SHALL 首先调用创建应用 API（POST /admin/applications）
2. WHEN 应用创建成功, THE Wizard SHALL 依次调用登录方式配置 API（PUT /admin/applications/{app_id}/login-methods）和权限范围配置 API（PUT /admin/applications/{app_id}/scopes）
3. WHEN 用户设置了非默认的限流值, THE Wizard SHALL 调用更新应用 API（PUT /admin/applications/{app_id}）以保存限流配置
4. WHILE API 调用正在执行, THE Wizard SHALL 展示加载状态并禁用"确认创建"按钮，防止重复提交
5. WHEN 所有 API 调用均成功完成, THE Wizard SHALL 关闭向导并刷新应用列表

### 需求 9：密钥展示

**用户故事：** 作为管理员，我希望在应用创建成功后看到 App Secret，以便安全地保存凭证。

#### 验收标准

1. WHEN 所有 API 调用均成功完成, THE Secret_Display SHALL 以模态框形式展示 App ID 和 App Secret
2. THE Secret_Display SHALL 展示警告信息，告知用户密钥仅展示一次
3. THE Secret_Display SHALL 为 App ID 和 App Secret 提供一键复制功能
4. WHEN 用户点击"我已保存"按钮, THE Secret_Display SHALL 关闭模态框

### 需求 10：错误处理

**用户故事：** 作为管理员，我希望在创建过程中遇到错误时获得清晰的反馈，以便了解问题并采取措施。

#### 验收标准

1. IF 创建应用 API 调用失败, THEN THE Wizard SHALL 展示后端返回的错误信息并保持向导打开状态，允许用户修改后重试
2. IF 应用创建成功但后续配置 API 调用失败, THEN THE Wizard SHALL 展示错误信息，告知用户应用已创建但部分配置未成功，并提示用户前往详情页手动完成配置
3. IF 网络连接中断, THEN THE Wizard SHALL 展示网络错误提示信息
