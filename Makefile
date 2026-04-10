PYTHON := python3
.PHONY: install generate-test-data ingest harmonise categorise build-cube serve-dashboard run-tests export

install:
	@echo "Running install"
	$(PYTHON) -m pip install -r requirements.txt

generate-test-data:
	@echo "Running generate-test-data"
	$(PYTHON) src/utils/generate_test_data.py

ingest:
	@echo "Running ingest"
	$(PYTHON) src/ingestion/ingest.py

harmonise:
	@echo "Running harmonise"
	$(PYTHON) src/suppliers/harmoniser.py --db data/db/spend_cube.db

categorise:
	@echo "Running categorise"
	$(PYTHON) src/categorisation/categoriser.py --db data/db/spend_cube.db

build-cube:
	@echo "Running build-cube"
	$(PYTHON) src/cube/builder.py --db data/db/spend_cube.db
	$(PYTHON) src/recommendations/engine.py --db data/db/spend_cube.db

serve-dashboard:
	@echo "Running serve-dashboard"
	PYTHONPATH=$(shell pwd) streamlit run dashboard/app.py

run-tests:
	@echo "Running run-tests"
	pytest tests/ -v --cov=src

export:
	@echo "Running export"
	$(PYTHON) src/cube/exporter.py --db data/db/spend_cube.db --format parquet
