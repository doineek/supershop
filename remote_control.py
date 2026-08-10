"""
remote_control.py
------------------
Real-time Firebase bridge for DOINEEK Supershop POS & E-Commerce Web App.

Features:
  1. Real-time Backup & Cloud Push (Website -> Cloud Firestore)
  2. Two-Way Product & Setting Sync (Firebase Console -> Local SQLite DB)
  3. Live Remote Control (Maintenance Mode, Announcements, Force Logout)
"""

import os
import threading
import time
from datetime import datetime

import firebase_admin
from firebase_admin import credentials, firestore

from database import get_connection

CRED_FILE = "firebase_credentials.json"

STATE = {
    "maintenance_mode": False,
    "maintenance_message": "Shop is temporarily closed. Please try again later.",
    "announcement": "",
    "force_logout": False,
}

_db = None
_state_lock = threading.Lock()


def _init_firebase():
    global _db
    if _db is not None:
        return _db

    with _state_lock:
        if _db is not None:
            return _db

        cred = None
        if os.path.exists(CRED_FILE):
            try:
                cred = credentials.Certificate(CRED_FILE)
            except Exception as e:
                print(f"[remote_control] Failed to load {CRED_FILE}: {e}")

        if not cred:
            env_json = os.environ.get("FIREBASE_CREDENTIALS_JSON") or os.environ.get("FIREBASE_CREDENTIALS")
            if env_json:
                try:
                    import json
                    cred_dict = json.loads(env_json)
                    cred = credentials.Certificate(cred_dict)
                except Exception as e:
                    print(f"[remote_control] Failed to parse FIREBASE_CREDENTIALS env var: {e}")

        if not cred:
            print(f"[remote_control] [ALERT] Neither {CRED_FILE} nor FIREBASE_CREDENTIALS env var found.")
            return None

        try:
            if not firebase_admin._apps:
                firebase_admin.initialize_app(cred)
            _db = firestore.client()
            return _db
        except Exception as e:
            if firebase_admin._apps:
                try:
                    _db = firestore.client()
                    return _db
                except Exception:
                    pass
            print(f"[remote_control] [ERROR] Firebase initialization error: {e}")
            return None


# ---------------------------------------------------------------------------
# 1) REAL-TIME BACKUP (Local Database -> Firestore)
# ---------------------------------------------------------------------------

def _worker_push_sale(sale_id):
    try:
        db = _init_firebase()
        if not db:
            return
        conn = get_connection()
        sale = conn.execute("SELECT * FROM sales WHERE id = ?", (sale_id,)).fetchone()
        items = conn.execute("SELECT * FROM sale_items WHERE sale_id = ?", (sale_id,)).fetchall()
        if sale:
            sale_dict = dict(sale)
            sale_dict.pop("is_synced", None)
            sale_dict["items"] = [dict(i) for i in items]
            db.collection("sales").document(str(sale_id)).set(sale_dict)
            conn.execute("UPDATE sales SET is_synced = 1 WHERE id = ?", (sale_id,))
            conn.commit()
            print(f"[remote_control] [OK] Sale #{sale_id} pushed to Firebase.")
        conn.close()
    except Exception as e:
        print(f"[remote_control] sale #{sale_id} push failed: {e}")

def push_sale_to_cloud(sale_id):
    """Upload a POS sale + items right after checkout in background."""
    threading.Thread(target=_worker_push_sale, args=(sale_id,), daemon=True).start()


def _worker_push_product(product_id):
    try:
        db = _init_firebase()
        if not db:
            return
        conn = get_connection()
        product = conn.execute("""
            SELECT p.*, c.name AS category_name
            FROM products p
            LEFT JOIN categories c ON p.category_id = c.id
            WHERE p.id = ?
        """, (product_id,)).fetchone()
        conn.close()
        if product:
            p_dict = dict(product)
            doc_id = str(p_dict.get("sku")) if p_dict.get("sku") else str(p_dict.get("id"))
            db.collection("products").document(doc_id).set(p_dict)
            print(f"[remote_control] [OK] Product #{product_id} ({p_dict.get('category_name')}) pushed to Firebase.")
    except Exception as e:
        print(f"[remote_control] product #{product_id} push failed: {e}")

def push_product_to_cloud(product_id):
    """Upload a product right after update or creation in background."""
    threading.Thread(target=_worker_push_product, args=(product_id,), daemon=True).start()


def _worker_push_categories():
    try:
        db = _init_firebase()
        if not db:
            return
        conn = get_connection()
        cats = conn.execute("SELECT * FROM categories ORDER BY name").fetchall()
        conn.close()
        for c in cats:
            c_dict = dict(c)
            db.collection("categories").document(str(c_dict["id"])).set(c_dict)
        print(f"[remote_control] [OK] {len(cats)} Categories pushed to Firebase.")
    except Exception as e:
        print(f"[remote_control] push categories failed: {e}")

def push_categories_to_cloud():
    """Upload categories to Firestore in background."""
    threading.Thread(target=_worker_push_categories, daemon=True).start()


def delete_product_from_cloud(sku):
    """Mirror local product deletion into Firestore."""
    def _worker():
        try:
            db = _init_firebase()
            if not db:
                return
            db.collection("products").document(str(sku)).delete()
        except Exception as e:
            print(f"[remote_control] product delete failed: {e}")
    threading.Thread(target=_worker, daemon=True).start()


def _worker_push_online_order(order_id):
    try:
        db = _init_firebase()
        if not db:
            return
        conn = get_connection()
        order = conn.execute("SELECT * FROM online_orders WHERE id = ?", (order_id,)).fetchone()
        items = conn.execute("SELECT * FROM online_order_items WHERE order_id = ?", (order_id,)).fetchall()
        conn.close()
        if order:
            order_dict = dict(order)
            order_dict["items"] = [dict(i) for i in items]
            db.collection("online_orders").document(str(order["order_number"])).set(order_dict)
            print(f"[remote_control] [OK] Online Order #{order_id} pushed to Firebase.")
    except Exception as e:
        print(f"[remote_control] online order #{order_id} push failed: {e}")

def push_online_order_to_cloud(order_id):
    """Upload online order + items to Firestore in background."""
    threading.Thread(target=_worker_push_online_order, args=(order_id,), daemon=True).start()


def push_delivery_areas_to_cloud():
    """Upload active delivery areas to Firestore in background."""
    def _worker():
        try:
            db = _init_firebase()
            if not db:
                return
            conn = get_connection()
            areas = conn.execute("SELECT * FROM delivery_areas WHERE is_active = 1").fetchall()
            conn.close()
            db.collection("config").document("delivery_areas").set({"areas": [dict(a) for a in areas]})
        except Exception as e:
            print(f"[remote_control] push delivery areas failed: {e}")
    threading.Thread(target=_worker, daemon=True).start()


def push_all_to_cloud():
    """Pushes full state to cloud after a system reset or major change."""
    try:
        push_full_backup()
        push_categories_to_cloud()
        if 'push_packages_to_cloud' in globals():
            push_packages_to_cloud()
        push_delivery_areas_to_cloud()
    except Exception as e:
        print(f"[remote_control] push_all_to_cloud error: {e}")


def push_full_backup():
    """Full periodic sync safety net."""
    try:
        db = _init_firebase()
        if not db:
            return
        conn = get_connection()

        # Push Categories
        for cat_row in conn.execute("SELECT * FROM categories").fetchall():
            db.collection("categories").document(str(cat_row["id"])).set(dict(cat_row))

        # Push Products with Category Name
        for row in conn.execute("""
            SELECT p.*, c.name AS category_name
            FROM products p
            LEFT JOIN categories c ON p.category_id = c.id
        """).fetchall():
            r_dict = dict(row)
            doc_id = str(r_dict.get("sku")) if r_dict.get("sku") else str(r_dict.get("id"))
            db.collection("products").document(doc_id).set(r_dict)

        for row in conn.execute("SELECT * FROM settings").fetchall():
            db.collection("settings").document(row["key"]).set({"value": row["value"]})

        areas = conn.execute("SELECT * FROM delivery_areas WHERE is_active = 1").fetchall()
        db.collection("config").document("delivery_areas").set({"areas": [dict(a) for a in areas]})

        orders = conn.execute("SELECT * FROM online_orders").fetchall()
        for ord_row in orders:
            items = conn.execute("SELECT * FROM online_order_items WHERE order_id = ?", (ord_row["id"],)).fetchall()
            o_dict = dict(ord_row)
            o_dict["items"] = [dict(i) for i in items]
            db.collection("online_orders").document(str(ord_row["order_number"])).set(o_dict)

        unsynced = conn.execute("SELECT id FROM sales WHERE is_synced = 0").fetchall()
        conn.close()

        for row in unsynced:
            push_sale_to_cloud(row["id"])

        print("[remote_control] [OK] full backup cycle complete.")
    except Exception as e:
        print(f"[remote_control] full backup failed: {e}")


# ---------------------------------------------------------------------------
# 2) TWO-WAY SYNC (Firebase Console -> Local SQLite Database)
# ---------------------------------------------------------------------------

def _on_products_change(doc_snapshots, changes, read_time):
    """
    Live listener watching `products` collection in Firestore.
    If the shop owner modifies product price, stock, or name in Firebase Console,
    it updates the local SQLite database automatically in real time!
    """
    try:
        conn = get_connection()
        for change in changes:
            doc = change.document
            data = doc.to_dict() or {}
            sku = doc.id
            if change.type.name in ("ADDED", "MODIFIED"):
                name = data.get("name")
                sell_price = data.get("sell_price")
                mrp = data.get("mrp")
                stock_qty = data.get("stock_qty")
                description = data.get("description", "")
                image_url = data.get("image_url", "")
                is_trending = data.get("is_trending", 0)
                is_flash_sale = data.get("is_flash_sale", 0)
                is_offer = data.get("is_offer", 0)
                offer_title = data.get("offer_title", "")

                if name and sell_price is not None:
                    conn.execute("""
                        UPDATE products SET name=?, sell_price=?, mrp=?, stock_qty=?,
                                             description=?, image_url=?, is_trending=?,
                                             is_flash_sale=?, is_offer=?, offer_title=?
                        WHERE sku=?
                    """, (name, float(sell_price), float(mrp or 0), int(stock_qty or 0),
                          description, image_url, int(is_trending or 0),
                          int(is_flash_sale or 0), int(is_offer or 0), offer_title, sku))
            elif change.type.name == "REMOVED":
                conn.execute("DELETE FROM products WHERE sku=?", (sku,))
        conn.commit()
        conn.close()
        print(f"[remote_control] [SYNC] Two-Way Product Sync updated local SQLite DB from Firebase Console.")
    except Exception as e:
        print(f"[remote_control] Two-way product sync failed: {e}")


def _on_settings_change(doc_snapshots, changes, read_time):
    for doc in doc_snapshots:
        data = doc.to_dict() or {}
        with _state_lock:
            STATE["maintenance_mode"] = bool(data.get("maintenance_mode", False))
            STATE["maintenance_message"] = data.get(
                "maintenance_message", STATE["maintenance_message"]
            )
            STATE["announcement"] = data.get("announcement", "")
            STATE["force_logout"] = bool(data.get("force_logout", False))
        print(f"[remote_control] [SYNC] remote settings updated: {STATE}")


def _ensure_remote_doc(db):
    ref = db.collection("remote_control").document("settings")
    if not ref.get().exists:
        ref.set(STATE)


def _on_online_orders_change(doc_snapshots, changes, read_time):
    """
    Live listener watching `online_orders` collection in Firestore.
    If a customer places an order on mobile app / website cloud server,
    it syncs into local SQLite database automatically in real time!
    """
    try:
        conn = get_connection()
        for change in changes:
            doc = change.document
            data = doc.to_dict() or {}
            order_number = doc.id
            if change.type.name in ("ADDED", "MODIFIED"):
                existing = conn.execute("SELECT id FROM online_orders WHERE order_number = ?", (order_number,)).fetchone()
                if not existing:
                    cur = conn.cursor()
                    cur.execute("""
                        INSERT INTO online_orders (
                            order_number, customer_name, customer_phone, customer_email,
                            country, district, area, address_details, payment_method,
                            payment_status, subtotal, delivery_charge, total_amount,
                            order_status, delivery_otp, created_at, updated_at
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        order_number,
                        data.get("customer_name", ""),
                        data.get("customer_phone", ""),
                        data.get("customer_email", ""),
                        data.get("country", "Bangladesh"),
                        data.get("district", ""),
                        data.get("area", ""),
                        data.get("address_details", ""),
                        data.get("payment_method", "cod"),
                        data.get("payment_status", "pending"),
                        float(data.get("subtotal") or 0.0),
                        float(data.get("delivery_charge") or 60.0),
                        float(data.get("total_amount") or 0.0),
                        data.get("order_status", "new"),
                        data.get("delivery_otp", ""),
                        data.get("created_at", datetime.now().isoformat()),
                        data.get("updated_at", datetime.now().isoformat())
                    ))
                    new_order_id = cur.lastrowid
                    items = data.get("items", [])
                    for item in items:
                        cur.execute("""
                            INSERT INTO online_order_items (order_id, product_id, product_name, unit_price, mrp_price, quantity, total_price)
                            VALUES (?, ?, ?, ?, ?, ?, ?)
                        """, (
                            new_order_id,
                            item.get("product_id", 0),
                            item.get("product_name", ""),
                            float(item.get("unit_price") or 0.0),
                            float(item.get("mrp_price") or 0.0),
                            int(item.get("quantity") or 1),
                            float(item.get("total_price") or 0.0)
                        ))
                    print(f"[remote_control] [SYNC] Real-time online order #{order_number} synced from Firebase to local SQLite DB.")
                else:
                    conn.execute(
                        "UPDATE online_orders SET order_status = ?, payment_status = ?, updated_at = ? WHERE order_number = ?",
                        (data.get("order_status", "new"), data.get("payment_status", "pending"), datetime.now().isoformat(), order_number)
                    )
        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[remote_control] online orders sync failed: {e}")


def start():
    """Starts Firebase listeners and periodic backup thread."""
    db = _init_firebase()
    if not db:
        print("[remote_control] [ALERT] Firebase not initialized. (Add firebase_credentials.json to enable live sync)")
        return

    try:
        _ensure_remote_doc(db)

        # Live listeners (Firebase Console -> Local App)
        db.collection("remote_control").document("settings").on_snapshot(_on_settings_change)
        db.collection("products").on_snapshot(_on_products_change)
        db.collection("online_orders").on_snapshot(_on_online_orders_change)

        def _safety_net_loop():
            while True:
                push_full_backup()
                time.sleep(300)

        threading.Thread(target=_safety_net_loop, daemon=True).start()
        print("[remote_control] [OK] Firebase real-time two-way backup & remote control started.")
    except Exception as e:
        print(f"[remote_control] start error: {e}")


def is_maintenance_mode():
    with _state_lock:
        return STATE["maintenance_mode"], STATE["maintenance_message"]


def get_announcement():
    with _state_lock:
        return STATE["announcement"]


def should_force_logout():
    with _state_lock:
        return STATE["force_logout"]
