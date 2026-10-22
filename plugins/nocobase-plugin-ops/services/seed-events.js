"use strict";
// Trusted idempotent event repair; no user or credential changes.
(async () => {
  const { Application } = require("@nocobase/server");
  const { getConfig } = require("@nocobase/app/lib/config");
  const app = new Application(await getConfig());
  await app.load();
  const tasks = await app.db
    .getRepository("opsTasks")
    .find({ filter: { environment: "synthetic" } });
  for (const task of tasks)
    await task.update({
      status: "todo",
      createdById: task.get("created_by_id"),
    });
  for (const store of await app.db
    .getRepository("opsStores")
    .find({ filter: { environment: "synthetic" } }))
    await store.update({ platform: "temu", site: "DE", timezone: "UTC" });
  for (const health of await app.db
    .getRepository("opsDataHealth")
    .find({ filter: { environment: "synthetic" } }))
    await health.update({ status: "needs_user" });
  const events = await app.db
    .getRepository("opsEvents")
    .find({ filter: { event_type: "created", environment: "synthetic" } });
  for (const event of events) {
    const task = tasks.find(
      (t) =>
        t.get("store_id") === event.get("store_id") &&
        t.get("warehouse_id") === event.get("warehouse_id"),
    );
    if (task) await event.update({ task_id: task.get("business_id") });
  }
  await app.destroy();
  console.log("Synthetic event references repaired");
})().catch(() => {
  console.error("Synthetic event repair failed");
  process.exit(1);
});
