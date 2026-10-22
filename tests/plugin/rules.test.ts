import test from "node:test";
import assert from "node:assert/strict";
import { login, api } from "./backend-helper.ts";
test("rule command publishes shadow immutable versions and rejects stale or production enable", async () => {
  const token = await login();
  const snap = await api("opsConfig:snapshot", token);
  assert.equal(snap.status, 200);
  let version = (await snap.json()).data.version;
  const body = {
    command: "publish",
    command_id: `publish-${Date.now()}`,
    expected_version: version,
    store_id: "858f0efd-4409-406c-adfb-28490350fd39",
    family: "R1",
    metric_version: "synthetic-v1",
    parameters: { drop_ratio: 0.3, min_baseline_orders: 10 },
    recovery: { observation_hours: 24, required_complete_days: 1 },
    reason: "synthetic test",
    environment: "synthetic",
  };
  const publish = await api("opsRule:command", token, body);
  assert.equal(publish.status, 200);
  const result = (await publish.json()).data;
  assert.equal(result.rule.status, "shadow");
  assert.equal(result.version, version + 1);
  const replay = await api(
    "opsRule:command",
    token,
    Object.fromEntries(Object.entries(body).reverse()),
  );
  assert.deepEqual((await replay.json()).data, result);
  const stale = await api("opsRule:command", token, {
    ...body,
    command_id: `stale-${Date.now()}`,
  });
  assert.equal(stale.status, 409);
  const enable = await api("opsRule:command", token, {
    ...body,
    command: "enable",
    command_id: `enable-${Date.now()}`,
    expected_version: result.version,
    rule_id: result.rule.id,
  });
  assert.equal(enable.status, 200);
  assert.equal((await enable.json()).data.rule.status, "enabled");
  const production = await api("opsRule:command", token, {
    ...body,
    command_id: `prod-${Date.now()}`,
    expected_version: result.version + 1,
    environment: "production",
  });
  assert.equal(production.status, 403);
});
import { roleToken, accounts } from "./backend-helper.ts";
test("operator cannot spoof publisher role and supervisor cannot change membership", async () => {
  const operator = await roleToken("operatorA"),
    supervisor = await roleToken("supervisor");
  assert.equal(
    (
      await api("opsRule:command", operator, {
        command: "publish",
        actor: { roles: ["root"] },
        roles: ["admin"],
      })
    ).status,
    403,
  );
  const snapshot = await (await api("opsConfig:snapshot", supervisor)).json();
  assert.equal(
    (
      await api("opsConfig:command", supervisor, {
        command: "saveMembership",
        command_id: `deny-${Date.now()}`,
        expected_version: snapshot.data.version,
        reason: "test",
        values: {},
      })
    ).status,
    403,
  );
});
test("snapshot directory is role limited and config rejects injected fields", async () => {
  const admin = await login(),
    supervisor = await roleToken("supervisor"),
    operator = await roleToken("operatorA"),
    integration = await roleToken("integration");
  for (const token of [admin, supervisor]) {
    const data = (await (await api("opsConfig:snapshot", token)).json()).data;
    assert.ok(Array.isArray(data.users));
    assert.ok(data.users.every((u: any) => !("password" in u)));
  }
  for (const token of [operator, integration])
    assert.equal(
      (await (await api("opsConfig:snapshot", token)).json()).data.users,
      undefined,
    );
  const version = (await (await api("opsConfig:snapshot", admin)).json()).data
    .version;
  const r = await api("opsConfig:command", admin, {
    command: "saveMembership",
    command_id: `inject-${Date.now()}`,
    expected_version: version,
    reason: "test",
    values: {
      business_id: "11111111-1111-4111-a111-111111111111",
      store_id: "22222222-2222-4222-a222-222222222222",
      environment: "synthetic",
      user_id: 1,
      version: 999,
      roles: ["root"],
    },
  });
  assert.equal(r.status, 400);
});
test("concurrent config commands serialize and rollback leaves no version or event", async () => {
  const token = await login();
  const snapshot = () =>
    api("opsConfig:snapshot", token)
      .then((r) => r.json())
      .then((r) => r.data);
  const before = await snapshot();
  const eventCount = async () =>
    (await (await api("opsEvents:list", token)).json()).meta.count;
  const events = await eventCount();
  const command = {
    command: "publish",
    expected_version: before.version,
    store_id: before.opsStores[0].store_id,
    family: "R2",
    metric_version: "synthetic-v1",
    parameters: { available_qty_threshold: 1 },
    recovery: { observation_hours: 24, required_complete_days: 1 },
    reason: "concurrency synthetic",
    environment: "synthetic",
  };
  const responses = await Promise.all([
    api("opsRule:command", token, {
      ...command,
      command_id: `parallel-a-${Date.now()}`,
    }),
    api("opsRule:command", token, {
      ...command,
      command_id: `parallel-b-${Date.now()}`,
    }),
  ]);
  assert.deepEqual(responses.map((r) => r.status).sort(), [200, 409]);
  const after = await snapshot();
  assert.equal(after.version, before.version + 1);
  assert.equal(await eventCount(), events + 1);
  const result = (
    await (
      await api("opsRule:command", token, {
        command: "retire",
        command_id: `retire-${Date.now()}`,
        expected_version: after.version,
        rule_id: (await responses.find((r) => r.status === 200)!.json()).data
          .rule.id,
        reason: "synthetic retire",
      })
    ).json()
  ).data;
  assert.equal(result.rule.status, "retired");
  assert.equal(result.version, after.version + 1);
});
test("administrator configuration write is versioned and audited; invalid scope does not write", async () => {
  const token = await login();
  const getSnapshot = async () =>
    (await (await api("opsConfig:snapshot", token)).json()).data;
  const before = await getSnapshot();
  const values = {
    business_id: "33333333-3333-4333-a333-333333333333",
    store_id: before.opsStores[0].business_id,
    user_id: before.users[0].id,
    rule_family: "R1",
    environment: "synthetic",
    title: "synthetic owner configuration test",
  };
  const r = await api("opsConfig:command", token, {
    command: "saveOwnerAssignment",
    command_id: `owner-${Date.now()}`,
    expected_version: before.version,
    reason: "synthetic config verification",
    values,
  });
  assert.equal(r.status, 200);
  assert.equal((await r.json()).data.version, before.version + 1);
  const after = await getSnapshot();
  assert.equal(after.version, before.version + 1);
  assert.ok(
    after.opsOwnerAssignments.some(
      (r: any) => r.business_id === values.business_id,
    ),
  );
  const invalid = await api("opsConfig:command", token, {
    command: "saveOwnerAssignment",
    command_id: `invalid-${Date.now()}`,
    expected_version: after.version,
    reason: "invalid scope test",
    values: { ...values, store_id: "99999999-9999-4999-a999-999999999999" },
  });
  assert.equal(invalid.status, 400);
  assert.equal((await getSnapshot()).version, after.version);
});
test("snapshot activeRules contains only latest enabled version per business scope", async () => {
  const token = await login();
  const data = (await (await api("opsConfig:snapshot", token)).json()).data;
  assert.ok(Array.isArray(data.activeRules));
  for (const rule of data.activeRules) {
    assert.equal(rule.status, "enabled");
    assert.ok(
      data.opsRules
        .filter(
          (r: any) =>
            r.family === rule.family &&
            r.store_id === rule.store_id &&
            r.warehouse_id === rule.warehouse_id,
        )
        .every((r: any) => r.version <= rule.version),
    );
  }
});
test("rule family validates exact parameters, numeric ranges, recovery window and scope", async () => {
  const token = await login();
  const data = (await (await api("opsConfig:snapshot", token)).json()).data;
  const base = {
    command: "publish",
    expected_version: data.version,
    store_id: data.opsStores[0].business_id,
    family: "R1",
    metric_version: "synthetic-v1",
    parameters: { drop_ratio: 0.3, min_baseline_orders: 5 },
    recovery: { observation_hours: 24, required_complete_days: 1 },
    reason: "invalid parameters synthetic",
    environment: "synthetic",
  };
  for (const change of [
    { parameters: { drop_ratio: 1.1, min_baseline_orders: 5 } },
    { parameters: { drop_ratio: 0.3, min_baseline_orders: 0 } },
    { parameters: { drop_ratio: 0.3, min_baseline_orders: 5, unknown: 1 } },
    { recovery: { observation_hours: 24, required_complete_days: 2 } },
    {
      family: "R3",
      parameters: { increase_ratio: 0, min_baseline_refunds: 3 },
    },
    { family: "R2", parameters: { available_qty_threshold: -1 } },
    { store_id: undefined },
  ]) {
    assert.equal(
      (
        await api("opsRule:command", token, {
          ...base,
          ...change,
          command_id: `invalid-rule-${crypto.randomUUID()}`,
        })
      ).status,
      400,
    );
  }
  assert.equal(
    (await (await api("opsConfig:snapshot", token)).json()).data.version,
    data.version,
  );
});
test("owner assignment cannot select a user outside the business scope", async () => {
  const token = await login();
  const snapshot = (await (await api("opsConfig:snapshot", token)).json()).data;
  const operatorB = snapshot.users.find(
    (u: any) => u.nickname === "synthetic operatorB",
  );
  const storeA = snapshot.opsStores.find((s: any) => s.title === "合成测试店A");
  const r = await api("opsConfig:command", token, {
    command: "saveOwnerAssignment",
    command_id: `owner-scope-${crypto.randomUUID()}`,
    expected_version: snapshot.version,
    reason: "synthetic owner scope rejection",
    values: {
      business_id: crypto.randomUUID(),
      store_id: storeA.business_id,
      user_id: operatorB.id,
      rule_family: "R1",
      environment: "synthetic",
    },
  });
  assert.equal(r.status, 400);
});
test("R2 can publish and enable within an authorized warehouse scope without a store", async () => {
  const token = await roleToken("supervisor");
  const data = (await (await api("opsConfig:snapshot", token)).json()).data;
  const warehouse = data.opsWarehouseScopes[0].warehouse_id;
  const published = await api("opsRule:command", token, {
    command: "publish",
    command_id: crypto.randomUUID(),
    expected_version: data.version,
    reason: "synthetic warehouse rule",
    warehouse_id: warehouse,
    family: "R2",
    metric_version: "synthetic-v1",
    parameters: { available_qty_threshold: 5 },
    recovery: { observation_hours: 24, required_complete_days: 1 },
    environment: "synthetic",
  });
  assert.equal(published.status, 200);
  const rule = (await published.json()).data;
  const enabled = await api("opsRule:command", token, {
    command: "enable",
    command_id: crypto.randomUUID(),
    expected_version: rule.version,
    reason: "synthetic warehouse enable",
    rule_id: rule.rule.id,
  });
  assert.equal(enabled.status, 200);
  assert.equal((await enabled.json()).data.rule.warehouse_id, warehouse);
});
test("old rule versions cannot bypass the latest retired lifecycle or re-enable enabled rules", async () => {
  const token = await login();
  const snapshot = async () =>
    (await (await api("opsConfig:snapshot", token)).json()).data;
  const initial = await snapshot();
  const body = {
    command: "publish",
    command_id: crypto.randomUUID(),
    expected_version: initial.version,
    reason: "synthetic lifecycle regression",
    store_id: initial.opsStores[0].business_id,
    family: "R3",
    metric_version: "synthetic-v1",
    parameters: { increase_ratio: 0.5, min_baseline_refunds: 3 },
    recovery: { observation_hours: 24, required_complete_days: 1 },
    environment: "synthetic",
  };
  const shadow = (await (await api("opsRule:command", token, body)).json())
    .data;
  const enable = await api("opsRule:command", token, {
    command: "enable",
    command_id: crypto.randomUUID(),
    expected_version: shadow.version,
    reason: "synthetic enable",
    rule_id: shadow.rule.id,
  });
  assert.equal(enable.status, 200);
  const enabled = (await enable.json()).data;
  assert.equal(
    (
      await api("opsRule:command", token, {
        command: "enable",
        command_id: crypto.randomUUID(),
        expected_version: enabled.version,
        reason: "invalid re-enable",
        rule_id: enabled.rule.id,
      })
    ).status,
    409,
  );
  const retirement = await api("opsRule:command", token, {
    command: "retire",
    command_id: crypto.randomUUID(),
    expected_version: enabled.version,
    reason: "synthetic retire",
    rule_id: enabled.rule.id,
  });
  assert.equal(retirement.status, 200);
  const retired = (await retirement.json()).data;
  for (const [command, rule_id] of [
    ["enable", shadow.rule.id],
    ["retire", shadow.rule.id],
    ["retire", retired.rule.id],
  ])
    assert.equal(
      (
        await api("opsRule:command", token, {
          command,
          rule_id,
          command_id: crypto.randomUUID(),
          expected_version: retired.version,
          reason: "invalid old version transition",
        })
      ).status,
      409,
    );
  assert.ok(
    !(await snapshot()).activeRules.some(
      (r: any) => r.family === "R3" && r.store_id === body.store_id,
    ),
  );
});
test("replaying a previous rule command rechecks the supervisor current scope", async () => {
  const admin = await login(),
    supervisor = await roleToken("supervisor");
  const snapshot = async (token = admin) =>
    (await (await api("opsConfig:snapshot", token)).json()).data;
  const data = await snapshot();
  const membership = data.opsMemberships.find(
    (m: any) =>
      m.user_id === accounts().supervisor.id &&
      m.store_id === data.opsStores[0].business_id,
  );
  const command = {
    command: "publish",
    command_id: crypto.randomUUID(),
    expected_version: data.version,
    reason: "synthetic replay authorization",
    store_id: membership.store_id,
    family: "R1",
    metric_version: "synthetic-v1",
    parameters: { drop_ratio: 0.3, min_baseline_orders: 5 },
    recovery: { observation_hours: 24, required_complete_days: 1 },
    environment: "synthetic",
  };
  assert.equal((await api("opsRule:command", supervisor, command)).status, 200);
  const set = async (status: string) =>
    api("opsConfig:command", admin, {
      command: "saveMembership",
      command_id: crypto.randomUUID(),
      expected_version: (await snapshot()).version,
      reason: "synthetic replay scope regression",
      values: { business_id: membership.business_id, status },
    });
  try {
    assert.equal((await set("inactive")).status, 200);
    assert.ok(
      !(await snapshot(supervisor)).opsRules.some(
        (r: any) => r.store_id === membership.store_id,
      ),
    );
    assert.equal(
      (await api("opsRule:command", supervisor, command)).status,
      403,
    );
  } finally {
    assert.equal((await set("active")).status, 200);
  }
});
test("owner patch validates the full retained store and warehouse scope", async () => {
  const token = await login();
  const snapshot = async () =>
    (await (await api("opsConfig:snapshot", token)).json()).data;
  const data = await snapshot();
  const warehouse = data.opsWarehouseScopes.find(
    (w: any) => w.user_id === accounts().supervisor.id,
  ).warehouse_id;
  const store = data.opsMemberships.find(
    (m: any) => m.user_id === accounts().operatorA.id,
  ).store_id;
  const business_id = crypto.randomUUID();
  const create = await api("opsConfig:command", token, {
    command: "saveOwnerAssignment",
    command_id: crypto.randomUUID(),
    expected_version: data.version,
    reason: "synthetic owner full scope regression",
    values: {
      business_id,
      store_id: store,
      warehouse_id: warehouse,
      user_id: accounts().supervisor.id,
      rule_family: "R2",
      environment: "synthetic",
    },
  });
  assert.equal(create.status, 200);
  const changed = await api("opsConfig:command", token, {
    command: "saveOwnerAssignment",
    command_id: crypto.randomUUID(),
    expected_version: (await snapshot()).version,
    reason: "invalid owner patch",
    values: { business_id, user_id: accounts().operatorA.id },
  });
  assert.equal(changed.status, 400);
  const owner = (await snapshot()).opsOwnerAssignments.find(
    (o: any) => o.business_id === business_id,
  );
  assert.equal(owner.warehouse_id, warehouse);
  assert.equal(owner.user_id, accounts().supervisor.id);
});
test("concurrent snapshot readers see one committed configuration version", async () => {
  const token = await login();
  const get = async () =>
    (await (await api("opsConfig:snapshot", token)).json()).data;
  const original = await get();
  const store = original.opsStores[0];
  let writing = true;
  const check = (snapshot: any) => {
    for (const collection of [
      "opsStores",
      "opsMemberships",
      "opsWarehouseScopes",
      "opsOwnerAssignments",
      "opsRules",
    ])
      for (const row of snapshot[collection])
        assert.ok(
          row.version <= snapshot.version || row.version === 1,
          `${collection} row version ${row.version} exceeds snapshot ${snapshot.version}`,
        );
  };
  const save = async (title: string) => {
    const data = await get();
    const r = await api("opsConfig:command", token, {
      command: "saveStore",
      command_id: crypto.randomUUID(),
      expected_version: data.version,
      reason: "synthetic consistent snapshot regression",
      values: { business_id: store.business_id, title },
    });
    assert.equal(r.status, 200);
  };
  try {
    const writer = (async () => {
      try {
        for (let i = 0; i < 8; i++)
          await save(`synthetic snapshot consistency ${i}`);
      } finally {
        writing = false;
      }
    })();
    const readers = Array.from({ length: 3 }, async () => {
      do {
        check(await get());
      } while (writing);
    });
    await Promise.all([writer, ...readers]);
  } finally {
    await save(store.title);
  }
});
test("an owner must retain an actual operations role as well as business membership", async () => {
  const token = await login();
  const id = accounts().operatorA.id;
  const snapshot = async () =>
    (await (await api("opsConfig:snapshot", token)).json()).data;
  const setRoles = (roles: string[]) =>
    api(`users/${id}/roles:set`, token, roles);
  try {
    assert.equal((await setRoles(["member"])).status, 200);
    const data = await snapshot();
    const membership = data.opsMemberships.find(
      (m: any) => m.user_id === id && m.status === "active",
    );
    assert.ok(membership);
    const rejected = await api("opsConfig:command", token, {
      command: "saveOwnerAssignment",
      command_id: crypto.randomUUID(),
      expected_version: data.version,
      reason: "synthetic owner actual role regression",
      values: {
        business_id: crypto.randomUUID(),
        store_id: membership.store_id,
        user_id: id,
        rule_family: "R1",
        environment: "synthetic",
      },
    });
    assert.equal(rejected.status, 400);
    assert.equal((await snapshot()).version, data.version);
  } finally {
    assert.equal((await setRoles(["ops_operator"])).status, 200);
  }
});
