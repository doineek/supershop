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

from database import (
    get_connection, init_db, round_to_whole, create_product_units,
    generate_invoice_number, get_all_settings, update_settings
)
from barcode_utils import generate_barcode_svg
import remote_control

app = Flask(__name__)
app.secret_key = "doineek-supershop-secret-key"

UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads', 'products')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER


@app.before_request
def handle_cors_options():
    if request.method == "OPTIONS":
        response = app.make_default_options_response()
        response.headers['Access-Control-Allow-Origin'] = '*'
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With'
        response.headers['Access-Control-Allow-Methods'] = 'GET, POST, PUT, DELETE, OPTIONS'
        return response


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
# Dashboard
# ===========================================================================

@app.route("/")
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

@app.route("/products")
@login_required
def products():
    conn = get_connection()
    open_cat = request.args.get("open_cat", "0") == "1"
    rows = conn.execute("""
        SELECT p.*, c.name AS category_name,
               (SELECT COUNT(*) FROM product_units u WHERE u.product_id = p.id AND u.status = 'in_stock') AS tag_count
        FROM products p
        LEFT JOIN categories c ON p.category_id = c.id
        ORDER BY p.name
    """).fetchall()
    categories = conn.execute("SELECT * FROM categories ORDER BY name").fetchall()
    sub_categories = conn.execute("SELECT * FROM sub_categories ORDER BY name").fetchall()
    sub_sub_categories = conn.execute("SELECT * FROM sub_sub_categories ORDER BY name").fetchall()
    brands = conn.execute("SELECT * FROM brands ORDER BY name").fetchall()
    conn.close()
    return render_template("products.html", products=rows, categories=categories, sub_categories=sub_categories, sub_sub_categories=sub_sub_categories, brands=brands, open_cat=open_cat)


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

        try:
            cur = conn.cursor()
            cur.execute(
                "INSERT INTO products (sku, name, brand, category_id, sub_category_id, sub_sub_category_id, cost_price, mrp, sell_price, vat_pct, stock_qty, low_stock_threshold, sl_number, description, image_url, is_trending, is_flash_sale, is_offer, is_promotion, offer_title, offer_type, offer_value, offer_base, expiry_date) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (sku, name, brand, category_id, sub_category_id, sub_sub_category_id, cost_price, mrp, sell_price, vat_pct, stock_qty, low_stock_threshold, sl_number, description, image_url, is_trending, is_flash_sale, is_offer, is_promotion, offer_title, offer_type, offer_value, offer_base, expiry_date)
            )
            new_product_id = cur.lastrowid
            create_product_units(conn, new_product_id, stock_qty)
            conn.commit()
            conn.close()
            remote_control.push_product_to_cloud(new_product_id)
            flash(f'Product "{name}" added with {stock_qty} printable tag(s).', "success")
            return redirect(url_for("products"))
        except Exception as e:
            flash(f"Could not save product: {e}", "error")
    conn.close()
    return render_template("product_form.html", categories=categories, sub_categories=sub_categories, sub_sub_categories=sub_sub_categories, brands=brands, product=None)


@app.route("/products/<int:product_id>/edit", methods=["GET", "POST"])
@login_required
@admin_required
def edit_product(product_id):
    conn = get_connection()
    categories = conn.execute("SELECT * FROM categories ORDER BY name").fetchall()
    sub_categories = conn.execute("SELECT * FROM sub_categories ORDER BY name").fetchall()
    sub_sub_categories = conn.execute("SELECT * FROM sub_sub_categories ORDER BY name").fetchall()
    brands = conn.execute("SELECT * FROM brands ORDER BY name").fetchall()
    product = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    conn.close()

    if not product:
        flash("Product not found.", "error")
        return redirect(url_for("products"))

    if request.method == "POST":
        new_stock_qty = int(request.form["stock_qty"] or 0)
        old_stock_qty = product["stock_qty"]
        brand = request.form.get("brand", "").strip()
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
                filename = secure_filename(f"{sku_clean}_{int(datetime.now().timestamp())}_{random.randint(10,99)}_{file.filename}")
                file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
                file.save(file_path)
                uploaded_urls.append(url_for("static", filename=f"uploads/products/{filename}"))

        if uploaded_urls:
            if image_url:
                image_url = ", ".join(uploaded_urls) + ", " + image_url
            else:
                image_url = ", ".join(uploaded_urls)
        elif not image_url:
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

        w_conn = get_connection()
        w_conn.execute("""
            UPDATE products SET sku=?, name=?, brand=?, category_id=?, sub_category_id=?, sub_sub_category_id=?, cost_price=?, mrp=?, sell_price=?,
                                 vat_pct=?, stock_qty=?, low_stock_threshold=?, sl_number=?,
                                 description=?, image_url=?, is_trending=?, is_flash_sale=?, is_offer=?, is_promotion=?,
                                 offer_title=?, offer_type=?, offer_value=?, offer_base=?, expiry_date=?
            WHERE id=?
        """, (
            request.form["sku"].strip(),
            request.form["name"].strip(),
            brand,
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
        if new_stock_qty > old_stock_qty:
            added = new_stock_qty - old_stock_qty
            create_product_units(w_conn, product_id, added)
            flash(f"Product updated. {added} new printable tag(s) created for the restock.", "success")
        else:
            flash("Product updated.", "success")
        w_conn.commit()
        w_conn.close()
        remote_control.push_product_to_cloud(product_id)
        return redirect(url_for("products"))

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
        remote_control.delete_product_from_cloud(product["sku"])
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

    flash(f"Product '{product['name']}' ({ret_qty} units) moved to Returned Items / Date Expired section.", "success")
    return redirect(url_for("products"))


@app.route("/returned_items")
@login_required
def returned_items():
    conn = get_connection()
    today_date = datetime.now().strftime("%Y-%m-%d")

    # Auto-sync expired items from products table if any expired products exist
    expired_prods = conn.execute("""
        SELECT * FROM products 
        WHERE expiry_date IS NOT NULL AND expiry_date != '' AND expiry_date <= ? AND stock_qty > 0
    """, (today_date,)).fetchall()

    for ep in expired_prods:
        # Check if already logged for this product with 'Expired' reason
        already_logged = conn.execute(
            "SELECT id FROM returned_items WHERE product_id = ? AND reason LIKE '%Expired%'", (ep["id"],)
        ).fetchone()
        if not already_logged:
            conn.execute("""
                INSERT INTO returned_items (product_id, item_name, quantity, reason, expiry_date, date_returned)
                VALUES (?, ?, ?, ?, ?, ?)
            """, (ep["id"], ep["name"], ep["stock_qty"], f"Auto-Sync: Date Expired ({ep['expiry_date']})", ep["expiry_date"], datetime.now().strftime("%Y-%m-%d %H:%M:%S")))

    conn.commit()

    rows = conn.execute("SELECT * FROM returned_items ORDER BY date_returned DESC").fetchall()
    conn.close()
    return render_template("returned_items.html", items=rows)


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

    # Serials already sitting in the cashier's cart (from any product line) -
    # never propose one of these again for this scan.
    exclude = [s for s in request.args.get("exclude", "").split(",") if s]

    conn = get_connection()
    # Every physical tag's barcode encodes the product's SKU (shared across
    # all units of that product), matching how the invoice barcode is coded
    # on the print receipt - so a scan always resolves to a real product.
    product = conn.execute("SELECT * FROM products WHERE sku = ?", (code,)).fetchone()
    if not product:
        conn.close()
        return jsonify({"error": f'No product found for code "{code}".'}), 404

    # Auto-suggest the next available in-stock unit's own serial (SN-xxxxxx)
    # for this line, so the cashier can see - and the sale can record -
    # exactly which physical unit is being sold, even though every tag of
    # this product carries an identical barcode.
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
        "unit_serial": unit["a_code"] if unit else None,
    })


@app.route("/pos")
@login_required
def pos():
    conn = get_connection()
    all_products = conn.execute(
        "SELECT * FROM products WHERE stock_qty > 0 ORDER BY name"
    ).fetchall()
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
    customer_mobile = re.sub(r"\D", "", data.get("customer_mobile", "") or "")

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
        if offer_type == 'buy_x_get_y' or ('buy' in offer_title.lower()):
            buy_qty, free_qty = 2, 1
            if offer_value and ',' in offer_value:
                try:
                    parts = [int(p.strip()) for p in offer_value.split(',')]
                    if len(parts) >= 2:
                        buy_qty, free_qty = parts[0], parts[1]
                except Exception:
                    pass
            total_set = buy_qty + free_qty
            sets = quantity // total_set
            remainder = quantity % total_set
            paid_qty = sets * buy_qty + min(remainder, buy_qty)

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

    # IMPORTANT: rounded_total must include VAT, otherwise the customer is
    # charged/shown a "Net Payable" that is missing the VAT amount even
    # though VAT is computed and displayed on the receipt.
    grand_total = sub_total + total_vat
    rounded_total = round_to_whole(grand_total)
    saved_amount = round(mrp_total - grand_total, 2)
    change_amount = round((cash_amount + card_amount) - rounded_total, 2)

    if change_amount < 0:
        conn.close()
        return jsonify({"error": f"Amount tendered is short by {abs(change_amount):.2f}."}), 400

    invoice_number = generate_invoice_number()
    invoice_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    if customer_mobile and len(customer_mobile) == 11 and customer_mobile.startswith("01"):
        existing_cust = cur.execute("SELECT id FROM customer_users WHERE phone = ?", (customer_mobile,)).fetchone()
        if not existing_cust:
            pass_hash = generate_password_hash("123456")
            name_to_use = customer_name if customer_name else f"Customer {customer_mobile[-4:]}"
            cur.execute("""
                INSERT INTO customer_users (phone, name, email, password_hash, plain_password, created_at)
                VALUES (?, ?, '', ?, '123456', ?)
            """, (customer_mobile, name_to_use, pass_hash, datetime.now().isoformat()))

    cur.execute("""
        INSERT INTO sales (invoice_number, invoice_date, cashier_id, customer_id, customer_name, customer_mobile,
                            total_amount, rounded_total, vat_amount, saved_amount,
                            cash_amount, card_amount, change_amount, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        invoice_number, invoice_date, session["user_id"], customer_name, customer_name, customer_mobile,
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

    # Real-time backup: push this invoice and updated product stocks to Firebase immediately
    remote_control.push_sale_to_cloud(sale_id)
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
@login_required
def sales_history():
    conn = get_connection()
    # Both Admin and Cashier can view all sales and online customer transactions
    rows = conn.execute("""
        SELECT s.*, COALESCE(u.username, 'Online App') AS cashier_name
        FROM sales s LEFT JOIN users u ON s.cashier_id = u.id
        ORDER BY s.created_at DESC
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
        conn.execute("DELETE FROM sale_items WHERE sale_id = ?", (sale_id,))
        conn.execute("DELETE FROM sales WHERE id = ?", (sale_id,))
        conn.commit()
        flash("Sale log entry deleted successfully.", "success")
    else:
        flash("Sale entry not found.", "error")
    conn.close()
    return redirect(url_for("sales_history"))


@app.route("/sales/<int:sale_id>")
@login_required
def sale_receipt(sale_id):
    conn = get_connection()
    sale = conn.execute("""
        SELECT s.*, COALESCE(u.username, 'Online App') AS cashier_name
        FROM sales s LEFT JOIN users u ON s.cashier_id = u.id
        WHERE s.id = ?
    """, (sale_id,)).fetchone()
    items = conn.execute("""
        SELECT si.*, p.name AS product_name, p.sku, p.offer_type, p.offer_value, p.offer_title
        FROM sale_items si JOIN products p ON si.product_id = p.id
        WHERE si.sale_id = ?
    """, (sale_id,)).fetchall()
    settings = get_all_settings(conn)
    conn.close()

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

    customer_directory.sort(key=lambda x: x["last_visit"], reverse=True)
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
    sale = conn.execute("""
        SELECT s.*, COALESCE(u.username, 'Online App') AS cashier_name
        FROM sales s LEFT JOIN users u ON s.cashier_id = u.id
        WHERE s.id = ?
    """, (sale_id,)).fetchone()
    if sale:
        conn.execute("UPDATE sales SET print_count = print_count + 1 WHERE id = ?", (sale_id,))
        conn.commit()
        sale = conn.execute("""
            SELECT s.*, COALESCE(u.username, 'Online App') AS cashier_name
            FROM sales s LEFT JOIN users u ON s.cashier_id = u.id
            WHERE s.id = ?
        """, (sale_id,)).fetchone()
    items = conn.execute("""
        SELECT si.*, p.name AS product_name, p.sku, p.offer_type, p.offer_value, p.offer_title
        FROM sale_items si JOIN products p ON si.product_id = p.id
        WHERE si.sale_id = ?
    """, (sale_id,)).fetchall()
    settings = get_all_settings(conn)
    conn.close()
    
    if not sale:
        flash("Sale not found.", "error")
        return redirect(url_for("sales_history"))

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
    cats = conn.execute("SELECT * FROM categories ORDER BY name").fetchall()
    subs = conn.execute("SELECT * FROM sub_categories ORDER BY name").fetchall()
    subsubs = conn.execute("SELECT * FROM sub_sub_categories ORDER BY name").fetchall()

    cat_counts = dict(conn.execute("SELECT category_id, COUNT(*) FROM products WHERE category_id IS NOT NULL GROUP BY category_id").fetchall())
    sub_counts = dict(conn.execute("SELECT sub_category_id, COUNT(*) FROM products WHERE sub_category_id IS NOT NULL GROUP BY sub_category_id").fetchall())
    subsub_counts = dict(conn.execute("SELECT sub_sub_category_id, COUNT(*) FROM products WHERE sub_sub_category_id IS NOT NULL GROUP BY sub_sub_category_id").fetchall())
    uncategorized_count = conn.execute("SELECT COUNT(*) FROM products WHERE category_id IS NULL OR category_id NOT IN (SELECT id FROM categories)").fetchone()[0]
    conn.close()
    
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

    # Append virtual 'Uncategorized' category node
    cat_list.append({
        "id": -1,
        "name": "Uncategorized",
        "icon": "📦",
        "product_count": uncategorized_count,
        "sub_categories": []
    })
    return jsonify(cat_list)


@app.route("/offers", methods=["GET"])
@login_required
@admin_required
def offers_page():
    conn = get_connection()
    all_products = conn.execute("SELECT * FROM products ORDER BY name").fetchall()
    offer_products = conn.execute("""
        SELECT p.*, c.name AS category_name
        FROM products p
        LEFT JOIN categories c ON p.category_id = c.id
        WHERE p.is_offer = 1 OR p.is_promotion = 1 OR p.offer_type = 'bogo'
        ORDER BY p.id DESC
    """).fetchall()
    categories = conn.execute("SELECT * FROM categories ORDER BY name").fetchall()
    sub_categories = conn.execute("SELECT * FROM sub_categories ORDER BY name").fetchall()
    sub_sub_categories = conn.execute("SELECT * FROM sub_sub_categories ORDER BY name").fetchall()
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
            flash(f"Voucher '{code}' created successfully.", "success")
        except Exception as e:
            flash(f"Could not create voucher: {e}", "error")
        conn.close()
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
            flash(f"Voucher '{code}' updated successfully.", "success")
        except Exception as e:
            flash(f"Could not update voucher: {e}", "error")
    else:
        flash("Please provide a valid voucher code and discount value.", "error")
    conn.close()
    return redirect(url_for("offers_page"))


@app.route("/vouchers/<int:voucher_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_voucher(voucher_id):
    conn = get_connection()
    conn.execute("DELETE FROM vouchers WHERE id = ?", (voucher_id,))
    conn.commit()
    conn.close()
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

    total_eligible_price = 0.0

    for item in cart_items:
        p_id = item.get("product_id")
        qty = int(item.get("quantity") or 1)
        sell_price = float(item.get("price") or 0)

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

    if offer_type == "bogo" and not offer_title:
        offer_title = f"Buy {offer_value or '1'} Get 1 Free"
        is_offer = 1

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

    # Offline POS counter sales summary
    offline_sales_summary = conn.execute(f"""
        SELECT 
            COALESCE(SUM(rounded_total), 0) AS revenue,
            COALESCE(SUM(vat_amount), 0) AS vat,
            COALESCE(SUM(saved_amount), 0) AS discounts,
            COUNT(id) AS tx_count
        FROM sales WHERE (channel IS NULL OR channel != 'Online') AND {date_filter}
    """).fetchone()

    # Online orders summary (direct from online_orders table)
    online_orders_summary = conn.execute(f"""
        SELECT 
            COUNT(*) AS tx_count,
            COALESCE(SUM(total_amount), 0) AS revenue
        FROM online_orders WHERE {date_filter}
    """).fetchone()

    # Offline COGS
    offline_cogs_row = conn.execute(f"""
        SELECT COALESCE(SUM(si.quantity * si.cost_price), 0) AS total_cogs
        FROM sale_items si
        JOIN sales s ON si.sale_id = s.id
        WHERE (s.channel IS NULL OR s.channel != 'Online') AND {date_filter.replace('created_at', 's.created_at')}
    """).fetchone()

    # Online COGS
    online_cogs_row = conn.execute(f"""
        SELECT COALESCE(SUM(oi.quantity * COALESCE(p.cost_price, oi.unit_price * 0.7)), 0) AS total_cogs
        FROM online_order_items oi
        JOIN online_orders o ON oi.order_id = o.id
        LEFT JOIN products p ON oi.product_id = p.id
        WHERE {date_filter.replace('created_at', 'o.created_at')}
    """).fetchone()

    pos_rev = float(offline_sales_summary["revenue"])
    online_rev = float(online_orders_summary["revenue"])
    revenue = pos_rev + online_rev

    pos_cnt = int(offline_sales_summary["tx_count"])
    online_cnt = int(online_orders_summary["tx_count"])
    tx_count = pos_cnt + online_cnt

    cogs = float(offline_cogs_row["total_cogs"]) + float(online_cogs_row["total_cogs"])
    gross_profit = revenue - cogs

    income_row = conn.execute(f"""
        SELECT COALESCE(SUM(amount), 0) AS total
        FROM ledger_entries WHERE entry_type='income' AND {ledger_filter}
    """).fetchone()
    other_income = float(income_row["total"])

    expense_row = conn.execute(f"""
        SELECT COALESCE(SUM(amount), 0) AS total
        FROM ledger_entries WHERE entry_type='expense' AND {ledger_filter}
    """).fetchone()
    other_expenses = float(expense_row["total"])

    # Net profit calculation formula
    net_profit = (gross_profit + other_income) - other_expenses

    ledger_entries = conn.execute(f"""
        SELECT * FROM ledger_entries
        WHERE {ledger_filter}
        ORDER BY entry_date DESC, id DESC
    """).fetchall()

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
        revenue=revenue,
        cogs=cogs,
        gross_profit=gross_profit,
        other_income=other_income,
        other_expenses=other_expenses,
        net_profit=net_profit,
        ledger_entries=ledger_entries,
        top_products=top_products,
        slow_movers=slow_movers,
        dead_stock=dead_stock,
        total_units_sold=total_units_sold,
        max_qty_sold=max_qty_sold,
        tx_count=tx_count,
        online_summary={"tx_count": online_cnt, "revenue": online_rev},
        offline_summary={"tx_count": pos_cnt, "revenue": pos_rev}
    )


@app.route("/reports/entry/new", methods=["POST"])
@login_required
@admin_required
def add_ledger_entry():
    title = request.form["title"].strip()
    entry_type = request.form["entry_type"]
    amount = float(request.form.get("amount") or 0)
    entry_date = request.form["entry_date"] or date.today().isoformat()

    conn = get_connection()
    conn.execute(
        "INSERT INTO ledger_entries (entry_type, title, amount, entry_date, created_at) VALUES (?, ?, ?, ?, ?)",
        (entry_type, title, amount, entry_date, datetime.now().isoformat())
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

    conn = get_connection()
    conn.execute(
        "UPDATE ledger_entries SET title=?, entry_type=?, amount=?, entry_date=? WHERE id=?",
        (title, entry_type, amount, entry_date, entry_id)
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
        item_list = [dict(i) for i in items]
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
    conn.execute("DELETE FROM online_order_items WHERE order_id = ?", (order_id,))
    conn.execute("DELETE FROM online_orders WHERE id = ?", (order_id,))
    conn.commit()
    conn.close()
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
        # Create sale record if not created yet
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
def api_settings():
    settings = get_all_settings()
    settings["logo_url"] = url_for("static", filename="images/logo.png", _external=True)
    if not settings.get("customer_support_phone"):
        settings["customer_support_phone"] = settings.get("shop_phone", "")
    return jsonify(settings)


@app.route("/api/products", methods=["GET"])
def api_products():
    conn = get_connection()
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
    conn.close()

    result = []
    for r in rows:
        d = dict(r)
        img = (d.get("image_url") or "").strip()
        if img:
            parts = [p.strip() for p in img.split(",") if p.strip()]
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
        
        prod = None
        if prod_id is not None:
            try:
                prod = conn.execute("SELECT * FROM products WHERE id = ?", (int(prod_id),)).fetchone()
            except Exception:
                prod = conn.execute("SELECT * FROM products WHERE id = ?", (prod_id,)).fetchone()
        
        if not prod:
            p_title = (item.get("product_name") or item.get("name") or item.get("title") or "").strip()
            if p_title:
                prod = conn.execute("SELECT * FROM products WHERE LOWER(name) = LOWER(?)", (p_title,)).fetchone()

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
            sku_val = (item.get("sku") or "").strip()
            p_name = (item.get("product_name") or item.get("name") or item.get("title") or "Item").strip()
            if sku_val and "(" in sku_val:
                p_name = sku_val
            unit_price = float(item.get("unit_price") or item.get("sell_price") or item.get("price") or 0.0)
            mrp_price = float(item.get("mrp_price") or item.get("mrp") or unit_price)
            offer_type = ""
            offer_value = ""
            offer_title = ""

        paid_qty = qty
        actual_qty = qty

        if offer_type == 'buy_x_get_y' or ('buy' in offer_title.lower()):
            buy_qty, free_qty_set = 2, 1
            if offer_value and ',' in offer_value:
                try:
                    parts = [int(p.strip()) for p in offer_value.split(',')]
                    if len(parts) >= 2:
                        buy_qty, free_qty_set = parts[0], parts[1]
                except Exception:
                    pass
            
            total_set = buy_qty + free_qty_set
            if qty % total_set == 0:
                paid_qty = (qty // total_set) * buy_qty
                actual_qty = qty
            elif qty >= buy_qty:
                free_items = (qty // buy_qty) * free_qty_set
                paid_qty = qty
                actual_qty = qty + free_items

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

    cur = conn.cursor()
    cur.execute("""
        INSERT INTO online_orders (
            order_number, customer_name, customer_phone, customer_email,
            country, district, area, address_details, payment_method,
            payment_status, subtotal, delivery_charge, total_amount,
            order_status, delivery_otp, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'new', ?, ?, ?)
    """, (
        order_number, customer_name, customer_phone, customer_email,
        country, district, area, address_details, payment_method,
        "pending" if payment_method == "cod" else "paid",
        subtotal, delivery_charge, total_amount, otp, created_at, created_at
    ))

    order_id = cur.lastrowid

    for item in processed_items:
        cur.execute("""
            INSERT INTO online_order_items (order_id, product_id, product_name, unit_price, mrp_price, quantity, total_price)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (order_id, item["product_id"], item["product_name"], item["unit_price"], item["mrp_price"], item["quantity"], item["total_price"]))

        cur.execute(
            "UPDATE products SET stock_qty = MAX(0, stock_qty - ?) WHERE id = ?",
            (item["quantity"], item["product_id"])
        )
        remote_control.push_product_to_cloud(item["product_id"])

    cur.execute("UPDATE online_orders SET is_stock_deducted = 1 WHERE id = ?", (order_id,))
    conn.commit()
    conn.close()

    remote_control.push_online_order_to_cloud(order_id)

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


# In-memory OTP storage for verification (Phone -> OTP Code + Expiry)
OTP_STORE = {}

def send_sms_otp(phone, otp_code):
    """
    Sends cellular SMS / WhatsApp OTP directly to the customer's mobile number.
    Integrates with Bangladesh SMS API (e.g., BulkSMSBD, Greenweb, Gp/Robi) or WhatsApp.
    """
    sms_api_key = os.environ.get("SMS_API_KEY", "")
    if sms_api_key:
        try:
            import requests
            url = f"https://api.bulksmsbd.net/smsapi?api_key={sms_api_key}&type=text&number={phone}&senderid=8809612000000&message=Your+DOINEEK+Supershop+OTP+code+is+{otp_code}"
            requests.get(url, timeout=5)
        except Exception as e:
            print(f"SMS API Send Error: {e}")


@app.route("/api/customer/send-otp", methods=["POST"])
def api_customer_send_otp():
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

    conn.close()

    import random
    otp_code = f"{random.randint(1000, 9999)}"
    OTP_STORE[phone] = {
        "otp": otp_code,
        "created_at": datetime.now()
    }

    # Dispatch cellular SMS / WhatsApp OTP
    send_sms_otp(phone, otp_code)

    return jsonify({
        "success": True,
        "message": f"OTP verification code sent to {phone}. Please check your SMS inbox.",
        "whatsapp_url": f"https://wa.me/88{phone}?text=Your%20DOINEEK%20Supershop%20OTP%20Code%20is%20{otp_code}"
    })


@app.route("/api/customer/verify-otp", methods=["POST"])
def api_customer_verify_otp():
    data = request.json or {}
    phone = data.get("phone", "").strip()
    otp_input = data.get("otp", "").strip()

    record = OTP_STORE.get(phone)
    if not record:
        return jsonify({"success": False, "message": "OTP expired or not found. Please request a new OTP."}), 400

    if record["otp"] == otp_input:
        return jsonify({"success": True, "message": "OTP verified successfully!"})
    else:
        return jsonify({"success": False, "message": "Invalid OTP code. Please enter the correct code from your SMS inbox."}), 400


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
        flash(f"Package '{name}' updated successfully.", "success")
    else:
        flash("Please enter package name, price, and select at least 1 product.", "error")
    conn.close()
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
    flash("Product package deleted successfully.", "success")
    return redirect(url_for("packages_page"))


@app.route("/api/packages", methods=["GET"])
def api_packages():
    conn = get_connection()
    pkg_rows = conn.execute("SELECT * FROM packages WHERE is_active = 1 ORDER BY id DESC").fetchall()
    packages_list = []
    for pkg in pkg_rows:
        p_dict = dict(pkg)
        items = conn.execute("""
            SELECT pi.*, p.name AS product_name, p.sell_price, p.mrp, p.image_url
            FROM package_items pi JOIN products p ON pi.product_id = p.id
            WHERE pi.package_id = ?
        """, (pkg["id"],)).fetchall()
        p_dict["items"] = [dict(i) for i in items]
        packages_list.append(p_dict)
    conn.close()
    return jsonify(packages_list)


# ===========================================================================
# Application Entry Point & Automatic Real-Time Firebase Listener
# ===========================================================================

try:
    init_db()
    remote_control.start()
    remote_control.push_categories_to_cloud()
except Exception as _rc_err:
    print(f"[app.py] Automatic Firebase listener initialization: {_rc_err}")

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000, use_reloader=False)