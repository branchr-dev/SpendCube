.PHONY: install generate-test-data ingest harmonise categorise build-cube serve-dashboard run-tests export

install:
	@echo "Running install"
	pip install -r requirements.txt

generate-test-data:
	@echo "Running generate-test-data"
	python src/utils/generate_test_data.py

ingest:
	@echo "Running ingest"
	python src/ingestion/ingest.py

harmonise:
	@echo "Running harmonise"
	python src/suppliers/harmoniser.py --db data/db/spend_cube.db

categorise:
	@echo "Running categorise"
	python src/categorisation/categoriser.py --db data/db/spend_cube.db

build-cube:
	@echo "Running build-cube"
	python src/cube/builder.py --db data/db/spend_cube.db
	python src/recommendations/engine.py --db data/db/spend_cube.db

serve-dashboard:
	@echo "Running serve-dashboard"
	streamlit run dashboard/app.py

run-tests:
	@echo "Running run-tests"
	pytest tests/ -v --cov=src

export:
	@echo "Running export"
	python src/cube/exporter.py --db data/db/spend_cube.db --format parquet
