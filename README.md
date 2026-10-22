# 项目2：运营巡检与任务分发

当前完成的是 **T01资料准备 + T02本地开发基础**。NocoBase社区版负责工作台，独立数据服务承载后续采集、规则及复查，自研插件承载后续任务与权限。当前没有真实店铺数据，也没有自动巡检或派单。

## 本机入口

- NocoBase：<http://127.0.0.1:13000>
- 数据服务就绪检查：<http://127.0.0.1:18000/health/ready>
- 管理员邮箱：`owner@project2.local`。随机密码位于 `.local/secrets/deploy.env` 的 `INIT_ROOT_PASSWORD`，不要发送到聊天或提交Git。

仅绑定本机环回地址。PostgreSQL没有宿主机端口；两个逻辑库由独立非超级用户连接。Colima项目配置为4核/6GB内存/30GB磁盘，使用独立context `colima-project2`，未改系统默认Docker context。

## 运行与停止

本机已安装 Colima、Docker CLI、Compose。首次在其他Mac复现需先安装这些工具，且安装 Python 3.13 和 Node 26.0.0。

```sh
# 若虚拟机停止，先启动。按实际仓库路径替换 mount。
colima start project2 --cpus 4 --memory 6 --disk 30 --vm-type vz --runtime docker --activate=false --mount "$PWD:w"
make bootstrap
make setup-dev
make up
make status
make test

# 停止容器但保留数据卷；需要时再 make up
make down
# 也可进一步停止虚拟机以释放内存
colima stop project2
```

`make bootstrap` 只生成/保留本地配置；重复执行不会更换已有密码。`make setup-dev` 安装锁定的本地测试依赖。`make up` 构建服务，并安装/核验自研插件骨架。Linux服务器需按部署环境配置Docker与 `PROJECT2_DOCKER_CONTEXT`，本轮没有部署远程服务器。

**不要删除 `.local/secrets/deploy.env` 或执行 `down -v`。** 密码文件与数据库卷需要成对保留；首次初始化后只改env不会自动修改数据库密码或管理员密码。当前尚未建立生产备份方案。

## 测试边界

| 命令 | 当前含义 |
|---|---|
| `make test-data` | 本机Python/Node共同契约测试 + 容器真实PostgreSQL健康测试 |
| `make verify-contracts` | Python与TypeScript对相同合成夹具作相同判断 |
| `make test-plugin` | 真实NocoBase实例：匿名拒绝，管理员登录后获取T02状态 |
| `make test-bootstrap` | 私有配置生成、社区门禁等工具测试 |
| `make verify-community` | 容器实际插件与权威数据库清单、固定官方社区源码政策交叉核验 |
| `scripts/verify-isolation.sh` | 两个应用账号不能连接对方数据库 |
| `make test-ego`、`make test-e2e` | T02尚未实现，明确失败，不能当作通过 |

`CASE`仅接受计划里的固定映射。未实现用例会返回非0，例如 `make test-data CASE=test_wdt`、`make test-plugin CASE=scope`；未知CASE也失败。计划中的经营端点仅为[接口草案](contracts/openapi.yaml)，当前应用只开放两个健康端点。

## 资料与继续开发

- [开工资料清单](docs/intake/README.md)；用户填写副本在 `.local/intake/two-stores.md`。
- [字段口径](docs/field-dictionary.md)、[三条规则登记](docs/rule-register.md)。规则默认shadow，真实授权和口径未核实前不经营派单。
- [版本与费用边界](docs/versions-and-licenses.md)、[社区来源政策](docs/community-policy.md)、[运行手册](docs/operations-runbook.md)。
- [批准的完整计划](docs/superpowers/plans/2026-10-22-project2-two-store-community.md)；本轮范围止于T01/T02。

旺店通凭据由授权人员填本地 `.local/secrets/wdt.env`，先核实产品版本、签名字段和正式只读权限；本轮尚未使用该文件或调用旺店通。Ego浏览器Profile、Cookie与密码未复制到服务。真实填写件、接口原件和秘密均不入Git。
