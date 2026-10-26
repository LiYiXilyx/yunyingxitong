# T04 连接器工程与真实验收记录

**2026-10-26 状态：partial。** 已具备只读连接器、合成协议测试、真实 PostgreSQL 共享限流验证入口、限流表安装和离线配置检查。官方文档核查发生于 2026-10-23，详见 [协议依据与未决项](wdt-protocol.md)。本轮没有向真实 ERP 发送请求，产品/版本、正式凭据、两店身份及授权样本仍未确认，不能标记 T04 完成。

T03 的 2026-10-22 合成环境验收保持历史结论。T05 标准化、批次、水位和指标未开始；本轮不部署 Ego worker、不巡检经营、不派单。`make test` 的通过结果也不能替代真实 ERP 验收。

## 已有工程能力

代码位于 `services/ops-data/ops_data/connectors/wdt/`，测试位于 `services/ops-data/tests/test_wdt.py` 与 `test_wdt_postgres.py`。

| 范围 | 当前行为 | 验收边界 |
|---|---|---|
| 鉴权 | 按 Java/Postman 的 key+value 源串签名；body 编码一次复用；每次尝试在限流之后刷新 Unix 秒时间戳和签名 | fixture 为 synthetic；没有官方预期 digest 或正式账号成功证据 |
| 请求 | 固定官方 HTTPS host、POST、精确只读路径允许清单、禁止重定向、默认 live 关闭 | `get` 不是 HTTP GET；实际产品兼容性尚未确认 |
| 分页 | 端点分别使用参数名；冻结窗口、检查 total/连续页/重复页/同页及跨页相同内容记录/冲突元数据/页数上限 | profile 和起页有未决项；内容比较不等于业务 ID 去重，分页完成不等于业务完整性完成 |
| 共享限流 | ops 数据库独立表，SID + URI 桶，滚动 60 秒最多 40 次许可；数据库连接/语句/锁超时分别 3/3/1 秒，acquire 等待预算默认 65 秒 | 只覆盖共用数据库与客户端的调用方；超时或预算耗尽停止请求，不绕过限流；许可与实际发包之间仍存在调度时差 |
| 错误与重试 | HTTP 与业务错误分开；超时和指定状态有限次重试；每次重签；Retry-After 超过 30 秒停止 | 服务端重试规则和业务错误码字典未确认；没有后台延期作业 |
| 输出 | `RawResult.pages` 原始页和 `RawResult.scope` 查询范围；对象 repr 与异常脱敏 | 不直接写业务事实、创建批次或投递任务；原始页仍须受控保存 |

## 可复现命令

沿用项目既有 Colima/Compose 环境，首次本地基础准备见 [README](../README.md)。无需填写 ERP 凭据即可安装限流表和执行合成/数据库测试。

```sh
# 重建并启动 ops-data，使用其应用账号迁移自己的 ops 数据库
make setup-wdt

# 只读检查本机私有配置，不发送 ERP 或其他网络请求
make wdt-check

# 合成连接器用例 + 容器真实 PostgreSQL 独立连接用例
make test-data CASE=test_wdt

# 现有工程回归；默认数据测试已包含 test_wdt
make test
```

`make setup-wdt` 运行 `python -m ops_data.connectors.wdt.migrate`，仅通过容器的 `OPS_DATABASE_URL` 创建 ops 数据库中的 `wdt_rate_reservations` 表与索引。迁移可重复执行并保留已有记录，不连接 ERP，不直接写 NocoBase 数据库；失败返回非 0，错误信息不含连接串。它会重建 ops-data 镜像；修改本地代码后不要直接拿旧容器里的测试结果作为新代码验证。

`make wdt-check` 调用 `scripts/wdt-check.py`，默认读取 `.local/secrets/wdt.env`。要求该文件是当前用户所有、权限恰为 0600 的普通文件，拒绝符号链接；仅解析字面值，不执行 shell、替换变量或输出配置值。检查项为 `WDT_APP_NAME`、`WDT_SID`、`WDT_SIGNING_KEY`、`WDT_BASE_URL`；URL 只接受 `https://openapi.qizhishangke.com`（可带末尾 `/`）。

| 离线检查情况 | 报告与退出码 | 含义 |
|---|---|---|
| 四项为空、缺少任一项，或文件/格式/权限/URL 不符合要求 | `status=needs_user`，检查脚本 exit 2 | 需要授权人员补配置或修正本地文件；报告列键名/问题码，不回显值 |
| 四项非空且上述静态检查通过 | `status=configured_not_verified`，exit 0 | 只证明本地配置满足静态条件；不证明密钥有效、产品匹配或接口已授权 |
| 上述任一结果 | `live_verified=false`、`network_request_sent=false` | 离线检查均不发送网络请求，也不会打开 live 开关 |

单独执行脚本时的 exit 2 会使 `make wdt-check` 以非 0 结束，这是需要人工补资料的状态，不应改成静默成功。当前检查器不把 `wdt.env` 注入服务，也没有面向生产的 live 采集命令；不能通过配置检查便声称服务已连接 ERP。

`make test-data CASE=test_wdt` 在 ops-data 容器中同时执行两个测试文件，并以 `OPS_DATABASE_URL` 提供测试所需的 `OPS_TEST_DATABASE_URL`。真实 PostgreSQL 测试使用随机 synthetic 桶、独立连接和并发线程，覆盖过期记录后重新竞争许可、SID/URI 分桶及重复迁移保留记录，只清理自身 synthetic 桶。缺少数据库配置或数据库不可用会明确失败，**不能 skip 后算通过**。仅手工运行 `test_wdt.py` 不包含共享数据库验证。

## 连接器调用接口

以下为库接口说明，不是可直接复制执行的真实采集脚本。正式凭据由受控配置持有，不在示例、聊天或 Git 中填写。

| API | 必需选择与输出 |
|---|---|
| `WdtClient(WdtConfig(...), PostgresRateLimiter(database_url)).request(endpoint, payload)` | endpoint 为模块 `ENDPOINTS` 中的精确路径。默认 live 关闭，凭据及产品、范围、响应契约、live 确认必须满足；确认值须为布尔 `True` |
| `PageContract(layout, size_field, verified=False)` / `ResponseProfile` | `layout` 为 `flat/nested`，`size_field` 为 `pagesize/pageSize`。候选 profile 需据端点证据选择；`verified` 不能代替真实验证 |
| `OrdersConnector.fetch(*, shop_id, begin, end, trade_status_code, contract, page_start=1, max_pages=1000)` | 显式店铺、修改时间窗（最多 90 天）及状态；0 为全状态。当前 scope 的业务时区和起页核验仍未确认 |
| `OrdersConnector.fetch_items(*, trade_ids, response_profile_verified=False)` | 1–100 个主单 ID；不传分页字段，返回原始页与 ID 范围 |
| `InventoryConnector.fetch(*, warehouse_no, page_start, page_start_verified=False, response_profile_verified=False, max_pages=1000)` | 显式普通仓库和起页；采用官方普通库存外壳，另记 `documented_profile_source`；真实 profile 确认默认 False；scope 为仓库，不按两店重复加总 |
| `ShopsConnector.fetch(*, begin, end, status, page_start, contract, page_start_verified=False, max_pages=1000)` | 显式时间窗、0 更新时间/1 创建时间、起页和候选 profile |
| `RefundsConnector.fetch(*, begin, end, contract, page_start=1, max_pages=1000)` | 修改时间窗最多 30 天，固定每页 50，不传 `pageSize`；店铺归属 `unresolved` |

业务时间格式当前为 `YYYY-MM-DD HH:MM:SS`；其源时区未确认，不能从“Temu 德国”推定 Europe/Berlin。起页 1 是订单/退款的候选默认值，不是已完成真实验证。`RawResult.scope.collection_complete` 只代表当前候选契约下的分页数量检查，同时标注 `completeness_basis=candidate_profile_and_count_only`，不是 T05 可提交批次状态。profile 和起页确认标记均仅接受布尔 `True`。平台仓只有传输允许清单，增量库存禁止调用。

## 本轮最终验证证据

以下为 2026-10-26 在本项目 Colima/Compose 环境中的最终执行记录。T04 最终数量来自 `make test` 默认数据套件执行的两个 WDT 测试文件，和 `CASE=test_wdt` 入口指向相同目标；单独 CASE 命令在上文列为复现入口。

| 验证项 | 日期 / 实际结果 / 证据 |
|---|---|
| `make setup-wdt` | 两次执行均退出 0；重复迁移保留记录另由真实 PG 用例验证 |
| `python3 scripts/wdt-check.py`（`make wdt-check` 的底层命令） | `status=needs_user`，四个必需项为空，检查脚本 exit 2；`live_verified=false`、`network_request_sent=false`；未输出配置值 |
| 最终 `make test` 中的 T04 套件 | 47 项通过：44 项离线测试 + 3 项真实 PostgreSQL 测试，无 skip；覆盖最终分页、确认标记、超时和限流回归 |
| 最终 `make test` 其他套件与门禁 | 整体退出 0；工具 49、Python 契约 28、PG 健康 3、插件 25、Node 契约 4 项通过；社区门禁核对 101 个安装/77 个启用插件，双库隔离通过 |
| 真实 ERP 请求、两店样本与对账 | 未执行；无真实请求/响应证据 |

独立审查提出的 3 项 Important 与 1 项 Minor 已修复并复核；修复后的最终测试结果如上。工程验证通过，仍保留 T04 partial，直到下述真实验收项通过。

## 正式联调所需资料

1. 旺店通准确产品名、版本、账号适用文档与授权责任人，确认本报告列出的跨境路由适用。API 已开通不等于产品与协议相符。
2. 授权人员在本机私有 `wdt.env` 填正式凭据与基址，保留 0600；文档只记配置引用，不发送密钥、SID、签名或完整认证 URL。
3. 两店 ERP `shopId/shopNo`、平台原生店铺 ID、站点、币种、IANA 时区及业务日切点，并保留 ERP 列表和平台后台的身份佐证；不能仅按店名匹配。
4. 每店只读权限及仓库列表、共仓范围、仓库类型、库存负责人；共享仓不能按两店各记一份，`availableNum` 口径需业务确认。
5. Shop/普通库存的起页、订单/子单/退款的完整成功外壳和字段类型、业务错误码说明、源业务时区；如可取得，补官方签名预期 digest 和增量游标边界说明。
6. 两店订单与子单、取消/拆合单、部分/全额退款、共仓 SKU、组合装样本及可对照的源端汇总。退款没有 shopId 时必须验证订单关联和平台身份消歧，无法唯一归属则保持 unresolved。

资料填写沿用 [两店模板](intake/two-stores.md) 的私有副本 `.local/intake/two-stores.md`。真实原件、客户信息与秘密不入 Git；脱敏证据保留端点、参数名、时间窗、范围、外壳和关联关系。

## 后续联调与完成条件

1. 核实产品、正式只读授权和两店/仓库绑定，完成离线检查；记录所有确认的证据来源。资料未齐继续离线，不用公开示例账号尝试调用。
2. 确认候选响应 profile 和 Shop/库存起页后，以受控最小范围进行首轮只读请求。首次真实响应若与候选契约冲突，停止该端点、记录脱敏差异并修订契约；不能仅为了通过而放宽解析。
3. 先核对店铺身份，再按明确状态和冻结修改时间窗分别取两店订单/子单；按仓库取普通库存；最后取得退款并验证归店。共享仓只采集一份范围事实，不能乘以店数。
4. 保存各端点脱敏请求/响应、产品版本、采集时间、业务时区、起页/profile 确认依据和页数/total 对账摘要；核对源端显示的同范围记录及状态。无相关样本的场景明确保留缺口，不补造成功证据。
5. 工程测试、两店授权样本、状态与字段映射、分页完整性和差异解释均通过后才将 T04 标记完成。T05 的标准化、批次事务、水位、回补和业务指标另行实施；Ego worker 与经营派单仍属于后续阶段。
