.PHONY: setup dev api web build test evals simulate

setup:            ## Install backend and frontend dependencies
	cd backend && uv sync
	cd frontend && npm install

api:              ## API + HL7 listener with the demo hospital (http://localhost:8000)
	cd backend && uv run uvicorn flowdeck.main:app --reload

web:              ## Frontend dev server (http://localhost:5173)
	cd frontend && npm run dev

build:            ## Build the UI so the API serves it at http://localhost:8000
	cd frontend && npm run build

test:             ## Lint + tests
	cd backend && uv run ruff check . && uv run pytest -q

evals:            ## Forecast backtest + assistant evaluation
	backend/.venv/bin/python evals/forecast_eval.py --seeds 30
	backend/.venv/bin/python evals/assistant_eval.py --seeds 10

simulate:         ## Stream the rest of the simulated day into a running FlowDeck
	python3 simulator/simulate_day.py --send --speed 60
