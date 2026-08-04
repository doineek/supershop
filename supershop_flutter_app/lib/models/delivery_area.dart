class DeliveryArea {
  final int id;
  final String country;
  final String district;
  final String area;
  final bool isActive;

  DeliveryArea({
    required this.id,
    required this.country,
    required this.district,
    required this.area,
    required this.isActive,
  });

  factory DeliveryArea.fromJson(Map<String, dynamic> json) {
    return DeliveryArea(
      id: json['id'] ?? 0,
      country: json['country'] ?? 'Bangladesh',
      district: json['district'] ?? '',
      area: json['area'] ?? '',
      isActive: (json['is_active'] ?? 1) == 1,
    );
  }
}
