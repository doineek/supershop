// pos.js
// Browser-side POS logic with localStorage persistence and Table Layout

const CART_STORAGE_KEY = "supershop_cart";
const CUSTOMER_ID_KEY = "supershop_customer_id";
const CUSTOMER_MOBILE_KEY = "supershop_customer_mobile";

const posSettings = window.POS_SETTINGS || {};
const applyMaxQtyToPos = String(posSettings.apply_max_qty_to_pos || "0") === "1" || String(posSettings.apply_max_qty_to_pos || "") === "true";
const maxOrderQtyProduct = parseInt(posSettings.max_order_qty_product || 0, 10) || 0;
const maxOrderQtyPackage = parseInt(posSettings.max_order_qty_package || 0, 10) || 0;

let cart = {};
const savedCart = localStorage.getItem(CART_STORAGE_KEY);
if (savedCart) {
  try { cart = JSON.parse(savedCart); } catch (e) { cart = {}; }
}
// Backward-compat: older carts saved before serial-tracking existed won't
// have a `serials` array - fill it in with unassigned (null) slots so
// nothing crashes.
Object.keys(cart).forEach(id => {
  const item = cart[id];
  if (!Array.isArray(item.serials)) {
    item.serials = new Array(item.quantity || 0).fill(null);
  }
  if (typeof item.sku !== "string") item.sku = "";
});

const productList = document.getElementById("productList");
const searchBox = document.getElementById("searchBox");
const subTotalTextEl = document.getElementById("subTotalText");
const vatRowEl = document.getElementById("vatRow");
const vatAmountEl = document.getElementById("vatAmount");
const savedRowEl = document.getElementById("savedRow");
const savedAmountEl = document.getElementById("savedAmount");
const cartTotalEl = document.getElementById("cartTotal");
const cashInput = document.getElementById("cashInput");
const cardInput = document.getElementById("cardInput");
const changeDueEl = document.getElementById("changeDue");
const checkoutBtn = document.getElementById("checkoutBtn");
const customerIdInput = document.getElementById("customerIdInput");
const customerMobileInput = document.getElementById("customerMobileInput");

const allTiles = Array.from(document.querySelectorAll(".pos-product"));

function switchPosCatalog(tab) {
  const prodList = document.getElementById("productList");
  const pkgList = document.getElementById("packageList");
  const tabProdBtn = document.getElementById("posTabProducts");
  const tabPkgBtn = document.getElementById("posTabPackages");

  if (tab === "packages") {
    if (prodList) prodList.style.display = "none";
    if (pkgList) pkgList.style.display = "grid";
    if (tabProdBtn) {
      tabProdBtn.style.background = "#f1f5f9";
      tabProdBtn.style.color = "#475569";
      tabProdBtn.style.borderColor = "#cbd5e1";
    }
    if (tabPkgBtn) {
      tabPkgBtn.style.background = "#ea580c";
      tabPkgBtn.style.color = "#ffffff";
      tabPkgBtn.style.borderColor = "#ea580c";
    }
  } else {
    if (prodList) prodList.style.display = "grid";
    if (pkgList) pkgList.style.display = "none";
    if (tabProdBtn) {
      tabProdBtn.style.background = "#0284c7";
      tabProdBtn.style.color = "#ffffff";
      tabProdBtn.style.borderColor = "#0284c7";
    }
    if (tabPkgBtn) {
      tabPkgBtn.style.background = "#fff7ed";
      tabPkgBtn.style.color = "#ea580c";
      tabPkgBtn.style.borderColor = "#ea580c";
    }
  }
}
window.switchPosCatalog = switchPosCatalog;

const savedCustId = localStorage.getItem(CUSTOMER_ID_KEY);
if (savedCustId) customerIdInput.value = savedCustId;
const savedCustMobile = localStorage.getItem(CUSTOMER_MOBILE_KEY);
if (savedCustMobile) customerMobileInput.value = savedCustMobile;

function saveCart() {
  localStorage.setItem(CART_STORAGE_KEY, JSON.stringify(cart));
  localStorage.setItem(CUSTOMER_ID_KEY, customerIdInput.value || "");
  localStorage.setItem(CUSTOMER_MOBILE_KEY, customerMobileInput.value || "");
}

function currentCartSerials() {
  let all = [];
  Object.values(cart).forEach(item => { all = all.concat(item.serials.filter(Boolean)); });
  return all;
}

function roundToWhole(amount) {
  const fraction = amount - Math.floor(amount);
  return fraction >= 0.5 ? Math.ceil(amount) : Math.floor(amount);
}

searchBox.addEventListener("input", () => {
  const term = searchBox.value.toLowerCase();
  allTiles.forEach(btn => {
    btn.style.display = btn.dataset.search.includes(term) ? "" : "none";
  });
});

searchBox.addEventListener("keydown", async (e) => {
  if (e.key !== "Enter") return;
  e.preventDefault();
  const typed = searchBox.value.trim();
  if (!typed) return;
  try {
    const exclude = currentCartSerials().join(",");
    const res = await fetch("/pos/lookup?code=" + encodeURIComponent(typed) + "&exclude=" + encodeURIComponent(exclude));
    const data = await res.json();
    if (!res.ok) { alert(data.error || "Code not recognized."); return; }
    addToCart({
      id: data.id, name: data.name, sku: data.sku, price: data.price,
      mrp: data.mrp, vat_pct: data.vat_pct || 0, stock: data.stock_qty,
      serial: data.unit_serial || null,
    });
    searchBox.value = "";
    allTiles.forEach(btn => { btn.style.display = ""; });
  } catch (err) {
    alert("Could not reach the server to look up that code.");
  }
});

const cameraBtn = document.getElementById("cameraBtn");
let cameraStream = null;
let cameraActive = false;

cameraBtn.addEventListener("click", async () => {
  if (cameraActive) {
    stopCamera();
    return;
  }
  try {
    cameraStream = await navigator.mediaDevices.getUserMedia({
      video: { facingMode: "environment" }
    });
    const videoEl = document.createElement("video");
    videoEl.id = "cameraVideo";
    videoEl.style = "position:fixed; top:0; left:0; width:100vw; height:100vh; object-fit:cover; z-index:9999;";
    videoEl.autoplay = true;
    videoEl.playsInline = true;
    videoEl.srcObject = cameraStream;
    document.body.appendChild(videoEl);
    cameraActive = true;
    cameraBtn.textContent = "❌";

    if ("BarcodeDetector" in window) {
      const detector = new BarcodeDetector({ formats: ["code_128", "ean_13", "upc_a"] });
      const detectFrame = async () => {
        if (!cameraActive) return;
        try {
          const codes = await detector.detect(videoEl);
          if (codes.length > 0) {
            const code = codes[0].rawValue;
            stopCamera();
            searchBox.value = code;
            searchBox.dispatchEvent(new KeyboardEvent("keydown", { key: "Enter" }));
            return;
          }
        } catch (e) {}
        requestAnimationFrame(detectFrame);
      };
      detectFrame();
    } else {
      alert("Browser does not support auto barcode detection. Point camera and type code manually.");
    }
  } catch (err) {
    alert("Could not access camera.");
  }
});

function stopCamera() {
  if (cameraStream) {
    cameraStream.getTracks().forEach(t => t.stop());
    cameraStream = null;
  }
  const videoEl = document.getElementById("cameraVideo");
  if (videoEl) videoEl.remove();
  cameraActive = false;
  cameraBtn.textContent = "📷";
}

allTiles.forEach(btn => {
  btn.addEventListener("click", () => addToCart({
    id: btn.dataset.id, name: btn.dataset.name, sku: btn.dataset.sku,
    price: parseFloat(btn.dataset.price),
    mrp: parseFloat(btn.dataset.mrp) || 0,
    vat_pct: parseFloat(btn.dataset.vat) || 0,
    stock: parseInt(btn.dataset.stock, 10),
    is_package: btn.dataset.isPkg === "true",
    offer_type: btn.dataset.offerType || "",
    offer_value: btn.dataset.offerValue || "",
    offer_title: btn.dataset.offerTitle || "",
    serial: null,
  }));
});

function parseBogoQuantitiesJS(offerValue, offerTitle, name) {
  const v = (offerValue || "").trim();
  const t = (offerTitle || "").trim();
  const n = (name || "").trim();

  const reg = /buy\s*(\d+)\s*get\s*(\d+)/i;
  for (const str of [v, t, n]) {
    if (str) {
      const match = str.match(reg);
      if (match) {
        const b = parseInt(match[1], 10);
        const f = parseInt(match[2], 10);
        if (b > 0 && f > 0) return { buyQty: b, freeQty: f };
      }
    }
  }

  if (v && v.includes(",")) {
    const parts = v.split(",").map(p => parseInt(p.trim(), 10));
    if (parts.length >= 2 && !isNaN(parts[0]) && !isNaN(parts[1]) && parts[0] > 0 && parts[1] > 0) {
      return { buyQty: parts[0], freeQty: parts[1] };
    }
  }

  if (v && /^\d+$/.test(v)) {
    const d = parseInt(v, 10);
    if (d > 0) return { buyQty: d, freeQty: 1 };
  }

  return { buyQty: 1, freeQty: 1 };
}

function getBuyXGetYStats(item) {
  const offerType = (item.offer_type || "").toLowerCase();
  const offerTitle = (item.offer_title || "").toLowerCase();
  const offerValue = (item.offer_value || "").toLowerCase();
  const isOffer = offerType === "buy_x_get_y" || offerType === "bogo" || offerType === "buy_x_get_x" || offerTitle.includes("buy") || offerValue.includes("buy");

  if (!isOffer) {
    return { isOffer: false, buyQty: 0, freeQty: 0, paidQty: item.quantity, freeQtyTotal: 0 };
  }

  const { buyQty, freeQty } = parseBogoQuantitiesJS(item.offer_value, item.offer_title, item.name);
  const totalSet = buyQty + freeQty;
  const sets = Math.floor(item.quantity / totalSet);
  const remainder = item.quantity % totalSet;
  const paidQty = sets * buyQty + Math.min(remainder, buyQty);
  const freeQtyTotal = item.quantity - paidQty;

  return { isOffer: true, buyQty, freeQty, paidQty, freeQtyTotal };
}

function addToCart(data) {
  const id = String(data.id);
  const isPkg = data.is_package || data.isPkg || id.startsWith("pkg_");
  if (!cart[id]) {
    cart[id] = {
      name: data.name, sku: data.sku || (isPkg ? "COMBO" : ""), price: data.price, mrp: data.mrp || 0,
      vat_pct: data.vat_pct || 0, stock: data.stock, quantity: 0, serials: [],
      is_package: isPkg,
      offer_type: data.offer_type || "", offer_value: data.offer_value || "", offer_title: data.offer_title || ""
    };
  }
  if (cart[id].quantity >= cart[id].stock) {
    alert("No more stock available for " + cart[id].name);
    return;
  }
  if (applyMaxQtyToPos) {
    if (isPkg && maxOrderQtyPackage > 0 && (cart[id].quantity + 1) > maxOrderQtyPackage) {
      alert(`Maximum order limit reached: You can order at most ${maxOrderQtyPackage} units of Combo Package "${cart[id].name}" per order.`);
      return;
    }
    if (!isPkg && maxOrderQtyProduct > 0 && (cart[id].quantity + 1) > maxOrderQtyProduct) {
      alert(`Maximum order limit reached: You can order at most ${maxOrderQtyProduct} units of "${cart[id].name}" per order.`);
      return;
    }
  }
  if (data.serial && cart[id].serials.includes(data.serial)) {
    alert("This exact tag (" + data.serial + ") has already been scanned into the cart.");
    return;
  }
  cart[id].serials.push(data.serial || null);
  cart[id].quantity += 1;

  // Buy 2 Get 1 Scan Prompt
  const stats = getBuyXGetYStats(cart[id]);
  if (stats.isOffer && cart[id].quantity === stats.buyQty) {
    alert(`🎁 BUY ${stats.buyQty} GET ${stats.freeQty} OFFER ACTIVE!\n\nYou scanned ${stats.buyQty} items of "${cart[id].name}". Please scan/bring 1 more unit to get it 100% FREE!`);
  }

  saveCart();
  renderCart();
}

function renderCart() {
  const ids = Object.keys(cart).filter(id => cart[id].quantity > 0);
  const cartBody = document.getElementById("cartItemsBody");
  cartBody.innerHTML = "";

  if (ids.length === 0) {
    cartBody.innerHTML = `<tr id="emptyCartRow"><td colspan="7" style="text-align:center; padding:20px; color:var(--ink-soft);">Cart is empty — scan or click an item below.</td></tr>`;
  }

  let subTotal = 0, mrpTotal = 0, totalVat = 0;

  ids.forEach((id, idx) => {
    const item = cart[id];
    const offerStats = getBuyXGetYStats(item);
    const lineSub = item.price * offerStats.paidQty;
    const freeDiscount = item.price * offerStats.freeQtyTotal;
    const lineVat = lineSub * (item.vat_pct / 100);
    const lineTotalWithVat = lineSub + lineVat;

    subTotal += lineSub;
    totalVat += lineVat;
    mrpTotal += (item.mrp > 0 ? item.mrp : item.price) * item.quantity;

    const tr = document.createElement("tr");
    tr.style.borderBottom = "1px dotted var(--line)";
    const scannedCount = item.serials.filter(Boolean).length;
    const serialNote = scannedCount > 0
      ? `<br><small style="color:var(--green)">Scanned: ${scannedCount}/${item.quantity} (${item.serials.filter(Boolean).join(", ")})</small>`
      : `<br><small style="color:var(--ink-soft)">No tag scanned yet</small>`;

    let offerNote = "";
    if (offerStats.isOffer) {
      if (offerStats.freeQtyTotal > 0) {
        offerNote = `<br><span style="color:#9333ea; font-weight:bold; font-size:11px;">🎁 Buy ${offerStats.buyQty} Get ${offerStats.freeQty} FREE (${offerStats.freeQtyTotal} Free Item(s): -৳${freeDiscount.toFixed(2)})</span>`;
      } else if (item.quantity === offerStats.buyQty) {
        offerNote = `<br><span style="color:#d97706; font-weight:bold; font-size:11px;">💡 ${item.quantity} scanned! Scan 1 more item to get 3rd item 100% FREE!</span>`;
      } else {
        offerNote = `<br><span style="color:#9333ea; font-size:11px;">🎁 Buy ${offerStats.buyQty} Get ${offerStats.freeQty} Offer Available</span>`;
      }
    }

    tr.innerHTML = `
      <td style="padding:8px 4px;">${idx + 1}</td>
      <td style="padding:8px 4px;">
        <strong>${item.sku ? item.sku + " - " : ""}${item.name}</strong>${serialNote}${offerNote}
      </td>
      <td style="padding:8px 4px; text-align:center;">
        <input class="qty-input" type="number" min="1" max="${item.stock}" value="${item.quantity}" 
               data-id="${id}" style="width:55px; padding:4px; text-align:center; border:1px solid var(--line); border-radius:4px; font-weight:600;">
      </td>
      <td class="num" style="padding:8px 4px;">৳${item.price.toFixed(2)}</td>
      <td class="num" style="padding:8px 4px;">৳${lineVat.toFixed(2)}</td>
      <td class="num" style="padding:8px 4px; font-weight:700;">৳${lineTotalWithVat.toFixed(2)}</td>
      <td style="text-align:right; padding:8px 4px;">
        <button class="btn btn-danger btn-small" data-action="remove" data-id="${id}" style="padding:2px 6px;">×</button>
      </td>
    `;
    cartBody.appendChild(tr);
  });

  const rounded = roundToWhole(subTotal + totalVat);
  const saved = mrpTotal - (subTotal + totalVat);

  cartTotalEl.textContent = "৳" + rounded.toFixed(2);
  subTotalTextEl.textContent = "Subtotal: ৳" + subTotal.toFixed(2);
  vatAmountEl.textContent = "৳" + totalVat.toFixed(2);
  savedAmountEl.textContent = "৳" + saved.toFixed(2);

  updateChange();
}

document.getElementById("cartItemsBody").addEventListener("change", (e) => {
  const input = e.target.closest("input.qty-input");
  if (!input) return;
  const id = input.dataset.id;
  const item = cart[id];
  let val = parseInt(input.value, 10);
  if (isNaN(val) || val < 1) val = 1;
  if (val > item.stock) { val = item.stock; alert("Max stock is " + item.stock); }
  if (applyMaxQtyToPos) {
    if (item.is_package && maxOrderQtyPackage > 0 && val > maxOrderQtyPackage) {
      val = maxOrderQtyPackage;
      alert(`Maximum order limit reached: You can order at most ${maxOrderQtyPackage} units of Combo Package "${item.name}" per order.`);
      input.value = val;
    } else if (!item.is_package && maxOrderQtyProduct > 0 && val > maxOrderQtyProduct) {
      val = maxOrderQtyProduct;
      alert(`Maximum order limit reached: You can order at most ${maxOrderQtyProduct} units of "${item.name}" per order.`);
      input.value = val;
    }
  }

  if (val > item.quantity) {
    // Growing quantity manually (no scan) - add unassigned slots.
    for (let i = item.quantity; i < val; i++) item.serials.push(null);
  } else if (val < item.quantity) {
    const scannedCount = item.serials.filter(Boolean).length;
    if (val < scannedCount) {
      alert(`You've scanned ${scannedCount} physical tag(s) for this product. Remove a scanned item with the × button instead of typing a lower quantity.`);
      renderCart();
      return;
    }
    // Shrinking quantity manually - drop unassigned (null) slots first.
    let toRemove = item.quantity - val;
    for (let i = item.serials.length - 1; i >= 0 && toRemove > 0; i--) {
      if (item.serials[i] === null) { item.serials.splice(i, 1); toRemove--; }
    }
  }

  item.quantity = val;
  saveCart();
  renderCart();
});

document.getElementById("cartItemsBody").addEventListener("click", (e) => {
  const btn = e.target.closest("button[data-action='remove']");
  if (!btn) return;
  delete cart[btn.dataset.id];
  saveCart();
  renderCart();
});

function updateChange() {
  const rounded = parseFloat(cartTotalEl.textContent.replace("৳", "")) || 0;
  const cash = parseFloat(cashInput.value) || 0;
  const card = parseFloat(cardInput.value) || 0;
  const change = cash + card - rounded;
  changeDueEl.textContent = "৳" + change.toFixed(2);
  changeDueEl.style.color = change < 0 ? "var(--danger)" : "var(--green)";
}
cashInput.addEventListener("input", updateChange);
cardInput.addEventListener("input", updateChange);

checkoutBtn.addEventListener("click", async () => {
  const items = Object.keys(cart)
    .filter(id => cart[id].quantity > 0)
    .map(id => {
      const isPkg = cart[id].is_package || String(id).startsWith("pkg_");
      const cleanId = isPkg ? parseInt(String(id).replace("pkg_", ""), 10) : parseInt(id, 10);
      return {
        product_id: isPkg ? null : cleanId,
        package_id: isPkg ? cleanId : null,
        is_package: isPkg,
        quantity: cart[id].quantity,
        serials: cart[id].serials.filter(Boolean),
      };
    });

  if (items.length === 0) {
    alert("Add at least one product before charging the customer.");
    return;
  }

  let cash_amount = parseFloat(cashInput.value) || 0;

  let card_amount = parseFloat(cardInput.value) || 0;
  const customer_name = customerIdInput.value.trim();
  const customer_mobile = customerMobileInput.value.trim();

  if (customer_mobile) {
    if (!/^01\d{9}$/.test(customer_mobile)) {
      alert("Customer Mobile Number must start with '01' and be exactly 11 digits (e.g. 01700000000).");
      return;
    }
  }

  const rounded = parseFloat(cartTotalEl.textContent.replace("৳", "")) || 0;
  if (cash_amount === 0 && card_amount === 0) {
    cash_amount = rounded;
  }

  checkoutBtn.disabled = true;
  checkoutBtn.textContent = "Processing...";

  try {
    const res = await fetch("/pos/checkout", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ items, cash_amount, card_amount, customer_name, customer_mobile }),
    });

    const data = await res.json();

    if (!res.ok) {
      alert(data.error || "Something went wrong.");
      checkoutBtn.disabled = false;
      checkoutBtn.textContent = "CHARGE CUSTOMER";
      return;
    }

    localStorage.removeItem(CART_STORAGE_KEY);
    localStorage.removeItem(CUSTOMER_ID_KEY);
    localStorage.removeItem(CUSTOMER_MOBILE_KEY);
    cart = {};

    window.location.href = "/sales/" + data.sale_id;
  } catch (err) {
    alert("Could not reach the server.");
    checkoutBtn.disabled = false;
    checkoutBtn.textContent = "CHARGE CUSTOMER";
  }
});

customerIdInput.addEventListener("input", () => {
  localStorage.setItem(CUSTOMER_ID_KEY, customerIdInput.value || "");
});
customerMobileInput.addEventListener("input", () => {
  let digitsOnly = customerMobileInput.value.replace(/\D/g, "");
  if (digitsOnly.length > 11) {
    digitsOnly = digitsOnly.slice(0, 11);
  }
  customerMobileInput.value = digitsOnly;
  localStorage.setItem(CUSTOMER_MOBILE_KEY, customerMobileInput.value || "");
});

renderCart();