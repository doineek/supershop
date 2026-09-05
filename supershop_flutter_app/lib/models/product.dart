import '../services/api_service.dart';

class Product {
  final int id;
  final String sku;
  final String name;
  final String brand;
  final String unit;
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

  final int? subCategoryId;
  final String subCategoryName;
  final int? subSubCategoryId;
  final String subSubCategoryName;

  Product({
    required this.id,
    required this.sku,
    required this.name,
    this.brand = '',
    this.unit = '',
    this.categoryId,
    this.categoryName = '',
    this.subCategoryId,
    this.subCategoryName = '',
    this.subSubCategoryId,
    this.subSubCategoryName = '',
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

  bool get isPackage => name.startsWith('📦') || sku.toUpperCase() == 'COMBO';

  List<String> get imageList {
    if (imageUrl.isEmpty) return [];
    String raw = imageUrl.trim();
    if (raw.isEmpty) return [];
    if (raw.contains(' || ')) {
      return raw.split(' || ').map((e) => e.trim()).where((e) => e.isNotEmpty).toList();
    }
    RegExp reg = RegExp(r',\s*(?=data:image\/|https?:\/\/|\/static\/|\/uploads\/)', caseSensitive: false);
    List<String> rawList = raw.split(reg).map((e) => e.trim()).where((e) => e.isNotEmpty).toList();
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

  bool get isComboPackage {
    String u = unit.toLowerCase();
    String n = name.toLowerCase();
    String c = categoryName.toLowerCase();
    String d = description.toLowerCase();
    return u.contains('combo') || u.contains('package') ||
           n.contains('📦') || n.contains('combo') || n.contains('package') ||
           c.contains('combo') || c.contains('package') ||
           d.contains('combo') || d.contains('package');
  }

  factory Product.fromJson(Map<String, dynamic> json) {
    String img = (json['image_url'] ?? '').toString().trim();

    return Product(
      id: json['id'] ?? 0,
      sku: json['sku'] ?? '',
      name: json['name'] ?? '',
      brand: json['brand'] ?? '',
      unit: (json['unit'] ?? json['unit_name'] ?? '').toString(),
      categoryId: json['category_id'],
      categoryName: json['category_name'] ?? '',
      subCategoryId: json['sub_category_id'],
      subCategoryName: json['sub_category_name'] ?? '',
      subSubCategoryId: json['sub_sub_category_id'],
      subSubCategoryName: json['sub_sub_category_name'] ?? '',
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

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'sku': sku,
      'name': name,
      'brand': brand,
      'unit': unit,
      'category_id': categoryId,
      'category_name': categoryName,
      'sub_category_id': subCategoryId,
      'sub_category_name': subCategoryName,
      'sub_sub_category_id': subSubCategoryId,
      'sub_sub_category_name': subSubCategoryName,
      'mrp': mrp,
      'sell_price': sellPrice,
      'stock_qty': stockQty,
      'description': description,
      'image_url': imageUrl,
      'is_trending': isTrending ? 1 : 0,
      'is_flash_sale': isFlashSale ? 1 : 0,
      'is_offer': isOffer ? 1 : 0,
      'offer_title': offerTitle,
      'offer_type': offerType,
      'offer_value': offerValue,
      'offer_base': offerBase,
    };
  }
}
