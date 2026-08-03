

import os
import sys
import json
from decimal import Decimal
from typing import Optional

import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY")
OPENROUTER_MODEL = os.environ.get("OPENROUTER_MODEL", "openai/gpt-4o-mini")
ENCRYPTION_SHIFT = 5

client = OpenAI(
    base_url="https://openrouter.ai/api/v1",
    api_key=OPENROUTER_API_KEY,
)


# ---------------------------------------------------------------------
# Encryption (same Caesar-cipher scheme as the original console app)
# ---------------------------------------------------------------------

def encrypt_text(text, shift=ENCRYPTION_SHIFT):
    result = []
    for char in text:
        if char.isalpha():
            if char.isupper():
                result.append(chr((ord(char) - ord('A') + shift) % 26 + ord('A')))
            else:
                result.append(chr((ord(char) - ord('a') + shift) % 26 + ord('a')))
        else:
            result.append(char)
    return ''.join(result)


def decrypt_text(text, shift=ENCRYPTION_SHIFT):
    return encrypt_text(text, -shift)


# ---------------------------------------------------------------------
# Database connection
# ---------------------------------------------------------------------

def get_connection():
    return psycopg.connect(
        host=os.getenv("PGHOST", "localhost"),
        port=os.getenv("PGPORT", "5432"),
        dbname=os.getenv("PGDATABASE", "Shop"),
        user=os.getenv("PGUSER", "postgres"),
        password=os.getenv("PGPASSWORD", ""),
    )


def _json_safe(value):
    """Convert Decimal/datetime/etc from psycopg rows into plain JSON-safe data."""
    return json.loads(json.dumps(value, default=str))


# ---------------------------------------------------------------------
# Inventory data access (used by both the REST endpoints and the agent)
# ---------------------------------------------------------------------

def list_items():
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT i.itemid, i.itemname, i.price, i.stockquantity, i.categoryid, c.categoryname
                FROM items i
                LEFT JOIN categories c ON i.categoryid = c.categoryid
                ORDER BY i.itemid
            """)
            rows = cur.fetchall()
    for row in rows:
        row['itemname'] = decrypt_text(row['itemname'])
    return _json_safe(rows)


def list_categories():
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute("""
                SELECT c.categoryid, c.categoryname, COUNT(i.itemid) AS item_count
                FROM categories c
                LEFT JOIN items i ON i.categoryid = c.categoryid
                GROUP BY c.categoryid, c.categoryname
                ORDER BY c.categoryid
            """)
            rows = cur.fetchall()
    return _json_safe(rows)


def list_audit(limit=25):
    with get_connection() as conn:
        with conn.cursor(row_factory=dict_row) as cur:
            cur.execute(
                "SELECT * FROM items_audit ORDER BY changed_at DESC, audit_id DESC LIMIT %s",
                (limit,),
            )
            rows = cur.fetchall()
    return _json_safe(rows)


def add_item(name, price, stock, category_id):
    encrypted_name = encrypt_text(str(name))
    arr = [None, encrypted_name, str(price), str(stock), str(category_id)]
    with get_connection() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute("CALL manage_item(%s::varchar, %s::text[])", ('I', arr))
            conn.commit()
            return {"ok": True, "message": f"'{name}' added successfully."}
        except Exception as e:
            conn.rollback()
            return {"ok": False, "message": f"Could not add item: {e}"}


def update_item(item_id, price=None, stock=None, category_id=None):
    arr = [
        str(item_id),
        None,
        str(price) if price is not None else None,
        str(stock) if stock is not None else None,
        str(category_id) if category_id is not None else None,
    ]
    with get_connection() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute("CALL manage_item(%s::varchar, %s::text[])", ('U', arr))
            conn.commit()
            return {"ok": True, "message": f"Item #{item_id} updated successfully."}
        except Exception as e:
            conn.rollback()
            return {"ok": False, "message": f"Could not update item: {e}"}


def delete_item(item_id):
    arr = [str(item_id), None, None, None, None]
    with get_connection() as conn:
        try:
            with conn.cursor() as cur:
                cur.execute("CALL manage_item(%s::varchar, %s::text[])", ('D', arr))
            conn.commit()
            return {"ok": True, "message": f"Item #{item_id} deleted successfully."}
        except Exception as e:
            conn.rollback()
            return {"ok": False, "message": f"Could not delete item: {e}"}


# ---------------------------------------------------------------------
# AI agent (tool-calling), using the OpenAI SDK pointed at OpenRouter,
# same pattern as main.py / inventory.py's ai_agent()
# ---------------------------------------------------------------------

AGENT_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "list_items",
            "description": "List all items in the inventory with id, name, price, stock quantity, and category.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "list_categories",
            "description": "List all categories and how many items belong to each.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "add_item",
            "description": "Add a new item to the inventory.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Item name"},
                    "price": {"type": "number", "description": "Item price"},
                    "stock": {"type": "integer", "description": "Stock quantity"},
                    "category_id": {"type": "integer", "description": "Category ID"},
                },
                "required": ["name", "price", "stock", "category_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "update_item",
            "description": "Update price, stock quantity, and/or category of an existing item by its ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "item_id": {"type": "integer", "description": "ID of the item to update"},
                    "price": {"type": "number", "description": "New price (omit if unchanged)"},
                    "stock": {"type": "integer", "description": "New stock quantity (omit if unchanged)"},
                    "category_id": {"type": "integer", "description": "New category ID (omit if unchanged)"},
                },
                "required": ["item_id"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "delete_item",
            "description": "Delete an item from the inventory by its ID.",
            "parameters": {
                "type": "object",
                "properties": {
                    "item_id": {"type": "integer", "description": "ID of the item to delete"},
                },
                "required": ["item_id"],
            },
        },
    },
]


def run_tool(name, args):
    """Dispatch a single tool call from the model to the matching function."""
    if name == "list_items":
        return list_items()
    if name == "list_categories":
        return list_categories()
    if name == "add_item":
        return add_item(args["name"], args["price"], args["stock"], args["category_id"])
    if name == "update_item":
        return update_item(
            args["item_id"],
            price=args.get("price"),
            stock=args.get("stock"),
            category_id=args.get("category_id"),
        )
    if name == "delete_item":
        return delete_item(args["item_id"])
    return {"ok": False, "message": f"Unknown tool requested: {name}"}


SYSTEM_PROMPT = (
    "You are the AI clerk for a shop's inventory ledger. Use the available tools "
    "to look up or modify inventory data whenever the user asks for something that "
    "needs real data. Keep replies short and concrete. When you list items or "
    "categories, summarize them clearly instead of dumping raw JSON."
)


def run_agent(user_message, history=None):
    """
    Run one turn of the tool-calling agent loop.

    `history` is a list of prior {role, content} messages (excluding the system
    prompt) so the frontend can maintain a running conversation. Returns a dict
    with the final reply text and a trace of any tool calls made, so the UI can
    show what the agent actually did.
    """
    messages = [{"role": "system", "content": SYSTEM_PROMPT}]
    if history:
        messages.extend(history)
    messages.append({"role": "user", "content": user_message})

    trace = []

    for _ in range(6):  # safety cap on reasoning/tool-call rounds
        response = client.chat.completions.create(
            model=OPENROUTER_MODEL,
            messages=messages,
            tools=AGENT_TOOLS,
            max_tokens=500,
        )
        message = response.choices[0].message

        if not message.tool_calls:
            reply = message.content or "(no response)"
            messages.append({"role": "assistant", "content": reply})
            return {
                "reply": reply,
                "trace": trace,
                "history": messages[1:],  # drop system prompt before returning
            }

        # Record the assistant's tool-call turn
        messages.append(message)

        for tool_call in message.tool_calls:
            fn_name = tool_call.function.name
            try:
                fn_args = json.loads(tool_call.function.arguments or "{}")
            except json.JSONDecodeError:
                fn_args = {}

            try:
                result = run_tool(fn_name, fn_args)
            except Exception as e:
                result = {"ok": False, "message": str(e)}

            trace.append({"tool": fn_name, "args": fn_args, "result": result})

            messages.append({
                "role": "tool",
                "tool_call_id": tool_call.id,
                "content": json.dumps(_json_safe(result)),
            })

    return {
        "reply": "Stopped after 6 steps to avoid an endless loop.",
        "trace": trace,
        "history": messages[1:],
    }
