import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../models/product.dart';
import '../services/api_service.dart';

class CartItem {
  final Product product;
  int quantity;

  CartItem({required this.product, this.quantity = 1});

  double get unitPrice => product.effectivePrice;

  bool get isBuyOffer {
    String ot = product.offerType.toLowerCase().trim();
    String title = product.offerTitle.toLowerCase().trim();
    String val = product.offerValue.toLowerCase().trim();
    String pName = product.name.toLowerCase().trim();

    return ot == 'buy_x_get_y' ||
        ot == 'buy_x_get_x' ||
        ot == 'bogo' ||
        title.contains('buy') ||
        val.contains('buy') ||
        title.contains('get') ||
        val.contains('get') ||
        pName.contains('buy') ||
        (product.isOffer && val.contains(','));
  }

  Map<String, int> get bogoStats {
    String val = product.offerValue.trim();
    String title = product.offerTitle.trim();
    String name = product.name.trim();

    // Convert Bangla digits if present
    const banglaToEng = {'০': '0', '১': '1', '২': '2', '৩': '3', '৪': '4', '৫': '5', '৬': '6', '৭': '7', '৮': '8', '৯': '9'};
    String normalizeDigits(String s) {
      String out = s;
      banglaToEng.forEach((b, e) => out = out.replaceAll(b, e));
      return out;
    }

    int buyQty = 1;
    int freeQty = 1;
    bool found = false;

    RegExp reg = RegExp(r'buy\s*(\d+)\s*[\w\s,]*get\s*(\d+)', caseSensitive: false);
    for (String raw in [val, title, name]) {
      String str = normalizeDigits(raw);
      if (str.isNotEmpty) {
        Match? match = reg.firstMatch(str);
        if (match != null) {
          int? b = int.tryParse(match.group(1)!);
          int? f = int.tryParse(match.group(2)!);
          if (b != null && f != null && b > 0 && f > 0) {
            buyQty = b;
            freeQty = f;
            found = true;
            break;
          }
        }
      }
    }

    if (!found && val.contains(',')) {
      var parts = normalizeDigits(val).split(',').map((e) => int.tryParse(e.trim()) ?? 0).toList();
      if (parts.length >= 2 && parts[0] > 0 && parts[1] > 0) {
        buyQty = parts[0];
        freeQty = parts[1];
        found = true;
      }
    }

    if (!found && RegExp(r'^\d+$').hasMatch(normalizeDigits(val))) {
      int? d = int.tryParse(normalizeDigits(val));
      if (d != null && d > 0) {
        buyQty = d;
        freeQty = 1;
        found = true;
      }
    }

    return {'buyQty': buyQty, 'freeQty': freeQty};
  }

  int get buyQuantity => bogoStats['buyQty'] ?? 1;
  int get freePerSetQuantity => bogoStats['freeQty'] ?? 1;

  int get paidQuantity {
    if (!isBuyOffer) return quantity;

    int buyQty = buyQuantity;
    int freeQty = freePerSetQuantity;

    int totalSet = buyQty + freeQty;
    int sets = quantity ~/ totalSet;
    int remainder = quantity % totalSet;
    int paid = (sets * buyQty) + (remainder > buyQty ? buyQty : remainder);
    return paid;
  }

  int get freeQuantity => quantity - paidQuantity;

  double get totalPrice => unitPrice * paidQuantity;
}

class CartProvider extends ChangeNotifier {
  final List<CartItem> _items = [];

  // Selected Location
  String _selectedCountry = 'Bangladesh';
  String _selectedDistrict = 'Tangail';
  String _selectedArea = 'Akur Takur Para';
  String _addressDetails = '';
  double _customDeliveryCharge = 60.0;
  bool _freeDeliveryActive = false;
  double _freeDeliveryMinAmount = 1000.0;
  int _maxOrderQtyProduct = 0;
  int _maxOrderQtyPackage = 0;
  String? _lastError;

  CartProvider() {
    refreshDeliveryCharge();
    _initPersistenceAndSync();
  }

  String _activeCustomerPhone = '';
  String _lastSyncedServerTs = '';
  DateTime _lastLocalMutationAt = DateTime.fromMillisecondsSinceEpoch(0);
  Timer? _cartSyncTimer;
  Timer? _pushDebounceTimer;
  bool _isSyncing = false;

  Future<void> _initPersistenceAndSync() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final savedPhone = (prefs.getString('user_phone') ?? '').trim();
      final isDeliveryMan = prefs.getBool('is_delivery_man') ?? false;
      if (!isDeliveryMan) {
        _activeCustomerPhone = savedPhone;
      }
      _lastSyncedServerTs = prefs.getString('cart_sync_ts_$_activeCustomerPhone') ?? '';
      final rawCart = prefs.getString('local_cart_items') ?? '';
      if (rawCart.isNotEmpty && _items.isEmpty) {
        final decoded = jsonDecode(rawCart);
        if (decoded is List) {
          for (final entry in decoded) {
            if (entry is Map) {
              _items.add(_cartItemFromMap(Map<String, dynamic>.from(entry)));
            }
          }
          notifyListeners();
        }
      }
    } catch (_) {}
    if (_activeCustomerPhone.isNotEmpty) {
      await syncWithServer();
      _startPeriodicSync();
    }
  }

  void _startPeriodicSync() {
    _cartSyncTimer?.cancel();
    if (_activeCustomerPhone.isEmpty) return;
    _cartSyncTimer = Timer.periodic(const Duration(seconds: 4), (_) {
      syncWithServer();
    });
  }

  Future<void> onCustomerSessionChanged({String? phone}) async {
    final prefs = await SharedPreferences.getInstance();
    final isDeliveryMan = prefs.getBool('is_delivery_man') ?? false;
    final nextPhone = isDeliveryMan ? '' : (phone ?? prefs.getString('user_phone') ?? '').trim();
    if (nextPhone == _activeCustomerPhone) {
      if (nextPhone.isNotEmpty) {
        await syncWithServer();
        _startPeriodicSync();
      }
      return;
    }
    _activeCustomerPhone = nextPhone;
    _lastSyncedServerTs = nextPhone.isNotEmpty
        ? (prefs.getString('cart_sync_ts_$nextPhone') ?? '')
        : '';
    if (nextPhone.isEmpty) {
      _cartSyncTimer?.cancel();
      _pushDebounceTimer?.cancel();
    } else {
      await syncWithServer();
      _startPeriodicSync();
    }
  }

  static int _toInt(dynamic v, [int fb = 0]) {
    if (v == null) return fb;
    if (v is int) return v;
    if (v is num) return v.toInt();
    return int.tryParse(v.toString()) ?? fb;
  }

  static double _toDouble(dynamic v, [double fb = 0.0]) {
    if (v == null) return fb;
    if (v is double) return v;
    if (v is num) return v.toDouble();
    return double.tryParse(v.toString()) ?? fb;
  }

  CartItem _cartItemFromMap(Map<String, dynamic> m) {
    final bool isPkg = m['is_package'] == true || m['package_id'] != null;
    final int rawId = _toInt(m['product_id'] ?? m['id']);
    final int? pkgId = m['package_id'] != null ? _toInt(m['package_id']).abs() : (isPkg ? rawId.abs() : null);
    final int prodId = isPkg ? -(pkgId ?? rawId.abs()).abs() : rawId;
    final double price = _toDouble(m['price'] ?? m['sell_price'] ?? m['unit_price']);
    final double mrp = _toDouble(m['mrp'], price);
    final int stock = _toInt(m['stock_qty'], 99);
    final int qty = _toInt(m['quantity'], 1);

    final product = Product(
      id: prodId,
      packageId: pkgId,
      sku: (m['sku'] ?? '').toString(),
      name: (m['name'] ?? m['product_name'] ?? 'Item').toString(),
      mrp: mrp > 0 ? mrp : price,
      sellPrice: price,
      stockQty: stock,
      imageUrl: (m['image_url'] ?? m['img'] ?? '').toString(),
      offerTitle: (m['offer_title'] ?? '').toString(),
      offerType: (m['offer_type'] ?? '').toString(),
      offerValue: (m['offer_value'] ?? '').toString(),
      offerBase: (m['offer_base'] ?? 'mrp').toString(),
    );
    return CartItem(product: product, quantity: qty > 0 ? qty : 1);
  }

  List<Map<String, dynamic>> _serializeItems() {
    return _items.map((it) {
      final p = it.product;
      final bool isPkg = p.isPackage;
      final int? pkgId = p.packageId ?? (isPkg ? p.id.abs() : null);
      return {
        'id': isPkg ? -(pkgId ?? p.id.abs()) : p.id,
        'product_id': isPkg ? -(pkgId ?? p.id.abs()) : p.id,
        'package_id': pkgId,
        'is_package': isPkg,
        'sku': p.sku,
        'name': p.name,
        'price': p.sellPrice,
        'mrp': p.mrp,
        'quantity': it.quantity,
        'stock_qty': p.stockQty,
        'image_url': p.imageUrl,
        'offer_type': p.offerType,
        'offer_value': p.offerValue,
        'offer_title': p.offerTitle,
        'offer_base': p.offerBase,
      };
    }).toList();
  }

  Future<void> _saveLocalOnly() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString('local_cart_items', jsonEncode(_serializeItems()));
    } catch (_) {}
  }

  void _schedulePushToServer({bool immediate = false}) {
    _lastLocalMutationAt = DateTime.now();
    _saveLocalOnly();
    if (_activeCustomerPhone.isEmpty) return;
    _pushDebounceTimer?.cancel();
    if (immediate) {
      _pushToServerNow();
    } else {
      _pushDebounceTimer = Timer(const Duration(milliseconds: 150), _pushToServerNow);
    }
  }

  Future<void> _pushToServerNow() async {
    if (_activeCustomerPhone.isEmpty) return;
    try {
      final payload = _serializeItems();
      final res = await ApiService.syncServerCart(_activeCustomerPhone, payload);
      if (res != null && res['success'] == true) {
        final ts = (res['updated_at'] ?? '').toString();
        if (ts.isNotEmpty) {
          _lastSyncedServerTs = ts;
          final prefs = await SharedPreferences.getInstance();
          await prefs.setString('cart_sync_ts_$_activeCustomerPhone', ts);
        }
      }
    } catch (_) {}
  }

  Future<void> syncWithServer() async {
    if (_activeCustomerPhone.isEmpty || _isSyncing) return;
    if (DateTime.now().difference(_lastLocalMutationAt).inMilliseconds < 1500) return;
    _isSyncing = true;
    try {
      final data = await ApiService.fetchServerCart(_activeCustomerPhone);
      if (data == null || data['success'] != true) return;
      final String serverTs = (data['updated_at'] ?? '').toString();
      final List<dynamic> serverItems = data['items'] as List<dynamic>? ?? [];

      if (serverTs.isEmpty && _items.isNotEmpty) {
        // First time syncing while app already holds local items
        await _pushToServerNow();
        return;
      }

      if (serverTs.isNotEmpty && serverTs != _lastSyncedServerTs) {
        // Only apply server snapshot if another local edit did not start mid-request
        if (DateTime.now().difference(_lastLocalMutationAt).inMilliseconds >= 1200) {
          _items
            ..clear()
            ..addAll(serverItems.whereType<Map>().map((e) => _cartItemFromMap(Map<String, dynamic>.from(e))));
          _lastSyncedServerTs = serverTs;
          final prefs = await SharedPreferences.getInstance();
          await prefs.setString('cart_sync_ts_$_activeCustomerPhone', serverTs);
          await _saveLocalOnly();
          notifyListeners();
        }
      }
    } catch (_) {
    } finally {
      _isSyncing = false;
    }
  }

  @override
  void dispose() {
    _cartSyncTimer?.cancel();
    _pushDebounceTimer?.cancel();
    super.dispose();
  }

  void refreshDeliveryCharge() async {
    var settings = await ApiService.fetchShopSettings();
    if (settings.containsKey("delivery_charge")) {
      double val = double.tryParse(settings["delivery_charge"].toString()) ?? 60.0;
      _customDeliveryCharge = val;
    }
    if (settings.containsKey("free_delivery_active")) {
      _freeDeliveryActive = settings["free_delivery_active"].toString() == "1" || settings["free_delivery_active"].toString() == "true";
    }
    if (settings.containsKey("free_delivery_min_amount")) {
      _freeDeliveryMinAmount = double.tryParse(settings["free_delivery_min_amount"].toString()) ?? 1000.0;
    }
    if (settings.containsKey("max_order_qty_product")) {
      _maxOrderQtyProduct = int.tryParse(settings["max_order_qty_product"].toString()) ?? 0;
    }
    if (settings.containsKey("max_order_qty_package")) {
      _maxOrderQtyPackage = int.tryParse(settings["max_order_qty_package"].toString()) ?? 0;
    }
    notifyListeners();
  }

  List<CartItem> get items => _items;
  int get maxOrderQtyProduct => _maxOrderQtyProduct;
  int get maxOrderQtyPackage => _maxOrderQtyPackage;
  String? get lastError => _lastError;

  String get selectedCountry => _selectedCountry;
  String get selectedDistrict => _selectedDistrict;
  String get selectedArea => _selectedArea;
  String get addressDetails => _addressDetails;

  int get totalItemCount => _items.fold(0, (sum, i) => sum + i.quantity);

  double get subtotal => _items.fold(0.0, (sum, i) => sum + i.totalPrice);
  
  bool get isFreeDelivery => _freeDeliveryActive && subtotal >= _freeDeliveryMinAmount;
  bool get freeDeliveryActive => _freeDeliveryActive;
  double get freeDeliveryMinAmount => _freeDeliveryMinAmount;
  double get baseDeliveryCharge => _items.isEmpty ? 0.0 : _customDeliveryCharge;
  
  double get deliveryCharge => _items.isEmpty ? 0.0 : (isFreeDelivery ? 0.0 : _customDeliveryCharge);
  double get grandTotal => subtotal + deliveryCharge;

  void setLocation(String country, String district, String area, {String details = ''}) {
    _selectedCountry = country;
    _selectedDistrict = district;
    _selectedArea = area;
    if (details.isNotEmpty) _addressDetails = details;
    notifyListeners();
  }

  bool addToCart(Product product) {
    _lastError = null;
    if (product.stockQty <= 0) {
      _lastError = 'Sorry, "${product.name}" is OUT OF STOCK.';
      return false;
    }

    bool isPkg = product.isPackage || product.name.startsWith('📦');
    int maxLimit = isPkg ? _maxOrderQtyPackage : _maxOrderQtyProduct;

    int index = _items.indexWhere((i) => i.product.id == product.id && (i.product.isPackage == isPkg));
    int currentQty = index >= 0 ? _items[index].quantity : 0;

    if (maxLimit > 0 && (currentQty + 1) > maxLimit) {
      String typeLabel = isPkg ? 'Combo Package' : 'product';
      _lastError = 'Maximum order limit reached: You can order at most $maxLimit units of $typeLabel "${product.name}" per order.';
      return false;
    }

    if (index >= 0) {
      if (_items[index].quantity >= product.stockQty) {
        _lastError = 'Cannot add more: only ${product.stockQty} available in stock.';
        return false;
      }
      _items[index].quantity++;
    } else {
      _items.add(CartItem(product: product));
    }
    notifyListeners();
    _schedulePushToServer();
    return true;
  }

  bool updateQuantity(int productId, int quantity, {bool? isPackage}) {
    _lastError = null;
    int index;
    if (isPackage != null) {
      index = _items.indexWhere((i) => i.product.id == productId && (i.product.isPackage == isPackage));
    } else {
      index = _items.indexWhere((i) => i.product.id == productId);
    }
    if (index >= 0) {
      if (quantity <= 0) {
        _items.removeAt(index);
        notifyListeners();
        _schedulePushToServer();
        return true;
      } else {
        final prod = _items[index].product;
        bool isPkg = prod.isPackage || prod.name.startsWith('📦');
        int maxLimit = isPkg ? _maxOrderQtyPackage : _maxOrderQtyProduct;

        if (maxLimit > 0 && quantity > maxLimit) {
          String typeLabel = isPkg ? 'Combo Package' : 'product';
          _lastError = 'Maximum order limit reached: You can order at most $maxLimit units of $typeLabel "${prod.name}" per order.';
          return false;
        }

        if (quantity > prod.stockQty) {
          _lastError = 'Cannot add more: only ${prod.stockQty} available in stock.';
          return false;
        }
        _items[index].quantity = quantity;
        notifyListeners();
        _schedulePushToServer();
        return true;
      }
    }
    return false;
  }

  void clearCart({bool syncToServer = true}) {
    _items.clear();
    notifyListeners();
    if (syncToServer) {
      _schedulePushToServer(immediate: true);
    } else {
      _saveLocalOnly();
    }
  }
}
