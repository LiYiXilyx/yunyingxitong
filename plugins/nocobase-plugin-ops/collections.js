"use strict";
const str = (name) => ({
  name,
  type: "string",
  interface: "input",
  uiSchema: { title: name, type: "string", "x-component": "Input" },
});
const num = (name) => ({
  name,
  type: "integer",
  interface: "integer",
  uiSchema: { title: name, type: "number", "x-component": "InputNumber" },
});
const json = (name) => ({
  name,
  type: "json",
  interface: "json",
  uiSchema: { title: name, "x-component": "Input.JSON" },
});
const common = [
  str("business_id"),
  str("title"),
  str("store_id"),
  str("warehouse_id"),
  str("scope_type"),
  str("status"),
  num("version"),
  { ...str("environment"), defaultValue: "synthetic" },
];
const definitions = {
  opsStores: [
    str("connection_id"),
    str("erp_store_id"),
    str("platform"),
    str("site"),
    str("timezone"),
  ],
  opsMemberships: [num("user_id"), str("membership_role")],
  opsWarehouseScopes: [num("user_id")],
  opsOwnerAssignments: [num("user_id"), str("rule_family")],
  opsRules: [
    str("family"),
    str("metric_version"),
    json("parameters"),
    json("recovery"),
    num("approved_by"),
    str("reason"),
  ],
  opsTasks: [
    num("created_by_id"),
    num("assignee_id"),
    str("incident_id"),
    str("rule_version_id"),
    str("source"),
    str("due_at"),
  ],
  opsIncidents: [str("fingerprint"), str("rule_family")],
  opsOccurrences: [
    str("incident_id"),
    str("evaluation_id"),
    json("observation"),
  ],
  opsActionAttempts: [str("task_id"), num("actor_id"), str("description")],
  opsEffectReviews: [
    str("task_id"),
    str("action_id"),
    json("baseline"),
    json("observation_window"),
    str("result"),
  ],
  opsEvidence: [str("task_id"), str("sha256"), str("media_type")],
  opsEvents: [
    str("task_id"),
    num("actor_id"),
    str("event_type"),
    str("reason"),
    json("payload"),
  ],
  opsDataHealth: [
    str("source"), str("scope_key"), json("health_scope"), str("data_type"), str("health_revision"), str("envelope_hash"), str("last_attempt_at"), str("freshness_deadline"), json("expected_window"), json("missing_fields"), str("error_class"),
    str("last_success_at"),
    str("business_date"),
    json("details"),
  ],
  opsDataIssues: [str("source"), str("description"), str("issue_key"), json("health_scope"), str("data_type"), str("error_class"), str("health_revision"), num("assignee_id")],
  opsConfigVersions: [json("snapshot"), num("actor_id"), str("reason")],
  opsCommandReceipts: [str("command_id"), json("result")],
};
module.exports = Object.entries(definitions).map(([name, fields]) => ({
  name,
  title: name,
  autoGenId: true,
  createdAt: true,
  updatedAt: false,
  ...(name === "opsTasks" ? { createdBy: true } : {}),
  fields: [...common, ...fields],
}));
