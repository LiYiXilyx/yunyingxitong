# T01 字段字典（候选映射，未获真实样本核验）

来源为本地接口研究摘录及 2026-10-23 官方文档核查记录；2026-10-26 更新工程边界，未向真实 ERP 请求样本。公开协议依据与差异见 [T04 协议记录](wdt-protocol.md)。标准字段为项目内部候选名，不是 ERP 请求参数；T04 返回原始页与查询范围，T05 已实现显式映射驱动的内部标准化与指标，当前仅完成合成工程验证。所有映射状态均为“文档已查、真实未确认”；缺失值保持缺失，不能补 0。产品/版本、身份和必需映射未确认时禁止启用对应生产规则。

| 来源与源字段 | 标准字段 / 语义 | 类型或枚举 / 核验缺口 |
|---|---|---|
| [Shop](../research/wdt/shop.txt) getShopList：shopId、shopNo、shopName | erp_shop_id、erp_shop_no、store_name | Integer/String/String；连接引用+shopId定位，不能仅按名称 |
| 同上：platformId、platformName、kjType | platform_id、platform_name、cross_border_type | kjType 0无/1本地/2跨境；不是站点ID |
| 平台后台 / 人工确认：原生店铺ID、站点、时区、币种 | platform_store_id、site_id、timezone、currency | Shop摘录没有这些返回字段；必须另行确认，不从名称推断 |
| 公共参数：sid、appName | credential_ref（仅保存配置引用） | 正式值只在安全配置；sign/timestamp 为运行时 query 参数，timestamp 为 Unix 秒；appName 与签名密钥分别使用，产品兼容性与实际授权待核验 |
| [Order](../research/wdt/order.txt) 主单：tradeId、tradeNo、srcTids | erp_trade_id、erp_trade_no、source_order_refs | 主单ID/ERP号/平台订单号集合；拆合解析规则待真实样本确认，不以tradeId计平台单量 |
| Order子单：orderId、tradeId、srcTid、srcOid | erp_line_id、erp_trade_id、platform_order_id、platform_line_id | 子单重建平台订单与拆合关联；去重候选为连接+店铺+srcTid，需验证稳定性 |
| Order：tradeTime、payTime、created、modified | ordered_at、paid_at、source_created_at、source_modified_at | 文档时间不带明确时区；源时区待核验，保存UTC与原始时区/业务日期 |
| Order主单：tradeStatusCode、tradeStatusDesc | order_status_raw、order_status_label | 文档编码 1 递交中/2 待处理/3 配货中/4 已发货/7 已取消/8 待审核，真实样本待确认；请求省略默认 4，显式 0 表示全状态，不能当作记录状态；支付有效性另确认 |
| Order主单：refundStatus | master_refund_status_raw | 0无/1申请退款/2部分退款/3退款成功 |
| Order子单：refundStatus | line_refund_status_raw | 0无/1取消退款/2申请退款/5退款成功/7子单部分退款；与主单枚举不同，禁止共用解码 |
| Order子单：num、apiSpecNo | sold_quantity、platform_sku_no | num为销售数量（BigDecimal），不是订单数；组合装单位待确认 |
| [StockSpec](../research/wdt/stock-spec.txt) getStockSpecList：warehouseNo、specId、specNo | warehouse_no、erp_spec_id、erp_sku_no | 按连接+仓库+ERP规格定位；SKU编码跨连接不可默认唯一；共仓是同一仓库范围事实，不能按两店复制或加总 |
| 同上：availableNum、stockNumTotal、stockNum、defectNum | available_quantity、total_quantity、good_quantity、defective_quantity | BigDecimal；分别可发/总/正品/残次，不互相替换；R2候选availableNum须业务确认 |
| 同上：warehouseType（请求） | warehouse_type | 1普通仓有货区货位/127普通仓无货区货位/128高级仓；getIncrementalStockSpecList 对 warehouseNo 必填标注与描述矛盾，游标单位与相等边界未确认，当前禁止增量调用 |
| StockSpec getSmtStockSpecList：stockNum、reserveNum、warehouseId、warehouseNo | platform_warehouse_stock_raw等 | 属另一个端点；不擅自推导为availableNum或混入普通仓库存 |
| [Refund](../research/wdt/refund.txt) getApiRefundOrder：refundNo、tid、shopName、platformName | platform_refund_id、platform_order_id、source_shop_name、source_platform_name | 返回未列shopId；须用订单关联和平台身份消歧，不能只按店名归店 |
| 同上：created、modified、status、type | refund_created_at、refund_modified_at、refund_status_raw、refund_type_raw | status 0未知/1申请中/2接受申请/3已取消/4争议/5退款成功/6已关闭；type 1未发货退款申请/2退货/3换货/4退款不退货 |
| 同上子单：oid、specId、specNo、num | platform_line_id、platform_spec_id、platform_sku_no、returned_quantity | specId为平台规格ID，不是ERP specId；num为退回数量，不是退款申请数 |
| [Employee](../research/wdt/employee.txt) getEmployeeList：employeeId、account、fullName | erp_employee_id、employee_account_ref、employee_name_ref | 0系统/1管理员；ERP员工不自动等于业务运营负责人，需显式绑定角色与范围 |
| 业务确认：组合装BOM、组件倍数、有效日期 | bundle_components、component_quantity、effective_from/to | 当前上述摘录不足以确认组合装映射，待产品接口及真实样本，不推导数量 |

分页外壳、源端点、产品版本、抓取时间、业务范围、批次完整性和绑定版本必须随证据保留。不同端点参数命名不同，例如 getShopList 使用 `page_no/page_size`，getApiRefundOrder 使用 `pageNo` 且没有文档支持的 `pageSize` 入参；订单子单没有分页参数，不能通用改名或补字段后假定兼容。这里的所有读取端点均使用 HTTP POST。

Shop 与普通库存的 `page_no` 表格样例为 0、JSON 样例为 1，仍需确认起页；订单/退款外壳与 `pagesize` 大小写须按真实样本确认。`RawResult.scope` 保存已使用的范围、候选 profile 与确认标记；库存文档来源单独记录，不自动确认真实 profile。`collection_complete` 同时标注 `completeness_basis=candidate_profile_and_count_only`，只表示候选契约下分页数量检查完成，不表示店铺归属、业务覆盖或 T05 批次完整性已经通过。


## T05 已实现的标准化口径（真实映射仍待确认）

标准化输入必须显式提供 source_kind（synthetic / wdt_api / manual_import）、connection_id、正整数十进制字符串 binding_version、mapping_version、IANA source_timezone、mapping_confirmed、业务绑定及 allowed_scope。未知来源、状态、身份、时区或缺必需字段会产生静态 issues，批次不得进入完整指标。`mapping_confirmed is True` 是调用方提供的显式门禁，不是系统自动核实真实映射的证明；生产确认仍需人员审核真实资料和对账证据，不能因为合成测试通过就设为已确认。

| 实现对象 | 当前工程口径 | 真实验收缺口 |
|---|---|---|
| 订单事实 | 显式配对 master/lines，按 orderId 保存源事实；平台订单按业务店铺+srcTid 去重，数量按业务店铺+srcTid+srcOid 去重；最新源修改时间反映状态更正，同时间异内容拒绝 | 拆合样本及平台子单身份稳定性待核实，tradeId 不计平台订单数 |
| 订单状态与日期 | order_status_map 显式映射 paid/void/pending；支付时间决定业务日，内部统一 UTC；无偏移且 DST 歧义/不存在时间拒绝 | 不把候选编码自动解释为正式支付口径，源时区待确认 |
| 数量与金额类数值 | Decimal 字符串精确运算，拒绝浮点、NaN、Infinity；缺失不补0 | 单位、组合装口径及实际小数精度待真实样本确认 |
| 普通库存 | warehouseNo 经 warehouse_bindings 映射业务仓库，按仓库/specId 保留当前数量，不乘关联店数；库存可仅带 warehouse_ids | 可发库存业务含义、共仓身份待确认；当前事实不等于历史时点库存重建 |
| 退款申请 | 显式 platformId、refundNo、tid，以 refund_order_bindings 的 platformId:tid 键绑定唯一店铺；按平台退款ID计申请，ERP退货仅关联 | 平台身份需实际适配提供并确认，冒号键不得存在组成歧义，不凭店名推断 |
| 商品/BOM | 仅明确 synthetic/manual_import 模型；catalog_mapping_confirmed 严格为 True；组件倍数为正 Decimal，拒绝跨连接、循环、重复或缺失组件 | 未接通官方商品/BOM端点，当前需完整引用图，不编造真实路由 |
| 指标覆盖 | 只有显式完整覆盖证据才能产生 complete；源修改时间查询窗不等于业务历史完整覆盖；不足时 values={} | 28完整业务日真实回补及迟到数据回扫待验收 |
| 对账 | 显式身份字段和Decimal值字段；区分缺源/缺目标/数值差异/重复身份/缺字段/非法值；任一侧None为不足；查询窗不同拒绝直接比较 | 差异只输出稳定身份摘要和字段，始终保留未解释，不自动视为合理差异 |

同一 scope/data_type 当前要求单一权威连接。来源必须保持隔离，不混合 synthetic 与真实事实。原始页暂存尚未配置脱敏字段白名单及保留/清理周期，这些属于生产前置工作。T05 工程56项及完整验收216项不同用例通过，详见 [T05验收记录](t05-acceptance.md)；真实验收仍为 partial。
