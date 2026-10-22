import test from "node:test";
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { client } from "../../scripts/lib/nocobase-api.mjs";
const accounts = JSON.parse(
  readFileSync(
    new URL("../../.local/secrets/t03-accounts.json", import.meta.url),
    "utf8",
  ),
);
const expected = ["ops_t03_tasks", "ops_t03_incidents", "ops_t03_health"];
function ids(rows) {
  return rows.flatMap((r) => [r.schemaUid, ...ids(r.children || [])]);
}
test("native menu authorizes operators only to work pages, supervisors also to management", async () => {
  const operator = await client(accounts.operatorA);
  const supervisor = await client(accounts.supervisor);
  const own = ids((await operator("desktopRoutes", "listAccessible")).data);
  const boss = ids((await supervisor("desktopRoutes", "listAccessible")).data);
  for (const id of expected) {
    assert.ok(own.includes(id), `operator missing ${id}`);
    assert.ok(boss.includes(id));
  }
  assert.ok(
    !own.includes("ops_t03_settings"),
    "operator must not receive management menu",
  );
  assert.ok(
    boss.includes("ops_t03_settings"),
    "supervisor should receive management menu",
  );
});
test("enabled project client has a loadable browser entry and all four page schemas exist", async () => {
  const entry = await fetch(
    "http://127.0.0.1:13000/static/plugins/@project2/plugin-ops/dist/client/index.js",
  );
  assert.equal(entry.status, 200);
  assert.match(await entry.text(), /define\(["']@project2\/plugin-ops["']/);
  const request = await client();
  for (const id of [...expected, "ops_t03_settings"]) {
    const schema = await request("uiSchemas", `getJsonSchema/${id}`, {
      params: { includeAsyncNode: true },
    });
    assert.equal(schema.data["x-uid"], id);
    assert.equal(schema.data["x-component"], "Page");
  }
});
