import 'package:flutter/material.dart';
import '../../services/admin_api_service.dart';
import '../../widgets/thermal_print_helper.dart';

class AdminSettingsScreen extends StatefulWidget {
  const AdminSettingsScreen({super.key});

  @override
  State<AdminSettingsScreen> createState() => _AdminSettingsScreenState();
}

class _AdminSettingsScreenState extends State<AdminSettingsScreen> {
  bool _loading = true;
  bool _saving = false;

  final _shopNameCtrl = TextEditingController();
  final _shopPhoneCtrl = TextEditingController();
  final _supportPhoneCtrl = TextEditingController();
  final _waPhoneCtrl = TextEditingController();
  final _shopAddrCtrl = TextEditingController();
  final _vatCtrl = TextEditingController();

  final _delChargeCtrl = TextEditingController();
  final _riderFeeCtrl = TextEditingController();
  final _pharmDelCtrl = TextEditingController();
  final _pharmDiscCtrl = TextEditingController();
  final _maxProdCtrl = TextEditingController();
  final _maxPkgCtrl = TextEditingController();
  final _printerNameCtrl = TextEditingController();

  bool _applyMaxPos = false;
  bool _autoExpLoss = false;
  bool _pcAutoPrint = false;
  String _paperWidth = '80mm';

  bool _pcOnline = false;
  String _resolvedPrinter = '';
  int _pendingJobs = 0;
  List<String> _printers = [];

  @override
  void initState() {
    super.initState();
    _load();
  }

  @override
  void dispose() {
    _shopNameCtrl.dispose();
    _shopPhoneCtrl.dispose();
    _supportPhoneCtrl.dispose();
    _waPhoneCtrl.dispose();
    _shopAddrCtrl.dispose();
    _vatCtrl.dispose();
    _delChargeCtrl.dispose();
    _riderFeeCtrl.dispose();
    _pharmDelCtrl.dispose();
    _pharmDiscCtrl.dispose();
    _maxProdCtrl.dispose();
    _maxPkgCtrl.dispose();
    _printerNameCtrl.dispose();
    super.dispose();
  }

  bool _asBool(dynamic v) => ['1', 'true', 'yes', 'on'].contains('${v ?? ''}'.trim().toLowerCase());

  Future<void> _load() async {
    if (mounted) setState(() => _loading = true);
    final res = await AdminApiService.fetchAdminSettings();
    if (!mounted) return;
    final s = res['settings'] is Map ? Map<String, dynamic>.from(res['settings'] as Map) : <String, dynamic>{};
    final t = res['thermal'] is Map ? Map<String, dynamic>.from(res['thermal'] as Map) : <String, dynamic>{};

    setState(() {
      _shopNameCtrl.text = (s['shop_name'] ?? '').toString();
      _shopPhoneCtrl.text = (s['shop_phone'] ?? '').toString();
      _supportPhoneCtrl.text = (s['customer_support_phone'] ?? '').toString();
      _waPhoneCtrl.text = (s['admin_whatsapp_phone'] ?? '').toString();
      _shopAddrCtrl.text = (s['shop_address'] ?? '').toString();
      _vatCtrl.text = (s['vat_reg_no'] ?? '').toString();

      _delChargeCtrl.text = (s['delivery_charge'] ?? '50').toString();
      _riderFeeCtrl.text = (s['rider_delivery_fee'] ?? '30').toString();
      _pharmDelCtrl.text = (s['pharmacy_delivery_charge'] ?? '50').toString();
      _pharmDiscCtrl.text = (s['pharmacy_discount_percent'] ?? '0').toString();
      _maxProdCtrl.text = (s['max_order_qty_product'] ?? '0').toString();
      _maxPkgCtrl.text = (s['max_order_qty_package'] ?? '0').toString();

      _printerNameCtrl.text = (s['thermal_printer_name'] ?? '').toString();
      _paperWidth = (s['thermal_paper_width'] ?? '80mm').toString() == '58mm' ? '58mm' : '80mm';
      _applyMaxPos = _asBool(s['apply_max_qty_to_pos']);
      _autoExpLoss = _asBool(s['auto_record_expired_as_loss']);
      _pcAutoPrint = _asBool(s['thermal_pc_auto_print']);

      _pcOnline = t['pc_agent_online'] == true;
      _resolvedPrinter = (t['resolved_printer'] ?? '').toString();
      _pendingJobs = ((t['pending_jobs'] ?? 0) as num).toInt();
      _printers = (t['printers'] as List? ?? []).map((e) => e.toString()).toList();
      _loading = false;
    });
  }

  Future<void> _save() async {
    setState(() => _saving = true);
    final res = await AdminApiService.saveAdminSettings({
      'shop_name': _shopNameCtrl.text.trim(),
      'shop_phone': _shopPhoneCtrl.text.trim(),
      'customer_support_phone': _supportPhoneCtrl.text.trim(),
      'admin_whatsapp_phone': _waPhoneCtrl.text.trim(),
      'shop_address': _shopAddrCtrl.text.trim(),
      'vat_reg_no': _vatCtrl.text.trim(),
      'delivery_charge': _delChargeCtrl.text.trim(),
      'rider_delivery_fee': _riderFeeCtrl.text.trim(),
      'pharmacy_delivery_charge': _pharmDelCtrl.text.trim(),
      'pharmacy_discount_percent': _pharmDiscCtrl.text.trim(),
      'max_order_qty_product': _maxProdCtrl.text.trim(),
      'max_order_qty_package': _maxPkgCtrl.text.trim(),
      'apply_max_qty_to_pos': _applyMaxPos ? '1' : '0',
      'auto_record_expired_as_loss': _autoExpLoss ? '1' : '0',
      'thermal_printer_name': _printerNameCtrl.text.trim(),
      'thermal_paper_width': _paperWidth,
      'thermal_pc_auto_print': _pcAutoPrint ? '1' : '0',
    });
    if (!mounted) return;
    setState(() => _saving = false);
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(res['message']?.toString() ?? 'সেভ সম্পন্ন'),
        backgroundColor: res['success'] == true ? Colors.green.shade700 : Colors.red,
      ),
    );
    if (res['success'] == true) _load();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        backgroundColor: Colors.teal.shade900,
        foregroundColor: Colors.white,
        title: const Text('⚙️ সেটিংস ও থার্মাল প্রিন্টার', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
        actions: [
          IconButton(icon: const Icon(Icons.refresh), onPressed: _load),
        ],
      ),
      body: _loading
          ? const Center(child: CircularProgressIndicator())
          : ListView(
              padding: const EdgeInsets.all(14),
              children: [
                // PC Thermal Printer Status Card
                Container(
                  padding: const EdgeInsets.all(12),
                  decoration: BoxDecoration(
                    color: _pcOnline ? Colors.green.shade50 : Colors.amber.shade50,
                    borderRadius: BorderRadius.circular(12),
                    border: Border.all(color: _pcOnline ? Colors.green.shade300 : Colors.amber.shade400),
                  ),
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        _pcOnline ? '🟢 PC থার্মাল প্রিন্টার অনলাইন' : '🔴 PC প্রিন্ট এজেন্ট অফলাইন',
                        style: TextStyle(fontWeight: FontWeight.bold, color: _pcOnline ? Colors.green.shade900 : Colors.amber.shade900),
                      ),
                      const SizedBox(height: 4),
                      Text(
                        'প্রিন্টার: ${_resolvedPrinter.isNotEmpty ? _resolvedPrinter : 'সেট নেই'} • পেন্ডিং জব: $_pendingJobs টি',
                        style: const TextStyle(fontSize: 12),
                      ),
                      const SizedBox(height: 8),
                      Wrap(
                        spacing: 8,
                        children: [
                          ElevatedButton.icon(
                            onPressed: () => ThermalPrintHelper.runTestPrintAndConfirm(context),
                            icon: const Icon(Icons.print, size: 15),
                            label: const Text('টেস্ট প্রিন্ট', style: TextStyle(fontSize: 11.5)),
                            style: ElevatedButton.styleFrom(backgroundColor: Colors.teal.shade700, foregroundColor: Colors.white),
                          ),
                          OutlinedButton.icon(
                            onPressed: () async {
                              final messenger = ScaffoldMessenger.of(context);
                              final r = await AdminApiService.processPendingThermalJobs();
                              if (!mounted) return;
                              messenger.showSnackBar(
                                SnackBar(content: Text(r['message']?.toString() ?? 'প্রসেস সম্পন্ন')),
                              );
                              _load();
                            },
                            icon: const Icon(Icons.playlist_play, size: 16),
                            label: const Text('পেন্ডিং কিউ প্রিন্ট', style: TextStyle(fontSize: 11.5)),
                          ),
                        ],
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 14),
                const Text('🏪 দোকানের তথ্য', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 14)),
                const SizedBox(height: 8),
                TextField(controller: _shopNameCtrl, decoration: const InputDecoration(labelText: 'দোকানের নাম', border: OutlineInputBorder(), isDense: true)),
                const SizedBox(height: 8),
                TextField(controller: _shopPhoneCtrl, decoration: const InputDecoration(labelText: 'দোকানের ফোন', border: OutlineInputBorder(), isDense: true)),
                const SizedBox(height: 8),
                TextField(controller: _supportPhoneCtrl, decoration: const InputDecoration(labelText: 'কাস্টমার সাপোর্ট ফোন', border: OutlineInputBorder(), isDense: true)),
                const SizedBox(height: 8),
                TextField(controller: _waPhoneCtrl, decoration: const InputDecoration(labelText: 'অ্যাডমিন WhatsApp', border: OutlineInputBorder(), isDense: true)),
                const SizedBox(height: 8),
                TextField(controller: _shopAddrCtrl, maxLines: 2, decoration: const InputDecoration(labelText: 'ঠিকানা', border: OutlineInputBorder(), isDense: true)),
                const SizedBox(height: 8),
                TextField(controller: _vatCtrl, decoration: const InputDecoration(labelText: 'VAT / BIN রেজি. নং', border: OutlineInputBorder(), isDense: true)),
                const SizedBox(height: 14),
                const Text('🚚 ডেলিভারি ও অর্ডার সীমা', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 14)),
                const SizedBox(height: 8),
                Row(
                  children: [
                    Expanded(child: TextField(controller: _delChargeCtrl, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: 'সাধারণ ডেলিভারি চার্জ', border: OutlineInputBorder(), isDense: true))),
                    const SizedBox(width: 8),
                    Expanded(child: TextField(controller: _riderFeeCtrl, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: 'রাইডার প্রতি অর্ডার ফি', border: OutlineInputBorder(), isDense: true))),
                  ],
                ),
                const SizedBox(height: 8),
                Row(
                  children: [
                    Expanded(child: TextField(controller: _pharmDelCtrl, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: 'ফার্মেসী ডেলিভারি চার্জ', border: OutlineInputBorder(), isDense: true))),
                    const SizedBox(width: 8),
                    Expanded(child: TextField(controller: _pharmDiscCtrl, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: 'ফার্মেসী ডিসকাউন্ট (%)', border: OutlineInputBorder(), isDense: true))),
                  ],
                ),
                const SizedBox(height: 8),
                Row(
                  children: [
                    Expanded(child: TextField(controller: _maxProdCtrl, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: 'ম্যাক্স প্রোডাক্ট পরিমাণ (0=সীমাহীন)', border: OutlineInputBorder(), isDense: true))),
                    const SizedBox(width: 8),
                    Expanded(child: TextField(controller: _maxPkgCtrl, keyboardType: TextInputType.number, decoration: const InputDecoration(labelText: 'ম্যাক্স প্যাকেজ পরিমাণ', border: OutlineInputBorder(), isDense: true))),
                  ],
                ),
                SwitchListTile(dense: true, contentPadding: EdgeInsets.zero, title: const Text('POS বিলেও ম্যাক্স পরিমাণ সীমা প্রযোজ্য'), value: _applyMaxPos, onChanged: (v) => setState(() => _applyMaxPos = v)),
                SwitchListTile(dense: true, contentPadding: EdgeInsets.zero, title: const Text('মেয়াদোত্তীর্ণ পণ্য অটো লস হিসেবে গণ্য'), value: _autoExpLoss, onChanged: (v) => setState(() => _autoExpLoss = v)),
                const SizedBox(height: 10),
                const Text('🖨️ থার্মাল প্রিন্টার কনফিগারেশন', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 14)),
                const SizedBox(height: 8),
                if (_printers.isNotEmpty)
                  DropdownButtonFormField<String>(
                    initialValue: _printers.contains(_printerNameCtrl.text.trim()) ? _printerNameCtrl.text.trim() : null,
                    decoration: const InputDecoration(labelText: 'Windows প্রিন্টার নির্বাচন', border: OutlineInputBorder(), isDense: true),
                    items: _printers.map((p) => DropdownMenuItem(value: p, child: Text(p))).toList(),
                    onChanged: (v) {
                      if (v != null) setState(() => _printerNameCtrl.text = v);
                    },
                  )
                else
                  TextField(controller: _printerNameCtrl, decoration: const InputDecoration(labelText: 'থার্মাল প্রিন্টারের নাম', border: OutlineInputBorder(), isDense: true)),
                const SizedBox(height: 8),
                DropdownButtonFormField<String>(
                  initialValue: _paperWidth,
                  decoration: const InputDecoration(labelText: 'পেপার সাইজ', border: OutlineInputBorder(), isDense: true),
                  items: const [
                    DropdownMenuItem(value: '80mm', child: Text('80mm Thermal Roll')),
                    DropdownMenuItem(value: '58mm', child: Text('58mm Thermal Roll')),
                  ],
                  onChanged: (v) {
                    if (v != null) setState(() => _paperWidth = v);
                  },
                ),
                SwitchListTile(dense: true, contentPadding: EdgeInsets.zero, title: const Text('ক্লাউড/POS বিলে অটো প্রিন্ট'), value: _pcAutoPrint, onChanged: (v) => setState(() => _pcAutoPrint = v)),
                const SizedBox(height: 14),
                SizedBox(
                  width: double.infinity,
                  child: ElevatedButton.icon(
                    onPressed: _saving ? null : _save,
                    icon: const Icon(Icons.save),
                    label: Text(_saving ? 'সংরক্ষণ হচ্ছে...' : 'সব সেটিংস সংরক্ষণ করুন'),
                    style: ElevatedButton.styleFrom(
                      backgroundColor: Colors.teal.shade700,
                      foregroundColor: Colors.white,
                      padding: const EdgeInsets.symmetric(vertical: 14),
                    ),
                  ),
                ),
              ],
            ),
    );
  }
}
