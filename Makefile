.PHONY: install dev-api dev-web build serve test lint

install:
	cd backend && python3 -m venv .venv && .venv/bin/pip install -r requirements.txt -r requirements-dev.txt
	cd frontend && npm install

dev-api:  ## Django API on :8000
	cd backend && DJANGO_DEBUG=true .venv/bin/python manage.py runserver 8000

dev-web:  ## Vite dev server on :5173 (proxies /api to :8000)
	cd frontend && npm run dev

build:
	cd frontend && npm run build

serve: build  ## Production-style: Django serves the built app on :8000
	cd backend && .venv/bin/gunicorn config.wsgi --bind 127.0.0.1:8000 --workers 1 --threads 4 --timeout 120

test:
	cd backend && .venv/bin/python manage.py test

lint:
	cd backend && .venv/bin/ruff check . && .venv/bin/ruff format --check .
	cd frontend && npm run lint && npx tsc -b
