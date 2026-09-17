import 'dart:async';
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../models/notification_model.dart';
import 'api_service.dart';

class NotificationService {
  static final NotificationService instance = NotificationService._internal();

  NotificationService._internal();

  final ValueNotifier<List<AppNotification>> notificationsNotifier = ValueNotifier<List<AppNotification>>([]);
  final ValueNotifier<int> unreadCountNotifier = ValueNotifier<int>(0);

  final Set<int> _seenIds = <int>{};
  Timer? _pollingTimer;
  bool _isFetching = false;
  String _currentPhone = '';

  String get currentPhone => _currentPhone;
  List<AppNotification> get notifications => notificationsNotifier.value;
  int get unreadCount => unreadCountNotifier.value;

  Future<void> init() async {
    await _loadFromCache();
    await fetchNotifications();
    _startPeriodicPolling();
  }

  void _startPeriodicPolling() {
    _pollingTimer?.cancel();
    _pollingTimer = Timer.periodic(const Duration(seconds: 20), (_) {
      fetchNotifications();
    });
  }

  void dispose() {
    _pollingTimer?.cancel();
  }

  void clearLocalState() {
    _currentPhone = '';
    _seenIds.clear();
    notificationsNotifier.value = [];
    unreadCountNotifier.value = 0;
  }

  Future<void> _loadFromCache() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      _currentPhone = prefs.getString('user_phone') ?? '';

      // If user is not logged in, do not load or show any notifications
      if (_currentPhone.trim().isEmpty) {
        notificationsNotifier.value = [];
        unreadCountNotifier.value = 0;
        return;
      }

      // 1. Load seen IDs set
      final seenList = prefs.getStringList('cached_seen_notif_ids') ?? [];
      _seenIds.clear();
      for (var s in seenList) {
        final id = int.tryParse(s);
        if (id != null) _seenIds.add(id);
      }

      // 2. Load cached notification list
      final rawJson = prefs.getString('cached_app_notifications');
      if (rawJson != null && rawJson.isNotEmpty) {
        final List<dynamic> decoded = jsonDecode(rawJson);
        final list = decoded.map((e) {
          final notif = AppNotification.fromJson(Map<String, dynamic>.from(e));
          if (_seenIds.contains(notif.id)) {
            notif.isRead = true;
          }
          return notif;
        }).toList();

        notificationsNotifier.value = list;
        _recalculateUnread();
      }
    } catch (e) {
      debugPrint('[NotificationService] cache load error: $e');
    }
  }

  Future<void> _saveToCache() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      if (_currentPhone.trim().isEmpty) {
        await prefs.remove('cached_app_notifications');
        return;
      }
      final encoded = jsonEncode(notificationsNotifier.value.map((n) => n.toJson()).toList());
      await prefs.setString('cached_app_notifications', encoded);

      final seenList = _seenIds.map((id) => id.toString()).toList();
      await prefs.setStringList('cached_seen_notif_ids', seenList);
    } catch (e) {
      debugPrint('[NotificationService] cache save error: $e');
    }
  }

  Future<void> fetchNotifications({String? phone}) async {
    if (_isFetching) return;
    _isFetching = true;

    try {
      final prefs = await SharedPreferences.getInstance();
      final userPhone = (phone ?? prefs.getString('user_phone') ?? _currentPhone).trim();
      _currentPhone = userPhone;

      // If user is not logged in, clear any existing notifications and return
      if (userPhone.isEmpty) {
        notificationsNotifier.value = [];
        unreadCountNotifier.value = 0;
        try {
          await prefs.remove('cached_app_notifications');
        } catch (_) {}
        return;
      }

      final res = await ApiService.httpGet(
        '/api/notifications?phone=${Uri.encodeComponent(userPhone)}',
        timeout: const Duration(seconds: 8),
      );

      if (res != null && res.statusCode == 200) {
        final Map<String, dynamic> data = jsonDecode(res.body);
        if (data['success'] == true) {
          final List<dynamic> rawList = data['notifications'] ?? [];
          final freshList = rawList.map((e) {
            final notif = AppNotification.fromJson(Map<String, dynamic>.from(e));
            // Apply local seen cache
            if (_seenIds.contains(notif.id)) {
              notif.isRead = true;
            }
            return notif;
          }).toList();

          notificationsNotifier.value = freshList;
          _recalculateUnread();
          await _saveToCache();
        }
      }
    } catch (e) {
      debugPrint('[NotificationService] fetch error: $e');
    } finally {
      _isFetching = false;
    }
  }

  void _recalculateUnread() {
    int count = 0;
    for (var n in notificationsNotifier.value) {
      if (!n.isRead && !_seenIds.contains(n.id)) {
        count++;
      }
    }
    unreadCountNotifier.value = count;
  }

  Future<void> markAsRead(int notifId) async {
    _seenIds.add(notifId);

    final currentList = notificationsNotifier.value;
    for (var n in currentList) {
      if (n.id == notifId) {
        n.isRead = true;
      }
    }

    notificationsNotifier.value = List<AppNotification>.from(currentList);
    _recalculateUnread();
    await _saveToCache();

    // Sync to backend
    try {
      final prefs = await SharedPreferences.getInstance();
      final phone = prefs.getString('user_phone') ?? _currentPhone;
      await ApiService.httpPost(
        '/api/notifications/mark-read',
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'phone': phone, 'id': notifId}),
      );
    } catch (_) {}
  }

  Future<void> markAllAsRead() async {
    final currentList = notificationsNotifier.value;
    for (var n in currentList) {
      n.isRead = true;
      _seenIds.add(n.id);
    }

    notificationsNotifier.value = List<AppNotification>.from(currentList);
    unreadCountNotifier.value = 0;
    await _saveToCache();

    // Sync to backend
    try {
      final prefs = await SharedPreferences.getInstance();
      final phone = prefs.getString('user_phone') ?? _currentPhone;
      await ApiService.httpPost(
        '/api/notifications/mark-read',
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'phone': phone, 'id': 'all'}),
      );
    } catch (_) {}
  }

  Future<void> clearAll() async {
    notificationsNotifier.value = [];
    unreadCountNotifier.value = 0;
    _seenIds.clear();
    await _saveToCache();

    try {
      final prefs = await SharedPreferences.getInstance();
      final phone = prefs.getString('user_phone') ?? _currentPhone;
      await ApiService.httpPost(
        '/api/notifications/clear',
        headers: {'Content-Type': 'application/json'},
        body: jsonEncode({'phone': phone}),
      );
    } catch (_) {}
  }
}
