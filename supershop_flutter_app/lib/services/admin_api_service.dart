import 'dart:convert';
import 'api_service.dart';

/// Native JSON API client for In-App Admin modules (no external browser launches).
class AdminApiService {
  static const Map<String, String> _jsonHeaders = {
    'Content-Type': 'application/json',
  };

  static Map<String, dynamic> _decodeOrError(
    dynamic res,
    String fallbackMessage,
  ) {
    if (res != null) {
      try {
        final parsed = jsonDecode(res.body);
        if (parsed is Map<String, dynamic>) return parsed;
      } catch (_) {}
    }
    return {'success': false, 'message': fallbackMessage};
  }

  static Future<Map<String, dynamic>> fetchOnlineOrders({
    String dept = 'all',
    String status = 'all',
    String query = '',
  }) async {
    try {
      final path =
          '/api/admin/online-orders?dept=${Uri.encodeComponent(dept)}'
          '&status=${Uri.encodeComponent(status)}'
          '&q=${Uri.encodeComponent(query.trim())}';
      final res = await ApiService.httpGet(path, timeout: const Duration(seconds: 15));
      return _decodeOrError(res, 'অনলাইন অর্ডার লোড করা যায়নি।');
    } catch (e) {
      return {'success': false, 'message': 'নেটওয়ার্ক ত্রুটি: $e', 'orders': []};
    }
  }

  static Future<Map<String, dynamic>> performOnlineOrderAction({
    required int orderId,
    required String action,
    String? status,
    int? riderId,
    String? otp,
    String? addressDetails,
  }) async {
    try {
      final body = <String, dynamic>{
        'action': action,
        if (status != null) 'status': status,
        if (riderId != null) 'rider_id': riderId,
        if (otp != null) 'otp': otp,
        if (addressDetails != null) 'address_details': addressDetails,
      };
      final res = await ApiService.httpPost(
        '/api/admin/online-orders/$orderId/action',
        headers: _jsonHeaders,
        body: jsonEncode(body),
        timeout: const Duration(seconds: 15),
      );
      return _decodeOrError(res, 'অর্ডার অ্যাকশন সম্পন্ন করা যায়নি।');
    } catch (e) {
      return {'success': false, 'message': 'নেটওয়ার্ক ত্রুটি: $e'};
    }
  }

  static Future<Map<String, dynamic>> fetchCustomerProfile(String phone) async {
    try {
      final res = await ApiService.httpGet(
        '/api/admin/customer-profile?phone=${Uri.encodeComponent(phone.trim())}',
        timeout: const Duration(seconds: 12),
      );
      return _decodeOrError(res, 'কাস্টমার প্রোফাইল লোড করা যায়নি।');
    } catch (e) {
      return {'success': false, 'message': 'নেটওয়ার্ক ত্রুটি: $e'};
    }
  }

  static Future<Map<String, dynamic>> fetchReports({
    String period = 'monthly',
    String dept = 'all',
  }) async {
    try {
      final res = await ApiService.httpGet(
        '/api/admin/reports?period=${Uri.encodeComponent(period)}&dept=${Uri.encodeComponent(dept)}',
        timeout: const Duration(seconds: 15),
      );
      return _decodeOrError(res, 'রিপোর্ট লোড করা যায়নি।');
    } catch (e) {
      return {'success': false, 'message': 'নেটওয়ার্ক ত্রুটি: $e'};
    }
  }

  static Future<Map<String, dynamic>> addLedgerEntry({
    required String title,
    required String entryType,
    required double amount,
    String entryDate = '',
    String targetSegment = 'all',
  }) async {
    try {
      final res = await ApiService.httpPost(
        '/api/admin/reports/ledger',
        headers: _jsonHeaders,
        body: jsonEncode({
          'title': title,
          'entry_type': entryType,
          'amount': amount,
          if (entryDate.isNotEmpty) 'entry_date': entryDate,
          'target_segment': targetSegment,
        }),
        timeout: const Duration(seconds: 12),
      );
      return _decodeOrError(res, 'লেজার এন্ট্রি সেভ করা যায়নি।');
    } catch (e) {
      return {'success': false, 'message': 'নেটওয়ার্ক ত্রুটি: $e'};
    }
  }

  static Future<Map<String, dynamic>> deleteLedgerEntry(int entryId) async {
    try {
      final res = await ApiService.httpPost(
        '/api/admin/reports/ledger/$entryId/delete',
        headers: _jsonHeaders,
        body: jsonEncode({}),
        timeout: const Duration(seconds: 12),
      );
      return _decodeOrError(res, 'লেজার এন্ট্রি মোছা যায়নি।');
    } catch (e) {
      return {'success': false, 'message': 'নেটওয়ার্ক ত্রুটি: $e'};
    }
  }

  static Future<Map<String, dynamic>> saveRider({
    int? riderId,
    required String fullName,
    required String username,
    String password = '',
    bool isActive = true,
    bool canRxQuoteBill = false,
  }) async {
    try {
      final res = await ApiService.httpPost(
        '/api/admin/riders/save',
        headers: _jsonHeaders,
        body: jsonEncode({
          if (riderId != null) 'rider_id': riderId,
          'full_name': fullName,
          'username': username,
          if (password.isNotEmpty) 'password': password,
          'is_active': isActive,
          'can_rx_quote_bill': canRxQuoteBill,
        }),
        timeout: const Duration(seconds: 15),
      );
      return _decodeOrError(res, 'রাইডার তথ্য সংরক্ষণ করা যায়নি।');
    } catch (e) {
      return {'success': false, 'message': 'নেটওয়ার্ক ত্রুটি: $e'};
    }
  }

  static Future<Map<String, dynamic>> deleteRider(int riderId) async {
    try {
      final res = await ApiService.httpPost(
        '/api/admin/riders/$riderId/delete',
        headers: _jsonHeaders,
        body: jsonEncode({}),
        timeout: const Duration(seconds: 12),
      );
      return _decodeOrError(res, 'রাইডার ডিলিট করা যায়নি।');
    } catch (e) {
      return {'success': false, 'message': 'নেটওয়ার্ক ত্রুটি: $e'};
    }
  }

  static Future<Map<String, dynamic>> payRider({
    required int riderId,
    required double amount,
    String paymentMethod = 'Cash',
    String note = '',
    String payoutDate = '',
  }) async {
    try {
      final res = await ApiService.httpPost(
        '/api/admin/riders/$riderId/pay',
        headers: _jsonHeaders,
        body: jsonEncode({
          'amount': amount,
          'payment_method': paymentMethod,
          'note': note,
          if (payoutDate.isNotEmpty) 'payout_date': payoutDate,
        }),
        timeout: const Duration(seconds: 15),
      );
      return _decodeOrError(res, 'রাইডার পেমেন্ট সম্পন্ন করা যায়নি।');
    } catch (e) {
      return {'success': false, 'message': 'নেটওয়ার্ক ত্রুটি: $e'};
    }
  }

  static Future<Map<String, dynamic>> deleteRiderPayout(int payoutId) async {
    try {
      final res = await ApiService.httpPost(
        '/api/admin/riders/payouts/$payoutId/delete',
        headers: _jsonHeaders,
        body: jsonEncode({}),
        timeout: const Duration(seconds: 12),
      );
      return _decodeOrError(res, 'পেমেন্ট রেকর্ড মোছা যায়নি।');
    } catch (e) {
      return {'success': false, 'message': 'নেটওয়ার্ক ত্রুটি: $e'};
    }
  }

  static Future<Map<String, dynamic>> fetchAdminSettings() async {
    try {
      final res = await ApiService.httpGet('/api/admin/settings', timeout: const Duration(seconds: 12));
      return _decodeOrError(res, 'সেটিংস লোড করা যায়নি।');
    } catch (e) {
      return {'success': false, 'message': 'নেটওয়ার্ক ত্রুটি: $e'};
    }
  }

  static Future<Map<String, dynamic>> saveAdminSettings(Map<String, dynamic> updates) async {
    try {
      final res = await ApiService.httpPost(
        '/api/admin/settings',
        headers: _jsonHeaders,
        body: jsonEncode(updates),
        timeout: const Duration(seconds: 15),
      );
      return _decodeOrError(res, 'সেটিংস সেভ করা যায়নি।');
    } catch (e) {
      return {'success': false, 'message': 'নেটওয়ার্ক ত্রুটি: $e'};
    }
  }

  static Future<Map<String, dynamic>> fetchPharmacySettings() async {
    try {
      final res = await ApiService.httpGet('/api/admin/pharmacy/settings', timeout: const Duration(seconds: 10));
      return _decodeOrError(res, 'ফার্মেসী সেটিংস লোড করা যায়নি।');
    } catch (e) {
      return {'success': false, 'message': 'নেটওয়ার্ক ত্রুটি: $e'};
    }
  }

  static Future<Map<String, dynamic>> savePharmacySettings(Map<String, dynamic> updates) async {
    try {
      final res = await ApiService.httpPost(
        '/api/admin/pharmacy/settings',
        headers: _jsonHeaders,
        body: jsonEncode(updates),
        timeout: const Duration(seconds: 12),
      );
      return _decodeOrError(res, 'ফার্মেসী সেটিংস সেভ করা যায়নি।');
    } catch (e) {
      return {'success': false, 'message': 'নেটওয়ার্ক ত্রুটি: $e'};
    }
  }

  static Future<Map<String, dynamic>> deletePharmacyMedicine(int medId) async {
    try {
      final res = await ApiService.httpPost(
        '/api/admin/pharmacy/medicines/$medId/delete',
        headers: _jsonHeaders,
        body: jsonEncode({}),
        timeout: const Duration(seconds: 12),
      );
      return _decodeOrError(res, 'ঔষধ ডিলিট করা যায়নি।');
    } catch (e) {
      return {'success': false, 'message': 'নেটওয়ার্ক ত্রুটি: $e'};
    }
  }

  static Future<Map<String, dynamic>> fetchThermalPrinters() async {
    try {
      final res = await ApiService.httpGet('/api/thermal/printers', timeout: const Duration(seconds: 10));
      return _decodeOrError(res, 'প্রিন্টার তালিকা লোড করা যায়নি।');
    } catch (e) {
      return {'success': false, 'message': 'নেটওয়ার্ক ত্রুটি: $e', 'printers': []};
    }
  }

  static Future<Map<String, dynamic>> processPendingThermalJobs() async {
    try {
      final res = await ApiService.httpPost(
        '/api/thermal/process-pending',
        headers: _jsonHeaders,
        body: jsonEncode({}),
        timeout: const Duration(seconds: 15),
      );
      return _decodeOrError(res, 'প্রিন্ট কিউ প্রসেস করা যায়নি।');
    } catch (e) {
      return {'success': false, 'message': 'নেটওয়ার্ক ত্রুটি: $e'};
    }
  }
}
