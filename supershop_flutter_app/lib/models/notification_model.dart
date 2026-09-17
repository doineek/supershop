class AppNotification {
  final int id;
  final String customerPhone;
  final String title;
  final String message;
  final String type; // 'order', 'offer', 'suggestion', 'general'
  final String referenceId;
  bool isRead;
  final String createdAt;

  AppNotification({
    required this.id,
    required this.customerPhone,
    required this.title,
    required this.message,
    required this.type,
    required this.referenceId,
    required this.isRead,
    required this.createdAt,
  });

  factory AppNotification.fromJson(Map<String, dynamic> json) {
    return AppNotification(
      id: json['id'] is int ? json['id'] : int.tryParse(json['id']?.toString() ?? '0') ?? 0,
      customerPhone: json['customer_phone']?.toString() ?? '',
      title: json['title']?.toString() ?? 'Notification',
      message: json['message']?.toString() ?? '',
      type: json['type']?.toString() ?? 'general',
      referenceId: json['reference_id']?.toString() ?? '',
      isRead: json['is_read'] == 1 || json['is_read'] == true,
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
      'created_at': createdAt,
    };
  }
}
