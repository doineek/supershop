class AppNotification {
  final int id;
  final String customerPhone;
  final String title;
  final String message;
  final String type; // 'order', 'pharmacy_quote', 'offer', 'suggestion', 'general'
  final String referenceId;
  bool isRead;
  final bool isImportant;
  final String createdAt;

  AppNotification({
    required this.id,
    required this.customerPhone,
    required this.title,
    required this.message,
    required this.type,
    required this.referenceId,
    required this.isRead,
    this.isImportant = false,
    required this.createdAt,
  });

  bool get isOrderRelated {
    final t = type.toLowerCase().trim();
    return t == 'order' || t == 'pharmacy_quote' || t == 'pharmacy' || t == 'order_confirmation';
  }

  factory AppNotification.fromJson(Map<String, dynamic> json) {
    final t = json['type']?.toString() ?? 'general';
    final imp = json['is_important'] == true || json['is_important'] == 1 || t == 'pharmacy_quote';
    return AppNotification(
      id: json['id'] is int ? json['id'] : int.tryParse(json['id']?.toString() ?? '0') ?? 0,
      customerPhone: json['customer_phone']?.toString() ?? '',
      title: json['title']?.toString() ?? 'Notification',
      message: json['message']?.toString() ?? '',
      type: t,
      referenceId: json['reference_id']?.toString() ?? '',
      isRead: json['is_read'] == 1 || json['is_read'] == true,
      isImportant: imp,
      createdAt: json['created_at']?.toString() ?? '',
    );
  }

  Map<String, dynamic> toJson() {
    return {
      'id': id,
      'customer_phone': customerPhone,
      'title': title,
      'message': message,
      'type': type,
      'reference_id': referenceId,
      'is_read': isRead ? 1 : 0,
      'is_important': isImportant,
      'created_at': createdAt,
    };
  }
}
