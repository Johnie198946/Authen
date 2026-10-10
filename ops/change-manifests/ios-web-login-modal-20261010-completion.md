# Authen App网页登录

task_id: ios-web-login-modal-20261010
status: TESTED
branch: codex/ios-web-login-modal-20261010
worktree: /Users/dengzhaoyu/Desktop/TepVis/.worktrees/authen-app-login-20261010
head/local_commit: 132ea99883b8560f0890dd7267a13833e6bedf62（基线）
remote_sha: 未推送
server_before: auth/main.py sha256 3ba881ca2e133044b12dbec6c66ff6e06bb21b9d2ac6fe1196ec39d20597d8cf; api_logger.py 4502510137bf11e3415aba125c45d240d3ada76acd8488194bbb5d89b1b8847f; authen@auth active
server_after: 未部署
health_check: 未部署，不适用
functional_check: 32项真实Redis/SQLite认证、JWT、刷新、日志、短信回归通过；真实隔离网页/Quantum/iOS联调确认和取消成功
rollback_point: 尚未部署，待备份现有两文件
manifest: ops/change-manifests/ios-web-login-modal-20261010-completion.md
remaining_risks: 生产发布待完成，JWT沿现有15分钟策略

开工前完整Git盘点见ops/acceptance/ios-web-login-modal-20261010/git-inventory.json。origin/main源码指纹与生产完全一致；未使用旧UserAuthen副本。用户已授权完成开发和提交/推送/部署。本次沿现有auth/main.py+Redis实现app-login，无新服务/表/依赖：校验本人原Authen访问令牌、账号active/锁定、归属、期限及六位码；Lua原子确认/一次性兑换，已完成请求从pending索引移除，取消与确认互斥，未知账号返回同样请求形态并限流；沿原SSO/JWT创建会话。共享日志屏蔽state/ticket/code。

变更文件：services/auth/main.py、shared/middleware/api_logger.py、tests/test_app_login.py、tests/test_api_logging.py、tests/test_token_refresh.py和本任务ops记录。两个旧测试修复仅调整日志数据库fixture、UTC时间比较，使测试正确指向隔离库和JWT UTC时间。

命令：JWT_SECRET_KEY=isolated-test-secret /private/tmp/quansyn-venv/bin/python -m pytest tests/test_app_login.py tests/test_phone_code_login.py tests/test_jwt_tokens.py tests/test_token_refresh.py tests/test_api_logging.py -q
结果：32 passed，旧python-jose UTC弃用警告未改变依赖。

生产未变更，不宣称上线。部署使用GitHub已核验SHA，先备份原文件，检查源指纹未变化，然后更新两个Python文件并重启现有authen@auth服务；失败恢复备份。JWT代码、凭证配置和数据库结构不修改。
