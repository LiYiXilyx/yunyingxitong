# T04 旺店通协议依据与未决项

官方文档核查日期为 **2026-10-23**；工程整理日期为 **2026-10-26**。本轮沿用当日只读核查记录，没有向真实 ERP 发送请求。用户实际旺店通产品、版本、正式凭据和两店身份尚未确认，因此这些文档事实不能证明实际账号与路由兼容。T04 状态为 **partial**，真实验收见 [T04 验收记录](t04-acceptance.md)。

## 鉴权与请求字节

依据：[Auth](https://zsxj.yuque.com/cdy1c2/ie96h9/fe7f28)、[独立 Postman 示例](https://zsxj.yuque.com/cdy1c2/ie96h9/aazyr1ofgndkc7tg)、[Call Guide](https://zsxj.yuque.com/cdy1c2/ie96h9/oslywk)。

Auth 的 Java 可执行代码与独立 Postman 可执行示例一致：`appName`、`body`、`sid`、`timestamp` 按键顺序连接 **key + value**，前后拼接签名密钥，再计算 MD5。`sign` 不参与源串，不插入 `=`、`&` 或长度前缀：

```text
key + "appName" + appName + "body" + rawBody
    + "sid" + sid + "timestamp" + timestamp + key
```

Call Guide 示意图描述 URL 键值对拼接，与上述两份可执行示例矛盾。本实现按两份可执行示例处理，保留该矛盾待正式产品联调确认，不复制官方公开示例密钥。

公共参数 `appName/sid/timestamp/sign` 位于 URL query，业务 JSON 是 POST raw body。Postman 对请求体执行一次 `JSON.stringify`，同一字符串用于签名与发送；不能在签名后再次格式化、排序或改写 body。签名前没有 URL 编码步骤；query 的传输编码与签名源串是两件事。当前客户端将业务对象编码为紧凑 UTF-8 JSON，保留键插入顺序，禁止 NaN/Infinity，并在重试中复用同一 body 字节；金额精度和末尾零应以字符串保存。

Postman 明确使用 `Math.floor(Date.now()/1000).toString()`，Auth 要求 10 位 Unix 秒且与当前时间偏差不超过 5 秒。请求鉴权时间戳与业务时间字符串、增量库存游标没有可互换关系。每次请求尝试在共享限流放行后重新取时间并签名，是本地重试策略，不是官方重试保证。

MD5 Hex 调用已在示例中核对；**UTF-8 字符串和小写 32 位 Hex 是所用库 API 语义的推断，不是官方文字明确规定，核查时未独立读取库主源。** 当前未取得官方包含预期 digest 的完整 golden。`services/ops-data/tests/fixtures/wdt/signature.json` 是使用自造输入、经独立 Node.js crypto 计算核对的 **synthetic fixture**，不能称为官方成功请求或真实签名验证。

## 只读端点

下表全部使用 **HTTP POST**，生产前缀为 `https://openapi.qizhishangke.com/api/openservices/`。方法名中的 `get` 表示读取语义，不是 HTTP GET。客户端固定 HTTPS host、精确路径允许清单且不跟随重定向。

| 官方依据 / 路径后缀 | 请求事实 | 当前工程支持与缺口 |
|---|---|---|
| [Shop](https://zsxj.yuque.com/cdy1c2/ie96h9/aq96iz) `shop/v1/getShopList` | `page_no/page_size`，最大 200；`status` 必填，0 更新时间、1 创建时间；无时间范围时 `id_list/name_list` 至少一项 | `ShopsConnector` 使用显式时间窗、状态、起页和候选响应 profile。表中起页示例 0，JSON 示例 1，不能默认为已确认 |
| [Order](https://zsxj.yuque.com/cdy1c2/ie96h9/xtvmyr) `trade/v1/getSalesTradeList` | `pageNo/pageSize`，示例 1/200，最大 200；创建或修改时间窗最多 90 天，发货窗最多 30 天；创建窗、修改窗、`tradeNoList`、`tradeIdList` 至少一项 | `OrdersConnector` 按显式 `shopId` 和修改时间窗查询。`tradeStatusCode` 省略默认 4（已发货），全状态必须显式 0；工程要求调用者选择状态，不以默认已发货代替口径 |
| 同 Order 页 `trade/v1/getSalesTradeOrderList` | `tradeIds` 数组必填，最多 100；未列分页参数；`shopId/platformId/srcTids` 可选 | `fetch_items` 按 1–100 个主单 ID 取子单，不发送分页字段；子单外壳候选为 `code/data` 列表 |
| [Stock](https://zsxj.yuque.com/cdy1c2/ie96h9/rs1pys) `stockSpec/v1/getStockSpecList` | `page_no/page_size`，最大 200；`warehouseNo` 可选；`warehouseType` 为 1/127/128 | `InventoryConnector` 为避免无范围采集，要求显式仓库与起页。表中起页示例 0、JSON 示例 1；原始结果按仓库 scope 保存，不能当作每店独有库存 |
| 同 Stock 页 `stockSpec/v1/getSmtStockSpecList` | `account` 必填；`pageNo` 明确从 1 开始，`pageSize` 最大 200；各 ID/编号列表最多 200 | 仅列入传输允许清单，尚无专用采集器；平台仓库存不能混同普通仓 `availableNum` |
| 同 Stock 页 `stockSpec/v1/getIncrementalStockSpecList` | `updateTimeStamp` 必填、`pageSize` 最大 200；响应有 `hasNextPage/updateTimeStamp`，无 `pageNo` | **未允许调用、未实现采集。** `warehouseNo` 必填标记与“非必填”描述矛盾；游标单位、相同时间戳边界、完整外壳和记录数组名未确认，不能猜测加 1 |
| [Refund](https://zsxj.yuque.com/cdy1c2/ie96h9/zfvv4mdb63om8a0s) `trade/v1/getApiRefundOrder` | `orderNo`、创建窗、修改窗至少一组，时间窗最多 30 天；`pageNo` 示例 1，默认每页 50；未列 `pageSize` 入参 | `RefundsConnector` 用修改时间窗、固定 50，不发送 `pageSize`。文档未列 `shopId`，结果店铺归属保持 unresolved，不能只按 `shopName` 归店 |

订单主单状态码的文档含义为：1 递交中、2 待处理、3 配货中、4 已发货、7 已取消、8 待审核；请求值 0 表示全状态，不能将其当成一条订单的业务状态。支付有效性、取消与退款是否计入业务指标仍需确认。退款状态为 0 未知、1 申请中、2 接受申请、3 已取消、4 争议、5 退款成功、6 已关闭。

## 响应契约与分页完整性

普通库存有完整官方成功 JSON：外层为 `code/data/msg/timestamp`，内层 `data` 包含 `currentPage/data/empty/pageSize/total`，记录位于 `data.data` 数组。官方原例包含一条库存记录，`code` 为数值 200；表格却将 `code` 标为 string。当前传输层仅将数值 `200` 和字符串 `"200"` 作为成功候选，还要求 `data` 存在；HTTP 200 本身不构成成功。库存数值示例混合 number/string，后续标准化必须保持十进制精度。

Shop 文档描述外层 `code/msg/data`，`data` 内有 `currentPage/pageSize/total/empty/data`，但记录集合的表格类型写 object，缺完整成功 JSON，不能直接断言列表类型已获官方证明。订单主单和退款表格使用 `pagesize`（全小写），没有完整 JSON 证明公共外壳层级；子单另有 `code/msg/data` 表。不能把库存的 `data.data` 外壳推广为全部接口事实，也未发现普通列表使用 `has_more`。

`PageContract(layout, size_field, verified=False)`（别名 `ResponseProfile`）只接受 `flat/nested` 布局及 `pagesize/pageSize` 字段名。订单主单、退款和店铺必须由调用者显式选择候选 profile。`verified` 是调用者确认标记，只有布尔 `True` 才记录为确认，不是自动验证结果。库存使用官方外壳，另以 `documented_profile_source=official_stock_example` 记录文档来源；`response_profile_verified` 仍默认 False，只有调用者显式确认才为 True，不能把文档样例当成真实账号验证。

当前分页策略冻结请求时间窗与过滤条件，要求页号连续、记录集合为列表、元数据类型和页大小一致、total 稳定；累计数量等于 total 才结束。整页重复、同页或跨页内容完全相同的重复记录（含整页乱序和部分重叠）、冲突的外壳或大小字段、empty 与集合矛盾、累计超 total、未到 total 就出现短页、超过页数上限均报错。默认最多 1000 页，可显式设定的上限不超过 10000。这是客户端保守策略，官方没有逐条保证该算法；记录内容比较不等于稳定业务 ID 去重，也不能证明分页过程中源记录绝不变化。

输出为 `RawResult.pages` 和 `RawResult.scope`。其中 `collection_complete=True` 只说明按给定 profile 完成分页数量检查，并同时记录 `completeness_basis=candidate_profile_and_count_only`；不代表真实业务覆盖、店铺归属、业务 ID 去重、批次入库或可用水位通过验收。T05 仍未开始。

## 限流、错误与安全边界

Call Guide 按公共 query 的 **SID + URI** 限制全部接口，要求调用频率 **小于 60 次/min**，不是 appName 全局配额，也不是允许等于 60。官方未说明固定窗/滑动窗、429/Retry-After、业务错误码字典或重试退避。

本地工程采用同一 ops 数据库中的 PostgreSQL 共享限流表和事务 advisory lock：每个 SID + URI 在滚动 60 秒内最多 40 次许可。表只保存哈希桶和时间，不存明文 SID；等待结束后重新连接、加锁并读取数据库当前时间，不提前发放未来预约。它只覆盖使用同一数据库与此客户端的进程；同一 SID 的其他调用方也会消耗服务端额度。许可返回到网络发送之间若进程长时间暂停，数据库不能原子保证实际发包时序，真实部署仍需约束调度或集中发送。

限流器数据库连接超时 3 秒、语句超时 3 秒、锁等待超时 1 秒；每次 acquire 的等待预算默认 65 秒，可设置为大于 0 且不超过 65 秒。等待循环使用单调时钟检查预算，超出预算或数据库异常会停止该请求，由客户端返回脱敏的共享限流不可用错误；不无界等待，也不绕过限流直接发送。该等待预算与 ERP 网络请求超时分别计算。

客户端默认 live 关闭。正式凭据齐备、产品兼容、授权范围、响应契约与 live 开关均明确确认后才可发请求；各确认开关必须是布尔 `True`，字符串 `"true"` 不能代替。该门禁只检查调用方确认，不能代替证据审查。

每次尝试均重新限流和重签。默认最多 3 次尝试，允许 1–5 次；默认超时 10 秒，允许大于 0 且不超过 60 秒。超时/连接异常，以及 HTTP 429、500、502、503、504 有限次重试；其他 HTTP 错误和业务错误拒绝，不盲目重试。支持数字秒数与 HTTP 日期的 Retry-After；若需等待超过 30 秒，则以 `retry deferred` 停止本次调用，**不会缩短等待后提前重试，也没有在后台安排任务**。无可用 Retry-After 时使用本地指数退避。

客户端与结果对象的 repr、异常使用脱敏内容，不输出凭据、签名、完整 URL 或业务原始页。原始页保留在返回值中供后续受控取证；调用方仍不能把它们直接写入普通日志。当前没有真实 ERP 请求证据、正式错误码验证或生产限流容量结论。
