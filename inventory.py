
import os
import sys
import json
import urllib.request
import urllib.error
from decimal import Decimal, InvalidOperation

import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv

load_dotenv()

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY")
GEMINI_BASE_URL = os.environ.get("GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta/models")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
ENCRYPTION_SHIFT = 5  

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


def get_connection():
    try:
        return psycopg.connect(
            host=os.getenv("PGHOST", "localhost"),
            port=os.getenv("PGPORT", "5432"),
            dbname=os.getenv("PGDATABASE", "Shop"),
            user=os.getenv("PGUSER", "postgres"),
            password=os.getenv("PGPASSWORD", ""),
        )
    except psycopg.OperationalError as e:
        print(f"\n[ERROR] Could not connect to the database:\n  {e}")
        print("Check your .env file (PGHOST/PGPORT/PGDATABASE/PGUSER/PGPASSWORD) and that Postgres is running.\n")
        sys.exit(1)


def print_header(title):
    print("\n" + "=" * 60)
    print(f" {title}")
    print("=" * 60)


def print_table(rows, columns):
    if not rows:
        print("  (no rows to show)")
        return

    widths = {}
    for col in columns:
        widths[col] = max(len(col), max(len(str(row.get(col, ""))) for row in rows))

    header = "  ".join(col.ljust(widths[col]) for col in columns)
    print(header)
    print("  ".join("-" * widths[col] for col in columns))
    for row in rows:
        print("  ".join(str(row.get(col, "")).ljust(widths[col]) for col in columns))


def pause():
    input("\nPress Enter to continue...")


def view_items(conn):
    print_header("Items")
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT i.itemid, i.itemname, i.price, i.stockquantity, c.categoryname
            FROM items i
            LEFT JOIN categories c ON i.categoryid = c.categoryid
            ORDER BY i.itemid
        """)
        rows = cur.fetchall()
    # Decrypt item names for display
    for row in rows:
        row['itemname'] = decrypt_text(row['itemname'])
    print_table(rows, ["itemid", "itemname", "price", "stockquantity", "categoryname"])
    pause()


def view_categories(conn):
    print_header("Categories")
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT c.categoryid, c.categoryname, Count(i.itemid) As item_count
            FROM categories c
            LEFT JOIN items i ON i.categoryid = c.categoryid
            GROUP BY c.categoryid, c.categoryname
            ORDER BY c.categoryid
        """)
        rows = cur.fetchall()
    print_table(rows, ["categoryid", "categoryname", "item_count"])
    pause()


def add_item(conn):
    print_header("Add a new item")
    name = input("Item name : ").strip()
    if not name:
        print("[!] Item name cannot be empty.")
        pause()
        return

    price = prompt_decimal("Price : ")
    if price is None:
        return

    stock = prompt_int("Stock quantity : ")
    if stock is None:
        return

    view_categories_inline(conn)
    category_id = prompt_int("Category ID (from the list above) : ")
    if category_id is None:
        return

    encrypted_name = encrypt_text(name)
    arr = [None, encrypted_name, str(price), str(stock), str(category_id)]

    try:
        with conn.cursor() as cur:
            cur.execute("CALL manage_item(%s::varchar, %s::text[])", ('I', arr))
        conn.commit()
        print(f"\n[OK] '{name}' added successfully.")
    except Exception as e:
        conn.rollback()
        print(f"\n[ERROR] Could not add item: {e}")
    pause()


def update_item(conn):
    print_header("Update an item")
    view_items_inline(conn)
    item_id = prompt_int("Item ID to update : ")
    if item_id is None:
        return

    print("Leave a field blank to keep its current value.")
    price = input("New price (blank = unchanged) : ").strip()
    stock = input("New stock quantity (blank = unchanged) : ").strip()
    category = input("New category ID (blank = unchanged) : ").strip()

    arr = [
        str(item_id),
        None,
        price if price else None,
        stock if stock else None,
        category if category else None,
    ]

    try:
        with conn.cursor() as cur:
            cur.execute("CALL manage_item(%s::varchar, %s::text[])", ('U', arr))
        conn.commit()
        print(f"\n[OK] Item #{item_id} updated successfully.")
    except Exception as e:
        conn.rollback()
        print(f"\n[ERROR] Could not update item: {e}")
    pause()


def delete_item(conn):
    print_header("Delete an item")
    view_items_inline(conn)
    item_id = prompt_int("Item ID to delete : ")
    if item_id is None:
        return

    confirm = input(f"Type 'yes' to confirm deleting item #{item_id}: ").strip().lower()
    if confirm != "yes":
        print("Cancelled.")
        pause()
        return

    arr = [str(item_id), None, None, None, None]

    try:
        with conn.cursor() as cur:
            cur.execute("CALL manage_item(%s::varchar, %s::text[])", ('D', arr))
        conn.commit()
        print(f"\n[OK] Item #{item_id} deleted successfully.")
    except Exception as e:
        conn.rollback()
        print(f"\n[ERROR] Could not delete item : {e}")
    pause()


def view_encrypted(conn):
    print_header("Encrypted item names")
    shift = prompt_int("Shift value (e.g. 5) :  ", allow_default=5)
    if shift is None:
        shift = 5
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT itemid, itemname FROM items ORDER BY itemid")
        rows = cur.fetchall()

    for row in rows:
        decrypted = decrypt_text(row['itemname'])
        row['decrypted_name'] = decrypted
        row['re_encrypted'] = encrypt_text(decrypted, shift)
    print_table(rows, ["itemid", "decrypted_name", "re_encrypted"])
    pause()


def view_audit(conn):
    print_header("Audit trail (most recent first)")
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT * FROM items_audit ORDER BY changed_at DESC, audit_id DESC LIMIT 25")
        rows = cur.fetchall()
    print_table(rows, ["audit_id", "item_id", "action_type", "old_price", "new_price", "changed_at"])
    pause()


def view_items_inline(conn):
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT itemid, itemname, price, stockquantity FROM items ORDER BY itemid")
        rows = cur.fetchall()
    # Decrypt item names for display
    for row in rows:
        row['itemname'] = decrypt_text(row['itemname'])
    print_table(rows, ["itemid", "itemname", "price", "stockquantity"])


def view_categories_inline(conn):
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT categoryid, categoryname FROM categories ORDER BY categoryid")
        rows = cur.fetchall()
    print_table(rows, ["categoryid", "categoryname"])



def prompt_decimal(label):
    raw = input(label).strip()
    try:
        return Decimal(raw)
    except InvalidOperation:
        print("[!] Please enter a valid number.")
        pause()
        return None


def prompt_int(label, allow_default=None):
    raw = input(label).strip()
    if not raw and allow_default is not None:
        return allow_default
    try:
        return int(raw)
    except ValueError:
        print("[!] Please enter a whole number.")
        if allow_default is None:
            pause()
        return None


def migrate():
    """Migrate and encrypt all existing item names in the database."""
    confirm = input("This will encrypt all existing item names. Continue? (yes/no): ").strip().lower()
    if confirm != "yes":
        print("Cancelled.")
        pause()
        return
    
    conn = get_connection()
    print("Connected to database. Fetching all items...")
    
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT itemid, itemname FROM items")
        items = cur.fetchall()
    
    print(f"Found {len(items)} items to encrypt.")
    
    if len(items) == 0:
        print("No items to encrypt.")
        conn.close()
        pause()
        return
    
    # Update each item with encrypted name
    updated_count = 0
    for item in items:
        encrypted_name = encrypt_text(item['itemname'])
        print(f"  Encrypting: {item['itemname']} -> {encrypted_name}")
        
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE items SET itemname = %s WHERE itemid = %s",
                (encrypted_name, item['itemid'])
            )
        updated_count += 1
    
    conn.commit()
    print(f"\n✓ Successfully encrypted {updated_count} items!")
    conn.close()
    pause()


# ---------------------------------------------------------
# GEMINI API — low-level request helper
# (uses the CURRENT Gemini API: v1beta .../{model}:generateContent
#  — not the old, deprecated v1beta2 chat-bison-001:generateMessage
#  endpoint, which is what was causing the "scalar field" error)
# ---------------------------------------------------------
def gemini_generate_content(contents, tools=None, temperature=0.7):
    """Send a request to the Gemini generateContent endpoint and return
    the model's response content block: {"role": "model", "parts": [...]}."""
    if not GEMINI_API_KEY:
        raise RuntimeError("GEMINI_API_KEY is not set. Add it to your .env file.")

    endpoint = f"{GEMINI_BASE_URL.rstrip('/')}/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "contents": contents,
        "generationConfig": {"temperature": temperature},
    }
    if tools:
        payload["tools"] = tools

    req = urllib.request.Request(
        endpoint,
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            response_text = resp.read().decode("utf-8")
    except urllib.error.HTTPError as err:
        error_body = err.read().decode("utf-8")
        raise RuntimeError(f"Gemini API error {err.code}: {error_body}") from err
    except urllib.error.URLError as err:
        raise RuntimeError(f"Gemini request failed: {err.reason}") from err

    response_data = json.loads(response_text)
    candidates = response_data.get("candidates")
    if not candidates:
        raise RuntimeError(f"Unexpected Gemini response: {response_data}")
    return candidates[0]["content"]


def gemini_text(prompt_text, temperature=0.7):
    """Simple single-turn text generation — used by the description feature."""
    content = gemini_generate_content(
        contents=[{"role": "user", "parts": [{"text": prompt_text}]}],
        temperature=temperature,
    )
    parts = content.get("parts", [])
    return "".join(p.get("text", "") for p in parts).strip()


# ---------------------------------------------------------
# GENERATIVE AI — Gemini writes a product description
# ---------------------------------------------------------
def generate_description(conn):
    """Ask Gemini API to write a short description for an existing item."""
    print_header("Generate item description (Gemini API)")
    view_items_inline(conn)
    item_id = prompt_int("Item ID to generate a description for : ")
    if item_id is None:
        return

    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("""
            SELECT i.itemname, c.categoryname
            FROM items i
            LEFT JOIN categories c ON i.categoryid = c.categoryid
            WHERE i.itemid = %s
        """, (item_id,))
        row = cur.fetchone()

    if not row:
        print("[!] No item with that ID.")
        pause()
        return

    item_name = decrypt_text(row['itemname'])
    prompt = (
        f"Write one short, appealing product description (max 25 words) for an item "
        f"called '{item_name}' in the '{row['categoryname']}' category. "
        f"Reply with only the description, no extra text."
    )

    print("\nAsking Gemini API...")
    try:
        description = gemini_text(prompt)
        print(f"\nGenerated description:\n  \"{description}\"")
    except Exception as e:
        print(f"\n[ERROR] Could not reach Gemini API: {e}")
        print("Make sure GEMINI_API_KEY is set and the model is available.")
    pause()


# ---------------------------------------------------------
# AGENTIC AI — Gemini decides which function to call
# (Gemini's function-calling schema uses UPPERCASE type names
#  and a "functionDeclarations" wrapper, unlike OpenAI/Ollama's
#  "type": "function" format.)
# ---------------------------------------------------------
AGENT_TOOLS = [
    {
        "functionDeclarations": [
            {
                "name": "list_items",
                "description": "List all items in the inventory with id, name, price, stock quantity, and category.",
                "parameters": {"type": "OBJECT", "properties": {}},
            },
            {
                "name": "list_categories",
                "description": "List all categories and how many items belong to each.",
                "parameters": {"type": "OBJECT", "properties": {}},
            },
            {
                "name": "add_item_ai",
                "description": "Add a new item to the inventory.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "name": {"type": "STRING", "description": "Item name"},
                        "price": {"type": "NUMBER", "description": "Item price"},
                        "stock": {"type": "INTEGER", "description": "Stock quantity"},
                        "category_id": {"type": "INTEGER", "description": "Category ID"},
                    },
                    "required": ["name", "price", "stock", "category_id"],
                },
            },
            {
                "name": "update_item_ai",
                "description": "Update price, stock quantity, and/or category of an existing item by its ID.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "item_id": {"type": "INTEGER", "description": "ID of the item to update"},
                        "price": {"type": "NUMBER", "description": "New price (omit if unchanged)"},
                        "stock": {"type": "INTEGER", "description": "New stock quantity (omit if unchanged)"},
                        "category_id": {"type": "INTEGER", "description": "New category ID (omit if unchanged)"},
                    },
                    "required": ["item_id"],
                },
            },
            {
                "name": "delete_item_ai",
                "description": "Delete an item from the inventory by its ID.",
                "parameters": {
                    "type": "OBJECT",
                    "properties": {
                        "item_id": {"type": "INTEGER", "description": "ID of the item to delete"},
                    },
                    "required": ["item_id"],
                },
            },
        ]
    }
]


def list_items_ai(conn):
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
    return rows


def list_categories_ai(conn):
    with conn.cursor(row_factory=dict_row) as cur:
        cur.execute("SELECT categoryid, categoryname FROM categories ORDER BY categoryid")
        return cur.fetchall()


def add_item_ai(conn, name, price, stock, category_id):
    encrypted_name = encrypt_text(str(name))
    arr = [None, encrypted_name, str(price), str(stock), str(category_id)]
    try:
        with conn.cursor() as cur:
            cur.execute("CALL manage_item(%s::varchar, %s::text[])", ('I', arr))
        conn.commit()
        return f"'{name}' added successfully."
    except Exception as e:
        conn.rollback()
        return f"[ERROR] Could not add item: {e}"


def update_item_ai(conn, item_id, price=None, stock=None, category_id=None):
    arr = [
        str(item_id),
        None,
        str(price) if price is not None else None,
        str(stock) if stock is not None else None,
        str(category_id) if category_id is not None else None,
    ]
    try:
        with conn.cursor() as cur:
            cur.execute("CALL manage_item(%s::varchar, %s::text[])", ('U', arr))
        conn.commit()
        return f"Item #{item_id} updated successfully."
    except Exception as e:
        conn.rollback()
        return f"[ERROR] Could not update item: {e}"


def delete_item_ai(conn, item_id):
    arr = [str(item_id), None, None, None, None]
    try:
        with conn.cursor() as cur:
            cur.execute("CALL manage_item(%s::varchar, %s::text[])", ('D', arr))
        conn.commit()
        return f"Item #{item_id} deleted successfully."
    except Exception as e:
        conn.rollback()
        return f"[ERROR] Could not delete item: {e}"


def run_tool(conn, name, args):
    """Dispatch a single tool call from the model to the matching function."""
    if name == "list_items":
        return list_items_ai(conn)
    if name == "list_categories":
        return list_categories_ai(conn)
    if name == "add_item_ai":
        return add_item_ai(conn, args["name"], args["price"], args["stock"], args["category_id"])
    if name == "update_item_ai":
        return update_item_ai(
            conn, args["item_id"],
            price=args.get("price"), stock=args.get("stock"), category_id=args.get("category_id"),
        )
    if name == "delete_item_ai":
        return delete_item_ai(conn, args["item_id"])
    return f"[!] Unknown tool requested: {name}"


def _json_safe(value):
    """Convert Decimal/datetime/etc from psycopg rows into plain JSON-safe data."""
    return json.loads(json.dumps(value, default=str))


def ai_agent(conn):
    """Take a plain-English request and let Gemini decide which tool(s) to call."""
    print_header("Ask in plain English (Gemini AI assistant)")
    request = input("What would you like to do? > ").strip()
    if not request:
        return

    contents = [{"role": "user", "parts": [{"text": request}]}]

    print("\nThinking...")
    try:
        for _ in range(6):  # safety cap on reasoning/tool-call rounds
            model_content = gemini_generate_content(contents, tools=AGENT_TOOLS)
            contents.append(model_content)
            parts = model_content.get("parts", [])

            function_calls = [p["functionCall"] for p in parts if "functionCall" in p]
            if not function_calls:
                text = "".join(p.get("text", "") for p in parts).strip()
                print(f"\n{text or '(no response)'}")
                break

            function_response_parts = []
            for fc in function_calls:
                fn_name = fc["name"]
                fn_args = fc.get("args", {})
                print(f"  -> calling {fn_name}({fn_args})")
                try:
                    result = run_tool(conn, fn_name, fn_args)
                except Exception as e:
                    result = f"[ERROR] {e}"

                function_response_parts.append({
                    "functionResponse": {
                        "name": fn_name,
                        "response": {"result": _json_safe(result)},
                    }
                })

            contents.append({"role": "function", "parts": function_response_parts})
        else:
            print("\n[!] Stopped after 6 steps to avoid an endless loop.")
    except Exception as e:
        print(f"\n[ERROR] Could not reach Gemini API: {e}")
        print("Make sure GEMINI_API_KEY is set and the model is available.")
    pause()


MENU = """
+----------------------------------------------------------+
|                LEDGER - INVENTORY CONSOLE                |
+----------------------------------------------------------+
| 1. View items                                             |
| 2. View categories                                        |
| 3. Add item                                                |
| 4. Update item                                             |
| 5. Delete item                                             |
| 6. View encrypted item names                               |
| 7. View audit trail                                        |
| 8. Migrate and encrypt item names                          |
| 9. Generate item description (Gemini API)                   |
| 10. Ask in plain English (Gemini AI assistant)              |
| 0. Exit                                                    |
+----------------------------------------------------------+
"""


def main():
    conn = get_connection()
    print("Connected to the database successfully.")

    actions = {
        "1": view_items,
        "2": view_categories,
        "3": add_item,
        "4": update_item,
        "5": delete_item,
        "6": view_encrypted,
        "7": view_audit,
        "8": lambda conn: migrate(),
        "9": generate_description,
        "10": ai_agent,
    }

    while True:
        print(MENU)
        choice = input("Choose an option: ").strip()

        if choice == "0":
            print("Goodbye.")
            break

        action = actions.get(choice)
        if action:
            action(conn)
        else:
            print("[!] Invalid option, try again.")

    conn.close()


if __name__ == "__main__":
    main()
