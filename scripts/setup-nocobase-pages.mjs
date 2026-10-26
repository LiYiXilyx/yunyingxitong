import { mkdirSync, writeFileSync } from "node:fs";
import { client } from "./lib/nocobase-api.mjs";
import { pageSpecs, pageSchema, routeSpec } from "../config/nocobase-pages.mjs";
const request = await client();
const replace = process.argv.includes("--replace-pages");
const refreshHealth = process.argv.includes("--refresh-health");
const allRoles = (await request("roles", "list", { params: { pageSize: 200 } }))
  .data;
for (const name of [
  "member",
  "ops_operator",
  "ops_supervisor",
  "ops_integration",
]) {
  if (allRoles.some((r) => r.name === name))
    await request("roles", "update", {
      params: { filterByTk: name },
      values: { allowNewMenu: false },
    });
}
const pages = [];
const schemas = [];
for (const spec of pageSpecs) {
  const schema = pageSchema(spec);
  schemas.push(schema);
  const existing = (
    await request("desktopRoutes", "list", {
      params: { filter: { schemaUid: schema["x-uid"] }, pageSize: 10 },
    })
  ).data;
  if (existing.length > 1) throw Error("Duplicate managed page: " + spec.key);
  let route = existing[0];
  if (!route) {
    route = (
      await request("desktopRoutes", "create", { values: routeSpec(spec) })
    ).data;
  }
  let current;
  try {
    current = (
      await request("uiSchemas", `getJsonSchema/${schema["x-uid"]}`, {
        params: { includeAsyncNode: true },
      })
    ).data;
  } catch (e) {
    if (!e.message.includes("404")) throw e;
  }
  if (current?.["x-uid"] && (replace || (refreshHealth && spec.key === "health"))) {
    const dir = new URL("../.local/ui-backups/", import.meta.url);
    mkdirSync(dir, { recursive: true, mode: 0o700 });
    writeFileSync(
      new URL(`${schema["x-uid"]}-${Date.now()}.json`, dir),
      JSON.stringify(current, null, 2),
      { mode: 0o600 },
    );
    await request("uiSchemas", `remove/${schema["x-uid"]}`, { values: {} });
    current = null;
  }
  if (!current?.["x-uid"])
    await request("uiSchemas", "insert", { values: schema });
  pages.push(route);
  console.log("Ready page: " + spec.title);
}
for (const name of [
  "member",
  "ops_operator",
  "ops_supervisor",
  "ops_integration",
]) {
  if (!allRoles.some((r) => r.name === name)) continue;
  const existing = (
    await request(`roles/${name}/desktopRoutes`, "list", {
      params: { pageSize: 2000 },
    })
  ).data;
  const preserved = existing
    .filter((r) => !String(r.schemaUid || "").startsWith("ops_t03_"))
    .map((r) => r.id);
  const allowed =
    name === "ops_supervisor"
      ? pages
      : name === "ops_operator"
        ? pages.filter((r) => r.schemaUid !== "ops_t03_settings")
        : [];
  await request(`roles/${name}/desktopRoutes`, "set", {
    values: [...new Set([...preserved, ...allowed.map((r) => r.id)])],
  });
}
writeFileSync(
  new URL("../docs/nocobase-config/pages.json", import.meta.url),
  JSON.stringify(schemas, null, 2) + "\n",
);
console.log(
  "Native pages and role menus configured. Existing unmanaged pages were preserved.",
);
