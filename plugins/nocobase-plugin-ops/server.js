"use strict";
const { Plugin } = require("@nocobase/server");
const collections = require("./collections");
const { identity, scope, visible } = require("./services/access");
class OpsBootstrapPlugin extends Plugin {
  async beforeLoad() {
    this.db.addMigrations({
      namespace: this.name,
      directory: require("path").join(__dirname, "migrations"),
      context: { plugin: this },
    });
    for (const definition of collections) this.db.collection(definition);
  }
  async load() {
    for (const definition of collections)
      await this.db.getCollection(definition.name).sync();
    await require("./migrations/20261022120000-t03-business-integrity").applyBusinessIntegrity(
      this.db,
    );
    await require("./services/data-health").integrity(this.db);
    const db = this.db;
    require("./services/commands").register(this);
    this.app.resourceManager.use(
      async (ctx, next) => {
        const resource = ctx.action?.resourceName || "";
        if (
          resource
            .split(/[.,]/)
            .some((n) => collections.some((c) => c.name === n)) &&
          (resource.includes(".") ||
            !["list", "get"].includes(ctx.action.actionName) && !(resource === "opsDataHealth" && ctx.action.actionName === "ingest"))
        )
          ctx.throw(403, "Business writes and generic operations are disabled");
        await next();
      },
      { tag: "ops-early-guard", before: "validate-filter-params" },
    );
    this.app.resource({
      name: "opsBootstrap",
      actions: {
        async status(ctx) {
          ctx.body = {
            schema_version: "1",
            stage: "T02",
            business_ready: false,
          };
        },
      },
    });
    this.app.acl.allow("opsBootstrap", "status", "loggedIn");
    for (const definition of collections) {
      const name = definition.name;
      const read = async (ctx) => {
        const who = await identity(db, ctx);
        const grants = await scope(db, who);
        const p = ctx.action.params;
        if ((p.appends && p.appends.length) || p.association)
          ctx.throw(403, "Relationship expansion is disabled");
        const rows = await db
          .getRepository(name)
          .find({ filter: p.filter || {}, sort: ["id"] });
        const allowed = [];
        for (const row of rows) {
          if (!visible(row, who, grants, name)) continue;
          if (!who.admin && row.get("task_id")) {
            const task = await db
              .getRepository("opsTasks")
              .findOne({ filter: { business_id: row.get("task_id") } });
            if (!task || !visible(task, who, grants, "opsTasks")) continue;
          }
          allowed.push(row);
        }
        if (ctx.action.actionName === "get" || ctx.action.getName() === "get") {
          const row = allowed.find(
            (r) => String(r.get("id")) === String(p.filterByTk),
          );
          if (!row) ctx.throw(404, "Record not found");
          ctx.body = row.toJSON();
        } else {
          const size = Math.min(Math.max(Number(p.pageSize) || 20, 1), 200);
          const page = Math.max(Number(p.page) || 1, 1);
          ctx.body = {
            count: allowed.length,
            rows: allowed
              .slice((page - 1) * size, page * size)
              .map((r) => r.toJSON()),
            page,
            pageSize: size,
          };
        }
      };
      if (name === "opsDataHealth")
        require("./services/data-health").register(this, { list: read, get: read });
      else this.app.resource({ name, actions: { list: read, get: read } });
      this.app.acl.allow(name, ["list", "get"], "loggedIn");
    }
    this.app.resourceManager.use(
      async (ctx, next) => {
        const resource = ctx.action?.resourceName || "";
        const name = resource.split(/[.,]/)[0];
        if (
          collections.some((c) => c.name === name) ||
          resource
            .split(/[.,]/)
            .some((n) => collections.some((c) => c.name === n))
        ) {
          const who = await identity(db, ctx);
          void who;
          if (
            resource !== name ||
            !["list", "get"].includes(ctx.action.getName()) && !(resource === "opsDataHealth" && ctx.action.getName() === "ingest")
          )
            ctx.throw(
              403,
              "Business writes and generic operations are disabled",
            );
        }
        await next();
      },
      { tag: "ops-scope-guard", after: "auth", before: "acl" },
    );
  }
}
module.exports = OpsBootstrapPlugin;
