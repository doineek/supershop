import 'package:flutter/material.dart';
import '../../services/admin_api_service.dart';

class AdminReportsScreen extends StatefulWidget {
  final String initialDept;

  const AdminReportsScreen({super.key, this.initialDept = 'all'});

  @override
  State<AdminReportsScreen> createState() => _AdminReportsScreenState();
}

class _AdminReportsScreenState extends State<AdminReportsScreen> {
  String _period = 'monthly';
  late String _dept;
  bool _loading = true;
  Map<String, dynamic> _data = {};

  @override
  void initState() {
    super.initState();
    _dept = widget.initialDept;
    _loadReports();
  }

  Future<void> _loadReports() async {
    if (mounted) setState(() => _loading = true);
    final res = await AdminApiService.fetchReports(period: _period, dept: _dept);
    if (!mounted) return;
    setState(() {
      _data = res;
      _loading = false;
    });
  }

  double _num(dynamic v) => ((v ?? 0) as num).toDouble();

  Widget _kpiCard(String title, String value, Color color, IconData icon) {
    return Expanded(
      child: Container(
        padding: const EdgeInsets.all(11),
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.08),
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: color.withValues(alpha: 0.3)),
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                Icon(icon, color: color, size: 17),
                const SizedBox(width: 5),
                Expanded(
                  child: Text(title, style: TextStyle(fontSize: 11, fontWeight: FontWeight.bold, color: color), overflow: TextOverflow.ellipsis),
                ),
              ],
            ),
            const SizedBox(height: 5),
            Text(value, style: TextStyle(fontSize: 15, fontWeight: FontWeight.w900, color: color)),
          ],
        ),
      ),
    );
  }

  Widget _summarySectionCard(String title, Map<String, dynamic> summary, Color accent) {
    if (summary.isEmpty) return const SizedBox.shrink();
    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12), side: BorderSide(color: accent.withValues(alpha: 0.3))),
      child: Padding(
        padding: const EdgeInsets.all(12),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(title, style: TextStyle(fontWeight: FontWeight.bold, fontSize: 13.5, color: accent)),
            const Divider(height: 14),
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text('বিক্রি: ৳${_num(summary['revenue']).toStringAsFixed(0)}', style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 12)),
                Text('খরচ: ৳${_num(summary['cogs']).toStringAsFixed(0)}', style: const TextStyle(fontSize: 12, color: Colors.black54)),
                Text('লাভ: ৳${_num(summary['gross_profit'] ?? summary['profit']).toStringAsFixed(0)}', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 12, color: Colors.green.shade800)),
              ],
            ),
            if (summary['tx_count'] != null)
              Padding(
                padding: const EdgeInsets.only(top: 4),
                child: Text('মোট লেনদেন: ${summary['tx_count']} টি', style: const TextStyle(fontSize: 11, color: Colors.grey)),
              ),
          ],
        ),
      ),
    );
  }

  Future<void> _openAddLedgerDialog() async {
    final titleCtrl = TextEditingController();
    final amountCtrl = TextEditingController();
    String entryType = 'expense';
    String targetSeg = 'all';

    await showDialog(
      context: context,
      builder: (dlgCtx) => StatefulBuilder(
        builder: (_, setDlgState) => AlertDialog(
          title: const Text('➕ আয় / খরচ লেজার এন্ট্রি', style: TextStyle(fontSize: 15, fontWeight: FontWeight.bold)),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              DropdownButtonFormField<String>(
                initialValue: entryType,
                decoration: const InputDecoration(labelText: 'ধরন', isDense: true),
                items: const [
                  DropdownMenuItem(value: 'expense', child: Text('খরচ (Expense)')),
                  DropdownMenuItem(value: 'income', child: Text('আয় (Income)')),
                ],
                onChanged: (v) {
                  if (v != null) setDlgState(() => entryType = v);
                },
              ),
              const SizedBox(height: 8),
              DropdownButtonFormField<String>(
                initialValue: targetSeg,
                decoration: const InputDecoration(labelText: 'বিভাগ', isDense: true),
                items: const [
                  DropdownMenuItem(value: 'all', child: Text('পুরো সুপারশপ')),
                  DropdownMenuItem(value: 'general', child: Text('সাধারণ সুপারশপ')),
                  DropdownMenuItem(value: 'pharmacy', child: Text('ফার্মেসী')),
                ],
                onChanged: (v) {
                  if (v != null) setDlgState(() => targetSeg = v);
                },
              ),
              const SizedBox(height: 8),
              TextField(controller: titleCtrl, decoration: const InputDecoration(labelText: 'বিবরণ *', isDense: true)),
              const SizedBox(height: 8),
              TextField(
                controller: amountCtrl,
                keyboardType: const TextInputType.numberWithOptions(decimal: true),
                decoration: const InputDecoration(labelText: 'পরিমাণ (৳) *', isDense: true),
              ),
            ],
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(dlgCtx), child: const Text('বাতিল')),
            ElevatedButton(
              onPressed: () async {
                final double amt = double.tryParse(amountCtrl.text.trim()) ?? 0;
                if (titleCtrl.text.trim().isEmpty || amt <= 0) return;
                final res = await AdminApiService.addLedgerEntry(
                  title: titleCtrl.text.trim(),
                  entryType: entryType,
                  amount: amt,
                  targetSegment: targetSeg,
                );
                if (!dlgCtx.mounted) return;
                Navigator.pop(dlgCtx);
                if (!mounted) return;
                ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(
                    content: Text(res['message']?.toString() ?? 'সম্পন্ন'),
                    backgroundColor: res['success'] == true ? Colors.green.shade700 : Colors.red,
                  ),
                );
                if (res['success'] == true) _loadReports();
              },
              style: ElevatedButton.styleFrom(backgroundColor: Colors.teal.shade700, foregroundColor: Colors.white),
              child: const Text('যোগ করুন'),
            ),
          ],
        ),
      ),
    );
    titleCtrl.dispose();
    amountCtrl.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final periods = [
      {'k': 'daily', 'label': 'আজ'},
      {'k': 'weekly', 'label': '৭ দিন'},
      {'k': 'monthly', 'label': '১ মাস'},
      {'k': '3_monthly', 'label': '৩ মাস'},
      {'k': '6_monthly', 'label': '৬ মাস'},
      {'k': 'yearly', 'label': '১ বছর'},
      {'k': 'all', 'label': 'সর্বমোট'},
    ];
    final depts = [
      {'k': 'all', 'label': '🏪 পুরো সুপারশপ'},
      {'k': 'general', 'label': '🛒 সাধারণ পণ্য'},
      {'k': 'pharmacy', 'label': '💊 ফার্মেসী'},
    ];

    final genSum = _data['general_summary'] is Map ? Map<String, dynamic>.from(_data['general_summary'] as Map) : <String, dynamic>{};
    final pharmSum = _data['pharmacy_summary'] is Map ? Map<String, dynamic>.from(_data['pharmacy_summary'] as Map) : <String, dynamic>{};
    final onlSum = _data['online_summary'] is Map ? Map<String, dynamic>.from(_data['online_summary'] as Map) : <String, dynamic>{};
    final posSum = _data['offline_summary'] is Map ? Map<String, dynamic>.from(_data['offline_summary'] as Map) : <String, dynamic>{};
    final topProds = (_data['top_products'] as List? ?? []).whereType<Map>().toList();
    final topMeds = (_data['top_medicines'] as List? ?? []).whereType<Map>().toList();
    final ledger = (_data['ledger_entries'] as List? ?? []).whereType<Map>().toList();

    return Scaffold(
      appBar: AppBar(
        backgroundColor: Colors.teal.shade900,
        foregroundColor: Colors.white,
        title: const Text('📊 রিপোর্ট ও লাভ-লস হিসাব', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
        actions: [
          IconButton(icon: const Icon(Icons.refresh), onPressed: _loadReports),
        ],
      ),
      body: Column(
        children: [
          Container(
            color: Colors.white,
            padding: const EdgeInsets.fromLTRB(12, 10, 12, 8),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                SingleChildScrollView(
                  scrollDirection: Axis.horizontal,
                  child: Row(
                    children: depts
                        .map((d) => Padding(
                              padding: const EdgeInsets.only(right: 6),
                              child: ChoiceChip(
                                label: Text(d['label']!, style: const TextStyle(fontSize: 11.5, fontWeight: FontWeight.bold)),
                                selected: _dept == d['k'],
                                selectedColor: Colors.teal.shade700,
                                labelStyle: TextStyle(color: _dept == d['k'] ? Colors.white : Colors.black87),
                                onSelected: (_) {
                                  setState(() => _dept = d['k']!);
                                  _loadReports();
                                },
                              ),
                            ))
                        .toList(),
                  ),
                ),
                const SizedBox(height: 6),
                SingleChildScrollView(
                  scrollDirection: Axis.horizontal,
                  child: Row(
                    children: periods
                        .map((p) => Padding(
                              padding: const EdgeInsets.only(right: 6),
                              child: ChoiceChip(
                                label: Text(p['label']!, style: const TextStyle(fontSize: 11)),
                                selected: _period == p['k'],
                                onSelected: (_) {
                                  setState(() => _period = p['k']!);
                                  _loadReports();
                                },
                              ),
                            ))
                        .toList(),
                  ),
                ),
              ],
            ),
          ),
          Expanded(
            child: _loading
                ? const Center(child: CircularProgressIndicator())
                : RefreshIndicator(
                    onRefresh: _loadReports,
                    child: ListView(
                      padding: const EdgeInsets.all(12),
                      children: [
                        Row(
                          children: [
                            _kpiCard('মোট বিক্রি', '৳${_num(_data['revenue']).toStringAsFixed(0)}', Colors.teal.shade800, Icons.point_of_sale),
                            const SizedBox(width: 8),
                            _kpiCard('ক্রয় মূল্য (COGS)', '৳${_num(_data['cogs']).toStringAsFixed(0)}', Colors.indigo.shade800, Icons.inventory),
                          ],
                        ),
                        const SizedBox(height: 8),
                        Row(
                          children: [
                            _kpiCard('মোট লাভ (Gross)', '৳${_num(_data['gross_profit']).toStringAsFixed(0)}', Colors.green.shade800, Icons.trending_up),
                            const SizedBox(width: 8),
                            _kpiCard('নিট লাভ (Net)', '৳${_num(_data['net_profit']).toStringAsFixed(0)}', _num(_data['net_profit']) >= 0 ? Colors.green.shade900 : Colors.red.shade800, Icons.account_balance_wallet),
                          ],
                        ),
                        const SizedBox(height: 8),
                        Row(
                          children: [
                            _kpiCard('অন্যান্য আয়', '৳${_num(_data['other_income']).toStringAsFixed(0)}', Colors.blue.shade800, Icons.add_chart),
                            const SizedBox(width: 8),
                            _kpiCard('অন্যান্য খরচ', '৳${_num(_data['other_expenses']).toStringAsFixed(0)}', Colors.orange.shade900, Icons.money_off),
                          ],
                        ),
                        const SizedBox(height: 14),
                        _summarySectionCard('🛒 সাধারণ সুপারশপ বিভাগ', genSum, const Color(0xFF6B21A8)),
                        _summarySectionCard('💊 ফার্মেসী বিভাগ', pharmSum, const Color(0xFF0F766E)),
                        _summarySectionCard('🌐 অনলাইন অর্ডার বিক্রি', onlSum, Colors.blue.shade800),
                        _summarySectionCard('🏪 POS / কাউন্টার বিক্রি', posSum, Colors.indigo.shade800),
                        if (topProds.isNotEmpty) ...[
                          const SizedBox(height: 6),
                          const Text('🔥 সেরা বিক্রিত সাধারণ পণ্য', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 13.5)),
                          const SizedBox(height: 4),
                          ...topProds.take(6).map((p) => Card(
                                child: ListTile(
                                  dense: true,
                                  title: Text((p['name'] ?? '').toString(), style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 12.5)),
                                  trailing: Text('বিক্রি: ${p['qty'] ?? p['total_qty'] ?? 0} • ৳${_num(p['revenue'] ?? p['total_revenue']).toStringAsFixed(0)}', style: const TextStyle(fontSize: 11.5, fontWeight: FontWeight.bold)),
                                ),
                              )),
                        ],
                        if (topMeds.isNotEmpty) ...[
                          const SizedBox(height: 8),
                          const Text('💊 সেরা বিক্রিত ঔষধ', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 13.5)),
                          const SizedBox(height: 4),
                          ...topMeds.take(6).map((m) => Card(
                                child: ListTile(
                                  dense: true,
                                  title: Text((m['name'] ?? '').toString(), style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 12.5)),
                                  trailing: Text('বিক্রি: ${m['qty'] ?? m['total_qty'] ?? 0} • ৳${_num(m['revenue'] ?? m['total_revenue']).toStringAsFixed(0)}', style: const TextStyle(fontSize: 11.5, fontWeight: FontWeight.bold)),
                                ),
                              )),
                        ],
                        const Divider(height: 22),
                        Row(
                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                          children: [
                            const Text('📒 আয় / খরচ লেজার', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 14)),
                            ElevatedButton.icon(
                              onPressed: _openAddLedgerDialog,
                              icon: const Icon(Icons.add, size: 16),
                              label: const Text('এন্ট্রি যোগ', style: TextStyle(fontSize: 11.5)),
                              style: ElevatedButton.styleFrom(backgroundColor: Colors.teal.shade700, foregroundColor: Colors.white),
                            ),
                          ],
                        ),
                        const SizedBox(height: 6),
                        if (ledger.isEmpty)
                          const Padding(padding: EdgeInsets.all(14), child: Center(child: Text('এই সময়কালে কোনো লেজার এন্ট্রি নেই', style: TextStyle(color: Colors.grey))))
                        else
                          ...ledger.map((l) {
                            final bool isInc = (l['entry_type'] ?? '') == 'income';
                            return Card(
                              margin: const EdgeInsets.only(bottom: 6),
                              child: ListTile(
                                dense: true,
                                leading: Icon(isInc ? Icons.arrow_downward : Icons.arrow_upward, color: isInc ? Colors.green.shade700 : Colors.red.shade700),
                                title: Text((l['title'] ?? '').toString(), style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 12.5)),
                                subtitle: Text('${l['entry_date'] ?? ''} • ${l['target_segment'] ?? 'all'}', style: const TextStyle(fontSize: 11)),
                                trailing: Row(
                                  mainAxisSize: MainAxisSize.min,
                                  children: [
                                    Text(
                                      '${isInc ? '+' : '-'}৳${_num(l['amount']).toStringAsFixed(0)}',
                                      style: TextStyle(fontWeight: FontWeight.bold, color: isInc ? Colors.green.shade800 : Colors.red.shade700),
                                    ),
                                    IconButton(
                                      icon: const Icon(Icons.delete_outline, size: 18, color: Colors.red),
                                      onPressed: () async {
                                        final res = await AdminApiService.deleteLedgerEntry(((l['id'] ?? 0) as num).toInt());
                                        if (res['success'] == true) _loadReports();
                                      },
                                    ),
                                  ],
                                ),
                              ),
                            );
                          }),
                      ],
                    ),
                  ),
          ),
        ],
      ),
    );
  }
}
