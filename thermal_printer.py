"""
thermal_printer.py
------------------
ESC/POS Thermal Printer engine & PC Spooler bridge for DOINEEK Supershop.
Supports:
- Direct RAW printing to any USB/Bluetooth/LAN Windows thermal printer (58mm / 80mm) via win32print
- Automatic printer discovery (prioritizing POS58 / POS80 / Thermal / EPSON / XPrinter)
- Clean receipt formatting for POS Sales, Online Orders, Pharmacy RX Orders & Rider Mobile Bills
- Bengali-to-readable-ASCII transliteration for ESC/POS CP437 hardware compatibility
- Cloud-to-PC queue execution for printing from mobile devices anywhere
"""

import base64
import json
import platform
import re
import threading
import uuid
from datetime import datetime, timedelta, timezone


_PRINT_LOCK = threading.Lock()

# Bengali Unicode to clean readable phonetic ASCII for ESC/POS 58mm/80mm hardware
_BN_MAP = {
    "অ": "o", "আ": "a", "ই": "i", "ঈ": "ee", "উ": "u", "ঊ": "oo", "ঋ": "ri",
    "এ": "e", "ঐ": "oi", "ও": "o", "ঔ": "ou",
    "া": "a", "ি": "i", "ী": "i", "ু": "u", "ূ": "u", "ৃ": "ri",
    "ে": "e", "ৈ": "oi", "ো": "o", "ৌ": "ou", "্": "", "ং": "ng", "ঃ": "h", "ঁ": "n",
    "ক": "k", "খ": "kh", "গ": "g", "ঘ": "gh", "ঙ": "ng",
    "চ": "ch", "ছ": "chh", "জ": "j", "ঝ": "jh", "ঞ": "n",
    "ট": "t", "ঠ": "th", "ড": "d", "ঢ": "dh", "ণ": "n",
    "ত": "t", "থ": "th", "দ": "d", "ধ": "dh", "ন": "n",
    "প": "p", "ফ": "f", "ব": "b", "ভ": "bh", "ম": "m",
    "য": "j", "র": "r", "ল": "l", "শ": "sh", "ষ": "sh", "স": "s", "হ": "h",
    "ড়": "r", "ঢ়": "rh", "য়": "y", "ৎ": "t",
    "০": "0", "১": "1", "২": "2", "৩": "3", "৪": "4",
    "৫": "5", "৬": "6", "৭": "7", "৮": "8", "৯": "9",
    "৳": "TK ",
}


def bd_now_str():
    bd_tz = timezone(timedelta(hours=6))
    return datetime.now(bd_tz).strftime("%Y-%m-%d %H:%M:%S")


def to_printer_ascii(text):
    """Converts Unicode/Emoji/Bengali strings into crisp printable ASCII for ESC/POS printers."""
    if text is None:
        return ""
    s = str(text)
    out = []
    for ch in s:
        if 32 <= ord(ch) <= 126 or ch in ("\n", "\r", "\t"):
            out.append(ch)
        elif ch in _BN_MAP:
            out.append(_BN_MAP[ch])
        else:
            # Strip emojis/unsupported glyphs cleanly
            continue
    cleaned = re.sub(r"[ \t]+", " ", "".join(out))
    return cleaned.strip()


def is_windows_pc():
    return platform.system().lower() == "windows"


def list_windows_printers():
    """Returns installed Windows printer names, putting thermal/POS printers first."""
    if not is_windows_pc():
        return []
    try:
        import win32print
        flags = win32print.PRINTER_ENUM_LOCAL | win32print.PRINTER_ENUM_CONNECTIONS
        raw = win32print.EnumPrinters(flags)
        names = [p[2] for p in raw if len(p) >= 3 and p[2]]
        thermal_kw = ("pos", "thermal", "58", "80", "xp-", "xprinter", "rongta", "bixolon", "epson", "receipt")

        def _score(name):
            low = name.lower()
            if any(k in low for k in thermal_kw):
                return (0, low)
            if any(v in low for v in ("onenote", "xps", "pdf", "fax")):
                return (2, low)
            return (1, low)

        return sorted(list(dict.fromkeys(names)), key=_score)
    except Exception as e:
        print(f"[thermal_printer] list_windows_printers notice: {e}")
        return []


def resolve_target_printer(conn=None, requested_printer=None):
    """Selects best thermal printer on the Windows PC."""
    if not is_windows_pc():
        return ""
    installed = list_windows_printers()
    if requested_printer and requested_printer.strip():
        req = requested_printer.strip()
        for p in installed:
            if p.lower() == req.lower():
                return p
        return req

    saved = ""
    if conn is not None:
        try:
            row = conn.execute("SELECT value FROM settings WHERE key = 'thermal_printer_name'").fetchone()
            if row and row["value"]:
                saved = row["value"].strip()
        except Exception:
            pass
    if saved:
        for p in installed:
            if p.lower() == saved.lower():
                return p
        if not installed:
            return saved

    thermal_kw = ("pos", "thermal", "58", "80", "xp-", "xprinter", "rongta", "bixolon", "epson", "receipt")
    for p in installed:
        if any(k in p.lower() for k in thermal_kw):
            return p

    try:
        import win32print
        dflt = win32print.GetDefaultPrinter()
        if dflt:
            return dflt
    except Exception:
        pass
    return installed[0] if installed else ""


def send_raw_escpos_to_windows_printer(printer_name, raw_bytes):
    """Sends raw ESC/POS bytes directly to a Windows printer spooler."""
    if not is_windows_pc():
        return False, "Server is not running on Windows PC"
    if not printer_name:
        return False, "No Windows printer found or configured"
    try:
        import win32print
        with _PRINT_LOCK:
            hprinter = win32print.OpenPrinter(printer_name)
            try:
                job_info = ("DOINEEK Supershop Receipt", None, "RAW")
                win32print.StartDocPrinter(hprinter, 1, job_info)
                try:
                    win32print.StartPagePrinter(hprinter)
                    win32print.WritePrinter(hprinter, raw_bytes)
                    win32print.EndPagePrinter(hprinter)
                finally:
                    win32print.EndDocPrinter(hprinter)
            finally:
                win32print.ClosePrinter(hprinter)
        return True, f"Printed to {printer_name}"
    except Exception as e:
        return False, str(e)


def _pad_lr(left_txt, right_txt, width):
    left = str(left_txt or "")
    right = str(right_txt or "")
    if len(left) + len(right) + 1 <= width:
        spaces = width - len(left) - len(right)
        return f"{left}{' ' * spaces}{right}"
    max_left = max(4, width - len(right) - 1)
    return f"{left[:max_left]} {right}"


def _wrap_text(text, width):
    words = str(text or "").split()
    if not words:
        return []
    lines, cur = [], ""
    for w in words:
        if not cur:
            cur = w[:width]
        elif len(cur) + 1 + len(w) <= width:
            cur += " " + w
        else:
            lines.append(cur)
            cur = w[:width]
    if cur:
        lines.append(cur)
    return lines


def build_escpos_bytes(receipt_data, paper_width="58mm"):
    """Builds both raw ESC/POS byte stream and a human-readable text preview."""
    chars = 42 if str(paper_width).strip() == "80mm" else 32
    sep = "-" * chars
    dsep = "=" * chars

    shop_name = to_printer_ascii(receipt_data.get("shop_name") or "DOINEEK SUPERSHOP")
    shop_addr = to_printer_ascii(receipt_data.get("shop_address") or "")
    shop_phone = to_printer_ascii(receipt_data.get("shop_phone") or "")
    title = to_printer_ascii(receipt_data.get("title") or "SALES RECEIPT")

    inv_no = to_printer_ascii(receipt_data.get("invoice_number") or "")
    dt_str = to_printer_ascii(receipt_data.get("date_str") or bd_now_str()[:16])
    cust_name = to_printer_ascii(receipt_data.get("customer_name") or "Walk-in Customer")
    cust_phone = to_printer_ascii(receipt_data.get("customer_phone") or "")
    cust_addr = to_printer_ascii(receipt_data.get("customer_address") or "")
    rider_name = to_printer_ascii(receipt_data.get("rider_name") or "")
    channel_label = to_printer_ascii(receipt_data.get("channel_label") or "")
    otp = to_printer_ascii(receipt_data.get("delivery_otp") or "")
    pay_method = to_printer_ascii(receipt_data.get("payment_method") or "CASH").upper()
    pay_status = to_printer_ascii(receipt_data.get("payment_status") or "").upper()

    ESC = b"\x1b"
    GS = b"\x1d"
    INIT = ESC + b"@"
    ALIGN_C = ESC + b"a\x01"
    ALIGN_L = ESC + b"a\x00"
    BOLD_ON = ESC + b"E\x01"
    BOLD_OFF = ESC + b"E\x00"
    SIZE_2X = GS + b"!\x11"
    SIZE_1X = GS + b"!\x00"
    CUT = b"\n\n\n" + GS + b"V\x42\x03"

    buf = bytearray()
    preview_lines = []

    def add_line(txt="", raw=True):
        s = str(txt)
        preview_lines.append(s)
        if raw:
            buf.extend(s.encode("ascii", errors="replace") + b"\n")

    buf.extend(INIT)
    buf.extend(ALIGN_C)
    buf.extend(BOLD_ON + SIZE_2X)
    add_line(shop_name[:20])
    buf.extend(SIZE_1X + BOLD_OFF)
    if shop_addr:
        for ln in _wrap_text(shop_addr, chars):
            add_line(ln)
    if shop_phone:
        add_line(f"Tel: {shop_phone}"[:chars])
    buf.extend(BOLD_ON)
    add_line(f"[ {title} ]"[:chars])
    buf.extend(BOLD_OFF)
    buf.extend(ALIGN_L)
    add_line(dsep)

    if inv_no:
        add_line(f"Inv/Ord: {inv_no}"[:chars])
    add_line(f"Date   : {dt_str}"[:chars])
    if channel_label:
        add_line(f"Channel: {channel_label}"[:chars])
    add_line(f"Cust   : {cust_name}"[:chars])
    if cust_phone:
        add_line(f"Mobile : {cust_phone}"[:chars])
    if cust_addr:
        for idx, ln in enumerate(_wrap_text(cust_addr, chars - 7)):
            prefix = "Addr  : " if idx == 0 else "        "
            add_line(f"{prefix}{ln}"[:chars])
    if rider_name:
        add_line(f"Rider  : {rider_name}"[:chars])
    add_line(sep)

    # Items header
    buf.extend(BOLD_ON)
    add_line(_pad_lr("Item x Qty", "Total", chars))
    buf.extend(BOLD_OFF)
    add_line(sep)

    for it in receipt_data.get("items", []):
        name = to_printer_ascii(it.get("name") or it.get("product_name") or "Item")
        qty = it.get("quantity", 1)
        uprice = float(it.get("unit_price") or 0.0)
        ltotal = float(it.get("total_price") if it.get("total_price") is not None else (float(qty) * uprice))
        name_lines = _wrap_text(name, chars)
        for nl in name_lines:
            add_line(nl)
        qty_detail = f"  {qty} x {uprice:.2f}"
        add_line(_pad_lr(qty_detail, f"{ltotal:.2f}", chars))

    add_line(sep)
    subtotal = float(receipt_data.get("subtotal") or 0.0)
    deliv = float(receipt_data.get("delivery_charge") or 0.0)
    discount = float(receipt_data.get("discount") or 0.0)
    vat = float(receipt_data.get("vat") or 0.0)
    grand = float(receipt_data.get("total_amount") or 0.0)

    add_line(_pad_lr("Sub-total", f"TK {subtotal:.2f}", chars))
    if deliv > 0:
        add_line(_pad_lr("Delivery Charge", f"TK {deliv:.2f}", chars))
    if discount > 0.004:
        add_line(_pad_lr("Discount/Saved", f"-TK {discount:.2f}", chars))
    if vat > 0.004:
        add_line(_pad_lr("VAT", f"TK {vat:.2f}", chars))

    add_line(dsep)
    buf.extend(BOLD_ON)
    add_line(_pad_lr("NET PAYABLE", f"TK {grand:.2f}", chars))
    buf.extend(BOLD_OFF)
    add_line(dsep)

    add_line(_pad_lr("Payment Method", pay_method, chars))
    if pay_status:
        add_line(_pad_lr("Payment Status", pay_status, chars))
    if otp:
        buf.extend(ALIGN_C + BOLD_ON)
        add_line(f"Delivery OTP: {otp}")
        buf.extend(BOLD_OFF + ALIGN_L)

    add_line(sep)
    buf.extend(ALIGN_C)
    add_line("Thank you for shopping with us!")
    add_line("DOINEEK Supershop & Pharmacy")
    buf.extend(ALIGN_L)
    buf.extend(CUT)

    return bytes(buf), "\n".join(preview_lines)


def _load_shop_settings(conn):
    rows = conn.execute("SELECT key, value FROM settings").fetchall()
    return {r["key"]: r["value"] for r in rows}


def build_receipt_data_from_sale(conn, sale_id):
    sale = conn.execute("SELECT * FROM sales WHERE id = ?", (sale_id,)).fetchone()
    if not sale:
        return None
    settings = _load_shop_settings(conn)
    items_rows = conn.execute("""
        SELECT si.*, p.name AS product_name
        FROM sale_items si
        LEFT JOIN products p ON si.product_id = p.id
        WHERE si.sale_id = ?
    """, (sale_id,)).fetchall()
    items = []
    has_med = False
    for r in items_rows:
        serials = (r["unit_serials"] or "").strip()
        pname = r["product_name"] or "Item"
        if serials.startswith("💊"):
            has_med = True
            med_label = serials.replace("💊", "").strip()
            if med_label:
                pname = med_label
        items.append({
            "name": pname,
            "quantity": r["quantity"],
            "unit_price": r["unit_price"],
            "total_price": round(float(r["unit_price"] or 0) * float(r["quantity"] or 1), 2),
        })

    inv = sale["invoice_number"] or f"INV-{sale['id']}"
    ch = sale["channel"] or "Offline"
    if ch == "Pharmacy POS" or (has_med and not inv.startswith("INV-ONLINE")):
        ch_lbl = "Pharmacy POS"
        title = "PHARMACY BILL"
    elif "ONLINE-RX" in inv.upper():
        ch_lbl = "Pharmacy Online"
        title = "PHARMACY ONLINE"
    elif ch == "Online" or inv.startswith("INV-ONLINE"):
        ch_lbl = "Online Order"
        title = "ONLINE INVOICE"
    else:
        ch_lbl = "In-Store / Rider POS"
        title = "SALES RECEIPT"

    cash_a = float(sale["cash_amount"] or 0)
    card_a = float(sale["card_amount"] or 0)
    pay_m = "CARD/MOBILE" if card_a > 0 and cash_a <= 0 else ("SPLIT" if card_a > 0 and cash_a > 0 else "CASH")

    return {
        "shop_name": settings.get("shop_name", "DOINEEK"),
        "shop_address": settings.get("shop_address", ""),
        "shop_phone": settings.get("shop_phone", ""),
        "title": title,
        "invoice_number": inv,
        "date_str": (sale["created_at"] or "")[:16].replace("T", " "),
        "channel_label": ch_lbl,
        "customer_name": sale["customer_name"] or "Walk-in",
        "customer_phone": sale["customer_mobile"] or "",
        "subtotal": float(sale["total_amount"] or 0),
        "discount": float(sale["saved_amount"] or 0),
        "vat": float(sale["vat_amount"] or 0),
        "total_amount": float(sale["rounded_total"] or sale["total_amount"] or 0),
        "payment_method": pay_m,
        "payment_status": "PAID",
        "items": items,
    }


def build_receipt_data_from_online_order(conn, order_id_or_number):
    order = None
    try:
        order = conn.execute("SELECT * FROM online_orders WHERE id = ?", (int(order_id_or_number),)).fetchone()
    except Exception:
        order = None
    if not order:
        order = conn.execute("SELECT * FROM online_orders WHERE order_number = ?", (str(order_id_or_number),)).fetchone()
    if not order:
        return None

    settings = _load_shop_settings(conn)
    items_rows = conn.execute("SELECT * FROM online_order_items WHERE order_id = ?", (order["id"],)).fetchall()
    items = []
    for it in items_rows:
        items.append({
            "name": it["product_name"] or "Product",
            "quantity": it["quantity"] or 1,
            "unit_price": it["unit_price"] or 0,
            "total_price": it["total_price"] or (float(it["unit_price"] or 0) * int(it["quantity"] or 1)),
        })

    is_pharm = str(order["order_number"] or "").startswith("RX-")
    if is_pharm and (not items or (len(items) == 1 and float(items[0]["unit_price"]) == 0)):
        pharm = conn.execute(
            "SELECT * FROM pharmacy_orders WHERE online_order_id = ? OR order_number = ? LIMIT 1",
            (order["id"], order["order_number"]),
        ).fetchone()
        if pharm:
            for field in ("approved_items_json", "requested_items_json"):
                try:
                    parsed = json.loads(pharm[field] or "[]")
                    if parsed:
                        items = [
                            {
                                "name": f"{x.get('name', 'Medicine')} {x.get('strength', '')}".strip(),
                                "quantity": x.get("quantity", 1),
                                "unit_price": float(x.get("unit_price") or 0),
                                "total_price": float(x.get("total_price") or (float(x.get("unit_price") or 0) * int(x.get("quantity") or 1))),
                            }
                            for x in parsed
                        ]
                        break
                except Exception:
                    pass

    addr_parts = [
        p for p in [order["address_details"], order["area"], order["district"]]
        if p and p not in ("Delivery Address", "Main Area", "Main Town")
    ]
    return {
        "shop_name": settings.get("shop_name", "DOINEEK"),
        "shop_address": settings.get("shop_address", ""),
        "shop_phone": settings.get("shop_phone", ""),
        "title": "PHARMACY ONLINE" if is_pharm else "ONLINE DELIVERY",
        "invoice_number": order["order_number"] or f"OL-{order['id']}",
        "date_str": (order["created_at"] or "")[:16].replace("T", " "),
        "channel_label": "Pharmacy Online (App/Web)" if is_pharm else "Online Order (App/Web)",
        "customer_name": order["customer_name"] or "Customer",
        "customer_phone": order["customer_phone"] or "",
        "customer_address": ", ".join(addr_parts),
        "rider_name": order["assigned_rider_name"] or "",
        "delivery_otp": order["delivery_otp"] or "",
        "subtotal": float(order["subtotal"] or 0),
        "delivery_charge": float(order["delivery_charge"] or 0),
        "total_amount": float(order["total_amount"] or 0),
        "payment_method": order["payment_method"] or "COD",
        "payment_status": order["payment_status"] or "pending",
        "items": items,
    }


def build_receipt_data_from_pharmacy_order(conn, order_id_or_number):
    """Builds receipt dict directly from pharmacy_orders (or its mirrored online_order)."""
    pharm = None
    try:
        pharm = conn.execute("SELECT * FROM pharmacy_orders WHERE id = ?", (int(order_id_or_number),)).fetchone()
    except Exception:
        pharm = None
    if not pharm:
        pharm = conn.execute("SELECT * FROM pharmacy_orders WHERE order_number = ?", (str(order_id_or_number),)).fetchone()
    if not pharm:
        return build_receipt_data_from_online_order(conn, order_id_or_number)

    if pharm["online_order_id"]:
        mirrored = build_receipt_data_from_online_order(conn, pharm["online_order_id"])
        if mirrored:
            return mirrored

    settings = _load_shop_settings(conn)
    items = []
    for field in ("approved_items_json", "requested_items_json"):
        try:
            parsed = json.loads(pharm[field] or "[]")
            if parsed:
                items = [
                    {
                        "name": f"{x.get('name', 'Medicine')} {x.get('strength', '')}".strip(),
                        "quantity": x.get("quantity", 1),
                        "unit_price": float(x.get("unit_price") or 0),
                        "total_price": float(x.get("total_price") or (float(x.get("unit_price") or 0) * int(x.get("quantity") or 1))),
                    }
                    for x in parsed
                ]
                break
        except Exception:
            pass
    if not items:
        items.append({
            "name": f"Prescription Order ({pharm['order_number']})",
            "quantity": 1,
            "unit_price": float(pharm["subtotal"] or pharm["total_amount"] or 0),
            "total_price": float(pharm["subtotal"] or pharm["total_amount"] or 0),
        })

    addr_parts = [
        p for p in [pharm["delivery_address"], pharm["area"], pharm["district"]]
        if p and p not in ("Delivery Address", "Main Area", "Main Town")
    ]
    return {
        "shop_name": settings.get("shop_name", "DOINEEK"),
        "shop_address": settings.get("shop_address", ""),
        "shop_phone": settings.get("shop_phone", ""),
        "title": "PHARMACY ONLINE",
        "invoice_number": pharm["order_number"] or f"RX-{pharm['id']}",
        "date_str": (pharm["created_at"] or "")[:16].replace("T", " "),
        "channel_label": "Pharmacy Online (App/Web)",
        "customer_name": pharm["customer_name"] or "Customer",
        "customer_phone": pharm["customer_phone"] or "",
        "customer_address": ", ".join(addr_parts),
        "rider_name": pharm["assigned_rider_name"] or "",
        "delivery_otp": pharm["delivery_otp"] or "",
        "subtotal": float(pharm["subtotal"] or 0),
        "delivery_charge": float(pharm["delivery_charge"] or 0),
        "total_amount": float(pharm["total_amount"] or 0),
        "payment_method": pharm["payment_method"] or "COD",
        "payment_status": pharm["payment_status"] or "pending",
        "items": items,
    }


def build_test_receipt_data(conn, invoice_number="TEST-PRINT"):
    """Builds a short diagnostic slip to verify USB thermal alignment & cutting."""
    settings = _load_shop_settings(conn)
    return {
        "shop_name": settings.get("shop_name", "DOINEEK"),
        "shop_address": settings.get("shop_address", ""),
        "shop_phone": settings.get("shop_phone", ""),
        "title": "THERMAL TEST SLIP",
        "invoice_number": invoice_number or "TEST-PRINT",
        "date_str": bd_now_str()[:16].replace("T", " "),
        "channel_label": "PC USB Thermal Diagnostics",
        "customer_name": "Shop Admin",
        "customer_phone": settings.get("shop_phone", ""),
        "subtotal": 100.0,
        "delivery_charge": 0.0,
        "total_amount": 100.0,
        "payment_method": "TEST",
        "payment_status": "OK",
        "items": [
            {"name": "Miniket Rice 5kg (Test)", "quantity": 1, "unit_price": 80.0, "total_price": 80.0},
            {"name": "Napa Extra 500mg (Test)", "quantity": 1, "unit_price": 20.0, "total_price": 20.0},
        ],
    }


def _resolve_receipt_data(conn, source_type, source_id, invoice_number=""):
    st = (source_type or "online_order").strip().lower()
    if st == "test":
        return build_test_receipt_data(conn, invoice_number=invoice_number or "TEST-PRINT")
    if st == "sale":
        return build_receipt_data_from_sale(conn, int(source_id or 0))
    if st == "pharmacy_order":
        return build_receipt_data_from_pharmacy_order(conn, source_id or invoice_number)
    return build_receipt_data_from_online_order(conn, source_id or invoice_number)


def enqueue_or_print_receipt(conn=None, receipt_data=None, job_type="online_order", ref_id=0,
                             order_number="", printer_name=None, requested_by="",
                             source_device="", paper_width=None, remote_ctrl=None,
                             source_type=None, source_id=None, invoice_number="",
                             requested_from=""):
    """
    Creates a print job record, prints immediately if running on a Windows PC with printer attached,
    otherwise pushes the ESC/POS job to Cloud Firestore so the shop's Windows PC prints automatically.
    Supports both explicit (conn, receipt_data, ...) and high-level (source_type, source_id, ...) calls.
    """
    own_conn = False
    if conn is None:
        import database
        conn = database.get_connection()
        own_conn = True

    try:
        eff_type = (source_type or job_type or "online_order").strip().lower()
        eff_id = int(source_id if source_id is not None else (ref_id or 0))
        eff_num = str(invoice_number or order_number or "")
        eff_src = str(requested_from or source_device or "")

        if receipt_data is None:
            receipt_data = _resolve_receipt_data(conn, eff_type, eff_id, invoice_number=eff_num)
            if receipt_data is None:
                return {"success": False, "printed_directly": False, "message": "Receipt record not found."}

        settings = _load_shop_settings(conn)
        width = paper_width or settings.get("thermal_paper_width") or "58mm"
        raw_bytes, text_preview = build_escpos_bytes(receipt_data, paper_width=width)
        escpos_b64 = base64.b64encode(raw_bytes).decode("ascii")
        job_uuid = uuid.uuid4().hex
        now_iso = bd_now_str()

        target_printer = resolve_target_printer(conn, requested_printer=printer_name)
        printed_ok = False
        mode = "cloud_queued"
        status = "pending"
        printed_at = ""
        err_msg = ""

        if is_windows_pc() and target_printer:
            printed_ok, msg = send_raw_escpos_to_windows_printer(target_printer, raw_bytes)
            if printed_ok:
                status = "printed"
                mode = "direct_pc"
                printed_at = now_iso
            else:
                err_msg = msg

        conn.execute("""
            INSERT INTO thermal_print_jobs (
                job_uuid, job_type, ref_id, order_number, printer_name, paper_width,
                raw_escpos_b64, text_preview, status, requested_by, source_device,
                created_at, printed_at, error_msg
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            job_uuid, eff_type, eff_id, str(eff_num or receipt_data.get("invoice_number") or ""),
            target_printer, width, escpos_b64, text_preview, status,
            str(requested_by or ""), eff_src, now_iso, printed_at, err_msg
        ))
        conn.commit()

        if remote_ctrl is not None and not printed_ok:
            try:
                remote_ctrl.push_thermal_print_job_to_cloud(job_uuid)
            except Exception as e:
                print(f"[thermal_printer] push cloud job failed: {e}")

        return {
            "success": True if (printed_ok or status == "pending") else False,
            "printed_directly": bool(printed_ok),
            "mode": mode,
            "status": status,
            "job_uuid": job_uuid,
            "printer_name": target_printer,
            "text_preview": text_preview,
            "message": (
                f"Printed directly on {target_printer}!" if printed_ok
                else f"Queued for PC Thermal Printer ({eff_num or job_uuid[:8]}). Shop Windows PC will auto-print once connected."
            ),
            "error": err_msg,
        }
    finally:
        if own_conn and conn is not None:
            conn.close()


def process_pending_pc_print_jobs(get_conn_fn=None, remote_ctrl=None, limit=20):
    """Claims any pending thermal print jobs locally on a Windows PC and sends them to Windows Spooler."""
    if not is_windows_pc():
        return {"processed": 0, "printed": 0, "failed": 0}
    if get_conn_fn is None:
        import database
        get_conn_fn = database.get_connection

    conn = get_conn_fn()
    try:
        settings = _load_shop_settings(conn)
        if settings.get("thermal_pc_auto_print", "1") == "0":
            return {"processed": 0, "printed": 0, "failed": 0}
        pending = conn.execute(
            "SELECT * FROM thermal_print_jobs WHERE status = 'pending' ORDER BY id ASC LIMIT ?",
            (int(limit or 20),),
        ).fetchall()
        processed = 0
        failed = 0
        for job in pending:
            # Atomic claim to prevent duplicate print if multiple threads wake up
            cur = conn.execute(
                "UPDATE thermal_print_jobs SET status = 'printing' WHERE id = ? AND status = 'pending'",
                (job["id"],),
            )
            conn.commit()
            if cur.rowcount == 0:
                continue
            target_printer = resolve_target_printer(conn, requested_printer=job["printer_name"])
            raw_bytes = base64.b64decode(job["raw_escpos_b64"].encode("ascii")) if job["raw_escpos_b64"] else b""
            if not raw_bytes and job["text_preview"]:
                raw_bytes = job["text_preview"].encode("ascii", errors="replace") + b"\n\n\n\x1dV\x42\x03"

            ok, msg = send_raw_escpos_to_windows_printer(target_printer, raw_bytes)
            now_iso = bd_now_str()
            if ok:
                conn.execute(
                    "UPDATE thermal_print_jobs SET status = 'printed', printer_name = ?, printed_at = ?, error_msg = '' WHERE id = ?",
                    (target_printer, now_iso, job["id"]),
                )
                processed += 1
            else:
                conn.execute(
                    "UPDATE thermal_print_jobs SET status = 'failed', error_msg = ? WHERE id = ?",
                    (msg, job["id"]),
                )
                failed += 1
            conn.commit()
            if remote_ctrl is not None:
                try:
                    remote_ctrl.push_thermal_print_job_to_cloud(job["job_uuid"])
                except Exception:
                    pass
        return {"processed": processed, "printed": processed, "failed": failed}
    finally:
        conn.close()
