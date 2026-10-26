# 项目2：运营巡检与任务分发

当前提供 **T02 本地开发基础、T03 合成数据工作台、T04 旺店通只读连接器工程和 T05 数据入库与健康接收工程**。T05 已实现标准化、持久批次与指标、健康摘要接收及纯对账，可进行手动合成演练。**2026-10-26：T04/T05 整体验收仍为 partial**，真实资料未齐，尚未完成两店 28 个完整业务日回补及 20 单、10 SKU、退款和日汇总对账。定时 worker 与真实端到端适配尚未装配，真实数据投递未启用，没有真实巡检或经营派单；后续经营任务处理、证据和复查尚未实现。

## 本机入口

- NocoBase：<http://127.0.0.1:13000>
- 数据服务就绪检查：<http://127.0.0.1:18000/health/ready>
- 管理员邮箱：`owner@project2.local`。随机密码位于 `.local/secrets/deploy.env` 的 `INIT_ROOT_PASSWORD`，不要发送到聊天或提交Git。
- T03主管、A店运营、B店运营、集成账号保存在本机 `.local/secrets/t03-accounts.json`（权限0600），用账号文件里的邮箱和密码登录。该文件仅用于本地合成验收，不在仓库和聊天中展示密码。

登录后从左侧进入“我的任务”“异常中心”“数据健康”“管理设置”。任务详情中的事件时间线只读；状态、负责人、规则和权限的普通表格写入已关闭。

| 角色 | T03业务范围 |
|---|---|
| 管理员 | 维护合成店铺、成员、仓库范围和默认负责人；发布/启停合成规则 |
| 主管 | 查看授权店铺及共享仓库；在授权范围发布/启停规则；配置只读 |
| 运营 | 查看本人负责且拥有店铺/仓库范围的任务；无规则发布和人员配置权限 |
| 集成账号 | 仅有授权业务读取范围；无业务页面菜单和规则/配置写入口；可按授权范围接收数据健康命令；HTTP经营派单尚未实现 |

菜单可见不代表数据授权。后端每次请求重新核对角色与有效成员关系；A店运营不能读取B店任务，共仓任务还需要独立仓库授权。

仅绑定本机环回地址。PostgreSQL没有宿主机端口；两个逻辑库由独立非超级用户连接。Colima项目配置为4核/6GB内存/30GB磁盘，使用独立context `colima-project2`，未改系统默认Docker context。

## 运行与停止

本机已安装 Colima、Docker CLI、Compose。首次在其他Mac复现需先安装这些工具，且安装 Python 3.13 和 Node 26.0.0。

```sh
# 若虚拟机停止，先启动。按实际仓库路径替换 mount。
colima start project2 --cpus 4 --memory 6 --disk 30 --vm-type vz --runtime docker --activate=false --mount "$PWD:w"
make bootstrap
make setup-dev
make setup-t03
make setup-wdt
make setup-t05
make status
make test

# 停止容器但保留数据卷；需要时再 make up
make down
# 也可进一步停止虚拟机以释放内存
colima stop project2
```

`make bootstrap` 只生成/保留本地配置；重复执行不会更换已有密码。`make setup-dev` 安装锁定的本地测试依赖。`make setup-t03` 构建客户端、启动服务并核验插件，准备合成账号和数据、修复合成事件引用、配置自有四个页面；重复执行保留账号密码及现有页面布局。`make up` 仅启动服务并核验插件，已有T03环境日常重启可直接使用。Linux服务器需按部署环境配置Docker与 `PROJECT2_DOCKER_CONTEXT`，本轮没有部署远程服务器。

`make setup-wdt` 重建并启动 ops-data，仅用其应用账号在自己的 ops 数据库创建共享限流表，可重复执行并保留记录；不连接 ERP。代码变更后先执行此命令，确保容器测试使用当前代码。T04 的命令、接口和真实联调条件见 [T04 验收记录](docs/t04-acceptance.md)。

`make setup-t05` 准备 T05 内部库迁移；`make demo-t05` 执行手动合成批次、指标和健康投递演练。健康命令接收端为 NocoBase（13000）的 `POST /api/opsDataHealth:ingest`，当前演练仅用 synthetic 来源。命令不会装配定时采集 worker 或启用真实数据投递，详见 [T05 验收边界](docs/t05-acceptance.md)。

**不要删除 `.local/secrets/deploy.env`、`.local/secrets/t03-accounts.json` 或执行 `down -v`。** 密码文件与数据库卷需要成对保留；首次初始化后只改env不会自动修改数据库密码或管理员密码。T03账号已存在而本机及容器凭据记录均丢失时，安装会拒绝静默重置；需恢复原记录。修改账号密码后应同步更新私密文件，安装脚本不会覆盖用户改过的密码。当前尚未建立生产备份方案。

首次T03安装中途失败时，脚本会尽量取回已生成的部分账号恢复记录并保存为0600；保留该文件后重新执行 `make setup-t03` 可沿用原密码继续。如果提示无法取回恢复记录，应先保留当前容器并恢复凭据，不要重建容器或删除数据卷。

## 测试边界

| 命令 | 当前含义 |
|---|---|
| `make test-data` | 本机契约测试 + 容器真实 PostgreSQL 健康测试 + T04 连接器与T05标准化/批次/作业测试 |
| `make test-data CASE=test_ingestion` | T05 标准化、持久批次、指标、健康扫描/发件与对账的合成及本地 PostgreSQL 验证；本轮56项通过 |
| `make test-data CASE=test_wdt` | 合成鉴权/分页/错误用例及真实 PostgreSQL 独立连接并发、迁移用例；数据库不可用则失败，不 skip |
| `make wdt-check` | 离线检查本机 0600 旺店通配置；未齐返回 needs_user / 非 0，静态完整返回 configured_not_verified / 0，均不发网络请求 |
| `make verify-contracts` | Python与TypeScript对相同合成夹具作相同判断 |
| `make test-plugin` | 已运行T03环境：串行运行bootstrap、scope、rules、pages、client、data-health，验证真实账号权限、版本冲突和四页配置 |
| `make test-plugin CASE=scope` / `CASE=rules` / `CASE=pages` | 单独运行权限、规则或页面集成测试 |
| `make test-bootstrap` | 私有配置生成、社区门禁等工具测试 |
| `make verify-community` | 容器实际插件与权威数据库清单、固定官方社区源码政策交叉核验 |
| `scripts/verify-isolation.sh` | 两个应用账号不能连接对方数据库 |
| `make test-ego`、`make test-e2e` | 尚未实现，明确失败，不能当作通过 |

`CASE`仅接受固定映射。未实现用例会返回非0，例如 `make test-plugin CASE=tasks`（evidence/reviews同样失败）；未知CASE也失败。默认 `make test` 已包含 T04/T05 用例，但不调用 ERP。插件测试会增添明确标识的合成配置版本与审计事件，只能在本地验收环境运行。

[接口契约](contracts/openapi.yaml)明确标注实现状态：`opsConfig:snapshot`、`opsConfig:command`、`opsRule:command`运行于NocoBase（13000），配置`expected_version`是整数；T05 的 `opsDataHealth:ingest` 位于 NocoBase（13000）。数据服务（18000）的外部入口仍以健康检查为主，T05 通过内部库与手动合成演练使用；其余经营业务 API 保持 pending，不能据此当作已交付功能。

## 资料与继续开发

- [开工资料清单](docs/intake/README.md)；用户填写副本在 `.local/intake/two-stores.md`。
- [字段口径](docs/field-dictionary.md)、[三条规则登记](docs/rule-register.md)。规则默认shadow，真实授权和口径未核实前不经营派单。
- [版本与费用边界](docs/versions-and-licenses.md)、[社区来源政策](docs/community-policy.md)、[运行手册](docs/operations-runbook.md)。
- [T03复现与验收](docs/t03-acceptance.md)、[T04协议依据](docs/wdt-protocol.md)、[T04工程与真实验收](docs/t04-acceptance.md)、[T05工程与真实验收](docs/t05-acceptance.md)、[批准的完整计划](docs/superpowers/plans/2026-10-22-project2-two-store-community.md)。T03 保留 2026-10-22 的合成验收结论；T04 工程不能替代两店正式接口验收。

旺店通凭据由授权人员填本地 `.local/secrets/wdt.env`（0600），先核实产品版本、正式只读权限、两店与仓库身份。`make wdt-check` 只输出是否齐备和问题码，不回显配置值；退出 0 不代表密钥有效或连接成功，也不会向服务注入凭据或开启 live。当前客户端默认禁止真实请求，尚无正式 live 采集命令。Ego 浏览器 Profile、Cookie 与密码未复制到服务，本轮不上 Ego worker。真实填写件、接口原件和秘密均不入 Git。

T05 生产前还需补原始页暂存的脱敏字段白名单、保留与清理周期；同一 scope/data_type 必须配置单一权威连接，避免多个连接竞争同一健康摘要。当前工程不代表已满足生产数据治理和真实口径验收。最终集成测试结果：已通过：T05 56项，完整验收216项不同用例（详见T05验收记录）。
