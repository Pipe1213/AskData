# AskData

AskData is a web app for asking questions about a PostgreSQL database in plain language.

You type a business question, the backend plans how to answer it, turns it into SQL, checks that the SQL is safe, runs it against PostgreSQL, and returns:

- a short answer
- the SQL it used
- result rows
- a simple chart when it makes sense
- the tables involved

The project is beyond the first MVP. It now has persistent local sessions, a planner-led pipeline, a compact trust trace, and a generic PostgreSQL core that can run against more than one included dataset.

## What the product looks like

### Main chat view

![AskData chat view](assets/readme/chat-answer.png)

### Inspecting the answer details

![AskData answer details](assets/readme/chat-answer-details.png)

### Schema view

![AskData schema view](assets/readme/schema-view.png)

## How it works

The product has three main parts:

- a `Next.js` frontend
- a `FastAPI` backend
- a `PostgreSQL` database loaded with one active demo dataset at a time

At a high level, the request flow is:

1. the user asks a question in the chat UI
2. the backend builds a small plan for the request
3. the backend finds the most relevant schema context
4. the backend asks the model for SQL
5. the SQL is validated with read-only rules
6. the SQL is executed against PostgreSQL
7. the backend formats the result for the UI and stores the turn in local session history

## Architecture

![AskData architecture diagram](assets/architecture/askdata-system-architecture.png)

The editable diagram source is included here:

- [askdata-system-architecture.excalidraw](assets/architecture/askdata-system-architecture.excalidraw)

## Current scope

The current version includes:

- PostgreSQL only
- two included demo datasets:
  - `pagila`
  - `retail_ops`
- natural-language question input
- schema overview
- schema-aware retrieval
- planner-guided SQL generation with an LLM
- parser-based SQL validation
- read-only execution with timeout and row limits
- a conversation-style UI with browser-scoped persistent session history
- bounded retries and a compact trust trace
- a generic PostgreSQL core with dataset adapters

The current version does **not** include:

- user-provided databases
- authentication
- multi-database support
- dashboard building

## Stack

### Frontend

- `Next.js`
- `TypeScript`
- `Tailwind CSS`
- `Recharts`

### Backend

- `FastAPI`
- `Pydantic`
- `psycopg`
- `sqlglot`
- `OpenAI`

### Data and local infrastructure

- `PostgreSQL`
- `Docker Compose`
- included demo datasets under `demo_data/seed/`

## Repo structure

```text
AskData/
├─ backend/
│  ├─ app/
│  │  ├─ api/
│  │  ├─ core/
│  │  ├─ db/
│  │  ├─ llm/
│  │  ├─ schemas/
│  │  ├─ services/
│  │  └─ utils/
│  └─ tests/
├─ frontend/
│  ├─ app/
│  ├─ components/
│  ├─ lib/
│  └─ styles/
├─ demo_data/
│  ├─ example_questions/
│  └─ seed/
├─ assets/
│  ├─ architecture/
│  └─ readme/
├─ docker-compose.yml
└─ Makefile
```

## Run locally

### Prerequisites

You need:

- `Python 3.11+`
- `Node.js 20+`
- `npm`
- `Docker` and `Docker Compose`
- an `OPENAI_API_KEY`

### 1. Start PostgreSQL

```bash
make docker-up
```

This starts PostgreSQL with the default demo database.

The local database is exposed on:

- `localhost:55432`

### 2. Choose the active demo dataset

By default, AskData starts on `pagila`.

To switch datasets later without changing the backend connection string:

```bash
make load-dataset DATASET=retail_ops
```

Available dataset names:

- `pagila`
- `retail_ops`

This reloads the `public` schema only and keeps AskData's internal `askdata_app` persistence schema intact.

### 3. Create local env files

Backend:

```bash
cp backend/.env.example backend/.env
```

Then set your real OpenAI key in `backend/.env`.

Frontend:

```bash
cp frontend/.env.example frontend/.env.local
```

### 4. Install dependencies

Backend:

```bash
make backend-install
```

Frontend:

```bash
make frontend-install
```

### 5. Start the app

Backend:

```bash
make backend-dev
```

Frontend:

```bash
make frontend-dev
```

Open:

- frontend: `http://127.0.0.1:3000`
- backend: `http://127.0.0.1:8000`

## Verify the project

Run the main checks:

```bash
make verify
```

That runs:

- backend tests
- frontend lint
- frontend production build

You can also check the backend directly:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/examples
curl http://127.0.0.1:8000/schema/overview
```

If you switch datasets while the backend is already running, the loader will try to refresh the schema cache automatically. If needed, you can also do it manually:

```bash
make reload-schema-cache
```

## Benchmarks

Run the benchmark for the active or chosen dataset:

```bash
make benchmark-backend
make benchmark-backend DATASET=retail_ops
make benchmark-backend DATASET=pagila
make benchmark-dual
```

The benchmark runner checks:

- operational success
- no-row outcomes
- task type and primary artifact expectations
- rough table-usage alignment

`make benchmark-backend DATASET=...` now reloads the requested dataset first, so the benchmark always runs against the matching live schema.

## Example questions

Try these in the chat UI on `pagila`:

- `Which 10 customers spent the most in total?`
- `What are the top 10 film categories by total revenue?`
- `How much revenue did each staff member process?`
- `How many rentals happened each month?`
- `Now show only the top 5`

Try these on `retail_ops`:

- `Which 10 customers generated the most revenue?`
- `What were the top product categories by revenue last quarter?`
- `How did monthly revenue change by sales channel?`
- `Which brands have the highest return amount?`

## Safety rules

The backend currently enforces:

- `SELECT`-only queries
- no `INSERT`, `UPDATE`, `DELETE`, `DROP`, or `ALTER`
- no multiple statements
- parser-based SQL validation before execution
- read-only execution
- statement timeout
- row limit policy
- at most one repair attempt

## Current limitations

- answer quality is solid for many common questions, but not guaranteed on every business question
- the generic PostgreSQL path is real, but it has only been validated on the two included datasets so far
- bounded retries improve recovery, but this is not an open-ended agent
- chart selection and primary artifact choice are still heuristic
- deployment is still deferred

## Project status

AskData is currently in a strong local-demo V2 foundation state:

- persistent local sessions
- planner-led query pipeline
- answer-first UI
- generic PostgreSQL core plus dataset adapters
- two included datasets for evaluation

The next engineering focus is:

- stronger generic-schema evaluation
- better bounded recovery on hard questions and no-row cases
- tighter follow-up behavior over longer analytical threads

- backend MVP
- frontend MVP
- conversation-first UI refinement
- quality improvements for retrieval and formatting
- local setup cleanup
- README, screenshots, and architecture assets

## Deployment note

The app is not publicly deployed yet.

The current recommended future setup is:

- frontend on Vercel
- backend on Render or Railway
- PostgreSQL on Neon or another managed Postgres provider

Deployment is intentionally deferred until hosting, costs, and public-demo protections are reviewed more carefully.
