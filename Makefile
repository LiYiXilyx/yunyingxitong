.PHONY: bootstrap up down status setup-dev setup-t03 build-plugin-client test-data test-plugin test-ego test-e2e test-bootstrap verify-community verify-contracts test
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
