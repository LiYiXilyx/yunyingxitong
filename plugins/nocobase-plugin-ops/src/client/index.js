/* Project-owned NocoBase client module. Compiled by inserting collection metadata only. */
(function (factory) {
  if (typeof define === "function" && define.amd)
    define("@project2/plugin-ops", [
      "@nocobase/client",
      "react",
      "antd",
    ], factory);
  else if (typeof module === "object")
    module.exports = factory(
      require("@nocobase/client"),
      require("react"),
      require("antd"),
    );
})(function (client, React, antd) {
  const h = React.createElement;
  const {
    Alert,
    Button,
    Card,
    Form,
    Input,
    Select,
    Tabs,
    Table,
    Tag,
    Space,
    Timeline,
    Typography,
  } = antd;
  const definitions = /*__OPS_COLLECTIONS__*/ [];
  const notice = {
    tasks:
      "当前展示的是测试任务。这里只查看任务与处理历史，提交处理、验收和效果复查将在后续阶段开放。",
    incidents: "当前为测试异常；尚未读取旺店通，也未运行真实经营巡检。",
    health: "当前为测试采集状态。本地服务正常不代表旺店通或平台数据已接通。",
  };
  function OpsPageNotice({ kind }) {
    return h(Alert, {
      type: "info",
      showIcon: true,
      message: "开发验证 · 测试数据",
      description: notice[kind],
      style: { marginBottom: 16 },
    });
  }
  function OpsTimeline() {
    const api = client.useAPIClient();
    const row = client.useRecord();
    const collectionRow = client.useCollectionRecordData();
    const record = collectionRow || row;
    const [events, setEvents] = React.useState([]);
    const [error, setError] = React.useState("");
    React.useEffect(() => {
      let alive = true;
      setEvents([]);
      setError("");
      if (!record?.business_id) return;
      api
        .resource("opsEvents")
        .list({ filter: { task_id: record.business_id }, pageSize: 100 })
        .then((r) => {
          if (alive) setEvents(r.data.data || []);
        })
        .catch(() => {
          if (alive) setError("无法读取处理历史，请刷新后重试。");
        });
      return () => {
        alive = false;
      };
    }, [record?.business_id]);
    return h(
      Card,
      { title: "处理时间线 · 只读" },
      error
        ? h(Alert, { type: "error", message: error })
        : events.length
          ? h(Timeline, {
              items: events.map((e) => ({
                children: h(
                  "div",
                  null,
                  h("strong", null, e.title || e.event_type),
                  h("div", null, e.reason || "—"),
                  h(
                    "small",
                    { style: { color: "#777" } },
                    `${e.createdAt || ""} · 操作人 ${e.actor_id ?? "系统"}`,
                  ),
                ),
              })),
            })
          : h(
              Typography.Text,
              { type: "secondary" },
              "暂无处理事件。记录由服务端追加，不能在页面修改或删除。",
            ),
    );
  }
  function OpsManagement() {
    const api = client.useAPIClient();
    const [snapshot, setSnapshot] = React.useState(null);
    const [failure, setFailure] = React.useState("");
    const [success, setSuccess] = React.useState("");
    const [busy, setBusy] = React.useState(false);
    const [pending, setPending] = React.useState(null);
    const [storeSelection, setStoreSelection] = React.useState(undefined);
    const inFlight = React.useRef(false);
    const [storeForm] = Form.useForm();
    const [memberForm] = Form.useForm();
    const [ruleForm] = Form.useForm();
    const load = () =>
      api
        .resource("opsConfig")
        .snapshot()
        .then((r) => setSnapshot(r.data.data))
        .catch(() => setFailure("当前账号无法读取管理配置。"));
    React.useEffect(() => {
      load();
    }, []);
    const clearEditors = () => {
      storeForm.resetFields();
      memberForm.resetFields();
      ruleForm.resetFields();
      setStoreSelection(undefined);
    };
    const perform = async (operation) => {
      if (inFlight.current) return false;
      inFlight.current = true;
      setBusy(true);
      setFailure("");
      setSuccess("");
      try {
        const r = await api
          .resource(operation.resource)
          .command({ values: operation.values });
        setPending(null);
        if (
          operation.resource === "opsConfig" &&
          operation.values.command === "saveStore"
        ) {
          const savedId = operation.values.values.business_id;
          storeForm.setFieldsValue({ business_id: savedId });
          setStoreSelection(savedId);
        }
        await load();
        setSuccess(
          `保存成功，配置版本 ${r.data.data.version}。下方原生列表可刷新页面查看。`,
        );
        return true;
      } catch (e) {
        const status = e.response?.status;
        if (!status || status >= 500) {
          setPending(operation);
          setFailure(
            "操作结果尚未确认。请点击“重试上一操作”，系统会沿用原请求核对结果，避免重复保存。",
          );
          return false;
        }
        setPending(null);
        if (status === 409) clearEditors();
        setFailure(
          status === 409
            ? "配置已被其他人修改，旧表单已清空。请重新选择店铺或人员，查看最新内容后再填写。"
            : e.response?.data?.errors?.[0]?.message ||
                "保存失败，请检查权限和输入。",
        );
        await load();
        return false;
      } finally {
        inFlight.current = false;
        setBusy(false);
      }
    };
    const send = (resource, body) => {
      if (pending || inFlight.current) return false;
      return perform({
        resource,
        values: {
          ...body,
          command_id: crypto.randomUUID(),
          expected_version: snapshot.version,
        },
      });
    };
    const locked = busy || !!pending;
    if (!snapshot)
      return h(
        Card,
        { title: "管理设置" },
        h(Alert, {
          type: failure ? "error" : "info",
          message: failure || "正在读取配置…",
        }),
        failure ? h(Button, { onClick: load }, "重新读取配置") : null,
      );
    const stores = snapshot.opsStores || [];
    const users = snapshot.users || [];
    const storeOptions = stores.map((s) => ({
      label: s.title,
      value: s.business_id,
    }));
    const userOptions = users.map((u) => ({
      label: `${u.nickname || "用户"}（${u.id}）`,
      value: u.id,
    }));
    const warehouseOptions = [
      ...new Map(
        (snapshot.opsWarehouseScopes || []).map((w) => [
          w.warehouse_id,
          { label: w.title || w.warehouse_id, value: w.warehouse_id },
        ]),
      ).values(),
    ];
    const field = (name, label, child, required = true) =>
      h(
        Form.Item,
        {
          name,
          label,
          rules: required
            ? [{ required: true, message: "请填写" + label }]
            : [],
        },
        child,
      );
    const saveStore = async (values) => {
      const uuid = values.business_id || crypto.randomUUID();
      const { reason, ...rest } = values;
      await send("opsConfig", {
        command: "saveStore",
        reason,
        values: {
          ...rest,
          business_id: uuid,
          store_id: uuid,
          environment: "synthetic",
        },
      });
    };
    const saveMember = async (values) => {
      const { kind, reason, ...rest } = values;
      const command = {
        store: "saveMembership",
        warehouse: "saveWarehouseScope",
        owner: "saveOwnerAssignment",
      }[kind];
      const payload = {
        business_id: crypto.randomUUID(),
        environment: "synthetic",
        user_id: rest.user_id,
        title: rest.title || "测试人员授权",
      };
      if (kind === "warehouse") payload.warehouse_id = rest.warehouse_id;
      else payload.store_id = rest.store_id;
      if (kind === "store") payload.membership_role = rest.membership_role;
      if (kind === "owner") payload.rule_family = rest.rule_family;
      const source =
        snapshot[
          {
            store: "opsMemberships",
            warehouse: "opsWarehouseScopes",
            owner: "opsOwnerAssignments",
          }[kind]
        ] || [];
      const previous = source.find(
        (r) =>
          (kind === "owner" || String(r.user_id) === String(rest.user_id)) &&
          (kind === "warehouse"
            ? r.warehouse_id === rest.warehouse_id
            : r.store_id === rest.store_id) &&
          (kind !== "owner" || r.rule_family === rest.rule_family),
      );
      if (previous) payload.business_id = previous.business_id;
      if (kind !== "owner") payload.status = "active";
      await send("opsConfig", { command, reason, values: payload });
    };
    const accessRows = [
      ...(snapshot.opsMemberships || []).map((r) => ({ ...r, kind: "store" })),
      ...(snapshot.opsWarehouseScopes || []).map((r) => ({
        ...r,
        kind: "warehouse",
      })),
    ];
    const changeAccess = (row) => {
      const values = {
        business_id: row.business_id,
        user_id: row.user_id,
        title: row.title,
        environment: "synthetic",
        status: row.status === "active" ? "inactive" : "active",
      };
      if (row.kind === "store") {
        values.store_id = row.store_id;
        values.membership_role = row.membership_role;
      } else values.warehouse_id = row.warehouse_id;
      return send("opsConfig", {
        command: row.kind === "store" ? "saveMembership" : "saveWarehouseScope",
        reason: `页面${values.status === "inactive" ? "撤销" : "恢复"}测试业务范围授权`,
        values,
      });
    };
    const defaults = {
      R1: { drop_ratio: 0.3, min_baseline_orders: 5 },
      R2: { available_qty_threshold: 5 },
      R3: { increase_ratio: 0.5, min_baseline_refunds: 3 },
    };
    const publish = async (values) => {
      try {
        const { reason, parameters, recovery, ...rest } = values;
        await send("opsRule", {
          command: "publish",
          reason,
          ...rest,
          parameters: JSON.parse(parameters),
          recovery: JSON.parse(recovery),
          environment: "synthetic",
        });
      } catch {
        setFailure("参数或恢复条件不是有效 JSON，请检查格式。");
      }
    };
    const storeEditor = h(
      Form,
      {
        form: storeForm,
        disabled: locked,
        layout: "vertical",
        onFinish: saveStore,
        initialValues: {
          platform: "temu",
          site: "DE",
          timezone: "UTC",
          reason: "测试店铺配置",
        },
      },
      h(
        Form.Item,
        { label: "选择要编辑的测试店铺" },
        h(Select, {
          value: storeSelection,
          allowClear: true,
          placeholder: "留空可新增测试店铺",
          options: storeOptions,
          onChange: (id) => {
            setStoreSelection(id);
            storeForm.resetFields();
            if (id) {
              const s = stores.find((x) => x.business_id === id);
              storeForm.setFieldsValue(
                Object.fromEntries(
                  [
                    "business_id",
                    "title",
                    "connection_id",
                    "erp_store_id",
                    "platform",
                    "site",
                    "timezone",
                  ].map((k) => [k, s[k]]),
                ),
              );
            }
          },
        }),
      ),
      h(Form.Item, { name: "business_id", hidden: true }, h(Input)),
      field(
        "title",
        "店铺名称",
        h(Input, { placeholder: "例如：[测试] Temu 德国 A 店" }),
      ),
      h(
        Space,
        { align: "start", wrap: true },
        field("platform", "平台", h(Input)),
        field("site", "站点", h(Input)),
        field(
          "timezone",
          "业务时区",
          h(Input, { placeholder: "IANA 时区，例如 UTC" }),
        ),
      ),
      field(
        "connection_id",
        "测试连接代号",
        h(Input, { placeholder: "仅代号，不填SID或密钥" }),
      ),
      field(
        "erp_store_id",
        "测试ERP店铺编号",
        h(Input, { placeholder: "测试占位值，未经接口核验" }),
      ),
      field("reason", "修改原因", h(Input)),
      h(
        Button,
        { type: "primary", htmlType: "submit", loading: busy },
        "保存测试店铺",
      ),
    );
    const memberFormView = h(
      Form,
      {
        form: memberForm,
        disabled: locked,
        layout: "vertical",
        onFinish: saveMember,
        initialValues: {
          kind: "store",
          membership_role: "ops_operator",
          reason: "测试人员范围配置",
        },
      },
      field(
        "kind",
        "配置类型",
        h(Select, {
          options: [
            { label: "店铺成员", value: "store" },
            { label: "仓库访问范围", value: "warehouse" },
            { label: "规则负责人", value: "owner" },
          ],
        }),
      ),
      field(
        "user_id",
        "人员",
        h(Select, {
          options: userOptions,
          showSearch: true,
          optionFilterProp: "label",
        }),
      ),
      h(
        Form.Item,
        { noStyle: true, shouldUpdate: true },
        ({ getFieldValue }) => {
          const kind = getFieldValue("kind");
          return h(
            React.Fragment,
            null,
            kind === "warehouse"
              ? field(
                  "warehouse_id",
                  "仓库",
                  h(Select, { options: warehouseOptions }),
                )
              : field("store_id", "店铺", h(Select, { options: storeOptions })),
            kind === "store"
              ? field(
                  "membership_role",
                  "成员职责",
                  h(Select, {
                    options: [
                      { label: "运营", value: "ops_operator" },
                      { label: "主管", value: "ops_supervisor" },
                      { label: "集成服务", value: "ops_integration" },
                    ],
                  }),
                )
              : null,
            kind === "owner"
              ? field(
                  "rule_family",
                  "规则",
                  h(Select, {
                    options: ["R1", "R2", "R3"].map((x) => ({
                      value: x,
                      label: x,
                    })),
                  }),
                )
              : null,
          );
        },
      ),
      field("reason", "修改原因", h(Input)),
      h(
        Button,
        { type: "primary", htmlType: "submit", loading: busy },
        "保存测试授权",
      ),
      h(
        "p",
        { style: { marginTop: 12, color: "#777" } },
        "系统账号与全局角色仍由管理员在 NocoBase 原生用户/角色设置维护。这里管理业务范围，不能给账号提升系统角色。",
      ),
    );
    const memberEditor = h(
      React.Fragment,
      null,
      memberFormView,
      h(Typography.Title, { level: 5 }, "现有业务授权"),
      h(Table, {
        size: "small",
        rowKey: "business_id",
        pagination: { pageSize: 8 },
        dataSource: accessRows,
        columns: [
          {
            title: "人员",
            dataIndex: "user_id",
            render: (id) =>
              users.find((u) => String(u.id) === String(id))?.nickname ||
              `用户 ${id}`,
          },
          {
            title: "业务范围",
            render: (_, r) =>
              r.kind === "store"
                ? stores.find((s) => s.business_id === r.store_id)?.title ||
                  r.store_id
                : `仓库 · ${r.warehouse_id}`,
          },
          {
            title: "状态",
            dataIndex: "status",
            render: (s) =>
              h(
                Tag,
                { color: s === "active" ? "green" : "default" },
                s === "active" ? "有效" : "已撤销",
              ),
          },
          {
            title: "操作",
            render: (_, r) =>
              h(
                Button,
                {
                  size: "small",
                  disabled: locked,
                  danger: r.status === "active",
                  onClick: () => changeAccess(r),
                },
                r.status === "active" ? "撤销授权" : "恢复授权",
              ),
          },
        ],
      }),
      h(
        "p",
        { style: { color: "#777" } },
        "撤销后，已有登录立即失去该业务范围。仓库权限与店铺权限分别管理；需要完全移出人员时，请检查其全部授权。",
      ),
    );
    const latestRules = [
      ...new Map(
        [...(snapshot.opsRules || [])]
          .sort((a, b) => Number(a.version) - Number(b.version))
          .map((r) => [
            JSON.stringify([
              r.family,
              r.store_id || null,
              r.warehouse_id || null,
            ]),
            r,
          ]),
      ).values(),
    ];
    const ruleEditor = h(
      React.Fragment,
      null,
      h(
        Form,
        {
          form: ruleForm,
          disabled: locked,
          layout: "vertical",
          onFinish: publish,
          initialValues: {
            family: "R1",
            metric_version: "test-v1",
            parameters: JSON.stringify(defaults.R1, null, 2),
            recovery: JSON.stringify(
              { observation_hours: 24, required_complete_days: 1 },
              null,
              2,
            ),
            reason: "测试规则发布",
          },
        },
        field(
          "family",
          "规则类型",
          h(Select, {
            options: [
              { value: "R1", label: "R1 · 支付订单下降" },
              { value: "R2", label: "R2 · 可用库存不足" },
              { value: "R3", label: "R3 · 退款申请增加" },
            ],
            onChange: (value) =>
              ruleForm.setFieldsValue({
                parameters: JSON.stringify(defaults[value], null, 2),
              }),
          }),
        ),
        field(
          "store_id",
          "店铺（R1/R3 必填）",
          h(Select, { allowClear: true, options: storeOptions }),
          false,
        ),
        field(
          "warehouse_id",
          "仓库（R2 可选仓库范围）",
          h(Select, { allowClear: true, options: warehouseOptions }),
          false,
        ),
        field("metric_version", "指标口径版本", h(Input)),
        field("parameters", "测试参数（JSON）", h(Input.TextArea, { rows: 4 })),
        field(
          "recovery",
          "观察与恢复条件（JSON）",
          h(Input.TextArea, { rows: 4 }),
        ),
        field("reason", "发布原因", h(Input)),
        h(
          Button,
          { type: "primary", htmlType: "submit", loading: busy },
          "发布为 shadow 测试版本",
        ),
      ),
      h(
        "div",
        { style: { marginTop: 20 } },
        h(Typography.Text, { strong: true }, "测试规则启停"),
        h(Table, {
          size: "small",
          pagination: { pageSize: 5 },
          rowKey: "id",
          dataSource: latestRules,
          columns: [
            { title: "规则", dataIndex: "title" },
            { title: "状态", dataIndex: "status" },
            { title: "版本", dataIndex: "version" },
            {
              title: "操作",
              render: (_, r) =>
                h(
                  Space,
                  null,
                  h(
                    Button,
                    {
                      size: "small",
                      disabled: locked || r.status !== "shadow",
                      onClick: () =>
                        send("opsRule", {
                          command: "enable",
                          rule_id: r.id,
                          reason: "页面启用测试规则",
                        }),
                    },
                    "启用测试",
                  ),
                  h(
                    Button,
                    {
                      size: "small",
                      disabled: locked || r.status === "retired",
                      onClick: () =>
                        send("opsRule", {
                          command: "retire",
                          rule_id: r.id,
                          reason: "页面停用测试规则",
                        }),
                    },
                    "停用",
                  ),
                ),
            },
          ],
        }),
      ),
    );
    const items = [];
    if (snapshot.capabilities?.manageConfig) {
      items.push(
        { key: "stores", label: "店铺管理", children: storeEditor },
        { key: "members", label: "人员与范围", children: memberEditor },
      );
    }
    if (snapshot.capabilities?.publishRules)
      items.push({ key: "rules", label: "规则版本", children: ruleEditor });
    return h(
      Card,
      {
        title: "配置工作区",
        extra: h(Button, { onClick: load, disabled: locked }, "刷新配置"),
      },
      h(Alert, {
        type: "warning",
        showIcon: true,
        message: "测试环境 · 配置版本 " + snapshot.version,
        description:
          "所有配置仅用于测试。ERP店铺身份、时区及规则参数尚未完成真实业务核验，不能启用生产规则。",
        style: { marginBottom: 16 },
      }),
      failure
        ? h(Alert, {
            type: "error",
            message: failure,
            style: { marginBottom: 12 },
          })
        : null,
      pending
        ? h(
            Button,
            {
              type: "primary",
              disabled: busy,
              onClick: () => perform(pending),
              style: { marginBottom: 12 },
            },
            "重试上一操作",
          )
        : null,
      success
        ? h(Alert, {
            type: "success",
            message: success,
            style: { marginBottom: 12 },
          })
        : null,
      items.length
        ? h(Tabs, { items })
        : h(Alert, {
            type: "info",
            message: "当前账号仅可查看配置，没有管理或发布权限。",
          }),
    );
  }
  class PluginOpsClient extends client.Plugin {
    async load() {
      this.app.use(({ children }) =>
        h(
          client.ExtendCollectionsProvider,
          { collections: definitions },
          children,
        ),
      );
      this.app.addComponents({ OpsPageNotice, OpsTimeline, OpsManagement });
    }
  }
  return { default: PluginOpsClient };
});
