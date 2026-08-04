import 'dart:async';
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import '../models/product.dart';
import '../models/delivery_area.dart';
import '../models/online_order.dart';

class ApiService {
  static String _customUrl = "";

  static void setServerUrl(String url) {
    _customUrl = url.trim();
  }

  /// Dynamic Base URL:
  /// - Global 24/7 Online Production Server: https://supershop-mj0g.onrender.com
  /// - Web / Chrome: http://127.0.0.1:5000
  static String get baseUrl {
    if (_customUrl.isNotEmpty) {
      return _customUrl;
    }
    if (kIsWeb) {
      String host = Uri.base.host.isNotEmpty ? Uri.base.host : "127.0.0.1";
      return "http://$host:5000";
    }
    return "https://supershop-mj0g.onrender.com";
  }

  static Future<Map<String, dynamic>> fetchShopSettings() async {
    try {
      final response = await http.get(Uri.parse('$baseUrl/api/settings'));
      if (response.statusCode == 200) {
        return jsonDecode(response.body);
      }
    } catch (e) {
      debugPrint("Error fetching shop settings: $e");
    }
    return {
      "shop_name": "DOINEEK দৈনিক",
      "shop_phone": "+880-1XXX-XXXXXX",
      "shop_address": "House 12, Road 5, Tangail",
    };
  }

  static Future<Map<String, String>> fetchStorePolicies() async {
    try {
      final response = await http.get(Uri.parse('$baseUrl/api/settings/policies'));
      if (response.statusCode == 200) {
        Map<String, dynamic> data = jsonDecode(response.body);
        return data.map((key, value) => MapEntry(key, value.toString()));
      }
    } catch (e) {
      debugPrint("Error fetching store policies: $e");
    }
    return {};
  }

  static Future<List<Product>> fetchProducts() async {
    try {
      final response = await http.get(Uri.parse('$baseUrl/api/products'));
      if (response.statusCode == 200) {
        List<dynamic> data = jsonDecode(response.body);
        return data.map((json) => Product.fromJson(json)).toList();
      }
    } catch (e) {
      debugPrint("Error fetching products: $e");
    }
    return [];
  }

  /// Real-time Auto Data Stream for Products (Pulls latest data every 5 seconds)
  static Stream<List<Product>> productsStream() async* {
    while (true) {
      yield await fetchProducts();
      await Future.delayed(const Duration(seconds: 5));
    }
  }

  static Future<List<DeliveryArea>> fetchDeliveryAreas() async {
    try {
      final response = await http.get(Uri.parse('$baseUrl/api/delivery-areas'));
      if (response.statusCode == 200) {
        List<dynamic> data = jsonDecode(response.body);
        return data.map((json) => DeliveryArea.fromJson(json)).toList();
      }
    } catch (e) {
      debugPrint("Error fetching delivery areas: $e");
    }
    return [];
  }

  static Future<Map<String, dynamic>> placeOrder({
    required String customerName,
    required String customerPhone,
    required String customerEmail,
    required String country,
    required String district,
    required String area,
    required String addressDetails,
    required String paymentMethod,
    required List<Map<String, dynamic>> cartItems,
  }) async {
    try {
      final response = await http.post(
        Uri.parse('$baseUrl/api/orders/place'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'customer_name': customerName,
          'customer_phone': customerPhone,
          'customer_email': customerEmail,
          'country': country,
          'district': district,
          'area': area,
          'address_details': addressDetails,
          'payment_method': paymentMethod,
          'cart_items': cartItems,
        }),
      );

      final body = jsonDecode(response.body);
      if (response.statusCode == 200) {
        return body;
      } else {
        return {'success': false, 'message': body['message'] ?? 'Failed to place order'};
      }
    } catch (e) {
      return {'success': false, 'message': 'Network connection error: $e'};
    }
  }

  static Future<List<OnlineOrder>> fetchMyOrders(String phone) async {
    try {
      final response = await http.get(Uri.parse('$baseUrl/api/orders/my-orders?phone=$phone'));
      if (response.statusCode == 200) {
        List<dynamic> data = jsonDecode(response.body);
        return data.map((json) => OnlineOrder.fromJson(json)).toList();
      }
    } catch (e) {
      debugPrint("Error fetching my orders: $e");
    }
    return [];
  }

  /// Real-time Auto Data Stream for Customer Orders (Pulls latest status every 3 seconds)
  static Stream<List<OnlineOrder>> myOrdersStream(String phone) async* {
    while (true) {
      yield await fetchMyOrders(phone);
      await Future.delayed(const Duration(seconds: 3));
    }
  }

  static Future<List<OnlineOrder>> fetchDeliveryOrders() async {
    try {
      final response = await http.get(Uri.parse('$baseUrl/api/orders/delivery-orders'));
      if (response.statusCode == 200) {
        List<dynamic> data = jsonDecode(response.body);
        return data.map((json) => OnlineOrder.fromJson(json)).toList();
      }
    } catch (e) {
      debugPrint("Error fetching delivery orders: $e");
    }
    return [];
  }

  static Future<Map<String, dynamic>> verifyDeliveryOtp(String orderNumber, String otp) async {
    try {
      final response = await http.post(
        Uri.parse('$baseUrl/api/delivery/verify-otp'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'order_number': orderNumber,
          'otp': otp,
        }),
      );
      return jsonDecode(response.body);
    } catch (e) {
      return {'success': false, 'message': 'Network error: $e'};
    }
  }

  static Future<Map<String, dynamic>> login({
    required String phone,
    required String password,
    bool isDeliveryMan = false,
  }) async {
    try {
      final response = await http.post(
        Uri.parse('$baseUrl/api/auth/login'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'phone': phone,
          'password': password,
          'is_delivery_man': isDeliveryMan,
        }),
      );
      return jsonDecode(response.body);
    } catch (e) {
      return {'success': false, 'message': 'Network error: $e'};
    }
  }

  static Future<Map<String, dynamic>> register({
    required String phone,
    required String name,
    String email = '',
    required String password,
  }) async {
    try {
      final response = await http.post(
        Uri.parse('$baseUrl/api/auth/register'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'phone': phone,
          'name': name,
          'email': email,
        }),
      );
      return jsonDecode(response.body);
    } catch (e) {
      return {'success': false, 'message': 'Network error: $e'};
    }
  }

  static Future<Map<String, dynamic>> cancelOrder({
    required String orderNumber,
    required String phone,
  }) async {
    try {
      final response = await http.post(
        Uri.parse('$baseUrl/api/orders/cancel'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'order_number': orderNumber,
          'customer_phone': phone,
        }),
      );
      return jsonDecode(response.body);
    } catch (e) {
      return {'success': false, 'message': 'Network error: $e'};
    }
  }

  static Future<Map<String, dynamic>> changePassword({
    required String phone,
    required String oldPassword,
    required String newPassword,
  }) async {
    try {
      final response = await http.post(
        Uri.parse('$baseUrl/api/auth/change-password'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'phone': phone,
          'old_password': oldPassword,
          'new_password': newPassword,
        }),
      );
      return jsonDecode(response.body);
    } catch (e) {
      return {'success': false, 'message': 'Network error: $e'};
    }
  }

  static Future<Map<String, dynamic>> resetForgotPassword({
    required String phone,
    required String newPassword,
  }) async {
    try {
      final response = await http.post(
        Uri.parse('$baseUrl/api/auth/forgot-password/reset'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'phone': phone,
          'new_password': newPassword,
        }),
      );
      return jsonDecode(response.body);
    } catch (e) {
      return {'success': false, 'message': 'Network error: $e'};
    }
  }

  static Future<Map<String, dynamic>> sendCustomerOtp({
    required String phone,
    String purpose = 'registration',
  }) async {
    try {
      final response = await http.post(
        Uri.parse('$baseUrl/api/customer/send-otp'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'phone': phone,
          'purpose': purpose,
        }),
      );
      return jsonDecode(response.body);
    } catch (e) {
      return {'success': false, 'message': 'Network error: $e'};
    }
  }

  static Future<Map<String, dynamic>> verifyCustomerOtp({
    required String phone,
    required String otp,
  }) async {
    try {
      final response = await http.post(
        Uri.parse('$baseUrl/api/customer/verify-otp'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'phone': phone,
          'otp': otp,
        }),
      );
      return jsonDecode(response.body);
    } catch (e) {
      return {'success': false, 'message': 'Network error: $e'};
    }
  }

  static Future<Map<String, dynamic>> acceptRiderOrder({
    required int orderId,
    required String riderName,
    required String riderPhone,
  }) async {
    try {
      final response = await http.post(
        Uri.parse('$baseUrl/api/rider/accept-order'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'order_id': orderId,
          'rider_name': riderName,
          'rider_phone': riderPhone,
        }),
      );
      if (response.statusCode == 200) {
        return jsonDecode(response.body);
      }
      var decoded = jsonDecode(response.body);
      return {'success': false, 'message': decoded['message'] ?? 'Failed to accept order'};
    } catch (e) {
      return {'success': false, 'message': 'Network error: $e'};
    }
  }

  static Future<Map<String, dynamic>> updateRiderOrderStatus({
    required int orderId,
    required String status,
    String otp = '',
  }) async {
    try {
      final response = await http.post(
        Uri.parse('$baseUrl/api/rider/update-order-status'),
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({
          'order_id': orderId,
          'status': status,
          'otp': otp,
        }),
      );
      if (response.statusCode == 200) {
        return jsonDecode(response.body);
      }
      var decoded = jsonDecode(response.body);
      return {'success': false, 'message': decoded['message'] ?? 'Failed to update order status'};
    } catch (e) {
      return {'success': false, 'message': 'Network error: $e'};
    }
  }
}
