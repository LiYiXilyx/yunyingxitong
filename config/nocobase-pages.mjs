// Versioned native NocoBase v1 pages. Access is always enforced by the server plugin.
export const labels = {
  id: "记录编号",
  business_id: "业务编号",
  title: "名称",
  store_id: "店铺编号",
  warehouse_id: "仓库编号",
  scope_type: "范围类型",
  status: "状态",
  version: "版本",
  environment: "数据用途",
  createdAt: "记录时间",
  connection_id: "旺店通连接代号",
  erp_store_id: "旺店通店铺ID",
  platform: "平台",
  site: "站点",
  timezone: "业务时区",
  user_id: "人员编号",
  membership_role: "成员职责",
  rule_family: "规则类型",
  family: "规则类型",
  metric_version: "指标口径版本",
  parameters: "参数",
  recovery: "复查与恢复条件",
  approved_by: "批准人",
  reason: "原因",
  assignee_id: "负责人编号",
  incident_id: "异常编号",
  rule_version_id: "规则版本编号",
  source: "来源",
  due_at: "处理期限",
  fingerprint: "异常指纹",
  evaluation_id: "评估编号",
  observation: "观测值",
  task_id: "任务编号",
  actor_id: "操作人编号",
  description: "说明",
  action_id: "动作编号",
  baseline: "固定基线",
  observation_window: "观察窗口",
  result: "结果",
  sha256: "内容哈希",
  media_type: "文件类型",
  event_type: "事件",
  payload: "事件内容",
  last_success_at: "最后成功时间",
  last_attempt_at: "最后尝试时间",
  data_type: "数据类型",
  freshness_deadline: "时效截止时间",
  error_class: "问题分类",
  health_revision: "健康状态版本",
  expected_window: "应采集时间范围",
  missing_fields: "缺少的资料或字段",
  business_date: "业务日期",
  details: "数据完整性说明",
  snapshot: "配置快照",
  command_id: "命令编号",
};
const field = (collection, name, form = false) => ({
  type: "string",
  "x-component": "CollectionField",
  "x-collection-field": `${collection}.${name}`,
  "x-read-pretty": true,
  ...(form ? { title: labels[name] || name, "x-decorator": "FormItem" } : {}),
});
function details(collection, names) {
  return {
    type: "void",
    "x-decorator": "FormBlockProvider",
    "x-decorator-props": {
      dataSource: "main",
      resource: collection,
      collection,
      action: "get",
      readPretty: true,
      useParams: "{{ useParamsFromRecord }}",
    },
    "x-component": "CardItem",
    properties: {
      form: {
        type: "void",
        "x-component": "FormV2",
        "x-use-component-props": "useFormBlockProps",
        "x-read-pretty": true,
        properties: Object.fromEntries(
          names.map((name) => [name, field(collection, name, true)]),
        ),
      },
    },
  };
}
export function table(collection, title, names, detailNames = names) {
  const columns = Object.fromEntries(
    names.map((name, i) => [
      `c${i}`,
      {
        type: "void",
        title: labels[name] || name,
        "x-decorator": "TableV2.Column.Decorator",
        "x-component": "TableV2.Column",
        properties: { [name]: field(collection, name) },
      },
    ]),
  );
  const drawer = {
    type: "void",
    title: title + "详情",
    "x-component": "Action.Container",
    "x-component-props": { className: "nb-action-popup" },
    properties: {
      details: details(collection, detailNames),
      ...(collection === "opsTasks"
        ? { timeline: { type: "void", "x-component": "OpsTimeline" } }
        : {}),
    },
  };
  const view = {
    type: "void",
    title: "查看",
    "x-action": "view",
    "x-component": "Action.Link",
    "x-component-props": { openMode: "drawer" },
    properties: { drawer },
  };
  columns.actions = {
    type: "void",
    title: "操作",
    "x-component": "TableV2.Column",
    "x-action-column": "actions",
    properties: {
      actions: { type: "void", "x-component": "Space", properties: { view } },
    },
  };
  return {
    type: "void",
    "x-decorator": "TableBlockProvider",
    "x-decorator-props": {
      dataSource: "main",
      collection,
      resource: collection,
      action: "list",
      params: { pageSize: 20 },
      rowKey: "id",
      showIndex: true,
      dragSort: false,
    },
    "x-component": "CardItem",
    "x-component-props": { title },
    properties: {
      table: {
        type: "array",
        "x-component": "TableV2",
        "x-use-component-props": "useTableBlockProps",
        "x-component-props": { rowKey: "id" },
        properties: columns,
      },
    },
  };
}
export const pageSpecs = [
  {
    key: "tasks",
    title: "我的任务",
    icon: "CheckSquareOutlined",
    blocks: [
      {
        type: "void",
        "x-component": "OpsPageNotice",
        "x-component-props": { kind: "tasks" },
      },
      table(
        "opsTasks",
        "运营任务",
        ["title", "status", "scope_type", "environment", "due_at"],
        [
          "title",
          "business_id",
          "status",
          "scope_type",
          "store_id",
          "warehouse_id",
          "assignee_id",
          "source",
          "due_at",
          "version",
          "environment",
        ],
      ),
    ],
  },
  {
    key: "incidents",
    title: "异常中心",
    icon: "WarningOutlined",
    blocks: [
      {
        type: "void",
        "x-component": "OpsPageNotice",
        "x-component-props": { kind: "incidents" },
      },
      table(
        "opsIncidents",
        "异常记录",
        ["title", "status", "rule_family", "scope_type", "environment"],
        [
          "title",
          "business_id",
          "status",
          "rule_family",
          "store_id",
          "warehouse_id",
          "environment",
        ],
      ),
    ],
  },
  {
    key: "health",
    title: "数据健康",
    icon: "HeartOutlined",
    blocks: [
      {
        type: "void",
        "x-component": "OpsPageNotice",
        "x-component-props": { kind: "health" },
      },
      table(
        "opsDataHealth",
        "数据同步状态",
        ["title", "status", "data_type", "last_attempt_at", "last_success_at", "freshness_deadline", "environment"],
        [
          "title",
          "status",
          "source",
          "store_id",
          "business_date",
          "last_success_at",
          "last_attempt_at",
          "freshness_deadline",
          "expected_window",
          "missing_fields",
          "error_class",
          "health_revision",
          "details",
          "environment",
        ],
      ),
      table(
        "opsDataIssues",
        "待处理的数据问题",
        ["title", "status", "data_type", "assignee_id", "environment"],
        ["title", "description", "data_type", "error_class", "assignee_id", "store_id", "warehouse_id", "status", "environment"],
      ),
    ],
  },
  {
    key: "settings",
    title: "管理设置",
    icon: "SettingOutlined",
    blocks: [
      { type: "void", "x-component": "OpsManagement" },
      table(
        "opsStores",
        "店铺档案",
        ["title", "platform", "site", "timezone", "environment"],
        [
          "title",
          "business_id",
          "connection_id",
          "erp_store_id",
          "platform",
          "site",
          "timezone",
          "version",
          "environment",
        ],
      ),
      table("opsMemberships", "店铺成员授权", [
        "title",
        "user_id",
        "membership_role",
        "store_id",
        "environment",
      ]),
      table(
        "opsRules",
        "规则版本（不可原地修改）",
        ["title", "family", "status", "version", "environment"],
        [
          "title",
          "business_id",
          "family",
          "status",
          "version",
          "store_id",
          "warehouse_id",
          "parameters",
          "recovery",
          "approved_by",
          "reason",
          "environment",
        ],
      ),
    ],
  },
];
export function pageSchema(spec) {
  const uid = "ops_t03_" + spec.key;
  return {
    type: "void",
    "x-component": "Page",
    "x-uid": uid,
    properties: {
      main: {
        type: "void",
        "x-component": "Grid",
        "x-uid": uid + "_tab",
        "x-async": true,
        properties: Object.fromEntries(
          spec.blocks.map((block, i) => [
            "row" + i,
            {
              type: "void",
              "x-component": "Grid.Row",
              properties: {
                col: {
                  type: "void",
                  "x-component": "Grid.Col",
                  properties: { block },
                },
              },
            },
          ]),
        ),
      },
    },
  };
}
export function routeSpec(spec) {
  const uid = "ops_t03_" + spec.key;
  return {
    type: "page",
    title: spec.title,
    icon: spec.icon,
    schemaUid: uid,
    menuSchemaUid: uid + "_menu",
    enableTabs: false,
    children: [
      {
        type: "tabs",
        schemaUid: uid + "_tab",
        tabSchemaName: "main",
        hidden: true,
      },
    ],
  };
}
