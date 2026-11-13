"""
database.py
------------
Everything related to talking to our SQLite database lives here.
SQLite stores the entire database in a single file (supershop.db).
"""

import os
import re
import json
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
        assigned_rider_id INTEGER NOT NULL DEFAULT 0,
        assigned_rider_name TEXT NOT NULL DEFAULT '',
        assigned_rider_phone TEXT NOT NULL DEFAULT '',
        rider_fee REAL NOT NULL DEFAULT 0.0,
        confirmed_at TEXT NOT NULL DEFAULT '',
        packed_at TEXT NOT NULL DEFAULT '',
        on_the_way_at TEXT NOT NULL DEFAULT '',
        delivered_at TEXT NOT NULL DEFAULT '',
        cancelled_at TEXT NOT NULL DEFAULT '',
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
        sell_price REAL NOT NULL DEFAULT 0,
        mrp REAL NOT NULL DEFAULT 0,
        batch_sl INTEGER NOT NULL DEFAULT 1,
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
        max_sale_limit INTEGER NOT NULL DEFAULT 0,
        sold_quantity INTEGER NOT NULL DEFAULT 0,
        show_in_banner INTEGER NOT NULL DEFAULT 0,
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

    CREATE TABLE IF NOT EXISTS customer_notifications (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        customer_phone TEXT DEFAULT '',
        title TEXT NOT NULL,
        message TEXT NOT NULL,
        type TEXT NOT NULL DEFAULT 'general',
        reference_id TEXT DEFAULT '',
        is_read INTEGER NOT NULL DEFAULT 0,
        created_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS customer_notification_reads (
        notification_id INTEGER,
        customer_phone TEXT,
        read_at TEXT,
        PRIMARY KEY(notification_id, customer_phone)
    );

    CREATE TABLE IF NOT EXISTS customer_notification_clears (
        customer_phone TEXT PRIMARY KEY,
        cleared_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS customer_carts (
        customer_phone TEXT PRIMARY KEY,
        items_json TEXT NOT NULL DEFAULT '[]',
        updated_at TEXT NOT NULL DEFAULT ''
    );

    CREATE TABLE IF NOT EXISTS pharmacy_medicines (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        name TEXT NOT NULL,
        generic_name TEXT NOT NULL DEFAULT '',
        dosage_form TEXT NOT NULL,
        strength TEXT NOT NULL DEFAULT '',
        manufacturer TEXT NOT NULL DEFAULT '',
        sku TEXT NOT NULL DEFAULT '',
        unit_price REAL NOT NULL DEFAULT 0.0,
        strip_price REAL NOT NULL DEFAULT 0.0,
        strip_size INTEGER NOT NULL DEFAULT 10,
        stock_qty INTEGER NOT NULL DEFAULT 999,
        is_prescription_required INTEGER NOT NULL DEFAULT 0,
        image_url TEXT NOT NULL DEFAULT '',
        description TEXT NOT NULL DEFAULT '',
        is_active INTEGER NOT NULL DEFAULT 1,
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL
    );

    CREATE TABLE IF NOT EXISTS pharmacy_orders (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        order_number TEXT UNIQUE NOT NULL,
        online_order_id INTEGER DEFAULT 0,
        customer_name TEXT NOT NULL,
        customer_phone TEXT NOT NULL,
        customer_email TEXT NOT NULL DEFAULT '',
        country TEXT NOT NULL DEFAULT 'Bangladesh',
        district TEXT NOT NULL DEFAULT 'Tangail',
        area TEXT NOT NULL DEFAULT 'Main Area',
        delivery_address TEXT NOT NULL,
        order_type TEXT NOT NULL DEFAULT 'both',
        prescription_url TEXT NOT NULL DEFAULT '',
        prescription_local_filename TEXT NOT NULL DEFAULT '',
        overall_duration_days INTEGER NOT NULL DEFAULT 0,
        customer_notes TEXT NOT NULL DEFAULT '',
        requested_items_json TEXT NOT NULL DEFAULT '[]',
        approved_items_json TEXT NOT NULL DEFAULT '[]',
        subtotal REAL NOT NULL DEFAULT 0,
        delivery_charge REAL NOT NULL DEFAULT 50,
        total_amount REAL NOT NULL DEFAULT 50,
        order_status TEXT NOT NULL DEFAULT 'reviewing',
        delivery_otp TEXT NOT NULL DEFAULT '',
        payment_method TEXT NOT NULL DEFAULT 'cod',
        payment_status TEXT NOT NULL DEFAULT 'pending',
        assigned_rider_id INTEGER NOT NULL DEFAULT 0,
        assigned_rider_name TEXT NOT NULL DEFAULT '',
        assigned_rider_phone TEXT NOT NULL DEFAULT '',
        rider_fee REAL NOT NULL DEFAULT 50.0,
        admin_notes TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        updated_at TEXT NOT NULL,
        confirmed_at TEXT NOT NULL DEFAULT '',
        packed_at TEXT NOT NULL DEFAULT '',
        on_the_way_at TEXT NOT NULL DEFAULT '',
        delivered_at TEXT NOT NULL DEFAULT '',
        cancelled_at TEXT NOT NULL DEFAULT ''
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
        "ALTER TABLE packages ADD COLUMN max_sale_limit INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE packages ADD COLUMN sold_quantity INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE packages ADD COLUMN show_in_banner INTEGER NOT NULL DEFAULT 0",
        "ALTER TABLE online_orders ADD COLUMN confirmed_at TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE online_orders ADD COLUMN packed_at TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE online_orders ADD COLUMN on_the_way_at TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE online_orders ADD COLUMN delivered_at TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE online_orders ADD COLUMN cancelled_at TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE product_units ADD COLUMN sell_price REAL NOT NULL DEFAULT 0",
        "ALTER TABLE product_units ADD COLUMN mrp REAL NOT NULL DEFAULT 0",
        "ALTER TABLE product_units ADD COLUMN batch_sl INTEGER NOT NULL DEFAULT 1",
        "ALTER TABLE customer_users ADD COLUMN registration_ip TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE customer_users ADD COLUMN registration_location TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE customer_users ADD COLUMN last_ip TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE customer_users ADD COLUMN last_location TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE customer_users ADD COLUMN last_seen_at TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE customer_users ADD COLUMN last_device TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE online_orders ADD COLUMN customer_ip TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE online_orders ADD COLUMN ip_location TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE pharmacy_orders ADD COLUMN customer_ip TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE pharmacy_orders ADD COLUMN ip_location TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE sales ADD COLUMN customer_ip TEXT NOT NULL DEFAULT ''",
        "ALTER TABLE sales ADD COLUMN ip_location TEXT NOT NULL DEFAULT ''",
    ]

    cur.executescript("""
    CREATE TABLE IF NOT EXISTS ip_geo_cache (
        ip TEXT PRIMARY KEY,
        location_label TEXT NOT NULL DEFAULT '',
        city TEXT NOT NULL DEFAULT '',
        region TEXT NOT NULL DEFAULT '',
        country TEXT NOT NULL DEFAULT '',
        isp TEXT NOT NULL DEFAULT '',
        updated_at TEXT NOT NULL DEFAULT ''
    );

    CREATE TABLE IF NOT EXISTS thermal_print_jobs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        job_uuid TEXT UNIQUE NOT NULL,
        job_type TEXT NOT NULL DEFAULT 'online_order',
        ref_id INTEGER DEFAULT 0,
        order_number TEXT NOT NULL DEFAULT '',
        printer_name TEXT NOT NULL DEFAULT '',
        paper_width TEXT NOT NULL DEFAULT '58mm',
        raw_escpos_b64 TEXT NOT NULL DEFAULT '',
        text_preview TEXT NOT NULL DEFAULT '',
        status TEXT NOT NULL DEFAULT 'pending',
        requested_by TEXT NOT NULL DEFAULT '',
        source_device TEXT NOT NULL DEFAULT '',
        created_at TEXT NOT NULL,
        printed_at TEXT NOT NULL DEFAULT '',
        error_msg TEXT NOT NULL DEFAULT ''
    );
    """)
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
        "thermal_printer_name": "",
        "thermal_paper_width": "58mm",
        "thermal_pc_auto_print": "1",
    }
    for key, value in default_settings.items():
        cur.execute("INSERT OR IGNORE INTO settings (key, value) VALUES (?, ?)", (key, value))

    # Pharmacy Indexes & Initial Medicines Seed
    try:
        # Ensure original & enhanced prescription url columns exist
        p_cols = [r[1] for r in cur.execute("PRAGMA table_info(pharmacy_orders)").fetchall()]
        if "prescription_original_url" not in p_cols:
            cur.execute("ALTER TABLE pharmacy_orders ADD COLUMN prescription_original_url TEXT DEFAULT ''")
        if "prescription_enhanced_url" not in p_cols:
            cur.execute("ALTER TABLE pharmacy_orders ADD COLUMN prescription_enhanced_url TEXT DEFAULT ''")

        cur.execute("CREATE INDEX IF NOT EXISTS idx_pharmacy_orders_phone ON pharmacy_orders(customer_phone)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_pharmacy_orders_num ON pharmacy_orders(order_number)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_pharmacy_medicines_name ON pharmacy_medicines(name)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_pharmacy_medicines_name_nocase ON pharmacy_medicines(name COLLATE NOCASE)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_pharmacy_medicines_generic_nocase ON pharmacy_medicines(generic_name COLLATE NOCASE)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_pharmacy_medicines_dosage ON pharmacy_medicines(dosage_form)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_pharmacy_medicines_sku ON pharmacy_medicines(sku)")
        cur.execute("CREATE INDEX IF NOT EXISTS idx_pharmacy_medicines_sku_nocase ON pharmacy_medicines(sku COLLATE NOCASE)")

        cur.execute("PRAGMA table_info(pharmacy_medicines)")
        med_col_names = [r["name"] for r in cur.fetchall()]
        if "sku" not in med_col_names:
            cur.execute("ALTER TABLE pharmacy_medicines ADD COLUMN sku TEXT DEFAULT ''")
            cur.execute("UPDATE pharmacy_medicines SET sku = printf('MED-%05d', id) WHERE sku IS NULL OR sku = ''")
        
        cur.execute("SELECT COUNT(*) AS c FROM pharmacy_medicines")
        if cur.fetchone()["c"] == 0:
            sample_medicines = [
                ('Napa 500mg', 'Paracetamol', 'ট্যাবলেট', '500mg', 'Beximco Pharmaceuticals', 1.20, 12.00, 10, 500, 0, '', 'জ্বর ও শরীরের ব্যথানাশক'),
                ('Napa Extra', 'Paracetamol + Caffeine', 'ট্যাবলেট', '500mg+65mg', 'Beximco Pharmaceuticals', 2.50, 30.00, 12, 500, 0, '', 'তীব্র মাথা ব্যথা ও জ্বরে দ্রুত কার্যকর'),
                ('Ace Plus', 'Paracetamol + Caffeine', 'ট্যাবলেট', '500mg+65mg', 'Square Pharmaceuticals', 2.50, 30.00, 12, 500, 0, '', 'মাথা ব্যথা ও ব্যথানাশক'),
                ('Fast 500mg', 'Paracetamol', 'ট্যাবলেট', '500mg', 'Acme Laboratories', 1.20, 12.00, 10, 400, 0, '', 'জ্বর ও ব্যথানাশক'),
                ('Fexo 120mg', 'Fexofenadine Hydrochloride', 'ট্যাবলেট', '120mg', 'Square Pharmaceuticals', 9.00, 90.00, 10, 300, 0, '', 'অ্যালার্জি, হাঁচি ও সর্দি প্রতিরোধক'),
                ('Fexo 180mg', 'Fexofenadine Hydrochloride', 'ট্যাবলেট', '180mg', 'Square Pharmaceuticals', 12.00, 120.00, 10, 200, 0, '', 'তীব্র অ্যালার্জি ও চুলকানির জন্য'),
                ('Alatrol 10mg', 'Cetirizine Hydrochloride', 'ট্যাবলেট', '10mg', 'Square Pharmaceuticals', 3.50, 35.00, 10, 400, 0, '', 'সর্দি, অ্যালার্জি ও চুলকানি নিরাময়ে'),
                ('Monas 10mg', 'Montelukast Sodium', 'ট্যাবলেট', '10mg', 'Acme Laboratories', 17.50, 175.00, 10, 300, 1, '', 'হাঁপানি ও দীর্ঘস্থায়ী শ্বাসকষ্ট নিয়ন্ত্রণ'),
                ('Montene 10mg', 'Montelukast Sodium', 'ট্যাবলেট', '10mg', 'Square Pharmaceuticals', 17.50, 175.00, 10, 300, 1, '', 'অ্যাজমা ও শ্বাসকষ্ট উপশমে'),
                ('Pantonix 20mg', 'Pantoprazole Sodium', 'ট্যাবলেট', '20mg', 'Incepta Pharmaceuticals', 7.00, 70.00, 10, 500, 0, '', 'গ্যাস্ট্রিক আলসার ও বুক জ্বালাপোড়া রোধে'),
                ('Finix 20mg', 'Rabeprazole Sodium', 'ট্যাবলেট', '20mg', 'Opsonin Pharma', 7.00, 70.00, 10, 400, 0, '', 'অ্যাসিডিটি ও পেটের গ্যাস নিরাময়ে'),
                ('Ciprocin 500mg', 'Ciprofloxacin', 'ট্যাবলেট', '500mg', 'Square Pharmaceuticals', 15.00, 150.00, 10, 200, 1, '', 'ব্যাকটেরিয়াল ইনফেকশন ও অ্যান্টিবায়োটিক'),
                ('Azithrocin 500mg', 'Azithromycin', 'ট্যাবলেট', '500mg', 'Square Pharmaceuticals', 35.00, 105.00, 3, 150, 1, '', 'শ্বাসনালী ও গলার ইনফেকশনে অ্যান্টিবায়োটিক'),
                ('Flexi 100mg', 'Aceclofenac', 'ট্যাবলেট', '100mg', 'Square Pharmaceuticals', 5.00, 50.00, 10, 300, 0, '', 'হাড়ের জোড়ায় তীব্র ব্যথা ও প্রদাহনাশক'),
                ('Clofenac 50mg', 'Diclofenac Sodium', 'ট্যাবলেট', '50mg', 'Square Pharmaceuticals', 3.00, 30.00, 10, 250, 0, '', 'ব্যথানাশক ও ফোলা কমানোর ওষুধ'),
                ('Entacyd Chewable', 'Antacid', 'ট্যাবলেট', 'Chewable', 'Square Pharmaceuticals', 2.00, 20.00, 10, 500, 0, '', 'পেটের তাৎক্ষণিক এসিডিটি নিরাময়ে'),
                ('Filwel Gold', 'Multivitamin & Multimineral', 'ট্যাবলেট', 'A to Z', 'Square Pharmaceuticals', 6.00, 60.00, 10, 300, 0, '', 'দৈনিক শক্তি ও রোগ প্রতিরোধ ক্ষমতা বৃদ্ধি'),
                ('Calbo-D', 'Calcium + Vitamin D3', 'ট্যাবলেট', '500mg+200IU', 'Square Pharmaceuticals', 7.00, 70.00, 10, 400, 0, '', 'হাড় ও দাঁত মজবুত করার ক্যালসিয়াম'),
                
                ('Seclo 20mg', 'Omeprazole', 'ক্যাপসুল', '20mg', 'Square Pharmaceuticals', 6.00, 60.00, 10, 600, 0, '', 'গ্যাস্ট্রিক ও এসিডিটি নিরাময়ে অত্যন্ত কার্যকরী'),
                ('Seclo 40mg', 'Omeprazole', 'ক্যাপসুল', '40mg', 'Square Pharmaceuticals', 10.00, 100.00, 10, 300, 0, '', 'তীব্র গ্যাস্ট্রিক আলসার উপশমে'),
                ('Maxpro 20mg', 'Esomeprazole Magnesium', 'ক্যাপসুল', '20mg', 'Square Pharmaceuticals', 7.00, 70.00, 10, 500, 0, '', 'হাইপার-অ্যাসিডিটি ও জিইআরডি নিরাময়'),
                ('Maxpro 40mg', 'Esomeprazole Magnesium', 'ক্যাপসুল', '40mg', 'Square Pharmaceuticals', 11.00, 110.00, 10, 300, 0, '', 'তীব্র গ্যাস্ট্রিক প্রতিরোধক'),
                ('Losectil 20mg', 'Omeprazole', 'ক্যাপসুল', '20mg', 'SK+F Pharmaceuticals', 6.00, 60.00, 10, 400, 0, '', 'পেটের জ্বালাপোড়া ও আলসার প্রতিরোধে'),
                ('Sergel 20mg', 'Esomeprazole', 'ক্যাপসুল', '20mg', 'Healthcare Pharmaceuticals', 7.00, 70.00, 10, 400, 0, '', 'গ্যাস্ট্রিক ও বুক জ্বালাপোড়া নিরাময়'),
                ('Cef-3 200mg', 'Cefixime Trihydrate', 'ক্যাপসুল', '200mg', 'Square Pharmaceuticals', 45.00, 270.00, 6, 150, 1, '', '৩য় প্রজন্মের শক্তিশালী অ্যান্টিবায়োটিক'),
                ('D-Rise 20000 IU', 'Cholecalciferol (Vitamin D3)', 'ক্যাপসুল', '20000 IU', 'Square Pharmaceuticals', 40.00, 160.00, 4, 200, 0, '', 'ভিটামিন ডি ঘাটতি পূরণকারী সাপ্তাহিক ডোজ'),
                ('Indever 10mg', 'Propranolol Hydrochloride', 'ক্যাপসুল', '10mg', 'Beximco Pharmaceuticals', 2.00, 20.00, 10, 200, 1, '', 'উচ্চ রক্তচাপ ও বুক ধড়ফড়ানি নিয়ন্ত্রণ'),
                ('Doxy-A 100mg', 'Doxycycline', 'ক্যাপসুল', '100mg', 'Square Pharmaceuticals', 3.50, 35.00, 10, 150, 1, '', 'ব্রণ ও ত্বকের ব্যাকটেরিয়াল ইনফেকশনে'),

                ('Napa Syrup 60ml', 'Paracetamol', 'সিরাপ', '120mg/5ml, 60ml', 'Beximco Pharmaceuticals', 35.00, 35.00, 1, 100, 0, '', 'বাচ্চাদের জ্বর ও শরীর ব্যথায় মিষ্টি সিরাপ'),
                ('Tofen Syrup 100ml', 'Ketotifen Fumarate', 'সিরাপ', '1mg/5ml, 100ml', 'Beximco Pharmaceuticals', 70.00, 70.00, 1, 80, 0, '', 'অ্যালার্জি, হাঁচি ও শিশুদের শ্বাসকষ্টে কার্যকর'),
                ('Adrylex Syrup 100ml', 'Diphenhydramine + Ammonium Cl', 'সিরাপ', '100ml Bottle', 'Square Pharmaceuticals', 65.00, 65.00, 1, 90, 0, '', 'শুকনো কাশি ও কফের উপশমে'),
                ('Brofex Syrup 100ml', 'Bromhexine Hydrochloride', 'সিরাপ', '100ml Bottle', 'Square Pharmaceuticals', 60.00, 60.00, 1, 90, 0, '', 'বুকের জমাট কফ সহজে বের করতে'),
                ('Entacyd Plus Suspension 200ml', 'Antacid + Simethicone', 'সাসপেনশন', '200ml Bottle', 'Square Pharmaceuticals', 95.00, 95.00, 1, 120, 0, '', 'বুক জ্বালা ও গ্যাস্ট্রিকের দ্রুত উপশমকারী সিরাপ'),
                ('Gaviscon Liquid 200ml', 'Sodium Alginate + Antacid', 'সাসপেনশন', '200ml Bottle', 'Reckitt Benckiser', 280.00, 280.00, 1, 50, 0, '', 'রিফ্লাক্স ও বুক জ্বালাপোড়ায় সুরক্ষার স্তর তৈরি করে'),
                ('Avolac Oral Solution 100ml', 'Lactulose', 'সিরাপ', '100ml Bottle', 'Square Pharmaceuticals', 150.00, 150.00, 1, 70, 0, '', 'কোষ্ঠকাঠিন্য দূর করার নিরাপদ সিরাপ'),
                ('Basok Syrup 100ml', 'Adhatoda Vasica (বাসক পাতা)', 'সিরাপ', '100ml Bottle', 'Square Pharmaceuticals', 80.00, 80.00, 1, 100, 0, '', 'প্রাকৃতিক হার্বাল কফ সিরাপ'),
                ('Cef-3 Dry Syrup 50ml', 'Cefixime', 'সাসপেনশন', '50ml Bottle', 'Square Pharmaceuticals', 160.00, 160.00, 1, 60, 1, '', 'বাচ্চাদের অ্যান্টিবায়োটিক সাসপেনশন'),
                ('Filwel Kids Syrup 100ml', 'Multivitamin & Lysine', 'সিরাপ', '100ml Bottle', 'Square Pharmaceuticals', 90.00, 90.00, 1, 80, 0, '', 'বাচ্চাদের ক্ষুধা ও পুষ্টিবর্ধক ভিটামিন সিরাপ'),

                ('Ceftron 1g IV/IM Injection', 'Ceftriaxone Sodium', 'ইনজেকশন', '1g Vial', 'Square Pharmaceuticals', 180.00, 180.00, 1, 50, 1, '', 'হাসপাতাল গ্রেড ব্রড-স্পেকট্রাম অ্যান্টিবায়োটিক ইনজেকশন'),
                ('Pantonix 40mg IV Injection', 'Pantoprazole Sodium', 'ইনজেকশন', '40mg Vial', 'Incepta Pharmaceuticals', 90.00, 90.00, 1, 60, 1, '', 'তীব্র গ্যাস্ট্রিক ও রক্তপাত রোধে আইভি ইনজেকশন'),
                ('Seclo 40mg IV Injection', 'Omeprazole Sodium', 'ইনজেকশন', '40mg Vial', 'Square Pharmaceuticals', 90.00, 90.00, 1, 60, 1, '', 'আইভি গ্যাস্ট্রিক ইনজেকশন'),
                ('Torax 30mg/ml Injection', 'Ketorolac Tromethamine', 'ইনজেকশন', '30mg Ampoule', 'Square Pharmaceuticals', 60.00, 60.00, 1, 50, 1, '', 'অস্ত্রোপচার পরবর্তী বা তীব্র ব্যথানাশক ইনজেকশন'),
                ('Tramadol 100mg/2ml Injection', 'Tramadol Hydrochloride', 'ইনজেকশন', '100mg Ampoule', 'Square Pharmaceuticals', 45.00, 45.00, 1, 40, 1, '', 'তীব্র ব্যথানাশক ওষুধ'),
                ('Insulin Mixtard 30 Penfill 100IU/ml', 'Biphasic Isophane Insulin', 'ইনজেকশন', '3ml Cartridge', 'Novo Nordisk', 480.00, 480.00, 1, 30, 1, '', 'ডায়াবেটিস রোগীদের ইনসুলিন'),
                ('Diclofenac 75mg/3ml Injection', 'Diclofenac Sodium', 'ইনজেকশন', '75mg Ampoule', 'Square Pharmaceuticals', 25.00, 25.00, 1, 80, 1, '', 'জরুরী ব্যথানাশক ইনজেকশন'),

                ('Moxaclav Eye Drops 5ml', 'Moxifloxacin', 'ড্রপ', '5ml Bottle', 'Square Pharmaceuticals', 140.00, 140.00, 1, 60, 1, '', 'চোখের ইনফেকশন ও প্রদাহের ড্রপ'),
                ('Dexaquick Eye/Ear Drops 5ml', 'Dexamethasone', 'ড্রপ', '5ml Bottle', 'Square Pharmaceuticals', 65.00, 65.00, 1, 70, 1, '', 'চোখ ও কানের ড্রপ'),
                ('Refresh Tears Eye Drops 10ml', 'Carboxymethylcellulose', 'ড্রপ', '10ml Bottle', 'Allergan', 220.00, 220.00, 1, 40, 0, '', 'চোখের শুষ্কতা ও জ্বালাপোড়া দূর করতে'),
                ('Otobiotic Ear Drops 5ml', 'Neomycin + Polymyxin + Hydrocortisone', 'ড্রপ', '5ml Bottle', 'Square Pharmaceuticals', 85.00, 85.00, 1, 50, 1, '', 'কানের ইনফেকশন ও ব্যথানাশক ড্রপ'),
                ('Antazol 0.1% Nasal Drops 10ml', 'Xylometazoline', 'ড্রপ', '10ml Bottle', 'Square Pharmaceuticals', 25.00, 25.00, 1, 100, 0, '', 'বন্ধ নাক দ্রুত খোলার ড্রপ'),

                ('Betnovate-N Cream 15g', 'Betamethasone + Neomycin', 'মলম/ক্রিম', '15g Tube', 'GSK Bangladesh', 60.00, 60.00, 1, 100, 1, '', 'চর্মরোগ, একজিমা ও চুলকানির ক্রিম'),
                ('Burnsil Ointment 25g', 'Silver Sulfadiazine', 'মলম/ক্রিম', '25g Tube', 'Square Pharmaceuticals', 65.00, 65.00, 1, 80, 0, '', 'আগুনে পোড়া ক্ষত ও ফোস্কার ওষুধ'),
                ('Daktarin Oral Gel 20g', 'Miconazole', 'মলম/ক্রিম', '20g Tube', 'Janssen', 110.00, 110.00, 1, 50, 0, '', 'মুখের ঘা ও জিহ্বার ফাঙ্গাল ইনফেকশনের জেল'),
                ('Cloben-G Cream 15g', 'Clotrimazole + Betamethasone + Gentamicin', 'মলম/ক্রিম', '15g Tube', 'Square Pharmaceuticals', 75.00, 75.00, 1, 90, 0, '', 'দাদ ও চর্মরোগের মিশ্র ক্রিম'),
                ('Neosten Cream 10g', 'Clotrimazole', 'মলম/ক্রিম', '10g Tube', 'Square Pharmaceuticals', 45.00, 45.00, 1, 80, 0, '', 'দাদ ও ফাঙ্গাল ইনফেকশনের মলম'),
                ('Viodin 10% Ointment 20g', 'Povidone Iodine', 'মলম/ক্রিম', '20g Tube', 'Square Pharmaceuticals', 50.00, 50.00, 1, 100, 0, '', 'ক্ষত জীবাণুমুক্ত করার অ্যান্টিসেপটিক মলম'),

                ('গজ পট্টি (Roller Gauze 2 inch)', 'Medical Gauze', 'ব্যান্ডেজ/ফার্স্ট এইড', '2 inch x 5 yard', 'Local Sterile Surgical', 20.00, 20.00, 1, 300, 0, '', 'কাটা-ছেঁড়ায় ক্ষত ড্রেসিংয়ের পাতলা গজ পট্টি'),
                ('গজ পট্টি বড় (Roller Gauze 4 inch)', 'Medical Gauze', 'ব্যান্ডেজ/ফার্স্ট এইড', '4 inch x 5 yard', 'Local Sterile Surgical', 35.00, 35.00, 1, 200, 0, '', 'বড় ক্ষত ব্যান্ডেজের চওড়া গজ পট্টি'),
                ('স্টেরাইল গজ প্যাড (Sterile Gauze Pad)', 'Cotton Gauze Pad', 'ব্যান্ডেজ/ফার্স্ট এইড', '3x3 inch (5 Pcs Pack)', 'MediPack Sterile', 40.00, 40.00, 1, 150, 0, '', 'জীবাণুমুক্ত ড্রেসিং গজ প্যাড ৫ পিস প্যাক'),
                ('ইলাস্টিক ক্রেপ ব্যান্ডেজ (Crepe Bandage 7.5cm)', 'Elastic Cotton', 'ব্যান্ডেজ/ফার্স্ট এইড', '7.5cm x 4.5m', 'OrthoBand', 90.00, 90.00, 1, 120, 0, '', 'পা মচকালে বা রগে টান লাগলে ব্যথানাশক ইলাস্টিক ব্যান্ডেজ'),
                ('ইলাস্টিক ক্রেপ ব্যান্ডেজ বড় (Crepe Bandage 10cm)', 'Elastic Cotton', 'ব্যান্ডেজ/ফার্স্ট এইড', '10cm x 4.5m', 'OrthoBand', 120.00, 120.00, 1, 80, 0, '', 'হাড়ের জোড়া ও পেশির সুরক্ষায় বড় ক্রেপ ব্যান্ডেজ'),
                ('হ্যান্ডিপ্লাস্ট ব্যান্ডএইড (Handiplast Band-Aid)', 'Adhesive Strip', 'ব্যান্ডেজ/ফার্স্ট এইড', '১০ পিস বক্স', 'Hansaplast / ACI', 30.00, 30.00, 1, 400, 0, '', 'ছোটখাটো কাটা-ছেঁড়ার ওয়াটারপ্রুফ স্টিকার ব্যান্ডএইড'),
                ('স্যাভলন অ্যান্টিসেপটিক লিকুইড ১১২ মি.লি.', 'Chlorhexidine + Cetrimide', 'ব্যান্ডেজ/ফার্স্ট এইড', '112ml Bottle', 'ACI Limited', 55.00, 55.00, 1, 150, 0, '', 'ক্ষত জীবাণুমুক্ত করার অ্যান্টিসেপটিক তরল'),
                ('স্যাভলন অ্যান্টিসেপটিক লিকুইড ৫৬৫ মি.লি.', 'Chlorhexidine + Cetrimide', 'ব্যান্ডেজ/ফার্স্ট এইড', '565ml Bottle', 'ACI Limited', 190.00, 190.00, 1, 80, 0, '', 'পারিবারিক ব্যবহারের জন্য বড় স্যাভলন লিকুইড'),
                ('হাইড্রোজেন পারক্সাইড ১০০ মি.লি.', 'Hydrogen Peroxide 6%', 'ব্যান্ডেজ/ফার্স্ট এইড', '100ml Bottle', 'Beximco / Local Chemical', 35.00, 35.00, 1, 100, 0, '', 'ক্ষতের রক্ত পরিষ্কার ও পুঁজ ধোয়ার স্যালাইন দ্রবণ'),
                ('মাইক্রোপোর সার্জিক্যাল পেপার টেপ', 'Surgical Paper Tape', 'ব্যান্ডেজ/ফার্স্ট এইড', '1 inch x 10 yard', '3M Micropore', 65.00, 65.00, 1, 150, 0, '', 'ব্যান্ডেজ লাগানোর স্কিন-ফ্রেন্ডলি সার্জিক্যাল টেপ'),
                ('মেডিকেল তুলার রোল (Absorbent Cotton 50g)', 'Pure Cotton', 'ব্যান্ডেজ/ফার্স্ট এইড', '50g Roll', 'Surgical Cotton BD', 30.00, 30.00, 1, 200, 0, '', 'জীবাণুমুক্ত বিশুদ্ধ শোষণকারী তুলা'),
                ('ওরাল স্যালাইন ওআরএস (ORSaline-N)', 'Oral Rehydration Salts', 'ব্যান্ডেজ/ফার্স্ট এইড', '৫ প্যাকেট কম্বো', 'SMC Enterprise', 35.00, 35.00, 1, 500, 0, '', 'ডায়রিয়া ও ডিহাইড্রেশনের ওআরএস স্যালাইন')
            ]
            for med in sample_medicines:
                cur.execute('''
                    INSERT INTO pharmacy_medicines (
                        name, generic_name, dosage_form, strength, manufacturer,
                        unit_price, strip_price, strip_size, stock_qty, is_prescription_required,
                        image_url, description, is_active, created_at, updated_at
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)
                ''', (
                    med[0], med[1], med[2], med[3], med[4],
                    med[5], med[6], med[7], med[8], med[9],
                    med[10], med[11], now_iso, now_iso
                ))
    except Exception as _p_err:
        print(f"[database.py] Pharmacy seeding error: {_p_err}")

    conn.commit()
    conn.close()


_GITHUB_RELEASE_CACHE = None
_GITHUB_CACHE_TIME = 0
_GITHUB_CACHE_TTL = 300  # 5 minutes in-memory cache


def _parse_semver(v):
    nums = re.findall(r'\d+', str(v or ""))
    return tuple(int(x) for x in nums) if nums else (0,)


def _fetch_github_latest_release():
    """Fetch the latest official GitHub release for doineek/supershop (cached for 5 min)."""
    global _GITHUB_RELEASE_CACHE, _GITHUB_CACHE_TIME
    now = time.time()
    if _GITHUB_RELEASE_CACHE is not None and (now - _GITHUB_CACHE_TIME) < _GITHUB_CACHE_TTL:
        return _GITHUB_RELEASE_CACHE

    try:
        import urllib.request
        req = urllib.request.Request(
            "https://api.github.com/repos/doineek/supershop/releases/latest",
            headers={"User-Agent": "DOINEEK-SuperShop-Web/1.0"}
        )
        with urllib.request.urlopen(req, timeout=3) as resp:
            if resp.status == 200:
                data = json.loads(resp.read().decode("utf-8"))
                tag = (data.get("tag_name") or "").strip().lstrip("v")
                assets = [a.get("name") for a in data.get("assets", []) if a.get("name")]
                _GITHUB_RELEASE_CACHE = {
                    "tag": tag,
                    "assets": assets,
                }
                _GITHUB_CACHE_TIME = now
                return _GITHUB_RELEASE_CACHE
    except Exception:
        pass

    return _GITHUB_RELEASE_CACHE


def get_app_version_info():
    """
    Dynamically read the latest app version and build number from:
    1. GitHub Releases latest tag (auto-updates whenever a new APK release is published)
    2. supershop_flutter_app/pubspec.yaml
    3. static/flutter_web/version.json
    Automatically stays in sync whenever the app is built or updated.
    """
    version = "1.0.15"
    build_number = "16"
    base_dir = os.path.dirname(os.path.abspath(__file__))
    found_in_pubspec = False

    # 1. Read pubspec.yaml if present (highest priority locally)
    pubspec_path = os.path.join(base_dir, "supershop_flutter_app", "pubspec.yaml")
    if os.path.exists(pubspec_path):
        try:
            with open(pubspec_path, "r", encoding="utf-8") as f:
                for line in f:
                    line_clean = line.strip()
                    if line_clean.startswith("version:"):
                        val = line_clean.split(":", 1)[1].strip().strip('"').strip("'")
                        if "+" in val:
                            parts = val.split("+", 1)
                            version = parts[0].strip()
                            build_number = parts[1].strip()
                        else:
                            version = val
                            build_number = ""
                        found_in_pubspec = True
                        break
        except Exception:
            pass

    # 2. Check static/flutter_web/version.json only if not found in pubspec.yaml
    if not found_in_pubspec:
        v_json_path = os.path.join(base_dir, "static", "flutter_web", "version.json")
        if os.path.exists(v_json_path):
            try:
                with open(v_json_path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    if data.get("version"):
                        version = str(data["version"]).strip()
                    if data.get("build_number") is not None:
                        build_number = str(data["build_number"]).strip()
            except Exception:
                pass

    # 3. Check GitHub Releases for newer release tags (auto-updates production on Render)
    gh_release = _fetch_github_latest_release()
    if gh_release and gh_release.get("tag"):
        gh_ver = gh_release["tag"]
        if _parse_semver(gh_ver) >= _parse_semver(version):
            version = gh_ver

    display = f"v{version} (Build {build_number})" if build_number else f"v{version}"
    full_title = f"Version {version} (Build {build_number}) • Official Release" if build_number else f"Version {version} • Official Release"
    short_version = f"v{version}"
    apk_filename = f"doineek_{short_version}.apk"

    return {
        "version": version,
        "build_number": build_number,
        "display": display,
        "full_title": full_title,
        "short_version": short_version,
        "apk_filename": apk_filename,
    }


DEFAULT_SETTINGS = {
    "shop_name": "DOINEEK",
    "shop_address": "House 12, Road 5, Dhanmondi, Dhaka-1205",
    "shop_phone": "+880-1XXX-XXXXXX",
    "vat_reg_no": "0",
    "delivery_charge": "60",
    "product_image_bg_color": "#FFFFFF",
    "rider_delivery_fee": "50",
    "app_version": "v1.0.18 (Build 19)",
    "app_version_short": "v1.0.18",
    "app_version_full": "Version 1.0.18 (Build 19) • Official Release",
    "apk_download_url": "https://github.com/doineek/supershop/releases/download/v1.0.18/doineek_v1.0.18.apk",
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

    # Automatically sync latest app version info from GitHub Releases / pubspec.yaml
    v_info = get_app_version_info()
    result["app_version"] = v_info["display"]
    result["app_version_short"] = v_info["short_version"]
    result["app_version_full"] = v_info["full_title"]
    result["app_version_num"] = v_info["version"]
    result["app_build_number"] = v_info["build_number"]
    result["apk_filename"] = v_info["apk_filename"]
    result["apk_download_url"] = f"https://github.com/doineek/supershop/releases/download/{v_info['short_version']}/{v_info['apk_filename']}"

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


def create_product_units(conn, product_id, quantity, sell_price=0.0, mrp=0.0, batch_sl=1):
    """Generates unique incrementing product serials (a_code) for each physical item in bulk.
    sell_price, mrp, and batch_sl are stored per unit so that each batch's price tag and SL
    are preserved even after a restock with different pricing."""
    if quantity <= 0:
        return []

    cur = conn.cursor()
    row = cur.execute(
        "SELECT COALESCE(MAX(sl_number), 0) AS m FROM product_units WHERE product_id = ?",
        (product_id,)
    ).fetchone()
    next_sl = (row["m"] if row else 0) + 1

    max_sn_row = cur.execute(
        "SELECT MAX(CAST(SUBSTR(a_code, 4) AS INTEGER)) AS m FROM product_units WHERE a_code LIKE 'SN-%'"
    ).fetchone()
    start_sn = ((max_sn_row["m"] or 0) if max_sn_row else 0) + 1

    max_id_row = cur.execute("SELECT COALESCE(MAX(id), 0) AS m FROM product_units").fetchone()
    start_id = ((max_id_row["m"] or 0) if max_id_row else 0) + 1
    now = datetime.now().isoformat()

    bulk_rows = []
    created_ids = []

    for i in range(quantity):
        curr_id = start_id + i
        sl_num = next_sl + i
        curr_sn = start_sn + i
        a_code = f"SN-{curr_sn:06d}"
        bulk_rows.append((curr_id, product_id, a_code, sl_num, 'in_stock', now, sell_price, mrp, batch_sl))
        created_ids.append(curr_id)

    cur.executemany(
        "INSERT INTO product_units (id, product_id, a_code, sl_number, status, created_at, sell_price, mrp, batch_sl) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
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


def clean_notif_title(title):
    """Strips leading emojis and special symbols so titles are clean across all clients."""
    if not title:
        return "Notification"
    return re.sub(r'^[^\w\d\s\u0980-\u09FF]+\s*', '', str(title)).strip() or str(title)


def add_customer_notification(customer_phone, title, message, notif_type="general", reference_id="", conn=None):
    """Inserts a new notification for a customer (or broadcast if customer_phone is empty)."""
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True
    try:
        now_str = datetime.now().isoformat()
        cleaned_title = clean_notif_title(title)
        cur = conn.execute(
            """INSERT INTO customer_notifications (customer_phone, title, message, type, reference_id, is_read, created_at)
               VALUES (?, ?, ?, ?, ?, 0, ?)""",
            (customer_phone or "", cleaned_title, message, notif_type, str(reference_id or ""), now_str)
        )
        conn.commit()
        return cur.lastrowid
    finally:
        if close_conn:
            conn.close()


def get_customer_notifications(customer_phone="", limit=60, conn=None):
    """
    Fetches notifications for a customer (their personal notifications + broadcast notifications).
    Calculates whether the broadcast notifications have been read by checking customer_notification_reads.
    Respects customer_notification_clears to avoid returning cleared notifications.
    """
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True
    try:
        phone = (customer_phone or "").strip()
        cleared_at = ""
        if phone:
            try:
                clr_row = conn.execute("SELECT cleared_at FROM customer_notification_clears WHERE customer_phone = ?", (phone,)).fetchone()
                if clr_row and clr_row["cleared_at"]:
                    cleared_at = clr_row["cleared_at"]
            except Exception:
                pass

        if phone:
            if cleared_at:
                rows = conn.execute("""
                    SELECT n.*,
                           CASE
                               WHEN n.customer_phone = ? THEN n.is_read
                               ELSE CASE WHEN r.notification_id IS NOT NULL THEN 1 ELSE 0 END
                           END AS effective_is_read
                    FROM customer_notifications n
                    LEFT JOIN customer_notification_reads r
                           ON n.id = r.notification_id AND r.customer_phone = ?
                    WHERE (n.customer_phone = ? OR n.customer_phone = '' OR n.customer_phone IS NULL)
                      AND n.created_at > ?
                    ORDER BY n.id DESC
                    LIMIT ?
                """, (phone, phone, phone, cleared_at, limit)).fetchall()
            else:
                rows = conn.execute("""
                    SELECT n.*,
                           CASE
                               WHEN n.customer_phone = ? THEN n.is_read
                               ELSE CASE WHEN r.notification_id IS NOT NULL THEN 1 ELSE 0 END
                           END AS effective_is_read
                    FROM customer_notifications n
                    LEFT JOIN customer_notification_reads r
                           ON n.id = r.notification_id AND r.customer_phone = ?
                    WHERE n.customer_phone = ? OR n.customer_phone = '' OR n.customer_phone IS NULL
                    ORDER BY n.id DESC
                    LIMIT ?
                """, (phone, phone, phone, limit)).fetchall()
        else:
            rows = conn.execute("""
                SELECT n.*, n.is_read AS effective_is_read
                FROM customer_notifications n
                WHERE n.customer_phone = '' OR n.customer_phone IS NULL
                ORDER BY n.id DESC
                LIMIT ?
            """, (limit,)).fetchall()

        results = []
        for r in rows:
            results.append({
                "id": r["id"],
                "customer_phone": r["customer_phone"],
                "title": clean_notif_title(r["title"]),
                "message": r["message"],
                "type": r["type"],
                "reference_id": r["reference_id"],
                "is_read": int(r["effective_is_read"]),
                "created_at": r["created_at"]
            })
        return results
    finally:
        if close_conn:
            conn.close()


def mark_notification_as_read(notif_id, customer_phone="", conn=None):
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True
    try:
        phone = (customer_phone or "").strip()
        now_str = datetime.now().isoformat()
        row = conn.execute("SELECT * FROM customer_notifications WHERE id = ?", (notif_id,)).fetchone()
        if row:
            if row["customer_phone"] and row["customer_phone"] == phone:
                conn.execute("UPDATE customer_notifications SET is_read = 1 WHERE id = ?", (notif_id,))
            elif not row["customer_phone"] and phone:
                conn.execute("INSERT OR IGNORE INTO customer_notification_reads (notification_id, customer_phone, read_at) VALUES (?, ?, ?)", (notif_id, phone, now_str))
            else:
                conn.execute("UPDATE customer_notifications SET is_read = 1 WHERE id = ?", (notif_id,))
        conn.commit()
        return True
    finally:
        if close_conn:
            conn.close()


def mark_all_notifications_as_read(customer_phone="", conn=None):
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True
    try:
        phone = (customer_phone or "").strip()
        now_str = datetime.now().isoformat()
        if phone:
            conn.execute("UPDATE customer_notifications SET is_read = 1 WHERE customer_phone = ?", (phone,))
            broadcast_rows = conn.execute("SELECT id FROM customer_notifications WHERE customer_phone = '' OR customer_phone IS NULL").fetchall()
            for b in broadcast_rows:
                conn.execute("INSERT OR IGNORE INTO customer_notification_reads (notification_id, customer_phone, read_at) VALUES (?, ?, ?)", (b["id"], phone, now_str))
        else:
            conn.execute("UPDATE customer_notifications SET is_read = 1 WHERE customer_phone = '' OR customer_phone IS NULL")
        conn.commit()
        return True
    finally:
        if close_conn:
            conn.close()


def clear_customer_notifications(customer_phone="", conn=None):
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True
    try:
        phone = (customer_phone or "").strip()
        now_str = datetime.now().isoformat()
        if phone:
            conn.execute("DELETE FROM customer_notifications WHERE customer_phone = ?", (phone,))
            conn.execute("""
                INSERT INTO customer_notification_clears (customer_phone, cleared_at)
                VALUES (?, ?)
                ON CONFLICT(customer_phone) DO UPDATE SET cleared_at = excluded.cleared_at
            """, (phone, now_str))
            broadcast_rows = conn.execute("SELECT id FROM customer_notifications WHERE customer_phone = '' OR customer_phone IS NULL").fetchall()
            for b in broadcast_rows:
                conn.execute("INSERT OR IGNORE INTO customer_notification_reads (notification_id, customer_phone, read_at) VALUES (?, ?, ?)", (b["id"], phone, now_str))
        conn.commit()
        return True
    finally:
        if close_conn:
            conn.close()


def get_portal_notifications(limit=60, conn=None):
    """
    Fetches all notifications (all online orders, offers, daily suggestions) for the admin/staff portal.
    """
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True
    try:
        rows = conn.execute("""
            SELECT n.*
            FROM customer_notifications n
            ORDER BY n.id DESC
            LIMIT ?
        """, (limit,)).fetchall()

        results = []
        for r in rows:
            results.append({
                "id": r["id"],
                "customer_phone": r["customer_phone"],
                "title": clean_notif_title(r["title"]),
                "message": r["message"],
                "type": r["type"],
                "reference_id": r["reference_id"],
                "is_read": int(r["is_read"] or 0),
                "created_at": r["created_at"]
            })
        return results
    finally:
        if close_conn:
            conn.close()


def mark_all_portal_notifications_as_read(conn=None):
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True
    try:
        conn.execute("UPDATE customer_notifications SET is_read = 1")
        conn.commit()
        return True
    finally:
        if close_conn:
            conn.close()


def clear_portal_notifications(conn=None):
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True
    try:
        conn.execute("DELETE FROM customer_notifications")
        conn.commit()
        return True
    finally:
        if close_conn:
            conn.close()

