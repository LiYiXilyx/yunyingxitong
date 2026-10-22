'use strict';
const test = require('node:test');
const assert = require('node:assert/strict');
const { readFileSync } = require('node:fs');
const { resolve } = require('node:path');
const vm = require('node:vm');
const { randomUUID } = require('node:crypto');

// Exercise the registered production component without a browser, login, or DB.
// React/AntD provide only hook/form storage; command payloads and handlers are real.
const source = readFileSync(process.env.OPS_CLIENT_TEST_SOURCE || resolve(__dirname,
  '../../plugins/nocobase-plugin-ops/src/client/index.js'), 'utf8');
const clone = (value) => value === undefined ? undefined : JSON.parse(JSON.stringify(value));
const STORE = '11111111-1111-4111-a111-111111111111';
function initialSnapshot() {
  return {
    version: 1, capabilities: { manageConfig: true, publishRules: true },
    users: [{ id: 7, nickname: 'Synthetic operator' }],
    opsMemberships: [], opsWarehouseScopes: [], opsOwnerAssignments: [],
    opsRules: [], activeRules: [],
    opsStores: [{ business_id: STORE, store_id: STORE, title: 'Original store',
      connection_id: 'synthetic', erp_store_id: 'original-erp', platform: 'temu',
      site: 'DE', timezone: 'UTC', environment: 'synthetic', version: 1 }],
  };
}
function fakeServer() {
  const state = initialSnapshot(), requests = [], receipts = new Map();
  const server = { state, requests, loseNextResponse: false };
  server.api = { resource: (resource) => ({
    snapshot: async () => ({ data: { data: clone(state) } }),
    command: async ({ values }) => {
      requests.push({ resource, values: clone(values) });
      if (receipts.has(values.command_id)) return { data: { data: clone(receipts.get(values.command_id)) } };
      if (values.expected_version !== state.version) throw { response: { status: 409 } };
      state.version += 1;
      if (values.command === 'saveStore') {
        const store = { ...clone(values.values), version: state.version };
        const index = state.opsStores.findIndex((s) => s.business_id === store.business_id);
        if (index < 0) state.opsStores.push(store); else state.opsStores[index] = store;
      } else if (values.command === 'publish') {
        state.opsRules.push({ id: state.opsRules.length + 1, ...clone(values), version: state.version, status: 'shadow' });
      }
      const result = { version: state.version, saved: true };
      receipts.set(values.command_id, result);
      if (server.loseNextResponse) {
        server.loseNextResponse = false;
        throw Error('Simulated connection loss after the server committed');
      }
      return { data: { data: clone(result) } };
    },
  }) };
  return server;
}
async function mount(server) {
  const hooks = [];
  let cursor = 0, changed = true, tree, components;
  const effects = [];
  const slot = (initialize) => {
    const index = cursor++;
    if (!(index in hooks)) hooks[index] = initialize();
    return hooks[index];
  };
  const React = {
    createElement: (type, props, ...children) => ({ type, props: { ...props, children } }),
    Fragment: 'Fragment',
    useState(initial) {
      const state = slot(() => ({ value: typeof initial === 'function' ? initial() : initial }));
      return [state.value, (next) => {
        state.value = typeof next === 'function' ? next(state.value) : next;
        changed = true;
      }];
    },
    useRef: (initial) => slot(() => ({ current: initial })),
    useEffect(effect, deps) {
      const state = slot(() => ({ deps: undefined }));
      if (!state.deps || deps.some((v, i) => !Object.is(v, state.deps[i]))) {
        state.deps = deps;
        effects.push(effect);
      }
    },
  };
  function Form() {}
  Form.Item = 'Form.Item';
  Form.useForm = () => [slot(() => ({
    initialized: false, initialValues: {}, values: {},
    setFieldsValue(values) { Object.assign(this.values, values); },
    getFieldsValue() { return clone(this.values); },
    getFieldValue(name) { return this.values[name]; },
    resetFields() { this.values = clone(this.initialValues); },
  }))];
  const antd = Object.fromEntries(['Alert', 'Button', 'Card', 'Select', 'Tabs', 'Table',
    'Tag', 'Space', 'Timeline'].map((name) => [name, name]));
  Object.assign(antd, { Form, Input: Object.assign(function Input() {}, { TextArea: 'TextArea' }),
    Typography: { Text: 'Typography.Text', Title: 'Typography.Title' } });
  const client = { Plugin: class {}, useAPIClient: () => server.api };
  let exported;
  const define = (_name, _dependencies, factory) => { exported = factory(client, React, antd); };
  define.amd = true;
  vm.runInNewContext(source, { define, crypto: { randomUUID } });
  const plugin = new exported.default();
  plugin.app = { use() {}, addComponents(value) { components = value; } };
  await plugin.load();
  function nodes(root = tree) {
    if (Array.isArray(root)) return root.flatMap((node) => nodes(node));
    if (!root || typeof root !== 'object' || !root.props) return [];
    return [root, ...nodes(root.props.children),
      ...(root.props.items || []).flatMap((item) => nodes(item.children))];
  }
  async function render() {
    for (let cycle = 0; cycle < 12; cycle++) {
      changed = false; cursor = 0; tree = components.OpsManagement();
      for (const node of nodes()) if (node.type === Form && !node.props.form.initialized) {
        node.props.form.initialized = true;
        node.props.form.initialValues = clone(node.props.initialValues || {});
        node.props.form.resetFields();
      }
      while (effects.length) effects.shift()();
      await new Promise((done) => setImmediate(done));
      if (!changed) return;
    }
    throw Error('Component did not settle');
  }
  const form = (field) => nodes().find((node) => node.type === Form && nodes(node).some((child) => child.props.name === field));
  const storeSelector = () => nodes(form('connection_id')).find((node) => node.type === 'Select' && node.props.onChange);
  const button = (label) => nodes().find((node) => node.type === 'Button' && node.props.children.includes(label));
  await render();
  return { render, form, storeSelector, button, nodes };
}
const ruleFields = () => ({ family: 'R1', store_id: STORE, metric_version: 'test-v1',
  parameters: JSON.stringify({ drop_ratio: 0.3, min_baseline_orders: 5 }),
  recovery: JSON.stringify({ observation_hours: 24, required_complete_days: 1 }),
  reason: 'Synthetic rule confirmation' });

test('409 discards stale form values and reselecting a store loads the latest fields', async () => {
  const server = fakeServer(), view = await mount(server);
  view.storeSelector().props.onChange(STORE);
  view.form('connection_id').props.form.setFieldsValue({ title: 'My intended edit' });
  view.form('user_id').props.form.setFieldsValue({ user_id: 7, store_id: STORE });
  view.form('parameters').props.form.setFieldsValue(ruleFields());
  server.state.version = 2;
  server.state.opsStores[0] = { ...server.state.opsStores[0], title: 'Other admin edit',
    erp_store_id: 'updated-erp', version: 2 };
  const editor = view.form('connection_id');
  await editor.props.onFinish(editor.props.form.getFieldsValue());
  await view.render();
  assert.equal(view.form('connection_id').props.form.getFieldValue('business_id'), undefined);
  assert.equal(view.form('connection_id').props.form.getFieldValue('title'), undefined);
  assert.equal(view.form('user_id').props.form.getFieldValue('user_id'), undefined);
  assert.equal(view.form('parameters').props.form.getFieldValue('store_id'), undefined);
  assert.equal(view.storeSelector().props.value, undefined);
  assert.equal(server.state.opsStores[0].title, 'Other admin edit');
  view.storeSelector().props.onChange(STORE);
  await view.render();
  const fresh = view.form('connection_id');
  assert.equal(fresh.props.form.getFieldValue('title'), 'Other admin edit');
  fresh.props.form.setFieldsValue({ title: 'My reviewed edit' });
  await fresh.props.onFinish(fresh.props.form.getFieldsValue());
  assert.equal(server.requests[1].values.expected_version, 2);
  assert.equal(server.requests[1].values.values.erp_store_id, 'updated-erp');
});

test('an uncertain publish blocks new writes and retries the exact original operation', async () => {
  const server = fakeServer(), view = await mount(server);
  server.loseNextResponse = true;
  const editor = view.form('parameters');
  editor.props.form.setFieldsValue(ruleFields());
  await editor.props.onFinish(editor.props.form.getFieldsValue());
  await view.render();
  const blocked = view.form('parameters');
  assert.equal(blocked.props.disabled, true);
  await blocked.props.onFinish({ ...ruleFields(), reason: 'Accidental second submission' });
  assert.equal(server.requests.length, 1, 'Pending operation must prevent a second command');
  const retry = view.button('重试上一操作');
  assert.ok(retry && !retry.props.disabled, 'An explicit retry must remain available');
  await retry.props.onClick();
  await view.render();
  assert.deepEqual(server.requests[1], server.requests[0], 'Retry must retain command ID, version and complete values');
  assert.equal(server.state.version, 2);
  assert.equal(server.state.opsRules.length, 1);
  assert.equal(view.form('parameters').props.disabled, false);
  assert.equal(view.button('重试上一操作'), undefined);
});

test('a newly created store keeps its identity after a lost response is recovered', async () => {
  const server = fakeServer(), view = await mount(server);
  server.loseNextResponse = true;
  const editor = view.form('connection_id');
  editor.props.form.setFieldsValue({ title: 'New synthetic store', connection_id: 'synthetic',
    erp_store_id: 'new-erp', platform: 'temu', site: 'DE', timezone: 'UTC', reason: 'New store' });
  await editor.props.onFinish(editor.props.form.getFieldsValue());
  await view.render();
  const createdId = server.requests[0].values.values.business_id;
  await view.button('重试上一操作').props.onClick();
  await view.render();
  assert.equal(view.form('connection_id').props.form.getFieldValue('business_id'), createdId);
  assert.equal(view.storeSelector().props.value, createdId);
  const savedEditor = view.form('connection_id');
  savedEditor.props.form.setFieldsValue({ title: 'Updated new store' });
  await savedEditor.props.onFinish(savedEditor.props.form.getFieldsValue());
  assert.equal(server.requests[2].values.values.business_id, createdId);
  assert.equal(server.state.opsStores.length, 2, 'Editing after recovery must update the same new store');
});
