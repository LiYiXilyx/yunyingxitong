.PHONY: bootstrap up down status setup-dev setup-t03 setup-wdt setup-t05 demo-t05 wdt-check build-plugin-client test-data test-plugin test-ego test-e2e test-bootstrap verify-community verify-contracts test
bootstrap:
	python3 scripts/bootstrap.py
up: bootstrap build-plugin-client
	scripts/compose.sh up -d --build
	scripts/setup-plugin.sh
	python3 scripts/run-tests.py plugin --case bootstrap

down:
	scripts/compose.sh down
status:
	scripts/compose.sh ps

test-data:
	python3 scripts/run-tests.py data --case "$(CASE)"
test-plugin:
	python3 scripts/run-tests.py plugin --case "$(CASE)"
test-ego:
	python3 scripts/run-tests.py ego --case "$(CASE)"
test-e2e:
	python3 scripts/run-tests.py e2e --case "$(CASE)"
test-bootstrap:
	python3 -m unittest discover -s tests -p 'test_*.py'
verify-community:
	scripts/verify-community.sh
verify-contracts:
	python3 scripts/run-tests.py data --case contracts
	cd contracts && npm test
test: test-bootstrap test-data test-plugin verify-contracts verify-community
	scripts/verify-isolation.sh

setup-dev:
	python3 -m venv services/ops-data/.venv
	services/ops-data/.venv/bin/pip install -r services/ops-data/requirements.lock
	npm ci --prefix contracts --ignore-scripts

build-plugin-client:
	python3 scripts/build-plugin-client.py

setup-t03: up
	python3 scripts/setup-t03.py

# Install only the connector limiter table in the independent ops database.
setup-wdt:
	scripts/compose.sh up -d --build ops-data
	scripts/compose.sh exec -T ops-data python -m ops_data.connectors.wdt.migrate

# Offline check; missing credentials intentionally return nonzero.
wdt-check:
	python3 scripts/wdt-check.py

setup-t05: up
	scripts/compose.sh restart nocobase
	python3 scripts/wait-ready.py http://127.0.0.1:13000/api/app:getInfo
	scripts/compose.sh exec -T ops-data python -m ops_data.ingestion.migrate
	scripts/compose.sh exec -T ops-data python -c 'import os; from ops_data.jobs.ledger import JobLedger; from ops_data.jobs.health_scan import HealthScanner; db=os.environ["OPS_DATABASE_URL"]; JobLedger(db).migrate(); HealthScanner(db).migrate()'
	node scripts/setup-nocobase-pages.mjs --refresh-health

demo-t05:
	node scripts/demo-t05.mjs
