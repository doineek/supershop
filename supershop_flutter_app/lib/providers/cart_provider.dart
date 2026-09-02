import 'package:flutter/material.dart';
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

  CartProvider() {
    refreshDeliveryCharge();
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
    notifyListeners();
  }

  List<CartItem> get items => _items;

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

  void addToCart(Product product) {
    int index = _items.indexWhere((i) => i.product.id == product.id);
    if (index >= 0) {
      _items[index].quantity++;
    } else {
      _items.add(CartItem(product: product));
    }
    notifyListeners();
  }

  void updateQuantity(int productId, int quantity) {
    int index = _items.indexWhere((i) => i.product.id == productId);
    if (index >= 0) {
      if (quantity <= 0) {
        _items.removeAt(index);
      } else {
        _items[index].quantity = quantity;
      }
      notifyListeners();
    }
  }

  void clearCart() {
    _items.clear();
    notifyListeners();
  }
}
