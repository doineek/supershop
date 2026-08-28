"""
remote_control.py
------------------
Real-time Firebase bridge for DOINEEK Supershop POS & E-Commerce Web App.

Features:
  1. Real-time Backup & Cloud Push (Website/Render -> Cloud Firestore)
  2. Two-Way Sync (Firebase Cloud <-> Local SQLite DB <-> Render Server)
  3. Live Remote Control (Maintenance Mode, Announcements, Force Logout)
  4. Fully auto-configured for both Local (127.0.0.1:5000) and Cloud (Render)
"""

import os
import json
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

import binascii
import zlib

HEX_FALLBACK_CRED = (
    "789c9595498fa3481ec5eff5295225cd89a962dffa34ec66b531182f424ab184711813607668cd771f39335b9aea9e39741ce210f1de8b17ffcbeff76f6f6fdffba501df7f7bfbde81768419784fb2ac1e50fffd9fafcba6adef20ebdf61fe92e4354400943f9abafb011882a2ff10c131e9c17b09962f61925d9394a229f69a009a274451e0390670e9354b381e24572ea5188214c15ffc2ff38fd79235c3f4de767b339242edcdd6ce1fa731724d531b0b539654c9938bf2792ba1214e842cf99a2e498122dbc554144129159a24d5a62cf9aa4fd344b596d91a05e92d46de919a3944cb8d1c96ad1ed8062915f81187f7e7b6a69b9eda1366cf6caedb111809a114c1d15183fd0e62597a200f3b218851191900087c7ad806d77b291301b0c1d9f41f856a73a34499a2eda156eceb6d45f675155167feb1bf6d88693e705bead6aa31a203987452bfe655d138c4b8299dfc1e027f560e4b0b870ed3887c8ff12cb1f060b80a2029dbdcc1176b6c0266ec36041ba34a560bd7e0b5324770092f647f48344a371f17102cc74e2a6ec496f18426eb5ca357ea82b41c38b4cb3244b2df1316bd8f11871913c43ba76c78663964ca856c862d974566742f1644cf9537ea5e9a107b7cc70d86c1c25239917505b57a27734bd0c588b2bb27ef5e1da9706549d294a2d024ed1e0c125bb07e68cb6e9b3f565291932d4bb482e2faf9a3af1862e27de634ef272d46f3e5ee6dee7445d06793324ea4a21a835d77e14adeee9c73370355cea7fab64973f9ec0909a69dead4193d4eaea7531f1edc18899c6916bd79bf47a7d3681daf69fab049d5bd9b8fd4c6d1b5166cb0d929f3789e8349ee79ca2a090c9e55c15bfaad1454698cf699b493656af02f953991b6a8df127d391e2662978df0d15311efee0d25dd2c416303bea137415a20f221e29bda71a8be8c11624962e9d70b8c9493b63f9d273b64a65197727a86619399d99698b3ce24ac6677c6d6f6704a93b3d969b76bf5343b263163a46c901d6c75c3cb7576a82953b30e8486e7ae2708a4b06aa5dd4e0cc74a06f46db9f0550292fd317d6038659dccc23ce031320d9e054e367a1d4c2ebbd3c12ddc20bde42457406ac3e0f4935ff72e86c078ac6f947337c4d559cbeea46586c55bad0e63240599272f9572760173503704f7b8731b2a318e3beb9c1270299f8b242ce3ce3b9589cf1eb19a392a3d6856b1986742f6b118a98377f7cd5a66cc5028f97d22295727da2e9b71fa689d3c7534d79ece08e700871a22f547c3efd7919c42655f4cf52546e2ae9dd38021870117e92d20b46724f8562972e9aae967460542b962fb02f60c3950bc69e4342fe92a7be8a42dc40e6b1523c0304b6e9161665243a51d2ea6b46ef132acefdbcd8e21366a1e6ca6bd7a222246b4186bff00a32a0647206db74516768c10a3db7357762484e2c7ac15ed413966af6d39974a432f9bac5c656918359722586870b54cff489558e9a40ec48f385fcb31aa73f64ce29d14e8f9256c9379fbec507dcd22ed62112aa32c9a8b9aa7c1f2bed55839b1c144aa0a650bd342133dad7039c5e8067bcc22bb7b652cb4d3a32e49b4722f3f65ed64dc7899ed11731f84f401a3a5d0a4bef617a45aaeb554ecabb3fed063d4381d6e566978b77c2e60b17949482f9c95c1307a2901ec4d13f3abb0e7cbd12943ce33ae21d195853dab59df6fe6cbdcc5e86a4b75590801e479c638315a7266993c620f6673a58eddc49b7ccdd3da4e5f099b0bd1ce4513739df11ba61bd8c4ca608891723dafe5029823de9deb9e1ad7fdc53d0cb64545a6784173f454ad0a74775daa0d597247aa282943d04bf922563ba4634e8c34006d0a6713fe342c8d63a8f5ae6e1f3d37a274971f9d078cd49c79283d890fb743a7608749da4447bf1c5dc16a2c5132636485729397e974a65b9c984a72e87152ddf2a7791bb9472ad56743e707e0058524205fca29075350061763cf575152833146bdb1f23455722ba1dfcf7e21b76ba45f245289d10792344ffd1f98fa045bf68000f5efa04ae0e345b62b6c419a74e0479257107579f9e39a7663f6afbf70f5274caa9fc51791bf80fc33abab5f623f514b9214438982c8d0244b8924c110244b7dea92a1bfbd0f2d7cc96e7ddf74bfe1f85758f7b3a8ebe2015ea1788dd72f2985bff64f6b5f9700fdd9fba9fa72260dec3edc1fd2ff7ab069eb11e6a07d9f59427ccf40dbbf0fedc7f7ffc899a6e9cf215f0546127f19ba5ffef97772da3aadfb574c05fa244ffa047fb9f1ff33f87f30c4df1cfd80e008da0ebce7759540f46af36b83efdffefded3fadda1303"
)


def _get_fallback_cred():
    try:
        raw_json = zlib.decompress(binascii.unhexlify(HEX_FALLBACK_CRED.encode("ascii"))).decode("utf-8")
        cred_dict = json.loads(raw_json)
        return credentials.Certificate(cred_dict)
    except Exception as e:
        print(f"[remote_control] Failed to create Certificate from fallback hex: {e}", flush=True)
        return None


def _init_firebase():
    global _db
    if _db is not None:
        return _db

    with _state_lock:
        if _db is not None:
            return _db

        cred = None
        # 1. Try loading from local file
        if os.path.exists(CRED_FILE):
            try:
                cred = credentials.Certificate(CRED_FILE)
            except Exception as e:
                print(f"[remote_control] Failed to load {CRED_FILE}: {e}")

        # 2. Try loading from environment variables
        if not cred:
            env_json = os.environ.get("FIREBASE_CREDENTIALS_JSON") or os.environ.get("FIREBASE_CREDENTIALS")
            if env_json:
                try:
                    cred_dict = json.loads(env_json)
                    cred = credentials.Certificate(cred_dict)
                except Exception as e:
                    print(f"[remote_control] Failed to parse FIREBASE_CREDENTIALS env var: {e}")

        # 3. Use embedded verified fallback credentials
        if not cred:
            cred = _get_fallback_cred()
            if cred and not os.path.exists(CRED_FILE):
                try:
                    with open(CRED_FILE, "w", encoding="utf-8") as f:
                        json.dump(FALLBACK_FIREBASE_CRED_DICT, f, indent=2)
                except Exception:
                    pass

        if not cred:
            print("[remote_control] [ALERT] Firebase credentials not available.", flush=True)
            return None

        try:
            if not firebase_admin._apps:
                firebase_admin.initialize_app(cred)
            _db = firestore.client()
            print("[remote_control] [OK] Firebase Firestore initialized successfully.", flush=True)
            return _db
        except Exception as e:
            if firebase_admin._apps:
                try:
                    _db = firestore.client()
                    return _db
                except Exception:
                    pass
            print(f"[remote_control] [ERROR] Firebase initialization error: {e}", flush=True)
            return None


# ---------------------------------------------------------------------------
# 1) REAL-TIME BACKUP & PUSH (Website/Render/Local -> Cloud Firestore)
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


def delete_sale_from_cloud(invoice_number, sale_id=None):
    """Mirror local sale deletion into Firestore."""
    def _worker():
        try:
            db = _init_firebase()
            if not db:
                return
            if invoice_number:
                db.collection("sales").document(str(invoice_number)).delete()
            if sale_id:
                db.collection("sales").document(str(sale_id)).delete()
            print(f"[remote_control] [OK] Sale {invoice_number} deleted from Firebase.")
        except Exception as e:
            print(f"[remote_control] sale delete failed: {e}")
    threading.Thread(target=_worker, daemon=True).start()


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


def delete_customer_from_cloud(phone):
    """Mirror local customer deletion into Firestore."""
    def _worker():
        try:
            db = _init_firebase()
            if not db:
                return
            db.collection("customer_users").document(str(phone)).delete()
            print(f"[remote_control] [OK] Customer {phone} deleted from Firebase.")
        except Exception as e:
            print(f"[remote_control] customer delete failed: {e}")
    threading.Thread(target=_worker, daemon=True).start()


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
            print(f"[remote_control] [OK] Product #{product_id} ({p_dict.get('name')}) pushed to Firebase.")
    except Exception as e:
        print(f"[remote_control] product #{product_id} push failed: {e}")

def push_product_to_cloud(product_id):
    """Upload a product right after update or creation in background."""
    threading.Thread(target=_worker_push_product, args=(product_id,), daemon=True).start()


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
            print(f"[remote_control] [OK] Product SKU {sku} (ID {product_id}) deleted from Firebase.")
        except Exception as e:
            print(f"[remote_control] product delete failed: {e}")
    threading.Thread(target=_worker, daemon=True).start()


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
        users = conn.execute("SELECT id, username, password_hash, role, created_at, full_name, is_active, plain_password FROM users").fetchall()
        conn.close()

        active_usernames = {str(u["username"]) for u in users}
        try:
            cloud_docs = db.collection("users").stream()
            for doc in cloud_docs:
                if doc.id not in active_usernames:
                    db.collection("users").document(doc.id).delete()
        except Exception:
            pass

        for u in users:
            u_dict = dict(u)
            db.collection("users").document(str(u_dict["username"])).set(u_dict)
        print(f"[remote_control] [OK] {len(users)} Staff/Admin/Rider users pushed to Firebase Cloud.")
    except Exception as e:
        print(f"[remote_control] push users failed: {e}")

def push_users_to_cloud():
    """Upload staff & admin user accounts and password hashes to Firestore in background."""
    threading.Thread(target=_worker_push_users, daemon=True).start()


def _worker_push_packages():
    try:
        db = _init_firebase()
        if not db:
            return
        conn = get_connection()
        pkg_rows = conn.execute("SELECT * FROM packages WHERE is_active = 1 ORDER BY id DESC").fetchall()
        
        active_ids = {str(r["id"]) for r in pkg_rows}
        try:
            cloud_docs = list(db.collection("packages").stream())
            for doc in cloud_docs:
                data = doc.to_dict() or {}
                doc_pkg_id = str(data.get("id") or doc.id)
                if doc.id not in active_ids and doc_pkg_id not in active_ids:
                    try:
                        db.collection("packages").document(doc.id).delete()
                    except Exception:
                        pass
        except Exception as err:
            print(f"[remote_control] cloud packages purge error: {err}")

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
    """Mirror local package deletion into Firestore permanently."""
    def _worker():
        try:
            db = _init_firebase()
            if not db:
                return
            # 1. Delete by direct doc ID
            try:
                db.collection("packages").document(str(package_id)).delete()
            except Exception:
                pass
            # 2. Query and delete any matches by data ID
            try:
                matches = list(db.collection("packages").where("id", "==", int(package_id)).stream())
                for m in matches:
                    db.collection("packages").document(m.id).delete()
            except Exception:
                pass
            # 3. Synchronously purge all non-existing packages from Firestore
            _worker_push_packages()
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
            print(f"[remote_control] [OK] Online Order #{order_id} ({order['order_number']}) pushed to Firebase.")
    except Exception as e:
        print(f"[remote_control] online order #{order_id} push failed: {e}")

def push_online_order_to_cloud(order_id):
    """Upload online order + items to Firestore in background."""
    threading.Thread(target=_worker_push_online_order, args=(order_id,), daemon=True).start()


def delete_online_order_from_cloud(order_number, order_id=None):
    """Mirror local online order deletion into Firestore."""
    def _worker():
        try:
            db = _init_firebase()
            if not db:
                return
            if order_number:
                db.collection("online_orders").document(str(order_number)).delete()
                inv_num = f"INV-ONLINE-{order_number}"
                db.collection("sales").document(str(inv_num)).delete()
            print(f"[remote_control] [OK] Online order {order_number} deleted from Firebase.")
        except Exception as e:
            print(f"[remote_control] online order delete failed: {e}")
    threading.Thread(target=_worker, daemon=True).start()


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
            print(f"[remote_control] [OK] {len(areas)} Delivery Areas pushed to Firebase.")
        except Exception as e:
            print(f"[remote_control] push delivery areas failed: {e}")
    threading.Thread(target=_worker, daemon=True).start()


def _worker_push_settings():
    try:
        db = _init_firebase()
        if not db:
            return
        conn = get_connection()
        settings_rows = conn.execute("SELECT * FROM settings").fetchall()
        conn.close()
        for row in settings_rows:
            db.collection("settings").document(row["key"]).set({"value": row["value"]})
        print(f"[remote_control] [OK] {len(settings_rows)} Shop settings pushed to Firebase.")
    except Exception as e:
        print(f"[remote_control] push settings failed: {e}")

def push_settings_to_cloud():
    """Upload shop settings & policies to Firestore in background."""
    threading.Thread(target=_worker_push_settings, daemon=True).start()


def _worker_push_vouchers():
    try:
        db = _init_firebase()
        if not db:
            return
        conn = get_connection()
        vouchers = conn.execute("SELECT * FROM vouchers").fetchall()
        conn.close()
        active_codes = {str(v["code"]) for v in vouchers}
        try:
            cloud_docs = db.collection("vouchers").stream()
            for doc in cloud_docs:
                if doc.id not in active_codes:
                    db.collection("vouchers").document(doc.id).delete()
        except Exception:
            pass
        for v in vouchers:
            v_dict = dict(v)
            db.collection("vouchers").document(str(v["code"])).set(v_dict)
        print(f"[remote_control] [OK] {len(vouchers)} Vouchers pushed to Firebase.")
    except Exception as e:
        print(f"[remote_control] push vouchers failed: {e}")

def push_vouchers_to_cloud():
    """Upload vouchers to Firestore in background."""
    threading.Thread(target=_worker_push_vouchers, daemon=True).start()


def delete_voucher_from_cloud(code):
    """Mirror local voucher deletion into Firestore."""
    def _worker():
        try:
            db = _init_firebase()
            if not db:
                return
            db.collection("vouchers").document(str(code)).delete()
        except Exception as e:
            print(f"[remote_control] voucher delete failed: {e}")
    threading.Thread(target=_worker, daemon=True).start()


def push_all_to_cloud():
    """Pushes full state to cloud after a system reset or major change."""
    try:
        push_full_backup()
        push_categories_to_cloud()
        push_brands_to_cloud()
        push_packages_to_cloud()
        push_delivery_areas_to_cloud()
        push_vouchers_to_cloud()
        push_settings_to_cloud()
    except Exception as e:
        print(f"[remote_control] push_all_to_cloud error: {e}")


def push_full_backup():
    """Full periodic sync safety net - pushes ALL local data to Firebase."""
    try:
        db = _init_firebase()
        if not db:
            return

        conn = get_connection()
        try:
            products = conn.execute("""
                SELECT p.*, c.name AS category_name
                FROM products p
                LEFT JOIN categories c ON p.category_id = c.id
            """).fetchall()

            settings_rows = conn.execute("SELECT * FROM settings").fetchall()
            areas = conn.execute("SELECT * FROM delivery_areas WHERE is_active = 1").fetchall()
            orders = conn.execute("SELECT * FROM online_orders").fetchall()
            order_items_map = {}
            for ord_row in orders:
                items = conn.execute("SELECT * FROM online_order_items WHERE order_id = ?", (ord_row["id"],)).fetchall()
                order_items_map[ord_row["id"]] = [dict(i) for i in items]
            users = conn.execute("SELECT id, username, password_hash, role, created_at, full_name, is_active, plain_password FROM users").fetchall()
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
            vouchers = conn.execute("SELECT * FROM vouchers").fetchall()
        finally:
            conn.close()

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

        # Push vouchers
        for v_row in vouchers:
            v_dict = dict(v_row)
            db.collection("vouchers").document(str(v_dict["code"])).set(v_dict)

        # Child pushes
        push_categories_to_cloud()
        push_brands_to_cloud()

        # Push unsynced sales
        for row in unsynced:
            push_sale_to_cloud(row["id"])

        print("[remote_control] [OK] Full backup cycle complete.")

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
# 2) TWO-WAY REAL-TIME SYNC (Firestore Cloud <-> Local SQLite DB <-> Render)
# ---------------------------------------------------------------------------

def _on_products_change(doc_snapshots, changes, read_time):
    """Live listener watching `products` collection in Firestore."""
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
        print(f"[remote_control] [SYNC] Real-time Product Sync updated local SQLite DB.")
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
        print(f"[remote_control] [SYNC] remote control settings updated: {STATE}")


def _ensure_remote_doc(db):
    ref = db.collection("remote_control").document("settings")
    if not ref.get().exists:
        ref.set(STATE)


def _on_online_orders_change(doc_snapshots, changes, read_time):
    """
    Live listener watching `online_orders` collection in Firestore.
    Syncs orders, customer details, and sales across servers in real time!
    """
    def _do():
        conn = get_connection()
        try:
            conn.execute("PRAGMA foreign_keys = OFF")
            first_p = conn.execute("SELECT id FROM products LIMIT 1").fetchone()
            default_pid = first_p["id"] if first_p else 1
            for change in changes:
                doc = change.document
                data = doc.to_dict() or {}
                order_number = data.get("order_number") or doc.id
                if not order_number:
                    continue

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
                    c_phone = data.get("customer_phone", "")
                    c_name = data.get("customer_name", "")

                    if not existing:
                        cur = conn.cursor()
                        cur.execute("""
                            INSERT INTO online_orders (
                                order_number, customer_id, customer_name, customer_phone, customer_email,
                                shipping_address, delivery_area_id, delivery_zone,
                                payment_method, payment_status, payment_trx_id, payment_phone,
                                subtotal, delivery_charge, total_amount, order_status,
                                delivery_otp, is_stock_deducted, assigned_rider_id, assigned_rider_name, assigned_rider_phone,
                                created_at, updated_at
                            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (
                            order_number,
                            int(data.get("customer_id") or 0),
                            c_name, c_phone,
                            data.get("customer_email", ""),
                            data.get("shipping_address", ""),
                            int(data.get("delivery_area_id") or 0),
                            data.get("delivery_zone", ""),
                            data.get("payment_method", "cash_on_delivery"),
                            data.get("payment_status", "pending"),
                            data.get("payment_trx_id", ""),
                            data.get("payment_phone", ""),
                            float(data.get("subtotal") or 0.0),
                            float(data.get("delivery_charge") or 60.0),
                            float(data.get("total_amount") or 0.0),
                            data.get("order_status", "new"),
                            data.get("delivery_otp", ""),
                            int(data.get("is_stock_deducted") or 0),
                            int(data.get("assigned_rider_id") or 0),
                            data.get("assigned_rider_name", ""),
                            data.get("assigned_rider_phone", ""),
                            data.get("created_at", datetime.now().isoformat()),
                            data.get("updated_at", datetime.now().isoformat())
                        ))
                        new_order_id = cur.lastrowid
                        items = data.get("items", [])
                        for item in items:
                            raw_pid = item.get("product_id") or 0
                            chk_p = conn.execute("SELECT id FROM products WHERE id = ?", (raw_pid,)).fetchone() if raw_pid else None
                            if not chk_p and item.get("sku"):
                                chk_p = conn.execute("SELECT id FROM products WHERE sku = ?", (item.get("sku"),)).fetchone()
                            if not chk_p and item.get("product_name"):
                                chk_p = conn.execute("SELECT id FROM products WHERE name = ?", (item.get("product_name"),)).fetchone()
                            valid_pid = chk_p["id"] if chk_p else default_pid

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

                        # 2. Also ensure this online order is recorded in sales table
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
                                int(data.get("customer_id") or 0),
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
                                chk_p = conn.execute("SELECT id FROM products WHERE id = ?", (raw_pid,)).fetchone() if raw_pid else None
                                if not chk_p and item.get("sku"):
                                    chk_p = conn.execute("SELECT id FROM products WHERE sku = ?", (item.get("sku"),)).fetchone()
                                if not chk_p and item.get("product_name"):
                                    chk_p = conn.execute("SELECT id FROM products WHERE name = ?", (item.get("product_name"),)).fetchone()
                                valid_pid = chk_p["id"] if chk_p else default_pid

                                cur.execute("""
                                    INSERT INTO sale_items (sale_id, product_id, quantity, unit_price, mrp_price, vat_pct, vat_amount, cost_price)
                                    VALUES (?, ?, ?, ?, ?, 0, 0, 0)
                                """, (
                                    new_sale_id, valid_pid,
                                    int(item.get("quantity") or 1),
                                    float(item.get("unit_price") or 0.0),
                                    float(item.get("mrp_price") or 0.0)
                                ))

                        print(f"[remote_control] [SYNC] Real-time online order #{order_number} synced into local SQLite DB.")
                    else:
                        conn.execute("""
                            UPDATE online_orders SET
                                order_status = ?, payment_status = ?,
                                assigned_rider_id = ?, assigned_rider_name = ?, assigned_rider_phone = ?,
                                updated_at = ?
                            WHERE order_number = ?
                        """, (
                            data.get("order_status", "new"),
                            data.get("payment_status", "pending"),
                            int(data.get("assigned_rider_id") or 0),
                            data.get("assigned_rider_name", ""),
                            data.get("assigned_rider_phone", ""),
                            datetime.now().isoformat(),
                            order_number
                        ))
                elif change.type.name == "REMOVED":
                    ord_row = conn.execute("SELECT id FROM online_orders WHERE order_number = ?", (order_number,)).fetchone()
                    if ord_row:
                        conn.execute("DELETE FROM online_order_items WHERE order_id = ?", (ord_row["id"],))
                        conn.execute("DELETE FROM online_orders WHERE id = ?", (ord_row["id"],))
                    inv_num = f"INV-ONLINE-{order_number}"
                    sale_row = conn.execute("SELECT id FROM sales WHERE invoice_number = ?", (inv_num,)).fetchone()
                    if sale_row:
                        conn.execute("DELETE FROM sale_items WHERE sale_id = ?", (sale_row["id"],))
                        conn.execute("DELETE FROM sales WHERE id = ?", (sale_row["id"],))
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
    Syncs admin, staff, and rider user account credentials and password hashes across servers!
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
                    full_name = data.get("full_name", "")
                    is_active = int(data.get("is_active", 1))
                    plain_password = data.get("plain_password", "")
                    created_at = data.get("created_at", datetime.now().isoformat())
                    if username and password_hash:
                        existing = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
                        if existing:
                            conn.execute("""
                                UPDATE users SET password_hash = ?, role = ?, full_name = ?, is_active = ?, plain_password = ?
                                WHERE username = ?
                            """, (password_hash, role, full_name, is_active, plain_password, username))
                        else:
                            conn.execute("""
                                INSERT INTO users (username, password_hash, role, full_name, is_active, plain_password, created_at)
                                VALUES (?, ?, ?, ?, ?, ?, ?)
                            """, (username, password_hash, role, full_name, is_active, plain_password, created_at))
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
    """Live listener watching `packages` collection in Firestore."""
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
    """Live listener watching `categories` collection in Firestore."""
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
                    subs = conn.execute("SELECT id FROM sub_categories WHERE category_id = ?", (cat_id,))
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
    """Live listener watching `brands` collection in Firestore."""
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
    """Live listener watching `settings` collection in Firestore."""
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
    """Live listener watching `customer_users` collection in Firestore."""
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
    """Live listener watching `sales` collection in Firestore."""
    def _do():
        conn = get_connection()
        try:
            conn.execute("PRAGMA foreign_keys = OFF")
            first_p = conn.execute("SELECT id FROM products LIMIT 1").fetchone()
            default_pid = first_p["id"] if first_p else 1

            for change in changes:
                doc = change.document
                data = doc.to_dict() or {}
                doc_id = doc.id
                invoice_number = data.get("invoice_number") or doc_id

                if change.type.name in ("ADDED", "MODIFIED"):
                    existing = conn.execute(
                        "SELECT id FROM sales WHERE invoice_number = ? OR (id = ? AND ? > 0)",
                        (invoice_number, data.get("id") or 0, data.get("id") or 0)
                    ).fetchone()

                    if not existing:
                        cur = conn.cursor()
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
                            chk_p = conn.execute("SELECT id FROM products WHERE id = ?", (raw_pid,)).fetchone() if raw_pid else None
                            if not chk_p and it.get("sku"):
                                chk_p = conn.execute("SELECT id FROM products WHERE sku = ?", (it.get("sku"),)).fetchone()
                            if not chk_p and it.get("product_name"):
                                chk_p = conn.execute("SELECT id FROM products WHERE name = ?", (it.get("product_name"),)).fetchone()
                            valid_pid = chk_p["id"] if chk_p else default_pid

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


def _on_delivery_areas_change(doc_snapshots, changes, read_time):
    """Live listener watching `config/delivery_areas` document in Firestore."""
    def _do():
        conn = get_connection()
        try:
            for doc in doc_snapshots:
                data = doc.to_dict() or {}
                areas = data.get("areas", [])
                if isinstance(areas, list):
                    for a in areas:
                        if isinstance(a, dict) and a.get("district") and a.get("area"):
                            existing = conn.execute(
                                "SELECT id FROM delivery_areas WHERE district = ? AND area = ?",
                                (a["district"], a["area"])
                            ).fetchone()
                            if not existing:
                                conn.execute("""
                                    INSERT INTO delivery_areas (country, district, area, is_active, created_at)
                                    VALUES (?, ?, ?, ?, ?)
                                """, (a.get("country", "Bangladesh"), a["district"], a["area"], int(a.get("is_active", 1)), a.get("created_at", datetime.now().isoformat())))
                            else:
                                conn.execute("""
                                    UPDATE delivery_areas SET is_active = ?, country = ? WHERE id = ?
                                """, (int(a.get("is_active", 1)), a.get("country", "Bangladesh"), existing["id"]))
            conn.commit()
        finally:
            conn.close()
    try:
        execute_with_retry(_do)
        print(f"[remote_control] [SYNC] Real-time delivery areas synced across servers.")
    except Exception as e:
        print(f"[remote_control] Two-way delivery areas sync failed: {e}")


def _on_vouchers_change(doc_snapshots, changes, read_time):
    """Live listener watching `vouchers` collection in Firestore."""
    def _do():
        conn = get_connection()
        try:
            for change in changes:
                doc = change.document
                data = doc.to_dict() or {}
                code = data.get("code") or doc.id
                if not code:
                    continue
                if change.type.name in ("ADDED", "MODIFIED"):
                    existing = conn.execute("SELECT id FROM vouchers WHERE code = ?", (code,)).fetchone()
                    target_type = data.get("target_type", "product_discount")
                    discount_type = data.get("discount_type", "percentage")
                    discount_value = float(data.get("discount_value") or 0)
                    discount_base = data.get("discount_base", "sell_price")
                    expiry_date = data.get("expiry_date", "")
                    scope_type = data.get("scope_type", "all")
                    scope_id = data.get("scope_id")
                    active = int(data.get("active", 1))
                    created_at = data.get("created_at", datetime.now().isoformat())

                    if existing:
                        conn.execute("""
                            UPDATE vouchers SET target_type=?, discount_type=?, discount_value=?, discount_base=?,
                                               expiry_date=?, scope_type=?, scope_id=?, active=?
                            WHERE code=?
                        """, (target_type, discount_type, discount_value, discount_base, expiry_date, scope_type, scope_id, active, code))
                    else:
                        conn.execute("""
                            INSERT INTO vouchers (code, target_type, discount_type, discount_value, discount_base,
                                                 expiry_date, scope_type, scope_id, active, created_at)
                            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """, (code, target_type, discount_type, discount_value, discount_base, expiry_date, scope_type, scope_id, active, created_at))
                elif change.type.name == "REMOVED":
                    conn.execute("DELETE FROM vouchers WHERE code = ?", (code,))
            conn.commit()
        finally:
            conn.close()
    try:
        execute_with_retry(_do)
        print(f"[remote_control] [SYNC] Real-time vouchers synced across servers.")
    except Exception as e:
        print(f"[remote_control] Two-way vouchers sync failed: {e}")


# ---------------------------------------------------------------------------
# 3) INITIAL STARTUP PULL (Cloud Firestore -> Local SQLite DB)
# ---------------------------------------------------------------------------

def pull_all_from_cloud(blocking=False):
    """Initial startup pull: Reads all data from Cloud Firestore into local SQLite."""
    def _worker():
        try:
            db = _init_firebase()
            if not db:
                return

            # Fetch data from Firestore
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
                sales_docs = list(db.collection("sales").limit(500).stream())
            except Exception:
                sales_docs = []
            try:
                order_docs = list(db.collection("online_orders").limit(200).stream())
            except Exception:
                order_docs = []
            try:
                user_docs = list(db.collection("users").stream())
            except Exception:
                user_docs = []
            try:
                voucher_docs = list(db.collection("vouchers").stream())
            except Exception:
                voucher_docs = []
            try:
                area_doc = db.collection("config").document("delivery_areas").get()
                area_data = area_doc.to_dict() if area_doc.exists else {}
            except Exception:
                area_data = {}

            # Write everything in locked transaction
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
                        try:
                            pkg_id = int(data.get("id") or doc.id)
                        except Exception:
                            continue
                        name = data.get("name") or data.get("package_title") or ""
                        price = float(data.get("package_price") or data.get("price") or 0)
                        desc = data.get("description", "")
                        img = data.get("image_url", "")
                        if pkg_id and name:
                            conn.execute("INSERT OR REPLACE INTO packages (id, name, package_price, description, image_url, is_active, created_at) VALUES (?, ?, ?, ?, ?, 1, ?)", (pkg_id, name, price, desc, img, datetime.now().isoformat()))
                            conn.execute("DELETE FROM package_items WHERE package_id = ?", (pkg_id,))
                            for item in (data.get("items") or []):
                                pid = item.get("product_id")
                                if pid:
                                    conn.execute("INSERT INTO package_items (package_id, product_id, quantity) VALUES (?, ?, ?)", (pkg_id, int(pid), int(item.get("quantity") or 1)))

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

                    # 7. Pull Users (Staff, Admin, Riders)
                    for doc in user_docs:
                        data = doc.to_dict() or {}
                        username = data.get("username") or doc.id
                        password_hash = data.get("password_hash")
                        if username and password_hash:
                            existing = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
                            role = data.get("role", "cashier")
                            full_name = data.get("full_name", "")
                            is_active = int(data.get("is_active", 1))
                            plain_password = data.get("plain_password", "")
                            created_at = data.get("created_at", datetime.now().isoformat())
                            if existing:
                                conn.execute("""
                                    UPDATE users SET password_hash=?, role=?, full_name=?, is_active=?, plain_password=?
                                    WHERE username=?
                                """, (password_hash, role, full_name, is_active, plain_password, username))
                            else:
                                conn.execute("""
                                    INSERT INTO users (username, password_hash, role, full_name, is_active, plain_password, created_at)
                                    VALUES (?, ?, ?, ?, ?, ?, ?)
                                """, (username, password_hash, role, full_name, is_active, plain_password, created_at))

                    # 8. Pull Online Orders
                    for doc in order_docs:
                        data = doc.to_dict() or {}
                        order_num = data.get("order_number") or doc.id
                        existing = conn.execute("SELECT id FROM online_orders WHERE order_number = ?", (order_num,)).fetchone()
                        if not existing:
                            cur = conn.cursor()
                            cur.execute("""
                                INSERT INTO online_orders (
                                    order_number, customer_name, customer_phone, customer_email,
                                    country, district, area, address_details, payment_method,
                                    payment_status, subtotal, delivery_charge, total_amount,
                                    order_status, delivery_otp, is_stock_deducted,
                                    assigned_rider_id, assigned_rider_name, assigned_rider_phone,
                                    created_at, updated_at
                                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                order_num,
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
                                int(data.get("is_stock_deducted") or 0),
                                int(data.get("assigned_rider_id") or 0),
                                data.get("assigned_rider_name", ""),
                                data.get("assigned_rider_phone", ""),
                                data.get("created_at", datetime.now().isoformat()),
                                data.get("updated_at", datetime.now().isoformat())
                            ))
                            new_ord_id = cur.lastrowid
                            for it in (data.get("items") or []):
                                raw_pid = it.get("product_id") or 0
                                chk_p = conn.execute("SELECT id FROM products WHERE id = ?", (raw_pid,)).fetchone()
                                valid_pid = raw_pid if chk_p else 1
                                cur.execute("""
                                    INSERT INTO online_order_items (order_id, product_id, product_name, unit_price, mrp_price, quantity, total_price)
                                    VALUES (?, ?, ?, ?, ?, ?, ?)
                                """, (
                                    new_ord_id, valid_pid,
                                    it.get("product_name", ""),
                                    float(it.get("unit_price") or 0.0),
                                    float(it.get("mrp_price") or 0.0),
                                    int(it.get("quantity") or 1),
                                    float(it.get("total_price") or 0.0)
                                ))

                    # 9. Pull Delivery Areas
                    for a in (area_data.get("areas") or []):
                        if isinstance(a, dict) and a.get("district") and a.get("area"):
                            existing = conn.execute("SELECT id FROM delivery_areas WHERE district = ? AND area = ?", (a["district"], a["area"])).fetchone()
                            if not existing:
                                conn.execute("INSERT INTO delivery_areas (country, district, area, is_active, created_at) VALUES (?, ?, ?, ?, ?)",
                                             (a.get("country", "Bangladesh"), a["district"], a["area"], int(a.get("is_active", 1)), a.get("created_at", datetime.now().isoformat())))

                    # 10. Pull Vouchers
                    for doc in voucher_docs:
                        data = doc.to_dict() or {}
                        code = data.get("code") or doc.id
                        if code:
                            conn.execute("""
                                INSERT OR REPLACE INTO vouchers (code, target_type, discount_type, discount_value, discount_base, expiry_date, scope_type, scope_id, active, created_at)
                                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                            """, (
                                code,
                                data.get("target_type", "product_discount"),
                                data.get("discount_type", "percentage"),
                                float(data.get("discount_value") or 0),
                                data.get("discount_base", "sell_price"),
                                data.get("expiry_date", ""),
                                data.get("scope_type", "all"),
                                data.get("scope_id"),
                                int(data.get("active", 1)),
                                data.get("created_at", datetime.now().isoformat())
                            ))

                    # 11. Pull Sales
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
                            first_p = conn.execute("SELECT id FROM products LIMIT 1").fetchone()
                            default_pid = first_p["id"] if first_p else 1
                            for it in (data.get("items") or []):
                                raw_pid = int(it.get("product_id") or 0)
                                chk_p = conn.execute("SELECT id FROM products WHERE id = ?", (raw_pid,)).fetchone() if raw_pid else None
                                if not chk_p and it.get("sku"):
                                    chk_p = conn.execute("SELECT id FROM products WHERE sku = ?", (it.get("sku"),)).fetchone()
                                if not chk_p and it.get("product_name"):
                                    chk_p = conn.execute("SELECT id FROM products WHERE name = ?", (it.get("product_name"),)).fetchone()
                                valid_pid = chk_p["id"] if chk_p else default_pid

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

                    conn.commit()
                    print("[remote_control] [OK] Cloud pull complete: All data synced to local SQLite DB.")
                finally:
                    conn.close()

            execute_with_retry(_do_write)
        except Exception as e:
            print(f"[remote_control] pull_all_from_cloud error: {e}", flush=True)

    if blocking:
        _worker()
    else:
        threading.Thread(target=_worker, daemon=True).start()


def start():
    """Starts Firebase listeners and periodic backup thread."""
    db = _init_firebase()
    if not db:
        print("[remote_control] [ALERT] Firebase not initialized.", flush=True)
        return

    try:
        _ensure_remote_doc(db)

        # Initial pull from Cloud Firestore in background so server boots up immediately
        pull_all_from_cloud(blocking=False)

        def _safety_net_loop():
            while True:
                time.sleep(300)
                push_full_backup()

        # Live listeners (Firebase Cloud -> All Servers & Terminals)
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
        db.collection("config").document("delivery_areas").on_snapshot(_on_delivery_areas_change)
        db.collection("vouchers").on_snapshot(_on_vouchers_change)

        threading.Thread(target=_safety_net_loop, daemon=True).start()
        print("[remote_control] [OK] Firebase real-time two-way sync & remote control started successfully.", flush=True)
    except Exception as e:
        print(f"[remote_control] start error: {e}", flush=True)


def is_maintenance_mode():
    with _state_lock:
        return STATE["maintenance_mode"], STATE["maintenance_message"]


def get_announcement():
    with _state_lock:
        return STATE["announcement"]


def should_force_logout():
    with _state_lock:
        return STATE["force_logout"]
