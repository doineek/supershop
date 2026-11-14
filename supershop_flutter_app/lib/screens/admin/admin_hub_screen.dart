import 'dart:async';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../../services/api_service.dart';
import '../../widgets/rx_quote_builder_sheet.dart';
import '../../widgets/thermal_print_helper.dart';
import '../auth/login_screen.dart';
import '../customer/home_screen.dart';
import 'admin_online_orders_screen.dart';
import 'admin_pharmacy_panel_screen.dart';
import 'admin_reports_screen.dart';
import 'admin_riders_screen.dart';
import 'admin_settings_screen.dart';

class AdminHubScreen extends StatefulWidget {
  final String? username;
  final String? role;

  const AdminHubScreen({super.key, this.username, this.role});

  @override
  State<AdminHubScreen> createState() => _AdminHubScreenState();
}

class _AdminHubScreenState extends State<AdminHubScreen> with SingleTickerProviderStateMixin {
  late final TabController _tabCtrl;

  String _displayName = 'Admin';
  String _role = 'admin';
  String _staffPhone = '';

  bool _loadingDashboard = true;
  bool _loadingRxOrders = true;
  bool _loadingMeds = true;
  bool _loadingRiders = true;

  Map<String, dynamic> _dash = {};
  List<Map<String, dynamic>> _rxOrders = [];
  List<Map<String, dynamic>> _recentOnlineOrders = [];
  List<Map<String, dynamic>> _medicines = [];
  List<Map<String, dynamic>> _riders = [];

  final TextEditingController _medSearchCtrl = TextEditingController();
  Timer? _medDebounce;
  String _rxFilter = '';

  @override
  void initState() {
    super.initState();
    _tabCtrl = TabController(length: 3, vsync: this);
    _loadIdentity();
    _refreshAll();
  }

  @override
  void dispose() {
    _medDebounce?.cancel();
    _medSearchCtrl.dispose();
    _tabCtrl.dispose();
    super.dispose();
  }

  Future<void> _loadIdentity() async {
    final prefs = await SharedPreferences.getInstance();
    if (!mounted) return;
    setState(() {
      _displayName = widget.username ?? prefs.getString('user_name') ?? prefs.getString('user_phone') ?? 'Admin';
      _role = widget.role ?? prefs.getString('user_role') ?? 'admin';
      _staffPhone = prefs.getString('user_phone') ?? '';
    });
  }

  Future<void> _refreshAll() async {
    await Future.wait([
      _loadDashboard(),
      _loadPharmacyOrders(),
      _loadMedicines(_medSearchCtrl.text),
      _loadRiders(),
    ]);
  }

  Future<void> _loadDashboard() async {
    if (mounted) setState(() => _loadingDashboard = true);
    final res = await ApiService.fetchAdminMobileDashboard();
    if (!mounted) return;
    setState(() {
      _dash = res;
      _recentOnlineOrders = (res['recent_orders'] as List? ?? [])
          .whereType<Map>()
          .map((e) => Map<String, dynamic>.from(e))
          .toList();
      _loadingDashboard = false;
    });
  }

  Future<void> _loadPharmacyOrders() async {
    if (mounted) setState(() => _loadingRxOrders = true);
    final res = await ApiService.fetchAdminPharmacyOrders(status: _rxFilter);
    if (!mounted) return;
    setState(() {
      _rxOrders = (res['orders'] as List? ?? [])
          .whereType<Map>()
          .map((e) => Map<String, dynamic>.from(e))
          .toList();
      _loadingRxOrders = false;
    });
  }

  Future<void> _loadMedicines(String q) async {
    if (mounted) setState(() => _loadingMeds = true);
    final res = await ApiService.fetchAdminMedicines(query: q, perPage: 60);
    if (!mounted) return;
    setState(() {
      _medicines = (res['medicines'] as List? ?? [])
          .whereType<Map>()
          .map((e) => Map<String, dynamic>.from(e))
          .toList();
      _loadingMeds = false;
    });
  }

  Future<void> _loadRiders() async {
    if (mounted) setState(() => _loadingRiders = true);
    final res = await ApiService.fetchAdminRiders();
    if (!mounted) return;
    setState(() {
      _riders = (res['riders'] as List? ?? [])
          .whereType<Map>()
          .map((e) => Map<String, dynamic>.from(e))
          .toList();
      _loadingRiders = false;
    });
  }

  Future<void> _openInAppScreen(Widget screen) async {
    await Navigator.push(context, MaterialPageRoute(builder: (_) => screen));
    if (mounted) {
      _refreshAll();
    }
  }

  Future<void> _logout() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove('user_phone');
    await prefs.remove('user_name');
    await prefs.remove('user_role');
    await prefs.remove('is_admin_mode');
    await prefs.remove('stay_signed_in');
    await ApiService.setStaffToken('');
    if (!mounted) return;
    Navigator.pushAndRemoveUntil(
      context,
      MaterialPageRoute(builder: (_) => const LoginScreen()),
      (route) => false,
    );
  }

  void _openEditMedicineDialog(Map<String, dynamic> med) {
    final nameCtrl = TextEditingController(text: (med['name'] ?? '').toString());
    final stockCtrl = TextEditingController(text: '${((med['stock_qty'] ?? 0) as num).toInt()}');
    final mrpCtrl = TextEditingController(text: '${med['mrp'] ?? med['unit_price'] ?? 0}');
    final pieceSellCtrl = TextEditingController(text: '${med['unit_price'] ?? med['mrp'] ?? 0}');
    final pieceCostCtrl = TextEditingController(text: '${med['cost_price'] ?? 0}');

    final stripSizeCtrl = TextEditingController(text: '${((med['strip_size'] ?? 10) as num).toInt()}');
    final stripSellCtrl = TextEditingController(text: '${med['strip_price'] ?? 0}');
    final stripCostCtrl = TextEditingController(text: '${med['strip_cost_price'] ?? 0}');

    final packetSizeCtrl = TextEditingController(text: '${((med['packet_size'] ?? 30) as num).toInt()}');
    final packetSellCtrl = TextEditingController(text: '${med['packet_price'] ?? 0}');
    final packetCostCtrl = TextEditingController(text: '${med['packet_cost_price'] ?? 0}');

    bool saving = false;

    void autoCalcFromPiece() {
      final double ps = double.tryParse(pieceSellCtrl.text) ?? 0;
      final double pc = double.tryParse(pieceCostCtrl.text) ?? 0;
      final int sSize = int.tryParse(stripSizeCtrl.text) ?? 10;
      final int pSize = int.tryParse(packetSizeCtrl.text) ?? 30;
      if (ps > 0) {
        stripSellCtrl.text = (ps * sSize).toStringAsFixed(2);
        packetSellCtrl.text = (ps * pSize).toStringAsFixed(2);
      }
      if (pc > 0) {
        stripCostCtrl.text = (pc * sSize).toStringAsFixed(2);
        packetCostCtrl.text = (pc * pSize).toStringAsFixed(2);
      }
    }

    showDialog(
      context: context,
      builder: (dlgCtx) => StatefulBuilder(
        builder: (_, setDlgState) => AlertDialog(
          title: Text('💊 ${med['name'] ?? 'ঔষধ এডিট'}', style: const TextStyle(fontSize: 15, fontWeight: FontWeight.bold)),
          content: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                TextField(
                  controller: nameCtrl,
                  decoration: const InputDecoration(labelText: 'ঔষধের নাম', isDense: true),
                ),
                const SizedBox(height: 8),
                Row(
                  children: [
                    Expanded(
                      child: TextField(
                        controller: stockCtrl,
                        keyboardType: TextInputType.number,
                        decoration: const InputDecoration(labelText: 'মোট পিস স্টক', isDense: true),
                      ),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: TextField(
                        controller: mrpCtrl,
                        keyboardType: const TextInputType.numberWithOptions(decimal: true),
                        decoration: const InputDecoration(labelText: 'পিস MRP (৳)', isDense: true),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 10),
                Container(
                  padding: const EdgeInsets.all(8),
                  decoration: BoxDecoration(color: Colors.blue.shade50, borderRadius: BorderRadius.circular(8)),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text('১ পিস মূল্য (৳)', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 12)),
                      const SizedBox(height: 4),
                      Row(
                        children: [
                          Expanded(
                            child: TextField(
                              controller: pieceCostCtrl,
                              keyboardType: const TextInputType.numberWithOptions(decimal: true),
                              decoration: const InputDecoration(labelText: 'পিস ক্রয় (৳)', isDense: true),
                            ),
                          ),
                          const SizedBox(width: 8),
                          Expanded(
                            child: TextField(
                              controller: pieceSellCtrl,
                              keyboardType: const TextInputType.numberWithOptions(decimal: true),
                              decoration: const InputDecoration(labelText: 'পিস বিক্রয় (৳)', isDense: true),
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 6),
                Align(
                  alignment: Alignment.centerRight,
                  child: TextButton.icon(
                    onPressed: () {
                      autoCalcFromPiece();
                      setDlgState(() {});
                    },
                    icon: const Icon(Icons.calculate, size: 16),
                    label: const Text('পিস থেকে পাতা ও প্যাকেট হিসাব করুন', style: TextStyle(fontSize: 11.5)),
                  ),
                ),
                Container(
                  padding: const EdgeInsets.all(8),
                  decoration: BoxDecoration(color: Colors.teal.shade50, borderRadius: BorderRadius.circular(8)),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text('১ পাতা (Strip) মূল্য', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 12)),
                      const SizedBox(height: 4),
                      Row(
                        children: [
                          SizedBox(
                            width: 66,
                            child: TextField(
                              controller: stripSizeCtrl,
                              keyboardType: TextInputType.number,
                              decoration: const InputDecoration(labelText: 'পিস/পাতা', isDense: true),
                            ),
                          ),
                          const SizedBox(width: 6),
                          Expanded(
                            child: TextField(
                              controller: stripCostCtrl,
                              keyboardType: const TextInputType.numberWithOptions(decimal: true),
                              decoration: const InputDecoration(labelText: 'পাতা ক্রয়', isDense: true),
                            ),
                          ),
                          const SizedBox(width: 6),
                          Expanded(
                            child: TextField(
                              controller: stripSellCtrl,
                              keyboardType: const TextInputType.numberWithOptions(decimal: true),
                              decoration: const InputDecoration(labelText: 'পাতা বিক্রয়', isDense: true),
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 8),
                Container(
                  padding: const EdgeInsets.all(8),
                  decoration: BoxDecoration(color: Colors.purple.shade50, borderRadius: BorderRadius.circular(8)),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text('১ প্যাকেট / বক্স মূল্য', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 12)),
                      const SizedBox(height: 4),
                      Row(
                        children: [
                          SizedBox(
                            width: 66,
                            child: TextField(
                              controller: packetSizeCtrl,
                              keyboardType: TextInputType.number,
                              decoration: const InputDecoration(labelText: 'পিস/প্যাক', isDense: true),
                            ),
                          ),
                          const SizedBox(width: 6),
                          Expanded(
                            child: TextField(
                              controller: packetCostCtrl,
                              keyboardType: const TextInputType.numberWithOptions(decimal: true),
                              decoration: const InputDecoration(labelText: 'প্যাক ক্রয়', isDense: true),
                            ),
                          ),
                          const SizedBox(width: 6),
                          Expanded(
                            child: TextField(
                              controller: packetSellCtrl,
                              keyboardType: const TextInputType.numberWithOptions(decimal: true),
                              decoration: const InputDecoration(labelText: 'প্যাক বিক্রয়', isDense: true),
                            ),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.of(dlgCtx).pop(),
              child: const Text('বাতিল'),
            ),
            ElevatedButton(
              onPressed: saving
                  ? null
                  : () async {
                      setDlgState(() => saving = true);
                      final payload = {
                        'id': med['id'],
                        'name': nameCtrl.text.trim(),
                        'sku': med['sku'] ?? '',
                        'dosage_form': med['dosage_form'] ?? 'Tablet',
                        'strength': med['strength'] ?? '',
                        'generic_name': med['generic_name'] ?? '',
                        'manufacturer': med['manufacturer'] ?? '',
                        'stock_qty': int.tryParse(stockCtrl.text.trim()) ?? 0,
                        'mrp': double.tryParse(mrpCtrl.text.trim()) ?? 0,
                        'unit_price': double.tryParse(pieceSellCtrl.text.trim()) ?? 0,
                        'cost_price': double.tryParse(pieceCostCtrl.text.trim()) ?? 0,
                        'strip_size': int.tryParse(stripSizeCtrl.text.trim()) ?? 10,
                        'strip_price': double.tryParse(stripSellCtrl.text.trim()) ?? 0,
                        'strip_cost_price': double.tryParse(stripCostCtrl.text.trim()) ?? 0,
                        'packet_size': int.tryParse(packetSizeCtrl.text.trim()) ?? 30,
                        'packet_price': double.tryParse(packetSellCtrl.text.trim()) ?? 0,
                        'packet_cost_price': double.tryParse(packetCostCtrl.text.trim()) ?? 0,
                      };
                      final res = await ApiService.saveAdminMedicine(payload);
                      if (!dlgCtx.mounted) return;
                      Navigator.of(dlgCtx).pop();
                      if (!mounted) return;
                      ScaffoldMessenger.of(context).showSnackBar(
                        SnackBar(
                          content: Text(res['success'] == true
                              ? '✅ ঔষধের ক্রয়-বিক্রয় মূল্য আপডেট হয়েছে'
                              : (res['message']?.toString() ?? 'সংরক্ষণ ব্যর্থ হয়েছে')),
                          backgroundColor: res['success'] == true ? Colors.green.shade700 : Colors.red,
                        ),
                      );
                      _loadMedicines(_medSearchCtrl.text);
                    },
              style: ElevatedButton.styleFrom(backgroundColor: Colors.teal.shade700, foregroundColor: Colors.white),
              child: Text(saving ? 'সেভ হচ্ছে...' : 'সংরক্ষণ'),
            ),
          ],
        ),
      ),
    );
  }

  void _openStatusDialog(Map<String, dynamic> order) {
    final String current = (order['order_status'] ?? 'pending').toString();
    final bool customerConfirmed = order['customer_confirmed'] == true;
    int? selectedRiderId = ((order['assigned_rider_id'] ?? 0) as num).toInt();
    if (selectedRiderId <= 0) selectedRiderId = null;

    String targetStatus = current;
    final List<String> allowedStatuses = [
      'reviewing',
      'confirmed',
      'packed',
      'on_the_way',
      'delivered',
      'cancelled',
    ];
    if (!allowedStatuses.contains(targetStatus)) {
      targetStatus = 'confirmed';
    }

    showDialog(
      context: context,
      builder: (dlgCtx) => StatefulBuilder(
        builder: (_, setDlgState) => AlertDialog(
          title: Text('স্ট্যাটাস পরিবর্তন • #${order['order_number'] ?? ''}'),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (current == 'awaiting_customer_confirmation' && !customerConfirmed)
                Container(
                  padding: const EdgeInsets.all(8),
                  margin: const EdgeInsets.only(bottom: 10),
                  decoration: BoxDecoration(
                    color: Colors.amber.shade50,
                    borderRadius: BorderRadius.circular(8),
                    border: Border.all(color: Colors.amber.shade400),
                  ),
                  child: const Text(
                    '⚠️ কাস্টমার এখনও বিল কনফার্ম করেননি। কাস্টমার কনফার্ম করার আগে প্যাকড/ডেলিভারি করা যাবে না (প্রয়োজনে বাতিল করা যাবে)।',
                    style: TextStyle(fontSize: 11.5, color: Colors.black87),
                  ),
                ),
              DropdownButtonFormField<String>(
                initialValue: targetStatus,
                decoration: const InputDecoration(labelText: 'নতুন স্ট্যাটাস', isDense: true, border: OutlineInputBorder()),
                items: allowedStatuses
                    .map((s) => DropdownMenuItem(value: s, child: Text(s.toUpperCase())))
                    .toList(),
                onChanged: (v) {
                  if (v != null) setDlgState(() => targetStatus = v);
                },
              ),
              const SizedBox(height: 10),
              DropdownButtonFormField<int?>(
                initialValue: selectedRiderId,
                decoration: const InputDecoration(labelText: 'রাইডার অ্যাসাইন (ঐচ্ছিক)', isDense: true, border: OutlineInputBorder()),
                items: [
                  const DropdownMenuItem<int?>(value: null, child: Text('রাইডার নির্বাচন করুন')),
                  ..._riders.map((r) => DropdownMenuItem<int?>(
                        value: (r['id'] as num).toInt(),
                        child: Text('${r['full_name']} (${r['username']})'),
                      )),
                ],
                onChanged: (v) => setDlgState(() => selectedRiderId = v),
              ),
            ],
          ),
          actions: [
            TextButton(onPressed: () => Navigator.of(dlgCtx).pop(), child: const Text('বাতিল')),
            ElevatedButton(
              onPressed: () async {
                final res = await ApiService.updateAdminPharmacyOrderStatus(
                  orderId: ((order['id'] ?? 0) as num).toInt(),
                  status: targetStatus,
                  riderId: selectedRiderId,
                );
                if (!dlgCtx.mounted) return;
                Navigator.of(dlgCtx).pop();
                if (!mounted) return;
                ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(
                    content: Text(res['message']?.toString() ??
                        (res['success'] == true ? 'স্ট্যাটাস আপডেট হয়েছে' : 'আপডেট ব্যর্থ হয়েছে')),
                    backgroundColor: res['success'] == true ? Colors.green.shade700 : Colors.red,
                  ),
                );
                _loadPharmacyOrders();
                _loadDashboard();
              },
              style: ElevatedButton.styleFrom(backgroundColor: Colors.teal.shade700, foregroundColor: Colors.white),
              child: const Text('আপডেট করুন'),
            ),
          ],
        ),
      ),
    );
  }

  Widget _statTile(String label, String val, IconData icon, Color color, {VoidCallback? onTap}) {
    return Expanded(
      child: InkWell(
        onTap: onTap,
        borderRadius: BorderRadius.circular(12),
        child: Container(
          padding: const EdgeInsets.all(11),
          decoration: BoxDecoration(
            color: color.withValues(alpha: 0.08),
            borderRadius: BorderRadius.circular(12),
            border: Border.all(color: color.withValues(alpha: 0.25)),
          ),
          child: Column(
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Row(
                children: [
                  Icon(icon, color: color, size: 18),
                  const SizedBox(width: 6),
                  Expanded(
                    child: Text(label, style: TextStyle(fontSize: 11, color: color, fontWeight: FontWeight.bold), overflow: TextOverflow.ellipsis),
                  ),
                ],
              ),
              const SizedBox(height: 6),
              Text(val, style: TextStyle(fontSize: 16, fontWeight: FontWeight.w900, color: color)),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildDashboardTab() {
    if (_loadingDashboard) return const Center(child: CircularProgressIndicator());
    final bool pcOnline = _dash['pc_agent_online'] == true;
    final String pcPrinter = (_dash['pc_printer_name'] ?? '').toString();

    return RefreshIndicator(
      onRefresh: _refreshAll,
      child: ListView(
        padding: const EdgeInsets.all(14),
        children: [
          Row(
            children: [
              _statTile(
                'আজকের বিক্রি',
                '৳${((_dash['sales_today'] ?? 0) as num).toStringAsFixed(0)}',
                Icons.point_of_sale,
                Colors.teal.shade800,
                onTap: () => _openInAppScreen(const AdminReportsScreen()),
              ),
              const SizedBox(width: 8),
              _statTile(
                'আজকের লাভ',
                '৳${((_dash['profit_today'] ?? 0) as num).toStringAsFixed(0)}',
                Icons.trending_up,
                Colors.green.shade800,
                onTap: () => _openInAppScreen(const AdminReportsScreen()),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Row(
            children: [
              _statTile(
                'পেন্ডিং অনলাইন',
                '${_dash['pending_online_orders'] ?? 0} টি',
                Icons.shopping_bag,
                Colors.orange.shade800,
                onTap: () => _openInAppScreen(AdminOnlineOrdersScreen(staffPhone: _staffPhone)),
              ),
              const SizedBox(width: 8),
              _statTile(
                'পেন্ডিং Rx',
                '${_dash['pending_rx_orders'] ?? 0} টি',
                Icons.medical_services,
                Colors.indigo.shade800,
                onTap: () => _openInAppScreen(AdminPharmacyPanelScreen(initialTab: 0, staffPhone: _staffPhone)),
              ),
            ],
          ),
          const SizedBox(height: 8),
          Row(
            children: [
              _statTile(
                'মোট পণ্য / ঔষধ',
                '${_dash['products_count'] ?? 0} / ${_dash['medicines_count'] ?? 0}',
                Icons.inventory_2,
                Colors.blue.shade800,
                onTap: () => _openInAppScreen(AdminPharmacyPanelScreen(initialTab: 1, staffPhone: _staffPhone)),
              ),
              const SizedBox(width: 8),
              _statTile(
                'কাস্টমার / লো স্টক',
                '${_dash['customers_count'] ?? 0} / ${_dash['low_stock_medicines'] ?? 0}',
                Icons.people,
                Colors.deepPurple.shade800,
                onTap: () => _openInAppScreen(AdminOnlineOrdersScreen(staffPhone: _staffPhone)),
              ),
            ],
          ),
          const SizedBox(height: 14),

          // Windows PC Thermal Printer Status + Test Print
          Container(
            padding: const EdgeInsets.all(12),
            decoration: BoxDecoration(
              color: pcOnline ? Colors.green.shade50 : Colors.amber.shade50,
              borderRadius: BorderRadius.circular(12),
              border: Border.all(color: pcOnline ? Colors.green.shade300 : Colors.amber.shade400),
            ),
            child: Row(
              children: [
                Icon(pcOnline ? Icons.print : Icons.print_disabled, color: pcOnline ? Colors.green.shade800 : Colors.amber.shade900),
                const SizedBox(width: 10),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        pcOnline ? '🟢 দোকানের PC থার্মাল প্রিন্টার অনলাইন' : '🔴 দোকানের PC প্রিন্ট এজেন্ট অফলাইন',
                        style: TextStyle(fontWeight: FontWeight.bold, fontSize: 13, color: pcOnline ? Colors.green.shade900 : Colors.amber.shade900),
                      ),
                      Text(
                        pcPrinter.isNotEmpty
                            ? 'প্রিন্টার: $pcPrinter'
                            : 'দোকানের Windows PC-তে pc_print_agent.py চালু থাকলে ক্লাউড প্রিন্ট সাথে সাথে হবে।',
                        style: const TextStyle(fontSize: 11, color: Colors.black87),
                      ),
                    ],
                  ),
                ),
                ElevatedButton(
                  onPressed: () => ThermalPrintHelper.runTestPrintAndConfirm(context),
                  style: ElevatedButton.styleFrom(backgroundColor: Colors.teal.shade700, foregroundColor: Colors.white),
                  child: const Text('টেস্ট প্রিন্ট', style: TextStyle(fontSize: 11.5, fontWeight: FontWeight.bold)),
                ),
              ],
            ),
          ),
          const SizedBox(height: 16),

          // Native In-App Admin Modules (Opens inside the App — never external browser)
          const Text('📱 অ্যাপ অ্যাডমিন প্যানেল মডিউলসমূহ (অ্যাপের ভেতরেই)', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 13.5)),
          const SizedBox(height: 8),
          Wrap(
            spacing: 8,
            runSpacing: 8,
            children: [
              ActionChip(
                avatar: const Icon(Icons.shopping_cart, size: 17),
                label: const Text('অনলাইন অর্ডার্স'),
                onPressed: () => _openInAppScreen(AdminOnlineOrdersScreen(staffPhone: _staffPhone)),
              ),
              ActionChip(
                avatar: const Icon(Icons.local_pharmacy, size: 17),
                label: const Text('ফার্মেসী প্যানেল'),
                onPressed: () => _openInAppScreen(AdminPharmacyPanelScreen(staffPhone: _staffPhone)),
              ),
              ActionChip(
                avatar: const Icon(Icons.bar_chart, size: 17),
                label: const Text('রিপোর্ট ও লাভ-লস'),
                onPressed: () => _openInAppScreen(const AdminReportsScreen()),
              ),
              ActionChip(
                avatar: const Icon(Icons.delivery_dining, size: 17),
                label: const Text('রাইডার্স ও পেআউট'),
                onPressed: () => _openInAppScreen(const AdminRidersScreen()),
              ),
              ActionChip(
                avatar: const Icon(Icons.settings, size: 17),
                label: const Text('সেটিংস ও প্রিন্টার'),
                onPressed: () => _openInAppScreen(const AdminSettingsScreen()),
              ),
            ],
          ),
          const SizedBox(height: 18),

          OutlinedButton.icon(
            onPressed: () => Navigator.push(context, MaterialPageRoute(builder: (_) => const HomeScreen())),
            icon: const Icon(Icons.storefront),
            label: const Text('কাস্টমার অ্যাপ হিসেবে দেখুন'),
          ),
        ],
      ),
    );
  }

  Widget _buildOrdersTab() {
    return RefreshIndicator(
      onRefresh: () async {
        await _loadPharmacyOrders();
        await _loadDashboard();
      },
      child: ListView(
        padding: const EdgeInsets.all(12),
        children: [
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: Row(
              children: [
                for (final pair in [
                  {'k': '', 'label': 'সব Rx অর্ডার'},
                  {'k': 'pending', 'label': 'নতুন (Pending)'},
                  {'k': 'awaiting_customer_confirmation', 'label': 'কনফার্মেশন পেন্ডিং'},
                  {'k': 'confirmed', 'label': 'Confirmed'},
                ])
                  Padding(
                    padding: const EdgeInsets.only(right: 6),
                    child: ChoiceChip(
                      label: Text(pair['label']!, style: const TextStyle(fontSize: 11.5)),
                      selected: _rxFilter == pair['k'],
                      onSelected: (_) {
                        setState(() => _rxFilter = pair['k']!);
                        _loadPharmacyOrders();
                      },
                    ),
                  ),
              ],
            ),
          ),
          const SizedBox(height: 8),
          if (_loadingRxOrders)
            const Center(child: Padding(padding: EdgeInsets.all(24), child: CircularProgressIndicator()))
          else if (_rxOrders.isEmpty)
            const Padding(
              padding: EdgeInsets.all(24),
              child: Center(child: Text('এই ফিল্টারে কোনো ফার্মেসী অর্ডার নেই।', style: TextStyle(color: Colors.grey))),
            )
          else
            ..._rxOrders.map((o) {
              final String st = (o['order_status'] ?? 'pending').toString();
              final bool awaitingCust = st == 'awaiting_customer_confirmation';
              final double total = ((o['total_amount'] ?? 0) as num).toDouble();
              final int orderId = ((o['id'] ?? 0) as num).toInt();

              return Card(
                margin: const EdgeInsets.only(bottom: 10),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(12),
                  side: BorderSide(color: awaitingCust ? Colors.amber.shade400 : Colors.grey.shade300),
                ),
                child: Padding(
                  padding: const EdgeInsets.all(11),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Row(
                        children: [
                          Expanded(
                            child: Text('💊 #${o['order_number'] ?? ''}', style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 14)),
                          ),
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                            decoration: BoxDecoration(
                              color: awaitingCust
                                  ? Colors.amber.shade700
                                  : (st == 'confirmed' ? Colors.green.shade700 : Colors.indigo.shade600),
                              borderRadius: BorderRadius.circular(6),
                            ),
                            child: Text(
                              awaitingCust ? '⏳ কাস্টমার কনফার্ম বাকি' : st.toUpperCase(),
                              style: const TextStyle(color: Colors.white, fontSize: 10, fontWeight: FontWeight.bold),
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 4),
                      Text('👤 ${o['customer_name'] ?? ''} • 📞 ${o['customer_phone'] ?? ''}', style: const TextStyle(fontSize: 12.5)),
                      Text('📍 ${o['delivery_address'] ?? ''}', style: const TextStyle(fontSize: 11.5, color: Colors.black54)),
                      if (total > 0)
                        Padding(
                          padding: const EdgeInsets.only(top: 4),
                          child: Text('মোট বিল: ৳${total.toStringAsFixed(0)}', style: TextStyle(fontWeight: FontWeight.bold, color: Colors.teal.shade800)),
                        ),
                      const SizedBox(height: 8),
                      Wrap(
                        spacing: 6,
                        runSpacing: 6,
                        children: [
                          ElevatedButton.icon(
                            onPressed: () async {
                              final updated = await RxQuoteBuilderSheet.open(
                                context,
                                order: o,
                                isAdmin: true,
                                riderPhone: _staffPhone,
                              );
                              if (updated == true) _loadPharmacyOrders();
                            },
                            icon: const Icon(Icons.edit_note, size: 16),
                            label: const Text('Rx ও বিল তৈরি', style: TextStyle(fontSize: 11.5)),
                            style: ElevatedButton.styleFrom(backgroundColor: Colors.teal.shade700, foregroundColor: Colors.white),
                          ),
                          OutlinedButton.icon(
                            onPressed: () => _openStatusDialog(o),
                            icon: const Icon(Icons.sync_alt, size: 15),
                            label: const Text('স্ট্যাটাস / রাইডার', style: TextStyle(fontSize: 11.5)),
                          ),
                          OutlinedButton.icon(
                            onPressed: () => ThermalPrintHelper.printAndConfirm(
                              context,
                              riderPhone: _staffPhone,
                              sourceType: 'pharmacy_order',
                              sourceId: orderId,
                              invoiceNumber: (o['order_number'] ?? '').toString(),
                            ),
                            icon: const Icon(Icons.print, size: 15),
                            label: const Text('PC প্রিন্ট', style: TextStyle(fontSize: 11.5)),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
              );
            }),

          const Divider(height: 24),
          const Text('🛒 সাম্প্রতিক অনলাইন অর্ডার (সাধারণ + Rx)', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 13.5)),
          const SizedBox(height: 8),
          ..._recentOnlineOrders.map((oo) => Card(
                margin: const EdgeInsets.only(bottom: 7),
                child: ListTile(
                  dense: true,
                  title: Text('#${oo['order_number']} • ${oo['customer_name']}', style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 12.5)),
                  subtitle: Text('${oo['order_status']} • ৳${((oo['total_amount'] ?? 0) as num).toStringAsFixed(0)} • রাইডার: ${(oo['assigned_rider_name'] ?? '').toString().isNotEmpty ? oo['assigned_rider_name'] : 'নেই'}', style: const TextStyle(fontSize: 11)),
                  trailing: IconButton(
                    icon: const Icon(Icons.print, color: Colors.teal),
                    onPressed: () => ThermalPrintHelper.printAndConfirm(
                      context,
                      riderPhone: _staffPhone,
                      sourceType: 'online_order',
                      sourceId: ((oo['id'] ?? 0) as num).toInt(),
                      invoiceNumber: (oo['order_number'] ?? '').toString(),
                    ),
                  ),
                ),
              )),
        ],
      ),
    );
  }

  Widget _buildMedsAndRidersTab() {
    return ListView(
      padding: const EdgeInsets.all(12),
      children: [
        const Text('🚴 রাইডার Rx স্ক্যান ও কোটেশন পারমিশন', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 13.5)),
        const SizedBox(height: 6),
        if (_loadingRiders)
          const Center(child: LinearProgressIndicator())
        else if (_riders.isEmpty)
          const Text('কোনো ডেলিভারি রাইডার অ্যাকাউন্ট পাওয়া যায়নি।', style: TextStyle(color: Colors.grey, fontSize: 12))
        else
          ..._riders.map((r) {
            final bool allowed = r['can_rx_quote_bill'] == true;
            return Card(
              margin: const EdgeInsets.only(bottom: 6),
              child: SwitchListTile(
                dense: true,
                value: allowed,
                title: Text('${r['full_name']} (${r['username']})', style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13)),
                subtitle: Text(
                  allowed
                      ? '✅ ক্যামেরা স্ক্যান ও Rx কোটেশন বিল করার অনুমতি চালু আছে'
                      : '🔒 অনুমতি বন্ধ (শুধু সাধারণ ডেলিভারি ও POS)',
                  style: TextStyle(fontSize: 11, color: allowed ? Colors.green.shade800 : Colors.grey.shade700),
                ),
                onChanged: (val) async {
                  final res = await ApiService.toggleAdminRiderPermission(
                    riderId: ((r['id'] ?? 0) as num).toInt(),
                    allow: val,
                  );
                  if (!mounted) return;
                  ScaffoldMessenger.of(context).showSnackBar(
                    SnackBar(
                      content: Text(res['message']?.toString() ?? 'আপডেট সম্পন্ন'),
                      backgroundColor: res['success'] == true ? Colors.teal.shade700 : Colors.red,
                    ),
                  );
                  _loadRiders();
                },
              ),
            );
          }),

        const Divider(height: 24),
        const Text('💊 ফার্মেসী ঔষধ (পিস / পাতা / প্যাকেট ক্রয়-বিক্রয় মূল্য)', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 13.5)),
        const SizedBox(height: 8),
        TextField(
          controller: _medSearchCtrl,
          onChanged: (v) {
            _medDebounce?.cancel();
            _medDebounce = Timer(const Duration(milliseconds: 300), () => _loadMedicines(v.trim()));
          },
          decoration: InputDecoration(
            hintText: 'ঔষধের নাম বা জেনেরিক লিখুন...',
            prefixIcon: const Icon(Icons.search, size: 19),
            isDense: true,
            border: OutlineInputBorder(borderRadius: BorderRadius.circular(10)),
          ),
        ),
        const SizedBox(height: 8),
        if (_loadingMeds)
          const Center(child: Padding(padding: EdgeInsets.all(20), child: CircularProgressIndicator()))
        else
          ..._medicines.map((m) => Card(
                margin: const EdgeInsets.only(bottom: 6),
                child: ListTile(
                  dense: true,
                  title: Text('${m['name']} (${m['strength'] ?? ''})', style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 12.5)),
                  subtitle: Text(
                    'পিস: ক্রয় ৳${m['cost_price'] ?? 0} / বিক্রয় ৳${m['unit_price'] ?? 0} | '
                    'পাতা(${m['strip_size'] ?? 10}): ৳${m['strip_price'] ?? 0} | '
                    'প্যাকেট(${m['packet_size'] ?? 30}): ৳${m['packet_price'] ?? 0} | স্টক: ${m['stock_qty'] ?? 0}',
                    style: const TextStyle(fontSize: 11),
                  ),
                  trailing: IconButton(
                    icon: const Icon(Icons.edit, color: Colors.teal),
                    onPressed: () => _openEditMedicineDialog(m),
                  ),
                ),
              )),
      ],
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        backgroundColor: Colors.teal.shade900,
        foregroundColor: Colors.white,
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text('দৈনিক সুপারশপ • অ্যাডমিন প্যানেল', style: TextStyle(fontSize: 15, fontWeight: FontWeight.bold)),
            Text('$_displayName (${_role.toUpperCase()})', style: const TextStyle(fontSize: 11, color: Colors.white70)),
          ],
        ),
        actions: [
          IconButton(icon: const Icon(Icons.refresh), onPressed: _refreshAll),
          IconButton(tooltip: 'Logout', icon: const Icon(Icons.logout, color: Colors.redAccent), onPressed: _logout),
        ],
        bottom: TabBar(
          controller: _tabCtrl,
          indicatorColor: Colors.amberAccent,
          labelColor: Colors.white,
          unselectedLabelColor: Colors.white70,
          tabs: const [
            Tab(icon: Icon(Icons.dashboard, size: 19), text: 'ড্যাশবোর্ড'),
            Tab(icon: Icon(Icons.receipt_long, size: 19), text: 'অর্ডার ও Rx'),
            Tab(icon: Icon(Icons.medication, size: 19), text: 'ঔষধ ও রাইডার'),
          ],
        ),
      ),
      body: TabBarView(
        controller: _tabCtrl,
        children: [
          _buildDashboardTab(),
          _buildOrdersTab(),
          _buildMedsAndRidersTab(),
        ],
      ),
    );
  }
}
