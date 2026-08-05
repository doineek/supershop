import '../services/api_service.dart';

class Product {
  final int id;
  final String sku;
  final String name;
  final String brand;
  final int? categoryId;
  final String categoryName;
  final double mrp;
  final double sellPrice;
  final int stockQty;
  final String description;
  final String imageUrl;
  final bool isTrending;
  final bool isFlashSale;
  final bool isOffer;
  final String offerTitle;
  final String offerType;
  final String offerValue;
  final String offerBase; // 'mrp' or 'doineek'

  Product({
    required this.id,
    required this.sku,
    required this.name,
    this.brand = '',
    this.categoryId,
    this.categoryName = '',
    required this.mrp,
    required this.sellPrice,
    required this.stockQty,
    this.description = '',
    this.imageUrl = '',
    this.isTrending = false,
    this.isFlashSale = false,
    this.isOffer = false,
    this.offerTitle = '',
    this.offerType = '',
    this.offerValue = '',
    this.offerBase = 'mrp',
  });

  List<String> get imageList {
    if (imageUrl.isEmpty) return [];
    List<String> rawList = imageUrl.split(',').map((e) => e.trim()).where((e) => e.isNotEmpty).toList();
    List<String> result = [];
    for (var img in rawList) {
      if (img.startsWith('/')) {
        img = '${ApiService.baseUrl}$img';
      } else if (img.contains('127.0.0.1') && ApiService.baseUrl.contains('10.0.2.2')) {
        img = img.replaceFirst('127.0.0.1', '10.0.2.2');
      }
      result.add(img);
    }
    return result;
  }

  /// Calculates effective selling price based on Discount Base (MRP vs Doineek Price)
  double get effectivePrice {
    if (isOffer && offerType == 'percentage') {
      double pct = double.tryParse(offerValue) ?? 0.0;
      if (pct > 0) {
        if (offerBase == 'doineek') {
          return sellPrice - (sellPrice * (pct / 100.0));
        } else {
          double baseMrp = mrp > 0 ? mrp : sellPrice;
          return baseMrp - (baseMrp * (pct / 100.0));
        }
      }
    }
    return sellPrice;
  }

  factory Product.fromJson(Map<String, dynamic> json) {
    String img = (json['image_url'] ?? '').toString().trim();

    return Product(
      id: json['id'] ?? 0,
      sku: json['sku'] ?? '',
      name: json['name'] ?? '',
      brand: json['brand'] ?? '',
      categoryId: json['category_id'],
      categoryName: json['category_name'] ?? '',
      mrp: (json['mrp'] ?? 0).toDouble(),
      sellPrice: (json['sell_price'] ?? 0).toDouble(),
      stockQty: json['stock_qty'] ?? 0,
      description: json['description'] ?? '',
      imageUrl: img,
      isTrending: (json['is_trending'] ?? 0) == 1,
      isFlashSale: (json['is_flash_sale'] ?? 0) == 1,
      isOffer: (json['is_offer'] ?? 0) == 1,
      offerTitle: json['offer_title'] ?? '',
      offerType: json['offer_type'] ?? '',
      offerValue: (json['offer_value'] ?? '').toString(),
      offerBase: (json['offer_base'] ?? 'mrp').toString(),
    );
  }
}
