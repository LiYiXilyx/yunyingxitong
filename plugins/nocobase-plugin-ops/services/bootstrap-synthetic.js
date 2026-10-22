"use strict";
// Trusted container-only bootstrap. Never registered as an HTTP action.
const { randomBytes, createHash } = require("crypto");
const fs = require("fs");
async function bootstrap(app, output) {
  if (!output)
    throw Error(
      "A local credential output path is required before creating users",
    );
  const db = app.db;
  const accounts =
    output && fs.existsSync(output)
      ? JSON.parse(fs.readFileSync(output, "utf8"))
      : {};
  const persist = () => {
    if (!output) return;
    const temporary = `${output}.${process.pid}.${randomBytes(8).toString("hex")}.tmp`;
    fs.writeFileSync(temporary, JSON.stringify(accounts), {
      mode: 0o600,
      flag: "wx",
    });
    fs.renameSync(temporary, output);
    fs.chmodSync(output, 0o600);
  };
  const names = {
    supervisor: "ops_supervisor",
    operatorA: "ops_operator",
    operatorB: "ops_operator",
    integration: "ops_integration",
  };
  for (const [key, role] of Object.entries(names)) {
    const roles = db.getRepository("roles");
    if (!(await roles.findOne({ filterByTk: role })))
      await roles.create({ values: { name: role, title: role } });
    const email = `t03-${key.toLowerCase()}@synthetic.local`;
    const password =
      accounts[key]?.password || randomBytes(24).toString("base64url");
    let user = await db.getRepository("users").findOne({ filter: { email } });
    if (user && !accounts[key])
      throw Error(
        "Existing synthetic user has no local credential record; refusing password rotation",
      );
    accounts[key] = { email, password, ...(user ? { id: user.id } : {}) };
    persist();
    if (!user)
      user = await db
        .getRepository("users")
        .create({
          values: {
            email,
            username: `t03_${key}`,
            nickname: `synthetic ${key}`,
            password,
          },
        });
    await user.setRoles([role]);
    accounts[key] = { email, password, id: user.id };
    persist();
  }
  const uuid = (key) => {
    const h = createHash("sha256").update(key).digest("hex");
    return `${h.slice(0, 8)}-${h.slice(8, 12)}-4${h.slice(13, 16)}-a${h.slice(17, 20)}-${h.slice(20, 32)}`;
  };
  const stores = { A: uuid("synthetic-store-A"), B: uuid("synthetic-store-B") };
  const warehouse = uuid("synthetic-warehouse-W");
  const put = async (name, key, values) => {
    key = uuid(key);
    const repo = db.getRepository(name);
    const old = await repo.findOne({ filter: { business_id: key } });
    if (old) {
      await old.update(values);
      return old;
    }
    return repo.create({
      values: {
        business_id: key,
        environment: "synthetic",
        status: "active",
        version: 1,
        ...values,
      },
      ...(name === "opsTasks"
        ? {
            context: {
              state: { currentUser: { id: accounts.integration.id } },
            },
          }
        : {}),
    });
  };
  for (const store of ["A", "B"]) {
    await put("opsStores", `synthetic-store-${store}`, {
      title: `合成测试店${store}`,
      store_id: stores[store],
      connection_id: "synthetic",
      erp_store_id: stores[store],
      platform: "temu",
      site: "DE",
      timezone: "UTC",
    });
    for (const key of ["supervisor", "integration", `operator${store}`])
      await put("opsMemberships", `${key}-${store}`, {
        store_id: stores[store],
        user_id: accounts[key].id,
        membership_role: names[key],
      });
    await put("opsTasks", `synthetic-task-${store}`, {
      title: `合成测试任务${store}`,
      store_id: stores[store],
      scope_type: "store",
      assignee_id: accounts[`operator${store}`].id,
      source: "synthetic-integration",
      created_by_id: accounts.integration.id,
      status: "todo",
    });
    await put("opsIncidents", `synthetic-incident-${store}`, {
      title: `合成异常${store}`,
      store_id: stores[store],
      status: "open",
      fingerprint: `synthetic-${store}`,
    });
    await put("opsDataHealth", `synthetic-health-${store}`, {
      title: `合成数据健康${store}`,
      store_id: stores[store],
      status: "needs_user",
      source: "synthetic",
      details: { synthetic: true },
    });
  }
  await put("opsWarehouseScopes", "supervisor-W", {
    user_id: accounts.supervisor.id,
    warehouse_id: warehouse,
  });
  await put("opsTasks", "synthetic-task-warehouse", {
    title: "合成共仓任务",
    warehouse_id: warehouse,
    scope_type: "warehouse",
    assignee_id: accounts.operatorA.id,
    status: "todo",
    source: "synthetic-integration",
    created_by_id: accounts.integration.id,
  });
  for (const task of await db
    .getRepository("opsTasks")
    .find({ filter: { environment: "synthetic" } })) {
    await put("opsEvents", `created-${task.id}`, {
      title: "集成账号创建（合成）",
      store_id: task.store_id,
      warehouse_id: task.warehouse_id,
      task_id: task.business_id,
      actor_id: accounts.integration.id,
      event_type: "created",
      reason: "synthetic bootstrap",
    });
  }
  persist();
  return { created: true, synthetic: true };
}
module.exports = { bootstrap };
if (require.main === module)
  (async () => {
    const { Application } = require("@nocobase/server");
    const { getConfig } = require("@nocobase/app/lib/config");
    const app = new Application(await getConfig());
    await app.load();
    await bootstrap(app, process.argv[2]);
    await app.destroy();
    console.log("Synthetic bootstrap completed");
  })().catch(() => {
    console.error("Synthetic bootstrap failed");
    process.exit(1);
  });
