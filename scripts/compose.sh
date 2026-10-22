#!/bin/sh
set -eu
cd "$(dirname "$0")/.."
export DOCKER_CONTEXT="${PROJECT2_DOCKER_CONTEXT:-colima-project2}"
exec docker-compose --env-file .local/secrets/deploy.env -f deploy/compose.yaml "$@"
