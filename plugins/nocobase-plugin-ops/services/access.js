"use strict";
const operationsRoles = Object.freeze([
  "root",
  "admin",
  "ops_supervisor",
  "ops_operator",
  "ops_integration",
]);
const hasOperationsRole = (roles) =>
  roles.some((role) => operationsRoles.includes(role));
async function identity(db, ctx, transaction) {
  const id = ctx.state.currentUser?.id;
  if (!id) ctx.throw(401, "Authentication required");
  const user = await db
    .getRepository("users")
    .findOne({ filterByTk: id, appends: ["roles"], transaction });
  const roles = (user?.get("roles") || []).map((r) =>
    r.get ? r.get("name") : r.name,
  );
  if (!hasOperationsRole(roles))
    ctx.throw(403, "An operations role is required");
  return {
    id,
    roles,
    admin: roles.includes("root") || roles.includes("admin"),
    supervisor: roles.includes("ops_supervisor"),
    integration: roles.includes("ops_integration"),
  };
}
async function scope(db, who, transaction) {
  if (who.admin) return null;
  const memberships = await db
    .getRepository("opsMemberships")
    .find({ filter: { user_id: who.id, status: "active" }, transaction });
  const warehouses = await db
    .getRepository("opsWarehouseScopes")
    .find({ filter: { user_id: who.id, status: "active" }, transaction });
  return {
    stores: new Set(memberships.map((r) => r.get("store_id"))),
    warehouses: new Set(warehouses.map((r) => r.get("warehouse_id"))),
  };
}
function visible(row, who, grants, name) {
  if (who.admin) return true;
  const r = row.toJSON ? row.toJSON() : row;
  if (name === "opsMemberships" || name === "opsWarehouseScopes")
    return String(r.user_id) === String(who.id);
  if (name === "opsConfigVersions" || name === "opsCommandReceipts")
    return false;
  if (r.health_scope && (!r.health_scope.store_ids.every(id => grants.stores.has(id)) || !r.health_scope.warehouse_ids.every(id => grants.warehouses.has(id)))) return false;
  if (r.warehouse_id && !grants.warehouses.has(r.warehouse_id)) return false;
  if (r.store_id && !grants.stores.has(r.store_id)) return false;
  if (!r.store_id && !r.warehouse_id) return false;
  if (
    name === "opsTasks" &&
    !who.supervisor &&
    !who.integration &&
    String(r.assignee_id) !== String(who.id)
  )
    return false;
  return true;
}
module.exports = { identity, scope, visible, hasOperationsRole };
