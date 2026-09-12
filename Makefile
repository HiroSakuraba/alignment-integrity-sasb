.PHONY: test report verify provider-report live-dry live-fake live-pilot

test:
	python3 -m unittest discover -s tests -v

report:
	python3 -m sasb.landscape > reports/perturbation-map.json
	python3 -m sasb > reports/harness-run.json
	python3 -m sasb.chain > reports/chain-run.json
	python3 -m sasb.controls > reports/stage-a-controls.json
	python3 -m sasb.artifacts > reports/artifact-run.json

provider-report:
	python3 -m sasb.landscape > reports/perturbation-map.json
	python3 -m sasb.agents.providers

verify:
	python3 tools/verify_report.py

live-dry:
	python3 -m sasb.live --dry-run --mode worker --cap-usd 1.00

live-fake:
	python3 -m sasb.live --fake-transport --provider anthropic --mode worker --cap-usd 0.50 --out reports/live-run-local.json

live-pilot:
	python3 -m sasb.pilot --fake-transport --provider anthropic --mode worker --cap-usd 0.50 --force --out reports/live-run-local.json

reachability:
	python3 -m sasb.reachability

reachability-check:
	python3 -m unittest discover -s tests -p 'test_reachability.py' -v

replay-check:
	python3 -m unittest discover -s tests -p 'test_replay_regression.py' -v

expanded-report:
	python3 -m sasb.recovery > reports/expanded-testing.json
