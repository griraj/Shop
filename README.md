# AI Inventory — Inventory Ledger + AI Clerk

A split-screen web app on top of a Postgres inventory database:

- **Left panel — Stock Ledger:** view items, categories, and the audit trail; add new items with a form.
- **Right panel — AI Clerk:** a chat interface backed by a tool-calling agent (via OpenRouter). Ask things like *"add 20 units of Mouse at 2200 in Electronics"* or *"what's low on stock?"* and it calls the right tool(s) against your real database.

Also included: `inventory.py`, the original terminal-based console version of the same app (menu-driven, same database, same AI agent) — useful for testing the database/agent logic directly without the web UI.

## Project structure

```
Shop/
  app.py             FastAPI backend — REST endpoints + serves the frontend
  core.py            Shared DB/agent logic used by the web app
  inventory.py        Standalone terminal console app (same DB, same agent, menu-driven)
  main.sql            Database schema: tables, trigger, manage_item procedure, migration_log
  requirements.txt
  .env
  .gitignore
  static/
    index.html
    style.css
    app.js
```

## Setup

1. **Install dependencies** (ideally in a virtual environment):
   ```
   pip install -r requirements.txt
   ```
   On Windows, if `psycopg[binary]` gives you trouble:
   ```
   pip install fastapi "uvicorn[standard]" psycopg-binary python-dotenv openai pydantic
   ```

2. **Set up your `.env` file:**
   ```
   copy .env.example .env      (Windows)
   cp .env.example .env         (Mac/Linux)
   ```
   Fill in your real Postgres credentials and OpenRouter key.

3. **Create the database schema** — run `main.sql` against your Postgres database once (creates `items`, `categories`, `items_audit`, and the `manage_item` procedure).

4. **Run the web app:**
   ```
   uvicorn app:app --reload
   ```
   Then open `http://127.0.0.1:8000`.

   **Or run the console version instead:**
   ```
   python inventory.py
   ```

## How it's wired together

- `core.py` holds the actual logic — DB queries and the `run_agent()` tool-calling loop.
- `app.py` is a thin REST layer over `core.py` (`GET /api/items`, `POST /api/chat`, etc.), and serves the frontend.
- `static/app.js` calls those endpoints with `fetch()` — no page reloads, single-page app.
- The AI clerk keeps conversation history in the browser and sends it back with each message, so the model has memory of the conversation.
- When the agent calls a tool that changes data (`add_item`, `update_item`, `delete_item`), the frontend automatically refreshes the ledger tables.
- `inventory.py` is fully independent of the web app — it talks to the same database directly, useful if you want to test or demo the agent from a terminal.

## Notes on this cleanup

Removed from the original working folder (both were no longer needed):
- `main.py` — an early standalone practice script (calculator/weather chatbot), unrelated to this project, not imported by anything here.
- `patch_openrouter.py` — a one-time patch script whose changes are already applied inside `inventory.py`; it has no further purpose and hardcoded a personal file path.
- `__pycache__/` and `.env` — regenerated/local-only files that don't belong in a shared folder or version control.

## Extending it

- Add an "Edit" button next to each item row in the web UI (currently only Delete is wired up) — the pattern is the same as Add: a small form calling `PUT /api/items/{id}`.
- Add authentication before deploying this anywhere public — right now anyone who can reach the server can read/write your inventory and spend your OpenRouter credits.
