.PHONY: test report verify provider-report live-dry

test:
	python3 -m unittest discover -s tests -v

report:
	python3 -m sasb > reports/harness-run.json
	python3 -m sasb.chain > reports/chain-run.json
	python3 -m sasb.controls > reports/stage-a-controls.json
	python3 -m sasb.artifacts > reports/artifact-run.json

provider-report:
	python3 -m sasb.agents.providers

verify:
	python3 tools/verify_report.py

live-dry:
	python3 -m sasb.live --dry-run --mode worker --cap-usd 1.00
