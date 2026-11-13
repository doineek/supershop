int _asInt(dynamic v, [int fallback = 0]) {
  if (v == null) return fallback;
  if (v is int) return v;
  if (v is num) return v.toInt();
  return int.tryParse(v.toString()) ?? double.tryParse(v.toString())?.toInt() ?? fallback;
}

double _asDouble(dynamic v, [double fallback = 0.0]) {
  if (v == null) return fallback;
  if (v is double) return v;
  if (v is num) return v.toDouble();
  return double.tryParse(v.toString()) ?? fallback;
}

bool _asBool(dynamic v, [bool fallback = false]) {
  if (v == null) return fallback;
  if (v is bool) return v;
  final s = v.toString().toLowerCase();
  return s == 'true' || s == '1';
}

String _asStr(dynamic v, [String fallback = '']) {
  if (v == null) return fallback;
  return v.toString();
}

class OrderItem {
  final int id;
  final int productId;
  final String productName;
  final double unitPrice;
  final double mrpPrice;
  final int quantity;
  final double totalPrice;
  final bool isPackage;
  final int packageId;
  final String packageName;
  final double packagePrice;
  final String packageImage;
  final String packageDescription;
  final List<Map<String, dynamic>> packageItems;
  final bool isMedicine;
  final int medicineId;
  final String genericName;
  final String strength;
  final String dosageForm;
  final String imageUrl;

  OrderItem({
    required this.id,
    required this.productId,
    required this.productName,
    required this.unitPrice,
    required this.mrpPrice,
    required this.quantity,
    required this.totalPrice,
    this.isPackage = false,
    this.packageId = 0,
    this.packageName = '',
    this.packagePrice = 0.0,
    this.packageImage = '',
    this.packageDescription = '',
    this.packageItems = const [],
    this.isMedicine = false,
    this.medicineId = 0,
    this.genericName = '',
    this.strength = '',
    this.dosageForm = '',
    this.imageUrl = '',
  });

  factory OrderItem.fromJson(Map<String, dynamic> json) {
    final pName = _asStr(json['product_name']);
    final bool pkgFlag = _asBool(json['is_package']) ||
        _asInt(json['package_id']) > 0 ||
        pName.contains('📦');
    final bool medFlag = _asBool(json['is_medicine']) ||
        _asInt(json['medicine_id']) > 0 ||
        pName.contains('💊');
    final rawPkgItems = json['package_items'];
    final List<Map<String, dynamic>> parsedPkgItems = rawPkgItems is List
        ? rawPkgItems
            .whereType<Map>()
            .map((e) => Map<String, dynamic>.from(e))
            .toList()
        : const [];

    return OrderItem(
      id: _asInt(json['id']),
      productId: _asInt(json['product_id']),
      productName: pName,
      unitPrice: _asDouble(json['unit_price']),
      mrpPrice: _asDouble(json['mrp_price']),
      quantity: _asInt(json['quantity'], 1),
      totalPrice: _asDouble(json['total_price']),
      isPackage: pkgFlag,
      packageId: _asInt(json['package_id']),
      packageName: _asStr(json['package_name']),
      packagePrice: _asDouble(json['package_price']),
      packageImage: _asStr(json['package_image']),
      packageDescription: _asStr(json['package_description']),
      packageItems: parsedPkgItems,
      isMedicine: medFlag,
      medicineId: _asInt(json['medicine_id']),
      genericName: _asStr(json['generic_name']),
      strength: _asStr(json['strength']),
      dosageForm: _asStr(json['dosage_form']),
      imageUrl: _asStr(json['image_url']),
    );
  }
}

class OrderTimelineStep {
  final String stage;
  final String title;
  final String time;
  final String timeBd;
  final bool done;
  final bool active;

  OrderTimelineStep({
    required this.stage,
    required this.title,
    this.time = '',
    this.timeBd = '',
    this.done = false,
    this.active = false,
  });

  factory OrderTimelineStep.fromJson(Map<String, dynamic> json) {
    return OrderTimelineStep(
      stage: _asStr(json['stage'] ?? json['key']),
      title: _asStr(json['title']),
      time: _asStr(json['time']),
      timeBd: _asStr(json['time_bd'] ?? json['time_formatted']),
      done: _asBool(json['done'] ?? json['is_done']),
      active: _asBool(json['active'] ?? json['is_current']),
    );
  }
}

class OnlineOrder {
  final int id;
  final String orderNumber;
  final String customerName;
  final String customerPhone;
  final String customerEmail;
  final String country;
  final String district;
  final String area;
  final String addressDetails;
  final String paymentMethod;
  final String paymentStatus;
  final double subtotal;
  final double deliveryCharge;
  final double totalAmount;
  final String orderStatus;
  final String deliveryOtp;
  final String assignedRiderName;
  final String assignedRiderPhone;
  final String createdAt;
  final String createdAtBd;
  final String confirmedAt;
  final String packedAt;
  final String onTheWayAt;
  final String deliveredAt;
  final String cancelledAt;
  final bool isPharmacyOrder;
  final String prescriptionUrl;
  final String prescriptionOriginalUrl;
  final String prescriptionEnhancedUrl;
  final int overallDurationDays;
  final String customerNotes;
  final String pharmacyOrderType;
  final List<OrderTimelineStep> timeline;
  final List<OrderItem> items;

  OnlineOrder({
    required this.id,
    required this.orderNumber,
    required this.customerName,
    required this.customerPhone,
    required this.customerEmail,
    required this.country,
    required this.district,
    required this.area,
    required this.addressDetails,
    required this.paymentMethod,
    required this.paymentStatus,
    required this.subtotal,
    required this.deliveryCharge,
    required this.totalAmount,
    required this.orderStatus,
    required this.deliveryOtp,
    this.assignedRiderName = '',
    this.assignedRiderPhone = '',
    required this.createdAt,
    this.createdAtBd = '',
    this.confirmedAt = '',
    this.packedAt = '',
    this.onTheWayAt = '',
    this.deliveredAt = '',
    this.cancelledAt = '',
    this.isPharmacyOrder = false,
    this.prescriptionUrl = '',
    this.prescriptionOriginalUrl = '',
    this.prescriptionEnhancedUrl = '',
    this.overallDurationDays = 0,
    this.customerNotes = '',
    this.pharmacyOrderType = '',
    this.timeline = const [],
    required this.items,
  });

  factory OnlineOrder.fromJson(Map<String, dynamic> json) {
    var rawItems = json['items'] as List? ?? [];
    List<OrderItem> itemList = rawItems
        .whereType<Map>()
        .map((i) => OrderItem.fromJson(Map<String, dynamic>.from(i)))
        .toList();

    var rawTimeline = json['timeline'] as List? ?? [];
    List<OrderTimelineStep> timelineList = rawTimeline
        .whereType<Map>()
        .map((t) => OrderTimelineStep.fromJson(Map<String, dynamic>.from(t)))
        .toList();

    final ordNum = _asStr(json['order_number']);
    final rxUrl = _asStr(json['prescription_url']);
    final isPharm = _asBool(json['is_pharmacy_order']) ||
        ordNum.startsWith('RX-') ||
        rxUrl.isNotEmpty;

    return OnlineOrder(
      id: _asInt(json['id']),
      orderNumber: ordNum,
      customerName: _asStr(json['customer_name']),
      customerPhone: _asStr(json['customer_phone']),
      customerEmail: _asStr(json['customer_email']),
      country: _asStr(json['country'], 'Bangladesh'),
      district: _asStr(json['district']),
      area: _asStr(json['area']),
      addressDetails: _asStr(json['address_details']),
      paymentMethod: _asStr(json['payment_method'], 'cod'),
      paymentStatus: _asStr(json['payment_status'], 'pending'),
      subtotal: _asDouble(json['subtotal']),
      deliveryCharge: _asDouble(json['delivery_charge']),
      totalAmount: _asDouble(json['total_amount']),
      orderStatus: _asStr(json['order_status'], 'new'),
      deliveryOtp: _asStr(json['delivery_otp']),
      assignedRiderName: _asStr(json['assigned_rider_name']),
      assignedRiderPhone: _asStr(json['assigned_rider_phone']),
      createdAt: _asStr(json['created_at']),
      createdAtBd: _asStr(json['created_at_bd']),
      confirmedAt: _asStr(json['confirmed_at']),
      packedAt: _asStr(json['packed_at']),
      onTheWayAt: _asStr(json['on_the_way_at']),
      deliveredAt: _asStr(json['delivered_at']),
      cancelledAt: _asStr(json['cancelled_at']),
      isPharmacyOrder: isPharm,
      prescriptionUrl: rxUrl,
      prescriptionOriginalUrl: _asStr(json['prescription_original_url'], rxUrl),
      prescriptionEnhancedUrl: _asStr(json['prescription_enhanced_url'], rxUrl),
      overallDurationDays: _asInt(json['overall_duration_days']),
      customerNotes: _asStr(json['customer_notes']),
      pharmacyOrderType: _asStr(json['pharmacy_order_type']),
      timeline: timelineList,
      items: itemList,
    );
  }
}
