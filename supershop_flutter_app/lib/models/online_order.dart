class OrderItem {
  final int id;
  final int productId;
  final String productName;
  final double unitPrice;
  final double mrpPrice;
  final int quantity;
  final double totalPrice;

  OrderItem({
    required this.id,
    required this.productId,
    required this.productName,
    required this.unitPrice,
    required this.mrpPrice,
    required this.quantity,
    required this.totalPrice,
  });

  factory OrderItem.fromJson(Map<String, dynamic> json) {
    return OrderItem(
      id: json['id'] ?? 0,
      productId: json['product_id'] ?? 0,
      productName: json['product_name'] ?? '',
      unitPrice: (json['unit_price'] ?? 0).toDouble(),
      mrpPrice: (json['mrp_price'] ?? 0).toDouble(),
      quantity: json['quantity'] ?? 1,
      totalPrice: (json['total_price'] ?? 0).toDouble(),
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
  final String createdAt;
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
    required this.createdAt,
    required this.items,
  });

  factory OnlineOrder.fromJson(Map<String, dynamic> json) {
    var rawItems = json['items'] as List? ?? [];
    List<OrderItem> itemList = rawItems.map((i) => OrderItem.fromJson(i)).toList();

    return OnlineOrder(
      id: json['id'] ?? 0,
      orderNumber: json['order_number'] ?? '',
      customerName: json['customer_name'] ?? '',
      customerPhone: json['customer_phone'] ?? '',
      customerEmail: json['customer_email'] ?? '',
      country: json['country'] ?? 'Bangladesh',
      district: json['district'] ?? '',
      area: json['area'] ?? '',
      addressDetails: json['address_details'] ?? '',
      paymentMethod: json['payment_method'] ?? 'cod',
      paymentStatus: json['payment_status'] ?? 'pending',
      subtotal: (json['subtotal'] ?? 0).toDouble(),
      deliveryCharge: (json['delivery_charge'] ?? 0).toDouble(),
      totalAmount: (json['total_amount'] ?? 0).toDouble(),
      orderStatus: json['order_status'] ?? 'new',
      deliveryOtp: json['delivery_otp'] ?? '',
      createdAt: json['created_at'] ?? '',
      items: itemList,
    );
  }
}
