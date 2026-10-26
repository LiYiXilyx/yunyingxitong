"use strict";
const { createHash, randomUUID } = require("crypto");
const { identity, scope, visible, hasOperationsRole } = require("./access");
const { validateRule } = require("./rule-validation");
const sets = [
  "opsStores",
  "opsMemberships",
  "opsWarehouseScopes",
  "opsOwnerAssignments",
  "opsRules",
];
const canonical = (v) =>
  Array.isArray(v)
    ? v.map(canonical)
    : v && typeof v === "object"
      ? Object.fromEntries(
          Object.keys(v)
            .sort()
            .map((k) => [k, canonical(v[k])]),
        )
      : v;
const hash = (v) =>
  createHash("sha256")
    .update(JSON.stringify(canonical(v)))
    .digest("hex");
async function currentVersion(db, transaction) {
  const row = await db
    .getRepository("opsConfigVersions")
    .findOne({ sort: ["-version"], transaction });
  return row?.get("version") || 0;
}
async function snapshot(db, who, transaction) {
  const grants = await scope(db, who, transaction);
  const result = {
    version: await currentVersion(db, transaction),
    capabilities: {
      manageConfig: who.admin,
      publishRules: who.admin || who.supervisor,
    },
  };
  for (const name of sets) {
    result[name] = (await db.getRepository(name).find({ transaction }))
      .filter((r) => visible(r, who, grants, name))
      .map((r) => r.toJSON());
  }
  const latest = new Map();
  for (const rule of result.opsRules) {
    const key = JSON.stringify([
      rule.family,
      rule.store_id || null,
      rule.warehouse_id || null,
    ]);
    if (!latest.has(key) || latest.get(key).version < rule.version)
      latest.set(key, rule);
  }
  result.activeRules = Array.from(latest.values()).filter(
    (rule) => rule.status === "enabled",
  );
  if (who.admin || who.supervisor) {
    const members = await db
      .getRepository("opsMemberships")
      .find({ filter: { status: "active" }, transaction });
    const ids = new Set(
      members
        .filter((r) => who.admin || visible(r, who, grants, "opsStores"))
        .map((r) => Number(r.get("user_id"))),
    );
    result.users = (await db.getRepository("users").find({ transaction }))
      .filter((u) => who.admin || ids.has(Number(u.id)))
      .map((u) => ({ id: u.id, nickname: u.get("nickname") }));
  }
  return result;
}
const isUUID = (v) =>
  typeof v === "string" &&
  /^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(
    v,
  );
function register(plugin) {
  const db = plugin.db;
  const execute = (kind) => async (ctx) => {
    const who = await identity(db, ctx);
    if (!who.admin && !who.supervisor) ctx.throw(403, "Supervisor required");
    if (kind === "config" && !who.admin)
      ctx.throw(
        403,
        "Administrator required for membership and configuration changes",
      );
    const input = ctx.action.params.values || {};
    if (
      !input.command_id ||
      typeof input.command_id !== "string" ||
      input.command_id.length > 120 ||
      !Number.isInteger(input.expected_version) ||
      !input.reason ||
      typeof input.reason !== "string"
    )
      ctx.throw(400, "command_id, expected_version and reason are required");
    const result = await db.sequelize.transaction(async (transaction) => {
      // Serialize authoritative configuration changes across processes, not just requests.
      await db.sequelize.query("SELECT pg_advisory_xact_lock(734203)", {
        transaction,
      });
      const receipts = db.getRepository("opsCommandReceipts");
      const receipt = await receipts.findOne({
        filter: { business_id: input.command_id },
        transaction,
      });
      const digest = hash({ kind, actor: who.id, input });
      if (receipt) {
        if (receipt.get("title") !== digest)
          ctx.throw(409, "command_id already used with different input");
        const output = receipt.get("result");
        if (
          kind === "rule" &&
          (!output.rule ||
            !visible(output.rule, who, await scope(db, who), "opsRules"))
        )
          ctx.throw(403, "Scope denied for command replay");
        return output;
      }
      const version = await currentVersion(db, transaction);
      if (version !== input.expected_version)
        ctx.throw(409, "Configuration version conflict");
      let rule;
      let configScope;
      if (kind === "rule") {
        if (!["publish", "enable", "retire"].includes(input.command))
          ctx.throw(400, "Unknown rule command");
        let values;
        if (input.command === "publish") {
          if (
            !["R1", "R2", "R3"].includes(input.family) ||
            !input.metric_version ||
            !input.parameters ||
            typeof input.parameters !== "object" ||
            Array.isArray(input.parameters) ||
            !Object.keys(input.parameters).length ||
            !input.recovery ||
            typeof input.recovery !== "object"
          )
            ctx.throw(
              400,
              "Rule family, metric version, parameters and recovery are required",
            );
          values = {
            store_id: input.store_id || null,
            warehouse_id: input.warehouse_id || null,
            family: input.family,
            metric_version: input.metric_version,
            parameters: input.parameters,
            recovery: input.recovery,
            environment: input.environment || "shadow",
            status: "shadow",
          };
        } else {
          const previous = await db
            .getRepository("opsRules")
            .findOne({ filterByTk: input.rule_id, transaction });
          if (!previous) ctx.throw(404, "Rule not found");
          values = previous.toJSON();
          delete values.id;
          delete values.createdAt;
          if (!visible(values, who, await scope(db, who), "opsRules"))
            ctx.throw(403, "Scope denied");
          const latest = await db.getRepository("opsRules").findOne({
            filter: {
              family: values.family,
              store_id: values.store_id || null,
              warehouse_id: values.warehouse_id || null,
            },
            sort: ["-version"],
            transaction,
          });
          if (!latest || String(latest.id) !== String(previous.id))
            ctx.throw(409, "Rule command requires the current latest version");
          if (input.command === "enable" && values.status !== "shadow")
            ctx.throw(409, "Only the current shadow rule can be enabled");
          if (values.status === "retired")
            ctx.throw(409, "Retired rule cannot be changed");
          values.status = input.command === "enable" ? "enabled" : "retired";
        }
        if (input.command !== "retire") validateRule(ctx, values);
        if (!values.store_id && !values.warehouse_id)
          ctx.throw(400, "Business scope is required");
        const grants = await scope(db, who);
        if (!visible(values, who, grants, "opsRules"))
          ctx.throw(403, "Scope denied");
        if (values.environment !== "synthetic")
          ctx.throw(
            403,
            "Real business authorization is pending; only explicit synthetic scope is permitted",
          );
        if (values.store_id) {
          const store = await db
            .getRepository("opsStores")
            .findOne({ filter: { store_id: values.store_id }, transaction });
          if (!store || store.get("environment") !== "synthetic")
            ctx.throw(403, "Synthetic store required");
        }
        if (values.warehouse_id) {
          const warehouse = await db
            .getRepository("opsWarehouseScopes")
            .findOne({
              filter: {
                warehouse_id: values.warehouse_id,
                environment: "synthetic",
              },
              transaction,
            });
          if (!warehouse) ctx.throw(403, "Synthetic warehouse required");
        }
        rule = await db.getRepository("opsRules").create({
          values: {
            ...values,
            business_id: randomUUID(),
            title: `${values.family} ${input.command}`,
            version: version + 1,
            approved_by: who.id,
            reason: input.reason,
          },
          transaction,
        });
      } else {
        if (!who.admin)
          ctx.throw(
            403,
            "Administrator required for membership and configuration changes",
          );
        const mapping = {
          saveStore: "opsStores",
          saveMembership: "opsMemberships",
          saveWarehouseScope: "opsWarehouseScopes",
          saveOwnerAssignment: "opsOwnerAssignments",
        };
        const name = mapping[input.command];
        if (!name || !input.values || typeof input.values !== "object")
          ctx.throw(400, "Unknown configuration command");
        const allowed = {
          opsStores: [
            "business_id",
            "title",
            "store_id",
            "connection_id",
            "erp_store_id",
            "platform",
            "site",
            "timezone",
            "environment",
          ],
          opsMemberships: [
            "business_id",
            "title",
            "store_id",
            "user_id",
            "membership_role",
            "environment",
            "status",
          ],
          opsWarehouseScopes: [
            "business_id",
            "title",
            "warehouse_id",
            "user_id",
            "environment",
            "status",
          ],
          opsOwnerAssignments: [
            "business_id",
            "title",
            "store_id",
            "warehouse_id",
            "user_id",
            "rule_family",
            "environment",
          ],
        };
        const fields = allowed[name];
        const values = {};
        for (const [key, value] of Object.entries(input.values)) {
          if (!fields.includes(key)) ctx.throw(400, `Unknown field ${key}`);
          values[key] = value;
        }
        if (!isUUID(values.business_id))
          ctx.throw(400, "Valid business_id required");
        const repo = db.getRepository(name);
        const existing = await repo.findOne({
          filter: { business_id: values.business_id },
          transaction,
        });
        // Updates retain omitted fields. Validate the complete resulting scope, not only the patch.
        if (existing)
          for (const field of fields)
            if (
              !Object.hasOwn(values, field) &&
              existing.get(field) !== undefined
            )
              values[field] = existing.get(field);
        if (values.environment !== "synthetic")
          ctx.throw(
            403,
            "Only explicit synthetic configuration is permitted before authorization",
          );
        if (
          !isUUID(values.business_id) ||
          (!values.store_id && !values.warehouse_id) ||
          (values.store_id && !isUUID(values.store_id)) ||
          (values.warehouse_id && !isUUID(values.warehouse_id))
        )
          ctx.throw(400, "business_id and scope required");
        if (name === "opsStores" && values.business_id !== values.store_id)
          ctx.throw(400, "Store business_id must equal store_id");
        if (
          name !== "opsStores" &&
          values.store_id &&
          !(await db
            .getRepository("opsStores")
            .findOne({ filter: { business_id: values.store_id }, transaction }))
        )
          ctx.throw(400, "Store not found");
        if (name === "opsStores") {
          if (!values.connection_id || !values.erp_store_id || !values.timezone)
            ctx.throw(400, "Connection, ERP store and timezone required");
          try {
            new Intl.DateTimeFormat("en", { timeZone: values.timezone });
          } catch {
            ctx.throw(400, "Invalid IANA timezone");
          }
          const duplicate = await db.getRepository("opsStores").findOne({
            filter: {
              connection_id: values.connection_id,
              erp_store_id: values.erp_store_id,
            },
            transaction,
          });
          if (duplicate && duplicate.get("business_id") !== values.business_id)
            ctx.throw(409, "Connection and ERP store already bound");
        }
        if (
          ["opsMemberships", "opsWarehouseScopes"].includes(name) &&
          values.status !== undefined &&
          !["active", "inactive"].includes(values.status)
        )
          ctx.throw(400, "Membership status must be active or inactive");
        if (
          name === "opsMemberships" &&
          !["ops_supervisor", "ops_operator", "ops_integration"].includes(
            values.membership_role,
          )
        )
          ctx.throw(400, "Unknown membership role");
        if (
          [
            "opsMemberships",
            "opsWarehouseScopes",
            "opsOwnerAssignments",
          ].includes(name) &&
          (!Number.isInteger(values.user_id) ||
            !(await db
              .getRepository("users")
              .findOne({ filterByTk: values.user_id, transaction })))
        )
          ctx.throw(400, "Valid user_id required");
        if (name === "opsOwnerAssignments") {
          if (!["R1", "R2", "R3", "DATA"].includes(values.rule_family))
            ctx.throw(400, "Unknown owner rule family");
          const user = await db.getRepository("users").findOne({
            filterByTk: values.user_id,
            appends: ["roles"],
            transaction,
          });
          const targetRoles = user.get("roles").map((role) => role.get("name"));
          if (!hasOperationsRole(targetRoles))
            ctx.throw(400, "Owner requires an operations role");
          const admin = user
            .get("roles")
            .some((r) => ["root", "admin"].includes(r.get("name")));
          if (
            !admin &&
            values.store_id &&
            !(await db.getRepository("opsMemberships").findOne({
              filter: {
                user_id: values.user_id,
                store_id: values.store_id,
                status: "active",
              },
              transaction,
            }))
          )
            ctx.throw(400, "Owner requires store membership");
          if (
            !admin &&
            values.warehouse_id &&
            !(await db.getRepository("opsWarehouseScopes").findOne({
              filter: {
                user_id: values.user_id,
                warehouse_id: values.warehouse_id,
                status: "active",
              },
              transaction,
            }))
          )
            ctx.throw(400, "Owner requires warehouse scope");
        }
        configScope = values;
        if (existing)
          await existing.update(
            { ...values, version: version + 1 },
            { transaction },
          );
        else
          await repo.create({
            values: {
              ...(["opsMemberships", "opsWarehouseScopes"].includes(name)
                ? { status: "active" }
                : {}),
              ...values,
              version: version + 1,
            },
            transaction,
          });
      }
      await db.getRepository("opsEvents").create({
        values: {
          business_id: `command-${input.command_id}`,
          title: `${kind}:${input.command}`,
          store_id: rule?.get("store_id") || configScope?.store_id,
          warehouse_id: rule?.get("warehouse_id") || configScope?.warehouse_id,
          actor_id: who.id,
          event_type: `${kind}.${input.command}`,
          reason: input.reason,
          version: version + 1,
          environment: "synthetic",
          payload: { command_id: input.command_id, rule_id: rule?.id },
        },
        transaction,
      });
      const output = {
        version: version + 1,
        ...(rule ? { rule: rule.toJSON() } : { saved: true }),
      };
      await db.getRepository("opsConfigVersions").create({
        values: {
          business_id: `config-${version + 1}`,
          version: version + 1,
          actor_id: who.id,
          reason: input.reason,
          environment: "synthetic",
          snapshot: {
            ...(await snapshot(db, { ...who, admin: true }, transaction)),
            version: version + 1,
          },
        },
        transaction,
      });
      await receipts.create({
        values: {
          business_id: input.command_id,
          title: digest,
          result: output,
          environment: "synthetic",
        },
        transaction,
      });
      return output;
    });
    ctx.body = result;
  };
  plugin.app.resource({
    name: "opsRule",
    actions: { command: execute("rule") },
  });
  plugin.app.resource({
    name: "opsConfig",
    actions: {
      command: execute("config"),
      async snapshot(ctx) {
        ctx.body = await db.sequelize.transaction(
          { isolationLevel: "REPEATABLE READ", readOnly: true },
          async (transaction) =>
            snapshot(db, await identity(db, ctx, transaction), transaction),
        );
      },
    },
  });
  plugin.app.acl.allow("opsRule", "command", "loggedIn");
  plugin.app.acl.allow("opsConfig", ["command", "snapshot"], "loggedIn");
}
module.exports = { register };
