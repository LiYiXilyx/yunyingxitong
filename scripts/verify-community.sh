#!/usr/bin/env bash
set -euo pipefail
root="$(cd "$(dirname "$0")/.." && pwd)"
cd "$root"
if [[ $# -gt 1 || ( $# -eq 1 && ! -f "$1" ) ]]; then
  echo '用法: scripts/verify-community.sh [显式启用清单.json]' >&2
  exit 2
fi
inventory="$(mktemp)"
runtime="$(mktemp)"
trap 'rm -f "$inventory" "$runtime"' EXIT
# 只读取当前服务可见的插件package.json；包含项目自研命名空间。
./scripts/compose.sh exec -T nocobase node -e '
const fs=require("fs"); const rows=[];
const modules="/app/nocobase/node_modules";
for(const scope of fs.readdirSync(modules).filter(n=>n.startsWith("@"))){
 const base=modules+"/"+scope;
 if(!fs.existsSync(base))continue;
 for(const n of fs.readdirSync(base).filter(n=>n.startsWith("plugin-"))){
  const p=JSON.parse(fs.readFileSync(base+"/"+n+"/package.json","utf8"));
  rows.push({name:p.name,version:p.version,license:p.license});
 }
}
for(const n of fs.readdirSync(modules).filter(n=>n.startsWith("plugin-"))){
 const p=JSON.parse(fs.readFileSync(modules+"/"+n+"/package.json","utf8"));
 rows.push({name:p.name,version:p.version,license:p.license});
}
console.log(JSON.stringify(rows));' > "$inventory"
if [[ $# -eq 1 ]]; then
  python3 scripts/community_guard.py --installed-json "$inventory" --enabled-json "$1"
else
  container_id="$(./scripts/compose.sh ps -q nocobase)"
  if [[ -z "$container_id" || "$container_id" == *$'\n'* ]]; then
    echo '无法确定唯一NocoBase容器' >&2
    exit 1
  fi
  actual_image="$(docker --context "${PROJECT2_DOCKER_CONTEXT:-colima-project2}" inspect --format '{{.Config.Image}}' "$container_id")"
  ./scripts/compose.sh exec -T postgres psql -U postgres -d nocobase -At -v ON_ERROR_STOP=1 > "$runtime" <<'SQL'
SELECT COALESCE(json_agg(json_build_object(
  'packageName', "packageName", 'version', "version",
  'installed', "installed", 'enabled', "enabled"
)), '[]'::json) FROM "applicationPlugins";
SQL
  python3 scripts/community_guard.py --installed-json "$inventory" --runtime-json "$runtime" --actual-image "$actual_image"
fi
