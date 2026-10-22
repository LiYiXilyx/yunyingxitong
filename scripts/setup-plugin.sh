#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
python3 scripts/wait-ready.py http://127.0.0.1:13000/api/app:getInfo
state=$(scripts/compose.sh exec -T postgres psql -U postgres -d nocobase -At -v ON_ERROR_STOP=1 -c "SELECT COALESCE(bool_and(enabled AND installed),false) FROM \"applicationPlugins\" WHERE \"packageName\"='@project2/plugin-ops';")
if [ "$state" != t ]; then
  umask 077
  echo 'Installing local project plugin; details saved in .local/plugin-setup.log'
  scripts/compose.sh exec -T nocobase yarn nocobase pm add @project2/plugin-ops > .local/plugin-setup.log 2>&1
  scripts/compose.sh exec -T nocobase yarn nocobase pm enable @project2/plugin-ops >> .local/plugin-setup.log 2>&1
  scripts/compose.sh restart nocobase
fi
python3 scripts/wait-ready.py http://127.0.0.1:13000/api/opsBootstrap:status --codes 401,403
