"""
app.py
------
Entry point of the DOINEEK Supershop POS application.
Run it with:  python app.py
Then open a browser at: http://127.0.0.1:5000
"""

from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, has_request_context
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, date, timedelta
from functools import wraps
import os
import re
import sys
import sqlite3

# Fix Windows console encoding for Bengali/Unicode characters with real-time line buffering
if sys.platform == "win32":
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)


from database import (
    get_connection, init_db, round_to_whole, create_product_units,
    generate_invoice_number, get_all_settings, update_settings, execute_with_retry
)
from barcode_utils import generate_barcode_svg
import remote_control

app = Flask(__name__)
app.secret_key = "doineek-supershop-secret-key"

UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads', 'products')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER


def process_uploaded_image_file(file_path, max_dim=800, quality=75):
    """
    Optimizes an uploaded image file and returns a persistent Base64 Data URI.
    Ensures images survive ephemeral server restarts (Render) and sync seamlessly across all terminals & devices.
    """
    try:
        from PIL import Image
        import io, base64
        with Image.open(file_path) as im:
            im = im.convert("RGB")
            im.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
            out = io.BytesIO()
            im.save(out, format="JPEG", quality=quality, optimize=True)
            encoded = base64.b64encode(out.getvalue()).decode("utf-8")
            return f"data:image/jpeg;base64,{encoded}"
    except Exception as e:
        print(f"[image_processing] Error optimizing image {file_path}: {e}")
        return ""


def split_image_urls(img_str):
    if not img_str:
        return []
    img_str = str(img_str).strip()
    if not img_str:
        return []
    if ' || ' in img_str:
        return [s.strip() for s in img_str.split(' || ') if s.strip()]
    import re
    parts = re.split(r',\s*(?=data:image\/|https?:\/\/|\/static\/|\/uploads\/)', img_str)
    return [p.strip() for p in parts if p.strip()]


@app.template_filter('first_image')
def first_image_filter(img_val):
    if not img_val:
        return "/static/images/logo.png"
    parts = split_image_urls(img_val)
    return parts[0] if parts else "/static/images/logo.png"


@app.before_request
def handle_cors_options():
    if request.method == "OPTIONS":
        response = app.make_default_options_response()
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
        return response


@app.route("/api/ping", methods=["GET"])
@app.route("/health", methods=["GET"])
def health_check():
    return jsonify({
        "status": "ok",
        "service": "DOINEEK Supershop",
        "message": "Server is active & awake",
        "timestamp": datetime.now().isoformat()
    }), 200


def parse_bogo_quantities(offer_value, offer_title, product_name=""):
    """
    Parses buy_qty and free_qty for Buy X Get Y / BOGO offers.
    Supports formats like:
      - "Buy 4 Get 1 Free", "Buy 4 Get 1"
      - "4,1"
      - "4"
    """
    offer_val_str = (offer_value or "").strip()
    offer_title_str = (offer_title or "").strip()
    prod_name_str = (product_name or "").strip()

    bogo_pattern = re.compile(r"buy\s*(\d+)\s*get\s*(\d+)", re.IGNORECASE)
    for text in (offer_val_str, offer_title_str, prod_name_str):
        if text:
            match = bogo_pattern.search(text)
            if match:
                try:
                    b_qty = int(match.group(1))
                    f_qty = int(match.group(2))
                    if b_qty > 0 and f_qty > 0:
                        return b_qty, f_qty
                except Exception:
                    pass

    if offer_val_str and "," in offer_val_str:
        try:
            parts = [int(p.strip()) for p in offer_val_str.split(",") if p.strip().isdigit()]
            if len(parts) >= 2 and parts[0] > 0 and parts[1] > 0:
                return parts[0], parts[1]
        except Exception:
            pass

    if offer_val_str and offer_val_str.isdigit():
        val_digit = int(offer_val_str)
        if val_digit > 0:
            return val_digit, 1

    return 1, 1


@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With'
    response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
    return response


@app.before_request
def check_remote_control():
    """Runs before every page in the app. If the owner has switched on
    maintenance mode from the Firebase Console, every page (except the
    login screen and static files) is replaced with a short notice, and
    the page auto-refreshes so it comes back the instant the owner turns
    the switch back off - all without redeploying anything."""
    if request.path.startswith("/api/") or request.endpoint in (None, "static", "login"):
        return None

    if remote_control.should_force_logout():
        session.clear()
        return redirect(url_for("login"))

    maintenance_on, message = remote_control.is_maintenance_mode()
    if maintenance_on:
        return f"""
        <html><head><meta http-equiv="refresh" content="15">
        <title>Temporarily Closed</title></head>
        <body style="font-family:sans-serif;text-align:center;margin-top:15%;">
        <h2>{message}</h2>
        <p style="color:#888;">This page will refresh automatically.</p>
        </body></html>
        """, 503


@app.after_request
def add_cors_headers(response):
    """Add CORS headers to allow Web/Chrome/Flutter requests."""
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, Authorization"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, PUT, DELETE, OPTIONS"
    return response


@app.context_processor
def inject_shop_settings():
    """Makes `shop.shop_name`, `shop.shop_address`, `shop.shop_phone`,
    `shop.vat_reg_no` available in every template automatically, so the
    Settings page updates receipts, labels, and the header everywhere at
    once without touching each template's route."""
    return {"shop": get_all_settings()}


# ===========================================================================
# Helpers & Decorators
# ===========================================================================

def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return view(*args, **kwargs)
    return wrapped


def admin_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if session.get("role") != "admin":
            flash("Only an admin can perform this action.", "error")
            return redirect(url_for("dashboard"))
        return view(*args, **kwargs)
    return wrapped


# ===========================================================================
# Authentication
# ===========================================================================

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        conn = get_connection()
        user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()
        conn.close()
        if user and check_password_hash(user["password_hash"], password):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            session["role"] = user["role"]
            return redirect(url_for("dashboard"))
        flash("Wrong username or password.", "error")
    return render_template("login.html")


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))


# ===========================================================================
# Customer Storefront & Dashboard Routes
# ===========================================================================

def ensure_customer_profile_columns():
    try:
        conn = get_connection()
        cols = [r[1] for r in conn.execute("PRAGMA table_info(customer_users)").fetchall()]
        if "avatar_base64" not in cols:
            conn.execute("ALTER TABLE customer_users ADD COLUMN avatar_base64 TEXT DEFAULT ''")
        if "avatar_url" not in cols:
            conn.execute("ALTER TABLE customer_users ADD COLUMN avatar_url TEXT DEFAULT ''")
        if "address" not in cols:
            conn.execute("ALTER TABLE customer_users ADD COLUMN address TEXT DEFAULT ''")
        conn.commit()
        conn.close()
    except Exception as e:
        print("[migration] customer_users column check:", e)

ensure_customer_profile_columns()


def get_categories_tree_data(conn):
    cats = conn.execute("SELECT * FROM categories ORDER BY name").fetchall()
    subs = conn.execute("SELECT * FROM sub_categories ORDER BY name").fetchall()
    subsubs = conn.execute("SELECT * FROM sub_sub_categories ORDER BY name").fetchall()

    cat_counts = dict(conn.execute("SELECT category_id, COUNT(*) FROM products WHERE category_id IS NOT NULL GROUP BY category_id").fetchall())
    sub_counts = dict(conn.execute("SELECT sub_category_id, COUNT(*) FROM products WHERE sub_category_id IS NOT NULL GROUP BY sub_category_id").fetchall())
    subsub_counts = dict(conn.execute("SELECT sub_sub_category_id, COUNT(*) FROM products WHERE sub_sub_category_id IS NOT NULL GROUP BY sub_sub_category_id").fetchall())
    uncategorized_count = conn.execute("SELECT COUNT(*) FROM products WHERE category_id IS NULL OR category_id NOT IN (SELECT id FROM categories)").fetchone()[0]
    
    cat_list = []
    for c in cats:
        c_dict = dict(c)
        c_subs = []
        for s in subs:
            if s["category_id"] == c["id"]:
                s_dict = dict(s)
                s_subsubs = []
                for ss in subsubs:
                    if ss["sub_category_id"] == s["id"]:
                        ss_dict = dict(ss)
                        ss_dict["product_count"] = subsub_counts.get(ss["id"], 0)
                        s_subsubs.append(ss_dict)
                s_dict["product_count"] = sub_counts.get(s["id"], 0)
                s_dict["sub_sub_categories"] = s_subsubs
                c_subs.append(s_dict)
        c_dict["product_count"] = cat_counts.get(c["id"], 0)
        c_dict["sub_categories"] = c_subs
        cat_list.append(c_dict)

    if uncategorized_count > 0:
        cat_list.append({
            "id": -1,
            "name": "Uncategorized",
            "icon": "📦",
            "product_count": uncategorized_count,
            "sub_categories": []
        })
    return cat_list


def render_storefront():
    conn = get_connection()
    today_date = datetime.now().strftime("%Y-%m-%d")
    
    # Active Products (exclude expired)
    products = conn.execute("""
        SELECT p.*, 
               c.name AS category_name,
               s.name AS sub_category_name,
               ss.name AS sub_sub_category_name
        FROM products p
        LEFT JOIN categories c ON p.category_id = c.id
        LEFT JOIN sub_categories s ON p.sub_category_id = s.id
        LEFT JOIN sub_sub_categories ss ON p.sub_sub_category_id = ss.id
        WHERE (p.expiry_date IS NULL OR p.expiry_date = '' OR p.expiry_date >= ?) AND p.stock_qty > 0
        ORDER BY p.name
    """, (today_date,)).fetchall()
    
    categories = conn.execute("SELECT * FROM categories ORDER BY name").fetchall()
    categories_tree = get_categories_tree_data(conn)
    
    raw_pkgs = conn.execute("SELECT * FROM packages WHERE is_active = 1").fetchall()
    packages = []
    for pkg in raw_pkgs:
        p_dict = dict(pkg)
        items = conn.execute("""
            SELECT pi.*, p.name AS product_name, p.sell_price, p.mrp
            FROM package_items pi JOIN products p ON pi.product_id = p.id
            WHERE pi.package_id = ?
        """, (pkg["id"],)).fetchall()
        p_dict["included_items"] = [dict(i) for i in items]
        packages.append(p_dict)
        
    delivery_areas_rows = conn.execute("SELECT * FROM delivery_areas WHERE is_active = 1 ORDER BY district, area").fetchall()
    delivery_areas = [dict(r) for r in delivery_areas_rows]
    
    districts = sorted(list(set([r["district"].strip() for r in delivery_areas if r.get("district") and r["district"].strip()])))
    if not districts:
        districts = ["Tangail"]

    # Fetch real Active Special Offers & Banner Promotions from database
    promo_rows = conn.execute("""
        SELECT p.*, c.name AS category_name
        FROM products p
        LEFT JOIN categories c ON p.category_id = c.id
        WHERE p.is_promotion = 1 OR p.is_offer = 1 OR p.offer_type = 'bogo'
        ORDER BY p.id DESC
    """).fetchall()
    promos = [dict(r) for r in promo_rows]

    shop_settings = get_all_settings(conn)
    conn.close()
    
    return render_template(
        "store.html",
        products=[dict(p) for p in products],
        categories=[dict(c) for c in categories],
        categories_tree=categories_tree,
        packages=packages,
        delivery_areas=delivery_areas,
        districts=districts,
        promotions=promos,
        promo_interval_sec=int(shop_settings.get("promo_interval_sec") or 2),
        settings=shop_settings
    )


@app.route("/api/customer/update-profile", methods=["POST"])
def api_customer_update_profile():
    data = request.json or {}
    phone = data.get("phone", "").strip()
    name = data.get("name", "").strip()
    email = data.get("email", "").strip()
    avatar_base64 = data.get("avatar_base64", "").strip()
    avatar_url = data.get("avatar_url", "").strip()
    address = data.get("address", "").strip()

    if not phone:
        return jsonify({"success": False, "message": "Phone number is required."}), 400

    conn = get_connection()
    cust = conn.execute("SELECT * FROM customer_users WHERE phone = ?", (phone,)).fetchone()
    if not cust:
        conn.close()
        return jsonify({"success": False, "message": "Customer account not found."}), 404

    updates = []
    params = []
    if name:
        updates.append("name = ?")
        params.append(name)
    if email:
        updates.append("email = ?")
        params.append(email)
    if avatar_url:
        updates.append("avatar_url = ?")
        params.append(avatar_url)
    if avatar_base64:
        updates.append("avatar_base64 = ?")
        params.append(avatar_base64)
    if address:
        updates.append("address = ?")
        params.append(address)

    if updates:
        params.append(phone)
        conn.execute(f"UPDATE customer_users SET {', '.join(updates)} WHERE phone = ?", tuple(params))
        conn.commit()

    updated_cust = conn.execute("SELECT id, phone, name, email, avatar_url, avatar_base64, address FROM customer_users WHERE phone = ?", (phone,)).fetchone()
    conn.close()
    
    try:
        remote_control.push_customer_user_to_cloud(phone)
    except Exception as e:
        print("[customer_update] Error syncing to cloud:", e)

    return jsonify({
        "success": True,
        "message": "Profile updated successfully!",
        "user": dict(updated_cust) if updated_cust else {"phone": phone, "name": name}
    })


@app.route("/")
def home():
    if session.get("user_id"):
        return redirect(url_for("dashboard"))
    return render_storefront()


@app.route("/store")
def store_front():
    return render_storefront()


@app.route("/app")
@app.route("/app/<path:path>")
def flutter_web_app(path="index.html"):
    from flask import send_from_directory
    flutter_dir = os.path.join(app.static_folder, "flutter_web")
    if not path or path == "index.html" or not os.path.exists(os.path.join(flutter_dir, path)):
        return send_from_directory(flutter_dir, "index.html")
    return send_from_directory(flutter_dir, path)


@app.route("/dashboard")
@app.route("/admin")
@login_required
def dashboard():
    conn = get_connection()
    today = date.today().isoformat()
    today_sales = conn.execute(
        "SELECT COALESCE(SUM(rounded_total), 0) AS total, COUNT(*) AS count "
        "FROM sales WHERE date(created_at) = ?", (today,)
    ).fetchone()
    total_products = conn.execute("SELECT COUNT(*) AS c FROM products").fetchone()["c"]
    low_stock = conn.execute(
        "SELECT * FROM products WHERE stock_qty <= low_stock_threshold ORDER BY stock_qty ASC"
    ).fetchall()
    conn.close()
    return render_template(
        "dashboard.html",
        today_total=today_sales["total"],
        today_count=today_sales["count"],
        total_products=total_products,
        low_stock=low_stock,
    )


# ===========================================================================
# Products & Inventory
# ===========================================================================

def sync_expired_products():
    """
    Auto-detects expired products (expiry_date <= today), logs them into returned_items,
    sets active stock to 0, and pushes updates to Cloud Firestore.
    """
    today_date = datetime.now().strftime("%Y-%m-%d")
    conn = get_connection()
    try:
        expired_prods = conn.execute("""
            SELECT * FROM products
            WHERE expiry_date IS NOT NULL AND expiry_date != '' AND expiry_date <= ? AND stock_qty > 0
        """, (today_date,)).fetchall()

        if expired_prods:
            for ep in expired_prods:
                already = conn.execute(
                    "SELECT id FROM returned_items WHERE product_id = ? AND reason LIKE '%Expired%'", (ep["id"],)
                ).fetchone()
                if not already:
                    conn.execute("""
                        INSERT INTO returned_items (product_id, item_name, quantity, reason, expiry_date, date_returned)
                        VALUES (?, ?, ?, ?, ?, ?)
                    """, (
                        ep["id"], ep["name"], ep["stock_qty"],
                        f"Date Expired ({ep['expiry_date']})",
                        ep["expiry_date"],
                        datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    ))
                # Set active stock in products table to 0 so it's not sellable
                conn.execute("UPDATE products SET stock_qty = 0 WHERE id = ?", (ep["id"],))
            conn.commit()

            # Push each affected product to Firebase Cloud in background
            for ep in expired_prods:
                try:
                    remote_control.push_product_to_cloud(ep["id"])
                except Exception:
                    pass
    except Exception as e:
        print(f"[sync_expired_products] Error: {e}")
    finally:
        conn.close()


@app.route("/products")
@login_required
def products():
    sync_expired_products()
    conn = get_connection()
    open_cat = request.args.get("open_cat", "0") == "1"
    today_date = datetime.now().strftime("%Y-%m-%d")

    # Active (non-expired) products only - expired products are hidden from Inventory
    rows = conn.execute("""
        SELECT p.*,
               c.name AS category_name,
               sc.name AS sub_category_name,
               ssc.name AS sub_sub_category_name,
               (SELECT COUNT(*) FROM product_units u WHERE u.product_id = p.id AND u.status = 'in_stock') AS tag_count
        FROM products p
        LEFT JOIN categories c ON p.category_id = c.id
        LEFT JOIN sub_categories sc ON p.sub_category_id = sc.id
        LEFT JOIN sub_sub_categories ssc ON p.sub_sub_category_id = ssc.id
        WHERE (p.expiry_date IS NULL OR p.expiry_date = '' OR p.expiry_date > ?)
        ORDER BY p.name
    """, (today_date,)).fetchall()

    expired_row = conn.execute("SELECT COUNT(*) as c FROM returned_items WHERE reason LIKE '%Expired%'").fetchone()
    expired_count = expired_row["c"] if expired_row else 0
    categories = conn.execute("SELECT * FROM categories ORDER BY name").fetchall()
    sub_categories = conn.execute("SELECT * FROM sub_categories ORDER BY name").fetchall()
    sub_sub_categories = conn.execute("SELECT * FROM sub_sub_categories ORDER BY name").fetchall()
    brands = conn.execute("SELECT * FROM brands ORDER BY name").fetchall()
    conn.close()
    return render_template("products.html", products=rows, categories=categories,
                           sub_categories=sub_categories, sub_sub_categories=sub_sub_categories,
                           brands=brands, open_cat=open_cat, expired_count=expired_count)



@app.route("/products/new", methods=["GET", "POST"])
@login_required
@admin_required
def new_product():
    conn = get_connection()
    categories = conn.execute("SELECT * FROM categories ORDER BY name").fetchall()
    sub_categories = conn.execute("SELECT * FROM sub_categories ORDER BY name").fetchall()
    sub_sub_categories = conn.execute("SELECT * FROM sub_sub_categories ORDER BY name").fetchall()
    brands = conn.execute("SELECT * FROM brands ORDER BY name").fetchall()
    if request.method == "POST":
        sku = request.form["sku"].strip()
        name = request.form["name"].strip()
        brand = request.form.get("brand", "").strip()
        unit = request.form.get("unit", "").strip()
        category_id = request.form.get("category_id") or None
        sub_category_id = request.form.get("sub_category_id") or None
        sub_sub_category_id = request.form.get("sub_sub_category_id") or None
        cost_price = float(request.form["cost_price"] or 0)
        mrp = float(request.form["mrp"] or 0)
        sell_price = float(request.form["sell_price"] or 0)
        vat_pct = float(request.form["vat_pct"] or 0)
        stock_qty = int(request.form["stock_qty"] or 0)
        low_stock_threshold = int(request.form["low_stock_threshold"] or 5)
        sl_number = int(request.form.get("sl_number") or 1)
        description = request.form.get("description", "").strip()
        image_url = request.form.get("image_url", "").strip()
        
        # Auto-insert brand into brands table if new
        if brand:
            try:
                b_conn = get_connection()
                b_conn.execute("INSERT OR IGNORE INTO brands (name) VALUES (?)", (brand,))
                b_conn.commit()
                b_conn.close()
            except Exception:
                pass

        # Multi-file upload handling
        files = request.files.getlist("product_image_files") or request.files.getlist("product_image_file")
        uploaded_urls = []
        import random
        for file in files:
            if file and file.filename:
                filename = secure_filename(f"{sku}_{int(datetime.now().timestamp())}_{random.randint(10,99)}_{file.filename}")
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                data_uri = process_uploaded_image_file(file_path)
                if data_uri:
                    uploaded_urls.append(data_uri)
                else:
                    uploaded_urls.append(url_for("static", filename=f"uploads/products/{filename}"))

        if uploaded_urls:
            if image_url:
                image_url = ", ".join(uploaded_urls) + ", " + image_url
            else:
                image_url = ", ".join(uploaded_urls)

        is_trending = 1 if request.form.get("is_trending") == "on" else 0
        is_flash_sale = 1 if request.form.get("is_flash_sale") == "on" else 0
        is_offer = 1 if request.form.get("is_offer") == "on" else 0
        is_promotion = 1 if request.form.get("is_promotion") == "on" else 0
        offer_title = request.form.get("offer_title", "").strip()
        offer_type = request.form.get("offer_type", "").strip()
        offer_value = request.form.get("offer_value", "").strip()
        offer_base = request.form.get("offer_base", "mrp").strip()
        expiry_date = request.form.get("expiry_date", "").strip()

        def _do_insert():
            cur = conn.cursor()
            try:
                cur.execute(
                    "INSERT INTO products (sku, name, brand, unit, category_id, sub_category_id, sub_sub_category_id, cost_price, mrp, sell_price, vat_pct, stock_qty, low_stock_threshold, sl_number, description, image_url, is_trending, is_flash_sale, is_offer, is_promotion, offer_title, offer_type, offer_value, offer_base, expiry_date) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (sku, name, brand, unit, category_id, sub_category_id, sub_sub_category_id, cost_price, mrp, sell_price, vat_pct, stock_qty, low_stock_threshold, sl_number, description, image_url, is_trending, is_flash_sale, is_offer, is_promotion, offer_title, offer_type, offer_value, offer_base, expiry_date)
                )
            except sqlite3.OperationalError as op_err:
                if "no such column: unit" in str(op_err):
                    conn.execute("ALTER TABLE products ADD COLUMN unit TEXT NOT NULL DEFAULT ''")
                    cur.execute(
                        "INSERT INTO products (sku, name, brand, unit, category_id, sub_category_id, sub_sub_category_id, cost_price, mrp, sell_price, vat_pct, stock_qty, low_stock_threshold, sl_number, description, image_url, is_trending, is_flash_sale, is_offer, is_promotion, offer_title, offer_type, offer_value, offer_base, expiry_date) "
                        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                        (sku, name, brand, unit, category_id, sub_category_id, sub_sub_category_id, cost_price, mrp, sell_price, vat_pct, stock_qty, low_stock_threshold, sl_number, description, image_url, is_trending, is_flash_sale, is_offer, is_promotion, offer_title, offer_type, offer_value, offer_base, expiry_date)
                    )
                else:
                    raise op_err
            new_product_id = cur.lastrowid
            create_product_units(conn, new_product_id, stock_qty)
            conn.commit()
            return new_product_id

        try:
            new_product_id = execute_with_retry(_do_insert)
            conn.close()
            remote_control.push_product_to_cloud(new_product_id)
            flash(f'Product "{name}" added with {stock_qty} printable tag(s).', "success")
            return redirect(url_for("products"))
        except Exception as e:
            try:
                conn.close()
            except Exception:
                pass
            flash(f"Could not save product: {e}", "error")
    conn.close()
    return render_template("product_form.html", categories=categories, sub_categories=sub_categories, sub_sub_categories=sub_sub_categories, brands=brands, product=None)


@app.route("/products/<int:product_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def edit_product(product_id):
    conn = get_connection()
    product = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()

    if not product:
        conn.close()
        flash("Product not found.", "error")
        return redirect(url_for("products"))

    if request.method == "POST":
        new_stock_qty = int(request.form["stock_qty"] or 0)
        old_stock_qty = product["stock_qty"]
        sku_clean = request.form["sku"].strip()
        brand = request.form.get("brand", "").strip()
        unit = request.form.get("unit", "").strip()
        description = request.form.get("description", "").strip()
        image_url = request.form.get("image_url", "").strip()
        
        # Auto-insert brand into brands table if new
        if brand:
            try:
                conn.execute("INSERT OR IGNORE INTO brands (name) VALUES (?)", (brand,))
            except Exception:
                pass

        # Multi-file upload handling
        files = request.files.getlist("product_image_files") or request.files.getlist("product_image_file")
        uploaded_urls = []
        import random
        for file in files:
            if file and file.filename:
                filename = secure_filename(f"{sku_clean}_{int(datetime.now().timestamp())}_{random.randint(10,99)}_{file.filename}")
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                data_uri = process_uploaded_image_file(file_path)
                if data_uri:
                    uploaded_urls.append(data_uri)
                else:
                    uploaded_urls.append(url_for("static", filename=f"uploads/products/{filename}"))

        if uploaded_urls:
            if image_url:
                image_url = ", ".join(uploaded_urls) + ", " + image_url
            else:
                image_url = ", ".join(uploaded_urls)
        elif "image_url" not in request.form and product:
            image_url = product["image_url"]

        is_trending = 1 if request.form.get("is_trending") == "on" else 0
        is_flash_sale = 1 if request.form.get("is_flash_sale") == "on" else 0
        is_offer = 1 if request.form.get("is_offer") == "on" else 0
        is_promotion = 1 if request.form.get("is_promotion") == "on" else 0
        offer_title = request.form.get("offer_title", "").strip()
        offer_type = request.form.get("offer_type", "").strip()
        offer_value = request.form.get("offer_value", "").strip()
        offer_base = request.form.get("offer_base", "mrp").strip()
        expiry_date = request.form.get("expiry_date", "").strip()

        # Preserve existing offer settings if not explicitly provided or if BOGO
        existing_p = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
        if existing_p:
            if not offer_title and existing_p["offer_title"]:
                offer_title = existing_p["offer_title"]
            if not offer_type and existing_p["offer_type"]:
                offer_type = existing_p["offer_type"]
            if not offer_value and existing_p["offer_value"]:
                offer_value = existing_p["offer_value"]
            if not offer_base and existing_p["offer_base"]:
                offer_base = existing_p["offer_base"]
            if is_offer == 0 and existing_p["is_offer"] == 1 and request.form.get("is_offer") is None:
                is_offer = 1
            if is_promotion == 0 and existing_p["is_promotion"] == 1 and request.form.get("is_promotion") is None:
                is_promotion = 1

        if (offer_type in ('bogo', 'buy_x_get_y', 'buy_x_get_x') or 
            'buy' in offer_title.lower() or 
            'buy' in offer_value.lower()):
            offer_type = 'bogo'
            is_offer = 1
            if not offer_value and offer_title:
                offer_value = offer_title
            elif not offer_title and offer_value:
                offer_title = offer_value

        def _do_update():
            try:
                conn.execute("""
                    UPDATE products SET sku=?, name=?, brand=?, unit=?, category_id=?, sub_category_id=?, sub_sub_category_id=?, cost_price=?, mrp=?, sell_price=?,
                                         vat_pct=?, stock_qty=?, low_stock_threshold=?, sl_number=?,
                                         description=?, image_url=?, is_trending=?, is_flash_sale=?, is_offer=?, is_promotion=?,
                                         offer_title=?, offer_type=?, offer_value=?, offer_base=?, expiry_date=?
                    WHERE id=?
                """, (
                    sku_clean,
                    request.form["name"].strip(),
                    brand,
                    unit,
                    request.form.get("category_id") or None,
                    request.form.get("sub_category_id") or None,
                    request.form.get("sub_sub_category_id") or None,
                    float(request.form["cost_price"] or 0),
                    float(request.form["mrp"] or 0),
                    float(request.form["sell_price"] or 0),
                    float(request.form["vat_pct"] or 0),
                    new_stock_qty,
                    int(request.form["low_stock_threshold"] or 5),
                    int(request.form.get("sl_number") or 1),
                    description,
                    image_url,
                    is_trending,
                    is_flash_sale,
                    is_offer,
                    is_promotion,
                    offer_title,
                    offer_type,
                    offer_value,
                    offer_base,
                    expiry_date,
                    product_id
                ))
            except sqlite3.OperationalError as op_err:
                if "no such column: unit" in str(op_err):
                    conn.execute("ALTER TABLE products ADD COLUMN unit TEXT NOT NULL DEFAULT ''")
                    conn.execute("""
                        UPDATE products SET sku=?, name=?, brand=?, unit=?, category_id=?, sub_category_id=?, sub_sub_category_id=?, cost_price=?, mrp=?, sell_price=?,
                                             vat_pct=?, stock_qty=?, low_stock_threshold=?, sl_number=?,
                                             description=?, image_url=?, is_trending=?, is_flash_sale=?, is_offer=?, is_promotion=?,
                                             offer_title=?, offer_type=?, offer_value=?, offer_base=?, expiry_date=?
                        WHERE id=?
                    """, (
                        sku_clean,
                        request.form["name"].strip(),
                        brand,
                        unit,
                        request.form.get("category_id") or None,
                        request.form.get("sub_category_id") or None,
                        request.form.get("sub_sub_category_id") or None,
                        float(request.form["cost_price"] or 0),
                        float(request.form["mrp"] or 0),
                        float(request.form["sell_price"] or 0),
                        float(request.form["vat_pct"] or 0),
                        new_stock_qty,
                        int(request.form["low_stock_threshold"] or 5),
                        int(request.form.get("sl_number") or 1),
                        description,
                        image_url,
                        is_trending,
                        is_flash_sale,
                        is_offer,
                        is_promotion,
                        offer_title,
                        offer_type,
                        offer_value,
                        offer_base,
                        expiry_date,
                        product_id
                    ))
                else:
                    raise op_err

            if new_stock_qty > old_stock_qty:
                added = new_stock_qty - old_stock_qty
                create_product_units(conn, product_id, added)
            conn.commit()

        try:
            execute_with_retry(_do_update)
            conn.close()
            if new_stock_qty > old_stock_qty:
                flash(f"Product updated. {new_stock_qty - old_stock_qty} new printable tag(s) created for the restock.", "success")
            else:
                flash("Product updated.", "success")
            remote_control.push_product_to_cloud(product_id)
            return redirect(url_for("products"))
        except Exception as e:
            try:
                conn.rollback()
                conn.close()
            except Exception:
                pass
            flash(f"Could not update product: {e}", "error")
            return redirect(url_for("products"))

    categories = conn.execute("SELECT * FROM categories ORDER BY name").fetchall()
    sub_categories = conn.execute("SELECT * FROM sub_categories ORDER BY name").fetchall()
    sub_sub_categories = conn.execute("SELECT * FROM sub_sub_categories ORDER BY name").fetchall()
    brands = conn.execute("SELECT * FROM brands ORDER BY name").fetchall()
    conn.close()
    return render_template("product_form.html", categories=categories, sub_categories=sub_categories, sub_sub_categories=sub_sub_categories, brands=brands, product=product)


@app.route("/products/<int:product_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_product(product_id):
    conn = get_connection()
    product = conn.execute("SELECT sku FROM products WHERE id = ?", (product_id,)).fetchone()
    conn.execute("DELETE FROM products WHERE id = ?", (product_id,))
    conn.commit()
    conn.close()
    if product:
        remote_control.delete_product_from_cloud(product["sku"], product_id=product_id)
    else:
        remote_control.delete_product_from_cloud(None, product_id=product_id)
    flash("Product deleted.", "success")
    return redirect(url_for("products"))


@app.route("/products/<int:product_id>/restock", methods=["GET"])
@login_required
@admin_required
def restock_product(product_id):
    conn = get_connection()
    categories = conn.execute("SELECT * FROM categories ORDER BY name").fetchall()
    sub_categories = conn.execute("SELECT * FROM sub_categories ORDER BY name").fetchall()
    sub_sub_categories = conn.execute("SELECT * FROM sub_sub_categories ORDER BY name").fetchall()
    brands = conn.execute("SELECT * FROM brands ORDER BY name").fetchall()
    orig = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    conn.close()

    if not orig:
        flash("Product not found.", "error")
        return redirect(url_for("products"))

    # Convert to dict and increment SL Number by 1
    p_dict = dict(orig)
    new_sl = (p_dict.get("sl_number") or 1) + 1
    p_dict["id"] = None
    p_dict["sl_number"] = new_sl
    # Keep original SKU intact as requested by user
    p_dict["sku"] = orig["sku"]
    p_dict["stock_qty"] = 10

    flash(f"Restocking product: SL Number incremented to {new_sl}. You can modify price/stock/expiry and save.", "info")
    return render_template("product_form.html", categories=categories, sub_categories=sub_categories, sub_sub_categories=sub_sub_categories, brands=brands, product=p_dict)


@app.route("/products/<int:product_id>/return", methods=["POST"])
@login_required
def return_product(product_id):
    conn = get_connection()
    product = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    if not product:
        conn.close()
        flash("Product not found.", "error")
        return redirect(url_for("products"))

    ret_qty = int(request.form.get("quantity") or product["stock_qty"] or 1)
    reason = request.form.get("reason", "Returned by Cashier / Manager").strip()
    today_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    conn.execute("""
        INSERT INTO returned_items (product_id, item_name, quantity, reason, expiry_date, date_returned)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (product["id"], product["name"], ret_qty, reason, product["expiry_date"] or '', today_str))

    # Reduce product stock by returned quantity
    new_stock = max(0, product["stock_qty"] - ret_qty)
    conn.execute("UPDATE products SET stock_qty = ? WHERE id = ?", (new_stock, product["id"]))
    conn.commit()
    conn.close()
    remote_control.push_product_to_cloud(product["id"])

    flash(f"Product '{product['name']}' ({ret_qty} units) moved to Returned Items / Date Expired section.", "success")
    return redirect(url_for("products"))


@app.route("/returned_items")
@login_required
def returned_items():
    sync_expired_products()
    conn = get_connection()
    rows = conn.execute("SELECT * FROM returned_items ORDER BY date_returned DESC").fetchall()
    conn.close()
    return render_template("returned_items.html", items=rows)


@app.route("/returned_items/<int:return_id>/restock", methods=["GET", "POST"])
@login_required
@admin_required
def restock_from_returned(return_id):
    conn = get_connection()
    ret_item = conn.execute("SELECT * FROM returned_items WHERE id = ?", (return_id,)).fetchone()
    if not ret_item:
        conn.close()
        flash("Returned record not found.", "error")
        return redirect(url_for("returned_items"))

    # Try to find original product by product_id or by name
    product = None
    if ret_item["product_id"]:
        product = conn.execute("SELECT * FROM products WHERE id = ?", (ret_item["product_id"],)).fetchone()
    if not product:
        product = conn.execute("SELECT * FROM products WHERE LOWER(name) = LOWER(?)", (ret_item["item_name"],)).fetchone()

    categories = conn.execute("SELECT * FROM categories ORDER BY name").fetchall()
    sub_categories = conn.execute("SELECT * FROM sub_categories ORDER BY name").fetchall()
    sub_sub_categories = conn.execute("SELECT * FROM sub_sub_categories ORDER BY name").fetchall()
    brands = conn.execute("SELECT * FROM brands ORDER BY name").fetchall()

    if request.method == "POST":
        sku_clean = request.form["sku"].strip()
        name = request.form["name"].strip()
        brand = request.form.get("brand", "").strip()
        unit = request.form.get("unit", "").strip()
        category_id = request.form.get("category_id") or None
        sub_category_id = request.form.get("sub_category_id") or None
        sub_sub_category_id = request.form.get("sub_sub_category_id") or None
        cost_price = float(request.form.get("cost_price") or 0)
        mrp = float(request.form.get("mrp") or 0)
        sell_price = float(request.form.get("sell_price") or 0)
        vat_pct = float(request.form.get("vat_pct") or 0)
        stock_qty = int(request.form.get("stock_qty") or 0)
        low_stock_threshold = int(request.form.get("low_stock_threshold") or 5)
        sl_number = int(request.form.get("sl_number") or 1)
        description = request.form.get("description", "").strip()
        image_url = request.form.get("image_url", "").strip()
        expiry_date = request.form.get("expiry_date", "").strip()
        is_trending = 1 if request.form.get("is_trending") == "on" else 0
        is_flash_sale = 1 if request.form.get("is_flash_sale") == "on" else 0
        is_offer = 1 if request.form.get("is_offer") == "on" else 0
        is_promotion = 1 if request.form.get("is_promotion") == "on" else 0
        offer_title = request.form.get("offer_title", "").strip()
        offer_type = request.form.get("offer_type", "").strip()
        offer_value = request.form.get("offer_value", "").strip()
        offer_base = request.form.get("offer_base", "mrp").strip()

        # Multi-file upload handling
        files = request.files.getlist("product_image_files") or request.files.getlist("product_image_file")
        uploaded_urls = []
        import random
        for file in files:
            if file and file.filename:
                filename = secure_filename(f"{sku_clean}_{int(datetime.now().timestamp())}_{random.randint(10,99)}_{file.filename}")
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                data_uri = process_uploaded_image_file(file_path)
                if data_uri:
                    uploaded_urls.append(data_uri)
                else:
                    uploaded_urls.append(url_for("static", filename=f"uploads/products/{filename}"))
        if uploaded_urls:
            image_url = ", ".join(uploaded_urls) + (", " + image_url if image_url else "")
        elif "image_url" not in request.form and product:
            image_url = product["image_url"]

        target_product_id = product["id"] if product else None

        def _do_restock():
            nonlocal target_product_id
            if target_product_id:
                # Update existing product in products table
                conn.execute("""
                    UPDATE products SET
                        sku=?, name=?, brand=?, unit=?, category_id=?, sub_category_id=?, sub_sub_category_id=?,
                        cost_price=?, mrp=?, sell_price=?, vat_pct=?, stock_qty=?, low_stock_threshold=?,
                        sl_number=?, description=?, image_url=?, is_trending=?, is_flash_sale=?,
                        is_offer=?, is_promotion=?, offer_title=?, offer_type=?, offer_value=?, offer_base=?, expiry_date=?
                    WHERE id=?
                """, (
                    sku_clean, name, brand, unit, category_id, sub_category_id, sub_sub_category_id,
                    cost_price, mrp, sell_price, vat_pct, stock_qty, low_stock_threshold,
                    sl_number, description, image_url, is_trending, is_flash_sale,
                    is_offer, is_promotion, offer_title, offer_type, offer_value, offer_base, expiry_date,
                    target_product_id
                ))
            else:
                # Insert new product into products table
                cur = conn.cursor()
                cur.execute("""
                    INSERT INTO products (
                        sku, name, brand, unit, category_id, sub_category_id, sub_sub_category_id,
                        cost_price, mrp, sell_price, vat_pct, stock_qty, low_stock_threshold,
                        sl_number, description, image_url, is_trending, is_flash_sale,
                        is_offer, is_promotion, offer_title, offer_type, offer_value, offer_base, expiry_date
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    sku_clean, name, brand, unit, category_id, sub_category_id, sub_sub_category_id,
                    cost_price, mrp, sell_price, vat_pct, stock_qty, low_stock_threshold,
                    sl_number, description, image_url, is_trending, is_flash_sale,
                    is_offer, is_promotion, offer_title, offer_type, offer_value, offer_base, expiry_date
                ))
                target_product_id = cur.lastrowid

            if stock_qty > 0:
                create_product_units(conn, target_product_id, stock_qty)
            conn.commit()

        try:
            execute_with_retry(_do_restock)
            conn.close()
            remote_control.push_product_to_cloud(target_product_id)
            flash(f"Product '{name}' successfully restocked with {stock_qty} unit(s) and is now live in Inventory!", "success")
            return redirect(url_for("products"))
        except Exception as e:
            try:
                conn.rollback()
                conn.close()
            except Exception:
                pass
            flash(f"Could not restock product: {e}", "error")
            return redirect(url_for("returned_items"))

    # GET request: Prepare prefilled product dict
    if product:
        p_dict = dict(product)
        # Default restock quantity to returned quantity if available
        if ret_item["quantity"] and ret_item["quantity"] > 0:
            p_dict["stock_qty"] = ret_item["quantity"]
        else:
            p_dict["stock_qty"] = 10
        # If the product was expired, clear expiry_date so user is prompted to set a fresh one
        today_str = datetime.now().strftime("%Y-%m-%d")
        if p_dict.get("expiry_date") and p_dict["expiry_date"] <= today_str:
            p_dict["expiry_date"] = ""
    else:
        # Construct fallback dictionary from returned_items record
        p_dict = {
            "id": None,
            "sku": f"RESTOCK-{ret_item['id']}",
            "name": ret_item["item_name"],
            "brand": "",
            "unit": "pcs",
            "category_id": None,
            "sub_category_id": None,
            "sub_sub_category_id": None,
            "cost_price": 0.0,
            "mrp": 0.0,
            "sell_price": 0.0,
            "vat_pct": 0.0,
            "stock_qty": ret_item["quantity"] or 10,
            "low_stock_threshold": 5,
            "sl_number": 1,
            "description": f"Restocked from returned record #{ret_item['id']}",
            "image_url": "",
            "expiry_date": "",
            "is_trending": 0,
            "is_flash_sale": 0,
            "is_offer": 0,
            "is_promotion": 0,
            "offer_title": "",
            "offer_type": "",
            "offer_value": "",
            "offer_base": "mrp"
        }

    conn.close()
    return render_template(
        "product_form.html",
        categories=categories,
        sub_categories=sub_categories,
        sub_sub_categories=sub_sub_categories,
        brands=brands,
        product=p_dict,
        form_title=f"🔄 Restock '{ret_item['item_name']}' to Inventory"
    )



@app.route("/products/<int:product_id>/labels")
@login_required
def product_labels(product_id):
    conn = get_connection()
    product = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    if not product:
        conn.close()
        flash("Product not found.", "error")
        return redirect(url_for("products"))

    unit_id = request.args.get("unit_id", type=int)
    if unit_id:
        units = conn.execute(
            "SELECT * FROM product_units WHERE product_id = ? AND id = ? AND status = 'in_stock'",
            (product_id, unit_id)
        ).fetchall()
    else:
        units = conn.execute(
            "SELECT * FROM product_units WHERE product_id = ? AND status = 'in_stock' ORDER BY sl_number",
            (product_id,)
        ).fetchall()

    if units:
        # Each visit to this page is a print run - track how many times
        # this product's tags have been sent to the printer (shown on the
        # Inventory page as "Printed N time(s)").
        conn.execute(
            "UPDATE products SET label_print_count = label_print_count + 1 WHERE id = ?",
            (product_id,)
        )
        conn.commit()
        product = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    conn.close()

    # IMPORTANT: the barcode encodes the product's own SKU - the SAME value
    # for every physical unit - exactly like the working invoice barcode on
    # the print receipt. A per-unit barcode caused two problems: browsers/
    # scanners sometimes failed to resolve it back to a product at all, and
    # it made the barcode value collide visually with a "serial number".
    # Scanning any tag of this product now reliably adds that SKU to the
    # cart; which physical unit gets sold is tracked separately (see
    # /pos/lookup) using the SN-xxxxxx serial printed as plain text below
    # the barcode.
    shared_barcode_svg = generate_barcode_svg(product["sku"])
    tags = [(unit, shared_barcode_svg) for unit in units]

    # Default to auto-printing immediately on load - exactly like the sale
    # receipt print page - so opening this page from Inventory is truly a
    # single click that sends every tag to the printer without an extra
    # button press. Pass ?autoprint=0 to suppress it (e.g. just viewing).
    autoprint = request.args.get("autoprint", "1") == "1"
    return render_template("product_labels.html", product=product, tags=tags, autoprint=autoprint)


@app.route("/products/<int:product_id>/labels/print-all")
@login_required
def print_all_labels(product_id):
    conn = get_connection()
    product = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    if not product:
        conn.close()
        flash("Product not found.", "error")
        return redirect(url_for("products"))

    units = conn.execute(
        "SELECT * FROM product_units WHERE product_id = ? AND status = 'in_stock' ORDER BY sl_number",
        (product_id,)
    ).fetchall()

    if units:
        conn.execute(
            "UPDATE products SET label_print_count = label_print_count + 1 WHERE id = ?",
            (product_id,)
        )
        conn.commit()

    conn.close()
    return render_template("labels_print.html", product=product, units=units)


@app.route("/categories/new", methods=["POST"])
@login_required
@admin_required
def new_category():
    name = request.form["name"].strip()
    icon = request.form.get("icon", "").strip()
    if name:
        conn = get_connection()
        conn.execute("INSERT OR IGNORE INTO categories (name, icon) VALUES (?, ?)", (name, icon))
        conn.commit()
        conn.close()
        remote_control.push_categories_to_cloud()
        flash(f'Category "{name}" added.', "success")
    return redirect(url_for("products"))


# ===========================================================================
# POS & Checkout
# ===========================================================================

@app.route("/pos/lookup")
@login_required
def pos_lookup():
    code = request.args.get("code", "").strip()
    if not code:
        return jsonify({"error": "No code given."}), 400

    exclude = [s for s in request.args.get("exclude", "").split(",") if s]

    conn = get_connection()
    product = None
    specific_unit_serial = None

    # 1. Try matching physical tag's unique serial number (a_code) first (e.g. SN-000004)
    unit_by_acode = conn.execute("SELECT * FROM product_units WHERE a_code = ? AND status = 'in_stock'", (code,)).fetchone()
    if not unit_by_acode and code.upper().startswith("SN-"):
        unit_by_acode = conn.execute("SELECT * FROM product_units WHERE UPPER(a_code) = ? AND status = 'in_stock'", (code.upper(),)).fetchone()
    
    if unit_by_acode:
        product = conn.execute("SELECT * FROM products WHERE id = ?", (unit_by_acode["product_id"],)).fetchone()
        specific_unit_serial = unit_by_acode["a_code"]

    # 2. If not matched by serial tag, match by product SKU or name
    if not product:
        product = conn.execute("SELECT * FROM products WHERE sku = ? OR LOWER(name) = LOWER(?)", (code, code)).fetchone()

    if not product:
        conn.close()
        return jsonify({"error": f'No product found for tag or SKU "{code}".'}), 404

    # Check if expired
    today_date = datetime.now().strftime("%Y-%m-%d")
    if product["expiry_date"] and product["expiry_date"] <= today_date:
        conn.close()
        return jsonify({"error": f'Product "{product["name"]}" expired on {product["expiry_date"]} and has been moved to Returned/Expired section.'}), 400

    # 3. If a specific unit serial was not matched, pick the next available in-stock unit serial
    if not specific_unit_serial:
        if exclude:
            placeholders = ",".join("?" for _ in exclude)
            unit = conn.execute(f"""
                SELECT a_code FROM product_units
                WHERE product_id = ? AND status = 'in_stock' AND a_code NOT IN ({placeholders})
                ORDER BY sl_number LIMIT 1
            """, (product["id"], *exclude)).fetchone()
        else:
            unit = conn.execute("""
                SELECT a_code FROM product_units
                WHERE product_id = ? AND status = 'in_stock'
                ORDER BY sl_number LIMIT 1
            """, (product["id"],)).fetchone()
        if unit:
            specific_unit_serial = unit["a_code"]

    conn.close()

    return jsonify({
        "id": product["id"],
        "name": product["name"],
        "sku": product["sku"],
        "price": product["sell_price"],
        "mrp": product["mrp"],
        "vat_pct": product["vat_pct"],
        "stock_qty": product["stock_qty"],
        "is_offer": product["is_offer"],
        "offer_type": product["offer_type"],
        "offer_value": product["offer_value"],
        "offer_title": product["offer_title"],
        "unit_serial": specific_unit_serial,
    })


@app.route("/pos")
@login_required
def pos():
    sync_expired_products()
    today_date = datetime.now().strftime("%Y-%m-%d")
    conn = get_connection()
    all_products = conn.execute("""
        SELECT * FROM products 
        WHERE stock_qty > 0 AND (expiry_date IS NULL OR expiry_date = '' OR expiry_date > ?)
        ORDER BY name
    """, (today_date,)).fetchall()
    conn.close()
    return render_template("pos.html", products=all_products)


@app.route("/pos/checkout", methods=["POST"])
@login_required
def checkout():
    data = request.get_json()
    items = data.get("items", [])
    cash_amount = float(data.get("cash_amount") or 0)
    card_amount = float(data.get("card_amount") or 0)
    customer_name = data.get("customer_name", "").strip()
    raw_mobile = re.sub(r"\D", "", data.get("customer_mobile", "") or "")
    if raw_mobile.startswith("8801") and len(raw_mobile) == 13:
        raw_mobile = raw_mobile[2:]
    customer_mobile = raw_mobile

    if not items:
        return jsonify({"error": "Cart is empty."}), 400

    conn = get_connection()
    cur = conn.cursor()

    sub_total = 0
    mrp_total = 0
    total_vat = 0
    line_details = []

    for item in items:
        product = cur.execute("SELECT * FROM products WHERE id = ?", (item["product_id"],)).fetchone()
        if not product:
            conn.close()
            return jsonify({"error": "A product in the cart no longer exists."}), 400
        quantity = int(item["quantity"])
        if product["stock_qty"] < quantity:
            conn.close()
            return jsonify({"error": f'Not enough stock for "{product["name"]}".'}), 400

        # Serials the cashier actually scanned off a physical tag for this
        # line (may be fewer than quantity if some units were added by
        # clicking the product tile instead of scanning).
        scanned_serials = [s for s in (item.get("serials") or []) if s]
        valid_serials = []
        for serial in scanned_serials:
            unit_row = cur.execute(
                "SELECT id FROM product_units WHERE a_code = ? AND product_id = ? AND status = 'in_stock'",
                (serial, product["id"])
            ).fetchone()
            if not unit_row:
                conn.close()
                return jsonify({
                    "error": f'Scanned serial "{serial}" for "{product["name"]}" is no longer available. Please rescan or remove it from the cart.'
                }), 400
            valid_serials.append((serial, unit_row["id"]))

        offer_type = product["offer_type"] or ""
        offer_value = product["offer_value"] or ""
        offer_title = product["offer_title"] or ""
        paid_qty = quantity
        if offer_type in ('buy_x_get_y', 'bogo', 'buy_x_get_x') or ('buy' in offer_title.lower()) or ('buy' in offer_value.lower()):
            buy_qty, free_qty = parse_bogo_quantities(offer_value, offer_title, product["name"])
            total_set = buy_qty + free_qty
            sets = quantity // total_set
            remainder = quantity % total_set
            paid_qty = (sets * buy_qty) + min(remainder, buy_qty)

        line_subtotal = product["sell_price"] * paid_qty
        vat_rate = product["vat_pct"] / 100.0 if product["vat_pct"] else 0
        line_vat = line_subtotal * vat_rate

        sub_total += line_subtotal
        total_vat += line_vat
        mrp_for_line = product["mrp"] if product["mrp"] > 0 else product["sell_price"]
        mrp_total += mrp_for_line * quantity
        line_details.append((
            product["id"],
            quantity,
            product["sell_price"],
            mrp_for_line,
            product["vat_pct"],
            line_vat,
            product["cost_price"],
            valid_serials
        ))

    grand_total = sub_total + total_vat
    rounded_total = round_to_whole(grand_total)
    saved_amount = round(mrp_total - grand_total, 2)

    # If cashier left cash/card blank, default to exact cash payment
    if cash_amount == 0 and card_amount == 0:
        cash_amount = rounded_total
        change_amount = 0.0
    else:
        change_amount = round((cash_amount + card_amount) - rounded_total, 2)
        if change_amount < 0:
            conn.close()
            return jsonify({"error": f"Amount tendered is short by {abs(change_amount):.2f}."}), 400

    invoice_number = generate_invoice_number()

    invoice_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if customer_mobile and len(customer_mobile) == 11 and customer_mobile.startswith("01"):
        existing_cust = cur.execute("SELECT id, name FROM customer_users WHERE phone = ?", (customer_mobile,)).fetchone()
        if not existing_cust:
            pass_hash = generate_password_hash("123456")
            name_to_use = customer_name.strip() if customer_name and customer_name.strip() else f"Customer {customer_mobile[-4:]}"
            cur.execute("""
                INSERT INTO customer_users (phone, name, email, password_hash, plain_password, is_verified, created_at)
                VALUES (?, ?, '', ?, '123456', 1, ?)
            """, (customer_mobile, name_to_use, pass_hash, datetime.now().isoformat()))
        elif customer_name and customer_name.strip() and (not existing_cust["name"] or existing_cust["name"].startswith("Customer ")):
            cur.execute("UPDATE customer_users SET name = ? WHERE phone = ?", (customer_name.strip(), customer_mobile))

    cur.execute("""
        INSERT INTO sales (invoice_number, invoice_date, cashier_id, customer_id, customer_name, customer_mobile, channel,
                            total_amount, rounded_total, vat_amount, saved_amount,
                            cash_amount, card_amount, change_amount, created_at)
        VALUES (?, ?, ?, ?, ?, ?, 'Offline', ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        invoice_number, invoice_date, session.get("user_id", 1), customer_name, customer_name, customer_mobile,
        sub_total, rounded_total, total_vat, saved_amount,
        cash_amount, card_amount, change_amount, datetime.now().isoformat()
    ))
    sale_id = cur.lastrowid

    for product_id, quantity, unit_price, mrp_price, vat_pct, line_vat, cost_price, valid_serials in line_details:
        sold_serials = []

        # 1) Mark the units the cashier actually scanned as sold.
        for serial, unit_id in valid_serials:
            cur.execute("UPDATE product_units SET status = 'sold' WHERE id = ?", (unit_id,))
            sold_serials.append(serial)

        # 2) Auto-fill any remaining quantity (added without scanning a tag)
        #    from whatever units are still in stock.
        remaining = quantity - len(valid_serials)
        if remaining > 0:
            auto_units = cur.execute("""
                SELECT id, a_code FROM product_units
                WHERE product_id = ? AND status = 'in_stock'
                LIMIT ?
            """, (product_id, remaining)).fetchall()
            for u in auto_units:
                cur.execute("UPDATE product_units SET status = 'sold' WHERE id = ?", (u["id"],))
                sold_serials.append(u["a_code"])

        unit_serials_str = ", ".join(sold_serials)

        cur.execute(
            "INSERT INTO sale_items (sale_id, product_id, quantity, unit_price, mrp_price, vat_pct, vat_amount, cost_price, unit_serials) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (sale_id, product_id, quantity, unit_price, mrp_price, vat_pct, line_vat, cost_price, unit_serials_str)
        )
        cur.execute(
            "UPDATE products SET stock_qty = stock_qty - ? WHERE id = ?",
            (quantity, product_id)
        )

    conn.commit()
    conn.close()

    # Real-time backup: push this invoice, customer user, and updated product stocks to Firebase immediately
    remote_control.push_sale_to_cloud(sale_id)
    if customer_mobile and len(customer_mobile) == 11 and customer_mobile.startswith("01"):
        remote_control.push_customer_user_to_cloud(customer_mobile)
    for item in items:
        if item.get("product_id"):
            remote_control.push_product_to_cloud(item["product_id"])


    return jsonify({
        "success": True,
        "sale_id": sale_id,
        "invoice_number": invoice_number,
        "sub_total": sub_total,
        "rounded_total": rounded_total,
        "vat_amount": total_vat,
        "change_amount": change_amount,
    })


# ===========================================================================
# Sales History & Receipts
# ===========================================================================

@app.route("/sales")
@app.route("/sales/history")
@login_required
def sales_history():
    conn = get_connection()
    # Both Admin and Cashier can view all sales and online customer transactions
    rows = conn.execute("""
        SELECT s.*, COALESCE(u.username, 'Online App') AS cashier_name
        FROM sales s LEFT JOIN users u ON s.cashier_id = u.id
        ORDER BY s.id DESC
    """).fetchall()
    conn.close()
    return render_template("sales_history.html", sales=rows)


@app.route("/sales/<int:sale_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_sale(sale_id):
    conn = get_connection()
    sale = conn.execute("SELECT * FROM sales WHERE id = ?", (sale_id,)).fetchone()
    if sale:
        inv_num = sale["invoice_number"]
        conn.execute("DELETE FROM sale_items WHERE sale_id = ?", (sale_id,))
        conn.execute("DELETE FROM sales WHERE id = ?", (sale_id,))
        conn.commit()
        remote_control.delete_sale_from_cloud(inv_num, sale_id=sale_id)
        flash("Sale log entry deleted successfully.", "success")
    else:
        flash("Sale entry not found.", "error")
    conn.close()
    return redirect(url_for("sales_history"))


def prepare_receipt_data(conn, sale_id):
    sale = conn.execute("""
        SELECT s.*, COALESCE(u.username, 'Online App') AS cashier_name
        FROM sales s LEFT JOIN users u ON s.cashier_id = u.id
        WHERE s.id = ?
    """, (sale_id,)).fetchone()
    if not sale:
        return None, [], {}

    sale_dict = dict(sale)
    inv_num = str(sale_dict.get("invoice_number") or "")
    online_items_map = {}
    delivery_charge = 0.0
    if inv_num.startswith("INV-ONLINE-"):
        ord_num = inv_num.replace("INV-ONLINE-", "").strip()
        ord_row = conn.execute("SELECT * FROM online_orders WHERE order_number = ?", (ord_num,)).fetchone()
        if ord_row:
            delivery_charge = float(ord_row["delivery_charge"] or 0)
            sale_dict["delivery_charge"] = delivery_charge
            sale_dict["order_status"] = ord_row["order_status"]
            sale_dict["area"] = ord_row["area"]
            sale_dict["district"] = ord_row["district"]
            sale_dict["address_details"] = ord_row["address_details"]
            sale_dict["delivery_otp"] = ord_row["delivery_otp"]
            sale_dict["payment_method"] = ord_row["payment_method"]
            o_items = conn.execute("SELECT * FROM online_order_items WHERE order_id = ?", (ord_row["id"],)).fetchall()
            for oi in o_items:
                online_items_map[oi["product_id"]] = {
                    "product_name": oi["product_name"],
                    "total_price": float(oi["total_price"] or 0),
                    "quantity": int(oi["quantity"] or 1)
                }

    raw_items = conn.execute("""
        SELECT si.*, COALESCE(p.name, '') AS prod_name_tbl, COALESCE(p.sku, '') AS prod_sku, p.offer_type, p.offer_value, p.offer_title
        FROM sale_items si LEFT JOIN products p ON si.product_id = p.id
        WHERE si.sale_id = ?
    """, (sale_id,)).fetchall()
    
    items = []
    for r in raw_items:
        i_dict = dict(r)
        pid = i_dict["product_id"]
        
        if pid in online_items_map and online_items_map[pid].get("product_name"):
            i_dict["product_name"] = online_items_map[pid]["product_name"]
            i_dict["sku"] = "ONLINE"
        else:
            is_regular_prod = conn.execute("SELECT id FROM products WHERE id = ?", (pid,)).fetchone()
            pkg = None
            if not is_regular_prod or (i_dict.get("prod_name_tbl") or "").startswith("📦"):
                pkg = conn.execute("SELECT * FROM packages WHERE id = ?", (pid,)).fetchone()

            if pkg:
                p_items = conn.execute("""
                    SELECT pi.*, p.sku, p.name AS product_name
                    FROM package_items pi JOIN products p ON pi.product_id = p.id
                    WHERE pi.package_id = ?
                """, (pkg["id"],)).fetchall()
                details = []
                sl = 1
                for pi in p_items:
                    details.append(f"{pi['sku'] or 'SKU'} {pi['product_name']} SL:{sl}")
                    sl += 1
                i_dict["product_name"] = f"{pkg['name']} ({', '.join(details)})"
                i_dict["sku"] = "COMBO"
            else:
                i_dict["product_name"] = i_dict.get("prod_name_tbl") or "Item"
                i_dict["sku"] = i_dict.get("prod_sku") or ""

        qty = int(i_dict.get("quantity") or 1)
        unit_price = float(i_dict.get("unit_price") or 0.0)
        offer_type = i_dict.get("offer_type") or ""
        offer_title = i_dict.get("offer_title") or ""
        offer_value = i_dict.get("offer_value") or ""
        p_name = i_dict.get("product_name") or ""

        paid_qty = qty
        free_qty = 0
        is_bogo = (offer_type in ('buy_x_get_y', 'bogo', 'buy_x_get_x') or 
                   'buy' in offer_title.lower() or 
                   'buy' in offer_value.lower() or 
                   'buy' in p_name.lower())
        
        if is_bogo:
            b_qty, f_qty = parse_bogo_quantities(offer_value, offer_title, p_name)
            tot_set = b_qty + f_qty
            if tot_set > 0:
                sets = qty // tot_set
                rem = qty % tot_set
                paid_qty = (sets * b_qty) + min(rem, b_qty)
                free_qty = qty - paid_qty

        line_total = round(unit_price * paid_qty, 2)
        bogo_disc = round(unit_price * free_qty, 2)

        i_dict["paid_qty"] = paid_qty
        i_dict["free_qty"] = free_qty
        i_dict["line_total"] = line_total
        i_dict["bogo_discount"] = bogo_disc
        i_dict["is_bogo"] = is_bogo
        items.append(i_dict)

    settings = get_all_settings(conn)
    return sale_dict, items, settings


@app.route("/sales/<int:sale_id>")
@login_required
def sale_receipt(sale_id):
    conn = get_connection()
    sale, items, settings = prepare_receipt_data(conn, sale_id)
    conn.close()
    if not sale:
        flash("Sale not found.", "error")
        return redirect(url_for("sales_history"))

    total_words = number_to_words(int(round_to_whole(sale["rounded_total"] or sale["total_amount"])))
    return render_template("sale_receipt.html", sale=sale, items=items, total_words=total_words, shop=settings)


# ===========================================================================
# Customers
# ===========================================================================

@app.route("/customers/api/search")
@login_required
def customers_api_search():
    q = request.args.get("q", "").strip()
    if len(q) < 2:
        return jsonify([])
    like = f"%{q}%"
    conn = get_connection()
    
    # Registered App Customers
    reg_users = conn.execute("SELECT * FROM customer_users WHERE phone LIKE ? OR name LIKE ?", (like, like)).fetchall()
    
    # Online Order Customers
    online_cust = conn.execute("""
        SELECT customer_phone AS mobile, MAX(customer_name) AS name, COUNT(*) AS visits, SUM(total_amount) AS total_spent
        FROM online_orders
        WHERE customer_phone != '' AND (customer_name LIKE ? OR customer_phone LIKE ?)
        GROUP BY customer_phone
    """, (like, like)).fetchall()

    # Offline POS Customers
    pos_cust = conn.execute("""
        SELECT customer_mobile AS mobile, MAX(customer_name) AS name, COUNT(*) AS visits, SUM(rounded_total) AS total_spent
        FROM sales
        WHERE customer_mobile != '' AND (customer_name LIKE ? OR customer_mobile LIKE ?)
        GROUP BY customer_mobile
    """, (like, like)).fetchall()

    all_mobiles = set([u["phone"] for u in reg_users]) | set([o["mobile"] for o in online_cust]) | set([p["mobile"] for p in pos_cust])
    
    results = []
    for m in list(all_mobiles)[:10]:
        name = ""
        visits = 0
        total_spent = 0.0

        u_match = [u for u in reg_users if u["phone"] == m]
        if u_match:
            name = u_match[0]["name"]
        
        o_match = [o for o in online_cust if o["mobile"] == m]
        if o_match:
            if not name: name = o_match[0]["name"]
            visits += o_match[0]["visits"]
            total_spent += o_match[0]["total_spent"] or 0.0

        p_match = [p for p in pos_cust if p["mobile"] == m]
        if p_match:
            if not name: name = p_match[0]["name"]
            visits += p_match[0]["visits"]
            total_spent += p_match[0]["total_spent"] or 0.0

        results.append({
            "name": name or ("Customer " + m),
            "mobile": m,
            "visits": visits,
            "total_spent": round(total_spent, 2)
        })

    conn.close()
    return jsonify(results)


@app.route("/customers/api/profile")
@login_required
def customers_api_profile():
    phone = request.args.get("phone", "").strip()
    if not phone:
        return jsonify({"success": False, "message": "Phone number is required"}), 400

    conn = get_connection()
    user = conn.execute("SELECT * FROM customer_users WHERE phone = ?", (phone,)).fetchone()
    
    cust_name = ""
    if user and user["name"]:
        cust_name = user["name"]
    else:
        o = conn.execute("SELECT customer_name FROM online_orders WHERE customer_phone = ? AND customer_name != '' ORDER BY id DESC LIMIT 1", (phone,)).fetchone()
        if o and o["customer_name"]:
            cust_name = o["customer_name"]
        else:
            s = conn.execute("SELECT customer_name FROM sales WHERE customer_mobile = ? AND customer_name != '' ORDER BY id DESC LIMIT 1", (phone,)).fetchone()
            if s and s["customer_name"]:
                cust_name = s["customer_name"]

    online_stats = conn.execute("""
        SELECT COUNT(*) AS count, SUM(total_amount) AS total
        FROM online_orders WHERE customer_phone = ?
    """, (phone,)).fetchone()

    sales_stats = conn.execute("""
        SELECT COUNT(*) AS count, SUM(rounded_total) AS total
        FROM sales WHERE customer_mobile = ?
    """, (phone,)).fetchone()

    total_orders = (online_stats["count"] or 0) + (sales_stats["count"] or 0)
    total_spent = (online_stats["total"] or 0.0) + (sales_stats["total"] or 0.0)

    district = user["district"] if user and "district" in user.keys() else ""
    area = user["area"] if user and "area" in user.keys() else ""
    address_details = user["address_details"] if user and "address_details" in user.keys() else ""
    profile_image = user["profile_image"] if user and "profile_image" in user.keys() else ""

    if not district or not area:
        latest_order = conn.execute("SELECT district, area, address_details FROM online_orders WHERE customer_phone = ? ORDER BY id DESC LIMIT 1", (phone,)).fetchone()
        if latest_order:
            if not district: district = latest_order["district"] or ""
            if not area: area = latest_order["area"] or ""
            if not address_details: address_details = latest_order["address_details"] or ""

    conn.close()

    return jsonify({
        "success": True,
        "name": cust_name or f"Customer {phone}",
        "phone": phone,
        "email": user["email"] if user else "",
        "profile_image": profile_image,
        "district": district or "Not specified",
        "area": area or "Not specified",
        "address_details": address_details or "No detailed address recorded",
        "is_blocked": user["is_blocked"] if user else 0,
        "block_reason": user["block_reason"] if user else "",
        "total_orders": total_orders,
        "total_spent": round(total_spent, 2)
    })


@app.route("/customers")
@login_required
def customers_page():
    search = request.args.get("q", "").strip()
    conn = get_connection()

    matched_orders = []
    if search:
        like = f"%{search}%"
        # 1. Collect all associated phone numbers for search query (matches name or phone across all tables)
        matched_phones = set()
        cu_rows = conn.execute("SELECT phone FROM customer_users WHERE phone LIKE ? OR name LIKE ?", (like, like)).fetchall()
        for r in cu_rows:
            if r["phone"]: matched_phones.add(r["phone"])

        oo_rows = conn.execute("SELECT customer_phone FROM online_orders WHERE customer_phone LIKE ? OR customer_name LIKE ?", (like, like)).fetchall()
        for r in oo_rows:
            if r["customer_phone"]: matched_phones.add(r["customer_phone"])

        s_rows = conn.execute("SELECT customer_mobile FROM sales WHERE customer_mobile LIKE ? OR customer_name LIKE ?", (like, like)).fetchall()
        for r in s_rows:
            if r["customer_mobile"]: matched_phones.add(r["customer_mobile"])

        phone_list = list(matched_phones)

        # 2. Fetch sales log entries
        if phone_list:
            placeholders = ",".join(["?"] * len(phone_list))
            sales_rows = conn.execute(f"""
                SELECT s.id AS id,
                       s.invoice_number AS ref_number,
                       s.created_at,
                       s.customer_name,
                       s.customer_mobile,
                       s.rounded_total AS total_amount,
                       COALESCE(s.channel, 'Offline') AS channel,
                       'Completed' AS status,
                       '/sales/' || s.id || '/print' AS receipt_url
                FROM sales s
                WHERE s.customer_name LIKE ? OR s.customer_mobile LIKE ? OR s.customer_mobile IN ({placeholders})
            """, [like, like] + phone_list).fetchall()

            online_rows = conn.execute(f"""
                SELECT o.id AS id,
                       o.order_number AS ref_number,
                       o.created_at,
                       o.customer_name,
                       o.customer_phone AS customer_mobile,
                       o.total_amount,
                       'Online App' AS channel,
                       o.order_status AS status,
                       '/online_orders/' || o.id || '/invoice' AS receipt_url
                FROM online_orders o
                WHERE o.customer_name LIKE ? OR o.customer_phone LIKE ? OR o.customer_phone IN ({placeholders})
            """, [like, like] + phone_list).fetchall()
        else:
            sales_rows = conn.execute("""
                SELECT s.id AS id,
                       s.invoice_number AS ref_number,
                       s.created_at,
                       s.customer_name,
                       s.customer_mobile,
                       s.rounded_total AS total_amount,
                       COALESCE(s.channel, 'Offline') AS channel,
                       'Completed' AS status,
                       '/sales/' || s.id || '/print' AS receipt_url
                FROM sales s
                WHERE s.customer_name LIKE ? OR s.customer_mobile LIKE ?
            """, (like, like)).fetchall()

            online_rows = conn.execute("""
                SELECT o.id AS id,
                       o.order_number AS ref_number,
                       o.created_at,
                       o.customer_name,
                       o.customer_phone AS customer_mobile,
                       o.total_amount,
                       'Online App' AS channel,
                       o.order_status AS status,
                       '/online_orders/' || o.id || '/invoice' AS receipt_url
                FROM online_orders o
                WHERE o.customer_name LIKE ? OR o.customer_phone LIKE ?
            """, (like, like)).fetchall()

        seen_inv_numbers = set()
        for o in online_rows:
            o_dict = dict(o)
            seen_inv_numbers.add(f"INV-ONLINE-{o['ref_number']}")
            matched_orders.append(o_dict)

        for s in sales_rows:
            s_dict = dict(s)
            if s_dict["ref_number"] not in seen_inv_numbers:
                matched_orders.append(s_dict)

        matched_orders.sort(key=lambda x: x.get("created_at") or "", reverse=True)

    # Unified customer directory combining:
    # 1. Registered App Users (customer_users)
    # 2. Online Orders (online_orders)
    # 3. Offline Sales Log (sales)
    reg_users = conn.execute("SELECT * FROM customer_users").fetchall()
    reg_user_dict = {u["phone"]: dict(u) for u in reg_users}
    reg_phones = {u["phone"]: u["name"] for u in reg_users}

    online_stats = conn.execute("""
        SELECT customer_phone, MAX(customer_name) AS customer_name, COUNT(*) AS order_count,
               COALESCE(SUM(total_amount), 0) AS online_spent, MAX(created_at) AS last_activity
        FROM online_orders
        WHERE customer_phone != ''
        GROUP BY customer_phone
    """).fetchall()
    online_dict = {o["customer_phone"]: dict(o) for o in online_stats}

    pos_stats = conn.execute("""
        SELECT customer_mobile, MAX(customer_name) AS customer_name, COUNT(*) AS visit_count,
               COALESCE(SUM(rounded_total), 0) AS pos_spent, MAX(created_at) AS last_visit,
               SUM(CASE WHEN channel = 'Online' THEN 1 ELSE 0 END) AS online_sales_cnt,
               SUM(CASE WHEN channel IS NULL OR channel != 'Online' THEN 1 ELSE 0 END) AS offline_sales_cnt
        FROM sales
        WHERE customer_mobile != ''
        GROUP BY customer_mobile
    """).fetchall()
    pos_dict = {p["customer_mobile"]: dict(p) for p in pos_stats}

    all_phones = set(reg_phones.keys()) | set(online_dict.keys()) | set(pos_dict.keys())

    customer_directory = []
    for phone in all_phones:
        name = reg_phones.get(phone)
        if not name and phone in online_dict:
            name = online_dict[phone]["customer_name"]
        if not name and phone in pos_dict:
            name = pos_dict[phone]["customer_name"]
        if not name:
            name = "Customer " + phone

        has_registered = phone in reg_phones
        has_online_orders = phone in online_dict
        pos_info = pos_dict.get(phone, {})
        has_offline_sales = pos_info.get("offline_sales_cnt", 0) > 0

        is_online = has_registered or has_online_orders
        is_offline = has_offline_sales

        if is_online and is_offline:
            channel_tag = "Online & Offline"
        elif is_online:
            channel_tag = "Online"
        else:
            channel_tag = "Offline"

        visits = online_dict.get(phone, {}).get("order_count", 0) + pos_info.get("visit_count", 0)
        total_spent = online_dict.get(phone, {}).get("online_spent", 0.0) + pos_info.get("pos_spent", 0.0)

        d1 = online_dict.get(phone, {}).get("last_activity", "")
        d2 = pos_info.get("last_visit", "")
        last_activity = max(d1, d2) if (d1 and d2) else (d1 or d2 or "2026-01-01")

        reg_info = reg_user_dict.get(phone, {})
        is_blocked = reg_info.get("is_blocked", 0) == 1
        blocked_until = reg_info.get("blocked_until", "")
        block_reason = reg_info.get("block_reason", "")
        plain_pass = reg_info.get("plain_password", "") if reg_info else ""
        if not plain_pass and reg_info:
            plain_pass = "123456"
        email_addr = reg_info.get("email", "") if reg_info else ""

        customer_directory.append({
            "customer_name": name,
            "customer_mobile": phone,
            "profile_image": reg_info.get("profile_image") or reg_info.get("avatar") or reg_info.get("image_url") or "",
            "email": email_addr,
            "password": plain_pass if plain_pass else "—",
            "visit_count": visits,
            "total_spent": round(total_spent, 2),
            "last_visit": last_activity,
            "channel_tag": channel_tag,
            "is_blocked": is_blocked,
            "blocked_until": blocked_until,
            "block_reason": block_reason,
        })

    customer_directory.sort(key=lambda x: (x["last_visit"], reg_user_dict.get(x["customer_mobile"], {}).get("id", 0)), reverse=True)
    conn.close()

    matched_total_spent = sum(o["total_amount"] for o in matched_orders)
    return render_template(
        "customers.html",
        search=search,
        matched_orders=matched_orders,
        matched_total_spent=matched_total_spent,
        customer_directory=customer_directory
    )


@app.route("/customers/block", methods=["POST"])
@login_required
@admin_required
def block_customer():
    phone = re.sub(r"\D", "", request.form.get("phone", "") or "")
    action = request.form.get("action", "block")  # 'block' or 'unblock'
    duration = request.form.get("duration", "24h")  # '1h', '24h', '7d', '30d', 'permanent'
    reason = request.form.get("reason", "").strip()

    if not phone:
        flash("Customer phone number is required.", "error")
        return redirect(url_for("customers_page"))

    conn = get_connection()
    user = conn.execute("SELECT * FROM customer_users WHERE phone = ?", (phone,)).fetchone()
    if not user:
        conn.execute(
            "INSERT INTO customer_users (phone, name, password_hash, created_at) VALUES (?, ?, ?, ?)",
            (phone, f"Customer {phone}", generate_password_hash("blocked_user"), datetime.now().isoformat())
        )

    if action == "unblock":
        conn.execute(
            "UPDATE customer_users SET is_blocked = 0, blocked_until = '', block_reason = '' WHERE phone = ?",
            (phone,)
        )
        conn.commit()
        conn.close()
        remote_control.push_customer_user_to_cloud(phone)
        flash(f"Customer {phone} has been successfully unblocked.", "success")
        return redirect(url_for("customers_page"))

    now = datetime.now()
    if duration == "1h":
        until = (now + timedelta(hours=1)).isoformat()
        dur_label = "1 Hour"
    elif duration == "24h":
        until = (now + timedelta(days=1)).isoformat()
        dur_label = "24 Hours"
    elif duration == "7d":
        until = (now + timedelta(days=7)).isoformat()
        dur_label = "7 Days"
    elif duration == "30d":
        until = (now + timedelta(days=30)).isoformat()
        dur_label = "1 Month"
    else:
        until = "PERMANENT"
        dur_label = "Permanent"

    conn.execute(
        "UPDATE customer_users SET is_blocked = 1, blocked_until = ?, block_reason = ? WHERE phone = ?",
        (until, reason, phone)
    )
    conn.commit()
    conn.close()
    remote_control.push_customer_user_to_cloud(phone)
    flash(f"Customer {phone}  {dur_label} has been blocked.", "warning")
    return redirect(url_for("customers_page"))


def normalize_phone(phone_str):
    if not phone_str:
        return ""
    cleaned = re.sub(r"\D", "", str(phone_str))
    if cleaned.startswith("8801"):
        cleaned = cleaned[2:]
    return cleaned


@app.route("/customers/create", methods=["POST"])
@login_required
@admin_required
def create_customer_admin():
    name = request.form.get("name", "").strip()
    phone = normalize_phone(request.form.get("phone", ""))
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "").strip()

    if not name or not phone or not password:
        flash("Name, Mobile Number, and Password are required.", "error")
        return redirect(url_for("customers_page"))

    if not (len(phone) == 11 and phone.startswith("01")):
        flash("Mobile number must start with '01' and be exactly 11 digits.", "error")
        return redirect(url_for("customers_page"))

    if len(password) < 4:
        flash("Password must be at least 4 characters long.", "error")
        return redirect(url_for("customers_page"))

    conn = get_connection()
    existing = conn.execute(
        "SELECT id FROM customer_users WHERE phone = ? OR (email != '' AND email = ?)",
        (phone, email)
    ).fetchone()

    if existing:
        conn.close()
        flash("Already registered with this mobile number or email.", "error")
        return redirect(url_for("customers_page"))

    conn.execute(
        "INSERT INTO customer_users (phone, name, email, password_hash, plain_password, is_verified, created_at) VALUES (?, ?, ?, ?, ?, 1, ?)",
        (phone, name, email, generate_password_hash(password), password, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()
    remote_control.push_customer_user_to_cloud(phone)

    flash(f"Customer '{name}' ({phone}) created successfully! They can now log in to the Mobile App using this Mobile Number and Password.", "success")
    return redirect(url_for("customers_page"))


@app.route("/customers/edit", methods=["POST"])
@login_required
@admin_required
def edit_customer_admin():
    old_phone = normalize_phone(request.form.get("old_phone", ""))
    raw_new_phone = request.form.get("phone", "").strip()
    new_phone = normalize_phone(raw_new_phone)
    name = request.form.get("name", "").strip()
    email = request.form.get("email", "").strip()
    password = request.form.get("password", "").strip()

    if not old_phone or not name or not new_phone:
        flash("Customer Name and Mobile Number are required.", "error")
        return redirect(url_for("customers_page"))

    if not (len(new_phone) == 11 and new_phone.startswith("01")):
        flash("Mobile number must start with '01' and be exactly 11 digits.", "error")
        return redirect(url_for("customers_page"))

    conn = get_connection()
    cust = conn.execute("SELECT * FROM customer_users WHERE phone = ?", (old_phone,)).fetchone()

    if not cust:
        pw_hash = generate_password_hash(password) if password else generate_password_hash("123456")
        plain_pw = password if password else "123456"
        conn.execute(
            "INSERT INTO customer_users (phone, name, email, password_hash, plain_password, is_verified, created_at) VALUES (?, ?, ?, ?, ?, 1, ?)",
            (new_phone, name, email, pw_hash, plain_pw, datetime.now().isoformat())
        )
    else:
        if password:
            pw_hash = generate_password_hash(password)
            plain_pw = password
            conn.execute(
                "UPDATE customer_users SET phone = ?, name = ?, email = ?, password_hash = ?, plain_password = ? WHERE phone = ?",
                (new_phone, name, email, pw_hash, plain_pw, old_phone)
            )
        else:
            conn.execute(
                "UPDATE customer_users SET phone = ?, name = ?, email = ? WHERE phone = ?",
                (new_phone, name, email, old_phone)
            )

    if old_phone != new_phone:
        conn.execute("UPDATE sales SET customer_mobile = ?, customer_name = ? WHERE customer_mobile = ?", (new_phone, name, old_phone))
        conn.execute("UPDATE online_orders SET customer_phone = ?, customer_name = ? WHERE customer_phone = ?", (new_phone, name, old_phone))
    else:
        conn.execute("UPDATE sales SET customer_name = ? WHERE customer_mobile = ?", (name, old_phone))
        conn.execute("UPDATE online_orders SET customer_name = ? WHERE customer_phone = ?", (name, old_phone))

    conn.commit()
    conn.close()
    remote_control.push_customer_user_to_cloud(new_phone)


    flash(f"Customer '{name}' ({new_phone}) updated successfully!", "success")
    return redirect(url_for("customers_page"))


@app.route("/customers/delete", methods=["POST"])
@login_required
@admin_required
def delete_customer_admin():
    raw_phone = request.form.get("phone", "").strip()
    clean_phone = normalize_phone(raw_phone)
    if not raw_phone and not clean_phone:
        flash("Customer phone number is required for deletion.", "error")
        return redirect(url_for("customers_page"))

    conn = get_connection()
    cust = conn.execute("SELECT * FROM customer_users WHERE phone = ? OR phone = ?", (raw_phone, clean_phone)).fetchone()
    name = cust["name"] if cust else raw_phone

    # Wipes all occurrences across customer_users, sales, and online_orders (raw string, clean string, or matching substring)
    conn.execute("DELETE FROM customer_users WHERE phone = ? OR phone = ?", (raw_phone, clean_phone))
    if clean_phone and len(clean_phone) >= 7:
        like_pattern = f"%{clean_phone}%"
        conn.execute("UPDATE sales SET customer_mobile = '' WHERE customer_mobile = ? OR customer_mobile = ? OR customer_mobile LIKE ?", (raw_phone, clean_phone, like_pattern))
        conn.execute("UPDATE online_orders SET customer_phone = '' WHERE customer_phone = ? OR customer_phone = ? OR customer_phone LIKE ?", (raw_phone, clean_phone, like_pattern))
    else:
        conn.execute("UPDATE sales SET customer_mobile = '' WHERE customer_mobile = ?", (raw_phone,))
        conn.execute("UPDATE online_orders SET customer_phone = '' WHERE customer_phone = ?", (raw_phone,))

    conn.commit()
    conn.close()

    if clean_phone:
        remote_control.delete_customer_from_cloud(clean_phone)
    if raw_phone and raw_phone != clean_phone:
        remote_control.delete_customer_from_cloud(raw_phone)

    flash(f"Customer '{name}' ({raw_phone}) has been permanently deleted.", "success")
    return redirect(url_for("customers_page"))


@app.route("/riders")
@login_required
@admin_required
def riders_page():
    conn = get_connection()
    columns = [c[1] for c in conn.execute("PRAGMA table_info(users)").fetchall()]
    if "full_name" not in columns:
        try: conn.execute("ALTER TABLE users ADD COLUMN full_name TEXT NOT NULL DEFAULT ''")
        except: pass
    if "is_active" not in columns:
        try: conn.execute("ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")
        except: pass
    if "plain_password" not in columns:
        try: conn.execute("ALTER TABLE users ADD COLUMN plain_password TEXT NOT NULL DEFAULT ''")
        except: pass
    conn.commit()

    riders = conn.execute("SELECT * FROM users WHERE role = 'delivery' ORDER BY id DESC").fetchall()
    riders_list = []
    for r in riders:
        r_dict = dict(r)
        r_phone = r_dict.get("username", "")
        r_id = r_dict.get("id")
        
        # Fetch orders assigned or accepted by this rider
        rider_orders = conn.execute("""
            SELECT * FROM online_orders 
            WHERE assigned_rider_id = ? OR assigned_rider_phone = ?
            ORDER BY id DESC
        """, (r_id, r_phone)).fetchall()
        
        orders_data = []
        total_delivered = 0
        total_collected = 0.0
        
        for ord_row in rider_orders:
            o_dict = dict(ord_row)
            if o_dict.get("order_status") == "delivered":
                total_delivered += 1
                total_collected += float(o_dict.get("total_amount", 0))
            orders_data.append(o_dict)

        riders_list.append({
            "id": r_id,
            "username": r_phone,
            "full_name": r_dict.get("full_name") or r_phone,
            "plain_password": r_dict.get("plain_password") or "123456",
            "is_active": r_dict.get("is_active", 1),
            "created_at": r_dict.get("created_at", ""),
            "orders": orders_data,
            "total_orders": len(orders_data),
            "total_delivered": total_delivered,
            "total_collected": total_collected
        })
    conn.close()
    return render_template("riders.html", riders=riders_list)


@app.route("/riders/create", methods=["POST"])
@login_required
@admin_required
def create_rider_admin():
    full_name = request.form.get("full_name", "").strip()
    raw_user = request.form.get("username", "").strip()
    username = normalize_phone(raw_user)
    password = request.form.get("password", "").strip()

    if not full_name or not username or not password:
        flash("Rider Full Name, Mobile Number, and Password are required.", "error")
        return redirect(url_for("riders_page"))

    if not (len(username) == 11 and username.startswith("01")):
        flash("Rider mobile number must start with '01' and be exactly 11 digits.", "error")
        return redirect(url_for("riders_page"))

    if len(password) < 3:
        flash("Password must be at least 3 characters long.", "error")
        return redirect(url_for("riders_page"))

    conn = get_connection()
    columns = [c[1] for c in conn.execute("PRAGMA table_info(users)").fetchall()]
    if "full_name" not in columns:
        try: conn.execute("ALTER TABLE users ADD COLUMN full_name TEXT NOT NULL DEFAULT ''")
        except: pass
    if "is_active" not in columns:
        try: conn.execute("ALTER TABLE users ADD COLUMN is_active INTEGER NOT NULL DEFAULT 1")
        except: pass
    if "plain_password" not in columns:
        try: conn.execute("ALTER TABLE users ADD COLUMN plain_password TEXT NOT NULL DEFAULT ''")
        except: pass
    conn.commit()

    existing = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    if existing:
        conn.close()
        flash("A rider or staff user with this mobile number already exists.", "error")
        return redirect(url_for("riders_page"))

    conn.execute(
        "INSERT INTO users (username, password_hash, plain_password, role, full_name, is_active, created_at) VALUES (?, ?, ?, 'delivery', ?, 1, ?)",
        (username, generate_password_hash(password), password, full_name, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()
    remote_control.push_users_to_cloud()

    flash(f"Delivery Rider '{full_name}' ({username}) created successfully!", "success")
    return redirect(url_for("riders_page"))


@app.route("/riders/edit", methods=["POST"])
@login_required
@admin_required
def edit_rider_admin():
    rider_id = request.form.get("rider_id", type=int)
    full_name = request.form.get("full_name", "").strip()
    username = normalize_phone(request.form.get("username", ""))
    password = request.form.get("password", "").strip()
    is_active = request.form.get("is_active", type=int, default=1)

    if not rider_id or not full_name or not username:
        flash("Rider ID, Name, and Mobile Number are required.", "error")
        return redirect(url_for("riders_page"))

    conn = get_connection()
    if password:
        conn.execute(
            "UPDATE users SET full_name = ?, username = ?, password_hash = ?, plain_password = ?, is_active = ? WHERE id = ? AND role = 'delivery'",
            (full_name, username, generate_password_hash(password), password, is_active, rider_id)
        )
    else:
        conn.execute(
            "UPDATE users SET full_name = ?, username = ?, is_active = ? WHERE id = ? AND role = 'delivery'",
            (full_name, username, is_active, rider_id)
        )
    conn.commit()
    conn.close()
    remote_control.push_users_to_cloud()

    flash(f"Delivery Rider '{full_name}' updated successfully!", "success")
    return redirect(url_for("riders_page"))


@app.route("/riders/delete", methods=["POST"])
@login_required
@admin_required
def delete_rider_admin():
    rider_id = request.form.get("rider_id", type=int)
    if not rider_id:
        flash("Rider ID is required.", "error")
        return redirect(url_for("riders_page"))

    conn = get_connection()
    conn.execute("DELETE FROM users WHERE id = ? AND role = 'delivery'", (rider_id,))
    conn.commit()
    conn.close()
    remote_control.push_users_to_cloud()

    flash("Delivery rider account deleted successfully.", "success")
    return redirect(url_for("riders_page"))


def check_customer_block(conn, phone):
    if not phone:
        return False, ""
    phone_clean = re.sub(r"\D", "", phone)
    user = conn.execute("SELECT * FROM customer_users WHERE phone = ?", (phone_clean,)).fetchone()
    if not user or user["is_blocked"] != 1:
        return False, ""
    
    until = user["blocked_until"]
    reason = user.get("block_reason", "")
    reason_str = f" (Reason: {reason})" if reason else ""
    
    if until == "PERMANENT":
        return True, f"Your account has been permanently blocked{reason_str}। Please contact shop administration."
    
    try:
        until_dt = datetime.fromisoformat(until)
        if datetime.now() < until_dt:
            time_left_str = until_dt.strftime("%d-%m-%Y %I:%M %p")
            return True, f"Your account is temporarily blocked for {time_left_str} {reason_str}।"
        else:
            # Auto unblock
            conn.execute("UPDATE customer_users SET is_blocked = 0, blocked_until = '', block_reason = '' WHERE phone = ?", (phone_clean,))
            conn.commit()
            return False, ""
    except Exception:
        return True, f"Your account is temporarily blocked for   {reason_str}।"


@app.route("/sales/<int:sale_id>/print")
@login_required
def sale_receipt_print(sale_id):
    conn = get_connection()
    sale = conn.execute("SELECT id FROM sales WHERE id = ?", (sale_id,)).fetchone()
    if not sale:
        conn.close()
        flash("Sale not found.", "error")
        return redirect(url_for("sales_history"))

    conn.execute("UPDATE sales SET print_count = print_count + 1 WHERE id = ?", (sale_id,))
    conn.commit()

    sale, items, settings = prepare_receipt_data(conn, sale_id)
    conn.close()

    total_words = number_to_words(int(round_to_whole(sale["rounded_total"] or sale["total_amount"])))
    invoice_code = str(sale["invoice_number"] or sale["id"])
    invoice_barcode_svg = generate_barcode_svg(invoice_code)
    return render_template(
        "sale_receipt_print.html", sale=sale, items=items, total_words=total_words,
        invoice_barcode_svg=invoice_barcode_svg, shop=settings
    )


def number_to_words(n):
    if n == 0:
        return "Zero Taka Only"
    ones = ["", "One", "Two", "Three", "Four", "Five", "Six", "Seven", "Eight", "Nine",
            "Ten", "Eleven", "Twelve", "Thirteen", "Fourteen", "Fifteen", "Sixteen",
            "Seventeen", "Eighteen", "Nineteen"]
    tens = ["", "", "Twenty", "Thirty", "Forty", "Fifty", "Sixty", "Seventy", "Eighty", "Ninety"]

    def two_digits(x):
        if x < 20:
            return ones[x]
        return tens[x // 10] + (" " + ones[x % 10] if x % 10 else "")

    def three_digits(x):
        hundreds = x // 100
        rest = x % 100
        result = ""
        if hundreds:
            result += ones[hundreds] + " Hundred"
            if rest:
                result += " and " + two_digits(rest)
        elif rest:
            result += two_digits(rest)
        return result

    parts = []
    if n >= 10000000:
        parts.append(three_digits(n // 10000000) + " Crore")
        n %= 10000000
    if n >= 100000:
        parts.append(two_digits(n // 100000) + " Lakh")
        n %= 100000
    if n >= 1000:
        parts.append(two_digits(n // 1000) + " Thousand")
        n %= 1000
    if n > 0:
        parts.append(three_digits(n))

    return " ".join(parts) + " Taka Only"


# ===========================================================================
# Shop Settings (Admin Only)
# ===========================================================================

@app.route("/settings", methods=["GET", "POST"])
@login_required
@admin_required
def settings_page():
    conn = get_connection()
    if request.method == "POST":
        values = {
            "shop_name": request.form.get("shop_name", "").strip(),
            "shop_address": request.form.get("shop_address", "").strip(),
            "shop_phone": request.form.get("shop_phone", "").strip(),
            "customer_support_phone": request.form.get("customer_support_phone", "").strip(),
            "vat_reg_no": request.form.get("vat_reg_no", "").strip(),
            "delivery_charge": request.form.get("delivery_charge", "60").strip(),
            "promo_interval_sec": request.form.get("promo_interval_sec", "2").strip(),
            "smtp_app_password": request.form.get("smtp_app_password", "").strip(),
            "facebook_url": request.form.get("facebook_url", "").strip(),
            "youtube_url": request.form.get("youtube_url", "").strip(),
            "x_url": request.form.get("x_url", "").strip(),
            "instagram_url": request.form.get("instagram_url", "").strip(),
            "policy_about_us": request.form.get("policy_about_us", "").strip(),
            "policy_blog": request.form.get("policy_blog", "").strip(),
            "policy_cookies": request.form.get("policy_cookies", "").strip(),
            "policy_return_refund": request.form.get("policy_return_refund", "").strip(),
            "policy_privacy": request.form.get("policy_privacy", "").strip(),
            "policy_terms": request.form.get("policy_terms", "").strip(),
            "policy_warranty": request.form.get("policy_warranty", "").strip(),
            "policy_help_center": request.form.get("policy_help_center", "").strip(),
        }
        update_settings(conn, values)
        conn.commit()
        conn.close()
        remote_control.push_full_backup()
        flash("Shop settings and policies updated successfully.", "success")
        return redirect(url_for("settings_page"))
    current_settings = get_all_settings(conn)
    conn.close()
    return render_template("settings.html", settings=current_settings)


@app.route("/categories/edit/<int:category_id>", methods=["POST"])
@login_required
@admin_required
def edit_category(category_id):
    name = request.form.get("name", "").strip()
    icon = request.form.get("icon", "").strip()
    if name:
        conn = get_connection()
        conn.execute("UPDATE categories SET name = ?, icon = ? WHERE id = ?", (name, icon, category_id))
        conn.commit()
        conn.close()
        remote_control.push_categories_to_cloud()
        flash(f'Category "{name}" updated.', "success")
    return redirect(url_for("products"))


@app.route("/categories/delete/<int:category_id>", methods=["POST"])
@login_required
@admin_required
def delete_category(category_id):
    conn = get_connection()
    conn.execute("DELETE FROM categories WHERE id = ?", (category_id,))
    conn.execute("DELETE FROM sub_categories WHERE category_id = ?", (category_id,))
    conn.commit()
    conn.close()
    remote_control.push_categories_to_cloud()
    flash("Category deleted.", "info")
    return redirect(url_for("products"))


@app.route("/subcategories/new", methods=["POST"])
@login_required
@admin_required
def new_subcategory():
    category_id = request.form.get("category_id")
    name = request.form.get("name", "").strip()
    icon = request.form.get("icon", "").strip()
    if category_id and name:
        conn = get_connection()
        conn.execute("INSERT INTO sub_categories (category_id, name, icon) VALUES (?, ?, ?)", (category_id, name, icon))
        conn.commit()
        conn.close()
        remote_control.push_categories_to_cloud()
        flash(f'Sub-category "{name}" created.', "success")
    return redirect(url_for("products"))


@app.route("/subcategories/edit/<int:sub_id>", methods=["POST"])
@login_required
@admin_required
def edit_subcategory(sub_id):
    category_id = request.form.get("category_id")
    name = request.form.get("name", "").strip()
    icon = request.form.get("icon", "").strip()
    if name:
        conn = get_connection()
        conn.execute("UPDATE sub_categories SET category_id = ?, name = ?, icon = ? WHERE id = ?", (category_id, name, icon, sub_id))
        conn.commit()
        conn.close()
        remote_control.push_categories_to_cloud()
        flash(f'Sub-category "{name}" updated.', "success")
    return redirect(url_for("products"))


@app.route("/subcategories/delete/<int:sub_id>", methods=["POST"])
@login_required
@admin_required
def delete_subcategory(sub_id):
    conn = get_connection()
    conn.execute("DELETE FROM sub_categories WHERE id = ?", (sub_id,))
    conn.execute("DELETE FROM sub_sub_categories WHERE sub_category_id = ?", (sub_id,))
    conn.commit()
    conn.close()
    remote_control.push_categories_to_cloud()
    flash("Sub-category deleted.", "info")
    return redirect(url_for("products"))


@app.route("/subsubcategories/new", methods=["POST"])
@login_required
@admin_required
def new_subsubcategory():
    sub_category_id = request.form.get("sub_category_id")
    name = request.form.get("name", "").strip()
    icon = request.form.get("icon", "").strip()
    if sub_category_id and name:
        conn = get_connection()
        conn.execute("INSERT INTO sub_sub_categories (sub_category_id, name, icon) VALUES (?, ?, ?)", (sub_category_id, name, icon))
        conn.commit()
        conn.close()
        remote_control.push_categories_to_cloud()
        flash(f'Sub-sub-category "{name}" created.', "success")
    return redirect(url_for("products"))


@app.route("/subsubcategories/edit/<int:subsub_id>", methods=["POST"])
@login_required
@admin_required
def edit_subsubcategory(subsub_id):
    sub_category_id = request.form.get("sub_category_id")
    name = request.form.get("name", "").strip()
    icon = request.form.get("icon", "").strip()
    if name:
        conn = get_connection()
        conn.execute("UPDATE sub_sub_categories SET sub_category_id = ?, name = ?, icon = ? WHERE id = ?", (sub_category_id, name, icon, subsub_id))
        conn.commit()
        conn.close()
        remote_control.push_categories_to_cloud()
        flash(f'Sub-sub-category "{name}" updated.', "success")
    return redirect(url_for("products"))


@app.route("/subsubcategories/delete/<int:subsub_id>", methods=["POST"])
@login_required
@admin_required
def delete_subsubcategory(subsub_id):
    conn = get_connection()
    conn.execute("DELETE FROM sub_sub_categories WHERE id = ?", (subsub_id,))
    conn.commit()
    conn.close()
    remote_control.push_categories_to_cloud()
    flash("Sub-sub-category deleted.", "info")
    return redirect(url_for("products"))


@app.route("/brands/new", methods=["POST"])
@login_required
@admin_required
def add_brand():
    name = request.form.get("name", "").strip()
    if name:
        try:
            conn = get_connection()
            conn.execute("INSERT INTO brands (name) VALUES (?)", (name,))
            conn.commit()
            conn.close()
            remote_control.push_brands_to_cloud()
            flash(f'Brand "{name}" added.', "success")
        except Exception as e:
            flash(f"Could not add brand: {e}", "error")
    return redirect(url_for("products"))


@app.route("/brands/edit/<int:brand_id>", methods=["POST"])
@login_required
@admin_required
def edit_brand(brand_id):
    name = request.form.get("name", "").strip()
    if name:
        try:
            conn = get_connection()
            conn.execute("UPDATE brands SET name = ? WHERE id = ?", (name, brand_id))
            conn.commit()
            conn.close()
            remote_control.push_brands_to_cloud()
            flash(f'Brand updated to "{name}".', "success")
        except Exception as e:
            flash(f"Could not update brand: {e}", "error")
    return redirect(url_for("products"))


@app.route("/brands/delete/<int:brand_id>", methods=["POST"])
@login_required
@admin_required
def delete_brand(brand_id):
    conn = get_connection()
    conn.execute("DELETE FROM brands WHERE id = ?", (brand_id,))
    conn.commit()
    conn.close()
    remote_control.push_brands_to_cloud()
    flash("Brand deleted.", "info")
    return redirect(url_for("products"))


@app.route("/api/brands", methods=["GET"])
def api_brands():
    conn = get_connection()
    brands = conn.execute("SELECT * FROM brands ORDER BY name").fetchall()
    conn.close()
    return jsonify([dict(b) for b in brands])


@app.route("/api/categories/tree", methods=["GET"])
def api_categories_tree():
    conn = get_connection()
    cat_list = get_categories_tree_data(conn)
    conn.close()
    return jsonify(cat_list)


@app.route("/offers", methods=["GET"])
@login_required
@admin_required
def offers_page():
    conn = get_connection()
    all_products = [dict(p) for p in conn.execute("SELECT * FROM products ORDER BY name").fetchall()]
    offer_products = [dict(p) for p in conn.execute("""
        SELECT p.*, c.name AS category_name
        FROM products p
        LEFT JOIN categories c ON p.category_id = c.id
        WHERE p.is_offer = 1 OR p.is_promotion = 1 OR p.offer_type = 'bogo'
        ORDER BY p.id DESC
    """).fetchall()]
    categories = [dict(c) for c in conn.execute("SELECT * FROM categories ORDER BY name").fetchall()]
    sub_categories = [dict(s) for s in conn.execute("SELECT * FROM sub_categories ORDER BY name").fetchall()]
    sub_sub_categories = [dict(ss) for ss in conn.execute("SELECT * FROM sub_sub_categories ORDER BY name").fetchall()]
    vouchers = [dict(v) for v in conn.execute("SELECT * FROM vouchers ORDER BY id DESC").fetchall()]
    settings = get_all_settings(conn)
    conn.close()
    return render_template(
        "offers.html",
        all_products=all_products,
        offer_products=offer_products,
        categories=categories,
        sub_categories=sub_categories,
        sub_sub_categories=sub_sub_categories,
        vouchers=vouchers,
        settings=settings
    )


@app.route("/vouchers/new", methods=["POST"])
@login_required
@admin_required
def new_voucher():
    code = request.form.get("code", "").strip().upper()
    target_type = request.form.get("target_type", "product_discount").strip()
    discount_type = request.form.get("discount_type", "percentage").strip()
    discount_value = float(request.form.get("discount_value") or 0)
    discount_base = request.form.get("discount_base", "sell_price").strip()
    expiry_date = request.form.get("expiry_date", "").strip()
    scope_type = request.form.get("scope_type", "all").strip()
    scope_id = request.form.get("scope_id") or None
    if scope_id:
        scope_id = int(scope_id)

    if code and discount_value > 0:
        conn = get_connection()
        try:
            conn.execute("""
                INSERT INTO vouchers (code, target_type, discount_type, discount_value, discount_base, expiry_date, scope_type, scope_id, active, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)
            """, (code, target_type, discount_type, discount_value, discount_base, expiry_date, scope_type, scope_id, datetime.now().isoformat()))
            conn.commit()
            conn.close()
            remote_control.push_vouchers_to_cloud()
            flash(f"Voucher '{code}' created successfully.", "success")
        except Exception as e:
            conn.close()
            flash(f"Could not create voucher: {e}", "error")
    else:
        flash("Please provide a valid voucher code and discount value.", "error")

    return redirect(url_for("offers_page"))
@app.route("/vouchers/<int:voucher_id>/edit", methods=["POST"])
@login_required
@admin_required
def edit_voucher(voucher_id):
    conn = get_connection()
    v = conn.execute("SELECT * FROM vouchers WHERE id = ?", (voucher_id,)).fetchone()
    if not v:
        conn.close()
        flash("Voucher not found.", "error")
        return redirect(url_for("offers_page"))

    code = request.form.get("code", "").strip().upper()
    target_type = request.form.get("target_type", "product_discount").strip()
    discount_type = request.form.get("discount_type", "percentage").strip()
    discount_value = float(request.form.get("discount_value") or 0)
    discount_base = request.form.get("discount_base", "sell_price").strip()
    expiry_date = request.form.get("expiry_date", "").strip()
    scope_type = request.form.get("scope_type", "all").strip()
    scope_id = request.form.get("scope_id") or None
    if scope_id:
        scope_id = int(scope_id)
    active = 1 if request.form.get("active") == "1" else 0

    if code and discount_value > 0:
        try:
            conn.execute("""
                UPDATE vouchers 
                SET code = ?, target_type = ?, discount_type = ?, discount_value = ?, discount_base = ?, 
                    expiry_date = ?, scope_type = ?, scope_id = ?, active = ?
                WHERE id = ?
            """, (code, target_type, discount_type, discount_value, discount_base, expiry_date, scope_type, scope_id, active, voucher_id))
            conn.commit()
            conn.close()
            remote_control.push_vouchers_to_cloud()
            flash(f"Voucher '{code}' updated successfully.", "success")
        except Exception as e:
            conn.close()
            flash(f"Could not update voucher: {e}", "error")
    else:
        conn.close()
        flash("Please provide a valid voucher code and discount value.", "error")
    return redirect(url_for("offers_page"))


@app.route("/vouchers/<int:voucher_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_voucher(voucher_id):
    conn = get_connection()
    v = conn.execute("SELECT code FROM vouchers WHERE id = ?", (voucher_id,)).fetchone()
    code = v["code"] if v else None
    conn.execute("DELETE FROM vouchers WHERE id = ?", (voucher_id,))
    conn.commit()
    conn.close()
    if code:
        remote_control.delete_voucher_from_cloud(code)
    flash("Voucher deleted successfully.", "success")
    return redirect(url_for("offers_page"))


@app.route("/api/vouchers/apply", methods=["POST"])
def api_apply_voucher():
    data = request.get_json() or {}
    code = (data.get("code") or "").strip().upper()
    cart_items = data.get("cart_items") or []
    delivery_charge = float(data.get("delivery_charge") or 60.0)

    if not code:
        return jsonify({"success": False, "message": "Please enter a voucher code."}), 400

    if not cart_items:
        return jsonify({"success": False, "message": "Cart is empty."}), 400

    conn = get_connection()
    v = conn.execute("SELECT * FROM vouchers WHERE code = ? AND active = 1", (code,)).fetchone()
    if not v:
        conn.close()
        return jsonify({"success": False, "message": f"Voucher '{code}' is invalid or expired."}), 400

    today_date = datetime.now().strftime("%Y-%m-%d")
    v_exp = v["expiry_date"] if "expiry_date" in v.keys() else ""
    if v_exp and v_exp < today_date:
        conn.close()
        return jsonify({"success": False, "message": f"Voucher '{code}' expired on {v_exp}."}), 400

    target_type = v["target_type"] if "target_type" in v.keys() else "product_discount"
    discount_base = v["discount_base"] if "discount_base" in v.keys() else "sell_price"
    scope_type = v["scope_type"]
    scope_id = v["scope_id"]
    discount_type = v["discount_type"]
    discount_value = v["discount_value"]

    # Check if cart contains any Combo Package items
    has_combo_package = False
    for item in cart_items:
        p_id = item.get("product_id") or item.get("id")
        p_name = (item.get("product_name") or item.get("name") or "").strip()
        p_unit = (item.get("unit") or "").strip()

        if p_unit == "Combo Package" or p_name.startswith("📦"):
            has_combo_package = True
            break
        if p_id:
            pkg_row = conn.execute("SELECT id FROM packages WHERE id = ?", (p_id,)).fetchone()
            if pkg_row:
                has_combo_package = True
                break

    if has_combo_package:
        conn.close()
        return jsonify({
            "success": False,
            "message": f"কম্বো প্যাকেজ অর্ডারে কুপন/ভাউচার '{code}' প্রযোজ্য নয়। (Voucher '{code}' cannot be applied when a Combo Package is in the cart.)"
        }), 400

    total_eligible_price = 0.0

    for item in cart_items:
        p_id = item.get("product_id")
        qty = int(item.get("quantity") or 1)
        sell_price = float(item.get("price") or 0)
        p_name_raw = (item.get("product_name") or item.get("name") or "").strip()
        p_unit_raw = (item.get("unit") or "").strip()

        if p_unit_raw == "Combo Package" or p_name_raw.startswith("📦"):
            continue

        p = conn.execute("SELECT * FROM products WHERE id = ?", (p_id,)).fetchone()
        if not p:
            continue

        is_eligible = False
        target_name = "Selected Scope"

        if scope_type == "all":
            is_eligible = True
        elif scope_type == "product" and scope_id:
            if p["id"] == scope_id:
                is_eligible = True
            target_name = f"Product '{p['name']}'"
        elif scope_type == "category" and scope_id:
            if p["category_id"] == scope_id:
                is_eligible = True
            cat = conn.execute("SELECT name FROM categories WHERE id = ?", (scope_id,)).fetchone()
            if cat: target_name = f"Category '{cat['name']}'"
        elif scope_type == "sub_category" and scope_id:
            if p["sub_category_id"] == scope_id:
                is_eligible = True
            scat = conn.execute("SELECT name FROM sub_categories WHERE id = ?", (scope_id,)).fetchone()
            if scat: target_name = f"Sub-Category '{scat['name']}'"
        elif scope_type == "sub_sub_category" and scope_id:
            if p["sub_sub_category_id"] == scope_id:
                is_eligible = True
            sscat = conn.execute("SELECT name FROM sub_sub_categories WHERE id = ?", (scope_id,)).fetchone()
            if sscat: target_name = f"Sub-Sub-Category '{sscat['name']}'"

        if not is_eligible:
            conn.close()
            return jsonify({
                "success": False,
                "message": f"Voucher '{code}' is ONLY valid for {target_name}. Product '{p['name']}' in your cart is not eligible for this voucher."
            }), 400

        # Base price calculation (MRP vs Doineek Price)
        if discount_base == "mrp" and p["mrp"] > 0:
            item_base_price = p["mrp"]
        else:
            item_base_price = sell_price

        total_eligible_price += item_base_price * qty

    conn.close()

    if target_type == "delivery_discount":
        if discount_type == "flat":
            discount_amount = min(delivery_charge, discount_value)
        else:
            discount_amount = delivery_charge * (discount_value / 100.0)
        discount_amount = round(discount_amount, 2)
        return jsonify({
            "success": True,
            "target_type": "delivery_discount",
            "code": code,
            "discount_amount": discount_amount,
            "message": f"Delivery Voucher '{code}' applied! Saved TK {discount_amount:.2f} on delivery charge."
        })
    else:
        if discount_type == "flat":
            discount_amount = min(total_eligible_price, discount_value)
        else:
            discount_amount = total_eligible_price * (discount_value / 100.0)
        discount_amount = round(discount_amount, 2)
        return jsonify({
            "success": True,
            "target_type": "product_discount",
            "code": code,
            "discount_amount": discount_amount,
            "discount_base": discount_base,
            "message": f"Voucher '{code}' ({'MRP' if discount_base == 'mrp' else 'Doineek Price'}) applied! Saved TK {discount_amount:.2f}"
        })


@app.route("/offers/save", methods=["POST"])
@login_required
@admin_required
def save_product_offer():
    product_id = request.form.get("product_id")
    offer_title = request.form.get("offer_title", "").strip()
    offer_type = request.form.get("offer_type", "pct").strip()
    offer_value = request.form.get("offer_value", "").strip()
    offer_base = request.form.get("offer_base", "mrp").strip()
    is_offer = 1 if request.form.get("is_offer") == "1" else 0
    is_promotion = 1 if request.form.get("is_promotion") == "1" else 0

    if offer_type == "bogo":
        is_offer = 1
        if not offer_value and offer_title:
            offer_value = offer_title
        elif not offer_title and offer_value:
            offer_title = offer_value
        elif not offer_title and not offer_value:
            offer_title = "Buy 1 Get 1 Free"
            offer_value = "Buy 1 Get 1 Free"

    if product_id:
        conn = get_connection()
        product = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
        if product:
            cost_price = product["cost_price"] or 0
            mrp = product["mrp"] or product["sell_price"] or 0
            base_price = cost_price if offer_base == "cost_price" and cost_price > 0 else mrp
            sell_price = product["sell_price"]
            
            # Recalculate sell_price based on offer_base and offer_type
            if offer_type == "pct" and offer_value.replace('.', '', 1).isdigit() and base_price > 0:
                pct = float(offer_value)
                sell_price = max(0, base_price * (1.0 - pct / 100.0))
            elif offer_type == "flat" and offer_value.replace('.', '', 1).isdigit() and base_price > 0:
                flat_amt = float(offer_value)
                sell_price = max(0, base_price - flat_amt)

            conn.execute("""
                UPDATE products
                SET is_offer = ?, offer_title = ?, offer_type = ?, offer_value = ?, offer_base = ?, is_promotion = ?, sell_price = ?
                WHERE id = ?
            """, (is_offer, offer_title, offer_type, offer_value, offer_base, is_promotion, sell_price, product_id))
            conn.commit()
            remote_control.push_product_to_cloud(product_id)
            flash(f'Offer saved for "{product["name"]}".', "success")
        conn.close()
    return redirect(url_for("offers_page"))


@app.route("/offers/remove/<int:product_id>", methods=["POST"])
@login_required
@admin_required
def remove_product_offer(product_id):
    conn = get_connection()
    conn.execute("""
        UPDATE products
        SET is_offer = 0, is_promotion = 0, offer_title = '', offer_type = '', offer_value = '', offer_base = 'mrp'
        WHERE id = ?
    """, (product_id,))
    conn.commit()
    remote_control.push_product_to_cloud(product_id)
    conn.close()
    flash("Offer removed from product.", "info")
    return redirect(url_for("offers_page"))


@app.route("/offers/interval", methods=["POST"])
@login_required
@admin_required
def save_offer_interval():
    sec = request.form.get("promo_interval_sec", "2").strip()
    conn = get_connection()
    update_settings(conn, {"promo_interval_sec": sec})
    conn.commit()
    conn.close()
    flash("App banner slide interval updated.", "success")
    return redirect(url_for("offers_page"))


@app.route("/api/promotions", methods=["GET"])
def api_promotions():
    conn = get_connection()
    s = get_all_settings(conn)
    interval_sec = int(s.get("promo_interval_sec") or 2)
    rows = conn.execute("""
        SELECT p.*, c.name AS category_name
        FROM products p
        LEFT JOIN categories c ON p.category_id = c.id
        WHERE p.is_promotion = 1 OR p.is_offer = 1 OR p.offer_type = 'bogo'
        ORDER BY p.id DESC
    """).fetchall()
    conn.close()
    return jsonify({
        "interval_sec": interval_sec,
        "promotions": [dict(r) for r in rows]
    })


@app.route("/api/settings/policies", methods=["GET"])
def api_policies():
    conn = get_connection()
    s = get_all_settings(conn)
    conn.close()
    return jsonify({
        "about_us": s.get("policy_about_us") or "Welcome to DOINEEK Supershop! Your trusted daily online grocery & retail destination.",
        "blog": s.get("policy_blog") or "Latest updates and grocery shopping tips for a healthier lifestyle.",
        "cookies_policy": s.get("policy_cookies") or "We use essential cookies to ensure seamless shopping and cart persistence.",
        "return_refund_policy": s.get("policy_return_refund") or "7-day easy return & replacement policy for damaged or incorrect goods.",
        "privacy_policy": s.get("policy_privacy") or "Your personal data is encrypted and never shared with third parties.",
        "terms_conditions": s.get("policy_terms") or "By placing an order, you agree to our standard terms of online retail delivery.",
        "warranty_policy": s.get("policy_warranty") or "Official brand warranty applies to all electronic & appliance products.",
        "help_center": s.get("policy_help_center") or f"For 24/7 customer support, call {s.get('customer_support_phone') or s.get('shop_phone') or 'our helpline'}.",
    })


# ===========================================================================
# User & Staff Management (Admin Only)
# ===========================================================================

@app.route("/users", methods=["GET", "POST"])
@login_required
@admin_required
def users():
    conn = get_connection()
    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        role = request.form["role"]
        try:
            conn.execute(
                "INSERT INTO users (username, password_hash, role, created_at) VALUES (?, ?, ?, ?)",
                (username, generate_password_hash(password), role, datetime.now().isoformat())
            )
            conn.commit()
            remote_control.push_users_to_cloud()
            flash(f'User "{username}" created.', "success")
        except Exception as e:
            flash(f"Could not create user: {e}", "error")
    rows = conn.execute("SELECT id, username, role, created_at FROM users ORDER BY username").fetchall()
    conn.close()
    return render_template("users.html", users=rows)


@app.route("/users/<int:user_id>/password", methods=["POST"])
@login_required
@admin_required
def change_user_password(user_id):
    new_password = request.form["new_password"].strip()
    if not new_password or len(new_password) < 4:
        flash("Password must be at least 4 characters long.", "error")
        return redirect(url_for("users"))
    
    conn = get_connection()
    conn.execute(
        "UPDATE users SET password_hash = ? WHERE id = ?",
        (generate_password_hash(new_password), user_id)
    )
    conn.commit()
    conn.close()
    remote_control.push_users_to_cloud()
    flash("Password updated successfully.", "success")
    return redirect(url_for("users"))


@app.route("/users/<int:user_id>/edit", methods=["POST"])
@login_required
@admin_required
def edit_user(user_id):
    username = request.form.get("username", "").strip()
    role = request.form.get("role", "").strip()
    new_password = request.form.get("password", "").strip()

    conn = get_connection()
    if username and role in ['admin', 'cashier', 'delivery']:
        if new_password:
            conn.execute("UPDATE users SET username = ?, role = ?, password_hash = ? WHERE id = ?",
                         (username, role, generate_password_hash(new_password), user_id))
        else:
            conn.execute("UPDATE users SET username = ?, role = ? WHERE id = ?", (username, role, user_id))
        conn.commit()
        remote_control.push_users_to_cloud()
        flash(f"Staff user '{username}' updated successfully.", "success")
    conn.close()
    return redirect(url_for("users"))


@app.route("/users/<int:user_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_user(user_id):
    if user_id == session.get("user_id"):
        flash("You cannot delete your own active admin account.", "error")
        return redirect(url_for("users"))

    conn = get_connection()
    conn.execute("DELETE FROM users WHERE id = ?", (user_id,))
    conn.commit()
    conn.close()
    remote_control.push_users_to_cloud()
    flash("Staff account deleted successfully.", "success")
    return redirect(url_for("users"))


# ===========================================================================
# Advanced Financial Reports & Custom Ledger (Admin Only)
# ===========================================================================

@app.route("/reports", methods=["GET"])
@login_required
@admin_required
def reports():
    conn = get_connection()
    period = request.args.get("period", "monthly")
    today = date.today()
    today_str = today.isoformat()

    if period == "daily":
        date_filter = f"date(created_at) = '{today_str}'"
        ledger_filter = f"date(entry_date) = '{today_str}'"
    elif period == "weekly":
        start = (today - timedelta(days=6)).isoformat()
        date_filter = f"date(created_at) >= '{start}'"
        ledger_filter = f"date(entry_date) >= '{start}'"
    elif period == "3_monthly":
        start = (today - timedelta(days=89)).isoformat()
        date_filter = f"date(created_at) >= '{start}'"
        ledger_filter = f"date(entry_date) >= '{start}'"
    elif period == "6_monthly":
        start = (today - timedelta(days=179)).isoformat()
        date_filter = f"date(created_at) >= '{start}'"
        ledger_filter = f"date(entry_date) >= '{start}'"
    elif period == "quarterly":
        quarter_start_month = ((today.month - 1) // 3) * 3 + 1
        start = date(today.year, quarter_start_month, 1).isoformat()
        date_filter = f"date(created_at) >= '{start}'"
        ledger_filter = f"date(entry_date) >= '{start}'"
    elif period == "yearly":
        date_filter = f"strftime('%Y', created_at) = '{today_str[:4]}'"
        ledger_filter = f"strftime('%Y', entry_date) = '{today_str[:4]}'"
    elif period == "all":
        date_filter = "1=1"
        ledger_filter = "1=1"
    else:  # default monthly
        period = "monthly"
        date_filter = f"strftime('%Y-%m', created_at) = '{today_str[:7]}'"
        ledger_filter = f"strftime('%Y-%m', entry_date) = '{today_str[:7]}'"

    # 1. Offline POS counter sales summary
    offline_sales_summary = conn.execute(f"""
        SELECT 
            COALESCE(SUM(rounded_total), 0) AS revenue,
            COALESCE(SUM(vat_amount), 0) AS vat,
            COALESCE(SUM(saved_amount), 0) AS discounts,
            COUNT(id) AS tx_count
        FROM sales WHERE (channel IS NULL OR channel != 'Online') AND {date_filter}
    """).fetchone()

    # 2. Online orders summary
    online_orders_summary = conn.execute(f"""
        SELECT 
            COUNT(*) AS tx_count,
            COALESCE(SUM(total_amount), 0) AS revenue
        FROM online_orders WHERE {date_filter}
    """).fetchone()

    # 3. Offline COGS
    offline_cogs_row = conn.execute(f"""
        SELECT COALESCE(SUM(si.quantity * si.cost_price), 0) AS total_cogs
        FROM sale_items si
        JOIN sales s ON si.sale_id = s.id
        WHERE (s.channel IS NULL OR s.channel != 'Online') AND {date_filter.replace('created_at', 's.created_at')}
    """).fetchone()

    # 4. Online COGS
    online_cogs_row = conn.execute(f"""
        SELECT COALESCE(SUM(oi.quantity * COALESCE(p.cost_price, oi.unit_price * 0.7)), 0) AS total_cogs
        FROM online_order_items oi
        JOIN online_orders o ON oi.order_id = o.id
        LEFT JOIN products p ON oi.product_id = p.id
        WHERE {date_filter.replace('created_at', 'o.created_at')}
    """).fetchone()

    pos_rev = float(offline_sales_summary["revenue"])
    online_rev = float(online_orders_summary["revenue"])
    pos_cnt = int(offline_sales_summary["tx_count"])
    online_cnt = int(online_orders_summary["tx_count"])
    pos_cogs = float(offline_cogs_row["total_cogs"])
    online_cogs = float(online_cogs_row["total_cogs"])

    # 5. Product Packages Sales (POS + Online)
    pos_pkg = conn.execute(f"""
        SELECT 
            COALESCE(SUM(si.quantity * si.unit_price), 0) AS revenue,
            COALESCE(SUM(si.quantity * si.cost_price), 0) AS cogs,
            COALESCE(SUM(si.quantity), 0) AS qty_sold,
            COUNT(DISTINCT si.sale_id) AS tx_count
        FROM sale_items si
        JOIN sales s ON si.sale_id = s.id
        JOIN products p ON si.product_id = p.id
        WHERE (p.unit LIKE '%package%' OR p.unit LIKE '%combo%' OR p.name LIKE '%📦%' OR p.name LIKE '%package%' OR p.name LIKE '%combo%')
        AND {date_filter.replace('created_at', 's.created_at')}
    """).fetchone()

    online_pkg = conn.execute(f"""
        SELECT 
            COALESCE(SUM(oi.quantity * oi.unit_price), 0) AS revenue,
            COALESCE(SUM(oi.quantity * COALESCE(p.cost_price, oi.unit_price * 0.7)), 0) AS cogs,
            COALESCE(SUM(oi.quantity), 0) AS qty_sold,
            COUNT(DISTINCT oi.order_id) AS tx_count
        FROM online_order_items oi
        JOIN online_orders o ON oi.order_id = o.id
        LEFT JOIN products p ON oi.product_id = p.id
        WHERE (oi.product_name LIKE '📦%' OR oi.product_name LIKE '%package%' OR oi.product_name LIKE '%combo%' OR (p.unit IS NOT NULL AND (p.unit LIKE '%package%' OR p.unit LIKE '%combo%')))
        AND {date_filter.replace('created_at', 'o.created_at')}
    """).fetchone()

    pkg_rev = float(pos_pkg["revenue"]) + float(online_pkg["revenue"])
    pkg_cogs = float(pos_pkg["cogs"]) + float(online_pkg["cogs"])
    pkg_tx = int(pos_pkg["tx_count"]) + int(online_pkg["tx_count"])
    pkg_qty = int(pos_pkg["qty_sold"]) + int(online_pkg["qty_sold"])

    # 6. Offers & Promotions Sales (POS + Online)
    pos_off = conn.execute(f"""
        SELECT 
            COALESCE(SUM(si.quantity * si.unit_price), 0) AS revenue,
            COALESCE(SUM(si.quantity * si.cost_price), 0) AS cogs,
            COALESCE(SUM(si.quantity), 0) AS qty_sold,
            COUNT(DISTINCT si.sale_id) AS tx_count
        FROM sale_items si
        JOIN sales s ON si.sale_id = s.id
        JOIN products p ON si.product_id = p.id
        WHERE (
            p.is_offer = 1 OR p.is_promotion = 1 OR (p.offer_type != '' AND p.offer_type IS NOT NULL)
        )
        AND {date_filter.replace('created_at', 's.created_at')}
    """).fetchone()

    online_off = conn.execute(f"""
        SELECT 
            COALESCE(SUM(oi.quantity * oi.unit_price), 0) AS revenue,
            COALESCE(SUM(oi.quantity * COALESCE(p.cost_price, oi.unit_price * 0.7)), 0) AS cogs,
            COALESCE(SUM(oi.quantity), 0) AS qty_sold,
            COUNT(DISTINCT oi.order_id) AS tx_count
        FROM online_order_items oi
        JOIN online_orders o ON oi.order_id = o.id
        JOIN products p ON oi.product_id = p.id
        WHERE (
            p.is_offer = 1 OR p.is_promotion = 1 OR (p.offer_type != '' AND p.offer_type IS NOT NULL)
        )
        AND {date_filter.replace('created_at', 'o.created_at')}
    """).fetchone()

    off_rev = float(pos_off["revenue"]) + float(online_off["revenue"])
    off_cogs = float(pos_off["cogs"]) + float(online_off["cogs"])
    off_tx = int(pos_off["tx_count"]) + int(online_off["tx_count"])
    off_qty = int(pos_off["qty_sold"]) + int(online_off["qty_sold"])

    # Ledger entries for this period
    ledger_entries = conn.execute(f"""
        SELECT * FROM ledger_entries
        WHERE {ledger_filter}
        ORDER BY entry_date DESC, id DESC
    """).fetchall()

    def get_ledger_sums(segment_name):
        if segment_name == 'all':
            inc = sum(float(r['amount']) for r in ledger_entries if r['entry_type'] == 'income')
            exp = sum(float(r['amount']) for r in ledger_entries if r['entry_type'] == 'expense')
        else:
            inc = sum(float(r['amount']) for r in ledger_entries if r['entry_type'] == 'income' and (r['target_segment'] or 'all') == segment_name)
            exp = sum(float(r['amount']) for r in ledger_entries if r['entry_type'] == 'expense' and (r['target_segment'] or 'all') == segment_name)
        return inc, exp

    all_inc, all_exp = get_ledger_sums('all')
    on_inc, on_exp = get_ledger_sums('online')
    pos_inc, pos_exp = get_ledger_sums('offline')
    pkg_inc, pkg_exp = get_ledger_sums('packages')
    off_inc, off_exp = get_ledger_sums('offers')

    # Overall Summary
    total_rev = pos_rev + online_rev
    total_cogs = pos_cogs + online_cogs
    total_tx = pos_cnt + online_cnt
    overall_gross = total_rev - total_cogs
    overall_net = (overall_gross + all_inc) - all_exp

    # Online Summary
    online_gross = online_rev - online_cogs
    online_net = (online_gross + on_inc) - on_exp

    # Offline Summary
    offline_gross = pos_rev - pos_cogs
    offline_net = (offline_gross + pos_inc) - pos_exp

    # Packages Summary
    pkg_gross = pkg_rev - pkg_cogs
    pkg_net = (pkg_gross + pkg_inc) - pkg_exp

    # Offers Summary
    off_gross = off_rev - off_cogs
    off_net = (off_gross + off_inc) - off_exp

    sold_subquery = f"""
        SELECT si.product_id AS product_id,
               SUM(si.quantity) AS qty_sold,
               SUM(si.quantity * si.unit_price) AS revenue,
               SUM(si.quantity * si.cost_price) AS cogs_amt
        FROM sale_items si
        JOIN sales s ON si.sale_id = s.id
        WHERE {date_filter.replace('created_at', 's.created_at')}
        GROUP BY si.product_id
    """
    product_performance = conn.execute(f"""
        SELECT p.id, p.name, p.sku, p.stock_qty,
               COALESCE(sold.qty_sold, 0) AS qty_sold,
               COALESCE(sold.revenue, 0) AS revenue,
               COALESCE(sold.cogs_amt, 0) AS cogs_amt,
               (COALESCE(sold.revenue, 0) - COALESCE(sold.cogs_amt, 0)) AS profit
        FROM products p
        LEFT JOIN ({sold_subquery}) sold ON sold.product_id = p.id
        ORDER BY qty_sold DESC, revenue DESC
    """).fetchall()

    total_units_sold = sum(row["qty_sold"] for row in product_performance) or 1
    top_products = [row for row in product_performance if row["qty_sold"] > 0][:8]
    dead_stock = [row for row in product_performance if row["qty_sold"] == 0 and row["stock_qty"] > 0][:8]
    slow_movers = [
        row for row in product_performance
        if row["qty_sold"] > 0 and row["stock_qty"] > 0
    ]
    slow_movers = sorted(slow_movers, key=lambda r: r["qty_sold"])[:8]
    max_qty_sold = max((row["qty_sold"] for row in product_performance), default=0) or 1

    conn.close()
    return render_template(
        "reports.html",
        period=period,
        revenue=total_rev,
        cogs=total_cogs,
        gross_profit=overall_gross,
        other_income=all_inc,
        other_expenses=all_exp,
        net_profit=overall_net,
        ledger_entries=ledger_entries,
        top_products=top_products,
        slow_movers=slow_movers,
        dead_stock=dead_stock,
        total_units_sold=total_units_sold,
        max_qty_sold=max_qty_sold,
        tx_count=total_tx,
        online_summary={
            "tx_count": online_cnt,
            "revenue": online_rev,
            "cogs": online_cogs,
            "gross_profit": online_gross,
            "income": on_inc,
            "expense": on_exp,
            "net_profit": online_net
        },
        offline_summary={
            "tx_count": pos_cnt,
            "revenue": pos_rev,
            "cogs": pos_cogs,
            "gross_profit": offline_gross,
            "income": pos_inc,
            "expense": pos_exp,
            "net_profit": offline_net
        },
        packages_summary={
            "tx_count": pkg_tx,
            "qty_sold": pkg_qty,
            "revenue": pkg_rev,
            "cogs": pkg_cogs,
            "gross_profit": pkg_gross,
            "income": pkg_inc,
            "expense": pkg_exp,
            "net_profit": pkg_net
        },
        offers_summary={
            "tx_count": off_tx,
            "qty_sold": off_qty,
            "revenue": off_rev,
            "cogs": off_cogs,
            "gross_profit": off_gross,
            "income": off_inc,
            "expense": off_exp,
            "net_profit": off_net
        }
    )


@app.route("/reports/api/product_search")
@login_required
@admin_required
def reports_api_product_search():
    q = request.args.get("q", "").strip()
    if not q:
        return jsonify([])
    conn = get_connection()
    like = f"%{q}%"
    rows = conn.execute("""
        SELECT p.id, p.name, p.sku, p.image_url, p.stock_qty, p.sell_price, p.cost_price, p.unit, c.name AS category_name
        FROM products p
        LEFT JOIN categories c ON p.category_id = c.id
        WHERE p.name LIKE ? OR p.sku LIKE ? OR p.id = ?
        ORDER BY p.name ASC LIMIT 15
    """, (like, like, q if q.isdigit() else -1)).fetchall()
    conn.close()
    
    result = []
    for r in rows:
        img_parts = split_image_urls(r["image_url"])
        thumb = img_parts[0] if img_parts else "/static/images/logo.png"
        result.append({
            "id": r["id"],
            "name": r["name"],
            "sku": r["sku"],
            "category": r["category_name"] or "General",
            "stock_qty": r["stock_qty"],
            "sell_price": float(r["sell_price"] or 0),
            "cost_price": float(r["cost_price"] or 0),
            "unit": r["unit"] or "Piece",
            "image": thumb
        })
    return jsonify(result)


@app.route("/reports/api/product_analysis")
@login_required
@admin_required
def reports_api_product_analysis():
    product_id = request.args.get("product_id", type=int)
    period = request.args.get("period", "monthly")
    if not product_id:
        return jsonify({"error": "Product ID required"}), 400

    conn = get_connection()
    prod = conn.execute("""
        SELECT p.*, c.name AS category_name, b.name AS brand_name
        FROM products p
        LEFT JOIN categories c ON p.category_id = c.id
        LEFT JOIN brands b ON p.brand = b.name
        WHERE p.id = ?
    """, (product_id,)).fetchone()
    if not prod:
        conn.close()
        return jsonify({"error": "Product not found"}), 404

    today = date.today()
    today_str = today.isoformat()

    if period == "daily":
        date_filter = f"date(created_at) = '{today_str}'"
        prev_filter = f"date(created_at) = '{(today - timedelta(days=1)).isoformat()}'"
    elif period == "weekly":
        start = (today - timedelta(days=6)).isoformat()
        date_filter = f"date(created_at) >= '{start}'"
        prev_filter = f"date(created_at) >= '{(today - timedelta(days=13)).isoformat()}' AND date(created_at) < '{start}'"
    elif period == "3_monthly":
        start = (today - timedelta(days=89)).isoformat()
        date_filter = f"date(created_at) >= '{start}'"
        prev_filter = f"date(created_at) >= '{(today - timedelta(days=179)).isoformat()}' AND date(created_at) < '{start}'"
    elif period == "yearly":
        date_filter = f"strftime('%Y', created_at) = '{today_str[:4]}'"
        prev_filter = f"strftime('%Y', created_at) = '{str(today.year - 1)}'"
    elif period == "all":
        date_filter = "1=1"
        prev_filter = "1=0"
    else:  # monthly
        period = "monthly"
        date_filter = f"strftime('%Y-%m', created_at) = '{today_str[:7]}'"
        prev_month = (today.replace(day=1) - timedelta(days=1)).strftime('%Y-%m')
        prev_filter = f"strftime('%Y-%m', created_at) = '{prev_month}'"

    # POS Sales for this product
    pos_data = conn.execute(f"""
        SELECT 
            COALESCE(SUM(si.quantity), 0) AS qty_sold,
            COALESCE(SUM(si.quantity * si.unit_price), 0) AS revenue,
            COALESCE(SUM(si.quantity * si.cost_price), 0) AS cogs,
            COUNT(DISTINCT si.sale_id) AS tx_count
        FROM sale_items si
        JOIN sales s ON si.sale_id = s.id
        WHERE si.product_id = ? AND (s.channel IS NULL OR s.channel != 'Online') AND {date_filter.replace('created_at', 's.created_at')}
    """, (product_id,)).fetchone()

    # Online Sales for this product
    online_data = conn.execute(f"""
        SELECT 
            COALESCE(SUM(oi.quantity), 0) AS qty_sold,
            COALESCE(SUM(oi.quantity * oi.unit_price), 0) AS revenue,
            COALESCE(SUM(oi.quantity * COALESCE(?, oi.unit_price * 0.7)), 0) AS cogs,
            COUNT(DISTINCT oi.order_id) AS tx_count
        FROM online_order_items oi
        JOIN online_orders o ON oi.order_id = o.id
        WHERE oi.product_id = ? AND {date_filter.replace('created_at', 'o.created_at')}
    """, (prod["cost_price"], product_id)).fetchone()

    pos_qty = int(pos_data["qty_sold"])
    online_qty = int(online_data["qty_sold"])
    total_qty = pos_qty + online_qty

    pos_rev = float(pos_data["revenue"])
    online_rev = float(online_data["revenue"])
    total_rev = pos_rev + online_rev

    pos_cogs = float(pos_data["cogs"])
    online_cogs = float(online_data["cogs"])
    total_cogs = pos_cogs + online_cogs

    gross_profit = total_rev - total_cogs
    profit_margin_pct = round((gross_profit / total_rev * 100), 1) if total_rev > 0 else 0.0
    profit_factor = round((total_rev / total_cogs), 2) if total_cogs > 0 else (round(total_rev, 2) if total_rev > 0 else 1.0)
    roi_pct = round((gross_profit / total_cogs * 100), 1) if total_cogs > 0 else 0.0

    # Daily trends (last 7 data points)
    daily_trends = conn.execute("""
        SELECT date(s.created_at) as sale_date,
               SUM(si.quantity) as qty,
               SUM(si.quantity * si.unit_price) as rev,
               (SUM(si.quantity * si.unit_price) - SUM(si.quantity * si.cost_price)) as prof
        FROM sale_items si
        JOIN sales s ON si.sale_id = s.id
        WHERE si.product_id = ? AND s.created_at >= date('now', '-30 days')
        GROUP BY date(s.created_at)
        ORDER BY sale_date ASC LIMIT 30
    """, (product_id,)).fetchall()

    trends_list = [
        {"date": r["sale_date"], "qty": r["qty"], "revenue": float(r["rev"]), "profit": float(r["prof"])}
        for r in daily_trends
    ]

    img_parts = split_image_urls(prod["image_url"])
    thumb = img_parts[0] if img_parts else "/static/images/logo.png"

    conn.close()
    return jsonify({
        "product": {
            "id": prod["id"],
            "name": prod["name"],
            "sku": prod["sku"],
            "brand": prod["brand_name"] or prod["brand"] or "Generic",
            "category": prod["category_name"] or "General",
            "unit": prod["unit"] or "Piece",
            "stock_qty": prod["stock_qty"],
            "stock_value": round(prod["stock_qty"] * (prod["cost_price"] or 0), 2),
            "sell_price": float(prod["sell_price"] or 0),
            "cost_price": float(prod["cost_price"] or 0),
            "mrp": float(prod["mrp"] or 0),
            "image": thumb
        },
        "metrics": {
            "period": period,
            "total_qty_sold": total_qty,
            "pos_qty_sold": pos_qty,
            "online_qty_sold": online_qty,
            "total_revenue": total_rev,
            "pos_revenue": pos_rev,
            "online_revenue": online_rev,
            "total_cogs": total_cogs,
            "gross_profit": gross_profit,
            "profit_margin_pct": profit_margin_pct,
            "profit_factor": profit_factor,
            "roi_pct": roi_pct,
            "total_invoices": int(pos_data["tx_count"]) + int(online_data["tx_count"])
        },
        "trends": trends_list
    })


@app.route("/reports/entry/new", methods=["POST"])
@login_required
@admin_required
def add_ledger_entry():
    title = request.form["title"].strip()
    entry_type = request.form["entry_type"]
    amount = float(request.form.get("amount") or 0)
    entry_date = request.form["entry_date"] or date.today().isoformat()
    target_segment = request.form.get("target_segment", "all").strip()

    conn = get_connection()
    conn.execute(
        "INSERT INTO ledger_entries (entry_type, title, amount, entry_date, created_at, target_segment) VALUES (?, ?, ?, ?, ?, ?)",
        (entry_type, title, amount, entry_date, datetime.now().isoformat(), target_segment)
    )
    conn.commit()
    conn.close()
    flash(f"Added {entry_type.upper()}: {title} (TK {amount:,.2f})", "success")
    return redirect(url_for("reports"))


@app.route("/reports/entry/<int:entry_id>/edit", methods=["POST"])
@login_required
@admin_required
def edit_ledger_entry(entry_id):
    title = request.form["title"].strip()
    entry_type = request.form["entry_type"]
    amount = float(request.form.get("amount") or 0)
    entry_date = request.form["entry_date"]
    target_segment = request.form.get("target_segment", "all").strip()

    conn = get_connection()
    conn.execute(
        "UPDATE ledger_entries SET title=?, entry_type=?, amount=?, entry_date=?, target_segment=? WHERE id=?",
        (title, entry_type, amount, entry_date, target_segment, entry_id)
    )
    conn.commit()
    conn.close()
    flash("Entry updated successfully.", "success")
    return redirect(url_for("reports"))


@app.route("/reports/entry/<int:entry_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_ledger_entry(entry_id):
    conn = get_connection()
    conn.execute("DELETE FROM ledger_entries WHERE id=?", (entry_id,))
    conn.commit()
    conn.close()
    flash("Entry deleted successfully.", "success")
    return redirect(url_for("reports"))


# ===========================================================================
# Online Orders & Delivery Areas (Web Admin)
# ===========================================================================

@app.route("/online_orders")
@login_required
def online_orders():
    conn = get_connection()
    orders = conn.execute("SELECT * FROM online_orders ORDER BY id DESC").fetchall()
    orders_list = []
    for ord_row in orders:
        items = conn.execute("SELECT * FROM online_order_items WHERE order_id = ?", (ord_row["id"],)).fetchall()
        o_dict = dict(ord_row)
        item_list = []
        for i in items:
            it_dict = dict(i)
            p_id = it_dict.get("product_id")
            p_name = (it_dict.get("product_name") or "").strip()
            
            pkg = None
            is_combo_tag = p_name.startswith("📦") or it_dict.get("unit") == "Combo Package"
            is_regular_prod = conn.execute("SELECT id FROM products WHERE id = ?", (p_id,)).fetchone() if p_id else None

            if not is_regular_prod or is_combo_tag:
                if p_id:
                    pkg = conn.execute("SELECT * FROM packages WHERE id = ?", (p_id,)).fetchone()
                if not pkg and is_combo_tag:
                    clean_pname = p_name.replace("📦", "").split("(")[0].strip()
                    pkg = conn.execute("SELECT * FROM packages WHERE name = ?", (clean_pname,)).fetchone()

            if pkg and "(" not in p_name:
                p_items = conn.execute("""
                    SELECT pi.*, p.sku, p.name AS product_name
                    FROM package_items pi JOIN products p ON pi.product_id = p.id
                    WHERE pi.package_id = ?
                """, (pkg["id"],)).fetchall()
                details = []
                sl = 1
                for pi in p_items:
                    details.append(f"{pi['sku'] or 'SKU'} {pi['product_name']} SL:{sl}")
                    sl += 1
                if details:
                    it_dict["product_name"] = f"{pkg['name']} ({', '.join(details)})"

            item_list.append(it_dict)

        o_dict["items"] = item_list
        o_dict["order_items"] = item_list
        orders_list.append(o_dict)
    riders = conn.execute("SELECT * FROM users WHERE role = 'delivery' AND is_active = 1").fetchall()
    conn.close()
    return render_template("online_orders.html", orders=orders_list, riders=riders)


@app.route("/online_orders/<int:order_id>/assign_rider", methods=["POST"])
@login_required
def assign_online_order_rider(order_id):
    rider_id = request.form.get("rider_id", type=int)
    conn = get_connection()
    order = conn.execute("SELECT * FROM online_orders WHERE id = ?", (order_id,)).fetchone()
    if not order:
        conn.close()
        flash("Order not found.", "error")
        return redirect(url_for("online_orders"))

    rider_name = ""
    rider_phone = ""
    if rider_id:
        rider = conn.execute("SELECT * FROM users WHERE id = ? AND role = 'delivery'", (rider_id,)).fetchone()
        if rider:
            rider_name = rider["full_name"] if rider["full_name"] else rider["username"]
            rider_phone = rider["username"]

    conn.execute(
        "UPDATE online_orders SET order_status = 'verified', assigned_rider_id = ?, assigned_rider_name = ?, assigned_rider_phone = ?, updated_at = ? WHERE id = ?",
        (rider_id or 0, rider_name, rider_phone, datetime.now().isoformat(), order_id)
    )
    deduct_online_order_stock(conn, order)
    conn.commit()
    conn.close()

    remote_control.push_online_order_to_cloud(order_id)
    if rider_name:
        flash(f"Order #{order['order_number']} assigned to Delivery Rider '{rider_name}' ({rider_phone}) and verified!", "success")
    else:
        flash(f"Order #{order['order_number']} verified successfully!", "success")
    return redirect(url_for("online_orders"))


@app.route("/api/rider/accept-order", methods=["POST"])
def api_rider_accept_order():
    data = request.json or {}
    order_id = data.get("order_id")
    rider_name = data.get("rider_name", "").strip()
    rider_phone = normalize_phone(data.get("rider_phone", ""))

    if not order_id or not rider_phone:
        return jsonify({"success": False, "message": "Order ID and Rider Phone are required."}), 400

    conn = get_connection()
    order = conn.execute("SELECT * FROM online_orders WHERE id = ?", (order_id,)).fetchone()
    if not order:
        conn.close()
        return jsonify({"success": False, "message": "Order not found."}), 400

    conn.execute(
        "UPDATE online_orders SET order_status = 'verified', assigned_rider_name = ?, assigned_rider_phone = ?, updated_at = ? WHERE id = ?",
        (rider_name if rider_name else rider_phone, rider_phone, datetime.now().isoformat(), order_id)
    )
    deduct_online_order_stock(conn, order)
    conn.commit()
    conn.close()

    remote_control.push_online_order_to_cloud(order_id)
    return jsonify({
        "success": True,
        "message": f"Order #{order['order_number']} accepted successfully! Customer has been notified."
    })


@app.route("/api/rider/update-order-status", methods=["POST"])
def api_rider_update_order_status():
    data = request.json or {}
    order_id = data.get("order_id")
    status = data.get("status", "").strip()
    otp = data.get("otp", "").strip()

    if not order_id or not status:
        return jsonify({"success": False, "message": "Order ID and status are required."}), 400

    conn = get_connection()
    order = conn.execute("SELECT * FROM online_orders WHERE id = ?", (order_id,)).fetchone()
    if not order:
        conn.close()
        return jsonify({"success": False, "message": "Order not found."}), 400

    if status == "delivered":
        if not otp or order["delivery_otp"] != otp:
            conn.close()
            return jsonify({"success": False, "message": "Invalid OTP code. Please enter the correct 4-digit OTP from customer app."}), 400

    if status in ["verified", "packed", "on_the_way", "delivered", "cancelled"]:
        conn.execute(
            "UPDATE online_orders SET order_status = ?, updated_at = ? WHERE id = ?",
            (status, datetime.now().isoformat(), order_id)
        )
        if status == "verified" and order["is_stock_deducted"] == 0:
            deduct_online_order_stock(conn, order)
        conn.commit()

    conn.close()
    remote_control.push_online_order_to_cloud(order_id)
    return jsonify({
        "success": True,
        "message": f"Order #{order['order_number']} status updated to '{status.upper()}' successfully!"
    })


@app.route("/api/online_orders/unread_count", methods=["GET"])
def api_online_orders_count():
    conn = get_connection()
    new_count = conn.execute("SELECT COUNT(*) AS c FROM online_orders WHERE order_status = 'new'").fetchone()["c"]
    total_count = conn.execute("SELECT COUNT(*) AS c FROM online_orders").fetchone()["c"]
    conn.close()
    return jsonify({"new_count": new_count, "total_count": total_count})


def deduct_online_order_stock(conn, order):
    """Deducts stock for online order if not deducted yet."""
    order_id = order["id"]
    current = conn.execute("SELECT is_stock_deducted FROM online_orders WHERE id = ?", (order_id,)).fetchone()
    if current and current["is_stock_deducted"] == 1:
        return

    items = conn.execute("SELECT * FROM online_order_items WHERE order_id = ?", (order_id,)).fetchall()
    for item in items:
        pid = item["product_id"]
        qty = item["quantity"]
        pkg = conn.execute("SELECT id FROM packages WHERE id = ?", (pid,)).fetchone()
        if not pkg and item["product_name"]:
            pkg = conn.execute("SELECT id FROM packages WHERE name = ? OR instr(?, name) > 0", (item["product_name"], item["product_name"])).fetchone()

        if pkg:
            p_items = conn.execute("SELECT product_id, quantity FROM package_items WHERE package_id = ?", (pkg["id"],)).fetchall()
            for pi in p_items:
                conn.execute(
                    "UPDATE products SET stock_qty = MAX(0, stock_qty - ?) WHERE id = ?",
                    (pi["quantity"] * qty, pi["product_id"])
                )
                remote_control.push_product_to_cloud(pi["product_id"])
        else:
            conn.execute(
                "UPDATE products SET stock_qty = MAX(0, stock_qty - ?) WHERE id = ?",
                (qty, pid)
            )
            remote_control.push_product_to_cloud(pid)

    conn.execute("UPDATE online_orders SET is_stock_deducted = 1 WHERE id = ?", (order_id,))

    # Check if sale record already exists for this online order
    inv_num = f"INV-ONLINE-{order['order_number']}"
    existing_sale = conn.execute("SELECT id FROM sales WHERE invoice_number = ?", (inv_num,)).fetchone()
    
    if not existing_sale:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO sales (invoice_number, invoice_date, cashier_id, customer_name, customer_mobile,
                                total_amount, rounded_total, vat_amount, saved_amount, cash_amount,
                                card_amount, change_amount, created_at, channel)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Online')
        """, (
            inv_num,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            session.get("user_id", 1) if has_request_context() else 1,
            order["customer_name"],
            order["customer_phone"],
            order["subtotal"],
            order["total_amount"],
            0,
            0,
            order["total_amount"],
            0,
            0,
            datetime.now().isoformat()
        ))
        sale_id = cur.lastrowid
        
        for item in items:
            cur.execute("""
                INSERT INTO sale_items (sale_id, product_id, quantity, unit_price, mrp_price, vat_pct, vat_amount, cost_price)
                VALUES (?, ?, ?, ?, ?, 0, 0, 0)
            """, (
                sale_id,
                item["product_id"],
                item["quantity"],
                item["unit_price"],
                item["mrp_price"]
            ))
        remote_control.push_sale_to_cloud(sale_id)


def restore_online_order_stock(conn, order):
    """Restores stock for online order if stock was deducted."""
    order_id = order["id"]
    current = conn.execute("SELECT is_stock_deducted FROM online_orders WHERE id = ?", (order_id,)).fetchone()
    
    # Restore stock if is_stock_deducted == 1 OR if order status was verified/packed/on_the_way/delivered
    is_deducted = (current and current["is_stock_deducted"] == 1) or (order["order_status"] in ("verified", "packed", "on_the_way", "delivered"))

    if is_deducted:
        items = conn.execute("SELECT * FROM online_order_items WHERE order_id = ?", (order_id,)).fetchall()
        for item in items:
            pid = item["product_id"]
            qty = item["quantity"]
            pkg = conn.execute("SELECT id FROM packages WHERE id = ?", (pid,)).fetchone()
            if pkg:
                p_items = conn.execute("SELECT product_id, quantity FROM package_items WHERE package_id = ?", (pid,)).fetchall()
                for pi in p_items:
                    conn.execute(
                        "UPDATE products SET stock_qty = stock_qty + ? WHERE id = ?",
                        (pi["quantity"] * qty, pi["product_id"])
                    )
                    remote_control.push_product_to_cloud(pi["product_id"])
            else:
                conn.execute(
                    "UPDATE products SET stock_qty = stock_qty + ? WHERE id = ?",
                    (qty, pid)
                )
                remote_control.push_product_to_cloud(pid)

        conn.execute("UPDATE online_orders SET is_stock_deducted = 0 WHERE id = ?", (order_id,))

        inv_num = f"INV-ONLINE-{order['order_number']}"
        sale = conn.execute("SELECT id FROM sales WHERE invoice_number = ?", (inv_num,)).fetchone()
        if sale:
            conn.execute("DELETE FROM sale_items WHERE sale_id = ?", (sale["id"],))
            conn.execute("DELETE FROM sales WHERE id = ?", (sale["id"],))


@app.route("/online_orders/<int:order_id>/update_status", methods=["POST"])
@login_required
def update_online_order_status(order_id):
    new_status = request.form.get("status")
    conn = get_connection()
    
    order = conn.execute("SELECT * FROM online_orders WHERE id = ?", (order_id,)).fetchone()
    if not order:
        conn.close()
        flash("Order not found.", "error")
        return redirect(url_for("online_orders"))

    if new_status == "delivered":
        conn.execute(
            "UPDATE online_orders SET order_status = ?, payment_status = 'paid', updated_at = ? WHERE id = ?",
            (new_status, datetime.now().isoformat(), order_id)
        )
    else:
        conn.execute(
            "UPDATE online_orders SET order_status = ?, updated_at = ? WHERE id = ?",
            (new_status, datetime.now().isoformat(), order_id)
        )

    if new_status in ("verified", "packed", "on_the_way", "delivered"):
        deduct_online_order_stock(conn, order)
    elif new_status == "cancelled":
        restore_online_order_stock(conn, order)

    conn.commit()
    conn.close()
    remote_control.push_online_order_to_cloud(order_id)
    flash(f"Order #{order_id} status updated to {new_status}.", "success")
    return redirect(url_for("online_orders"))


@app.route("/online_orders/<int:order_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_online_order(order_id):
    conn = get_connection()
    ord_row = conn.execute("SELECT order_number FROM online_orders WHERE id = ?", (order_id,)).fetchone()
    order_num = ord_row["order_number"] if ord_row else None
    conn.execute("DELETE FROM online_order_items WHERE order_id = ?", (order_id,))
    conn.execute("DELETE FROM online_orders WHERE id = ?", (order_id,))
    conn.commit()
    conn.close()
    if order_num:
        remote_control.delete_online_order_from_cloud(order_num, order_id=order_id)
    flash("Online order deleted successfully.", "success")
    return redirect(url_for("online_orders"))


@app.route("/online_orders/<int:order_id>/invoice")
@login_required
def online_order_invoice(order_id):
    conn = get_connection()
    order = conn.execute("SELECT * FROM online_orders WHERE id = ?", (order_id,)).fetchone()
    if not order:
        conn.close()
        flash("Order not found.", "error")
        return redirect(url_for("online_orders"))

    inv_num = f"INV-ONLINE-{order['order_number']}"
    sale = conn.execute("SELECT id FROM sales WHERE invoice_number = ?", (inv_num,)).fetchone()
    
    if not sale:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO sales (invoice_number, invoice_date, cashier_id, customer_name, customer_mobile,
                                total_amount, rounded_total, vat_amount, saved_amount, cash_amount,
                                card_amount, change_amount, created_at, channel)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'Online')
        """, (
            inv_num,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
            session.get("user_id", 1),
            order["customer_name"],
            order["customer_phone"],
            order["subtotal"],
            order["total_amount"],
            0,
            0,
            order["total_amount"],
            0,
            0,
            datetime.now().isoformat()
        ))
        sale_id = cur.lastrowid
        
        items = conn.execute("SELECT * FROM online_order_items WHERE order_id = ?", (order_id,)).fetchall()
        for item in items:
            cur.execute("""
                INSERT INTO sale_items (sale_id, product_id, quantity, unit_price, mrp_price, vat_pct, vat_amount, cost_price)
                VALUES (?, ?, ?, ?, ?, 0, 0, 0)
            """, (
                sale_id,
                item["product_id"],
                item["quantity"],
                item["unit_price"],
                item["mrp_price"]
            ))
        conn.commit()
    else:
        sale_id = sale["id"]

    conn.close()
    return redirect(url_for("sale_receipt_print", sale_id=sale_id))


@app.route("/api/online_orders/customer_search")
@login_required
def api_online_customer_search():
    q = request.args.get("q", "").strip()
    if not q or len(q) < 2:
        return jsonify([])

    conn = get_connection()
    like_q = f"%{q}%"
    rows = conn.execute("""
        SELECT DISTINCT customer_name, customer_phone, customer_email, area, district, address_details
        FROM online_orders
        WHERE customer_phone LIKE ? OR customer_name LIKE ? OR area LIKE ? OR district LIKE ?
        ORDER BY id DESC
        LIMIT 10
    """, (like_q, like_q, like_q, like_q)).fetchall()

    results = []
    for r in rows:
        orders = conn.execute(
            "SELECT * FROM online_orders WHERE customer_phone = ? ORDER BY id DESC",
            (r["customer_phone"],)
        ).fetchall()
        cust_dict = dict(r)
        cust_dict["order_count"] = len(orders)
        cust_dict["orders"] = [dict(o) for o in orders]
        results.append(cust_dict)

    conn.close()
    return jsonify(results)


@app.route("/online_orders/<int:order_id>/verify_otp", methods=["POST"])
@login_required
def verify_online_order_otp(order_id):
    input_otp = request.form.get("otp", "").strip()
    conn = get_connection()
    order = conn.execute("SELECT delivery_otp FROM online_orders WHERE id = ?", (order_id,)).fetchone()
    if order and order["delivery_otp"] == input_otp:
        conn.execute(
            "UPDATE online_orders SET order_status = 'delivered', payment_status = 'paid', updated_at = ? WHERE id = ?",
            (datetime.now().isoformat(), order_id)
        )
        conn.commit()
        conn.close()
        remote_control.push_online_order_to_cloud(order_id)
        flash(f"OTP Verified! Order #{order_id} marked as DELIVERED.", "success")
    else:
        conn.close()
        flash("Invalid OTP entered. Please check customer's app OTP.", "error")
    return redirect(url_for("online_orders"))


@app.route("/delivery_areas", methods=["GET", "POST"])
@login_required
@admin_required
def delivery_areas():
    conn = get_connection()
    # Auto-cleanup existing duplicates
    conn.execute("DELETE FROM delivery_areas WHERE id NOT IN (SELECT MIN(id) FROM delivery_areas GROUP BY LOWER(district), LOWER(area))")
    conn.commit()

    if request.method == "POST":
        country = request.form.get("country", "Bangladesh").strip()
        district = request.form.get("district", "").strip()
        area = request.form.get("area", "").strip()
        if district and area:
            existing = conn.execute(
                "SELECT id FROM delivery_areas WHERE LOWER(district) = LOWER(?) AND LOWER(area) = LOWER(?)",
                (district, area)
            ).fetchone()
            if existing:
                conn.execute("UPDATE delivery_areas SET is_active = 1 WHERE id = ?", (existing["id"],))
            else:
                conn.execute(
                    "INSERT INTO delivery_areas (country, district, area, is_active, created_at) VALUES (?, ?, ?, 1, ?)",
                    (country, district, area, datetime.now().isoformat())
                )
            conn.commit()
            remote_control.push_delivery_areas_to_cloud()
            flash(f"Delivery area '{area}, {district}' updated successfully.", "success")
    
    areas = conn.execute("SELECT * FROM delivery_areas ORDER BY district, area").fetchall()
    areas_list = [dict(a) for a in areas]
    conn.close()
    return render_template("delivery_areas.html", areas=areas_list)


@app.route("/delivery_areas/<int:area_id>/toggle", methods=["POST"])
@login_required
@admin_required
def toggle_delivery_area(area_id):
    conn = get_connection()
    area = conn.execute("SELECT is_active FROM delivery_areas WHERE id = ?", (area_id,)).fetchone()
    if area:
        new_status = 0 if area["is_active"] == 1 else 1
        conn.execute("UPDATE delivery_areas SET is_active = ? WHERE id = ?", (new_status, area_id))
        conn.commit()
        remote_control.push_delivery_areas_to_cloud()
        flash("Delivery area status toggled.", "success")
    conn.close()
    return redirect(url_for("delivery_areas"))


@app.route("/delivery_areas/<int:area_id>/edit", methods=["POST"])
@login_required
@admin_required
def edit_delivery_area(area_id):
    conn = get_connection()
    country = request.form.get("country", "Bangladesh").strip()
    district = request.form.get("district", "").strip()
    area = request.form.get("area", "").strip()
    if district and area:
        conn.execute(
            "UPDATE delivery_areas SET country = ?, district = ?, area = ? WHERE id = ?",
            (country, district, area, area_id)
        )
        conn.commit()
        remote_control.push_delivery_areas_to_cloud()
        flash("Delivery area updated successfully.", "success")
    conn.close()
    return redirect(url_for("delivery_areas"))


@app.route("/delivery_areas/<int:area_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_delivery_area(area_id):
    conn = get_connection()
    conn.execute("DELETE FROM delivery_areas WHERE id = ?", (area_id,))
    conn.commit()
    conn.close()
    remote_control.push_delivery_areas_to_cloud()
    flash("Delivery area removed.", "success")
    return redirect(url_for("delivery_areas"))


# ===========================================================================
# REST API for Flutter Mobile Application
# ===========================================================================

@app.route("/api/settings", methods=["GET"])
@app.route("/api/settings/shop", methods=["GET"])
def api_settings():
    settings = get_all_settings()
    settings["logo_url"] = url_for("static", filename="images/logo.png", _external=True)
    if not settings.get("customer_support_phone"):
        settings["customer_support_phone"] = settings.get("shop_phone", "")
    return jsonify(settings)


@app.route("/api/products", methods=["GET"])
def api_products():
    conn = get_connection()
    today_date = datetime.now().strftime("%Y-%m-%d")
    include_expired = request.args.get("include_expired", "0") == "1"

    if include_expired:
        # Admin view: show all including expired
        rows = conn.execute("""
            SELECT p.*,
                   c.name AS category_name,
                   sc.name AS sub_category_name,
                   ssc.name AS sub_sub_category_name
            FROM products p
            LEFT JOIN categories c ON p.category_id = c.id
            LEFT JOIN sub_categories sc ON p.sub_category_id = sc.id
            LEFT JOIN sub_sub_categories ssc ON p.sub_sub_category_id = ssc.id
            ORDER BY p.name
        """).fetchall()
    else:
        # Public/default: exclude expired products
        rows = conn.execute("""
            SELECT p.*,
                   c.name AS category_name,
                   sc.name AS sub_category_name,
                   ssc.name AS sub_sub_category_name
            FROM products p
            LEFT JOIN categories c ON p.category_id = c.id
            LEFT JOIN sub_categories sc ON p.sub_category_id = sc.id
            LEFT JOIN sub_sub_categories ssc ON p.sub_sub_category_id = ssc.id
            WHERE (p.expiry_date IS NULL OR p.expiry_date = '' OR p.expiry_date >= ?)
            ORDER BY p.name
        """, (today_date,)).fetchall()
    conn.close()

    result = []
    for r in rows:
        d = dict(r)
        img = (d.get("image_url") or "").strip()
        if img:
            parts = split_image_urls(img)
            norm_parts = []
            for p in parts:
                if p.startswith("/static/"):
                    norm_parts.append(request.host_url.rstrip("/") + p)
                else:
                    norm_parts.append(p)
            d["image_url"] = ", ".join(norm_parts)
        result.append(d)
    return jsonify(result)



@app.route("/api/categories", methods=["GET"])
def api_categories():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM categories ORDER BY name").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/delivery-areas", methods=["GET"])
def api_delivery_areas():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM delivery_areas WHERE is_active = 1 ORDER BY district, area").fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])


@app.route("/api/orders/place", methods=["POST"])
def api_place_order():
    data = request.json or {}
    country = (data.get("country") or data.get("country_name") or "Bangladesh").strip()
    district = (data.get("district") or data.get("district_name") or "Tangail").strip()
    area = (data.get("area") or data.get("area_name") or "Main Area").strip()
    customer_name = (data.get("customer_name") or data.get("name") or "Customer").strip()
    customer_phone = (data.get("customer_phone") or data.get("phone") or "").strip()
    customer_email = (data.get("customer_email") or data.get("email") or "").strip()
    address_details = (data.get("address_details") or data.get("address") or data.get("location") or "Delivery Address").strip()
    payment_method = (data.get("payment_method") or "cod").lower()
    cart_items = data.get("cart_items") or data.get("items") or data.get("products") or []

    if not customer_phone:
        return jsonify({"success": False, "message": "Please enter a valid Phone number."}), 400

    if not cart_items:
        return jsonify({"success": False, "message": "Your cart is empty."}), 400

    conn = get_connection()
    # Check Customer Block Status
    is_blocked, block_msg = check_customer_block(conn, customer_phone)
    if is_blocked:
        conn.close()
        return jsonify({"success": False, "message": block_msg}), 403

    # Location Area Verification (Auto-register active area if new)
    if country and district and area:
        try:
            conn.execute(
                "INSERT OR IGNORE INTO delivery_areas (country, district, area, is_active, created_at) VALUES (?, ?, ?, 1, ?)",
                (country, district, area, datetime.now().isoformat())
            )
            conn.commit()
        except Exception:
            pass
    conn.commit()

    import random
    otp = f"{random.randint(1000, 9999)}"
    now_str = datetime.now().strftime("%Y%m%d%H%M%S")
    rand_suffix = random.randint(100, 999)
    order_number = f"ORD-{now_str}-{rand_suffix}"

    subtotal = 0.0
    processed_items = []

    for item in cart_items:
        prod_id = item.get("product_id") or item.get("id") or item.get("prod_id")
        qty = int(item.get("quantity") or item.get("qty") or item.get("count") or 1)
        p_name_raw = (item.get("product_name") or item.get("name") or item.get("title") or "").strip()
        p_sku_raw = (item.get("sku") or "").strip()

        # Check if item is a Combo Package first
        pkg = None
        if prod_id is not None:
            try:
                pkg = conn.execute("SELECT * FROM packages WHERE id = ?", (int(prod_id),)).fetchone()
            except Exception:
                pass
        
        if not pkg and p_name_raw:
            clean_pname = p_name_raw.replace("📦", "").strip()
            pkg = conn.execute("SELECT * FROM packages WHERE name = ? OR instr(?, name) > 0 OR instr(name, ?) > 0", (clean_pname, clean_pname, clean_pname)).fetchone()

        if pkg:
            p_id = pkg["id"]
            unit_price = float(pkg["package_price"])
            mrp_price = float(item.get("mrp_price") or item.get("mrp") or unit_price)

            p_items = conn.execute("""
                SELECT pi.*, p.sku, p.name AS product_name, p.sell_price, p.mrp
                FROM package_items pi JOIN products p ON pi.product_id = p.id
                WHERE pi.package_id = ?
            """, (pkg["id"],)).fetchall()

            item_details = []
            sl = 1
            for pi in p_items:
                item_details.append(f"{pi['sku'] or 'SKU'} {pi['product_name']} SL:{sl}")
                sl += 1

            if item_details:
                p_name = f"{pkg['name']} ({', '.join(item_details)})"
            else:
                p_name = f"{pkg['name']}"

            offer_type = ""
            offer_value = ""
            offer_title = ""
        else:
            prod = None
            if prod_id is not None:
                try:
                    prod = conn.execute("SELECT * FROM products WHERE id = ?", (int(prod_id),)).fetchone()
                except Exception:
                    prod = conn.execute("SELECT * FROM products WHERE id = ?", (prod_id,)).fetchone()
            
            if not prod and p_name_raw:
                prod = conn.execute("SELECT * FROM products WHERE LOWER(name) = LOWER(?)", (p_name_raw,)).fetchone()

            if prod:
                p_id = prod["id"]
                p_name = prod["name"]
                unit_price = float(prod["sell_price"])
                mrp_price = float(prod["mrp"])
                offer_type = prod["offer_type"] or ""
                offer_value = prod["offer_value"] or ""
                offer_title = prod["offer_title"] or ""
            else:
                p_id = prod_id or 0
                p_name = p_sku_raw if (p_sku_raw and "(" in p_sku_raw) else p_name_raw
                unit_price = float(item.get("unit_price") or item.get("sell_price") or item.get("price") or 0.0)
                mrp_price = float(item.get("mrp_price") or item.get("mrp") or unit_price)
                offer_type = ""
                offer_value = ""
                offer_title = ""

        paid_qty = qty
        actual_qty = qty

        if offer_type in ('buy_x_get_y', 'bogo', 'buy_x_get_x') or ('buy' in offer_title.lower()) or ('buy' in offer_value.lower()) or ('buy' in p_name.lower()):
            buy_qty, free_qty_set = parse_bogo_quantities(offer_value, offer_title, p_name)
            total_set = buy_qty + free_qty_set
            sets = qty // total_set
            remainder = qty % total_set
            paid_qty = (sets * buy_qty) + min(remainder, buy_qty)
            actual_qty = qty

        line_total = unit_price * paid_qty
        subtotal += line_total
        processed_items.append({
            "product_id": p_id,
            "product_name": p_name,
            "unit_price": unit_price,
            "mrp_price": mrp_price,
            "quantity": actual_qty,
            "paid_qty": paid_qty,
            "total_price": line_total
        })

    if not processed_items:
        conn.close()
        return jsonify({"success": False, "message": "No valid cart items found."}), 400

    shop_settings = get_all_settings(conn)
    delivery_charge = float(data.get("delivery_charge") or shop_settings.get("delivery_charge") or 60.0)
    total_amount = subtotal + delivery_charge
    created_at = datetime.now().isoformat()

    # Normalize phone
    digits = re.sub(r"\D", "", str(customer_phone or ""))
    if digits.startswith("8801") and len(digits) == 13:
        digits = digits[2:]
    clean_phone = digits if digits else customer_phone

    cur = conn.cursor()

    # 1. Auto-create or update Customer in customer_users
    if clean_phone and len(clean_phone) == 11 and clean_phone.startswith("01"):
        chk_cust = cur.execute("SELECT id, name FROM customer_users WHERE phone = ?", (clean_phone,)).fetchone()
        if not chk_cust:
            pass_hash = generate_password_hash("123456")
            name_to_use = customer_name.strip() if customer_name and customer_name.strip() else f"Customer {clean_phone[-4:]}"
            cur.execute("""
                INSERT INTO customer_users (phone, name, email, password_hash, plain_password, is_verified, created_at)
                VALUES (?, ?, ?, ?, '123456', 1, ?)
            """, (clean_phone, name_to_use, customer_email or "", pass_hash, created_at))
        elif customer_name and customer_name.strip() and (not chk_cust["name"] or chk_cust["name"].startswith("Customer ")):
            cur.execute("UPDATE customer_users SET name = ? WHERE phone = ?", (customer_name.strip(), clean_phone))

    # 2. Insert into online_orders
    cur.execute("""
        INSERT INTO online_orders (
            order_number, customer_name, customer_phone, customer_email,
            country, district, area, address_details, payment_method,
            payment_status, subtotal, delivery_charge, total_amount,
            order_status, delivery_otp, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new', ?, ?, ?)
    """, (
        order_number, customer_name, clean_phone, customer_email,
        country, district, area, address_details, payment_method,
        "pending" if payment_method == "cod" else "paid",
        subtotal, delivery_charge, total_amount, otp, created_at, created_at
    ))
    order_id = cur.lastrowid

    # 3. Insert into online_order_items
    for item in processed_items:
        raw_pid = item["product_id"]
        valid_pid = raw_pid
        chk_p = conn.execute("SELECT id FROM products WHERE id = ?", (raw_pid,)).fetchone()
        if not chk_p:
            first_p = conn.execute("SELECT id FROM products LIMIT 1").fetchone()
            valid_pid = first_p["id"] if first_p else 1

        cur.execute("""
            INSERT INTO online_order_items (order_id, product_id, product_name, unit_price, mrp_price, quantity, total_price)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (order_id, valid_pid, item["product_name"], item["unit_price"], item["mrp_price"], item["quantity"], item["total_price"]))

        if chk_p:
            cur.execute(
                "UPDATE products SET stock_qty = MAX(0, stock_qty - ?) WHERE id = ?",
                (item["quantity"], valid_pid)
            )
            remote_control.push_product_to_cloud(valid_pid)

    cur.execute("UPDATE online_orders SET is_stock_deducted = 1 WHERE id = ?", (order_id,))

    # 4. Also insert into sales table so it appears in Sales Log immediately
    inv_num = f"INV-ONLINE-{order_number}"
    chk_user = cur.execute("SELECT id FROM users LIMIT 1").fetchone()
    valid_cashier_id = chk_user["id"] if chk_user else 1

    cur.execute("""
        INSERT INTO sales (
            invoice_number, invoice_date, cashier_id, customer_id, customer_name, customer_mobile, channel,
            total_amount, rounded_total, vat_amount, saved_amount, cash_amount, card_amount, change_amount, created_at, is_synced
        ) VALUES (?, ?, ?, ?, ?, ?, 'Online', ?, ?, 0, 0, ?, 0, 0, ?, 0)
    """, (
        inv_num,
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        valid_cashier_id,
        customer_name,
        customer_name,
        clean_phone,
        subtotal,
        total_amount,
        total_amount,
        created_at
    ))
    sale_id = cur.lastrowid

    for item in processed_items:
        raw_pid = item["product_id"]
        chk_prod = cur.execute("SELECT id FROM products WHERE id = ?", (raw_pid,)).fetchone()
        if not chk_prod:
            first_prod = cur.execute("SELECT id FROM products LIMIT 1").fetchone()
            valid_pid = first_prod["id"] if first_prod else None
        else:
            valid_pid = raw_pid

        if valid_pid:
            cur.execute("""
                INSERT INTO sale_items (sale_id, product_id, quantity, unit_price, mrp_price, vat_pct, vat_amount, cost_price)
                VALUES (?, ?, ?, ?, ?, 0, 0, 0)
            """, (
                sale_id, valid_pid, item["quantity"], item["unit_price"], item["mrp_price"]
            ))


    conn.commit()
    conn.close()

    # 5. Push to Cloud
    remote_control.push_online_order_to_cloud(order_id)
    remote_control.push_sale_to_cloud(sale_id)
    if clean_phone and len(clean_phone) == 11 and clean_phone.startswith("01"):
        remote_control.push_customer_user_to_cloud(clean_phone)

    return jsonify({
        "success": True,
        "message": "Order submitted successfully!",
        "order_number": order_number,
        "delivery_otp": otp,
        "total_amount": total_amount
    })



@app.route("/api/orders/pending-count", methods=["GET"])
def api_pending_orders_count():
    conn = get_connection()
    count_row = conn.execute("SELECT COUNT(*) FROM online_orders WHERE order_status = 'pending'").fetchone()
    count = count_row[0] if count_row else 0
    latest = conn.execute("SELECT id, order_number, total_amount, customer_name FROM online_orders ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    latest_id = latest["id"] if latest else 0
    latest_num = latest["order_number"] if latest else ""
    latest_name = latest["customer_name"] if latest else ""
    latest_amount = latest["total_amount"] if latest else 0
    return jsonify({
        "pending_count": count,
        "latest_id": latest_id,
        "latest_num": latest_num,
        "latest_name": latest_name,
        "latest_amount": latest_amount
    })


@app.route("/api/orders/my-orders", methods=["GET"])
def api_my_orders():
    phone = request.args.get("phone", "").strip()
    if not phone:
        return jsonify([])

    conn = get_connection()
    orders = conn.execute(
        "SELECT * FROM online_orders WHERE customer_phone = ? ORDER BY id DESC",
        (phone,)
    ).fetchall()

    result = []
    for ord_row in orders:
        items = conn.execute("SELECT * FROM online_order_items WHERE order_id = ?", (ord_row["id"],)).fetchall()
        o_dict = dict(ord_row)
        o_dict["items"] = [dict(i) for i in items]
        result.append(o_dict)

    conn.close()
    return jsonify(result)


@app.route("/api/orders/cancel", methods=["POST"])
def api_cancel_order():
    data = request.json or {}
    order_number = data.get("order_number", "").strip()
    phone = data.get("customer_phone", "").strip()

    if not order_number or not phone:
        return jsonify({"success": False, "message": "Please enter Order Number and Phone Number."}), 400

    conn = get_connection()
    order = conn.execute(
        "SELECT * FROM online_orders WHERE order_number = ? AND customer_phone = ?",
        (order_number, phone)
    ).fetchone()

    if not order:
        conn.close()
        return jsonify({"success": False, "message": "Order not found!"}), 404

    if order["order_status"] in ("delivered", "cancelled"):
        conn.close()
        return jsonify({"success": False, "message": "This order has already been completed or cancelled."}), 400

    # 10 minutes limit check (600 seconds)
    try:
        created_dt = datetime.fromisoformat(order["created_at"])
        seconds_passed = (datetime.now() - created_dt).total_seconds()
        if seconds_passed > 600:
            conn.close()
            return jsonify({
                "success": False,
                "message": "Sorry! Order was placed more than 10 minutes ago and cannot be cancelled."
            }), 400
    except Exception as e:
        pass

    # Restore stock if stock was deducted for this order
    restore_online_order_stock(conn, order)

    conn.execute(
        "UPDATE online_orders SET order_status = 'cancelled', updated_at = ? WHERE id = ?",
        (datetime.now().isoformat(), order["id"])
    )
    conn.commit()
    conn.close()
    remote_control.push_online_order_to_cloud(order["id"])

    return jsonify({"success": True, "message": "Order has been cancelled successfully."})


@app.route("/api/orders/delivery-orders", methods=["GET"])
def api_delivery_orders():
    conn = get_connection()
    orders = conn.execute(
        "SELECT * FROM online_orders WHERE order_status IN ('new', 'verified', 'packed', 'on_the_way') ORDER BY id DESC"
    ).fetchall()

    result = []
    for ord_row in orders:
        items = conn.execute("SELECT * FROM online_order_items WHERE order_id = ?", (ord_row["id"],)).fetchall()
        o_dict = dict(ord_row)
        o_dict["items"] = [dict(i) for i in items]
        result.append(o_dict)

    conn.close()
    return jsonify(result)


# In-memory WhatsApp OTP & Phone Verification Storage
OTP_STORE = {}
VERIFIED_PHONES = set()

@app.route("/api/customer/send-whatsapp-otp", methods=["POST"])
@app.route("/api/customer/send-otp", methods=["POST"])
@app.route("/api/customer/send-flash-call", methods=["POST"])
@app.route("/api/customer/initiate-missed-call-verify", methods=["POST"])
def api_customer_send_whatsapp_otp():
    """
    Generates and dispatches WhatsApp OTP directly for mobile verification.
    """
    data = request.json or {}
    phone = data.get("phone", "").strip()
    purpose = data.get("purpose", "registration").strip()

    if not phone or len(phone) != 11 or not phone.startswith("01") or not phone.isdigit():
        return jsonify({
            "success": False,
            "message": "Mobile number must start with '01' and be exactly 11 digits (e.g. 01712345678)"
        }), 400

    conn = get_connection()
    # Check block status
    is_blocked, block_msg = check_customer_block(conn, phone)
    if is_blocked:
        conn.close()
        return jsonify({"success": False, "message": block_msg}), 403

    if purpose == "forgot_password":
        cust = conn.execute("SELECT id FROM customer_users WHERE phone = ?", (phone,)).fetchone()
        if not cust:
            conn.close()
            return jsonify({"success": False, "message": "No account found with this mobile number. Please register first."}), 400
    elif purpose == "registration":
        existing = conn.execute("SELECT id FROM customer_users WHERE phone = ?", (phone,)).fetchone()
        if existing:
            conn.close()
            return jsonify({
                "success": False,
                "already_registered": True,
                "message": "Already registered with this mobile number or email."
            }), 400

    shop_settings = get_all_settings(conn)
    conn.close()

    import random
    otp_code = f"{random.randint(1000, 9999)}"
    
    OTP_STORE[phone] = {
        "otp": otp_code,
        "created_at": datetime.now()
    }

    # WhatsApp Direct Open & Notification Link
    shop_name = shop_settings.get("shop_name") or "DOINEEK Supershop"
    whatsapp_url = f"https://wa.me/88{phone}?text=Your%20{shop_name.replace(' ', '%20')}%20Verification%20OTP%20is%20*{otp_code}*%20(Valid%20for%2010%20minutes)"

    return jsonify({
        "success": True,
        "otp_code": otp_code,
        "whatsapp_url": whatsapp_url,
        "message": f"WhatsApp OTP generated for {phone}. Please check WhatsApp to view code.",
        # Backward compatibility
        "verification_code": otp_code,
        "target_phone": phone
    })


@app.route("/api/customer/verify-whatsapp-otp", methods=["POST"])
@app.route("/api/customer/verify-otp", methods=["POST"])
@app.route("/api/customer/confirm-missed-call", methods=["POST"])
@app.route("/api/customer/verify-flash-call", methods=["POST"])
def api_customer_verify_whatsapp_otp():
    data = request.json or {}
    phone = data.get("phone", "").strip()
    otp_input = data.get("otp", "").strip()

    record = OTP_STORE.get(phone)
    if not record:
        return jsonify({"success": False, "message": "OTP expired or not found. Please click 'Send WhatsApp OTP' again."}), 400

    if record["otp"] == otp_input:
        VERIFIED_PHONES.add(phone)
        return jsonify({"success": True, "message": "WhatsApp OTP verified successfully!"})
    else:
        return jsonify({"success": False, "message": "Invalid OTP code. Please enter the correct 4-digit PIN from WhatsApp."}), 400


@app.route("/api/delivery/verify-otp", methods=["POST"])
def api_verify_otp():
    data = request.json or {}
    order_number = data.get("order_number", "").strip()
    otp = data.get("otp", "").strip()

    conn = get_connection()
    order = conn.execute("SELECT id, delivery_otp FROM online_orders WHERE order_number = ?", (order_number,)).fetchone()
    if order and order["delivery_otp"] == otp:
        conn.execute(
            "UPDATE online_orders SET order_status = 'delivered', updated_at = ? WHERE id = ?",
            (datetime.now().isoformat(), order["id"])
        )
        conn.commit()
        conn.close()
        remote_control.push_online_order_to_cloud(order["id"])
        return jsonify({"success": True, "message": "OTP verified! Order updated to Delivered."})

    conn.close()
    return jsonify({"success": False, "message": "Invalid OTP code. Please check customer app delivery OTP."}), 400


@app.route("/api/auth/register", methods=["POST"])
def api_auth_register():
    data = request.json or {}
    phone = data.get("phone", "").strip()
    name = data.get("name", "").strip()
    email = data.get("email", "").strip()
    password = data.get("password", "").strip()

    if not phone or not name or not password:
        return jsonify({"success": False, "message": "Please enter name, mobile number, and password."}), 400

    if not (len(phone) == 11 and phone.startswith("01") and phone.isdigit()):
        return jsonify({
            "success": False,
            "message": "Mobile number must start with '01' and be exactly 11 digits (e.g. 01712345678)"
        }), 400

    # Enforce Mobile Number Verification
    if phone not in VERIFIED_PHONES:
        return jsonify({
            "success": False,
            "not_verified": True,
            "message": "Mobile number has not been verified yet. Please verify your mobile number via WhatsApp OTP first."
        }), 400

    conn = get_connection()
    # Check Customer Block Status
    is_blocked, block_msg = check_customer_block(conn, phone)
    if is_blocked:
        conn.close()
        return jsonify({"success": False, "message": block_msg}), 403

    existing = conn.execute("SELECT id FROM customer_users WHERE phone = ? OR (email != '' AND email = ?)", (phone, email)).fetchone()
    if existing:
        conn.close()
        return jsonify({
            "success": False,
            "already_registered": True,
            "message": "Already registered with this mobile number or email."
        }), 400

    conn.execute(
        "INSERT INTO customer_users (phone, name, email, password_hash, plain_password, is_verified, created_at) VALUES (?, ?, ?, ?, ?, 1, ?)",
        (phone, name, email, generate_password_hash(password), password, datetime.now().isoformat())
    )
    conn.commit()
    conn.close()
    
    # Verification fulfilled
    VERIFIED_PHONES.discard(phone)
    remote_control.push_customer_user_to_cloud(phone)

    return jsonify({"success": True, "message": "Registration successful! You can now log in."})


@app.route("/api/auth/change-password", methods=["POST"])
def api_auth_change_password():
    data = request.json or {}
    phone = data.get("phone", "").strip()
    old_pass = data.get("old_password", "").strip()
    new_pass = data.get("new_password", "").strip()

    if not phone or not old_pass or not new_pass:
        return jsonify({"success": False, "message": "Please fill in all password fields."}), 400

    conn = get_connection()
    cust = conn.execute("SELECT * FROM customer_users WHERE phone = ?", (phone,)).fetchone()
    if not cust:
        conn.close()
        return jsonify({"success": False, "message": "Customer record not found."}), 400

    if not check_password_hash(cust["password_hash"], old_pass):
        conn.close()
        return jsonify({"success": False, "message": "Current password is incorrect."}), 400

    conn.execute(
        "UPDATE customer_users SET password_hash = ?, plain_password = ? WHERE phone = ?",
        (generate_password_hash(new_pass), new_pass, phone)
    )
    conn.commit()
    conn.close()
    remote_control.push_customer_user_to_cloud(phone)
    return jsonify({"success": True, "message": "Password updated successfully!"})


@app.route("/api/auth/forgot-password/reset", methods=["POST"])
def api_auth_forgot_password_reset():
    data = request.json or {}
    phone = data.get("phone", "").strip()
    new_pass = data.get("new_password", "").strip()

    if not phone or not new_pass:
        return jsonify({"success": False, "message": "Please provide mobile number and new password."}), 400

    conn = get_connection()
    cust = conn.execute("SELECT * FROM customer_users WHERE phone = ?", (phone,)).fetchone()
    if not cust:
        conn.close()
        return jsonify({"success": False, "message": "No account found with this mobile number."}), 400

    conn.execute(
        "UPDATE customer_users SET password_hash = ?, plain_password = ? WHERE phone = ?",
        (generate_password_hash(new_pass), new_pass, phone)
    )
    conn.commit()
    conn.close()
    remote_control.push_customer_user_to_cloud(phone)
    return jsonify({"success": True, "message": "Password reset successfully! You can now log in with your new password."})



@app.route("/api/auth/login", methods=["POST"])
def api_auth_login():
    data = request.json or {}
    phone = data.get("phone", "").strip()
    password = data.get("password", "").strip()
    is_delivery_man = data.get("is_delivery_man", False)

    if not phone or not password:
        return jsonify({"success": False, "message": "Please enter your mobile number and password."}), 400

    if not is_delivery_man:
        phone = normalize_phone(phone)
        if not (len(phone) == 11 and phone.startswith("01") and phone.isdigit()):
            return jsonify({
                "success": False,
                "message": "Mobile number must start with '01' and be exactly 11 digits (e.g. 01712345678)"
            }), 400

    conn = get_connection()
    if not is_delivery_man:
        is_blocked, block_msg = check_customer_block(conn, phone)
        if is_blocked:
            conn.close()
            return jsonify({"success": False, "message": block_msg}), 403

    if is_delivery_man:
        phone = normalize_phone(phone)
        user_row = conn.execute("SELECT * FROM users WHERE username = ? AND role = 'delivery'", (phone,)).fetchone()
        if not user_row:
            conn.close()
            return jsonify({"success": False, "message": "Invalid delivery rider username or password."}), 400
        
        user = dict(user_row)
        if not check_password_hash(user["password_hash"], password):
            conn.close()
            return jsonify({"success": False, "message": "Invalid delivery rider username or password."}), 400
        if user.get("is_active", 1) == 0:
            conn.close()
            return jsonify({"success": False, "message": "This rider account is suspended/inactive. Please contact Admin."}), 403
        conn.close()
        return jsonify({
            "success": True,
            "user": {"name": user.get("full_name") or user.get("username"), "phone": phone, "role": user.get("role", "delivery")}
        })

    cust = conn.execute("SELECT * FROM customer_users WHERE phone = ?", (phone,)).fetchone()
    conn.close()

    if not cust:
        return jsonify({
            "success": False,
            "message": "This mobile number is not registered. Please register an account first."
        }), 400

    if not check_password_hash(cust["password_hash"], password):
        return jsonify({"success": False, "message": "Incorrect password. Please try again."}), 400

    if cust["is_verified"] != 1:
        return jsonify({"success": False, "message": "Account is not verified. Please verify via OTP."}), 400

    return jsonify({
        "success": True,
        "user": {
            "name": cust["name"],
            "phone": cust["phone"],
            "email": cust["email"]
        }
    })


# ===========================================================================
# Product Packages & Combo Bundles Section (Admin & API)
# ===========================================================================

@app.route("/packages", methods=["GET", "POST"])
@login_required
@admin_required
def packages_page():
    conn = get_connection()
    if request.method == "POST":
        name = request.form.get("name", "").strip()
        description = request.form.get("description", "").strip()
        package_price = float(request.form.get("package_price") or 0)
        image_url = request.form.get("image_url", "").strip()
        prod_ids = request.form.getlist("product_ids")

        file = request.files.get("package_image_file")
        if file and file.filename:
            import os, time
            from werkzeug.utils import secure_filename
            upload_dir = os.path.join(app.root_path, "static", "uploads", "packages")
            os.makedirs(upload_dir, exist_ok=True)
            fn = secure_filename(file.filename)
            file_path = os.path.join(upload_dir, f"{int(time.time())}_{fn}")
            file.save(file_path)
            data_uri = process_uploaded_image_file(file_path)
            if data_uri:
                image_url = data_uri
            else:
                rel_path = os.path.relpath(file_path, app.root_path).replace("\\", "/")
                image_url = f"/{rel_path}"

        if name and package_price > 0 and prod_ids:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO packages (name, description, image_url, package_price, is_active, created_at)
                VALUES (?, ?, ?, ?, 1, ?)
            """, (name, description, image_url, package_price, datetime.now().isoformat()))
            pkg_id = cur.lastrowid

            for pid in prod_ids:
                item_qty = int(request.form.get(f"qty_{pid}") or 1)
                cur.execute("""
                    INSERT INTO package_items (package_id, product_id, quantity)
                    VALUES (?, ?, ?)
                """, (pkg_id, int(pid), item_qty))
            conn.commit()
            
            # Push updated packages to Cloud Firestore
            remote_control.push_packages_to_cloud()
            flash(f"Package '{name}' created successfully.", "success")
        else:
            flash("Please enter package name, price, and select at least 1 product.", "error")

    all_products = conn.execute("SELECT * FROM products ORDER BY name").fetchall()
    pkg_rows = conn.execute("SELECT * FROM packages ORDER BY id DESC").fetchall()
    
    packages_list = []
    for pkg in pkg_rows:
        p_dict = dict(pkg)
        items = conn.execute("""
            SELECT pi.*, p.name AS product_name, p.sell_price, p.mrp
            FROM package_items pi JOIN products p ON pi.product_id = p.id
            WHERE pi.package_id = ?
        """, (pkg["id"],)).fetchall()
        p_dict["items"] = [dict(i) for i in items]
        packages_list.append(p_dict)

    conn.close()
    return render_template("packages.html", packages=packages_list, products=all_products)


@app.route("/packages/<int:package_id>/edit", methods=["POST"])
@login_required
@admin_required
def edit_package(package_id):
    conn = get_connection()
    pkg = conn.execute("SELECT * FROM packages WHERE id = ?", (package_id,)).fetchone()
    if not pkg:
        conn.close()
        flash("Package not found.", "error")
        return redirect(url_for("packages_page"))

    name = request.form.get("name", "").strip()
    description = request.form.get("description", "").strip()
    package_price = float(request.form.get("package_price") or 0)
    image_url = request.form.get("image_url", "").strip()
    prod_ids = request.form.getlist("product_ids")

    file = request.files.get("package_image_file")
    if file and file.filename:
        import os, time
        from werkzeug.utils import secure_filename
        upload_dir = os.path.join(app.root_path, "static", "uploads", "packages")
        os.makedirs(upload_dir, exist_ok=True)
        fn = secure_filename(file.filename)
        file_path = os.path.join(upload_dir, f"{int(time.time())}_{fn}")
        file.save(file_path)
        data_uri = process_uploaded_image_file(file_path)
        if data_uri:
            image_url = data_uri
        else:
            rel_path = os.path.relpath(file_path, app.root_path).replace("\\", "/")
            image_url = f"/{rel_path}"
    elif not image_url and pkg:
        image_url = pkg["image_url"]

    if name and package_price > 0 and prod_ids:
        cur = conn.cursor()
        cur.execute("""
            UPDATE packages SET name = ?, description = ?, image_url = ?, package_price = ?
            WHERE id = ?
        """, (name, description, image_url, package_price, package_id))
        
        cur.execute("DELETE FROM package_items WHERE package_id = ?", (package_id,))
        for pid in prod_ids:
            item_qty = int(request.form.get(f"qty_{pid}") or 1)
            cur.execute("""
                INSERT INTO package_items (package_id, product_id, quantity)
                VALUES (?, ?, ?)
            """, (package_id, int(pid), item_qty))
        conn.commit()
        
        # Push updated packages to Cloud Firestore
        remote_control.push_packages_to_cloud()
        flash(f"Package '{name}' updated successfully.", "success")
    else:
        flash("Please enter package name, price, and select at least 1 product.", "error")
    conn.close()
    return redirect(url_for("packages_page"))


@app.route("/packages/<int:package_id>/toggle-status", methods=["POST"])
@login_required
@admin_required
def toggle_package_status(package_id):
    conn = get_connection()
    pkg = conn.execute("SELECT id, name, is_active FROM packages WHERE id = ?", (package_id,)).fetchone()
    if not pkg:
        conn.close()
        flash("Package not found.", "error")
        return redirect(url_for("packages_page"))
    
    new_status = 0 if pkg["is_active"] else 1
    conn.execute("UPDATE packages SET is_active = ? WHERE id = ?", (new_status, package_id))
    conn.commit()
    conn.close()
    
    # Sync status to cloud Firestore
    remote_control.push_packages_to_cloud()
    
    status_text = "Activated (Now Live on Store & App)" if new_status == 1 else "Deactivated (Hidden from Store & App)"
    flash(f"Combo package '{pkg['name']}' has been {status_text}.", "success")
    return redirect(url_for("packages_page"))


@app.route("/packages/<int:package_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_package(package_id):
    conn = get_connection()
    conn.execute("DELETE FROM package_items WHERE package_id = ?", (package_id,))
    conn.execute("DELETE FROM packages WHERE id = ?", (package_id,))
    conn.commit()
    conn.close()
    
    # Mirror deletion in Cloud Firestore and sync cloud packages
    remote_control.delete_package_from_cloud(package_id)
    remote_control.push_packages_to_cloud()
    
    flash("Product package deleted successfully.", "success")
    return redirect(url_for("packages_page"))


@app.route("/api/packages", methods=["GET"])
def api_packages():
    conn = get_connection()
    pkg_rows = conn.execute("SELECT * FROM packages WHERE is_active = 1 ORDER BY id DESC").fetchall()
    packages_list = []
    for pkg in pkg_rows:
        p_dict = dict(pkg)
        img = (p_dict.get("image_url") or "").strip()
        if img and img.startswith("/static/"):
            p_dict["image_url"] = request.host_url.rstrip("/") + img

        items = conn.execute("""
            SELECT pi.*, p.name AS product_name, p.sell_price, p.mrp, p.image_url, p.sku
            FROM package_items pi JOIN products p ON pi.product_id = p.id
            WHERE pi.package_id = ?
        """, (pkg["id"],)).fetchall()
        item_list = []
        for i in items:
            it_d = dict(i)
            p_img = (it_d.get("image_url") or "").strip()
            if p_img and p_img.startswith("/static/"):
                it_d["image_url"] = request.host_url.rstrip("/") + p_img
            item_list.append(it_d)
        p_dict["items"] = item_list
        packages_list.append(p_dict)
    conn.close()
    return jsonify(packages_list)


# ===========================================================================
# 🚨 System Reset & 2FA Email OTP Verification
# ===========================================================================

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

RESET_SENDER_EMAIL = os.environ.get("SMTP_SENDER_EMAIL") or "doineek.supershop@gmail.com"
RESET_SENDER_PASS = os.environ.get("SMTP_APP_PASSWORD") or os.environ.get("SMTP_SENDER_PASS") or "Bangladesh@2"
RESET_RECIPIENT_EMAIL = "najmul.djd@gmail.com"

def send_reset_otp_email(otp_code):
    conn = get_connection()
    shop_settings = get_all_settings(conn)
    conn.close()

    custom_pass = (shop_settings.get("smtp_app_password") or "").strip()
    sender = RESET_SENDER_EMAIL.strip()
    password = (custom_pass or RESET_SENDER_PASS).replace(" ", "").strip()

    print(f"\n=======================================================")
    print(f"🚨 SYSTEM RESET OTP GENERATED FOR {RESET_RECIPIENT_EMAIL}: [{otp_code}]")
    print(f"=======================================================\n")

    try:
        msg = MIMEMultipart("alternative")
        msg["Subject"] = f"CRITICAL: System Reset Confirmation OTP [{otp_code}]"
        msg["From"] = f"DOINEEK Supershop Security <{sender}>"
        msg["To"] = RESET_RECIPIENT_EMAIL

        text_content = f"DOINEEK Supershop - System Reset OTP: {otp_code}\n\nWarning: Entering this OTP will permanently delete selected system records."
        html_content = f"""
        <div style="font-family: Arial, sans-serif; max-width: 550px; margin: 0 auto; padding: 24px; border: 2px solid #dc2626; border-radius: 12px; background: #fff5f5;">
          <h2 style="color: #dc2626; margin-top: 0;">🚨 CRITICAL SYSTEM RESET OTP</h2>
          <p style="font-size: 15px; color: #1e293b;">A request has been initiated to reset system data for DOINEEK Supershop.</p>
          <div style="background: #dc2626; color: white; padding: 18px; border-radius: 8px; text-align: center; font-size: 32px; font-weight: bold; letter-spacing: 8px; margin: 20px 0;">
            {otp_code}
          </div>
          <p style="color: #991b1b; font-weight: bold; font-size: 14px;">⚠️ WARNING: Authorizing this OTP will permanently wipe selected database categories (Inventory, Sales, Customers, Orders, Reports, Staff, etc.).</p>
          <p style="font-size: 12px; color: #64748b; margin-bottom: 0;">Sent from connected account {sender} to {RESET_RECIPIENT_EMAIL}. If you did not request this, please ignore this email.</p>
        </div>
        """
        msg.attach(MIMEText(text_content, "plain"))
        msg.attach(MIMEText(html_content, "html"))

        # 1. Try Port 587 (TLS)
        try:
            server = smtplib.SMTP("smtp.gmail.com", 587, timeout=10)
            server.starttls()
            server.login(sender, password)
            server.sendmail(sender, RESET_RECIPIENT_EMAIL, msg.as_string())
            server.quit()
            return True, "OTP email sent successfully."
        except Exception as err587:
            # 2. Try Port 465 (SSL)
            try:
                server = smtplib.SMTP_SSL("smtp.gmail.com", 465, timeout=10)
                server.login(sender, password)
                server.sendmail(sender, RESET_RECIPIENT_EMAIL, msg.as_string())
                server.quit()
                return True, "OTP email sent successfully."
            except Exception:
                raise err587
    except Exception as e:
        err_str = str(e)
        print(f"[send_reset_otp_email] SMTP Error: {err_str}")
        if "BadCredentials" in err_str or "Username and Password not accepted" in err_str:
            return False, f"Google Gmail SMTP Auth Error: Gmail requires a 16-character App Password (Google Account -> Security -> 2-Step Verification -> App Passwords). Generated OTP: {otp_code}"
        return False, err_str


@app.route("/admin/system-reset/send-otp", methods=["POST"])
@login_required
@admin_required
def admin_reset_send_otp():
    data = request.json or {}
    categories = data.get("categories") or []
    
    if not categories:
        return jsonify({"success": False, "message": "Please select at least one data category to reset."}), 400

    import random, time
    otp = f"{random.randint(100000, 999999)}"
    
    session["reset_otp"] = otp
    session["reset_categories"] = categories
    session["reset_otp_time"] = time.time()

    ok, msg = send_reset_otp_email(otp)
    if ok:
        return jsonify({"success": True, "message": f"Verification OTP has been sent to {RESET_RECIPIENT_EMAIL}."})
    else:
        return jsonify({
            "success": True,
            "warning": True,
            "otp": otp,
            "message": f"Gmail SMTP Auth Notice: Set App Password in Shop Settings for email delivery. Active Session OTP: {otp}"
        })


@app.route("/admin/system-reset/confirm", methods=["POST"])
@login_required
@admin_required
def admin_reset_confirm():
    data = request.json or {}
    entered_otp = (data.get("otp") or "").strip()
    
    saved_otp = session.get("reset_otp")
    categories = session.get("reset_categories") or data.get("categories") or []
    saved_time = session.get("reset_otp_time") or 0
    import time

    if not saved_otp or not entered_otp or entered_otp != saved_otp:
        return jsonify({"success": False, "message": "Invalid OTP. Please check your email and try again."}), 400

    if (time.time() - saved_time) > 600:
        session.pop("reset_otp", None)
        return jsonify({"success": False, "message": "OTP has expired. Please request a new OTP."}), 400

    conn = get_connection()
    cur = conn.cursor()
    wiped_items = []

    try:
        # 1. Create automatic point-in-time snapshot before reset
        try:
            from database import create_system_snapshot
            snap_lbl = f"Pre-Reset Backup ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})"
            create_system_snapshot(conn, label=snap_lbl)
        except Exception as _snap_err:
            print(f"[admin_reset_confirm] Automatic pre-reset snapshot notice: {_snap_err}")

        def safe_del(tbl, clause="", p=()):
            try:
                q = f"DELETE FROM {tbl}"
                if clause:
                    q += f" WHERE {clause}"
                cur.execute(q, p)
            except Exception as _t_err:
                print(f"[system_reset] Notice for table {tbl}: {_t_err}")

        if "inventory" in categories:
            safe_del("product_units")
            safe_del("products")
            wiped_items.append("Inventory & Products")

        if "sales_log" in categories:
            safe_del("sale_items")
            safe_del("sales")
            wiped_items.append("Sales Log")

        if "customers" in categories:
            safe_del("customer_users")
            safe_del("customers")
            wiped_items.append("Customers")

        if "online_orders" in categories:
            safe_del("online_order_items")
            safe_del("online_orders")
            wiped_items.append("Online Orders")

        if "returned_expired" in categories:
            safe_del("returned_items")
            wiped_items.append("Returned / Expired Items")

        if "packages" in categories:
            safe_del("package_items")
            safe_del("packages")
            wiped_items.append("Product Packages & Combos")

        if "offers_promotions" in categories:
            safe_del("vouchers")
            try:
                cur.execute("UPDATE products SET is_offer = 0, is_promotion = 0, offer_type = NULL, offer_value = NULL, offer_title = NULL")
            except Exception:
                pass
            wiped_items.append("Offers, Banner Promotions & Vouchers")

        if "delivery_areas" in categories:
            safe_del("delivery_areas")
            wiped_items.append("Delivery Areas")

        if "riders_staff" in categories:
            safe_del("users", "role != 'admin' AND id != ?", (session.get("user_id", 0),))
            wiped_items.append("Riders & Staff Users")

        if "reports" in categories:
            safe_del("ledger_entries")
            wiped_items.append("Reports & Ledger Entries")

        conn.commit()
        conn.close()

        # 2. Wipe Cloud Firestore collections so deleted data does not auto-restore!
        try:
            if hasattr(remote_control, "wipe_cloud_collections"):
                remote_control.wipe_cloud_collections(categories)
        except Exception as _rc_err:
            print(f"[admin_reset_confirm] Cloud wipe notice: {_rc_err}")
        
        session.pop("reset_otp", None)
        session.pop("reset_categories", None)

        return jsonify({
            "success": True,
            "message": f"System Reset Complete! Pre-reset snapshot saved. Successfully wiped: {', '.join(wiped_items)}."
        })
    except Exception as e:
        conn.rollback()
        conn.close()
        return jsonify({"success": False, "message": f"Error during system reset: {e}"}), 500


@app.route("/admin/system-restore", methods=["POST"])
@login_required
@admin_required
def admin_system_restore():
    data = request.json or {}
    target = data.get("snapshot_id") or data.get("datetime")
    if not target:
        return jsonify({"success": False, "message": "Please select a valid snapshot or Datetime to restore."}), 400

    from database import restore_system_snapshot
    ok, msg = restore_system_snapshot(target)
    if ok:
        try:
            remote_control.push_full_backup()
        except Exception:
            pass
        return jsonify({"success": True, "message": msg})
    else:
        return jsonify({"success": False, "message": msg}), 400


@app.route("/admin/create-snapshot", methods=["POST"])
@login_required
@admin_required
def admin_create_snapshot():
    data = request.json or {}
    lbl = data.get("label") or f"Manual Snapshot ({datetime.now().strftime('%Y-%m-%d %H:%M:%S')})"
    from database import create_system_snapshot
    snap_id, snap_time = create_system_snapshot(label=lbl)
    return jsonify({
        "success": True,
        "message": f"System Snapshot #{snap_id} created successfully at {snap_time}!",
        "snapshot_id": snap_id,
        "snapshot_time": snap_time
    })


@app.route("/admin/force-cloud-sync", methods=["POST"])
@login_required
@admin_required
def admin_force_cloud_sync():
    try:
        remote_control.push_full_backup()
        return jsonify({"success": True, "message": "Instant Live Cloud Sync completed! All local data pushed to https://doineek.onrender.com/."})
    except Exception as e:
        return jsonify({"success": False, "message": f"Cloud Sync Error: {e}"}), 500


@app.route("/api/snapshots", methods=["GET"])
@login_required
def api_list_snapshots():
    conn = get_connection()
    rows = conn.execute("SELECT id, snapshot_time, label, created_at FROM system_snapshots ORDER BY id DESC").fetchall()
    conn.close()
    return jsonify({"success": True, "snapshots": [dict(r) for r in rows]})


# ===========================================================================
# Application Entry Point & Automatic Real-Time Firebase Listener
# ===========================================================================

try:
    init_db()
    remote_control.start()
except Exception as _rc_err:
    print(f"[app.py] Automatic Firebase listener initialization: {_rc_err}", flush=True)



# ===========================================================================
# Sync Status & Force Push API
# ===========================================================================

@app.route("/api/sync/status")
def api_sync_status():
    """Returns Firebase connection and product count on local vs Firebase."""
    try:
        db = remote_control._init_firebase()
        firebase_ok = db is not None
        conn = get_connection()
        local_products = conn.execute("SELECT COUNT(*) as c FROM products").fetchone()["c"]
        local_categories = conn.execute("SELECT COUNT(*) as c FROM categories").fetchone()["c"]
        conn.close()
        firebase_products = 0
        if firebase_ok:
            try:
                firebase_products = len(list(db.collection("products").stream()))
            except Exception:
                pass
        return jsonify({
            "firebase_connected": firebase_ok,
            "local_products": local_products,
            "local_categories": local_categories,
            "firebase_products": firebase_products,
            "status": "ok"
        })
    except Exception as e:
        return jsonify({"status": "error", "message": str(e)}), 500


@app.route("/api/sync/force-push", methods=["POST"])
def api_force_push():
    """Force-pushes ALL local data to Firebase immediately. Admin only."""
    if not session.get("user_id"):
        return jsonify({"success": False, "message": "Not authenticated"}), 401
    try:
        remote_control.push_full_backup()
        remote_control.push_categories_to_cloud()
        remote_control.push_brands_to_cloud()
        return jsonify({"success": True, "message": "Full sync pushed to Firebase. Render will update within 10 seconds."})
    except Exception as e:
        return jsonify({"success": False, "message": str(e)}), 500




@app.route("/download-apk")
@app.route("/apk")
def download_app_apk():
    """Direct 1-click APK download for Android users."""
    from flask import send_file
    apk_path = os.path.join(app.root_path, "static", "apk", "supershop_latest.apk")
    if not os.path.exists(apk_path):
        flutter_apk = os.path.join(app.root_path, "supershop_flutter_app", "build", "app", "outputs", "flutter-apk", "app-release.apk")
        if os.path.exists(flutter_apk):
            import shutil
            os.makedirs(os.path.dirname(apk_path), exist_ok=True)
            shutil.copy2(flutter_apk, apk_path)
    return send_file(
        apk_path,
        as_attachment=True,
        download_name="supershop_app.apk",
        mimetype="application/vnd.android.package-archive"
    )

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000, use_reloader=False)
