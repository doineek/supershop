import 'package:flutter/material.dart';
import '../../services/admin_api_service.dart';
import '../../services/api_service.dart';

class AdminRidersScreen extends StatefulWidget {
  const AdminRidersScreen({super.key});

  @override
  State<AdminRidersScreen> createState() => _AdminRidersScreenState();
}

class _AdminRidersScreenState extends State<AdminRidersScreen> {
  bool _loading = true;
  List<Map<String, dynamic>> _riders = [];
  Map<String, dynamic> _summary = {};

  @override
  void initState() {
    super.initState();
    _loadRiders();
  }

  Future<void> _loadRiders() async {
    if (mounted) setState(() => _loading = true);
    final res = await ApiService.fetchAdminRiders();
    if (!mounted) return;
    setState(() {
      _riders = (res['riders'] as List? ?? [])
          .whereType<Map>()
          .map((e) => Map<String, dynamic>.from(e))
          .toList();
      _summary = res['summary'] is Map ? Map<String, dynamic>.from(res['summary'] as Map) : {};
      _loading = false;
    });
  }

  void _showSnack(String msg, {bool isError = false}) {
    if (!mounted) return;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(content: Text(msg), backgroundColor: isError ? Colors.red.shade700 : Colors.green.shade700),
    );
  }

  Future<void> _openRiderForm([Map<String, dynamic>? existing]) async {
    final bool isNew = existing == null;
    final nameCtrl = TextEditingController(text: (existing?['full_name'] ?? '').toString());
    final phoneCtrl = TextEditingController(text: (existing?['username'] ?? '').toString());
    final passCtrl = TextEditingController();
    bool isActive = existing?['is_active'] != 0 && existing?['is_active'] != false;
    bool canRx = existing?['can_rx_quote_bill'] == true || existing?['can_rx_quote_bill'] == 1;

    await showDialog(
      context: context,
      builder: (dlgCtx) => StatefulBuilder(
        builder: (_, setDlgState) => AlertDialog(
          title: Text(isNew ? '➕ নতুন ডেলিভারি রাইডার' : '✏️ রাইডার এডিট', style: const TextStyle(fontSize: 15, fontWeight: FontWeight.bold)),
          content: SingleChildScrollView(
            child: Column(
              mainAxisSize: MainAxisSize.min,
              children: [
                TextField(controller: nameCtrl, decoration: const InputDecoration(labelText: 'পুরো নাম *', isDense: true)),
                const SizedBox(height: 8),
                TextField(controller: phoneCtrl, keyboardType: TextInputType.phone, decoration: const InputDecoration(labelText: 'মোবাইল নম্বর (01...) *', isDense: true)),
                const SizedBox(height: 8),
                TextField(
                  controller: passCtrl,
                  decoration: InputDecoration(
                    labelText: isNew ? 'পাসওয়ার্ড (কমপক্ষে ৩ অক্ষর) *' : 'নতুন পাসওয়ার্ড (পরিবর্তন না করলে খালি)',
                    isDense: true,
                  ),
                ),
                SwitchListTile(
                  dense: true,
                  contentPadding: EdgeInsets.zero,
                  title: const Text('অ্যাক্টিভ অ্যাকাউন্ট'),
                  value: isActive,
                  onChanged: (v) => setDlgState(() => isActive = v),
                ),
                SwitchListTile(
                  dense: true,
                  contentPadding: EdgeInsets.zero,
                  title: const Text('Rx স্ক্যান ও কোটেশন অনুমতি'),
                  value: canRx,
                  onChanged: (v) => setDlgState(() => canRx = v),
                ),
              ],
            ),
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(dlgCtx), child: const Text('বাতিল')),
            ElevatedButton(
              onPressed: () async {
                final res = await AdminApiService.saveRider(
                  riderId: existing != null ? ((existing['id'] ?? 0) as num).toInt() : null,
                  fullName: nameCtrl.text.trim(),
                  username: phoneCtrl.text.trim(),
                  password: passCtrl.text.trim(),
                  isActive: isActive,
                  canRxQuoteBill: canRx,
                );
                if (!dlgCtx.mounted) return;
                Navigator.pop(dlgCtx);
                _showSnack(res['message']?.toString() ?? 'সম্পন্ন', isError: res['success'] != true);
                if (res['success'] == true) _loadRiders();
              },
              style: ElevatedButton.styleFrom(backgroundColor: Colors.teal.shade700, foregroundColor: Colors.white),
              child: const Text('সংরক্ষণ'),
            ),
          ],
        ),
      ),
    );
    nameCtrl.dispose();
    phoneCtrl.dispose();
    passCtrl.dispose();
  }

  Future<void> _openPayRiderDialog(Map<String, dynamic> rider) async {
    final double due = ((rider['balance_due'] ?? 0) as num).toDouble();
    final amtCtrl = TextEditingController(text: due > 0 ? due.toStringAsFixed(0) : '');
    final noteCtrl = TextEditingController();
    String method = 'Cash';

    await showDialog(
      context: context,
      builder: (dlgCtx) => StatefulBuilder(
        builder: (_, setDlgState) => AlertDialog(
          title: Text('💰 ${rider['full_name']} - কে পেমেন্ট', style: const TextStyle(fontSize: 15, fontWeight: FontWeight.bold)),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              Text('বকেয়া পাওনা: ৳${due.toStringAsFixed(2)}', style: TextStyle(fontWeight: FontWeight.bold, color: Colors.orange.shade900)),
              const SizedBox(height: 10),
              TextField(controller: amtCtrl, keyboardType: const TextInputType.numberWithOptions(decimal: true), decoration: const InputDecoration(labelText: 'পেমেন্ট পরিমাণ (৳)', isDense: true)),
              const SizedBox(height: 8),
              DropdownButtonFormField<String>(
                initialValue: method,
                decoration: const InputDecoration(labelText: 'পেমেন্ট মাধ্যম', isDense: true),
                items: const [
                  DropdownMenuItem(value: 'Cash', child: Text('Cash')),
                  DropdownMenuItem(value: 'bKash', child: Text('bKash')),
                  DropdownMenuItem(value: 'Nagad', child: Text('Nagad')),
                  DropdownMenuItem(value: 'Bank', child: Text('Bank')),
                ],
                onChanged: (v) {
                  if (v != null) setDlgState(() => method = v);
                },
              ),
              const SizedBox(height: 8),
              TextField(controller: noteCtrl, decoration: const InputDecoration(labelText: 'নোট (ঐচ্ছিক)', isDense: true)),
            ],
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(dlgCtx), child: const Text('বাতিল')),
            ElevatedButton(
              onPressed: () async {
                final double amt = double.tryParse(amtCtrl.text.trim()) ?? 0;
                if (amt <= 0) return;
                final res = await AdminApiService.payRider(
                  riderId: ((rider['id'] ?? 0) as num).toInt(),
                  amount: amt,
                  paymentMethod: method,
                  note: noteCtrl.text.trim(),
                );
                if (!dlgCtx.mounted) return;
                Navigator.pop(dlgCtx);
                _showSnack(res['message']?.toString() ?? '', isError: res['success'] != true);
                if (res['success'] == true) _loadRiders();
              },
              style: ElevatedButton.styleFrom(backgroundColor: Colors.green.shade700, foregroundColor: Colors.white),
              child: const Text('পেমেন্ট কনফার্ম'),
            ),
          ],
        ),
      ),
    );
    amtCtrl.dispose();
    noteCtrl.dispose();
  }

  void _openPayoutHistory(Map<String, dynamic> rider) {
    final payouts = (rider['payouts'] as List? ?? []).whereType<Map>().map((e) => Map<String, dynamic>.from(e)).toList();
    showDialog(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('📜 পেমেন্ট হিস্ট্রি • ${rider['full_name']}', style: const TextStyle(fontSize: 15, fontWeight: FontWeight.bold)),
        content: SizedBox(
          width: 340,
          child: payouts.isEmpty
              ? const Text('কোনো পেমেন্ট রেকর্ড নেই')
              : ListView.separated(
                  shrinkWrap: true,
                  itemCount: payouts.length,
                  separatorBuilder: (_, __) => const Divider(height: 1),
                  itemBuilder: (_, idx) {
                    final p = payouts[idx];
                    return ListTile(
                      dense: true,
                      title: Text('৳${((p['amount'] ?? 0) as num).toStringAsFixed(0)} (${p['payment_method'] ?? 'Cash'})', style: const TextStyle(fontWeight: FontWeight.bold)),
                      subtitle: Text('${p['payout_date'] ?? ''} ${p['note'] ?? ''}'),
                      trailing: IconButton(
                        icon: const Icon(Icons.delete_outline, color: Colors.red, size: 18),
                        onPressed: () async {
                          final res = await AdminApiService.deleteRiderPayout(((p['id'] ?? 0) as num).toInt());
                          if (ctx.mounted) Navigator.pop(ctx);
                          _showSnack(res['message']?.toString() ?? '', isError: res['success'] != true);
                          if (res['success'] == true) _loadRiders();
                        },
                      ),
                    );
                  },
                ),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('বন্ধ')),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        backgroundColor: Colors.teal.shade900,
        foregroundColor: Colors.white,
        title: const Text('🛵 রাইডার্স ও পেআউট', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
        actions: [
          IconButton(icon: const Icon(Icons.person_add), onPressed: () => _openRiderForm()),
          IconButton(icon: const Icon(Icons.refresh), onPressed: _loadRiders),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : RefreshIndicator(
              onRefresh: _loadRiders,
              child: ListView(
                padding: const EdgeInsets.all(12),
                children: [
                  if (_summary.isNotEmpty)
                    Container(
                      margin: const EdgeInsets.only(bottom: 12),
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: Colors.teal.shade50,
                        borderRadius: BorderRadius.circular(12),
                        border: Border.all(color: Colors.teal.shade200),
                      ),
                      child: Row(
                        mainAxisAlignment: MainAxisAlignment.spaceAround,
                        children: [
                          _sumCol('রাইডার', '${_riders.length} জন', Colors.teal.shade900),
                          _sumCol('মোট আয়', '৳${((_summary['total_earned'] ?? 0) as num).toStringAsFixed(0)}', Colors.indigo.shade800),
                          _sumCol('পরিশোধিত', '৳${((_summary['total_paid'] ?? 0) as num).toStringAsFixed(0)}', Colors.green.shade800),
                          _sumCol('মোট বকেয়া', '৳${((_summary['total_due'] ?? 0) as num).toStringAsFixed(0)}', Colors.orange.shade900),
                        ],
                      ),
                    ),
                  ..._riders.map((r) {
                    final double earned = ((r['total_earned'] ?? 0) as num).toDouble();
                    final double paid = ((r['total_paid'] ?? 0) as num).toDouble();
                    final double due = ((r['balance_due'] ?? 0) as num).toDouble();
                    final bool allowed = r['can_rx_quote_bill'] == true;
                    return Card(
                      margin: const EdgeInsets.only(bottom: 10),
                      child: Padding(
                        padding: const EdgeInsets.all(12),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              children: [
                                Expanded(
                                  child: Text('${r['full_name']} (${r['username']})', style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 14)),
                                ),
                                IconButton(icon: const Icon(Icons.edit, size: 18, color: Colors.teal), onPressed: () => _openRiderForm(r)),
                                IconButton(
                                  icon: const Icon(Icons.delete_outline, size: 18, color: Colors.red),
                                  onPressed: () async {
                                    final ok = await showDialog<bool>(
                                      context: context,
                                      builder: (ctx) => AlertDialog(
                                        title: const Text('রাইডার ডিলিট'),
                                        content: Text('${r['full_name']}-কে ডিলিট করতে চান?'),
                                        actions: [
                                          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('না')),
                                          ElevatedButton(onPressed: () => Navigator.pop(ctx, true), style: ElevatedButton.styleFrom(backgroundColor: Colors.red), child: const Text('ডিলিট', style: TextStyle(color: Colors.white))),
                                        ],
                                      ),
                                    );
                                    if (ok == true) {
                                      final res = await AdminApiService.deleteRider(((r['id'] ?? 0) as num).toInt());
                                      _showSnack(res['message']?.toString() ?? '', isError: res['success'] != true);
                                      if (res['success'] == true) _loadRiders();
                                    }
                                  },
                                ),
                              ],
                            ),
                            Text(
                              'ডেলিভারি: ${r['total_delivered'] ?? 0}/${r['total_orders'] ?? 0} • আয়: ৳${earned.toStringAsFixed(0)} • পরিশোধ: ৳${paid.toStringAsFixed(0)} • বকেয়া: ৳${due.toStringAsFixed(0)}',
                              style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
                            ),
                            SwitchListTile(
                              dense: true,
                              contentPadding: EdgeInsets.zero,
                              title: const Text('Rx স্ক্যান ও কোটেশন বিল অনুমতি', style: TextStyle(fontSize: 12)),
                              value: allowed,
                              onChanged: (val) async {
                                final res = await ApiService.toggleAdminRiderPermission(riderId: ((r['id'] ?? 0) as num).toInt(), allow: val);
                                _showSnack(res['message']?.toString() ?? '', isError: res['success'] != true);
                                _loadRiders();
                              },
                            ),
                            Wrap(
                              spacing: 8,
                              children: [
                                ElevatedButton.icon(
                                  onPressed: due > 0 ? () => _openPayRiderDialog(r) : null,
                                  icon: const Icon(Icons.payments, size: 15),
                                  label: const Text('পেমেন্ট দিন', style: TextStyle(fontSize: 11.5)),
                                  style: ElevatedButton.styleFrom(backgroundColor: Colors.green.shade700, foregroundColor: Colors.white),
                                ),
                                OutlinedButton.icon(
                                  onPressed: () => _openPayoutHistory(r),
                                  icon: const Icon(Icons.history, size: 15),
                                  label: const Text('পেমেন্ট হিস্ট্রি', style: TextStyle(fontSize: 11.5)),
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
    );
  }

  Widget _sumCol(String lbl, String val, Color c) {
    return Column(
      children: [
        Text(lbl, style: const TextStyle(fontSize: 11, color: Colors.black54)),
        Text(val, style: TextStyle(fontSize: 14, fontWeight: FontWeight.w900, color: c)),
      ],
    );
  }
}
