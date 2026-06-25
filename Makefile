.PHONY: run install docker test clean

run:            ## local dev (SQLite, hot reload)
	./run.sh

install:        ## create venv + install deps
	cd backend && python3 -m venv .venv && ./.venv/bin/pip install -U pip -r requirements.txt

docker:         ## full stack: API + Postgres(pgvector) + Redis
	docker compose up --build

test:           ## run the in-process smoke check (28 assertions)
	cd backend && DATABASE_URL="sqlite+aiosqlite:///./_check.db" PYTHONPATH=. ./.venv/bin/python check.py && rm -f ./_check.db

clean:
	rm -rf backend/.venv backend/learning.db backend/app/__pycache__ backend/app/**/__pycache__
