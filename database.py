"""
database.py
------------
Everything related to talking to our SQLite database lives here.
SQLite stores the entire database in a single file (supershop.db).
"""

import sqlite3
from datetime import datetime
import math
import random

DB_NAME = "supershop.db"


def get_connection():
    conn = sqlite3.connect(DB_NAME, timeout=60.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 60000")
    return conn


def init_db():
    conn = sqlite3.connect(DB_NAME, timeout=60.0)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA busy_timeout = 60000")
    conn.execute("PRAGMA foreign_keys = OFF")
    cur = conn.cursor()

    cur.executescript("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password_hash TEXT NOT NULL,
        role TEXT NOT NULL CHECK(role IN ('admin', 'cashier', 'delivery')),
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL
    );

    CREATE TABLE IF NOT EXISTS products (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sku TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        brand TEXT NOT NULL DEFAULT '',
        category_id INTEGER,
        cost_price REAL NOT NULL DEFAULT 0,
        mrp REAL NOT NULL DEFAULT 0,
        sell_price REAL NOT NULL DEFAULT 0,
        vat_pct REAL NOT NULL DEFAULT 0,
        stock_qty INTEGER NOT NULL DEFAULT 0,
        low_stock_threshold INTEGER NOT NULL DEFAULT 5,
        sl_number INTEGER NOT NULL DEFAULT 1,
        description TEXT NOT NULL DEFAULT '',
        image_url TEXT NOT NULL DEFAULT '',
        is_trending INTEGER NOT NULL DEFAULT 0,
        is_flash_sale INTEGER NOT NULL DEFAULT 0,
        is_offer INTEGER NOT NULL DEFAULT 0,
        offer_title TEXT NOT NULL DEFAULT '',
        offer_type TEXT NOT NULL DEFAULT '',
        offer_value TEXT NOT NULL DEFAULT '',
        offer_base TEXT NOT NULL DEFAULT 'mrp',
        FOREIGN KEY (category_id) REFERENCES categories(id)
    );

    CREATE TABLE IF NOT EXISTS delivery_areas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        country TEXT NOT NULL DEFAULT 'Bangladesh',
        district TEXT NOT NULL,
        area TEXT NOT NULL,
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS online_orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_number TEXT UNIQUE NOT NULL,
        customer_name TEXT NOT NULL,
        customer_phone TEXT NOT NULL,
        customer_email TEXT NOT NULL DEFAULT '',
        country TEXT NOT NULL DEFAULT 'Bangladesh',
        district TEXT NOT NULL,
        area TEXT NOT NULL,
        address_details TEXT NOT NULL,
        payment_method TEXT NOT NULL DEFAULT 'cod',
        payment_status TEXT NOT NULL DEFAULT 'pending',
        subtotal REAL NOT NULL DEFAULT 0,
        delivery_charge REAL NOT NULL DEFAULT 0,
        total_amount REAL NOT NULL DEFAULT 0,
        order_status TEXT NOT NULL DEFAULT 'new',
        delivery_otp TEXT NOT NULL DEFAULT '',
        is_stock_deducted INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS online_order_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_id INTEGER NOT NULL,
        product_id INTEGER NOT NULL,
        product_name TEXT NOT NULL,
        unit_price REAL NOT NULL,
        mrp_price REAL NOT NULL DEFAULT 0,
        quantity INTEGER NOT NULL,
        total_price REAL NOT NULL,
        FOREIGN KEY (order_id) REFERENCES online_orders(id),
        FOREIGN KEY (product_id) REFERENCES products(id)
    );

    CREATE TABLE IF NOT EXISTS customer_users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        phone TEXT UNIQUE NOT NULL,
        name TEXT NOT NULL,
        email TEXT DEFAULT '',
        password_hash TEXT NOT NULL,
        is_verified INTEGER NOT NULL DEFAULT 1,
        is_blocked INTEGER NOT NULL DEFAULT 0,
        blocked_until TEXT NOT NULL DEFAULT '',
        block_reason TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS sales (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        invoice_number TEXT UNIQUE NOT NULL DEFAULT '',
        invoice_date TEXT NOT NULL DEFAULT '',
        cashier_id INTEGER NOT NULL,
        customer_id TEXT NOT NULL DEFAULT '',
        total_amount REAL NOT NULL,
        rounded_total REAL NOT NULL DEFAULT 0,
        vat_amount REAL NOT NULL DEFAULT 0,
        saved_amount REAL NOT NULL DEFAULT 0,
        cash_amount REAL NOT NULL DEFAULT 0,
        card_amount REAL NOT NULL DEFAULT 0,
        change_amount REAL NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL,
        FOREIGN KEY (cashier_id) REFERENCES users(id)
    );

    CREATE TABLE IF NOT EXISTS sale_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sale_id INTEGER NOT NULL,
        product_id INTEGER NOT NULL,
        quantity INTEGER NOT NULL,
        unit_price REAL NOT NULL,
        mrp_price REAL NOT NULL DEFAULT 0,
        vat_pct REAL NOT NULL DEFAULT 0,
        vat_amount REAL NOT NULL DEFAULT 0,
        cost_price REAL NOT NULL DEFAULT 0,
        FOREIGN KEY (sale_id) REFERENCES sales(id),
        FOREIGN KEY (product_id) REFERENCES products(id)
    );

    CREATE TABLE IF NOT EXISTS product_units (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER NOT NULL,
        a_code TEXT UNIQUE NOT NULL,
        sl_number INTEGER NOT NULL DEFAULT 0,
        status TEXT NOT NULL DEFAULT 'in_stock',
        created_at TEXT NOT NULL,
        FOREIGN KEY (product_id) REFERENCES products(id)
    );

    CREATE TABLE IF NOT EXISTS ledger_entries (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        entry_type TEXT NOT NULL CHECK(entry_type IN ('income', 'expense')),
        title TEXT NOT NULL,
        amount REAL NOT NULL DEFAULT 0,
        entry_date TEXT NOT NULL,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS settings (
        key TEXT PRIMARY KEY,
        value TEXT NOT NULL DEFAULT ''
    );

    CREATE TABLE IF NOT EXISTS sub_categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        category_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        icon TEXT NOT NULL DEFAULT '',
        FOREIGN KEY (category_id) REFERENCES categories(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS sub_sub_categories (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sub_category_id INTEGER NOT NULL,
        name TEXT NOT NULL,
        icon TEXT NOT NULL DEFAULT '',
        FOREIGN KEY (sub_category_id) REFERENCES sub_categories(id) ON DELETE CASCADE
    );

    CREATE TABLE IF NOT EXISTS brands (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT UNIQUE NOT NULL,
        logo TEXT NOT NULL DEFAULT ''
    );

    CREATE TABLE IF NOT EXISTS vouchers (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        code TEXT UNIQUE NOT NULL,
        discount_type TEXT NOT NULL DEFAULT 'percentage',
        discount_value REAL NOT NULL DEFAULT 0,
        discount_base TEXT NOT NULL DEFAULT 'sell_price',
        target_type TEXT NOT NULL DEFAULT 'product_discount',
        expiry_date TEXT NOT NULL DEFAULT '',
        scope_type TEXT NOT NULL DEFAULT 'all',
        scope_id INTEGER DEFAULT NULL,
        active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS returned_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        product_id INTEGER,
        item_name TEXT NOT NULL,
        quantity INTEGER NOT NULL DEFAULT 1,
        reason TEXT NOT NULL DEFAULT '',
        expiry_date TEXT NOT NULL DEFAULT '',
        date_returned TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS packages (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        image_url TEXT NOT NULL DEFAULT '',
        package_price REAL NOT NULL,
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS package_items (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        package_id INTEGER NOT NULL,
        product_id INTEGER NOT NULL,
        quantity INTEGER NOT NULL DEFAULT 1,
        FOREIGN KEY (package_id) REFERENCES packages(id) ON DELETE CASCADE,
        FOREIGN KEY (product_id) REFERENCES products(id) ON DELETE CASCADE
    );
    """)

    migrations = [
        "ALTER TABLE categories ADD COLUMN parent_id INTEGER DEFAULT NULL",
        "ALTER TABLE categories ADD COLUMN icon TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE sub_categories ADD COLUMN icon TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE sub_sub_categories ADD COLUMN icon TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE products ADD COLUMN sub_category_id INTEGER DEFAULT NULL",
        "ALTER TABLE products ADD COLUMN sub_sub_category_id INTEGER DEFAULT NULL",
        "ALTER TABLE products ADD COLUMN is_promotion INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE products ADD COLUMN mrp REAL NOT NULL DEFAULT 0",
        "ALTER TABLE products ADD COLUMN sl_number INTEGER NOT NULL DEFAULT 1",
        "ALTER TABLE products ADD COLUMN description TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE products ADD COLUMN image_url TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE products ADD COLUMN is_trending INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE products ADD COLUMN is_flash_sale INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE products ADD COLUMN is_offer INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE products ADD COLUMN offer_title TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE products ADD COLUMN expiry_date TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE sales ADD COLUMN rounded_total REAL NOT NULL DEFAULT 0",
        "ALTER TABLE sales ADD COLUMN saved_amount REAL NOT NULL DEFAULT 0",
        "ALTER TABLE sales ADD COLUMN cash_amount REAL NOT NULL DEFAULT 0",
        "ALTER TABLE sales ADD COLUMN card_amount REAL NOT NULL DEFAULT 0",
        "ALTER TABLE sales ADD COLUMN change_amount REAL NOT NULL DEFAULT 0",
        "ALTER TABLE sale_items ADD COLUMN mrp_price REAL NOT NULL DEFAULT 0",
        "ALTER TABLE products ADD COLUMN vat_pct REAL NOT NULL DEFAULT 0",
        "ALTER TABLE sales ADD COLUMN invoice_number TEXT UNIQUE NOT NULL DEFAULT ''",
        "ALTER TABLE sales ADD COLUMN invoice_date TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE sales ADD COLUMN customer_id TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE sales ADD COLUMN vat_amount REAL NOT NULL DEFAULT 0",
        "ALTER TABLE sale_items ADD COLUMN vat_pct REAL NOT NULL DEFAULT 0",
        "ALTER TABLE sale_items ADD COLUMN vat_amount REAL NOT NULL DEFAULT 0",
        "ALTER TABLE sale_items ADD COLUMN cost_price REAL NOT NULL DEFAULT 0",
        "ALTER TABLE sale_items ADD COLUMN unit_serials TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE products ADD COLUMN label_print_count INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE sales ADD COLUMN customer_name TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE sales ADD COLUMN customer_mobile TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE sales ADD COLUMN print_count INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE sales ADD COLUMN is_synced INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE products ADD COLUMN offer_type TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE products ADD COLUMN offer_value TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE products ADD COLUMN offer_base TEXT NOT NULL DEFAULT 'mrp'",
        "ALTER TABLE sales ADD COLUMN channel TEXT NOT NULL DEFAULT 'Offline'",
        "ALTER TABLE online_orders ADD COLUMN is_stock_deducted INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE customer_users ADD COLUMN is_blocked INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE customer_users ADD COLUMN blocked_until TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE customer_users ADD COLUMN block_reason TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE users ADD COLUMN full_name TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1",
        "ALTER TABLE customer_users ADD COLUMN plain_password TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE online_orders ADD COLUMN assigned_rider_id INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE online_orders ADD COLUMN assigned_rider_name TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE online_orders ADD COLUMN assigned_rider_phone TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE vouchers ADD COLUMN discount_base TEXT NOT NULL DEFAULT 'sell_price'",
        "ALTER TABLE vouchers ADD COLUMN target_type TEXT NOT NULL DEFAULT 'product_discount'",
        "ALTER TABLE vouchers ADD COLUMN expiry_date TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE users ADD COLUMN plain_password TEXT NOT NULL DEFAULT ''",
    ]
    for statement in migrations:
        try:
            cur.execute(statement)
        except sqlite3.OperationalError:
            pass

    # Check if 'users' table accepts 'delivery' role
    try:
        cur.execute("INSERT INTO users (username, password_hash, role, created_at) VALUES ('__test_del__', 'x', 'delivery', '')")
        cur.execute("DELETE FROM users WHERE username = '__test_del__'")
    except sqlite3.IntegrityError:
        cur.execute("PRAGMA foreign_keys = OFF")
        cur.execute("CREATE TABLE users_dg_tmp AS SELECT * FROM users")
        cur.execute("DROP TABLE users")
        cur.execute("""
            CREATE TABLE users (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                username TEXT UNIQUE NOT NULL,
                password_hash TEXT NOT NULL,
                role TEXT NOT NULL DEFAULT 'cashier',
                created_at TEXT NOT NULL,
                full_name TEXT NOT NULL DEFAULT '',
                is_active INTEGER NOT NULL DEFAULT 1,
                plain_password TEXT NOT NULL DEFAULT ''
            )
        """)
        columns = [c[1] for c in cur.execute("PRAGMA table_info(users_dg_tmp)").fetchall()]
        fn_col = "full_name" if "full_name" in columns else "''"
        ia_col = "is_active" if "is_active" in columns else "1"
        pw_col = "plain_password" if "plain_password" in columns else "''"
        cur.execute(f"""
            INSERT INTO users (id, username, password_hash, role, created_at, full_name, is_active, plain_password)
            SELECT id, username, password_hash, role, created_at, {fn_col}, {ia_col}, {pw_col}
            FROM users_dg_tmp
        """)
        cur.execute("DROP TABLE users_dg_tmp")
        cur.execute("PRAGMA foreign_keys = ON")
        conn.commit()

    cur.execute("SELECT COUNT(*) AS c FROM users")
    if cur.fetchone()["c"] == 0:
        from werkzeug.security import generate_password_hash
        cur.execute(
            "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
            ("admin", generate_password_hash("admin123"), "admin", datetime.now().isoformat())
        )

    cur.execute("SELECT COUNT(*) AS c FROM delivery_areas")
    if cur.fetchone()["c"] == 0:
        now_iso = datetime.now().isoformat()
        cur.execute(
            "INSERT INTO delivery_areas (country, district, area, is_active, created_at) VALUES (?, ?, ?, 1, ?)",
            ("Bangladesh", "Tangail", "Akur Takur Para", now_iso)
        )
        cur.execute(
            "INSERT INTO delivery_areas (country, district, area, is_active, created_at) VALUES (?, ?, ?, 1, ?)",
            ("Bangladesh", "Tangail", "College Para", now_iso)
        )

    # Seed default shop settings (only if not already present) so the Settings
    # page and every receipt/label always has a value to fall back on.
    default_settings = {
        "shop_name": "DOINEEK",
        "shop_address": "House 12, Road 5, Dhanmondi, Dhaka-1205",
        "shop_phone": "+880-1XXX-XXXXXX",
        "vat_reg_no": "0",
        "delivery_charge": "60",
    }
    for key, value in default_settings.items():
        cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, value))

    conn.commit()
    conn.close()


DEFAULT_SETTINGS = {
    "shop_name": "DOINEEK",
    "shop_address": "House 12, Road 5, Dhanmondi, Dhaka-1205",
    "shop_phone": "+880-1XXX-XXXXXX",
    "vat_reg_no": "0",
    "delivery_charge": "60",
}


def get_all_settings(conn=None):
    """Return a dict of shop settings, always filled in with sane defaults."""
    close_after = False
    if conn is None:
        conn = get_connection()
        close_after = True
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    if close_after:
        conn.close()
    result = DEFAULT_SETTINGS.copy()
    for row in rows:
        if row["value"] not in (None, ""):
            result[row["key"]] = row["value"]
    return result


def update_settings(conn, values: dict):
    """Upsert a dict of {key: value} into the settings table."""
    for key, value in values.items():
        conn.execute(
            "INSERT INTO settings (key, value) VALUES (?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value)
        )


def round_to_whole(amount):
    fraction = amount - math.floor(amount)
    if fraction >= 0.50:
        return float(math.ceil(amount))
    return float(math.floor(amount))


def generate_invoice_number():
    now = datetime.now()
    date_part = now.strftime("%Y%m%d")
    rand_part = random.randint(1000, 9999)
    return f"INV-{date_part}-{rand_part}"


def create_product_units(conn, product_id, quantity):
    """Generates unique incrementing product serials (a_code) for each physical item."""
    if quantity <= 0:
        return []

    cur = conn.cursor()
    row = cur.execute(
        "SELECT COALESCE(MAX(sl_number), 0) AS m FROM product_units WHERE product_id = ?",
        (product_id,)
    ).fetchone()
    next_sl = row["m"] + 1
    now = datetime.now().isoformat()

    created_ids = []
    for i in range(quantity):
        cur.execute(
            "INSERT INTO product_units (product_id, a_code, sl_number, status, created_at) "
            "VALUES (?, 'PENDING', ?, 'in_stock', ?)",
            (product_id, next_sl + i, now)
        )
        new_id = cur.lastrowid
        # "SN-" prefix + zero-padded id: visually and structurally distinct
        # from typical SKU formats (e.g. "SKU-A", "SKU200"), so a serial can
        # never be mistaken for - or accidentally collide with - a SKU.
        a_code = f"SN-{new_id:06d}"
        cur.execute("UPDATE product_units SET a_code = ? WHERE id = ?", (a_code, new_id))
        created_ids.append(new_id)

    return created_ids