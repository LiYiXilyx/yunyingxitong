# T02 本地运行手册

## 平常使用

1. 启动Colima profile `project2`，再在项目根执行 `make up`。
2. `make status` 应显示三个服务healthy。用README里的本机入口访问。
3. `make test` 与 `scripts/verify-isolation.sh` 是本轮检查入口。业务巡检/派单尚未实现。
4. 不用时 `make down` 保留数据，再 `colima stop project2` 释放虚拟机内存。

## 配置与持久化

- `.local/secrets/deploy.env`：数据库、应用与初始管理员密码；0600，目录0700，Git忽略。
- `.local/secrets/wdt.env`：真实旺店通凭据的空白私有模板；目前不被服务读取。
- `.local/intake/`：用户填写资料和确认进度；不要把真实业务数据复制回仓库模板。
- Docker卷 `project2_postgres-data`、`project2_nocobase-storage` 位于Colima虚拟机。普通down、restart保留卷；删除profile/卷会丢数据，不能用来解决普通启动问题。
- 初次启动数据库时创建两个业务库并撤销PUBLIC连接权限。NocoBase和ops服务均使用非超级用户；跨库连接在数据库层拒绝。

## 故障检查

先用 `make status` 区分容器停止和健康失败。未启动虚拟机时不要改连接配置，先启动profile。数据库未ready时数据服务返回503，页面可用不代表ERP连接正常。

日志查看：`scripts/compose.sh logs --tail 100 服务名`。本轮脚本不打印秘密；未来加入外部API前仍需复核日志脱敏。`scripts/compose.sh config`会展开秘密，平常仅执行 `config --quiet`，不要复制配置输出到聊天。

插件代码变更后用 `scripts/compose.sh restart nocobase` 重新加载；官方CLI可能在日志报告启用失败却退出0，因此部署脚本还会通过实际HTTP资源检测，不能只看CLI退出码。插件联调完整检查为 `make test-plugin`。

`make verify-community`失败时保留现场，核对未知插件、版本漂移或运行清单查询失败；不要删除检查或直接把包名补进白名单。镜像版本、Docker摘要和社区政策应一同审查更新。

## 本轮不代表生产就绪

尚未建立远程TLS、备份恢复、可靠投递、按店权限、真实巡检/派单、Ego采集和故障补偿。页面里不配置真实运营流程。管理员仅限开发环境使用，不能作为全体运营共用账号。真实店铺接入按后续T03及之后里程碑逐项验收。
