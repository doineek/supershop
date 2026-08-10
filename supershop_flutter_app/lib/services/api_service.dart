import 'dart:async';
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:http/http.dart' as http;
import 'package:shared_preferences/shared_preferences.dart';
import '../models/product.dart';
import '../models/delivery_area.dart';
import '../models/online_order.dart';

class ApiService {
  static String _customUrl = "";
  static String _activeUrl = "";

  static Future<void> initServerUrl() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      String saved = prefs.getString('server_url') ?? '';
      if (saved.isNotEmpty) {
        _customUrl = saved.trim();
      }
    } catch (_) {}
  }

  static Future<void> setServerUrl(String url) async {
    _customUrl = url.trim();
    _activeUrl = "";
    try {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString('server_url', _customUrl);
    } catch (_) {}
  }

  /// Candidate server URLs in priority order for global & local connectivity
  static List<String> get candidateUrls {
    List<String> list = [];
    if (_customUrl.isNotEmpty) {
      list.add(_customUrl);
    }
    if (_activeUrl.isNotEmpty && !list.contains(_activeUrl)) {
      list.add(_activeUrl);
    }
    if (kIsWeb) {
      String host = Uri.base.host.isNotEmpty ? Uri.base.host : "127.0.0.1";
      String webUrl = "http://$host:5000";
      if (!list.contains(webUrl)) list.add(webUrl);
    }
    // 1. Global 24/7 Online Production Server (accessible from anywhere on 4G, 5G, Wi-Fi)
    const String cloudUrl = "https://supershop-mj0g.onrender.com";
    if (!list.contains(cloudUrl)) list.add(cloudUrl);

    // 2. Direct Local Wi-Fi network IPs of PC (fallback when on same Wi-Fi)
    final localIps = [
      "http://192.168.0.102:5000",
      "http://192.168.0.100:5000",
      "http://192.168.0.101:5000",
      "http://192.168.0.103:5000",
      "http://192.168.1.102:5000",
      "http://192.168.1.100:5000",
      "http://127.0.0.1:5000",
      "http://10.0.2.2:5000"
    ];

    for (var ip in localIps) {
      if (!list.contains(ip)) list.add(ip);
    }
    return list;
  }

  static String get baseUrl {
    return _activeUrl.isNotEmpty ? _activeUrl : candidateUrls.first;
  }

  static Future<http.Response?> httpGet(String path, {Duration timeout = const Duration(seconds: 4)}) async {
    for (String serverUrl in candidateUrls) {
      try {
        final res = await http.get(Uri.parse('$serverUrl$path')).timeout(timeout);
        if (res.statusCode == 200) {
          _activeUrl = serverUrl;
          return res;
        }
      } catch (_) {}
    }
    return null;
  }

  static Future<http.Response?> httpPost(String path, {Map<String, String>? headers, Object? body, Duration timeout = const Duration(seconds: 6)}) async {
    for (String serverUrl in candidateUrls) {
      try {
        final res = await http.post(
          Uri.parse('$serverUrl$path'),
          headers: headers ?? {'Content-Type': 'application/json'},
          body: body,
        ).timeout(timeout);

        if (res.statusCode >= 200 && res.statusCode < 500) {
          _activeUrl = serverUrl;
          return res;
        }
      } catch (_) {}
    }
    return null;
  }

  static Future<Map<String, dynamic>> fetchShopSettings() async {
    try {
      final res = await httpGet('/api/settings');
      if (res != null && res.statusCode == 200) {
        return jsonDecode(res.body);
      }
    } catch (e) {
      debugPrint("Error fetching shop settings: $e");
    }
    return {
      "shop_name": "DOINEEK Supershop",
      "shop_phone": "+880-1XXX-XXXXXX",
      "shop_address": "House 12, Road 5, Tangail",
    };
  }

  static Future<Map<String, String>> fetchStorePolicies() async {
    try {
      final res = await httpGet('/api/settings/policies');
      if (res != null && res.statusCode == 200) {
        Map<String, dynamic> data = jsonDecode(res.body);
        return data.map((key, value) => MapEntry(key, value.toString()));
      }
    } catch (e) {
      debugPrint("Error fetching store policies: $e");
    }
    return {};
  }

  static Future<List<dynamic>> fetchCategoriesTree() async {
    try {
      final res = await httpGet('/api/categories/tree');
      if (res != null && res.statusCode == 200) {
        return jsonDecode(res.body);
      }
    } catch (e) {
      debugPrint("Error fetching category tree: $e");
    }
    return [];
  }

  static Future<Map<String, dynamic>> fetchPromotions() async {
    try {
      final res = await httpGet('/api/promotions');
      if (res != null && res.statusCode == 200) {
        return jsonDecode(res.body);
      }
    } catch (e) {
      debugPrint("Error fetching promotions: $e");
    }
    return {"interval_sec": 2, "promotions": []};
  }

  static Future<List<Product>> fetchProducts() async {
    try {
      final res = await httpGet('/api/products');
      if (res != null && res.statusCode == 200) {
        List<dynamic> data = jsonDecode(res.body);
        return data.map((json) => Product.fromJson(json)).toList();
      }
    } catch (e) {
      debugPrint("Error fetching products: $e");
    }
    return [];
  }

  static Stream<List<Product>> productsStream() async* {
    while (true) {
      yield await fetchProducts();
      await Future.delayed(const Duration(seconds: 5));
    }
  }

  static Future<List<DeliveryArea>> fetchDeliveryAreas() async {
    try {
      final res = await httpGet('/api/delivery-areas');
      if (res != null && res.statusCode == 200) {
        List<dynamic> data = jsonDecode(res.body);
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
    final payload = jsonEncode({
      'customer_name': customerName,
      'customer_phone': customerPhone,
      'customer_email': customerEmail,
      'country': country,
      'district': district,
      'area': area,
      'address_details': addressDetails,
      'payment_method': paymentMethod,
      'cart_items': cartItems,
    });

    final res = await httpPost('/api/orders/place', body: payload, timeout: const Duration(seconds: 12));
    if (res != null) {
      try {
        final body = jsonDecode(res.body);
        if (res.statusCode == 200) {
          return body;
        } else {
          return {'success': false, 'message': body['message'] ?? 'Failed to place order (${res.statusCode})'};
        }
      } catch (_) {}
    }
    return {'success': false, 'message': 'Network connection error: Unable to connect to server.'};
  }

  static Future<List<OnlineOrder>> fetchMyOrders(String phone) async {
    try {
      final res = await httpGet('/api/orders/my-orders?phone=$phone');
      if (res != null && res.statusCode == 200) {
        List<dynamic> data = jsonDecode(res.body);
        return data.map((json) => OnlineOrder.fromJson(json)).toList();
      }
    } catch (e) {
      debugPrint("Error fetching my orders: $e");
    }
    return [];
  }

  static Stream<List<OnlineOrder>> myOrdersStream(String phone) async* {
    while (true) {
      yield await fetchMyOrders(phone);
      await Future.delayed(const Duration(seconds: 3));
    }
  }

  static Future<List<OnlineOrder>> fetchDeliveryOrders() async {
    try {
      final res = await httpGet('/api/orders/delivery-orders');
      if (res != null && res.statusCode == 200) {
        List<dynamic> data = jsonDecode(res.body);
        return data.map((json) => OnlineOrder.fromJson(json)).toList();
      }
    } catch (e) {
      debugPrint("Error fetching delivery orders: $e");
    }
    return [];
  }

  static Future<Map<String, dynamic>> verifyDeliveryOtp(String orderNumber, String otp) async {
    try {
      final res = await httpPost('/api/delivery/verify-otp', body: jsonEncode({
        'order_number': orderNumber,
        'otp': otp,
      }));
      if (res != null) return jsonDecode(res.body);
    } catch (e) {
      return {'success': false, 'message': 'Network error: $e'};
    }
    return {'success': false, 'message': 'Network error'};
  }

  static Future<Map<String, dynamic>> login({
    required String phone,
    required String password,
    bool isDeliveryMan = false,
  }) async {
    try {
      final res = await httpPost('/api/auth/login', body: jsonEncode({
        'phone': phone,
        'password': password,
        'is_delivery_man': isDeliveryMan,
      }));
      if (res != null) return jsonDecode(res.body);
    } catch (e) {
      return {'success': false, 'message': 'Network error: $e'};
    }
    return {'success': false, 'message': 'Network error'};
  }

  static Future<Map<String, dynamic>> register({
    required String phone,
    required String name,
    String email = '',
    required String password,
  }) async {
    try {
      final res = await httpPost('/api/auth/register', body: jsonEncode({
        'phone': phone,
        'name': name,
        'email': email,
        'password': password,
      }));
      if (res != null) return jsonDecode(res.body);
    } catch (e) {
      return {'success': false, 'message': 'Network error: $e'};
    }
    return {'success': false, 'message': 'Network error'};
  }

  static Future<Map<String, dynamic>> cancelOrder({
    required String orderNumber,
    required String phone,
  }) async {
    try {
      final res = await httpPost('/api/orders/cancel', body: jsonEncode({
        'order_number': orderNumber,
        'customer_phone': phone,
      }));
      if (res != null) return jsonDecode(res.body);
    } catch (e) {
      return {'success': false, 'message': 'Network error: $e'};
    }
    return {'success': false, 'message': 'Network error'};
  }

  static Future<Map<String, dynamic>> changePassword({
    required String phone,
    required String oldPassword,
    required String newPassword,
  }) async {
    try {
      final res = await httpPost('/api/auth/change-password', body: jsonEncode({
        'phone': phone,
        'old_password': oldPassword,
        'new_password': newPassword,
      }));
      if (res != null) return jsonDecode(res.body);
    } catch (e) {
      return {'success': false, 'message': 'Network error: $e'};
    }
    return {'success': false, 'message': 'Network error'};
  }

  static Future<Map<String, dynamic>> resetForgotPassword({
    required String phone,
    required String newPassword,
  }) async {
    try {
      final res = await httpPost('/api/auth/forgot-password/reset', body: jsonEncode({
        'phone': phone,
        'new_password': newPassword,
      }));
      if (res != null) return jsonDecode(res.body);
    } catch (e) {
      return {'success': false, 'message': 'Network error: $e'};
    }
    return {'success': false, 'message': 'Network error'};
  }

  static Future<Map<String, dynamic>> sendCustomerOtp({
    required String phone,
    String purpose = 'registration',
  }) async {
    try {
      final res = await httpPost('/api/customer/send-otp', body: jsonEncode({
        'phone': phone,
        'purpose': purpose,
      }));
      if (res != null) return jsonDecode(res.body);
    } catch (e) {
      return {'success': false, 'message': 'Network error: $e'};
    }
    return {'success': false, 'message': 'Network error'};
  }

  static Future<Map<String, dynamic>> verifyCustomerOtp({
    required String phone,
    required String otp,
  }) async {
    try {
      final res = await httpPost('/api/customer/verify-otp', body: jsonEncode({
        'phone': phone,
        'otp': otp,
      }));
      if (res != null) return jsonDecode(res.body);
    } catch (e) {
      return {'success': false, 'message': 'Network error: $e'};
    }
    return {'success': false, 'message': 'Network error'};
  }

  static Future<Map<String, dynamic>> acceptRiderOrder({
    required int orderId,
    required String riderName,
    required String riderPhone,
  }) async {
    try {
      final res = await httpPost('/api/rider/accept-order', body: jsonEncode({
        'order_id': orderId,
        'rider_name': riderName,
        'rider_phone': riderPhone,
      }));
      if (res != null) return jsonDecode(res.body);
    } catch (e) {
      return {'success': false, 'message': 'Network error: $e'};
    }
    return {'success': false, 'message': 'Network error'};
  }

  static Future<Map<String, dynamic>> updateRiderOrderStatus({
    required int orderId,
    required String status,
    String otp = '',
  }) async {
    try {
      final res = await httpPost('/api/rider/update-order-status', body: jsonEncode({
        'order_id': orderId,
        'status': status,
        'otp': otp,
      }));
      if (res != null) return jsonDecode(res.body);
    } catch (e) {
      return {'success': false, 'message': 'Network error: $e'};
    }
    return {'success': false, 'message': 'Network error'};
  }
}
