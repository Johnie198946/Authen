# Authen App网页登录

task_id: ios-web-login-modal-20261010
status: DEPLOYED
branch: codex/ios-web-login-modal-20261010
worktree: /Users/dengzhaoyu/Desktop/TepVis/.worktrees/authen-app-login-20261010
head/local_commit: dd981f8ab5efab53b182f4a1c7858cab6eb2d4f8（部署代码）
remote_sha: dd981f8ab5efab53b182f4a1c7858cab6eb2d4f8；git ls-remote origin refs/heads/codex/ios-web-login-modal-20261010 已核对
server_before: auth/main.py sha256 3ba881ca2e133044b12dbec6c66ff6e06bb21b9d2ac6fe1196ec39d20597d8cf; api_logger.py 4502510137bf11e3415aba125c45d240d3ada76acd8488194bbb5d89b1b8847f; authen@auth active
server_after: /opt/authen/.app-login-deployed-sha=dd981f8ab5efab53b182f4a1c7858cab6eb2d4f8；auth/main.py sha256 ad38f6d720aa7391e1d82130cf93a41dd86cb18de60ae21c0c98b70e252b23a5；api_logger.py 3e8c3a7691aded2f6c2a374eb03c1927deaa5bf583e5fa6586375e39fe9b98cc
health_check: authen@auth.service active；127.0.0.1:8001/health HTTP200
functional_check: 32项真实Redis/SQLite认证、JWT、刷新、日志、短信回归通过；真实隔离网页/Quantum/iOS联调确认和取消成功
rollback_point: /opt/ai-lab-shared/rollbacks/authen-app-login-20261010.n0uOAS
manifest: ops/change-manifests/ios-web-login-modal-20261010-completion.md
remaining_risks: 真实正式账号的App确认+网页跳转待最终验收；JWT沿现有15分钟策略

开工前完整Git盘点见ops/acceptance/ios-web-login-modal-20261010/git-inventory.json。origin/main源码指纹与生产完全一致；未使用旧UserAuthen副本。用户已授权完成开发和提交/推送/部署。本次沿现有auth/main.py+Redis实现app-login，无新服务/表/依赖：校验本人原Authen访问令牌、账号active/锁定、归属、期限及六位码；Lua原子确认/一次性兑换，已完成请求从pending索引移除，取消与确认互斥，未知账号返回同样请求形态并限流；沿原SSO/JWT创建会话。共享日志屏蔽state/ticket/code。

变更文件：services/auth/main.py、shared/middleware/api_logger.py、tests/test_app_login.py、tests/test_api_logging.py、tests/test_token_refresh.py和本任务ops记录。两个旧测试修复仅调整日志数据库fixture、UTC时间比较，使测试正确指向隔离库和JWT UTC时间。

命令：JWT_SECRET_KEY=isolated-test-secret /private/tmp/quansyn-venv/bin/python -m pytest tests/test_app_login.py tests/test_phone_code_login.py tests/test_jwt_tokens.py tests/test_token_refresh.py tests/test_api_logging.py -q
结果：32 passed，旧python-jose UTC弃用警告未改变依赖。

已按核验SHA部署：备份原文件并核对指纹后更新两个Python文件，编译校验并重启现有authen@auth服务。生产新增API存在、未知state返回410；完整真实正式账号联调仍待验收。回滚恢复上述备份两文件并重启服务。JWT代码、凭证配置和数据库结构不修改。
