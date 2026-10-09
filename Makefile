PYTHON ?= python

.PHONY: install test run clean

install:
	$(PYTHON) -m pip install -e ".[dev]"

test:
	pytest -q

run:
	nfnotify-lab all --config configs/experiment.yaml --out artifacts

clean:
	rm -rf artifacts .pytest_cache .ruff_cache
