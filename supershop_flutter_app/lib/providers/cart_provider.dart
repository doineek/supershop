import 'package:flutter/material.dart';
import '../models/product.dart';
import '../services/api_service.dart';

class CartItem {
  final Product product;
  int quantity;

  CartItem({required this.product, this.quantity = 1});

  double get unitPrice => product.effectivePrice;

  bool get isBuyOffer {
    String ot = product.offerType.toLowerCase();
    String title = product.offerTitle.toLowerCase();
    return ot == 'buy_x_get_y' || ot == 'bogo' || title.contains('buy');
  }

  int get paidQuantity {
    if (!isBuyOffer) return quantity;
    int buyQty = 2;
    int freeQty = 1;
    if (product.offerValue.contains(',')) {
      var parts = product.offerValue.split(',').map((e) => int.tryParse(e.trim()) ?? 0).toList();
      if (parts.length >= 2 && parts[0] > 0 && parts[1] > 0) {
        buyQty = parts[0];
        freeQty = parts[1];
      }
    }
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

  CartProvider() {
    refreshDeliveryCharge();
  }

  void refreshDeliveryCharge() async {
    var settings = await ApiService.fetchShopSettings();
    if (settings.containsKey("delivery_charge")) {
      double val = double.tryParse(settings["delivery_charge"].toString()) ?? 60.0;
      _customDeliveryCharge = val;
      notifyListeners();
    }
  }

  List<CartItem> get items => _items;

  String get selectedCountry => _selectedCountry;
  String get selectedDistrict => _selectedDistrict;
  String get selectedArea => _selectedArea;
  String get addressDetails => _addressDetails;

  int get totalItemCount => _items.fold(0, (sum, i) => sum + i.quantity);

  double get subtotal => _items.fold(0.0, (sum, i) => sum + i.totalPrice);
  double get deliveryCharge => _items.isEmpty ? 0.0 : _customDeliveryCharge;
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
