import 'dart:async';
import 'package:flutter/material.dart';
import '../services/api_service.dart';
import 'app_image_loader.dart';
import 'barcode_scanner_sheet.dart';

/// Shared prescription image inspector + barcode/search multi-unit quotation builder
/// for both Admin (`isAdmin: true`) and permitted Riders (`isAdmin: false`).
class RxQuoteBuilderSheet extends StatefulWidget {
  final Map<String, dynamic> order;
  final bool isAdmin;
  final String riderPhone;

  const RxQuoteBuilderSheet({
    super.key,
    required this.order,
    required this.isAdmin,
    this.riderPhone = '',
  });

  static Future<bool?> open(
    BuildContext context, {
    required Map<String, dynamic> order,
    required bool isAdmin,
    String riderPhone = '',
  }) {
    return showModalBottomSheet<bool>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => RxQuoteBuilderSheet(
        order: order,
        isAdmin: isAdmin,
        riderPhone: riderPhone,
      ),
    );
  }

  @override
  State<RxQuoteBuilderSheet> createState() => _RxQuoteBuilderSheetState();
}

class _RxQuoteBuilderSheetState extends State<RxQuoteBuilderSheet> {
  final TextEditingController _searchCtrl = TextEditingController();
  final TextEditingController _deliveryCtrl = TextEditingController();
  final TextEditingController _notesCtrl = TextEditingController();

  Timer? _debounce;
  bool _loadingCatalog = false;
  bool _submitting = false;
  int _selectedImageIdx = 0;

  List<String> _rxImages = [];
  List<Map<String, dynamic>> _requestedItems = [];
  List<Map<String, dynamic>> _cart = [];
  List<Map<String, dynamic>> _searchResults = [];

  @override
  void initState() {
    super.initState();
    final o = widget.order;
    final imgs = (o['prescription_images'] as List? ?? [])
        .map((e) => e.toString().trim())
        .where((e) => e.isNotEmpty)
        .toList();
    if (imgs.isEmpty && (o['prescription_url'] ?? '').toString().trim().isNotEmpty) {
      imgs.add(o['prescription_url'].toString().trim());
    }
    _rxImages = imgs;

    _requestedItems = (o['requested_items'] as List? ?? [])
        .whereType<Map>()
        .map((e) => Map<String, dynamic>.from(e))
        .toList();

    final approved = (o['approved_items'] as List? ?? [])
        .whereType<Map>()
        .map((e) => Map<String, dynamic>.from(e))
        .toList();
    _cart = approved.map((it) {
      final int qty = ((it['quantity'] ?? it['qty'] ?? 1) as num).toInt().clamp(1, 999);
      final double unitP = ((it['unit_price'] ?? 0) as num).toDouble();
      final String type = (it['item_type'] ?? (it['medicine_id'] != null ? 'medicine' : 'product')).toString();
      final String unitMode = (it['unit_mode'] ?? it['sell_unit'] ?? 'piece').toString();
      return {
        'id': it['medicine_id'] ?? it['product_id'] ?? it['id'],
        'medicine_id': it['medicine_id'],
        'product_id': it['product_id'],
        'item_type': type,
        'name': (it['name'] ?? 'Item').toString(),
        'unit_mode': unitMode,
        'sell_unit': unitMode,
        'quantity': qty,
        'unit_price': unitP,
        'piece_price': unitP,
        'strip_price': ((it['strip_price'] ?? 0) as num).toDouble(),
        'packet_price': ((it['packet_price'] ?? 0) as num).toDouble(),
        'strip_size': ((it['strip_size'] ?? 10) as num).toInt(),
        'packet_size': ((it['packet_size'] ?? 30) as num).toInt(),
        'unit': (it['unit'] ?? 'পিস').toString(),
      };
    }).toList();

    final double dChg = ((o['delivery_charge'] ?? 50) as num).toDouble();
    _deliveryCtrl.text = dChg.toStringAsFixed(0);
    _notesCtrl.text = (o['admin_notes'] ?? '').toString();
    _searchCatalog('');
  }

  @override
  void dispose() {
    _debounce?.cancel();
    _searchCtrl.dispose();
    _deliveryCtrl.dispose();
    _notesCtrl.dispose();
    super.dispose();
  }

  Future<void> _searchCatalog(String q, {bool autoAddExact = false}) async {
    if (!mounted) return;
    setState(() => _loadingCatalog = true);
    final res = await ApiService.fetchRiderCatalog(
      riderPhone: widget.riderPhone.isNotEmpty ? widget.riderPhone : 'admin',
      query: q,
      type: 'all',
    );
    if (!mounted) return;

    final meds = (res['medicines'] as List? ?? [])
        .whereType<Map>()
        .map((e) => Map<String, dynamic>.from(e))
        .toList();
    final prods = (res['products'] as List? ?? [])
        .whereType<Map>()
        .map((e) => Map<String, dynamic>.from(e))
        .toList();
    final pkgs = (res['packages'] as List? ?? [])
        .whereType<Map>()
        .map((e) => Map<String, dynamic>.from(e))
        .toList();

    final combined = [...meds, ...prods, ...pkgs];
    setState(() {
      _searchResults = combined;
      _loadingCatalog = false;
    });

    if (autoAddExact && q.isNotEmpty && combined.isNotEmpty) {
      final exact = combined.firstWhere(
        (m) => (m['sku'] ?? '').toString().trim().toLowerCase() == q.trim().toLowerCase(),
        orElse: () => combined.first,
      );
      if ((exact['sku'] ?? '').toString().trim().toLowerCase() == q.trim().toLowerCase() ||
          combined.length == 1) {
        _addCatalogItem(exact);
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text('✅ স্ক্যান করা আইটেম যোগ হয়েছে: ${exact['name']}'),
            backgroundColor: Colors.teal.shade700,
            duration: const Duration(seconds: 2),
          ),
        );
      }
    }
  }

  void _onSearchChanged(String val) {
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 280), () => _searchCatalog(val.trim()));
  }

  Future<void> _scanBarcode() async {
    final code = await BarcodeScannerSheet.scan(
      context,
      title: 'ঔষধ বা পণ্যের বারকোড স্ক্যান করুন',
    );
    if (code == null || code.isEmpty || !mounted) return;
    _searchCtrl.text = code;
    await _searchCatalog(code, autoAddExact: true);
  }

  void _addCatalogItem(Map<String, dynamic> item) {
    final String type = (item['item_type'] ?? 'medicine').toString();
    final int id = (item['id'] as num?)?.toInt() ?? 0;
    final int stripSize = ((item['strip_size'] ?? 10) as num).toInt().clamp(1, 500);
    final int packetSize = ((item['packet_size'] ?? 30) as num).toInt().clamp(1, 5000);
    final double piecePrice = ((item['sell_price'] ?? item['unit_price'] ?? 0) as num).toDouble();
    final double stripPriceRaw = ((item['strip_price'] ?? 0) as num).toDouble();
    final double packetPriceRaw = ((item['packet_price'] ?? 0) as num).toDouble();
    final double stripPrice = stripPriceRaw > 0 ? stripPriceRaw : (piecePrice * stripSize);
    final double packetPrice = packetPriceRaw > 0 ? packetPriceRaw : (piecePrice * packetSize);

    setState(() {
      final idx = _cart.indexWhere(
        (c) => c['id'] == id && c['item_type'] == type && (c['sell_unit'] ?? 'piece') == 'piece',
      );
      if (idx >= 0) {
        _cart[idx]['quantity'] = (_cart[idx]['quantity'] as int) + 1;
      } else {
        _cart.add({
          'id': id,
          'medicine_id': type == 'medicine' ? id : null,
          'product_id': type != 'medicine' ? id : null,
          'item_type': type,
          'name': (item['name'] ?? 'Item').toString(),
          'generic_name': (item['generic_name'] ?? '').toString(),
          'dosage_form': (item['dosage_form'] ?? 'Tablet').toString(),
          'strength': (item['strength'] ?? '').toString(),
          'unit_mode': 'piece',
          'sell_unit': 'piece',
          'quantity': 1,
          'unit_price': piecePrice,
          'piece_price': piecePrice,
          'strip_price': stripPrice,
          'packet_price': packetPrice,
          'strip_size': stripSize,
          'packet_size': packetSize,
          'unit': type == 'medicine' ? 'পিস' : (item['unit'] ?? 'পিস').toString(),
        });
      }
    });
  }

  void _changeCartUnit(int idx, String nextMode) {
    setState(() {
      final c = _cart[idx];
      final double pieceP = ((c['piece_price'] ?? c['unit_price'] ?? 0) as num).toDouble();
      final int sSize = ((c['strip_size'] ?? 10) as num).toInt().clamp(1, 500);
      final int pSize = ((c['packet_size'] ?? 30) as num).toInt().clamp(1, 5000);
      final double stripP = ((c['strip_price'] ?? 0) as num).toDouble() > 0
          ? ((c['strip_price'] ?? 0) as num).toDouble()
          : pieceP * sSize;
      final double packetP = ((c['packet_price'] ?? 0) as num).toDouble() > 0
          ? ((c['packet_price'] ?? 0) as num).toDouble()
          : pieceP * pSize;

      c['unit_mode'] = nextMode;
      c['sell_unit'] = nextMode;
      if (nextMode == 'strip') {
        c['unit_price'] = stripP;
        c['unit'] = 'পাতা ($sSize)';
      } else if (nextMode == 'packet') {
        c['unit_price'] = packetP;
        c['unit'] = 'প্যাকেট ($pSize)';
      } else {
        c['unit_price'] = pieceP;
        c['unit'] = 'পিস';
      }
    });
  }

  double get _subtotal => _cart.fold<double>(
        0.0,
        (sum, it) =>
            sum +
            (((it['unit_price'] ?? 0) as num).toDouble() *
                ((it['quantity'] ?? 1) as num).toInt()),
      );

  double get _deliveryCharge => double.tryParse(_deliveryCtrl.text.trim()) ?? 50.0;
  double get _grandTotal => _subtotal + _deliveryCharge;

  Future<void> _submitQuote() async {
    if (_cart.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text('অন্তত ১টি ঔষধ বা পণ্য যোগ করুন।'), backgroundColor: Colors.red),
      );
      return;
    }
    setState(() => _submitting = true);
    final int orderId = ((widget.order['id'] ?? 0) as num).toInt();

    final payloadItems = _cart
        .map((c) => {
              'item_type': c['item_type'],
              if (c['medicine_id'] != null) 'medicine_id': c['medicine_id'],
              if (c['product_id'] != null) 'product_id': c['product_id'],
              'id': c['id'],
              'name': c['name'],
              'generic_name': c['generic_name'] ?? '',
              'dosage_form': c['dosage_form'] ?? '',
              'strength': c['strength'] ?? '',
              'quantity': c['quantity'],
              'unit_mode': c['unit_mode'] ?? 'piece',
              'sell_unit': c['sell_unit'] ?? 'piece',
              'unit_price': c['unit_price'],
              'unit': c['unit'] ?? 'পিস',
            })
        .toList();

    final res = widget.isAdmin
        ? await ApiService.submitAdminPharmacyQuote(
            orderId: orderId,
            items: payloadItems,
            deliveryCharge: _deliveryCharge,
            adminNotes: _notesCtrl.text.trim(),
          )
        : await ApiService.submitRiderPharmacyQuote(
            orderId: orderId,
            items: payloadItems,
            riderPhone: widget.riderPhone,
            deliveryCharge: _deliveryCharge,
            adminNotes: _notesCtrl.text.trim(),
          );

    if (!mounted) return;
    setState(() => _submitting = false);

    if (res['success'] == true) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            res['message']?.toString() ??
                '✅ কোটেশন পাঠানো হয়েছে! কাস্টমারের মোবাইলে নোটিফিকেশন গিয়েছে।',
          ),
          backgroundColor: Colors.green.shade700,
        ),
      );
      Navigator.of(context).pop(true);
    } else {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(res['message']?.toString() ?? 'কোটেশন পাঠানো যায়নি।'),
          backgroundColor: Colors.red,
        ),
      );
    }
  }

  void _openFullImage(String url) {
    showDialog(
      context: context,
      builder: (_) => Dialog(
        backgroundColor: Colors.black,
        insetPadding: const EdgeInsets.all(8),
        child: Stack(
          children: [
            InteractiveViewer(
              minScale: 0.8,
              maxScale: 5.0,
              child: Center(
                child: AppImageLoader(imageUrl: url, fit: BoxFit.contain),
              ),
            ),
            Positioned(
              top: 8,
              right: 8,
              child: CircleAvatar(
                backgroundColor: Colors.black54,
                child: IconButton(
                  icon: const Icon(Icons.close, color: Colors.white),
                  onPressed: () => Navigator.of(context).pop(),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final o = widget.order;
    final bottomInset = MediaQuery.of(context).viewInsets.bottom;

    return Container(
      height: MediaQuery.of(context).size.height * 0.94,
      decoration: const BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.vertical(top: Radius.circular(18)),
      ),
      child: Column(
        children: [
          // Top Header
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 11),
            decoration: BoxDecoration(
              color: Colors.teal.shade800,
              borderRadius: const BorderRadius.vertical(top: Radius.circular(18)),
            ),
            child: Row(
              children: [
                const Icon(Icons.medical_services, color: Colors.white),
                const SizedBox(width: 8),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        'Rx কোটেশন ও বিল #${o['order_number'] ?? ''}',
                        style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 14.5),
                      ),
                      Text(
                        '${o['customer_name'] ?? ''} • ${o['customer_phone'] ?? ''}',
                        style: const TextStyle(color: Colors.white70, fontSize: 11),
                      ),
                    ],
                  ),
                ),
                IconButton(
                  icon: const Icon(Icons.close, color: Colors.white),
                  onPressed: () => Navigator.of(context).pop(false),
                ),
              ],
            ),
          ),

          Expanded(
            child: ListView(
              padding: EdgeInsets.fromLTRB(12, 10, 12, bottomInset + 16),
              children: [
                // Prescription Preview & Zoom
                if (_rxImages.isNotEmpty) ...[
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      const Text('📄 প্রেসক্রিপশন ছবি (জুম করতে ট্যাপ করুন)', style: TextStyle(fontWeight: FontWeight.bold, fontSize: 12.5)),
                      if (_rxImages.length > 1)
                        Text('${_selectedImageIdx + 1}/${_rxImages.length}', style: const TextStyle(fontSize: 11.5, color: Colors.teal)),
                    ],
                  ),
                  const SizedBox(height: 6),
                  GestureDetector(
                    onTap: () => _openFullImage(_rxImages[_selectedImageIdx]),
                    child: Container(
                      height: 175,
                      width: double.infinity,
                      decoration: BoxDecoration(
                        color: Colors.grey.shade100,
                        borderRadius: BorderRadius.circular(10),
                        border: Border.all(color: Colors.teal.shade200),
                      ),
                      clipBehavior: Clip.antiAlias,
                      child: Stack(
                        fit: StackFit.expand,
                        children: [
                          AppImageLoader(imageUrl: _rxImages[_selectedImageIdx], fit: BoxFit.contain),
                          Positioned(
                            bottom: 6,
                            right: 6,
                            child: Container(
                              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                              decoration: BoxDecoration(
                                color: Colors.black54,
                                borderRadius: BorderRadius.circular(12),
                              ),
                              child: const Row(
                                children: [
                                  Icon(Icons.zoom_in, color: Colors.white, size: 14),
                                  SizedBox(width: 4),
                                  Text('ফুলস্ক্রিন', style: TextStyle(color: Colors.white, fontSize: 10.5)),
                                ],
                              ),
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                  if (_rxImages.length > 1) ...[
                    const SizedBox(height: 6),
                    SizedBox(
                      height: 44,
                      child: ListView.separated(
                        scrollDirection: Axis.horizontal,
                        itemCount: _rxImages.length,
                        separatorBuilder: (_, __) => const SizedBox(width: 6),
                        itemBuilder: (_, idx) => GestureDetector(
                          onTap: () => setState(() => _selectedImageIdx = idx),
                          child: Container(
                            width: 44,
                            decoration: BoxDecoration(
                              borderRadius: BorderRadius.circular(6),
                              border: Border.all(
                                color: idx == _selectedImageIdx ? Colors.teal.shade700 : Colors.grey.shade300,
                                width: idx == _selectedImageIdx ? 2.5 : 1,
                              ),
                            ),
                            clipBehavior: Clip.antiAlias,
                            child: AppImageLoader(imageUrl: _rxImages[idx], fit: BoxFit.cover),
                          ),
                        ),
                      ),
                    ),
                  ],
                  const SizedBox(height: 10),
                ],

                // Customer Request Info
                if (_requestedItems.isNotEmpty || (o['customer_notes'] ?? '').toString().isNotEmpty)
                  Container(
                    padding: const EdgeInsets.all(9),
                    margin: const EdgeInsets.only(bottom: 10),
                    decoration: BoxDecoration(
                      color: Colors.green.shade50,
                      borderRadius: BorderRadius.circular(10),
                      border: Border.all(color: Colors.green.shade200),
                    ),
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        if ((o['customer_notes'] ?? '').toString().isNotEmpty)
                          Text('📝 কাস্টমার নোট: ${o['customer_notes']}', style: TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: Colors.green.shade900)),
                        if (((o['overall_duration_days'] ?? 0) as num) > 0)
                          Text('⏱️ মেয়াদ: ${o['overall_duration_days']} দিন', style: const TextStyle(fontSize: 11.5, fontWeight: FontWeight.bold)),
                        if (_requestedItems.isNotEmpty) ...[
                          const SizedBox(height: 4),
                          Text(
                            'রিকোয়েস্টেড: ${_requestedItems.map((e) => '${e['name']} x${e['quantity'] ?? 1}').join(', ')}',
                            style: const TextStyle(fontSize: 11.5),
                          ),
                        ],
                      ],
                    ),
                  ),

                // Search + Barcode Scan Row
                Row(
                  children: [
                    Expanded(
                      child: TextField(
                        controller: _searchCtrl,
                        onChanged: _onSearchChanged,
                        decoration: InputDecoration(
                          hintText: 'ঔষধ / পণ্য / SKU খুঁজুন...',
                          prefixIcon: const Icon(Icons.search, size: 19),
                          isDense: true,
                          border: OutlineInputBorder(borderRadius: BorderRadius.circular(10)),
                          contentPadding: const EdgeInsets.symmetric(horizontal: 10, vertical: 10),
                        ),
                      ),
                    ),
                    const SizedBox(width: 8),
                    ElevatedButton.icon(
                      onPressed: _scanBarcode,
                      icon: const Icon(Icons.qr_code_scanner, size: 18),
                      label: const Text('স্ক্যান'),
                      style: ElevatedButton.styleFrom(
                        backgroundColor: Colors.indigo.shade700,
                        foregroundColor: Colors.white,
                        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 11),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 8),

                // Search Matches
                if (_loadingCatalog)
                  const Padding(
                    padding: EdgeInsets.symmetric(vertical: 12),
                    child: Center(child: CircularProgressIndicator(strokeWidth: 2)),
                  )
                else
                  Container(
                    constraints: const BoxConstraints(maxHeight: 190),
                    decoration: BoxDecoration(
                      border: Border.all(color: Colors.grey.shade200),
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: _searchResults.isEmpty
                        ? const Padding(
                            padding: EdgeInsets.all(14),
                            child: Center(child: Text('কোনো আইটেম পাওয়া যায়নি', style: TextStyle(color: Colors.grey, fontSize: 12))),
                          )
                        : ListView.separated(
                            shrinkWrap: true,
                            itemCount: _searchResults.length,
                            separatorBuilder: (_, __) => const Divider(height: 1),
                            itemBuilder: (_, idx) {
                              final it = _searchResults[idx];
                              final bool isMed = it['item_type'] == 'medicine';
                              final double p = ((it['sell_price'] ?? 0) as num).toDouble();
                              final int st = ((it['stock_qty'] ?? 0) as num).toInt();
                              return ListTile(
                                dense: true,
                                leading: Text(isMed ? '💊' : '🛒', style: const TextStyle(fontSize: 18)),
                                title: Text((it['name'] ?? '').toString(), style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 12.5)),
                                subtitle: Text(
                                  'TK ${p.toStringAsFixed(1)} • স্টক: $st${isMed && (it['strip_price'] ?? 0) > 0 ? ' • পাতা ৳${((it['strip_price'] ?? 0) as num).toStringAsFixed(0)}' : ''}',
                                  style: const TextStyle(fontSize: 11),
                                ),
                                trailing: ElevatedButton(
                                  onPressed: () => _addCatalogItem(it),
                                  style: ElevatedButton.styleFrom(
                                    backgroundColor: Colors.teal.shade700,
                                    foregroundColor: Colors.white,
                                    minimumSize: const Size(0, 28),
                                    padding: const EdgeInsets.symmetric(horizontal: 10),
                                  ),
                                  child: const Text('+ যোগ', style: TextStyle(fontSize: 11, fontWeight: FontWeight.bold)),
                                ),
                              );
                            },
                          ),
                  ),
                const SizedBox(height: 12),

                // Quote Cart Items
                Text('📋 কোটেশন তালিকা (${_cart.length} আইটেম)', style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13)),
                const SizedBox(height: 6),
                if (_cart.isEmpty)
                  Container(
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(color: Colors.grey.shade50, borderRadius: BorderRadius.circular(8)),
                    child: const Text('উপর থেকে ঔষধ বা পণ্য যোগ করুন', style: TextStyle(color: Colors.grey, fontSize: 12)),
                  )
                else
                  ...List.generate(_cart.length, (idx) {
                    final c = _cart[idx];
                    final bool isMed = c['item_type'] == 'medicine';
                    final String unitMode = (c['sell_unit'] ?? 'piece').toString();
                    final double up = ((c['unit_price'] ?? 0) as num).toDouble();
                    final int qty = ((c['quantity'] ?? 1) as num).toInt();
                    return Card(
                      margin: const EdgeInsets.only(bottom: 6),
                      child: Padding(
                        padding: const EdgeInsets.all(8),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              children: [
                                Expanded(
                                  child: Text(
                                    '${isMed ? '💊' : '🛒'} ${c['name']}',
                                    style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 12.5),
                                  ),
                                ),
                                IconButton(
                                  visualDensity: VisualDensity.compact,
                                  icon: const Icon(Icons.delete_outline, color: Colors.red, size: 18),
                                  onPressed: () => setState(() => _cart.removeAt(idx)),
                                ),
                              ],
                            ),
                            Row(
                              children: [
                                if (isMed)
                                  DropdownButton<String>(
                                    value: unitMode,
                                    isDense: true,
                                    items: [
                                      const DropdownMenuItem(value: 'piece', child: Text('পিস', style: TextStyle(fontSize: 11.5))),
                                      DropdownMenuItem(value: 'strip', child: Text('পাতা (${c['strip_size'] ?? 10})', style: const TextStyle(fontSize: 11.5))),
                                      DropdownMenuItem(value: 'packet', child: Text('প্যাকেট (${c['packet_size'] ?? 30})', style: const TextStyle(fontSize: 11.5))),
                                    ],
                                    onChanged: (v) {
                                      if (v != null) _changeCartUnit(idx, v);
                                    },
                                  ),
                                const Spacer(),
                                IconButton(
                                  visualDensity: VisualDensity.compact,
                                  icon: const Icon(Icons.remove_circle_outline, size: 18),
                                  onPressed: () {
                                    setState(() {
                                      if (qty <= 1) {
                                        _cart.removeAt(idx);
                                      } else {
                                        c['quantity'] = qty - 1;
                                      }
                                    });
                                  },
                                ),
                                Text('$qty', style: const TextStyle(fontWeight: FontWeight.bold)),
                                IconButton(
                                  visualDensity: VisualDensity.compact,
                                  icon: const Icon(Icons.add_circle_outline, size: 18),
                                  onPressed: () => setState(() => c['quantity'] = qty + 1),
                                ),
                                const SizedBox(width: 6),
                                Text('৳${(up * qty).toStringAsFixed(0)}', style: const TextStyle(fontWeight: FontWeight.bold, color: Colors.teal)),
                              ],
                            ),
                          ],
                        ),
                      ),
                    );
                  }),

                const SizedBox(height: 8),
                Row(
                  children: [
                    Expanded(
                      flex: 2,
                      child: TextField(
                        controller: _deliveryCtrl,
                        keyboardType: TextInputType.number,
                        onChanged: (_) => setState(() {}),
                        decoration: const InputDecoration(
                          labelText: 'ডেলিভারি চার্জ (৳)',
                          isDense: true,
                          border: OutlineInputBorder(),
                        ),
                      ),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      flex: 3,
                      child: TextField(
                        controller: _notesCtrl,
                        decoration: const InputDecoration(
                          labelText: 'ফার্মাসিস্ট/রাইডার নোট',
                          isDense: true,
                          border: OutlineInputBorder(),
                        ),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 12),

                ElevatedButton.icon(
                  onPressed: _submitting ? null : _submitQuote,
                  icon: _submitting
                      ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white))
                      : const Icon(Icons.send_rounded, color: Colors.white),
                  label: Text(
                    _submitting
                        ? 'পাঠানো হচ্ছে...'
                        : 'কাস্টমার কনফার্মেশনের জন্য বিল পাঠান • ৳${_grandTotal.toStringAsFixed(0)}',
                    style: const TextStyle(fontWeight: FontWeight.bold, color: Colors.white),
                  ),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: Colors.teal.shade800,
                    padding: const EdgeInsets.symmetric(vertical: 13),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
