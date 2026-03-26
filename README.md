# AskData

AskData is an AI analytics copilot that lets users ask business questions in natural language over a PostgreSQL database and receive:

- a short answer summary
- the generated SQL
- result rows
- a simple chart recommendation
- the tables used to answer the question

The project is built as a product, not as a one-off text-to-SQL script. Its core value is the controlled pipeline around the model: schema-aware retrieval, SQL safety validation, read-only execution, structured responses, and a chat-first UI.

## Why this project exists

Generic LLMs can already connect to databases. AskData exists to show how that capability becomes a usable, trustworthy product.

The focus is on:

- safe SQL generation and execution
- schema-aware context retrieval
- deterministic backend orchestration
- inspectable outputs for user trust
- local reproducibility with Docker
- a polished enough UX to work as a portfolio project

## Current MVP scope

AskData currently supports:

- PostgreSQL only
- Pagila as the development dataset
- natural-language question input
- schema introspection and schema overview
- heuristic schema retrieval
- LLM-based SQL generation
- parser-based SQL validation
- read-only SQL execution with timeout and row caps
- answer summaries, result tables, and chart hints
- session-local multi-turn chat in the UI

Out of scope for the MVP:

- connect-your-own-database
- authentication
- persistent chat history
- multi-database support
- multi-agent orchestration
- dashboard building

## Product flow

1. The user asks a business question in the chat UI.
2. The backend retrieves the most relevant schema context.
3. The model generates SQL in a structured response format.
4. The SQL is validated with read-only safety rules.
5. The query is executed against PostgreSQL with a timeout and row limit policy.
6. The backend returns a structured JSON response with summary, SQL, rows, chart hint, warnings, and used tables.
7. The frontend renders that response as a conversational answer with optional details.

## Architecture summary

### Frontend

- `Next.js`
- `TypeScript`
- `Tailwind CSS`
- `Recharts`

The frontend is conversation-first. The main UI has two persistent regions:

- a collapsible left rail for navigation, prompts, warnings, and lineage
- a chat surface for the conversation and schema view

The UI keeps chat history only in browser memory for the current session.

### Backend

- `FastAPI`
- `Pydantic`
- `psycopg`
- `sqlglot`
- `OpenAI`

The backend is a deterministic pipeline, not a multi-agent system:

1. receive question
2. retrieve schema context
3. generate SQL
4. validate SQL
5. execute SQL
6. optionally repair once
7. format response

### Data and infrastructure

- `PostgreSQL`
- `Docker Compose`
- `Pagila`

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
├─ docker-compose.yml
└─ Makefile
```

## Prerequisites

You need:

- `Python 3.11+`
- `Node.js 20+`
- `npm`
- `Docker` and `Docker Compose`
- an `OPENAI_API_KEY`

## Local setup

### 1. Start PostgreSQL with Pagila

```bash
make docker-up
```

This starts PostgreSQL and loads Pagila from:

- `demo_data/seed/pagila.sql`

The local database is exposed on:

- `localhost:55432`

### 2. Configure the backend

Create a local backend env file:

```bash
cp backend/.env.example backend/.env
```

Then set your real OpenAI key in:

- `backend/.env`

Important backend defaults:

- backend API: `http://127.0.0.1:8000`
- PostgreSQL host: `localhost`
- PostgreSQL port: `55432`

### 3. Configure the frontend

Create a local frontend env file:

```bash
cp frontend/.env.example frontend/.env.local
```

Default frontend API target:

- `NEXT_PUBLIC_ASKDATA_API_BASE_URL=http://127.0.0.1:8000`

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

## Verification

Run the automated checks:

```bash
make verify
```

That runs:

- backend tests
- frontend lint
- frontend production build

You can also verify the live API manually:

```bash
curl http://127.0.0.1:8000/health
curl http://127.0.0.1:8000/examples
curl http://127.0.0.1:8000/schema/overview
```

## Example questions

Try these in the chat UI:

- `Which 10 customers spent the most in total?`
- `What are the top 10 film categories by total revenue?`
- `How much revenue did each staff member process?`
- `How many rentals happened each month?`
- `Now show only the top 5`

## Safety model

The MVP enforces:

- `SELECT`-only query policy
- rejection of unsafe statements such as `INSERT`, `UPDATE`, `DELETE`, `DROP`, and `ALTER`
- rejection of multiple statements
- parser-based validation before execution
- read-only database connection behavior
- statement timeout
- row limit policy
- at most one repair attempt

## Current limitations

- answer quality is good for many common business questions, but not perfect
- follow-up support is lightweight, not full conversational memory
- conversation history is session-local only
- charting is heuristic
- Pagila dataset quirks can appear in user-facing outputs

## Project status

The project is currently at:

- Phase 4.5: packaging and deployment preparation

Completed so far:

- backend MVP
- frontend MVP
- conversation-first Phase 3 UX and quality pass
- local setup audit
- README, demo assets, and architecture assets

Deployment is intentionally deferred until the packaging phase is complete and costs/hosting tradeoffs are reviewed carefully.

## Deployment note

The project is deployment-ready in architecture, but not yet deployed publicly.

The current recommended future hosting shape is:

- frontend on Vercel
- backend on Render or Railway
- PostgreSQL on Neon or another managed Postgres provider

The project still needs final hosting choice, production env configuration, and cost controls before public deployment.
