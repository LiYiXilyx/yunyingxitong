import test from "node:test";
import assert from "node:assert/strict";
import { login, api, base } from "./backend-helper.ts";
test("business model is readable by authenticated administrator, denies anonymous and direct writes", async () => {
  const denied = await api("opsTasks:list");
  assert.ok([401, 403].includes(denied.status));
  const token = await login();
  const list = await api("opsTasks:list", token);
  assert.equal(list.status, 200);
  assert.ok(Array.isArray((await list.json()).data));
  for (const action of ["create", "update", "destroy", "export", "query"])
    assert.equal(
      (
        await api(`opsTasks:${action}`, token, {
          status: "closed",
          actor: { roles: ["admin"] },
        })
      ).status,
      403,
      action,
    );
});
import { roleToken, accounts } from "./backend-helper.ts";
test("real user roles and memberships isolate store details, assignees and shared warehouse", async () => {
  const a = await roleToken("operatorA"),
    b = await roleToken("operatorB"),
    supervisor = await roleToken("supervisor"),
    integration = await roleToken("integration");
  const read = async (token: string, name = "opsTasks") =>
    (await (await api(`${name}:list?pageSize=200`, token)).json()).data;
  const mine = await read(a);
  assert.equal(mine.length, 1);
  assert.equal(mine[0].title, "合成测试任务A");
  assert.equal(mine[0].created_by_id, accounts().integration.id);
  assert.equal(Number(mine[0].createdById), accounts().integration.id);
  assert.equal(mine[0].assignee_id, accounts().operatorA.id);
  const other = await read(b);
  assert.equal(other.length, 1);
  assert.equal(other[0].title, "合成测试任务B");
  assert.equal(
    (await api(`opsTasks:get?filterByTk=${other[0].id}`, a)).status,
    404,
  );
  const all = await read(supervisor);
  assert.equal(all.length, 3);
  const warehouse = all.find((r: any) => r.scope_type === "warehouse");
  assert.ok(warehouse);
  assert.equal(
    (await api(`opsTasks:get?filterByTk=${warehouse.id}`, a)).status,
    404,
  );
  assert.equal((await read(integration)).length, 2);
  assert.equal((await read(a, "opsIncidents")).length, 1);
  assert.equal((await read(a, "opsDataHealth")).length, 1);
  for (const path of [
    "opsTasks:export",
    "opsTasks:query",
    "opsTasks:update?filterByTk=1",
    "opsTasks:destroy?filterByTk=1",
    "opsEvents:create",
    "opsRules:update?filterByTk=1",
    "opsMemberships:create",
    "users.opsTasks:list",
  ])
    assert.ok(
      [403, 404].includes(
        (
          await api(path, a, {
            roles: ["admin"],
            actor: { roles: ["root"] },
            status: "closed",
          })
        ).status,
      ),
      path,
    );
  assert.equal((await api("opsTasks:list?appends=anything", a)).status, 403);
  const filtered = await api(
    `opsTasks:list?filter=${encodeURIComponent(JSON.stringify({ store_id: other[0].store_id }))}`,
    a,
  );
  assert.equal((await filtered.json()).data.length, 0);
});
test("task timeline uses business UUID and excludes other stores", async () => {
  const token = await roleToken("operatorA");
  const task = (await (await api("opsTasks:list", token)).json()).data[0];
  const events = (
    await (
      await api(
        `opsEvents:list?filter=${encodeURIComponent(JSON.stringify({ task_id: task.business_id }))}`,
        token,
      )
    ).json()
  ).data;
  assert.ok(events.length >= 1);
  assert.ok(
    events.every(
      (e: any) =>
        e.task_id === task.business_id && e.store_id === task.store_id,
    ),
  );
  const b = await roleToken("operatorB");
  const denied = (
    await (
      await api(
        `opsEvents:list?filter=${encodeURIComponent(JSON.stringify({ task_id: task.business_id }))}`,
        b,
      )
    ).json()
  ).data;
  assert.equal(denied.length, 0);
});
test("revoking and restoring membership takes effect immediately for an already logged-in token", async () => {
  const admin = await login(),
    operator = await roleToken("operatorA");
  const snap = async () =>
    (await (await api("opsConfig:snapshot", admin)).json()).data;
  const data = await snap();
  const member = data.opsMemberships.find(
    (m: any) => m.user_id === accounts().operatorA.id,
  );
  const task = (await (await api("opsTasks:list", operator)).json()).data[0];
  const values = {
    business_id: member.business_id,
    store_id: member.store_id,
    user_id: member.user_id,
    membership_role: member.membership_role,
    environment: "synthetic",
  };
  const change = async (status: string) => {
    const version = (await snap()).version;
    return api("opsConfig:command", admin, {
      command: "saveMembership",
      command_id: crypto.randomUUID(),
      expected_version: version,
      reason: "synthetic immediate permission revocation test",
      values: { ...values, status },
    });
  };
  try {
    assert.equal((await change("inactive")).status, 200);
    assert.equal(
      (await (await api("opsTasks:list", operator)).json()).data.length,
      0,
    );
    assert.equal(
      (await api(`opsTasks:get?filterByTk=${task.id}`, operator)).status,
      404,
    );
    assert.ok(
      [403, 404].includes((await api("users.opsTasks:list", operator)).status),
    );
    assert.equal((await api("opsTasks:export", operator)).status, 403);
  } finally {
    assert.equal((await change("active")).status, 200);
  }
  assert.equal(
    (await (await api("opsTasks:list", operator)).json()).data.length,
    1,
  );
});
test("removing the actual operations role denies old tokens despite remaining membership", async () => {
  const admin = await login(),
    operator = await roleToken("operatorA");
  const id = accounts().operatorA.id;
  const setRoles = async (roles: string[]) =>
    api(`users/${id}/roles:set`, admin, roles);
  try {
    assert.equal((await setRoles(["member"])).status, 200);
    for (const path of [
      "opsTasks:list",
      "opsConfig:snapshot",
      "opsEvents:list",
    ])
      assert.equal((await api(path, operator)).status, 403, path);
    const spoof = await fetch(`${base}/api/opsTasks:list`, {
      headers: {
        authorization: `Bearer ${operator}`,
        "x-role": "ops_operator",
      },
    });
    assert.ok([401, 403].includes(spoof.status));
  } finally {
    assert.equal((await setRoles(["ops_operator"])).status, 200);
  }
  assert.equal((await api("opsTasks:list", operator)).status, 200);
});
