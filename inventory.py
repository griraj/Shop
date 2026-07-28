

import os
import sys
from decimal import Decimal, InvalidOperation

import psycopg
from psycopg.rows import dict_row
from dotenv import load_dotenv

load_dotenv()

api_key = os.environ.get("OPENAI_API_KEY")
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
            FROM categories c~
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
    # Decrypt from storage, then re-encrypt with user's shift for display
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
