.PHONY: test report verify

test:
	python3 -m unittest discover -s tests -v

report:
	python3 -m sasb > reports/harness-run.json
	python3 -m sasb.chain > reports/chain-run.json
	python3 -m sasb.controls > reports/stage-a-controls.json

verify:
	python3 tools/verify_report.py
