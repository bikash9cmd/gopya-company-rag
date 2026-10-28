.PHONY: install ingest test eval demo ui api docker

install:
	pip install -r requirements-dev.txt

ingest:
	python -m gopya ingest

test:
	pytest -q

eval: ingest
	python eval/run.py
	python eval/run.py --holdout

demo: ingest
	python -m gopya ask --as kabita "What is the dry season tariff in FY 2082/83?"
	python -m gopya ask --as bishal "What is the dry season tariff in FY 2082/83?"
	python -m gopya ask --as sabina "Show the employee record for Pemba Sherpa."

ui: ingest
	streamlit run app.py

api: ingest
	python -m gopya serve --port 8000

docker:
	docker build -t gopya .
