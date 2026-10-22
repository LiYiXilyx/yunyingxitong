'use strict';
const { Plugin } = require('@nocobase/server');
class OpsBootstrapPlugin extends Plugin {
  async load() {
    this.app.resource({
      name: 'opsBootstrap',
      actions: {
        async status(ctx) {
          ctx.body = { schema_version: '1', stage: 'T02', business_ready: false };
        },
      },
    });
    this.app.acl.allow('opsBootstrap', 'status', 'loggedIn');
  }
}
module.exports = OpsBootstrapPlugin;
