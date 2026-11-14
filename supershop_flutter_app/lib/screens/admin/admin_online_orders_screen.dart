import 'dart:async';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../../services/admin_api_service.dart';
import '../../widgets/app_image_loader.dart';
import '../../widgets/rx_quote_builder_sheet.dart';
import '../../widgets/thermal_print_helper.dart';

class AdminOnlineOrdersScreen extends StatefulWidget {
  final String? staffPhone;
  final String initialDept;

  const AdminOnlineOrdersScreen({
    super.key,
    this.staffPhone,
    this.initialDept = 'all',
  });

  @override
  State<AdminOnlineOrdersScreen> createState() => _AdminOnlineOrdersScreenState();
}

class _AdminOnlineOrdersScreenState extends State<AdminOnlineOrdersScreen> {
  String _staffPhone = '';
  String _staffRole = 'admin';
  late String _deptFilter;
  String _statusFilter = 'all';
  final TextEditingController _searchCtrl = TextEditingController();
  Timer? _debounce;
  Timer? _liveSyncTimer;
  bool _isSilentSyncing = false;

  bool _loading = true;
  List<Map<String, dynamic>> _orders = [];
  List<Map<String, dynamic>> _riders = [];
  Map<String, dynamic> _counts = {};

  @override
  void initState() {
    super.initState();
    _deptFilter = widget.initialDept;
    _initAndLoad();
    _liveSyncTimer = Timer.periodic(const Duration(seconds: 4), (_) {
      _loadOrders(silent: true);
    });
  }

  @override
  void dispose() {
    _liveSyncTimer?.cancel();
    _debounce?.cancel();
    _searchCtrl.dispose();
    super.dispose();
  }

  Future<void> _initAndLoad() async {
    final prefs = await SharedPreferences.getInstance();
    if (!mounted) return;
    setState(() {
      _staffPhone = (widget.staffPhone ?? '').isNotEmpty
          ? widget.staffPhone!
          : (prefs.getString('user_phone') ?? '');
      _staffRole = (prefs.getString('user_role') ?? 'admin').toLowerCase();
    });
    await _loadOrders();
  }

  Future<void> _loadOrders({bool silent = false}) async {
    if (silent && _isSilentSyncing) return;
    if (silent) {
      _isSilentSyncing = true;
    } else if (mounted) {
      setState(() => _loading = true);
    }
    try {
      final res = await AdminApiService.fetchOnlineOrders(
        dept: _deptFilter,
        status: _statusFilter,
        query: _searchCtrl.text,
      );
      if (!mounted) return;
      setState(() {
        _orders = (res['orders'] as List? ?? [])
            .whereType<Map>()
            .map((e) => Map<String, dynamic>.from(e))
            .toList();
        _riders = (res['riders'] as List? ?? [])
            .whereType<Map>()
            .map((e) => Map<String, dynamic>.from(e))
            .toList();
        _counts = res['counts'] is Map
            ? Map<String, dynamic>.from(res['counts'] as Map)
            : {};
        _loading = false;
      });
    } finally {
      _isSilentSyncing = false;
    }
  }

  Color _statusColor(String status) {
    switch (status.trim().toLowerCase()) {
      case 'new':
      case 'pending':
      case 'pending_confirmation':
      case 'reviewing':
        return Colors.blue.shade700;
      case 'awaiting_customer_confirmation':
        return Colors.amber.shade800;
      case 'verified':
      case 'confirmed':
        return Colors.indigo.shade700;
      case 'packed':
        return Colors.orange.shade800;
      case 'on_the_way':
        return Colors.cyan.shade700;
      case 'delivered':
        return Colors.green.shade700;
      case 'cancelled':
        return Colors.red.shade700;
      default:
        return Colors.blueGrey.shade700;
    }
  }

  void _showSnack(String msg, {bool isError = false}) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(msg),
        backgroundColor: isError ? Colors.red.shade700 : Colors.green.shade700,
      ),
    );
  }

  void _openPrescriptionZoom(String url) {
    showDialog(
      context: context,
      barrierColor: Colors.black87,
      builder: (ctx) => Dialog(
        backgroundColor: Colors.black,
        insetPadding: const EdgeInsets.all(10),
        child: Column(
          children: [
            AppBar(
              backgroundColor: Colors.black,
              foregroundColor: Colors.white,
              title: const Text('📋 প্রেসক্রিপশন', style: TextStyle(fontSize: 15)),
            ),
            Expanded(
              child: InteractiveViewer(
                minScale: 0.7,
                maxScale: 5.0,
                child: Center(
                  child: AppImageLoader(imageUrl: url, fit: BoxFit.contain),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _openCustomerProfileDialog(String phone, String fallbackName) async {
    if (phone.trim().isEmpty) return;
    showDialog(
      context: context,
      builder: (ctx) => FutureBuilder<Map<String, dynamic>>(
        future: AdminApiService.fetchCustomerProfile(phone),
        builder: (ctx, snap) {
          if (snap.connectionState == ConnectionState.waiting) {
            return const AlertDialog(
              content: SizedBox(
                height: 110,
                child: Center(child: CircularProgressIndicator()),
              ),
            );
          }
          final data = snap.data ?? {};
          final cust = data['customer'] is Map
              ? Map<String, dynamic>.from(data['customer'] as Map)
              : <String, dynamic>{};
          if (data['success'] != true || cust.isEmpty) {
            return AlertDialog(
              title: Text(fallbackName),
              content: Text(data['message']?.toString() ?? 'প্রোফাইল তথ্য পাওয়া যায়নি।'),
              actions: [
                TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('বন্ধ')),
              ],
            );
          }
          final List<Map<String, dynamic>> pastOrders = (cust['orders'] as List? ?? [])
              .whereType<Map>()
              .map((e) => Map<String, dynamic>.from(e))
              .toList();
          return AlertDialog(
            title: Row(
              children: [
                const Icon(Icons.person_pin, color: Colors.teal),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    (cust['name'] ?? fallbackName).toString(),
                    style: const TextStyle(fontSize: 15.5, fontWeight: FontWeight.bold),
                  ),
                ),
              ],
            ),
            content: SizedBox(
              width: 360,
              child: SingleChildScrollView(
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  mainAxisSize: MainAxisSize.min,
                  children: [
                    _kv('📞 মোবাইল', (cust['phone'] ?? '').toString()),
                    _kv('📅 সদস্য হয়েছেন', (cust['member_since'] ?? '-').toString()),
                    _kv('📍 ঠিকানা', '${cust['address'] ?? ''} (${cust['area'] ?? ''}, ${cust['district'] ?? ''})'),
                    _kv('🌐 সর্বশেষ IP', (cust['last_ip'] ?? '-').toString()),
                    _kv('🗺️ IP লোকেশন', (cust['last_location'] ?? '-').toString()),
                    if ((cust['last_device'] ?? '').toString().isNotEmpty)
                      _kv('📱 ডিভাইস', (cust['last_device'] ?? '').toString()),
                    _kv(
                      '📊 পরিসংখ্যান',
                      'মোট অর্ডার: ${cust['order_count'] ?? 0} টি • মোট খরচ: ৳${((cust['total_spent'] ?? 0) as num).toStringAsFixed(0)}',
                    ),
                    const SizedBox(height: 6),
                    Wrap(
                      spacing: 6,
                      children: [
                        Chip(
                          label: Text(
                            cust['is_verified'] == true ? '✅ ভেরিফাইড' : 'অভেরিফাইড',
                            style: const TextStyle(fontSize: 11),
                          ),
                          backgroundColor: cust['is_verified'] == true
                              ? Colors.green.shade50
                              : Colors.grey.shade200,
                        ),
                        if (cust['is_blocked'] == true)
                          Chip(
                            label: Text(
                              '🚫 ব্লকড: ${cust['block_reason'] ?? ''}',
                              style: const TextStyle(fontSize: 11, color: Colors.red),
                            ),
                            backgroundColor: Colors.red.shade50,
                          ),
                      ],
                    ),
                    const Divider(),
                    const Text('সাম্প্রতিক অর্ডারসমূহ:', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 12.5)),
                    const SizedBox(height: 4),
                    ...pastOrders.take(8).map((po) => Padding(
                          padding: const EdgeInsets.only(bottom: 4),
                          child: Text(
                            '• #${po['order_number']} (${po['order_status']}) — ৳${((po['total_amount'] ?? 0) as num).toStringAsFixed(0)}',
                            style: const TextStyle(fontSize: 11.5),
                          ),
                        )),
                  ],
                ),
              ),
            ),
            actions: [
              TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('বন্ধ করুন')),
            ],
          );
        },
      ),
    );
  }

  Widget _kv(String k, String v) {
    return Padding(
      padding: const EdgeInsets.only(bottom: 4),
      child: RichText(
        text: TextSpan(
          style: const TextStyle(fontSize: 12, color: Color(0xFF1E293B)),
          children: [
            TextSpan(text: '$k: ', style: const TextStyle(fontWeight: FontWeight.bold)),
            TextSpan(text: v.trim().isEmpty ? '-' : v),
          ],
        ),
      ),
    );
  }

  Future<void> _openStatusAndRiderDialog(Map<String, dynamic> order) async {
    final int orderId = ((order['id'] ?? 0) as num).toInt();
    final String currentStatus = (order['order_status'] ?? 'new').toString().toLowerCase();
    final bool awaiting = currentStatus == 'awaiting_customer_confirmation';
    String nextStatus = awaiting ? 'cancelled' : currentStatus;
    const statusChoices = [
      'new',
      'verified',
      'packed',
      'on_the_way',
      'delivered',
      'cancelled',
    ];
    if (!statusChoices.contains(nextStatus)) nextStatus = 'verified';

    int selectedRider = ((order['assigned_rider_id'] ?? 0) as num).toInt();
    bool busy = false;

    await showDialog(
      context: context,
      builder: (dlgCtx) => StatefulBuilder(
        builder: (_, setDlgState) => AlertDialog(
          title: Text('অর্ডার #${order['order_number']}', style: const TextStyle(fontSize: 15, fontWeight: FontWeight.bold)),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (awaiting)
                Container(
                  margin: const EdgeInsets.only(bottom: 10),
                  padding: const EdgeInsets.all(8),
                  decoration: BoxDecoration(
                    color: Colors.amber.shade50,
                    borderRadius: BorderRadius.circular(8),
                    border: Border.all(color: Colors.amber.shade400),
                  ),
                  child: const Text(
                    '⚠️ কাস্টমার কনফার্মেশন বাকি — কনফার্ম ছাড়া সামনের ধাপে নেওয়া যাবে না (শুধু বাতিল করা যাবে)।',
                    style: TextStyle(fontSize: 11.5, color: Color(0xFF92400E)),
                  ),
                ),
              DropdownButtonFormField<String>(
                initialValue: nextStatus,
                decoration: const InputDecoration(labelText: 'অর্ডার স্ট্যাটাস', isDense: true),
                items: statusChoices
                    .map((s) => DropdownMenuItem(value: s, child: Text(s.toUpperCase())))
                    .toList(),
                onChanged: (v) {
                  if (v != null) setDlgState(() => nextStatus = v);
                },
              ),
              const SizedBox(height: 12),
              DropdownButtonFormField<int>(
                initialValue: _riders.any((r) => ((r['id'] ?? 0) as num).toInt() == selectedRider)
                    ? selectedRider
                    : 0,
                decoration: const InputDecoration(labelText: 'ডেলিভারি রাইডার', isDense: true),
                items: [
                  const DropdownMenuItem(value: 0, child: Text('রাইডার নেই / আনঅ্যাসাইন')),
                  ..._riders.map((r) => DropdownMenuItem(
                        value: ((r['id'] ?? 0) as num).toInt(),
                        child: Text('${r['full_name']} (${r['username']})'),
                      )),
                ],
                onChanged: (v) {
                  if (v != null) setDlgState(() => selectedRider = v);
                },
              ),
            ],
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(dlgCtx), child: const Text('বাতিল')),
            ElevatedButton(
              onPressed: busy
                  ? null
                  : () async {
                      setDlgState(() => busy = true);
                      final int origRider = ((order['assigned_rider_id'] ?? 0) as num).toInt();
                      Map<String, dynamic> res = {'success': true, 'message': 'আপডেট সম্পন্ন'};
                      if (selectedRider != origRider && !awaiting) {
                        res = await AdminApiService.performOnlineOrderAction(
                          orderId: orderId,
                          action: 'assign_rider',
                          riderId: selectedRider,
                        );
                      }
                      if (res['success'] == true && nextStatus != currentStatus) {
                        res = await AdminApiService.performOnlineOrderAction(
                          orderId: orderId,
                          action: 'update_status',
                          status: nextStatus,
                        );
                      }
                      if (!dlgCtx.mounted) return;
                      Navigator.pop(dlgCtx);
                      _showSnack(
                        res['message']?.toString() ?? 'আপডেট সম্পন্ন',
                        isError: res['success'] != true,
                      );
                      _loadOrders();
                    },
              style: ElevatedButton.styleFrom(backgroundColor: Colors.teal.shade700, foregroundColor: Colors.white),
              child: Text(busy ? 'সেভ হচ্ছে...' : 'আপডেট করুন'),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _openOtpDialog(Map<String, dynamic> order) async {
    final ctrl = TextEditingController();
    await showDialog(
      context: context,
      builder: (dlgCtx) => AlertDialog(
        title: Text('OTP ডেলিভারি • #${order['order_number']}', style: const TextStyle(fontSize: 15)),
        content: TextField(
          controller: ctrl,
          keyboardType: TextInputType.number,
          decoration: const InputDecoration(
            labelText: 'কাস্টমারের ৪ ডিজিট OTP দিন',
            border: OutlineInputBorder(),
          ),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(dlgCtx), child: const Text('বাতিল')),
          ElevatedButton(
            onPressed: () async {
              final res = await AdminApiService.performOnlineOrderAction(
                orderId: ((order['id'] ?? 0) as num).toInt(),
                action: 'verify_otp',
                otp: ctrl.text.trim(),
              );
              if (!dlgCtx.mounted) return;
              Navigator.pop(dlgCtx);
              _showSnack(res['message']?.toString() ?? '', isError: res['success'] != true);
              if (res['success'] == true) _loadOrders();
            },
            child: const Text('ভেরিফাই'),
          ),
        ],
      ),
    );
    ctrl.dispose();
  }

  Future<void> _openEditAddressDialog(Map<String, dynamic> order) async {
    final ctrl = TextEditingController(text: (order['address_details'] ?? '').toString());
    await showDialog(
      context: context,
      builder: (dlgCtx) => AlertDialog(
        title: const Text('ঠিকানা আপডেট', style: TextStyle(fontSize: 15)),
        content: TextField(
          controller: ctrl,
          maxLines: 3,
          decoration: const InputDecoration(
            labelText: 'বিস্তারিত ঠিকানা',
            border: OutlineInputBorder(),
          ),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(dlgCtx), child: const Text('বাতিল')),
          ElevatedButton(
            onPressed: () async {
              final res = await AdminApiService.performOnlineOrderAction(
                orderId: ((order['id'] ?? 0) as num).toInt(),
                action: 'update_address',
                addressDetails: ctrl.text.trim(),
              );
              if (!dlgCtx.mounted) return;
              Navigator.pop(dlgCtx);
              _showSnack(res['message']?.toString() ?? '', isError: res['success'] != true);
              if (res['success'] == true) _loadOrders();
            },
            child: const Text('সেভ'),
          ),
        ],
      ),
    );
    ctrl.dispose();
  }

  Future<void> _confirmDeleteOrder(Map<String, dynamic> order) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('অর্ডার ডিলিট নিশ্চিত করুন'),
        content: Text('আপনি কি নিশ্চিতভাবে #${order['order_number']} মুছে ফেলতে চান?'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('না')),
          ElevatedButton(
            onPressed: () => Navigator.pop(ctx, true),
            style: ElevatedButton.styleFrom(backgroundColor: Colors.red),
            child: const Text('হ্যাঁ, ডিলিট', style: TextStyle(color: Colors.white)),
          ),
        ],
      ),
    );
    if (ok != true) return;
    final res = await AdminApiService.performOnlineOrderAction(
      orderId: ((order['id'] ?? 0) as num).toInt(),
      action: 'delete',
    );
    _showSnack(res['message']?.toString() ?? '', isError: res['success'] != true);
    if (res['success'] == true) _loadOrders();
  }

  Widget _deptChip(String key, String label, Color accent) {
    final selected = _deptFilter == key;
    return Padding(
      padding: const EdgeInsets.only(right: 6),
      child: ChoiceChip(
        label: Text(
          label,
          style: TextStyle(
            fontSize: 11.5,
            fontWeight: FontWeight.w700,
            color: selected ? Colors.white : const Color(0xFF1E293B),
          ),
        ),
        selected: selected,
        selectedColor: accent,
        onSelected: (_) {
          setState(() => _deptFilter = key);
          _loadOrders();
        },
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        backgroundColor: Colors.teal.shade900,
        foregroundColor: Colors.white,
        title: const Text('অনলাইন অর্ডার্স ম্যানেজমেন্ট', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
        actions: [
          IconButton(icon: const Icon(Icons.refresh), onPressed: _loadOrders),
        ],
      ),
      body: Column(
        children: [
          Container(
            padding: const EdgeInsets.fromLTRB(12, 10, 12, 8),
            color: Colors.white,
            child: Column(
              children: [
                SingleChildScrollView(
                  scrollDirection: Axis.horizontal,
                  child: Row(
                    children: [
                      _deptChip('all', 'সব (${_counts['all'] ?? _orders.length})', const Color(0xFF1E293B)),
                      _deptChip('regular', '🛒 সুপারশপ (${_counts['regular'] ?? 0})', const Color(0xFF6B21A8)),
                      _deptChip('pharmacy', '💊 ফার্মেসী (${_counts['pharmacy'] ?? 0})', const Color(0xFF0F766E)),
                      _deptChip('awaiting_confirmation', '🔔 কনফার্ম বাকি (${_counts['awaiting_confirmation'] ?? 0})', const Color(0xFFD97706)),
                    ],
                  ),
                ),
                const SizedBox(height: 8),
                Row(
                  children: [
                    Expanded(
                      flex: 3,
                      child: TextField(
                        controller: _searchCtrl,
                        onChanged: (_) {
                          _debounce?.cancel();
                          _debounce = Timer(const Duration(milliseconds: 350), _loadOrders);
                        },
                        decoration: InputDecoration(
                          hintText: 'অর্ডার #, নাম বা মোবাইল...',
                          prefixIcon: const Icon(Icons.search, size: 18),
                          isDense: true,
                          border: OutlineInputBorder(borderRadius: BorderRadius.circular(10)),
                          contentPadding: const EdgeInsets.symmetric(vertical: 9),
                        ),
                      ),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      flex: 2,
                      child: DropdownButtonFormField<String>(
                        initialValue: _statusFilter,
                        isDense: true,
                        decoration: InputDecoration(
                          border: OutlineInputBorder(borderRadius: BorderRadius.circular(10)),
                          contentPadding: const EdgeInsets.symmetric(horizontal: 8, vertical: 8),
                        ),
                        items: const [
                          DropdownMenuItem(value: 'all', child: Text('সব স্ট্যাটাস', style: TextStyle(fontSize: 12))),
                          DropdownMenuItem(value: 'new', child: Text('New', style: TextStyle(fontSize: 12))),
                          DropdownMenuItem(value: 'awaiting_customer_confirmation', child: Text('Confirm বাকি', style: TextStyle(fontSize: 12))),
                          DropdownMenuItem(value: 'verified', child: Text('Verified', style: TextStyle(fontSize: 12))),
                          DropdownMenuItem(value: 'packed', child: Text('Packed', style: TextStyle(fontSize: 12))),
                          DropdownMenuItem(value: 'on_the_way', child: Text('On Way', style: TextStyle(fontSize: 12))),
                          DropdownMenuItem(value: 'delivered', child: Text('Delivered', style: TextStyle(fontSize: 12))),
                          DropdownMenuItem(value: 'cancelled', child: Text('Cancelled', style: TextStyle(fontSize: 12))),
                        ],
                        onChanged: (v) {
                          if (v != null) {
                            setState(() => _statusFilter = v);
                            _loadOrders();
                          }
                        },
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
          Expanded(
            child: _loading
                ? const Center(child: CircularProgressIndicator())
                : _orders.isEmpty
                    ? const Center(child: Text('কোনো অনলাইন অর্ডার পাওয়া যায়নি'))
                    : RefreshIndicator(
                        onRefresh: _loadOrders,
                        child: ListView.builder(
                          padding: const EdgeInsets.all(12),
                          itemCount: _orders.length,
                          itemBuilder: (_, idx) {
                            final o = _orders[idx];
                            final bool isPharm = o['is_pharmacy_order'] == true;
                            final String st = (o['order_status'] ?? 'new').toString();
                            final bool isAwaiting = st.toLowerCase() == 'awaiting_customer_confirmation';
                            final Color deptColor = isAwaiting
                                ? const Color(0xFFD97706)
                                : (isPharm ? const Color(0xFF0F766E) : const Color(0xFF6B21A8));
                            final Color stColor = _statusColor(st);
                            final items = (o['items'] as List? ?? []).whereType<Map>().toList();
                            final rxUrl = (o['prescription_url'] ?? '').toString();

                            return Card(
                              margin: const EdgeInsets.only(bottom: 12),
                              shape: RoundedRectangleBorder(
                                borderRadius: BorderRadius.circular(12),
                                side: BorderSide(color: deptColor.withValues(alpha: isAwaiting ? 0.9 : 0.35), width: isAwaiting ? 1.8 : 1.0),
                              ),
                              child: Padding(
                                padding: const EdgeInsets.all(12),
                                child: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Row(
                                      children: [
                                        Container(
                                          padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
                                          decoration: BoxDecoration(color: deptColor, borderRadius: BorderRadius.circular(6)),
                                          child: Text(
                                            isPharm ? '💊 ফার্মেসী Rx' : '🛒 সুপারশপ',
                                            style: const TextStyle(color: Colors.white, fontSize: 10, fontWeight: FontWeight.bold),
                                          ),
                                        ),
                                        const SizedBox(width: 8),
                                        Expanded(
                                          child: Text(
                                            '#${o['order_number']}',
                                            style: const TextStyle(fontWeight: FontWeight.w900, fontSize: 14),
                                          ),
                                        ),
                                        Container(
                                          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                                          decoration: BoxDecoration(color: stColor, borderRadius: BorderRadius.circular(12)),
                                          child: Text(
                                            st.toUpperCase(),
                                            style: const TextStyle(color: Colors.white, fontSize: 10, fontWeight: FontWeight.bold),
                                          ),
                                        ),
                                      ],
                                    ),
                                    const SizedBox(height: 8),
                                    InkWell(
                                      onTap: () => _openCustomerProfileDialog(
                                        (o['customer_phone'] ?? '').toString(),
                                        (o['customer_name'] ?? '').toString(),
                                      ),
                                      child: Row(
                                        children: [
                                          const Icon(Icons.person, size: 15, color: Colors.teal),
                                          const SizedBox(width: 4),
                                          Expanded(
                                            child: Text(
                                              '${o['customer_name'] ?? ''} • ${o['customer_phone'] ?? ''} (প্রোফাইল দেখুন ➔)',
                                              style: TextStyle(
                                                fontSize: 12.5,
                                                fontWeight: FontWeight.bold,
                                                color: Colors.teal.shade800,
                                                decoration: TextDecoration.underline,
                                              ),
                                            ),
                                          ),
                                        ],
                                      ),
                                    ),
                                    const SizedBox(height: 4),
                                    Text(
                                      '📍 ${o['address_details'] ?? ''} (${o['area'] ?? ''}, ${o['district'] ?? ''})',
                                      style: const TextStyle(fontSize: 11.5, color: Colors.black87),
                                    ),
                                    Text(
                                      '📅 ${o['created_at'] ?? ''} • সদস্য: ${o['customer_member_since'] ?? '-'} • মোট: ৳${((o['total_amount'] ?? 0) as num).toStringAsFixed(2)}',
                                      style: const TextStyle(fontSize: 11, color: Colors.black54, fontWeight: FontWeight.w600),
                                    ),
                                    if ((o['assigned_rider_name'] ?? '').toString().isNotEmpty)
                                      Text(
                                        '🛵 রাইডার: ${o['assigned_rider_name']} (${o['assigned_rider_phone'] ?? ''})',
                                        style: TextStyle(fontSize: 11.5, color: Colors.blue.shade800, fontWeight: FontWeight.w700),
                                      ),
                                    if (rxUrl.isNotEmpty)
                                      Padding(
                                        padding: const EdgeInsets.only(top: 6),
                                        child: InkWell(
                                          onTap: () => _openPrescriptionZoom(rxUrl),
                                          child: Row(
                                            children: [
                                              ClipRRect(
                                                borderRadius: BorderRadius.circular(6),
                                                child: SizedBox(
                                                  width: 48,
                                                  height: 48,
                                                  child: AppImageLoader(imageUrl: rxUrl, fit: BoxFit.cover),
                                                ),
                                              ),
                                              const SizedBox(width: 8),
                                              Text(
                                                '📋 প্রেসক্রিপশন বড় করে দেখুন',
                                                style: TextStyle(color: Colors.teal.shade800, fontWeight: FontWeight.bold, fontSize: 12),
                                              ),
                                            ],
                                          ),
                                        ),
                                      ),
                                    if (items.isNotEmpty) ...[
                                      const SizedBox(height: 6),
                                      Container(
                                        width: double.infinity,
                                        padding: const EdgeInsets.all(8),
                                        decoration: BoxDecoration(
                                          color: Colors.grey.shade50,
                                          borderRadius: BorderRadius.circular(8),
                                          border: Border.all(color: Colors.grey.shade200),
                                        ),
                                        child: Column(
                                          crossAxisAlignment: CrossAxisAlignment.start,
                                          children: items
                                              .take(6)
                                              .map((it) => Text(
                                                    '• ${it['product_name'] ?? ''} × ${it['quantity'] ?? 1} — ৳${((it['total_price'] ?? 0) as num).toStringAsFixed(0)}',
                                                    style: const TextStyle(fontSize: 11.5),
                                                  ))
                                              .toList(),
                                        ),
                                      ),
                                    ],
                                    const SizedBox(height: 8),
                                    Wrap(
                                      spacing: 6,
                                      runSpacing: 6,
                                      children: [
                                        if (isPharm && o['pharmacy_order_id'] != null)
                                          ElevatedButton.icon(
                                            onPressed: () async {
                                              final rxOrder = Map<String, dynamic>.from(o);
                                              rxOrder['id'] = o['pharmacy_order_id'];
                                              final updated = await RxQuoteBuilderSheet.open(
                                                context,
                                                order: rxOrder,
                                                isAdmin: true,
                                                riderPhone: _staffPhone,
                                              );
                                              if (updated == true) _loadOrders();
                                            },
                                            icon: const Icon(Icons.edit_note, size: 15),
                                            label: const Text('Rx কোট / বিল', style: TextStyle(fontSize: 11)),
                                            style: ElevatedButton.styleFrom(backgroundColor: Colors.teal.shade700, foregroundColor: Colors.white),
                                          ),
                                        OutlinedButton.icon(
                                          onPressed: () => _openStatusAndRiderDialog(o),
                                          icon: const Icon(Icons.sync_alt, size: 14),
                                          label: const Text('স্ট্যাটাস / রাইডার', style: TextStyle(fontSize: 11)),
                                        ),
                                        if (st.toLowerCase() != 'delivered' && st.toLowerCase() != 'cancelled')
                                          OutlinedButton.icon(
                                            onPressed: () => _openOtpDialog(o),
                                            icon: const Icon(Icons.vpn_key, size: 14),
                                            label: const Text('OTP ডেলিভারি', style: TextStyle(fontSize: 11)),
                                          ),
                                        OutlinedButton.icon(
                                          onPressed: () => _openEditAddressDialog(o),
                                          icon: const Icon(Icons.edit_location_alt, size: 14),
                                          label: const Text('ঠিকানা', style: TextStyle(fontSize: 11)),
                                        ),
                                        OutlinedButton.icon(
                                          onPressed: () => ThermalPrintHelper.printAndConfirm(
                                            context,
                                            riderPhone: _staffPhone,
                                            sourceType: 'online_order',
                                            sourceId: ((o['id'] ?? 0) as num).toInt(),
                                            invoiceNumber: (o['order_number'] ?? '').toString(),
                                          ),
                                          icon: const Icon(Icons.print, size: 14),
                                          label: const Text('প্রিন্ট', style: TextStyle(fontSize: 11)),
                                        ),
                                        if (_staffRole == 'admin')
                                          IconButton(
                                            tooltip: 'অর্ডার ডিলিট',
                                            icon: const Icon(Icons.delete_outline, color: Colors.red, size: 19),
                                            onPressed: () => _confirmDeleteOrder(o),
                                          ),
                                      ],
                                    ),
                                  ],
                                ),
                              ),
                            );
                          },
                        ),
                      ),
          ),
        ],
      ),
    );
  }
}
