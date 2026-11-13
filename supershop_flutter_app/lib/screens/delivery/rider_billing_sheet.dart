import 'dart:async';
import 'package:flutter/material.dart';
import '../../services/api_service.dart';

/// Opens the mobile Rider Billing bottom sheet supporting Regular Products, Combos & Pharmacy Medicines.
Future<void> showRiderBillingModal(
  BuildContext context, {
  required String riderPhone,
  VoidCallback? onBillCreated,
}) {
  return showModalBottomSheet(
    context: context,
    isScrollControlled: true,
    backgroundColor: Colors.transparent,
    builder: (ctx) => RiderBillingSheet(
      riderPhone: riderPhone,
      onBillCreated: onBillCreated,
    ),
  );
}

class RiderBillingSheet extends StatefulWidget {
  final String riderPhone;
  final VoidCallback? onBillCreated;

  const RiderBillingSheet({
    Key? key,
    required this.riderPhone,
    this.onBillCreated,
  }) : super(key: key);

  @override
  State<RiderBillingSheet> createState() => _RiderBillingSheetState();
}

class _RiderBillingSheetState extends State<RiderBillingSheet> {
  final TextEditingController _searchCtrl = TextEditingController();
  final TextEditingController _custNameCtrl = TextEditingController(text: 'Walk-in / Rider Customer');
  final TextEditingController _custPhoneCtrl = TextEditingController();
  final TextEditingController _discountCtrl = TextEditingController(text: '0');

  Timer? _debounce;
  String _activeTab = 'products'; // 'products', 'packages', 'pharmacy'
  bool _loadingCatalog = true;
  bool _submitting = false;
  bool _printToPc = true;

  List<Map<String, dynamic>> _products = [];
  List<Map<String, dynamic>> _packages = [];
  List<Map<String, dynamic>> _medicines = [];
  final List<Map<String, dynamic>> _cart = [];

  @override
  void initState() {
    super.initState();
    _loadCatalog('');
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _searchCtrl.dispose();
    _custNameCtrl.dispose();
    _custPhoneCtrl.dispose();
    _discountCtrl.dispose();
    super.dispose();
  }

  Future<void> _loadCatalog(String query) async {
    if (!mounted) return;
    setState(() => _loadingCatalog = true);
    final res = await ApiService.fetchRiderCatalog(
      riderPhone: widget.riderPhone,
      query: query,
      type: 'all',
    );
    if (!mounted) return;
    setState(() {
      _products = (res['products'] as List? ?? [])
          .whereType<Map>()
          .map((e) => Map<String, dynamic>.from(e))
          .toList();
      _packages = (res['packages'] as List? ?? [])
          .whereType<Map>()
          .map((e) => Map<String, dynamic>.from(e))
          .toList();
      _medicines = (res['medicines'] as List? ?? [])
          .whereType<Map>()
          .map((e) => Map<String, dynamic>.from(e))
          .toList();
      _loadingCatalog = false;
    });
  }

  void _onSearchChanged(String val) {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 300), () {
      _loadCatalog(val.trim());
    });
  }

  void _addToCart(Map<String, dynamic> item) {
    final int id = (item['id'] as num?)?.toInt() ?? 0;
    final String itemType = (item['item_type'] ?? 'product').toString();
    final idx = _cart.indexWhere((c) => c['id'] == id && c['item_type'] == itemType);
    setState(() {
      if (idx >= 0) {
        _cart[idx]['quantity'] = (_cart[idx]['quantity'] as int) + 1;
      } else {
        _cart.add({
          'id': id,
          'item_type': itemType,
          'name': item['name'] ?? 'Item',
          'unit_price': ((item['sell_price'] ?? 0) as num).toDouble(),
          'quantity': 1,
        });
      }
    });
  }

  void _updateCartQty(int index, int delta) {
    setState(() {
      final int next = (_cart[index]['quantity'] as int) + delta;
      if (next <= 0) {
        _cart.removeAt(index);
      } else {
        _cart[index]['quantity'] = next;
      }
    });
  }

  double get _cartSubtotal => _cart.fold<double>(
        0.0,
        (sum, c) => sum + ((c['unit_price'] as double) * (c['quantity'] as int)),
      );

  double get _extraDiscount => double.tryParse(_discountCtrl.text.trim()) ?? 0.0;

  double get _netTotal => (_cartSubtotal - _extraDiscount).clamp(0.0, double.infinity);

  Future<void> _submitBill() async {
    if (_cart.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('অনুগ্রহ করে অন্তত একটি পণ্য বা ঔষধ যোগ করুন।'), backgroundColor: Colors.red),
      );
      return;
    }
    setState(() => _submitting = true);
    final res = await ApiService.createRiderBill(
      riderPhone: widget.riderPhone,
      customerName: _custNameCtrl.text,
      customerPhone: _custPhoneCtrl.text,
      items: _cart,
      extraDiscount: _extraDiscount,
      printToPc: _printToPc,
    );
    if (!mounted) return;
    setState(() => _submitting = false);

    if (res['success'] == true) {
      final String inv = (res['invoice_number'] ?? '').toString();
      final double total = ((res['rounded_total'] ?? _netTotal) as num).toDouble();
      final Map<String, dynamic> th = res['thermal_print'] is Map
          ? Map<String, dynamic>.from(res['thermal_print'])
          : {};
      final String thermalMsg = (th['message'] ?? '').toString();

      widget.onBillCreated?.call();
      Navigator.of(context).pop();
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            '✅ বিল তৈরি: $inv (TK ${total.toStringAsFixed(0)})${thermalMsg.isNotEmpty ? '\n🖨️ $thermalMsg' : ''}',
          ),
          backgroundColor: Colors.teal.shade700,
          duration: const Duration(seconds: 5),
        ),
      );
    } else {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(res['message']?.toString() ?? 'বিল তৈরি ব্যর্থ হয়েছে।'),
          backgroundColor: Colors.red,
        ),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final List<Map<String, dynamic>> visibleList = _activeTab == 'pharmacy'
        ? _medicines
        : (_activeTab == 'packages' ? _packages : _products);

    return DraggableScrollableSheet(
      initialChildSize: 0.92,
      minChildSize: 0.65,
      maxChildSize: 0.96,
      builder: (_, scrollCtrl) => Container(
        decoration: const BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.vertical(top: Radius.circular(18)),
        ),
        child: Column(
          children: [
            // Header
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
              decoration: BoxDecoration(
                color: Colors.teal.shade800,
                borderRadius: const BorderRadius.vertical(top: Radius.circular(18)),
              ),
              child: Row(
                children: [
                  const Icon(Icons.receipt_long, color: Colors.white),
                  const SizedBox(width: 8),
                  const Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          'রাইডার মোবাইল বিলিং (POS)',
                          style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 15),
                        ),
                        Text(
                          'সাধারণ পণ্য, কম্বো ও ফার্মেসী ঔষধ + PC প্রিন্ট',
                          style: TextStyle(color: Colors.white70, fontSize: 11),
                        ),
                      ],
                    ),
                  ),
                  IconButton(
                    icon: const Icon(Icons.close, color: Colors.white),
                    onPressed: () => Navigator.of(context).pop(),
                  ),
                ],
              ),
            ),

            // Search & Tabs
            Padding(
              padding: const EdgeInsets.fromLTRB(12, 10, 12, 6),
              child: Column(
                children: [
                  TextField(
                    controller: _searchCtrl,
                    onChanged: _onSearchChanged,
                    decoration: InputDecoration(
                      hintText: 'পণ্য, কম্বো বা ঔষধের নাম লিখে খুঁজুন...',
                      prefixIcon: const Icon(Icons.search, size: 20),
                      isDense: true,
                      border: OutlineInputBorder(borderRadius: BorderRadius.circular(10)),
                      contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                    ),
                  ),
                  const SizedBox(height: 8),
                  Row(
                    children: [
                      _buildTabChip('products', '🛒 পণ্য (${_products.length})', Colors.blue.shade700),
                      const SizedBox(width: 6),
                      _buildTabChip('packages', '🎁 কম্বো (${_packages.length})', Colors.deepPurple.shade700),
                      const SizedBox(width: 6),
                      _buildTabChip('pharmacy', '💊 ঔষধ (${_medicines.length})', Colors.green.shade700),
                    ],
                  ),
                ],
              ),
            ),

            // Catalog List
            Expanded(
              child: _loadingCatalog
                  ? const Center(child: CircularProgressIndicator())
                  : visibleList.isEmpty
                      ? const Center(child: Text('কোনো আইটেম পাওয়া যায়নি।', style: TextStyle(color: Colors.grey)))
                      : ListView.builder(
                          controller: scrollCtrl,
                          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                          itemCount: visibleList.length,
                          itemBuilder: (_, idx) {
                            final it = visibleList[idx];
                            final double price = ((it['sell_price'] ?? 0) as num).toDouble();
                            final int stock = ((it['stock_qty'] ?? 0) as num).toInt();
                            final String extra = it['item_type'] == 'medicine'
                                ? "${it['generic_name'] ?? ''} ${it['strength'] ?? ''}".trim()
                                : (it['category'] ?? '').toString();
                            return Card(
                              margin: const EdgeInsets.only(bottom: 6),
                              elevation: 1,
                              child: ListTile(
                                dense: true,
                                title: Text(
                                  (it['name'] ?? '').toString(),
                                  style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13),
                                ),
                                subtitle: Text(
                                  'TK ${price.toStringAsFixed(0)} • স্টক: $stock${extra.isNotEmpty ? ' • $extra' : ''}',
                                  style: TextStyle(fontSize: 11, color: Colors.grey.shade700),
                                ),
                                trailing: ElevatedButton(
                                  onPressed: () => _addToCart(it),
                                  style: ElevatedButton.styleFrom(
                                    backgroundColor: Colors.teal.shade700,
                                    foregroundColor: Colors.white,
                                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                                    minimumSize: const Size(0, 30),
                                  ),
                                  child: const Text('+ যোগ', style: TextStyle(fontSize: 11, fontWeight: FontWeight.bold)),
                                ),
                              ),
                            );
                          },
                        ),
            ),

            // Cart & Customer Checkout Dock
            Container(
              padding: EdgeInsets.fromLTRB(12, 8, 12, MediaQuery.of(context).viewInsets.bottom + 10),
              decoration: BoxDecoration(
                color: Colors.grey.shade100,
                border: Border(top: BorderSide(color: Colors.grey.shade300)),
              ),
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  if (_cart.isNotEmpty) ...[
                    SizedBox(
                      height: _cart.length > 2 ? 92 : (_cart.length * 36.0),
                      child: ListView.builder(
                        itemCount: _cart.length,
                        itemBuilder: (_, i) {
                          final c = _cart[i];
                          return Padding(
                            padding: const EdgeInsets.symmetric(vertical: 2),
                            child: Row(
                              children: [
                                Expanded(
                                  child: Text(
                                    '${c['item_type'] == 'medicine' ? '💊' : '🛒'} ${c['name']}',
                                    overflow: TextOverflow.ellipsis,
                                    style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
                                  ),
                                ),
                                IconButton(
                                  visualDensity: VisualDensity.compact,
                                  icon: const Icon(Icons.remove_circle_outline, size: 18, color: Colors.red),
                                  onPressed: () => _updateCartQty(i, -1),
                                ),
                                Text('${c['quantity']}', style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 12)),
                                IconButton(
                                  visualDensity: VisualDensity.compact,
                                  icon: const Icon(Icons.add_circle_outline, size: 18, color: Colors.teal),
                                  onPressed: () => _updateCartQty(i, 1),
                                ),
                                Text(
                                  'TK ${((c['unit_price'] as double) * (c['quantity'] as int)).toStringAsFixed(0)}',
                                  style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 12),
                                ),
                              ],
                            ),
                          );
                        },
                      ),
                    ),
                    const Divider(height: 8),
                  ],
                  Row(
                    children: [
                      Expanded(
                        flex: 3,
                        child: TextField(
                          controller: _custNameCtrl,
                          style: const TextStyle(fontSize: 12),
                          decoration: const InputDecoration(
                            labelText: 'কাস্টমার নাম',
                            isDense: true,
                            filled: true,
                            fillColor: Colors.white,
                            border: OutlineInputBorder(),
                          ),
                        ),
                      ),
                      const SizedBox(width: 6),
                      Expanded(
                        flex: 3,
                        child: TextField(
                          controller: _custPhoneCtrl,
                          keyboardType: TextInputType.phone,
                          style: const TextStyle(fontSize: 12),
                          decoration: const InputDecoration(
                            labelText: 'মোবাইল',
                            isDense: true,
                            filled: true,
                            fillColor: Colors.white,
                            border: OutlineInputBorder(),
                          ),
                        ),
                      ),
                      const SizedBox(width: 6),
                      Expanded(
                        flex: 2,
                        child: TextField(
                          controller: _discountCtrl,
                          keyboardType: TextInputType.number,
                          onChanged: (_) => setState(() {}),
                          style: const TextStyle(fontSize: 12),
                          decoration: const InputDecoration(
                            labelText: 'ছাড় (TK)',
                            isDense: true,
                            filled: true,
                            fillColor: Colors.white,
                            border: OutlineInputBorder(),
                          ),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 6),
                  Row(
                    children: [
                      Checkbox(
                        value: _printToPc,
                        visualDensity: VisualDensity.compact,
                        onChanged: (v) => setState(() => _printToPc = v ?? true),
                      ),
                      const Expanded(
                        child: Text(
                          '🖨️ বিল সেভ করে দোকানের PC থার্মাল প্রিন্টারে প্রিন্ট করুন',
                          style: TextStyle(fontSize: 11, fontWeight: FontWeight.w600),
                        ),
                      ),
                    ],
                  ),
                  SizedBox(
                    width: double.infinity,
                    child: ElevatedButton.icon(
                      onPressed: _submitting ? null : _submitBill,
                      icon: _submitting
                          ? const SizedBox(
                              width: 16,
                              height: 16,
                              child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                            )
                          : const Icon(Icons.check_circle, color: Colors.white),
                      label: Text(
                        _submitting
                            ? 'বিল সেভ হচ্ছে...'
                            : 'বিল তৈরি করুন • TK ${_netTotal.toStringAsFixed(0)} (${_cart.length} আইটেম)',
                        style: const TextStyle(fontWeight: FontWeight.bold, color: Colors.white),
                      ),
                      style: ElevatedButton.styleFrom(
                        backgroundColor: Colors.teal.shade800,
                        padding: const EdgeInsets.symmetric(vertical: 12),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildTabChip(String tabKey, String label, Color activeColor) {
    final bool selected = _activeTab == tabKey;
    return Expanded(
      child: InkWell(
        onTap: () => setState(() => _activeTab = tabKey),
        borderRadius: BorderRadius.circular(8),
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 4),
          decoration: BoxDecoration(
            color: selected ? activeColor : Colors.grey.shade200,
            borderRadius: BorderRadius.circular(8),
          ),
          alignment: Alignment.center,
          child: Text(
            label,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              fontSize: 11,
              fontWeight: FontWeight.bold,
              color: selected ? Colors.white : Colors.grey.shade800,
            ),
          ),
        ),
      ),
    );
  }
}
