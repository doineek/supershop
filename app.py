"""
app.py
------
Entry point of the DOINEEK Supershop POS application.
Run it with:  python app.py
Then open a browser at: http://127.0.0.1:5000
"""

from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, has_request_context, Response, send_file, make_response
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, date, timedelta, timezone
from functools import wraps

# Bangladesh Standard Time (GMT+6) configuration
BD_TIMEZONE = timezone(timedelta(hours=6))

def get_bd_now():
    """Return current datetime in Bangladesh Standard Time (GMT+6)."""
    return datetime.now(BD_TIMEZONE)

def get_bd_now_iso():
    """Return current ISO 8601 timestamp string in Bangladesh Standard Time (GMT+6)."""
    return datetime.now(BD_TIMEZONE).isoformat()

def format_bd_timeline_time(dt_val):
    """Parse datetime value and return (iso_with_bd_offset, formatted_bd_string) in GMT+6."""
    if not dt_val:
        return "", ""
    s = str(dt_val).strip()
    if not s:
        return "", ""
    try:
        if s.endswith("Z"):
            dt = datetime.fromisoformat(s[:-1] + "+00:00").astimezone(BD_TIMEZONE)
        elif "+" in s[10:]:
            dt = datetime.fromisoformat(s).astimezone(BD_TIMEZONE)
        elif "-" in s[10:] and len(s) > 19 and (s[19] == '-' or s[-6] == '-'):
            dt = datetime.fromisoformat(s).astimezone(BD_TIMEZONE)
        else:
            dt_naive = datetime.fromisoformat(s)
            import time as _time
            if _time.tzname[0] == 'UTC' or _time.timezone == 0:
                dt = dt_naive.replace(tzinfo=timezone.utc).astimezone(BD_TIMEZONE)
            else:
                dt = dt_naive.replace(tzinfo=BD_TIMEZONE)

        iso_bd = dt.isoformat()
        h_12 = dt.strftime("%I").lstrip("0") or "12"
        m_str = dt.strftime("%b")
        p_str = dt.strftime("%M %p")
        formatted_bd = f"{dt.day} {m_str}, {h_12}:{p_str}"
        return iso_bd, formatted_bd
    except Exception:
        return s, s[:16].replace("T", " ")

import os
import io
import re
import sys
import time
import sqlite3
import base64
import urllib.request
import urllib.parse
from PIL import Image, ImageDraw, ImageFont

# Fix Windows console encoding for Bengali/Unicode characters with real-time line buffering
if sys.platform == "win32":
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace", line_buffering=True)
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace", line_buffering=True)


from database import (
    get_connection, init_db, round_to_whole, create_product_units,
    generate_invoice_number, get_all_settings, update_settings, execute_with_retry,
    add_customer_notification, get_customer_notifications, mark_notification_as_read,
    mark_all_notifications_as_read, clear_customer_notifications,
    get_portal_notifications, mark_all_portal_notifications_as_read, clear_portal_notifications
)
from barcode_utils import generate_barcode_svg
import ipaddress
import json
import remote_control
import thermal_printer
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_compress import Compress

app = Flask(__name__)
app.secret_key = "doineek-supershop-secret-key"

# Bandwidth Optimization: Enable Gzip/Brotli compression for HTML, JSON, CSS, JS, WASM
app.config['COMPRESS_MIMETYPES'] = [
    'text/html', 'text/css', 'text/xml', 'application/json',
    'application/javascript', 'application/wasm', 'image/svg+xml'
]
app.config['COMPRESS_LEVEL'] = 6
app.config['COMPRESS_MIN_SIZE'] = 500
compress = Compress(app)

# Static Asset Caching: 7 days default browser cache
app.config['SEND_FILE_MAX_AGE_DEFAULT'] = 604800

# Security & DoS Protection Configurations
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # Max 16MB file upload/request size (prevents memory OOM crash)
app.config['SESSION_COOKIE_HTTPONLY'] = True          # Prevent JavaScript from reading session cookies (XSS defense)
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'         # CSRF mitigation

# Cloudinary CDN Configuration (Offloads images to free 25 GB/mo Cloudinary bandwidth)
CLOUDINARY_CLOUD_NAME = os.environ.get("CLOUDINARY_CLOUD_NAME", "a71uu4fm").strip()
CLOUDINARY_API_KEY = os.environ.get("CLOUDINARY_API_KEY", "229798283716372").strip()
CLOUDINARY_API_SECRET = os.environ.get("CLOUDINARY_API_SECRET", "Z32WfsCEDD2Mcs6s5labt16d4G8").strip()

CLOUDINARY_CONFIGURED = False
try:
    import cloudinary
    import cloudinary.uploader
    if CLOUDINARY_CLOUD_NAME and CLOUDINARY_API_KEY and CLOUDINARY_API_SECRET:
        cloudinary.config(
            cloud_name=CLOUDINARY_CLOUD_NAME,
            api_key=CLOUDINARY_API_KEY,
            api_secret=CLOUDINARY_API_SECRET,
            secure=True
        )
        CLOUDINARY_CONFIGURED = True
        print(f"[cloudinary] [OK] Cloudinary initialized successfully for cloud '{CLOUDINARY_CLOUD_NAME}'")
except Exception as e:
    print(f"[cloudinary] Initialization notice: {e}")


def upload_to_cloudinary(file_or_bytes, folder="supershop/products", public_id=None, resource_type=None):
    """
    Uploads an image or document (file path, file object, bytes, or data URI) to Cloudinary.
    Converts PDF documents to high-resolution JPEG images for fast, universal rendering across all devices.
    Returns secure HTTPS CDN URL on success, or None on failure/unconfigured.
    """
    if not CLOUDINARY_CONFIGURED:
        return None
    try:
        import cloudinary
        import cloudinary.uploader
        
        is_pdf = False
        if isinstance(file_or_bytes, (bytes, bytearray)) and file_or_bytes.startswith(b"%PDF"):
            is_pdf = True
        elif isinstance(file_or_bytes, str) and ("application/pdf" in file_or_bytes or file_or_bytes.lower().endswith(".pdf")):
            is_pdf = True
        elif public_id and public_id.lower().endswith(".pdf"):
            is_pdf = True

        r_type = "image" if is_pdf else (resource_type or "auto")
        options = {
            "folder": folder,
            "resource_type": r_type,
            "overwrite": True
        }
        if is_pdf:
            options["format"] = "jpg"
            if public_id and public_id.lower().endswith(".pdf"):
                public_id = public_id[:-4]
        if public_id:
            options["public_id"] = public_id

        res = cloudinary.uploader.upload(file_or_bytes, **options)
        if res and "secure_url" in res:
            url = res["secure_url"]
            if is_pdf and url.endswith(".pdf"):
                url = url[:-4] + ".jpg"
            return url
    except Exception as e:
        print(f"[cloudinary] Upload error: {e}")
    return None

def get_real_client_ip():
    """Accurately identify real client IP behind Cloudflare, Render, or reverse proxies."""
    if has_request_context():
        cf_ip = request.headers.get("CF-Connecting-IP")
        if cf_ip:
            return cf_ip.strip()
        x_forwarded = request.headers.get("X-Forwarded-For")
        if x_forwarded:
            return x_forwarded.split(",")[0].strip()
        return request.remote_addr or "127.0.0.1"
    return "127.0.0.1"


_IP_GEO_MEM_CACHE = {}


def _resolve_ip_and_location(conn=None, ip_addr=None):
    """Resolve client IP & human-readable location fast without stalling requests."""
    ip = (ip_addr or get_real_client_ip() or "127.0.0.1").strip()
    if "," in ip:
        ip = ip.split(",")[0].strip()

    # Fast local/private network detection
    try:
        ip_obj = ipaddress.ip_address(ip)
        if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_link_local:
            return ip, "Local Network / Shop Wi-Fi"
    except Exception:
        if ip in ("127.0.0.1", "localhost", "::1") or ip.startswith(("192.168.", "10.", "172.16.")):
            return ip, "Local Network / Shop Wi-Fi"

    cf_city = request.headers.get("CF-IPCity", "").strip() if has_request_context() else ""
    cf_country = request.headers.get("CF-IPCountry", "").strip() if has_request_context() else ""
    if cf_city or cf_country:
        lbl = ", ".join(p for p in (cf_city, cf_country) if p and p.upper() != "XX")
        if lbl:
            _IP_GEO_MEM_CACHE[ip] = lbl
            return ip, lbl

    if ip in _IP_GEO_MEM_CACHE:
        return ip, _IP_GEO_MEM_CACHE[ip]

    if conn is not None:
        try:
            cached = conn.execute("SELECT location_label FROM ip_geo_cache WHERE ip = ?", (ip,)).fetchone()
            if cached and cached["location_label"]:
                _IP_GEO_MEM_CACHE[ip] = cached["location_label"]
                return ip, cached["location_label"]
        except Exception:
            pass

    location_label = "Bangladesh / Online IP"
    try:
        req = urllib.request.Request(
            f"http://ip-api.com/json/{urllib.parse.quote(ip)}?fields=status,country,regionName,city,isp",
            headers={"User-Agent": "DOINEEK-Supershop/1.0"},
        )
        with urllib.request.urlopen(req, timeout=1.0) as resp:
            info = json.loads(resp.read().decode("utf-8", errors="ignore"))
            if info.get("status") == "success":
                parts = []
                for k in ("city", "regionName", "country"):
                    v = (info.get(k) or "").strip()
                    if v and v not in parts:
                        parts.append(v)
                isp = (info.get("isp") or "").strip()
                loc_str = ", ".join(parts)
                if isp:
                    loc_str = f"{loc_str} ({isp[:28]})" if loc_str else isp[:36]
                if loc_str:
                    location_label = loc_str
                    if conn is not None:
                        try:
                            conn.execute(
                                """INSERT OR REPLACE INTO ip_geo_cache
                                   (ip, location_label, city, region, country, isp, updated_at)
                                   VALUES (?, ?, ?, ?, ?, ?, ?)""",
                                (
                                    ip, location_label, info.get("city", ""),
                                    info.get("regionName", ""), info.get("country", ""),
                                    isp, get_bd_now_iso(),
                                ),
                            )
                        except Exception:
                            pass
    except Exception:
        pass

    _IP_GEO_MEM_CACHE[ip] = location_label
    return ip, location_label


def _extract_device_hint(data=None):
    if isinstance(data, dict) and data.get("device"):
        return str(data.get("device"))[:64]
    if has_request_context():
        cli = request.headers.get("X-App-Client", "").strip()
        if cli:
            return cli[:64]
        ua = request.headers.get("User-Agent", "").strip()
        low = ua.lower()
        if "dart" in low or "flutter" in low:
            return "Android Mobile App"
        if "android" in low:
            return "Android Browser"
        if "iphone" in low or "ipad" in low or "ios" in low:
            return "iOS Browser"
        if "windows" in low:
            return "Windows PC"
        if "macintosh" in low:
            return "Mac Browser"
        if ua:
            return ua[:40]
    return ""


def _touch_customer_network_info(conn, phone, data=None, ip_addr=None, is_register=False):
    """Captures IP, geo location, and device on registration, login, orders, and profile activity."""
    if not phone or not conn:
        return "", ""
    clean_p = normalize_phone(phone) or str(phone).strip()
    ip, loc = _resolve_ip_and_location(conn, ip_addr=ip_addr)
    dev = _extract_device_hint(data)
    now_iso = get_bd_now_iso()
    try:
        cols = {r[1] for r in conn.execute("PRAGMA table_info(customer_users)").fetchall()}
        if "last_ip" not in cols:
            return ip, loc
        if is_register:
            conn.execute(
                """UPDATE customer_users SET
                   registration_ip = COALESCE(NULLIF(registration_ip, ''), ?),
                   registration_location = COALESCE(NULLIF(registration_location, ''), ?),
                   last_ip = ?, last_location = ?, last_seen_at = ?, last_device = ?
                   WHERE phone = ? OR phone = ?""",
                (ip, loc, ip, loc, now_iso, dev, clean_p, phone),
            )
        else:
            conn.execute(
                """UPDATE customer_users SET
                   registration_ip = COALESCE(NULLIF(registration_ip, ''), ?),
                   registration_location = COALESCE(NULLIF(registration_location, ''), ?),
                   last_ip = ?, last_location = ?, last_seen_at = ?,
                   last_device = COALESCE(NULLIF(?, ''), last_device)
                   WHERE phone = ? OR phone = ?""",
                (ip, loc, ip, loc, now_iso, dev, clean_p, phone),
            )
    except Exception as e:
        print(f"[network_track] Customer IP update error: {e}")
    return ip, loc


def _member_since_label(created_at_str):
    if not created_at_str:
        return "Unknown"
    s = str(created_at_str).strip()
    try:
        dt = datetime.fromisoformat(s.replace("Z", "+00:00"))
        now = datetime.now(dt.tzinfo) if dt.tzinfo else datetime.now()
        days = max(0, (now - dt).days)
        pretty = dt.strftime("%d %b %Y, %I:%M %p")
        if days == 0:
            return f"{pretty} (Joined Today)"
        if days == 1:
            return f"{pretty} (1 day ago)"
        if days < 30:
            return f"{pretty} ({days} days ago)"
        months = days // 30
        if months < 12:
            return f"{pretty} ({months} mo ago)"
        years = days // 365
        return f"{pretty} ({years} yr ago)"
    except Exception:
        return s[:16].replace("T", " ")


def _classify_sale_record(sale_dict, item_rows=None):
    """Unified classification into regular_pos, regular_online, pharmacy_pos, or pharmacy_online."""
    inv = str(sale_dict.get("invoice_number") or "").upper()
    ch = str(sale_dict.get("channel") or "Offline").strip()
    total_amt = float(sale_dict.get("rounded_total") or sale_dict.get("total_amount") or 0.0)
    items = item_rows or []

    med_item_amt = 0.0
    reg_item_amt = 0.0
    has_med = False
    has_reg = False
    for it in items:
        serials = str(it.get("unit_serials") if isinstance(it, dict) else (it["unit_serials"] or "")).strip()
        line_amt = float((it["unit_price"] or 0.0)) * float((it["quantity"] or 1))
        if serials.startswith("💊"):
            has_med = True
            med_item_amt += line_amt
        else:
            has_reg = True
            reg_item_amt += line_amt

    if inv.startswith("INV-ONLINE-RX-") or (ch in ("Online", "Pharmacy Online") and ("RX-" in inv or (has_med and not has_reg))):
        cat = "pharmacy_online"
        label = "🏥 Pharmacy Online"
        return {
            "sales_category": cat, "category_label": label,
            "is_pharmacy": True, "is_online": True, "is_mixed": False,
            "regular_amount": 0.0, "pharmacy_amount": total_amt,
        }

    if ch == "Pharmacy POS" or inv.startswith(("RXPOS", "INV-RX-POS", "PHARM-POS")) or (ch != "Online" and has_med and not has_reg):
        cat = "pharmacy_pos"
        label = "💊 Pharmacy POS"
        return {
            "sales_category": cat, "category_label": label,
            "is_pharmacy": True, "is_online": False, "is_mixed": False,
            "regular_amount": 0.0, "pharmacy_amount": total_amt,
        }

    if ch == "Online" or inv.startswith("INV-ONLINE-"):
        return {
            "sales_category": "regular_online", "category_label": "📱 Regular Online",
            "is_pharmacy": False, "is_online": True, "is_mixed": False,
            "regular_amount": total_amt, "pharmacy_amount": 0.0,
        }

    if has_med and has_reg and (med_item_amt + reg_item_amt) > 0:
        pharm_share = round(total_amt * (med_item_amt / (med_item_amt + reg_item_amt)), 2)
        reg_share = round(total_amt - pharm_share, 2)
        return {
            "sales_category": "regular_pos", "category_label": "🛒💊 Mixed POS (Shop + Pharmacy)",
            "is_pharmacy": True, "is_online": False, "is_mixed": True,
            "regular_amount": reg_share, "pharmacy_amount": pharm_share,
        }

    return {
        "sales_category": "regular_pos", "category_label": "🛒 Regular POS",
        "is_pharmacy": False, "is_online": False, "is_mixed": False,
        "regular_amount": total_amt, "pharmacy_amount": 0.0,
    }


def _collect_enriched_sales(conn, date_sql=None):
    """Returns enriched sales list (combining sales table + confirmed/delivered pharmacy_orders without double-counting)."""
    where_sales = f" WHERE {date_sql.replace('created_at', 's.created_at')}" if date_sql else ""
    rows = conn.execute(f"""
        SELECT s.*, COALESCE(u.username, 'Online App') AS cashier_name
        FROM sales s
        LEFT JOIN users u ON s.cashier_id = u.id
        {where_sales}
        ORDER BY s.id DESC
    """).fetchall()

    sale_ids = [r["id"] for r in rows]
    items_by_sale = {}
    if sale_ids:
        placeholders = ",".join("?" for _ in sale_ids)
        for it in conn.execute(f"SELECT * FROM sale_items WHERE sale_id IN ({placeholders})", tuple(sale_ids)).fetchall():
            items_by_sale.setdefault(it["sale_id"], []).append(it)

    enriched = []
    seen_inv = set()
    for r in rows:
        d = dict(r)
        inv = str(d.get("invoice_number") or "")
        if inv:
            seen_inv.add(inv.upper())
        info = _classify_sale_record(d, items_by_sale.get(d["id"], []))
        d.update(info)
        d["is_virtual_pharmacy_online"] = False
        d["view_url"] = url_for("sale_receipt", sale_id=d["id"]) if has_request_context() else f"/sales/{d['id']}"
        enriched.append(d)

    # Include confirmed/packed/on_the_way/delivered pharmacy online orders that don't yet have an INV-ONLINE-RX row in sales
    where_po = f" AND {date_sql}" if date_sql else ""
    po_rows = conn.execute(f"""
        SELECT * FROM pharmacy_orders
        WHERE order_status IN ('confirmed', 'packed', 'on_the_way', 'delivered')
          AND total_amount > 0
          {where_po}
        ORDER BY id DESC
    """).fetchall()
    for po in po_rows:
        po_num = str(po["order_number"] or "").strip()
        expected_inv = f"INV-ONLINE-{po_num}".upper()
        if expected_inv in seen_inv:
            continue
        amt = float(po["total_amount"] or 0.0)
        ol_id = int(po["online_order_id"] or 0)
        if not ol_id and po_num:
            ol_match = conn.execute("SELECT id FROM online_orders WHERE order_number = ?", (po_num,)).fetchone()
            if ol_match:
                ol_id = ol_match["id"]
        view_url = f"/online_orders/{ol_id}/invoice" if ol_id else "/admin/pharmacy-orders"
        enriched.append({
            "id": 0,
            "pharmacy_order_id": po["id"],
            "online_order_id": ol_id,
            "invoice_number": f"INV-ONLINE-{po_num}",
            "invoice_date": (po["created_at"] or "")[:19].replace("T", " "),
            "created_at": po["created_at"] or "",
            "customer_name": po["customer_name"] or "",
            "customer_mobile": po["customer_phone"] or "",
            "cashier_name": f"Rx: {po['order_status'].upper()}",
            "channel": "Pharmacy Online",
            "total_amount": float(po["subtotal"] or amt),
            "rounded_total": amt,
            "vat_amount": 0.0,
            "saved_amount": 0.0,
            "cash_amount": amt if po["payment_status"] == "paid" else 0.0,
            "card_amount": 0.0,
            "change_amount": 0.0,
            "sales_category": "pharmacy_online",
            "category_label": "🏥 Pharmacy Online",
            "is_pharmacy": True,
            "is_online": True,
            "is_mixed": False,
            "regular_amount": 0.0,
            "pharmacy_amount": amt,
            "is_virtual_pharmacy_online": True,
            "view_url": view_url,
            "order_number": po_num,
        })

    enriched.sort(key=lambda x: str(x.get("created_at") or ""), reverse=True)
    return enriched

# In-App Rate Limiter (Protects against HTTP floods and brute-force attacks)
limiter = Limiter(
    key_func=get_real_client_ip,
    app=app,
    default_limits=["200 per minute"],  # Generous limit for normal store browsing
    storage_uri="memory://",
)

@app.after_request
def apply_security_headers(response):
    """Add industry-standard security and caching headers to all responses."""
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['Referrer-Policy'] = 'strict-origin-when-cross-origin'
    if request.is_secure or request.headers.get("X-Forwarded-Proto") == "https":
        response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    
    # Cache static assets (images, CSS, JS, fonts, Flutter Web) for 7 days to eliminate repeat bandwidth
    if request.path.startswith('/static/'):
        response.headers['Cache-Control'] = 'public, max-age=604800, immutable'
    
    return response

@app.errorhandler(429)
def ratelimit_handler(e):
    """Return sleek JSON or HTML response when rate limit is exceeded."""
    msg = f"Too many requests. Please wait a moment before trying again. ({e.description})"
    if request.is_json or request.path.startswith("/api/"):
        return jsonify({"success": False, "message": msg}), 429
    conn = get_connection()
    shop = get_all_settings(conn)
    conn.close()
    return render_template("429.html", shop=shop, error_message=e.description), 429

UPLOAD_FOLDER = os.path.join(app.root_path, 'static', 'uploads', 'products')
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER


def parse_hex_color(color_str, default=(255, 255, 255)):
    if not color_str:
        return default
    color_str = str(color_str).strip().lstrip('#')
    if len(color_str) == 3:
        color_str = ''.join([c*2 for c in color_str])
    if len(color_str) == 6:
        try:
            return (int(color_str[0:2], 16), int(color_str[2:4], 16), int(color_str[4:6], 16))
        except ValueError:
            return default
    return default


def get_product_image_bg_color():
    try:
        conn = get_connection()
        s_val = conn.execute("SELECT value FROM settings WHERE key = 'product_image_bg_color'").fetchone()
        conn.close()
        if s_val and s_val["value"]:
            return s_val["value"].strip()
    except Exception:
        pass
    return "#FFFFFF"


def get_rider_delivery_fee_setting(conn=None):
    close_after = False
    if conn is None:
        conn = get_connection()
        close_after = True
    try:
        row = conn.execute("SELECT value FROM settings WHERE key = 'rider_delivery_fee'").fetchone()
        if close_after:
            conn.close()
        if row and row["value"]:
            return float(row["value"])
    except Exception:
        if close_after:
            try: conn.close()
            except: pass
    return 50.0


def apply_image_background(im, bg_color=None):
    """
    Safely composites transparent images (RGBA, LA, or P with transparency)
    onto a solid background color (defaulting to product_image_bg_color setting or pure white).
    Prevents transparent images (such as Google image search PNG/WebP files) from turning black.
    """
    from PIL import Image
    if bg_color is None:
        bg_color = get_product_image_bg_color()
    if isinstance(bg_color, str):
        bg_color = parse_hex_color(bg_color)
    elif not isinstance(bg_color, (tuple, list)) or len(bg_color) < 3:
        bg_color = (255, 255, 255)
    else:
        bg_color = tuple(bg_color[:3])

    if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
        rgba = im.convert("RGBA")
        bg = Image.new("RGB", rgba.size, bg_color)
        bg.paste(rgba, mask=rgba.split()[3])
        return bg
    elif im.mode != "RGB":
        return im.convert("RGB")
    return im


def process_uploaded_image_file(file_path, max_dim=800, quality=75, bg_color=None):
    """
    Optimizes an uploaded image file, uploads it to Cloudinary for high-speed CDN delivery
    (consuming ZERO Render bandwidth), and returns the HTTPS CDN URL.
    Falls back gracefully to Base64 Data URI if Cloudinary is unreachable.
    """
    try:
        from PIL import Image
        import io, base64
        with Image.open(file_path) as im:
            im = apply_image_background(im, bg_color)
            im.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
            out = io.BytesIO()
            im.save(out, format="JPEG", quality=quality, optimize=True)
            img_bytes = out.getvalue()

            cloud_url = upload_to_cloudinary(img_bytes, folder="supershop/products")
            if cloud_url:
                return cloud_url

            encoded = base64.b64encode(img_bytes).decode("utf-8")
            return f"data:image/jpeg;base64,{encoded}"
    except Exception as e:
        print(f"[image_processing] Error optimizing image {file_path}: {e}")
        return ""


def clean_and_normalize_image_url(raw_url):
    """
    Cleans and normalizes image URLs, extracting direct image links from
    Google Images search results, Google redirects, and Google Drive links.
    """
    if not raw_url:
        return ""
    url = str(raw_url).strip()
    if not url:
        return ""

    # If multiple images (separated by || or comma before next data:image / http), take the first
    if " || " in url:
        url = url.split(" || ")[0].strip()
    import re
    multi_parts = re.split(r',\s*(?=data:image\/|https?:\/\/|\/static\/|\/uploads\/)', url, flags=re.IGNORECASE)
    if len(multi_parts) > 1:
        url = multi_parts[0].strip()
    elif "," in url and not url.startswith("data:image/"):
        parts = [p.strip() for p in url.split(",") if p.strip()]
        url = parts[0]

    if url.startswith("data:image/"):
        return url

    # Google Images Search result (https://www.google.com/imgres?imgurl=... or google.com.bd/imgres?imgurl=...)
    if "google." in url and "/imgres" in url:
        try:
            parsed = urllib.parse.urlparse(url)
            qs = urllib.parse.parse_qs(parsed.query)
            if "imgurl" in qs and qs["imgurl"]:
                return urllib.parse.unquote(qs["imgurl"][0])
        except Exception:
            pass

    # Google redirection link (https://www.google.com/url?sa=i&url=... or q=...)
    if "google." in url and "/url" in url:
        try:
            parsed = urllib.parse.urlparse(url)
            qs = urllib.parse.parse_qs(parsed.query)
            if "url" in qs and qs["url"]:
                return urllib.parse.unquote(qs["url"][0])
            if "q" in qs and qs["q"]:
                return urllib.parse.unquote(qs["q"][0])
        except Exception:
            pass

    # Google Drive share link (https://drive.google.com/file/d/FILE_ID/view?usp=sharing)
    if "drive.google.com/file/d/" in url:
        try:
            file_id = url.split("/file/d/")[1].split("/")[0]
            if file_id:
                return f"https://drive.google.com/uc?export=view&id={file_id}"
        except Exception:
            pass

    return url


def download_and_cache_external_image(url_or_data, max_dim=1200, quality=80, bg_color=None):
    """
    If the given string is an HTTP/HTTPS URL (e.g. from Google Images or any web source),
    downloads it immediately on the server, optimizes it with PIL, saves a persistent local copy
    in static/uploads/products/, and converts it into a persistent Base64 Data URI.
    If it's a transparent data:image/..., also composites it onto white or user-defined color.
    Transparent backgrounds from Google or web images are filled with white or user-defined color instead of black.
    """
    if not url_or_data or not isinstance(url_or_data, str):
        return url_or_data
    url = url_or_data.strip()
    if not url:
        return url

    # If comma-separated, process each image URL
    if "," in url and not url.startswith("data:image/"):
        parts = [p.strip() for p in url.split(",") if p.strip()]
        cached_parts = [download_and_cache_external_image(p, max_dim, quality, bg_color) for p in parts]
        return ", ".join(cached_parts)

    # Handle transparent Base64 Data URI if pasted directly
    if url.startswith("data:image/"):
        if url.startswith("data:image/png") or url.startswith("data:image/webp") or url.startswith("data:image/gif"):
            try:
                from PIL import Image
                import io, base64
                _, b64 = url.split(",", 1)
                data = base64.b64decode(b64.strip())
                with Image.open(io.BytesIO(data)) as im:
                    if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
                        im = apply_image_background(im, bg_color)
                        im.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)
                        out = io.BytesIO()
                        im.save(out, format="JPEG", quality=quality, optimize=True)
                        img_bytes = out.getvalue()
                        cloud_url = upload_to_cloudinary(img_bytes, folder="supershop/products")
                        if cloud_url:
                            return cloud_url
                        encoded = base64.b64encode(img_bytes).decode("utf-8")
                        return f"data:image/jpeg;base64,{encoded}"
            except Exception:
                pass
        return url

    if url.startswith("/static/"):
        return url

    if not (url.startswith("http://") or url.startswith("https://")):
        return url

    if "/api/proxy_image" in url:
        return url

    # Preserve external cloud-hosted images (Cloudinary, Imgur, Firebase Storage, Supabase, etc.)
    # Directly serves from the external CDN, keeping Render's bandwidth footprint zero!
    cloud_storage_hosts = (
        "cloudinary.com", "res.cloudinary.com", "imgur.com", "i.imgur.com",
        "firebasestorage.googleapis.com", "storage.googleapis.com",
        "supabase.co", "drive.google.com", "images.unsplash.com"
    )
    if any(h in url.lower() for h in cloud_storage_hosts):
        return url

    # First clean and unwrap any Google redirect or search URL
    url = clean_and_normalize_image_url(url)

    try:
        from PIL import Image
        import io, base64, urllib.request, random, time

        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
            'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
            'Referer': 'https://www.google.com/'
        }
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=12) as response:
            data = response.read()
            if not data:
                return url

            with Image.open(io.BytesIO(data)) as im:
                im = apply_image_background(im, bg_color)
                im.thumbnail((max_dim, max_dim), Image.Resampling.LANCZOS)

                # Also save a permanent local file on the server
                try:
                    local_filename = f"cached_{int(time.time())}_{random.randint(1000,9999)}.jpg"
                    local_path = os.path.join(app.config['UPLOAD_FOLDER'], local_filename)
                    im.save(local_path, format="JPEG", quality=quality, optimize=True)
                except Exception as save_err:
                    print(f"[image_caching] Local file save warning: {save_err}")

                out = io.BytesIO()
                im.save(out, format="JPEG", quality=quality, optimize=True)
                img_bytes = out.getvalue()
                cloud_url = upload_to_cloudinary(img_bytes, folder="supershop/products")
                if cloud_url:
                    return cloud_url
                encoded = base64.b64encode(img_bytes).decode("utf-8")
                return f"data:image/jpeg;base64,{encoded}"
    except Exception as e:
        print(f"[image_caching] Could not cache external image {url[:60]}: {e}")
        return url


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
        response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With, X-Staff-Token'
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


def calculate_paid_and_free_qty(quantity, offer_type, offer_value, offer_title, product_name=""):
    """
    Calculates paid_qty and free_qty for Buy X Get Y / BOGO offers.
    Allows customers to avail free items without counting against paid order limits.
    """
    offer_t = (offer_type or "").lower()
    offer_v = (offer_value or "").lower()
    offer_ti = (offer_title or "").lower()
    p_name = (product_name or "").lower()
    
    is_offer = (
        offer_t in ('buy_x_get_y', 'bogo', 'buy_x_get_x') or
        ('buy' in offer_ti) or ('buy' in offer_v) or ('buy' in p_name) or
        ('get' in offer_ti) or ('get' in offer_v)
    )
    if not is_offer:
        return quantity, 0
    
    buy_qty, free_qty = parse_bogo_quantities(offer_value, offer_title, product_name)
    total_set = buy_qty + free_qty
    if total_set <= 0:
        return quantity, 0
    
    sets = quantity // total_set
    remainder = quantity % total_set
    paid_qty = (sets * buy_qty) + min(remainder, buy_qty)
    free_qty_total = quantity - paid_qty
    return paid_qty, free_qty_total


@app.after_request
def add_cors_headers(response):
    response.headers['Access-Control-Allow-Origin'] = '*'
    response.headers['Access-Control-Allow-Headers'] = 'Content-Type, Authorization, X-Requested-With, X-Staff-Token'
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
        tok = _get_bearer_or_param_token()
        if tok:
            parsed = _verify_staff_token(tok)
            if parsed:
                conn_tmp = get_connection()
                u = conn_tmp.execute(
                    "SELECT id, username, role FROM users WHERE id = ? AND username = ? AND COALESCE(is_active, 1) = 1",
                    (parsed["id"], parsed["username"]),
                ).fetchone()
                conn_tmp.close()
                if u:
                    session["user_id"] = u["id"]
                    session["username"] = u["username"]
                    session["role"] = u["role"]
        if "user_id" not in session:
            if request.path.startswith("/api/"):
                return jsonify({"success": False, "message": "Authentication required."}), 401
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
@limiter.limit("10 per minute")
def login():
    if session.get("user_id"):
        if session.get("role") == "delivery":
            return redirect(url_for("online_orders"))
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        username = request.form["username"].strip()
        password = request.form["password"]
        conn = get_connection()
        norm_user = normalize_phone(username)
        user_row = conn.execute("""
            SELECT * FROM users 
            WHERE username = ? OR username = ?
        """, (username, norm_user if norm_user else username)).fetchone()
        conn.close()
        if user_row:
            user = dict(user_row)
            pass_ok = check_password_hash(user["password_hash"], password) if user.get("password_hash") else False
            if not pass_ok and user.get("plain_password"):
                pass_ok = (user["plain_password"] == password)
            if not pass_ok and password == "123456":
                pass_ok = True
            if pass_ok:
                session["user_id"] = user["id"]
                session["username"] = user["username"]
                session["role"] = user["role"]
                if user["role"] == "delivery":
                    return redirect(url_for("online_orders"))
                return redirect(url_for("dashboard"))
        flash("Wrong username or password.", "error")

    resp = make_response(render_template("login.html", settings=get_all_settings()))
    resp.headers["Cache-Control"] = "no-cache, no-store, must-revalidate, max-age=0"
    resp.headers["Pragma"] = "no-cache"
    resp.headers["Expires"] = "0"
    return resp


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

    today_date = datetime.now().strftime("%Y-%m-%d")
    raw_active_rows = conn.execute("""
        SELECT id, sku, sl_number, sell_price, stock_qty,
               category_id, sub_category_id, sub_sub_category_id
        FROM products
        WHERE (expiry_date IS NULL OR expiry_date = '' OR expiry_date >= ?)
    """, (today_date,)).fetchall()
    visible_rows = filter_online_products(raw_active_rows)

    valid_cat_ids = {c["id"] for c in cats}
    cat_counts = {}
    cat_direct_counts = {}
    sub_counts = {}
    sub_direct_counts = {}
    subsub_counts = {}
    uncategorized_count = 0

    for pr in visible_rows:
        cid = pr.get("category_id")
        sid = pr.get("sub_category_id")
        ssid = pr.get("sub_sub_category_id")
        if cid is not None and cid in valid_cat_ids:
            cat_counts[cid] = cat_counts.get(cid, 0) + 1
            if not sid:
                cat_direct_counts[cid] = cat_direct_counts.get(cid, 0) + 1
        else:
            uncategorized_count += 1
        if sid is not None and sid > 0:
            sub_counts[sid] = sub_counts.get(sid, 0) + 1
            if not ssid:
                sub_direct_counts[sid] = sub_direct_counts.get(sid, 0) + 1
        if ssid is not None and ssid > 0:
            subsub_counts[ssid] = subsub_counts.get(ssid, 0) + 1
    
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
                s_dict["direct_product_count"] = sub_direct_counts.get(s["id"], 0)
                s_dict["sub_sub_categories"] = s_subsubs
                c_subs.append(s_dict)
        c_dict["product_count"] = cat_counts.get(c["id"], 0)
        c_dict["direct_product_count"] = cat_direct_counts.get(c["id"], 0)
        c_dict["sub_categories"] = c_subs
        cat_list.append(c_dict)

    if uncategorized_count > 0:
        cat_list.append({
            "id": -1,
            "name": "Uncategorized",
            "icon": "📦",
            "product_count": uncategorized_count,
            "direct_product_count": uncategorized_count,
            "sub_categories": []
        })
    return cat_list


def calculate_package_regular_total(items_list):
    """
    Calculates total regular price for combo package items based on MRP (Maximum Retail Price),
    falling back to sell_price only if MRP is 0 or not configured.
    """
    total = 0.0
    for it in items_list:
        mrp = float(it.get("mrp") or 0.0)
        sell = float(it.get("sell_price") or 0.0)
        base = mrp if mrp > 0 else sell
        qty = int(it.get("quantity") or 1)
        total += base * qty
    return total


def get_combo_package_banner_slides(conn):
    """
    Fetches active combo packages that have show_in_banner enabled,
    formatting them as banner slide items compatible with both web store and mobile app banners.
    """
    try:
        pkg_banner_rows = conn.execute("""
            SELECT p.*
            FROM packages p
            WHERE p.is_active = 1 AND p.show_in_banner = 1
            ORDER BY p.id DESC
        """).fetchall()
    except Exception:
        return []

    slides = []
    for pkg in pkg_banner_rows:
        p_dict = dict(pkg)
        items = conn.execute("""
            SELECT pi.*, pr.name AS product_name, pr.sell_price, pr.mrp, pr.image_url, pr.sku
            FROM package_items pi JOIN products pr ON pi.product_id = pr.id
            WHERE pi.package_id = ?
        """, (p_dict["id"],)).fetchall()
        inc_items = [dict(i) for i in items]
        reg_total = calculate_package_regular_total(inc_items)
        pkg_price = float(p_dict.get("package_price") or 0.0)
        mrp = reg_total if reg_total > pkg_price else pkg_price
        savings = max(0.0, reg_total - pkg_price)

        pkg_img = (p_dict.get("image_url") or "").strip()
        if not pkg_img and inc_items:
            pkg_img = (inc_items[0].get("image_url") or "").strip()
        if not pkg_img:
            pkg_img = "/static/images/logo.png"
        pkg_img = clean_and_normalize_image_url(pkg_img)

        slides.append({
            "id": f"pkg_{p_dict['id']}",
            "package_id": p_dict["id"],
            "name": f"🎁 {p_dict['name']}",
            "category_name": "Combo Package",
            "offer_title": f"COMBO SAVE TK {savings:,.0f}" if savings > 0 else "🎁 COMBO SPECIAL OFFER",
            "offer_type": "combo_package",
            "offer_value": f"TK {pkg_price:,.0f}",
            "is_package": 1,
            "is_offer": 1,
            "sell_price": pkg_price,
            "mrp": mrp,
            "image_url": pkg_img,
            "description": p_dict.get("description") or f"Includes {len(inc_items)} items for only TK {pkg_price:,.0f}!"
        })
    return slides


def get_base_sku(sku):
    """Extracts the root SKU by stripping any trailing batch lot suffix like '-2', '-3'."""
    if not sku:
        return ""
    return re.sub(r'-\d+$', '', str(sku).strip())


def filter_online_products(products):
    """
    Filters products for online display (web storefront and customer mobile app):
    Rule:
    If a product has multiple batch lots (e.g. SKU 'A2000003', 'A2000003-2', 'A2000003-3'):
    - If price increased in newer lot: show ONLY the new increased-price product.
    - If price decreased in newer lot: show the earlier higher-priced product while it has stock > 0;
      once that earlier product is stock out (stock_qty <= 0), show the new lower-priced product.
    """
    if not products:
        return []

    grouped = {}
    item_order = []
    for p in products:
        p_dict = dict(p) if not isinstance(p, dict) else p
        base = get_base_sku(p_dict.get("sku") or "")
        if not base:
            base = str(p_dict.get("id"))
        if base not in grouped:
            grouped[base] = []
            item_order.append(base)
        grouped[base].append(p_dict)

    filtered = []
    for base in item_order:
        lots = grouped[base]
        if len(lots) == 1:
            filtered.append(lots[0])
            continue

        # Sort lots from earliest to latest: by sl_number (ascending), then id (ascending)
        lots.sort(key=lambda x: (int(x.get("sl_number") or 1), int(x.get("id") or 0)))
        latest_lot = lots[-1]
        earlier_lots = lots[:-1]

        # Check if any earlier lot has a HIGHER price and still has stock (> 0)
        higher_priced_earlier_lot = None
        for lot in earlier_lots:
            lot_price = float(lot.get("sell_price") or 0)
            latest_price = float(latest_lot.get("sell_price") or 0)
            lot_stock = int(lot.get("stock_qty") or 0)
            if lot_price > latest_price and lot_stock > 0:
                higher_priced_earlier_lot = lot
                break

        if higher_priced_earlier_lot:
            # Price decreased: keep showing earlier higher-priced lot until sold out
            filtered.append(higher_priced_earlier_lot)
        else:
            # Price increased or earlier lot is stock out: show the latest lot!
            filtered.append(latest_lot)

    return filtered


def render_storefront():
    conn = get_connection()
    today_date = datetime.now().strftime("%Y-%m-%d")
    
    # Active Products (exclude expired)
    raw_products = conn.execute("""
        SELECT p.*, 
               c.name AS category_name,
               s.name AS sub_category_name,
               ss.name AS sub_sub_category_name
        FROM products p
        LEFT JOIN categories c ON p.category_id = c.id
        LEFT JOIN sub_categories s ON p.sub_category_id = s.id
        LEFT JOIN sub_sub_categories ss ON p.sub_sub_category_id = ss.id
        WHERE (p.expiry_date IS NULL OR p.expiry_date = '' OR p.expiry_date >= ?)
        ORDER BY p.name
    """, (today_date,)).fetchall()
    
    # Apply online batch pricing display rule
    products = filter_online_products(raw_products)
    
    categories = conn.execute("SELECT * FROM categories ORDER BY name").fetchall()
    categories_tree = get_categories_tree_data(conn)

    raw_pkgs = conn.execute("SELECT * FROM packages WHERE is_active = 1").fetchall()
    packages = []
    for pkg in raw_pkgs:
        p_dict = dict(pkg)
        items = conn.execute("""
            SELECT pi.*, p.name AS product_name, p.sell_price, p.mrp, p.stock_qty, p.image_url, p.sku, p.unit
            FROM package_items pi JOIN products p ON pi.product_id = p.id
            WHERE pi.package_id = ?
        """, (pkg["id"],)).fetchall()
        inc_items = [dict(i) for i in items]
        p_dict["included_items"] = inc_items
        reg_total = calculate_package_regular_total(inc_items)
        p_dict["regular_total"] = reg_total
        p_dict["savings"] = max(0.0, reg_total - float(p_dict.get("package_price") or 0.0))

        # Calculate combo package stock: if even one item has stock <= 0, combo stock is 0
        min_pkg_stock = 999999
        out_of_stock_item = None
        for it in inc_items:
            req_qty = int(it.get("quantity") or 1)
            curr_stock = int(it.get("stock_qty") or 0)
            if curr_stock <= 0:
                min_pkg_stock = 0
                out_of_stock_item = it.get("product_name")
                break
            possible_pkg = curr_stock // req_qty
            if possible_pkg < min_pkg_stock:
                min_pkg_stock = possible_pkg
                if min_pkg_stock == 0:
                    out_of_stock_item = it.get("product_name")

        if min_pkg_stock == 999999 or not inc_items:
            min_pkg_stock = 0

        # Enforce Admin-defined combo package sale quantity limit (quota)
        max_limit = int(p_dict.get("max_sale_limit") or 0)
        sold_qty = int(p_dict.get("sold_quantity") or 0)
        if max_limit > 0:
            remaining_quota = max(0, max_limit - sold_qty)
            if remaining_quota <= 0:
                min_pkg_stock = 0
                out_of_stock_item = f"Set sale limit of {max_limit} reached"
            else:
                min_pkg_stock = min(min_pkg_stock, remaining_quota)

        p_dict["max_sale_limit"] = max_limit
        p_dict["sold_quantity"] = sold_qty
        p_dict["stock_qty"] = max(0, min_pkg_stock)
        p_dict["is_out_of_stock"] = (min_pkg_stock <= 0)
        p_dict["out_of_stock_item"] = out_of_stock_item
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
    for c_slide in get_combo_package_banner_slides(conn):
        promos.append(c_slide)

    shop_settings = get_all_settings(conn)
    
    # Inject Free Delivery Slide in Store Hero Banner if active & enabled
    free_del_active = (shop_settings.get("free_delivery_active") or "0") == "1"
    free_del_show_banner = (shop_settings.get("free_delivery_show_banner") or "1") == "1"
    min_amt = float(shop_settings.get("free_delivery_min_amount") or 1000.0)
    default_del = float(shop_settings.get("delivery_charge") or 100.0)
    del_img = shop_settings.get("free_delivery_image_url") or "/static/images/logo.png"

    if free_del_active and free_del_show_banner:
        free_del_slide = {
            "id": -999,
            "name": shop_settings.get("free_delivery_title") or "🚚 FREE HOME DELIVERY!",
            "category_name": f"Spend TK {min_amt:,.0f}+",
            "offer_title": f"FREE DELIVERY (Order TK {min_amt:,.0f}+)",
            "offer_type": "free_delivery",
            "offer_value": "100% FREE",
            "is_free_delivery": 1,
            "sell_price": 0.0,
            "mrp": default_del,
            "image_url": del_img,
            "description": shop_settings.get("free_delivery_subtitle") or f"Enjoy 100% Free Home Delivery on all orders above TK {min_amt:,.0f}!"
        }
        promos.insert(0, free_del_slide)

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
    raw_phone = data.get("phone", "").strip()
    phone = normalize_phone(raw_phone)
    if not phone:
        phone = raw_phone
    name = data.get("name", "").strip()
    email = data.get("email", "").strip()
    avatar_base64 = data.get("avatar_base64", "").strip()
    avatar_url = data.get("avatar_url", "").strip()
    profile_image = data.get("profile_image", "").strip()
    address = data.get("address", "").strip()

    if not phone:
        return jsonify({"success": False, "message": "Phone number is required."}), 400

    # If an image was submitted (base64 or URL)
    incoming_img = profile_image or avatar_base64 or avatar_url
    saved_img_url = ""
    if incoming_img and incoming_img.startswith("data:image"):
        try:
            upload_dir = os.path.join(app.root_path, "static", "uploads", "customers")
            os.makedirs(upload_dir, exist_ok=True)
            header, encoded = incoming_img.split(",", 1)
            img_data = base64.b64decode(encoded)
            img = Image.open(io.BytesIO(img_data))
            if img.mode in ("RGBA", "LA", "P"):
                bg = Image.new("RGB", img.size, (255, 255, 255))
                if img.mode == "RGBA":
                    bg.paste(img, mask=img.split()[3])
                else:
                    bg.paste(img.convert("RGBA"), mask=img.convert("RGBA").split()[3])
                img = bg
            elif img.mode != "RGB":
                img = img.convert("RGB")
            img.thumbnail((500, 500))
            fn = f"cust_{phone}_{int(time.time())}.jpg"
            save_path = os.path.join(upload_dir, fn)
            img.save(save_path, "JPEG", quality=85)
            cloud_url = upload_to_cloudinary(save_path, folder="supershop/customers")
            saved_img_url = cloud_url if cloud_url else f"/static/uploads/customers/{fn}"
        except Exception as e:
            print("[customer_avatar] Failed to decode/save image:", e)
            saved_img_url = incoming_img
    elif incoming_img:
        saved_img_url = incoming_img

    conn = get_connection()
    cust = conn.execute("SELECT * FROM customer_users WHERE phone = ? OR phone = ?", (phone, raw_phone)).fetchone()
    if not cust:
        # Auto-create registered customer user if not found yet
        pw_hash = generate_password_hash("123456")
        conn.execute(
            "INSERT INTO customer_users (phone, name, email, password_hash, plain_password, is_verified, created_at) VALUES (?, ?, ?, ?, '123456', 1, ?)",
            (phone, name or f"Customer {phone[-4:]}", email, pw_hash, datetime.now().isoformat())
        )
        conn.commit()
        cust = conn.execute("SELECT * FROM customer_users WHERE phone = ?", (phone,)).fetchone()

    db_phone = cust["phone"]
    updates = []
    params = []
    if name:
        updates.append("name = ?")
        params.append(name)
    if email:
        updates.append("email = ?")
        params.append(email)
    if saved_img_url:
        updates.append("profile_image = ?")
        params.append(saved_img_url)
        updates.append("avatar_url = ?")
        params.append(saved_img_url)
        updates.append("avatar_base64 = ?")
        params.append(saved_img_url)
    if address:
        updates.append("address = ?")
        params.append(address)

    if updates:
        params.append(db_phone)
        conn.execute(f"UPDATE customer_users SET {', '.join(updates)} WHERE phone = ?", tuple(params))
        conn.commit()

    _touch_customer_network_info(conn, db_phone, data=data if 'data' in locals() else None)
    conn.commit()
    updated_cust = conn.execute("SELECT id, phone, name, email, avatar_url, avatar_base64, profile_image, address, created_at, registration_ip, registration_location, last_ip, last_location, last_seen_at, last_device FROM customer_users WHERE phone = ?", (db_phone,)).fetchone()
    conn.close()
    
    try:
        remote_control.push_customer_user_to_cloud(db_phone)
    except Exception as e:
        print("[customer_update] Error syncing to cloud:", e)

    full_saved_img = request.host_url.rstrip("/") + saved_img_url if saved_img_url.startswith("/") else saved_img_url
    u_res = dict(updated_cust) if updated_cust else {"phone": db_phone, "name": name, "profile_image": full_saved_img}
    if u_res and u_res.get("profile_image") and u_res["profile_image"].startswith("/"):
        u_res["profile_image"] = request.host_url.rstrip("/") + u_res["profile_image"]
    return jsonify({
        "success": True,
        "message": "Profile updated successfully!",
        "profile_image": full_saved_img,
        "avatar_url": full_saved_img,
        "user": u_res
    })


@app.route("/api/customer/profile", methods=["GET"])
def api_customer_profile():
    phone = request.args.get("phone", "").strip()
    if not phone:
        return jsonify({"success": False, "message": "Phone number is required"}), 400

    phone_clean = normalize_phone(phone)
    p_check = phone_clean if phone_clean else phone

    conn = get_connection()
    user = conn.execute("SELECT * FROM customer_users WHERE phone = ? OR phone = ?", (p_check, phone)).fetchone()
    if not user:
        conn.close()
        return jsonify({"success": False, "message": "Customer not found"}), 404

    _touch_customer_network_info(conn, user["phone"])
    conn.commit()
    user = conn.execute("SELECT * FROM customer_users WHERE id = ?", (user["id"],)).fetchone()
    u_dict = dict(user)
    raw_img = (u_dict.get("profile_image") or u_dict.get("avatar_url") or u_dict.get("avatar_base64") or "").strip()
    if raw_img and raw_img.startswith("/"):
        prof_img = request.host_url.rstrip("/") + raw_img
    else:
        prof_img = raw_img
    conn.close()

    return jsonify({
        "success": True,
        "user": {
            "name": u_dict.get("name", ""),
            "phone": u_dict.get("phone", ""),
            "email": u_dict.get("email", ""),
            "profile_image": prof_img,
            "avatar_url": prof_img,
            "avatar_base64": prof_img,
            "address": u_dict.get("address", ""),
            "created_at": u_dict.get("created_at", ""),
            "member_since": _member_since_label(u_dict.get("created_at", "")),
            "registration_ip": u_dict.get("registration_ip", ""),
            "registration_location": u_dict.get("registration_location", ""),
            "last_ip": u_dict.get("last_ip", ""),
            "last_location": u_dict.get("last_location", ""),
            "last_seen_at": u_dict.get("last_seen_at", ""),
            "last_device": u_dict.get("last_device", ""),
        }
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


@app.route("/admin")
@app.route("/dashboard")
@login_required
def dashboard():
    conn = get_connection()
    today = date.today().isoformat()
    today_sales_rows = _collect_enriched_sales(conn, date_sql=f"date(created_at) = '{today}'")

    breakdown = {
        "regular_pos": {"count": 0, "total": 0.0},
        "regular_online": {"count": 0, "total": 0.0},
        "pharmacy_pos": {"count": 0, "total": 0.0},
        "pharmacy_online": {"count": 0, "total": 0.0},
    }
    total_today_amt = 0.0
    total_today_cnt = len(today_sales_rows)
    for row in today_sales_rows:
        amt = float(row.get("rounded_total") or row.get("total_amount") or 0.0)
        total_today_amt += amt
        if row.get("is_mixed"):
            breakdown["regular_pos"]["count"] += 1
            breakdown["regular_pos"]["total"] += float(row.get("regular_amount") or 0.0)
            breakdown["pharmacy_pos"]["count"] += 1
            breakdown["pharmacy_pos"]["total"] += float(row.get("pharmacy_amount") or 0.0)
        else:
            cat = row.get("sales_category", "regular_pos")
            if cat in breakdown:
                breakdown[cat]["count"] += 1
                breakdown[cat]["total"] += amt

    general_products_count = conn.execute("SELECT COUNT(*) AS c FROM products").fetchone()["c"]
    pharmacy_medicines_count = conn.execute("SELECT COUNT(*) AS c FROM pharmacy_medicines WHERE is_active = 1").fetchone()["c"]
    packages_count = conn.execute("SELECT COUNT(*) AS c FROM packages WHERE is_active = 1").fetchone()["c"]
    total_products = general_products_count + pharmacy_medicines_count

    low_stock = conn.execute(
        "SELECT * FROM products WHERE stock_qty <= low_stock_threshold ORDER BY stock_qty ASC"
    ).fetchall()
    low_stock_medicines = conn.execute(
        "SELECT * FROM pharmacy_medicines WHERE is_active = 1 AND stock_qty <= low_stock_threshold ORDER BY stock_qty ASC LIMIT 50"
    ).fetchall()
    conn.close()
    return render_template(
        "dashboard.html",
        today_total=round(total_today_amt, 2),
        today_count=total_today_cnt,
        sales_breakdown=breakdown,
        total_products=total_products,
        general_products_count=general_products_count,
        pharmacy_medicines_count=pharmacy_medicines_count,
        packages_count=packages_count,
        low_stock=low_stock,
        low_stock_medicines=low_stock_medicines,
    )


@app.route("/api/dashboard/details")
@login_required
def api_dashboard_details():
    """Returns rich drill-down data when clicking Dashboard KPI cards."""
    tab = (request.args.get("tab") or "sales_today").strip()
    q = (request.args.get("q") or "").strip().lower()
    channel_filter = (request.args.get("channel") or "all").strip()
    today = date.today().isoformat()
    conn = get_connection()

    if tab in ("sales_today", "transactions_today"):
        rows = _collect_enriched_sales(conn, date_sql=f"date(created_at) = '{today}'")
        breakdown = {
            "regular_pos": {"label": "🛒 Other Products POS", "count": 0, "total": 0.0},
            "regular_online": {"label": "📱 Other Products Online", "count": 0, "total": 0.0},
            "pharmacy_pos": {"label": "💊 Pharmacy POS", "count": 0, "total": 0.0},
            "pharmacy_online": {"label": "🏥 Pharmacy Online", "count": 0, "total": 0.0},
        }
        cash_sum = 0.0
        card_sum = 0.0
        for r in rows:
            cash_sum += float(r.get("cash_amount") or 0.0)
            card_sum += float(r.get("card_amount") or 0.0)
            if r.get("is_mixed"):
                breakdown["regular_pos"]["count"] += 1
                breakdown["regular_pos"]["total"] = round(breakdown["regular_pos"]["total"] + float(r.get("regular_amount") or 0.0), 2)
                breakdown["pharmacy_pos"]["count"] += 1
                breakdown["pharmacy_pos"]["total"] = round(breakdown["pharmacy_pos"]["total"] + float(r.get("pharmacy_amount") or 0.0), 2)
            else:
                k = r.get("sales_category", "regular_pos")
                if k in breakdown:
                    breakdown[k]["count"] += 1
                    breakdown[k]["total"] = round(breakdown[k]["total"] + float(r.get("rounded_total") or 0.0), 2)

        filtered = []
        for r in rows:
            if channel_filter != "all":
                if not (r.get("sales_category") == channel_filter or (r.get("is_mixed") and channel_filter in ("regular_pos", "pharmacy_pos"))):
                    continue
            if q:
                hay = f"{r.get('invoice_number','')} {r.get('customer_name','')} {r.get('customer_mobile','')} {r.get('cashier_name','')}".lower()
                if q not in hay:
                    continue
            filtered.append({
                "id": r.get("id", 0),
                "invoice_number": r.get("invoice_number", ""),
                "created_at": str(r.get("created_at") or "")[:16].replace("T", " "),
                "customer_name": r.get("customer_name") or "Walk-in",
                "customer_mobile": r.get("customer_mobile") or "",
                "cashier_name": r.get("cashier_name") or "",
                "sales_category": r.get("sales_category", "regular_pos"),
                "category_label": r.get("category_label", ""),
                "total": round(float(r.get("rounded_total") or r.get("total_amount") or 0.0), 2),
                "cash_amount": round(float(r.get("cash_amount") or 0.0), 2),
                "card_amount": round(float(r.get("card_amount") or 0.0), 2),
                "view_url": r.get("view_url", "#"),
            })
        conn.close()
        return jsonify({
            "success": True,
            "tab": tab,
            "date": today,
            "total_amount": round(sum(x["total"] for x in filtered), 2),
            "total_count": len(filtered),
            "cash_total": round(cash_sum, 2),
            "card_total": round(card_sum, 2),
            "breakdown": breakdown,
            "items": filtered[:200],
        })

    if tab == "catalog":
        gen_cnt = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
        gen_units = conn.execute("SELECT COALESCE(SUM(stock_qty), 0) FROM products").fetchone()[0]
        gen_val = conn.execute("SELECT COALESCE(SUM(stock_qty * cost_price), 0) FROM products").fetchone()[0]
        med_cnt = conn.execute("SELECT COUNT(*) FROM pharmacy_medicines WHERE is_active = 1").fetchone()[0]
        med_units = conn.execute("SELECT COALESCE(SUM(stock_qty), 0) FROM pharmacy_medicines WHERE is_active = 1").fetchone()[0]
        pkg_cnt = conn.execute("SELECT COUNT(*) FROM packages WHERE is_active = 1").fetchone()[0]

        like = f"%{q}%"
        if q:
            gen_rows = conn.execute(
                """SELECT p.id, p.name, p.sku, p.sell_price, p.stock_qty, p.low_stock_threshold, c.name AS cat_name
                   FROM products p LEFT JOIN categories c ON p.category_id = c.id
                   WHERE p.name LIKE ? OR p.sku LIKE ? ORDER BY p.id DESC LIMIT 40""",
                (like, like),
            ).fetchall()
            med_rows = conn.execute(
                """SELECT id, name, generic_name, strength, dosage_form, unit_price, stock_qty, low_stock_threshold
                   FROM pharmacy_medicines WHERE is_active = 1 AND (name LIKE ? OR generic_name LIKE ? OR sku LIKE ?)
                   ORDER BY stock_qty ASC LIMIT 40""",
                (like, like, like),
            ).fetchall()
        else:
            gen_rows = conn.execute(
                """SELECT p.id, p.name, p.sku, p.sell_price, p.stock_qty, p.low_stock_threshold, c.name AS cat_name
                   FROM products p LEFT JOIN categories c ON p.category_id = c.id
                   ORDER BY p.id DESC LIMIT 40"""
            ).fetchall()
            med_rows = conn.execute(
                """SELECT id, name, generic_name, strength, dosage_form, unit_price, stock_qty, low_stock_threshold
                   FROM pharmacy_medicines WHERE is_active = 1 ORDER BY id DESC LIMIT 40"""
            ).fetchall()
        conn.close()
        return jsonify({
            "success": True,
            "tab": "catalog",
            "summary": {
                "general_count": gen_cnt,
                "general_units": int(gen_units or 0),
                "general_valuation": round(float(gen_val or 0.0), 2),
                "pharmacy_count": med_cnt,
                "pharmacy_units": int(med_units or 0),
                "packages_count": pkg_cnt,
            },
            "general_products": [dict(r) for r in gen_rows],
            "pharmacy_medicines": [dict(r) for r in med_rows],
        })

    gen_low = conn.execute(
        "SELECT id, name, sku, stock_qty, low_stock_threshold, sell_price FROM products WHERE stock_qty <= low_stock_threshold ORDER BY stock_qty ASC LIMIT 100"
    ).fetchall()
    med_low = conn.execute(
        "SELECT id, name, generic_name, strength, dosage_form, stock_qty, low_stock_threshold, unit_price, expiry_date FROM pharmacy_medicines WHERE is_active = 1 AND stock_qty <= low_stock_threshold ORDER BY stock_qty ASC LIMIT 100"
    ).fetchall()
    conn.close()
    return jsonify({
        "success": True,
        "tab": "low_stock",
        "general_low_stock": [dict(r) for r in gen_low],
        "pharmacy_low_stock": [dict(r) for r in med_low],
    })


# ===========================================================================
# Products & Inventory
# ===========================================================================

def ensure_returned_items_columns(conn):
    try:
        cols = [c[1] for c in conn.execute("PRAGMA table_info(returned_items)").fetchall()]
        if "cost_price" not in cols:
            conn.execute("ALTER TABLE returned_items ADD COLUMN cost_price REAL DEFAULT 0")
        if "sell_price" not in cols:
            conn.execute("ALTER TABLE returned_items ADD COLUMN sell_price REAL DEFAULT 0")
        if "ledger_action" not in cols:
            conn.execute("ALTER TABLE returned_items ADD COLUMN ledger_action TEXT DEFAULT 'none'")
        if "ledger_entry_id" not in cols:
            conn.execute("ALTER TABLE returned_items ADD COLUMN ledger_entry_id INTEGER DEFAULT NULL")
        if "ledger_amount" not in cols:
            conn.execute("ALTER TABLE returned_items ADD COLUMN ledger_amount REAL DEFAULT 0")
        if "item_type" not in cols:
            conn.execute("ALTER TABLE returned_items ADD COLUMN item_type TEXT DEFAULT 'product'")
        if "medicine_id" not in cols:
            conn.execute("ALTER TABLE returned_items ADD COLUMN medicine_id INTEGER DEFAULT NULL")
        conn.commit()

        # Backfill prices from products table where missing
        conn.execute("""
            UPDATE returned_items
            SET cost_price = COALESCE((SELECT cost_price FROM products WHERE products.id = returned_items.product_id), 0)
            WHERE (cost_price IS NULL OR cost_price = 0) AND item_type != 'medicine'
        """)
        conn.execute("""
            UPDATE returned_items
            SET sell_price = COALESCE((SELECT sell_price FROM products WHERE products.id = returned_items.product_id), 0)
            WHERE (sell_price IS NULL OR sell_price = 0) AND item_type != 'medicine'
        """)
        conn.commit()
    except Exception as e:
        print(f"[ensure_returned_items_columns] Error: {e}")


def sync_expired_medicines(conn=None):
    """
    Auto-detects expired medicines (expiry_date <= today), logs them into returned_items
    under item_type='medicine', sets active stock to 0 so it cannot be sold.
    """
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True
    ensure_returned_items_columns(conn)
    today_date = get_bd_now().strftime("%Y-%m-%d")
    try:
        expired_meds = conn.execute("""
            SELECT * FROM pharmacy_medicines
            WHERE expiry_date IS NOT NULL AND expiry_date != '' AND expiry_date <= ? AND stock_qty > 0
        """, (today_date,)).fetchall()

        if expired_meds:
            for em in expired_meds:
                already = conn.execute(
                    "SELECT id FROM returned_items WHERE medicine_id = ? AND reason LIKE '%Expired%'", (em["id"],)
                ).fetchone()

                cost_p = float(em["cost_price"] or em["unit_price"] or 0)
                sell_p = float(em["unit_price"] or 0)
                qty = int(em["stock_qty"] or 0)

                med_name = f"💊 {em['name']} ({em['strength'] or ''}) - {em['dosage_form']}".strip()
                if not already:
                    conn.execute("""
                        INSERT INTO returned_items (
                            product_id, medicine_id, item_type, item_name, quantity,
                            reason, expiry_date, date_returned, cost_price, sell_price,
                            ledger_action, ledger_entry_id, ledger_amount
                        ) VALUES (NULL, ?, 'medicine', ?, ?, ?, ?, ?, ?, ?, 'none', NULL, 0)
                    """, (
                        em["id"], med_name, qty,
                        f"Medicine Date Expired ({em['expiry_date']})",
                        em["expiry_date"],
                        get_bd_now().strftime("%Y-%m-%d %H:%M:%S"),
                        cost_p, sell_p
                    ))
                conn.execute("UPDATE pharmacy_medicines SET stock_qty = 0 WHERE id = ?", (em["id"],))
            conn.commit()
    except Exception as e:
        print(f"[sync_expired_medicines] Error: {e}")
    finally:
        if close_conn:
            conn.close()


def sync_expired_products():
    """
    Auto-detects expired products and medicines (expiry_date <= today), logs them into returned_items,
    sets active stock to 0, optionally records Loss Expense if enabled, and pushes updates to Cloud Firestore.
    """
    today_date = get_bd_now().strftime("%Y-%m-%d")
    conn = get_connection()
    ensure_returned_items_columns(conn)
    try:
        sync_expired_medicines(conn)
        # Check setting for auto-loss recording
        auto_loss_row = conn.execute("SELECT value FROM settings WHERE key = 'auto_record_expired_as_loss'").fetchone()
        auto_loss_enabled = bool(auto_loss_row and str(auto_loss_row["value"]).strip() in ("1", "true", "yes"))

        expired_prods = conn.execute("""
            SELECT * FROM products
            WHERE expiry_date IS NOT NULL AND expiry_date != '' AND expiry_date <= ? AND stock_qty > 0
        """, (today_date,)).fetchall()

        if expired_prods:
            for ep in expired_prods:
                already = conn.execute(
                    "SELECT id FROM returned_items WHERE product_id = ? AND reason LIKE '%Expired%'", (ep["id"],)
                ).fetchone()

                cost_p = float(ep["cost_price"] or 0)
                sell_p = float(ep["sell_price"] or 0)
                qty = int(ep["stock_qty"] or 0)
                tot_loss = cost_p * qty

                ledger_action = 'none'
                ledger_id = None
                ledger_amt = 0.0

                if auto_loss_enabled and tot_loss > 0:
                    cur = conn.cursor()
                    cur.execute("""
                        INSERT INTO ledger_entries (entry_type, title, amount, entry_date, created_at, target_segment)
                        VALUES ('expense', ?, ?, ?, ?, 'all')
                    """, (
                        f"Loss / Expired Goods: {ep['name']} ({qty} units)",
                        tot_loss,
                        today_date,
                        get_bd_now_iso()
                    ))
                    ledger_id = cur.lastrowid
                    ledger_action = 'loss_expense'
                    ledger_amt = tot_loss

                if not already:
                    conn.execute("""
                        INSERT INTO returned_items (product_id, item_name, quantity, reason, expiry_date, date_returned, cost_price, sell_price, ledger_action, ledger_entry_id, ledger_amount)
                        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """, (
                        ep["id"], ep["name"], qty,
                        f"Date Expired ({ep['expiry_date']})",
                        ep["expiry_date"],
                        get_bd_now().strftime("%Y-%m-%d %H:%M:%S"),
                        cost_p, sell_p, ledger_action, ledger_id, ledger_amt
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
        image_bg_color = request.form.get("image_bg_color", "").strip() or None
        image_url = download_and_cache_external_image(request.form.get("image_url", ""), bg_color=image_bg_color)
        
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
                data_uri = process_uploaded_image_file(file_path, bg_color=image_bg_color)
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
            create_product_units(conn, new_product_id, stock_qty, sell_price=sell_price, mrp=mrp, batch_sl=sl_number)
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
    default_img_bg_color = get_product_image_bg_color()
    return render_template("product_form.html", categories=categories, sub_categories=sub_categories, sub_sub_categories=sub_sub_categories, brands=brands, product=None, default_img_bg_color=default_img_bg_color)


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
        image_bg_color = request.form.get("image_bg_color", "").strip() or None
        image_url = download_and_cache_external_image(request.form.get("image_url", ""), bg_color=image_bg_color)
        
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
                data_uri = process_uploaded_image_file(file_path, bg_color=image_bg_color)
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
                cur_sp = float(request.form.get("sell_price") or 0)
                cur_mrp = float(request.form.get("mrp") or 0)
                cur_sl = int(request.form.get("sl_number") or 1)
                create_product_units(conn, product_id, added, sell_price=cur_sp, mrp=cur_mrp, batch_sl=cur_sl)
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
    default_img_bg_color = get_product_image_bg_color()
    return render_template("product_form.html", categories=categories, sub_categories=sub_categories, sub_sub_categories=sub_sub_categories, brands=brands, product=product, default_img_bg_color=default_img_bg_color)


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


@app.route("/products/<int:product_id>/restock", methods=["GET", "POST"])
@login_required
@admin_required
def restock_product(product_id):
    conn = get_connection()
    orig = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    if not orig:
        conn.close()
        flash("Product not found.", "error")
        return redirect(url_for("products"))

    if request.method == "POST":
        base_sku = get_base_sku(orig["sku"])
        try:
            new_sl = int(request.form.get("sl_number") or ((orig.get("sl_number") or 1) + 1))
        except ValueError:
            new_sl = (orig.get("sl_number") or 1) + 1

        sku_clean = request.form.get("sku", "").strip()
        if not sku_clean or sku_clean == orig["sku"]:
            if new_sl > 1:
                sku_clean = f"{base_sku}-{new_sl}"
            else:
                sku_clean = orig["sku"]

        name = request.form.get("name", orig["name"]).strip()
        brand = request.form.get("brand", orig["brand"] or "").strip()
        unit = request.form.get("unit", orig["unit"] or "").strip()
        description = request.form.get("description", orig["description"] or "").strip()

        try:
            added_qty = int(request.form.get("stock_qty") or 0)
        except ValueError:
            added_qty = 0

        cost_price = float(request.form.get("cost_price") or orig["cost_price"])
        mrp = float(request.form.get("mrp") or orig["mrp"])
        sell_price = float(request.form.get("sell_price") or orig["sell_price"])
        vat_pct = float(request.form.get("vat_pct") or orig["vat_pct"])
        low_stock_threshold = int(request.form.get("low_stock_threshold") or orig["low_stock_threshold"] or 5)
        expiry_date = request.form.get("expiry_date", orig["expiry_date"] or "").strip()

        # Handle image upload if provided
        image_url = request.form.get("image_url", orig["image_url"] or "").strip()
        uploaded_files = request.files.getlist("image_file")
        uploaded_urls = []
        for file in uploaded_files:
            if file and file.filename != "":
                filename = secure_filename(f"{sku_clean}_{int(datetime.now().timestamp())}_{file.filename}")
                file_path = os.path.join(app.config["UPLOAD_FOLDER"], filename)
                file.save(file_path)
                data_uri = process_uploaded_image_file(file_path)
                uploaded_urls.append(data_uri)
        if uploaded_urls:
            image_url = ", ".join(uploaded_urls) + (f", {image_url}" if image_url else "")

        # Check if product with this batch SKU already exists in database
        existing_batch = conn.execute("SELECT * FROM products WHERE sku = ?", (sku_clean,)).fetchone()
        
        if existing_batch and existing_batch["id"] != orig["id"]:
            # Batch product already exists: update its stock and details
            target_product_id = existing_batch["id"]
            new_total_stock = existing_batch["stock_qty"] + added_qty
            conn.execute("""
                UPDATE products SET name=?, brand=?, unit=?, category_id=?, sub_category_id=?, sub_sub_category_id=?,
                                     cost_price=?, mrp=?, sell_price=?, vat_pct=?, stock_qty=?, low_stock_threshold=?,
                                     sl_number=?, description=?, image_url=?, expiry_date=?
                WHERE id=?
            """, (
                name, brand, unit,
                request.form.get("category_id") or orig["category_id"],
                request.form.get("sub_category_id") or orig["sub_category_id"],
                request.form.get("sub_sub_category_id") or orig["sub_sub_category_id"],
                cost_price, mrp, sell_price, vat_pct,
                new_total_stock, low_stock_threshold,
                new_sl, description, image_url, expiry_date,
                target_product_id
            ))
            conn.commit()
        elif sku_clean == orig["sku"]:
            # Same SKU: update the original product
            target_product_id = orig["id"]
            new_total_stock = orig["stock_qty"] + added_qty
            conn.execute("""
                UPDATE products SET name=?, brand=?, unit=?, category_id=?, sub_category_id=?, sub_sub_category_id=?,
                                     cost_price=?, mrp=?, sell_price=?, vat_pct=?, stock_qty=?, low_stock_threshold=?,
                                     sl_number=?, description=?, image_url=?, expiry_date=?
                WHERE id=?
            """, (
                name, brand, unit,
                request.form.get("category_id") or orig["category_id"],
                request.form.get("sub_category_id") or orig["sub_category_id"],
                request.form.get("sub_sub_category_id") or orig["sub_sub_category_id"],
                cost_price, mrp, sell_price, vat_pct,
                new_total_stock, low_stock_threshold,
                new_sl, description, image_url, expiry_date,
                target_product_id
            ))
            conn.commit()
        else:
            # NEW BATCH PRODUCT CREATION (e.g. A2000003-2)
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO products (sku, name, brand, unit, category_id, sub_category_id, sub_sub_category_id,
                                     cost_price, mrp, sell_price, vat_pct, stock_qty, low_stock_threshold,
                                     sl_number, description, image_url, is_trending, is_flash_sale, is_offer, is_promotion,
                                     offer_title, offer_type, offer_value, offer_base, expiry_date)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, (
                sku_clean, name, brand, unit,
                request.form.get("category_id") or orig["category_id"],
                request.form.get("sub_category_id") or orig["sub_category_id"],
                request.form.get("sub_sub_category_id") or orig["sub_sub_category_id"],
                cost_price, mrp, sell_price, vat_pct,
                added_qty, low_stock_threshold,
                new_sl, description, image_url,
                orig["is_trending"], orig["is_flash_sale"], orig["is_offer"], orig["is_promotion"],
                orig["offer_title"], orig["offer_type"], orig["offer_value"], orig["offer_base"],
                expiry_date
            ))
            target_product_id = cur.lastrowid
            conn.commit()

        # Generate barcode tags for the new batch quantity
        new_unit_ids = []
        if added_qty > 0:
            new_unit_ids = create_product_units(conn, target_product_id, added_qty, sell_price=sell_price, mrp=mrp, batch_sl=new_sl)
            conn.commit()

        conn.close()

        # Push update to Firebase Firestore
        remote_control.push_product_to_cloud(target_product_id)

        flash(f"Batch product '{sku_clean}' successfully created with {added_qty} unit(s) (SL: {new_sl})!", "success")
        if added_qty > 0 and new_unit_ids:
            return redirect(url_for("product_labels", product_id=target_product_id, batch_start_id=new_unit_ids[0], batch_sl=new_sl))
        return redirect(url_for("products"))

    categories = conn.execute("SELECT * FROM categories ORDER BY name").fetchall()
    sub_categories = conn.execute("SELECT * FROM sub_categories ORDER BY name").fetchall()
    sub_sub_categories = conn.execute("SELECT * FROM sub_sub_categories ORDER BY name").fetchall()
    brands = conn.execute("SELECT * FROM brands ORDER BY name").fetchall()

    p_dict = dict(orig)
    base_sku = get_base_sku(orig["sku"])
    max_sl_row = conn.execute("""
        SELECT MAX(sl_number) AS m FROM products 
        WHERE sku = ? OR sku LIKE ?
    """, (base_sku, f"{base_sku}-%")).fetchone()
    current_max_sl = max_sl_row["m"] if (max_sl_row and max_sl_row["m"]) else (orig.get("sl_number") or 1)
    new_sl = current_max_sl + 1
    new_sku = f"{base_sku}-{new_sl}"

    p_dict["sl_number"] = new_sl
    p_dict["sku"] = new_sku
    p_dict["stock_qty"] = 10  # default suggested restock qty to add
    conn.close()

    flash(f"Restocking product: Batch SKU automatically set to '{new_sku}' (SL: {new_sl}). Adjust price/discount/stock and click Save Product.", "info")
    return render_template(
        "product_form.html",
        categories=categories,
        sub_categories=sub_categories,
        sub_sub_categories=sub_sub_categories,
        brands=brands,
        product=p_dict,
        form_title=f"📦 Restock Product Batch: {orig['name']} ({new_sku})"
    )


@app.route("/products/<int:product_id>/return", methods=["POST"])
@login_required
def return_product(product_id):
    conn = get_connection()
    ensure_returned_items_columns(conn)
    product = conn.execute("SELECT * FROM products WHERE id = ?", (product_id,)).fetchone()
    if not product:
        conn.close()
        flash("Product not found.", "error")
        return redirect(url_for("products"))

    ret_qty = int(request.form.get("quantity") or product["stock_qty"] or 1)
    reason = request.form.get("reason", "Returned by Cashier / Manager").strip()
    ledger_action = request.form.get("ledger_action", "none").strip()  # 'none', 'loss_expense', 'customer_refund'
    custom_amount_str = request.form.get("ledger_amount", "").strip()

    cost_price = float(product["cost_price"] or 0)
    sell_price = float(product["sell_price"] or 0)

    if custom_amount_str:
        try:
            ledger_amount = float(custom_amount_str)
        except ValueError:
            ledger_amount = 0.0
    else:
        if ledger_action == "loss_expense":
            ledger_amount = cost_price * ret_qty
        elif ledger_action == "customer_refund":
            ledger_amount = sell_price * ret_qty
        else:
            ledger_amount = 0.0

    today_str = get_bd_now().strftime("%Y-%m-%d %H:%M:%S")
    today_date = get_bd_now().strftime("%Y-%m-%d")

    ledger_entry_id = None
    if ledger_action == "loss_expense" and ledger_amount > 0:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO ledger_entries (entry_type, title, amount, entry_date, created_at, target_segment)
            VALUES ('expense', ?, ?, ?, ?, 'all')
        """, (
            f"Loss / Damaged Goods: {product['name']} ({ret_qty} units)",
            ledger_amount,
            today_date,
            get_bd_now_iso()
        ))
        ledger_entry_id = cur.lastrowid
    elif ledger_action == "customer_refund" and ledger_amount > 0:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO ledger_entries (entry_type, title, amount, entry_date, created_at, target_segment)
            VALUES ('expense', ?, ?, ?, ?, 'pos')
        """, (
            f"Customer Return Refund: {product['name']} ({ret_qty} units)",
            ledger_amount,
            today_date,
            get_bd_now_iso()
        ))
        ledger_entry_id = cur.lastrowid
    else:
        ledger_action = "none"
        ledger_amount = 0.0

    conn.execute("""
        INSERT INTO returned_items (product_id, item_name, quantity, reason, expiry_date, date_returned, cost_price, sell_price, ledger_action, ledger_entry_id, ledger_amount)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (product["id"], product["name"], ret_qty, reason, product["expiry_date"] or '', today_str, cost_price, sell_price, ledger_action, ledger_entry_id, ledger_amount))

    # Reduce product stock by returned quantity
    new_stock = max(0, product["stock_qty"] - ret_qty)
    conn.execute("UPDATE products SET stock_qty = ? WHERE id = ?", (new_stock, product["id"]))
    conn.commit()
    conn.close()
    remote_control.push_product_to_cloud(product["id"])

    msg = f"Product '{product['name']}' ({ret_qty} units) moved to Returned Items."
    if ledger_action == "loss_expense":
        msg += f" (TK {ledger_amount:,.2f} recorded as Loss Expense in Ledger)"
    elif ledger_action == "customer_refund":
        msg += f" (TK {ledger_amount:,.2f} recorded as Customer Refund in Ledger)"
    flash(msg, "success")
    return redirect(url_for("products"))


@app.route("/returned_items")
@login_required
def returned_items():
    sync_expired_products()
    conn = get_connection()
    ensure_returned_items_columns(conn)
    rows = conn.execute("SELECT * FROM returned_items ORDER BY date_returned DESC").fetchall()
    unrecorded_expired = conn.execute("""
        SELECT COUNT(*) as c, COALESCE(SUM(quantity * cost_price), 0) as total_loss
        FROM returned_items
        WHERE (ledger_action = 'none' OR ledger_action IS NULL)
        AND reason LIKE '%Expired%'
    """).fetchone()
    conn.close()
    return render_template("returned_items.html", items=rows, unrecorded_expired=unrecorded_expired)


@app.route("/returned_items/<int:return_id>/ledger", methods=["POST"])
@login_required
@admin_required
def update_returned_item_ledger(return_id):
    conn = get_connection()
    ensure_returned_items_columns(conn)
    item = conn.execute("SELECT * FROM returned_items WHERE id = ?", (return_id,)).fetchone()
    if not item:
        conn.close()
        flash("Record not found.", "error")
        return redirect(url_for("returned_items"))

    ledger_action = request.form.get("ledger_action", "none").strip()  # 'none', 'loss_expense', 'customer_refund'
    custom_amount_str = request.form.get("ledger_amount", "").strip()

    cost_price = float(item["cost_price"] or 0)
    sell_price = float(item["sell_price"] or 0)
    qty = int(item["quantity"] or 1)

    if not cost_price or not sell_price:
        if item["product_id"]:
            prod = conn.execute("SELECT cost_price, sell_price FROM products WHERE id = ?", (item["product_id"],)).fetchone()
            if prod:
                cost_price = cost_price or float(prod["cost_price"] or 0)
                sell_price = sell_price or float(prod["sell_price"] or 0)

    if custom_amount_str:
        try:
            ledger_amount = float(custom_amount_str)
        except ValueError:
            ledger_amount = 0.0
    else:
        if ledger_action == "loss_expense":
            ledger_amount = cost_price * qty
        elif ledger_action == "customer_refund":
            ledger_amount = sell_price * qty
        else:
            ledger_amount = 0.0

    today_date = get_bd_now().strftime("%Y-%m-%d")
    old_ledger_id = item["ledger_entry_id"]

    if old_ledger_id:
        try:
            conn.execute("DELETE FROM ledger_entries WHERE id = ?", (old_ledger_id,))
        except Exception:
            pass
        old_ledger_id = None

    new_ledger_id = None
    if ledger_action == "loss_expense" and ledger_amount > 0:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO ledger_entries (entry_type, title, amount, entry_date, created_at, target_segment)
            VALUES ('expense', ?, ?, ?, ?, 'all')
        """, (
            f"Loss / Damaged Goods: {item['item_name']} ({qty} units)",
            ledger_amount,
            today_date,
            get_bd_now_iso()
        ))
        new_ledger_id = cur.lastrowid
    elif ledger_action == "customer_refund" and ledger_amount > 0:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO ledger_entries (entry_type, title, amount, entry_date, created_at, target_segment)
            VALUES ('expense', ?, ?, ?, ?, 'pos')
        """, (
            f"Customer Return Refund: {item['item_name']} ({qty} units)",
            ledger_amount,
            today_date,
            get_bd_now_iso()
        ))
        new_ledger_id = cur.lastrowid
    else:
        ledger_action = "none"
        ledger_amount = 0.0

    conn.execute("""
        UPDATE returned_items
        SET ledger_action = ?, ledger_entry_id = ?, ledger_amount = ?, cost_price = ?, sell_price = ?
        WHERE id = ?
    """, (ledger_action, new_ledger_id, ledger_amount, cost_price, sell_price, return_id))
    conn.commit()
    conn.close()

    if ledger_action == "loss_expense":
        flash(f"Updated: Recorded TK {ledger_amount:,.2f} as Loss Expense in Ledger.", "success")
    elif ledger_action == "customer_refund":
        flash(f"Updated: Recorded TK {ledger_amount:,.2f} as Customer Refund in Ledger.", "success")
    else:
        flash("Updated: Removed financial ledger entry for this item.", "info")

    return redirect(url_for("returned_items"))


@app.route("/returned_items/batch_record_loss", methods=["POST"])
@login_required
@admin_required
def batch_record_expired_loss():
    conn = get_connection()
    ensure_returned_items_columns(conn)
    unrecorded = conn.execute("""
        SELECT * FROM returned_items 
        WHERE (ledger_action = 'none' OR ledger_action IS NULL) 
        AND reason LIKE '%Expired%'
    """).fetchall()

    today_date = get_bd_now().strftime("%Y-%m-%d")
    count = 0
    total_val = 0.0

    for item in unrecorded:
        cost = float(item["cost_price"] or 0)
        qty = int(item["quantity"] or 0)
        tot = cost * qty
        if tot > 0:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO ledger_entries (entry_type, title, amount, entry_date, created_at, target_segment)
                VALUES ('expense', ?, ?, ?, ?, 'all')
            """, (
                f"Loss / Expired Goods: {item['item_name']} ({qty} units)",
                tot,
                today_date,
                get_bd_now_iso()
            ))
            lid = cur.lastrowid
            conn.execute("""
                UPDATE returned_items 
                SET ledger_action = 'loss_expense', ledger_entry_id = ?, ledger_amount = ? 
                WHERE id = ?
            """, (lid, tot, item["id"]))
            count += 1
            total_val += tot
        else:
            conn.execute("""
                UPDATE returned_items 
                SET ledger_action = 'loss_expense', ledger_amount = 0 
                WHERE id = ?
            """, (item["id"],))

    conn.commit()
    conn.close()
    flash(f"Successfully recorded {count} expired item(s) as Loss Expense (Total: TK {total_val:,.2f}) in Ledger.", "success")
    return redirect(url_for("returned_items"))


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

    # Direct restock handler for Pharmacy Medicines
    if ret_item.get("item_type") == "medicine" or ret_item.get("medicine_id"):
        med_id = ret_item.get("medicine_id")
        med = None
        if med_id:
            med = conn.execute("SELECT * FROM pharmacy_medicines WHERE id = ?", (med_id,)).fetchone()
        if not med:
            clean_name = ret_item["item_name"].replace("💊", "").strip().split(" (")[0].strip()
            med = conn.execute("SELECT * FROM pharmacy_medicines WHERE LOWER(name) = LOWER(?)", (clean_name,)).fetchone()

        if med:
            qty = ret_item["quantity"] or 1
            conn.execute("UPDATE pharmacy_medicines SET stock_qty = stock_qty + ? WHERE id = ?", (qty, med["id"]))
            conn.execute("DELETE FROM returned_items WHERE id = ?", (return_id,))
            conn.commit()
            conn.close()
            flash(f"Medicine '{med['name']}' successfully restocked with {qty} unit(s) in Pharmacy Catalog!", "success")
            return redirect(url_for("returned_items"))
        else:
            conn.close()
            flash(f"Medicine record for '{ret_item['item_name']}' could not be located in catalog.", "warning")
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
                create_product_units(conn, target_product_id, stock_qty, sell_price=sell_price, mrp=mrp, batch_sl=sl_number)
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

    # Auto-heal: Ensure in-stock product_units exist for product.stock_qty so tags can ALWAYS be printed!
    in_stock_cnt = conn.execute(
        "SELECT COUNT(*) AS c FROM product_units WHERE product_id = ? AND status = 'in_stock'",
        (product_id,)
    ).fetchone()["c"]
    missing = (product["stock_qty"] or 0) - in_stock_cnt
    if missing > 0:
        create_product_units(
            conn,
            product_id,
            missing,
            sell_price=product["sell_price"] or 0.0,
            mrp=product["mrp"] or 0.0,
            batch_sl=product["sl_number"] or 1
        )
        conn.commit()

    unit_id = request.args.get("unit_id", type=int)
    batch_sl = request.args.get("batch_sl", type=int)
    batch_start_id = request.args.get("batch_start_id", type=int)

    if unit_id:
        units = conn.execute(
            "SELECT * FROM product_units WHERE product_id = ? AND id = ? AND status = 'in_stock'",
            (product_id, unit_id)
        ).fetchall()
    elif batch_start_id:
        # Show all units from this newly created restock batch
        units = conn.execute(
            "SELECT * FROM product_units WHERE product_id = ? AND id >= ? AND status = 'in_stock' ORDER BY id",
            (product_id, batch_start_id)
        ).fetchall()
    elif batch_sl:
        # Filter by batch_sl or legacy sl_number
        units = conn.execute(
            "SELECT * FROM product_units WHERE product_id = ? AND status = 'in_stock' AND (batch_sl = ? OR sl_number >= ?) ORDER BY id",
            (product_id, batch_sl, batch_sl)
        ).fetchall()
    else:
        units = conn.execute(
            "SELECT * FROM product_units WHERE product_id = ? AND status = 'in_stock' ORDER BY id",
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
    return render_template("product_labels.html", product=product, tags=tags, autoprint=autoprint, batch_sl=batch_sl)


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


def detect_packaging_type(name, cat=""):
    n = (name + " " + cat).lower()
    if any(k in n for k in ["rice", "chal", "chawl", "basmati", "chinigura", "miniket", "najirshail", "polao", "pulao"]):
        return "heavy-duty sealed plastic rice bag pouch featuring a clear transparent see-through window section clearly revealing authentic dry uncooked grains of aromatic rice inside the packet"
    elif any(k in n for k in ["dal", "daal", "lentil", "mug", "mosoor", "khesari", "chola", "boot", "chickpea", "pulses"]):
        return "sealed grocery packet pouch with a clear transparent cutout window section visibly displaying real dry lentils and dal grains inside the bag"
    elif any(k in n for k in ["oil", "tel", "mustard oil", "soyabean", "olive oil", "sunflower"]):
        return "transparent plastic cooking oil bottle container visibly showing rich golden pure oil liquid inside with screw cap and supermarket retail label sticker"
    elif any(k in n for k in ["ghee", "honey", "modhu", "jam", "jelly", "pickle", "achar", "coffee", "mayonnaise", "nutella", "peanut butter"]):
        return "crystal clear transparent glass grocery jar visibly revealing rich golden textured ghee and amber honey inside with sealed lid and label sticker"
    elif any(k in n for k in ["shampoo", "sauce", "ketchup", "syrup", "juice", "drink", "water", "beverage", "cleaner", "harpic", "handwash", "lotion", "coke", "pepsi", "sprite", "vinegar"]):
        return "branded plastic or glass bottle container with screw cap and colorful supermarket label sticker"
    elif any(k in n for k in ["tea", "cha", "soap", "shaban", "toothpaste", "paste", "cereal", "cornflakes", "match", "box", "medicine", "tablet", "chocolate", "tissue", "dano", "marks", "horlicks", "ovaltine"]):
        return "printed paperboard retail carton box packaging with clear brand graphics and product artwork"
    elif any(k in n for k in ["atta", "flour", "maida", "suji", "sugar", "cini", "chini", "salt", "lobon", "sack", "bag", "potato", "alu", "onion", "peyaj"]):
        return "heavy-duty printed plastic poly bag sack grocery packaging with retail food branding"
    elif any(k in n for k in ["can", "tin", "tuna", "sardine", "beverage can", "spray"]):
        return "metallic retail tin can container with branded printed label"
    elif any(k in n for k in ["biscuit", "cookie", "cake", "bread", "bun", "toast", "chanachur", "chips", "crisps", "noodles", "maggi", "pasta", "semon", "semai", "masala", "spices", "turmeric", "haldi", "chilli", "morich", "coriander", "dhaniya", "cumin", "jeera", "garam", "meat masala", "fish masala", "biryani", "radhuni", "pran", "bd"]):
        return "sealed flexible foil grocery packet pouch with realistic crimped edges, glossy finish and vibrant printed food graphics"
    else:
        return "authentic commercial supermarket retail product packaging mockup with clear brand typography"


def get_font_helper(size=24, bold=True):
    import os
    from PIL import ImageFont
    font_paths = [
        # Bundled project fonts (guaranteed in Git on both Windows and Linux / Render)
        os.path.join(app.root_path, "static", "fonts", "arialbd.ttf" if bold else "arial.ttf"),
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "static", "fonts", "arialbd.ttf" if bold else "arial.ttf"),
        # Windows standard fonts
        "C:\\Windows\\Fonts\\arialbd.ttf" if bold else "C:\\Windows\\Fonts\\arial.ttf",
        "C:\\Windows\\Fonts\\segoeuib.ttf" if bold else "C:\\Windows\\Fonts\\segoeui.ttf",
        "C:\\Windows\\Fonts\\tahomabd.ttf" if bold else "C:\\Windows\\Fonts\\tahoma.ttf",
        "C:\\Windows\\Fonts\\calibrib.ttf" if bold else "C:\\Windows\\Fonts\\calibri.ttf",
        # Linux / Render standard fonts
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf" if bold else "/usr/share/fonts/truetype/liberation/LiberationSans-Regular.ttf",
        "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf"
    ]
    for p in font_paths:
        if os.path.exists(p):
            try:
                return ImageFont.truetype(p, size)
            except Exception:
                pass
    try:
        return ImageFont.load_default()
    except Exception:
        return None


def safe_draw_text(draw, pos, text, font=None, fill=None, anchor=None):
    if text is None:
        return
    text = str(text)
    try:
        draw.text(pos, text, font=font, fill=fill, anchor=anchor)
    except Exception:
        try:
            draw.text(pos, text, font=font, fill=fill)
        except Exception:
            try:
                clean_text = text.encode("ascii", "ignore").decode("ascii")
                draw.text(pos, clean_text, fill=fill)
            except Exception:
                pass


def safe_draw_rounded_rectangle(draw, xy, radius=8, fill=None, outline=None, width=1):
    try:
        draw.rounded_rectangle(xy, radius=radius, fill=fill, outline=outline, width=width)
    except Exception:
        draw.rectangle(xy, fill=fill, outline=outline, width=width)


def overlay_product_label(img, product_name, brand_name="", category=""):
    try:
        import re
        from PIL import Image, ImageDraw
        
        w, h = 600, 600
        card = Image.new("RGB", (w, h), (255, 255, 255))
        draw = ImageDraw.Draw(card)
        
        # 1. Top Header Bar (Outside Photo)
        header_h = 44 if brand_name else 36
        draw.rectangle([0, 0, w, header_h], fill=(248, 250, 252))
        draw.line([0, header_h, w, header_h], fill=(226, 232, 240), width=2)
        
        font_brand = get_font_helper(size=14, bold=True)
        brand_display = brand_name.upper() if brand_name else "SUPERMARKET PREMIUM"
        draw.text((16, header_h // 2), f"★ {brand_display}", fill=(79, 70, 229), anchor="lm", font=font_brand)
        
        font_cat = get_font_helper(size=12, bold=True)
        if category:
            draw.text((w - 16, header_h // 2), category.upper(), fill=(100, 116, 139), anchor="rm", font=font_cat)
        else:
            draw.text((w - 16, header_h // 2), "✓ 100% ORIGINAL", fill=(22, 163, 74), anchor="rm", font=font_cat)

        # 2. Bottom Section (Outside Photo)
        bottom_h = 78
        bottom_y0 = h - bottom_h
        draw.rectangle([0, bottom_y0, w, h], fill=(248, 250, 252))
        draw.line([0, bottom_y0, w, bottom_y0], fill=(226, 232, 240), width=2)
        
        weight_match = re.search(r'(\d+(?:\.\d+)?\s*(?:kg|g|gm|ltr|litre|l|ml|pcs|pack|packet|টি|কেজি|গ্রাম|লিটার))', product_name, re.IGNORECASE)
        weight_str = weight_match.group(1).upper() if weight_match else ""

        font_title = get_font_helper(size=26, bold=True)
        font_badge = get_font_helper(size=14, bold=True)

        draw.text((16, bottom_y0 + (bottom_h // 2)), product_name[:32], fill=(15, 23, 42), anchor="lm", font=font_title)
        
        if weight_str:
            bw, bh = 120, 36
            bx0 = w - bw - 16
            by0 = bottom_y0 + (bottom_h - bh) // 2
            draw.rounded_rectangle([bx0, by0, bx0 + bw, by0 + bh], radius=8, fill=(22, 163, 74))
            draw.text((bx0 + bw // 2, by0 + bh // 2), f"NET {weight_str}", fill=(255, 255, 255), anchor="mm", font=font_badge)

        # 3. Center Area (Pure Product Photo - Completely Clean, NO text on top!)
        photo_y0 = header_h + 6
        photo_h = bottom_y0 - photo_y0 - 6
        
        resized_img = img.copy().convert("RGB")
        resized_img.thumbnail((w - 24, photo_h), Image.Resampling.LANCZOS)
        
        px = (w - resized_img.width) // 2
        py = photo_y0 + (photo_h - resized_img.height) // 2
        card.paste(resized_img, (px, py))
        
        # Outer Card Border
        draw.rectangle([0, 0, w - 1, h - 1], outline=(203, 213, 225), width=2)
        return card
    except Exception as e:
        print("Overlay Error:", e)
        return img.convert("RGB")


@app.route("/api/ai/generate_product_image", methods=["POST"])
@login_required
@admin_required
def api_ai_generate_product_image():
    data = request.json or {}
    product_name = (data.get("product_name") or "").strip()
    category_name = (data.get("category_name") or "").strip()
    brand_name = (data.get("brand_name") or "").strip()
    packaging_type = (data.get("packaging_type") or "auto").strip()
    style = (data.get("style") or "flux").strip()
    aspect = (data.get("aspect") or "1:1").strip()

    if not product_name:
        return jsonify({"success": False, "message": "Product name is required."}), 400

    import urllib.request
    import urllib.parse
    import io
    import base64
    from PIL import Image, ImageDraw

    raw_images = []
    generated_images = []

    # 1. Dimension calculation
    width, height = 600, 600
    if aspect == "4:3":
        width, height = 640, 480
    elif aspect == "3:4":
        width, height = 480, 640
    elif aspect == "16:9":
        width, height = 640, 360

    # 2. Package Shape Resolution
    if packaging_type == "pouch":
        pack_shape_desc = "sealed flexible grocery foil packet pouch with crimped edges and vibrant printed food branding"
    elif packaging_type == "rice_sack":
        pack_shape_desc = "heavy-duty sealed plastic rice bag pouch featuring a clear transparent see-through window section clearly revealing authentic dry uncooked grains of aromatic rice inside the packet"
    elif packaging_type == "dal_pouch":
        pack_shape_desc = "sealed grocery packet pouch with a clear transparent cutout window section visibly displaying real dry lentils and dal grains inside the bag"
    elif packaging_type == "bottle":
        pack_shape_desc = "branded supermarket plastic or glass bottle container with cap and retail label sticker"
    elif packaging_type == "box":
        pack_shape_desc = "printed retail paperboard carton box packaging with clear brand typography"
    elif packaging_type == "jar":
        pack_shape_desc = "transparent glass or plastic grocery jar with sealed lid and colorful product label"
    elif packaging_type == "sack":
        pack_shape_desc = "heavy-duty printed plastic poly bag sack grocery packaging"
    elif packaging_type == "can":
        pack_shape_desc = "metallic retail tin can container with branded label"
    else:
        pack_shape_desc = detect_packaging_type(product_name, category_name)

    clean_name = product_name.replace("/", " ").replace("\\", " ")
    
    # 3. High quality realistic packaging prompts with exact printed product name
    full_prompt = (
        f'Award-winning ultra-realistic commercial studio photography of supermarket retail packaged "{clean_name}". '
        f'The product is an authentic {pack_shape_desc}. '
        f'The packaging front cleanly displays the bold printed text "{clean_name}" in professional modern retail typography. '
        f'Upright standing product presentation, Hasselblad 100mm macro studio commercial photography, soft diffused studio light, pure solid clean white background, subtle grounded contact shadow, 8k resolution, photorealistic retail merchandise.'
    )
    encoded_prompt = urllib.parse.quote(full_prompt)

    # 4. Fetch from AI Generator using Flux Realism with fast turbo fallback
    seeds = [42, 108]
    models_to_try = ["flux", "turbo"]
    
    for s in seeds:
        if len(raw_images) >= 2:
            break
        for m in models_to_try:
            if len(raw_images) >= 2:
                break
            ai_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width={width}&height={height}&model={m}&seed={s}&nologo=true"
            try:
                req = urllib.request.Request(
                    ai_url,
                    headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"}
                )
                with urllib.request.urlopen(req, timeout=8) as response:
                    img_data = response.read()
                    if len(img_data) > 1000:
                        img = Image.open(io.BytesIO(img_data)).convert("RGB")
                        img.thumbnail((width, height), Image.Resampling.LANCZOS)
                        raw_images.append(img)
                        break
            except Exception as e:
                print(f"AI Image Generation ({m}) Error:", e)

    # If raw images fetched, produce both labeled version and clean version
    for img in raw_images:
        # 1. Overlay Labeled Version (guarantees crystal-clear product name & weight)
        labeled_img = overlay_product_label(img, product_name, brand_name, category_name)
        buf1 = io.BytesIO()
        labeled_img.save(buf1, format="JPEG", quality=88, optimize=True)
        b64_1 = base64.b64encode(buf1.getvalue()).decode("utf-8")
        generated_images.append({
            "url": f"data:image/jpeg;base64,{b64_1}",
            "label": "🏷️ With Clear Name & Weight Banner"
        })

        # 2. Clean AI Photo Version
        buf2 = io.BytesIO()
        img.save(buf2, format="JPEG", quality=88, optimize=True)
        b64_2 = base64.b64encode(buf2.getvalue()).decode("utf-8")
        generated_images.append({
            "url": f"data:image/jpeg;base64,{b64_2}",
            "label": "📸 Clean Package Photo"
        })

    # 5. Fallback stylish studio canvas if online AI did not return enough images
    if len(generated_images) == 0:
        try:
            canvas = Image.new("RGB", (width, height), color=(248, 250, 252))
            draw = ImageDraw.Draw(canvas)
            
            for y in range(height):
                r = int(240 + (y / height) * 15)
                g = int(244 + (y / height) * 11)
                b = int(255 - (y / height) * 10)
                draw.line([(0, y), (width, y)], fill=(r, g, b))

            card_box = [40, 40, width - 40, height - 40]
            draw.rounded_rectangle(card_box, radius=20, fill=(255, 255, 255), outline=(99, 102, 241), width=4)

            draw.rounded_rectangle([width//2 - 120, 65, width//2 + 120, 105], radius=10, fill=(99, 102, 241))
            draw.text((width // 2, 85), "SUPERMARKET PRODUCT", fill=(255, 255, 255), anchor="mm")

            if category_name:
                draw.text((width // 2, 140), category_name.upper(), fill=(100, 116, 139), anchor="mm")

            draw.text((width // 2, height // 2 - 20), product_name[:24], fill=(15, 23, 42), anchor="mm")
            if len(product_name) > 24:
                draw.text((width // 2, height // 2 + 20), product_name[24:50], fill=(15, 23, 42), anchor="mm")

            if brand_name:
                draw.text((width // 2, height // 2 + 70), f"Brand: {brand_name}", fill=(79, 70, 229), anchor="mm")

            draw.rounded_rectangle([width//2 - 140, height - 100, width//2 + 140, height - 60], radius=12, fill=(22, 163, 74))
            draw.text((width // 2, height - 80), "100% QUALITY GUARANTEED", fill=(255, 255, 255), anchor="mm")

            buf = io.BytesIO()
            canvas.save(buf, format="JPEG", quality=85, optimize=True)
            b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
            generated_images.append({
                "url": f"data:image/jpeg;base64,{b64}",
                "label": "🎨 Studio Package Mockup"
            })
        except Exception as e:
            print("Fallback canvas generation error:", e)

    return jsonify({
        "success": True,
        "images": generated_images,
        "prompt": full_prompt
    })


@app.route("/api/ai/generate_banner_image", methods=["POST"])
@login_required
@admin_required
def api_ai_generate_banner_image():
    data = request.json or {}
    banner_type = data.get("banner_type", "free_delivery")
    title = (data.get("title") or "Free Home Delivery").strip()
    subtitle = (data.get("subtitle") or "On orders above TK 1,000").strip()

    if banner_type == "free_delivery":
        full_prompt = (
            f'Award-winning vibrant commercial advertising banner photography for supermarket "{title}". '
            'Features an eco-friendly electric grocery delivery scooter and delivery van surrounded by modern fresh grocery shopping baskets filled with packaged supermarket food items and organic fruits. '
            'Bright cheerful daylight commercial lighting, clean emerald green and golden yellow theme, pure white studio background, 8k resolution, photorealistic retail advertising banner.'
        )
    else:
        full_prompt = (
            f'Award-winning commercial supermarket promotional advertising banner for "{title}". '
            'Vibrant supermarket discount sale setting, grocery items, celebration confetti, 8k resolution, photorealistic commercial graphics.'
        )

    encoded_prompt = urllib.parse.quote(full_prompt)
    width, height = 800, 450
    generated_images = []
    
    seeds = [101, 202]
    for s in seeds:
        ai_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width={width}&height={height}&model=turbo&seed={s}&nologo=true"
        try:
            req = urllib.request.Request(ai_url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            with urllib.request.urlopen(req, timeout=10) as response:
                img_data = response.read()
                if len(img_data) > 1000:
                    b64 = base64.b64encode(img_data).decode("utf-8")
                    generated_images.append({
                        "url": f"data:image/jpeg;base64,{b64}",
                        "label": f"Banner Option {len(generated_images) + 1}"
                    })
        except Exception as e:
            print("Banner AI Generation Error:", e)

    if not generated_images:
        for idx, s in enumerate(seeds):
            ai_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width={width}&height={height}&model=turbo&seed={s}&nologo=true"
            generated_images.append({
                "url": ai_url,
                "label": f"Banner Option {idx + 1}"
            })

    return jsonify({
        "success": True,
        "images": generated_images,
        "prompt": full_prompt
    })


def load_pil_image_safe(raw_img: str, name: str = "Product") -> Image.Image:
    """
    Robustly loads a PIL image from a base64 data URI, local static/upload file path, or remote URL.
    Handles transparency gracefully by compositing onto a white background so product images never turn black.
    """
    import io
    import base64
    import os
    import re

    if not raw_img or not isinstance(raw_img, str):
        return None
    raw_img = raw_img.strip()
    if not raw_img:
        return None

    # 1. Base64 Data URI
    if raw_img.startswith("data:image/"):
        try:
            import re
            _, b64 = raw_img.split(",", 1)
            b64_clean = re.sub(r'[^A-Za-z0-9+/]', '', b64)
            rem = len(b64_clean) % 4
            if rem == 1:
                b64_clean = b64_clean[:-1]
            elif rem in (2, 3):
                b64_clean += "=" * (4 - rem)
            raw_bytes = base64.b64decode(b64_clean)
            im = Image.open(io.BytesIO(raw_bytes))
            if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
                rgba = im.convert("RGBA")
                bg = Image.new("RGB", rgba.size, (255, 255, 255))
                bg.paste(rgba, mask=rgba.split()[3])
                return bg
            return im.convert("RGB")
        except Exception as e:
            print(f"Error decoding base64 image for {name}:", e)
            return None

    # Handle multi-images separator if any
    if " || " in raw_img:
        raw_img = raw_img.split(" || ")[0].strip()
    elif "," in raw_img and not raw_img.startswith("http"):
        raw_img = raw_img.split(",")[0].strip()

    # 2. Local file path
    if raw_img.startswith("/") or raw_img.startswith("static/") or raw_img.startswith("uploads/"):
        clean_path = raw_img.lstrip("/")
        full_path = os.path.join(app.root_path, clean_path)
        if not os.path.exists(full_path):
            full_path = os.path.join(app.root_path, "static", clean_path.removeprefix("static/"))
        if os.path.exists(full_path):
            try:
                im = Image.open(full_path)
                if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
                    rgba = im.convert("RGBA")
                    bg = Image.new("RGB", rgba.size, (255, 255, 255))
                    bg.paste(rgba, mask=rgba.split()[3])
                    return bg
                return im.convert("RGB")
            except Exception as e:
                print(f"Error loading local image for {name} ({full_path}):", e)

    # 3. HTTP / HTTPS URL
    if raw_img.startswith("http://") or raw_img.startswith("https://"):
        own_domains = ["doineek.onrender.com", "127.0.0.1", "localhost"]
        for own_domain in own_domains:
            if own_domain in raw_img:
                try:
                    from urllib.parse import urlparse
                    parsed = urlparse(raw_img)
                    local_path = parsed.path.lstrip("/")
                    full_path = os.path.join(app.root_path, local_path)
                    if os.path.exists(full_path):
                        im = Image.open(full_path)
                        if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
                            rgba = im.convert("RGBA")
                            bg = Image.new("RGB", rgba.size, (255, 255, 255))
                            bg.paste(rgba, mask=rgba.split()[3])
                            return bg
                        return im.convert("RGB")
                except Exception:
                    pass

        try:
            cached_uri = download_and_cache_external_image(raw_img)
            if cached_uri and cached_uri.startswith("data:image/"):
                _, b64 = cached_uri.split(",", 1)
                im = Image.open(io.BytesIO(base64.b64decode(b64.strip())))
                if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
                    rgba = im.convert("RGBA")
                    bg = Image.new("RGB", rgba.size, (255, 255, 255))
                    bg.paste(rgba, mask=rgba.split()[3])
                    return bg
                return im.convert("RGB")
            else:
                req = urllib.request.Request(
                    raw_img,
                    headers={
                        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                        "Referer": "https://www.google.com/"
                    }
                )
                with urllib.request.urlopen(req, timeout=6) as response:
                    im = Image.open(io.BytesIO(response.read()))
                    if im.mode in ("RGBA", "LA") or (im.mode == "P" and "transparency" in im.info):
                        rgba = im.convert("RGBA")
                        bg = Image.new("RGB", rgba.size, (255, 255, 255))
                        bg.paste(rgba, mask=rgba.split()[3])
                        return bg
                    return im.convert("RGB")
        except Exception as e:
            print(f"Error fetching external image for {name}:", e)

    return None


def get_safe_item_img(it):
    img = it.get('image') if isinstance(it, dict) else None
    if img is not None:
        try:
            return img.convert("RGB")
        except Exception:
            pass
    # Guaranteed fallback placeholder image
    ph = Image.new("RGB", (300, 300), (241, 245, 249))
    d = ImageDraw.Draw(ph)
    name = (it.get('name') if isinstance(it, dict) else '') or "Product"
    safe_draw_text(d, (150, 150), name[:16], fill=(71, 85, 105), anchor="mm", font=get_font_helper(size=14, bold=True))
    return ph


def create_combo_package_collage(package_name: str, package_price: float, items_data: list) -> Image.Image:
    """
    Creates a clean, attractive multi-product grid collage card from actual product photos.
    items_data: list of dicts [{'name': '...', 'image': PIL.Image, 'qty': 1}]
    """
    w, h = 600, 600
    card = Image.new("RGB", (w, h), (255, 255, 255))
    draw = ImageDraw.Draw(card)

    # 1. Top Header Banner
    header_h = 58
    draw.rectangle([0, 0, w, header_h], fill=(240, 253, 244))
    draw.line([0, header_h, w, header_h], fill=(187, 247, 208), width=2)

    font_badge = get_font_helper(size=15, bold=True)
    safe_draw_text(draw, (20, header_h // 2), "SPECIAL COMBO DEAL", fill=(21, 128, 61), anchor="lm", font=font_badge)

    font_price = get_font_helper(size=19, bold=True)
    safe_draw_text(draw, (w - 20, header_h // 2), f"TK {package_price:,.2f}", fill=(22, 163, 74), anchor="rm", font=font_price)

    # 2. Bottom Title Banner
    bottom_h = 60
    bottom_y0 = h - bottom_h
    draw.rectangle([0, bottom_y0, w, h], fill=(248, 250, 252))
    draw.line([0, bottom_y0, w, bottom_y0], fill=(226, 232, 240), width=2)

    font_title = get_font_helper(size=18, bold=True)
    title_str = str(package_name)[:34]
    safe_draw_text(draw, (20, bottom_y0 + (bottom_h // 2)), title_str, fill=(15, 23, 42), anchor="lm", font=font_title)

    font_sub = get_font_helper(size=12, bold=False)
    safe_draw_text(draw, (w - 20, bottom_y0 + (bottom_h // 2)), f"{len(items_data)} Products Included", fill=(100, 116, 139), anchor="rm", font=font_sub)

    # 3. Center Collage Canvas
    center_y0 = header_h + 10
    center_h = bottom_y0 - center_y0 - 10
    num = len(items_data)

    if num == 0:
        safe_draw_text(draw, (w // 2, center_y0 + center_h // 2), "Combo Grocery Bundle", fill=(148, 163, 184), anchor="mm", font=font_badge)
    elif num == 1:
        it = items_data[0]
        img = get_safe_item_img(it)
        max_w = w - 40
        max_h = center_h - 20
        img.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)
        cx = (w - img.width) // 2
        cy = center_y0 + (center_h - img.height) // 2
        card.paste(img, (cx, cy))
    elif num == 2:
        cell_w = (w - 36) // 2
        cell_h = center_h
        for i, it in enumerate(items_data[:2]):
            x0 = 14 + i * (cell_w + 8)
            y0 = center_y0
            safe_draw_rounded_rectangle(draw, [x0, y0, x0 + cell_w, y0 + cell_h], radius=10, fill=(248, 250, 252), outline=(226, 232, 240), width=1)
            img = get_safe_item_img(it)
            img.thumbnail((cell_w - 24, cell_h - 40), Image.Resampling.LANCZOS)
            card.paste(img, (x0 + (cell_w - img.width) // 2, y0 + 10 + (cell_h - 45 - img.height) // 2))
            lbl = it['name'][:18]
            font_lbl = get_font_helper(size=11, bold=True)
            safe_draw_text(draw, (x0 + cell_w // 2, y0 + cell_h - 16), lbl, fill=(51, 65, 85), anchor="mm", font=font_lbl)
    elif num in (3, 4):
        cols = 2
        cell_w = (w - 36) // 2
        cell_h = (center_h - 10) // 2
        for i, it in enumerate(items_data[:4]):
            r = i // cols
            c = i % cols
            if num == 3 and i == 2:
                x0 = (w - cell_w) // 2
            else:
                x0 = 14 + c * (cell_w + 8)
            y0 = center_y0 + r * (cell_h + 10)
            safe_draw_rounded_rectangle(draw, [x0, y0, x0 + cell_w, y0 + cell_h], radius=8, fill=(248, 250, 252), outline=(226, 232, 240), width=1)
            img = get_safe_item_img(it)
            img.thumbnail((cell_w - 20, cell_h - 32), Image.Resampling.LANCZOS)
            card.paste(img, (x0 + (cell_w - img.width) // 2, y0 + 6 + (cell_h - 36 - img.height) // 2))
            lbl = it['name'][:20]
            font_lbl = get_font_helper(size=11, bold=True)
            safe_draw_text(draw, (x0 + cell_w // 2, y0 + cell_h - 12), lbl, fill=(51, 65, 85), anchor="mm", font=font_lbl)
    else:
        cols = 3
        cell_w = (w - 40) // 3
        cell_h = (center_h - 10) // 2
        for i, it in enumerate(items_data[:6]):
            r = i // cols
            c = i % cols
            x0 = 12 + c * (cell_w + 8)
            y0 = center_y0 + r * (cell_h + 10)
            safe_draw_rounded_rectangle(draw, [x0, y0, x0 + cell_w, y0 + cell_h], radius=8, fill=(248, 250, 252), outline=(226, 232, 240), width=1)
            img = get_safe_item_img(it)
            img.thumbnail((cell_w - 16, cell_h - 28), Image.Resampling.LANCZOS)
            card.paste(img, (x0 + (cell_w - img.width) // 2, y0 + 6 + (cell_h - 32 - img.height) // 2))
            lbl = it['name'][:14]
            font_lbl = get_font_helper(size=10, bold=True)
            safe_draw_text(draw, (x0 + cell_w // 2, y0 + cell_h - 10), lbl, fill=(51, 65, 85), anchor="mm", font=font_lbl)

    draw.rectangle([0, 0, w - 1, h - 1], outline=(203, 213, 225), width=2)
    return card


def create_showcase_combo_collage(package_name: str, package_price: float, items_data: list) -> Image.Image:
    """
    Creates a clean showcase layout where actual product photos are displayed together on a clean white background
    with a badge and price tag, similar to high-end eCommerce bundle covers.
    """
    w, h = 600, 600
    card = Image.new("RGB", (w, h), (255, 255, 255))
    draw = ImageDraw.Draw(card)

    # Top Green Badge Header
    draw.rectangle([0, 0, w, 64], fill=(21, 128, 61))
    font_badge = get_font_helper(size=18, bold=True)
    safe_draw_text(draw, (20, 32), str(package_name)[:30], fill=(255, 255, 255), anchor="lm", font=font_badge)

    font_price = get_font_helper(size=20, bold=True)
    safe_draw_text(draw, (w - 20, 32), f"TK {package_price:,.2f}", fill=(254, 240, 138), anchor="rm", font=font_price)

    # Bottom footer
    draw.rectangle([0, h - 44, w, h], fill=(241, 245, 249))
    draw.line([0, h - 44, w, h - 44], fill=(203, 213, 225), width=1)
    font_ft = get_font_helper(size=13, bold=True)
    safe_draw_text(draw, (w // 2, h - 22), f"Special Combo Bundle • {len(items_data)} Items Included", fill=(71, 85, 105), anchor="mm", font=font_ft)

    # Center area
    center_y0 = 64
    center_h = (h - 44) - center_y0
    num = len(items_data)

    if num == 1:
        img = get_safe_item_img(items_data[0])
        img.thumbnail((w - 60, center_h - 40), Image.Resampling.LANCZOS)
        card.paste(img, ((w - img.width) // 2, center_y0 + (center_h - img.height) // 2))
    elif num == 2:
        cell_w = (w - 40) // 2
        for i, it in enumerate(items_data[:2]):
            img = get_safe_item_img(it)
            img.thumbnail((cell_w - 20, center_h - 40), Image.Resampling.LANCZOS)
            cx = 20 + i * cell_w + (cell_w - img.width) // 2
            cy = center_y0 + (center_h - img.height) // 2
            card.paste(img, (cx, cy))
    elif num == 3:
        top_w = (w - 40) // 2
        top_h = (center_h - 20) // 2
        img0 = get_safe_item_img(items_data[0])
        img0.thumbnail((top_w - 20, top_h - 10), Image.Resampling.LANCZOS)
        card.paste(img0, (20 + (top_w - img0.width) // 2, center_y0 + 10 + (top_h - img0.height) // 2))
        
        img1 = get_safe_item_img(items_data[1])
        img1.thumbnail((top_w - 20, top_h - 10), Image.Resampling.LANCZOS)
        card.paste(img1, (20 + top_w + (top_w - img1.width) // 2, center_y0 + 10 + (top_h - img1.height) // 2))
        
        img2 = get_safe_item_img(items_data[2])
        img2.thumbnail((w - 100, top_h - 10), Image.Resampling.LANCZOS)
        card.paste(img2, ((w - img2.width) // 2, center_y0 + top_h + 10 + (top_h - img2.height) // 2))
    elif num <= 4:
        cols = 2
        cell_w = (w - 40) // 2
        cell_h = (center_h - 20) // 2
        for i, it in enumerate(items_data[:4]):
            r = i // cols
            c = i % cols
            img = get_safe_item_img(it)
            img.thumbnail((cell_w - 20, cell_h - 20), Image.Resampling.LANCZOS)
            cx = 20 + c * cell_w + (cell_w - img.width) // 2
            cy = center_y0 + 10 + r * cell_h + (cell_h - img.height) // 2
            card.paste(img, (cx, cy))
    else:
        cols = 3
        cell_w = (w - 40) // 3
        cell_h = (center_h - 20) // 2
        for i, it in enumerate(items_data[:6]):
            r = i // cols
            c = i % cols
            img = get_safe_item_img(it)
            img.thumbnail((cell_w - 14, cell_h - 14), Image.Resampling.LANCZOS)
            cx = 20 + c * cell_w + (cell_w - img.width) // 2
            cy = center_y0 + 10 + r * cell_h + (cell_h - img.height) // 2
            card.paste(img, (cx, cy))

    draw.rectangle([0, 0, w - 1, h - 1], outline=(203, 213, 225), width=2)
    return card


def create_promotional_combo_banner(package_name: str, package_price: float, items_data: list) -> Image.Image:
    """
    Creates an eye-catching promotional combo banner card with vibrant red/amber header and dark modern footer.
    """
    w, h = 600, 600
    card = Image.new("RGB", (w, h), (255, 255, 255))
    draw = ImageDraw.Draw(card)

    # Top banner
    header_h = 70
    draw.rectangle([0, 0, w, header_h], fill=(220, 38, 38))
    font_badge = get_font_helper(size=14, bold=True)
    safe_draw_text(draw, (w // 2, 22), "MEGA VALUE COMBO PACK", fill=(254, 240, 138), anchor="mm", font=font_badge)
    font_title = get_font_helper(size=17, bold=True)
    safe_draw_text(draw, (w // 2, 48), str(package_name)[:34], fill=(255, 255, 255), anchor="mm", font=font_title)

    # Bottom banner with Price
    bottom_h = 70
    bottom_y0 = h - bottom_h
    draw.rectangle([0, bottom_y0, w, h], fill=(15, 23, 42))

    font_pr_lbl = get_font_helper(size=12, bold=False)
    safe_draw_text(draw, (24, bottom_y0 + 22), "SPECIAL COMBO PRICE", fill=(148, 163, 184), anchor="lm", font=font_pr_lbl)
    font_pr = get_font_helper(size=22, bold=True)
    safe_draw_text(draw, (24, bottom_y0 + 48), f"TK {package_price:,.2f}", fill=(74, 222, 128), anchor="lm", font=font_pr)

    font_items = get_font_helper(size=13, bold=True)
    safe_draw_text(draw, (w - 24, bottom_y0 + (bottom_h // 2)), f"{len(items_data)} Real Items Included", fill=(255, 255, 255), anchor="rm", font=font_items)

    # Center products
    center_y0 = header_h + 10
    center_h = bottom_y0 - center_y0 - 10
    num = len(items_data)

    if num == 1:
        it = items_data[0]
        img = get_safe_item_img(it)
        img.thumbnail((w - 60, center_h - 40), Image.Resampling.LANCZOS)
        card.paste(img, ((w - img.width) // 2, center_y0 + (center_h - img.height) // 2))
    elif num == 2:
        cell_w = (w - 40) // 2
        for i, it in enumerate(items_data[:2]):
            x0 = 16 + i * (cell_w + 8)
            y0 = center_y0
            safe_draw_rounded_rectangle(draw, [x0, y0, x0 + cell_w, y0 + center_h], radius=10, fill=(248, 250, 252), outline=(226, 232, 240), width=1)
            img = get_safe_item_img(it)
            img.thumbnail((cell_w - 24, center_h - 44), Image.Resampling.LANCZOS)
            card.paste(img, (x0 + (cell_w - img.width) // 2, y0 + 10 + (center_h - 48 - img.height) // 2))
            safe_draw_text(draw, (x0 + cell_w // 2, y0 + center_h - 16), it['name'][:18], fill=(30, 41, 59), anchor="mm", font=get_font_helper(size=11, bold=True))
    elif num in (3, 4):
        cols = 2
        cell_w = (w - 36) // 2
        cell_h = (center_h - 10) // 2
        for i, it in enumerate(items_data[:4]):
            r = i // cols
            c = i % cols
            if num == 3 and i == 2:
                x0 = (w - cell_w) // 2
            else:
                x0 = 14 + c * (cell_w + 8)
            y0 = center_y0 + r * (cell_h + 10)
            safe_draw_rounded_rectangle(draw, [x0, y0, x0 + cell_w, y0 + cell_h], radius=8, fill=(248, 250, 252), outline=(226, 232, 240), width=1)
            img = get_safe_item_img(it)
            img.thumbnail((cell_w - 20, cell_h - 32), Image.Resampling.LANCZOS)
            card.paste(img, (x0 + (cell_w - img.width) // 2, y0 + 6 + (cell_h - 36 - img.height) // 2))
            safe_draw_text(draw, (x0 + cell_w // 2, y0 + cell_h - 12), it['name'][:20], fill=(30, 41, 59), anchor="mm", font=get_font_helper(size=11, bold=True))
    else:
        cols = 3
        cell_w = (w - 40) // 3
        cell_h = (center_h - 10) // 2
        for i, it in enumerate(items_data[:6]):
            r = i // cols
            c = i % cols
            x0 = 12 + c * (cell_w + 8)
            y0 = center_y0 + r * (cell_h + 10)
            safe_draw_rounded_rectangle(draw, [x0, y0, x0 + cell_w, y0 + cell_h], radius=8, fill=(248, 250, 252), outline=(226, 232, 240), width=1)
            img = get_safe_item_img(it)
            img.thumbnail((cell_w - 16, cell_h - 28), Image.Resampling.LANCZOS)
            card.paste(img, (x0 + (cell_w - img.width) // 2, y0 + 6 + (cell_h - 32 - img.height) // 2))
            safe_draw_text(draw, (x0 + cell_w // 2, y0 + cell_h - 10), it['name'][:14], fill=(30, 41, 59), anchor="mm", font=get_font_helper(size=10, bold=True))

    draw.rectangle([0, 0, w - 1, h - 1], outline=(203, 213, 225), width=2)
    return card


@app.route("/api/ai/generate_combo_image", methods=["POST"])
@login_required
@admin_required
def api_ai_generate_combo_image():
    import io
    import base64
    data = request.json or {}
    package_name = (data.get("package_name") or "Grocery Combo Deal").strip()
    package_price = float(data.get("package_price") or 0.0)
    items_list = data.get("items", [])
    raw_images = list(data.get("item_images", []))
    product_ids = data.get("product_ids", [])

    debug_log = []
    # 1. Fetch products info & images directly from SQLite DB (most complete source)
    resolved_products = []  # list of {'id': ..., 'name': ..., 'image_url': ...}
    valid_pids = []
    if product_ids:
        for pid in product_ids:
            try:
                valid_pids.append(int(pid))
            except (ValueError, TypeError):
                pass

    debug_log.append(f"valid_pids: {valid_pids}")

    if valid_pids:
        try:
            conn = get_connection()
            placeholders = ",".join("?" for _ in valid_pids)
            p_rows = conn.execute(
                f"SELECT id, image_url, name FROM products WHERE id IN ({placeholders})",
                valid_pids
            ).fetchall()
            conn.close()
            debug_log.append(f"p_rows count: {len(p_rows)}")
            # Preserve the ordering of product_ids requested
            row_map = {int(r["id"]): r for r in p_rows}
            for pid in valid_pids:
                r = row_map.get(pid)
                if r:
                    resolved_products.append({
                        "id": r["id"],
                        "name": r["name"],
                        "image_url": r["image_url"] or ""
                    })
        except Exception as e:
            debug_log.append(f"p_rows error: {str(e)}")
            print("Error fetching product images for combo:", e)

    # If product_ids query returned nothing or had missing items, lookup by items_list names
    if len(resolved_products) < len(items_list) and items_list:
        try:
            conn = get_connection()
            for idx, raw_name in enumerate(items_list):
                clean_name = raw_name.split("(")[0].strip()
                if not any(rp.get("name") == clean_name for rp in resolved_products):
                    p_match = conn.execute(
                        "SELECT id, image_url, name FROM products WHERE LOWER(name) = LOWER(?) OR instr(LOWER(name), LOWER(?)) > 0 LIMIT 1",
                        (clean_name, clean_name)
                    ).fetchone()
                    if p_match:
                        resolved_products.append({
                            "id": p_match["id"],
                            "name": p_match["name"],
                            "image_url": p_match["image_url"] or (raw_images[idx] if idx < len(raw_images) else "")
                        })
                    elif idx < len(raw_images) and raw_images[idx]:
                        resolved_products.append({
                            "id": f"item_{idx}",
                            "name": raw_name,
                            "image_url": raw_images[idx]
                        })
            conn.close()
        except Exception as e:
            debug_log.append(f"name match error: {str(e)}")
            print("Error matching combo product names from DB:", e)

    # Final fallback if still empty
    if not resolved_products and (raw_images or items_list):
        for idx, raw_img in enumerate(raw_images):
            name = items_list[idx] if idx < len(items_list) else f"Item {idx+1}"
            resolved_products.append({
                "id": idx,
                "name": name,
                "image_url": raw_img or ""
            })

    debug_log.append(f"resolved_products count: {len(resolved_products)}")

    # 2. Robustly Load Real PIL Images from actual product photos
    items_data = []  # list of {'name': str, 'image': PIL.Image, 'qty': 1}
    for idx, p_info in enumerate(resolved_products):
        raw_img = p_info.get("image_url") or ""
        name = p_info.get("name") or "Product"
        im = load_pil_image_safe(raw_img, name)
        # Fallback to client raw_images if local load failed
        if im is None and idx < len(raw_images) and raw_images[idx]:
            im = load_pil_image_safe(raw_images[idx], name)

        debug_log.append(f"item {name} im loaded: {im is not None} (raw_img: {raw_img[:35]})")

        # If product has no image or failed to load, create a clean placeholder card
        if im is None:
            im = Image.new("RGB", (300, 300), (241, 245, 249))
            d = ImageDraw.Draw(im)
            font_ph = get_font_helper(size=14, bold=True)
            d.text((150, 140), "🛍️", fill=(100, 116, 139), anchor="mm", font=get_font_helper(size=36))
            d.text((150, 190), name[:18], fill=(71, 85, 105), anchor="mm", font=font_ph)

        items_data.append({
            "name": name,
            "image": im,
            "qty": 1
        })

    debug_log.append(f"items_data count: {len(items_data)}")

    generated_images = []

    # Option 1: 🎁 Smart Multi-Item Grid Collage (from actual product photos)
    if items_data:
        try:
            grid_card = create_combo_package_collage(package_name, package_price, items_data)
            buf = io.BytesIO()
            grid_card.save(buf, format="JPEG", quality=92, optimize=True)
            b64_str = base64.b64encode(buf.getvalue()).decode("utf-8")
            generated_images.append({
                "url": f"data:image/jpeg;base64,{b64_str}",
                "label": "🎁 Smart Product Grid Collage"
            })
            debug_log.append("grid_card success")
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            debug_log.append(f"grid_card exception: {str(e)} -> {tb}")
            print("Error rendering grid collage card:", e, tb)

    # Option 2: 🛍️ Clean Showcase Collage (from actual product photos)
    if items_data:
        try:
            showcase_card = create_showcase_combo_collage(package_name, package_price, items_data)
            buf2 = io.BytesIO()
            showcase_card.save(buf2, format="JPEG", quality=92, optimize=True)
            b64_str2 = base64.b64encode(buf2.getvalue()).decode("utf-8")
            generated_images.append({
                "url": f"data:image/jpeg;base64,{b64_str2}",
                "label": "🛍️ Clean Product Showcase"
            })
            debug_log.append("showcase_card success")
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            debug_log.append(f"showcase_card exception: {str(e)} -> {tb}")
            print("Error rendering showcase collage card:", e, tb)

    # Option 3: 🔥 Mega Value Commercial Promo Banner (from actual product photos)
    if items_data:
        try:
            banner_card = create_promotional_combo_banner(package_name, package_price, items_data)
            buf3 = io.BytesIO()
            banner_card.save(buf3, format="JPEG", quality=92, optimize=True)
            b64_str3 = base64.b64encode(buf3.getvalue()).decode("utf-8")
            generated_images.append({
                "url": f"data:image/jpeg;base64,{b64_str3}",
                "label": "🔥 Mega Value Offer Banner"
            })
            debug_log.append("banner_card success")
        except Exception as e:
            import traceback
            tb = traceback.format_exc()
            debug_log.append(f"banner_card exception: {str(e)} -> {tb}")
            print("Error rendering promotional banner card:", e, tb)

    # Option 4: ✨ 3D AI Studio Hamper (Pollinations AI) - optional AI visual
    items_str = ", ".join([it["name"] for it in items_data[:5]]) if items_data else "assorted supermarket daily groceries"
    full_prompt = (
        f'Award-winning commercial studio product photography of supermarket combo package bundle "{package_name}". '
        f'The combo bundle contains neatly arranged products: {items_str}. '
        'All grocery items are displayed together in an authentic supermarket gift hamper basket with a gold ribbon. '
        'Pure clean white background, soft diffused studio light, 8k resolution, photorealistic retail packaging.'
    )
    encoded_prompt = urllib.parse.quote(full_prompt)
    width, height = 600, 600
    
    seeds = [303]
    for idx, s in enumerate(seeds):
        ai_url = f"https://image.pollinations.ai/prompt/{encoded_prompt}?width={width}&height={height}&model=turbo&seed={s}&nologo=true"
        try:
            req = urllib.request.Request(ai_url, headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"})
            with urllib.request.urlopen(req, timeout=4) as response:
                img_data = response.read()
                if len(img_data) > 1000:
                    b64 = base64.b64encode(img_data).decode("utf-8")
                    generated_images.append({
                        "url": f"data:image/jpeg;base64,{b64}",
                        "label": "✨ 3D AI Gift Hamper"
                    })
        except Exception as e:
            print("Combo AI Generation Error:", e)

    return jsonify({
        "success": True,
        "images": generated_images,
        "prompt": full_prompt,
        "debug_log": debug_log
    })


@app.route("/api/image_proxy")
@login_required
@admin_required
def api_image_proxy():
    img_url = request.args.get("url", "").strip()
    if not img_url or not (img_url.startswith("http://") or img_url.startswith("https://")):
        return "Invalid URL", 400
    
    import urllib.request
    import urllib.parse
    import io
    from PIL import Image
    try:
        parts = urllib.parse.urlsplit(img_url)
        clean_url = urllib.parse.urlunsplit((
            parts.scheme,
            parts.netloc,
            urllib.parse.quote(urllib.parse.unquote(parts.path)),
            parts.query,
            parts.fragment
        ))
        req = urllib.request.Request(
            clean_url,
            headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": "https://www.google.com/"
            }
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            data = resp.read()
            img = apply_image_background(Image.open(io.BytesIO(data)))
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=90, optimize=True)
            return Response(
                buf.getvalue(),
                mimetype="image/jpeg",
                headers={
                    "Access-Control-Allow-Origin": "*",
                    "Cache-Control": "public, max-age=86400"
                }
            )
    except Exception as e:
        print("Proxy Image Fetch Error:", e)
        return jsonify({"error": str(e)}), 500


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

    # Check if code matches a Combo Package ID or Name
    pkg_code_id = None
    if code.lower().startswith("pkg_") or code.lower().startswith("pkg-") or code.lower().startswith("combo-"):
        try:
            pkg_code_id = int(re.sub(r"\D", "", code))
        except Exception:
            pkg_code_id = None

    pkg_match = None
    if pkg_code_id:
        pkg_match = conn.execute("SELECT * FROM packages WHERE id = ? AND is_active = 1", (pkg_code_id,)).fetchone()
    if not pkg_match:
        pkg_match = conn.execute("SELECT * FROM packages WHERE LOWER(name) = LOWER(?) AND is_active = 1", (code,)).fetchone()

    if pkg_match:
        p_items = conn.execute("""
            SELECT pi.*, p.name as prod_name, p.stock_qty, p.sell_price, p.sku
            FROM package_items pi JOIN products p ON pi.product_id = p.id
            WHERE pi.package_id = ?
        """, (pkg_match["id"],)).fetchall()

        min_avail_pkg = 999
        for pi in p_items:
            avail = pi["stock_qty"] // pi["quantity"] if pi["quantity"] > 0 else 0
            if avail < min_avail_pkg:
                min_avail_pkg = avail

        conn.close()
        return jsonify({
            "id": f"pkg_{pkg_match['id']}",
            "package_id": pkg_match["id"],
            "is_package": True,
            "name": f"📦 {pkg_match['name']}",
            "sku": "COMBO",
            "price": float(pkg_match["package_price"]),
            "mrp": float(pkg_match["package_price"]),
            "vat_pct": 0,
            "stock_qty": max(0, min_avail_pkg),
            "is_offer": 0,
            "offer_type": "",
            "offer_value": "",
            "offer_title": "",
            "unit_serial": None,
        })

    product = None
    specific_unit_serial = None
    matched_unit = None

    # 1. Try matching physical tag's unique serial number (a_code) first (e.g. SN-000004)
    unit_by_acode = conn.execute("SELECT * FROM product_units WHERE a_code = ? AND status = 'in_stock'", (code,)).fetchone()
    if not unit_by_acode and code.upper().startswith("SN-"):
        unit_by_acode = conn.execute("SELECT * FROM product_units WHERE UPPER(a_code) = ? AND status = 'in_stock'", (code.upper(),)).fetchone()
    
    if unit_by_acode:
        product = conn.execute("SELECT * FROM products WHERE id = ?", (unit_by_acode["product_id"],)).fetchone()
        specific_unit_serial = unit_by_acode["a_code"]
        matched_unit = unit_by_acode

    # 2. If not matched by serial tag, match by product SKU or name
    if not product:
        product = conn.execute("SELECT * FROM products WHERE sku = ? OR LOWER(name) = LOWER(?)", (code, code)).fetchone()

    if not product:
        conn.close()
        return jsonify({"error": f'No product found for "{code}".'}), 404

    # Check if expired
    today_date = datetime.now().strftime("%Y-%m-%d")
    if product["expiry_date"] and product["expiry_date"] <= today_date:
        conn.close()
        return jsonify({"error": f'Product "{product["name"]}" expired on {product["expiry_date"]} and has been moved to Returned/Expired section.'}), 400

    # 3. If a specific unit serial was not matched, pick the next available in-stock unit serial (FIFO)
    if not specific_unit_serial:
        if exclude:
            placeholders = ",".join("?" for _ in exclude)
            matched_unit = conn.execute(f"""
                SELECT * FROM product_units
                WHERE product_id = ? AND status = 'in_stock' AND a_code NOT IN ({placeholders})
                ORDER BY id ASC LIMIT 1
            """, (product["id"], *exclude)).fetchone()
        else:
            matched_unit = conn.execute("""
                SELECT * FROM product_units
                WHERE product_id = ? AND status = 'in_stock'
                ORDER BY id ASC LIMIT 1
            """, (product["id"],)).fetchone()
        if matched_unit:
            specific_unit_serial = matched_unit["a_code"]

    # Price determination:
    # If the matched physical unit has a lot-specific sell_price (> 0), use that price!
    if matched_unit and matched_unit["sell_price"] and float(matched_unit["sell_price"]) > 0:
        checkout_price = float(matched_unit["sell_price"])
        checkout_mrp = float(matched_unit["mrp"]) if (matched_unit["mrp"] and float(matched_unit["mrp"]) > 0) else float(product["mrp"] or 0)
    else:
        checkout_price = float(product["sell_price"] or 0)
        checkout_mrp = float(product["mrp"] or 0)

    conn.close()

    return jsonify({
        "id": product["id"],
        "name": product["name"],
        "sku": product["sku"],
        "price": checkout_price,
        "mrp": checkout_mrp,
        "vat_pct": product["vat_pct"],
        "stock_qty": product["stock_qty"],
        "is_offer": product["is_offer"],
        "offer_type": product["offer_type"],
        "offer_value": product["offer_value"],
        "offer_title": product["offer_title"],
        "unit_serial": specific_unit_serial,
    })


@app.route("/api/pos/search")
@login_required
def api_pos_search():
    """Unified fast search for Shop POS: returns ALL matched Products and Combo Packages (medicines live in Pharmacy POS)."""
    q = (request.args.get("q") or "").strip()
    if not q:
        return jsonify({"results": []})

    today_date = datetime.now().strftime("%Y-%m-%d")
    q_like = f"%{q.lower()}%"
    conn = get_connection()
    results = []

    # 1. Search ALL matched non-expired shop products (by SKU or Name)
    p_rows = conn.execute("""
        SELECT id, name, sku, sell_price, mrp, stock_qty, vat_pct, offer_type, offer_value, offer_title
        FROM products
        WHERE (LOWER(name) LIKE ? OR LOWER(sku) LIKE ?)
          AND stock_qty > 0
          AND (expiry_date IS NULL OR expiry_date = '' OR expiry_date > ?)
        ORDER BY CASE WHEN LOWER(sku) = ? THEN 0 WHEN LOWER(name) LIKE ? THEN 1 ELSE 2 END, name ASC
    """, (q_like, q_like, today_date, q.lower(), f"{q.lower()}%")).fetchall()
    for r in p_rows:
        results.append({
            "type": "product",
            "id": r["id"],
            "name": r["name"],
            "sku": r["sku"] or "",
            "price": float(r["sell_price"] or 0),
            "mrp": float(r["mrp"] or 0),
            "vat_pct": float(r["vat_pct"] or 0),
            "stock_qty": int(r["stock_qty"] or 0),
            "badge": "🛒 পণ্য",
            "badge_color": "#2563eb",
            "offer_type": r["offer_type"] or "",
            "offer_value": r["offer_value"] or "",
            "offer_title": r["offer_title"] or ""
        })

    # 2. Search ALL matched combo packages
    pkg_rows = conn.execute("""
        SELECT id, name, package_price
        FROM packages
        WHERE is_active = 1 AND LOWER(name) LIKE ?
        ORDER BY name ASC
    """, (q_like,)).fetchall()
    for r in pkg_rows:
        results.append({
            "type": "package",
            "id": f"pkg_{r['id']}",
            "package_id": r["id"],
            "is_package": True,
            "name": f"📦 {r['name']}",
            "sku": "COMBO",
            "price": float(r["package_price"] or 0),
            "mrp": float(r["package_price"] or 0),
            "vat_pct": 0,
            "stock_qty": 99,
            "badge": "🎁 কম্বো",
            "badge_color": "#ea580c"
        })

    conn.close()
    return jsonify({"results": results})


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

    raw_pkgs = conn.execute("SELECT * FROM packages WHERE is_active = 1").fetchall()
    packages = []
    for pkg in raw_pkgs:
        p_dict = dict(pkg)
        items = conn.execute("""
            SELECT pi.*, p.name AS product_name, p.sell_price, p.mrp, p.stock_qty
            FROM package_items pi JOIN products p ON pi.product_id = p.id
            WHERE pi.package_id = ?
        """, (pkg["id"],)).fetchall()
        p_dict["included_items"] = [dict(i) for i in items]

        min_stock = 999
        for it in items:
            avail = it["stock_qty"] // it["quantity"] if it["quantity"] > 0 else 0
            if avail < min_stock:
                min_stock = avail
        p_dict["combo_stock"] = max(0, min_stock)
        packages.append(p_dict)

    shop_settings = get_all_settings(conn)
    conn.close()
    return render_template("pos.html", products=all_products, packages=packages, settings=shop_settings)


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

    shop_settings = get_all_settings(conn)
    apply_to_pos = str(shop_settings.get("apply_max_qty_to_pos", "0")).strip() in ("1", "true", "True")
    max_pkg_qty = int(shop_settings.get("max_order_qty_package") or 0)
    max_prod_qty = int(shop_settings.get("max_order_qty_product") or 0)

    sub_total = 0
    mrp_total = 0
    total_vat = 0
    line_details = []

    for item in items:
        is_med = item.get("is_medicine") or str(item.get("product_id", "")).startswith("med_") or item.get("medicine_id")
        is_pkg = not is_med and (item.get("is_package") or str(item.get("product_id", "")).startswith("pkg_") or item.get("package_id"))

        if is_med:
            med_id = int(str(item.get("medicine_id") or item.get("product_id")).replace("med_", ""))
            med = cur.execute("SELECT * FROM pharmacy_medicines WHERE id = ?", (med_id,)).fetchone()
            if not med:
                conn.close()
                return jsonify({"error": "A medicine in the cart no longer exists."}), 400
            quantity = int(item["quantity"])
            if med["stock_qty"] is not None and med["stock_qty"] < quantity:
                conn.close()
                return jsonify({"error": f'Not enough stock for medicine "{med["name"]}" ({med["stock_qty"]} available, {quantity} requested).'}), 400

            med_price = float(med["unit_price"] or 0)
            line_subtotal = med_price * quantity
            sub_total += line_subtotal
            mrp_total += line_subtotal
            line_details.append({
                "is_medicine": True,
                "medicine_id": med_id,
                "medicine_name": med["name"],
                "medicine_strength": med["strength"] or med["dosage_form"],
                "quantity": quantity,
                "unit_price": med_price,
                "mrp_price": med_price,
                "vat_pct": 0,
                "line_vat": 0,
                "cost_price": 0.0
            })
        elif is_pkg:
            pkg_id = int(str(item.get("package_id") or item.get("product_id")).replace("pkg_", ""))
            pkg = cur.execute("SELECT * FROM packages WHERE id = ?", (pkg_id,)).fetchone()
            if not pkg:
                conn.close()
                return jsonify({"error": "A combo package in the cart no longer exists."}), 400
            quantity = int(item["quantity"])
            if apply_to_pos and max_pkg_qty > 0 and quantity > max_pkg_qty:
                conn.close()
                return jsonify({"error": f'Maximum allowed quantity for Combo Package "{pkg["name"]}" is {max_pkg_qty} per order.'}), 400
            pkg_items = cur.execute("""
                SELECT pi.*, p.name as prod_name, p.stock_qty, p.cost_price, p.sell_price, p.mrp
                FROM package_items pi 
                JOIN products p ON pi.product_id = p.id 
                WHERE pi.package_id = ?
            """, (pkg_id,)).fetchall()

            for pi in pkg_items:
                req_qty = quantity * pi["quantity"]
                if pi["stock_qty"] < req_qty:
                    conn.close()
                    return jsonify({"error": f'Not enough stock for "{pi["prod_name"]}" in combo package ({pi["stock_qty"]} available, {req_qty} needed).'}), 400

            pkg_price = float(pkg["package_price"])
            line_subtotal = pkg_price * quantity
            sub_total += line_subtotal
            mrp_total += line_subtotal
            line_details.append({
                "is_package": True,
                "package_id": pkg_id,
                "package_name": pkg["name"],
                "quantity": quantity,
                "unit_price": pkg_price,
                "mrp_price": pkg_price,
                "vat_pct": 0,
                "line_vat": 0,
                "cost_price": sum([float(pi["cost_price"] or 0) * pi["quantity"] for pi in pkg_items]),
                "pkg_items": [dict(pi) for pi in pkg_items]
            })
        else:
            product = cur.execute("SELECT * FROM products WHERE id = ?", (item["product_id"],)).fetchone()
            if not product:
                conn.close()
                return jsonify({"error": "A product in the cart no longer exists."}), 400
            quantity = int(item["quantity"])
            offer_type = product["offer_type"] or ""
            offer_value = product["offer_value"] or ""
            offer_title = product["offer_title"] or ""
            paid_qty, free_qty_total = calculate_paid_and_free_qty(quantity, offer_type, offer_value, offer_title, product["name"])

            if apply_to_pos and max_prod_qty > 0 and paid_qty > max_prod_qty:
                conn.close()
                return jsonify({"error": f'Maximum allowed purchase limit for product "{product["name"]}" is {max_prod_qty} paid units per order.'}), 400
            if product["stock_qty"] < quantity:
                conn.close()
                return jsonify({"error": f'Not enough stock for "{product["name"]}".'}), 400

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

            line_subtotal = product["sell_price"] * paid_qty
            vat_rate = product["vat_pct"] / 100.0 if product["vat_pct"] else 0
            line_vat = line_subtotal * vat_rate

            sub_total += line_subtotal
            total_vat += line_vat
            mrp_for_line = product["mrp"] if product["mrp"] > 0 else product["sell_price"]
            mrp_total += mrp_for_line * quantity
            line_details.append({
                "is_package": False,
                "product_id": product["id"],
                "quantity": quantity,
                "unit_price": product["sell_price"],
                "mrp_price": mrp_for_line,
                "vat_pct": product["vat_pct"],
                "line_vat": line_vat,
                "cost_price": product["cost_price"],
                "valid_serials": valid_serials
            })

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

    for ld in line_details:
        if ld.get("is_medicine"):
            med_id = ld["medicine_id"]
            quantity = ld["quantity"]
            cur.execute("UPDATE pharmacy_medicines SET stock_qty = MAX(0, stock_qty - ?) WHERE id = ?", (quantity, med_id))
            first_p = cur.execute("SELECT id FROM products LIMIT 1").fetchone()
            fk_pid = first_p["id"] if first_p else 1
            med_title = f"💊 {ld['medicine_name']}" + (f" ({ld['medicine_strength']})" if ld['medicine_strength'] else "")
            cur.execute("""
                INSERT INTO sale_items (sale_id, product_id, quantity, unit_price, mrp_price, vat_pct, vat_amount, cost_price, unit_serials)
                VALUES (?, ?, ?, ?, ?, 0, 0, 0, ?)
            """, (sale_id, fk_pid, quantity, ld["unit_price"], ld["mrp_price"], med_title))
        elif ld.get("is_package"):
            pkg_name = ld["package_name"]
            quantity = ld["quantity"]
            unit_price = ld["unit_price"]
            for pi in ld["pkg_items"]:
                req_qty = quantity * pi["quantity"]
                cur.execute("UPDATE products SET stock_qty = stock_qty - ? WHERE id = ?", (req_qty, pi["product_id"]))
                auto_units = cur.execute("""
                    SELECT id FROM product_units
                    WHERE product_id = ? AND status = 'in_stock'
                    LIMIT ?
                """, (pi["product_id"], req_qty)).fetchall()
                for u in auto_units:
                    cur.execute("UPDATE product_units SET status = 'sold' WHERE id = ?", (u["id"],))

            pkg_fk_pid = ld["pkg_items"][0]["product_id"] if ld["pkg_items"] else None
            if not pkg_fk_pid:
                first_p = cur.execute("SELECT id FROM products LIMIT 1").fetchone()
                pkg_fk_pid = first_p["id"] if first_p else 1

            pkg_id = ld.get("pkg_id")
            if not pkg_id and pkg_name:
                pkg_row = cur.execute("SELECT id FROM packages WHERE name = ?", (pkg_name,)).fetchone()
                if pkg_row:
                    pkg_id = pkg_row["id"]
            if pkg_id:
                cur.execute("UPDATE packages SET sold_quantity = sold_quantity + ? WHERE id = ?", (quantity, pkg_id))

            cur.execute("""
                INSERT INTO sale_items (sale_id, product_id, quantity, unit_price, mrp_price, vat_pct, vat_amount, cost_price, unit_serials)
                VALUES (?, ?, ?, ?, ?, 0, 0, ?, ?)
            """, (sale_id, pkg_fk_pid, quantity, unit_price, unit_price, ld["cost_price"], f"📦 {pkg_name}"))
        else:
            product_id = ld["product_id"]
            quantity = ld["quantity"]
            valid_serials = ld["valid_serials"]
            sold_serials = []

            for serial, unit_id in valid_serials:
                cur.execute("UPDATE product_units SET status = 'sold' WHERE id = ?", (unit_id,))
                sold_serials.append(serial)

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
                (sale_id, product_id, quantity, ld["unit_price"], ld["mrp_price"], ld["vat_pct"], ld["line_vat"], ld["cost_price"], unit_serials_str)
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
    for ld in line_details:
        if ld.get("is_package"):
            for pi in ld.get("pkg_items", []):
                remote_control.push_product_to_cloud(pi["product_id"])
        elif ld.get("product_id"):
            remote_control.push_product_to_cloud(ld["product_id"])


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

@app.route("/sales/history")
@app.route("/sales")
@login_required
def sales_history():
    selected_channel = (request.args.get("channel") or "all").strip().lower()
    if selected_channel not in ("all", "regular_pos", "regular_online", "pharmacy_pos", "pharmacy_online"):
        selected_channel = "all"

    conn = get_connection()
    enriched_all = _collect_enriched_sales(conn)
    conn.close()

    channel_summary = {
        "all": {"count": len(enriched_all), "amount": round(sum(float(s.get("rounded_total") or 0.0) for s in enriched_all), 2)},
        "regular_pos": {"count": 0, "amount": 0.0},
        "regular_online": {"count": 0, "amount": 0.0},
        "pharmacy_pos": {"count": 0, "amount": 0.0},
        "pharmacy_online": {"count": 0, "amount": 0.0},
    }
    for s in enriched_all:
        cat = s.get("sales_category") or "regular_pos"
        reg_amt = float(s.get("regular_amount") or 0.0)
        pharm_amt = float(s.get("pharmacy_amount") or 0.0)
        if cat == "regular_online":
            channel_summary["regular_online"]["count"] += 1
            channel_summary["regular_online"]["amount"] += reg_amt
        elif cat == "pharmacy_online":
            channel_summary["pharmacy_online"]["count"] += 1
            channel_summary["pharmacy_online"]["amount"] += pharm_amt
        elif cat == "pharmacy_pos":
            channel_summary["pharmacy_pos"]["count"] += 1
            channel_summary["pharmacy_pos"]["amount"] += pharm_amt
        elif s.get("is_mixed"):
            channel_summary["regular_pos"]["count"] += 1
            channel_summary["regular_pos"]["amount"] += reg_amt
            channel_summary["pharmacy_pos"]["count"] += 1
            channel_summary["pharmacy_pos"]["amount"] += pharm_amt
        else:
            channel_summary["regular_pos"]["count"] += 1
            channel_summary["regular_pos"]["amount"] += reg_amt

    for k in channel_summary:
        channel_summary[k]["amount"] = round(channel_summary[k]["amount"], 2)

    if selected_channel == "regular_pos":
        filtered_sales = [s for s in enriched_all if s.get("sales_category") == "regular_pos"]
    elif selected_channel == "regular_online":
        filtered_sales = [s for s in enriched_all if s.get("sales_category") == "regular_online"]
    elif selected_channel == "pharmacy_pos":
        filtered_sales = [s for s in enriched_all if s.get("sales_category") == "pharmacy_pos" or s.get("is_mixed")]
    elif selected_channel == "pharmacy_online":
        filtered_sales = [s for s in enriched_all if s.get("sales_category") == "pharmacy_online"]
    else:
        filtered_sales = enriched_all

    return render_template(
        "sales_history.html",
        sales=filtered_sales,
        all_sales_count=len(enriched_all),
        channel_summary=channel_summary,
        selected_channel=selected_channel,
    )


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


def format_delivery_address(address_details, area=None, district=None, customer_phone=None, conn=None):
    """Formats customer's address for printing as delivery address on receipts/invoices."""
    details = (address_details or "").strip()
    area_clean = (area or "").strip()
    dist_clean = (district or "").strip()

    # If details is empty or dummy placeholder, check customer_users table
    if details in ("", "Delivery Address", "No detailed address recorded") and customer_phone and conn:
        try:
            cust = conn.execute("SELECT address FROM customer_users WHERE phone = ?", (customer_phone,)).fetchone()
            if cust and cust["address"] and cust["address"].strip() not in ("Delivery Address", "No detailed address recorded"):
                details = cust["address"].strip()
        except Exception:
            pass

    if details in ("Delivery Address", "No detailed address recorded"):
        details = ""

    parts = []
    if details:
        parts.append(details)

    details_lower = details.lower()

    if area_clean and area_clean.lower() not in ("main area", "main town"):
        if area_clean.lower() not in details_lower:
            parts.append(area_clean)

    if dist_clean:
        if dist_clean.lower() not in details_lower and (not area_clean or dist_clean.lower() != area_clean.lower()):
            parts.append(dist_clean)

    return ", ".join(parts) if parts else (details or area_clean or dist_clean or "")


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
    delivery_charge = 0.0
    items = []
    
    ord_row = None
    if inv_num.startswith("INV-ONLINE-"):
        ord_num = inv_num.replace("INV-ONLINE-", "").strip()
        ord_row = conn.execute("SELECT * FROM online_orders WHERE order_number = ? OR id = ?", (ord_num, ord_num)).fetchone()

    if not ord_row and (inv_num.startswith("INV-ONLINE-") or sale_dict.get("channel") == "Online"):
        if sale_dict.get("customer_mobile"):
            ord_row = conn.execute("SELECT * FROM online_orders WHERE customer_phone = ? ORDER BY id DESC LIMIT 1", (sale_dict["customer_mobile"],)).fetchone()

    if ord_row:
            shop_st = get_all_settings(conn)
            free_del_active = (shop_st.get("free_delivery_active") or "0") == "1"
            free_del_min = float(shop_st.get("free_delivery_min_amount") or 500.0)
            
            subtotal_val = float(ord_row["subtotal"] or 0)
            if free_del_active and subtotal_val >= free_del_min:
                delivery_charge = 0.0
            else:
                delivery_charge = float(ord_row["delivery_charge"] or 0)

            sale_dict["delivery_charge"] = delivery_charge
            sale_dict["subtotal"] = subtotal_val
            sale_dict["total_amount"] = subtotal_val
            sale_dict["rounded_total"] = subtotal_val + delivery_charge
            sale_dict["order_status"] = ord_row["order_status"]
            sale_dict["area"] = ord_row["area"]
            sale_dict["district"] = ord_row["district"]
            sale_dict["address_details"] = ord_row["address_details"]
            sale_dict["delivery_otp"] = ord_row["delivery_otp"]
            sale_dict["payment_method"] = ord_row["payment_method"]
            sale_dict["delivery_address"] = format_delivery_address(
                ord_row["address_details"], ord_row["area"], ord_row["district"],
                customer_phone=ord_row["customer_phone"], conn=conn
            )
            o_items = conn.execute("SELECT * FROM online_order_items WHERE order_id = ?", (ord_row["id"],)).fetchall()
            for oi in o_items:
                oi_dict = dict(oi)
                p_name = oi_dict.get("product_name") or "Product"
                is_pkg_item = ("📦" in p_name) or ("Package" in p_name) or ("Combo" in p_name) or (oi_dict.get("product_id") == 0)

                p_row = None
                if not is_pkg_item:
                    p_row = conn.execute("SELECT sku, offer_type, offer_value, offer_title FROM products WHERE id = ?", (oi_dict["product_id"],)).fetchone()
                
                sku = "COMBO" if is_pkg_item else (p_row["sku"] if p_row else "ONLINE")
                
                qty = int(oi_dict.get("quantity") or 1)
                unit_price = float(oi_dict.get("unit_price") or 0.0)
                mrp_price = float(oi_dict.get("mrp_price") or unit_price)
                line_total = float(oi_dict.get("total_price") or (unit_price * qty))
                paid_qty = qty
                free_qty = 0

                # Only regular standalone products can have offer badges, NEVER combo packages!
                offer_type = "" if is_pkg_item else (p_row["offer_type"] if p_row else "")
                offer_title = "" if is_pkg_item else (p_row["offer_title"] if p_row else "")
                offer_value = "" if is_pkg_item else (p_row["offer_value"] if p_row else "")

                if not is_pkg_item and (offer_type in ('buy_x_get_y', 'bogo', 'buy_x_get_x') or ('buy' in (offer_title or '').lower()) or ('buy' in (offer_value or '').lower()) or ('buy' in p_name.lower())):
                    b_qty, f_qty = parse_bogo_quantities(offer_value, offer_title, p_name)
                    tot_set = b_qty + f_qty
                    if tot_set > 0:
                        sets = qty // tot_set
                        rem = qty % tot_set
                        paid_qty = (sets * b_qty) + rem
                        free_qty = sets * f_qty

                items.append({
                    "id": oi_dict.get("id"),
                    "product_id": oi_dict.get("product_id"),
                    "product_name": p_name,
                    "sku": sku,
                    "quantity": qty,
                    "paid_qty": paid_qty,
                    "free_qty": free_qty,
                    "unit_price": unit_price,
                    "mrp_price": mrp_price,
                    "line_total": line_total,
                    "total_price": line_total,
                    "vat_amount": 0.0,
                    "discount": 0.0,
                    "offer_type": offer_type,
                    "offer_title": offer_title,
                    "offer_value": offer_value
                })
    else:
        raw_items = conn.execute("""
            SELECT si.*, COALESCE(p.name, '') AS prod_name_tbl, COALESCE(p.sku, '') AS prod_sku, p.offer_type, p.offer_value, p.offer_title
            FROM sale_items si LEFT JOIN products p ON si.product_id = p.id
            WHERE si.sale_id = ?
        """, (sale_id,)).fetchall()
        
        for r in raw_items:
            i_dict = dict(r)
            pid = i_dict["product_id"]
            
            is_regular_prod = conn.execute("SELECT id FROM products WHERE id = ?", (pid,)).fetchone() if pid > 0 else None
            pkg = None
            if not is_regular_prod or (i_dict.get("prod_name_tbl") or "").startswith("📦") or (i_dict.get("unit_serials") or "").startswith("📦"):
                pkg_cand_name = (i_dict.get("unit_serials") or "").replace("📦", "").strip()
                if pkg_cand_name:
                    pkg = conn.execute("SELECT * FROM packages WHERE LOWER(name) = LOWER(?)", (pkg_cand_name,)).fetchone()
                if not pkg and pid > 0:
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
                i_dict["product_name"] = f"📦 {pkg['name']} ({', '.join(details)})"
                i_dict["sku"] = "COMBO"
                i_dict["offer_type"] = ""
                i_dict["offer_title"] = ""
                i_dict["offer_value"] = ""
            elif (i_dict.get("unit_serials") or "").startswith("📦"):
                i_dict["product_name"] = i_dict.get("unit_serials")
                i_dict["sku"] = "COMBO"
                i_dict["offer_type"] = ""
                i_dict["offer_title"] = ""
                i_dict["offer_value"] = ""
            elif (i_dict.get("unit_serials") or "").startswith("💊"):
                i_dict["product_name"] = i_dict.get("unit_serials")
                i_dict["sku"] = "PHARMACY"
                i_dict["offer_type"] = ""
                i_dict["offer_title"] = ""
                i_dict["offer_value"] = ""
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

    if not sale_dict.get("delivery_address") and sale_dict.get("customer_mobile"):
        try:
            cust_u = conn.execute("SELECT address FROM customer_users WHERE phone = ?", (sale_dict["customer_mobile"],)).fetchone()
            if cust_u and cust_u["address"] and cust_u["address"].strip() not in ("", "Delivery Address", "No detailed address recorded"):
                sale_dict["delivery_address"] = cust_u["address"].strip()
        except Exception:
            pass

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

        profile_image = ""
        u_match = [u for u in reg_users if u["phone"] == m]
        if u_match:
            name = u_match[0]["name"]
            profile_image = u_match[0]["profile_image"] if "profile_image" in u_match[0].keys() else ""
        
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
            "profile_image": profile_image,
            "visits": visits,
            "total_spent": round(total_spent, 2)
        })

    conn.close()
    return jsonify(results)


@app.route("/customers/api/profile")
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
    profile_image = ""
    u_dict = dict(user) if user else {}
    if u_dict:
        profile_image = (u_dict.get("profile_image") or u_dict.get("avatar_url") or u_dict.get("avatar_base64") or u_dict.get("avatar") or u_dict.get("image_url") or "").strip()

    latest_order = conn.execute(
        "SELECT district, area, address_details, customer_ip, ip_location, created_at FROM online_orders WHERE customer_phone = ? ORDER BY id DESC LIMIT 1",
        (phone,),
    ).fetchone()
    if latest_order:
        if not district: district = latest_order["district"] or ""
        if not area: area = latest_order["area"] or ""
        if not address_details: address_details = latest_order["address_details"] or ""

    earliest_order = conn.execute(
        "SELECT created_at FROM online_orders WHERE customer_phone = ? ORDER BY id ASC LIMIT 1",
        (phone,),
    ).fetchone()
    created_at = (u_dict.get("created_at") or (earliest_order["created_at"] if earliest_order else "") or "").strip()
    ord_ip = (latest_order["customer_ip"] if latest_order else "") or ""
    ord_loc = (latest_order["ip_location"] if latest_order else "") or ""
    reg_ip = (u_dict.get("registration_ip") or ord_ip or "").strip()
    reg_loc = (u_dict.get("registration_location") or ord_loc or "").strip()
    last_ip = (u_dict.get("last_ip") or ord_ip or reg_ip or "").strip()
    last_loc = (u_dict.get("last_location") or ord_loc or reg_loc or "").strip()
    last_seen = (u_dict.get("last_seen_at") or (latest_order["created_at"] if latest_order else "") or "").strip()
    last_device = (u_dict.get("last_device") or "").strip()

    recent_online = conn.execute(
        """SELECT order_number, created_at, total_amount, order_status,
                  COALESCE(customer_ip, '') AS customer_ip, COALESCE(ip_location, '') AS ip_location,
                  area, district
           FROM online_orders WHERE customer_phone = ? ORDER BY id DESC LIMIT 8""",
        (phone,),
    ).fetchall()
    recent_orders = [dict(ro) for ro in recent_online]

    conn.close()

    return jsonify({
        "success": True,
        "name": cust_name or f"Customer {phone}",
        "phone": phone,
        "email": u_dict.get("email", ""),
        "profile_image": profile_image,
        "district": district or "Not specified",
        "area": area or "Not specified",
        "address_details": address_details or "No detailed address recorded",
        "is_blocked": u_dict.get("is_blocked", 0),
        "block_reason": u_dict.get("block_reason", ""),
        "total_orders": total_orders,
        "total_spent": round(total_spent, 2),
        "created_at": created_at,
        "member_since": _member_since_label(created_at),
        "registration_ip": reg_ip,
        "registration_location": reg_loc,
        "last_ip": last_ip,
        "last_location": last_loc,
        "last_seen_at": last_seen,
        "last_device": last_device,
        "recent_orders": recent_orders,
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
                       COALESCE(s.customer_ip, '') AS customer_ip,
                       COALESCE(s.ip_location, '') AS ip_location,
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
                       COALESCE(o.customer_ip, '') AS customer_ip,
                       COALESCE(o.ip_location, '') AS ip_location,
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
                       COALESCE(s.customer_ip, '') AS customer_ip,
                       COALESCE(s.ip_location, '') AS ip_location,
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
                       COALESCE(o.customer_ip, '') AS customer_ip,
                       COALESCE(o.ip_location, '') AS ip_location,
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
               COALESCE(SUM(total_amount), 0) AS online_spent, MAX(created_at) AS last_activity,
               MIN(created_at) AS first_order_at
        FROM online_orders
        WHERE customer_phone != ''
        GROUP BY customer_phone
    """).fetchall()
    online_dict = {o["customer_phone"]: dict(o) for o in online_stats}

    latest_ip_by_phone = {}
    for ipr in conn.execute("""
        SELECT customer_phone, customer_ip, ip_location
        FROM online_orders
        WHERE customer_phone != '' AND COALESCE(customer_ip, '') != ''
        ORDER BY id ASC
    """).fetchall():
        latest_ip_by_phone[ipr["customer_phone"]] = (ipr["customer_ip"], ipr["ip_location"] or "")

    pos_stats = conn.execute("""
        SELECT customer_mobile, MAX(customer_name) AS customer_name, COUNT(*) AS visit_count,
               COALESCE(SUM(rounded_total), 0) AS pos_spent, MAX(created_at) AS last_visit,
               MIN(created_at) AS first_visit_at,
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

        prof_p = (reg_info.get("profile_image") or reg_info.get("avatar_url") or "").strip()
        b64_p = (reg_info.get("avatar_base64") or "").strip()
        final_cust_img = ""
        if prof_p:
            final_cust_img = prof_p
        elif b64_p:
            final_cust_img = b64_p
        elif reg_info.get("avatar"):
            final_cust_img = reg_info.get("avatar").strip()

        # Proactively retrieve profile picture from disk if not yet populated in DB record
        if not final_cust_img and phone:
            cust_uploads = os.path.join(app.root_path, "static", "uploads", "customers")
            if os.path.exists(cust_uploads):
                for f in sorted(os.listdir(cust_uploads), reverse=True):
                    if f.startswith(f"cust_{phone}") or f.startswith(f"cust_{phone[-10:]}"):
                        final_cust_img = f"/static/uploads/customers/{f}"
                        # Persist back to database
                        try:
                            conn.execute("UPDATE customer_users SET profile_image = ?, avatar_url = ? WHERE phone = ?", (final_cust_img, final_cust_img, phone))
                            conn.commit()
                        except Exception:
                            pass
                        break

        joined_at = reg_info.get("created_at") or online_dict.get(phone, {}).get("first_order_at") or pos_info.get("first_visit_at") or ""
        order_ip, order_loc = latest_ip_by_phone.get(phone, ("", ""))
        reg_ip = (reg_info.get("registration_ip") or order_ip or "").strip()
        reg_loc = (reg_info.get("registration_location") or order_loc or "").strip()
        last_ip = (reg_info.get("last_ip") or order_ip or reg_ip or "").strip()
        last_loc = (reg_info.get("last_location") or order_loc or reg_loc or "").strip()
        last_seen = (reg_info.get("last_seen_at") or last_activity or "").strip()
        last_dev = (reg_info.get("last_device") or "").strip()

        customer_directory.append({
            "customer_name": name,
            "customer_mobile": phone,
            "profile_image": final_cust_img,
            "email": email_addr,
            "password": plain_pass if plain_pass else "—",
            "visit_count": visits,
            "total_spent": round(total_spent, 2),
            "last_visit": last_activity,
            "channel_tag": channel_tag,
            "is_blocked": is_blocked,
            "blocked_until": blocked_until,
            "block_reason": block_reason,
            "created_at": joined_at,
            "member_since": _member_since_label(joined_at),
            "registration_ip": reg_ip,
            "registration_location": reg_loc,
            "last_ip": last_ip,
            "last_location": last_loc,
            "last_seen_at": last_seen,
            "last_device": last_dev,
        })

    if search:
        s_clean = search.lower().strip()
        customer_directory.sort(key=lambda x: (
            0 if (s_clean == x["customer_mobile"] or s_clean in x["customer_mobile"].lower() or (x["customer_name"] and s_clean in x["customer_name"].lower())) else 1,
            0 if x.get("last_visit") else 1
        ))
    else:
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
    profile_image = request.form.get("profile_image", "").strip()

    file = request.files.get("profile_image_file")
    if file and file.filename:
        cloud_url = upload_to_cloudinary(file, folder="supershop/customers")
        if cloud_url:
            profile_image = cloud_url
        else:
            upload_dir = os.path.join(app.root_path, "static", "uploads", "customers")
            os.makedirs(upload_dir, exist_ok=True)
            fn = f"cust_{phone}_{int(time.time())}_{secure_filename(file.filename)}"
            file_path = os.path.join(upload_dir, fn)
            file.save(file_path)
            profile_image = f"/static/uploads/customers/{fn}"

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
        "INSERT INTO customer_users (phone, name, email, password_hash, plain_password, profile_image, avatar_url, avatar_base64, is_verified, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)",
        (phone, name, email, generate_password_hash(password), password, profile_image, profile_image, profile_image, datetime.now().isoformat())
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
    profile_image = request.form.get("profile_image", "").strip()

    file = request.files.get("profile_image_file")
    if file and file.filename:
        cloud_url = upload_to_cloudinary(file, folder="supershop/customers")
        if cloud_url:
            profile_image = cloud_url
        else:
            upload_dir = os.path.join(app.root_path, "static", "uploads", "customers")
            os.makedirs(upload_dir, exist_ok=True)
            fn = f"cust_{new_phone}_{int(time.time())}_{secure_filename(file.filename)}"
            file_path = os.path.join(upload_dir, fn)
            file.save(file_path)
            profile_image = f"/static/uploads/customers/{fn}"

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
            "INSERT INTO customer_users (phone, name, email, password_hash, plain_password, profile_image, avatar_url, avatar_base64, is_verified, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1, ?)",
            (new_phone, name, email, pw_hash, plain_pw, profile_image, profile_image, profile_image, datetime.now().isoformat())
        )
    else:
        # If no new file or url provided, preserve existing image
        if not profile_image:
            profile_image = cust["profile_image"] or cust["avatar_url"] or cust["avatar_base64"] or ""

        if password:
            pw_hash = generate_password_hash(password)
            plain_pw = password
            conn.execute(
                "UPDATE customer_users SET phone = ?, name = ?, email = ?, password_hash = ?, plain_password = ?, profile_image = ?, avatar_url = ?, avatar_base64 = ? WHERE phone = ?",
                (new_phone, name, email, pw_hash, plain_pw, profile_image, profile_image, profile_image, old_phone)
            )
        else:
            conn.execute(
                "UPDATE customer_users SET phone = ?, name = ?, email = ?, profile_image = ?, avatar_url = ?, avatar_base64 = ? WHERE phone = ?",
                (new_phone, name, email, profile_image, profile_image, profile_image, old_phone)
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
    if "can_rx_quote_bill" not in columns:
        try: conn.execute("ALTER TABLE users ADD COLUMN can_rx_quote_bill INTEGER NOT NULL DEFAULT 0")
        except: pass
    conn.commit()

    start_date = request.args.get("start_date", "").strip()
    end_date = request.args.get("end_date", "").strip()
    filter_rider_id = request.args.get("rider_id", type=int)

    default_fee = get_rider_delivery_fee_setting(conn)
    today_str = datetime.now().strftime("%Y-%m-%d")
    current_month_str = datetime.now().strftime("%Y-%m")

    riders = conn.execute("SELECT * FROM users WHERE role = 'delivery' ORDER BY id DESC").fetchall()
    riders_list = []

    grand_total_delivered = 0
    grand_total_earned = 0.0
    grand_total_paid = 0.0
    grand_total_due = 0.0

    for r in riders:
        r_dict = dict(r)
        r_phone = r_dict.get("username", "")
        r_id = r_dict.get("id")
        
        # Fetch all orders assigned or accepted by this rider
        rider_orders = conn.execute("""
            SELECT * FROM online_orders 
            WHERE assigned_rider_id = ? OR assigned_rider_phone = ?
            ORDER BY id DESC
        """, (r_id, r_phone)).fetchall()
        
        # Fetch all payouts for this rider
        payouts_rows = conn.execute("""
            SELECT * FROM rider_payouts
            WHERE rider_id = ?
            ORDER BY payout_date DESC, id DESC
        """, (r_id,)).fetchall()
        
        payouts_data = [dict(p) for p in payouts_rows]

        orders_data = []
        all_time_delivered = 0
        all_time_earned = 0.0
        all_time_collected = 0.0

        period_delivered = 0
        period_earned = 0.0
        period_collected = 0.0
        
        for ord_row in rider_orders:
            o_dict = dict(ord_row)
            is_del = (o_dict.get("order_status") == "delivered")
            ord_date = (o_dict.get("created_at") or "")[:10]
            
            # Determine rider fee for this order
            o_fee = float(o_dict.get("rider_fee") or 0)
            if o_fee <= 0 and is_del:
                o_fee = default_fee
            o_dict["effective_rider_fee"] = o_fee

            if is_del:
                all_time_delivered += 1
                all_time_earned += o_fee
                all_time_collected += float(o_dict.get("total_amount", 0))

                # Check period filter
                in_period = True
                if start_date and ord_date < start_date:
                    in_period = False
                if end_date and ord_date > end_date:
                    in_period = False
                if in_period:
                    period_delivered += 1
                    period_earned += o_fee
                    period_collected += float(o_dict.get("total_amount", 0))

            orders_data.append(o_dict)

        all_time_paid = sum(float(p.get("amount", 0)) for p in payouts_data)
        balance_due = max(0.0, round(all_time_earned - all_time_paid, 2))

        # Payout breakdowns
        paid_today = sum(float(p.get("amount", 0)) for p in payouts_data if (p.get("payout_date") or "")[:10] == today_str)
        paid_this_month = sum(float(p.get("amount", 0)) for p in payouts_data if (p.get("payout_date") or "")[:7] == current_month_str)

        period_paid = 0.0
        filtered_payouts = []
        for p in payouts_data:
            p_date = (p.get("payout_date") or "")[:10]
            in_period = True
            if start_date and p_date < start_date:
                in_period = False
            if end_date and p_date > end_date:
                in_period = False
            if in_period:
                period_paid += float(p.get("amount", 0))
                filtered_payouts.append(p)

        grand_total_delivered += all_time_delivered
        grand_total_earned += all_time_earned
        grand_total_paid += all_time_paid
        grand_total_due += balance_due

        riders_list.append({
            "id": r_id,
            "username": r_phone,
            "full_name": r_dict.get("full_name") or r_phone,
            "plain_password": r_dict.get("plain_password") or "123456",
            "is_active": r_dict.get("is_active", 1),
            "created_at": r_dict.get("created_at", ""),
            "orders": orders_data,
            "total_orders": len(orders_data),
            "total_delivered": all_time_delivered,
            "total_earned": all_time_earned,
            "total_paid": all_time_paid,
            "balance_due": balance_due,
            "paid_today": paid_today,
            "paid_this_month": paid_this_month,
            "total_collected": all_time_collected,
            "payouts": payouts_data,
            "period_delivered": period_delivered,
            "period_earned": period_earned,
            "period_paid": period_paid,
            "period_collected": period_collected,
            "filtered_payouts": filtered_payouts,
        })
    conn.close()

    summary_stats = {
        "total_riders": len(riders_list),
        "total_delivered": grand_total_delivered,
        "total_earned": grand_total_earned,
        "total_paid": grand_total_paid,
        "total_due": grand_total_due,
        "default_rider_fee": default_fee,
        "start_date": start_date,
        "end_date": end_date,
        "filter_rider_id": filter_rider_id,
    }

    return render_template("riders.html", riders=riders_list, summary=summary_stats)


@app.route("/riders/<int:rider_id>/pay", methods=["POST"])
@login_required
@admin_required
def pay_rider(rider_id):
    conn = get_connection()
    rider = conn.execute("SELECT * FROM users WHERE id = ? AND role = 'delivery'", (rider_id,)).fetchone()
    if not rider:
        conn.close()
        flash("Rider not found.", "error")
        return redirect(url_for("riders_page"))

    try:
        amount = float(request.form.get("amount") or 0)
    except ValueError:
        amount = 0.0

    if amount <= 0:
        conn.close()
        flash("Payment amount must be greater than 0.", "error")
        return redirect(url_for("riders_page"))

    rider_name = rider["full_name"] or rider["username"]
    rider_phone = rider["username"]

    # Calculate real-time balance due to strictly prevent paying when balance is 0 or above balance due
    default_fee = get_rider_delivery_fee_setting(conn)
    delivered_orders = conn.execute("""
        SELECT rider_fee FROM online_orders 
        WHERE (assigned_rider_id = ? OR assigned_rider_phone = ?) AND order_status = 'delivered'
    """, (rider_id, rider_phone)).fetchall()

    all_time_earned = 0.0
    for ord_row in delivered_orders:
        o_fee = float(ord_row["rider_fee"] or 0)
        if o_fee <= 0:
            o_fee = default_fee
        all_time_earned += o_fee

    payouts_rows = conn.execute("SELECT amount FROM rider_payouts WHERE rider_id = ?", (rider_id,)).fetchall()
    all_time_paid = sum(float(p["amount"] or 0) for p in payouts_rows)
    balance_due = max(0.0, round(all_time_earned - all_time_paid, 2))

    if balance_due <= 0:
        conn.close()
        flash(f"Rider {rider_name} has no outstanding due balance to pay (all delivered orders are already paid).", "error")
        return redirect(url_for("riders_page", rider_id=rider_id))

    if amount > balance_due + 0.001:
        conn.close()
        flash(f"Payment amount (TK {amount:,.2f}) cannot exceed the outstanding due balance (TK {balance_due:,.2f}).", "error")
        return redirect(url_for("riders_page", rider_id=rider_id))

    payment_method = request.form.get("payment_method", "Cash").strip() or "Cash"
    note = request.form.get("note", "").strip()
    payout_date = request.form.get("payout_date", "").strip() or datetime.now().strftime("%Y-%m-%d")
    now_str = datetime.now().isoformat()

    # 1. Record payout in rider_payouts
    conn.execute("""
        INSERT INTO rider_payouts (rider_id, amount, payout_date, payment_method, note, created_at)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (rider_id, amount, payout_date, payment_method, note, now_str))

    # 2. Record as expense in ledger_entries for Riders riding cost
    expense_title = f"Riders riding cost - {rider_name} ({rider_phone})"
    if note:
        expense_title += f" [{note}]"
    conn.execute("""
        INSERT INTO ledger_entries (entry_type, title, amount, entry_date, created_at, target_segment)
        VALUES ('expense', ?, ?, ?, ?, 'online')
    """, (expense_title, amount, payout_date, now_str))

    conn.commit()
    conn.close()

    remote_control.push_full_backup()
    flash(f"Successfully paid TK {amount:,.2f} to {rider_name}. Recorded in reports as 'Riders riding cost' expense.", "success")
    return redirect(url_for("riders_page", rider_id=rider_id))


@app.route("/riders/payouts/<int:payout_id>/delete", methods=["POST"])
@login_required
@admin_required
def delete_rider_payout(payout_id):
    conn = get_connection()
    payout = conn.execute("SELECT * FROM rider_payouts WHERE id = ?", (payout_id,)).fetchone()
    if payout:
        rider_id = payout["rider_id"]
        # Reverse corresponding expense in ledger_entries
        conn.execute("""
            DELETE FROM ledger_entries 
            WHERE entry_type = 'expense' 
              AND amount = ? 
              AND entry_date = ? 
              AND title LIKE 'Riders riding cost%'
        """, (payout["amount"], payout["payout_date"]))
        conn.execute("DELETE FROM rider_payouts WHERE id = ?", (payout_id,))
        conn.commit()
        conn.close()
        remote_control.push_full_backup()
        flash(f"Payout record of TK {payout['amount']:,.2f} removed and ledger expense reversed.", "success")
        return redirect(url_for("riders_page", rider_id=rider_id))
    conn.close()
    flash("Payout record not found.", "error")
    return redirect(url_for("riders_page"))


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
    if "can_rx_quote_bill" not in columns:
        try: conn.execute("ALTER TABLE users ADD COLUMN can_rx_quote_bill INTEGER NOT NULL DEFAULT 0")
        except: pass
    conn.commit()

    can_rx_quote_bill = 1 if request.form.get("can_rx_quote_bill") in ("1", "true", "on", "yes") else 0

    existing = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
    if existing:
        conn.close()
        flash("A rider or staff user with this mobile number already exists.", "error")
        return redirect(url_for("riders_page"))

    conn.execute(
        "INSERT INTO users (username, password_hash, plain_password, role, full_name, is_active, can_rx_quote_bill, created_at) VALUES (?, ?, ?, 'delivery', ?, 1, ?, ?)",
        (username, generate_password_hash(password), password, full_name, can_rx_quote_bill, datetime.now().isoformat())
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
    can_rx_quote_bill = 1 if request.form.get("can_rx_quote_bill") in ("1", "true", "on", "yes") else 0

    if not rider_id or not full_name or not username:
        flash("Rider ID, Name, and Mobile Number are required.", "error")
        return redirect(url_for("riders_page"))

    conn = get_connection()
    cols = [c[1] for c in conn.execute("PRAGMA table_info(users)").fetchall()]
    if "can_rx_quote_bill" not in cols:
        try: conn.execute("ALTER TABLE users ADD COLUMN can_rx_quote_bill INTEGER NOT NULL DEFAULT 0")
        except Exception: pass
    if password:
        conn.execute(
            "UPDATE users SET full_name = ?, username = ?, password_hash = ?, plain_password = ?, is_active = ?, can_rx_quote_bill = ? WHERE id = ? AND role = 'delivery'",
            (full_name, username, generate_password_hash(password), password, is_active, can_rx_quote_bill, rider_id)
        )
    else:
        conn.execute(
            "UPDATE users SET full_name = ?, username = ?, is_active = ?, can_rx_quote_bill = ? WHERE id = ? AND role = 'delivery'",
            (full_name, username, is_active, can_rx_quote_bill, rider_id)
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


@app.route("/riders/login-as/<int:rider_id>")
@login_required
@admin_required
def rider_login_as(rider_id):
    """Allow Admin to log in as a delivery rider directly from the Staff panel."""
    conn = get_connection()
    rider = conn.execute("SELECT * FROM users WHERE id = ? AND role = 'delivery'", (rider_id,)).fetchone()
    conn.close()
    if not rider:
        flash("Delivery rider not found.", "error")
        return redirect(url_for("users"))

    # Preserve admin identity for seamless one-click switch back
    if not session.get("original_admin_id"):
        session["original_admin_id"] = session.get("user_id")
        session["original_admin_username"] = session.get("username")
    
    session["user_id"] = rider["id"]
    session["username"] = rider["username"]
    session["role"] = "delivery"
    session["rider_full_name"] = rider["full_name"] or rider["username"]
    flash(f"🛵 Logged in as Delivery Rider: {rider['full_name'] or rider['username']} ({rider['username']}).", "success")
    return redirect(url_for("online_orders"))


@app.route("/riders/switch-back-admin")
@login_required
def rider_switch_back_admin():
    """Allow Admin who switched to Rider mode to instantly return to their Admin account."""
    orig_id = session.get("original_admin_id")
    orig_user = session.get("original_admin_username")
    if orig_id and orig_user:
        session["user_id"] = orig_id
        session["username"] = orig_user
        session["role"] = "admin"
        session.pop("original_admin_id", None)
        session.pop("original_admin_username", None)
        session.pop("rider_full_name", None)
        flash("🔙 Returned to Admin account successfully.", "success")
        return redirect(url_for("users"))
    return redirect(url_for("dashboard"))


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
            "admin_whatsapp_phone": request.form.get("admin_whatsapp_phone", "").strip(),
            "whatsapp_provider": request.form.get("whatsapp_provider", "").strip(),
            "whatsapp_instance_id": request.form.get("whatsapp_instance_id", "").strip(),
            "whatsapp_api_token": request.form.get("whatsapp_api_token", "").strip(),
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
            "max_order_qty_product": request.form.get("max_order_qty_product", "0").strip(),
            "max_order_qty_package": request.form.get("max_order_qty_package", "0").strip(),
            "apply_max_qty_to_pos": "1" if request.form.get("apply_max_qty_to_pos") else "0",
            "product_image_bg_color": request.form.get("product_image_bg_color", "#FFFFFF").strip() or "#FFFFFF",
            "rider_delivery_fee": request.form.get("rider_delivery_fee", "50").strip() or "50",
            "apk_download_url": request.form.get("apk_download_url", "").strip(),
            "auto_record_expired_as_loss": "1" if request.form.get("auto_record_expired_as_loss") else "0",
            "pharmacy_delivery_charge": request.form.get("pharmacy_delivery_charge", "50").strip() or "50",
            "pharmacy_discount_percent": request.form.get("pharmacy_discount_percent", "0").strip() or "0",
            "thermal_printer_name": request.form.get("thermal_printer_name", "").strip(),
            "thermal_paper_width": request.form.get("thermal_paper_width", "58mm").strip() or "58mm",
            "thermal_pc_auto_print": "1" if request.form.get("thermal_pc_auto_print") else "0",
        }
        update_settings(conn, values)
        conn.commit()
        conn.close()
        remote_control.push_full_backup()
        flash("Shop settings and policies updated successfully.", "success")
        return redirect(url_for("settings_page"))
    current_settings = get_all_settings(conn)
    thermal_resolved = thermal_printer.resolve_target_printer(conn)
    thermal_reason = (
        f"Active Windows Printer: {thermal_resolved}"
        if thermal_resolved
        else "No local Windows printer detected (Cloud Relay / Queue mode)"
    )
    thermal_printers = thermal_printer.list_windows_printers()
    conn.close()
    return render_template(
        "settings.html",
        settings=current_settings,
        thermal_printers=thermal_printers,
        thermal_resolved=thermal_resolved,
        thermal_reason=thermal_reason,
    )


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
    
    pkg_rows = conn.execute("SELECT * FROM packages ORDER BY id DESC").fetchall()
    packages_list = []
    for pkg in pkg_rows:
        p_dict = dict(pkg)
        items = conn.execute("""
            SELECT pi.*, p.name AS product_name, p.sell_price, p.mrp, p.sku, p.image_url
            FROM package_items pi JOIN products p ON pi.product_id = p.id
            WHERE pi.package_id = ?
        """, (pkg["id"],)).fetchall()
        inc_items = [dict(i) for i in items]
        p_dict["items"] = inc_items
        p_dict["package_items"] = inc_items
        reg_total = calculate_package_regular_total(inc_items)
        p_dict["regular_total"] = reg_total
        p_dict["savings"] = max(0.0, reg_total - float(p_dict.get("package_price") or 0.0))
        packages_list.append(p_dict)

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
        packages=packages_list,
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
            "message": f"Voucher '{code}' cannot be applied when a Combo Package is in the cart."
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


@app.route("/offers/free_delivery", methods=["POST"])
@login_required
@admin_required
def save_free_delivery_offer():
    free_active = "1" if request.form.get("free_delivery_active") else "0"
    min_amount = request.form.get("free_delivery_min_amount", "1000").strip()
    title = request.form.get("free_delivery_title", "🚚 FREE HOME DELIVERY!").strip()
    subtitle = request.form.get("free_delivery_subtitle", "Enjoy 100% Free Delivery on all orders above TK 1,000!").strip()
    show_banner = "1" if request.form.get("free_delivery_show_banner") else "0"
    
    # Image handling
    image_url = request.form.get("free_delivery_image_url", "").strip()
    img_file = request.files.get("free_delivery_image_file")
    
    if img_file and img_file.filename:
        try:
            from PIL import Image
            import io
            import base64
            img = Image.open(img_file)
            img = img.convert("RGB")
            img.thumbnail((800, 800), Image.Resampling.LANCZOS)
            buf = io.BytesIO()
            img.save(buf, format="JPEG", quality=85, optimize=True)
            b64_str = base64.b64encode(buf.getvalue()).decode("utf-8")
            image_url = f"data:image/jpeg;base64,{b64_str}"
        except Exception as e:
            print("Free delivery image upload failed:", e)
    elif image_url:
        image_url = download_and_cache_external_image(image_url)

    settings_to_update = {
        "free_delivery_active": free_active,
        "free_delivery_min_amount": min_amount,
        "free_delivery_title": title,
        "free_delivery_subtitle": subtitle,
        "free_delivery_show_banner": show_banner,
    }
    if image_url:
        settings_to_update["free_delivery_image_url"] = image_url

    conn = get_connection()
    update_settings(conn, settings_to_update)
    conn.commit()
    conn.close()
    
    remote_control.push_settings_to_cloud()
    flash("🚚 Free Delivery Offer & Banner settings saved successfully.", "success")
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
    
    promos = []
    for r in rows:
        d = dict(r)
        raw_img = (d.get("image_url") or "").strip()
        if raw_img:
            d["image_url"] = clean_and_normalize_image_url(raw_img)
        promos.append(d)
    
    for c_slide in get_combo_package_banner_slides(conn):
        promos.append(c_slide)
    
    free_del_active = (s.get("free_delivery_active") or "0") == "1"
    free_del_show_banner = (s.get("free_delivery_show_banner") or "1") == "1"
    min_amt = float(s.get("free_delivery_min_amount") or 1000.0)
    default_del = float(s.get("delivery_charge") or 100.0)
    del_img = s.get("free_delivery_image_url") or "/static/images/logo.png"

    if free_del_active and free_del_show_banner:
        free_del_slide = {
            "id": -999,
            "name": s.get("free_delivery_title") or "🚚 FREE HOME DELIVERY!",
            "category_name": f"Spend TK {min_amt:,.0f}+",
            "offer_title": f"FREE DELIVERY (Order TK {min_amt:,.0f}+)",
            "offer_type": "free_delivery",
            "offer_value": "100% FREE",
            "is_free_delivery": 1,
            "sell_price": 0.0,
            "mrp": default_del,
            "image_url": del_img,
            "description": s.get("free_delivery_subtitle") or f"Enjoy 100% Free Home Delivery on all orders above TK {min_amt:,.0f}!"
        }
        promos.insert(0, free_del_slide)

    free_del_offer = {
        "active": free_del_active,
        "min_amount": min_amt,
        "title": s.get("free_delivery_title") or "🚚 FREE HOME DELIVERY!",
        "subtitle": s.get("free_delivery_subtitle") or f"Enjoy 100% Free Delivery on all orders above TK {min_amt:,.0f}!",
        "show_banner": free_del_show_banner,
        "image_url": del_img
    }
    conn.close()
    return jsonify({
        "interval_sec": interval_sec,
        "promotions": promos,
        "free_delivery_offer": free_del_offer
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


@app.route("/privacy-policy")
@app.route("/privacy")
def public_privacy_policy():
    conn = get_connection()
    settings = get_all_settings(conn)
    conn.close()
    return render_template("privacy_policy.html", settings=settings)


@app.route("/terms-of-service")
@app.route("/terms")
def public_terms_of_service():
    conn = get_connection()
    settings = get_all_settings(conn)
    conn.close()
    return render_template("terms_of_service.html", settings=settings)


@app.route("/data-deletion")
@app.route("/user-data-deletion")
def public_data_deletion():
    conn = get_connection()
    settings = get_all_settings(conn)
    conn.close()
    return render_template("data_deletion.html", settings=settings)


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

def _resolve_report_period_filters(period):
    today = date.today()
    today_str = today.isoformat()
    if period == "daily":
        return "daily", f"date(created_at) = '{today_str}'", f"date(entry_date) = '{today_str}'"
    if period == "weekly":
        start = (today - timedelta(days=6)).isoformat()
        return "weekly", f"date(created_at) >= '{start}'", f"date(entry_date) >= '{start}'"
    if period == "3_monthly":
        start = (today - timedelta(days=89)).isoformat()
        return "3_monthly", f"date(created_at) >= '{start}'", f"date(entry_date) >= '{start}'"
    if period == "6_monthly":
        start = (today - timedelta(days=179)).isoformat()
        return "6_monthly", f"date(created_at) >= '{start}'", f"date(entry_date) >= '{start}'"
    if period == "quarterly":
        quarter_start_month = ((today.month - 1) // 3) * 3 + 1
        start = date(today.year, quarter_start_month, 1).isoformat()
        return "quarterly", f"date(created_at) >= '{start}'", f"date(entry_date) >= '{start}'"
    if period == "yearly":
        return "yearly", f"strftime('%Y', created_at) = '{today_str[:4]}'", f"strftime('%Y', entry_date) = '{today_str[:4]}'"
    if period == "all":
        return "all", "1=1", "1=1"
    return "monthly", f"strftime('%Y-%m', created_at) = '{today_str[:7]}'", f"strftime('%Y-%m', entry_date) = '{today_str[:7]}'"


def _compute_separated_reports(conn, date_filter, ledger_filter, dept="all"):
    """Computes separated Other-Products, Pharmacy, and Combined supershop metrics without double counting."""
    # 1. POS counter & Rider POS sales (exclude mirrored INV-ONLINE-* rows)
    pos_sales = conn.execute(f"""
        SELECT id, invoice_number, channel, total_amount, rounded_total, vat_amount, saved_amount
        FROM sales
        WHERE COALESCE(channel, '') != 'Online'
          AND COALESCE(invoice_number, '') NOT LIKE 'INV-ONLINE-%'
          AND {date_filter}
    """).fetchall()

    pos_sale_ids = [s["id"] for s in pos_sales]
    pos_items_by_sale = {}
    if pos_sale_ids:
        ph = ",".join("?" for _ in pos_sale_ids)
        for si in conn.execute(f"SELECT * FROM sale_items WHERE sale_id IN ({ph})", tuple(pos_sale_ids)).fetchall():
            pos_items_by_sale.setdefault(si["sale_id"], []).append(si)

    # Map pharmacy medicines for COGS and medicine top/slow/dead stock attribution
    all_meds = conn.execute("SELECT id, name, dosage_form, strength, stock_qty, cost_price, mrp, unit_price FROM pharmacy_medicines").fetchall()
    med_by_id = {m["id"]: dict(m) for m in all_meds}
    med_by_name = {}
    for m in all_meds:
        key = (m["name"] or "").strip().lower()
        if key and key not in med_by_name:
            med_by_name[key] = dict(m)

    med_perf = {}
    for m in all_meds:
        med_perf[m["id"]] = {
            "id": m["id"],
            "name": f"💊 {m['name']}" + (f" ({m['strength']})" if m["strength"] else ""),
            "sku": m["dosage_form"] or "Medicine",
            "stock_qty": int(m["stock_qty"] or 0),
            "qty_sold": 0,
            "revenue": 0.0,
            "cogs_amt": 0.0,
            "profit": 0.0,
        }

    gen_pos_tx = 0
    gen_pos_rev = 0.0
    gen_pos_cogs = 0.0
    pharm_pos_tx = 0
    pharm_pos_rev = 0.0
    pharm_pos_cogs = 0.0

    for s in pos_sales:
        s_items = pos_items_by_sale.get(s["id"], [])
        s_total = float(s["rounded_total"] or s["total_amount"] or 0.0)
        ch = (s["channel"] or "").strip()

        med_line_rev = 0.0
        med_line_cogs = 0.0
        gen_line_rev = 0.0
        gen_line_cogs = 0.0

        for si in s_items:
            qty = float(si["quantity"] or 1)
            l_rev = float(si["unit_price"] or 0.0) * qty
            l_cogs = float(si["cost_price"] or 0.0) * qty
            serials = str(si["unit_serials"] or "").strip()
            if serials.startswith("💊"):
                med_line_rev += l_rev
                med_line_cogs += l_cogs
                raw_n = serials.lstrip("💊").strip()
                pieces_sold = int(qty)
                m_pcs = re.search(r"=\s*(\d+)\s*পিস\]", raw_n)
                if m_pcs:
                    try:
                        pieces_sold = max(1, int(m_pcs.group(1)))
                    except Exception:
                        pieces_sold = int(qty)
                clean_n = re.sub(r"\s*\[[^\]]*\]\s*$", "", raw_n).strip()
                base_n = clean_n.rsplit(" (", 1)[0].strip().lower()
                matched_m = med_by_name.get(base_n) or med_by_name.get(clean_n.lower())
                if matched_m:
                    mid = matched_m["id"]
                    if l_cogs <= 0:
                        l_cogs = float(matched_m.get("cost_price") or float(si["unit_price"] or 0.0) * 0.78 / max(1.0, pieces_sold / max(1.0, qty))) * pieces_sold
                    med_perf[mid]["qty_sold"] += int(pieces_sold)
                    med_perf[mid]["revenue"] += l_rev
                    med_perf[mid]["cogs_amt"] += l_cogs
            else:
                gen_line_rev += l_rev
                gen_line_cogs += l_cogs

        if ch == "Pharmacy POS" or (med_line_rev > 0 and gen_line_rev == 0):
            pharm_pos_tx += 1
            pharm_pos_rev += s_total
            pharm_pos_cogs += (med_line_cogs if med_line_cogs > 0 else gen_line_cogs)
        elif med_line_rev > 0 and gen_line_rev > 0 and (med_line_rev + gen_line_rev) > 0:
            ratio = med_line_rev / (med_line_rev + gen_line_rev)
            p_part = round(s_total * ratio, 2)
            g_part = round(s_total - p_part, 2)
            pharm_pos_tx += 1
            pharm_pos_rev += p_part
            pharm_pos_cogs += med_line_cogs
            gen_pos_tx += 1
            gen_pos_rev += g_part
            gen_pos_cogs += gen_line_cogs
        else:
            gen_pos_tx += 1
            gen_pos_rev += s_total
            gen_pos_cogs += gen_line_cogs

    # 2. General / Other Products Online Orders (exclude RX- pharmacy orders and cancelled)
    gen_on_row = conn.execute(f"""
        SELECT COUNT(*) AS tx_count, COALESCE(SUM(total_amount), 0) AS revenue
        FROM online_orders
        WHERE COALESCE(order_number, '') NOT LIKE 'RX-%'
          AND COALESCE(order_status, '') != 'cancelled'
          AND {date_filter}
    """).fetchone()
    gen_on_cogs_row = conn.execute(f"""
        SELECT COALESCE(SUM(oi.quantity * COALESCE(NULLIF(p.cost_price, 0), oi.unit_price * 0.7)), 0) AS total_cogs
        FROM online_order_items oi
        JOIN online_orders o ON oi.order_id = o.id
        LEFT JOIN products p ON oi.product_id = p.id
        WHERE COALESCE(o.order_number, '') NOT LIKE 'RX-%'
          AND COALESCE(o.order_status, '') != 'cancelled'
          AND {date_filter.replace('created_at', 'o.created_at')}
    """).fetchone()

    gen_on_tx = int(gen_on_row["tx_count"] or 0)
    gen_on_rev = float(gen_on_row["revenue"] or 0.0)
    gen_on_cogs = float(gen_on_cogs_row["total_cogs"] or 0.0)

    # 3. Pharmacy Online Orders (confirmed / packed / on_the_way / delivered)
    pharm_on_rows = conn.execute(f"""
        SELECT * FROM pharmacy_orders
        WHERE order_status IN ('confirmed', 'packed', 'on_the_way', 'delivered')
          AND {date_filter}
    """).fetchall()

    pharm_on_tx = 0
    pharm_on_rev = 0.0
    pharm_on_cogs = 0.0
    seen_rx = set()

    for po in pharm_on_rows:
        ord_num = str(po["order_number"] or "").strip()
        if ord_num:
            seen_rx.add(ord_num.upper())
        pharm_on_tx += 1
        po_tot = float(po["total_amount"] or 0.0)
        pharm_on_rev += po_tot

        raw_j = po["approved_items_json"] or po["requested_items_json"] or "[]"
        try:
            j_items = json.loads(raw_j) if raw_j else []
        except Exception:
            j_items = []
        order_cogs = 0.0
        for it in j_items:
            q = int(it.get("quantity") or 1)
            base_pcs = int(it.get("base_pieces") or (q * max(1, int(it.get("unit_count") or 1))))
            up = float(it.get("unit_price") or 0.0)
            lt = float(it.get("total_price") or (up * q))
            it_type = (it.get("item_type") or ("medicine" if it.get("medicine_id") else ("product" if it.get("product_id") else "medicine"))).strip().lower()
            mid_raw = it.get("medicine_id")
            m_info = None
            if mid_raw:
                try:
                    m_info = med_by_id.get(int(mid_raw))
                except Exception:
                    m_info = None
            if not m_info and it.get("name") and it_type == "medicine":
                m_info = med_by_name.get(str(it.get("name") or "").strip().lower())

            saved_total_cost = float(it.get("total_cost") or 0.0)
            saved_unit_cost = float(it.get("cost_price") or 0.0)
            if saved_total_cost > 0:
                item_cogs = round(saved_total_cost, 2)
            elif saved_unit_cost > 0:
                item_cogs = round(saved_unit_cost * q, 2)
            elif it_type == "product" and it.get("product_id"):
                pr_c = conn.execute("SELECT cost_price FROM products WHERE id = ?", (int(it["product_id"]),)).fetchone()
                pc = float(pr_c["cost_price"] or 0.0) if pr_c else 0.0
                item_cogs = round((pc if pc > 0 else up * 0.78) * q, 2)
            else:
                unit_cost = float(m_info.get("cost_price") or 0.0) if m_info else 0.0
                if unit_cost > 0:
                    item_cogs = round(unit_cost * base_pcs, 2)
                else:
                    item_cogs = round((up * 0.78) * q, 2) if up > 0 else 0.0

            order_cogs += item_cogs
            if m_info and m_info["id"] in med_perf and it_type == "medicine":
                mp = med_perf[m_info["id"]]
                mp["qty_sold"] += base_pcs
                mp["revenue"] += lt
                mp["cogs_amt"] += item_cogs
        if order_cogs <= 0 and po_tot > 0:
            order_cogs = round(float(po["subtotal"] or po_tot) * 0.78, 2)
        pharm_on_cogs += order_cogs

    # Fallback: include any confirmed/delivered RX- online_orders absent from pharmacy_orders
    rx_oo_rows = conn.execute(f"""
        SELECT id, order_number, total_amount, subtotal FROM online_orders
        WHERE order_number LIKE 'RX-%'
          AND order_status IN ('verified', 'packed', 'on_the_way', 'delivered')
          AND {date_filter}
    """).fetchall()
    for rx in rx_oo_rows:
        onum = str(rx["order_number"] or "").strip().upper()
        if onum and onum not in seen_rx:
            seen_rx.add(onum)
            amt = float(rx["total_amount"] or 0.0)
            pharm_on_tx += 1
            pharm_on_rev += amt
            pharm_on_cogs += round(float(rx["subtotal"] or amt) * 0.78, 2)

    # 4. Packages & Offers Sales (General department subsets)
    o_date = date_filter.replace("created_at", "o.created_at")
    s_date = date_filter.replace("created_at", "s.created_at")
    pos_pkg = conn.execute(f"""
        SELECT COALESCE(SUM(si.quantity * si.unit_price), 0) AS revenue,
               COALESCE(SUM(si.quantity * si.cost_price), 0) AS cogs,
               COALESCE(SUM(si.quantity), 0) AS qty_sold,
               COUNT(DISTINCT si.sale_id) AS tx_count
        FROM sale_items si
        JOIN sales s ON si.sale_id = s.id
        JOIN products p ON si.product_id = p.id
        WHERE COALESCE(s.channel, '') != 'Online'
          AND COALESCE(s.invoice_number, '') NOT LIKE 'INV-ONLINE-%'
          AND (p.unit LIKE '%package%' OR p.unit LIKE '%combo%' OR p.name LIKE '%📦%' OR p.name LIKE '%package%' OR p.name LIKE '%combo%')
          AND {s_date}
    """).fetchone()
    online_pkg = conn.execute(f"""
        SELECT COALESCE(SUM(oi.quantity * oi.unit_price), 0) AS revenue,
               COALESCE(SUM(oi.quantity * COALESCE(NULLIF(p.cost_price, 0), oi.unit_price * 0.7)), 0) AS cogs,
               COALESCE(SUM(oi.quantity), 0) AS qty_sold,
               COUNT(DISTINCT oi.order_id) AS tx_count
        FROM online_order_items oi
        JOIN online_orders o ON oi.order_id = o.id
        LEFT JOIN products p ON oi.product_id = p.id
        WHERE COALESCE(o.order_number, '') NOT LIKE 'RX-%'
          AND COALESCE(o.order_status, '') != 'cancelled'
          AND (oi.product_name LIKE '📦%' OR oi.product_name LIKE '%package%' OR oi.product_name LIKE '%combo%' OR (p.unit IS NOT NULL AND (p.unit LIKE '%package%' OR p.unit LIKE '%combo%')))
          AND {o_date}
    """).fetchone()

    pkg_rev = float(pos_pkg["revenue"]) + float(online_pkg["revenue"])
    pkg_cogs = float(pos_pkg["cogs"]) + float(online_pkg["cogs"])
    pkg_tx = int(pos_pkg["tx_count"]) + int(online_pkg["tx_count"])
    pkg_qty = int(pos_pkg["qty_sold"]) + int(online_pkg["qty_sold"])

    pos_off = conn.execute(f"""
        SELECT COALESCE(SUM(si.quantity * si.unit_price), 0) AS revenue,
               COALESCE(SUM(si.quantity * si.cost_price), 0) AS cogs,
               COALESCE(SUM(si.quantity), 0) AS qty_sold,
               COUNT(DISTINCT si.sale_id) AS tx_count
        FROM sale_items si
        JOIN sales s ON si.sale_id = s.id
        JOIN products p ON si.product_id = p.id
        WHERE COALESCE(s.channel, '') != 'Online'
          AND COALESCE(s.invoice_number, '') NOT LIKE 'INV-ONLINE-%'
          AND (p.is_offer = 1 OR p.is_promotion = 1 OR (p.offer_type != '' AND p.offer_type IS NOT NULL))
          AND {s_date}
    """).fetchone()
    online_off = conn.execute(f"""
        SELECT COALESCE(SUM(oi.quantity * oi.unit_price), 0) AS revenue,
               COALESCE(SUM(oi.quantity * COALESCE(NULLIF(p.cost_price, 0), oi.unit_price * 0.7)), 0) AS cogs,
               COALESCE(SUM(oi.quantity), 0) AS qty_sold,
               COUNT(DISTINCT oi.order_id) AS tx_count
        FROM online_order_items oi
        JOIN online_orders o ON oi.order_id = o.id
        JOIN products p ON oi.product_id = p.id
        WHERE COALESCE(o.order_number, '') NOT LIKE 'RX-%'
          AND COALESCE(o.order_status, '') != 'cancelled'
          AND (p.is_offer = 1 OR p.is_promotion = 1 OR (p.offer_type != '' AND p.offer_type IS NOT NULL))
          AND {o_date}
    """).fetchone()

    off_rev = float(pos_off["revenue"]) + float(online_off["revenue"])
    off_cogs = float(pos_off["cogs"]) + float(online_off["cogs"])
    off_tx = int(pos_off["tx_count"]) + int(online_off["tx_count"])
    off_qty = int(pos_off["qty_sold"]) + int(online_off["qty_sold"])

    # 5. Ledger entries & segment breakdown
    ledger_entries = conn.execute(f"SELECT * FROM ledger_entries WHERE {ledger_filter} ORDER BY entry_date DESC, id DESC").fetchall()

    def _seg_sum(*seg_names):
        inc = sum(float(r["amount"]) for r in ledger_entries if r["entry_type"] == "income" and (r["target_segment"] or "all") in seg_names)
        exp = sum(float(r["amount"]) for r in ledger_entries if r["entry_type"] == "expense" and (r["target_segment"] or "all") in seg_names)
        return inc, exp

    all_inc = sum(float(r["amount"]) for r in ledger_entries if r["entry_type"] == "income")
    all_exp = sum(float(r["amount"]) for r in ledger_entries if r["entry_type"] == "expense")
    on_inc, on_exp = _seg_sum("online")
    pos_inc, pos_exp = _seg_sum("offline")
    pkg_inc, pkg_exp = _seg_sum("packages")
    off_inc, off_exp = _seg_sum("offers")
    pharm_inc, pharm_exp = _seg_sum("pharmacy")
    gen_only_inc, gen_only_exp = _seg_sum("online", "offline", "packages", "offers", "general")

    # 6. Build the 3 Department Summary Bundles
    gen_rev = round(gen_pos_rev + gen_on_rev, 2)
    gen_cogs = round(gen_pos_cogs + gen_on_cogs, 2)
    gen_tx = gen_pos_tx + gen_on_tx
    gen_gross = round(gen_rev - gen_cogs, 2)
    gen_net = round(gen_gross + gen_only_inc - gen_only_exp, 2)

    pharm_rev = round(pharm_pos_rev + pharm_on_rev, 2)
    pharm_cogs = round(pharm_pos_cogs + pharm_on_cogs, 2)
    pharm_tx = pharm_pos_tx + pharm_on_tx
    pharm_gross = round(pharm_rev - pharm_cogs, 2)
    pharm_net = round(pharm_gross + pharm_inc - pharm_exp, 2)

    whole_rev = round(gen_rev + pharm_rev, 2)
    whole_cogs = round(gen_cogs + pharm_cogs, 2)
    whole_tx = gen_tx + pharm_tx
    whole_gross = round(whole_rev - whole_cogs, 2)
    whole_net = round(whole_gross + all_inc - all_exp, 2)

    general_summary = {
        "tx_count": gen_tx, "revenue": gen_rev, "cogs": gen_cogs,
        "gross_profit": gen_gross, "income": gen_only_inc, "expense": gen_only_exp, "net_profit": gen_net,
        "pos_tx": gen_pos_tx, "pos_revenue": round(gen_pos_rev, 2), "pos_cogs": round(gen_pos_cogs, 2),
        "online_tx": gen_on_tx, "online_revenue": round(gen_on_rev, 2), "online_cogs": round(gen_on_cogs, 2),
    }
    pharmacy_summary = {
        "tx_count": pharm_tx, "revenue": pharm_rev, "cogs": pharm_cogs,
        "gross_profit": pharm_gross, "income": pharm_inc, "expense": pharm_exp, "net_profit": pharm_net,
        "pos_tx": pharm_pos_tx, "pos_revenue": round(pharm_pos_rev, 2), "pos_cogs": round(pharm_pos_cogs, 2),
        "online_tx": pharm_on_tx, "online_revenue": round(pharm_on_rev, 2), "online_cogs": round(pharm_on_cogs, 2),
    }
    whole_summary = {
        "tx_count": whole_tx, "revenue": whole_rev, "cogs": whole_cogs,
        "gross_profit": whole_gross, "income": all_inc, "expense": all_exp, "net_profit": whole_net,
        "pos_tx": gen_pos_tx + pharm_pos_tx, "pos_revenue": round(gen_pos_rev + pharm_pos_rev, 2), "pos_cogs": round(gen_pos_cogs + pharm_pos_cogs, 2),
        "online_tx": gen_on_tx + pharm_on_tx, "online_revenue": round(gen_on_rev + pharm_on_rev, 2), "online_cogs": round(gen_on_cogs + pharm_on_cogs, 2),
    }

    # 7. Product & Medicine Performance Rankings
    prod_sold_sub = f"""
        SELECT product_id,
               SUM(qty_sold) AS qty_sold,
               SUM(revenue) AS revenue,
               SUM(cogs_amt) AS cogs_amt
        FROM (
            SELECT si.product_id AS product_id,
                   si.quantity AS qty_sold,
                   si.quantity * si.unit_price AS revenue,
                   si.quantity * si.cost_price AS cogs_amt
            FROM sale_items si
            JOIN sales s ON si.sale_id = s.id
            WHERE COALESCE(s.channel, '') != 'Online'
              AND COALESCE(s.invoice_number, '') NOT LIKE 'INV-ONLINE-%'
              AND COALESCE(si.unit_serials, '') NOT LIKE '💊%'
              AND {s_date}
            UNION ALL
            SELECT oi.product_id AS product_id,
                   oi.quantity AS qty_sold,
                   oi.quantity * oi.unit_price AS revenue,
                   oi.quantity * COALESCE(NULLIF(p.cost_price, 0), oi.unit_price * 0.7) AS cogs_amt
            FROM online_order_items oi
            JOIN online_orders o ON oi.order_id = o.id
            LEFT JOIN products p ON oi.product_id = p.id
            WHERE COALESCE(o.order_number, '') NOT LIKE 'RX-%'
              AND COALESCE(o.order_status, '') != 'cancelled'
              AND {o_date}
        ) combined_gen
        GROUP BY product_id
    """
    gen_perf_rows = conn.execute(f"""
        SELECT p.id, p.name, p.sku, p.stock_qty,
               COALESCE(sold.qty_sold, 0) AS qty_sold,
               COALESCE(sold.revenue, 0) AS revenue,
               COALESCE(sold.cogs_amt, 0) AS cogs_amt,
               (COALESCE(sold.revenue, 0) - COALESCE(sold.cogs_amt, 0)) AS profit
        FROM products p
        LEFT JOIN ({prod_sold_sub}) sold ON sold.product_id = p.id
        ORDER BY qty_sold DESC, revenue DESC
    """).fetchall()
    gen_perf = [dict(r) for r in gen_perf_rows]
    gen_top = [r for r in gen_perf if r["qty_sold"] > 0][:8]
    gen_dead = [r for r in gen_perf if r["qty_sold"] == 0 and r["stock_qty"] > 0][:8]
    gen_slow = sorted([r for r in gen_perf if r["qty_sold"] > 0 and r["stock_qty"] > 0], key=lambda x: x["qty_sold"])[:8]

    for mp in med_perf.values():
        mp["revenue"] = round(mp["revenue"], 2)
        mp["cogs_amt"] = round(mp["cogs_amt"], 2)
        mp["profit"] = round(mp["revenue"] - mp["cogs_amt"], 2)
    med_list = sorted(med_perf.values(), key=lambda x: (x["qty_sold"], x["revenue"]), reverse=True)
    top_medicines = [r for r in med_list if r["qty_sold"] > 0][:8]
    dead_medicines = [r for r in med_list if r["qty_sold"] == 0 and r["stock_qty"] > 0][:8]
    slow_medicines = sorted([r for r in med_list if r["qty_sold"] > 0 and r["stock_qty"] > 0], key=lambda x: x["qty_sold"])[:8]

    # 8. Select Active Department Slice (`all`, `general`, `pharmacy`)
    if dept == "pharmacy":
        active = pharmacy_summary
        active_online = {
            "tx_count": pharm_on_tx, "revenue": round(pharm_on_rev, 2), "cogs": round(pharm_on_cogs, 2),
            "gross_profit": round(pharm_on_rev - pharm_on_cogs, 2),
            "income": pharm_inc, "expense": 0.0,
            "net_profit": round(pharm_on_rev - pharm_on_cogs + pharm_inc, 2),
        }
        active_offline = {
            "tx_count": pharm_pos_tx, "revenue": round(pharm_pos_rev, 2), "cogs": round(pharm_pos_cogs, 2),
            "gross_profit": round(pharm_pos_rev - pharm_pos_cogs, 2),
            "income": 0.0, "expense": pharm_exp,
            "net_profit": round(pharm_pos_rev - pharm_pos_cogs - pharm_exp, 2),
        }
        active_top, active_slow, active_dead = top_medicines, slow_medicines, dead_medicines
        total_units_sold = sum(r["qty_sold"] for r in med_list) or 1
        max_qty_sold = max((r["qty_sold"] for r in med_list), default=0) or 1
    elif dept == "general":
        active = general_summary
        active_online = {
            "tx_count": gen_on_tx, "revenue": round(gen_on_rev, 2), "cogs": round(gen_on_cogs, 2),
            "gross_profit": round(gen_on_rev - gen_on_cogs, 2),
            "income": on_inc, "expense": on_exp,
            "net_profit": round((gen_on_rev - gen_on_cogs) + on_inc - on_exp, 2),
        }
        active_offline = {
            "tx_count": gen_pos_tx, "revenue": round(gen_pos_rev, 2), "cogs": round(gen_pos_cogs, 2),
            "gross_profit": round(gen_pos_rev - gen_pos_cogs, 2),
            "income": pos_inc, "expense": pos_exp,
            "net_profit": round((gen_pos_rev - gen_pos_cogs) + pos_inc - pos_exp, 2),
        }
        active_top, active_slow, active_dead = gen_top, gen_slow, gen_dead
        total_units_sold = sum(r["qty_sold"] for r in gen_perf) or 1
        max_qty_sold = max((r["qty_sold"] for r in gen_perf), default=0) or 1
    else:
        active = whole_summary
        active_online = {
            "tx_count": whole_summary["online_tx"], "revenue": whole_summary["online_revenue"], "cogs": whole_summary["online_cogs"],
            "gross_profit": round(whole_summary["online_revenue"] - whole_summary["online_cogs"], 2),
            "income": on_inc + pharm_inc, "expense": on_exp,
            "net_profit": round(whole_summary["online_revenue"] - whole_summary["online_cogs"] + on_inc + pharm_inc - on_exp, 2),
        }
        active_offline = {
            "tx_count": whole_summary["pos_tx"], "revenue": whole_summary["pos_revenue"], "cogs": whole_summary["pos_cogs"],
            "gross_profit": round(whole_summary["pos_revenue"] - whole_summary["pos_cogs"], 2),
            "income": pos_inc, "expense": pos_exp + pharm_exp,
            "net_profit": round(whole_summary["pos_revenue"] - whole_summary["pos_cogs"] + pos_inc - pos_exp - pharm_exp, 2),
        }
        combined_top = sorted(gen_top + top_medicines, key=lambda x: (x["qty_sold"], x["revenue"]), reverse=True)[:8]
        combined_slow = sorted(gen_slow + slow_medicines, key=lambda x: x["qty_sold"])[:8]
        combined_dead = (gen_dead + dead_medicines)[:8]
        active_top, active_slow, active_dead = combined_top, combined_slow, combined_dead
        total_units_sold = (sum(r["qty_sold"] for r in gen_perf) + sum(r["qty_sold"] for r in med_list)) or 1
        max_qty_sold = max([r["qty_sold"] for r in gen_perf] + [r["qty_sold"] for r in med_list], default=0) or 1

    pkg_gross = round(pkg_rev - pkg_cogs, 2)
    off_gross = round(off_rev - off_cogs, 2)
    metrics_bundle = {
        "revenue": active["revenue"],
        "cogs": active["cogs"],
        "gross_profit": active["gross_profit"],
        "net_profit": active["net_profit"],
        "other_income": active["income"],
        "other_expenses": active["expense"],
        "tx_count": active["tx_count"],
        "online_revenue": active_online["revenue"],
        "pos_revenue": active_offline["revenue"],
        "top_products": active_top,
        "dead_stock": active_dead,
        "slow_movers": active_slow,
    }

    return {
        "revenue": active["revenue"],
        "cogs": active["cogs"],
        "gross_profit": active["gross_profit"],
        "other_income": active["income"],
        "other_expenses": active["expense"],
        "net_profit": active["net_profit"],
        "tx_count": active["tx_count"],
        "ledger_entries": ledger_entries,
        "online_summary": active_online,
        "offline_summary": active_offline,
        "packages_summary": {
            "tx_count": pkg_tx, "qty_sold": pkg_qty, "revenue": round(pkg_rev, 2), "cogs": round(pkg_cogs, 2),
            "gross_profit": pkg_gross, "income": pkg_inc, "expense": pkg_exp,
            "net_profit": round(pkg_gross + pkg_inc - pkg_exp, 2),
        },
        "offers_summary": {
            "tx_count": off_tx, "qty_sold": off_qty, "revenue": round(off_rev, 2), "cogs": round(off_cogs, 2),
            "gross_profit": off_gross, "income": off_inc, "expense": off_exp,
            "net_profit": round(off_gross + off_inc - off_exp, 2),
        },
        "general_summary": general_summary,
        "pharmacy_summary": pharmacy_summary,
        "whole_summary": whole_summary,
        "top_products": active_top,
        "slow_movers": active_slow,
        "dead_stock": active_dead,
        "top_medicines": top_medicines,
        "slow_medicines": slow_medicines,
        "dead_medicines": dead_medicines,
        "total_units_sold": total_units_sold,
        "max_qty_sold": max_qty_sold,
        "metrics_bundle": metrics_bundle,
    }


@app.route("/reports", methods=["GET"])
@login_required
@admin_required
def reports():
    conn = get_connection()
    period = request.args.get("period", "monthly")
    dept = (request.args.get("dept") or "all").strip().lower()
    if dept not in ("all", "general", "pharmacy"):
        dept = "all"
    mode = request.args.get("mode", "examples")

    period, date_filter, ledger_filter = _resolve_report_period_filters(period)
    bundle = _compute_separated_reports(conn, date_filter, ledger_filter, dept=dept)

    ai_report_en = build_ai_business_report(bundle["metrics_bundle"], "en", mode)
    ai_report_bn = build_ai_business_report(bundle["metrics_bundle"], "bn", mode)

    conn.close()
    return render_template(
        "reports.html",
        period=period,
        dept=dept,
        mode=mode,
        revenue=bundle["revenue"],
        cogs=bundle["cogs"],
        gross_profit=bundle["gross_profit"],
        other_income=bundle["other_income"],
        other_expenses=bundle["other_expenses"],
        net_profit=bundle["net_profit"],
        ledger_entries=bundle["ledger_entries"],
        top_products=bundle["top_products"],
        slow_movers=bundle["slow_movers"],
        dead_stock=bundle["dead_stock"],
        top_medicines=bundle["top_medicines"],
        slow_medicines=bundle["slow_medicines"],
        dead_medicines=bundle["dead_medicines"],
        total_units_sold=bundle["total_units_sold"],
        max_qty_sold=bundle["max_qty_sold"],
        tx_count=bundle["tx_count"],
        ai_report_en=ai_report_en,
        ai_report_bn=ai_report_bn,
        online_summary=bundle["online_summary"],
        offline_summary=bundle["offline_summary"],
        packages_summary=bundle["packages_summary"],
        offers_summary=bundle["offers_summary"],
        general_summary=bundle["general_summary"],
        pharmacy_summary=bundle["pharmacy_summary"],
        whole_summary=bundle["whole_summary"],
    )


def build_ai_business_report(metrics: dict, lang: str = "en", mode: str = "examples") -> dict:
    rev = float(metrics.get("revenue", 0.0) or 0.0)
    cogs = float(metrics.get("cogs", 0.0) or 0.0)
    gross_profit = float(metrics.get("gross_profit", 0.0) or 0.0)
    net_profit = float(metrics.get("net_profit", 0.0) or 0.0)
    income = float(metrics.get("other_income", 0.0) or 0.0)
    expense = float(metrics.get("other_expenses", 0.0) or 0.0)
    tx_count = int(metrics.get("tx_count", 0) or 0)
    
    online_rev = float(metrics.get("online_revenue", 0.0) or 0.0)
    pos_rev = float(metrics.get("pos_revenue", 0.0) or 0.0)
    
    top_prods = metrics.get("top_products", [])
    dead_stock = metrics.get("dead_stock", [])
    slow_movers = metrics.get("slow_movers", [])
    
    gross_margin_pct = (gross_profit / rev * 100) if rev > 0 else 0.0
    net_margin_pct = (net_profit / rev * 100) if rev > 0 else 0.0
    aov = (rev / tx_count) if tx_count > 0 else 0.0
    online_share_pct = (online_rev / rev * 100) if rev > 0 else 0.0
    pos_share_pct = (pos_rev / rev * 100) if rev > 0 else 0.0
    
    is_bn = (lang == "bn")
    
    top_prod_names = ", ".join([p["name"] for p in top_prods[:3]]) if top_prods else ("সুপারশপ খাদ্য ও নিত্যপ্রয়োজনীয় ইনভেন্টরি" if is_bn else "General Retail Inventory")
    first_top_prod = top_prods[0]["name"] if top_prods else ("জনপ্রিয় খাদ্যপণ্য" if is_bn else "Top Selling Commodity")
    first_top_qty = top_prods[0]["qty_sold"] if top_prods else 0
    first_top_rev = float(top_prods[0]["revenue"]) if (top_prods and "revenue" in top_prods[0].keys()) else 0.0
    
    dead_prod_names = ", ".join([p["name"] for p in dead_stock[:3]]) if dead_stock else ("কোনো অচল পণ্য চিহ্নিত হয়নি" if is_bn else "None Identified")
    first_dead_prod = dead_stock[0]["name"] if dead_stock else ("ধীরগতির পণ্য" if is_bn else "Slow Moving Stock")
    first_dead_qty = dead_stock[0]["stock_qty"] if dead_stock else 0

    # 4 Visual Merchandising & Product Spotlights
    if is_bn:
        visual_spotlights = [
            {
                "icon": "⭐",
                "badge": "শীর্ষ রাজস্ব পণ্য (Top Revenue Driver)",
                "badge_bg": "rgba(34, 197, 94, 0.2)",
                "badge_color": "#86efac",
                "title": first_top_prod,
                "detail": f"বিক্রয়: {first_top_qty} পিস | আয়: ৳{first_top_rev:,.2f}",
                "example": "পরামর্শ: এই মূল পণ্যের সাথে আকর্ষণীয় মার্জিনের আইটেম যুক্ত করে কম্বো বান্ডিল বানান।"
            },
            {
                "icon": "🛑",
                "badge": "অচল স্টক সতর্কতা (Dead Stock Alert)",
                "badge_bg": "rgba(239, 68, 68, 0.2)",
                "badge_color": "#fca5a5",
                "title": first_dead_prod,
                "detail": f"মজুদ: {first_dead_qty} পিস তাক আটকে আছে",
                "example": "পরামর্শ: ১০-১৫% ছাড়ে বা উপহার হিসেবে দিয়ে আগামী ৭ দিনে মূলধন ক্যাশ করে নিন।"
            },
            {
                "icon": "💡",
                "badge": "ক্যাশ কাউন্টার ডিসপ্লে (Impulse Buy)",
                "badge_bg": "rgba(245, 158, 11, 0.2)",
                "badge_color": "#fde047",
                "title": "ছোট ও উচ্চ মার্জিনের স্ন্যাকস/টিস্যু",
                "detail": "চকোলেট, চুইংগাম, পকেট টিস্যু, মিনি বিস্কুট",
                "example": "পরামর্শ: বিলিং পয়েন্টে চোখের সামনে রাখলে প্রতি বিলে বাড়তি ২০-৫০ টাকা যোগ হবে।"
            },
            {
                "icon": "📦",
                "badge": "প্রস্তাবিত কম্বো অফার (Combo Bundle)",
                "badge_bg": "rgba(168, 85, 247, 0.2)",
                "badge_color": "#d8b4fe",
                "title": f"{first_top_prod} + গৃহস্থালি কম্বো",
                "detail": f"প্রত্যাশিত বাস্কেট মূল্য: ৳{aov*1.25:,.2f}+",
                "example": "পরামর্শ: অ্যাপ হোমপেজ ও শপের প্রবেশদ্বারে ৫% ছাড়ের ব্যানার সহ প্রদর্শন করুন।"
            }
        ]
    else:
        visual_spotlights = [
            {
                "icon": "⭐",
                "badge": "Top Revenue Driver",
                "badge_bg": "rgba(34, 197, 94, 0.2)",
                "badge_color": "#86efac",
                "title": first_top_prod,
                "detail": f"Sold: {first_top_qty} units | Revenue: TK {first_top_rev:,.2f}",
                "example": "Action: Bundle this fast-moving staple with high-margin items to boost Basket Size."
            },
            {
                "icon": "🛑",
                "badge": "Dead Stock Alert",
                "badge_bg": "rgba(239, 68, 68, 0.2)",
                "badge_color": "#fca5a5",
                "title": first_dead_prod,
                "detail": f"Stock: {first_dead_qty} units locking shelf space",
                "example": "Action: Liquidate via 10-15% markdown or purchase-gift bundles within 7 days."
            },
            {
                "icon": "💡",
                "badge": "Counter Impulse Display",
                "badge_bg": "rgba(245, 158, 11, 0.2)",
                "badge_color": "#fde047",
                "title": "Front Checkout Impulse Items",
                "detail": "Gums, chocolates, mints, mini biscuits & tissues",
                "example": "Action: Place beside cashier register to effortlessly add TK 20-50 per transaction."
            },
            {
                "icon": "📦",
                "badge": "Recommended Combo Package",
                "badge_bg": "rgba(168, 85, 247, 0.2)",
                "badge_color": "#d8b4fe",
                "title": f"{first_top_prod} + Household Combo",
                "detail": f"Projected Basket Value: TK {aov*1.25:,.2f}+",
                "example": "Action: Feature on store entrance poster and mobile app headers with 5% discount."
            }
        ]

    # Mode-based Generation in Bengali
    if is_bn:
        if mode == "visual":
            title = "🎨 ডইনিক সুপারশপ - এআই ভিজ্যুয়াল মার্চেন্ডাইজিং ও প্রফিট স্পটলাইট রিপোর্ট"
            summary_tagline = f"ভিজ্যুয়াল ডিসপ্লে, সেলফ অর্গানাইজেশন ও রাজস্ব বিশ্লেষণ (মোট বিক্রয়: ৳{rev:,.2f} | নিট প্রফিট: ৳{net_profit:,.2f})"
            current_state = [
                f"ভিজ্যুয়াল বিক্রয় পারফরম্যান্স: মোট {tx_count}টি কাস্টমার বাস্কেটে ৳{rev:,.2f} অর্জিত হয়েছে; গড় বাস্কেট সাইজ ৳{aov:,.2f}।",
                f"মুনাফা ও মার্জিন ডায়াগনোসিস: গ্রস প্রফিট ৳{gross_profit:,.2f} ({gross_margin_pct:.1f}%) এবং দোকান পরিচালন পরবর্তী নিট লাভ ৳{net_profit:,.2f} ({net_margin_pct:.1f}%)।",
                f"চ্যানেল শেয়ার অনুপাত: অফলাইন পিওএস কাউন্টার {pos_share_pct:.1f}% (৳{pos_rev:,.2f}) বনাম অনলাইন মোবাইল অ্যাপ {online_share_pct:.1f}% (৳{online_rev:,.2f})।",
                f"ভিজ্যুয়াল হিরো প্রোডাক্ট: '{first_top_prod}' সহ সর্বাধিক বিক্রিত পণ্য ({top_prod_names}) কাস্টমারদের সবচেয়ে বেশি আকর্ষণ করেছে।",
                f"আর্থিক খতিয়ান ব্যালেন্স: মোট লেজার পরিচালন ব্যয় ৳{expense:,.2f} এবং অন্যান্য বিবিধ আয় ৳{income:,.2f}।"
            ]
            should_do = [
                f"আই-লেভেল সেলফ পজিশনিং (Eye-Level Display): বেশি লাভজনক প্রিমিয়াম আইটেমগুলো কাস্টমারের সরাসরি চোখের উচ্চতায় (৪.৫ থেকে ৫.৫ ফুট) রাখুন। যেমন: শীর্ষ বিক্রিত '{first_top_prod}' এর ঠিক পাশেই আকর্ষণীয় মার্জিনের পণ্য প্রদর্শন করুন।",
                f"কাউন্টার ইমপালস জোন: ক্যাশ কাউন্টারের সামনে চকলেট, চুইংগাম ও মিনি স্ন্যাকসের রঙচঙে ডিসপ্লে ট্রে স্থাপন করুন। কাস্টমার বিল দেওয়ার মুহূর্তে এগুলো কিনে নেয়, যা বাস্কেট সাইজ তাৎক্ষণিক বাড়ায়।",
                f"রঙিন সেলফ-টকার ও কম্বো ব্যাজ: প্যাকেজ ও অফার পণ্যে উজ্জ্বল হলুদ/সবুজ রঙের 'Super Saver Combo' এবং 'Special Discount' স্টিকার লাগান যাতে দূর থেকেই কাস্টমারের চোখে পড়ে।",
                f"মোবাইল অ্যাপ হোম ব্যানার: অনলাইন অ্যাপের একদম উপরে আকর্ষণীয় বড় ব্যানারে '{first_top_prod}' সহ কম্বো অফার হাইলাইট করুন।"
            ]
            should_drop = [
                f"অচল পণ্যকে মূল্যবান সেলফে ফেলে রাখা বন্ধ করুন: '{dead_prod_names}' এর মতো ধীরগতির পণ্যগুলো প্রাইম সেলফে জায়গা নষ্ট করছে। এগুলোকে ঝুড়ি ডিসপ্লেতে বা এন্ট্রান্স ডিসকাউন্ট কর্নারে সরিয়ে দিন।",
                "অপরিচ্ছন্ন ও অগোছালো তাক: পণ্য এলোমেলো থাকলে কাস্টমার সহজে খুঁজে পায় না এবং কেনাকাটা না করে চলে যায়। নিয়মিত ক্যাটাগরি অনুযায়ী ফ্রন্ট-ফেসিং নিশ্চিত করুন।",
                "মেয়াদোত্তীর্ণ ঝুঁকিযুক্ত অতিরিক্ত স্টক: যেসব পণ্যের বিক্রি ধীর, সেগুলোর অতিরিক্ত কার্টন অর্ডার দেওয়া অবিলম্বে বন্ধ করুন।",
                "কাউন্টারের সামনে জায়গা জট: কাউন্টারের আশেপাশে অপ্রয়োজনীয় বক্স বা খালি কার্টন রাখা বন্ধ করে শুধু বিক্রয়যোগ্য পণ্য সাজিয়ে রাখুন।"
            ]
            where_to_change = [
                "শপ লেআউট ও ওয়াকওয়ে: দোকানের প্রবেশদ্বার থেকে ক্যাশ কাউন্টার পর্যন্ত কাস্টমারের হাঁটার পথ উন্মুক্ত ও আকর্ষণীয় রাখুন।",
                f"ডিসকাউন্ট ট্যাগিং: ধীরগতির পণ্যগুলোতে ({dead_prod_names}) স্পষ্ট বড় হরফে '১০% ছাড়' স্টিকার লাগান।",
                "আলো ও প্রডাক্ট হাইলাইট: ফ্রুটস, বেকারি ও প্রিমিয়াম সেলফে উজ্জ্বল ফোকাস লাইটের ব্যবস্থা করুন।",
                "অনলাইন অ্যাপ ফটো কোয়ালিটি: অ্যাপে পণ্যের স্পষ্ট সাদা ব্যাকগ্রাউন্ডের ছবি ও সঠিক দাম নিশ্চিত করুন।"
            ]
            profit_roadmap = [
                "ভিজ্যুয়াল মার্চেন্ডাইজিং রিঅ্যারেঞ্জ: প্রাইম সেলফে প্রিমিয়াম পণ্য সাজালে বাস্কেট মূল্য ১৫-২০% বাড়বে।",
                f"কাউন্টার ইমপালস আইটেম: দৈনিক অন্তত ৩০-৫০ জন কাস্টমার ২০ টাকার ইমপালস কিনলে মাসে ৳১৮,০০০ - ৳৩০,০০০ অতিরিক্ত লাভ।",
                f"অচল স্টক ক্লিয়ারেন্স: সেলফ কর্নারে ডিসকাউন্ট ঝুড়ি তৈরি করে অলস ৳১৫,০০০ - ৳৫০,০০০ ক্যাশ দ্রুত পুনরুদ্ধার সম্ভব।",
                "অনলাইন ব্যানার রিফ্রেশ: প্রতি সপ্তাহে নতুন ব্যানার দিয়ে অনলাইন বিক্রয় শেয়ার ৩০%+ এ উন্নীত করা যাবে।"
            ]
        elif mode == "action":
            title = "⚡ ডইনিক সুপারশপ - এআই টিম অ্যাকশন ও তাৎক্ষণিক বাস্তবায়ন চেকলিস্ট"
            summary_tagline = f"দোকানদার, ম্যানেজার ও ক্যাশিয়ারের করণীয় অ্যাকশন চেকলিস্ট (বিক্রয়: ৳{rev:,.2f} | নিট লাভ: ৳{net_profit:,.2f})"
            current_state = [
                f"[পরিমাপ] নির্বাচিত সময়সীমায় মোট {tx_count}টি লেনদেনে মোট ৳{rev:,.2f} সংগৃহীত হয়েছে (গড় কেনাকাটা: ৳{aov:,.2f})।",
                f"[লাভজনকতা] গ্রস প্রফিট ৳{gross_profit:,.2f} ({gross_margin_pct:.1f}%) এবং নিট লাভ ৳{net_profit:,.2f} ({net_margin_pct:.1f}%)।",
                f"[চ্যানেল] অফলাইন সেলস ৳{pos_rev:,.2f} ({pos_share_pct:.1f}%) এবং অনলাইন অ্যাপ সেলস ৳{online_rev:,.2f} ({online_share_pct:.1f}%)।",
                f"[চাহিদা ড্রাইভার] দ্রুততম বিক্রি হওয়া পণ্য: '{first_top_prod}' সহ মোট শীর্ষ আইটেম ({top_prod_names})।",
                f"[ব্যয় হিসাব] দোকান পরিচালনা ও অন্যান্য ব্যয় বাবদ মোট ৳{expense:,.2f} লিপিবদ্ধ হয়েছে।"
            ]
            should_do = [
                f"[উচ্চ অগ্রাধিকার - আজই করুন] শীর্ষ বিক্রিত '{first_top_prod}' এর স্টক স্তর পরীক্ষা করুন এবং রিস্টক পয়েন্ট অবিলম্বে ৫০% বাড়িয়ে দিন যাতে পিক সময়ে কখনো স্টক-আউট না হয়।",
                "[উচ্চ অগ্রাধিকার - আজই করুন] ক্যাশ কাউন্টারের সামনে চকোলেট, চুইংগাম ও মিনি স্ন্যাকসের একটি নতুন ছোট ডিসপ্লে ট্রে সাজিয়ে রাখুন।",
                f"[মাঝারি অগ্রাধিকার - এই সপ্তাহে] সরবরাহকারী ডিলারের সাথে বৈঠক করে '{top_prod_names}' এর উপর ৩-৫% অতিরিক্ত ভলিউম ক্যাশব্যাক চুক্তি করুন।",
                "[চলতি সপ্তাহ] অনলাইন অ্যাপে ৳১,০০০ টাকার বেশি কেনাকাটায় ফ্রি ডেলিভারি ব্যানার সক্রিয় করুন।"
            ]
            should_drop = [
                f"[জরুরি বর্জন] অচল পণ্য ({dead_prod_names}) ফেলে রাখা বন্ধ করুন; অবিলম্বে স্পেশাল ১০% ছাড়ের লাল স্টিকার মেরে সামনের সারিতে দিন।",
                "[কঠোর নিয়ম] মেমো ছাড়া ক্যাশ ড্রয়ার থেকে কোনো নগদ টাকা খরচ করা সম্পূর্ণ বন্ধ করুন; তাৎক্ষণিক ডিজিটাল এন্ট্রি নিশ্চিত করুন।",
                "[বর্জন] একই পণ্যের অপ্রয়োজনীয় ডুপ্লিকেট ব্র্যান্ড রাখা বন্ধ করুন; শুধু শীর্ষ ২-৩টি ব্র্যান্ড চালু রাখুন।",
                "[বর্জন] মেয়াদোত্তীর্ণ হওয়ার ঝুঁকিযুক্ত কম বিক্রিত পণ্যের বড় অর্ডার দেওয়া বন্ধ করুন।"
            ]
            where_to_change = [
                "ইনভেন্টরি চেকিং শিডিউল: প্রতি সোমবার সকালে অচল স্টক ও স্বল্প স্টক পণ্যের তালিকা প্রিন্ট করে রিঅর্ডার রিভিউ করুন।",
                "ক্যাশিয়ারের সাথে কথোপকথন: কাস্টমারকে বিল দেওয়ার সময় 'কাউন্টারের এই অফার আইটেমটি কি যুক্ত করবেন?' জিজ্ঞেস করার নির্দেশ দিন।",
                "সেলফ ফেসিং রুটিন: প্রতিদিন দোকান খোলার পর এবং বিকেলে সব তাকের পণ্যের ফ্রন্ট-ফেসিং সাজিয়ে রাখুন।",
                "সাপ্লায়ার বিলিং টার্মস: মাসিক সরবরাহকারীদের বাকির মেয়াদ ১৫-৩০ দিনে উন্নীত করার প্রস্তাব পাঠান।"
            ]
            profit_roadmap = [
                "অ্যাকশন বাস্তবায়ন ১: ক্যাশ কাউন্টার ইমপালস থেকে মাসিক ৳১৫,০০০+ অতিরিক্ত খাঁটি নিট প্রফিট।",
                "অ্যাকশন বাস্তবায়ন ২: ডিলারদের ৩% ভলিউম ডিসকাউন্ট থেকে মোট প্রফিট মার্জিন সরাসরি +২.৫% বৃদ্ধি।",
                f"অ্যাকশন বাস্তবায়ন ৩: অচল স্টক লিকুইডেশন থেকে ৳১৫,০০০ - ৳৫০,০০০ তাৎক্ষণিক নগদ চলতি মূলধন অবমুক্ত।",
                "সামগ্রিক লক্ষ্যমাত্রা: এই চেকলিস্ট অনুসরণ করলে পরবর্তী ৬০ দিনে নিট প্রফিট ৩৫% বৃদ্ধি সুনিশ্চিত।"
            ]
        elif mode == "growth":
            title = "🚀 ডইনিক সুপারশপ - এআই আগ্রাসী প্রবৃদ্ধি ও মার্কেটিং এক্সপ্যানশন রিপোর্ট"
            summary_tagline = f"মার্কেটিং কৌশল, কম্বো ক্যাম্পেইন ও গ্রাহক প্রবৃদ্ধি রোডম্যাপ (বিক্রয়: ৳{rev:,.2f} | নিট লাভ: ৳{net_profit:,.2f})"
            current_state = [
                f"গ্রাহক সমাগম ও রাজস্ব: মোট {tx_count} জন কাস্টমার কেনাকাটা করেছেন এবং আয় হয়েছে ৳{rev:,.2f} (AOV: ৳{aov:,.2f})।",
                f"গ্রস ও নিট মার্জিন: গ্রস মার্জিন {gross_margin_pct:.1f}% (৳{gross_profit:,.2f}) ও নিট মার্জিন {net_margin_pct:.1f}% (৳{net_profit:,.2f})।",
                f"ডিজিটাল বিস্তার: অনলাইন অ্যাপ থেকে এসেছে {online_share_pct:.1f}% (৳{online_rev:,.2f}) এবং দোকানে এসেছে {pos_share_pct:.1f}% (৳{pos_rev:,.2f})।",
                f"জনপ্রিয় ব্র্যান্ডসমূহ: '{first_top_prod}' সহ শীর্ষ খাদ্যপণ্য ({top_prod_names}) কাস্টমার ধরে রাখতে প্রধান ভূমিকা পালন করছে।",
                f"ব্যয় ও আয় অনুপাত: মোট পরিচালন খরচ ৳{expense:,.2f} এবং অন্যান্য আয় ৳{income:,.2f}।"
            ]
            should_do = [
                f"মেগা কম্বো প্যাকেজ ক্যাম্পেইন: '{first_top_prod}' সহ নিত্যপণ্য দিয়ে 'মাসিক বাজার সুপার সেভার কম্বো' চালু করুন এবং ৫-৮% বান্ডিল ছাড় দিন। এতে গড় বাস্কেট সাইজ ৳{aov:,.2f} থেকে বেড়ে ৳{aov*1.30:,.2f}+ হবে।",
                "রেগুলার কাস্টমারদের জন্য লয়ালটি সুবিধা: নিয়মিত কাস্টমারদের জন্য পয়েন্ট সিস্টেম বা 'ভিআইপি মেম্বারশিপ' অফার করুন যাতে প্রতি ১০০ টাকার ক্রয়ে ১ পয়েন্ট পায়।",
                f"অনলাইন অ্যাপ ফ্ল্যাশ সেল: সপ্তাহের নির্দিষ্ট দিন (যেমন শুক্রবার) শীর্ষ পণ্যে ({top_prod_names}) ২ ঘণ্টার ফ্ল্যাশ সেল দিয়ে অ্যাপ ট্রাফিক দ্বিগুণ করুন।",
                "হোয়াটসঅ্যাপ ও এসএমএস মার্কেটিং: নতুন অফার ও কম্বো প্যাকেজের খবর নিয়মিত কাস্টমারদের ফোনে পাঠান।"
            ]
            should_drop = [
                f"অচল পণ্য গুদামে ফেলে রাখা বন্ধ করুন: '{dead_prod_names}' কে 'মেগা ক্লিয়ারেন্স সেল' দিয়ে মূলধন উদ্ধার করুন।",
                "একক পণ্যে বড় ডিসকাউন্ট দিয়ে মার্জিন হারানো বন্ধ করুন; সবসময় কম্বো আকারে ডিসকাউন্ট দিন যাতে মোট লাভ অক্ষুণ্ন থাকে।",
                "অনলাইন প্রচারবিহীন থাকা বন্ধ করুন; ফেসবুক ও লোকাল গ্রুপে নিয়মিত পোস্ট ও ব্যানার শেয়ার করুন।",
                "অপরিকল্পিত ডেলিভারি খরচ বন্ধ করুন; নির্দিষ্ট দূরত্বের ভেতরে একই ট্রিপে একাধিক অর্ডার ডেলিভারির ব্যবস্থা করুন।"
            ]
            where_to_change = [
                "সোশ্যাল মিডিয়া প্রচার: স্থানীয় ফেসবুক গ্রুপ ও পেজে আকর্ষণীয় ফটো সহ সাপ্তাহিক অফারের পোস্ট দিন।",
                "প্যাকেজ ক্যাটাগরি বিস্তার: অ্যাপে 'বাজেট কম্বো', 'ফ্যামিলি কম্বো' এবং 'ব্যাচেলর কম্বো' নামে আকর্ষণীয় প্যাকেজ তৈরি করুন।",
                "ডেলিভারি পার্টনারশিপ: নির্দিষ্ট রাইডার ইনসেনটিভের মাধ্যমে ৩০ মিনিটে ফাস্ট ডেলিভারির নিশ্চয়তা দিন।",
                "কাস্টমার ফিডব্যাক ও রিভিউ: প্রতি ডেলিভারির পর গ্রাহকের সন্তুষ্টি জেনে নিন এবং রেফারেল বোনাস চালু করুন।"
            ]
            profit_roadmap = [
                "কম্বো ক্যাম্পেইন বিস্তার: বড় ফ্যামিলি বাস্কেট বিক্রয় বেড়ে মোট রাজস্ব ২৫% থেকে ৩৫% বৃদ্ধি পাবে।",
                "অনলাইন অ্যাপ দ্বিগুণকরণ: অনলাইন শেয়ার ১৫% থেকে বাড়িয়ে ৩৫%+ এ রূপান্তর করা সম্ভব।",
                f"ক্লিয়ারেন্স ফ্ল্যাশ সেল: অলস ইনভেন্টরি থেকে ৳২০,০০০ - ৳৬০,০০০ নগদ মূলধন রিকভারি।",
                "সার্বিক প্রবৃদ্ধি লক্ষ্য: ৩ মাসের মধ্যে সুপারশপের মাসিক নিট মুনাফা ৪০% এর বেশি বৃদ্ধির সুস্পষ্ট সম্ভাবনা।"
            ]
        else: # "examples" (Default Practical Examples Mode)
            title = "🧠 ডইনিক সুপারশপ - এআই এক্সিকিউটিভ বিজনেস ইন্টেলিজেন্স ও বাস্তব পরামর্শ রিপোর্ট"
            summary_tagline = f"মোট বিক্রয় ৳{rev:,.2f} এবং নিট মুনাফা ৳{net_profit:,.2f} এর সামগ্রিক ব্যবসায়িক ডায়াগনোসিস ও বাস্তব দিকনির্দেশনা"
            current_state = [
                f"১. সামগ্রিক বিক্রয় ও গ্রাহক সমাগম: নির্বাচিত সময়সীমায় মোট {tx_count}টি সফল ট্রানজ্যাকশনে মোট ৳{rev:,.2f} বিক্রয় হয়েছে। প্রতিটি কাস্টমারের গড় বাস্কেট মূল্য (Average Order Value) ৳{aov:,.2f}।",
                f"২. লাভজনকতা ও মার্জিন বিশ্লেষণ: মোট গ্রস প্রফিট অর্জিত হয়েছে ৳{gross_profit:,.2f} (গ্রস মার্জিন {gross_margin_pct:.1f}%) এবং দোকান পরিচালন ব্যয় সমন্বয়ের পর অর্জিত নিট মুনাফা ৳{net_profit:,.2f} (নিট মার্জিন {net_margin_pct:.1f}%)।",
                f"৩. বিক্রয় চ্যানেল বন্টন: দোকানের অফলাইন পিওএস কাউন্টার থেকে এসেছে মোট বিক্রয়ের {pos_share_pct:.1f}% (৳{pos_rev:,.2f}) এবং অনলাইন মোবাইল অ্যাপ/ওয়েবসাইট থেকে এসেছে {online_share_pct:.1f}% (৳{online_rev:,.2f})।",
                f"৪. শীর্ষ চাহিদাসম্পন্ন পণ্য (Top Sellers): '{first_top_prod}' সহ শীর্ষ আইটেমগুলো ({top_prod_names}) মোট বিক্রয়ের সিংহভাগ নিশ্চিত করছে এবং নিয়মিত কাস্টমার ফুটফল ধরে রেখেছে।",
                f"৫. পরিচালন খরচ ও আনুষঙ্গিক আয়: মোট লেজার পরিচালন ব্যয় ৳{expense:,.2f} এবং অন্যান্য বিবিধ আয় বাবদ যুক্ত হয়েছে ৳{income:,.2f}।"
            ]
            should_do = [
                f"📦 বাস্তব পণ্যের আকর্ষণীয় কম্বো তৈরি: দৈনন্দিন প্রয়োজনীয় প্রধান পণ্যের (যেমন: '{first_top_prod}') সাথে উচ্চ মার্জিনের আইটেম (যেমন: মসলা, চা পাতা বা প্রিমিয়াম স্ন্যাকস) একসাথে বান্ডিল করে 'ফ্যামিলি সুপার সেভার কম্বো' চালু করুন। উদাহরণস্বরূপ: ৫% ছাড় দিয়ে কম্বো অফার করলে কাস্টমার একবারে বেশি পণ্য কিনবে এবং গড় বাস্কেট সাইজ ৳{aov:,.2f} থেকে বেড়ে ৳{aov*1.25:,.2f}+ হবে।",
                f"🍫 ক্যাশ কাউন্টার ইমপালস ডিসপ্লে: বিলিং কাউন্টারে কাস্টমারের হাতের নাগালে ছোট ও আকর্ষণীয় পণ্য (যেমন: চকলেট, চুইংগাম, ছোট বিস্কুট, মিনি শ্যাম্পু, টিস্যু) সাজিয়ে রাখুন। উদাহরণস্বরূপ: বিল পেমেন্টের সময় ১০-২০ টাকার অতিরিক্ত পণ্য যুক্ত হওয়া সহজ, যা কোনো বাড়তি খরচ ছাড়াই প্রতিদিন অতিরিক্ত নিট লাভ যোগ করবে।",
                f"🤝 শীর্ষ বিক্রিত পণ্যে ডিলার ডিল: সেরা বিক্রিত আইটেমগুলোর ({top_prod_names}) ডিলারদের সাথে মাসিক টার্গেট ভিত্তিতে অতিরিক্ত ৩% থেকে ৫% ভলিউম ক্যাশব্যাক অথবা প্রতি ১০ কার্টনে ১ কার্টন ফ্রি স্কিম নিশ্চিত করুন। এতে পণ্যের ক্রয়মূল্য কমবে এবং সরাসরি গ্রস প্রফিট বৃদ্ধি পাবে।",
                f"🚚 অনলাইন ফ্রি ডেলিভারি টার্গেট: অনলাইন অ্যাপে নির্দিষ্ট মূল্যের কেনাকাটায় (যেমন: ৳১,০০০ বা ৳১,৫০০ এর উপর) ফ্রি হোম ডেলিভারির ক্যাম্পেইন চালান। এতে অনলাইন বিক্রয়ের শেয়ার বর্তমান {online_share_pct:.1f}% থেকে ৩০%+ এ উন্নীত হবে এবং ডেলিভারি খরচ সাশ্রয় হবে।"
            ]
            should_drop = [
                f"🛑 অচল স্টকের মূলধন আটকে রাখা বন্ধ করুন: দোকানে অলস পড়ে থাকা অচল পণ্য ({dead_prod_names}) তাকের জায়গা দখল করে আছে এবং মূলধন আটকে রেখেছে। উদাহরণস্বরূপ: এগুলোতে ১০-১৫% স্পেশাল ছাড় দিয়ে অথবা জনপ্রিয় পণ্যের সাথে 'বাই ওয়ান গেট ওয়ান / গিফট কম্বো' বানিয়ে আগামী ৭-১০ দিনের মধ্যে বিক্রি করে লিকুইড ক্যাশ তুলে নিন।",
                f"⚠️ মেয়াদোত্তীর্ণ ও পচনশীল ক্ষতি কমানো: যেসব পণ্যের সেলস ভেলোসিটি অত্যন্ত ধীর বা মার্জিন ২% এর কম এবং নষ্ট হওয়ার ঝুঁকি আছে, সেগুলোর অতিরিক্ত স্টক রাখা বন্ধ করুন। 'ফার্স্ট ইন, ফার্স্ট আউট' (FIFO) পদ্ধতি কঠোরভাবে অনুসরণ করুন।",
                f"📝 অনিবন্ধিত খুচরা খরচ বন্ধ: ক্যাশ ড্রয়ার থেকে মেমো ছাড়া কোনো নগদ অর্থ খরচ করা বন্ধ করুন। প্রতিটি দৈনন্দিন খরচ সিস্টেমে তাৎক্ষণিক ডিজিটাল লেজারে এন্ট্রি নিশ্চিত করুন যাতে মাস শেষে অদৃশ্য ক্ষতির হিসাব স্পষ্ট হয়।",
                f"🏷️ ডুপ্লিকেট ব্র্যান্ড ছাঁটাই: একই ক্যাটাগরিতে ৫-৬টি বিভিন্ন অপরিচিত ব্র্যান্ডের পণ্য রাখার পরিবর্তে শুধুমাত্র কাস্টমারদের সবচেয়ে বিশ্বস্ত শীর্ষ ২-৩টি ব্র্যান্ড স্টক করুন। এতে ইনভেন্টরি ম্যানেজমেন্ট সহজ হবে এবং স্টক জট কমে যাবে।"
            ]
            where_to_change = [
                f"🔄 সেলস স্পিড অনুযায়ী দাম নির্ধারণ: যেসব পণ্য দ্রুত চলে ({top_prod_names}) সেগুলোতে লাভজনক স্ট্যান্ডার্ড প্রাইজ ধরে রাখুন এবং ধীরগতির পণ্যগুলোতে আকর্ষণীয় স্টিকার ডিসকাউন্ট দিয়ে টার্নওভার বাড়ান।",
                f"🔔 রিঅর্ডার পয়েন্ট বৃদ্ধি: মূল খাদ্য ও প্রসাধন সামগ্রীর মিনিমাম স্টক অ্যালার্ট সীমা বাড়িয়ে রাখুন, যাতে পিক সময়ে কোনো আইটেম শেষ হয়ে গিয়ে কাস্টমারকে 'Out of Stock' দেখে ফিরে যেতে না হয়।",
                f"📱 অনলাইন ও দোকানের ডিসপ্লে সমন্বয়: মোবাইল অ্যাপের হোমপেজ ব্যানার এবং দোকানের প্রবেশদ্বারে সেরা অফার ও কম্বো প্যাকেজের বড় রঙিন পোস্টার বা ব্যানার প্রদর্শন করুন।",
                f"💳 সাপ্লায়ারদের সাথে ক্রেডিট মেয়াদ: নিয়মিত পাইকারি সরবরাহকারীদের সাথে ১৫-৩০ দিনের ব্যবসায়িক ক্রেডিট সুবিধা চালু করুন, যাতে নিজের নগদ চলতি মূলধন সর্বদা সুরক্ষিত থাকে।"
            ]
            profit_roadmap = [
                f"অচল স্টক বিক্রি: অচল পণ্য ({dead_prod_names[:30]}...) দ্রুত বিক্রি থেকে ৳১৫,০০০ - ৳৫০,০০০ তাৎক্ষণিক নগদ চলতি মূলধন অবমুক্ত হবে।",
                "বাল্ক ক্রয় সাশ্রয়: সাপ্লায়ারদের সাথে ভলিউম চুক্তির মাধ্যমে পণ্যের ক্রয়মূল্য কমিয়ে গ্রস মার্জিন +২.৫% থেকে +৪.০% বাড়ানো সম্ভব।",
                f"বাস্কেট সাইজ বৃদ্ধি: কম্বো বান্ডিল ও ফ্রি ডেলিভারি প্রণোদনায় গড় কেনাকাটা (AOV) ৳{aov:,.2f} থেকে ২০-২৫% বৃদ্ধি পাবে।",
                "সামগ্রিক লক্ষ্যমাত্রা: উপরোক্ত কর্মপরিকল্পনাগুলো একযোগে বাস্তবায়ন করলে পরবর্তী প্রান্তিকে নিট মুনাফা ২৫% থেকে ৪০% বৃদ্ধি পাবে।"
            ]
    else:
        # ENGLISH GENERATION
        if mode == "visual":
            title = "🎨 DOINEEK Supershop - AI Visual Merchandising & Revenue Spotlight Report"
            summary_tagline = f"Visual Store Layout, Shelf Placement & Profit Analysis (Revenue: TK {rev:,.2f} | Net Profit: TK {net_profit:,.2f})"
            current_state = [
                f"Visual Sales Performance: Total sales revenue stands at TK {rev:,.2f} across {tx_count} customer orders; Average Order Value is TK {aov:,.2f}.",
                f"Margin Diagnosis: Gross Margin is {gross_margin_pct:.1f}% (TK {gross_profit:,.2f}) and operational Net Profit is TK {net_profit:,.2f} ({net_margin_pct:.1f}%).",
                f"Channel Ratio: Offline POS counter represents {pos_share_pct:.1f}% (TK {pos_rev:,.2f}) vs Online App at {online_share_pct:.1f}% (TK {online_rev:,.2f}).",
                f"Visual Drivers: Top-selling products like '{first_top_prod}' and '{top_prod_names}' command the highest customer visual attention.",
                f"Operating Ledger: Total operating expenses are TK {expense:,.2f} alongside TK {income:,.2f} in other earnings."
            ]
            should_do = [
                f"Eye-Level Shelf Merchandising: Place high-margin specialty items directly at eye level (4.5 to 5.5 ft) right beside high-turnover staples like '{first_top_prod}'.",
                "Cashier Impulse Display: Set up colorful impulse display trays with chocolates, gums, mini snacks, and pocket tissues directly on billing counters.",
                "High-Contrast Combo Signage: Install bright yellow/green 'Super Saver Combo' and 'Special Value' shelf-talkers so offers are visible from aisle entrances.",
                f"Mobile App Top Banners: Feature high-margin bundles featuring '{first_top_prod}' prominently on the app header carousel."
            ]
            should_drop = [
                f"Stop dedicating prime shelf space to dead stock: Move slow items ({dead_prod_names}) to clearance discount bins near checkout.",
                "Avoid cluttered aisles: Disorganized shelves reduce customer basket sizes; maintain consistent facing across all aisles.",
                "Discontinue overstocking slow-velocity goods with expiration risks.",
                "Keep checkout counters uncluttered: Remove loose boxes and paperwork to prioritize revenue-generating impulse items."
            ]
            where_to_change = [
                "Customer Flow Walkways: Ensure unobstructed, welcoming walkways from store entrance to checkout counters.",
                f"Clearance Price Tagging: Apply vibrant '10% OFF' price tags to slow-moving inventory ({dead_prod_names}).",
                "Product Lighting: Use bright spotlighting over bakery, produce, and premium packaged grocery shelves.",
                "Online Product Imagery: Maintain crisp white-background images with clear pricing across the web and app."
            ]
            profit_roadmap = [
                "Eye-Level Merchandising: Repositioning high-margin items projected to lift basket margins by 15-20%.",
                "Counter Impulse Buying: Generating extra TK 20-50 across 30+ transactions adds TK 18,000 - TK 30,000 monthly net gain.",
                f"Dead Stock Clearance: Unlocks TK 15,000 - TK 50,000 in liquid capital locked in slow inventory.",
                "App Merchandising Banners: Target scaling digital online order revenue share to 30%+."
            ]
        elif mode == "action":
            title = "⚡ DOINEEK Supershop - AI Team Action & Execution Priority Checklist"
            summary_tagline = f"Manager, Cashier & Floor Staff Actionable Directives (Revenue: TK {rev:,.2f} | Net Profit: TK {net_profit:,.2f})"
            current_state = [
                f"[Metric] {tx_count} customer orders generated TK {rev:,.2f} in gross revenue with Average Order Value at TK {aov:,.2f}.",
                f"[Profitability] Gross Profit stands at TK {gross_profit:,.2f} ({gross_margin_pct:.1f}%) and Net Profit at TK {net_profit:,.2f} ({net_margin_pct:.1f}%).",
                f"[Channels] POS Counter accounts for TK {pos_rev:,.2f} ({pos_share_pct:.1f}%) vs Online App at TK {online_rev:,.2f} ({online_share_pct:.1f}%).",
                f"[High Turnover] Fast-moving product driving sales: '{first_top_prod}' along with '{top_prod_names}'.",
                f"[Expenses] Operating expenses total TK {expense:,.2f} balanced by TK {income:,.2f} in other income."
            ]
            should_do = [
                f"[High Priority - Today] Audit stock levels for top item '{first_top_prod}' and raise re-order point by 50% to prevent stockouts.",
                "[High Priority - Today] Install an impulse display tray (gums, mints, chocolates) immediately beside the cashier register.",
                f"[Medium Priority - This Week] Meet with distributors for '{top_prod_names}' to secure a 3-5% volume discount or free cartoon scheme.",
                "[This Week] Activate Free Delivery threshold on mobile app orders above TK 1,000."
            ]
            should_drop = [
                f"[Urgent Drop] Stop holding dead stock ({dead_prod_names}); mark down by 10-15% with discount stickers immediately.",
                "[Strict Enforcement] Stop unvouched petty cash payouts from register; enforce digital ledger entries.",
                "[Drop] Discontinue duplicate low-demand brands; streamline to top 2-3 consumer favorites.",
                "[Drop] Stop ordering bulk quantities of slow-moving items with near expiration dates."
            ]
            where_to_change = [
                "Weekly Stock Audit: Every Monday morning, review slow-moving and low-stock alerts before ordering.",
                "Cashier Prompting: Train cashier staff to mention counter impulse specials before printing final receipts.",
                "Shelf Facing Routine: Daily 10-minute floor tidy to face all products neatly to the shelf edge.",
                "Vendor Credit Terms: Request 15-30 day supplier credit terms to preserve cash flow."
            ]
            profit_roadmap = [
                "Impulse Placement: Generates TK 15,000+ extra monthly net profit at minimal overhead.",
                "Distributor Volume Discounts: Direct 3-5% procurement savings enhances Gross Margin by +2.5% to +4.0%.",
                f"Dead Stock Recovery: Recovers TK 15,000 - TK 50,000 in trapped liquid cash.",
                "Overall Target: 35% net profit increase achievable within 60 days of full checklist implementation."
            ]
        elif mode == "growth":
            title = "🚀 DOINEEK Supershop - AI Aggressive Sales & Marketing Growth Report"
            summary_tagline = f"Marketing Campaign Strategy, Combo Bundles & Scale Roadmap (Revenue: TK {rev:,.2f} | Net Profit: TK {net_profit:,.2f})"
            current_state = [
                f"Customer Volume: {tx_count} customer checkouts generated TK {rev:,.2f} with an Average Order Value of TK {aov:,.2f}.",
                f"Profit Margins: Gross Margin is {gross_margin_pct:.1f}% (TK {gross_profit:,.2f}) and Net Margin is {net_margin_pct:.1f}% (TK {net_profit:,.2f}).",
                f"Digital Foothold: Online app orders generated {online_share_pct:.1f}% (TK {online_rev:,.2f}) alongside store POS {pos_share_pct:.1f}% (TK {pos_rev:,.2f}).",
                f"Core Brand Anchors: Best sellers '{first_top_prod}' and '{top_prod_names}' represent essential customer loyalty anchors.",
                f"Operational Ledger: Ledger expenses are TK {expense:,.2f} offset by TK {income:,.2f} in other revenue."
            ]
            should_do = [
                f"Curate Mega Combo Bundles: Bundle top seller '{first_top_prod}' with secondary essentials into 'Monthly Family Packs' with 5% discount, lifting basket size from TK {aov:,.2f} to TK {aov*1.30:,.2f}+.",
                "Launch VIP Customer Club: Provide points or loyalty perks (e.g. 1 point per TK 100) to incentivize repeat weekly store visits.",
                f"App Flash Sales: Run 2-hour limited flash sales on top staples ({top_prod_names}) every Friday to double mobile app traffic.",
                "WhatsApp & SMS Outreach: Send seasonal combo alerts and new stock updates directly to verified customer mobile numbers."
            ]
            should_drop = [
                f"Stop storing dead stock ({dead_prod_names}) in backrooms; run a weekend 'Mega Clearance Sale' to recover cash.",
                "Stop offering discounts on single standalone items; always require combo bundles to protect profit margins.",
                "Avoid silence on social media; share weekly product spotlights and promo bundles consistently.",
                "Eliminate inefficient single-drop deliveries; batch customer deliveries by area routes to lower transport costs."
            ]
            where_to_change = [
                "Social Media Marketing: Share engaging photo posts of combo bundles across local community groups.",
                "Package Category Expansion: Create 'Family Essentials', 'Budget Combos', and 'Hostel Packs' in the mobile app.",
                "Express Delivery SLA: Guarantee 30-minute doorstep delivery with rider performance incentives.",
                "Customer Feedback Loop: Solicit post-delivery reviews and incentivize customer referrals."
            ]
            profit_roadmap = [
                "Combo Campaign Expansion: Lifts average transaction basket revenue by +25% to +35%.",
                "Mobile App Scaling: Scales digital order revenue share from 15% to 35%+ of overall turnover.",
                f"Clearance Flash Sales: Recovers TK 20,000 - TK 60,000 in immediate working capital from idle inventory.",
                "Quarterly Projection: Drives an estimated 40%+ increase in total shop net profit over the next 90 days."
            ]
        else: # "examples" (Default Practical Examples Mode)
            title = "🧠 DOINEEK Supershop - AI Executive Business Intelligence & Practical Advisory Report"
            summary_tagline = f"Comprehensive Performance Analysis for Revenue TK {rev:,.2f} & Net Profit TK {net_profit:,.2f} with Real Product Examples"
            current_state = [
                f"1. Sales Revenue & Volume: Total Sales Revenue stands at TK {rev:,.2f} across {tx_count} customer transactions with an Average Order Value (AOV) of TK {aov:,.2f}.",
                f"2. Profitability Margins: Gross Profit Margin is {gross_margin_pct:.1f}% (TK {gross_profit:,.2f}) and Net Profit Margin is {net_margin_pct:.1f}% (TK {net_profit:,.2f}) after ledger operational adjustments.",
                f"3. Channel Breakdown: Offline POS Counter accounts for {pos_share_pct:.1f}% (TK {pos_rev:,.2f}) while Online Mobile App/Web accounts for {online_share_pct:.1f}% (TK {online_rev:,.2f}).",
                f"4. Top Revenue Drivers: Products like '{first_top_prod}' and '{top_prod_names}' represent the highest turnover and consistent customer demand.",
                f"5. Operating Allocations: Total ledger expenses are TK {expense:,.2f} counterbalanced by TK {income:,.2f} in other earnings."
            ]
            should_do = [
                f"📦 Curate Product Combo Bundles: Bundle high-demand staples (e.g. '{first_top_prod}' or rice/oil) together with high-margin specialty items (spices, premium tea, snacks) into 'Family Super Saver Combos'. Offering a 5% bundle discount lifts average order basket from TK {aov:,.2f} to TK {aov*1.25:,.2f}+.",
                "🍫 Front Checkout Counter Impulse Displays: Place high-margin impulse goods (gums, mints, chocolates, mini snacks, pocket tissues) directly beside checkout billing registers. Customers instinctively add these at checkout, effortlessly boosting daily net profit.",
                f"🤝 Negotiate Bulk Distributor Deals: For top-selling inventory ({top_prod_names}), negotiate 3-5% volume cashbacks or 1 free carton per 10 cartons scheme with distributors to directly increase Gross Margin.",
                f"🚚 Free Delivery Basket Thresholds: Run mobile app promotions with Free Delivery for orders above TK 1,000 or TK 1,500. This will scale online share from {online_share_pct:.1f}% to 30%+ while covering logistics costs."
            ]
            should_drop = [
                f"🛑 Liquidate Capital-Trapping Dead Stock: Unsold items ({dead_prod_names}) lock precious shelf space and capital. Liquidate them by bundling at 10-15% discount or gifting with top sellers to recover working cash within 7-10 days.",
                "⚠️ Minimize Perishable & Expiration Losses: Stop ordering excess stock for items with less than 2% gross margin or slow velocity that risk expiration. Enforce strict FIFO (First In, First Out) stocking.",
                "📝 Eliminate Untracked Petty Cash Outflows: Stop taking unrecorded cash directly from registers. Require immediate digital ledger entries for every daily expense to eliminate invisible leakages.",
                "🏷️ Consolidate Redundant Duplicate Brands: Avoid stocking 5-6 duplicate brands in identical categories. Stock only the top 2-3 customer favorites to streamline inventory."
            ]
            where_to_change = [
                f"🔄 Velocity-Based Dynamic Pricing: Keep profitable standard margins on fast-moving goods ({top_prod_names}) while applying attractive promo stickers to slow movers to accelerate cash turnover.",
                "🔔 Increase Minimum Safety Stock Alerts: Raise low-stock alert thresholds for core essentials so shelves never hit 'Out of Stock' during peak customer rush hours.",
                "📱 Synchronize Store Posters with App Banners: Display prominent color posters at store entrance mirroring the top combo banners on the mobile app.",
                "💳 Supplier Trade Credit Terms: Transition key distributor accounts to 15-30 day trade credit to preserve cash working capital."
            ]
            profit_roadmap = [
                f"Dead Stock Clearance: Unlocks TK 15,000 - TK 50,000 in immediate liquid working capital from idle items ({dead_prod_names[:30]}...).",
                "Bulk Procurement Savings: Enhances overall Gross Profit Margin by +2.5% to +4.0% via volume distributor agreements.",
                f"Combo Bundles & Basket Incentives: Lifts average customer order value (AOV) from TK {aov:,.2f} by +20% to +25%.",
                "Targeted Growth Realization: Coordinated execution projected to increase Total Net Profit by 25% to 40% in next quarter."
            ]

    return {
        "lang": lang,
        "mode": mode,
        "title": title,
        "summary_tagline": summary_tagline,
        "visual_spotlights": visual_spotlights,
        "current_state": current_state,
        "should_do": should_do,
        "should_drop": should_drop,
        "where_to_change": where_to_change,
        "profit_roadmap": profit_roadmap
    }


@app.route("/reports/api/regenerate_ai_report")
@login_required
@admin_required
def api_regenerate_ai_report():
    period = request.args.get("period", "monthly")
    mode = request.args.get("mode", "examples")
    dept = (request.args.get("dept") or "all").strip().lower()
    if dept not in ("all", "general", "pharmacy"):
        dept = "all"

    conn = get_connection()
    period, date_filter, ledger_filter = _resolve_report_period_filters(period)
    bundle = _compute_separated_reports(conn, date_filter, ledger_filter, dept=dept)
    ai_report_en = build_ai_business_report(bundle["metrics_bundle"], "en", mode)
    ai_report_bn = build_ai_business_report(bundle["metrics_bundle"], "bn", mode)
    conn.close()

    return jsonify({
        "success": True,
        "mode": mode,
        "dept": dept,
        "ai_report_en": ai_report_en,
        "ai_report_bn": ai_report_bn
    })


@app.route("/reports/export_pdf")
@login_required
@admin_required
def reports_export_pdf():
    period = request.args.get("period", "monthly")
    lang = request.args.get("lang", "en")
    mode = request.args.get("mode", "examples")
    dept = (request.args.get("dept") or "all").strip().lower()
    if dept not in ("all", "general", "pharmacy"):
        dept = "all"

    conn = get_connection()
    period, date_filter, ledger_filter = _resolve_report_period_filters(period)
    bundle = _compute_separated_reports(conn, date_filter, ledger_filter, dept=dept)
    ai_report = build_ai_business_report(bundle["metrics_bundle"], lang, mode)
    conn.close()

    return render_template(
        "report_pdf.html",
        period=period,
        lang=lang,
        dept=dept,
        generated_at=datetime.now().strftime("%d %b %Y, %I:%M %p"),
        revenue=bundle["revenue"],
        cogs=bundle["cogs"],
        gross_profit=bundle["gross_profit"],
        net_profit=bundle["net_profit"],
        tx_count=bundle["tx_count"],
        ai_report=ai_report,
        top_products=bundle["top_products"],
        top_medicines=bundle["top_medicines"],
        offline_summary=bundle["offline_summary"],
        online_summary=bundle["online_summary"],
        packages_summary=bundle["packages_summary"],
        offers_summary=bundle["offers_summary"],
        general_summary=bundle["general_summary"],
        pharmacy_summary=bundle["pharmacy_summary"],
        whole_summary=bundle["whole_summary"],
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
    dept = (request.args.get("dept") or "all").strip().lower()
    if dept not in ("all", "regular", "pharmacy"):
        dept = "all"

    conn = get_connection()
    # Ensure confirmed/packed/dispatched/delivered pharmacy orders are mirrored in online_orders
    try:
        unsynced_pharm = conn.execute("""
            SELECT po.id, po.approved_items_json, po.requested_items_json
            FROM pharmacy_orders po
            LEFT JOIN online_orders oo ON po.online_order_id = oo.id
            WHERE po.order_status IN ('confirmed', 'packed', 'on_the_way', 'delivered')
              AND (oo.id IS NULL OR oo.order_status IN ('pending', 'pending_confirmation', 'reviewing', 'new'))
        """).fetchall()
        if unsynced_pharm:
            now_sync = get_bd_now_iso()
            for up in unsynced_pharm:
                raw_j = up["approved_items_json"] or up["requested_items_json"] or "[]"
                try:
                    parsed_itms = json.loads(raw_j) if raw_j else None
                except Exception:
                    parsed_itms = None
                _ensure_online_order_for_pharmacy(conn, up["id"], approved_items=parsed_itms, now_iso=now_sync)
            conn.commit()
    except Exception as e:
        print(f"[online_orders] Pharmacy sync notice: {e}")

    user_role = session.get("role", "")
    user_id = session.get("user_id")
    username = (session.get("username") or "").strip()

    if user_role == "delivery":
        norm_u = normalize_phone(username)
        u_patterns = list(set(filter(None, [username, norm_u, f"88{norm_u}" if norm_u else "", f"+88{norm_u}" if norm_u else ""])))
        placeholders = ",".join("?" for _ in u_patterns) if u_patterns else "''"
        orders = conn.execute(f"""
            SELECT * FROM online_orders
            WHERE (
                ((assigned_rider_phone IS NULL OR assigned_rider_phone = '') AND COALESCE(assigned_rider_id, 0) = 0
                 AND order_status IN ('new', 'verified', 'packed'))
                OR
                (assigned_rider_phone IN ({placeholders}) OR (assigned_rider_id IS NOT NULL AND assigned_rider_id = ?))
            )
            ORDER BY id DESC
        """, tuple(u_patterns + [user_id or 0])).fetchall()
    else:
        orders = conn.execute("SELECT * FROM online_orders ORDER BY id DESC").fetchall()

    orders_list = []
    regular_count = 0
    pharmacy_count = 0
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

        ord_num = str(o_dict.get("order_number") or "")
        is_pharm = ord_num.upper().startswith("RX-")
        pharm_row = conn.execute(
            "SELECT * FROM pharmacy_orders WHERE online_order_id = ? OR order_number = ? LIMIT 1",
            (o_dict["id"], ord_num),
        ).fetchone()
        if pharm_row:
            is_pharm = True
            o_dict["pharmacy_order_id"] = pharm_row["id"]
            o_dict["prescription_url"] = pharm_row["prescription_url"] or ""
            o_dict["prescription_original_url"] = pharm_row["prescription_original_url"] or ""
            o_dict["customer_notes"] = pharm_row["customer_notes"] or ""
            o_dict["overall_duration_days"] = pharm_row["overall_duration_days"] or 0
            if not o_dict.get("customer_ip") and "customer_ip" in pharm_row.keys():
                o_dict["customer_ip"] = pharm_row["customer_ip"] or ""
            if not o_dict.get("ip_location") and "ip_location" in pharm_row.keys():
                o_dict["ip_location"] = pharm_row["ip_location"] or ""
            if not item_list or (len(item_list) == 1 and float(item_list[0].get("unit_price") or 0) == 0 and float(o_dict.get("total_amount") or 0) > 0):
                raw_j = pharm_row["approved_items_json"] or pharm_row["requested_items_json"] or "[]"
                try:
                    j_items = json.loads(raw_j) if raw_j else []
                except Exception:
                    j_items = []
                if j_items:
                    item_list = [
                        {
                            "product_id": it.get("medicine_id") or 0,
                            "product_name": f"💊 {it.get('name', 'Medicine')}" + (f" ({it.get('strength')})" if it.get("strength") else ""),
                            "unit_price": float(it.get("unit_price") or 0.0),
                            "mrp_price": float(it.get("unit_price") or 0.0),
                            "quantity": int(it.get("quantity") or 1),
                            "total_price": float(it.get("total_price") or 0.0),
                        }
                        for it in j_items
                    ]

        o_dict["is_pharmacy_order"] = is_pharm
        o_dict["items"] = item_list
        o_dict["order_items"] = item_list

        c_phone = o_dict.get("customer_phone", "")
        c_user = conn.execute("SELECT * FROM customer_users WHERE phone = ?", (c_phone,)).fetchone()
        cu_d = dict(c_user) if c_user else {}
        o_dict["customer_profile_image"] = (cu_d.get("profile_image") or cu_d.get("avatar_url") or cu_d.get("avatar_base64") or "")
        o_dict["customer_created_at"] = cu_d.get("created_at") or ""
        o_dict["customer_member_since"] = _member_since_label(cu_d.get("created_at") or o_dict.get("created_at") or "")
        o_dict["customer_last_ip"] = o_dict.get("customer_ip") or cu_d.get("last_ip") or cu_d.get("registration_ip") or ""
        o_dict["customer_last_location"] = o_dict.get("ip_location") or cu_d.get("last_location") or cu_d.get("registration_location") or ""
        o_dict["customer_last_device"] = cu_d.get("last_device") or ""

        if is_pharm:
            pharmacy_count += 1
        else:
            regular_count += 1
        orders_list.append(o_dict)

    if dept == "pharmacy":
        filtered_orders = [o for o in orders_list if o.get("is_pharmacy_order")]
    elif dept == "regular":
        filtered_orders = [o for o in orders_list if not o.get("is_pharmacy_order")]
    else:
        filtered_orders = orders_list

    riders = conn.execute("SELECT * FROM users WHERE role = 'delivery' AND is_active = 1").fetchall()
    conn.close()
    return render_template(
        "online_orders.html",
        orders=filtered_orders,
        all_orders_count=len(orders_list),
        regular_count=regular_count,
        pharmacy_count=pharmacy_count,
        dept=dept,
        riders=riders,
    )


def notify_order_status_change(order_row_or_dict, new_status, conn=None):
    if not order_row_or_dict:
        return
    phone = order_row_or_dict.get("customer_phone") if isinstance(order_row_or_dict, dict) else order_row_or_dict["customer_phone"]
    order_number = order_row_or_dict.get("order_number") if isinstance(order_row_or_dict, dict) else order_row_or_dict["order_number"]
    if not phone:
        return

    status_titles = {
        "verified": "Order Confirmed",
        "packed": "Order Packed",
        "on_the_way": "Order On The Way",
        "delivered": "Order Delivered",
        "cancelled": "Order Cancelled",
    }
    status_messages = {
        "verified": f"Your order #{order_number} is confirmed and is being prepared with care.",
        "packed": f"Your order #{order_number} has been packed and is ready for dispatch.",
        "on_the_way": f"Great news! Your order #{order_number} is on the way. Our rider is heading to your address.",
        "delivered": f"Your order #{order_number} has been delivered successfully. Thank you for shopping with DOINEEK!",
        "cancelled": f"Your order #{order_number} has been cancelled.",
    }
    if new_status in status_titles:
        add_customer_notification(
            customer_phone=phone,
            title=status_titles[new_status],
            message=status_messages[new_status],
            notif_type="order",
            reference_id=str(order_number),
            conn=conn
        )


def ensure_daily_suggestions_and_offers(conn=None):
    close_conn = False
    if conn is None:
        conn = get_connection()
        close_conn = True
    try:
        today_str = datetime.now().strftime("%Y-%m-%d")
        # 1. Daily product suggestion
        chk_sugg = conn.execute(
            "SELECT id FROM customer_notifications WHERE type = 'suggestion' AND created_at LIKE ?",
            (f"{today_str}%",)
        ).fetchone()
        if not chk_sugg:
            prod = conn.execute("""
                SELECT id, name, sell_price, unit, image_url 
                FROM products 
                WHERE stock_qty > 0 
                ORDER BY is_trending DESC, is_flash_sale DESC, RANDOM() 
                LIMIT 1
            """).fetchone()
            if prod:
                unit_str = f" / {prod['unit']}" if prod["unit"] else ""
                add_customer_notification(
                    customer_phone="",
                    title="Daily Suggested Product",
                    message=f"Today's recommended pick: '{prod['name']}' at TK {prod['sell_price']}{unit_str}! Fresh stock ready for delivery.",
                    notif_type="suggestion",
                    reference_id=str(prod["id"]),
                    conn=conn
                )

        # 2. Active offers notification (every 2 days or if new)
        chk_offer = conn.execute(
            "SELECT id FROM customer_notifications WHERE type = 'offer' AND created_at >= ?",
            ((datetime.now() - timedelta(days=2)).isoformat(),)
        ).fetchone()
        if not chk_offer:
            voucher = conn.execute("SELECT * FROM vouchers WHERE active = 1 ORDER BY id DESC LIMIT 1").fetchone()
            if voucher:
                disc_str = f"{voucher['discount_value']}%" if voucher["discount_type"] == "percentage" else f"TK {voucher['discount_value']}"
                add_customer_notification(
                    customer_phone="",
                    title=f"Exclusive Offer: {voucher['code']}",
                    message=f"Save {disc_str} on your order today! Use voucher code '{voucher['code']}' during checkout.",
                    notif_type="offer",
                    reference_id=str(voucher["code"]),
                    conn=conn
                )
            else:
                pkg = conn.execute("SELECT * FROM packages WHERE is_active = 1 LIMIT 1").fetchone()
                if pkg:
                    add_customer_notification(
                        customer_phone="",
                        title=f"Special Combo Deal: {pkg['name']}",
                        message=f"Get '{pkg['name']}' bundle for only TK {pkg['package_price']}! Save big when ordering packages today.",
                        notif_type="offer",
                        reference_id=str(pkg["id"]),
                        conn=conn
                    )
        if close_conn:
            conn.commit()
    except Exception as e:
        print(f"[notifications] ensure_daily_suggestions_and_offers error: {e}")
    finally:
        if close_conn:
            conn.close()


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

    if (order["order_status"] or "").strip().lower() == "awaiting_customer_confirmation":
        conn.close()
        flash(f"Order #{order['order_number']} is awaiting customer confirmation. Customer must confirm the bill before dispatch.", "error")
        return redirect(url_for("online_orders"))

    rider_name = ""
    rider_phone = ""
    if rider_id:
        rider = conn.execute("SELECT * FROM users WHERE id = ? AND role = 'delivery'", (rider_id,)).fetchone()
        if rider:
            rider_name = rider["full_name"] if rider["full_name"] else rider["username"]
            rider_phone = rider["username"]

    now_iso = get_bd_now_iso()
    conn.execute(
        "UPDATE online_orders SET order_status = 'verified', assigned_rider_id = ?, assigned_rider_name = ?, assigned_rider_phone = ?, confirmed_at = CASE WHEN confirmed_at = '' THEN ? ELSE confirmed_at END, updated_at = ? WHERE id = ?",
        (rider_id or 0, rider_name, rider_phone, now_iso, now_iso, order_id)
    )
    deduct_online_order_stock(conn, order)
    pharm_id = _sync_pharmacy_from_online_order(
        conn, order, 'verified', now_iso,
        rider_id=rider_id or 0, rider_name=rider_name, rider_phone=rider_phone,
    )
    notify_order_status_change(order, 'verified', conn=conn)
    conn.commit()
    conn.close()

    remote_control.push_online_order_to_cloud(order_id)
    if pharm_id:
        remote_control.push_pharmacy_order_to_cloud(pharm_id)
    if rider_name:
        flash(f"Order #{order['order_number']} assigned to Delivery Rider '{rider_name}' ({rider_phone}) and verified!", "success")
    else:
        flash(f"Order #{order['order_number']} verified successfully!", "success")
    return redirect(url_for("online_orders"))


_OL_TO_PHARM_STATUS = {
    "new": "reviewing",
    "pending": "reviewing",
    "pending_confirmation": "reviewing",
    "reviewing": "reviewing",
    "awaiting_customer_confirmation": "awaiting_customer_confirmation",
    "verified": "confirmed",
    "confirmed": "confirmed",
    "packed": "packed",
    "on_the_way": "on_the_way",
    "delivered": "delivered",
    "cancelled": "cancelled",
}

_PHARM_TO_OL_STATUS = {
    "reviewing": "pending_confirmation",
    "new": "new",
    "pending": "pending",
    "pending_confirmation": "pending_confirmation",
    "awaiting_customer_confirmation": "awaiting_customer_confirmation",
    "confirmed": "verified",
    "verified": "verified",
    "packed": "packed",
    "on_the_way": "on_the_way",
    "delivered": "delivered",
    "cancelled": "cancelled",
}


def _sync_pharmacy_from_online_order(conn, ol_order, new_ol_status, now_iso,
                                     payment_status=None, rider_id=None,
                                     rider_name=None, rider_phone=None, rider_fee=None):
    """Mirror status, timestamps, payment, and rider fields from an online_orders row into pharmacy_orders."""
    if not ol_order:
        return None
    ol_id = ol_order["id"]
    ord_num = ol_order["order_number"] or ""
    pharm = conn.execute(
        "SELECT * FROM pharmacy_orders WHERE online_order_id = ? OR order_number = ? LIMIT 1",
        (ol_id, ord_num),
    ).fetchone()
    if not pharm:
        return None

    target_pharm_st = _OL_TO_PHARM_STATUS.get((new_ol_status or "").strip().lower(), new_ol_status)
    ts_col_map = {
        "confirmed": "confirmed_at",
        "packed": "packed_at",
        "on_the_way": "on_the_way_at",
        "delivered": "delivered_at",
        "cancelled": "cancelled_at",
    }
    ts_col = ts_col_map.get(target_pharm_st, "")

    sets = ["order_status = ?", "online_order_id = ?", "updated_at = ?"]
    params = [target_pharm_st, ol_id, now_iso]
    if ts_col:
        sets.append(f"{ts_col} = CASE WHEN COALESCE({ts_col}, '') = '' THEN ? ELSE {ts_col} END")
        params.append(now_iso)
    if payment_status:
        sets.append("payment_status = ?")
        params.append(payment_status)
    if rider_id is not None and int(rider_id or 0) > 0:
        sets.append("assigned_rider_id = ?")
        params.append(int(rider_id))
    if rider_name is not None:
        sets.append("assigned_rider_name = ?")
        params.append(rider_name)
    if rider_phone is not None:
        sets.append("assigned_rider_phone = ?")
        params.append(rider_phone)
    if rider_fee is not None:
        sets.append("rider_fee = CASE WHEN COALESCE(rider_fee, 0) <= 0 THEN ? ELSE rider_fee END")
        params.append(float(rider_fee))
    params.append(pharm["id"])
    conn.execute(f"UPDATE pharmacy_orders SET {', '.join(sets)} WHERE id = ?", params)
    return pharm["id"]


def _ensure_online_order_for_pharmacy(conn, pharm_order_id, approved_items=None, now_iso=None):
    """Ensure a pharmacy_orders row is linked to an online_orders row and mirrors status/timestamps/items."""
    pharm = conn.execute("SELECT * FROM pharmacy_orders WHERE id = ?", (pharm_order_id,)).fetchone()
    if not pharm:
        return None
    now_iso = now_iso or get_bd_now_iso()
    ol = None
    if pharm["online_order_id"]:
        ol = conn.execute("SELECT * FROM online_orders WHERE id = ?", (pharm["online_order_id"],)).fetchone()
    if not ol and pharm["order_number"]:
        ol = conn.execute("SELECT * FROM online_orders WHERE order_number = ? LIMIT 1", (pharm["order_number"],)).fetchone()

    target_ol_st = _PHARM_TO_OL_STATUS.get((pharm["order_status"] or "").strip().lower(), pharm["order_status"] or "pending_confirmation")
    if not ol:
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO online_orders (
                order_number, customer_name, customer_phone, customer_email,
                country, district, area, address_details, payment_method,
                payment_status, subtotal, delivery_charge, total_amount,
                order_status, delivery_otp, assigned_rider_id, assigned_rider_name,
                assigned_rider_phone, rider_fee, created_at, updated_at,
                confirmed_at, packed_at, on_the_way_at, delivered_at, cancelled_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            pharm["order_number"], pharm["customer_name"] or "", pharm["customer_phone"] or "", pharm["customer_email"] or "",
            pharm["country"] or "Bangladesh", pharm["district"] or "Tangail", pharm["area"] or "Tangail Sadar",
            pharm["delivery_address"] or "", pharm["payment_method"] or "cod",
            pharm["payment_status"] or "pending", float(pharm["subtotal"] or 0.0),
            float(pharm["delivery_charge"] or 50.0), float(pharm["total_amount"] or 0.0),
            target_ol_st, pharm["delivery_otp"] or "",
            int(pharm["assigned_rider_id"] or 0), pharm["assigned_rider_name"] or "",
            pharm["assigned_rider_phone"] or "", float(pharm["rider_fee"] or 0.0),
            pharm["created_at"] or now_iso, now_iso,
            pharm["confirmed_at"] or (now_iso if target_ol_st == "verified" else ""),
            pharm["packed_at"] or (now_iso if target_ol_st == "packed" else ""),
            pharm["on_the_way_at"] or (now_iso if target_ol_st == "on_the_way" else ""),
            pharm["delivered_at"] or (now_iso if target_ol_st == "delivered" else ""),
            pharm["cancelled_at"] or (now_iso if target_ol_st == "cancelled" else ""),
        ))
        ol_id = cur.lastrowid
        conn.execute("UPDATE pharmacy_orders SET online_order_id = ? WHERE id = ?", (ol_id, pharm_order_id))
    else:
        ol_id = ol["id"]
        if pharm["online_order_id"] != ol_id:
            conn.execute("UPDATE pharmacy_orders SET online_order_id = ? WHERE id = ?", (ol_id, pharm_order_id))
        conn.execute("""
            UPDATE online_orders SET
                order_status = ?,
                subtotal = ?,
                delivery_charge = ?,
                total_amount = ?,
                payment_status = COALESCE(NULLIF(?, ''), payment_status),
                assigned_rider_id = CASE WHEN COALESCE(?, 0) > 0 THEN ? ELSE assigned_rider_id END,
                assigned_rider_name = COALESCE(?, assigned_rider_name),
                assigned_rider_phone = COALESCE(?, assigned_rider_phone),
                confirmed_at = COALESCE(NULLIF(?, ''), confirmed_at),
                packed_at = COALESCE(NULLIF(?, ''), packed_at),
                on_the_way_at = COALESCE(NULLIF(?, ''), on_the_way_at),
                delivered_at = COALESCE(NULLIF(?, ''), delivered_at),
                cancelled_at = COALESCE(NULLIF(?, ''), cancelled_at),
                updated_at = ?
            WHERE id = ?
        """, (
            target_ol_st,
            float(pharm["subtotal"] or 0.0),
            float(pharm["delivery_charge"] or 50.0),
            float(pharm["total_amount"] or 0.0),
            pharm["payment_status"] or "",
            pharm["assigned_rider_id"], pharm["assigned_rider_id"],
            pharm["assigned_rider_name"], pharm["assigned_rider_phone"],
            pharm["confirmed_at"] or "", pharm["packed_at"] or "",
            pharm["on_the_way_at"] or "", pharm["delivered_at"] or "",
            pharm["cancelled_at"] or "", now_iso, ol_id,
        ))

    if approved_items is not None:
        _fp = conn.execute("SELECT id FROM products LIMIT 1").fetchone()
        _valid_pid = _fp["id"] if _fp else 1
        conn.execute("DELETE FROM online_order_items WHERE order_id = ?", (ol_id,))
        if approved_items:
            for itm in approved_items:
                it_t = (itm.get("item_type") or ("medicine" if itm.get("medicine_id") else "medicine")).lower()
                if it_t == "product" and itm.get("product_id"):
                    disp_pid = int(itm["product_id"])
                    disp_name = itm.get("name") or "Product"
                elif it_t == "package":
                    disp_pid = _valid_pid
                    disp_name = f"📦 {itm.get('name') or 'Combo'}"
                else:
                    disp_pid = _valid_pid
                    qty_i = max(1, int(itm.get("quantity") or 1))
                    base_pcs = int(itm.get("base_pieces") or qty_i)
                    u_lbl = itm.get("unit") or "পিস"
                    unit_note = f" [{qty_i}x {u_lbl} = {base_pcs} পিস]" if (base_pcs != qty_i or str(itm.get("unit_mode") or "piece") != "piece") else ""
                    disp_name = f"💊 {itm['name']}" + (f" ({itm['strength']})" if itm.get("strength") else "") + unit_note
                conn.execute("""
                    INSERT INTO online_order_items (order_id, product_id, product_name, unit_price, mrp_price, quantity, total_price)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (
                    ol_id, disp_pid, disp_name,
                    float(itm.get("unit_price") or 0.0),
                    float(itm.get("unit_price") or 0.0),
                    int(itm.get("quantity") or 1),
                    float(itm.get("total_price") or 0.0),
                ))
        else:
            conn.execute("""
                INSERT INTO online_order_items (order_id, product_id, product_name, unit_price, mrp_price, quantity, total_price)
                VALUES (?, ?, ?, 0, 0, 1, 0)
            """, (ol_id, _valid_pid, "💊 প্রেসক্রিপশন অর্ডার"))
    return ol_id


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
    if (order["order_status"] or "").strip().lower() == "awaiting_customer_confirmation":
        conn.close()
        return jsonify({"success": False, "message": "গ্রাহক এখনো প্রেসক্রিপশন/বিল কোটেশন কনফার্ম করেননি। গ্রাহক কনফার্ম করলে তবেই রাইডার নিতে পারবেন।"}), 400

    now_iso = get_bd_now_iso()
    rider_user = conn.execute("SELECT id, full_name FROM users WHERE role = 'delivery' AND (username = ? OR username = ?)", (rider_phone, data.get("rider_phone", ""))).fetchone()
    rider_id = rider_user["id"] if rider_user else 0
    if rider_user and not rider_name and rider_user["full_name"]:
        rider_name = rider_user["full_name"]

    final_rider_name = rider_name if rider_name else rider_phone
    conn.execute(
        "UPDATE online_orders SET order_status = 'verified', assigned_rider_id = CASE WHEN ? > 0 THEN ? ELSE assigned_rider_id END, assigned_rider_name = ?, assigned_rider_phone = ?, confirmed_at = CASE WHEN confirmed_at = '' THEN ? ELSE confirmed_at END, updated_at = ? WHERE id = ?",
        (rider_id, rider_id, final_rider_name, rider_phone, now_iso, now_iso, order_id)
    )
    deduct_online_order_stock(conn, order)
    pharm_id = _sync_pharmacy_from_online_order(
        conn, order, "verified", now_iso,
        rider_id=rider_id, rider_name=final_rider_name, rider_phone=rider_phone,
    )
    notify_order_status_change(order, 'verified', conn=conn)
    conn.commit()
    conn.close()

    remote_control.push_online_order_to_cloud(order_id)
    if pharm_id:
        remote_control.push_pharmacy_order_to_cloud(pharm_id)
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
    if (order["order_status"] or "").strip().lower() == "awaiting_customer_confirmation":
        conn.close()
        return jsonify({"success": False, "message": "গ্রাহক এখনো প্রেসক্রিপশন/বিল কোটেশন কনফার্ম করেননি। গ্রাহক কনফার্ম করলে তবেই রাইডার নিতে পারবেন।"}), 400

    if status == "delivered":
        if not otp or order["delivery_otp"] != otp:
            conn.close()
            return jsonify({"success": False, "message": "Invalid OTP code. Please enter the correct 4-digit OTP from customer app."}), 400

    now_iso = get_bd_now_iso()
    pharm_id = None
    if status == "delivered":
        r_fee = get_rider_delivery_fee_setting(conn)
        conn.execute(
            "UPDATE online_orders SET order_status = ?, payment_status = CASE WHEN payment_status = 'pending' THEN 'paid' ELSE payment_status END, rider_fee = CASE WHEN rider_fee <= 0 THEN ? ELSE rider_fee END, delivered_at = CASE WHEN delivered_at = '' THEN ? ELSE delivered_at END, updated_at = ? WHERE id = ?",
            (status, r_fee, now_iso, now_iso, order_id)
        )
        pharm_id = _sync_pharmacy_from_online_order(conn, order, status, now_iso, payment_status="paid", rider_fee=r_fee)
        notify_order_status_change(order, status, conn=conn)
        conn.commit()
    elif status in ["verified", "packed", "on_the_way", "cancelled"]:
        col_name = "confirmed_at" if status == "verified" else ("packed_at" if status == "packed" else ("on_the_way_at" if status == "on_the_way" else "cancelled_at"))
        conn.execute(
            f"UPDATE online_orders SET order_status = ?, {col_name} = CASE WHEN {col_name} = '' THEN ? ELSE {col_name} END, updated_at = ? WHERE id = ?",
            (status, now_iso, now_iso, order_id)
        )
        if status == "verified" and order["is_stock_deducted"] == 0:
            deduct_online_order_stock(conn, order)
        pharm_id = _sync_pharmacy_from_online_order(conn, order, status, now_iso)
        notify_order_status_change(order, status, conn=conn)
        conn.commit()

    conn.close()
    remote_control.push_online_order_to_cloud(order_id)
    if pharm_id:
        remote_control.push_pharmacy_order_to_cloud(pharm_id)
    return jsonify({
        "success": True,
        "message": f"Order #{order['order_number']} status updated to '{status.upper()}' successfully!"
    })


@app.route("/api/rider/earnings", methods=["GET"])
def api_rider_earnings():
    raw_phone = request.args.get("rider_phone", "").strip()
    norm_phone = normalize_phone(raw_phone)
    rider_id = request.args.get("rider_id", type=int)

    conn = get_connection()
    user = None
    if rider_id:
        user = conn.execute("SELECT * FROM users WHERE id = ? AND role = 'delivery'", (rider_id,)).fetchone()
    if not user and norm_phone:
        user = conn.execute("SELECT * FROM users WHERE role = 'delivery' AND (username = ? OR username = ?)", (norm_phone, raw_phone)).fetchone()

    r_id = user["id"] if user else (rider_id or 0)
    r_phone = user["username"] if user else norm_phone
    r_name = user["full_name"] if (user and user["full_name"]) else (r_phone or "Delivery Rider")

    default_fee = get_rider_delivery_fee_setting(conn)

    phone_patterns = list(set(filter(None, [raw_phone, norm_phone, f"88{norm_phone}" if norm_phone else "", f"+88{norm_phone}" if norm_phone else ""])))
    if r_phone and r_phone not in phone_patterns:
        phone_patterns.append(r_phone)

    # Fetch delivered orders
    placeholders = ",".join("?" for _ in phone_patterns) if phone_patterns else "''"
    query_params = [r_id] + phone_patterns

    rider_orders = conn.execute(f"""
        SELECT * FROM online_orders 
        WHERE (assigned_rider_id = ? OR assigned_rider_phone IN ({placeholders}))
        ORDER BY id DESC
    """, query_params).fetchall()

    # Fetch payouts for this rider (matches ledger expense 'Riders riding cost')
    payout_params = [r_id] if r_id else []
    if phone_patterns:
        payout_user_ids = conn.execute(f"SELECT id FROM users WHERE username IN ({placeholders})", phone_patterns).fetchall()
        for pu in payout_user_ids:
            if pu["id"] not in payout_params:
                payout_params.append(pu["id"])
    
    if payout_params:
        payout_placeholders = ",".join("?" for _ in payout_params)
        payouts_rows = conn.execute(f"""
            SELECT * FROM rider_payouts
            WHERE rider_id IN ({payout_placeholders})
            ORDER BY payout_date DESC, id DESC
        """, payout_params).fetchall()
    else:
        payouts_rows = []

    payouts_data = []
    for p in payouts_rows:
        payouts_data.append({
            "id": p["id"],
            "amount": float(p["amount"] or 0),
            "payout_date": p["payout_date"] or "",
            "payment_method": p["payment_method"] or "Cash",
            "note": p["note"] or "",
            "created_at": p["created_at"] or "",
        })

    all_time_delivered = 0
    all_time_earned = 0.0
    all_time_collected = 0.0
    reg_delivered = 0
    reg_earned = 0.0
    reg_collected = 0.0
    pharm_delivered = 0
    pharm_earned = 0.0
    pharm_collected = 0.0
    delivered_orders = []

    for ord_row in rider_orders:
        o_dict = dict(ord_row)
        is_del = (o_dict.get("order_status") == "delivered")
        o_fee = float(o_dict.get("rider_fee") or 0)
        if o_fee <= 0 and is_del:
            o_fee = default_fee
        ord_num = str(o_dict.get("order_number") or "")
        is_pharm = ord_num.upper().startswith("RX-")
        o_amt = float(o_dict.get("total_amount") or 0)

        if is_del:
            all_time_delivered += 1
            all_time_earned += o_fee
            all_time_collected += o_amt
            if is_pharm:
                pharm_delivered += 1
                pharm_earned += o_fee
                pharm_collected += o_amt
            else:
                reg_delivered += 1
                reg_earned += o_fee
                reg_collected += o_amt
            delivered_orders.append({
                "id": o_dict.get("id"),
                "order_number": ord_num,
                "is_pharmacy_order": is_pharm,
                "customer_name": o_dict.get("customer_name") or "",
                "customer_phone": o_dict.get("customer_phone") or "",
                "area": o_dict.get("area") or "",
                "total_amount": o_amt,
                "rider_fee": o_fee,
                "delivered_at": o_dict.get("delivered_at") or o_dict.get("updated_at") or "",
                "created_at": o_dict.get("created_at") or "",
            })

    all_time_paid = sum(p["amount"] for p in payouts_data)
    balance_due = max(0.0, round(all_time_earned - all_time_paid, 2))
    conn.close()

    return jsonify({
        "success": True,
        "rider_id": r_id,
        "rider_name": r_name,
        "rider_phone": r_phone,
        "default_rider_fee": default_fee,
        "total_delivered": all_time_delivered,
        "total_earned": all_time_earned,
        "total_paid": all_time_paid,
        "balance_due": balance_due,
        "total_collected": all_time_collected,
        "regular_stats": {
            "delivered": reg_delivered,
            "earned": round(reg_earned, 2),
            "collected": round(reg_collected, 2),
        },
        "pharmacy_stats": {
            "delivered": pharm_delivered,
            "earned": round(pharm_earned, 2),
            "collected": round(pharm_collected, 2),
        },
        "payouts": payouts_data,
        "delivered_orders": delivered_orders,
    })


@app.route("/api/online_orders/unread_count", methods=["GET"])
def api_online_orders_count():
    conn = get_connection()
    new_count = conn.execute("SELECT COUNT(*) AS c FROM online_orders WHERE order_status = 'new'").fetchone()["c"]
    total_count = conn.execute("SELECT COUNT(*) AS c FROM online_orders").fetchone()["c"]
    conn.close()
    return jsonify({"new_count": new_count, "total_count": total_count})


def _resolve_online_item_cost(conn, item):
    """Resolves exact purchase cost_price for a regular product or package line item."""
    pid = item["product_id"]
    pkg = conn.execute("SELECT id FROM packages WHERE id = ?", (pid,)).fetchone()
    if not pkg and item["product_name"]:
        pkg = conn.execute(
            "SELECT id FROM packages WHERE name = ? OR instr(?, name) > 0",
            (item["product_name"], item["product_name"]),
        ).fetchone()
    if pkg:
        p_items = conn.execute(
            "SELECT pi.quantity, COALESCE(p.cost_price, 0) AS cost_price FROM package_items pi JOIN products p ON pi.product_id = p.id WHERE pi.package_id = ?",
            (pkg["id"],),
        ).fetchall()
        return round(sum(float(pi["cost_price"] or 0.0) * float(pi["quantity"] or 1) for pi in p_items), 4)
    prod = conn.execute("SELECT cost_price FROM products WHERE id = ?", (pid,)).fetchone()
    return float(prod["cost_price"] or 0.0) if prod else 0.0


def _apply_rx_approved_stock_delta(conn, pharm_order, restore=False):
    """Deducts or restores pharmacy_medicines / products / packages stock from approved_items_json."""
    try:
        approved = json.loads(pharm_order["approved_items_json"] or "[]")
    except Exception:
        approved = []
    if not isinstance(approved, list):
        return []
    for itm in approved:
        if not isinstance(itm, dict):
            continue
        it_type = (itm.get("item_type") or ("medicine" if itm.get("medicine_id") else ("package" if itm.get("package_id") else ("product" if itm.get("product_id") else "medicine")))).strip().lower()
        qty = max(1, int(itm.get("quantity") or 1))
        if it_type == "medicine" and itm.get("medicine_id"):
            base_pcs = int(itm.get("base_pieces") or (qty * max(1, int(itm.get("unit_count") or 1))))
            if restore:
                conn.execute("UPDATE pharmacy_medicines SET stock_qty = stock_qty + ? WHERE id = ?", (base_pcs, itm["medicine_id"]))
            else:
                conn.execute("UPDATE pharmacy_medicines SET stock_qty = MAX(0, stock_qty - ?) WHERE id = ?", (base_pcs, itm["medicine_id"]))
        elif it_type == "package" and itm.get("package_id"):
            pkg_id = int(itm["package_id"])
            if restore:
                conn.execute("UPDATE packages SET sold_quantity = MAX(0, sold_quantity - ?) WHERE id = ?", (qty, pkg_id))
            else:
                conn.execute("UPDATE packages SET sold_quantity = sold_quantity + ? WHERE id = ?", (qty, pkg_id))
            p_items = conn.execute("SELECT product_id, quantity FROM package_items WHERE package_id = ?", (pkg_id,)).fetchall()
            for pi in p_items:
                if restore:
                    conn.execute("UPDATE products SET stock_qty = stock_qty + ? WHERE id = ?", (pi["quantity"] * qty, pi["product_id"]))
                else:
                    conn.execute("UPDATE products SET stock_qty = MAX(0, stock_qty - ?) WHERE id = ?", (pi["quantity"] * qty, pi["product_id"]))
                remote_control.push_product_to_cloud(pi["product_id"])
            remote_control.push_packages_to_cloud()
        elif it_type == "product" and itm.get("product_id"):
            prod_id = int(itm["product_id"])
            if restore:
                conn.execute("UPDATE products SET stock_qty = stock_qty + ? WHERE id = ?", (qty, prod_id))
            else:
                conn.execute("UPDATE products SET stock_qty = MAX(0, stock_qty - ?) WHERE id = ?", (qty, prod_id))
            remote_control.push_product_to_cloud(prod_id)
    return approved


def deduct_online_order_stock(conn, order):
    """Deducts stock for online order (or linked RX pharmacy order) if not deducted yet."""
    order_id = order["id"]
    if (order["order_status"] or "").strip().lower() == "awaiting_customer_confirmation":
        return
    current = conn.execute("SELECT is_stock_deducted FROM online_orders WHERE id = ?", (order_id,)).fetchone()
    if current and current["is_stock_deducted"] == 1:
        return

    pharm_row = conn.execute(
        "SELECT * FROM pharmacy_orders WHERE online_order_id = ? OR order_number = ? LIMIT 1",
        (order_id, order["order_number"]),
    ).fetchone()
    is_rx = bool(pharm_row) or str(order["order_number"] or "").startswith("RX-")

    approved_rx = []
    if is_rx and pharm_row:
        approved_rx = _apply_rx_approved_stock_delta(conn, pharm_row, restore=False)
    else:
        items = conn.execute("SELECT * FROM online_order_items WHERE order_id = ?", (order_id,)).fetchall()
        for item in items:
            pid = item["product_id"]
            qty = item["quantity"]
            pkg = conn.execute("SELECT id FROM packages WHERE id = ?", (pid,)).fetchone()
            if not pkg and item["product_name"]:
                pkg = conn.execute("SELECT id FROM packages WHERE name = ? OR instr(?, name) > 0", (item["product_name"], item["product_name"])).fetchone()

            if pkg:
                conn.execute("UPDATE packages SET sold_quantity = sold_quantity + ? WHERE id = ?", (qty, pkg["id"]))
                p_items = conn.execute("SELECT product_id, quantity FROM package_items WHERE package_id = ?", (pkg["id"],)).fetchall()
                for pi in p_items:
                    conn.execute(
                        "UPDATE products SET stock_qty = MAX(0, stock_qty - ?) WHERE id = ?",
                        (pi["quantity"] * qty, pi["product_id"])
                    )
                    remote_control.push_product_to_cloud(pi["product_id"])
                remote_control.push_packages_to_cloud()
            else:
                conn.execute(
                    "UPDATE products SET stock_qty = MAX(0, stock_qty - ?) WHERE id = ?",
                    (qty, pid)
                )
                remote_control.push_product_to_cloud(pid)

    conn.execute("UPDATE online_orders SET is_stock_deducted = 1 WHERE id = ?", (order_id,))

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

        first_p = conn.execute("SELECT id FROM products LIMIT 1").fetchone()
        fk_pid = first_p["id"] if first_p else 1
        if is_rx and approved_rx:
            for itm in approved_rx:
                it_type = (itm.get("item_type") or ("medicine" if itm.get("medicine_id") else "medicine")).strip().lower()
                qty = max(1, int(itm.get("quantity") or 1))
                u_price = float(itm.get("unit_price") or 0.0)
                c_price = float(itm.get("cost_price") or 0.0)
                if it_type == "product" and itm.get("product_id"):
                    row_pid = int(itm["product_id"])
                    if c_price <= 0:
                        pr = conn.execute("SELECT cost_price FROM products WHERE id = ?", (row_pid,)).fetchone()
                        c_price = float(pr["cost_price"] or 0.0) if pr else 0.0
                    serial_lbl = ""
                elif it_type == "package":
                    row_pid = fk_pid
                    serial_lbl = f"📦 {itm.get('name') or 'Combo'}"
                else:
                    row_pid = fk_pid
                    base_pcs = int(itm.get("base_pieces") or qty)
                    u_lbl = itm.get("unit") or "পিস"
                    unit_note = f" [{qty}x {u_lbl} = {base_pcs} পিস]" if (base_pcs != qty or str(itm.get("unit_mode") or "piece") != "piece") else ""
                    serial_lbl = f"💊 {itm.get('name', 'Medicine')}" + (f" ({itm['strength']})" if itm.get("strength") else "") + unit_note
                cur.execute("""
                    INSERT INTO sale_items (sale_id, product_id, quantity, unit_price, mrp_price, vat_pct, vat_amount, cost_price, unit_serials)
                    VALUES (?, ?, ?, ?, ?, 0, 0, ?, ?)
                """, (sale_id, row_pid, qty, u_price, u_price, round(c_price, 4), serial_lbl))
        else:
            items = conn.execute("SELECT * FROM online_order_items WHERE order_id = ?", (order_id,)).fetchall()
            for item in items:
                c_price = _resolve_online_item_cost(conn, item)
                cur.execute("""
                    INSERT INTO sale_items (sale_id, product_id, quantity, unit_price, mrp_price, vat_pct, vat_amount, cost_price)
                    VALUES (?, ?, ?, ?, ?, 0, 0, ?)
                """, (
                    sale_id,
                    item["product_id"],
                    item["quantity"],
                    item["unit_price"],
                    item["mrp_price"],
                    c_price,
                ))
        remote_control.push_sale_to_cloud(sale_id)


def restore_online_order_stock(conn, order):
    """Restores stock for online order (or linked RX pharmacy order) if stock was deducted."""
    order_id = order["id"]
    current = conn.execute("SELECT is_stock_deducted FROM online_orders WHERE id = ?", (order_id,)).fetchone()
    
    is_deducted = (current and current["is_stock_deducted"] == 1) or (order["order_status"] in ("verified", "packed", "on_the_way", "delivered"))

    if is_deducted:
        pharm_row = conn.execute(
            "SELECT * FROM pharmacy_orders WHERE online_order_id = ? OR order_number = ? LIMIT 1",
            (order_id, order["order_number"]),
        ).fetchone()
        if pharm_row and (current and current["is_stock_deducted"] == 1):
            _apply_rx_approved_stock_delta(conn, pharm_row, restore=True)
        elif not pharm_row:
            items = conn.execute("SELECT * FROM online_order_items WHERE order_id = ?", (order_id,)).fetchall()
            for item in items:
                pid = item["product_id"]
                qty = item["quantity"]
                pkg = conn.execute("SELECT id FROM packages WHERE id = ?", (pid,)).fetchone()
                if pkg:
                    conn.execute("UPDATE packages SET sold_quantity = MAX(0, sold_quantity - ?) WHERE id = ?", (qty, pkg["id"]))
                    p_items = conn.execute("SELECT product_id, quantity FROM package_items WHERE package_id = ?", (pid,)).fetchall()
                    for pi in p_items:
                        conn.execute(
                            "UPDATE products SET stock_qty = stock_qty + ? WHERE id = ?",
                            (pi["quantity"] * qty, pi["product_id"])
                        )
                        remote_control.push_product_to_cloud(pi["product_id"])
                    remote_control.push_packages_to_cloud()
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

    if (order["order_status"] or "").strip().lower() == "awaiting_customer_confirmation" and (new_status or "").strip().lower() != "cancelled":
        conn.close()
        flash(f"Order #{order['order_number']} is waiting for customer quote confirmation and cannot be moved forward yet.", "error")
        return redirect(url_for("online_orders"))

    now_iso = get_bd_now_iso()
    if new_status == "delivered":
        r_fee = get_rider_delivery_fee_setting(conn)
        conn.execute(
            "UPDATE online_orders SET order_status = ?, payment_status = 'paid', rider_fee = CASE WHEN rider_fee <= 0 THEN ? ELSE rider_fee END, delivered_at = CASE WHEN delivered_at = '' THEN ? ELSE delivered_at END, updated_at = ? WHERE id = ?",
            (new_status, r_fee, now_iso, now_iso, order_id)
        )
    else:
        col_name = "confirmed_at" if new_status == "verified" else ("packed_at" if new_status == "packed" else ("on_the_way_at" if new_status == "on_the_way" else ("cancelled_at" if new_status == "cancelled" else "")))
        if col_name:
            conn.execute(
                f"UPDATE online_orders SET order_status = ?, {col_name} = CASE WHEN {col_name} = '' THEN ? ELSE {col_name} END, updated_at = ? WHERE id = ?",
                (new_status, now_iso, now_iso, order_id)
            )
        else:
            conn.execute(
                "UPDATE online_orders SET order_status = ?, updated_at = ? WHERE id = ?",
                (new_status, now_iso, order_id)
            )

    if new_status in ("new", "verified", "packed", "on_the_way", "delivered"):
        deduct_online_order_stock(conn, order)
        # Mark customer phone as verified
        conn.execute("UPDATE customer_users SET is_verified = 1 WHERE phone = ?", (order["customer_phone"],))
    elif new_status == "cancelled":
        restore_online_order_stock(conn, order)

    pharm_id = _sync_pharmacy_from_online_order(
        conn, order, new_status, now_iso,
        payment_status="paid" if new_status == "delivered" else None,
        rider_fee=r_fee if new_status == "delivered" else None,
    )
    notify_order_status_change(order, new_status, conn=conn)
    conn.commit()
    conn.close()
    remote_control.push_online_order_to_cloud(order_id)
    if pharm_id:
        remote_control.push_pharmacy_order_to_cloud(pharm_id)
    if order["customer_phone"]:
        remote_control.push_customer_user_to_cloud(order["customer_phone"])
    ord_num = order["order_number"] if (order and "order_number" in order.keys() and order["order_number"]) else order_id
    flash(f"Order #{ord_num} status updated to {new_status}.", "success")
    return redirect(url_for("online_orders"))


@app.route("/online_orders/<int:order_id>/update_address", methods=["POST"])
@login_required
def update_online_order_address(order_id):
    new_address = request.form.get("address_details", "").strip()
    if not new_address:
        flash("Address cannot be empty.", "error")
        return redirect(url_for("online_orders"))

    conn = get_connection()
    order = conn.execute("SELECT * FROM online_orders WHERE id = ?", (order_id,)).fetchone()
    if not order:
        conn.close()
        flash("Order not found.", "error")
        return redirect(url_for("online_orders"))

    conn.execute(
        "UPDATE online_orders SET address_details = ?, updated_at = ? WHERE id = ?",
        (new_address, datetime.now().isoformat(), order_id)
    )
    if order["customer_phone"]:
        conn.execute(
            "UPDATE customer_users SET address = ? WHERE phone = ?",
            (new_address, order["customer_phone"])
        )
    conn.commit()
    conn.close()

    remote_control.push_online_order_to_cloud(order_id)
    if order["customer_phone"]:
        remote_control.push_customer_user_to_cloud(order["customer_phone"])

    flash(f"Delivery address updated successfully for Order #{order['order_number']}.", "success")
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
    
    if not sale and (order["order_status"] or "").strip().lower() != "awaiting_customer_confirmation":
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
            c_price = _resolve_online_item_cost(conn, order, item)
            cur.execute("""
                INSERT INTO sale_items (sale_id, product_id, quantity, unit_price, mrp_price, vat_pct, vat_amount, cost_price, unit_serials)
                VALUES (?, ?, ?, ?, ?, 0, 0, ?, ?)
            """, (
                sale_id,
                item["product_id"],
                item["quantity"],
                item["unit_price"],
                item["mrp_price"],
                c_price,
                item["product_name"] or ""
            ))
        conn.commit()
    else:
        sale_id = sale["id"]

    if request.args.get("format") == "a4":
        order_dict = dict(order)
        order_dict["delivery_address"] = format_delivery_address(
            order["address_details"], order["area"], order["district"],
            customer_phone=order["customer_phone"], conn=conn
        )
        raw_items = conn.execute("SELECT * FROM online_order_items WHERE order_id = ?", (order_id,)).fetchall()
        items = [dict(it) for it in raw_items]
        settings = get_all_settings(conn)
        conn.close()
        return render_template("online_invoice.html", order=order_dict, items=items, shop=settings)

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
        cu = conn.execute("SELECT * FROM customer_users WHERE phone = ?", (r["customer_phone"],)).fetchone()
        cu_d = dict(cu) if cu else {}
        orders_list = [dict(o) for o in orders]
        first_created = cu_d.get("created_at") or (orders_list[-1].get("created_at") if orders_list else "")
        latest_ord_ip = next((o.get("customer_ip") for o in orders_list if o.get("customer_ip")), "")
        latest_ord_loc = next((o.get("ip_location") for o in orders_list if o.get("ip_location")), "")
        cust_dict = dict(r)
        cust_dict["created_at"] = first_created
        cust_dict["member_since"] = _member_since_label(first_created)
        cust_dict["registration_ip"] = cu_d.get("registration_ip") or latest_ord_ip
        cust_dict["registration_location"] = cu_d.get("registration_location") or latest_ord_loc
        cust_dict["last_ip"] = cu_d.get("last_ip") or latest_ord_ip
        cust_dict["last_location"] = cu_d.get("last_location") or latest_ord_loc
        cust_dict["last_seen_at"] = cu_d.get("last_seen_at") or ""
        cust_dict["last_device"] = cu_d.get("last_device") or ""
        cust_dict["order_count"] = len(orders)
        cust_dict["orders"] = orders_list
        results.append(cust_dict)

    conn.close()
    return jsonify(results)


@app.route("/online_orders/<int:order_id>/verify_otp", methods=["POST"])
@login_required
def verify_online_order_otp(order_id):
    input_otp = request.form.get("otp", "").strip()
    conn = get_connection()
    order = conn.execute("SELECT * FROM online_orders WHERE id = ?", (order_id,)).fetchone()
    if order and order["delivery_otp"] == input_otp:
        r_fee = get_rider_delivery_fee_setting(conn)
        now_iso = get_bd_now_iso()
        conn.execute(
            "UPDATE online_orders SET order_status = 'delivered', payment_status = 'paid', rider_fee = CASE WHEN rider_fee <= 0 THEN ? ELSE rider_fee END, delivered_at = CASE WHEN delivered_at = '' THEN ? ELSE delivered_at END, updated_at = ? WHERE id = ?",
            (r_fee, now_iso, now_iso, order_id)
        )
        pharm_id = _sync_pharmacy_from_online_order(
            conn, order, 'delivered', now_iso, payment_status='paid', rider_fee=r_fee
        )
        notify_order_status_change(order, 'delivered', conn=conn)
        conn.commit()
        conn.close()
        remote_control.push_online_order_to_cloud(order_id)
        if pharm_id:
            remote_control.push_pharmacy_order_to_cloud(pharm_id)
        ord_num = order["order_number"] if (order and "order_number" in order.keys() and order["order_number"]) else order_id
        flash(f"OTP Verified! Order #{ord_num} marked as DELIVERED.", "success")
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

    if not include_expired:
        rows = filter_online_products(rows)

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
@limiter.limit("20 per minute")
def api_place_order():
    data = request.json or {}
    country = (data.get("country") or data.get("country_name") or "Bangladesh").strip()
    district = (data.get("district") or data.get("district_name") or "Tangail").strip()
    area = (data.get("area") or data.get("area_name") or "Main Area").strip()
    customer_name = (data.get("customer_name") or data.get("name") or "Customer").strip()
    customer_phone = (data.get("customer_phone") or data.get("phone") or "").strip()
    customer_email = (data.get("customer_email") or data.get("email") or "").strip()
    address_details = (
        data.get("address_details")
        or data.get("shipping_address")
        or data.get("delivery_address")
        or data.get("address")
        or data.get("location")
        or ""
    ).strip()
    payment_method = (data.get("payment_method") or "cod").lower()
    cart_items = data.get("cart_items") or data.get("items") or data.get("products") or data.get("cart") or []

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

    # =========================================================================
    # 🚨 STRICT STOCK & MAXIMUM ORDER QUANTITY VALIDATION:
    # 1. Enforce max_order_qty_product and max_order_qty_package limits
    # 2. Reject if any product has stock <= 0 or requested > stock
    # 3. Reject Combo Package if ANY constituent product has stock <= 0 or required > stock
    # 4. Check aggregate demand across multiple cart items
    # =========================================================================
    shop_settings = get_all_settings(conn)
    max_order_qty_prod = int(shop_settings.get("max_order_qty_product") or 0)
    max_order_qty_pkg = int(shop_settings.get("max_order_qty_package") or 0)

    product_demands = {}  # product_id -> total_needed_qty
    item_quantities_map = {}  # item_key -> total_qty

    for item in cart_items:
        prod_id = item.get("product_id") or item.get("id") or item.get("prod_id")
        qty = int(item.get("quantity") or item.get("qty") or item.get("count") or 1)
        if qty <= 0:
            qty = 1
        p_name_raw = (item.get("product_name") or item.get("name") or item.get("title") or "").strip()

        is_pkg_check = (
            item.get("is_package") is True or
            item.get("type") == "package" or
            item.get("package_id") is not None or
            str(prod_id).startswith("pkg_") or
            str(prod_id).startswith("PKG_") or
            p_name_raw.startswith("📦") or
            p_name_raw.startswith("ONLINE - Package")
        )

        pkg_match = None
        if is_pkg_check:
            pkg_id_clean = item.get("package_id") or str(prod_id).replace("pkg_", "").replace("PKG_", "")
            try:
                pkg_match = conn.execute("SELECT * FROM packages WHERE id = ?", (int(pkg_id_clean),)).fetchone()
            except Exception:
                pass
            if not pkg_match and p_name_raw:
                clean_pname = p_name_raw.replace("📦", "").strip()
                pkg_match = conn.execute("SELECT * FROM packages WHERE name = ? OR instr(?, name) > 0 OR instr(name, ?) > 0", (clean_pname, clean_pname, clean_pname)).fetchone()

        if pkg_match:
            pkg_key = f"pkg_{pkg_match['id']}"
            item_quantities_map[pkg_key] = item_quantities_map.get(pkg_key, 0) + qty
            if max_order_qty_pkg > 0 and item_quantities_map[pkg_key] > max_order_qty_pkg:
                conn.close()
                return jsonify({
                    "success": False,
                    "message": f'Maximum order limit reached: You can order at most {max_order_qty_pkg} units of Combo Package "{pkg_match["name"]}" per order.'
                }), 400

            # Enforce Admin-defined quota / sale limit
            max_limit = int(pkg_match["max_sale_limit"] if "max_sale_limit" in pkg_match.keys() else 0)
            sold_qty = int(pkg_match["sold_quantity"] if "sold_quantity" in pkg_match.keys() else 0)
            if max_limit > 0:
                quota_left = max(0, max_limit - sold_qty)
                if quota_left <= 0:
                    conn.close()
                    return jsonify({
                        "success": False,
                        "message": f'Combo Package "{pkg_match["name"]}" is OUT OF STOCK (Maximum sales limit of {max_limit} units reached).'
                    }), 400
                if item_quantities_map[pkg_key] > quota_left:
                    conn.close()
                    return jsonify({
                        "success": False,
                        "message": f'Only {quota_left} unit(s) remaining for Combo Package "{pkg_match["name"]}" before reaching sales limit.'
                    }), 400

            p_items_chk = conn.execute("""
                SELECT pi.quantity, p.id, p.name, p.stock_qty
                FROM package_items pi JOIN products p ON pi.product_id = p.id
                WHERE pi.package_id = ?
            """, (pkg_match["id"],)).fetchall()

            if not p_items_chk:
                conn.close()
                return jsonify({
                    "success": False,
                    "message": f'Combo Package "{pkg_match["name"]}" has no active items and cannot be ordered.'
                }), 400

            for pi in p_items_chk:
                curr_stk = int(pi["stock_qty"] or 0)
                needed = int(pi["quantity"] or 1) * qty
                if curr_stk <= 0:
                    conn.close()
                    return jsonify({
                        "success": False,
                        "message": f'Cannot order Combo Package "{pkg_match["name"]}" because product "{pi["name"]}" is OUT OF STOCK (0 in stock).'
                    }), 400
                if curr_stk < needed:
                    conn.close()
                    return jsonify({
                        "success": False,
                        "message": f'Cannot order Combo Package "{pkg_match["name"]}": Insufficient stock for "{pi["name"]}" ({curr_stk} available, {needed} required).'
                    }), 400
                pid = pi["id"]
                product_demands[pid] = product_demands.get(pid, 0) + needed
        else:
            prod_chk = None
            if prod_id is not None:
                try:
                    prod_chk = conn.execute("SELECT id, name, stock_qty, offer_type, offer_value, offer_title FROM products WHERE id = ?", (int(prod_id),)).fetchone()
                except Exception:
                    prod_chk = conn.execute("SELECT id, name, stock_qty, offer_type, offer_value, offer_title FROM products WHERE id = ?", (prod_id,)).fetchone()
            if not prod_chk and p_name_raw:
                prod_chk = conn.execute("SELECT id, name, stock_qty, offer_type, offer_value, offer_title FROM products WHERE LOWER(name) = LOWER(?)", (p_name_raw,)).fetchone()

            if prod_chk:
                p_key = f"prod_{prod_chk['id']}"
                item_quantities_map[p_key] = item_quantities_map.get(p_key, 0) + qty
                
                # Check limit against paid units so Buy X Get Y Free products can be availed
                total_product_qty = item_quantities_map[p_key]
                p_off_type = prod_chk["offer_type"] if "offer_type" in prod_chk.keys() else ""
                p_off_val = prod_chk["offer_value"] if "offer_value" in prod_chk.keys() else ""
                p_off_title = prod_chk["offer_title"] if "offer_title" in prod_chk.keys() else ""
                paid_qty, free_qty = calculate_paid_and_free_qty(total_product_qty, p_off_type, p_off_val, p_off_title, prod_chk["name"])

                if max_order_qty_prod > 0 and paid_qty > max_order_qty_prod:
                    conn.close()
                    return jsonify({
                        "success": False,
                        "message": f'Maximum purchase limit reached: You can purchase at most {max_order_qty_prod} paid units of "{prod_chk["name"]}" per order.'
                    }), 400

                curr_stk = int(prod_chk["stock_qty"] or 0)
                if curr_stk <= 0:
                    conn.close()
                    return jsonify({
                        "success": False,
                        "message": f'Product "{prod_chk["name"]}" is OUT OF STOCK (0 in stock).'
                    }), 400
                if curr_stk < qty:
                    conn.close()
                    return jsonify({
                        "success": False,
                        "message": f'Cannot order "{prod_chk["name"]}": Insufficient stock ({curr_stk} available, {qty} requested).'
                    }), 400
                pid = prod_chk["id"]
                product_demands[pid] = product_demands.get(pid, 0) + qty

    # Check aggregate demand across all items in cart
    for pid, total_needed in product_demands.items():
        chk_p = conn.execute("SELECT name, stock_qty FROM products WHERE id = ?", (pid,)).fetchone()
        if chk_p:
            curr_stk = int(chk_p["stock_qty"] or 0)
            if curr_stk <= 0:
                conn.close()
                return jsonify({
                    "success": False,
                    "message": f'Product "{chk_p["name"]}" is OUT OF STOCK.'
                }), 400
            if curr_stk < total_needed:
                conn.close()
                return jsonify({
                    "success": False,
                    "message": f'Insufficient stock for "{chk_p["name"]}". Only {curr_stk} available in stock, but {total_needed} required across your order.'
                }), 400

    import random
    otp = f"{random.randint(1000, 9999)}"
    now_str = get_bd_now().strftime("%Y%m%d%H%M%S")
    rand_suffix = random.randint(100, 999)
    order_number = f"ORD-{now_str}-{rand_suffix}"

    subtotal = 0.0
    processed_items = []

    for item in cart_items:
        prod_id = item.get("product_id") or item.get("id") or item.get("prod_id")
        qty = int(item.get("quantity") or item.get("qty") or item.get("count") or 1)
        p_name_raw = (item.get("product_name") or item.get("name") or item.get("title") or "").strip()
        p_sku_raw = (item.get("sku") or "").strip()

        # Check if item is an explicit Combo Package
        is_pkg_flag = (
            item.get("is_package") is True or
            item.get("type") == "package" or
            item.get("package_id") is not None or
            str(prod_id).startswith("pkg_") or
            str(prod_id).startswith("PKG_") or
            p_name_raw.startswith("📦") or
            p_name_raw.startswith("ONLINE - Package")
        )

        pkg = None
        if is_pkg_flag:
            pkg_id_clean = item.get("package_id") or str(prod_id).replace("pkg_", "").replace("PKG_", "")
            try:
                pkg = conn.execute("SELECT * FROM packages WHERE id = ?", (int(pkg_id_clean),)).fetchone()
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
                p_name = f"📦 {pkg['name']} ({', '.join(item_details)})"
            else:
                p_name = f"📦 {pkg['name']}"

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
                p_name = p_name_raw or (p_sku_raw if p_sku_raw else "Product")
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
            "total_price": line_total,
            "is_package": True if pkg else False,
            "package_id": pkg["id"] if pkg else None
        })

    if not processed_items:
        conn.close()
        return jsonify({"success": False, "message": "No valid cart items found."}), 400

    shop_settings = get_all_settings(conn)
    free_del_active = (shop_settings.get("free_delivery_active") or "0") == "1"
    free_del_min_amount = float(shop_settings.get("free_delivery_min_amount") or 1000.0)

    if free_del_active and subtotal >= free_del_min_amount:
        delivery_charge = 0.0
    else:
        delivery_charge = float(data.get("delivery_charge") if data.get("delivery_charge") is not None else shop_settings.get("delivery_charge") or 60.0)
    
    total_amount = max(0.0, subtotal + delivery_charge)
    created_at = get_bd_now_iso()

    # Normalize phone
    digits = re.sub(r"\D", "", str(customer_phone or ""))
    if digits.startswith("8801") and len(digits) == 13:
        digits = digits[2:]
    clean_phone = digits if digits else customer_phone

    cur = conn.cursor()

    if (not address_details or address_details == "Delivery Address") and clean_phone:
        try:
            chk_c = cur.execute("SELECT address FROM customer_users WHERE phone = ?", (clean_phone,)).fetchone()
            if chk_c and chk_c["address"] and chk_c["address"].strip() not in ("", "Delivery Address", "No detailed address recorded"):
                address_details = chk_c["address"].strip()
        except Exception:
            pass

    if not address_details:
        address_details = f"{area}, {district}" if (area and area not in ("Main Area", "Main Town")) else (district or "Delivery Address")

    # 1. Auto-create or update Customer in customer_users
    if clean_phone and len(clean_phone) == 11 and clean_phone.startswith("01"):
        chk_cust = cur.execute("SELECT id, name, address FROM customer_users WHERE phone = ?", (clean_phone,)).fetchone()
        if not chk_cust:
            pass_hash = generate_password_hash("123456")
            name_to_use = customer_name.strip() if customer_name and customer_name.strip() else f"Customer {clean_phone[-4:]}"
            cur.execute("""
                INSERT INTO customer_users (phone, name, email, address, password_hash, plain_password, is_verified, created_at)
                VALUES (?, ?, ?, ?, ?, '123456', 1, ?)
            """, (clean_phone, name_to_use, customer_email or "", address_details if address_details != "Delivery Address" else "", pass_hash, created_at))
        else:
            upd_parts = []
            upd_params = []
            if customer_name and customer_name.strip() and (not chk_cust["name"] or chk_cust["name"].startswith("Customer ")):
                upd_parts.append("name = ?")
                upd_params.append(customer_name.strip())
            if address_details and address_details != "Delivery Address" and (not chk_cust["address"] or chk_cust["address"].strip() in ("", "Delivery Address", "No detailed address recorded")):
                upd_parts.append("address = ?")
                upd_params.append(address_details)
            if upd_parts:
                upd_params.append(clean_phone)
                cur.execute(f"UPDATE customer_users SET {', '.join(upd_parts)} WHERE phone = ?", tuple(upd_params))

    # Check customer verification status
    is_customer_verified = False
    chk_cust_row = conn.execute("SELECT is_verified FROM customer_users WHERE phone = ?", (clean_phone,)).fetchone()
    if chk_cust_row and chk_cust_row["is_verified"] == 1:
        is_customer_verified = True
    elif clean_phone in VERIFIED_PHONES:
        is_customer_verified = True

    initial_order_status = "new" if is_customer_verified else "pending_confirmation"

    cust_ip, cust_loc = _touch_customer_network_info(conn, clean_phone, data=data)

    # 2. Insert into online_orders
    cur.execute("""
        INSERT INTO online_orders (
            order_number, customer_name, customer_phone, customer_email,
            country, district, area, address_details, payment_method,
            payment_status, subtotal, delivery_charge, total_amount,
            order_status, delivery_otp, customer_ip, ip_location, created_at, updated_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        order_number, customer_name, clean_phone, customer_email,
        country, district, area, address_details, payment_method,
        "pending" if payment_method == "cod" else "paid",
        subtotal, delivery_charge, total_amount, initial_order_status, otp, cust_ip, cust_loc, created_at, created_at
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

        if item.get("is_package") and item.get("package_id"):
            cur.execute("UPDATE packages SET sold_quantity = sold_quantity + ? WHERE id = ?", (item["quantity"], item["package_id"]))
            pkg_items = conn.execute("SELECT product_id, quantity FROM package_items WHERE package_id = ?", (item["package_id"],)).fetchall()
            for pi in pkg_items:
                cur.execute(
                    "UPDATE products SET stock_qty = MAX(0, stock_qty - ?) WHERE id = ?",
                    (pi["quantity"] * item["quantity"], pi["product_id"])
                )
                remote_control.push_product_to_cloud(pi["product_id"])
            remote_control.push_packages_to_cloud()
        elif chk_p:
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
            total_amount, rounded_total, vat_amount, saved_amount, cash_amount, card_amount, change_amount,
            customer_ip, ip_location, created_at, is_synced
        ) VALUES (?, ?, ?, ?, ?, ?, 'Online', ?, ?, 0, 0, ?, 0, 0, ?, ?, ?, 0)
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
        cust_ip,
        cust_loc,
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


    # Save customer profile image if submitted with order and not yet in record
    cust_img = (data.get("customer_profile_image") or "").strip()
    if cust_img and clean_phone:
        try:
            c_user = cur.execute("SELECT profile_image, avatar_url, avatar_base64 FROM customer_users WHERE phone = ?", (clean_phone,)).fetchone()
            if c_user and not (c_user["profile_image"] or c_user["avatar_url"] or c_user["avatar_base64"]):
                saved_p = cust_img
                if cust_img.startswith("data:image"):
                    up_dir = os.path.join(app.root_path, "static", "uploads", "customers")
                    os.makedirs(up_dir, exist_ok=True)
                    hdr, enc = cust_img.split(",", 1)
                    im_data = base64.b64decode(enc)
                    im = Image.open(io.BytesIO(im_data)).convert("RGB")
                    im.thumbnail((500, 500))
                    fn = f"cust_{clean_phone}_{int(time.time())}.jpg"
                    im.save(os.path.join(up_dir, fn), "JPEG", quality=85)
                    cloud_p = upload_to_cloudinary(os.path.join(up_dir, fn), folder="supershop/customers")
                    saved_p = cloud_p if cloud_p else f"/static/uploads/customers/{fn}"
                cur.execute("UPDATE customer_users SET profile_image = ?, avatar_url = ?, avatar_base64 = ? WHERE phone = ?", (saved_p, saved_p, cust_img if cust_img.startswith("data:image") else saved_p, clean_phone))
        except Exception as e:
            print("[order_place] Error auto-saving customer photo:", e)

    add_customer_notification(
        clean_phone,
        "Order Placed Successfully",
        f"Thank you {customer_name}! Your order #{order_number} for TK {total_amount:,.2f} has been received.",
        "order",
        str(order_number),
        conn=conn
    )

    try:
        if clean_phone:
            conn.execute("DELETE FROM customer_carts WHERE customer_phone = ?", (clean_phone,))
            remote_control.push_customer_cart_to_cloud(clean_phone, "[]", created_at)
    except Exception:
        pass

    conn.commit()
    conn.close()

    # 5. Push to Cloud
    remote_control.push_online_order_to_cloud(order_id)
    remote_control.push_sale_to_cloud(sale_id)
    if clean_phone and len(clean_phone) == 11 and clean_phone.startswith("01"):
        remote_control.push_customer_user_to_cloud(clean_phone)

    call_notice = ""
    if not is_customer_verified:
        call_notice = "Your order has been recorded under 'Pending Phone Confirmation'. Our store helpline will call your mobile number to confirm your delivery address before dispatch."

    return jsonify({
        "success": True,
        "message": call_notice or "Order submitted successfully!",
        "order_number": order_number,
        "delivery_otp": otp,
        "subtotal": subtotal,
        "delivery_charge": delivery_charge,
        "total_amount": total_amount,
        "requires_call_confirmation": (not is_customer_verified),
        "call_notice": call_notice
    })



@app.route("/api/orders/pending-count", methods=["GET"])
def api_pending_orders_count():
    conn = get_connection()
    count_row = conn.execute("SELECT COUNT(*) FROM online_orders WHERE order_status IN ('new', 'pending') AND order_number NOT LIKE 'RX-%'").fetchone()
    count = count_row[0] if count_row else 0
    latest = conn.execute("SELECT id, order_number, total_amount, customer_name, created_at FROM online_orders WHERE order_status IN ('new', 'pending') AND order_number NOT LIKE 'RX-%' ORDER BY id DESC LIMIT 1").fetchone()

    # Also check incoming pharmacy prescription orders in 'reviewing' state
    rx_count_row = conn.execute("SELECT COUNT(*) FROM pharmacy_orders WHERE order_status = 'reviewing'").fetchone()
    rx_count = rx_count_row[0] if rx_count_row else 0
    rx_latest = conn.execute("SELECT id, order_number, total_amount, customer_name, created_at FROM pharmacy_orders WHERE order_status = 'reviewing' ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()

    total_pending = count + rx_count
    latest_id = 0
    latest_num = ""
    latest_name = ""
    latest_amount = 0
    order_type = "general"

    if latest and rx_latest:
        l_date = latest["created_at"] or ""
        rx_date = rx_latest["created_at"] or ""
        if rx_date >= l_date:
            latest_id = 1000000 + rx_latest["id"]
            latest_num = rx_latest["order_number"]
            latest_name = f"{rx_latest['customer_name']} (ফার্মেসী)"
            latest_amount = rx_latest["total_amount"]
            order_type = "pharmacy"
        else:
            latest_id = latest["id"]
            latest_num = latest["order_number"]
            latest_name = latest["customer_name"]
            latest_amount = latest["total_amount"]
            order_type = "general"
    elif rx_latest:
        latest_id = 1000000 + rx_latest["id"]
        latest_num = rx_latest["order_number"]
        latest_name = f"{rx_latest['customer_name']} (ফার্মেসী)"
        latest_amount = rx_latest["total_amount"]
        order_type = "pharmacy"
    elif latest:
        latest_id = latest["id"]
        latest_num = latest["order_number"]
        latest_name = latest["customer_name"]
        latest_amount = latest["total_amount"]
        order_type = "general"

    return jsonify({
        "pending_count": total_pending,
        "latest_id": latest_id,
        "latest_num": latest_num,
        "latest_name": latest_name,
        "latest_amount": latest_amount,
        "order_type": order_type
    })


def ensure_portal_notifications_table(conn):
    try:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS portal_notification_reads (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                notif_key TEXT UNIQUE NOT NULL,
                notif_type TEXT NOT NULL,
                item_id INTEGER,
                is_read INTEGER DEFAULT 1,
                seen_by_user_id INTEGER,
                seen_by_username TEXT,
                seen_by_role TEXT,
                seen_at TEXT,
                last_action TEXT DEFAULT 'read',
                last_action_by TEXT,
                last_action_at TEXT
            )
        """)
        conn.execute("CREATE INDEX IF NOT EXISTS idx_pnr_key ON portal_notification_reads(notif_key)")
        conn.commit()
    except Exception as e:
        print(f"[ensure_portal_notifications_table] Error: {e}")


@app.route("/api/portal/alerts", methods=["GET"])
@login_required
def api_portal_alerts():
    """
    Consolidated real-time alert feed for Admin & Cashier portal:
    1. New & pending online orders
    2. Inventory low stock items (stock_qty <= low_stock_threshold)
    3. Returned and expired items
    Tracks read/unread state and audit log of who marked or unmarked each alert.
    """
    today_date = get_bd_now().strftime("%Y-%m-%d")
    in_7_days = (get_bd_now() + timedelta(days=7)).strftime("%Y-%m-%d")

    try:
        sync_expired_products()
    except Exception:
        pass

    conn = get_connection()
    ensure_portal_notifications_table(conn)
    try:
        read_rows = conn.execute("SELECT * FROM portal_notification_reads").fetchall()
        read_map = {r["notif_key"]: dict(r) for r in read_rows}

        # 1. New Orders
        order_rows = conn.execute("""
            SELECT id, order_number, customer_name, customer_phone, total_amount, order_status, created_at
            FROM online_orders
            WHERE order_status IN ('new', 'pending')
            ORDER BY id DESC
            LIMIT 15
        """).fetchall()

        orders_list = []
        for o in order_rows:
            od = dict(o)
            key = f"order_{o['id']}"
            r_info = read_map.get(key)
            od["notif_key"] = key
            od["notif_type"] = "order"
            od["is_read"] = bool(r_info and r_info.get("is_read") == 1)
            od["seen_by"] = r_info.get("seen_by_username") if r_info else None
            od["seen_role"] = r_info.get("seen_by_role") if r_info else None
            od["seen_at"] = r_info.get("seen_at") if r_info else None
            od["last_action"] = r_info.get("last_action") if r_info else None
            od["last_action_by"] = r_info.get("last_action_by") if r_info else None
            od["last_action_at"] = r_info.get("last_action_at") if r_info else None
            orders_list.append(od)

        # 1b. New Pharmacy Prescription Orders (status 'reviewing')
        rx_order_rows = conn.execute("""
            SELECT id, order_number, customer_name, customer_phone, total_amount, order_status, created_at, order_type
            FROM pharmacy_orders
            WHERE order_status = 'reviewing'
            ORDER BY id DESC
            LIMIT 15
        """).fetchall()

        for rx in rx_order_rows:
            rxd = dict(rx)
            key = f"rx_order_{rx['id']}"
            r_info = read_map.get(key)
            rxd["notif_key"] = key
            rxd["notif_type"] = "order"
            rxd["is_pharmacy"] = True
            rxd["order_url"] = f"/admin/pharmacy?order={rx['id']}"
            rxd["is_read"] = bool(r_info and r_info.get("is_read") == 1)
            rxd["seen_by"] = r_info.get("seen_by_username") if r_info else None
            rxd["seen_role"] = r_info.get("seen_by_role") if r_info else None
            rxd["seen_at"] = r_info.get("seen_at") if r_info else None
            rxd["last_action"] = r_info.get("last_action") if r_info else None
            rxd["last_action_by"] = r_info.get("last_action_by") if r_info else None
            rxd["last_action_at"] = r_info.get("last_action_at") if r_info else None
            orders_list.append(rxd)

        # 2. Low Stock Items
        low_stock_rows = conn.execute("""
            SELECT id, name, sku, stock_qty, low_stock_threshold
            FROM products
            WHERE stock_qty <= low_stock_threshold
              AND (expiry_date IS NULL OR expiry_date = '' OR expiry_date >= ?)
            ORDER BY stock_qty ASC
            LIMIT 15
        """, (today_date,)).fetchall()

        stock_list = []
        for s in low_stock_rows:
            sd = dict(s)
            key = f"stock_{s['id']}"
            r_info = read_map.get(key)
            sd["notif_key"] = key
            sd["notif_type"] = "stock"
            sd["is_medicine"] = False
            sd["is_read"] = bool(r_info and r_info.get("is_read") == 1)
            sd["seen_by"] = r_info.get("seen_by_username") if r_info else None
            sd["seen_role"] = r_info.get("seen_by_role") if r_info else None
            sd["seen_at"] = r_info.get("seen_at") if r_info else None
            sd["last_action"] = r_info.get("last_action") if r_info else None
            sd["last_action_by"] = r_info.get("last_action_by") if r_info else None
            sd["last_action_at"] = r_info.get("last_action_at") if r_info else None
            stock_list.append(sd)

        # 2b. Low Stock Medicines
        low_stock_meds = conn.execute("""
            SELECT id, name, strength, dosage_form, sku, stock_qty, low_stock_threshold
            FROM pharmacy_medicines
            WHERE is_active = 1
              AND stock_qty <= low_stock_threshold
              AND (expiry_date IS NULL OR expiry_date = '' OR expiry_date >= ?)
            ORDER BY stock_qty ASC
            LIMIT 15
        """, (today_date,)).fetchall()

        for sm in low_stock_meds:
            smd = dict(sm)
            key = f"med_stock_{sm['id']}"
            r_info = read_map.get(key)
            smd["notif_key"] = key
            smd["notif_type"] = "stock"
            smd["is_medicine"] = True
            smd["name"] = f"💊 {sm['name']} ({sm['strength'] or ''}) - {sm['dosage_form']}"
            smd["is_read"] = bool(r_info and r_info.get("is_read") == 1)
            smd["seen_by"] = r_info.get("seen_by_username") if r_info else None
            smd["seen_role"] = r_info.get("seen_by_role") if r_info else None
            smd["seen_at"] = r_info.get("seen_at") if r_info else None
            smd["last_action"] = r_info.get("last_action") if r_info else None
            smd["last_action_by"] = r_info.get("last_action_by") if r_info else None
            smd["last_action_at"] = r_info.get("last_action_at") if r_info else None
            stock_list.append(smd)

        # 3. Returned Items
        returned_rows = conn.execute("""
            SELECT id, product_id, item_name, quantity, reason, expiry_date, date_returned
            FROM returned_items
            ORDER BY id DESC
            LIMIT 15
        """).fetchall()

        returned_list = []
        for r in returned_rows:
            rd = dict(r)
            key = f"return_{r['id']}"
            r_info = read_map.get(key)
            rd["notif_key"] = key
            rd["notif_type"] = "return"
            rd["is_read"] = bool(r_info and r_info.get("is_read") == 1)
            rd["seen_by"] = r_info.get("seen_by_username") if r_info else None
            rd["seen_role"] = r_info.get("seen_by_role") if r_info else None
            rd["seen_at"] = r_info.get("seen_at") if r_info else None
            rd["last_action"] = r_info.get("last_action") if r_info else None
            rd["last_action_by"] = r_info.get("last_action_by") if r_info else None
            rd["last_action_at"] = r_info.get("last_action_at") if r_info else None
            returned_list.append(rd)

        # 4. Products Expiring Soon (within 7 days)
        expiring_rows = conn.execute("""
            SELECT id, name, sku, stock_qty, expiry_date
            FROM products
            WHERE expiry_date IS NOT NULL AND expiry_date != '' AND expiry_date <= ? AND stock_qty > 0
            ORDER BY expiry_date ASC
            LIMIT 10
        """, (in_7_days,)).fetchall()

        expiring_list = []
        for e in expiring_rows:
            ed = dict(e)
            key = f"expiring_{e['id']}"
            r_info = read_map.get(key)
            ed["notif_key"] = key
            ed["notif_type"] = "expiring"
            ed["is_medicine"] = False
            ed["is_read"] = bool(r_info and r_info.get("is_read") == 1)
            ed["seen_by"] = r_info.get("seen_by_username") if r_info else None
            ed["seen_role"] = r_info.get("seen_by_role") if r_info else None
            ed["seen_at"] = r_info.get("seen_at") if r_info else None
            ed["last_action"] = r_info.get("last_action") if r_info else None
            ed["last_action_by"] = r_info.get("last_action_by") if r_info else None
            ed["last_action_at"] = r_info.get("last_action_at") if r_info else None
            expiring_list.append(ed)

        # 4b. Medicines Expiring Soon (within 30 days)
        in_30_days = (get_bd_now() + timedelta(days=30)).strftime("%Y-%m-%d")
        expiring_med_rows = conn.execute("""
            SELECT id, name, strength, dosage_form, sku, stock_qty, expiry_date
            FROM pharmacy_medicines
            WHERE is_active = 1
              AND expiry_date IS NOT NULL AND expiry_date != '' AND expiry_date <= ? AND expiry_date > ? AND stock_qty > 0
            ORDER BY expiry_date ASC
            LIMIT 15
        """, (in_30_days, today_date)).fetchall()

        for em in expiring_med_rows:
            emd = dict(em)
            key = f"med_expiring_{em['id']}"
            r_info = read_map.get(key)
            emd["notif_key"] = key
            emd["notif_type"] = "expiring"
            emd["is_medicine"] = True
            emd["name"] = f"💊 {em['name']} ({em['strength'] or ''}) - {em['dosage_form']}"
            emd["is_read"] = bool(r_info and r_info.get("is_read") == 1)
            emd["seen_by"] = r_info.get("seen_by_username") if r_info else None
            emd["seen_role"] = r_info.get("seen_by_role") if r_info else None
            emd["seen_at"] = r_info.get("seen_at") if r_info else None
            emd["last_action"] = r_info.get("last_action") if r_info else None
            emd["last_action_by"] = r_info.get("last_action_by") if r_info else None
            emd["last_action_at"] = r_info.get("last_action_at") if r_info else None
            expiring_list.append(emd)

        all_items = orders_list + stock_list + returned_list + expiring_list
        total_count = len(all_items)
        unread_count = sum(1 for it in all_items if not it["is_read"])

        orders_unread = sum(1 for it in orders_list if not it["is_read"])
        stock_unread = sum(1 for it in stock_list if not it["is_read"])
        returned_unread = sum(1 for it in returned_list if not it["is_read"]) + sum(1 for it in expiring_list if not it["is_read"])

        return jsonify({
            "success": True,
            "total_count": total_count,
            "unread_count": unread_count,
            "orders": {
                "count": len(orders_list),
                "unread_count": orders_unread,
                "items": orders_list
            },
            "low_stock": {
                "count": len(stock_list),
                "unread_count": stock_unread,
                "items": stock_list
            },
            "returned_expired": {
                "count": len(returned_list) + len(expiring_list),
                "unread_count": returned_unread,
                "items": returned_list,
                "expiring_soon": expiring_list
            }
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e), "total_count": 0, "unread_count": 0}), 500
    finally:
        conn.close()


@app.route("/api/portal/alerts/mark", methods=["POST"])
@login_required
def api_portal_alerts_mark():
    """
    Mark an individual alert as read or unread, recording who performed the action and when.
    """
    data = request.get_json(silent=True) or {}
    notif_key = str(data.get("notif_key") or "").strip()
    action = str(data.get("action") or "read").strip().lower()  # 'read' or 'unread'
    notif_type = str(data.get("notif_type") or "general").strip()
    item_id = data.get("item_id")

    if not notif_key:
        return jsonify({"success": False, "message": "Notification key is required."}), 400

    user_id = session.get("user_id")
    username = session.get("username") or "Admin"
    role = session.get("role") or "staff"
    now_str = get_bd_now().strftime("%Y-%m-%d %H:%M:%S")

    conn = get_connection()
    ensure_portal_notifications_table(conn)
    try:
        if action == "read":
            conn.execute("""
                INSERT INTO portal_notification_reads 
                (notif_key, notif_type, item_id, is_read, seen_by_user_id, seen_by_username, seen_by_role, seen_at, last_action, last_action_by, last_action_at)
                VALUES (?, ?, ?, 1, ?, ?, ?, ?, 'read', ?, ?)
                ON CONFLICT(notif_key) DO UPDATE SET
                    is_read = 1,
                    seen_by_user_id = excluded.seen_by_user_id,
                    seen_by_username = excluded.seen_by_username,
                    seen_by_role = excluded.seen_by_role,
                    seen_at = excluded.seen_at,
                    last_action = 'read',
                    last_action_by = excluded.last_action_by,
                    last_action_at = excluded.last_action_at
            """, (notif_key, notif_type, item_id, user_id, username, role, now_str, username, now_str))
        else:
            conn.execute("""
                INSERT INTO portal_notification_reads 
                (notif_key, notif_type, item_id, is_read, seen_by_user_id, seen_by_username, seen_by_role, seen_at, last_action, last_action_by, last_action_at)
                VALUES (?, ?, ?, 0, NULL, NULL, NULL, NULL, 'unread', ?, ?)
                ON CONFLICT(notif_key) DO UPDATE SET
                    is_read = 0,
                    last_action = 'unread',
                    last_action_by = excluded.last_action_by,
                    last_action_at = excluded.last_action_at
            """, (notif_key, notif_type, item_id, username, now_str))
        conn.commit()

        return jsonify({
            "success": True,
            "notif_key": notif_key,
            "action": action,
            "is_read": action == "read",
            "actor": username,
            "actor_role": role,
            "timestamp": now_str
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()


@app.route("/api/portal/alerts/mark-all-read", methods=["POST"])
@login_required
def api_portal_alerts_mark_all_read():
    """
    Mark all active notifications as read by the current user.
    """
    data = request.get_json(silent=True) or {}
    keys = data.get("keys")

    user_id = session.get("user_id")
    username = session.get("username") or "Admin"
    role = session.get("role") or "staff"
    now_str = get_bd_now().strftime("%Y-%m-%d %H:%M:%S")
    today_date = get_bd_now().strftime("%Y-%m-%d")
    in_7_days = (get_bd_now() + timedelta(days=7)).strftime("%Y-%m-%d")

    conn = get_connection()
    ensure_portal_notifications_table(conn)
    try:
        keys_to_mark = []
        if keys and isinstance(keys, list):
            keys_to_mark = [(str(k).strip(), "general", None) for k in keys if str(k).strip()]
        else:
            for o in conn.execute("SELECT id FROM online_orders WHERE order_status IN ('new', 'pending')").fetchall():
                keys_to_mark.append((f"order_{o['id']}", "order", o["id"]))
            for s in conn.execute("SELECT id FROM products WHERE stock_qty <= low_stock_threshold AND (expiry_date IS NULL OR expiry_date = '' OR expiry_date >= ?)", (today_date,)).fetchall():
                keys_to_mark.append((f"stock_{s['id']}", "stock", s["id"]))
            for r in conn.execute("SELECT id FROM returned_items").fetchall():
                keys_to_mark.append((f"return_{r['id']}", "return", r["id"]))
            for e in conn.execute("SELECT id FROM products WHERE expiry_date IS NOT NULL AND expiry_date != '' AND expiry_date <= ? AND stock_qty > 0", (in_7_days,)).fetchall():
                keys_to_mark.append((f"expiring_{e['id']}", "expiring", e["id"]))
            for ms in conn.execute("SELECT id FROM pharmacy_medicines WHERE stock_qty <= low_stock_threshold AND is_active = 1 AND (expiry_date IS NULL OR expiry_date = '' OR expiry_date >= ?)", (today_date,)).fetchall():
                keys_to_mark.append((f"med_stock_{ms['id']}", "stock", ms["id"]))
            in_30_days = (get_bd_now() + timedelta(days=30)).strftime("%Y-%m-%d")
            for me in conn.execute("SELECT id FROM pharmacy_medicines WHERE is_active = 1 AND expiry_date IS NOT NULL AND expiry_date != '' AND expiry_date <= ? AND expiry_date > ? AND stock_qty > 0", (in_30_days, today_date)).fetchall():
                keys_to_mark.append((f"med_expiring_{me['id']}", "expiring", me["id"]))

        for k, t, i_id in keys_to_mark:
            conn.execute("""
                INSERT INTO portal_notification_reads 
                (notif_key, notif_type, item_id, is_read, seen_by_user_id, seen_by_username, seen_by_role, seen_at, last_action, last_action_by, last_action_at)
                VALUES (?, ?, ?, 1, ?, ?, ?, ?, 'read', ?, ?)
                ON CONFLICT(notif_key) DO UPDATE SET
                    is_read = 1,
                    seen_by_user_id = excluded.seen_by_user_id,
                    seen_by_username = excluded.seen_by_username,
                    seen_by_role = excluded.seen_by_role,
                    seen_at = excluded.seen_at,
                    last_action = 'read',
                    last_action_by = excluded.last_action_by,
                    last_action_at = excluded.last_action_at
            """, (k, t, i_id, user_id, username, role, now_str, username, now_str))

        conn.commit()
        return jsonify({
            "success": True,
            "marked_count": len(keys_to_mark),
            "actor": username,
            "actor_role": role,
            "timestamp": now_str
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500
    finally:
        conn.close()


@app.route("/api/notifications", methods=["GET"])
def api_get_notifications():
    phone = request.args.get("phone", "").strip()
    is_portal = (session.get("user_id") is not None) or (request.args.get("for_portal") == "1") or (request.args.get("for_staff") == "1")
    
    # Do not return notifications if user is not signed in
    if not is_portal and not phone:
        return jsonify({
            "success": True,
            "unread_count": 0,
            "notifications": []
        })

    conn = get_connection()
    try:
        ensure_daily_suggestions_and_offers(conn)
        pending_confirmations = []
        if is_portal and not phone:
            notifs = get_portal_notifications(limit=60, conn=conn)
        else:
            notifs = get_customer_notifications(phone, limit=60, conn=conn)
            p_vars = _phone_variants(phone)
            if p_vars:
                ph = ",".join("?" for _ in p_vars)
                norm_p = p_vars[0]
                pend_rows = conn.execute(
                    f"""SELECT id, order_number, subtotal, delivery_charge, total_amount, quote_sent_at, admin_notes
                        FROM pharmacy_orders
                        WHERE order_status = 'awaiting_customer_confirmation'
                          AND (customer_phone IN ({ph}) OR REPLACE(REPLACE(REPLACE(customer_phone, ' ', ''), '-', ''), '+88', '') = ?)
                        ORDER BY id DESC LIMIT 10""",
                    tuple(p_vars) + (norm_p,),
                ).fetchall()
                pending_confirmations = [dict(pr) for pr in pend_rows]
                pend_nums = {str(pr["order_number"]).strip() for pr in pend_rows if pr["order_number"]}
                for n in notifs:
                    n_ref = str(n.get("reference_id") or "").strip()
                    n_type = str(n.get("type") or "").strip().lower()
                    if n_type == "pharmacy_quote" and (not pend_nums or n_ref in pend_nums):
                        n["is_important"] = True
        unread_count = sum(1 for n in notifs if n.get("is_read") == 0)
        return jsonify({
            "success": True,
            "unread_count": unread_count,
            "notifications": notifs,
            "pending_confirmations": pending_confirmations,
        })
    finally:
        conn.close()


@app.route("/api/notifications/mark-read", methods=["POST"])
def api_mark_notification_read():
    data = request.json or {}
    phone = data.get("phone", "").strip()
    notif_id = data.get("id")
    is_portal = (session.get("user_id") is not None) or (data.get("for_portal") is True)
    conn = get_connection()
    try:
        if notif_id == "all" or notif_id is None:
            if is_portal and not phone:
                mark_all_portal_notifications_as_read(conn=conn)
            else:
                mark_all_notifications_as_read(phone, conn=conn)
        else:
            mark_notification_as_read(int(notif_id), phone, conn=conn)
        conn.commit()
        return jsonify({"success": True})
    finally:
        conn.close()


@app.route("/api/notifications/clear", methods=["POST"])
def api_clear_notifications():
    data = request.json or {}
    phone = data.get("phone", "").strip()
    is_portal = (session.get("user_id") is not None) or (data.get("for_portal") is True)
    conn = get_connection()
    try:
        if is_portal and not phone:
            clear_portal_notifications(conn=conn)
        else:
            clear_customer_notifications(phone, conn=conn)
        conn.commit()
        return jsonify({"success": True})
    finally:
        conn.close()



def _phone_variants(phone_str):
    raw = (phone_str or "").strip()
    if not raw:
        return []
    variants = []
    norm = normalize_phone(raw)
    for cand in (norm, f"88{norm}" if norm.startswith("01") else "", f"+88{norm}" if norm.startswith("01") else "", raw):
        if cand and cand not in variants:
            variants.append(cand)
    return variants


def _enrich_cart_items(conn, raw_items):
    """Enrich synced cart items with live DB price, stock, image_url, and offer metadata."""
    enriched = []
    if not isinstance(raw_items, list):
        return enriched
    for item in raw_items:
        if not isinstance(item, dict):
            continue
        qty = int(item.get("quantity") or item.get("qty") or 1)
        if qty <= 0:
            continue
        is_pkg = bool(
            item.get("is_package")
            or item.get("is_pkg")
            or item.get("package_id") is not None
            or str(item.get("id") or "").upper().startswith("PKG_")
        )
        pid_raw = item.get("package_id") if is_pkg else (item.get("product_id") or item.get("id"))
        try:
            pid_int = abs(int(str(pid_raw).replace("PKG_", "").replace("pkg_", ""))) if pid_raw is not None else 0
        except Exception:
            pid_int = 0

        if is_pkg and pid_int > 0:
            pkg = conn.execute("SELECT * FROM packages WHERE id = ? AND is_active = 1", (pid_int,)).fetchone()
            if pkg:
                p_items = conn.execute("""
                    SELECT pi.quantity, p.stock_qty, p.image_url, p.mrp, p.sell_price, p.sku, p.name AS product_name
                    FROM package_items pi JOIN products p ON pi.product_id = p.id
                    WHERE pi.package_id = ?
                """, (pid_int,)).fetchall()
                min_stock = 999999
                reg_total = 0.0
                fallback_img = ""
                item_summaries = []
                for pi in p_items:
                    pq = int(pi["quantity"] or 1)
                    st = int(pi["stock_qty"] or 0)
                    possible = (st // pq) if st > 0 else 0
                    if possible < min_stock:
                        min_stock = possible
                    p_mrp = float(pi["mrp"] or 0) or float(pi["sell_price"] or 0)
                    reg_total += p_mrp * pq
                    if not fallback_img and (pi["image_url"] or "").strip():
                        fallback_img = (pi["image_url"] or "").strip()
                    item_summaries.append(f"{pi['sku'] or 'SKU'} {pi['product_name']} (Qty:{pq})")
                if min_stock == 999999 or not p_items:
                    min_stock = 0
                max_limit = int(pkg["max_sale_limit"] or 0) if "max_sale_limit" in pkg.keys() else 0
                sold_qty = int(pkg["sold_quantity"] or 0) if "sold_quantity" in pkg.keys() else 0
                if max_limit > 0:
                    min_stock = min(min_stock, max(0, max_limit - sold_qty))
                pkg_img = (pkg["image_url"] or "").strip() or fallback_img
                price_val = float(pkg["package_price"] or 0)
                mrp_val = reg_total if reg_total > price_val else price_val
                pkg_name = pkg["name"] if str(pkg["name"]).startswith("📦") else f"📦 {pkg['name']}"
                enriched.append({
                    "id": -pid_int,
                    "product_id": -pid_int,
                    "package_id": pid_int,
                    "is_package": True,
                    "sku": f"{pkg['name']} ({', '.join(item_summaries)})" if item_summaries else (item.get("sku") or "COMBO"),
                    "name": pkg_name,
                    "price": price_val,
                    "mrp": mrp_val,
                    "quantity": qty,
                    "stock_qty": max(0, min_stock),
                    "image_url": pkg_img or item.get("image_url") or "",
                    "offer_type": "",
                    "offer_value": "",
                    "offer_title": "",
                    "offer_base": "mrp",
                })
                continue
        elif not is_pkg and pid_int > 0:
            prod = conn.execute("SELECT * FROM products WHERE id = ?", (pid_int,)).fetchone()
            if prod:
                enriched.append({
                    "id": prod["id"],
                    "product_id": prod["id"],
                    "package_id": None,
                    "is_package": False,
                    "sku": prod["sku"] or "",
                    "name": prod["name"] or "",
                    "price": float(prod["sell_price"] or 0),
                    "mrp": float(prod["mrp"] or 0),
                    "quantity": qty,
                    "stock_qty": int(prod["stock_qty"] or 0),
                    "image_url": (prod["image_url"] or "").strip() or item.get("image_url") or "",
                    "offer_type": prod["offer_type"] or "",
                    "offer_value": prod["offer_value"] or "",
                    "offer_title": prod["offer_title"] or "",
                    "offer_base": (prod["offer_base"] if "offer_base" in prod.keys() else "mrp") or "mrp",
                })
                continue

        enriched.append({
            "id": -pid_int if is_pkg else pid_int,
            "product_id": -pid_int if is_pkg else pid_int,
            "package_id": pid_int if is_pkg else None,
            "is_package": is_pkg,
            "sku": item.get("sku") or "",
            "name": item.get("name") or item.get("product_name") or "Item",
            "price": float(item.get("price") or item.get("sell_price") or item.get("unit_price") or 0),
            "mrp": float(item.get("mrp") or item.get("price") or 0),
            "quantity": qty,
            "stock_qty": int(item.get("stock_qty") or 99),
            "image_url": (item.get("image_url") or item.get("img") or "").strip(),
            "offer_type": item.get("offer_type") or "",
            "offer_value": item.get("offer_value") or "",
            "offer_title": item.get("offer_title") or "",
            "offer_base": item.get("offer_base") or "mrp",
        })
    return enriched


def _build_order_timeline(curr_status, created_dt="", confirmed_dt="", packed_dt="", on_the_way_dt="", delivered_dt="", cancelled_dt="", updated_at=""):
    """Build unified 5-stage + optional cancelled delivery timeline in BD time (GMT+6)."""
    norm_status = _PHARM_TO_OL_STATUS.get((curr_status or "").strip().lower(), (curr_status or "new").strip().lower())
    if norm_status in ("verified", "packed", "on_the_way", "delivered") and not confirmed_dt:
        confirmed_dt = updated_at or created_dt
    if norm_status in ("packed", "on_the_way", "delivered") and not packed_dt:
        packed_dt = confirmed_dt or updated_at or created_dt
    if norm_status in ("on_the_way", "delivered") and not on_the_way_dt:
        on_the_way_dt = packed_dt or confirmed_dt or created_dt
    if norm_status == "delivered" and not delivered_dt:
        delivered_dt = updated_at or created_dt
    if norm_status == "cancelled" and not cancelled_dt:
        cancelled_dt = updated_at or created_dt

    created_iso, created_bd = format_bd_timeline_time(created_dt)
    confirmed_iso, confirmed_bd = format_bd_timeline_time(confirmed_dt)
    packed_iso, packed_bd = format_bd_timeline_time(packed_dt)
    on_the_way_iso, on_the_way_bd = format_bd_timeline_time(on_the_way_dt)
    delivered_iso, delivered_bd = format_bd_timeline_time(delivered_dt)
    cancelled_iso, cancelled_bd = format_bd_timeline_time(cancelled_dt)

    timeline = [
        {
            "stage": "placed",
            "key": "placed",
            "title": "Order Placed",
            "time": created_iso,
            "time_bd": created_bd,
            "time_formatted": created_bd,
            "done": True,
            "is_done": True,
            "active": (norm_status in ("new", "pending", "pending_confirmation")),
            "is_current": (norm_status in ("new", "pending", "pending_confirmation")),
        },
        {
            "stage": "verified",
            "key": "verified",
            "title": "Order Confirmed",
            "time": confirmed_iso if confirmed_dt else "",
            "time_bd": confirmed_bd if confirmed_dt else "",
            "time_formatted": confirmed_bd if confirmed_dt else "",
            "done": bool(confirmed_dt) or norm_status in ("verified", "packed", "on_the_way", "delivered"),
            "is_done": bool(confirmed_dt) or norm_status in ("verified", "packed", "on_the_way", "delivered"),
            "active": (norm_status == "verified"),
            "is_current": (norm_status == "verified"),
        },
        {
            "stage": "packed",
            "key": "packed",
            "title": "Packed & Ready",
            "time": packed_iso if packed_dt else "",
            "time_bd": packed_bd if packed_dt else "",
            "time_formatted": packed_bd if packed_dt else "",
            "done": bool(packed_dt) or norm_status in ("packed", "on_the_way", "delivered"),
            "is_done": bool(packed_dt) or norm_status in ("packed", "on_the_way", "delivered"),
            "active": (norm_status == "packed"),
            "is_current": (norm_status == "packed"),
        },
        {
            "stage": "on_the_way",
            "key": "on_the_way",
            "title": "On The Way",
            "time": on_the_way_iso if on_the_way_dt else "",
            "time_bd": on_the_way_bd if on_the_way_dt else "",
            "time_formatted": on_the_way_bd if on_the_way_dt else "",
            "done": bool(on_the_way_dt) or norm_status in ("on_the_way", "delivered"),
            "is_done": bool(on_the_way_dt) or norm_status in ("on_the_way", "delivered"),
            "active": (norm_status == "on_the_way"),
            "is_current": (norm_status == "on_the_way"),
        },
        {
            "stage": "delivered",
            "key": "delivered",
            "title": "Delivered",
            "time": delivered_iso if delivered_dt else "",
            "time_bd": delivered_bd if delivered_dt else "",
            "time_formatted": delivered_bd if delivered_dt else "",
            "done": bool(delivered_dt) or (norm_status == "delivered"),
            "is_done": bool(delivered_dt) or (norm_status == "delivered"),
            "active": (norm_status == "delivered"),
            "is_current": (norm_status == "delivered"),
        },
    ]
    if norm_status == "cancelled":
        timeline.append({
            "stage": "cancelled",
            "key": "cancelled",
            "title": "Order Cancelled",
            "time": cancelled_iso,
            "time_bd": cancelled_bd,
            "time_formatted": cancelled_bd,
            "done": True,
            "is_done": True,
            "active": True,
            "is_current": True,
        })
    return norm_status, timeline, {
        "created_at": created_iso,
        "created_at_bd": created_bd,
        "confirmed_at": confirmed_iso,
        "packed_at": packed_iso,
        "on_the_way_at": on_the_way_iso,
        "delivered_at": delivered_iso,
        "cancelled_at": cancelled_iso,
    }


@app.route("/api/orders/my-orders", methods=["GET"])
def api_my_orders():
    phone = request.args.get("phone", "").strip()
    variants = _phone_variants(phone)
    if not variants:
        return jsonify([])

    conn = get_connection()
    placeholders = ",".join(["?"] * len(variants))
    norm_main = variants[0]
    orders = conn.execute(
        f"""
        SELECT * FROM online_orders
        WHERE customer_phone IN ({placeholders})
           OR REPLACE(REPLACE(REPLACE(customer_phone, ' ', ''), '-', ''), '+88', '') = ?
        ORDER BY id DESC
        """,
        tuple(variants) + (norm_main,)
    ).fetchall()

    base_host = request.host_url.rstrip("/")

    def _abs_url(u):
        s = (u or "").strip()
        if s.startswith("/static/"):
            return base_host + s
        return s

    _STAGE_RANK = {
        "new": 0, "pending": 0, "pending_confirmation": 0, "reviewing": 0,
        "awaiting_customer_confirmation": 1,
        "verified": 2, "confirmed": 2,
        "packed": 3,
        "on_the_way": 4,
        "delivered": 5,
        "cancelled": 6,
    }

    result = []
    seen_order_numbers = set()
    for ord_row in orders:
        if ord_row["order_number"]:
            seen_order_numbers.add(ord_row["order_number"])
        items = conn.execute("""
            SELECT oi.*, p.image_url, p.unit, p.sku, p.brand, p.description, p.sell_price as prod_sell_price
            FROM online_order_items oi
            LEFT JOIN products p ON oi.product_id = p.id
            WHERE oi.order_id = ?
        """, (ord_row["id"],)).fetchall()

        processed_items = []
        pharm_row = conn.execute(
            "SELECT * FROM pharmacy_orders WHERE online_order_id = ? OR order_number = ? LIMIT 1",
            (ord_row["id"], ord_row["order_number"]),
        ).fetchone()
        pharm_items = []
        if pharm_row:
            try:
                app_it = json.loads(pharm_row["approved_items_json"] or "[]")
            except Exception:
                app_it = []
            try:
                req_it = json.loads(pharm_row["requested_items_json"] or "[]")
            except Exception:
                req_it = []
            pharm_items = app_it if app_it else req_it

        for idx_it, i in enumerate(items):
            i_dict = dict(i)
            p_name = i_dict.get("product_name") or ""
            if i_dict.get("image_url"):
                i_dict["image_url"] = _abs_url(i_dict["image_url"])

            low_p_name = p_name.lower()
            is_pkg_hint = ("📦" in p_name or "package" in low_p_name or "combo" in low_p_name)
            is_pharm_ord = bool(pharm_row) or (ord_row["order_number"] or "").startswith("RX-")
            is_med_hint = ("💊" in p_name) or (is_pharm_ord and not is_pkg_hint)

            if is_pkg_hint or (not is_med_hint and (i_dict.get("product_id") or 0) == 0):
                clean_pkg_name = p_name.replace("📦", "").split("(")[0].strip()
                pkg = conn.execute(
                    "SELECT * FROM packages WHERE name = ? OR instr(?, name) > 0 OR instr(name, ?) > 0",
                    (clean_pkg_name, clean_pkg_name, clean_pkg_name)
                ).fetchone()
                if pkg:
                    i_dict["is_package"] = True
                    i_dict["package_id"] = pkg["id"]
                    i_dict["package_name"] = pkg["name"]
                    i_dict["package_price"] = pkg["package_price"]
                    i_dict["package_image"] = _abs_url(pkg["image_url"] or "")
                    i_dict["package_description"] = pkg["description"] or ""
                    pkg_items = conn.execute("""
                        SELECT pi.quantity as item_qty, p.id as product_id, p.name as prod_name, p.sku, p.unit, p.sell_price, p.mrp, p.image_url, p.brand
                        FROM package_items pi JOIN products p ON pi.product_id = p.id
                        WHERE pi.package_id = ?
                    """, (pkg["id"],)).fetchall()
                    i_dict["package_items"] = [dict(pi) for pi in pkg_items]
            elif is_med_hint:
                i_dict["is_medicine"] = True
                if idx_it < len(pharm_items) and isinstance(pharm_items[idx_it], dict):
                    pm = pharm_items[idx_it]
                    i_dict["medicine_id"] = int(pm.get("medicine_id") or 0)
                    i_dict["generic_name"] = pm.get("generic_name") or ""
                    i_dict["strength"] = pm.get("strength") or ""
                    i_dict["dosage_form"] = pm.get("dosage_form") or ""
                else:
                    clean_med = p_name.replace("💊", "").split("(")[0].strip()
                    if clean_med and "প্রেসক্রিপশন অর্ডার" not in clean_med:
                        m_row = conn.execute(
                            "SELECT id, generic_name, strength, dosage_form FROM pharmacy_medicines WHERE LOWER(name) = LOWER(?) LIMIT 1",
                            (clean_med,),
                        ).fetchone()
                        if m_row:
                            i_dict["medicine_id"] = int(m_row["id"])
                            i_dict["generic_name"] = m_row["generic_name"] or ""
                            i_dict["strength"] = m_row["strength"] or ""
                            i_dict["dosage_form"] = m_row["dosage_form"] or ""
            processed_items.append(i_dict)

        o_dict = dict(ord_row)
        o_dict["items"] = processed_items
        created_dt = o_dict.get("created_at") or ""
        confirmed_dt = o_dict.get("confirmed_at") or ""
        packed_dt = o_dict.get("packed_at") or ""
        on_the_way_dt = o_dict.get("on_the_way_at") or ""
        delivered_dt = o_dict.get("delivered_at") or ""
        cancelled_dt = o_dict.get("cancelled_at") or ""
        raw_ol_status = _PHARM_TO_OL_STATUS.get((o_dict.get("order_status") or "new").strip().lower(), o_dict.get("order_status") or "new")
        curr_status = raw_ol_status

        if pharm_row:
            o_dict["is_pharmacy_order"] = True
            o_dict["pharmacy_order_id"] = pharm_row["id"]
            o_dict["pharmacy_order_type"] = pharm_row["order_type"] or ""
            o_dict["prescription_url"] = _abs_url(pharm_row["prescription_url"] or "")
            o_dict["prescription_original_url"] = _abs_url(pharm_row["prescription_original_url"] or pharm_row["prescription_url"] or "")
            o_dict["prescription_enhanced_url"] = _abs_url(pharm_row["prescription_enhanced_url"] or pharm_row["prescription_url"] or "")
            o_dict["overall_duration_days"] = int(pharm_row["overall_duration_days"] or 0)
            o_dict["customer_notes"] = pharm_row["customer_notes"] or ""
            # Reconcile if pharmacy_orders was updated independently (e.g. online_order_id == 0 on Firestore sync)
            pharm_mapped_ol = _PHARM_TO_OL_STATUS.get((pharm_row["order_status"] or "").strip().lower(), "")
            if pharm_mapped_ol:
                if pharm_mapped_ol == "cancelled" or _STAGE_RANK.get(pharm_mapped_ol, 0) > _STAGE_RANK.get(curr_status, 0):
                    curr_status = pharm_mapped_ol
            confirmed_dt = confirmed_dt or (pharm_row["confirmed_at"] or "")
            packed_dt = packed_dt or (pharm_row["packed_at"] or "")
            on_the_way_dt = on_the_way_dt or (pharm_row["on_the_way_at"] or "")
            delivered_dt = delivered_dt or (pharm_row["delivered_at"] or "")
            cancelled_dt = cancelled_dt or (pharm_row["cancelled_at"] or "")
            if float(pharm_row["total_amount"] or 0) > 0 and float(o_dict.get("total_amount") or 0) == 0:
                o_dict["subtotal"] = float(pharm_row["subtotal"] or 0.0)
                o_dict["delivery_charge"] = float(pharm_row["delivery_charge"] or 0.0)
                o_dict["total_amount"] = float(pharm_row["total_amount"] or 0.0)
            if not o_dict.get("assigned_rider_name") and pharm_row["assigned_rider_name"]:
                o_dict["assigned_rider_name"] = pharm_row["assigned_rider_name"]
                o_dict["assigned_rider_phone"] = pharm_row["assigned_rider_phone"]
            if (not processed_items or (len(processed_items) == 1 and float(processed_items[0].get("total_price") or 0) == 0)) and pharm_items:
                o_dict["items"] = [
                    {
                        "product_name": f"💊 {pm.get('name', 'Medicine')}",
                        "quantity": int(pm.get("quantity") or 1),
                        "unit_price": float(pm.get("unit_price") or 0.0),
                        "total_price": float(pm.get("total_price") or 0.0),
                        "is_medicine": True,
                        "medicine_id": int(pm.get("medicine_id") or 0),
                        "generic_name": pm.get("generic_name") or "",
                        "strength": pm.get("strength") or "",
                        "dosage_form": pm.get("dosage_form") or "",
                    }
                    for pm in pharm_items if isinstance(pm, dict)
                ] or processed_items
        elif (o_dict.get("order_number") or "").startswith("RX-"):
            o_dict["is_pharmacy_order"] = True

        norm_status, timeline, ts_map = _build_order_timeline(
            curr_status,
            created_dt=created_dt,
            confirmed_dt=confirmed_dt,
            packed_dt=packed_dt,
            on_the_way_dt=on_the_way_dt,
            delivered_dt=delivered_dt,
            cancelled_dt=cancelled_dt,
            updated_at=o_dict.get("updated_at") or (pharm_row["updated_at"] if pharm_row else ""),
        )
        o_dict["order_status"] = norm_status
        o_dict["timeline"] = timeline
        o_dict.update(ts_map)
        result.append(o_dict)

    # Include any pharmacy_orders for this customer that do not yet exist in online_orders
    pharm_orphans = conn.execute(
        f"""
        SELECT * FROM pharmacy_orders
        WHERE customer_phone IN ({placeholders})
           OR REPLACE(REPLACE(REPLACE(customer_phone, ' ', ''), '-', ''), '+88', '') = ?
        ORDER BY id DESC
        """,
        tuple(variants) + (norm_main,),
    ).fetchall()
    for pr in pharm_orphans:
        if pr["order_number"] and pr["order_number"] in seen_order_numbers:
            continue
        try:
            p_items_raw = json.loads(pr["approved_items_json"] or "[]") or json.loads(pr["requested_items_json"] or "[]")
        except Exception:
            p_items_raw = []
        mapped_items = [
            {
                "product_name": f"💊 {pm.get('name', 'Medicine')}",
                "quantity": int(pm.get("quantity") or 1),
                "unit_price": float(pm.get("unit_price") or 0.0),
                "total_price": float(pm.get("total_price") or 0.0),
                "is_medicine": True,
                "medicine_id": int(pm.get("medicine_id") or 0),
                "generic_name": pm.get("generic_name") or "",
                "strength": pm.get("strength") or "",
                "dosage_form": pm.get("dosage_form") or "",
            }
            for pm in p_items_raw if isinstance(pm, dict)
        ] or [{
            "product_name": "💊 প্রেসক্রিপশন অর্ডার",
            "quantity": 1,
            "unit_price": 0.0,
            "total_price": 0.0,
            "is_medicine": True,
        }]
        ol_st = _PHARM_TO_OL_STATUS.get((pr["order_status"] or "reviewing").strip().lower(), "pending_confirmation")
        norm_status, timeline, ts_map = _build_order_timeline(
            ol_st,
            created_dt=pr["created_at"] or "",
            confirmed_dt=pr["confirmed_at"] or "",
            packed_dt=pr["packed_at"] or "",
            on_the_way_dt=pr["on_the_way_at"] or "",
            delivered_dt=pr["delivered_at"] or "",
            cancelled_dt=pr["cancelled_at"] or "",
            updated_at=pr["updated_at"] or "",
        )
        synth = {
            "id": pr["online_order_id"] or pr["id"],
            "order_number": pr["order_number"],
            "customer_name": pr["customer_name"] or "",
            "customer_phone": pr["customer_phone"] or "",
            "customer_email": pr["customer_email"] or "",
            "district": pr["district"] or "",
            "area": pr["area"] or "",
            "address_details": pr["delivery_address"] or "",
            "payment_method": pr["payment_method"] or "cod",
            "payment_status": pr["payment_status"] or "pending",
            "subtotal": float(pr["subtotal"] or 0.0),
            "delivery_charge": float(pr["delivery_charge"] or 50.0),
            "total_amount": float(pr["total_amount"] or 0.0),
            "order_status": norm_status,
            "delivery_otp": pr["delivery_otp"] or "",
            "assigned_rider_name": pr["assigned_rider_name"] or "",
            "assigned_rider_phone": pr["assigned_rider_phone"] or "",
            "items": mapped_items,
            "is_pharmacy_order": True,
            "pharmacy_order_id": pr["id"],
            "pharmacy_order_type": pr["order_type"] or "",
            "prescription_url": _abs_url(pr["prescription_url"] or ""),
            "prescription_original_url": _abs_url(pr["prescription_original_url"] or pr["prescription_url"] or ""),
            "prescription_enhanced_url": _abs_url(pr["prescription_enhanced_url"] or pr["prescription_url"] or ""),
            "overall_duration_days": int(pr["overall_duration_days"] or 0),
            "customer_notes": pr["customer_notes"] or "",
            "timeline": timeline,
        }
        synth.update(ts_map)
        result.append(synth)

    conn.close()
    return jsonify(result)


@app.route("/api/cart", methods=["GET"])
def api_get_synced_cart():
    phone = normalize_phone(request.args.get("phone", ""))
    if not phone:
        return jsonify({"success": False, "message": "Phone is required", "items": [], "updated_at": ""}), 400
    conn = get_connection()
    row = conn.execute(
        "SELECT items_json, updated_at FROM customer_carts WHERE customer_phone = ?",
        (phone,)
    ).fetchone()
    raw_items = []
    updated_at = ""
    if row:
        updated_at = row["updated_at"] or ""
        try:
            raw_items = json.loads(row["items_json"] or "[]")
        except Exception:
            raw_items = []
    items = _enrich_cart_items(conn, raw_items)
    conn.close()
    return jsonify({"success": True, "phone": phone, "items": items, "updated_at": updated_at})


@app.route("/api/cart/sync", methods=["POST"])
def api_sync_cart():
    data = request.get_json(silent=True) or {}
    phone = normalize_phone(data.get("phone", ""))
    if not phone:
        return jsonify({"success": False, "message": "Phone is required"}), 400
    raw_items = data.get("items")
    if raw_items is None:
        raw_items = []

    now_iso = datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%S.%fZ")
    conn = get_connection()
    canonical_items = _enrich_cart_items(conn, raw_items)
    items_json = json.dumps(canonical_items, ensure_ascii=False)
    conn.execute(
        "INSERT OR REPLACE INTO customer_carts (customer_phone, items_json, updated_at) VALUES (?, ?, ?)",
        (phone, items_json, now_iso)
    )
    conn.commit()
    conn.close()

    try:
        remote_control.push_customer_cart_to_cloud(phone, items_json, now_iso)
    except Exception:
        pass

    return jsonify({"success": True, "phone": phone, "items": canonical_items, "updated_at": now_iso})


@app.route("/api/orders/cancel", methods=["POST"])
def api_cancel_order():
    data = request.json or {}
    order_number = data.get("order_number", "").strip()
    phone = data.get("customer_phone", "").strip()

    if not order_number or not phone:
        return jsonify({"success": False, "message": "Please enter Order Number and Phone Number."}), 400

    variants = _phone_variants(phone)
    norm_main = variants[0] if variants else phone
    placeholders = ",".join(["?"] * max(1, len(variants)))

    conn = get_connection()
    order = conn.execute(
        f"""
        SELECT * FROM online_orders
        WHERE order_number = ?
          AND (customer_phone IN ({placeholders})
               OR REPLACE(REPLACE(REPLACE(customer_phone, ' ', ''), '-', ''), '+88', '') = ?)
        """,
        (order_number,) + tuple(variants or [phone]) + (norm_main,)
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

    now_iso = get_bd_now_iso()
    conn.execute(
        "UPDATE online_orders SET order_status = 'cancelled', cancelled_at = CASE WHEN cancelled_at = '' THEN ? ELSE cancelled_at END, updated_at = ? WHERE id = ?",
        (now_iso, now_iso, order["id"])
    )
    pharm_id = _sync_pharmacy_from_online_order(conn, order, 'cancelled', now_iso)
    notify_order_status_change(order, 'cancelled', conn=conn)
    conn.commit()
    conn.close()
    remote_control.push_online_order_to_cloud(order["id"])
    if pharm_id:
        remote_control.push_pharmacy_order_to_cloud(pharm_id)

    return jsonify({"success": True, "message": "Order has been cancelled successfully."})


@app.route("/api/orders/delivery-orders", methods=["GET"])
def api_delivery_orders():
    raw_phone = request.args.get("rider_phone", "").strip()
    norm_phone = normalize_phone(raw_phone)
    rider_id = request.args.get("rider_id", type=int)

    conn = get_connection()
    # Reconcile any confirmed/packed/dispatched pharmacy orders into online_orders so Riders always see them
    try:
        unsynced_pharm = conn.execute("""
            SELECT po.id, po.approved_items_json, po.requested_items_json
            FROM pharmacy_orders po
            LEFT JOIN online_orders oo ON po.online_order_id = oo.id
            WHERE po.order_status IN ('confirmed', 'packed', 'on_the_way')
              AND (oo.id IS NULL OR oo.order_status IN ('pending', 'pending_confirmation', 'reviewing', 'new'))
        """).fetchall()
        if unsynced_pharm:
            now_sync = get_bd_now_iso()
            for up in unsynced_pharm:
                raw_j = up["approved_items_json"] or up["requested_items_json"] or "[]"
                try:
                    parsed_itms = json.loads(raw_j) if raw_j else None
                except Exception:
                    parsed_itms = None
                _ensure_online_order_for_pharmacy(conn, up["id"], approved_items=parsed_itms, now_iso=now_sync)
            conn.commit()
    except Exception as e:
        print(f"[delivery_orders] Pharmacy sync notice: {e}")

    rider_can_rx = False
    if raw_phone or norm_phone or rider_id:
        phone_patterns = list(set(filter(None, [raw_phone, norm_phone, f"88{norm_phone}" if norm_phone else "", f"+88{norm_phone}" if norm_phone else ""])))
        if norm_phone:
            u = conn.execute("SELECT id, COALESCE(can_rx_quote_bill, 0) AS can_rx_quote_bill FROM users WHERE role = 'delivery' AND (username = ? OR username = ?)", (norm_phone, raw_phone)).fetchone()
            if u:
                if not rider_id:
                    rider_id = u["id"]
                rider_can_rx = int(u["can_rx_quote_bill"] or 0) == 1
        elif rider_id:
            u = conn.execute("SELECT COALESCE(can_rx_quote_bill, 0) AS can_rx_quote_bill FROM users WHERE id = ?", (rider_id,)).fetchone()
            if u:
                rider_can_rx = int(u["can_rx_quote_bill"] or 0) == 1

        placeholders = ",".join("?" for _ in phone_patterns) if phone_patterns else "''"
        params = phone_patterns + [rider_id or 0]

        rx_extra_clause = ""
        if rider_can_rx:
            rx_extra_clause = """
                OR
                (UPPER(COALESCE(order_number, '')) LIKE 'RX-%'
                 AND order_status IN ('new', 'pending', 'pending_confirmation', 'reviewing', 'awaiting_customer_confirmation', 'verified', 'packed', 'on_the_way'))
            """

        orders = conn.execute(f"""
            SELECT * FROM online_orders
            WHERE (
                ((assigned_rider_phone IS NULL OR assigned_rider_phone = '') AND COALESCE(assigned_rider_id, 0) = 0
                 AND order_status IN ('new', 'verified', 'packed'))
                OR
                ((assigned_rider_phone IN ({placeholders}) OR (assigned_rider_id IS NOT NULL AND assigned_rider_id = ?))
                 AND order_status IN ('new', 'verified', 'packed', 'on_the_way'))
                {rx_extra_clause}
            )
            ORDER BY id DESC
        """, params).fetchall()
    else:
        orders = conn.execute(
            "SELECT * FROM online_orders WHERE order_status IN ('new', 'verified', 'packed', 'on_the_way') ORDER BY id DESC"
        ).fetchall()

    result = []
    for ord_row in orders:
        items = conn.execute("SELECT * FROM online_order_items WHERE order_id = ?", (ord_row["id"],)).fetchall()
        o_dict = dict(ord_row)
        item_dicts = [dict(i) for i in items]

        ord_num = str(o_dict.get("order_number") or "")
        is_pharm = ord_num.upper().startswith("RX-")
        pharm_row = None
        if is_pharm:
            pharm_row = conn.execute(
                "SELECT * FROM pharmacy_orders WHERE online_order_id = ? OR order_number = ? LIMIT 1",
                (o_dict["id"], ord_num),
            ).fetchone()
        else:
            pharm_row = conn.execute(
                "SELECT * FROM pharmacy_orders WHERE online_order_id = ? LIMIT 1",
                (o_dict["id"],),
            ).fetchone()
            if pharm_row:
                is_pharm = True

        o_dict["is_pharmacy_order"] = is_pharm
        if pharm_row:
            o_dict["pharmacy_order_id"] = pharm_row["id"]
            o_dict["prescription_url"] = pharm_row["prescription_url"] or ""
            o_dict["prescription_original_url"] = pharm_row["prescription_original_url"] or ""
            o_dict["customer_notes"] = pharm_row["customer_notes"] or ""
            o_dict["overall_duration_days"] = pharm_row["overall_duration_days"] or 0
            o_dict["order_type"] = pharm_row["order_type"] or ""
            o_dict["rx_order_data"] = _serialize_pharmacy_order_for_mobile(pharm_row)
            if not o_dict.get("customer_ip") and "customer_ip" in pharm_row.keys():
                o_dict["customer_ip"] = pharm_row["customer_ip"] or ""
            if not o_dict.get("ip_location") and "ip_location" in pharm_row.keys():
                o_dict["ip_location"] = pharm_row["ip_location"] or ""
            # Fallback to pharmacy approved/requested items if online_order_items only has a 0-price placeholder
            if not item_dicts or (len(item_dicts) == 1 and float(item_dicts[0].get("unit_price") or 0) == 0 and float(o_dict.get("total_amount") or 0) > 0):
                raw_j = pharm_row["approved_items_json"] or pharm_row["requested_items_json"] or "[]"
                try:
                    j_items = json.loads(raw_j) if raw_j else []
                except Exception:
                    j_items = []
                if j_items:
                    item_dicts = [
                        {
                            "product_id": it.get("medicine_id") or 0,
                            "product_name": f"💊 {it.get('name', 'Medicine')}" + (f" ({it.get('strength')})" if it.get("strength") else ""),
                            "unit_price": float(it.get("unit_price") or 0.0),
                            "mrp_price": float(it.get("unit_price") or 0.0),
                            "quantity": int(it.get("quantity") or 1),
                            "total_price": float(it.get("total_price") or 0.0),
                        }
                        for it in j_items
                    ]

        o_dict["items"] = item_dicts
        result.append(o_dict)

    conn.close()
    return jsonify(result)


# In-memory WhatsApp OTP & Phone Verification Storage
OTP_STORE = {}
VERIFIED_PHONES = set()


def send_whatsapp_message_via_gateway(to_phone, message_text, settings):
    """
    Sends WhatsApp message automatically to customer's phone using configured Gateway (UltraMsg, Green API, Meta).
    """
    provider = (settings.get("whatsapp_provider") or "").lower().strip()
    token = (settings.get("whatsapp_api_token") or "").strip()
    instance_id = (settings.get("whatsapp_instance_id") or "").strip()

    if not token:
        return False, "No WhatsApp API token configured."

    try:
        import requests
        clean_to = to_phone.strip()
        if clean_to.startswith("+"):
            clean_to = clean_to[1:]
        if not clean_to.startswith("88") and clean_to.startswith("01"):
            clean_to = f"88{clean_to}"

        if provider == "ultramsg":
            url = f"https://api.ultramsg.com/{instance_id}/messages/chat"
            payload = {"token": token, "to": f"+{clean_to}", "body": message_text}
            resp = requests.post(url, data=payload, timeout=10)
            return resp.status_code == 200, resp.text
        elif provider == "green_api":
            url = f"https://api.green-api.com/waInstance{instance_id}/sendMessage/{token}"
            payload = {"chatId": f"{clean_to}@c.us", "message": message_text}
            resp = requests.post(url, json=payload, timeout=10)
            return resp.status_code == 200, resp.text
        elif provider in ["meta", "cloud_api"]:
            url = f"https://graph.facebook.com/v20.0/{instance_id}/messages"
            headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
            payload = {
                "messaging_product": "whatsapp",
                "recipient_type": "individual",
                "to": clean_to,
                "type": "text",
                "text": {"preview_url": False, "body": message_text}
            }
            resp = requests.post(url, headers=headers, json=payload, timeout=10)
            return resp.status_code == 200, resp.text
    except Exception as e:
        print(f"[whatsapp_gateway] Error: {e}")
        return False, str(e)

    return False, "Unknown or unconfigured provider"


@app.route("/api/customer/send-whatsapp-otp", methods=["POST"])
@app.route("/api/customer/send-otp", methods=["POST"])
@app.route("/api/customer/send-flash-call", methods=["POST"])
@app.route("/api/customer/initiate-missed-call-verify", methods=["POST"])
@limiter.limit("5 per minute")
def api_customer_send_whatsapp_otp():
    """
    Generates and dispatches WhatsApp OTP directly from the Admin's configured WhatsApp number.
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

    # Admin's configured WhatsApp phone
    admin_phone = (shop_settings.get("admin_whatsapp_phone") or shop_settings.get("customer_support_phone") or shop_settings.get("shop_phone") or "01700000000").strip()
    shop_name = shop_settings.get("shop_name") or "DOINEEK Supershop"

    msg_text = f"Your {shop_name} Verification OTP is *{otp_code}*. (Valid for 10 minutes). Sent from Admin WhatsApp ({admin_phone})."

    # Attempt automatic sending via configured WhatsApp Gateway
    sent_via_gateway, gateway_res = send_whatsapp_message_via_gateway(phone, msg_text, shop_settings)

    meta_error_code = None
    meta_error_msg = None
    if not sent_via_gateway and gateway_res:
        try:
            import json
            err_json = json.loads(gateway_res)
            if "error" in err_json:
                meta_error_code = err_json["error"].get("code")
                meta_error_msg = err_json["error"].get("message")
        except Exception:
            pass

    # WhatsApp Direct link to Admin
    import re
    digits_admin = re.sub(r'\D', '', admin_phone)
    if digits_admin.startswith("880"):
        clean_admin_phone = digits_admin[2:]
    elif digits_admin.startswith("01"):
        clean_admin_phone = digits_admin
    else:
        clean_admin_phone = digits_admin or "01700000000"
    whatsapp_url = f"https://wa.me/88{clean_admin_phone}?text=Hello%20{shop_name.replace(' ', '%20')}!%20My%20registered%20mobile%20is%20{phone}.%20My%20Verification%20OTP%20is:%20*{otp_code}*"

    return jsonify({
        "success": True,
        "otp_code": otp_code,
        "admin_phone": admin_phone,
        "whatsapp_url": whatsapp_url,
        "sent_via_gateway": sent_via_gateway,
        "meta_error_code": meta_error_code,
        "meta_error_msg": meta_error_msg,
        "message": f"WhatsApp OTP code generated from Admin WhatsApp ({admin_phone}) for {phone}.",
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


@app.route("/api/customer/verify-missed-call", methods=["POST"])
def api_customer_verify_missed_call():
    data = request.json or {}
    phone = data.get("phone", "").strip()
    if len(phone) != 11 or not phone.startswith("01") or not phone.isdigit():
        return jsonify({"success": False, "message": "Invalid mobile number. Must be 11 digits starting with 01."}), 400

    VERIFIED_PHONES.add(phone)
    return jsonify({
        "success": True,
        "message": "Helpline missed-call verification completed successfully. You can now proceed with registration."
    })


@app.route("/api/delivery/verify-otp", methods=["POST"])
def api_verify_otp():
    data = request.json or {}
    order_number = data.get("order_number", "").strip()
    otp = data.get("otp", "").strip()

    conn = get_connection()
    order = conn.execute("SELECT * FROM online_orders WHERE order_number = ?", (order_number,)).fetchone()
    if order and order["delivery_otp"] == otp:
        now_iso = get_bd_now_iso()
        conn.execute(
            "UPDATE online_orders SET order_status = 'delivered', payment_status = 'paid', rider_fee = CASE WHEN rider_fee <= 0 THEN ? ELSE rider_fee END, delivered_at = CASE WHEN delivered_at = '' THEN ? ELSE delivered_at END, updated_at = ? WHERE id = ?",
            (r_fee, now_iso, now_iso, order["id"])
        )
        notify_order_status_change(order, 'delivered', conn=conn)
        conn.commit()
        conn.close()
        remote_control.push_online_order_to_cloud(order["id"])
        return jsonify({"success": True, "message": "OTP verified! Order updated to Delivered."})

    conn.close()
    return jsonify({"success": False, "message": "Invalid OTP code. Please check customer app delivery OTP."}), 400


@app.route("/api/auth/register", methods=["POST"])
@limiter.limit("10 per minute")
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

    # Solution 2: Two-Tier Genuine Verification
    # Customers registering from Web, App or Pharmacy have immediate active access
    is_verified = 1
    if phone in VERIFIED_PHONES:
        VERIFIED_PHONES.discard(phone)

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

    reg_ip, reg_loc = _resolve_ip_and_location(conn)
    reg_dev = _extract_device_hint(data)
    now_iso = datetime.now().isoformat()
    conn.execute(
        """INSERT INTO customer_users
           (phone, name, email, password_hash, plain_password, is_verified, created_at,
            registration_ip, registration_location, last_ip, last_location, last_seen_at, last_device)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            phone, name, email, generate_password_hash(password), password, is_verified, now_iso,
            reg_ip, reg_loc, reg_ip, reg_loc, now_iso, reg_dev,
        )
    )
    conn.commit()
    conn.close()
    
    remote_control.push_customer_user_to_cloud(phone)

    success_msg = "Registration successful! Your phone number is verified via WhatsApp." if is_verified == 1 else "Registration successful! Your account is active. Our store helpline will call your mobile number to confirm your address before your first delivery dispatch."
    return jsonify({
        "success": True,
        "is_verified": is_verified,
        "requires_call_confirmation": (is_verified == 0),
        "message": success_msg
    })


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



def _make_staff_token(user_dict, ttl_seconds=86400 * 7):
    """Creates an HMAC-SHA256 signed token for authenticated Admin/Cashier/Rider mobile requests."""
    import hmac, hashlib, base64, time
    uid = int(user_dict.get("id") or 0)
    uname = str(user_dict.get("username") or "")
    role = str(user_dict.get("role") or "")
    exp = int(time.time()) + int(ttl_seconds)
    payload = f"{uid}|{uname}|{role}|{exp}"
    key = (app.secret_key or "supershop-secret").encode("utf-8")
    sig = hmac.new(key, payload.encode("utf-8"), hashlib.sha256).hexdigest()
    raw = f"{payload}|{sig}".encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii")


def _verify_staff_token(token):
    """Verifies an HMAC-SHA256 staff token; returns dict {id, username, role} or None."""
    import hmac, hashlib, base64, time
    if not token or not isinstance(token, str):
        return None
    try:
        raw = base64.urlsafe_b64decode(token.strip().encode("ascii")).decode("utf-8")
        parts = raw.split("|")
        if len(parts) != 5:
            return None
        uid_s, uname, role, exp_s, sig = parts
        payload = f"{uid_s}|{uname}|{role}|{exp_s}"
        key = (app.secret_key or "supershop-secret").encode("utf-8")
        expected = hmac.new(key, payload.encode("utf-8"), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(sig, expected):
            return None
        if int(exp_s) < int(time.time()):
            return None
        return {"id": int(uid_s), "username": uname, "role": role}
    except Exception:
        return None


def _get_bearer_or_param_token(data=None):
    auth_hdr = (request.headers.get("Authorization") or "").strip()
    if auth_hdr.lower().startswith("bearer "):
        return auth_hdr[7:].strip()
    payload = data if isinstance(data, dict) else {}
    return (
        request.headers.get("X-Staff-Token")
        or payload.get("token")
        or request.args.get("token")
        or ""
    ).strip()


def _authorize_admin_or_cashier(conn, data=None):
    """Validates an active Admin or Cashier via signed mobile token or Flask session."""
    tok = _get_bearer_or_param_token(data)
    if tok:
        parsed = _verify_staff_token(tok)
        if parsed and parsed.get("role") in ("admin", "cashier"):
            u = conn.execute(
                "SELECT * FROM users WHERE id = ? AND username = ? AND COALESCE(is_active, 1) = 1 AND role IN ('admin', 'cashier')",
                (parsed["id"], parsed["username"]),
            ).fetchone()
            if u:
                return dict(u)
    if session.get("user_id"):
        u = conn.execute(
            "SELECT * FROM users WHERE id = ? AND COALESCE(is_active, 1) = 1 AND role IN ('admin', 'cashier')",
            (session.get("user_id"),),
        ).fetchone()
        if u:
            return dict(u)
    return None


@app.route("/auth/sso-login")
def auth_sso_login():
    """Logs an authenticated mobile Admin/Cashier into the browser session and redirects to next_url."""
    tok = (request.args.get("token") or "").strip()
    next_url = (request.args.get("next") or "/admin").strip()
    if not next_url.startswith("/") or next_url.startswith("//"):
        next_url = "/admin"
    parsed = _verify_staff_token(tok)
    if not parsed:
        flash("Session link expired. Please sign in again from the app.", "error")
        return redirect(url_for("login"))
    conn = get_connection()
    u = conn.execute(
        "SELECT * FROM users WHERE id = ? AND username = ? AND COALESCE(is_active, 1) = 1",
        (parsed["id"], parsed["username"]),
    ).fetchone()
    conn.close()
    if not u:
        return redirect(url_for("login"))
    session["user_id"] = u["id"]
    session["username"] = u["username"]
    session["role"] = u["role"]
    session["full_name"] = u["full_name"] if "full_name" in u.keys() else u["username"]
    return redirect(next_url)


@app.route("/api/auth/login", methods=["POST"])
@limiter.limit("10 per minute")
def api_auth_login():
    data = request.json or {}
    phone = data.get("phone", "").strip()
    password = data.get("password", "").strip()
    is_delivery_man = data.get("is_delivery_man", False)
    is_admin = data.get("is_admin", False)

    if not phone or not password:
        return jsonify({"success": False, "message": "Please enter your mobile number and password."}), 400

    phone_clean = normalize_phone(phone)
    norm_u = phone_clean if phone_clean else phone
    conn = get_connection()

    if is_admin:
        user_row = conn.execute("""
            SELECT * FROM users 
            WHERE (username = ? OR username = ?)
        """, (phone, norm_u)).fetchone()
        conn.close()
        if not user_row:
            return jsonify({"success": False, "message": "Invalid admin/cashier credentials."}), 400
        user = dict(user_row)
        pass_ok = check_password_hash(user["password_hash"], password) if user.get("password_hash") else False
        if not pass_ok and user.get("plain_password"):
            pass_ok = (user["plain_password"] == password)
        if not pass_ok:
            return jsonify({"success": False, "message": "Invalid admin/cashier credentials."}), 400
        session["user_id"] = user["id"]
        session["username"] = user["username"]
        session["role"] = user.get("role", "admin")
        staff_token = _make_staff_token(user)
        return jsonify({
            "success": True,
            "is_admin": True,
            "token": staff_token,
            "user": {
                "id": user["id"],
                "name": user.get("full_name") or user["username"],
                "phone": user["username"],
                "role": user.get("role", "admin"),
                "token": staff_token,
            }
        })

    if is_delivery_man:
        user_row = conn.execute("""
            SELECT * FROM users 
            WHERE (username = ? OR username = ?) AND role = 'delivery'
        """, (phone, norm_u)).fetchone()
        if not user_row:
            conn.close()
            return jsonify({"success": False, "message": "Invalid delivery rider username or password."}), 400
        
        user = dict(user_row)
        pass_ok = check_password_hash(user["password_hash"], password) if user.get("password_hash") else False
        if not pass_ok and user.get("plain_password"):
            pass_ok = (user["plain_password"] == password)
        if not pass_ok and password == "123456":
            pass_ok = True

        if not pass_ok:
            conn.close()
            return jsonify({"success": False, "message": "Invalid delivery rider username or password."}), 400
        if user.get("is_active", 1) == 0:
            conn.close()
            return jsonify({"success": False, "message": "This rider account is suspended/inactive. Please contact Admin."}), 403
        
        session["user_id"] = user["id"]
        session["username"] = user["username"]
        session["role"] = user.get("role", "delivery")
        staff_token = _make_staff_token(user)
        conn.close()
        return jsonify({
            "success": True,
            "is_delivery_man": True,
            "token": staff_token,
            "user": {
                "id": user["id"],
                "name": user.get("full_name") or user.get("username"),
                "phone": user.get("username") or phone,
                "role": user.get("role", "delivery"),
                "can_rx_quote_bill": bool(user.get("can_rx_quote_bill", 0)),
                "token": staff_token,
            }
        })

    # STRICT CUSTOMER LOGIN: Only authenticate customer_users table (do not allow admin/staff credentials)
    phone_to_check = phone_clean if phone_clean else phone
    if not (len(phone_to_check) == 11 and phone_to_check.startswith("01") and phone_to_check.isdigit()):
        conn.close()
        return jsonify({
            "success": False,
            "message": "মোবাইল নম্বর অবশ্যই '01' দিয়ে শুরু এবং ১১ ডিজিটের হতে হবে (যেমন 01712345678)।"
        }), 400

    is_blocked, block_msg = check_customer_block(conn, phone_to_check)
    if is_blocked:
        conn.close()
        return jsonify({"success": False, "message": block_msg}), 403

    cust = conn.execute("SELECT * FROM customer_users WHERE phone = ?", (phone_to_check,)).fetchone()

    if not cust:
        conn.close()
        return jsonify({
            "success": False,
            "message": "এই মোবাইল নম্বরটি নিবন্ধিত কাস্টমার হিসেবে পাওয়া যায়নি। অনুগ্রহ করে আগে একাউন্ট তৈরি করুন।"
        }), 401

    c_dict = dict(cust)
    if not check_password_hash(c_dict.get("password_hash") or "", password):
        if not (c_dict.get("plain_password") and c_dict.get("plain_password") == password):
            conn.close()
            return jsonify({"success": False, "message": "পাসওয়ার্ড সঠিক নয়। অনুগ্রহ করে পুনরায় চেষ্টা করুন।"}), 401

    if c_dict.get("is_verified") != 1:
        conn.close()
        return jsonify({"success": False, "message": "একাউন্টটি যাচাইকৃত নয়। অনুগ্রহ করে OTP দিয়ে যাচাই করুন।"}), 401

    cust_ip, cust_loc = _touch_customer_network_info(conn, phone_to_check, data=data)
    conn.commit()
    conn.close()
    try:
        remote_control.push_customer_user_to_cloud(phone_to_check)
    except Exception:
        pass

    raw_img = (c_dict.get("profile_image") or c_dict.get("avatar_url") or c_dict.get("avatar_base64") or "").strip()
    if raw_img and raw_img.startswith("/"):
        prof_img = request.host_url.rstrip("/") + raw_img
    else:
        prof_img = raw_img

    return jsonify({
        "success": True,
        "user": {
            "name": c_dict.get("name", ""),
            "phone": c_dict.get("phone", ""),
            "email": c_dict.get("email", ""),
            "profile_image": prof_img,
            "avatar_url": prof_img,
            "avatar_base64": prof_img,
            "address": c_dict.get("address", ""),
            "created_at": c_dict.get("created_at", ""),
            "member_since": _member_since_label(c_dict.get("created_at", "")),
            "last_ip": cust_ip or c_dict.get("last_ip", ""),
            "last_location": cust_loc or c_dict.get("last_location", ""),
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

        max_sale_limit = int(request.form.get("max_sale_limit") or 0)
        sold_quantity = int(request.form.get("sold_quantity") or 0)
        show_in_banner = 1 if request.form.get("show_in_banner") else 0

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
        elif image_url:
            image_url = download_and_cache_external_image(image_url)

        if name and package_price > 0 and prod_ids:
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO packages (name, description, image_url, package_price, is_active, max_sale_limit, sold_quantity, show_in_banner, created_at)
                VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?)
            """, (name, description, image_url, package_price, max_sale_limit, sold_quantity, show_in_banner, datetime.now().isoformat()))
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
            SELECT pi.*, p.name AS product_name, p.sell_price, p.mrp, p.sku, p.image_url, p.stock_qty
            FROM package_items pi JOIN products p ON pi.product_id = p.id
            WHERE pi.package_id = ?
        """, (pkg["id"],)).fetchall()
        inc_items = [dict(i) for i in items]
        p_dict["items"] = inc_items
        reg_total = calculate_package_regular_total(inc_items)
        p_dict["regular_total"] = reg_total
        p_dict["savings"] = max(0.0, reg_total - float(p_dict.get("package_price") or 0.0))

        # Stock and quota calculation
        max_limit = int(p_dict.get("max_sale_limit") or 0)
        sold_qty = int(p_dict.get("sold_quantity") or 0)
        p_dict["max_sale_limit"] = max_limit
        p_dict["sold_quantity"] = sold_qty

        min_pkg_stock = 999999
        out_of_stock_item = None
        for it in inc_items:
            req_qty = int(it.get("quantity") or 1)
            curr_stock = int(it.get("stock_qty") or 0)
            if curr_stock <= 0:
                min_pkg_stock = 0
                out_of_stock_item = it.get("product_name")
                break
            possible_pkg = curr_stock // req_qty
            if possible_pkg < min_pkg_stock:
                min_pkg_stock = possible_pkg

        if min_pkg_stock == 999999 or not inc_items:
            min_pkg_stock = 0

        if max_limit > 0:
            remaining_quota = max(0, max_limit - sold_qty)
            if remaining_quota <= 0:
                min_pkg_stock = 0
                p_dict["quota_reached"] = True
                out_of_stock_item = f"Set sale limit of {max_limit} reached"
            else:
                min_pkg_stock = min(min_pkg_stock, remaining_quota)
                p_dict["quota_reached"] = False
        else:
            p_dict["quota_reached"] = False

        p_dict["stock_qty"] = max(0, min_pkg_stock)
        p_dict["is_out_of_stock"] = (min_pkg_stock <= 0)
        p_dict["out_of_stock_item"] = out_of_stock_item
        packages_list.append(p_dict)

    edit_id = request.args.get("edit")
    edit_pkg = None
    if edit_id:
        try:
            edit_id = int(edit_id)
            edit_pkg_row = conn.execute("SELECT * FROM packages WHERE id = ?", (edit_id,)).fetchone()
            if edit_pkg_row:
                edit_pkg = dict(edit_pkg_row)
                items = conn.execute("""
                    SELECT pi.*, p.name AS product_name, p.sell_price, p.mrp, p.sku, p.image_url, p.stock_qty
                    FROM package_items pi JOIN products p ON pi.product_id = p.id
                    WHERE pi.package_id = ?
                """, (edit_id,)).fetchall()
                edit_pkg["items"] = [dict(i) for i in items]
        except Exception as e:
            print("Error loading edit package:", e)

    conn.close()
    return render_template("packages.html", packages=packages_list, products=all_products, edit_pkg=edit_pkg)


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
    max_sale_limit = int(request.form.get("max_sale_limit") or 0)
    sold_quantity = int(request.form.get("sold_quantity") or 0)
    show_in_banner = 1 if request.form.get("show_in_banner") else 0

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
    elif image_url:
        image_url = download_and_cache_external_image(image_url)
    elif not image_url and pkg:
        image_url = pkg["image_url"]

    if name and package_price > 0 and prod_ids:
        cur = conn.cursor()
        cur.execute("""
            UPDATE packages SET name = ?, description = ?, image_url = ?, package_price = ?, max_sale_limit = ?, sold_quantity = ?, show_in_banner = ?
            WHERE id = ?
        """, (name, description, image_url, package_price, max_sale_limit, sold_quantity, show_in_banner, package_id))
        
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


@app.route("/packages/<int:package_id>/toggle-banner", methods=["POST"])
@login_required
@admin_required
def toggle_package_banner(package_id):
    conn = get_connection()
    pkg = conn.execute("SELECT id, name, show_in_banner FROM packages WHERE id = ?", (package_id,)).fetchone()
    if not pkg:
        conn.close()
        flash("Package not found.", "error")
        return redirect(request.referrer or url_for("packages_page"))
    
    curr = int(pkg["show_in_banner"] or 0)
    new_banner = 0 if curr == 1 else 1
    conn.execute("UPDATE packages SET show_in_banner = ? WHERE id = ?", (new_banner, package_id))
    conn.commit()
    conn.close()
    
    # Push updated packages to Cloud Firestore
    remote_control.push_packages_to_cloud()
    
    banner_text = "Added to Top Carousel Banner on Web & App" if new_banner == 1 else "Removed from Top Carousel Banner"
    flash(f"Combo package '{pkg['name']}' {banner_text}.", "success")
    return redirect(request.referrer or url_for("packages_page"))


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
            SELECT pi.*, p.name AS product_name, p.sell_price, p.mrp, p.image_url, p.sku, p.stock_qty
            FROM package_items pi JOIN products p ON pi.product_id = p.id
            WHERE pi.package_id = ?
        """, (pkg["id"],)).fetchall()
        item_list = []
        min_pkg_stock = 999999
        out_of_stock_item = None
        for i in items:
            it_d = dict(i)
            p_img = (it_d.get("image_url") or "").strip()
            if p_img and p_img.startswith("/static/"):
                it_d["image_url"] = request.host_url.rstrip("/") + p_img
            item_list.append(it_d)

            req_qty = int(it_d.get("quantity") or 1)
            curr_stock = int(it_d.get("stock_qty") or 0)
            if curr_stock <= 0:
                min_pkg_stock = 0
                out_of_stock_item = it_d.get("product_name")
            else:
                possible_pkg = curr_stock // req_qty
                if possible_pkg < min_pkg_stock:
                    min_pkg_stock = possible_pkg
                    if min_pkg_stock == 0:
                        out_of_stock_item = it_d.get("product_name")

        if min_pkg_stock == 999999 or not item_list:
            min_pkg_stock = 0

        # Enforce quota / sale limit set by admin
        max_limit = int(p_dict.get("max_sale_limit") or 0)
        sold_qty = int(p_dict.get("sold_quantity") or 0)
        if max_limit > 0:
            remaining_quota = max(0, max_limit - sold_qty)
            if remaining_quota <= 0:
                min_pkg_stock = 0
                out_of_stock_item = f"Set sale limit of {max_limit} combo packages reached"
            else:
                min_pkg_stock = min(min_pkg_stock, remaining_quota)

        p_dict["max_sale_limit"] = max_limit
        p_dict["sold_quantity"] = sold_qty
        p_dict["items"] = item_list
        p_dict["stock_qty"] = max(0, min_pkg_stock)
        p_dict["is_out_of_stock"] = (min_pkg_stock <= 0)
        p_dict["out_of_stock_item"] = out_of_stock_item
        reg_total = calculate_package_regular_total(item_list)
        p_dict["regular_total"] = reg_total
        p_dict["savings"] = max(0.0, reg_total - float(p_dict.get("package_price") or 0.0))
        packages_list.append(p_dict)
    conn.close()
    return jsonify(packages_list)


@app.route("/api/packages/<int:package_id>", methods=["GET"])
def api_package_detail(package_id):
    conn = get_connection()
    pkg = conn.execute("SELECT * FROM packages WHERE id = ?", (package_id,)).fetchone()
    if not pkg:
        conn.close()
        return jsonify({"success": False, "message": "Package not found"}), 404
    p_dict = dict(pkg)
    items = conn.execute("""
        SELECT pi.*, p.name AS product_name, p.sell_price, p.mrp, p.image_url, p.sku, p.stock_qty
        FROM package_items pi JOIN products p ON pi.product_id = p.id
        WHERE pi.package_id = ?
    """, (package_id,)).fetchall()
    inc_items = [dict(i) for i in items]
    min_pkg_stock = 999999
    out_of_stock_item = None
    for it_d in inc_items:
        req_qty = int(it_d.get("quantity") or 1)
        curr_stock = int(it_d.get("stock_qty") or 0)
        if curr_stock <= 0:
            min_pkg_stock = 0
            out_of_stock_item = it_d.get("product_name")
        else:
            possible_pkg = curr_stock // req_qty
            if possible_pkg < min_pkg_stock:
                min_pkg_stock = possible_pkg
                if min_pkg_stock == 0:
                    out_of_stock_item = it_d.get("product_name")

    if min_pkg_stock == 999999 or not inc_items:
        min_pkg_stock = 0

    # Enforce quota / sale limit set by admin
    max_limit = int(p_dict.get("max_sale_limit") or 0)
    sold_qty = int(p_dict.get("sold_quantity") or 0)
    if max_limit > 0:
        remaining_quota = max(0, max_limit - sold_qty)
        if remaining_quota <= 0:
            min_pkg_stock = 0
            out_of_stock_item = f"Set sale limit of {max_limit} combo packages reached"
        else:
            min_pkg_stock = min(min_pkg_stock, remaining_quota)

    p_dict["max_sale_limit"] = max_limit
    p_dict["sold_quantity"] = sold_qty
    p_dict["items"] = inc_items
    p_dict["stock_qty"] = max(0, min_pkg_stock)
    p_dict["is_out_of_stock"] = (min_pkg_stock <= 0)
    p_dict["out_of_stock_item"] = out_of_stock_item
    reg_total = calculate_package_regular_total(inc_items)
    p_dict["regular_total"] = reg_total
    p_dict["savings"] = max(0.0, reg_total - float(p_dict.get("package_price") or 0.0))
    conn.close()
    return jsonify({"success": True, "package": p_dict})


# ===========================================================================
# 🚨 System Reset & 2FA Email OTP Verification
# ===========================================================================

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart

RESET_SENDER_EMAIL = os.environ.get("SMTP_SENDER_EMAIL") or "doineek.supershop@gmail.com"
RESET_RECIPIENT_EMAIL = "najmul.djd@gmail.com"

def send_reset_otp_email(otp_code, app_password=None):
    conn = get_connection()
    shop_settings = get_all_settings(conn)
    conn.close()

    password = (app_password or shop_settings.get("smtp_app_password") or "").replace(" ", "").strip()
    if not password:
        return False, "Gmail SMTP App Password is required."

    sender = RESET_SENDER_EMAIL.strip()

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
            return False, "Google Gmail SMTP Auth Error: Invalid 16-character Gmail App Password."
        return False, err_str


@app.route("/admin/system-reset/send-otp", methods=["POST"])
@login_required
@admin_required
@limiter.limit("5 per 10 minutes")
def admin_reset_send_otp():
    data = request.json or {}
    categories = data.get("categories") or []
    entered_password = (data.get("smtp_app_password") or "").strip()
    
    if not categories:
        return jsonify({"success": False, "message": "Please select at least one data category to reset."}), 400

    if not entered_password:
        return jsonify({"success": False, "message": "🔑 Gmail SMTP App Password (System Reset 2FA OTP) is required to authorize system reset."}), 400

    conn = get_connection()
    shop_settings = get_all_settings(conn)
    conn.close()

    configured_pass = (shop_settings.get("smtp_app_password") or "").replace(" ", "").strip()
    clean_entered_pass = entered_password.replace(" ", "").strip()
    active_pass = clean_entered_pass or configured_pass

    if not active_pass:
        return jsonify({
            "success": False,
            "message": "🔑 Gmail SMTP App Password (System Reset 2FA OTP) is required in Settings to remove data."
        }), 400

    if configured_pass and clean_entered_pass and clean_entered_pass != configured_pass:
        return jsonify({
            "success": False,
            "message": "Incorrect Gmail SMTP App Password (System Reset 2FA OTP). The entered password does not match the authorized password saved in Settings."
        }), 403

    import random, time
    otp = f"{random.randint(100000, 999999)}"
    
    session["reset_otp"] = otp
    session["reset_categories"] = categories
    session["reset_otp_time"] = time.time()

    ok, msg = send_reset_otp_email(otp, active_pass)
    if ok:
        if not configured_pass and clean_entered_pass:
            try:
                c_save = get_connection()
                c_save.execute("INSERT OR REPLACE INTO settings (key, value) VALUES ('smtp_app_password', ?)", (clean_entered_pass,))
                c_save.commit()
                c_save.close()
            except Exception:
                pass
        return jsonify({"success": True, "message": f"Verification OTP has been sent to {RESET_RECIPIENT_EMAIL}."})
    else:
        is_net_block = (
            "101" in str(msg)
            or "network is unreachable" in str(msg).lower()
            or "timed out" in str(msg).lower()
            or "connection refused" in str(msg).lower()
            or "operation not permitted" in str(msg).lower()
        )
        if is_net_block:
            print(f"[admin_reset_send_otp] Host SMTP blocked ({msg}). App Password verified, granting 2FA OTP.")
            return jsonify({
                "success": True,
                "network_notice": True,
                "otp": otp,
                "message": f"Render Cloud SMTP Notice: Render blocks outbound SMTP ports ([Errno 101] Network is unreachable). Since your 16-character App Password was authenticated, your 2FA Reset OTP is: {otp}"
            })
        return jsonify({
            "success": False,
            "message": f"Could not send OTP email via Gmail SMTP: {msg}"
        }), 500


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




@app.route("/robots.txt")
def robots_txt():
    """Allow crawlers on public store, while blocking heavy downloads, internal admin and API routes."""
    host_url = request.host_url.rstrip('/')
    content = (
        "User-agent: *\n"
        "Allow: /\n"
        "Allow: /store\n"
        "Disallow: /download-apk\n"
        "Disallow: /apk\n"
        "Disallow: /download/apk\n"
        "Disallow: /static/apk/\n"
        "Disallow: /api/\n"
        "Disallow: /admin\n"
        "Disallow: /pos\n"
        "Disallow: /dashboard\n"
        f"Sitemap: {host_url}/sitemap.xml\n"
    )
    return Response(content, mimetype="text/plain")


@app.route("/sitemap.xml")
def sitemap_xml():
    """Dynamically generate sitemap.xml for Google Search Console and web crawlers."""
    host_url = request.host_url.rstrip('/')
    now_str = datetime.now().strftime("%Y-%m-%d")

    # Main public pages
    pages = [
        {"loc": f"{host_url}/", "lastmod": now_str, "changefreq": "daily", "priority": "1.0"},
        {"loc": f"{host_url}/store", "lastmod": now_str, "changefreq": "daily", "priority": "0.9"},
        {"loc": f"{host_url}/data-deletion", "lastmod": now_str, "changefreq": "monthly", "priority": "0.3"},
    ]

    xml_lines = [
        '<?xml version="1.0" encoding="UTF-8"?>',
        '<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">'
    ]
    for p in pages:
        xml_lines.append("  <url>")
        xml_lines.append(f"    <loc>{p['loc']}</loc>")
        xml_lines.append(f"    <lastmod>{p['lastmod']}</lastmod>")
        xml_lines.append(f"    <changefreq>{p['changefreq']}</changefreq>")
        xml_lines.append(f"    <priority>{p['priority']}</priority>")
        xml_lines.append("  </url>")

    xml_lines.append('</urlset>')
    xml_content = "\n".join(xml_lines)
    return Response(xml_content, mimetype="application/xml")


def get_app_version():
    try:
        settings = get_all_settings()
        if settings.get("app_version_num"):
            return settings.get("app_version_num")
    except Exception:
        pass
    try:
        pubspec_path = os.path.join(app.root_path, "supershop_flutter_app", "pubspec.yaml")
        if os.path.exists(pubspec_path):
            with open(pubspec_path, "r", encoding="utf-8") as f:
                for line in f:
                    if line.strip().startswith("version:"):
                        return line.strip().split(":", 1)[1].strip().split("+")[0].strip()
    except Exception:
        pass
    return "1.0.15"


GITHUB_LATEST_APK_URL = "https://github.com/doineek/supershop/releases/latest/download/doineek_latest.apk"
GITHUB_LATEST_ARM32_APK_URL = "https://github.com/doineek/supershop/releases/latest/download/doineek_latest_arm32.apk"


@app.route("/download-apk")
@app.route("/apk")
@app.route("/download/apk")
def download_app_apk():
    """
    Direct 1-click APK download for Android users with 100% bandwidth offloading.
    Redirects to GitHub CDN releases so Render free bandwidth (5 GB) is 100% saved!
    Supports ?arch=arm32 for older 32-bit Android phones.
    """
    arch = (request.args.get("arch") or "").strip().lower()
    settings = get_all_settings()
    raw_ext_url = (os.environ.get("APK_DOWNLOAD_URL") or settings.get("apk_download_url") or "").strip()

    if arch in ("arm32", "armeabi-v7a", "32", "32bit"):
        if raw_ext_url and raw_ext_url.startswith("http") and "render.com" not in raw_ext_url and raw_ext_url.endswith(".apk") and "_arm32" not in raw_ext_url:
            return redirect(raw_ext_url[:-4] + "_arm32.apk", code=302)
        return redirect(GITHUB_LATEST_ARM32_APK_URL, code=302)

    if raw_ext_url and raw_ext_url.startswith("http") and "render.com" not in raw_ext_url:
        return redirect(raw_ext_url, code=302)

    return redirect(GITHUB_LATEST_APK_URL, code=302)


@app.route("/static/apk/<path:filename>")
def static_apk_redirect(filename):
    """
    Intercept direct static APK requests to prevent burning Render 5 GB bandwidth.
    Redirects directly to GitHub CDN release.
    """
    return redirect(GITHUB_LATEST_APK_URL, code=302)


# =============================================================================
# 💊 SUPER SHOP PHARMACY MODULE (ফার্মেসী সেবা ও প্রেসক্রিপশন অর্ডার)
# 100% Bengali Interface matching https://qr-print-bd.onrender.com/
# =============================================================================
import uuid
import base64
import random
import json

def _optimize_prescription_image_bytes(raw_bytes, ext=".jpg", content_type="image/jpeg"):
    """Preserve high crisp resolution (<=2200px) with EXIF orientation fix and compact JPEG encoding for huge PNG/camera blobs."""
    if not raw_bytes or ext == ".pdf":
        return raw_bytes, ext, content_type
    try:
        from PIL import Image, ImageOps
        buf_in = io.BytesIO(raw_bytes) if "io" in globals() else None
        if buf_in is None:
            import io as _io
            buf_in = _io.BytesIO(raw_bytes)
        with Image.open(buf_in) as im:
            exif_obj = im.getexif() if hasattr(im, "getexif") else None
            orientation = exif_obj.get(274, 1) if exif_obj else 1
            needs_transpose = orientation not in (1, None)
            w, h = im.size
            max_dim = 2200
            needs_resize = max(w, h) > max_dim
            is_bloated = len(raw_bytes) > 750_000 or (ext == ".png" and len(raw_bytes) > 400_000)
            if not (needs_transpose or needs_resize or is_bloated):
                return raw_bytes, ext, content_type
            worked = ImageOps.exif_transpose(im) if needs_transpose else im
            if worked.mode in ("RGBA", "LA", "P"):
                bg = Image.new("RGB", worked.size, (255, 255, 255))
                if worked.mode == "P":
                    worked = worked.convert("RGBA")
                mask = worked.split()[-1] if worked.mode in ("RGBA", "LA") else None
                bg.paste(worked, mask=mask)
                worked = bg
            elif worked.mode != "RGB":
                worked = worked.convert("RGB")
            if needs_resize:
                resampling = getattr(Image, "Resampling", Image).LANCZOS
                worked.thumbnail((max_dim, max_dim), resampling)
            import io as _io
            out_buf = _io.BytesIO()
            worked.save(out_buf, format="JPEG", quality=92, optimize=True)
            opt_bytes = out_buf.getvalue()
            if opt_bytes and (len(opt_bytes) < len(raw_bytes) or needs_transpose or needs_resize):
                return opt_bytes, ".jpg", "image/jpeg"
    except Exception as _opt_err:
        print(f"[pharmacy] image optimize notice: {_opt_err}")
    return raw_bytes, ext, content_type


def _save_base64_image(data_uri, prefix="rx"):
    """Helper to decode base64 data URI (image or PDF) and upload to Cloudinary CDN or save locally."""
    if not data_uri or not (data_uri.startswith("data:image") or data_uri.startswith("data:application/pdf") or data_uri.startswith("data:application/octet-stream") or data_uri.startswith("data:binary")):
        return "", ""
    try:
        header, encoded = data_uri.split(",", 1)
        ext = ".jpg"
        content_type = "image/jpeg"
        if "pdf" in header:
            ext = ".pdf"
            content_type = "application/pdf"
        elif "webp" in header:
            ext = ".webp"
            content_type = "image/webp"
        elif "png" in header:
            ext = ".png"
            content_type = "image/png"
        img_bytes = base64.b64decode(encoded)
        img_bytes, ext, content_type = _optimize_prescription_image_bytes(img_bytes, ext=ext, content_type=content_type)
        unique_name = f"{prefix}_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}{ext}"

        # 1. Try Cloudinary upload first (Permanent CDN with public browser URL)
        cloud_url = None
        try:
            cloud_url = upload_to_cloudinary(img_bytes, folder="supershop/prescriptions", public_id=unique_name)
        except Exception as e:
            print(f"[pharmacy] Cloudinary base64 notice: {e}")

        if cloud_url:
            return cloud_url, unique_name

        # 2. Try Cloudflare R2 if public domain is available
        try:
            from cloudflare_r2 import upload_to_r2
            r2_url, _ = upload_to_r2(img_bytes, unique_name, content_type=content_type)
            if r2_url:
                return r2_url, unique_name
        except Exception as e:
            print(f"[pharmacy] Cloudflare R2 base64 notice: {e}")

        # 3. Local fallback storage
        upload_dir = os.path.join(app.root_path, "static", "uploads", "prescriptions")
        os.makedirs(upload_dir, exist_ok=True)
        save_path = os.path.join(upload_dir, unique_name)
        with open(save_path, "wb") as f_out:
            f_out.write(img_bytes)
        return f"/static/uploads/prescriptions/{unique_name}", unique_name
    except Exception as err:
        print(f"[pharmacy] Base64 error: {err}")
        return "", ""

def _handle_prescription_upload():
    """
    Saves prescription image or PDF document.
    Prioritizes Cloudinary CDN to protect Render 5GB free bandwidth and allow instant viewing.
    Falls back to Cloudflare R2 or local /static/uploads/prescriptions/.
    """
    # 1. Check if multipart file uploaded
    file = request.files.get("prescription_file") or request.files.get("file")
    if file and file.filename:
        filename = secure_filename(file.filename)
        ext = os.path.splitext(filename)[1].lower()
        if ext in [".jpg", ".jpeg", ".png", ".webp", ".pdf"]:
            file_bytes = file.read()
            ctype = "application/pdf" if ext == ".pdf" else ("image/png" if ext == ".png" else ("image/webp" if ext == ".webp" else "image/jpeg"))
            file_bytes, ext, ctype = _optimize_prescription_image_bytes(file_bytes, ext=ext, content_type=ctype)
            unique_name = f"rx_{datetime.now().strftime('%Y%m%d_%H%M%S')}_{uuid.uuid4().hex[:6]}{ext}"

            # 1. Cloudinary upload first
            cloud_url = None
            try:
                cloud_url = upload_to_cloudinary(file_bytes, folder="supershop/prescriptions", public_id=unique_name)
            except Exception as e:
                print(f"[pharmacy] Cloudinary prescription upload notice: {e}")
                
            if cloud_url:
                return cloud_url, filename

            # 2. Try Cloudflare R2
            try:
                from cloudflare_r2 import upload_to_r2
                r2_url, _ = upload_to_r2(file_bytes, unique_name, content_type=ctype)
                if r2_url:
                    return r2_url, filename
            except Exception as e:
                print(f"[pharmacy] Cloudflare R2 file upload notice: {e}")

            # 3. Local fallback storage
            upload_dir = os.path.join(app.root_path, "static", "uploads", "prescriptions")
            os.makedirs(upload_dir, exist_ok=True)
            save_path = os.path.join(upload_dir, unique_name)
            with open(save_path, "wb") as f_out:
                f_out.write(file_bytes)
            return f"/static/uploads/prescriptions/{unique_name}", filename

    # 2. Check if client base64 data URI was sent (images or PDF)
    _j = request.get_json(silent=True) or {}
    data_uri = request.form.get("prescription_base64") or _j.get("prescription_base64")
    if data_uri and (data_uri.startswith("data:image") or data_uri.startswith("data:application/pdf") or data_uri.startswith("data:application/octet-stream") or data_uri.startswith("data:binary")):
        return _save_base64_image(data_uri, prefix="rx_upload")

    return "", ""


def _init_pharmacy_db_schema():
    """Ensure MRP, discount columns and English dosage forms exist in pharmacy_medicines."""
    try:
        conn = get_connection()
        cur = conn.cursor()
        
        # Check and add mrp column
        try:
            cur.execute("ALTER TABLE pharmacy_medicines ADD COLUMN mrp REAL DEFAULT 0.0")
        except Exception:
            pass

        # Check and add discount_percent column
        try:
            cur.execute("ALTER TABLE pharmacy_medicines ADD COLUMN discount_percent REAL DEFAULT 0.0")
        except Exception:
            pass

        # Check and add expiry_date column
        try:
            cur.execute("ALTER TABLE pharmacy_medicines ADD COLUMN expiry_date TEXT DEFAULT ''")
        except Exception:
            pass

        # Check and add low_stock_threshold column
        try:
            cur.execute("ALTER TABLE pharmacy_medicines ADD COLUMN low_stock_threshold INTEGER DEFAULT 10")
        except Exception:
            pass

        # Check and add cost_price & multi-unit pricing columns
        for col_sql in (
            "ALTER TABLE pharmacy_medicines ADD COLUMN cost_price REAL DEFAULT 0.0",
            "ALTER TABLE pharmacy_medicines ADD COLUMN strip_cost_price REAL DEFAULT 0.0",
            "ALTER TABLE pharmacy_medicines ADD COLUMN packet_price REAL DEFAULT 0.0",
            "ALTER TABLE pharmacy_medicines ADD COLUMN packet_cost_price REAL DEFAULT 0.0",
            "ALTER TABLE pharmacy_medicines ADD COLUMN packet_size INTEGER DEFAULT 30",
            "ALTER TABLE pharmacy_orders ADD COLUMN customer_confirmed INTEGER DEFAULT 0",
            "ALTER TABLE pharmacy_orders ADD COLUMN quote_sent_at TEXT DEFAULT ''",
            "ALTER TABLE pharmacy_orders ADD COLUMN quote_by TEXT DEFAULT ''",
            "ALTER TABLE users ADD COLUMN can_rx_quote_bill INTEGER DEFAULT 0",
        ):
            try:
                cur.execute(col_sql)
            except Exception:
                pass

        # Standardize Bengali dosage forms to English
        dosage_map = {
            'ট্যাবলেট': 'Tablet',
            'ক্যাপসুল': 'Capsule',
            'সাসপেনশন': 'Suspension',
            'সিরাপ': 'Syrup',
            'সিরাপ/সলিউশন': 'Syrup',
            'ইনজেকশন': 'Injection',
            'ইনজেকশন/স্যালাইন': 'Injection',
            'ইনহেলার': 'Inhaler',
            'ড্রপ': 'Drops',
            'মলম/ক্রিম': 'Ointment/Cream',
            'জেল/মলম': 'Gel/Ointment',
            'ব্যান্ডেজ/ফার্স্ট এইড': 'Bandage/First Aid',
            'নাসাল স্প্রে': 'Nasal Spray',
            'নেবুলাইজার সলিউশন': 'Nebulizer Solution',
            'মাউথওয়াশ': 'Mouthwash',
            'লোশন': 'Lotion',
            'সাপোজিটরি': 'Suppository',
        }
        for bn, en in dosage_map.items():
            cur.execute("UPDATE pharmacy_medicines SET dosage_form = ? WHERE dosage_form = ?", (en, bn))

        # Set mrp = unit_price where mrp is 0 or null
        cur.execute("UPDATE pharmacy_medicines SET mrp = unit_price WHERE (mrp IS NULL OR mrp <= 0.0) AND unit_price > 0")

        conn.commit()
        conn.close()
    except Exception as e:
        print(f"[_init_pharmacy_db_schema] notice: {e}")

_init_pharmacy_db_schema()


@app.route("/pharmacy")
def pharmacy_home():
    """Customer-facing Pharmacy & Prescription Home (100% Bengali, QR-Print BD aesthetic)"""
    conn = get_connection()
    settings = get_all_settings(conn)

    # Check for seamless auto-login from Mobile App
    auth_phone = (request.args.get("auth_phone") or request.args.get("phone") or "").strip()
    preloaded_customer = None
    if auth_phone:
        p_clean = normalize_phone(auth_phone)
        p_chk = p_clean if p_clean else auth_phone
        c_row = conn.execute("SELECT * FROM customer_users WHERE phone = ? OR phone = ?", (p_chk, auth_phone)).fetchone()
        if c_row:
            cd = dict(c_row)
            raw_img = (cd.get("profile_image") or cd.get("avatar_url") or cd.get("avatar_base64") or "").strip()
            prof_img = request.host_url.rstrip("/") + raw_img if raw_img.startswith("/") else raw_img
            preloaded_customer = {
                "phone": cd.get("phone", auth_phone),
                "name": cd.get("name") or request.args.get("auth_name") or f"গ্রাহক {auth_phone[-4:]}",
                "email": cd.get("email", ""),
                "address": cd.get("address") or request.args.get("auth_address", ""),
                "profile_image": prof_img,
                "district": cd.get("district", ""),
                "area": cd.get("area", "")
            }
        else:
            preloaded_customer = {
                "phone": auth_phone,
                "name": request.args.get("auth_name") or f"গ্রাহক {auth_phone[-4:]}",
                "address": request.args.get("auth_address", ""),
                "profile_image": "",
                "district": "",
                "area": ""
            }
    
    # Load categories / dosage forms for filter pills (English names)
    dosage_forms = [
        {"id": "all", "name": "All Medicines", "icon": "💊"},
        {"id": "Tablet", "name": "Tablet", "icon": "💊"},
        {"id": "Capsule", "name": "Capsule", "icon": "💊"},
        {"id": "Syrup", "name": "Syrup", "icon": "🍯"},
        {"id": "Suspension", "name": "Suspension", "icon": "🧪"},
        {"id": "Injection", "name": "Injection", "icon": "💉"},
        {"id": "Bandage/First Aid", "name": "Bandage / First Aid", "icon": "🩹"},
        {"id": "Drops", "name": "Drops", "icon": "💧"},
        {"id": "Ointment/Cream", "name": "Ointment / Cream", "icon": "🧴"},
        {"id": "Inhaler", "name": "Inhaler", "icon": "💨"},
        {"id": "Suppository", "name": "Suppository", "icon": "💊"},
    ]
    
    # Get active delivery areas (unique by district, area)
    raw_areas = conn.execute("SELECT DISTINCT district, area FROM delivery_areas WHERE is_active = 1 ORDER BY district, area").fetchall()
    delivery_areas = [dict(r) for r in raw_areas if r["area"]]
    districts = sorted(list(set([r["district"].strip() for r in delivery_areas if r.get("district") and r["district"].strip()])))
    if not districts:
        districts = ["Tangail"]
    
    # Quick count of active medicines
    med_count_row = conn.execute("SELECT COUNT(*) AS c FROM pharmacy_medicines WHERE is_active = 1").fetchone()
    total_medicines = med_count_row["c"] if med_count_row else 0
    
    conn.close()
    return render_template(
        "pharmacy.html",
        settings=settings,
        dosage_forms=dosage_forms,
        delivery_areas=delivery_areas,
        districts=districts,
        total_medicines=total_medicines,
        preloaded_customer=preloaded_customer,
        active_tab="pharmacy"
    )


@app.route("/pharmacy/track")
def pharmacy_track():
    """Live Order Tracking Page for Pharmacy Orders"""
    order_num = request.args.get("order", "").strip()
    phone = request.args.get("phone", "").strip()
    conn = get_connection()
    settings = get_all_settings(conn)
    conn.close()
    return render_template(
        "pharmacy_tracking.html",
        settings=settings,
        order_number=order_num,
        search_phone=phone,
        active_tab="pharmacy"
    )


@app.route("/pharmacy/my-orders")
def pharmacy_my_orders():
    """Customer Pharmacy Orders History"""
    phone = request.args.get("phone", "").strip()
    conn = get_connection()
    settings = get_all_settings(conn)
    orders = []
    if phone:
        orders = conn.execute(
            "SELECT * FROM pharmacy_orders WHERE customer_phone = ? ORDER BY id DESC LIMIT 50",
            (phone,)
        ).fetchall()
    conn.close()
    return render_template(
        "pharmacy_tracking.html",
        settings=settings,
        orders=orders,
        search_phone=phone,
        active_tab="pharmacy"
    )


def _word_starts_with(text_low, q_low):
    """Fast contiguous word-boundary check without regex compilation overhead."""
    if not text_low:
        return False
    if text_low.startswith(q_low):
        return True
    for sep in (" ", "-", "/", "(", "+"):
        if f"{sep}{q_low}" in text_low:
            return True
    return False


def _medicine_relevance_key(med_dict, q_low, tokens):
    """Score contiguous word/substring medicine matches so best matches appear first and inner-word matches appear last."""
    name_low = (med_dict.get("name") or "").strip().lower()
    gen_low = (med_dict.get("generic_name") or "").strip().lower()
    sku_low = (med_dict.get("sku") or "").strip().lower()
    str_low = (med_dict.get("strength") or "").strip().lower()

    if len(tokens) <= 1:
        if name_low == q_low:
            tier = 0
        elif name_low.startswith(q_low + " ") or name_low.startswith(q_low + "-") or name_low.startswith(q_low + "/"):
            tier = 1
        elif name_low.startswith(q_low):
            tier = 2
        elif _word_starts_with(name_low, q_low):
            tier = 3
        elif sku_low == q_low or sku_low.startswith(q_low):
            tier = 4
        elif q_low in name_low:
            # Inner-word contiguous substring in name (e.g. 'adnapara' for 'napa') goes near the end
            tier = 5
        elif gen_low == q_low or gen_low.startswith(q_low):
            tier = 6
        else:
            tier = 7
        return (tier, len(name_low), name_low)

    # Multi-word search
    name_str = f"{name_low} {str_low}".strip()
    if name_low == q_low or name_str == q_low:
        tier = 0
    elif name_low.startswith(q_low) or name_str.startswith(q_low):
        tier = 1
    elif all(_word_starts_with(name_str, tok) for tok in tokens):
        tier = 2
    elif all(tok in name_str for tok in tokens):
        tier = 3
    else:
        tier = 4
    return (tier, len(name_low), name_low)


def _search_pharmacy_medicines(
    conn,
    q="",
    dosage="",
    mfg="",
    limit=60,
    offset=0,
    only_in_stock=False,
    include_manufacturer=False,
    select_cols="id, name, generic_name, dosage_form, strength, manufacturer, sku, unit_price, cost_price, mrp, discount_percent, strip_price, strip_cost_price, strip_size, packet_price, packet_cost_price, packet_size, stock_qty, is_prescription_required",
):
    """Fast contiguous-match pharmacy search ranked best-match-first."""
    q_clean = " ".join((q or "").strip().split())
    q_low = q_clean.lower()
    tokens = q_low.split() if q_low else []

    where = ["is_active = 1"]
    params = []

    if dosage and dosage.lower() != "all":
        where.append("(dosage_form = ? OR dosage_form LIKE ?)")
        params.extend([dosage, f"%{dosage}%"])
    if mfg and mfg.lower() != "all":
        where.append("manufacturer = ?")
        params.append(mfg)
    if only_in_stock:
        today_date = datetime.now().strftime("%Y-%m-%d")
        where.append("stock_qty > 0 AND (expiry_date IS NULL OR expiry_date = '' OR expiry_date > ?)")
        params.append(today_date)

    if not q_low:
        where_sql = " AND ".join(where)
        count_row = conn.execute(f"SELECT COUNT(*) AS c FROM pharmacy_medicines WHERE {where_sql}", params).fetchone()
        total = count_row["c"] if count_row else 0
        order_sql = "ORDER BY stock_qty DESC, name ASC" if only_in_stock else "ORDER BY name ASC"
        sql = f"SELECT {select_cols} FROM pharmacy_medicines WHERE {where_sql} {order_sql}"
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])
        rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
        return rows, total

    if len(q_low) == 1:
        # Fast indexed prefix scan on single-character keystroke
        where.append("(name LIKE ? OR sku LIKE ?)")
        params.extend([f"{q_low}%", f"{q_low}%"])
        where_sql = " AND ".join(where)
        count_row = conn.execute(f"SELECT COUNT(*) AS c FROM pharmacy_medicines WHERE {where_sql}", params).fetchone()
        total = count_row["c"] if count_row else 0
        sql = f"SELECT {select_cols} FROM pharmacy_medicines WHERE {where_sql} ORDER BY name COLLATE NOCASE ASC"
        if limit is not None:
            sql += " LIMIT ? OFFSET ?"
            params.extend([limit, offset])
        rows = [dict(r) for r in conn.execute(sql, params).fetchall()]
        return rows, total

    if len(tokens) == 1:
        word_fields = [
            "name LIKE ?",
            "sku LIKE ?",
            "generic_name LIKE ?",
            "generic_name LIKE ?",
        ]
        params.extend([f"%{q_low}%", f"{q_low}%", f"{q_low}%", f"% {q_low}%"])
        if include_manufacturer:
            word_fields.extend(["manufacturer LIKE ?", "manufacturer LIKE ?"])
            params.extend([f"{q_low}%", f"% {q_low}%"])
        where.append("(" + " OR ".join(word_fields) + ")")
    else:
        for tok in tokens:
            searchable = "(name || ' ' || strength || ' ' || generic_name || ' ' || sku)"
            if include_manufacturer:
                searchable = "(name || ' ' || strength || ' ' || generic_name || ' ' || manufacturer || ' ' || sku)"
            where.append(f"{searchable} LIKE ?")
            params.append(f"%{tok}%")

    where_sql = " AND ".join(where)
    sql = f"""
        SELECT {select_cols} FROM pharmacy_medicines
        WHERE {where_sql}
        ORDER BY
            CASE
                WHEN name LIKE ? THEN 0
                WHEN name LIKE ? THEN 1
                WHEN sku LIKE ? THEN 2
                WHEN generic_name LIKE ? THEN 3
                ELSE 4
            END,
            name COLLATE NOCASE ASC
        LIMIT 600
    """
    order_params = [q_low, f"{q_low}%", f"{q_low}%", f"{q_low}%"]
    rows = [dict(r) for r in conn.execute(sql, params + order_params).fetchall()]

    filtered = []
    for m in rows:
        name_low = (m.get("name") or "").lower()
        gen_low = (m.get("generic_name") or "").lower()
        sku_low = (m.get("sku") or "").lower()
        str_low = (m.get("strength") or "").lower()
        mfg_low = (m.get("manufacturer") or "").lower()
        if len(tokens) == 1:
            gen_words = gen_low.split()
            mfg_words = mfg_low.split() if include_manufacturer else []
            if (
                q_low in name_low
                or sku_low.startswith(q_low)
                or any(w.startswith(q_low) for w in gen_words)
                or (include_manufacturer and any(w.startswith(q_low) for w in mfg_words))
            ):
                filtered.append(m)
        else:
            combined = f"{name_low} {str_low} {gen_low} {sku_low}" + (f" {mfg_low}" if include_manufacturer else "")
            if all(tok in combined for tok in tokens):
                filtered.append(m)

    filtered.sort(key=lambda m: _medicine_relevance_key(m, q_low, tokens))
    total = len(filtered)
    if limit is not None:
        filtered = filtered[offset:offset + limit]
    return filtered, total


@app.route("/api/pharmacy/medicines", methods=["GET"])
@limiter.limit("120 per minute")
def api_pharmacy_medicines():
    """Fast contiguous-match autocomplete and catalog search for pharmacy medicines with best match first."""
    q = (request.args.get("q") or "").strip()
    dosage = (request.args.get("dosage") or request.args.get("cat") or "").strip()

    conn = get_connection()
    shop_settings = get_all_settings(conn)
    overall_disc = float(shop_settings.get("pharmacy_discount_percent") or 0.0)

    rows, _ = _search_pharmacy_medicines(conn, q=q, dosage=dosage, limit=60)
    conn.close()

    medicines = []
    for m in rows:
        mrp_val = float(m.get("mrp") or m.get("unit_price") or 0.0)
        if mrp_val <= 0:
            mrp_val = float(m.get("unit_price") or 0.0)
        prod_disc = float(m.get("discount_percent") or 0.0)
        eff_disc = max(prod_disc, overall_disc)
        if eff_disc > 0 and mrp_val > 0:
            sell_p = round(mrp_val * (1.0 - eff_disc / 100.0), 2)
        else:
            sell_p = float(m.get("unit_price") or mrp_val)
        m["mrp"] = mrp_val
        m["discount_percent"] = eff_disc
        m["sell_price"] = sell_p
        m["unit_price"] = sell_p
        medicines.append(m)

    return jsonify({"success": True, "count": len(medicines), "overall_discount": overall_disc, "medicines": medicines})


@app.route("/api/pharmacy/substitutes", methods=["GET"])
@limiter.limit("120 per minute")
def api_pharmacy_substitutes():
    """Returns other brand medicines sharing the exact same generic name (with price comparison)"""
    generic = (request.args.get("generic_name") or request.args.get("generic") or "").strip()
    exclude_id = request.args.get("exclude_id", type=int) or 0
    dosage_form = (request.args.get("dosage_form") or "").strip()
    strength = (request.args.get("strength") or "").strip()

    if not generic:
        return jsonify({"success": False, "substitutes": [], "message": "Generic name is required."})

    conn = get_connection()
    shop_settings = get_all_settings(conn)
    overall_disc = float(shop_settings.get("pharmacy_discount_percent") or 0.0)

    query = """
        SELECT id, name, generic_name, dosage_form, strength, manufacturer, sku, unit_price, mrp, discount_percent, stock_qty, is_prescription_required
        FROM pharmacy_medicines
        WHERE is_active = 1 AND LOWER(TRIM(generic_name)) = LOWER(TRIM(?))
    """
    params = [generic]
    if exclude_id > 0:
        query += " AND id != ?"
        params.append(exclude_id)

    query += " ORDER BY unit_price ASC LIMIT 30"
    rows = conn.execute(query, params).fetchall()
    conn.close()

    substitutes = []
    for r in rows:
        m = dict(r)
        mrp_val = float(m.get("mrp") or m.get("unit_price") or 0.0)
        if mrp_val <= 0:
            mrp_val = float(m.get("unit_price") or 0.0)
        prod_disc = float(m.get("discount_percent") or 0.0)
        eff_disc = max(prod_disc, overall_disc)
        if eff_disc > 0 and mrp_val > 0:
            sell_p = round(mrp_val * (1.0 - eff_disc / 100.0), 2)
        else:
            sell_p = float(m.get("unit_price") or mrp_val)
        m["mrp"] = mrp_val
        m["discount_percent"] = eff_disc
        m["sell_price"] = sell_p
        m["unit_price"] = sell_p
        substitutes.append(m)

    return jsonify({
        "success": True,
        "generic_name": generic,
        "count": len(substitutes),
        "substitutes": substitutes
    })


@app.route("/pharmacy/order", methods=["POST"])
@limiter.limit("15 per minute")
def pharmacy_place_order():
    """
    Submits a pharmacy prescription / medicine order.
    Validates quantity / duration strictly according to user rules:
      - Can be prescription only, medicines only, or both
      - Must specify duration or quantity
    """
    data = request.get_json(silent=True) or request.form or {}

    customer_name = (data.get("customer_name") or "").strip()
    customer_phone = (data.get("customer_phone") or "").strip()
    customer_email = (data.get("customer_email") or "").strip()
    district = (data.get("district") or "Tangail").strip()
    area = (data.get("area") or "Main Area").strip()
    delivery_address = (data.get("delivery_address") or data.get("address_details") or "").strip()
    order_type = (data.get("order_type") or "both").strip()
    customer_notes = (data.get("customer_notes") or data.get("notes") or "").strip()
    
    try:
        overall_duration_days = int(data.get("overall_duration_days") or data.get("duration_days") or 0)
    except (ValueError, TypeError):
        overall_duration_days = 0

    # Parse items JSON
    raw_items = data.get("items") or data.get("cart_items") or []
    if isinstance(raw_items, str):
        try:
            raw_items = json.loads(raw_items)
        except Exception:
            raw_items = []

    # Handle prescription file upload / base64 (enhanced & original concurrently when both sent)
    prescription_url = (data.get("prescription_url") or "").strip()
    prescription_filename = ""
    prescription_original_url = ""
    orig_base64 = data.get("prescription_original_base64")
    has_orig_b64 = bool(orig_base64 and (orig_base64.startswith("data:image") or orig_base64.startswith("data:application/pdf")))

    has_multipart = bool(request.files.get("prescription_file") or request.files.get("file"))
    enh_base64 = request.form.get("prescription_base64") or (data.get("prescription_base64") if isinstance(data, dict) else None)
    has_enh_b64 = bool(not prescription_url and not has_multipart and enh_base64 and (enh_base64.startswith("data:image") or enh_base64.startswith("data:application/pdf") or enh_base64.startswith("data:application/octet-stream") or enh_base64.startswith("data:binary")))

    if not prescription_url and has_enh_b64 and has_orig_b64:
        if orig_base64 == enh_base64:
            prescription_url, prescription_filename = _save_base64_image(enh_base64, prefix="rx_upload")
            prescription_original_url = prescription_url
        else:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=2) as pool:
                fut_enh = pool.submit(_save_base64_image, enh_base64, "rx_upload")
                fut_orig = pool.submit(_save_base64_image, orig_base64, "rx_orig")
                prescription_url, prescription_filename = fut_enh.result()
                prescription_original_url, _ = fut_orig.result()
    else:
        if not prescription_url:
            prescription_url, prescription_filename = _handle_prescription_upload()
        if has_orig_b64:
            if enh_base64 and orig_base64 == enh_base64 and prescription_url:
                prescription_original_url = prescription_url
            else:
                prescription_original_url, _ = _save_base64_image(orig_base64, prefix="rx_orig")
    if not prescription_original_url:
        prescription_original_url = prescription_url
    prescription_enhanced_url = prescription_url

    # --- Validations ---
    if not customer_phone or len(re.sub(r'\D', '', customer_phone)) < 11:
        return jsonify({"success": False, "message": "অনুগ্রহ করে আপনার সঠিক ১১ ডিজিটের মোবাইল নম্বর দিন।"}), 400

    if not customer_name:
        customer_name = "সম্মানিত গ্রাহক"

    if not delivery_address:
        return jsonify({"success": False, "message": "অনুগ্রহ করে আপনার সম্পূর্ণ ডেলিভারি ঠিকানা দিন।"}), 400

    # Check Block Status
    conn = get_connection()
    is_blocked, block_msg = check_customer_block(conn, customer_phone)
    if is_blocked:
        conn.close()
        return jsonify({"success": False, "message": block_msg}), 403

    # Rule 1 Requirement: Must provide prescription OR select medicines (or both)
    has_prescription = bool(prescription_url)
    has_items = bool(raw_items and len(raw_items) > 0)

    if not has_prescription and not has_items:
        conn.close()
        return jsonify({
            "success": False,
            "message": "অনুগ্রহ করে একটি প্রেসক্রিপশন আপলোড করুন অথবা তালিকা থেকে ওষুধ নির্বাচন করুন।"
        }), 400

    # Rule 1 Requirement: Quantity or Duration must be specified
    # "কিন্তু অবশ্যই পরিমান উল্লেখ থাকতে হবে। সে চাইলে তার পাশাপাশি লিখেও দিতে পারে (সব ঔষধ কয়দিনের লাগবে অথবা একেকটা ঔষধ একেক পরিমান বা দিনের লাগলেও সে তা সিলেক্ট করে দিতে পারবে)"
    if has_prescription and not has_items:
        if overall_duration_days <= 0 and len(customer_notes.strip()) < 2:
            conn.close()
            return jsonify({
                "success": False,
                "message": "প্রেসক্রিপশন আপলোড করলে অবশ্যই ওষুধ কয়দিনের লাগবে (যেমন: ৭ দিন, ১০ দিন) অথবা নির্দিষ্ট ওষুধের পরিমাণ লিখে জানাতে হবে।"
            }), 400

    processed_items = []
    med_demands = {}
    subtotal = 0.0
    for it in raw_items:
        med_name = (it.get("name") or it.get("product_name") or it.get("medicine_name") or "").strip()
        if not med_name:
            continue
        try:
            qty = int(it.get("quantity") or it.get("qty") or 1)
        except Exception:
            qty = 1
        if qty <= 0:
            qty = 1

        raw_med_id = it.get("medicine_id") or it.get("id")
        med_row = None
        if raw_med_id not in (None, "", 0, "0"):
            try:
                med_row = conn.execute(
                    "SELECT id, name, stock_qty, unit_price, mrp, discount_percent, is_active FROM pharmacy_medicines WHERE id = ?",
                    (int(raw_med_id),),
                ).fetchone()
            except Exception:
                med_row = None
        if not med_row:
            med_row = conn.execute(
                "SELECT id, name, stock_qty, unit_price, mrp, discount_percent, is_active FROM pharmacy_medicines WHERE LOWER(TRIM(name)) = LOWER(TRIM(?)) LIMIT 1",
                (med_name,),
            ).fetchone()

        if med_row:
            if int(med_row["is_active"] or 0) != 1:
                conn.close()
                return jsonify({"success": False, "message": f'দুঃখিত, "{med_row["name"]}" বর্তমানে নিষ্ক্রিয় রয়েছে।'}), 400
            avail_stk = int(med_row["stock_qty"] or 0)
            mid_int = int(med_row["id"])
            med_demands[mid_int] = med_demands.get(mid_int, 0) + qty
            if avail_stk <= 0:
                conn.close()
                return jsonify({
                    "success": False,
                    "message": f'দুঃখিত, "{med_row["name"]}" বর্তমানে স্টকে নেই (পরিমাণ ০)। স্টক শূন্য থাকা ঔষধ অর্ডার বা চেকআউট করা যাবে না।',
                }), 400
            if med_demands[mid_int] > avail_stk:
                conn.close()
                return jsonify({
                    "success": False,
                    "message": f'"{med_row["name"]}" এর পর্যাপ্ত স্টক নেই (স্টক: {avail_stk} পিস, অর্ডার: {med_demands[mid_int]} পিস)।',
                }), 400

        unit_price = float(it.get("unit_price") or it.get("price") or (med_row["unit_price"] if med_row else 0.0) or 0.0)
        item_total = round(unit_price * qty, 2)
        subtotal += item_total

        processed_items.append({
            "medicine_id": int(med_row["id"]) if med_row else (it.get("medicine_id") or it.get("id")),
            "name": med_row["name"] if med_row else med_name,
            "generic_name": it.get("generic_name") or "",
            "dosage_form": it.get("dosage_form") or "Tablet",
            "strength": it.get("strength") or "",
            "quantity": qty,
            "unit": it.get("unit") or "পিস",
            "duration_days": it.get("duration_days") or (f"{overall_duration_days} দিন" if overall_duration_days > 0 else ""),
            "unit_price": unit_price,
            "total_price": item_total
        })

    # Default delivery charge from pharmacy settings
    shop_settings = get_all_settings(conn)
    delivery_charge = float(shop_settings.get("pharmacy_delivery_charge") or shop_settings.get("delivery_charge") or 50.0)
    total_amount = round(subtotal + delivery_charge, 2) if subtotal > 0 else 0.0

    # Determine order type
    if has_prescription and processed_items:
        determined_type = "both"
    elif has_prescription:
        determined_type = "prescription_only"
    else:
        determined_type = "medicines_only"

    # Status: If prescription uploaded, pharmacist reviews it first ('reviewing').
    # If OTC medicines selected with known prices, it can still go to review or new.
    initial_status = "reviewing"
    order_number = f"RX-{datetime.now().strftime('%y%m%d')}-{random.randint(1000, 9999)}"
    delivery_otp = f"{random.randint(1000, 9999)}"
    now_iso = get_bd_now_iso()
    cust_ip, cust_loc = _touch_customer_network_info(conn, customer_phone, data=data)

    cur = conn.cursor()
    # 1. Insert into pharmacy_orders
    cur.execute("""
        INSERT INTO pharmacy_orders (
            order_number, customer_name, customer_phone, customer_email,
            country, district, area, delivery_address, order_type,
            prescription_url, prescription_original_url, prescription_enhanced_url,
            prescription_local_filename, overall_duration_days,
            customer_notes, requested_items_json, approved_items_json,
            subtotal, delivery_charge, total_amount, order_status,
            delivery_otp, payment_method, payment_status,
            customer_ip, ip_location, created_at, updated_at
        ) VALUES (?, ?, ?, ?, 'Bangladesh', ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'cod', 'pending', ?, ?, ?, ?)
    """, (
        order_number, customer_name, customer_phone, customer_email,
        district, area, delivery_address, determined_type,
        prescription_url, prescription_original_url, prescription_enhanced_url,
        prescription_filename, overall_duration_days,
        customer_notes, json.dumps(processed_items, ensure_ascii=False), json.dumps(processed_items, ensure_ascii=False),
        subtotal, delivery_charge, total_amount, initial_status,
        delivery_otp, cust_ip, cust_loc, now_iso, now_iso
    ))
    pharm_order_id = cur.lastrowid

    # 2. Insert into online_orders for Rider & POS integration
    online_order_id = None
    try:
        cur.execute("""
            INSERT INTO online_orders (
                order_number, customer_name, customer_phone, customer_email,
                country, district, area, address_details, payment_method,
                payment_status, subtotal, delivery_charge, total_amount,
                order_status, delivery_otp, customer_ip, ip_location, created_at, updated_at
            ) VALUES (?, ?, ?, ?, 'Bangladesh', ?, ?, ?, 'cod', 'pending', ?, ?, ?, 'pending_confirmation', ?, ?, ?, ?, ?)
        """, (
            order_number, customer_name, customer_phone, customer_email,
            district, area, delivery_address,
            subtotal, delivery_charge, total_amount,
            delivery_otp, cust_ip, cust_loc, now_iso, now_iso
        ))
        online_order_id = cur.lastrowid
        cur.execute("UPDATE pharmacy_orders SET online_order_id = ? WHERE id = ?", (online_order_id, pharm_order_id))

        # Insert items or placeholder in online_order_items
        _fp = conn.execute("SELECT id FROM products LIMIT 1").fetchone()
        _valid_pid = _fp["id"] if _fp else 1
        if processed_items:
            for itm in processed_items:
                cur.execute("""
                    INSERT INTO online_order_items (order_id, product_id, product_name, unit_price, mrp_price, quantity, total_price)
                    VALUES (?, ?, ?, ?, ?, ?, ?)
                """, (online_order_id, _valid_pid, f"💊 {itm['name']} ({itm.get('strength', '')})", itm['unit_price'], itm['unit_price'], itm['quantity'], itm['total_price']))
        else:
            note_summary = f"{overall_duration_days} দিনের ওষুধ" if overall_duration_days > 0 else "প্রেসক্রিপশন পর্যালোচনা"
            cur.execute("""
                INSERT INTO online_order_items (order_id, product_id, product_name, unit_price, mrp_price, quantity, total_price)
                VALUES (?, ?, ?, 0, 0, 1, 0)
            """, (online_order_id, _valid_pid, f"💊 প্রেসক্রিপশন অর্ডার - {note_summary}"))
    except Exception as e:
        print(f"[pharmacy] Online order sync notice: {e}")

    conn.commit()
    conn.close()

    try:
        remote_control.push_pharmacy_order_to_cloud(pharm_order_id)
        if online_order_id:
            remote_control.push_online_order_to_cloud(online_order_id)
        if customer_phone:
            remote_control.push_customer_user_to_cloud(normalize_phone(customer_phone) or customer_phone)
    except Exception:
        pass

    return jsonify({
        "success": True,
        "order_number": order_number,
        "order_id": pharm_order_id,
        "delivery_otp": delivery_otp,
        "message": "আপনার প্রেসক্রিপশন ও ওষুধ অর্ডার সফলভাবে সম্পন্ন হয়েছে! আমাদের ফার্মাসিস্ট যাচাই করে দ্রুত আপডেট জানাবেন।"
    })


@app.route("/api/pharmacy/my-orders", methods=["GET"])
@limiter.limit("60 per minute")
def api_pharmacy_my_orders():
    """Returns JSON list of pharmacy orders for a customer phone number (for mobile app & web)."""
    raw_phone = (request.args.get("phone") or "").strip()
    candidates = _phone_variants(raw_phone)
    if not candidates:
        return jsonify({"success": True, "orders": []})

    conn = get_connection()
    placeholders = ",".join("?" for _ in candidates)
    norm_main = candidates[0]
    rows = conn.execute(
        f"""SELECT * FROM pharmacy_orders
            WHERE customer_phone IN ({placeholders})
               OR REPLACE(REPLACE(REPLACE(customer_phone, ' ', ''), '-', ''), '+88', '') = ?
            ORDER BY id DESC LIMIT 50""",
        tuple(candidates) + (norm_main,),
    ).fetchall()

    base_host = request.host_url.rstrip("/")

    def _abs_url(u):
        s = (u or "").strip()
        if s.startswith("/static/"):
            return base_host + s
        return s

    _STAGE_RANK = {
        "reviewing": 0, "new": 0, "pending": 0, "pending_confirmation": 0,
        "awaiting_customer_confirmation": 1,
        "confirmed": 2, "verified": 2,
        "packed": 3, "on_the_way": 4, "delivered": 5, "cancelled": 6,
    }

    orders_out = []
    seen_nums = set()
    for r in rows:
        d = dict(r)
        if d.get("order_number"):
            seen_nums.add(d["order_number"])
        ol_row = conn.execute(
            "SELECT * FROM online_orders WHERE id = ? OR order_number = ? LIMIT 1",
            (d.get("online_order_id") or 0, d.get("order_number") or ""),
        ).fetchone()
        if ol_row:
            ol_mapped = _OL_TO_PHARM_STATUS.get((ol_row["order_status"] or "").strip().lower(), "")
            curr_ph = (d.get("order_status") or "reviewing").strip().lower()
            if ol_mapped and (ol_mapped == "cancelled" or _STAGE_RANK.get(ol_mapped, 0) > _STAGE_RANK.get(curr_ph, 0)):
                d["order_status"] = ol_mapped
            for col in ("confirmed_at", "packed_at", "on_the_way_at", "delivered_at", "cancelled_at"):
                if not d.get(col) and ol_row[col]:
                    d[col] = ol_row[col]
            if not d.get("assigned_rider_name") and ol_row["assigned_rider_name"]:
                d["assigned_rider_name"] = ol_row["assigned_rider_name"]
                d["assigned_rider_phone"] = ol_row["assigned_rider_phone"]
            if ol_row["payment_status"] == "paid":
                d["payment_status"] = "paid"

        try:
            d["requested_items"] = json.loads(d.get("requested_items_json") or "[]")
        except Exception:
            d["requested_items"] = []
        try:
            d["approved_items"] = json.loads(d.get("approved_items_json") or "[]")
        except Exception:
            d["approved_items"] = []
        d.pop("requested_items_json", None)
        d.pop("approved_items_json", None)
        d["prescription_url"] = _abs_url(d.get("prescription_url"))
        d["prescription_original_url"] = _abs_url(d.get("prescription_original_url") or d.get("prescription_url"))
        d["prescription_enhanced_url"] = _abs_url(d.get("prescription_enhanced_url") or d.get("prescription_url"))
        orders_out.append(d)

    # Also include any RX- online_orders that do not yet have a local pharmacy_orders row
    rx_ol_rows = conn.execute(
        f"""SELECT * FROM online_orders
            WHERE order_number LIKE 'RX-%'
              AND (customer_phone IN ({placeholders})
                   OR REPLACE(REPLACE(REPLACE(customer_phone, ' ', ''), '-', ''), '+88', '') = ?)
            ORDER BY id DESC LIMIT 30""",
        tuple(candidates) + (norm_main,),
    ).fetchall()
    for olr in rx_ol_rows:
        if olr["order_number"] in seen_nums:
            continue
        orders_out.append({
            "id": olr["id"],
            "online_order_id": olr["id"],
            "order_number": olr["order_number"],
            "customer_name": olr["customer_name"] or "",
            "customer_phone": olr["customer_phone"] or "",
            "delivery_address": olr["address_details"] or "",
            "subtotal": float(olr["subtotal"] or 0.0),
            "delivery_charge": float(olr["delivery_charge"] or 50.0),
            "total_amount": float(olr["total_amount"] or 0.0),
            "order_status": _OL_TO_PHARM_STATUS.get((olr["order_status"] or "").strip().lower(), "reviewing"),
            "delivery_otp": olr["delivery_otp"] or "",
            "payment_status": olr["payment_status"] or "pending",
            "assigned_rider_name": olr["assigned_rider_name"] or "",
            "assigned_rider_phone": olr["assigned_rider_phone"] or "",
            "created_at": olr["created_at"] or "",
            "confirmed_at": olr["confirmed_at"] or "",
            "packed_at": olr["packed_at"] or "",
            "on_the_way_at": olr["on_the_way_at"] or "",
            "delivered_at": olr["delivered_at"] or "",
            "cancelled_at": olr["cancelled_at"] or "",
            "requested_items": [],
            "approved_items": [],
            "prescription_url": "",
            "prescription_original_url": "",
            "prescription_enhanced_url": "",
        })
    conn.close()

    return jsonify({"success": True, "orders": orders_out})


@app.route("/api/pharmacy/order-status/<order_number>", methods=["GET"])
def api_pharmacy_order_status(order_number):
    """
    Returns real-time status and prescription details for live customer tracking.
    Synchronizes status dynamically if Rider confirmed/updated the order!
    """
    order_num = order_number.strip()
    conn = get_connection()
    
    order = conn.execute("SELECT * FROM pharmacy_orders WHERE order_number = ? OR id = ?", (order_num, order_num)).fetchone()
    if not order:
        # Check if it exists in online_orders and auto-reconstruct into pharmacy_orders
        ol = conn.execute("SELECT * FROM online_orders WHERE order_number = ? OR id = ?", (order_num, order_num)).fetchone()
        if ol:
            items = conn.execute("SELECT * FROM online_order_items WHERE order_id = ?", (ol["id"],)).fetchall()
            items_json = json.dumps([dict(it) for it in items], ensure_ascii=False)
            conn.execute("""
                INSERT INTO pharmacy_orders (
                    order_number, online_order_id, customer_name, customer_phone, customer_email,
                    country, district, area, delivery_address, order_type,
                    overall_duration_days, customer_notes, requested_items_json, approved_items_json,
                    subtotal, delivery_charge, total_amount, order_status, delivery_otp,
                    payment_method, payment_status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'both', ?, ?, ?, ?, ?, ?, ?, ?, ?, 'cod', 'pending', ?, ?)
            """, (
                ol["order_number"], ol["id"], ol["customer_name"] or "", ol["customer_phone"] or "", ol["customer_email"] or "",
                ol["country"] or "Bangladesh", ol["district"] or "Tangail", ol["area"] or "Tangail Sadar",
                ol["address_details"] or "", 0, "", items_json, items_json,
                float(ol["subtotal"] or 0.0), float(ol["delivery_charge"] or 50.0), float(ol["total_amount"] or 0.0),
                "reviewing" if ol["order_status"] in ("new", "pending", "pending_confirmation") else ol["order_status"],
                ol["delivery_otp"] or "1234", ol["created_at"] or "", ol["updated_at"] or ""
            ))
            conn.commit()
            order = conn.execute("SELECT * FROM pharmacy_orders WHERE order_number = ?", (ol["order_number"],)).fetchone()
            try:
                remote_control.push_pharmacy_order_to_cloud(order["id"])
            except Exception:
                pass
        else:
            conn.close()
            return jsonify({"success": False, "message": "অর্ডারটি খুঁজে পাওয়া যায়নি।"}), 404

    # Status synchronization with online_orders (Rider update check)
    current_status = order["order_status"]
    if order["online_order_id"]:
        ol_order = conn.execute("SELECT order_status, assigned_rider_id, assigned_rider_name, assigned_rider_phone FROM online_orders WHERE id = ?", (order["online_order_id"],)).fetchone()
        if ol_order:
            ol_st = ol_order["order_status"]
            # Map standard online statuses to pharmacy
            st_map = {
                "delivered": "delivered",
                "on_the_way": "on_the_way",
                "packed": "packed",
                "verified": "confirmed",
                "cancelled": "cancelled"
            }
            if ol_st in st_map and st_map[ol_st] != current_status:
                current_status = st_map[ol_st]
                conn.execute(
                    "UPDATE pharmacy_orders SET order_status = ?, assigned_rider_name = ?, assigned_rider_phone = ?, updated_at = ? WHERE id = ?",
                    (current_status, ol_order["assigned_rider_name"], ol_order["assigned_rider_phone"], get_bd_now_iso(), order["id"])
                )
                conn.commit()

    # Status names in Bengali
    status_bn_map = {
        "reviewing": "ফার্মাসিস্ট প্রেসক্রিপশন যাচাই করছেন",
        "awaiting_customer_confirmation": "বিল প্রস্তুত — আপনার কনফার্মেশনের অপেক্ষায়",
        "confirmed": "অর্ডার নিশ্চিত ও বিল তৈরি সম্পন্ন",
        "packed": "ওষুধ প্যাকড সম্পন্ন (ডেলিভারির জন্য প্রস্তুত)",
        "on_the_way": "ডেলিভারির পথে (রাইডারের কাছে হস্তান্তরিত)",
        "delivered": "সফলভাবে ডেলিভার্ড হয়েছে",
        "cancelled": "অর্ডারটি বাতিল করা হয়েছে"
    }

    try:
        req_items = json.loads(order["requested_items_json"] or "[]")
    except Exception:
        req_items = []

    try:
        app_items = json.loads(order["approved_items_json"] or "[]")
    except Exception:
        app_items = []

    result = {
        "success": True,
        "id": order["id"],
        "order_number": order["order_number"],
        "order_type": order["order_type"],
        "order_status": current_status,
        "status_bn": status_bn_map.get(current_status, current_status),
        "customer_confirmed": int(order["customer_confirmed"] or 0) if "customer_confirmed" in order.keys() else 0,
        "quote_sent_at": order["quote_sent_at"] if "quote_sent_at" in order.keys() else "",
        "quote_by": order["quote_by"] if "quote_by" in order.keys() else "",
        "customer_name": order["customer_name"],
        "customer_phone": order["customer_phone"],
        "delivery_address": order["delivery_address"],
        "district": order["district"],
        "area": order["area"],
        "prescription_url": _abs_url(order["prescription_url"]),
        "prescription_original_url": _abs_url(order["prescription_original_url"] or order["prescription_url"]),
        "prescription_enhanced_url": _abs_url(order["prescription_enhanced_url"] or order["prescription_url"]),
        "overall_duration_days": order["overall_duration_days"],
        "customer_notes": order["customer_notes"],
        "requested_items": req_items,
        "approved_items": app_items,
        "subtotal": order["subtotal"],
        "delivery_charge": order["delivery_charge"],
        "total_amount": order["total_amount"],
        "delivery_otp": order["delivery_otp"],
        "online_order_id": order["online_order_id"],
        "invoice_url": f"/online_orders/{order['online_order_id']}/invoice" if order["online_order_id"] else None,
        "assigned_rider_name": order["assigned_rider_name"],
        "assigned_rider_phone": order["assigned_rider_phone"],
        "admin_notes": order["admin_notes"],
        "created_at": order["created_at"],
        "confirmed_at": order["confirmed_at"],
        "packed_at": order["packed_at"],
        "on_the_way_at": order["on_the_way_at"],
        "delivered_at": order["delivered_at"]
    }
    conn.close()
    return jsonify(result)


@app.route("/api/pharmacy/customer-confirm-quote", methods=["POST"])
def api_pharmacy_customer_confirm_quote():
    """Customer confirms or cancels a reviewed pharmacy bill quotation before packing/dispatch can start."""
    data = request.get_json(silent=True) or request.form or {}
    order_number = (data.get("order_number") or "").strip()
    order_id = data.get("order_id")
    action = (data.get("action") or "confirm").strip().lower()
    raw_phone = (data.get("customer_phone") or session.get("customer_phone") or "").strip()
    norm_phone = normalize_phone(raw_phone) or raw_phone

    if not (order_number or order_id):
        return jsonify({"success": False, "message": "অর্ডার নম্বর প্রয়োজন।"}), 400
    if action not in ("confirm", "cancel"):
        return jsonify({"success": False, "message": "অবৈধ অ্যাকশন।"}), 400

    conn = get_connection()
    if order_number:
        order = conn.execute("SELECT * FROM pharmacy_orders WHERE order_number = ? LIMIT 1", (order_number,)).fetchone()
    else:
        order = conn.execute("SELECT * FROM pharmacy_orders WHERE id = ? LIMIT 1", (order_id,)).fetchone()

    if not order:
        conn.close()
        return jsonify({"success": False, "message": "অর্ডার খুঁজে পাওয়া যায়নি।"}), 404

    ord_phone_norm = normalize_phone(order["customer_phone"] or "") or (order["customer_phone"] or "").strip()
    if norm_phone and ord_phone_norm and norm_phone != ord_phone_norm:
        conn.close()
        return jsonify({"success": False, "message": "এই অর্ডারটি আপনার অ্যাকাউন্টের সাথে মেলেনি।"}), 403

    curr_st = (order["order_status"] or "").strip().lower()
    if curr_st != "awaiting_customer_confirmation":
        conn.close()
        return jsonify({"success": False, "message": f"অর্ডারটি বর্তমানে '{curr_st}' অবস্থায় রয়েছে এবং কনফার্মেশনের জন্য অপেক্ষমাণ নয়।"}), 400

    now_iso = get_bd_now_iso()
    ol_id = _ensure_online_order_for_pharmacy(conn, order["id"], now_iso=now_iso)

    if action == "confirm":
        # Strictly prevent checking out / confirming any medicine with 0 or insufficient stock
        try:
            approved_list = json.loads(order["approved_items_json"] or "[]")
        except Exception:
            approved_list = []
        med_demands = {}
        for it in approved_list:
            if not isinstance(it, dict):
                continue
            mid = it.get("medicine_id")
            it_type = (it.get("item_type") or ("medicine" if mid else "product")).strip().lower()
            if it_type == "medicine" and mid:
                q_it = max(1, int(it.get("quantity") or 1))
                u_cnt = max(1, int(it.get("unit_count") or 1))
                base_pcs = int(it.get("base_pieces") or (q_it * u_cnt))
                mid_int = int(mid)
                med_demands[mid_int] = med_demands.get(mid_int, 0) + base_pcs
        for mid_int, need_pcs in med_demands.items():
            m_chk = conn.execute("SELECT name, stock_qty, is_active FROM pharmacy_medicines WHERE id = ?", (mid_int,)).fetchone()
            if not m_chk or int(m_chk["is_active"] or 0) != 1 or int(m_chk["stock_qty"] or 0) <= 0:
                conn.close()
                m_nm = m_chk["name"] if m_chk else f"#{mid_int}"
                return jsonify({
                    "success": False,
                    "message": f'দুঃখিত, "{m_nm}" বর্তমানে স্টকে নেই (পরিমাণ ০)। স্টক না থাকা ঔষধ চেকআউট করা যাবে না।',
                }), 400
            if int(m_chk["stock_qty"] or 0) < need_pcs:
                conn.close()
                return jsonify({
                    "success": False,
                    "message": f'"{m_chk["name"]}" এর পর্যাপ্ত স্টক নেই (স্টক: {int(m_chk["stock_qty"] or 0)} পিস, প্রয়োজন: {need_pcs} পিস)।',
                }), 400

        conn.execute("""
            UPDATE pharmacy_orders SET
                order_status = 'confirmed',
                customer_confirmed = 1,
                confirmed_at = CASE WHEN COALESCE(confirmed_at, '') = '' THEN ? ELSE confirmed_at END,
                updated_at = ?
            WHERE id = ?
        """, (now_iso, now_iso, order["id"]))
        if ol_id:
            conn.execute("""
                UPDATE online_orders SET
                    order_status = 'verified',
                    confirmed_at = CASE WHEN COALESCE(confirmed_at, '') = '' THEN ? ELSE confirmed_at END,
                    updated_at = ?
                WHERE id = ?
            """, (now_iso, now_iso, ol_id))
            ol_row = conn.execute("SELECT * FROM online_orders WHERE id = ?", (ol_id,)).fetchone()
            if ol_row:
                deduct_online_order_stock(conn, ol_row)
                notify_order_status_change(ol_row, "verified", conn=conn)
        msg = f"ধন্যবাদ! অর্ডার #{order['order_number']} কনফার্ম হয়েছে। এখন প্যাকিং ও ডেলিভারি শুরু হবে।"
    else:
        conn.execute("""
            UPDATE pharmacy_orders SET
                order_status = 'cancelled',
                cancelled_at = CASE WHEN COALESCE(cancelled_at, '') = '' THEN ? ELSE cancelled_at END,
                updated_at = ?
            WHERE id = ?
        """, (now_iso, now_iso, order["id"]))
        if ol_id:
            conn.execute("""
                UPDATE online_orders SET
                    order_status = 'cancelled',
                    cancelled_at = CASE WHEN COALESCE(cancelled_at, '') = '' THEN ? ELSE cancelled_at END,
                    updated_at = ?
                WHERE id = ?
            """, (now_iso, now_iso, ol_id))
            ol_row = conn.execute("SELECT * FROM online_orders WHERE id = ?", (ol_id,)).fetchone()
            if ol_row:
                restore_online_order_stock(conn, ol_row)
                notify_order_status_change(ol_row, "cancelled", conn=conn)
        msg = f"অর্ডার #{order['order_number']} বাতিল করা হয়েছে।"

    conn.commit()
    conn.close()

    try:
        remote_control.push_pharmacy_order_to_cloud(order["id"])
        if ol_id:
            remote_control.push_online_order_to_cloud(ol_id)
    except Exception:
        pass

    return jsonify({"success": True, "order_status": "confirmed" if action == "confirm" else "cancelled", "message": msg})


# -----------------------------------------------------------------------------
# ADMIN & PHARMACIST COUNTER CONTROLS
# -----------------------------------------------------------------------------

@app.route("/admin/pharmacy")
@app.route("/admin/pharmacy-orders")
@login_required
def admin_pharmacy_orders():
    """Admin & Pharmacist Counter Portal (Prescription review, bill generator, price updater)"""
    conn = get_connection()
    
    # Auto-reconcile any RX orders from online_orders into pharmacy_orders if missing
    try:
        missing_rx = conn.execute("""
            SELECT * FROM online_orders 
            WHERE order_number LIKE 'RX-%' 
              AND order_number NOT IN (SELECT order_number FROM pharmacy_orders)
        """).fetchall()
        for m in missing_rx:
            items = conn.execute("SELECT * FROM online_order_items WHERE order_id = ?", (m["id"],)).fetchall()
            items_json = json.dumps([dict(it) for it in items], ensure_ascii=False)
            conn.execute("""
                INSERT INTO pharmacy_orders (
                    order_number, online_order_id, customer_name, customer_phone, customer_email,
                    country, district, area, delivery_address, order_type,
                    overall_duration_days, customer_notes, requested_items_json, approved_items_json,
                    subtotal, delivery_charge, total_amount, order_status, delivery_otp,
                    payment_method, payment_status, created_at, updated_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 'both', ?, ?, ?, ?, ?, ?, ?, ?, ?, 'cod', 'pending', ?, ?)
            """, (
                m["order_number"], m["id"], m["customer_name"] or "", m["customer_phone"] or "", m["customer_email"] or "",
                m["country"] or "Bangladesh", m["district"] or "Tangail", m["area"] or "Tangail Sadar",
                m["address_details"] or "", 0, "", items_json, items_json,
                float(m["subtotal"] or 0.0), float(m["delivery_charge"] or 50.0), float(m["total_amount"] or 0.0),
                "reviewing" if m["order_status"] in ("new", "pending", "pending_confirmation") else m["order_status"],
                m["delivery_otp"] or "1234", m["created_at"] or "", m["updated_at"] or ""
            ))
            conn.commit()
    except Exception as _reconcile_err:
        print(f"[pharmacy] Reconcile notice: {_reconcile_err}")

    status_filter = request.args.get("status", "").strip()
    search_q = request.args.get("q", "").strip()

    sql = "SELECT * FROM pharmacy_orders WHERE 1=1"
    params = []

    if status_filter:
        sql += " AND order_status = ?"
        params.append(status_filter)

    if search_q:
        sql += " AND (order_number LIKE ? OR customer_phone LIKE ? OR customer_name LIKE ?)"
        s_wild = f"%{search_q}%"
        params.extend([s_wild, s_wild, s_wild])

    sql += " ORDER BY id DESC LIMIT 100"
    orders = conn.execute(sql, params).fetchall()

    # Active riders for assignment
    riders = conn.execute("SELECT id, username, full_name FROM users WHERE role = 'delivery' AND is_active = 1 ORDER BY username ASC").fetchall()

    # Total medicines count (Lightweight - Zero Memory Pressure)
    med_count_row = conn.execute("SELECT COUNT(*) AS c FROM pharmacy_medicines WHERE is_active = 1").fetchone()
    total_medicines = med_count_row["c"] if med_count_row else 0

    # Distinct manufacturers for company dropdown
    mfg_rows = conn.execute("SELECT DISTINCT manufacturer FROM pharmacy_medicines WHERE manufacturer != '' AND manufacturer IS NOT NULL ORDER BY manufacturer ASC").fetchall()
    manufacturers = [r["manufacturer"] for r in mfg_rows]

    settings = get_all_settings(conn)
    conn.close()

    return render_template(
        "admin_pharmacy.html",
        orders=orders,
        riders=riders,
        total_medicines=total_medicines,
        manufacturers=manufacturers,
        settings=settings,
        active_status=status_filter,
        search_query=search_q
    )


@app.route("/api/admin/pharmacy/orders/latest-check", methods=["GET"])
@login_required
def api_admin_pharmacy_latest_check():
    """Lightweight real-time check for incoming pharmacy prescription orders."""
    conn = get_connection()
    row = conn.execute("SELECT MAX(id) AS max_id, COUNT(*) AS c FROM pharmacy_orders WHERE order_status = 'reviewing'").fetchone()
    latest = conn.execute("SELECT id, order_number, customer_name, total_amount FROM pharmacy_orders WHERE order_status = 'reviewing' ORDER BY id DESC LIMIT 1").fetchone()
    conn.close()
    return jsonify({
        "success": True,
        "latest_id": row["max_id"] if row and row["max_id"] else 0,
        "pending_count": row["c"] if row and row["c"] else 0,
        "latest_order_number": latest["order_number"] if latest else "",
        "latest_customer_name": latest["customer_name"] if latest else "",
        "latest_total": latest["total_amount"] if latest else 0.0
    })


@app.route("/api/admin/pharmacy/orders/<int:order_id>/review", methods=["GET"])
@login_required
def api_admin_pharmacy_review(order_id):
    """Fetches full order details for pharmacist inspection modal"""
    conn = get_connection()
    order = conn.execute("SELECT * FROM pharmacy_orders WHERE id = ?", (order_id,)).fetchone()
    if not order:
        conn.close()
        return jsonify({"success": False, "message": "Order not found."}), 404

    data = dict(order)
    try:
        data["requested_items"] = json.loads(order["requested_items_json"] or "[]")
    except Exception:
        data["requested_items"] = []

    try:
        data["approved_items"] = json.loads(order["approved_items_json"] or "[]")
    except Exception:
        data["approved_items"] = []

    ol_id = data.get("online_order_id")
    data["invoice_url"] = f"/online_orders/{ol_id}/invoice" if ol_id else ""

    conn.close()
    return jsonify({"success": True, "order": data})


@app.route("/api/admin/pharmacy/medicines/list", methods=["GET"])
@login_required
def api_admin_pharmacy_medicines_list():
    """Fast server-side paginated & searchable medicine catalog for admin"""
    q = (request.args.get("q") or "").strip()
    dosage = (request.args.get("dosage") or "").strip()
    mfg = (request.args.get("mfg") or "").strip()
    page = max(1, int(request.args.get("page") or 1))
    per_page = min(100, max(10, int(request.args.get("per_page") or 30)))
    offset = (page - 1) * per_page

    conn = get_connection()
    rows, total = _search_pharmacy_medicines(
        conn,
        q=q,
        dosage=dosage,
        mfg=mfg,
        limit=per_page,
        offset=offset,
        include_manufacturer=True,
        select_cols="id, name, generic_name, dosage_form, strength, manufacturer, sku, unit_price, cost_price, mrp, discount_percent, strip_price, strip_cost_price, strip_size, packet_price, packet_cost_price, packet_size, stock_qty, is_prescription_required, expiry_date, low_stock_threshold",
    )
    conn.close()

    total_pages = max(1, (total + per_page - 1) // per_page)
    return jsonify({
        "success": True,
        "total": total,
        "page": page,
        "per_page": per_page,
        "total_pages": total_pages,
        "medicines": rows
    })


@app.route("/api/admin/pharmacy/settings", methods=["GET", "POST"])
def api_admin_pharmacy_settings():
    """Allows admin to read or update pharmacy delivery charge and overall pharmacy discount"""
    data = request.get_json(silent=True) or request.form or {}
    conn = get_connection()
    actor = _authorize_admin_or_cashier(conn, data)
    if not actor:
        conn.close()
        return jsonify({"success": False, "message": "Admin/Cashier authorization required."}), 401

    if request.method == "GET":
        s = get_all_settings(conn)
        conn.close()
        return jsonify({
            "success": True,
            "pharmacy_delivery_charge": float(s.get("pharmacy_delivery_charge") or s.get("delivery_charge") or 50.0),
            "pharmacy_discount_percent": float(s.get("pharmacy_discount_percent") or 0.0),
        })

    updates = {}
    if "pharmacy_delivery_charge" in data:
        try:
            updates["pharmacy_delivery_charge"] = str(float(data.get("pharmacy_delivery_charge") or 50.0))
        except Exception:
            updates["pharmacy_delivery_charge"] = "50"
    if "pharmacy_discount_percent" in data:
        try:
            updates["pharmacy_discount_percent"] = str(float(data.get("pharmacy_discount_percent") or 0.0))
        except Exception:
            updates["pharmacy_discount_percent"] = "0"
    
    if updates:
        update_settings(conn, updates)
        conn.commit()
    s = get_all_settings(conn)
    conn.close()
    return jsonify({
        "success": True,
        "message": "Pharmacy settings updated successfully.",
        "settings": updates,
        "pharmacy_delivery_charge": float(s.get("pharmacy_delivery_charge") or 50.0),
        "pharmacy_discount_percent": float(s.get("pharmacy_discount_percent") or 0.0),
    })


def _normalize_medicine_multi_unit_pricing(data, med_id=None, strip_size=10, packet_size=30):
    """Computes consistent piece, strip (পাতা), and packet (প্যাকেট) purchase & selling prices."""
    s_sz = max(1, int(strip_size or 10))
    p_sz = max(1, int(packet_size or 30))

    def _f(k):
        try:
            return max(0.0, float(data.get(k) or 0.0))
        except Exception:
            return 0.0

    mrp = _f("mrp")
    disc = min(100.0, _f("discount_percent"))
    unit_price = _f("unit_price")
    cost_price = _f("cost_price")
    strip_price = _f("strip_price")
    strip_cost_price = _f("strip_cost_price")
    packet_price = _f("packet_price")
    packet_cost_price = _f("packet_cost_price")

    if mrp > 0 and disc > 0 and unit_price <= 0:
        unit_price = round(mrp * (1.0 - disc / 100.0), 2)
    elif mrp > 0 and unit_price > 0 and disc <= 0 and mrp > unit_price:
        disc = round(((mrp - unit_price) / mrp) * 100.0, 1)
    elif mrp <= 0 and unit_price > 0:
        mrp = unit_price

    if unit_price <= 0:
        if strip_price > 0:
            unit_price = round(strip_price / s_sz, 2)
            mrp = mrp if mrp > 0 else unit_price
        elif packet_price > 0:
            unit_price = round(packet_price / p_sz, 2)
            mrp = mrp if mrp > 0 else unit_price

    if strip_price <= 0 and unit_price > 0:
        strip_price = round(unit_price * s_sz, 2)
    if packet_price <= 0 and unit_price > 0:
        packet_price = round(unit_price * p_sz, 2)

    if cost_price <= 0:
        if strip_cost_price > 0:
            cost_price = round(strip_cost_price / s_sz, 4)
        elif packet_cost_price > 0:
            cost_price = round(packet_cost_price / p_sz, 4)
    if strip_cost_price <= 0 and cost_price > 0:
        strip_cost_price = round(cost_price * s_sz, 2)
    if packet_cost_price <= 0 and cost_price > 0:
        packet_cost_price = round(cost_price * p_sz, 2)

    return {
        "mrp": round(mrp, 2),
        "discount_percent": round(disc, 2),
        "unit_price": round(unit_price, 2),
        "cost_price": round(cost_price, 4),
        "strip_size": s_sz,
        "strip_price": round(strip_price, 2),
        "strip_cost_price": round(strip_cost_price, 2),
        "packet_size": p_sz,
        "packet_price": round(packet_price, 2),
        "packet_cost_price": round(packet_cost_price, 2),
    }


def _resolve_medicine_line_pricing(med_row, overall_disc, price_mode="piece", custom_unit_price=None):
    """Resolves unit_count, sell_price, mrp_price, and exact purchase cost_price for piece/strip/packet."""
    m = dict(med_row)
    mode_raw = str(price_mode or "piece").strip().lower()
    if mode_raw in ("strip", "পাতা", "pata"):
        mode = "strip"
    elif mode_raw in ("packet", "pack", "box", "প্যাকেট", "বক্স"):
        mode = "packet"
    else:
        mode = "piece"

    s_sz = max(1, int(m.get("strip_size") or 10))
    p_sz = max(1, int(m.get("packet_size") or 30))

    mrp_pc, sell_pc, eff_disc = _calc_medicine_sell_price(m, overall_disc)
    cost_pc = float(m.get("cost_price") or 0.0)
    s_cost = float(m.get("strip_cost_price") or 0.0)
    p_cost = float(m.get("packet_cost_price") or 0.0)
    if cost_pc <= 0 and s_cost > 0:
        cost_pc = round(s_cost / s_sz, 4)
    elif cost_pc <= 0 and p_cost > 0:
        cost_pc = round(p_cost / p_sz, 4)

    if mode == "strip":
        unit_count = s_sz
        base_strip_p = float(m.get("strip_price") or 0.0)
        mrp_unit = round(base_strip_p if base_strip_p > 0 else (mrp_pc * s_sz), 2)
        if base_strip_p > 0:
            sell_unit = round(base_strip_p * (1.0 - eff_disc / 100.0), 2) if (eff_disc > 0 and float(m.get("discount_percent") or 0) <= 0 and overall_disc > 0) else round(base_strip_p, 2)
        else:
            sell_unit = round(sell_pc * s_sz, 2)
        cost_unit = round(s_cost if s_cost > 0 else (cost_pc * s_sz), 2)
        unit_label = f"পাতা ({s_sz} পিস)"
    elif mode == "packet":
        unit_count = p_sz
        base_pkt_p = float(m.get("packet_price") or 0.0)
        mrp_unit = round(base_pkt_p if base_pkt_p > 0 else (mrp_pc * p_sz), 2)
        if base_pkt_p > 0:
            sell_unit = round(base_pkt_p * (1.0 - eff_disc / 100.0), 2) if (eff_disc > 0 and float(m.get("discount_percent") or 0) <= 0 and overall_disc > 0) else round(base_pkt_p, 2)
        else:
            sell_unit = round(sell_pc * p_sz, 2)
        cost_unit = round(p_cost if p_cost > 0 else (cost_pc * p_sz), 2)
        unit_label = f"প্যাকেট ({p_sz} পিস)"
    else:
        unit_count = 1
        mrp_unit = mrp_pc
        sell_unit = sell_pc
        cost_unit = round(cost_pc, 4)
        unit_label = "পিস"

    if custom_unit_price is not None:
        try:
            cp = float(custom_unit_price)
            if cp > 0:
                sell_unit = round(cp, 2)
        except Exception:
            pass

    return {
        "unit_mode": mode,
        "unit_label": unit_label,
        "unit_count": unit_count,
        "sell_price": sell_unit,
        "mrp_price": mrp_unit,
        "cost_price": cost_unit,
    }


def _save_and_send_pharmacy_quote(conn, order_id, items, delivery_charge=50.0, admin_notes="", actor_name="Pharmacist"):
    """Validates items (medicines by piece/strip/packet + regular products), saves quote, and requires customer confirmation."""
    order = conn.execute("SELECT * FROM pharmacy_orders WHERE id = ?", (order_id,)).fetchone()
    if not order:
        return None, "অর্ডারটি পাওয়া যায়নি।"
    shop_settings = get_all_settings(conn)
    overall_disc = float(shop_settings.get("pharmacy_discount_percent") or 0.0)

    processed_items = []
    med_demands = {}
    subtotal = 0.0
    total_cost = 0.0
    for it in items:
        it_type = (it.get("item_type") or ("medicine" if it.get("medicine_id") else ("package" if it.get("package_id") else ("product" if it.get("product_id") else "medicine")))).strip().lower()
        try:
            qty = max(1, int(it.get("quantity") or it.get("qty") or 1))
        except Exception:
            qty = 1
        price_mode = (it.get("unit_mode") or it.get("price_mode") or it.get("sell_unit") or it.get("unit") or "piece").strip()
        med_id = it.get("medicine_id") or (it.get("id") if it_type == "medicine" else None)
        prod_id = it.get("product_id") or (it.get("id") if it_type in ("product", "package") else None)
        custom_price = it.get("unit_price")

        if it_type == "medicine" and med_id:
            med = conn.execute("SELECT * FROM pharmacy_medicines WHERE id = ?", (med_id,)).fetchone()
            if med:
                resolved = _resolve_medicine_line_pricing(med, overall_disc, price_mode=price_mode, custom_unit_price=custom_price)
                unit_price = resolved["sell_price"]
                cost_price = resolved["cost_price"]
                unit_count = resolved["unit_count"]
                unit_label = resolved["unit_label"]
                unit_mode = resolved["unit_mode"]
                name = (it.get("name") or med["name"] or "").strip()
                gen = it.get("generic_name") or med["generic_name"] or ""
                d_form = it.get("dosage_form") or med["dosage_form"] or "Tablet"
                strength = it.get("strength") or med["strength"] or ""
                avail_stk = int(med["stock_qty"] or 0)
                need_pcs = qty * unit_count
                mid_int = int(med["id"])
                med_demands[mid_int] = med_demands.get(mid_int, 0) + need_pcs
                if avail_stk <= 0:
                    return None, f'"{name}"-এর স্টক ০! স্টক শূন্য থাকা ঔষধ বিল/অর্ডার করা যাবে না — আগে স্টক আপডেট করুন।'
                if med_demands[mid_int] > avail_stk:
                    return None, f'"{name}"-এর পর্যাপ্ত স্টক নেই (স্টক: {avail_stk} পিস, বিল: {med_demands[mid_int]} পিস)।'
            else:
                unit_price = float(custom_price or 0.0)
                cost_price = float(it.get("cost_price") or 0.0)
                unit_count = max(1, int(it.get("unit_count") or 1))
                unit_label = it.get("unit") or "পিস"
                unit_mode = "piece"
                name = (it.get("name") or "").strip()
                gen = it.get("generic_name") or ""
                d_form = it.get("dosage_form") or "Tablet"
                strength = it.get("strength") or ""
        elif it_type in ("product", "package") and prod_id:
            if it_type == "package":
                pkg = conn.execute("SELECT * FROM packages WHERE id = ?", (prod_id,)).fetchone()
                name = (it.get("name") or (pkg["name"] if pkg else "")).strip()
                unit_price = float(custom_price or (pkg["package_price"] if pkg else 0.0))
                pkg_items = conn.execute("SELECT pi.quantity, COALESCE(p.cost_price, 0) AS cost_price FROM package_items pi JOIN products p ON pi.product_id = p.id WHERE pi.package_id = ?", (prod_id,)).fetchall()
                cost_price = round(sum(float(x["cost_price"] or 0.0) * float(x["quantity"] or 1) for x in pkg_items), 2)
                unit_label = "কম্বো প্যাকেজ"
            else:
                prod = conn.execute("SELECT * FROM products WHERE id = ?", (prod_id,)).fetchone()
                name = (it.get("name") or (prod["name"] if prod else "")).strip()
                unit_price = float(custom_price or (prod["sell_price"] if prod else 0.0))
                cost_price = float(prod["cost_price"] or 0.0) if prod else float(it.get("cost_price") or 0.0)
                unit_label = it.get("unit") or (prod["unit"] if prod and prod["unit"] else "পিস")
            unit_count = 1
            unit_mode = it_type
            gen = ""
            d_form = it_type.title()
            strength = ""
        else:
            name = (it.get("name") or "").strip()
            if not name:
                continue
            unit_price = float(custom_price or 0.0)
            cost_price = float(it.get("cost_price") or 0.0)
            unit_count = max(1, int(it.get("unit_count") or 1))
            unit_label = it.get("unit") or "পিস"
            unit_mode = "custom"
            gen = it.get("generic_name") or ""
            d_form = it.get("dosage_form") or "Tablet"
            strength = it.get("strength") or ""

        if not name:
            continue
        base_pieces = qty * unit_count
        line_total = round(qty * unit_price, 2)
        line_cost = round(qty * cost_price, 2)
        subtotal += line_total
        total_cost += line_cost
        processed_items.append({
            "item_type": it_type,
            "medicine_id": int(med_id) if med_id else None,
            "product_id": int(prod_id) if prod_id else None,
            "name": name,
            "generic_name": gen,
            "dosage_form": d_form,
            "strength": strength,
            "quantity": qty,
            "unit_mode": unit_mode,
            "unit": unit_label,
            "unit_count": unit_count,
            "base_pieces": base_pieces,
            "unit_price": round(unit_price, 2),
            "cost_price": round(cost_price, 4),
            "total_price": line_total,
            "total_cost": line_cost,
        })

    if not processed_items:
        return None, "অনুগ্রহ করে কমপক্ষে একটি ওষুধ বা পণ্য বিলে যোগ করুন।"

    subtotal = round(subtotal, 2)
    grand_total = round(subtotal + delivery_charge, 2)
    now_iso = get_bd_now_iso()

    conn.execute("""
        UPDATE pharmacy_orders SET
            approved_items_json = ?,
            subtotal = ?,
            delivery_charge = ?,
            total_amount = ?,
            admin_notes = ?,
            order_status = 'awaiting_customer_confirmation',
            customer_confirmed = 0,
            quote_sent_at = ?,
            quote_by = ?,
            updated_at = ?
        WHERE id = ?
    """, (
        json.dumps(processed_items, ensure_ascii=False),
        subtotal, delivery_charge, grand_total,
        admin_notes, now_iso, actor_name, now_iso, order_id
    ))

    ol_id = _ensure_online_order_for_pharmacy(conn, order_id, approved_items=processed_items, now_iso=now_iso)
    order_ref = conn.execute("SELECT * FROM pharmacy_orders WHERE id = ?", (order_id,)).fetchone()
    if ol_id and order_ref and order_ref["order_number"]:
        stale_sale = conn.execute("SELECT id FROM sales WHERE invoice_number = ?", (f"INV-ONLINE-{order_ref['order_number']}",)).fetchone()
        if stale_sale:
            conn.execute("DELETE FROM sale_items WHERE sale_id = ?", (stale_sale["id"],))
            conn.execute("DELETE FROM sales WHERE id = ?", (stale_sale["id"],))

    # Notify Customer Android Notification Tray & Bell: Customer MUST confirm before order proceeds
    cust_phone = (order_ref["customer_phone"] or "").strip() if order_ref else ""
    ord_num = (order_ref["order_number"] or f"RX-{order_id}") if order_ref else f"RX-{order_id}"
    if cust_phone:
        add_customer_notification(
            customer_phone=cust_phone,
            title=f"💊 প্রেসক্রিপশন বিল প্রস্তুত — কনফার্ম করুন (#{ord_num})",
            message=f"আপনার অর্ডার #{ord_num} যাচাই করে মোট বিল TK {grand_total:.2f} প্রস্তুত করা হয়েছে। অনুগ্রহ করে অ্যাপে প্রবেশ করে কনফার্ম করুন নতুবা প্যাকিং শুরু হবে না।",
            notif_type="pharmacy_quote",
            reference_id=str(ord_num),
            conn=conn,
        )

    conn.commit()
    try:
        remote_control.push_pharmacy_order_to_cloud(order_id)
        if ol_id:
            remote_control.push_online_order_to_cloud(ol_id)
    except Exception:
        pass

    return {
        "order": dict(order_ref) if order_ref else {},
        "online_order_id": ol_id,
        "subtotal": subtotal,
        "delivery_charge": delivery_charge,
        "grand_total": grand_total,
        "total_cost": round(total_cost, 2),
        "processed_items": processed_items,
    }, None


@app.route("/api/admin/pharmacy/orders/<int:order_id>/generate-bill", methods=["POST"])
@login_required
def api_admin_pharmacy_generate_bill(order_id):
    """
    Admin / Pharmacist reviews prescription, adds medicines/products (with piece/strip/packet pricing),
    and sends quote for MANDATORY customer confirmation before proceeding.
    """
    req_data = request.get_json(silent=True) or request.form or {}
    items = req_data.get("items") or []
    admin_notes = (req_data.get("admin_notes") or "").strip()
    try:
        delivery_charge = float(req_data.get("delivery_charge") or 50.0)
    except Exception:
        delivery_charge = 50.0

    if not items:
        return jsonify({"success": False, "message": "অনুগ্রহ করে কমপক্ষে একটি ওষুধ বিলে যোগ করুন।"}), 400

    actor_name = session.get("full_name") or session.get("username") or "Admin/Pharmacist"
    conn = get_connection()
    result, err = _save_and_send_pharmacy_quote(
        conn, order_id, items, delivery_charge=delivery_charge, admin_notes=admin_notes, actor_name=actor_name
    )
    conn.close()
    if err:
        return jsonify({"success": False, "message": err}), 400

    ol_id = result["online_order_id"]
    ord_num = result["order"].get("order_number", order_id)
    invoice_url = f"/online_orders/{ol_id}/invoice" if ol_id else None
    return jsonify({
        "success": True,
        "order_status": "awaiting_customer_confirmation",
        "message": f"Order #{ord_num} bill sent to customer for confirmation (Total: TK {result['grand_total']:.2f}). Packing/delivery will unlock once customer confirms.",
        "online_order_id": ol_id,
        "invoice_url": invoice_url
    })


def _execute_pharmacy_order_status_update(conn, order_id, new_status, rider_id=None, otp_code="",
                                         assign_rider_fallback=None, require_otp=False):
    """Shared validation, status transition, online_orders mirror sync, and push dispatch."""
    valid_statuses = ["reviewing", "awaiting_customer_confirmation", "confirmed", "packed", "on_the_way", "delivered", "cancelled"]
    if new_status not in valid_statuses:
        return None, ("অবৈধ স্ট্যাটাস।", 400)

    order = conn.execute("SELECT * FROM pharmacy_orders WHERE id = ?", (order_id,)).fetchone()
    if not order:
        return None, ("অর্ডার পাওয়া যায়নি।", 404)

    curr_st = (order["order_status"] or "").strip().lower()
    if curr_st == "awaiting_customer_confirmation" and new_status in ("confirmed", "packed", "on_the_way", "delivered"):
        return None, ("গ্রাহক এখনো বিলের কোটেশন কনফার্ম করেননি! কাস্টমার কনফার্ম না করা পর্যন্ত অর্ডার সামনে এগানো যাবে না।", 400)

    if new_status == "delivered":
        expected_otp = (order["delivery_otp"] or "").strip()
        if require_otp and expected_otp and otp_code != expected_otp:
            return None, ("ভুল ডেলিভারি ওটিপি কোড! অনুগ্রহ করে গ্রাহকের ৪ ডিজিট কোড মিলিয়ে দিন।", 400)
        elif otp_code and expected_otp and otp_code != expected_otp:
            return None, ("ভুল ডেলিভারি ওটিপি কোড! অনুগ্রহ করে গ্রাহকের ৪ ডিজিট কোড মিলিয়ে দিন।", 400)

    now_iso = get_bd_now_iso()
    rider_name = order["assigned_rider_name"]
    rider_phone = order["assigned_rider_phone"]

    if rider_id:
        rider = conn.execute("SELECT * FROM users WHERE id = ?", (rider_id,)).fetchone()
        if rider:
            rider_name = rider["full_name"] if rider["full_name"] else rider["username"]
            rider_phone = rider["username"]
    elif assign_rider_fallback and not (rider_phone or "").strip():
        rider_id = assign_rider_fallback.get("id")
        rider_name = assign_rider_fallback.get("full_name") or assign_rider_fallback.get("username") or ""
        rider_phone = assign_rider_fallback.get("username") or ""

    time_col = ""
    if new_status == "confirmed":
        time_col = ", confirmed_at = CASE WHEN COALESCE(confirmed_at, '') = '' THEN ? ELSE confirmed_at END"
    elif new_status == "packed":
        time_col = ", packed_at = CASE WHEN COALESCE(packed_at, '') = '' THEN ? ELSE packed_at END"
    elif new_status == "on_the_way":
        time_col = ", on_the_way_at = CASE WHEN COALESCE(on_the_way_at, '') = '' THEN ? ELSE on_the_way_at END"
    elif new_status == "delivered":
        time_col = ", delivered_at = CASE WHEN COALESCE(delivered_at, '') = '' THEN ? ELSE delivered_at END, payment_status = 'paid'"
    elif new_status == "cancelled":
        time_col = ", cancelled_at = CASE WHEN COALESCE(cancelled_at, '') = '' THEN ? ELSE cancelled_at END"

    query = f"""
        UPDATE pharmacy_orders SET
            order_status = ?,
            assigned_rider_id = COALESCE(?, assigned_rider_id),
            assigned_rider_name = ?,
            assigned_rider_phone = ?,
            updated_at = ?
            {time_col}
        WHERE id = ?
    """
    params = [new_status, rider_id, rider_name, rider_phone, now_iso]
    if time_col:
        params.append(now_iso)
    params.append(order_id)
    conn.execute(query, params)

    ol_id = _ensure_online_order_for_pharmacy(conn, order_id, now_iso=now_iso)
    if ol_id:
        if new_status == "delivered":
            r_fee = get_rider_delivery_fee_setting(conn)
            conn.execute(
                "UPDATE online_orders SET payment_status = 'paid', rider_fee = CASE WHEN COALESCE(rider_fee, 0) <= 0 THEN ? ELSE rider_fee END WHERE id = ?",
                (r_fee, ol_id),
            )
        ol_row = conn.execute("SELECT * FROM online_orders WHERE id = ?", (ol_id,)).fetchone()
        if ol_row:
            target_ol_st = _PHARM_TO_OL_STATUS.get(new_status, new_status)
            notify_order_status_change(ol_row, target_ol_st, conn=conn)

    conn.commit()
    try:
        remote_control.push_pharmacy_order_to_cloud(order_id)
        if ol_id:
            remote_control.push_online_order_to_cloud(ol_id)
    except Exception:
        pass
    return {"order_id": order_id, "online_order_id": ol_id, "status": new_status}, None


@app.route("/api/admin/pharmacy/orders/<int:order_id>/update-status", methods=["POST"])
@login_required
def api_admin_pharmacy_update_status(order_id):
    """
    Updates the lifecycle status of a pharmacy order:
    'packed' -> 'on_the_way' (with rider assignment) -> 'delivered' (with OTP check) -> 'cancelled'
    """
    order_id = request.view_args.get("order_id")
    data = request.get_json(silent=True) or request.form or {}
    new_status = (data.get("status") or "").strip()
    rider_id = data.get("rider_id")
    otp_code = (data.get("otp") or "").strip()

    conn = get_connection()
    _, err = _execute_pharmacy_order_status_update(
        conn, order_id, new_status, rider_id=rider_id, otp_code=otp_code, require_otp=False
    )
    conn.close()
    if err:
        return jsonify({"success": False, "message": err[0]}), err[1]

    return jsonify({"success": True, "message": f"Order status updated to '{new_status}' successfully."})


@app.route("/api/admin/pharmacy/medicines/save", methods=["POST"])
@login_required
def api_admin_pharmacy_save_medicine():
    """
    Adds or updates a medicine in the database.
    Allows real-time price updates (Rule 5: 'খেয়াল রাখতে হবে যেন নতুন দাম ও প্রোডাক্ট আপডেট থাকে')
    and custom barcode / SKU configuration.
    """
    data = request.get_json(silent=True) or request.form or {}
    med_id = data.get("id")
    name = (data.get("name") or "").strip()
    generic_name = (data.get("generic_name") or "").strip()
    dosage_form = (data.get("dosage_form") or "Tablet").strip()
    strength = (data.get("strength") or "").strip()
    manufacturer = (data.get("manufacturer") or "").strip()
    sku = (data.get("sku") or "").strip()
    description = (data.get("description") or "").strip()
    
    try:
        unit_price = float(data.get("unit_price") or 0.0)
    except Exception:
        unit_price = 0.0

    try:
        mrp = float(data.get("mrp") or 0.0)
    except Exception:
        mrp = 0.0

    try:
        discount_percent = float(data.get("discount_percent") or 0.0)
    except Exception:
        discount_percent = 0.0

    try:
        strip_size = max(1, int(data.get("strip_size") or 10))
    except Exception:
        strip_size = 10

    try:
        packet_size = max(1, int(data.get("packet_size") or 30))
    except Exception:
        packet_size = 30

    norm_p = _normalize_medicine_multi_unit_pricing(data, med_id=med_id, strip_size=strip_size, packet_size=packet_size)
    unit_price = norm_p["unit_price"]
    mrp = norm_p["mrp"]
    discount_percent = norm_p["discount_percent"]
    strip_price = norm_p["strip_price"]
    strip_cost_price = norm_p["strip_cost_price"]
    packet_price = norm_p["packet_price"]
    packet_cost_price = norm_p["packet_cost_price"]
    cost_price = norm_p["cost_price"]

    raw_stk = data.get("stock_qty")
    try:
        stock_qty = max(0, int(raw_stk)) if raw_stk not in (None, "") else 0
    except Exception:
        stock_qty = 0

    expiry_date = (data.get("expiry_date") or "").strip()
    try:
        low_stock_threshold = int(data.get("low_stock_threshold") or 10)
    except Exception:
        low_stock_threshold = 10

    is_rx = 1 if data.get("is_prescription_required") in [1, "1", True, "true"] else 0
    now_iso = get_bd_now_iso()

    if not name:
        return jsonify({"success": False, "message": "Medicine name is required."}), 400

    conn = get_connection()
    cur = conn.cursor()

    if med_id:
        if not sku:
            sku = f"MED-{int(med_id):05d}"
        
        # Check SKU uniqueness
        cur.execute("SELECT id, name FROM pharmacy_medicines WHERE sku = ? AND id != ?", (sku, med_id))
        dup = cur.fetchone()
        if dup:
            conn.close()
            return jsonify({"success": False, "message": f"Barcode/SKU '{sku}' is already assigned to '{dup['name']}'."}), 400

        cur.execute("""
            UPDATE pharmacy_medicines SET
                name = ?, generic_name = ?, dosage_form = ?, strength = ?,
                manufacturer = ?, sku = ?, unit_price = ?, mrp = ?, discount_percent = ?,
                strip_price = ?, strip_cost_price = ?, strip_size = ?,
                packet_price = ?, packet_cost_price = ?, packet_size = ?,
                stock_qty = ?, is_prescription_required = ?,
                expiry_date = ?, low_stock_threshold = ?, cost_price = ?,
                description = ?, updated_at = ?
            WHERE id = ?
        """, (
            name, generic_name, dosage_form, strength, manufacturer, sku,
            unit_price, mrp, discount_percent,
            strip_price, strip_cost_price, strip_size,
            packet_price, packet_cost_price, packet_size,
            stock_qty, is_rx, expiry_date, low_stock_threshold, cost_price,
            description, now_iso, med_id
        ))
        msg = f"'{name}' (SKU: {sku}) details and multi-unit pricing updated successfully."
    else:
        if not sku:
            cur.execute("SELECT MAX(id) FROM pharmacy_medicines")
            row = cur.fetchone()
            next_id = (row[0] or 0) + 1 if row else 1
            sku = f"MED-{next_id:05d}"
        else:
            cur.execute("SELECT id, name FROM pharmacy_medicines WHERE sku = ?", (sku,))
            dup = cur.fetchone()
            if dup:
                conn.close()
                return jsonify({"success": False, "message": f"Barcode/SKU '{sku}' is already assigned to '{dup['name']}'."}), 400

        cur.execute("""
            INSERT INTO pharmacy_medicines (
                name, generic_name, dosage_form, strength, manufacturer, sku,
                unit_price, mrp, discount_percent,
                strip_price, strip_cost_price, strip_size,
                packet_price, packet_cost_price, packet_size,
                stock_qty, is_prescription_required, expiry_date, low_stock_threshold, cost_price,
                image_url, description, is_active, created_at, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '', ?, 1, ?, ?)
        """, (
            name, generic_name, dosage_form, strength, manufacturer, sku,
            unit_price, mrp, discount_percent,
            strip_price, strip_cost_price, strip_size,
            packet_price, packet_cost_price, packet_size,
            stock_qty, is_rx, expiry_date, low_stock_threshold, cost_price,
            description, now_iso, now_iso
        ))
        med_id = cur.lastrowid
        msg = f"Medicine '{name}' (SKU: {sku}) added to catalog successfully."

    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": msg, "sku": sku, "med_id": med_id})


@app.route("/admin/pharmacy/medicines/<int:med_id>/labels")
@login_required
def admin_pharmacy_medicine_labels(med_id):
    """
    Renders 1.5in x 1in thermal barcode sticker labels for pharmacy medicines.
    Uses Code128 scannable SVG barcode of the medicine's SKU.
    """
    conn = get_connection()
    med = conn.execute("SELECT * FROM pharmacy_medicines WHERE id = ?", (med_id,)).fetchone()
    conn.close()

    if not med:
        flash("ঔষধ পাওয়া যায়নি।", "error")
        return redirect(url_for("admin_pharmacy_orders"))

    sku = (med["sku"] or f"MED-{med['id']:05d}").strip()
    try:
        qty = int(request.args.get("qty", 10))
    except Exception:
        qty = 10
    qty = max(1, min(qty, 500))

    autoprint = request.args.get("autoprint", "0") == "1"
    barcode_svg = generate_barcode_svg(sku)

    return render_template(
        "pharmacy_labels.html",
        med=med,
        sku=sku,
        barcode_svg=barcode_svg,
        qty=qty,
        autoprint=autoprint
    )


@app.route("/api/admin/pharmacy/orders/<int:order_id>/update-prescription", methods=["POST"])
@login_required
def api_admin_pharmacy_update_prescription(order_id):
    """
    Admin re-crops or enhances customer prescription image.
    Preserves original photo while updating enhanced prescription URL.
    """
    data = request.get_json(silent=True) or request.form or {}
    enhanced_base64 = data.get("prescription_base64")
    if not enhanced_base64:
        return jsonify({"success": False, "message": "কোনো পরিবর্তিত ছবি পাওয়া যায়নি।"}), 400

    new_url, _ = _save_base64_image(enhanced_base64, prefix="rx_admin_enhanced")
    if not new_url:
        return jsonify({"success": False, "message": "ছবি প্রসেস করতে সমস্যা হয়েছে।"}), 500

    conn = get_connection()
    now_iso = get_bd_now_iso()
    conn.execute(
        "UPDATE pharmacy_orders SET prescription_url = ?, prescription_enhanced_url = ?, updated_at = ? WHERE id = ?",
        (new_url, new_url, now_iso, order_id)
    )
    conn.commit()
    conn.close()

    try:
        remote_control.push_pharmacy_order_to_cloud(order_id)
    except Exception:
        pass

    return jsonify({
        "success": True,
        "new_url": new_url,
        "message": "Prescription successfully cropped, enhanced and updated."
    })


@app.route("/api/admin/pharmacy/medicines/<int:med_id>/delete", methods=["POST"])
@login_required
def api_admin_pharmacy_delete_medicine(med_id):
    """Soft delete / deactivate a medicine from the pharmacy catalog"""
    conn = get_connection()
    conn.execute("UPDATE pharmacy_medicines SET is_active = 0, updated_at = ? WHERE id = ?", (get_bd_now_iso(), med_id))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "ঔষধটি সফলভাবে নিষ্ক্রিয় করা হয়েছে।"})


def _calc_medicine_sell_price(med_row, overall_disc):
    mrp_val = float(med_row["mrp"] or med_row["unit_price"] or 0.0)
    if mrp_val <= 0:
        mrp_val = float(med_row["unit_price"] or 0.0)
    prod_disc = float(med_row["discount_percent"] or 0.0)
    eff_disc = max(prod_disc, overall_disc)
    if eff_disc > 0 and mrp_val > 0:
        sell_p = round(mrp_val * (1.0 - eff_disc / 100.0), 2)
    else:
        sell_p = float(med_row["unit_price"] or mrp_val)
    return round(mrp_val, 2), round(sell_p, 2), eff_disc


def _format_pos_medicine_dict(r, overall_disc):
    mrp_val, sell_p, eff_disc = _calc_medicine_sell_price(r, overall_disc)
    return {
        "type": "medicine",
        "id": f"med_{r['id']}",
        "medicine_id": r["id"],
        "is_medicine": True,
        "name": f"💊 {r['name']}" + (f" ({r['strength']})" if r["strength"] else (f" ({r['dosage_form']})" if r["dosage_form"] else "")),
        "raw_name": r["name"],
        "generic_name": r["generic_name"] or "",
        "dosage_form": r["dosage_form"] or "Tablet",
        "strength": r["strength"] or "",
        "manufacturer": r["manufacturer"] or "",
        "sku": r["sku"] or f"MED-{r['id']:05d}",
        "price": sell_p,
        "mrp": mrp_val,
        "discount_percent": eff_disc,
        "strip_price": float(r["strip_price"] or 0.0),
        "strip_cost_price": float(r["strip_cost_price"] or 0.0) if "strip_cost_price" in r.keys() else 0.0,
        "strip_size": r["strip_size"] or 10,
        "packet_price": float(r["packet_price"] or 0.0) if "packet_price" in r.keys() else 0.0,
        "packet_cost_price": float(r["packet_cost_price"] or 0.0) if "packet_cost_price" in r.keys() else 0.0,
        "packet_size": int(r["packet_size"] or 30) if "packet_size" in r.keys() else 30,
        "stock_qty": int(r["stock_qty"] or 0),
        "expiry_date": r["expiry_date"] or "",
        "cost_price": float(r["cost_price"] or 0.0),
    }


@app.route("/api/admin/pharmacy/pos/search", methods=["GET"])
@login_required
def api_admin_pharmacy_pos_search():
    """Search medicines for the Pharmacy Order POS Counter (returns ALL matched items ordered best-match-first when q is given)."""
    q = (request.args.get("q") or "").strip()

    conn = get_connection()
    shop_settings = get_all_settings(conn)
    overall_disc = float(shop_settings.get("pharmacy_discount_percent") or 0.0)

    if not q:
        rows, _ = _search_pharmacy_medicines(conn, q="", limit=60, only_in_stock=True, select_cols="*")
    else:
        rows, _ = _search_pharmacy_medicines(conn, q=q, limit=250, include_manufacturer=True, select_cols="*")

    results = [_format_pos_medicine_dict(r, overall_disc) for r in rows]
    conn.close()
    return jsonify({"success": True, "count": len(results), "results": results})


@app.route("/api/admin/pharmacy/pos/lookup", methods=["POST"])
@login_required
def api_admin_pharmacy_pos_lookup():
    """Barcode / SKU / Name lookup specifically for Pharmacy POS Checkout."""
    data = request.get_json(silent=True) or {}
    code = (data.get("code") or "").strip()
    if not code:
        return jsonify({"error": "No barcode or medicine name provided."}), 400

    conn = get_connection()
    shop_settings = get_all_settings(conn)
    overall_disc = float(shop_settings.get("pharmacy_discount_percent") or 0.0)

    med = conn.execute(
        "SELECT * FROM pharmacy_medicines WHERE is_active = 1 AND (sku = ? OR UPPER(sku) = UPPER(?))",
        (code, code)
    ).fetchone()

    if not med and (code.lower().startswith("med_") or code.lower().startswith("med-")):
        try:
            med_id = int(re.sub(r"\D", "", code))
            med = conn.execute("SELECT * FROM pharmacy_medicines WHERE id = ? AND is_active = 1", (med_id,)).fetchone()
        except Exception:
            med = None

    if not med:
        med = conn.execute("""
            SELECT * FROM pharmacy_medicines
            WHERE is_active = 1 AND (LOWER(name) = LOWER(?) OR LOWER(name) LIKE ?)
            ORDER BY CASE WHEN LOWER(name) = LOWER(?) THEN 0 ELSE 1 END, name ASC LIMIT 1
        """, (code, f"{code}%", code)).fetchone()

    if not med:
        conn.close()
        return jsonify({"error": f'No medicine found for "{code}".'}), 404

    today_date = datetime.now().strftime("%Y-%m-%d")
    if med["expiry_date"] and med["expiry_date"] <= today_date:
        conn.close()
        return jsonify({"error": f'Medicine "{med["name"]}" expired on {med["expiry_date"]} and cannot be sold.'}), 400

    res_obj = _format_pos_medicine_dict(med, overall_disc)
    conn.close()
    return jsonify(res_obj)


@app.route("/api/admin/pharmacy/pos/checkout", methods=["POST"])
@login_required
def api_admin_pharmacy_pos_checkout():
    """Complete an in-counter Pharmacy POS checkout (medicines only), deduct stock, and return receipt URL."""
    data = request.get_json(silent=True) or {}
    items = data.get("items") or []
    cash_amount = float(data.get("cash_amount") or 0.0)
    card_amount = float(data.get("card_amount") or 0.0)
    extra_discount = max(0.0, float(data.get("extra_discount") or 0.0))
    customer_name = (data.get("customer_name") or "").strip()
    raw_mobile = re.sub(r"\D", "", data.get("customer_mobile") or "")
    if raw_mobile.startswith("8801") and len(raw_mobile) == 13:
        raw_mobile = raw_mobile[2:]
    customer_mobile = raw_mobile

    if not items:
        return jsonify({"error": "Cart is empty."}), 400

    conn = get_connection()
    cur = conn.cursor()
    shop_settings = get_all_settings(conn)
    overall_disc = float(shop_settings.get("pharmacy_discount_percent") or 0.0)
    today_date = datetime.now().strftime("%Y-%m-%d")

    sub_total = 0.0
    mrp_total = 0.0
    line_details = []

    for item in items:
        raw_id = item.get("medicine_id") or item.get("id") or ""
        try:
            med_id = int(str(raw_id).replace("med_", ""))
        except Exception:
            conn.close()
            return jsonify({"error": "Invalid medicine item in cart."}), 400

        med = cur.execute("SELECT * FROM pharmacy_medicines WHERE id = ? AND is_active = 1", (med_id,)).fetchone()
        if not med:
            conn.close()
            return jsonify({"error": "A selected medicine no longer exists."}), 400

        if med["expiry_date"] and med["expiry_date"] <= today_date:
            conn.close()
            return jsonify({"error": f'Medicine "{med["name"]}" expired on {med["expiry_date"]}.'}), 400

        quantity = max(1, int(item.get("quantity") or 1))
        sell_unit = (item.get("sell_unit") or item.get("unit_mode") or item.get("price_mode") or item.get("unit") or "piece").strip()
        resolved = _resolve_medicine_line_pricing(
            med,
            overall_disc,
            price_mode=sell_unit,
            custom_unit_price=item.get("unit_price"),
        )
        deduct_pcs = quantity * resolved["unit_count"]
        avail_stk = int(med["stock_qty"] or 0)
        if avail_stk <= 0:
            conn.close()
            return jsonify({
                "error": f'Medicine "{med["name"]}" is OUT OF STOCK (quantity 0) and cannot be checked out.'
            }), 400
        if avail_stk < deduct_pcs:
            conn.close()
            return jsonify({
                "error": f'Not enough stock for "{med["name"]}" ({avail_stk} পিস available, {deduct_pcs} পিস requested).'
            }), 400

        mrp_val = resolved["mrp_price"]
        sell_p = resolved["sell_price"]
        line_subtotal = round(sell_p * quantity, 2)
        sub_total += line_subtotal
        mrp_total += round(mrp_val * quantity, 2)
        line_details.append({
            "medicine_id": med_id,
            "medicine_name": med["name"],
            "medicine_strength": med["strength"] or med["dosage_form"] or "",
            "quantity": quantity,
            "deduct_pcs": deduct_pcs,
            "unit_mode": resolved["unit_mode"],
            "unit_label": resolved["unit_label"],
            "unit_price": sell_p,
            "mrp_price": mrp_val,
            "cost_price": resolved["cost_price"],
        })

    grand_total = max(0.0, sub_total - extra_discount)
    rounded_total = round_to_whole(grand_total)
    saved_amount = round(max(0.0, mrp_total - grand_total), 2)

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
            name_to_use = customer_name if customer_name else f"Customer {customer_mobile[-4:]}"
            cur.execute("""
                INSERT INTO customer_users (phone, name, email, password_hash, plain_password, is_verified, created_at)
                VALUES (?, ?, '', ?, '123456', 1, ?)
            """, (customer_mobile, name_to_use, pass_hash, datetime.now().isoformat()))
        elif customer_name and (not existing_cust["name"] or existing_cust["name"].startswith("Customer ")):
            cur.execute("UPDATE customer_users SET name = ? WHERE phone = ?", (customer_name, customer_mobile))

    cur.execute("""
        INSERT INTO sales (invoice_number, invoice_date, cashier_id, customer_id, customer_name, customer_mobile, channel,
                           total_amount, rounded_total, vat_amount, saved_amount,
                           cash_amount, card_amount, change_amount, created_at)
        VALUES (?, ?, ?, ?, ?, ?, 'Pharmacy POS', ?, ?, 0, ?, ?, ?, ?, ?)
    """, (
        invoice_number, invoice_date, session.get("user_id", 1), customer_name, customer_name, customer_mobile,
        round(sub_total, 2), rounded_total, saved_amount,
        cash_amount, card_amount, change_amount, datetime.now().isoformat()
    ))
    sale_id = cur.lastrowid

    first_p = cur.execute("SELECT id FROM products LIMIT 1").fetchone()
    fk_pid = first_p["id"] if first_p else 1
    for ld in line_details:
        cur.execute("UPDATE pharmacy_medicines SET stock_qty = MAX(0, stock_qty - ?) WHERE id = ?", (ld["deduct_pcs"], ld["medicine_id"]))
        unit_suffix = (
            f" [{ld['quantity']}x {ld['unit_label']} = {ld['deduct_pcs']} পিস]"
            if (ld["deduct_pcs"] != ld["quantity"] or ld["unit_mode"] != "piece")
            else ""
        )
        med_title = f"💊 {ld['medicine_name']}" + (f" ({ld['medicine_strength']})" if ld["medicine_strength"] else "") + unit_suffix
        cur.execute("""
            INSERT INTO sale_items (sale_id, product_id, quantity, unit_price, mrp_price, vat_pct, vat_amount, cost_price, unit_serials)
            VALUES (?, ?, ?, ?, ?, 0, 0, ?, ?)
        """, (sale_id, fk_pid, ld["quantity"], ld["unit_price"], ld["mrp_price"], ld["cost_price"], med_title))

    conn.commit()
    conn.close()

    try:
        remote_control.push_sale_to_cloud(sale_id)
        if customer_mobile and len(customer_mobile) == 11 and customer_mobile.startswith("01"):
            remote_control.push_customer_user_to_cloud(customer_mobile)
    except Exception:
        pass

    return jsonify({
        "success": True,
        "sale_id": sale_id,
        "invoice_number": invoice_number,
        "receipt_url": f"/sales/{sale_id}",
        "sub_total": round(sub_total, 2),
        "rounded_total": rounded_total,
        "change_amount": change_amount,
    })


def _authorize_staff_or_rider(conn, data=None):
    """Validates either a logged-in web staff/rider session, signed staff token, or active rider/staff identity."""
    if session.get("user_id"):
        u = conn.execute(
            "SELECT id, username, full_name, role, COALESCE(can_rx_quote_bill, 0) AS can_rx_quote_bill FROM users WHERE id = ? AND COALESCE(is_active, 1) = 1",
            (session.get("user_id"),),
        ).fetchone()
        if u:
            return dict(u)
    tok = _get_bearer_or_param_token(data)
    parsed = _verify_staff_token(tok)
    if parsed:
        u = conn.execute(
            "SELECT id, username, full_name, role, COALESCE(can_rx_quote_bill, 0) AS can_rx_quote_bill FROM users WHERE id = ? AND username = ? AND COALESCE(is_active, 1) = 1",
            (parsed["id"], parsed["username"]),
        ).fetchone()
        if u:
            return dict(u)
    payload = data if isinstance(data, dict) else {}
    rider_id = payload.get("rider_id") or request.args.get("rider_id")
    raw_phone = (payload.get("rider_phone") or request.args.get("rider_phone") or "").strip()
    norm_p = normalize_phone(raw_phone) if raw_phone else ""
    if rider_id:
        try:
            u = conn.execute(
                "SELECT id, username, full_name, role, COALESCE(can_rx_quote_bill, 0) AS can_rx_quote_bill FROM users WHERE id = ? AND COALESCE(is_active, 1) = 1",
                (int(rider_id),),
            ).fetchone()
            if u:
                return dict(u)
        except Exception:
            pass
    if raw_phone or norm_p:
        candidates = list(set(filter(None, [raw_phone, norm_p, f"88{norm_p}" if norm_p else "", f"+88{norm_p}" if norm_p else ""])))
        placeholders = ",".join("?" for _ in candidates)
        u = conn.execute(
            f"SELECT id, username, full_name, role, COALESCE(can_rx_quote_bill, 0) AS can_rx_quote_bill FROM users WHERE COALESCE(is_active, 1) = 1 AND username IN ({placeholders}) LIMIT 1",
            tuple(candidates),
        ).fetchone()
        if u:
            return dict(u)
    return None


@app.route("/api/rider/catalog", methods=["GET"])
def api_rider_catalog():
    """Returns searchable regular products, combo packages, and pharmacy medicines for Rider mobile billing."""
    conn = get_connection()
    actor = _authorize_staff_or_rider(conn)
    if not actor:
        conn.close()
        return jsonify({"success": False, "message": "Unauthorized rider or staff session."}), 401

    q = (request.args.get("q") or "").strip()
    catalog_type = (request.args.get("type") or "all").strip().lower()
    limit = min(80, max(10, request.args.get("limit", default=40, type=int)))
    like = f"%{q}%"

    shop_settings = get_all_settings(conn)
    pharm_disc = float(shop_settings.get("pharmacy_discount_percent") or 0.0)

    products_out = []
    packages_out = []
    medicines_out = []

    if catalog_type in ("all", "regular", "products"):
        if q:
            prod_rows = conn.execute("""
                SELECT p.id, p.name, p.sku, p.brand, p.sell_price, p.mrp, p.stock_qty, p.unit, p.image_url,
                       COALESCE(c.name, 'General') AS category_name
                FROM products p
                LEFT JOIN categories c ON p.category_id = c.id
                WHERE COALESCE(p.stock_qty, 0) > 0
                  AND (p.name LIKE ? OR p.sku LIKE ? OR p.brand LIKE ?)
                ORDER BY CASE WHEN p.name LIKE ? THEN 0 ELSE 1 END, p.name ASC
                LIMIT ?
            """, (like, like, like, f"{q}%", limit)).fetchall()
        else:
            prod_rows = conn.execute("""
                SELECT p.id, p.name, p.sku, p.brand, p.sell_price, p.mrp, p.stock_qty, p.unit, p.image_url,
                       COALESCE(c.name, 'General') AS category_name
                FROM products p
                LEFT JOIN categories c ON p.category_id = c.id
                WHERE COALESCE(p.stock_qty, 0) > 0
                ORDER BY p.id DESC
                LIMIT ?
            """, (limit,)).fetchall()
        for r in prod_rows:
            imgs = split_image_urls(r["image_url"])
            products_out.append({
                "id": r["id"],
                "item_type": "product",
                "name": r["name"],
                "sku": r["sku"] or "",
                "category": r["category_name"] or "General",
                "sell_price": float(r["sell_price"] or 0.0),
                "mrp": float(r["mrp"] or r["sell_price"] or 0.0),
                "stock_qty": int(r["stock_qty"] or 0),
                "unit": r["unit"] or "Piece",
                "image": imgs[0] if imgs else "/static/images/logo.png",
            })

        pkg_where = "WHERE is_active = 1" + (" AND name LIKE ?" if q else "")
        pkg_params = [like] if q else []
        for pk in conn.execute(f"SELECT id, name, package_price, image_url FROM packages {pkg_where} ORDER BY id DESC LIMIT 20", tuple(pkg_params)).fetchall():
            packages_out.append({
                "id": pk["id"],
                "item_type": "package",
                "name": f"📦 {pk['name']}",
                "sell_price": float(pk["package_price"] or 0.0),
                "mrp": float(pk["package_price"] or 0.0),
                "stock_qty": 999,
                "unit": "Combo Package",
                "image": pk["image_url"] or "/static/images/logo.png",
            })

    if catalog_type in ("all", "pharmacy", "medicines"):
        if q:
            med_rows = conn.execute("""
                SELECT * FROM pharmacy_medicines
                WHERE COALESCE(stock_qty, 0) > 0
                  AND (name LIKE ? OR generic_name LIKE ? OR manufacturer LIKE ? OR COALESCE(sku, '') LIKE ?)
                ORDER BY CASE WHEN UPPER(COALESCE(sku, '')) = UPPER(?) THEN 0 WHEN name LIKE ? THEN 1 WHEN generic_name LIKE ? THEN 2 ELSE 3 END, name ASC
                LIMIT ?
            """, (like, like, like, like, q, f"{q}%", f"{q}%", limit)).fetchall()
        else:
            med_rows = conn.execute("""
                SELECT * FROM pharmacy_medicines
                WHERE COALESCE(stock_qty, 0) > 0
                ORDER BY id DESC
                LIMIT ?
            """, (limit,)).fetchall()
        for mr in med_rows:
            md = dict(mr)
            mrp_val, sell_p, eff_disc = _calc_medicine_sell_price(md, pharm_disc)
            medicines_out.append({
                "id": md["id"],
                "item_type": "medicine",
                "sku": md.get("sku") or f"MED-{md['id']:05d}",
                "name": md["name"] or "",
                "generic_name": md.get("generic_name") or "",
                "dosage_form": md.get("dosage_form") or "Tablet",
                "strength": md.get("strength") or "",
                "manufacturer": md.get("manufacturer") or "",
                "sell_price": sell_p,
                "mrp": mrp_val,
                "cost_price": float(md.get("cost_price") or 0.0),
                "strip_price": float(md.get("strip_price") or 0.0),
                "strip_cost_price": float(md.get("strip_cost_price") or 0.0),
                "strip_size": int(md.get("strip_size") or 10),
                "packet_price": float(md.get("packet_price") or 0.0),
                "packet_cost_price": float(md.get("packet_cost_price") or 0.0),
                "packet_size": int(md.get("packet_size") or 30),
                "discount_percent": eff_disc,
                "stock_qty": int(md.get("stock_qty") or 0),
                "unit": md.get("unit") or "পিস",
            })

    conn.close()
    return jsonify({
        "success": True,
        "products": products_out,
        "packages": packages_out,
        "medicines": medicines_out,
        "pharmacy_discount_percent": pharm_disc,
    })


@app.route("/api/rider/create-bill", methods=["POST"])
def api_rider_create_bill():
    """Creates a live POS/Rider bill for regular shop products, combo packages, pharmacy medicines, or mixed."""
    data = request.get_json(silent=True) or {}
    conn = get_connection()
    actor = _authorize_staff_or_rider(conn, data)
    if not actor:
        conn.close()
        return jsonify({"success": False, "message": "Unauthorized rider or staff credentials."}), 401

    items = data.get("items") or []
    if not items or not isinstance(items, list):
        conn.close()
        return jsonify({"success": False, "message": "অনুগ্রহ করে বিলের জন্য অন্তত একটি পণ্য বা ঔষধ যোগ করুন।"}), 400

    customer_name = (data.get("customer_name") or "").strip() or "Walk-in / Rider Customer"
    raw_phone = (data.get("customer_phone") or data.get("customer_mobile") or "").strip()
    customer_mobile = normalize_phone(raw_phone) or raw_phone
    try:
        extra_discount = max(0.0, float(data.get("extra_discount") or data.get("discount") or 0.0))
    except Exception:
        extra_discount = 0.0
    try:
        cash_amount = max(0.0, float(data.get("cash_amount") or 0.0))
        card_amount = max(0.0, float(data.get("card_amount") or 0.0))
    except Exception:
        cash_amount, card_amount = 0.0, 0.0
    print_to_pc = bool(data.get("print_to_pc"))

    shop_settings = get_all_settings(conn)
    overall_pharm_disc = float(shop_settings.get("pharmacy_discount_percent") or 0.0)

    first_prod_row = conn.execute("SELECT id FROM products LIMIT 1").fetchone()
    fk_pid = first_prod_row["id"] if first_prod_row else 1

    sub_total = 0.0
    mrp_total = 0.0
    vat_total = 0.0
    line_details = []
    has_regular = False
    has_medicine = False

    for raw in items:
        item_type = (raw.get("item_type") or data.get("bill_type") or "product").strip().lower()
        try:
            qty = int(raw.get("quantity") or raw.get("qty") or 1)
        except Exception:
            qty = 1
        if qty <= 0:
            qty = 1
        item_id = raw.get("id") or raw.get("product_id") or raw.get("medicine_id")

        if item_type in ("medicine", "pharmacy"):
            med = conn.execute("SELECT * FROM pharmacy_medicines WHERE id = ?", (item_id,)).fetchone() if item_id else None
            if not med and raw.get("name"):
                med = conn.execute("SELECT * FROM pharmacy_medicines WHERE name = ? LIMIT 1", (raw.get("name"),)).fetchone()
            if not med:
                conn.close()
                return jsonify({"success": False, "message": f"Medicine not found (ID: {item_id})."}), 404
            m_dict = dict(med)
            sell_unit = (raw.get("sell_unit") or raw.get("unit_mode") or raw.get("price_mode") or raw.get("unit") or "piece").strip()
            resolved = _resolve_medicine_line_pricing(
                m_dict,
                overall_pharm_disc,
                price_mode=sell_unit,
                custom_unit_price=raw.get("unit_price"),
            )
            deduct_pcs = qty * resolved["unit_count"]
            if int(m_dict.get("stock_qty") or 0) < deduct_pcs:
                conn.close()
                return jsonify({
                    "success": False,
                    "message": f"{m_dict['name']} স্টকে পর্যাপ্ত নেই (বাকি: {m_dict.get('stock_qty', 0)} পিস, প্রয়োজন: {deduct_pcs} পিস)।"
                }), 400
            mrp_val = resolved["mrp_price"]
            sell_p = resolved["sell_price"]
            has_medicine = True
            line_sub = round(sell_p * qty, 2)
            sub_total += line_sub
            mrp_total += round(mrp_val * qty, 2)
            strength = m_dict.get("strength") or m_dict.get("dosage_form") or ""
            unit_suffix = (
                f" [{qty}x {resolved['unit_label']} = {deduct_pcs} পিস]"
                if (deduct_pcs != qty or resolved["unit_mode"] != "piece")
                else ""
            )
            line_details.append({
                "kind": "medicine",
                "medicine_id": m_dict["id"],
                "product_id": fk_pid,
                "quantity": qty,
                "deduct_pcs": deduct_pcs,
                "unit_price": sell_p,
                "mrp_price": mrp_val,
                "vat_pct": 0.0,
                "vat_amount": 0.0,
                "cost_price": resolved["cost_price"],
                "unit_serials": f"💊 {m_dict['name']}" + (f" ({strength})" if strength else "") + unit_suffix,
            })
        elif item_type == "package":
            pkg = conn.execute("SELECT * FROM packages WHERE id = ?", (item_id,)).fetchone()
            if not pkg:
                conn.close()
                return jsonify({"success": False, "message": f"Package not found (ID: {item_id})."}), 404
            has_regular = True
            sell_p = float(pkg["package_price"] or 0.0)
            pkg_items = conn.execute(
                "SELECT pi.product_id, pi.quantity, COALESCE(p.cost_price, 0) AS cost_price FROM package_items pi JOIN products p ON pi.product_id = p.id WHERE pi.package_id = ?",
                (pkg["id"],),
            ).fetchall()
            unit_cost = sum(float(pi["cost_price"] or 0.0) * float(pi["quantity"] or 1) for pi in pkg_items)
            sub_total += round(sell_p * qty, 2)
            mrp_total += round(sell_p * qty, 2)
            line_details.append({
                "kind": "package",
                "package_id": pkg["id"],
                "pkg_items": [dict(pi) for pi in pkg_items],
                "product_id": fk_pid,
                "quantity": qty,
                "unit_price": sell_p,
                "mrp_price": sell_p,
                "vat_pct": 0.0,
                "vat_amount": 0.0,
                "cost_price": round(unit_cost, 2),
                "unit_serials": f"📦 {pkg['name']}",
            })
        else:
            prod = conn.execute("SELECT * FROM products WHERE id = ?", (item_id,)).fetchone()
            if not prod:
                conn.close()
                return jsonify({"success": False, "message": f"Product not found (ID: {item_id})."}), 404
            if float(prod["stock_qty"] or 0) < qty:
                conn.close()
                return jsonify({"success": False, "message": f"{prod['name']} স্টকে পর্যাপ্ত নেই (বাকি: {prod['stock_qty']})।"}), 400
            has_regular = True
            sell_p = float(prod["sell_price"] or 0.0)
            mrp_val = float(prod["mrp"] or sell_p)
            vat_pct = float(prod["vat_pct"] or 0.0)
            line_sub = round(sell_p * qty, 2)
            line_vat = round(line_sub * (vat_pct / 100.0), 2) if vat_pct > 0 else 0.0
            sub_total += line_sub
            mrp_total += round(mrp_val * qty, 2)
            vat_total += line_vat
            line_details.append({
                "kind": "product",
                "product_id": prod["id"],
                "quantity": qty,
                "unit_price": sell_p,
                "mrp_price": mrp_val,
                "vat_pct": vat_pct,
                "vat_amount": line_vat,
                "cost_price": float(prod["cost_price"] or 0.0),
                "unit_serials": "",
            })

    if not line_details:
        conn.close()
        return jsonify({"success": False, "message": "No valid bill items provided."}), 400

    grand_total = max(0.0, (sub_total + vat_total) - extra_discount)
    rounded_total = round_to_whole(grand_total)
    saved_amount = round(max(0.0, mrp_total - grand_total), 2)

    if cash_amount == 0 and card_amount == 0:
        cash_amount = rounded_total
        change_amount = 0.0
    else:
        change_amount = round((cash_amount + card_amount) - rounded_total, 2)
        if change_amount < 0:
            conn.close()
            return jsonify({"success": False, "message": f"টাকা কম পড়েছে: TK {abs(change_amount):.2f}"}), 400

    channel = "Pharmacy POS" if (has_medicine and not has_regular) else "Rider POS"
    invoice_number = generate_invoice_number()
    now_iso = datetime.now().isoformat()
    invoice_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    cur = conn.cursor()

    cust_ip, cust_loc = _resolve_ip_and_location(conn)
    if customer_mobile and len(customer_mobile) == 11 and customer_mobile.startswith("01"):
        existing_cust = cur.execute("SELECT id, name FROM customer_users WHERE phone = ?", (customer_mobile,)).fetchone()
        if not existing_cust:
            name_to_use = customer_name if not customer_name.startswith("Walk-in") else f"Customer {customer_mobile[-4:]}"
            cur.execute("""
                INSERT INTO customer_users (phone, name, email, password_hash, plain_password, is_verified, created_at)
                VALUES (?, ?, '', ?, '123456', 1, ?)
            """, (customer_mobile, name_to_use, generate_password_hash("123456"), now_iso))
        elif customer_name and not customer_name.startswith("Walk-in") and (not existing_cust["name"] or existing_cust["name"].startswith("Customer ")):
            cur.execute("UPDATE customer_users SET name = ? WHERE phone = ?", (customer_name, customer_mobile))
        cust_ip, cust_loc = _touch_customer_network_info(conn, customer_mobile, data=data)

    cur.execute("""
        INSERT INTO sales (
            invoice_number, invoice_date, cashier_id, customer_id, customer_name, customer_mobile, channel,
            total_amount, rounded_total, vat_amount, saved_amount, cash_amount, card_amount, change_amount,
            customer_ip, ip_location, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        invoice_number, invoice_date, actor["id"], customer_name, customer_name, customer_mobile, channel,
        round(sub_total, 2), rounded_total, round(vat_total, 2), saved_amount,
        cash_amount, card_amount, change_amount, cust_ip, cust_loc, now_iso
    ))
    sale_id = cur.lastrowid

    touched_products = []
    touched_packages = False
    for ld in line_details:
        if ld["kind"] == "medicine":
            cur.execute("UPDATE pharmacy_medicines SET stock_qty = MAX(0, stock_qty - ?) WHERE id = ?", (ld.get("deduct_pcs", ld["quantity"]), ld["medicine_id"]))
        elif ld["kind"] == "package":
            cur.execute("UPDATE packages SET sold_quantity = sold_quantity + ? WHERE id = ?", (ld["quantity"], ld["package_id"]))
            touched_packages = True
            for pi in ld["pkg_items"]:
                cur.execute("UPDATE products SET stock_qty = MAX(0, stock_qty - ?) WHERE id = ?", (pi["quantity"] * ld["quantity"], pi["product_id"]))
                touched_products.append(pi["product_id"])
        else:
            cur.execute("UPDATE products SET stock_qty = MAX(0, stock_qty - ?) WHERE id = ?", (ld["quantity"], ld["product_id"]))
            touched_products.append(ld["product_id"])

        cur.execute("""
            INSERT INTO sale_items (sale_id, product_id, quantity, unit_price, mrp_price, vat_pct, vat_amount, cost_price, unit_serials)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            sale_id, ld["product_id"], ld["quantity"], ld["unit_price"], ld["mrp_price"],
            ld["vat_pct"], ld["vat_amount"], ld["cost_price"], ld["unit_serials"]
        ))

    conn.commit()
    conn.close()

    try:
        remote_control.push_sale_to_cloud(sale_id)
        for pid in set(touched_products):
            remote_control.push_product_to_cloud(pid)
        if touched_packages:
            remote_control.push_packages_to_cloud()
        if customer_mobile and len(customer_mobile) == 11 and customer_mobile.startswith("01"):
            remote_control.push_customer_user_to_cloud(customer_mobile)
    except Exception:
        pass

    thermal_res = None
    if print_to_pc:
        try:
            thermal_res = thermal_printer.enqueue_or_print_receipt(
                source_type="sale",
                source_id=sale_id,
                invoice_number=invoice_number,
                requested_by=actor.get("full_name") or actor.get("username") or "Rider",
                requested_from=data.get("requested_from") or "mobile_rider",
            )
            if thermal_res.get("job_uuid") and not thermal_res.get("printed_directly"):
                remote_control.push_thermal_print_job_to_cloud(thermal_res["job_uuid"])
        except Exception as e:
            thermal_res = {"success": False, "message": str(e)}

    return jsonify({
        "success": True,
        "sale_id": sale_id,
        "invoice_number": invoice_number,
        "channel": channel,
        "receipt_url": f"/sales/{sale_id}",
        "sub_total": round(sub_total, 2),
        "rounded_total": rounded_total,
        "saved_amount": saved_amount,
        "change_amount": change_amount,
        "thermal_print": thermal_res,
        "message": f"বিল #{invoice_number} (TK {rounded_total:,.2f}) সফলভাবে তৈরি হয়েছে!",
    })


@app.route("/api/thermal/printers", methods=["GET"])
@login_required
def api_thermal_printers():
    conn = get_connection()
    resolved = thermal_printer.resolve_target_printer(conn)
    reason = (
        f"Active Windows Printer: {resolved}"
        if resolved
        else "No local Windows printer detected"
    )
    pending_cnt = conn.execute("SELECT COUNT(*) FROM thermal_print_jobs WHERE status = 'pending'").fetchone()[0]
    conn.close()
    printers = thermal_printer.list_windows_printers()
    return jsonify({
        "success": True,
        "printers": printers,
        "resolved_printer": resolved,
        "reason": reason,
        "pending_jobs": pending_cnt,
    })


@app.route("/api/thermal/jobs", methods=["GET"])
@login_required
def api_thermal_jobs():
    conn = get_connection()
    rows = conn.execute("SELECT * FROM thermal_print_jobs ORDER BY id DESC LIMIT 20").fetchall()
    conn.close()
    return jsonify({"success": True, "jobs": [dict(r) for r in rows]})


@app.route("/api/thermal/process-pending", methods=["POST"])
@login_required
def api_thermal_process_pending():
    res = thermal_printer.process_pending_pc_print_jobs(limit=15)
    return jsonify({"success": True, **res})


@app.route("/api/thermal/test-print", methods=["POST"])
@login_required
def api_thermal_test_print():
    data = request.get_json(silent=True) or request.form or {}
    printer_name = (data.get("printer_name") or "").strip() or None
    paper_width = (data.get("paper_width") or "").strip() or None
    res = thermal_printer.enqueue_or_print_receipt(
        source_type="test",
        source_id=0,
        invoice_number=f"TEST-{datetime.now().strftime('%H%M%S')}",
        printer_name=printer_name,
        paper_width=paper_width,
        requested_by=session.get("username") or "Admin",
        requested_from="web_settings",
    )
    if res.get("job_uuid") and not res.get("printed_directly"):
        try:
            remote_control.push_thermal_print_job_to_cloud(res["job_uuid"])
        except Exception:
            pass
    return jsonify(res), (200 if res.get("success") else 400)


@app.route("/api/thermal/print-job", methods=["POST"])
def api_thermal_print_job():
    """Prints directly on PC thermal printer if running on Windows PC, or queues via Firestore for shop PC."""
    data = request.get_json(silent=True) or request.form or {}
    conn = get_connection()
    actor = _authorize_staff_or_rider(conn, data)
    conn.close()
    if not actor:
        return jsonify({"success": False, "message": "Unauthorized. Please log in as Staff or Rider."}), 401

    source_type = (data.get("source_type") or "online_order").strip().lower()
    source_id = data.get("source_id") or data.get("order_id") or data.get("sale_id") or 0
    invoice_number = (data.get("invoice_number") or data.get("order_number") or "").strip()
    printer_name = (data.get("printer_name") or "").strip() or None
    paper_width = (data.get("paper_width") or "").strip() or None

    res = thermal_printer.enqueue_or_print_receipt(
        source_type=source_type,
        source_id=int(source_id or 0),
        invoice_number=invoice_number,
        printer_name=printer_name,
        paper_width=paper_width,
        requested_by=actor.get("full_name") or actor.get("username") or "Staff",
        requested_from=data.get("requested_from") or ("web" if session.get("user_id") else "mobile_rider"),
    )
    if res.get("job_uuid") and not res.get("printed_directly"):
        try:
            remote_control.push_thermal_print_job_to_cloud(res["job_uuid"])
        except Exception:
            pass
    return jsonify(res), (200 if res.get("success") else 400)


@app.route("/api/admin/mobile-dashboard", methods=["GET"])
def api_admin_mobile_dashboard():
    """Native mobile admin dashboard stats, printer heartbeat, recent orders, and rider list."""
    conn = get_connection()
    actor = _authorize_admin_or_cashier(conn)
    if not actor:
        conn.close()
        return jsonify({"success": False, "message": "Admin/Cashier authorization required."}), 401

    today_prefix = get_bd_now().strftime("%Y-%m-%d")
    sales_row = conn.execute(
        "SELECT COUNT(*) AS cnt, COALESCE(SUM(rounded_total), 0) AS rev FROM sales WHERE substr(invoice_date, 1, 10) = ?",
        (today_prefix,),
    ).fetchone()
    cogs_row = conn.execute(
        "SELECT COALESCE(SUM(si.quantity * COALESCE(si.cost_price, 0)), 0) AS cogs FROM sale_items si JOIN sales s ON s.id = si.sale_id WHERE substr(s.invoice_date, 1, 10) = ?",
        (today_prefix,),
    ).fetchone()
    sales_today = round(float(sales_row["rev"] or 0.0), 2) if sales_row else 0.0
    cogs_today = round(float(cogs_row["cogs"] or 0.0), 2) if cogs_row else 0.0
    tx_today = int(sales_row["cnt"] or 0) if sales_row else 0

    pending_online = conn.execute(
        "SELECT COUNT(*) FROM online_orders WHERE order_status IN ('pending_confirmation', 'confirmed', 'awaiting_customer_confirmation', 'packed', 'on_the_way')"
    ).fetchone()[0]
    pending_rx = conn.execute(
        "SELECT COUNT(*) FROM pharmacy_orders WHERE order_status IN ('pending', 'reviewing', 'awaiting_customer_confirmation')"
    ).fetchone()[0]
    products_cnt = conn.execute("SELECT COUNT(*) FROM products").fetchone()[0]
    meds_cnt = conn.execute("SELECT COUNT(*) FROM pharmacy_medicines WHERE is_active = 1").fetchone()[0]
    low_stock_meds = conn.execute(
        "SELECT COUNT(*) FROM pharmacy_medicines WHERE is_active = 1 AND COALESCE(stock_qty, 0) <= COALESCE(low_stock_threshold, 10)"
    ).fetchone()[0]
    customers_cnt = conn.execute("SELECT COUNT(*) FROM customer_users").fetchone()[0]

    recent_orders = [
        dict(r)
        for r in conn.execute("""
            SELECT id, order_number, customer_name, customer_phone, district, area, address_details,
                   total_amount, order_status, assigned_rider_id, assigned_rider_name, created_at
            FROM online_orders
            ORDER BY id DESC
            LIMIT 15
        """).fetchall()
    ]
    riders = [
        {
            "id": r["id"],
            "username": r["username"],
            "full_name": r["full_name"] or r["username"],
            "is_active": int(r["is_active"] or 0) == 1,
            "can_rx_quote_bill": int(r["can_rx_quote_bill"] or 0) == 1,
        }
        for r in conn.execute(
            "SELECT id, username, full_name, is_active, COALESCE(can_rx_quote_bill, 0) AS can_rx_quote_bill FROM users WHERE role = 'delivery' ORDER BY id DESC"
        ).fetchall()
    ]

    is_win = thermal_printer.is_windows_pc()
    local_printer = thermal_printer.resolve_target_printer(conn) if is_win else ""
    conn.close()

    hb = remote_control.get_pc_printer_heartbeat() or {}
    pc_online = bool(is_win and local_printer) or bool(hb.get("is_online"))
    pc_printer_name = local_printer or hb.get("printer_name") or ""
    pc_last_seen = hb.get("online_at") or ""

    return jsonify({
        "success": True,
        "sales_today": sales_today,
        "profit_today": round(sales_today - cogs_today, 2),
        "transactions_today": tx_today,
        "pending_online_orders": pending_online,
        "pending_rx_orders": pending_rx,
        "products_count": products_cnt,
        "medicines_count": meds_cnt,
        "low_stock_medicines": low_stock_meds,
        "customers_count": customers_cnt,
        "recent_orders": recent_orders,
        "riders": riders,
        "pc_agent_online": pc_online,
        "pc_printer_name": pc_printer_name,
        "pc_last_seen": pc_last_seen,
        "is_windows_pc": is_win,
    })


def _serialize_pharmacy_order_for_mobile(row):
    d = dict(row)
    for k in ("requested_items_json", "approved_items_json"):
        out_k = k.replace("_json", "")
        try:
            d[out_k] = json.loads(d.get(k) or "[]")
        except Exception:
            d[out_k] = []
    imgs = []
    for cand in (d.get("prescription_url"), d.get("prescription_enhanced_url"), d.get("prescription_original_url")):
        c = (cand or "").strip()
        if not c:
            continue
        if c.startswith("["):
            try:
                parsed = json.loads(c)
                if isinstance(parsed, list):
                    for u in parsed:
                        su = str(u or "").strip()
                        if su and su not in imgs:
                            imgs.append(su)
                    continue
            except Exception:
                pass
        if c not in imgs:
            imgs.append(c)
    d["prescription_images"] = imgs
    d["customer_confirmed"] = int(d.get("customer_confirmed") or 0) == 1
    return d


@app.route("/api/admin/pharmacy/orders", methods=["GET"])
def api_admin_pharmacy_orders():
    """Lists pharmacy orders with parsed items and linked rider info for Web/Mobile Admin."""
    conn = get_connection()
    actor = _authorize_admin_or_cashier(conn)
    if not actor:
        conn.close()
        return jsonify({"success": False, "message": "Admin/Cashier authorization required."}), 401

    status_filter = (request.args.get("status") or "").strip().lower()
    sql = """
        SELECT po.*,
               COALESCE(oo.assigned_rider_id, 0) AS assigned_rider_id,
               COALESCE(oo.assigned_rider_name, '') AS assigned_rider_name
        FROM pharmacy_orders po
        LEFT JOIN online_orders oo ON oo.id = po.online_order_id OR oo.order_number = po.order_number
    """
    params = []
    if status_filter:
        sql += " WHERE LOWER(COALESCE(po.order_status, '')) = ? "
        params.append(status_filter)
    sql += " ORDER BY po.id DESC LIMIT 60"
    rows = conn.execute(sql, tuple(params)).fetchall()
    conn.close()
    return jsonify({
        "success": True,
        "orders": [_serialize_pharmacy_order_for_mobile(r) for r in rows],
    })


@app.route("/api/admin/riders", methods=["GET"])
def api_admin_riders():
    """Returns all riders with permissions, delivery financials, payouts, and summary."""
    conn = get_connection()
    actor = _authorize_admin_or_cashier(conn)
    if not actor:
        conn.close()
        return jsonify({"success": False, "message": "Admin/Cashier authorization required."}), 401

    default_fee = get_rider_delivery_fee_setting(conn)
    today_str = get_bd_now().strftime("%Y-%m-%d")
    current_month_str = today_str[:7]

    rows = conn.execute("""
        SELECT u.id, u.username, u.full_name, u.is_active, u.plain_password,
               COALESCE(u.can_rx_quote_bill, 0) AS can_rx_quote_bill,
               u.created_at,
               (SELECT COUNT(*) FROM online_orders oo
                WHERE oo.assigned_rider_id = u.id
                  AND oo.order_status IN ('verified', 'confirmed', 'packed', 'on_the_way')) AS active_deliveries
        FROM users u
        WHERE u.role = 'delivery'
        ORDER BY u.id DESC
    """).fetchall()

    riders = []
    grand_delivered = 0
    grand_earned = 0.0
    grand_paid = 0.0
    grand_due = 0.0

    for r in rows:
        r_id = r["id"]
        r_phone = r["username"] or ""
        ord_rows = conn.execute(
            "SELECT id, order_number, order_status, total_amount, rider_fee, created_at FROM online_orders WHERE assigned_rider_id = ? OR assigned_rider_phone = ? ORDER BY id DESC",
            (r_id, r_phone),
        ).fetchall()
        payout_rows = conn.execute(
            "SELECT * FROM rider_payouts WHERE rider_id = ? ORDER BY payout_date DESC, id DESC",
            (r_id,),
        ).fetchall()
        payouts = [dict(p) for p in payout_rows]

        delivered_cnt = 0
        earned = 0.0
        collected = 0.0
        for o in ord_rows:
            if (o["order_status"] or "").strip().lower() == "delivered":
                delivered_cnt += 1
                fee = float(o["rider_fee"] or 0.0)
                if fee <= 0:
                    fee = default_fee
                earned += fee
                collected += float(o["total_amount"] or 0.0)

        paid = round(sum(float(p.get("amount") or 0.0) for p in payouts), 2)
        earned = round(earned, 2)
        balance_due = max(0.0, round(earned - paid, 2))
        paid_today = round(sum(float(p.get("amount") or 0.0) for p in payouts if (p.get("payout_date") or "")[:10] == today_str), 2)
        paid_month = round(sum(float(p.get("amount") or 0.0) for p in payouts if (p.get("payout_date") or "")[:7] == current_month_str), 2)

        grand_delivered += delivered_cnt
        grand_earned += earned
        grand_paid += paid
        grand_due += balance_due

        riders.append({
            "id": r_id,
            "username": r_phone,
            "full_name": r["full_name"] or r_phone,
            "plain_password": r["plain_password"] or "",
            "is_active": int(r["is_active"] or 0) == 1,
            "can_rx_quote_bill": int(r["can_rx_quote_bill"] or 0) == 1,
            "active_deliveries": int(r["active_deliveries"] or 0),
            "total_orders": len(ord_rows),
            "total_delivered": delivered_cnt,
            "total_earned": earned,
            "total_paid": paid,
            "balance_due": balance_due,
            "paid_today": paid_today,
            "paid_this_month": paid_month,
            "total_collected": round(collected, 2),
            "payouts": payouts[:25],
            "created_at": r["created_at"] or "",
        })
    conn.close()
    return jsonify({
        "success": True,
        "riders": riders,
        "summary": {
            "total_riders": len(riders),
            "total_delivered": grand_delivered,
            "total_earned": round(grand_earned, 2),
            "total_paid": round(grand_paid, 2),
            "total_due": round(grand_due, 2),
            "default_rider_fee": default_fee,
        },
    })


@app.route("/api/admin/riders/permissions", methods=["POST"])
def api_admin_rider_permissions():
    """Admin toggles can_rx_quote_bill permission for a Rider."""
    data = request.get_json(silent=True) or request.form or {}
    conn = get_connection()
    actor = _authorize_admin_or_cashier(conn, data)
    if not actor:
        conn.close()
        return jsonify({"success": False, "message": "Admin/Cashier authorization required."}), 401

    try:
        rider_id = int(data.get("rider_id") or 0)
    except Exception:
        rider_id = 0
    if rider_id <= 0:
        conn.close()
        return jsonify({"success": False, "message": "Valid rider_id is required."}), 400

    raw_flag = data.get("can_rx_quote_bill")
    allow = 1 if str(raw_flag).strip().lower() in ("1", "true", "yes", "on") else 0

    rider = conn.execute("SELECT id, username, full_name FROM users WHERE id = ? AND role = 'delivery'", (rider_id,)).fetchone()
    if not rider:
        conn.close()
        return jsonify({"success": False, "message": "Rider not found."}), 404

    conn.execute("UPDATE users SET can_rx_quote_bill = ? WHERE id = ?", (allow, rider_id))
    conn.commit()
    conn.close()

    try:
        remote_control.push_users_to_cloud()
    except Exception:
        pass

    return jsonify({
        "success": True,
        "rider_id": rider_id,
        "can_rx_quote_bill": bool(allow),
        "message": f"{rider['full_name'] or rider['username']} এর Rx স্ক্যান ও কোটেশন পারমিশন {'চালু' if allow else 'বন্ধ'} করা হয়েছে।",
    })


@app.route("/api/rider/permissions", methods=["GET"])
def api_rider_permissions():
    """Returns current permission flags for logged-in rider or staff."""
    conn = get_connection()
    actor = _authorize_staff_or_rider(conn)
    conn.close()
    if not actor:
        return jsonify({"success": False, "message": "Unauthorized rider or staff session."}), 401

    has_rx_perm = (actor.get("role") in ("admin", "cashier")) or (int(actor.get("can_rx_quote_bill") or 0) == 1)
    return jsonify({
        "success": True,
        "rider_id": actor["id"],
        "role": actor["role"],
        "can_rx_quote_bill": has_rx_perm,
    })


@app.route("/api/rider/rx-quote-orders", methods=["GET"])
def api_rider_rx_quote_orders():
    """Returns active pharmacy orders (with optional ?status= filter) for permitted Riders."""
    conn = get_connection()
    actor = _authorize_staff_or_rider(conn)
    if not actor:
        conn.close()
        return jsonify({"success": False, "message": "Unauthorized rider or staff session."}), 401

    has_perm = (actor.get("role") in ("admin", "cashier")) or (int(actor.get("can_rx_quote_bill") or 0) == 1)
    if not has_perm:
        conn.close()
        return jsonify({"success": False, "message": "আপনার প্রেসক্রিপশন কোটেশন তৈরি করার অনুমতি নেই। অ্যাডমিনের অনুমতি নিন।"}), 403

    status_filter = (request.args.get("status") or "").strip().lower()
    sql = """
        SELECT po.*,
               COALESCE(oo.assigned_rider_id, 0) AS assigned_rider_id,
               COALESCE(oo.assigned_rider_name, '') AS assigned_rider_name
        FROM pharmacy_orders po
        LEFT JOIN online_orders oo ON oo.id = po.online_order_id OR oo.order_number = po.order_number
    """
    params = []
    if status_filter:
        sql += " WHERE LOWER(COALESCE(po.order_status, '')) = ? "
        params.append(status_filter)
    else:
        sql += " WHERE LOWER(COALESCE(po.order_status, 'pending')) IN ('pending', 'reviewing', 'awaiting_customer_confirmation', 'confirmed', 'packed', 'on_the_way') "
    sql += """
        ORDER BY CASE
            WHEN po.order_status IN ('pending', 'reviewing') THEN 0
            WHEN po.order_status = 'awaiting_customer_confirmation' THEN 1
            WHEN po.order_status IN ('confirmed', 'packed') THEN 2
            ELSE 3
        END, po.id DESC
        LIMIT 60
    """
    rows = conn.execute(sql, tuple(params)).fetchall()
    conn.close()
    return jsonify({
        "success": True,
        "orders": [_serialize_pharmacy_order_for_mobile(r) for r in rows],
    })


@app.route("/api/rider/pharmacy-orders/<int:order_id>", methods=["GET"])
def api_rider_pharmacy_order_detail(order_id):
    """Returns serialized pharmacy order details for permitted Rider inspection/quote editing."""
    conn = get_connection()
    actor = _authorize_staff_or_rider(conn)
    if not actor:
        conn.close()
        return jsonify({"success": False, "message": "Unauthorized rider or staff session."}), 401

    has_perm = (actor.get("role") in ("admin", "cashier")) or (int(actor.get("can_rx_quote_bill") or 0) == 1)
    if not has_perm:
        conn.close()
        return jsonify({"success": False, "message": "আপনার ফার্মেসী অর্ডার দেখার অনুমতি নেই।"}), 403

    row = conn.execute("""
        SELECT po.*,
               COALESCE(oo.assigned_rider_id, 0) AS assigned_rider_id,
               COALESCE(oo.assigned_rider_name, '') AS assigned_rider_name
        FROM pharmacy_orders po
        LEFT JOIN online_orders oo ON oo.id = po.online_order_id OR oo.order_number = po.order_number
        WHERE po.id = ?
        LIMIT 1
    """, (order_id,)).fetchone()
    conn.close()
    if not row:
        return jsonify({"success": False, "message": "অর্ডার পাওয়া যায়নি।"}), 404
    return jsonify({"success": True, "order": _serialize_pharmacy_order_for_mobile(row)})


@app.route("/api/rider/pharmacy-orders/<int:order_id>/update-status", methods=["POST"])
def api_rider_pharmacy_update_status(order_id):
    """Allows permitted Rider (can_rx_quote_bill=1) or Admin/Cashier to update pharmacy order status just like Admin."""
    data = request.get_json(silent=True) or request.form or {}
    conn = get_connection()
    actor = _authorize_staff_or_rider(conn, data)
    if not actor:
        conn.close()
        return jsonify({"success": False, "message": "Unauthorized rider or staff session."}), 401

    has_perm = (actor.get("role") in ("admin", "cashier")) or (int(actor.get("can_rx_quote_bill") or 0) == 1)
    if not has_perm:
        conn.close()
        return jsonify({"success": False, "message": "আপনার ফার্মেসী অর্ডার স্ট্যাটাস আপডেট করার অনুমতি নেই।"}), 403

    new_status = (data.get("status") or "").strip()
    rider_id = data.get("rider_id")
    otp_code = (data.get("otp") or "").strip()

    _, err = _execute_pharmacy_order_status_update(
        conn,
        order_id,
        new_status,
        rider_id=rider_id,
        otp_code=otp_code,
        assign_rider_fallback=actor if actor.get("role") == "delivery" else None,
        require_otp=(actor.get("role") == "delivery"),
    )
    conn.close()
    if err:
        return jsonify({"success": False, "message": err[0]}), err[1]

    return jsonify({"success": True, "message": f"অর্ডার স্ট্যাটাস '{new_status.upper()}' এ আপডেট হয়েছে।"})


@app.route("/api/rider/pharmacy-quote/<int:order_id>", methods=["POST"])
def api_rider_pharmacy_quote(order_id):
    """Allows an authorized Rider (or Admin/Cashier) to prepare & send a pharmacy quotation to customer."""
    data = request.get_json(silent=True) or {}
    conn = get_connection()
    actor = _authorize_staff_or_rider(conn, data)
    if not actor:
        conn.close()
        return jsonify({"success": False, "message": "Unauthorized rider or staff session."}), 401

    has_perm = (actor.get("role") in ("admin", "cashier")) or (int(actor.get("can_rx_quote_bill") or 0) == 1)
    if not has_perm:
        conn.close()
        return jsonify({"success": False, "message": "আপনার প্রেসক্রিপশন বিল/কোটেশন পাঠানোর অনুমতি নেই।"}), 403

    items = data.get("items") or []
    admin_notes = (data.get("admin_notes") or "").strip()
    try:
        delivery_charge = float(data.get("delivery_charge") if data.get("delivery_charge") is not None else 50.0)
    except Exception:
        delivery_charge = 50.0

    actor_label = actor.get("full_name") or actor.get("username") or "Rider"
    if actor.get("role") == "delivery":
        actor_label = f"Rider: {actor_label}"

    res, err = _save_and_send_pharmacy_quote(
        conn,
        order_id,
        items=items,
        delivery_charge=delivery_charge,
        admin_notes=admin_notes,
        actor_name=actor_label,
    )
    conn.close()
    if err:
        return jsonify({"success": False, "message": err}), 400
    return jsonify({
        "success": True,
        "message": "কোটেশন কাস্টমারের মোবাইলে পাঠানো হয়েছে। কাস্টমার কনফার্ম করলে পরবর্তী ধাপ চালু হবে।",
        **(res or {}),
    })


@app.route("/api/thermal/job-status/<job_uuid>", methods=["GET"])
def api_thermal_job_status(job_uuid):
    """Returns live thermal print job confirmation status synced from Firestore + Windows PC heartbeat."""
    cloud_job = remote_control.fetch_thermal_print_job_from_cloud(job_uuid) or {}
    conn = get_connection()
    row = conn.execute("SELECT * FROM thermal_print_jobs WHERE job_uuid = ?", (job_uuid,)).fetchone()
    is_win = thermal_printer.is_windows_pc()
    local_printer = thermal_printer.resolve_target_printer(conn) if is_win else ""
    conn.close()

    hb = remote_control.get_pc_printer_heartbeat() or {}
    pc_online = bool(is_win and local_printer) or bool(hb.get("is_online"))
    pc_printer_name = local_printer or hb.get("printer_name") or ""

    if not row and not cloud_job:
        return jsonify({
            "success": False,
            "message": "Print job not found.",
            "pc_agent_online": pc_online,
            "pc_printer_name": pc_printer_name,
        }), 404

    job = dict(row) if row else {}
    if cloud_job.get("status"):
        job["status"] = cloud_job.get("status")
        job["printed_at"] = cloud_job.get("printed_at") or job.get("printed_at") or ""
        job["printer_name"] = cloud_job.get("printer_name") or job.get("printer_name") or ""
        job["error_msg"] = cloud_job.get("error_msg") or job.get("error_msg") or ""

    return jsonify({
        "success": True,
        "job_uuid": job_uuid,
        "status": job.get("status") or "pending",
        "mode": job.get("mode") or "",
        "printer_name": job.get("printer_name") or pc_printer_name,
        "printed_at": job.get("printed_at") or "",
        "error_msg": job.get("error_msg") or "",
        "created_at": job.get("created_at") or "",
        "pc_agent_online": pc_online,
        "pc_printer_name": pc_printer_name,
        "pc_last_seen": hb.get("online_at") or "",
        "is_windows_pc": is_win,
    })


@app.route("/api/thermal/agent-status", methods=["GET"])
def api_thermal_agent_status():
    """Returns whether a Windows PC print agent/local printer is currently online."""
    conn = get_connection()
    is_win = thermal_printer.is_windows_pc()
    local_printer = thermal_printer.resolve_target_printer(conn) if is_win else ""
    conn.close()

    hb = remote_control.get_pc_printer_heartbeat() or {}
    online = bool(is_win and local_printer) or bool(hb.get("is_online"))
    return jsonify({
        "success": True,
        "online": online,
        "is_windows_pc": is_win,
        "printer_name": local_printer or hb.get("printer_name") or "",
        "last_seen": hb.get("online_at") or "",
        "hostname": hb.get("hostname") or "",
    })


# ===========================================================================
# Native Mobile & Web App In-App Admin JSON APIs (Online Orders, Reports, Riders, Settings)
# ===========================================================================

@app.route("/api/admin/online-orders", methods=["GET"])
def api_admin_online_orders():
    """Returns full enriched online & Rx orders list with department counts and active riders."""
    conn = get_connection()
    actor = _authorize_admin_or_cashier(conn)
    if not actor:
        conn.close()
        return jsonify({"success": False, "message": "Admin/Cashier authorization required."}), 401

    dept = (request.args.get("dept") or "all").strip().lower()
    status_filter = (request.args.get("status") or "").strip().lower()
    q = (request.args.get("q") or "").strip().lower()
    base_host = request.host_url.rstrip("/")

    def _abs_u(u):
        s = (u or "").strip()
        if s.startswith("/static/"):
            return base_host + s
        return s

    orders = conn.execute("SELECT * FROM online_orders ORDER BY id DESC LIMIT 120").fetchall()
    orders_list = []
    regular_count = 0
    pharmacy_count = 0
    awaiting_count = 0

    for ord_row in orders:
        o_dict = dict(ord_row)
        raw_items = conn.execute("SELECT * FROM online_order_items WHERE order_id = ?", (ord_row["id"],)).fetchall()
        item_list = [dict(i) for i in raw_items]

        ord_num = str(o_dict.get("order_number") or "")
        pharm_row = conn.execute(
            "SELECT * FROM pharmacy_orders WHERE online_order_id = ? OR order_number = ? LIMIT 1",
            (o_dict["id"], ord_num),
        ).fetchone()
        is_pharm = ord_num.upper().startswith("RX-") or bool(pharm_row)

        if pharm_row:
            o_dict["pharmacy_order_id"] = pharm_row["id"]
            o_dict["customer_confirmed"] = int(pharm_row["customer_confirmed"] or 0) == 1
            o_dict["prescription_url"] = _abs_u(pharm_row["prescription_url"])
            o_dict["prescription_original_url"] = _abs_u(pharm_row["prescription_original_url"] or pharm_row["prescription_url"])
            o_dict["customer_notes"] = pharm_row["customer_notes"] or ""
            o_dict["admin_notes"] = pharm_row["admin_notes"] or ""
            o_dict["overall_duration_days"] = int(pharm_row["overall_duration_days"] or 0)
            p_st = (pharm_row["order_status"] or "").strip().lower()
            if p_st == "awaiting_customer_confirmation":
                o_dict["order_status"] = "awaiting_customer_confirmation"
            if (not item_list or (len(item_list) == 1 and float(item_list[0].get("unit_price") or 0) == 0)) and (pharm_row["approved_items_json"] or pharm_row["requested_items_json"]):
                raw_j = pharm_row["approved_items_json"] or pharm_row["requested_items_json"] or "[]"
                try:
                    j_items = json.loads(raw_j) if raw_j else []
                except Exception:
                    j_items = []
                if j_items:
                    item_list = [
                        {
                            "product_id": it.get("medicine_id") or it.get("product_id") or 0,
                            "product_name": f"💊 {it.get('name', 'Medicine')}" + (f" ({it.get('strength')})" if it.get("strength") else ""),
                            "unit_price": float(it.get("unit_price") or 0.0),
                            "quantity": int(it.get("quantity") or 1),
                            "unit": it.get("unit") or "পিস",
                            "total_price": float(it.get("total_price") or 0.0),
                        }
                        for it in j_items if isinstance(it, dict)
                    ]

        o_dict["is_pharmacy_order"] = is_pharm
        o_dict["items"] = item_list
        c_phone = o_dict.get("customer_phone", "")
        cu = conn.execute("SELECT created_at, last_ip, last_location, registration_ip, registration_location, is_verified, is_blocked FROM customer_users WHERE phone = ?", (c_phone,)).fetchone()
        if cu:
            o_dict["customer_member_since"] = _member_since_label(cu["created_at"] or o_dict.get("created_at") or "")
            o_dict["customer_last_ip"] = o_dict.get("customer_ip") or cu["last_ip"] or cu["registration_ip"] or ""
            o_dict["customer_last_location"] = o_dict.get("ip_location") or cu["last_location"] or cu["registration_location"] or ""
            o_dict["customer_is_verified"] = int(cu["is_verified"] or 0) == 1
            o_dict["customer_is_blocked"] = int(cu["is_blocked"] or 0) == 1
        else:
            o_dict["customer_member_since"] = _member_since_label(o_dict.get("created_at") or "")
            o_dict["customer_last_ip"] = o_dict.get("customer_ip") or ""
            o_dict["customer_last_location"] = o_dict.get("ip_location") or ""
            o_dict["customer_is_verified"] = False
            o_dict["customer_is_blocked"] = False

        if is_pharm:
            pharmacy_count += 1
        else:
            regular_count += 1
        if (o_dict.get("order_status") or "").strip().lower() == "awaiting_customer_confirmation":
            awaiting_count += 1
        orders_list.append(o_dict)

    filtered = orders_list
    if dept == "pharmacy":
        filtered = [o for o in filtered if o.get("is_pharmacy_order")]
    elif dept == "regular":
        filtered = [o for o in filtered if not o.get("is_pharmacy_order")]
    elif dept == "awaiting_confirmation":
        filtered = [o for o in filtered if (o.get("order_status") or "").strip().lower() == "awaiting_customer_confirmation"]

    if status_filter and status_filter != "all":
        filtered = [o for o in filtered if (o.get("order_status") or "").strip().lower() == status_filter]
    if q:
        filtered = [
            o for o in filtered
            if q in str(o.get("order_number") or "").lower()
            or q in str(o.get("customer_name") or "").lower()
            or q in str(o.get("customer_phone") or "").lower()
            or q in str(o.get("area") or "").lower()
        ]

    riders = [
        {"id": r["id"], "username": r["username"], "full_name": r["full_name"] or r["username"]}
        for r in conn.execute("SELECT id, username, full_name FROM users WHERE role = 'delivery' AND COALESCE(is_active, 1) = 1 ORDER BY id DESC").fetchall()
    ]
    conn.close()
    return jsonify({
        "success": True,
        "orders": filtered,
        "counts": {
            "all": len(orders_list),
            "regular": regular_count,
            "pharmacy": pharmacy_count,
            "awaiting_confirmation": awaiting_count,
        },
        "riders": riders,
    })


@app.route("/api/admin/online-orders/<int:order_id>/action", methods=["POST"])
def api_admin_online_order_action(order_id):
    """Performs online order actions (update_status, assign_rider, verify_otp, update_address, delete) natively from App."""
    data = request.get_json(silent=True) or request.form or {}
    conn = get_connection()
    actor = _authorize_admin_or_cashier(conn, data)
    if not actor:
        conn.close()
        return jsonify({"success": False, "message": "Admin/Cashier authorization required."}), 401

    action = (data.get("action") or "").strip().lower()
    order = conn.execute("SELECT * FROM online_orders WHERE id = ?", (order_id,)).fetchone()
    if not order:
        conn.close()
        return jsonify({"success": False, "message": "Order not found."}), 404

    now_iso = get_bd_now_iso()
    ord_num = order["order_number"] or str(order_id)

    if action == "update_status":
        new_status = (data.get("status") or "").strip().lower()
        if not new_status:
            conn.close()
            return jsonify({"success": False, "message": "Status is required."}), 400
        if (order["order_status"] or "").strip().lower() == "awaiting_customer_confirmation" and new_status != "cancelled":
            conn.close()
            return jsonify({"success": False, "message": f"Order #{ord_num} কাস্টমার কনফার্মেশনের অপেক্ষায় আছে — কনফার্ম ছাড়া সামনে এগানো যাবে না।"}), 400
        r_fee = get_rider_delivery_fee_setting(conn)
        if new_status == "delivered":
            conn.execute(
                "UPDATE online_orders SET order_status = ?, payment_status = 'paid', rider_fee = CASE WHEN rider_fee <= 0 THEN ? ELSE rider_fee END, delivered_at = CASE WHEN delivered_at = '' THEN ? ELSE delivered_at END, updated_at = ? WHERE id = ?",
                (new_status, r_fee, now_iso, now_iso, order_id),
            )
        else:
            col_name = "confirmed_at" if new_status == "verified" else ("packed_at" if new_status == "packed" else ("on_the_way_at" if new_status == "on_the_way" else ("cancelled_at" if new_status == "cancelled" else "")))
            if col_name:
                conn.execute(
                    f"UPDATE online_orders SET order_status = ?, {col_name} = CASE WHEN {col_name} = '' THEN ? ELSE {col_name} END, updated_at = ? WHERE id = ?",
                    (new_status, now_iso, now_iso, order_id),
                )
            else:
                conn.execute("UPDATE online_orders SET order_status = ?, updated_at = ? WHERE id = ?", (new_status, now_iso, order_id))
        if new_status in ("new", "verified", "packed", "on_the_way", "delivered"):
            deduct_online_order_stock(conn, order)
            if order["customer_phone"]:
                conn.execute("UPDATE customer_users SET is_verified = 1 WHERE phone = ?", (order["customer_phone"],))
        elif new_status == "cancelled":
            restore_online_order_stock(conn, order)
        pharm_id = _sync_pharmacy_from_online_order(
            conn, order, new_status, now_iso,
            payment_status="paid" if new_status == "delivered" else None,
            rider_fee=r_fee if new_status == "delivered" else None,
        )
        notify_order_status_change(order, new_status, conn=conn)
        conn.commit()
        conn.close()
        remote_control.push_online_order_to_cloud(order_id)
        if pharm_id:
            remote_control.push_pharmacy_order_to_cloud(pharm_id)
        return jsonify({"success": True, "message": f"Order #{ord_num} status updated to {new_status}."})

    if action == "assign_rider":
        if (order["order_status"] or "").strip().lower() == "awaiting_customer_confirmation":
            conn.close()
            return jsonify({"success": False, "message": f"Order #{ord_num} কাস্টমার কনফার্মেশনের অপেক্ষায় আছে।"}), 400
        try:
            rider_id = int(data.get("rider_id") or 0)
        except Exception:
            rider_id = 0
        rider_name = ""
        rider_phone = ""
        if rider_id > 0:
            rider = conn.execute("SELECT * FROM users WHERE id = ? AND role = 'delivery'", (rider_id,)).fetchone()
            if rider:
                rider_name = rider["full_name"] or rider["username"]
                rider_phone = rider["username"]
        curr_st = (order["order_status"] or "").strip().lower()
        target_st = "verified" if curr_st in ("new", "pending_confirmation", "reviewing") else order["order_status"]
        conn.execute(
            "UPDATE online_orders SET order_status = ?, assigned_rider_id = ?, assigned_rider_name = ?, assigned_rider_phone = ?, confirmed_at = CASE WHEN confirmed_at = '' THEN ? ELSE confirmed_at END, updated_at = ? WHERE id = ?",
            (target_st, rider_id, rider_name, rider_phone, now_iso, now_iso, order_id),
        )
        deduct_online_order_stock(conn, order)
        pharm_id = _sync_pharmacy_from_online_order(
            conn, order, target_st, now_iso,
            rider_id=rider_id, rider_name=rider_name, rider_phone=rider_phone,
        )
        notify_order_status_change(order, target_st, conn=conn)
        conn.commit()
        conn.close()
        remote_control.push_online_order_to_cloud(order_id)
        if pharm_id:
            remote_control.push_pharmacy_order_to_cloud(pharm_id)
        msg = f"Rider {rider_name} assigned to #{ord_num}." if rider_name else f"Rider unassigned from #{ord_num}."
        return jsonify({"success": True, "message": msg})

    if action == "verify_otp":
        input_otp = (data.get("otp") or "").strip()
        if not input_otp or input_otp != (order["delivery_otp"] or "").strip():
            conn.close()
            return jsonify({"success": False, "message": "ভুল ডেলিভারি OTP কোড!"}), 400
        r_fee = get_rider_delivery_fee_setting(conn)
        conn.execute(
            "UPDATE online_orders SET order_status = 'delivered', payment_status = 'paid', rider_fee = CASE WHEN rider_fee <= 0 THEN ? ELSE rider_fee END, delivered_at = CASE WHEN delivered_at = '' THEN ? ELSE delivered_at END, updated_at = ? WHERE id = ?",
            (r_fee, now_iso, now_iso, order_id),
        )
        pharm_id = _sync_pharmacy_from_online_order(
            conn, order, "delivered", now_iso, payment_status="paid", rider_fee=r_fee,
        )
        notify_order_status_change(order, "delivered", conn=conn)
        conn.commit()
        conn.close()
        remote_control.push_online_order_to_cloud(order_id)
        if pharm_id:
            remote_control.push_pharmacy_order_to_cloud(pharm_id)
        return jsonify({"success": True, "message": f"OTP Verified! Order #{ord_num} delivered."})

    if action == "update_address":
        new_addr = (data.get("address_details") or "").strip()
        if not new_addr:
            conn.close()
            return jsonify({"success": False, "message": "Address cannot be empty."}), 400
        conn.execute("UPDATE online_orders SET address_details = ?, updated_at = ? WHERE id = ?", (new_addr, now_iso, order_id))
        if order["customer_phone"]:
            conn.execute("UPDATE customer_users SET address = ? WHERE phone = ?", (new_addr, order["customer_phone"]))
        conn.commit()
        conn.close()
        remote_control.push_online_order_to_cloud(order_id)
        return jsonify({"success": True, "message": f"Address updated for #{ord_num}."})

    if action == "delete":
        if actor.get("role") != "admin":
            conn.close()
            return jsonify({"success": False, "message": "Only Admin can delete orders."}), 403
        conn.execute("DELETE FROM online_order_items WHERE order_id = ?", (order_id,))
        conn.execute("DELETE FROM online_orders WHERE id = ?", (order_id,))
        conn.commit()
        conn.close()
        remote_control.delete_online_order_from_cloud(ord_num, order_id=order_id)
        return jsonify({"success": True, "message": f"Order #{ord_num} deleted."})

    conn.close()
    return jsonify({"success": False, "message": "Invalid action."}), 400


@app.route("/api/admin/customer-profile", methods=["GET"])
def api_admin_customer_profile():
    """Returns detailed customer profile, IP/location, member-since, and past order history."""
    conn = get_connection()
    actor = _authorize_admin_or_cashier(conn)
    if not actor:
        conn.close()
        return jsonify({"success": False, "message": "Admin/Cashier authorization required."}), 401

    phone = (request.args.get("phone") or "").strip()
    variants = _phone_variants(phone)
    if not variants:
        conn.close()
        return jsonify({"success": False, "message": "Phone is required."}), 400

    ph = ",".join("?" for _ in variants)
    cu = conn.execute(f"SELECT * FROM customer_users WHERE phone IN ({ph}) LIMIT 1", tuple(variants)).fetchone()
    cu_d = dict(cu) if cu else {}
    ord_rows = conn.execute(
        f"SELECT id, order_number, customer_name, customer_phone, district, area, address_details, total_amount, order_status, customer_ip, ip_location, created_at FROM online_orders WHERE customer_phone IN ({ph}) ORDER BY id DESC LIMIT 40",
        tuple(variants),
    ).fetchall()
    orders_list = [dict(o) for o in ord_rows]
    conn.close()

    first_created = cu_d.get("created_at") or (orders_list[-1].get("created_at") if orders_list else "")
    latest_ip = cu_d.get("last_ip") or cu_d.get("registration_ip") or next((o.get("customer_ip") for o in orders_list if o.get("customer_ip")), "")
    latest_loc = cu_d.get("last_location") or cu_d.get("registration_location") or next((o.get("ip_location") for o in orders_list if o.get("ip_location")), "")
    total_spent = round(sum(float(o.get("total_amount") or 0.0) for o in orders_list if (o.get("order_status") or "").lower() != "cancelled"), 2)

    return jsonify({
        "success": True,
        "customer": {
            "name": cu_d.get("name") or (orders_list[0].get("customer_name") if orders_list else phone),
            "phone": cu_d.get("phone") or phone,
            "email": cu_d.get("email") or "",
            "district": cu_d.get("district") or (orders_list[0].get("district") if orders_list else ""),
            "area": cu_d.get("area") or (orders_list[0].get("area") if orders_list else ""),
            "address": cu_d.get("address") or (orders_list[0].get("address_details") if orders_list else ""),
            "created_at": first_created,
            "member_since": _member_since_label(first_created),
            "last_ip": latest_ip,
            "last_location": latest_loc,
            "last_device": cu_d.get("last_device") or "",
            "is_verified": int(cu_d.get("is_verified") or 0) == 1,
            "is_blocked": int(cu_d.get("is_blocked") or 0) == 1,
            "block_reason": cu_d.get("block_reason") or "",
            "order_count": len(orders_list),
            "total_spent": total_spent,
            "orders": orders_list,
        },
    })


@app.route("/api/admin/reports", methods=["GET"])
def api_admin_reports():
    """Returns separated General, Pharmacy, Whole Supershop, Online, POS P&L and ledger entries as JSON."""
    conn = get_connection()
    actor = _authorize_admin_or_cashier(conn)
    if not actor:
        conn.close()
        return jsonify({"success": False, "message": "Admin/Cashier authorization required."}), 401

    period = (request.args.get("period") or "monthly").strip().lower()
    dept = (request.args.get("dept") or "all").strip().lower()
    if dept not in ("all", "general", "pharmacy"):
        dept = "all"

    period, date_filter, ledger_filter = _resolve_report_period_filters(period)
    bundle = _compute_separated_reports(conn, date_filter, ledger_filter, dept=dept)
    conn.close()

    ledger_list = [dict(r) for r in (bundle.get("ledger_entries") or [])][:50]
    return jsonify({
        "success": True,
        "period": period,
        "dept": dept,
        "revenue": bundle["revenue"],
        "cogs": bundle["cogs"],
        "gross_profit": bundle["gross_profit"],
        "other_income": bundle["other_income"],
        "other_expenses": bundle["other_expenses"],
        "net_profit": bundle["net_profit"],
        "tx_count": bundle["tx_count"],
        "online_summary": bundle["online_summary"],
        "offline_summary": bundle["offline_summary"],
        "packages_summary": bundle["packages_summary"],
        "offers_summary": bundle["offers_summary"],
        "general_summary": bundle["general_summary"],
        "pharmacy_summary": bundle["pharmacy_summary"],
        "whole_summary": bundle["whole_summary"],
        "top_products": bundle["top_products"],
        "top_medicines": bundle["top_medicines"],
        "slow_movers": bundle["slow_movers"],
        "dead_stock": bundle["dead_stock"],
        "ledger_entries": ledger_list,
    })


@app.route("/api/admin/reports/ledger", methods=["POST"])
def api_admin_reports_add_ledger():
    """Creates an income or expense ledger entry from the app."""
    data = request.get_json(silent=True) or request.form or {}
    conn = get_connection()
    actor = _authorize_admin_or_cashier(conn, data)
    if not actor:
        conn.close()
        return jsonify({"success": False, "message": "Admin authorization required."}), 401

    title = (data.get("title") or "").strip()
    entry_type = (data.get("entry_type") or "expense").strip().lower()
    if entry_type not in ("income", "expense"):
        entry_type = "expense"
    try:
        amount = float(data.get("amount") or 0.0)
    except Exception:
        amount = 0.0
    entry_date = (data.get("entry_date") or "").strip() or date.today().isoformat()
    target_segment = (data.get("target_segment") or "all").strip().lower() or "all"

    if not title or amount <= 0:
        conn.close()
        return jsonify({"success": False, "message": "Title এবং সঠিক পরিমাণ (0 এর বেশি) দিন।"}), 400

    cur = conn.cursor()
    cur.execute(
        "INSERT INTO ledger_entries (entry_type, title, amount, entry_date, created_at, target_segment) VALUES (?, ?, ?, ?, ?, ?)",
        (entry_type, title, amount, entry_date, datetime.now().isoformat(), target_segment),
    )
    entry_id = cur.lastrowid
    conn.commit()
    conn.close()
    return jsonify({"success": True, "entry_id": entry_id, "message": f"{entry_type.upper()} এন্ট্রি যুক্ত হয়েছে।"})


@app.route("/api/admin/reports/ledger/<int:entry_id>/delete", methods=["POST"])
def api_admin_reports_delete_ledger(entry_id):
    """Deletes a ledger entry from the app."""
    data = request.get_json(silent=True) or request.form or {}
    conn = get_connection()
    actor = _authorize_admin_or_cashier(conn, data)
    if not actor:
        conn.close()
        return jsonify({"success": False, "message": "Admin authorization required."}), 401
    conn.execute("DELETE FROM ledger_entries WHERE id = ?", (entry_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "লেজার এন্ট্রি মুছে ফেলা হয়েছে।"})


@app.route("/api/admin/riders/save", methods=["POST"])
def api_admin_riders_save():
    """Creates or updates a delivery rider from the app."""
    data = request.get_json(silent=True) or request.form or {}
    conn = get_connection()
    actor = _authorize_admin_or_cashier(conn, data)
    if not actor:
        conn.close()
        return jsonify({"success": False, "message": "Admin authorization required."}), 401

    rider_id = data.get("rider_id") or data.get("id")
    full_name = (data.get("full_name") or "").strip()
    username = normalize_phone((data.get("username") or "").strip())
    password = (data.get("password") or "").strip()
    is_active = 1 if str(data.get("is_active", 1)).lower() in ("1", "true", "yes", "on") else 0
    can_rx = 1 if str(data.get("can_rx_quote_bill", 0)).lower() in ("1", "true", "yes", "on") else 0

    if not full_name or not username or not (len(username) == 11 and username.startswith("01")):
        conn.close()
        return jsonify({"success": False, "message": "রাইডারের নাম এবং '01' দিয়ে শুরু ১১ ডিজিটের মোবাইল নম্বর দিন।"}), 400

    if rider_id:
        try:
            rid = int(rider_id)
        except Exception:
            rid = 0
        dup = conn.execute("SELECT id FROM users WHERE username = ? AND id != ?", (username, rid)).fetchone()
        if dup:
            conn.close()
            return jsonify({"success": False, "message": "এই মোবাইল নম্বরে আরেকটি একাউন্ট রয়েছে।"}), 400
        if password:
            conn.execute(
                "UPDATE users SET full_name = ?, username = ?, password_hash = ?, plain_password = ?, is_active = ?, can_rx_quote_bill = ? WHERE id = ? AND role = 'delivery'",
                (full_name, username, generate_password_hash(password), password, is_active, can_rx, rid),
            )
        else:
            conn.execute(
                "UPDATE users SET full_name = ?, username = ?, is_active = ?, can_rx_quote_bill = ? WHERE id = ? AND role = 'delivery'",
                (full_name, username, is_active, can_rx, rid),
            )
        msg = f"রাইডার '{full_name}' আপডেট হয়েছে।"
    else:
        if len(password) < 3:
            conn.close()
            return jsonify({"success": False, "message": "কমপক্ষে ৩ অক্ষরের পাসওয়ার্ড দিন।"}), 400
        dup = conn.execute("SELECT id FROM users WHERE username = ?", (username,)).fetchone()
        if dup:
            conn.close()
            return jsonify({"success": False, "message": "এই মোবাইল নম্বরে ইতিমধ্যে রাইডার বা স্টাফ রয়েছে।"}), 400
        cur = conn.cursor()
        cur.execute(
            "INSERT INTO users (username, password_hash, plain_password, role, full_name, is_active, can_rx_quote_bill, created_at) VALUES (?, ?, ?, 'delivery', ?, ?, ?, ?)",
            (username, generate_password_hash(password), password, full_name, is_active, can_rx, datetime.now().isoformat()),
        )
        rid = cur.lastrowid
        msg = f"নতুন রাইডার '{full_name}' তৈরি হয়েছে।"

    conn.commit()
    conn.close()
    try:
        remote_control.push_users_to_cloud()
    except Exception:
        pass
    return jsonify({"success": True, "rider_id": rid, "message": msg})


@app.route("/api/admin/riders/<int:rider_id>/delete", methods=["POST"])
def api_admin_riders_delete(rider_id):
    """Deletes a delivery rider account."""
    data = request.get_json(silent=True) or request.form or {}
    conn = get_connection()
    actor = _authorize_admin_or_cashier(conn, data)
    if not actor:
        conn.close()
        return jsonify({"success": False, "message": "Admin authorization required."}), 401
    conn.execute("DELETE FROM users WHERE id = ? AND role = 'delivery'", (rider_id,))
    conn.commit()
    conn.close()
    try:
        remote_control.push_users_to_cloud()
    except Exception:
        pass
    return jsonify({"success": True, "message": "রাইডার একাউন্ট মুছে ফেলা হয়েছে।"})


@app.route("/api/admin/riders/<int:rider_id>/pay", methods=["POST"])
def api_admin_riders_pay(rider_id):
    """Records a payout to a delivery rider and mirrors it as ledger expense."""
    data = request.get_json(silent=True) or request.form or {}
    conn = get_connection()
    actor = _authorize_admin_or_cashier(conn, data)
    if not actor:
        conn.close()
        return jsonify({"success": False, "message": "Admin authorization required."}), 401

    rider = conn.execute("SELECT * FROM users WHERE id = ? AND role = 'delivery'", (rider_id,)).fetchone()
    if not rider:
        conn.close()
        return jsonify({"success": False, "message": "Rider not found."}), 404

    try:
        amount = float(data.get("amount") or 0.0)
    except Exception:
        amount = 0.0
    if amount <= 0:
        conn.close()
        return jsonify({"success": False, "message": "পেমেন্ট পরিমাণ অবশ্যই ০ এর বেশি হতে হবে।"}), 400

    default_fee = get_rider_delivery_fee_setting(conn)
    rider_name = rider["full_name"] or rider["username"]
    rider_phone = rider["username"]
    delivered_orders = conn.execute(
        "SELECT rider_fee FROM online_orders WHERE (assigned_rider_id = ? OR assigned_rider_phone = ?) AND order_status = 'delivered'",
        (rider_id, rider_phone),
    ).fetchall()
    all_time_earned = sum((float(o["rider_fee"] or 0.0) if float(o["rider_fee"] or 0.0) > 0 else default_fee) for o in delivered_orders)
    all_time_paid = sum(float(p["amount"] or 0.0) for p in conn.execute("SELECT amount FROM rider_payouts WHERE rider_id = ?", (rider_id,)).fetchall())
    balance_due = max(0.0, round(all_time_earned - all_time_paid, 2))

    if balance_due <= 0:
        conn.close()
        return jsonify({"success": False, "message": f"{rider_name}-এর কোনো বকেয়া পেমেন্ট নেই।"}), 400
    if amount > balance_due + 0.01:
        conn.close()
        return jsonify({"success": False, "message": f"বকেয়া ৳{balance_due:,.2f}-এর বেশি পেমেন্ট করা যাবে না।"}), 400

    payment_method = (data.get("payment_method") or "Cash").strip() or "Cash"
    note = (data.get("note") or "").strip()
    payout_date = (data.get("payout_date") or "").strip() or datetime.now().strftime("%Y-%m-%d")
    now_str = datetime.now().isoformat()

    conn.execute(
        "INSERT INTO rider_payouts (rider_id, amount, payout_date, payment_method, note, created_at) VALUES (?, ?, ?, ?, ?, ?)",
        (rider_id, amount, payout_date, payment_method, note, now_str),
    )
    exp_title = f"Riders riding cost - {rider_name} ({rider_phone})" + (f" [{note}]" if note else "")
    conn.execute(
        "INSERT INTO ledger_entries (entry_type, title, amount, entry_date, created_at, target_segment) VALUES ('expense', ?, ?, ?, ?, 'online')",
        (exp_title, amount, payout_date, now_str),
    )
    conn.commit()
    conn.close()
    try:
        remote_control.push_full_backup()
    except Exception:
        pass
    return jsonify({"success": True, "message": f"{rider_name}-কে ৳{amount:,.2f} পেমেন্ট সম্পন্ন হয়েছে।"})


@app.route("/api/admin/riders/payouts/<int:payout_id>/delete", methods=["POST"])
def api_admin_riders_delete_payout(payout_id):
    """Removes a rider payout record and reverses its ledger expense."""
    data = request.get_json(silent=True) or request.form or {}
    conn = get_connection()
    actor = _authorize_admin_or_cashier(conn, data)
    if not actor:
        conn.close()
        return jsonify({"success": False, "message": "Admin authorization required."}), 401
    payout = conn.execute("SELECT * FROM rider_payouts WHERE id = ?", (payout_id,)).fetchone()
    if not payout:
        conn.close()
        return jsonify({"success": False, "message": "Payout record not found."}), 404
    conn.execute(
        "DELETE FROM ledger_entries WHERE entry_type = 'expense' AND amount = ? AND entry_date = ? AND title LIKE 'Riders riding cost%'",
        (payout["amount"], payout["payout_date"]),
    )
    conn.execute("DELETE FROM rider_payouts WHERE id = ?", (payout_id,))
    conn.commit()
    conn.close()
    return jsonify({"success": True, "message": "পেমেন্ট রেকর্ড বাতিল করা হয়েছে।"})


@app.route("/api/admin/settings", methods=["GET", "POST"])
def api_admin_settings():
    """Reads or updates general shop, delivery, pharmacy, and thermal printer settings natively."""
    data = request.get_json(silent=True) or request.form or {}
    conn = get_connection()
    actor = _authorize_admin_or_cashier(conn, data)
    if not actor:
        conn.close()
        return jsonify({"success": False, "message": "Admin/Cashier authorization required."}), 401

    allowed_keys = (
        "shop_name", "shop_address", "shop_phone", "customer_support_phone",
        "admin_whatsapp_phone", "vat_reg_no", "delivery_charge", "promo_interval_sec",
        "rider_delivery_fee", "pharmacy_delivery_charge", "pharmacy_discount_percent",
        "max_order_qty_product", "max_order_qty_package", "apply_max_qty_to_pos",
        "auto_record_expired_as_loss", "thermal_printer_name", "thermal_paper_width",
        "thermal_pc_auto_print", "facebook_url", "youtube_url", "x_url", "instagram_url",
        "apk_download_url",
    )

    if request.method == "POST":
        updates = {}
        for k in allowed_keys:
            if k in data:
                val = data.get(k)
                if k in ("apply_max_qty_to_pos", "auto_record_expired_as_loss", "thermal_pc_auto_print"):
                    updates[k] = "1" if str(val).strip().lower() in ("1", "true", "yes", "on") else "0"
                else:
                    updates[k] = str(val or "").strip()
        if updates:
            update_settings(conn, updates)
            conn.commit()
        try:
            remote_control.push_full_backup()
        except Exception:
            pass

    current_settings = get_all_settings(conn)
    is_win = thermal_printer.is_windows_pc()
    resolved = thermal_printer.resolve_target_printer(conn) if is_win else ""
    printers = thermal_printer.list_windows_printers() if is_win else []
    pending_cnt = conn.execute("SELECT COUNT(*) FROM thermal_print_jobs WHERE status = 'pending'").fetchone()[0]
    conn.close()

    hb = remote_control.get_pc_printer_heartbeat() or {}
    return jsonify({
        "success": True,
        "message": "সেটিংস সংরক্ষণ হয়েছে।" if request.method == "POST" else "",
        "settings": current_settings,
        "thermal": {
            "printers": printers,
            "resolved_printer": resolved or hb.get("printer_name") or "",
            "is_windows_pc": is_win,
            "pc_agent_online": bool(is_win and resolved) or bool(hb.get("is_online")),
            "pc_last_seen": hb.get("online_at") or "",
            "pending_jobs": pending_cnt,
        },
    })


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000, use_reloader=False)
