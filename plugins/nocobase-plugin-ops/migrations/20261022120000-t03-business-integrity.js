"use strict";
const { Migration } = require("@nocobase/server");
const definitions = require("../collections");
async function applyBusinessIntegrity(db) {
  const generator = db.sequelize.getQueryInterface().queryGenerator;
  const index = async (name, collection, fields) => {
    const table = generator.quoteTable(
      db.getCollection(collection).model.getTableName(),
    );
    const columns = fields.map((f) => generator.quoteIdentifier(f)).join(", ");
    await db.sequelize.query(
      `CREATE UNIQUE INDEX IF NOT EXISTS ${generator.quoteIdentifier(name)} ON ${table} (${columns})`,
    );
  };
  for (const { name } of definitions)
    await index(`t03_${name}_business_id_unique`, name, ["business_id"]);
  await index("t03_store_connection_erp_unique", "opsStores", [
    "connection_id",
    "erp_store_id",
  ]);
  await index("t03_store_scope_unique", "opsStores", ["store_id"]);
  await index("t03_membership_user_store_unique", "opsMemberships", [
    "user_id",
    "store_id",
  ]);
  await index("t03_warehouse_user_scope_unique", "opsWarehouseScopes", [
    "user_id",
    "warehouse_id",
  ]);
}
class BusinessIntegrityMigration extends Migration {
  on = "afterLoad";
  async up() {
    await applyBusinessIntegrity(this.db);
  }
}
module.exports = BusinessIntegrityMigration;
module.exports.default = BusinessIntegrityMigration;
module.exports.applyBusinessIntegrity = applyBusinessIntegrity;
