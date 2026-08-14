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

from database import get_connection, execute_with_retry, _db_write_lock

CRED_FILE = "firebase_credentials.json"

STATE = {
    "maintenance_mode": False,
    "maintenance_message": "Shop is temporarily closed. Please try again later.",
    "announcement": "",
    "force_logout": False,
}

_db = None
_state_lock = threading.Lock()


B64_FIREBASE_CRED = "eyJ0eXBlIjogInNlcnZpY2VfYWNjb3VudCIsICJwcm9qZWN0X2lkIjogImRvaW5lZWstcG9zLWU0MDIzIiwgInByaXZhdGVfa2V5X2lkIjogImRvaW5lZWstcG9zLWU0MDIzIiwgInByaXZhdGVfa2V5IjogIi0tLS0tQkVHSU4gUFJJVkFURSBLRVktLS0tLVxuTUlJRXZnSUJBREFOR2txaGtpRzl3MEJBUUVGQUFTQ0JLZ3dnZ1NrQWdFQUFvSUJBUURRMzMwbXprY3pWU2JoXG5OVzJ4Nm4zQnBCVGtyRlNLRzFBZy9XL2lqcU9vM3B0MlIwSXQ0SGZPdmVHYTBDZ1NXTERTUlBpK2NiVTFVUDhTXG5rVkdlZTg3YlVPU2Zqa0IwU2VLZVlJUWxnREs2dkEySTlLTm5yOXRvT20xdG9tVjJZN2xSaEgwd3hVNk8yaHJEXG4zU2lhc0F0emRtZ3BMMHZIa0xkalRlUXhDVXlyaXVzK0UwZFIrNzUweTdldWY4ZWFrcmRML3lKdnBTNHZzSDA1XG5tQkRnTUc3RWtkbml5VFoxdFVhRTJGSWxaZVN5V3NBZ2gwTzROOHBjc01HdENvZzFKTGl1cnl5dVZCUXQwSjNSXG42K0d3aS9zTGtwNzR5VWNDWjFwdU82Y1ZJVmpneW4zeG1OdkZOYmEwUi9QNnVHRzVpa0NYMW9taUVvUEI2eVNzXG4yS3NxN01mTEFnTUJBQUVDZ2dFQUVqU3VBNWc1UVRLQk1yZGx6MUNCYU81MHI4Q01RZGx0bTQwdzdRNFh4UndFXG54WmpOSGozbTAzWUkyR1gxQ0RHdUtvc1R6MWhqNkxqSVNEQmR3b2hIYmRCWU44YStFWG9iTHZONkJvd1h0VFVNXG45NklJZ3RJampWWFh2SldmYmJsSzFETWpJbGJLL25mbzhLZUhQQ3h2WXhTd0J0NzJKazAraVlEOE55dE9BU21iXG5SY0FQQkIydVFabUl3MUs5RmhhRnlXVXcwUGN2aWx0MlY3TVJHQ2JIeVNwS2U3cDNIU2JnbjFsOS9Ib0xMMnRrXG5nNTEweXR6WmlWQ1hFUlhZd0tUNHd2RkFkM3hpVHBjSWNPMHhjc0kwSnBQWSt6clVYYmFZSXNFaGZtcUlzNGFJXG5DSG5LU09GR05kRjV1bzJJRUpVMEUvZE1OODgxOHpFa0tydzQ2NUFHaVFLQmdRRDBpMXRXYmwrLzJKWElnSVUvXG5JRzc1ZUxjdk5zaWFaUFhVTWdNU2JaZDE2Z2kySDQvM3E3elJNK25ldldvaDJMakc5ekx6a3NYRWNHSjdKckZpXG5BU2NOQnltQ1lNZTRVREgwNmxqNkgyYUdXUEpZYjBpeWtxeUE4eXZQTlhrYVE1VytvNFdDdGVwejlneHgwQlErXG5EdU5qUUlvQjRJVDhrN1JhQUNmTFZPeUh2d0tCZ1FEYXFGbnhvTkY0OFlTL2lFbjFGbHA3Unp2MXdUQ1Jnd29aXG45UHJ4YlM0MXV1LzkzT2UwRXFWOFFKazk2YnpFRlk0RGU4a3orUmdpdDQxdTI3SUdkMzdBRkQ1VXNBT2krVXptXG5lNDR5ZEoxVGNJMnVtRVVaSUF6Ty9rVG9qT0hQNDBIRGRTSHdSRFgwVjQ5SjRKUmxldkQ5U1dlQU9PZ2NUczQ4XG5ocVBrczFpaTlRS0JnUUNFbDJMSXRFTzZNMmJUTmN3SmRENTNpVnBaZ1N5M2VmSklRVzJrK2tMYkxpL1cvN29CXG5vZDVZMS9zQVNGZFpUcmF4T3Fzbm9mY1ZFWkowRDRDeUVNbnBxRzU3UUpwSmQwSCs5Mm1UQkorRVRJbnFKVHlYXG5oaXQrSjFzam1HeTNMdG5zYWFFa1JCcUJFWEdoN0I1dG40anU4YmxpVnlnRUF0b1F5bkRKTUp5bTVRS0JnRmxGXG5wTHMvSW1iVGpKUTZTNSt4eWExTlR4Q3VHR3RBYWU1aEU5ZGY4UjdrdkxrVDZOR2ZUMHNrZ0t4RGN0dEh4WnhzXG5mS0Fva2c4U2k3NzRHWDRFYVk1NGRWNVVJcGYyV3N3N0k3bzczRVBGejBLNlRuUE1udzRmeC9oK0ZHK3c1QmV1XG5DZll6a3llNFcvc1lvdDJ2elJaTVV1S0oyVkk5Wm54VnFESm1lc2pGQW9HQkFNdjJnazJHOEZrQlo5bVBuRitMXG5FZWlLMi81YTdYdXlwTEdEb1Bvcmx0NnZuYlBkV0xsaVZEZDRsQ3QxL3VoVXNDK1V3QUhWV1Frdk04SnBKOUFJXG5KVEJwZGtid1kzci8wd2sxdXQvMURPN1h4T1ZNVzJiRnhHRjd1ZU5TZ0E4blFBZDJMK0NuY2l5R1I3bVZhb2V2XG50R3o3MzJrNnowRmpZUWdCcnpWRlpBMUNcbi0tLS0tRU5EIFBSSVZBVEUgS0VZLS0tLS1cbiIsICJjbGllbnRfZW1haWwiOiAiZmlyZWJhc2UtYWRtaW5zZGstZmJzdmNAZG9pbmVlay1wb3MtZTQwMjMuaWFtLmdzZXJ2aWNlYWNjb3VudC5jb20iLCAiY2xpZW50X2lkIjogIjExMjQyOTg5NDMxNTI5MTA0MDE1MiIsICJhdXRoX3VyaSI6ICJodHRwczovL2FjY291bnRzLmdvb2dsZS5jb20vby9vYXV0aDIvYXV0aCIsICJ0b2tlbl91cmkiOiAiaHR0cHM6Ly9vYXV0aDIuZ29vZ2xlYXBpcy5jb20vdG9rZW4iLCAiYXV0aF9wcm92aWRlcl94NTA5X2NlcnRfdXJsIjogImh0dHBzOi8vd3d3Lmdvb2dsZWFwaXMuY29tL29hdXRoMi92MS9jZXJ0cyIsICJjbGllbnRfeDUwOV9jZXJ0X3VybCI6ICJodHRwczovL3d3dy5nb29nbGVhcGlzLmNvbS9yb2JvdC92MS9tZXRhZGF0YS94NTA5L2ZpcmViYXNlLWFkbWluc2RrLWZic3ZjJTQwZG9pbmVlay1wb3MtZTQwMjMuaWFtLmdzZXJ2aWNlYWNjb3VudC5jb20iLCAidW5pdmVyc2VfZG9tYWluIjogImdvb2dsZWFwaXMuY29tIn0="

def _get_fallback_cred():
    try:
        import base64, json
        raw = base64.b64decode(B64_FIREBASE_CRED.encode()).decode()
        return credentials.Certificate(json.loads(raw))
    except Exception:
        return None


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
            cred = _get_fallback_cred()

        if not cred:
            print(f"[remote_control] [ALERT] Firebase credentials not available.")
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
            doc_id = str(sale_dict.get("invoice_number")) if sale_dict.get("invoice_number") else str(sale_id)
            db.collection("sales").document(doc_id).set(sale_dict)
            conn.execute("UPDATE sales SET is_synced = 1 WHERE id = ?", (sale_id,))
            conn.commit()
            print(f"[remote_control] [OK] Sale #{sale_id} (Invoice: {doc_id}) pushed to Firebase.")

            # If customer_mobile exists, also push customer to customer_users collection in Firebase
            c_phone = sale_dict.get("customer_mobile")
            if c_phone:
                digits = "".join(ch for ch in str(c_phone) if ch.isdigit())
                if digits.startswith("8801") and len(digits) == 13:
                    digits = digits[2:]
                if digits:
                    cust = conn.execute("SELECT * FROM customer_users WHERE phone = ?", (digits,)).fetchone()
                    if cust:
                        db.collection("customer_users").document(digits).set(dict(cust))
        conn.close()
    except Exception as e:
        print(f"[remote_control] sale #{sale_id} push failed: {e}")

def push_sale_to_cloud(sale_id):
    """Upload a POS sale + items right after checkout in background."""
    threading.Thread(target=_worker_push_sale, args=(sale_id,), daemon=True).start()


def _worker_push_customer_user(phone):
    try:
        db = _init_firebase()
        if not db:
            return
        conn = get_connection()
        user = conn.execute("SELECT * FROM customer_users WHERE phone = ?", (phone,)).fetchone()
        conn.close()
        if user:
            u_dict = dict(user)
            db.collection("customer_users").document(str(phone)).set(u_dict)
            print(f"[remote_control] [OK] Customer User {phone} pushed to Firebase.")
    except Exception as e:
        print(f"[remote_control] customer {phone} push failed: {e}")

def push_customer_user_to_cloud(phone):
    """Uploads a customer user to Firebase Firestore in background."""
    threading.Thread(target=_worker_push_customer_user, args=(phone,), daemon=True).start()


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
        sub_cats = conn.execute("SELECT * FROM sub_categories ORDER BY name").fetchall()
        sub_sub_cats = conn.execute("SELECT * FROM sub_sub_categories ORDER BY name").fetchall()
        conn.close()

        active_cat_ids = {str(c["id"]) for c in cats}
        try:
            cloud_docs = db.collection("categories").stream()
            for doc in cloud_docs:
                if doc.id not in active_cat_ids:
                    db.collection("categories").document(doc.id).delete()
        except Exception:
            pass

        for c in cats:
            c_dict = dict(c)
            c_id = c["id"]
            cat_subs = [dict(s) for s in sub_cats if s["category_id"] == c_id]
            for s in cat_subs:
                s_id = s["id"]
                s["sub_sub_categories"] = [dict(ss) for ss in sub_sub_cats if ss["sub_category_id"] == s_id]
            c_dict["sub_categories"] = cat_subs
            db.collection("categories").document(str(c_id)).set(c_dict)

        print(f"[remote_control] [OK] {len(cats)} Categories (with subcategories) pushed to Firebase.")
    except Exception as e:
        print(f"[remote_control] push categories failed: {e}")

def push_categories_to_cloud():
    """Upload categories to Firestore in background."""
    threading.Thread(target=_worker_push_categories, daemon=True).start()


def _worker_push_brands():
    try:
        db = _init_firebase()
        if not db:
            return
        conn = get_connection()
        brands = conn.execute("SELECT * FROM brands ORDER BY name").fetchall()
        conn.close()

        active_brand_ids = {str(b["id"]) for b in brands}
        try:
            cloud_docs = db.collection("brands").stream()
            for doc in cloud_docs:
                if doc.id not in active_brand_ids:
                    db.collection("brands").document(doc.id).delete()
        except Exception:
            pass

        for b in brands:
            b_dict = dict(b)
            db.collection("brands").document(str(b["id"])).set(b_dict)

        print(f"[remote_control] [OK] {len(brands)} Brands pushed to Firebase.")
    except Exception as e:
        print(f"[remote_control] push brands failed: {e}")

def push_brands_to_cloud():
    """Upload brands to Firestore in background."""
    threading.Thread(target=_worker_push_brands, daemon=True).start()


def _worker_push_users():
    try:
        db = _init_firebase()
        if not db:
            return
        conn = get_connection()
        users = conn.execute("SELECT id, username, password_hash, role, created_at FROM users").fetchall()
        conn.close()
        for u in users:
            u_dict = dict(u)
            db.collection("users").document(str(u_dict["username"])).set(u_dict)
        print(f"[remote_control] [OK] {len(users)} Staff/Admin users pushed to Firebase Cloud.")
    except Exception as e:
        print(f"[remote_control] push users failed: {e}")


def push_users_to_cloud():
    """Upload staff & admin user accounts and password hashes to Firestore in background."""
    threading.Thread(target=_worker_push_users, daemon=True).start()


def delete_product_from_cloud(sku, product_id=None):
    """Mirror local product deletion into Firestore."""
    def _worker():
        try:
            db = _init_firebase()
            if not db:
                return
            if sku:
                db.collection("products").document(str(sku)).delete()
            if product_id:
                db.collection("products").document(str(product_id)).delete()
        except Exception as e:
            print(f"[remote_control] product delete failed: {e}")
    threading.Thread(target=_worker, daemon=True).start()


def _worker_push_packages():
    try:
        db = _init_firebase()
        if not db:
            return
        conn = get_connection()
        pkg_rows = conn.execute("SELECT * FROM packages WHERE is_active = 1 ORDER BY id DESC").fetchall()
        
        active_ids = {str(r["id"]) for r in pkg_rows}
        try:
            cloud_docs = db.collection("packages").stream()
            for doc in cloud_docs:
                if doc.id not in active_ids:
                    db.collection("packages").document(doc.id).delete()
        except Exception:
            pass

        for pkg in pkg_rows:
            p_dict = dict(pkg)
            items = conn.execute("""
                SELECT pi.*, p.name AS product_name, p.sell_price, p.mrp, p.image_url, p.sku
                FROM package_items pi JOIN products p ON pi.product_id = p.id
                WHERE pi.package_id = ?
            """, (pkg["id"],)).fetchall()
            p_dict["items"] = [dict(i) for i in items]
            db.collection("packages").document(str(pkg["id"])).set(p_dict)
        conn.close()
        print(f"[remote_control] [OK] {len(pkg_rows)} Packages pushed & synced to Firebase Cloud.")
    except Exception as e:
        print(f"[remote_control] push packages failed: {e}")


def push_packages_to_cloud():
    """Upload product packages & combo bundles to Firestore in background."""
    threading.Thread(target=_worker_push_packages, daemon=True).start()


def delete_package_from_cloud(package_id):
    """Mirror local package deletion into Firestore."""
    def _worker():
        try:
            db = _init_firebase()
            if not db:
                return
            db.collection("packages").document(str(package_id)).delete()
            push_packages_to_cloud()
        except Exception as e:
            print(f"[remote_control] package delete failed: {e}")
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
        push_brands_to_cloud()
        if 'push_packages_to_cloud' in globals():
            push_packages_to_cloud()
        push_delivery_areas_to_cloud()
    except Exception as e:
        print(f"[remote_control] push_all_to_cloud error: {e}")


def push_full_backup():
    """Full periodic sync safety net - pushes ALL local data to Firebase."""
    try:
        db = _init_firebase()
        if not db:
            return

        # Read ALL data from local SQLite FIRST, then close connection
        conn = get_connection()
        try:
            products = conn.execute("""
                SELECT p.*, c.name AS category_name
                FROM products p
                LEFT JOIN categories c ON p.category_id = c.id
            """).fetchall()
            active_skus = set()
            for r in products:
                if r["sku"]: active_skus.add(str(r["sku"]))
                active_skus.add(str(r["id"]))

            settings_rows = conn.execute("SELECT * FROM settings").fetchall()
            areas = conn.execute("SELECT * FROM delivery_areas WHERE is_active = 1").fetchall()
            orders = conn.execute("SELECT * FROM online_orders").fetchall()
            order_items_map = {}
            for ord_row in orders:
                items = conn.execute("SELECT * FROM online_order_items WHERE order_id = ?", (ord_row["id"],)).fetchall()
                order_items_map[ord_row["id"]] = [dict(i) for i in items]
            users = conn.execute("SELECT id, username, password_hash, role, created_at FROM users").fetchall()
            packages = conn.execute("SELECT * FROM packages WHERE is_active = 1").fetchall()
            pkg_items_map = {}
            for pkg_row in packages:
                items = conn.execute("""
                    SELECT pi.*, p.name AS product_name, p.sell_price, p.mrp, p.image_url, p.sku
                    FROM package_items pi JOIN products p ON pi.product_id = p.id
                    WHERE pi.package_id = ?
                """, (pkg_row["id"],)).fetchall()
                pkg_items_map[pkg_row["id"]] = [dict(i) for i in items]
            unsynced = conn.execute("SELECT id FROM sales WHERE is_synced = 0").fetchall()
        finally:
            conn.close()  # Close BEFORE any Firebase writes or thread spawns

        # Clean up deleted products from Firestore
        try:
            cloud_docs = db.collection("products").stream()
            for doc in cloud_docs:
                if doc.id not in active_skus:
                    db.collection("products").document(doc.id).delete()
        except Exception:
            pass

        # Push products
        for row in products:
            r_dict = dict(row)
            doc_id = str(r_dict.get("sku")) if r_dict.get("sku") else str(r_dict.get("id"))
            db.collection("products").document(doc_id).set(r_dict)

        # Push settings
        for row in settings_rows:
            db.collection("settings").document(row["key"]).set({"value": row["value"]})

        # Push delivery areas
        db.collection("config").document("delivery_areas").set({"areas": [dict(a) for a in areas]})

        # Push online orders
        for ord_row in orders:
            o_dict = dict(ord_row)
            o_dict["items"] = order_items_map.get(ord_row["id"], [])
            db.collection("online_orders").document(str(ord_row["order_number"])).set(o_dict)

        # Push users
        for u_row in users:
            db.collection("users").document(str(u_row["username"])).set(dict(u_row))

        # Push customer users
        try:
            cust_conn = get_connection()
            cust_users = cust_conn.execute("SELECT * FROM customer_users").fetchall()
            cust_conn.close()
            for c_row in cust_users:
                c_dict = dict(c_row)
                if c_dict.get("phone"):
                    db.collection("customer_users").document(str(c_dict["phone"])).set(c_dict)
        except Exception:
            pass

        # Push packages
        for pkg_row in packages:
            p_dict = dict(pkg_row)
            p_dict["items"] = pkg_items_map.get(pkg_row["id"], [])
            db.collection("packages").document(str(pkg_row["id"])).set(p_dict)

        # Now spawn child pushes (connection is already closed)
        push_categories_to_cloud()
        push_brands_to_cloud()

        # Push unsynced sales
        for row in unsynced:
            push_sale_to_cloud(row["id"])

        print("[remote_control] [OK] full backup cycle complete.")

    except Exception as e:
        print(f"[remote_control] full backup failed: {e}")



def wipe_cloud_collections(categories):
    """Deletes documents from specified Firestore collections when system reset occurs."""
    def _worker():
        try:
            db = _init_firebase()
            if not db:
                return

            coll_map = {
                "inventory": ["products"],
                "sales_log": ["sales"],
                "online_orders": ["online_orders"],
                "packages": ["packages"],
                "offers_promotions": ["vouchers"],
                "customers": ["customer_users"],
                "all": ["products", "sales", "online_orders", "packages", "vouchers", "customer_users", "categories", "brands"]
            }

            target_colls = set()
            for cat in categories:
                if cat in coll_map:
                    target_colls.update(coll_map[cat])

            for coll_name in target_colls:
                try:
                    docs = db.collection(coll_name).stream()
                    for doc in docs:
                        db.collection(coll_name).document(doc.id).delete()
                    print(f"[remote_control] [WIPE] Cloud collection '{coll_name}' cleared on reset.")
                except Exception as c_err:
                    print(f"[remote_control] Cloud wipe error on '{coll_name}': {c_err}")
        except Exception as e:
            print(f"[remote_control] wipe_cloud_collections error: {e}")

    threading.Thread(target=_worker, daemon=True).start()


# ---------------------------------------------------------------------------
# 2) TWO-WAY SYNC (Firebase Console -> Local SQLite Database)
# ---------------------------------------------------------------------------

def _on_products_change(doc_snapshots, changes, read_time):
    """
    Live listener watching `products` collection in Firestore.
    Syncs product creation, updates, and deletions in real time across servers.
    """
    def _do_sync():
        conn = get_connection()
        try:
            for change in changes:
                doc = change.document
                data = doc.to_dict() or {}
                doc_id = doc.id
                sku = data.get("sku") or doc_id
                prod_id = data.get("id")

                if change.type.name in ("ADDED", "MODIFIED"):
                    name = data.get("name")
                    if not name:
                        continue

                    brand = data.get("brand", "")
                    unit = data.get("unit", "")
                    category_id = data.get("category_id")
                    sub_category_id = data.get("sub_category_id")
                    sub_sub_category_id = data.get("sub_sub_category_id")
                    cost_price = float(data.get("cost_price") or 0)
                    mrp = float(data.get("mrp") or 0)
                    sell_price = float(data.get("sell_price") or 0)
                    vat_pct = float(data.get("vat_pct") or 0)
                    stock_qty = int(data.get("stock_qty") or 0)
                    low_stock_threshold = int(data.get("low_stock_threshold") or 5)
                    sl_number = int(data.get("sl_number") or 1)
                    description = data.get("description", "")
                    image_url = data.get("image_url", "")
                    is_trending = int(data.get("is_trending") or 0)
                    is_flash_sale = int(data.get("is_flash_sale") or 0)
                    is_offer = int(data.get("is_offer") or 0)
                    is_promotion = int(data.get("is_promotion") or 0)
                    offer_title = data.get("offer_title", "")
                    offer_type = data.get("offer_type", "")
                    offer_value = data.get("offer_value", "")
                    offer_base = data.get("offer_base", "mrp")
                    expiry_date = data.get("expiry_date", "")

                    existing = None
                    if sku:
                        existing = conn.execute("SELECT id FROM products WHERE sku = ?", (sku,)).fetchone()
                    if not existing and prod_id:
                        existing = conn.execute("SELECT id FROM products WHERE id = ?", (prod_id,)).fetchone()

                    if existing:
                        conn.execute("""
                            UPDATE products SET
                                sku=?, name=?, brand=?, unit=?, category_id=?, sub_category_id=?, sub_sub_category_id=?,
                                cost_price=?, mrp=?, sell_price=?, vat_pct=?, stock_qty=?, low_stock_threshold=?,
                                sl_number=?, description=?, image_url=?, is_trending=?, is_flash_sale=?,
                                is_offer=?, is_promotion=?, offer_title=?, offer_type=?, offer_value=?, offer_base=?, expiry_date=?
                            WHERE id=?
                        """, (
                            sku, name, brand, unit, category_id, sub_category_id, sub_sub_category_id,
                            cost_price, mrp, sell_price, vat_pct, stock_qty, low_stock_threshold,
                            sl_number, description, image_url, is_trending, is_flash_sale,
                            is_offer, is_promotion, offer_title, offer_type, offer_value, offer_base, expiry_date,
                            existing["id"]
                        ))
                    else:
                        conn.execute("""
                            INSERT INTO products (
                                sku, name, brand, unit, category_id, sub_category_id, sub_sub_category_id,
                                cost_price, mrp, sell_price, vat_pct, stock_qty, low_stock_threshold,
                                sl_number, description, image_url, is_trending, is_flash_sale,
                                is_offer, is_promotion, offer_title, offer_type, offer_value, offer_base, expiry_date
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            sku, name, brand, unit, category_id, sub_category_id, sub_sub_category_id,
                            cost_price, mrp, sell_price, vat_pct, stock_qty, low_stock_threshold,
                            sl_number, description, image_url, is_trending, is_flash_sale,
                            is_offer, is_promotion, offer_title, offer_type, offer_value, offer_base, expiry_date
                        ))

                elif change.type.name == "REMOVED":
                    conn.execute("DELETE FROM products WHERE sku=? OR id=?", (sku, prod_id or sku))
            conn.commit()
        finally:
            conn.close()

    try:
        execute_with_retry(_do_sync)
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
    it syncs into local SQLite database (online_orders, customer_users, sales) automatically in real time!
    """
    def _do():
        conn = get_connection()
        try:
            for change in changes:
                doc = change.document
                data = doc.to_dict() or {}
                order_number = doc.id
                c_name = data.get("customer_name", "")
                c_phone = data.get("customer_phone", "")
                c_email = data.get("customer_email", "")

                # 1. Auto-create or ensure customer in customer_users
                digits = "".join(ch for ch in str(c_phone) if ch.isdigit())
                if digits.startswith("8801") and len(digits) == 13:
                    digits = digits[2:]
                if digits and len(digits) == 11 and digits.startswith("01"):
                    chk_cust = conn.execute("SELECT id, name FROM customer_users WHERE phone = ?", (digits,)).fetchone()
                    if not chk_cust:
                        from werkzeug.security import generate_password_hash
                        pass_hash = generate_password_hash("123456")
                        name_to_use = c_name.strip() if c_name and c_name.strip() else f"Customer {digits[-4:]}"
                        conn.execute("""
                            INSERT INTO customer_users (phone, name, email, password_hash, plain_password, is_verified, created_at)
                            VALUES (?, ?, ?, ?, '123456', 1, ?)
                        """, (digits, name_to_use, c_email or "", pass_hash, data.get("created_at") or datetime.now().isoformat()))
                    elif c_name and c_name.strip() and (not chk_cust["name"] or chk_cust["name"].startswith("Customer ")):
                        conn.execute("UPDATE customer_users SET name = ? WHERE phone = ?", (c_name.strip(), digits))

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
                            c_name,
                            c_phone,
                            c_email,
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
                            raw_pid = item.get("product_id") or 0
                            valid_pid = raw_pid
                            chk_p = conn.execute("SELECT id FROM products WHERE id = ?", (raw_pid,)).fetchone()
                            if not chk_p:
                                first_p = conn.execute("SELECT id FROM products LIMIT 1").fetchone()
                                valid_pid = first_p["id"] if first_p else 1
                            cur.execute("""
                                INSERT INTO online_order_items (order_id, product_id, product_name, unit_price, mrp_price, quantity, total_price)
                                VALUES (?, ?, ?, ?, ?, ?, ?)
                            """, (
                                new_order_id, valid_pid,
                                item.get("product_name", ""),
                                float(item.get("unit_price") or 0.0),
                                float(item.get("mrp_price") or 0.0),
                                int(item.get("quantity") or 1),
                                float(item.get("total_price") or 0.0)
                            ))

                        # 2. Also ensure this online order is in the sales table (Sales Log)
                        inv_num = f"INV-ONLINE-{order_number}"
                        existing_sale = conn.execute("SELECT id FROM sales WHERE invoice_number = ?", (inv_num,)).fetchone()
                        if not existing_sale:
                            cur.execute("""
                                INSERT INTO sales (
                                    invoice_number, invoice_date, cashier_id, customer_id, customer_name, customer_mobile, channel,
                                    total_amount, rounded_total, vat_amount, saved_amount, cash_amount, card_amount, change_amount, created_at, is_synced
                                ) VALUES (?, ?, 1, ?, ?, ?, 'Online', ?, ?, 0, 0, ?, 0, 0, ?, 1)
                            """, (
                                inv_num,
                                data.get("created_at", datetime.now().strftime("%Y-%m-%d %H:%M:%S")),
                                c_name,
                                c_name,
                                c_phone,
                                float(data.get("subtotal") or 0.0),
                                float(data.get("total_amount") or 0.0),
                                float(data.get("total_amount") or 0.0),
                                data.get("created_at", datetime.now().isoformat())
                            ))
                            new_sale_id = cur.lastrowid
                            for item in items:
                                raw_pid = item.get("product_id") or 0
                                valid_pid = raw_pid if conn.execute("SELECT id FROM products WHERE id = ?", (raw_pid,)).fetchone() else 1
                                cur.execute("""
                                    INSERT INTO sale_items (sale_id, product_id, quantity, unit_price, mrp_price, vat_pct, vat_amount, cost_price)
                                    VALUES (?, ?, ?, ?, ?, 0, 0, 0)
                                """, (
                                    new_sale_id, valid_pid,
                                    int(item.get("quantity") or 1),
                                    float(item.get("unit_price") or 0.0),
                                    float(item.get("mrp_price") or 0.0)
                                ))

                        print(f"[remote_control] [SYNC] Real-time online order #{order_number} synced from Firebase to local SQLite DB.")
                    else:
                        conn.execute(
                            "UPDATE online_orders SET order_status = ?, payment_status = ?, updated_at = ? WHERE order_number = ?",
                            (data.get("order_status", "new"), data.get("payment_status", "pending"), datetime.now().isoformat(), order_number)
                        )
            conn.commit()
        finally:
            conn.close()
    try:
        execute_with_retry(_do)
    except Exception as e:
        print(f"[remote_control] online orders sync failed: {e}")



def _on_users_change(doc_snapshots, changes, read_time):
    """
    Live listener watching `users` collection in Firestore.
    Syncs admin & staff user account credentials and password hashes in real time across local & cloud servers!
    """
    def _do():
        conn = get_connection()
        try:
            for change in changes:
                doc = change.document
                data = doc.to_dict() or {}
                username = doc.id
                if change.type.name in ("ADDED", "MODIFIED"):
                    password_hash = data.get("password_hash")
                    role = data.get("role", "admin")
                    created_at = data.get("created_at", datetime.now().isoformat())
                    if username and password_hash:
                        existing = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
                        if existing:
                            conn.execute("UPDATE users SET password_hash = ?, role = ? WHERE username = ?", (password_hash, role, username))
                        else:
                            conn.execute("INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)", (username, password_hash, role, created_at))
                elif change.type.name == "REMOVED":
                    conn.execute("DELETE FROM users WHERE username = ?", (username,))
            conn.commit()
        finally:
            conn.close()
    try:
        execute_with_retry(_do)
        print(f"[remote_control] [SYNC] Real-time user accounts & passwords synced across servers.")
    except Exception as e:
        print(f"[remote_control] Two-way users sync failed: {e}")


def _on_packages_change(doc_snapshots, changes, read_time):
    """
    Live listener watching `packages` collection in Firestore.
    Syncs combo packages across local SQLite database and remote cloud server in real time!
    """
    def _do():
        conn = get_connection()
        try:
            for change in changes:
                doc = change.document
                data = doc.to_dict() or {}
                try:
                    pkg_id = int(doc.id)
                except Exception:
                    continue
                if change.type.name in ("ADDED", "MODIFIED"):
                    name = data.get("name", "")
                    description = data.get("description", "")
                    image_url = data.get("image_url", "")
                    package_price = float(data.get("package_price") or 0)
                    is_active = int(data.get("is_active", 1))
                    if name and package_price > 0:
                        existing = conn.execute("SELECT id FROM packages WHERE id = ?", (pkg_id,)).fetchone()
                        if existing:
                            conn.execute("""
                                UPDATE packages SET name = ?, description = ?, image_url = ?, package_price = ?, is_active = ?
                                WHERE id = ?
                            """, (name, description, image_url, package_price, is_active, pkg_id))
                        else:
                            conn.execute("""
                                INSERT INTO packages (id, name, description, image_url, package_price, is_active, created_at)
                                VALUES (?, ?, ?, ?, ?, ?, ?)
                            """, (pkg_id, name, description, image_url, package_price, is_active, datetime.now().isoformat()))
                        conn.execute("DELETE FROM package_items WHERE package_id = ?", (pkg_id,))
                        items = data.get("items", [])
                        for item in items:
                            pid = item.get("product_id")
                            qty = item.get("quantity") or 1
                            if pid:
                                conn.execute("""
                                    INSERT INTO package_items (package_id, product_id, quantity)
                                    VALUES (?, ?, ?)
                                """, (pkg_id, int(pid), int(qty)))
                elif change.type.name == "REMOVED":
                    conn.execute("DELETE FROM package_items WHERE package_id = ?", (pkg_id,))
                    conn.execute("DELETE FROM packages WHERE id = ?", (pkg_id,))
            conn.commit()
        finally:
            conn.close()
    try:
        execute_with_retry(_do)
        print(f"[remote_control] [SYNC] Real-time combo packages synced across servers.")
    except Exception as e:
        print(f"[remote_control] Two-way packages sync failed: {e}")


def _on_categories_change(doc_snapshots, changes, read_time):
    """
    Live listener watching `categories` collection in Firestore.
    Syncs category, subcategory, and sub-subcategory updates in real time across servers.
    """
    def _do():
        conn = get_connection()
        try:
            for change in changes:
                doc = change.document
                data = doc.to_dict() or {}
                try:
                    cat_id = int(doc.id)
                except Exception:
                    continue

                if change.type.name in ("ADDED", "MODIFIED"):
                    name = data.get("name", "")
                    parent_id = data.get("parent_id")
                    icon = data.get("icon", "")
                    if name:
                        existing = conn.execute("SELECT id FROM categories WHERE id = ?", (cat_id,)).fetchone()
                        if existing:
                            conn.execute("UPDATE categories SET name = ?, parent_id = ?, icon = ? WHERE id = ?", (name, parent_id, icon, cat_id))
                        else:
                            conn.execute("INSERT INTO categories (id, name, parent_id, icon) VALUES (?, ?, ?, ?)", (cat_id, name, parent_id, icon))

                        if "sub_categories" in data and isinstance(data["sub_categories"], list):
                            subs = data["sub_categories"]
                            current_sub_ids = [s.get("id") for s in subs if isinstance(s, dict) and s.get("id")]
                            if current_sub_ids:
                                placeholders = ','.join(['?'] * len(current_sub_ids))
                                conn.execute(f"DELETE FROM sub_categories WHERE category_id = ? AND id NOT IN ({placeholders})", [cat_id] + current_sub_ids)
                            else:
                                conn.execute("DELETE FROM sub_categories WHERE category_id = ?", (cat_id,))

                            for s in subs:
                                if not isinstance(s, dict):
                                    continue
                                s_id = s.get("id")
                                s_name = s.get("name", "")
                                s_icon = s.get("icon", "")
                                if s_id and s_name:
                                    existing_sub = conn.execute("SELECT id FROM sub_categories WHERE id = ?", (s_id,)).fetchone()
                                    if existing_sub:
                                        conn.execute("UPDATE sub_categories SET category_id = ?, name = ?, icon = ? WHERE id = ?", (cat_id, s_name, s_icon, s_id))
                                    else:
                                        conn.execute("INSERT INTO sub_categories (id, category_id, name, icon) VALUES (?, ?, ?, ?)", (s_id, cat_id, s_name, s_icon))

                                    if "sub_sub_categories" in s and isinstance(s["sub_sub_categories"], list):
                                        subsubs = s["sub_sub_categories"]
                                        current_ssub_ids = [ss.get("id") for ss in subsubs if isinstance(ss, dict) and ss.get("id")]
                                        if current_ssub_ids:
                                            placeholders_ss = ','.join(['?'] * len(current_ssub_ids))
                                            conn.execute(f"DELETE FROM sub_sub_categories WHERE sub_category_id = ? AND id NOT IN ({placeholders_ss})", [s_id] + current_ssub_ids)
                                        else:
                                            conn.execute("DELETE FROM sub_sub_categories WHERE sub_category_id = ?", (s_id,))
                                        for ss in subsubs:
                                            if not isinstance(ss, dict):
                                                continue
                                            ss_id = ss.get("id")
                                            ss_name = ss.get("name", "")
                                            ss_icon = ss.get("icon", "")
                                            if ss_id and ss_name:
                                                existing_ssub = conn.execute("SELECT id FROM sub_sub_categories WHERE id = ?", (ss_id,)).fetchone()
                                                if existing_ssub:
                                                    conn.execute("UPDATE sub_sub_categories SET sub_category_id = ?, name = ?, icon = ? WHERE id = ?", (s_id, ss_name, ss_icon, ss_id))
                                                else:
                                                    conn.execute("INSERT INTO sub_sub_categories (id, sub_category_id, name, icon) VALUES (?, ?, ?, ?)", (ss_id, s_id, ss_name, ss_icon))

                elif change.type.name == "REMOVED":
                    subs = conn.execute("SELECT id FROM sub_categories WHERE category_id = ?", (cat_id,)).fetchall()
                    for sub in subs:
                        conn.execute("DELETE FROM sub_sub_categories WHERE sub_category_id = ?", (sub["id"],))
                    conn.execute("DELETE FROM sub_categories WHERE category_id = ?", (cat_id,))
                    conn.execute("DELETE FROM categories WHERE id = ?", (cat_id,))

            conn.commit()
        finally:
            conn.close()
    try:
        execute_with_retry(_do)
        print(f"[remote_control] [SYNC] Real-time categories synced across servers.")
    except Exception as e:
        print(f"[remote_control] Two-way categories sync failed: {e}")


def _on_brands_change(doc_snapshots, changes, read_time):
    """
    Live listener watching `brands` collection in Firestore.
    Syncs brand updates in real time across servers.
    """
    def _do():
        conn = get_connection()
        try:
            for change in changes:
                doc = change.document
                data = doc.to_dict() or {}
                try:
                    brand_id = int(doc.id)
                except Exception:
                    continue
                if change.type.name in ("ADDED", "MODIFIED"):
                    name = data.get("name", "")
                    logo = data.get("logo", "")
                    if name:
                        existing = conn.execute("SELECT id FROM brands WHERE id = ?", (brand_id,)).fetchone()
                        if existing:
                            conn.execute("UPDATE brands SET name = ?, logo = ? WHERE id = ?", (name, logo, brand_id))
                        else:
                            conn.execute("INSERT INTO brands (id, name, logo) VALUES (?, ?, ?)", (brand_id, name, logo))
                elif change.type.name == "REMOVED":
                    conn.execute("DELETE FROM brands WHERE id = ?", (brand_id,))
            conn.commit()
        finally:
            conn.close()
    try:
        execute_with_retry(_do)
        print(f"[remote_control] [SYNC] Real-time brands synced across servers.")
    except Exception as e:
        print(f"[remote_control] Two-way brands sync failed: {e}")


def _on_shop_settings_change(doc_snapshots, changes, read_time):
    """
    Live listener watching `settings` collection in Firestore.
    Syncs shop settings & policies across local & remote cloud servers.
    """
    def _do():
        conn = get_connection()
        try:
            for change in changes:
                doc = change.document
                data = doc.to_dict() or {}
                key = doc.id
                val = data.get("value", "")
                if change.type.name in ("ADDED", "MODIFIED") and key:
                    conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, val))
                elif change.type.name == "REMOVED" and key:
                    conn.execute("DELETE FROM settings WHERE key = ?", (key,))
            conn.commit()
        finally:
            conn.close()
    try:
        execute_with_retry(_do)
        print(f"[remote_control] [SYNC] Real-time shop settings synced across servers.")
    except Exception as e:
        print(f"[remote_control] Two-way shop settings sync failed: {e}")


def _on_customer_users_change(doc_snapshots, changes, read_time):
    """
    Live listener watching `customer_users` collection in Firestore.
    Syncs newly registered customers and customers created at POS checkout across servers in real time!
    """
    def _do():
        conn = get_connection()
        try:
            for change in changes:
                doc = change.document
                data = doc.to_dict() or {}
                phone = data.get("phone") or doc.id
                if not phone:
                    continue

                if change.type.name in ("ADDED", "MODIFIED"):
                    existing = conn.execute("SELECT id FROM customer_users WHERE phone = ?", (phone,)).fetchone()
                    name = data.get("name", "")
                    email = data.get("email", "")
                    password_hash = data.get("password_hash", "")
                    plain_password = data.get("plain_password", "123456")
                    is_verified = int(data.get("is_verified") or 1)
                    is_blocked = int(data.get("is_blocked") or 0)
                    blocked_until = data.get("blocked_until", "")
                    block_reason = data.get("block_reason", "")
                    created_at = data.get("created_at") or datetime.now().isoformat()

                    if existing:
                        conn.execute("""
                            UPDATE customer_users SET
                                name = COALESCE(NULLIF(?, ''), name),
                                email = COALESCE(NULLIF(?, ''), email),
                                password_hash = COALESCE(NULLIF(?, ''), password_hash),
                                plain_password = COALESCE(NULLIF(?, ''), plain_password),
                                is_verified = ?,
                                is_blocked = ?,
                                blocked_until = ?,
                                block_reason = ?
                            WHERE phone = ?
                        """, (name, email, password_hash, plain_password, is_verified, is_blocked, blocked_until, block_reason, phone))
                    else:
                        conn.execute("""
                            INSERT INTO customer_users (
                                phone, name, email, password_hash, plain_password,
                                is_verified, is_blocked, blocked_until, block_reason, created_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            phone, name or f"Customer {phone[-4:]}", email, password_hash, plain_password,
                            is_verified, is_blocked, blocked_until, block_reason, created_at
                        ))
                    conn.commit()
                elif change.type.name == "REMOVED":
                    conn.execute("DELETE FROM customer_users WHERE phone = ?", (phone,))
                    conn.commit()
        finally:
            conn.close()

    try:
        execute_with_retry(_do)
        print(f"[remote_control] [SYNC] Real-time customer users synced across servers.")
    except Exception as e:
        print(f"[remote_control] Two-way customer users sync failed: {e}")


def _on_sales_change(doc_snapshots, changes, read_time):
    """
    Live listener watching `sales` collection in Firestore.
    Syncs completed sales/checkout invoices from Render Cloud Server or other terminals
    into the local SQLite database in real time!
    """
    def _do():
        conn = get_connection()
        try:
            for change in changes:
                doc = change.document
                data = doc.to_dict() or {}
                doc_id = doc.id
                invoice_number = data.get("invoice_number") or doc_id

                if change.type.name in ("ADDED", "MODIFIED"):
                    # Check if sale already exists in SQLite
                    existing = conn.execute(
                        "SELECT id FROM sales WHERE invoice_number = ? OR (id = ? AND ? > 0)",
                        (invoice_number, data.get("id") or 0, data.get("id") or 0)
                    ).fetchone()

                    if not existing:
                        cur = conn.cursor()
                        # Ensure cashier exists or fallback to first user
                        cashier_id = int(data.get("cashier_id") or 1)
                        chk_user = conn.execute("SELECT id FROM users WHERE id = ?", (cashier_id,)).fetchone()
                        if not chk_user:
                            first_user = conn.execute("SELECT id FROM users LIMIT 1").fetchone()
                            cashier_id = first_user["id"] if first_user else 1

                        customer_name = str(data.get("customer_name") or data.get("customer_id") or "")
                        customer_mobile = str(data.get("customer_mobile") or "")
                        channel = str(data.get("channel") or "Offline")

                        cur.execute("""
                            INSERT INTO sales (
                                invoice_number, invoice_date, cashier_id, customer_id, customer_name, customer_mobile, channel,
                                total_amount, rounded_total, vat_amount, saved_amount,
                                cash_amount, card_amount, change_amount, created_at, is_synced
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                        """, (
                            invoice_number,
                            data.get("invoice_date", ""),
                            cashier_id,
                            customer_name,
                            customer_name,
                            customer_mobile,
                            channel,
                            float(data.get("total_amount") or 0.0),
                            float(data.get("rounded_total") or 0.0),
                            float(data.get("vat_amount") or 0.0),
                            float(data.get("saved_amount") or 0.0),
                            float(data.get("cash_amount") or 0.0),
                            float(data.get("card_amount") or 0.0),
                            float(data.get("change_amount") or 0.0),
                            data.get("created_at") or datetime.now().isoformat(),
                        ))
                        new_sale_id = cur.lastrowid
                        items = data.get("items", [])
                        for it in items:
                            raw_pid = int(it.get("product_id") or 0)
                            chk_p = conn.execute("SELECT id FROM products WHERE id = ?", (raw_pid,)).fetchone()
                            valid_pid = raw_pid if chk_p else 1
                            cur.execute("""
                                INSERT INTO sale_items (
                                    sale_id, product_id, quantity, unit_price, mrp_price,
                                    vat_pct, vat_amount, cost_price, unit_serials
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                new_sale_id,
                                valid_pid,
                                int(it.get("quantity") or 1),
                                float(it.get("unit_price") or 0.0),
                                float(it.get("mrp_price") or 0.0),
                                float(it.get("vat_pct") or 0.0),
                                float(it.get("vat_amount") or 0.0),
                                float(it.get("cost_price") or 0.0),
                                str(it.get("unit_serials") or ""),
                            ))

                        # Auto-create or ensure customer in customer_users table
                        digits = "".join(ch for ch in customer_mobile if ch.isdigit())
                        if digits.startswith("8801") and len(digits) == 13:
                            digits = digits[2:]
                        if digits and len(digits) == 11 and digits.startswith("01"):
                            chk_cust = conn.execute("SELECT id FROM customer_users WHERE phone = ?", (digits,)).fetchone()
                            if not chk_cust:
                                from werkzeug.security import generate_password_hash
                                pass_hash = generate_password_hash("123456")
                                name_to_use = customer_name.strip() if customer_name and customer_name.strip() else f"Customer {digits[-4:]}"
                                cur.execute("""
                                    INSERT INTO customer_users (phone, name, email, password_hash, plain_password, is_verified, created_at)
                                    VALUES (?, ?, '', ?, '123456', 1, ?)
                                """, (digits, name_to_use, pass_hash, datetime.now().isoformat()))

                        conn.commit()
                        print(f"[remote_control] [SYNC] Real-time sale #{invoice_number} synced into local SQLite sales log.")
                elif change.type.name == "REMOVED":
                    conn.execute("DELETE FROM sales WHERE invoice_number = ?", (invoice_number,))
                    conn.commit()
        finally:
            conn.close()

    try:
        execute_with_retry(_do)
    except Exception as e:
        print(f"[remote_control] Two-way sales sync failed: {e}")


def pull_all_from_cloud():
    """Initial startup pull: Reads all categories, brands, products, packages, settings, customer_users, and sales from Cloud Firestore into local SQLite."""
    def _worker():
        try:
            db = _init_firebase()
            if not db:
                return

            # Fetch all data from Firestore FIRST (no lock needed for reads)
            cat_docs   = list(db.collection("categories").stream())
            brand_docs = list(db.collection("brands").stream())
            prod_docs  = list(db.collection("products").stream())
            pkg_docs   = list(db.collection("packages").stream())
            setting_docs = list(db.collection("settings").stream())
            try:
                cust_docs = list(db.collection("customer_users").stream())
            except Exception:
                cust_docs = []
            try:
                sales_docs = list(db.collection("sales").limit(100).stream())
            except Exception:
                sales_docs = []

            # Now write everything in ONE locked transaction
            def _do_write():
                conn = get_connection()
                try:
                    # 1. Pull Categories
                    for doc in cat_docs:
                        data = doc.to_dict() or {}
                        cat_id = data.get("id")
                        name = data.get("name", "")
                        icon = data.get("icon", "")
                        if cat_id and name:
                            conn.execute("INSERT OR REPLACE INTO categories (id, name, icon) VALUES (?, ?, ?)", (cat_id, name, icon))
                            subs = data.get("sub_categories", [])
                            for s in subs:
                                if isinstance(s, dict) and s.get("id") and s.get("name"):
                                    conn.execute("INSERT OR REPLACE INTO sub_categories (id, category_id, name, icon) VALUES (?, ?, ?, ?)", (s["id"], cat_id, s["name"], s.get("icon", "")))
                                    ssubs = s.get("sub_sub_categories", [])
                                    for ss in ssubs:
                                        if isinstance(ss, dict) and ss.get("id") and ss.get("name"):
                                            conn.execute("INSERT OR REPLACE INTO sub_sub_categories (id, sub_category_id, name, icon) VALUES (?, ?, ?, ?)", (ss["id"], s["id"], ss["name"], ss.get("icon", "")))

                    # 2. Pull Brands
                    for doc in brand_docs:
                        data = doc.to_dict() or {}
                        try:
                            brand_id = int(doc.id)
                            name = data.get("name", "")
                            logo = data.get("logo", "")
                            if name:
                                conn.execute("INSERT OR REPLACE INTO brands (id, name, logo) VALUES (?, ?, ?)", (brand_id, name, logo))
                        except Exception:
                            pass

                    # 3. Pull Products
                    for doc in prod_docs:
                        data = doc.to_dict() or {}
                        doc_id = doc.id
                        sku = data.get("sku") or doc_id
                        prod_id = data.get("id")
                        name = data.get("name")
                        if not name:
                            continue
                        brand = data.get("brand", "")
                        unit = data.get("unit", "")
                        category_id = data.get("category_id")
                        sub_category_id = data.get("sub_category_id")
                        sub_sub_category_id = data.get("sub_sub_category_id")
                        cost_price = float(data.get("cost_price") or 0)
                        mrp = float(data.get("mrp") or 0)
                        sell_price = float(data.get("sell_price") or 0)
                        vat_pct = float(data.get("vat_pct") or 0)
                        stock_qty = int(data.get("stock_qty") or 0)
                        low_stock_threshold = int(data.get("low_stock_threshold") or 5)
                        sl_number = int(data.get("sl_number") or 1)
                        description = data.get("description", "")
                        image_url = data.get("image_url", "")
                        is_trending = int(data.get("is_trending") or 0)
                        is_flash_sale = int(data.get("is_flash_sale") or 0)
                        is_offer = int(data.get("is_offer") or 0)
                        is_promotion = int(data.get("is_promotion") or 0)
                        offer_title = data.get("offer_title", "")
                        offer_type = data.get("offer_type", "")
                        offer_value = data.get("offer_value", "")
                        offer_base = data.get("offer_base", "mrp")
                        expiry_date = data.get("expiry_date", "")
                        existing = None
                        if sku:
                            existing = conn.execute("SELECT id FROM products WHERE sku = ?", (sku,)).fetchone()
                        if not existing and prod_id:
                            existing = conn.execute("SELECT id FROM products WHERE id = ?", (prod_id,)).fetchone()
                        if existing:
                            conn.execute("""
                                UPDATE products SET
                                    sku=?, name=?, brand=?, unit=?, category_id=?, sub_category_id=?, sub_sub_category_id=?,
                                    cost_price=?, mrp=?, sell_price=?, vat_pct=?, stock_qty=?, low_stock_threshold=?,
                                    sl_number=?, description=?, image_url=?, is_trending=?, is_flash_sale=?,
                                    is_offer=?, is_promotion=?, offer_title=?, offer_type=?, offer_value=?, offer_base=?, expiry_date=?
                                WHERE id=?
                            """, (
                                sku, name, brand, unit, category_id, sub_category_id, sub_sub_category_id,
                                cost_price, mrp, sell_price, vat_pct, stock_qty, low_stock_threshold,
                                sl_number, description, image_url, is_trending, is_flash_sale,
                                is_offer, is_promotion, offer_title, offer_type, offer_value, offer_base, expiry_date,
                                existing["id"]
                            ))
                        else:
                            conn.execute("""
                                INSERT INTO products (
                                    sku, name, brand, unit, category_id, sub_category_id, sub_sub_category_id,
                                    cost_price, mrp, sell_price, vat_pct, stock_qty, low_stock_threshold,
                                    sl_number, description, image_url, is_trending, is_flash_sale,
                                    is_offer, is_promotion, offer_title, offer_type, offer_value, offer_base, expiry_date
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                sku, name, brand, unit, category_id, sub_category_id, sub_sub_category_id,
                                cost_price, mrp, sell_price, vat_pct, stock_qty, low_stock_threshold,
                                sl_number, description, image_url, is_trending, is_flash_sale,
                                is_offer, is_promotion, offer_title, offer_type, offer_value, offer_base, expiry_date
                            ))

                    # 4. Pull Packages
                    for doc in pkg_docs:
                        data = doc.to_dict() or {}
                        pkg_id = data.get("id")
                        name = data.get("name", "")
                        title = data.get("package_title") or name
                        price = float(data.get("price") or data.get("package_price") or 0)
                        desc = data.get("description", "")
                        img = data.get("image_url", "")
                        if pkg_id and title:
                            conn.execute("INSERT OR REPLACE INTO packages (id, package_title, package_price, description, image_url, is_active, created_at) VALUES (?, ?, ?, ?, ?, 1, ?)", (pkg_id, title, price, desc, img, datetime.now().isoformat()))

                    # 5. Pull Settings
                    for doc in setting_docs:
                        data = doc.to_dict() or {}
                        key = doc.id
                        val = data.get("value", "")
                        if key:
                            conn.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?, ?)", (key, val))

                    # 6. Pull Customer Users
                    for doc in cust_docs:
                        data = doc.to_dict() or {}
                        phone = data.get("phone") or doc.id
                        if phone:
                            existing = conn.execute("SELECT id FROM customer_users WHERE phone = ?", (phone,)).fetchone()
                            name = data.get("name", "")
                            email = data.get("email", "")
                            password_hash = data.get("password_hash", "")
                            plain_password = data.get("plain_password", "123456")
                            is_verified = int(data.get("is_verified") or 1)
                            is_blocked = int(data.get("is_blocked") or 0)
                            blocked_until = data.get("blocked_until", "")
                            block_reason = data.get("block_reason", "")
                            created_at = data.get("created_at") or datetime.now().isoformat()
                            if existing:
                                conn.execute("""
                                    UPDATE customer_users SET
                                        name = COALESCE(NULLIF(?, ''), name),
                                        email = COALESCE(NULLIF(?, ''), email),
                                        password_hash = COALESCE(NULLIF(?, ''), password_hash),
                                        plain_password = COALESCE(NULLIF(?, ''), plain_password),
                                        is_verified = ?,
                                        is_blocked = ?,
                                        blocked_until = ?,
                                        block_reason = ?
                                    WHERE phone = ?
                                """, (name, email, password_hash, plain_password, is_verified, is_blocked, blocked_until, block_reason, phone))
                            else:
                                conn.execute("""
                                    INSERT INTO customer_users (
                                        phone, name, email, password_hash, plain_password,
                                        is_verified, is_blocked, blocked_until, block_reason, created_at
                                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                                """, (
                                    phone, name or f"Customer {phone[-4:]}", email, password_hash, plain_password,
                                    is_verified, is_blocked, blocked_until, block_reason, created_at
                                ))

                    # 7. Pull Sales
                    for doc in sales_docs:
                        data = doc.to_dict() or {}
                        invoice_number = data.get("invoice_number") or doc.id
                        existing = conn.execute(
                            "SELECT id FROM sales WHERE invoice_number = ? OR (id = ? AND ? > 0)",
                            (invoice_number, data.get("id") or 0, data.get("id") or 0)
                        ).fetchone()
                        if not existing:
                            cashier_id = int(data.get("cashier_id") or 1)
                            chk_user = conn.execute("SELECT id FROM users WHERE id = ?", (cashier_id,)).fetchone()
                            if not chk_user:
                                first_user = conn.execute("SELECT id FROM users LIMIT 1").fetchone()
                                cashier_id = first_user["id"] if first_user else 1
                            customer_name = str(data.get("customer_name") or data.get("customer_id") or "")
                            customer_mobile = str(data.get("customer_mobile") or "")
                            channel = str(data.get("channel") or "Offline")
                            cur = conn.cursor()
                            cur.execute("""
                                INSERT INTO sales (
                                    invoice_number, invoice_date, cashier_id, customer_id, customer_name, customer_mobile, channel,
                                    total_amount, rounded_total, vat_amount, saved_amount,
                                    cash_amount, card_amount, change_amount, created_at, is_synced
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1)
                            """, (
                                invoice_number,
                                data.get("invoice_date", ""),
                                cashier_id,
                                customer_name,
                                customer_name,
                                customer_mobile,
                                channel,
                                float(data.get("total_amount") or 0.0),
                                float(data.get("rounded_total") or 0.0),
                                float(data.get("vat_amount") or 0.0),
                                float(data.get("saved_amount") or 0.0),
                                float(data.get("cash_amount") or 0.0),
                                float(data.get("card_amount") or 0.0),
                                float(data.get("change_amount") or 0.0),
                                data.get("created_at") or datetime.now().isoformat(),
                            ))
                            new_sale_id = cur.lastrowid
                            for it in (data.get("items") or []):
                                raw_pid = int(it.get("product_id") or 0)
                                chk_p = conn.execute("SELECT id FROM products WHERE id = ?", (raw_pid,)).fetchone()
                                valid_pid = raw_pid if chk_p else 1
                                cur.execute("""
                                    INSERT INTO sale_items (
                                        sale_id, product_id, quantity, unit_price, mrp_price,
                                        vat_pct, vat_amount, cost_price, unit_serials
                                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                                """, (
                                    new_sale_id,
                                    valid_pid,
                                    int(it.get("quantity") or 1),
                                    float(it.get("unit_price") or 0.0),
                                    float(it.get("mrp_price") or 0.0),
                                    float(it.get("vat_pct") or 0.0),
                                    float(it.get("vat_amount") or 0.0),
                                    float(it.get("cost_price") or 0.0),
                                    str(it.get("unit_serials") or ""),
                                ))

                            # Ensure customer is recorded
                            digits = "".join(ch for ch in customer_mobile if ch.isdigit())
                            if digits.startswith("8801") and len(digits) == 13:
                                digits = digits[2:]
                            if digits and len(digits) == 11 and digits.startswith("01"):
                                chk_cust = conn.execute("SELECT id FROM customer_users WHERE phone = ?", (digits,)).fetchone()
                                if not chk_cust:
                                    from werkzeug.security import generate_password_hash
                                    pass_hash = generate_password_hash("123456")
                                    name_to_use = customer_name.strip() if customer_name and customer_name.strip() else f"Customer {digits[-4:]}"
                                    cur.execute("""
                                        INSERT INTO customer_users (phone, name, email, password_hash, plain_password, is_verified, created_at)
                                        VALUES (?, ?, '', ?, '123456', 1, ?)
                                    """, (digits, name_to_use, pass_hash, datetime.now().isoformat()))

                    conn.commit()
                    print("[remote_control] [OK] Initial cloud pull complete: Products, categories, brands, packages, settings, customers & sales synced to local SQLite DB.")
                finally:
                    conn.close()

            execute_with_retry(_do_write)
        except Exception as e:
            print(f"[remote_control] pull_all_from_cloud error: {e}")

    threading.Thread(target=_worker, daemon=True).start()



def start():
    """Starts Firebase listeners and periodic backup thread."""
    db = _init_firebase()
    if not db:
        print("[remote_control] [ALERT] Firebase not initialized. (Add firebase_credentials.json to enable live sync)")
        return

    try:
        _ensure_remote_doc(db)

        def _safety_net_loop():
            while True:
                push_full_backup()
                time.sleep(300)

        # Initial pull from Cloud Firestore on startup
        pull_all_from_cloud()

        # Live listeners (Firebase Cloud -> All Servers & Apps)
        db.collection("remote_control").document("settings").on_snapshot(_on_settings_change)
        db.collection("products").on_snapshot(_on_products_change)
        db.collection("sales").on_snapshot(_on_sales_change)
        db.collection("customer_users").on_snapshot(_on_customer_users_change)
        db.collection("online_orders").on_snapshot(_on_online_orders_change)
        db.collection("users").on_snapshot(_on_users_change)
        db.collection("packages").on_snapshot(_on_packages_change)
        db.collection("categories").on_snapshot(_on_categories_change)
        db.collection("brands").on_snapshot(_on_brands_change)
        db.collection("settings").on_snapshot(_on_shop_settings_change)

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
