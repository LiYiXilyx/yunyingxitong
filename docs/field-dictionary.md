# T01 字段字典（候选映射，未获真实样本核验）

来源为本地接口研究摘录，非本次联网验证。标准字段为项目内部候选名，不是ERP请求参数。所有映射状态均为“文档已查、真实未确认”；缺失值保持缺失，不能补0。产品/版本、身份和必需映射未确认时禁止启用对应生产规则。

| 来源与源字段 | 标准字段 / 语义 | 类型或枚举 / 核验缺口 |
|---|---|---|
| [Shop](../research/wdt/shop.txt) getShopList：shopId、shopNo、shopName | erp_shop_id、erp_shop_no、store_name | Integer/String/String；连接引用+shopId定位，不能仅按名称 |
| 同上：platformId、platformName、kjType | platform_id、platform_name、cross_border_type | kjType 0无/1本地/2跨境；不是站点ID |
| 平台后台 / 人工确认：原生店铺ID、站点、时区、币种 | platform_store_id、site_id、timezone、currency | Shop摘录没有这些返回字段；必须另行确认，不从名称推断 |
| 公共参数：sid、appName | credential_ref（仅保存配置引用） | 正式值只在安全配置；sign/timestamp为运行时请求参数；产品版本与appkey关系待核验 |
| [Order](../research/wdt/order.txt) 主单：tradeId、tradeNo、srcTids | erp_trade_id、erp_trade_no、source_order_refs | 主单ID/ERP号/平台订单号集合；拆合解析规则待真实样本确认，不以tradeId计平台单量 |
| Order子单：orderId、tradeId、srcTid、srcOid | erp_line_id、erp_trade_id、platform_order_id、platform_line_id | 子单重建平台订单与拆合关联；去重候选为连接+店铺+srcTid，需验证稳定性 |
| Order：tradeTime、payTime、created、modified | ordered_at、paid_at、source_created_at、source_modified_at | 文档时间不带明确时区；源时区待核验，保存UTC与原始时区/业务日期 |
| Order主单：tradeStatusCode、tradeStatusDesc | order_status_raw、order_status_label | 编码1/2/3/4/7/8；说明列递交中/待处理/配货中/已发货/已取消/待审核，未凭列表顺序建立映射；支付有效性另确认 |
| Order主单：refundStatus | master_refund_status_raw | 0无/1申请退款/2部分退款/3退款成功 |
| Order子单：refundStatus | line_refund_status_raw | 0无/1取消退款/2申请退款/5退款成功/7子单部分退款；与主单枚举不同，禁止共用解码 |
| Order子单：num、apiSpecNo | sold_quantity、platform_sku_no | num为销售数量（BigDecimal），不是订单数；组合装单位待确认 |
| [StockSpec](../research/wdt/stock-spec.txt) getStockSpecList：warehouseNo、specId、specNo | warehouse_no、erp_spec_id、erp_sku_no | 按连接+仓库+ERP规格定位；SKU编码跨连接不可默认唯一 |
| 同上：availableNum、stockNumTotal、stockNum、defectNum | available_quantity、total_quantity、good_quantity、defective_quantity | BigDecimal；分别可发/总/正品/残次，不互相替换；R2候选availableNum须业务确认 |
| 同上：warehouseType（请求） | warehouse_type | 1普通仓有货区货位/127普通仓无货区货位/128高级仓；getIncrementalStockSpecList对warehouseNo必填标注与描述矛盾，接入前核验 |
| StockSpec getSmtStockSpecList：stockNum、reserveNum、warehouseId、warehouseNo | platform_warehouse_stock_raw等 | 属另一个端点；不擅自推导为availableNum或混入普通仓库存 |
| [Refund](../research/wdt/refund.txt) getApiRefundOrder：refundNo、tid、shopName、platformName | platform_refund_id、platform_order_id、source_shop_name、source_platform_name | 返回未列shopId；须用订单关联和平台身份消歧，不能只按店名归店 |
| 同上：created、modified、status、type | refund_created_at、refund_modified_at、refund_status_raw、refund_type_raw | status 0未知/1申请中/2接受申请/3已取消/4争议/5退款成功/6已关闭；type 1未发货退款申请/2退货/3换货/4退款不退货 |
| 同上子单：oid、specId、specNo、num | platform_line_id、platform_spec_id、platform_sku_no、returned_quantity | specId为平台规格ID，不是ERP specId；num为退回数量，不是退款申请数 |
| [Employee](../research/wdt/employee.txt) getEmployeeList：employeeId、account、fullName | erp_employee_id、employee_account_ref、employee_name_ref | 0系统/1管理员；ERP员工不自动等于业务运营负责人，需显式绑定角色与范围 |
| 业务确认：组合装BOM、组件倍数、有效日期 | bundle_components、component_quantity、effective_from/to | 当前上述摘录不足以确认组合装映射，待产品接口及真实样本，不推导数量 |

分页外壳、源端点、产品版本、抓取时间、业务范围、批次完整性和绑定版本必须随证据保留。不同端点参数命名不同，例如getShopList使用page_no/page_size，getApiRefundOrder使用pageNo，不能通用改名后假定兼容。
