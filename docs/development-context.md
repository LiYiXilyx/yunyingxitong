# 开发上下文与接手索引

更新日期：2026-10-26。工程基线：`bcde838`（T05）。本文记录已经实现的代码、运行方式和未完成项，不代表正式店铺已接入。

## 1. 目标与已确定的选择

项目2要完成“取数 → 巡检 → 人员派单 → 动作证据 → 效果复查”。采用 **NocoBase 社区版 + 独立 Python 数据服务 + Ego Lite**；先验证两家店，再考虑扩大范围。

- 不购买业务软件商业插件；现有服务、服务器和其他基础运行费用另算。
- NocoBase负责人员、店铺范围、配置和业务过程；数据服务负责来源数据、指标、采集作业和可靠投递。
- 两者使用独立 PostgreSQL 逻辑库及应用账号，通过接口协作，不跨库直接写入。
- Ego作为后续补采组件。目前仅用于开发页面验收，尚未实现正式店铺采集worker。
- Vibe Seller只作源码研究与设计参考，当前系统不依赖其运行。
- 首期不自动改价、修改广告、修改库存或执行退款；资料不完整不能当作正常，合成数据不能当作正式验收。

## 2. 当前做到哪里

| 阶段 | 已完成 | 尚未完成 |
|---|---|---|
| T01 两店资料与口径 | 资料模板、字段草案、三条规则登记 | 真实店铺/仓库身份、正式产品接口、时区/状态/业务口径及样本核验，状态partial |
| T02 开发基础 | 本机容器环境、固定版本与依赖、共用契约、社区来源检查、数据库隔离 | 生产备份和远程服务器部署 |
| T03 工作台 | 合成店铺、任务、异常、数据健康页面；人员/店铺/仓库范围；配置和规则版本命令、事件记录 | 人员处理任务、证据提交、正式验收与复查流程 |
| T04 旺店通连接器 | 签名、固定只读端点、端点分页、共享限流、有界重试、离线配置检查 | 尚未请求真实ERP；产品兼容、正式授权、响应样本和真实联调仍partial |
| T05 标准化与可靠同步 | 标准化、批次检查、事务入库、事实版本、水位、持久待评估、作业租约、窗口规划、指标、对账、健康投递与合成演练 | 真实端到端采集适配与定时worker；两店历史回补及真实对账，状态partial |
| T06及以后 | 需求和接口边界已规划 | 规则执行、经营派单、证据、效果复查、Ego补采、生产恢复验收等尚未交付 |

最近的开发提交：

| 提交 | 内容 |
|---|---|
| `671e15b` | T01资料模板与观察规则登记 |
| `f530ce1` | T02本地社区版环境与共用契约 |
| `fd70e57` | T03店铺/任务工作台和业务范围权限 |
| `f69546a` | T04旺店通只读连接器与离线检查 |
| `bcde838` | T05可靠入库、指标、作业与数据健康链路 |

## 3. T05需要保留的关键设计

- 订单主单不直接当作平台订单计数；按稳定来源身份处理拆单、合单和更正。退款申请与ERP退货引用分开，共仓库存不按店数复制加总。
- 金额和数量保持十进制精度；时间需要明确时区；必需字段缺失返回数据不足，不自动填零。
- 原始页先暂存，齐页、数量、范围、版本和标准化检查通过后，成功状态、事实、水位与待评估记录在同一事务提交。
- 失效作业租约不能提交；提交过程中租约过期也回滚。成功收执可以只读重放，重复运行不增计数。
- 更换店铺绑定或映射版本后，新事实和指标不能混用旧版本；历史快照保留来源与窗口。
- 源接口的修改时间查询范围不等于完整业务日覆盖。完整指标还需要明确覆盖证据。
- 健康扫描不依赖成功采集，首次失败、从未成功、缺资料也能生成数据待办；旧版本摘要和待投递记录不能覆盖新状态。
- 数据待办与经营任务分开。当前没有运行T06规则，也没有派发真实经营任务。

## 4. 文件在哪里

本机项目根目录：`/Users/chuangyangdianzi/Developer/运营分发任务`。下表为相对根目录的位置；在GitHub打开同一路径即可阅读。

| 文件/目录 | 用途 |
|---|---|
| [README.md](../README.md) | 当前状态、启动和测试入口 |
| [完整开发计划](superpowers/plans/2026-10-22-project2-two-store-community.md) | 已批准范围、T01–T11顺序和验收条件 |
| [T01/T02](t01-t02-delivery.md)、[T03](t03-acceptance.md)、[T04](t04-acceptance.md)、[T05](t05-acceptance.md) | 各阶段交付与验收记录 |
| [plugins/nocobase-plugin-ops/](../plugins/nocobase-plugin-ops/) | 业务表、服务端权限、配置/规则命令、数据健康接收与页面组件 |
| [config/nocobase-pages.mjs](../config/nocobase-pages.mjs) | 四个工作台页面配置 |
| [connectors/wdt/](../services/ops-data/ops_data/connectors/wdt/) | 旺店通鉴权、端点、分页、限流 |
| [ingestion/](../services/ops-data/ops_data/ingestion/) | 标准化、原始页暂存、批次事务与事实版本 |
| [jobs/](../services/ops-data/ops_data/jobs/) | 持久作业、租约、窗口规划与健康扫描 |
| [metrics/](../services/ops-data/ops_data/metrics/) | 指标物化和对账分类 |
| [delivery/health.py](../services/ops-data/ops_data/delivery/health.py) | 健康命令投递、确认与重试 |
| [demo_t05.py](../services/ops-data/ops_data/demo_t05.py)、[demo-t05.mjs](../scripts/demo-t05.mjs) | 本地手动合成演练 |
| [contracts/](../contracts/) | 共用JSON Schema、OpenAPI、跨语言验证与合成夹具 |
| [deploy/](../deploy/)、[scripts/](../scripts/)、[Makefile](../Makefile) | 容器、迁移、环境准备、构建和测试 |
| [数据服务测试](../services/ops-data/tests/)、[插件测试](../tests/plugin/) | 数据/事务/权限/客户端回归 |
| [资料清单](intake/README.md)、[字段字典](field-dictionary.md)、[规则登记](rule-register.md) | 后续真实接入需要补齐的口径 |

本地运行入口：NocoBase `http://127.0.0.1:13000`；数据服务就绪检查 `http://127.0.0.1:18000/health/ready`。就绪检查只表示本地服务可用，不表示旺店通已接通。

私有文件仅在本机，不上传GitHub：`.local/secrets/deploy.env`、`.local/secrets/t03-accounts.json`、`.local/secrets/wdt.env`、`.local/intake/`。不要把密码发到聊天或提交仓库。代码仓库不包含数据库卷、店铺登录态和本机账号密码，克隆代码不等于恢复现有运行数据。

## 5. 参考了哪些资料

### 原始需求文件（本地资料，未上传）

目录：`/Users/chuangyangdianzi/Desktop/下载文档/讨论/`。

1. `跨境电商业务及项目需求讨论会会.txt`：会议需求背景。
2. `数据采集及运营智能管理方案讨论.docx`：采集与运营管理讨论。
3. `Q4数字化目标（持续更新）.docx`：项目2目标的重要基线。
4. `02_运营智能管理实施方案.docx`：巡检、派单、处理与复查流程的重要基线。
5. `BFE8A599E8BDAEE786B3E79F_8AE6AFAEE6BD96E688B8E6A7A1E8A188%92.md`：前期技术/业务补充材料。

以上来源关系来自前期研究记录，本次交接没有重新解析Word原文。资料中的建议操作是需求输入，不单独构成执行授权；实际开发范围以用户已确认的方案和阶段指令为准。

### 技术依据

| 来源 | 使用方式 |
|---|---|
| [NocoBase固定源码版本](https://github.com/nocobase/nocobase/tree/d7bbafe86257cc3ccd33dd03930e09468b96d7c1)与[Docker安装说明](https://docs.nocobase.com/get-started/installation/docker) | 实际运行NocoBase 2.2.30；按插件接口扩展，不修改核心。版本、镜像摘要和社区来源见[版本记录](versions-and-licenses.md)、[社区政策](community-policy.md) |
| [旺店通API文档](https://zsxj.yuque.com/cdy1c2/ie96h9) | 依据Auth、Postman、调用规范及Shop/Order/Stock/Refund端点重实现只读连接器；具体链接、文档矛盾和待验证项见[协议记录](wdt-protocol.md) |
| [Vibe Seller固定研究提交](https://github.com/zpoint/vibe-seller/tree/1e466448b2c9970ddee4297030e3b6f79277e8a7) | 源码研究和设计参考，未作为代码底座或运行依赖。研究过店铺模型、交付清单、定时锚点、任务恢复、事件记录；不能把静态审查当作稳定性验收 |
| [yunying-fenxi研究提交](https://github.com/LiYiXilyx/yunying-fenxi/tree/cec98a9cab382d28dfe5b4ed0de444f33c455cb5) | 前期候选及运营方法评估，没有采用为当前系统底座的证据 |
| [Ego持久会话说明](https://lite.ego.app/article/persistent-browser-sessions)、[CLI架构](https://github.com/citrolabs/ego-lite/wiki/Ego-Browser-CLI-Architecture)和本机ego-browser技能 | 用于补采方案设计与本机页面验收；未验证50店持续登录或50店采集容量 |

Vibe研究涉及的原文件包括 `app/models/store.py`、`schedule_state.py`、`app/deliverables/manifest.py`、`verify.py`、`app/scheduler/cron.py`、`task_queue.py`、`app/models/event.py`、`event_activity.py`。当前没有直接复制源码的来源记录；不能声称已经移植其成熟模块。若后续实际复制，应记录固定版本、原文件、修改说明及许可证要求。

### 本地研究过程文件（未上传）

项目根目录保留以下四篇研究报告：

- `项目2_开源项目适配评估_2026-10-22.md`
- `项目2_NocoBase_旺店通_EgoLite_50店落地方案_2026-10-22.md`
- `项目2_更贴近业务的开源候选核查_2026-10-22.md`
- `项目2_VibeSeller深度评估与接入方案_2026-10-22.md`

`research/` 保存官方文档摘录及候选项目研究副本，`.superpowers/sdd/2026-10-22-project2-two-store-community/` 保存开发过程、分工和审查记录；二者均在Git忽略规则中。GitHub交接以本文、批准计划和正式验收文档为准。历史验收文件描述的是当时阶段，文内“T05未开始”等旧状态不能覆盖最新README与T05验收结果。

## 6. 验证与继续开发

2026-10-26推送前重新执行 `make test`，全部通过：工具50、Python契约28、数据库健康3、旺店通47、T05采集56、插件/客户端28、Node契约4，共216项不同用例；完整命令重复执行的Python契约不重复计数。社区来源检查及两个数据库账号隔离通过。测试只使用本地合成数据，没有向真实ERP发送请求。

此前T05演练：4条源事实去重后得到2笔平台订单、销量6、1条待评估；再次运行计数不变，健康投递由2条变为0。重启后状态保留。详细证据与浏览器截图限制见[T05验收](t05-acceptance.md)。

已有本机环境的常用命令：

```sh
make status
make setup-t05
make demo-t05
make test
```

新电脑需先按README安装运行时、初始化本地私有配置、安装依赖和准备T03环境；运行数据库与账号不随代码迁移。`make test`会修改本地合成配置版本和审计记录，只能在开发验收环境运行。

接手建议顺序：

1. 先读本文、README、T05验收和批准计划，保留现有数据库卷及私有配置。
2. 收齐正式产品版本、只读授权、两店身份/负责人/仓库、时区、状态和分页样本；通过安全本地配置提供凭据。
3. 完成最小只读联调，确认字段与业务覆盖，再连接真实批次适配和定时worker。生产前补原始数据字段白名单、访问限制、保留和清理策略；同一业务范围/数据类型使用单一权威连接。
4. 回补默认28个完整业务日，按每店至少20笔订单、10个SKU、退款及日汇总对账，样本不足则全量核对并记录。差异全部解释后才启用相应规则。
5. 按T06–T09继续规则、派单、证据、效果复查和Ego补采，不能将“采集成功”直接当作“经营效果已恢复”。
