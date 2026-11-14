import 'dart:async';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../../services/admin_api_service.dart';
import '../../services/api_service.dart';
import '../../widgets/app_image_loader.dart';
import '../../widgets/rx_quote_builder_sheet.dart';
import '../../widgets/thermal_print_helper.dart';

class AdminPharmacyPanelScreen extends StatefulWidget {
  final int initialTab;
  final String? staffPhone;

  const AdminPharmacyPanelScreen({
    super.key,
    this.initialTab = 0,
    this.staffPhone,
  });

  @override
  State<AdminPharmacyPanelScreen> createState() => _AdminPharmacyPanelScreenState();
}

class _AdminPharmacyPanelScreenState extends State<AdminPharmacyPanelScreen>
    with SingleTickerProviderStateMixin {
  late final TabController _tabCtrl;
  String _staffPhone = '';

  bool _loadingOrders = true;
  bool _loadingMeds = true;
  bool _loadingSettings = true;
  bool _savingSettings = false;

  String _rxFilter = '';
  List<Map<String, dynamic>> _rxOrders = [];
  List<Map<String, dynamic>> _riders = [];
  List<Map<String, dynamic>> _medicines = [];

  final TextEditingController _medSearchCtrl = TextEditingController();
  Timer? _medDebounce;
  Timer? _liveSyncTimer;
  bool _isSilentSyncing = false;

  final TextEditingController _deliveryCtrl = TextEditingController(text: '50');
  final TextEditingController _discountCtrl = TextEditingController(text: '0');

  @override
  void initState() {
    super.initState();
    _tabCtrl = TabController(length: 3, vsync: this, initialIndex: widget.initialTab.clamp(0, 2));
    _initAndLoad();
    _liveSyncTimer = Timer.periodic(const Duration(seconds: 4), (_) {
      _loadRxOrders(silent: true);
    });
  }

  @override
  void dispose() {
    _liveSyncTimer?.cancel();
    _medDebounce?.cancel();
    _medSearchCtrl.dispose();
    _deliveryCtrl.dispose();
    _discountCtrl.dispose();
    _tabCtrl.dispose();
    super.dispose();
  }

  Future<void> _initAndLoad() async {
    final prefs = await SharedPreferences.getInstance();
    if (!mounted) return;
    setState(() {
      _staffPhone = (widget.staffPhone ?? '').isNotEmpty
          ? widget.staffPhone!
          : (prefs.getString('user_phone') ?? '');
    });
    await Future.wait([
      _loadRxOrders(),
      _loadMedicines(''),
      _loadSettings(),
      _loadRiders(),
    ]);
  }

  Future<void> _loadRiders() async {
    final res = await ApiService.fetchAdminRiders();
    if (!mounted) return;
    setState(() {
      _riders = (res['riders'] as List? ?? [])
          .whereType<Map>()
          .map((e) => Map<String, dynamic>.from(e))
          .toList();
    });
  }

  Future<void> _loadRxOrders({bool silent = false}) async {
    if (silent && _isSilentSyncing) return;
    if (silent) {
      _isSilentSyncing = true;
    } else if (mounted) {
      setState(() => _loadingOrders = true);
    }
    try {
      final res = await ApiService.fetchAdminPharmacyOrders(status: _rxFilter);
      if (!mounted) return;
      setState(() {
        _rxOrders = (res['orders'] as List? ?? [])
            .whereType<Map>()
            .map((e) => Map<String, dynamic>.from(e))
            .toList();
        _loadingOrders = false;
      });
    } finally {
      _isSilentSyncing = false;
    }
  }

  Future<void> _loadMedicines(String q) async {
    if (mounted) setState(() => _loadingMeds = true);
    final res = await ApiService.fetchAdminMedicines(query: q, perPage: 80);
    if (!mounted) return;
    setState(() {
      _medicines = (res['medicines'] as List? ?? [])
          .whereType<Map>()
          .map((e) => Map<String, dynamic>.from(e))
          .toList();
      _loadingMeds = false;
    });
  }

  Future<void> _loadSettings() async {
    if (mounted) setState(() => _loadingSettings = true);
    final res = await AdminApiService.fetchPharmacySettings();
    if (!mounted) return;
    final dynamic dCharge = res['delivery_charge'] ?? res['pharmacy_delivery_charge'] ?? 50;
    final dynamic dDisc = res['discount_percent'] ?? res['pharmacy_discount_percent'] ?? 0;
    setState(() {
      _deliveryCtrl.text = '$dCharge';
      _discountCtrl.text = '$dDisc';
      _loadingSettings = false;
    });
  }

  Future<void> _saveSettings() async {
    setState(() => _savingSettings = true);
    final res = await AdminApiService.savePharmacySettings({
      'delivery_charge': double.tryParse(_deliveryCtrl.text.trim()) ?? 50.0,
      'discount_percent': double.tryParse(_discountCtrl.text.trim()) ?? 0.0,
    });
    if (!mounted) return;
    setState(() => _savingSettings = false);
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(res['message']?.toString() ?? 'সেটিংস সংরক্ষণ সম্পন্ন'),
        backgroundColor: res['success'] == true ? Colors.green.shade700 : Colors.red,
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
              title: const Text('📋 প্রেসক্রিপশন'),
            ),
            Expanded(
              child: InteractiveViewer(
                minScale: 0.7,
                maxScale: 5.0,
                child: Center(child: AppImageLoader(imageUrl: url, fit: BoxFit.contain)),
              ),
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
    const allowedStatuses = ['reviewing', 'confirmed', 'packed', 'on_the_way', 'delivered', 'cancelled'];
    if (!allowedStatuses.contains(targetStatus)) targetStatus = 'confirmed';

    showDialog(
      context: context,
      builder: (dlgCtx) => StatefulBuilder(
        builder: (_, setDlgState) => AlertDialog(
          title: Text('স্ট্যাটাস: #${order['order_number']}', style: const TextStyle(fontSize: 15, fontWeight: FontWeight.bold)),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              if (current == 'awaiting_customer_confirmation' && !customerConfirmed)
                Container(
                  margin: const EdgeInsets.only(bottom: 10),
                  padding: const EdgeInsets.all(8),
                  decoration: BoxDecoration(color: Colors.amber.shade50, borderRadius: BorderRadius.circular(8)),
                  child: const Text('⏳ কাস্টমার এখনো কনফার্ম করেননি (শুধু বাতিল করা যাবে)।', style: TextStyle(fontSize: 11.5)),
                ),
              DropdownButtonFormField<String>(
                initialValue: targetStatus,
                decoration: const InputDecoration(labelText: 'নতুন স্ট্যাটাস', isDense: true),
                items: allowedStatuses.map((s) => DropdownMenuItem(value: s, child: Text(s.toUpperCase()))).toList(),
                onChanged: (v) {
                  if (v != null) setDlgState(() => targetStatus = v);
                },
              ),
              const SizedBox(height: 12),
              DropdownButtonFormField<int?>(
                initialValue: _riders.any((r) => ((r['id'] ?? 0) as num).toInt() == selectedRiderId)
                    ? selectedRiderId
                    : null,
                decoration: const InputDecoration(labelText: 'রাইডার অ্যাসাইন (ঐচ্ছিক)', isDense: true),
                items: [
                  const DropdownMenuItem<int?>(value: null, child: Text('রাইডার পরিবর্তন নয়')),
                  ..._riders.map((r) => DropdownMenuItem<int?>(
                        value: ((r['id'] ?? 0) as num).toInt(),
                        child: Text('${r['full_name']} (${r['username']})'),
                      )),
                ],
                onChanged: (v) => setDlgState(() => selectedRiderId = v),
              ),
            ],
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(dlgCtx), child: const Text('বাতিল')),
            ElevatedButton(
              onPressed: () async {
                final res = await ApiService.updateAdminPharmacyOrderStatus(
                  orderId: ((order['id'] ?? 0) as num).toInt(),
                  status: targetStatus,
                  riderId: selectedRiderId,
                );
                if (!dlgCtx.mounted) return;
                Navigator.pop(dlgCtx);
                if (!mounted) return;
                ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(
                    content: Text(res['message']?.toString() ?? 'আপডেট হয়েছে'),
                    backgroundColor: res['success'] == true ? Colors.green.shade700 : Colors.red,
                  ),
                );
                _loadRxOrders();
              },
              style: ElevatedButton.styleFrom(backgroundColor: Colors.teal.shade700, foregroundColor: Colors.white),
              child: const Text('আপডেট'),
            ),
          ],
        ),
      ),
    );
  }

  void _openAddOrEditMedicineDialog([Map<String, dynamic>? med]) {
    final bool isNew = med == null;
    final data = med ?? <String, dynamic>{};

    final nameCtrl = TextEditingController(text: (data['name'] ?? '').toString());
    final genericCtrl = TextEditingController(text: (data['generic_name'] ?? '').toString());
    final strengthCtrl = TextEditingController(text: (data['strength'] ?? '').toString());
    final dosageCtrl = TextEditingController(text: (data['dosage_form'] ?? 'Tablet').toString());
    final manufCtrl = TextEditingController(text: (data['manufacturer'] ?? '').toString());
    final stockCtrl = TextEditingController(text: '${((data['stock_qty'] ?? 0) as num).toInt()}');
    final mrpCtrl = TextEditingController(text: '${data['mrp'] ?? data['unit_price'] ?? 0}');
    final pieceSellCtrl = TextEditingController(text: '${data['unit_price'] ?? data['mrp'] ?? 0}');
    final pieceCostCtrl = TextEditingController(text: '${data['cost_price'] ?? 0}');

    final stripSizeCtrl = TextEditingController(text: '${((data['strip_size'] ?? 10) as num).toInt()}');
    final stripSellCtrl = TextEditingController(text: '${data['strip_price'] ?? 0}');
    final stripCostCtrl = TextEditingController(text: '${data['strip_cost_price'] ?? 0}');

    final packetSizeCtrl = TextEditingController(text: '${((data['packet_size'] ?? 30) as num).toInt()}');
    final packetSellCtrl = TextEditingController(text: '${data['packet_price'] ?? 0}');
    final packetCostCtrl = TextEditingController(text: '${data['packet_cost_price'] ?? 0}');

    bool saving = false;
    bool saved = false;

    void autoCalcFromPiece() {
      final double ps = double.tryParse(pieceSellCtrl.text) ?? 0;
      final double pc = double.tryParse(pieceCostCtrl.text) ?? 0;
      final int sSize = (int.tryParse(stripSizeCtrl.text) ?? 10).clamp(1, 500);
      final int pSize = (int.tryParse(packetSizeCtrl.text) ?? 30).clamp(1, 5000);
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
          title: Text(isNew ? '➕ নতুন ঔষধ যোগ করুন' : '💊 ${data['name'] ?? 'ঔষধ এডিট'}', style: const TextStyle(fontSize: 15, fontWeight: FontWeight.bold)),
          content: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                TextField(controller: nameCtrl, decoration: const InputDecoration(labelText: 'ঔষধের নাম *', isDense: true)),
                const SizedBox(height: 6),
                Row(
                  children: [
                    Expanded(child: TextField(controller: genericCtrl, decoration: const InputDecoration(labelText: 'জেনেরিক', isDense: true))),
                    const SizedBox(width: 6),
                    Expanded(child: TextField(controller: strengthCtrl, decoration: const InputDecoration(labelText: 'পাওয়ার (500mg)', isDense: true))),
                  ],
                ),
                const SizedBox(height: 6),
                Row(
                  children: [
                    Expanded(child: TextField(controller: dosageCtrl, decoration: const InputDecoration(labelText: 'ধরন (Tablet/Syrup)', isDense: true))),
                    const SizedBox(width: 6),
                    Expanded(child: TextField(controller: manufCtrl, decoration: const InputDecoration(labelText: 'কোম্পানি', isDense: true))),
                  ],
                ),
                const SizedBox(height: 6),
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
                        decoration: const InputDecoration(labelText: 'MRP (৳)', isDense: true),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                Container(
                  padding: const EdgeInsets.all(8),
                  decoration: BoxDecoration(color: Colors.blue.shade50, borderRadius: BorderRadius.circular(8)),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text('১ পিস মূল্য (৳)', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 12)),
                      Row(
                        children: [
                          Expanded(child: TextField(controller: pieceCostCtrl, keyboardType: const TextInputType.numberWithOptions(decimal: true), decoration: const InputDecoration(labelText: 'ক্রয়', isDense: true))),
                          const SizedBox(width: 6),
                          Expanded(child: TextField(controller: pieceSellCtrl, keyboardType: const TextInputType.numberWithOptions(decimal: true), decoration: const InputDecoration(labelText: 'বিক্রয়', isDense: true))),
                        ],
                      ),
                    ],
                  ),
                ),
                Align(
                  alignment: Alignment.centerRight,
                  child: TextButton.icon(
                    onPressed: () {
                      autoCalcFromPiece();
                      setDlgState(() {});
                    },
                    icon: const Icon(Icons.calculate, size: 15),
                    label: const Text('পিস থেকে পাতা/প্যাকেট হিসাব', style: TextStyle(fontSize: 11)),
                  ),
                ),
                Container(
                  padding: const EdgeInsets.all(8),
                  decoration: BoxDecoration(color: Colors.teal.shade50, borderRadius: BorderRadius.circular(8)),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text('১ পাতা (Strip) মূল্য', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 12)),
                      Row(
                        children: [
                          SizedBox(width: 58, child: TextField(controller: stripSizeCtrl, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: 'পিস', isDense: true))),
                          const SizedBox(width: 6),
                          Expanded(child: TextField(controller: stripCostCtrl, keyboardType: const TextInputType.numberWithOptions(decimal: true), decoration: const InputDecoration(labelText: 'ক্রয়', isDense: true))),
                          const SizedBox(width: 6),
                          Expanded(child: TextField(controller: stripSellCtrl, keyboardType: const TextInputType.numberWithOptions(decimal: true), decoration: const InputDecoration(labelText: 'বিক্রয়', isDense: true))),
                        ],
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 6),
                Container(
                  padding: const EdgeInsets.all(8),
                  decoration: BoxDecoration(color: Colors.purple.shade50, borderRadius: BorderRadius.circular(8)),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      const Text('১ প্যাকেট মূল্য', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 12)),
                      Row(
                        children: [
                          SizedBox(width: 58, child: TextField(controller: packetSizeCtrl, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: 'পিস', isDense: true))),
                          const SizedBox(width: 6),
                          Expanded(child: TextField(controller: packetCostCtrl, keyboardType: const TextInputType.numberWithOptions(decimal: true), decoration: const InputDecoration(labelText: 'ক্রয়', isDense: true))),
                          const SizedBox(width: 6),
                          Expanded(child: TextField(controller: packetSellCtrl, keyboardType: const TextInputType.numberWithOptions(decimal: true), decoration: const InputDecoration(labelText: 'বিক্রয়', isDense: true))),
                        ],
                      ),
                    ],
                  ),
                ),
              ],
            ),
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(dlgCtx), child: const Text('বাতিল')),
            ElevatedButton(
              onPressed: (saving || saved)
                  ? null
                  : () async {
                      if (nameCtrl.text.trim().isEmpty) return;
                      setDlgState(() => saving = true);
                      final payload = {
                        if (!isNew && data['id'] != null) 'id': data['id'],
                        'name': nameCtrl.text.trim(),
                        'sku': data['sku'] ?? '',
                        'dosage_form': dosageCtrl.text.trim().isEmpty ? 'Tablet' : dosageCtrl.text.trim(),
                        'strength': strengthCtrl.text.trim(),
                        'generic_name': genericCtrl.text.trim(),
                        'manufacturer': manufCtrl.text.trim(),
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
                      if (res['success'] == true) {
                        setDlgState(() {
                          saving = false;
                          saved = true;
                        });
                        await Future.delayed(const Duration(milliseconds: 450));
                        if (!dlgCtx.mounted) return;
                        Navigator.pop(dlgCtx);
                        if (!mounted) return;
                        _loadMedicines(_medSearchCtrl.text);
                        showDialog(
                          context: context,
                          builder: (okCtx) => AlertDialog(
                            title: const Row(
                              children: [
                                Icon(Icons.check_circle, color: Colors.green),
                                SizedBox(width: 8),
                                Text('Saved ✓'),
                              ],
                            ),
                            content: Text('"${nameCtrl.text.trim()}" এর তথ্য ও স্টক সফলভাবে সংরক্ষিত হয়েছে।'),
                            actions: [
                              ElevatedButton(
                                onPressed: () => Navigator.pop(okCtx),
                                style: ElevatedButton.styleFrom(backgroundColor: Colors.teal.shade700, foregroundColor: Colors.white),
                                child: const Text('ঠিক আছে'),
                              ),
                            ],
                          ),
                        );
                      } else {
                        setDlgState(() => saving = false);
                        ScaffoldMessenger.of(context).showSnackBar(
                          SnackBar(
                            content: Text(res['message']?.toString() ?? 'ব্যর্থ হয়েছে'),
                            backgroundColor: Colors.red,
                          ),
                        );
                      }
                    },
              style: ElevatedButton.styleFrom(
                backgroundColor: saved ? Colors.green.shade700 : Colors.teal.shade700,
                foregroundColor: Colors.white,
              ),
              child: Text(saved ? '✅ Saved' : (saving ? 'Saving...' : 'সংরক্ষণ')),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _confirmDeleteMedicine(Map<String, dynamic> med) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('ঔষধ ডিলিট'),
        content: Text('"${med['name']}" ক্যাটালগ থেকে মুছে ফেলতে চান?'),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('না')),
          ElevatedButton(
            onPressed: () => Navigator.pop(ctx, true),
            style: ElevatedButton.styleFrom(backgroundColor: Colors.red),
            child: const Text('ডিলিট', style: TextStyle(color: Colors.white)),
          ),
        ],
      ),
    );
    if (ok != true) return;
    final res = await AdminApiService.deletePharmacyMedicine(((med['id'] ?? 0) as num).toInt());
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(res['message']?.toString() ?? 'সম্পন্ন'),
        backgroundColor: res['success'] == true ? Colors.green.shade700 : Colors.red,
      ),
    );
    if (res['success'] == true) _loadMedicines(_medSearchCtrl.text);
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        backgroundColor: Colors.teal.shade900,
        foregroundColor: Colors.white,
        title: const Text('💊 ফার্মেসী অ্যাডমিন প্যানেল', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
        bottom: TabBar(
          controller: _tabCtrl,
          indicatorColor: Colors.amberAccent,
          labelColor: Colors.white,
          unselectedLabelColor: Colors.white70,
          tabs: const [
            Tab(text: 'Rx অর্ডার'),
            Tab(text: 'ঔষধ ও স্টক'),
            Tab(text: 'ফার্মেসী সেটিংস'),
          ],
        ),
      ),
      body: TabBarView(
        controller: _tabCtrl,
        children: [
          // Tab 1: Rx Orders
          RefreshIndicator(
            onRefresh: _loadRxOrders,
            child: ListView(
              padding: const EdgeInsets.all(12),
              children: [
                SingleChildScrollView(
                  scrollDirection: Axis.horizontal,
                  child: Row(
                    children: [
                      for (final pair in [
                        {'k': '', 'label': 'সব Rx'},
                        {'k': 'pending', 'label': 'নতুন'},
                        {'k': 'awaiting_customer_confirmation', 'label': 'কনফার্ম বাকি'},
                        {'k': 'confirmed', 'label': 'Confirmed'},
                        {'k': 'packed', 'label': 'Packed'},
                        {'k': 'delivered', 'label': 'Delivered'},
                      ])
                        Padding(
                          padding: const EdgeInsets.only(right: 6),
                          child: ChoiceChip(
                            label: Text(pair['label']!, style: const TextStyle(fontSize: 11.5)),
                            selected: _rxFilter == pair['k'],
                            onSelected: (_) {
                              setState(() => _rxFilter = pair['k']!);
                              _loadRxOrders();
                            },
                          ),
                        ),
                    ],
                  ),
                ),
                const SizedBox(height: 8),
                if (_loadingOrders)
                  const Center(child: Padding(padding: EdgeInsets.all(24), child: CircularProgressIndicator()))
                else if (_rxOrders.isEmpty)
                  const Padding(padding: EdgeInsets.all(32), child: Center(child: Text('কোনো Rx অর্ডার পাওয়া যায়নি।', style: TextStyle(color: Colors.grey))))
                else
                  ..._rxOrders.map((o) {
                    final int oid = ((o['id'] ?? 0) as num).toInt();
                    final String st = (o['order_status'] ?? 'pending').toString();
                    final bool awaiting = st == 'awaiting_customer_confirmation';
                    final double total = ((o['total_amount'] ?? 0) as num).toDouble();
                    final String rxUrl = (o['prescription_url'] ?? '').toString();
                    return Card(
                      margin: const EdgeInsets.only(bottom: 10),
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(12),
                        side: BorderSide(color: awaiting ? Colors.amber.shade700 : Colors.teal.shade200, width: awaiting ? 1.8 : 1),
                      ),
                      child: Padding(
                        padding: const EdgeInsets.all(12),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              children: [
                                Expanded(child: Text('💊 #${o['order_number']}', style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 14))),
                                Container(
                                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                                  decoration: BoxDecoration(
                                    color: awaiting ? Colors.amber.shade800 : Colors.teal.shade700,
                                    borderRadius: BorderRadius.circular(8),
                                  ),
                                  child: Text(awaiting ? 'কনফার্ম বাকি' : st.toUpperCase(), style: const TextStyle(color: Colors.white, fontSize: 10, fontWeight: FontWeight.bold)),
                                ),
                              ],
                            ),
                            const SizedBox(height: 4),
                            Text('👤 ${o['customer_name'] ?? ''} • 📞 ${o['customer_phone'] ?? ''}', style: const TextStyle(fontSize: 12.5)),
                            Text('📍 ${o['delivery_address'] ?? ''}', style: const TextStyle(fontSize: 11.5, color: Colors.black54)),
                            if ((o['customer_notes'] ?? '').toString().isNotEmpty)
                              Text('📝 নোট: ${o['customer_notes']}', style: TextStyle(fontSize: 11.5, color: Colors.amber.shade900)),
                            if (total > 0)
                              Padding(
                                padding: const EdgeInsets.only(top: 4),
                                child: Text('মোট বিল: ৳${total.toStringAsFixed(2)}', style: TextStyle(fontWeight: FontWeight.bold, color: Colors.teal.shade800)),
                              ),
                            if (rxUrl.isNotEmpty)
                              Padding(
                                padding: const EdgeInsets.only(top: 6),
                                child: InkWell(
                                  onTap: () => _openPrescriptionZoom(rxUrl),
                                  child: Text('📋 প্রেসক্রিপশন ছবি দেখুন ➔', style: TextStyle(color: Colors.teal.shade700, fontWeight: FontWeight.bold, fontSize: 12)),
                                ),
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
                                    if (updated == true) _loadRxOrders();
                                  },
                                  icon: const Icon(Icons.edit_note, size: 15),
                                  label: const Text('Rx ও বিল তৈরি', style: TextStyle(fontSize: 11.5)),
                                  style: ElevatedButton.styleFrom(backgroundColor: Colors.teal.shade700, foregroundColor: Colors.white),
                                ),
                                OutlinedButton.icon(
                                  onPressed: () => _openStatusDialog(o),
                                  icon: const Icon(Icons.sync_alt, size: 14),
                                  label: const Text('স্ট্যাটাস / রাইডার', style: TextStyle(fontSize: 11.5)),
                                ),
                                OutlinedButton.icon(
                                  onPressed: () => ThermalPrintHelper.printAndConfirm(
                                    context,
                                    riderPhone: _staffPhone,
                                    sourceType: 'pharmacy_order',
                                    sourceId: oid,
                                    invoiceNumber: (o['order_number'] ?? '').toString(),
                                  ),
                                  icon: const Icon(Icons.print, size: 14),
                                  label: const Text('PC প্রিন্ট', style: TextStyle(fontSize: 11.5)),
                                ),
                              ],
                            ),
                          ],
                        ),
                      ),
                    );
                  }),
              ],
            ),
          ),

          // Tab 2: Medicine Catalog
          Column(
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(12, 12, 12, 6),
                child: Row(
                  children: [
                    Expanded(
                      child: TextField(
                        controller: _medSearchCtrl,
                        onChanged: (v) {
                          _medDebounce?.cancel();
                          _medDebounce = Timer(const Duration(milliseconds: 300), () => _loadMedicines(v.trim()));
                        },
                        decoration: InputDecoration(
                          hintText: 'ঔষধ বা জেনেরিক খুঁজুন...',
                          prefixIcon: const Icon(Icons.search, size: 18),
                          isDense: true,
                          border: OutlineInputBorder(borderRadius: BorderRadius.circular(10)),
                        ),
                      ),
                    ),
                    const SizedBox(width: 8),
                    ElevatedButton.icon(
                      onPressed: () => _openAddOrEditMedicineDialog(),
                      icon: const Icon(Icons.add, size: 17),
                      label: const Text('নতুন ঔষধ', style: TextStyle(fontSize: 12)),
                      style: ElevatedButton.styleFrom(backgroundColor: Colors.teal.shade700, foregroundColor: Colors.white),
                    ),
                  ],
                ),
              ),
              Expanded(
                child: _loadingMeds
                    ? const Center(child: CircularProgressIndicator())
                    : RefreshIndicator(
                        onRefresh: () => _loadMedicines(_medSearchCtrl.text),
                        child: ListView.builder(
                          padding: const EdgeInsets.all(12),
                          itemCount: _medicines.length,
                          itemBuilder: (_, idx) {
                            final m = _medicines[idx];
                            final int st = ((m['stock_qty'] ?? 0) as num).toInt();
                            return Card(
                              margin: const EdgeInsets.only(bottom: 7),
                              child: ListTile(
                                dense: true,
                                title: Text('${m['name']} (${m['strength'] ?? ''})', style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 12.5)),
                                subtitle: Column(
                                  crossAxisAlignment: CrossAxisAlignment.start,
                                  children: [
                                    Text(
                                      'পিস: ক্রয় ৳${m['cost_price'] ?? 0} / বিক্রয় ৳${m['unit_price'] ?? 0} | '
                                      'পাতা(${m['strip_size'] ?? 10}): ৳${m['strip_price'] ?? 0} | '
                                      'প্যাকেট(${m['packet_size'] ?? 30}): ৳${m['packet_price'] ?? 0}',
                                      style: const TextStyle(fontSize: 11),
                                    ),
                                    Text(
                                      st <= 0 ? '❌ স্টক: 0 (অর্ডার/কোটেশন বন্ধ)' : '✅ স্টক: $st পিস',
                                      style: TextStyle(
                                        fontSize: 11,
                                        fontWeight: FontWeight.bold,
                                        color: st <= 0 ? Colors.red.shade700 : Colors.green.shade800,
                                      ),
                                    ),
                                  ],
                                ),
                                trailing: Row(
                                  mainAxisSize: MainAxisSize.min,
                                  children: [
                                    IconButton(
                                      icon: const Icon(Icons.edit, color: Colors.teal, size: 20),
                                      onPressed: () => _openAddOrEditMedicineDialog(m),
                                    ),
                                    IconButton(
                                      icon: const Icon(Icons.delete_outline, color: Colors.red, size: 20),
                                      onPressed: () => _confirmDeleteMedicine(m),
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

          // Tab 3: Pharmacy Settings
          _loadingSettings
              ? const Center(child: CircularProgressIndicator())
              : ListView(
                  padding: const EdgeInsets.all(16),
                  children: [
                    Card(
                      child: Padding(
                        padding: const EdgeInsets.all(14),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            const Text('⚙️ ফার্মেসী ডেলিভারি ও ডিসকাউন্ট সেটিংস', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 14)),
                            const SizedBox(height: 12),
                            TextField(
                              controller: _deliveryCtrl,
                              keyboardType: const TextInputType.numberWithOptions(decimal: true),
                              decoration: const InputDecoration(
                                labelText: 'ডিফল্ট ফার্মেসী ডেলিভারি চার্জ (৳)',
                                border: OutlineInputBorder(),
                              ),
                            ),
                            const SizedBox(height: 12),
                            TextField(
                              controller: _discountCtrl,
                              keyboardType: const TextInputType.numberWithOptions(decimal: true),
                              decoration: const InputDecoration(
                                labelText: 'সর্বমোট ডিসকাউন্ট (%)',
                                border: OutlineInputBorder(),
                              ),
                            ),
                            const SizedBox(height: 14),
                            SizedBox(
                              width: double.infinity,
                              child: ElevatedButton.icon(
                                onPressed: _savingSettings ? null : _saveSettings,
                                icon: const Icon(Icons.save),
                                label: Text(_savingSettings ? 'সেভ হচ্ছে...' : 'ফার্মেসী সেটিংস সেভ করুন'),
                                style: ElevatedButton.styleFrom(
                                  backgroundColor: Colors.teal.shade700,
                                  foregroundColor: Colors.white,
                                  padding: const EdgeInsets.symmetric(vertical: 12),
                                ),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  ],
                ),
        ],
      ),
    );
  }
}
