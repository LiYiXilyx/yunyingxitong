import { createRequire } from "node:module";
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { labels } from "../config/nocobase-pages.mjs";
const require = createRequire(import.meta.url);
const collections = require("../plugins/nocobase-plugin-ops/collections.js");
const statusLabels = {
  todo: "待处理",
  open: "待处理",
  doing: "处理中",
  unassigned: "待分配",
  submitted: "已提交",
  awaiting_review: "观察中",
  pending_close: "待确认关闭",
  closed: "已关闭",
  blocked: "受阻",
  reopened: "已重开",
  cancelled: "已取消",
  shadow: "仅观察",
  enabled: "已启用（测试）",
  retired: "已停用",
  active: "有效",
  inactive: "已撤销",
  partial: "数据不完整",
  succeeded: "采集成功",
  failed: "采集失败",
  needs_user: "需人工处理",
};
const enums = {
  status: Object.entries(statusLabels).map(([value, label]) => ({
    value,
    label,
  })),
  environment: [{ value: "synthetic", label: "测试数据" }],
  scope_type: [
    { value: "store", label: "店铺" },
    { value: "warehouse", label: "共享仓库" },
  ],
  membership_role: [
    { value: "ops_operator", label: "运营" },
    { value: "ops_supervisor", label: "主管" },
    { value: "ops_integration", label: "集成服务" },
  ],
};
const definitions = collections.map((c) => ({
  ...c,
  title:
    {
      opsTasks: "运营任务",
      opsStores: "店铺档案",
      opsIncidents: "异常记录",
      opsDataHealth: "数据健康",
      opsEvents: "业务事件",
    }[c.name] || c.name,
  filterTargetKey: "id",
  fields: [
    {
      name: "id",
      type: "bigInt",
      interface: "integer",
      primaryKey: true,
      uiSchema: {
        type: "number",
        title: "记录编号",
        "x-component": "InputNumber",
      },
    },
    {
      name: "createdAt",
      type: "date",
      interface: "datetime",
      uiSchema: {
        type: "string",
        title: "记录时间",
        "x-component": "DatePicker",
      },
    },
    ...c.fields.map((f) => ({
      ...f,
      uiSchema: {
        ...f.uiSchema,
        title: labels[f.name] || f.name,
        ...(enums[f.name]
          ? { "x-component": "Select", enum: enums[f.name] }
          : {}),
      },
      ...(enums[f.name] ? { interface: "select" } : {}),
    })),
  ],
}));
const source = readFileSync(
  new URL(
    "../plugins/nocobase-plugin-ops/src/client/index.js",
    import.meta.url,
  ),
  "utf8",
);
const marker = /\/\*__OPS_COLLECTIONS__\*\/\s*\[\]/;
if (!marker.test(source)) throw Error("Client metadata marker missing");
const target = new URL(
  "../plugins/nocobase-plugin-ops/dist/client/index.js",
  import.meta.url,
);
mkdirSync(new URL(".", target), { recursive: true });
writeFileSync(target, source.replace(marker, JSON.stringify(definitions)));
console.log("Project plugin client built with native collection metadata.");
