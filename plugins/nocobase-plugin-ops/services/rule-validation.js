"use strict";
/** Exact first-phase rule contracts. Values are thresholds, never executable expressions. */
function validateRule(ctx, rule) {
  const { family, parameters: p, recovery: r } = rule;
  const exact = (value, keys) =>
    value &&
    typeof value === "object" &&
    !Array.isArray(value) &&
    Object.keys(value).length === keys.length &&
    keys.every((k) => Object.hasOwn(value, k));
  const integer = (v, min, max = Number.MAX_SAFE_INTEGER) =>
    Number.isSafeInteger(v) && v >= min && v <= max;
  const positive = (v) => typeof v === "number" && Number.isFinite(v) && v > 0;
  if (family === "R1") {
    if (
      !exact(p, ["drop_ratio", "min_baseline_orders"]) ||
      !positive(p.drop_ratio) ||
      p.drop_ratio > 1 ||
      !integer(p.min_baseline_orders, 1)
    )
      ctx.throw(
        400,
        "R1 requires drop_ratio in (0,1] and integer min_baseline_orders >= 1",
      );
  } else if (family === "R2") {
    if (
      !exact(p, ["available_qty_threshold"]) ||
      !integer(p.available_qty_threshold, 0)
    )
      ctx.throw(400, "R2 requires integer available_qty_threshold >= 0");
  } else if (family === "R3") {
    if (
      !exact(p, ["increase_ratio", "min_baseline_refunds"]) ||
      !positive(p.increase_ratio) ||
      !integer(p.min_baseline_refunds, 1)
    )
      ctx.throw(
        400,
        "R3 requires increase_ratio > 0 and integer min_baseline_refunds >= 1",
      );
  } else ctx.throw(400, "Unknown rule family");
  if ((family === "R1" || family === "R3") && !rule.store_id)
    ctx.throw(400, "R1 and R3 require store scope");
  if (!rule.store_id && !rule.warehouse_id)
    ctx.throw(400, "Business scope required");
  if (
    !exact(r, ["observation_hours", "required_complete_days"]) ||
    !integer(r.observation_hours, 1, 8760) ||
    !integer(r.required_complete_days, 1, 366) ||
    r.observation_hours < r.required_complete_days * 24
  )
    ctx.throw(400, "Recovery requires a complete observation window");
  if (
    typeof rule.metric_version !== "string" ||
    !rule.metric_version.trim() ||
    rule.metric_version.length > 120
  )
    ctx.throw(400, "Valid metric_version required");
}
module.exports = { validateRule };
