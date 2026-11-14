import 'dart:async';
import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart' show Color;
import 'package:flutter_local_notifications/flutter_local_notifications.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../models/notification_model.dart';
import 'api_service.dart';

class NotificationService {
  static final NotificationService instance = NotificationService._internal();

  NotificationService._internal();

  final ValueNotifier<List<AppNotification>> notificationsNotifier = ValueNotifier<List<AppNotification>>([]);
  final ValueNotifier<int> unreadCountNotifier = ValueNotifier<int>(0);
  final ValueNotifier<List<Map<String, dynamic>>> pendingConfirmationsNotifier = ValueNotifier<List<Map<String, dynamic>>>([]);

  final FlutterLocalNotificationsPlugin _localPlugin = FlutterLocalNotificationsPlugin();
  final Set<int> _seenIds = <int>{};
  final Set<int> _systemNotifiedIds = <int>{};
  final Map<String, DateTime> _lastReminderAt = <String, DateTime>{};
  final Map<String, int> _activeReminderNotifIds = <String, int>{};
  Timer? _pollingTimer;
  bool _isFetching = false;
  bool _localInitDone = false;
  String _currentPhone = '';
  String _pendingTapPayload = '';

  void Function(String payload)? onNotificationTap;

  String get currentPhone => _currentPhone;
  List<AppNotification> get notifications => notificationsNotifier.value;
  int get unreadCount => unreadCountNotifier.value;

  String normalizeOrderRef(String raw) {
    String s = raw.trim();
    if (s.startsWith('#')) s = s.substring(1).trim();
    final m = RegExp(r'(RX-[A-Za-z0-9-]+|ORD-[A-Za-z0-9-]+)', caseSensitive: false).firstMatch(s);
    if (m != null) return m.group(1)!.toUpperCase();
    return s;
  }

  void _dispatchTapPayload(String rawPayload) {
    final cleaned = normalizeOrderRef(rawPayload);
    if (cleaned.isEmpty) return;
    if (onNotificationTap != null) {
      onNotificationTap!(cleaned);
    } else {
      _pendingTapPayload = cleaned;
    }
  }

  void flushPendingTap() {
    if (_pendingTapPayload.isNotEmpty && onNotificationTap != null) {
      final p = _pendingTapPayload;
      _pendingTapPayload = '';
      onNotificationTap!(p);
    }
  }

  Future<void> init() async {
    await _initLocalNotifications();
    await _loadFromCache();
    await fetchNotifications();
    _startPeriodicPolling();
  }

  Future<void> _initLocalNotifications() async {
    if (_localInitDone || kIsWeb) return;
    _localInitDone = true;
    try {
      const androidInit = AndroidInitializationSettings('@mipmap/ic_launcher');
      await _localPlugin.initialize(
        settings: const InitializationSettings(android: androidInit),
        onDidReceiveNotificationResponse: (NotificationResponse resp) {
          final p = (resp.payload ?? '').trim();
          if (p.isNotEmpty) {
            _dispatchTapPayload(p);
          }
        },
      );
      final launchDetails = await _localPlugin.getNotificationAppLaunchDetails();
      if (launchDetails != null && launchDetails.didNotificationLaunchApp) {
        final p = (launchDetails.notificationResponse?.payload ?? '').trim();
        if (p.isNotEmpty) {
          _pendingTapPayload = normalizeOrderRef(p);
        }
      }
      final androidImpl = _localPlugin.resolvePlatformSpecificImplementation<AndroidFlutterLocalNotificationsPlugin>();
      await androidImpl?.requestNotificationsPermission();
      await androidImpl?.createNotificationChannel(
        const AndroidNotificationChannel(
          'doineek_pharmacy_alerts',
          'DOINEEK Order & Pharmacy Alerts',
          description: 'Instant pharmacy bill confirmation and order status updates',
          importance: Importance.max,
          playSound: true,
          enableVibration: true,
        ),
      );
      await androidImpl?.createNotificationChannel(
        const AndroidNotificationChannel(
          'doineek_urgent_confirmations',
          'Urgent Order Confirmation Reminders',
          description: 'Critical reminders for pharmacy prescription bills awaiting customer confirmation',
          importance: Importance.max,
          playSound: true,
          enableVibration: true,
        ),
      );
    } catch (e) {
      debugPrint('[NotificationService] local notif init note: $e');
    }
  }

  void _startPeriodicPolling() {
    _pollingTimer?.cancel();
    _pollingTimer = Timer.periodic(const Duration(seconds: 10), (_) {
      fetchNotifications();
    });
  }

  void dispose() {
    _pollingTimer?.cancel();
  }

  void clearLocalState() {
    _currentPhone = '';
    _seenIds.clear();
    _systemNotifiedIds.clear();
    _lastReminderAt.clear();
    notificationsNotifier.value = [];
    unreadCountNotifier.value = 0;
    pendingConfirmationsNotifier.value = [];
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
      final sysList = prefs.getStringList('cached_system_notified_ids') ?? [];
      _systemNotifiedIds.clear();
      for (var s in sysList) {
        final id = int.tryParse(s);
        if (id != null) _systemNotifiedIds.add(id);
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

      final sysList = _systemNotifiedIds.map((id) => id.toString()).toList();
      await prefs.setStringList('cached_system_notified_ids', sysList);
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
        pendingConfirmationsNotifier.value = [];
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

          final List<dynamic> rawPending = data['pending_confirmations'] ?? [];
          final pendingList = rawPending
              .whereType<Map>()
              .map((e) => Map<String, dynamic>.from(e))
              .toList();
          pendingConfirmationsNotifier.value = pendingList;

          notificationsNotifier.value = freshList;
          _recalculateUnread();
          final newlyShownRefs = await _showNewSystemNotifications(freshList);
          await _handlePendingConfirmationReminders(pendingList, newlyShownRefs);
          await _saveToCache();
        }
      }
    } catch (e) {
      debugPrint('[NotificationService] fetch error: $e');
    } finally {
      _isFetching = false;
    }
  }

  Future<Set<String>> _showNewSystemNotifications(List<AppNotification> list) async {
    final shownRefs = <String>{};
    if (kIsWeb) return shownRefs;
    if (!_localInitDone) await _initLocalNotifications();
    for (final n in list) {
      if (n.isRead || _seenIds.contains(n.id) || _systemNotifiedIds.contains(n.id)) {
        continue;
      }
      _systemNotifiedIds.add(n.id);
      final bool isUrgent = n.isImportant ||
          n.type == 'pharmacy_quote' ||
          n.type == 'order_confirmation';
      final rawRef = n.referenceId.isNotEmpty ? n.referenceId : n.title;
      final normalized = normalizeOrderRef(rawRef);
      if (normalized.isNotEmpty) {
        shownRefs.add(normalized);
        if (isUrgent) {
          _lastReminderAt[normalized] = DateTime.now();
        }
      }
      final payload = normalized.isNotEmpty ? normalized : n.type;
      try {
        await _localPlugin.show(
          id: n.id,
          title: isUrgent ? '⚠️ জরুরি: ${n.title}' : n.title,
          body: isUrgent
              ? '${n.message}\n👉 Tap to view করে অর্ডারটি কনফার্ম বা বাতিল করুন।'
              : n.message,
          notificationDetails: NotificationDetails(
            android: AndroidNotificationDetails(
              isUrgent ? 'doineek_urgent_confirmations' : 'doineek_pharmacy_alerts',
              isUrgent ? 'Urgent Order Confirmation Reminders' : 'DOINEEK Order & Pharmacy Alerts',
              channelDescription: isUrgent
                  ? 'Critical reminders for pharmacy prescription bills awaiting customer confirmation'
                  : 'Instant pharmacy bill confirmation and order status updates',
              importance: Importance.max,
              priority: isUrgent ? Priority.max : Priority.high,
              color: isUrgent ? const Color(0xFFD97706) : const Color(0xFF6B21A8),
              onlyAlertOnce: false,
              enableVibration: true,
              playSound: true,
              styleInformation: const BigTextStyleInformation(''),
            ),
          ),
          payload: payload,
        );
      } catch (e) {
        debugPrint('[NotificationService] show tray notif error: $e');
      }
    }
    return shownRefs;
  }

  Future<void> _handlePendingConfirmationReminders(
    List<Map<String, dynamic>> pendingList,
    Set<String> justNotifiedRefs,
  ) async {
    final activeRefs = <String>{};
    for (final p in pendingList) {
      final ref = normalizeOrderRef((p['order_number'] ?? p['id'] ?? '').toString());
      if (ref.isNotEmpty) activeRefs.add(ref);
    }

    // Stop reminders automatically once confirmed or cancelled
    for (final existingRef in _activeReminderNotifIds.keys.toList()) {
      if (!activeRefs.contains(existingRef)) {
        final rid = _activeReminderNotifIds.remove(existingRef);
        _lastReminderAt.remove(existingRef);
        if (rid != null && !kIsWeb) {
          try {
            await _localPlugin.cancel(id: rid);
          } catch (_) {}
        }
      }
    }

    if (kIsWeb || pendingList.isEmpty) return;
    if (!_localInitDone) await _initLocalNotifications();

    final now = DateTime.now();
    for (final p in pendingList) {
      final ref = normalizeOrderRef((p['order_number'] ?? p['id'] ?? '').toString());
      if (ref.isEmpty) continue;
      if (justNotifiedRefs.contains(ref)) {
        _lastReminderAt[ref] = now;
        continue;
      }
      final prev = _lastReminderAt[ref];
      if (prev != null && now.difference(prev).inSeconds < 120) {
        continue;
      }
      _lastReminderAt[ref] = now;
      final int rid = 900000 + (ref.hashCode.abs() % 90000);
      _activeReminderNotifIds[ref] = rid;
      final double amt = ((p['total_amount'] ?? 0) as num).toDouble();
      try {
        await _localPlugin.show(
          id: rid,
          title: '🔔 জরুরি: অর্ডার #$ref কনফার্ম করুন!',
          body:
              'আপনার প্রেসক্রিপশন অর্ডারের বিল (৳${amt.toStringAsFixed(2)}) প্রস্তুত — Tap to view করে Confirm দিন, নাহলে ডেলিভারি শুরু হবে না।',
          notificationDetails: const NotificationDetails(
            android: AndroidNotificationDetails(
              'doineek_urgent_confirmations',
              'Urgent Order Confirmation Reminders',
              channelDescription:
                  'Critical reminders for pharmacy prescription bills awaiting customer confirmation',
              importance: Importance.max,
              priority: Priority.max,
              color: Color(0xFFD97706),
              onlyAlertOnce: false,
              enableVibration: true,
              playSound: true,
              styleInformation: BigTextStyleInformation(''),
            ),
          ),
          payload: ref,
        );
      } catch (e) {
        debugPrint('[NotificationService] reminder error: $e');
      }
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
