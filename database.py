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
import time
import threading

DB_NAME = "supershop.db"

# Global write lock: ensures only ONE thread writes to SQLite at a time.
# All DB write operations MUST acquire this lock before executing.
_db_write_lock = threading.Lock()


def get_connection():
    conn = sqlite3.connect(DB_NAME, timeout=30.0, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.execute("PRAGMA busy_timeout = 30000")
        conn.execute("PRAGMA journal_mode = WAL")
        conn.execute("PRAGMA synchronous = NORMAL")
    except Exception:
        pass
    return conn


def execute_with_retry(fn, max_retries=8, delay=0.1):
    """
    Acquires the global write lock and executes fn().
    If another thread is writing, this blocks (up to 60s) instead of crashing.
    Falls back to exponential retry on SQLite lock errors.
    """
    acquired = _db_write_lock.acquire(timeout=60.0)
    if not acquired:
        raise sqlite3.OperationalError("Could not acquire DB write lock within 60 seconds")
    try:
        for attempt in range(max_retries):
            try:
                return fn()
            except sqlite3.OperationalError as e:
                if "locked" in str(e).lower() and attempt < max_retries - 1:
                    time.sleep(delay * (2 ** attempt))
                else:
                    raise
    finally:
        _db_write_lock.release()


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
        unit TEXT NOT NULL DEFAULT '',
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
        cashier_id INTEGER NOT NULL DEFAULT 1,
        customer_id TEXT NOT NULL DEFAULT '',
        customer_name TEXT NOT NULL DEFAULT '',
        customer_mobile TEXT NOT NULL DEFAULT '',
        channel TEXT NOT NULL DEFAULT 'Offline',
        total_amount REAL NOT NULL,
        rounded_total REAL NOT NULL DEFAULT 0,
        vat_amount REAL NOT NULL DEFAULT 0,
        saved_amount REAL NOT NULL DEFAULT 0,
        cash_amount REAL NOT NULL DEFAULT 0,
        card_amount REAL NOT NULL DEFAULT 0,
        change_amount REAL NOT NULL DEFAULT 0,
        print_count INTEGER NOT NULL DEFAULT 0,
        is_synced INTEGER NOT NULL DEFAULT 0,
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

    CREATE TABLE IF NOT EXISTS system_snapshots (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        snapshot_time TEXT NOT NULL,
        label TEXT NOT NULL,
        snapshot_json TEXT NOT NULL,
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

    CREATE TABLE IF NOT EXISTS rider_payouts (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        rider_id INTEGER NOT NULL,
        amount REAL NOT NULL,
        payout_date TEXT NOT NULL,
        payment_method TEXT NOT NULL DEFAULT 'Cash',
        note TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        FOREIGN KEY (rider_id) REFERENCES users(id) ON DELETE CASCADE
    );
    """)

    migrations = [
        "ALTER TABLE products ADD COLUMN unit TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE categories ADD COLUMN parent_id INTEGER DEFAULT NULL",
        "ALTER TABLE categories ADD COLUMN icon TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE sub_categories ADD COLUMN icon TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE sub_sub_categories ADD COLUMN icon TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE products ADD COLUMN sub_category_id INTEGER DEFAULT NULL",
        "ALTER TABLE products ADD COLUMN sub_sub_category_id INTEGER DEFAULT NULL",
        "ALTER TABLE products ADD COLUMN brand TEXT NOT NULL DEFAULT ''",
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
        "ALTER TABLE ledger_entries ADD COLUMN target_segment TEXT NOT NULL DEFAULT 'all'",
        "ALTER TABLE online_orders ADD COLUMN rider_fee REAL NOT NULL DEFAULT 0.0",
        "ALTER TABLE customer_users ADD COLUMN profile_image TEXT NOT NULL DEFAULT ''",
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

    # Seed default taxonomy (categories, sub-categories, sub-sub-categories) if empty
    cur.execute("SELECT COUNT(*) AS c FROM categories")
    if cur.fetchone()["c"] == 0:
        default_cats = [
            ("Groceries & Pets", "🛒"),
            ("Electronics & Appliances", "⚡"),
            ("Health & Beauty", "💄"),
            ("Fashion & Apparel", "👔"),
            ("Home & Lifestyle", "🏠"),
            ("Toys, Games & Stationery", "🎮"),
            ("Automotive & Hardware", "🛠️"),
        ]
        for name, icon in default_cats:
            cur.execute("INSERT OR IGNORE INTO categories (name, icon) VALUES (?, ?)", (name, icon))

    cur.execute("SELECT COUNT(*) AS c FROM sub_categories")
    if cur.fetchone()["c"] == 0:
        cat_map = {row["name"]: row["id"] for row in cur.execute("SELECT id, name FROM categories").fetchall()}
        default_subs = [
            ("Dairy & Bakery", "🍞", "Groceries & Pets"),
            ("Beverages", "🧃", "Groceries & Pets"),
            ("Snacks & Branded Foods", "🍿", "Groceries & Pets"),
            ("Rice, Atta & Cooking Oils", "🌾", "Groceries & Pets"),
            ("Fruits & Vegetables", "🍎", "Groceries & Pets"),
            ("Personal Care & Household", "🧼", "Groceries & Pets"),
            ("Mobile & Accessories", "📱", "Electronics & Appliances"),
            ("Home & Kitchen Appliances", "🔌", "Electronics & Appliances"),
            ("Computer & IT Accessories", "💻", "Electronics & Appliances"),
            ("Skin & Body Care", "🧴", "Health & Beauty"),
            ("Hair Care & Grooming", "✂️", "Health & Beauty"),
            ("Hygiene & Tissue", "🧻", "Health & Beauty"),
            ("Men's Clothing", "👔", "Fashion & Apparel"),
            ("Women's Clothing", "👗", "Fashion & Apparel"),
            ("Kids & Baby Wear", "👶", "Fashion & Apparel"),
            ("Cleaning Supplies", "🧹", "Home & Lifestyle"),
            ("Kitchen & Dining", "🍽️", "Home & Lifestyle"),
        ]
        for s_name, s_icon, c_name in default_subs:
            if c_name in cat_map:
                cur.execute("INSERT OR IGNORE INTO sub_categories (category_id, name, icon) VALUES (?, ?, ?)", (cat_map[c_name], s_name, s_icon))

    cur.execute("SELECT COUNT(*) AS c FROM sub_sub_categories")
    if cur.fetchone()["c"] == 0:
        sub_map = {row["name"]: row["id"] for row in cur.execute("SELECT id, name FROM sub_categories").fetchall()}
        default_subsubs = [
            ("Milk & Cream", "🥛", "Dairy & Bakery"),
            ("Bread & Buns", "🍞", "Dairy & Bakery"),
            ("Butter & Cheese", "🧀", "Dairy & Bakery"),
            ("Tea & Coffee", "☕", "Beverages"),
            ("Soft Drinks & Juices", "🧃", "Beverages"),
            ("Biscuits & Cookies", "🍪", "Snacks & Branded Foods"),
            ("Chips & Chanachur", "🍿", "Snacks & Branded Foods"),
            ("Chocolates & Candy", "🍫", "Snacks & Branded Foods"),
            ("Smartphones", "📱", "Mobile & Accessories"),
            ("Chargers & Cables", "⚡", "Mobile & Accessories"),
            ("Earphones & Headphones", "🎧", "Mobile & Accessories"),
            ("Soaps & Body Wash", "🧼", "Skin & Body Care"),
            ("Shampoo & Conditioner", "🧴", "Hair Care & Grooming"),
            ("Facial Tissue & Wipes", "🧻", "Hygiene & Tissue"),
        ]
        for ss_name, ss_icon, s_name in default_subsubs:
            if s_name in sub_map:
                cur.execute("INSERT OR IGNORE INTO sub_sub_categories (sub_category_id, name, icon) VALUES (?, ?, ?)", (sub_map[s_name], ss_name, ss_icon))

    # Seed default shop settings (only if not already present) so the Settings
    # page and every receipt/label always has a value to fall back on.
    default_settings = {
        "shop_name": "DOINEEK",
        "shop_address": "House 12, Road 5, Dhanmondi, Dhaka-1205",
        "shop_phone": "+880-1XXX-XXXXXX",
        "vat_reg_no": "0",
        "delivery_charge": "60",
        "product_image_bg_color": "#FFFFFF",
        "rider_delivery_fee": "50",
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
    "product_image_bg_color": "#FFFFFF",
    "rider_delivery_fee": "50",
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
    """Generates unique incrementing product serials (a_code) for each physical item in bulk."""
    if quantity <= 0:
        return []

    cur = conn.cursor()
    row = cur.execute(
        "SELECT COALESCE(MAX(sl_number), 0) AS m FROM product_units WHERE product_id = ?",
        (product_id,)
    ).fetchone()
    next_sl = row["m"] + 1

    max_id_row = cur.execute("SELECT COALESCE(MAX(id), 0) AS m FROM product_units").fetchone()
    start_id = max_id_row["m"] + 1
    now = datetime.now().isoformat()

    bulk_rows = []
    created_ids = []

    for i in range(quantity):
        curr_id = start_id + i
        sl_num = next_sl + i
        a_code = f"SN-{curr_id:06d}"
        bulk_rows.append((curr_id, product_id, a_code, sl_num, 'in_stock', now))
        created_ids.append(curr_id)

    cur.executemany(
        "INSERT INTO product_units (id, product_id, a_code, sl_number, status, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        bulk_rows
    )
    return created_ids


def create_system_snapshot(conn=None, label="Automated System Backup"):
    """Captures full JSON snapshot of system state for point-in-time restore."""
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True

    try:
        data = {
            "products": [dict(r) for r in conn.execute("SELECT * FROM products").fetchall()],
            "categories": [dict(r) for r in conn.execute("SELECT * FROM categories").fetchall()],
            "sub_categories": [dict(r) for r in conn.execute("SELECT * FROM sub_categories").fetchall()],
            "sub_sub_categories": [dict(r) for r in conn.execute("SELECT * FROM sub_sub_categories").fetchall()],
            "brands": [dict(r) for r in conn.execute("SELECT * FROM brands").fetchall()],
            "packages": [dict(r) for r in conn.execute("SELECT * FROM packages").fetchall()],
            "package_items": [dict(r) for r in conn.execute("SELECT * FROM package_items").fetchall()],
            "sales": [dict(r) for r in conn.execute("SELECT * FROM sales").fetchall()],
            "sale_items": [dict(r) for r in conn.execute("SELECT * FROM sale_items").fetchall()],
            "online_orders": [dict(r) for r in conn.execute("SELECT * FROM online_orders").fetchall()],
            "online_order_items": [dict(r) for r in conn.execute("SELECT * FROM online_order_items").fetchall()],
            "vouchers": [dict(r) for r in conn.execute("SELECT * FROM vouchers").fetchall()],
            "settings": [dict(r) for r in conn.execute("SELECT * FROM settings").fetchall()],
            "delivery_areas": [dict(r) for r in conn.execute("SELECT * FROM delivery_areas").fetchall()],
        }

        now_str = datetime.now().isoformat()
        import json
        snap_json = json.dumps(data)

        cur = conn.cursor()
        cur.execute("""
            CREATE TABLE IF NOT EXISTS system_snapshots (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                snapshot_time TEXT NOT NULL,
                label TEXT NOT NULL,
                snapshot_json TEXT NOT NULL,
                created_at TEXT NOT NULL
            )
        """)
        cur.execute(
            "INSERT INTO system_snapshots (snapshot_time, label, snapshot_json, created_at) VALUES (?, ?, ?, ?)",
            (now_str, label, snap_json, now_str)
        )
        conn.commit()
        snap_id = cur.lastrowid
        return snap_id, now_str
    finally:
        if close_conn:
            conn.close()


def restore_system_snapshot(snapshot_id_or_time, conn=None):
    """Restores SQLite database state to a specific snapshot ID or closest Datetime."""
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True

    try:
        import json
        row = None
        if isinstance(snapshot_id_or_time, int) or (isinstance(snapshot_id_or_time, str) and str(snapshot_id_or_time).isdigit()):
            row = conn.execute("SELECT * FROM system_snapshots WHERE id = ?", (int(snapshot_id_or_time),)).fetchone()
        
        if not row and isinstance(snapshot_id_or_time, str):
            # Find closest snapshot created on or before target datetime string
            row = conn.execute(
                "SELECT * FROM system_snapshots WHERE snapshot_time <= ? ORDER BY snapshot_time DESC LIMIT 1",
                (snapshot_id_or_time,)
            ).fetchone()
            if not row:
                row = conn.execute("SELECT * FROM system_snapshots ORDER BY snapshot_time ASC LIMIT 1").fetchone()

        if not row:
            return False, "No matching system snapshot found for the selected datetime."

        snap_data = json.loads(row["snapshot_json"])
        snap_time = row["snapshot_time"]

        conn.execute("PRAGMA foreign_keys = OFF;")
        cur = conn.cursor()

        tables_to_clear = [
            "package_items", "packages", "sale_items", "sales",
            "online_order_items", "online_orders", "product_units",
            "products", "sub_sub_categories", "sub_categories",
            "categories", "brands", "vouchers", "delivery_areas", "settings"
        ]

        for tbl in tables_to_clear:
            try:
                cur.execute(f"DELETE FROM {tbl}")
            except Exception:
                pass

        def _bulk_insert(table_name, row_list):
            if not row_list:
                return
            cols = list(row_list[0].keys())
            placeholders = ", ".join(["?"] * len(cols))
            col_names = ", ".join(cols)
            sql = f"INSERT INTO {table_name} ({col_names}) VALUES ({placeholders})"
            for r in row_list:
                vals = [r[c] for c in cols]
                cur.execute(sql, vals)

        for key in ["categories", "sub_categories", "sub_sub_categories", "brands", "products", "packages", "package_items", "sales", "sale_items", "online_orders", "online_order_items", "vouchers", "settings", "delivery_areas"]:
            if key in snap_data:
                _bulk_insert(key, snap_data[key])

        conn.commit()
        conn.execute("PRAGMA foreign_keys = ON;")
        return True, f"System successfully restored to snapshot from {snap_time}!"
    finally:
        if close_conn:
            conn.close()