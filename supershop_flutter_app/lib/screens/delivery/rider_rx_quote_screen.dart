import 'package:flutter/material.dart';
import '../../services/api_service.dart';
import '../../widgets/rx_quote_builder_sheet.dart';

/// Dedicated screen for Riders with Admin-granted `can_rx_quote_bill` permission
/// to inspect Pharmacy prescriptions, scan barcodes / add items, and send quotations.
class RiderRxQuoteScreen extends StatefulWidget {
  final String riderPhone;

  const RiderRxQuoteScreen({super.key, required this.riderPhone});

  @override
  State<RiderRxQuoteScreen> createState() => _RiderRxQuoteScreenState();
}

class _RiderRxQuoteScreenState extends State<RiderRxQuoteScreen> {
  bool _loading = true;
  String _errorMsg = '';
  List<Map<String, dynamic>> _orders = [];

  @override
  void initState() {
    super.initState();
    _loadOrders();
  }

  Future<void> _loadOrders() async {
    if (mounted) setState(() => _loading = true);
    final res = await ApiService.fetchRiderRxQuoteOrders(riderPhone: widget.riderPhone);
    if (!mounted) return;
    setState(() {
      _loading = false;
      if (res['success'] == true) {
        _errorMsg = '';
        _orders = (res['orders'] as List? ?? [])
            .whereType<Map>()
            .map((e) => Map<String, dynamic>.from(e))
            .toList();
      } else {
        _errorMsg = (res['message'] ?? 'প্রেসক্রিপশন লোড করা যায়নি।').toString();
        _orders = [];
      }
    });
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        backgroundColor: Colors.teal.shade800,
        foregroundColor: Colors.white,
        title: const Text('🔬 Rx প্রেসক্রিপশন কোটেশন', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
        actions: [
          IconButton(icon: const Icon(Icons.refresh), onPressed: _loadOrders),
        ],
      ),
      body: RefreshIndicator(
        onRefresh: _loadOrders,
        child: _loading
            ? const Center(child: CircularProgressIndicator())
            : _errorMsg.isNotEmpty
                ? ListView(
                    padding: const EdgeInsets.all(24),
                    children: [
                      const SizedBox(height: 60),
                      const Icon(Icons.lock_outline, size: 54, color: Colors.orange),
                      const SizedBox(height: 12),
                      Text(
                        _errorMsg,
                        textAlign: TextAlign.center,
                        style: const TextStyle(fontSize: 14, fontWeight: FontWeight.bold),
                      ),
                    ],
                  )
                : _orders.isEmpty
                    ? ListView(
                        padding: const EdgeInsets.all(24),
                        children: const [
                          SizedBox(height: 80),
                          Icon(Icons.medical_information_outlined, size: 54, color: Colors.grey),
                          SizedBox(height: 10),
                          Center(child: Text('বর্তমানে কোনো পেন্ডিং Rx অর্ডার নেই।', style: TextStyle(color: Colors.grey))),
                        ],
                      )
                    : ListView.builder(
                        padding: const EdgeInsets.all(12),
                        itemCount: _orders.length,
                        itemBuilder: (_, idx) {
                          final o = _orders[idx];
                          final String st = (o['order_status'] ?? 'pending').toString();
                          final bool awaiting = st == 'awaiting_customer_confirmation';
                          final bool confirmed = st == 'confirmed';
                          return Card(
                            margin: const EdgeInsets.only(bottom: 10),
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(12),
                              side: BorderSide(
                                color: awaiting
                                    ? Colors.amber.shade400
                                    : (confirmed ? Colors.green.shade400 : Colors.teal.shade200),
                              ),
                            ),
                            child: Padding(
                              padding: const EdgeInsets.all(12),
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Row(
                                    children: [
                                      Expanded(
                                        child: Text(
                                          '💊 Order #${o['order_number'] ?? ''}',
                                          style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 14.5),
                                        ),
                                      ),
                                      Container(
                                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                                        decoration: BoxDecoration(
                                          color: awaiting
                                              ? Colors.amber.shade700
                                              : (confirmed ? Colors.green.shade700 : Colors.indigo.shade600),
                                          borderRadius: BorderRadius.circular(6),
                                        ),
                                        child: Text(
                                          awaiting ? '⏳ কাস্টমার কনফার্ম বাকি' : st.toUpperCase(),
                                          style: const TextStyle(color: Colors.white, fontSize: 10, fontWeight: FontWeight.bold),
                                        ),
                                      ),
                                    ],
                                  ),
                                  const SizedBox(height: 4),
                                  Text('👤 ${o['customer_name'] ?? ''} • 📞 ${o['customer_phone'] ?? ''}'),
                                  Text('📍 ${o['delivery_address'] ?? ''}', style: const TextStyle(fontSize: 12, color: Colors.black54)),
                                  if ((o['customer_notes'] ?? '').toString().isNotEmpty)
                                    Padding(
                                      padding: const EdgeInsets.only(top: 4),
                                      child: Text('📝 ${o['customer_notes']}', style: TextStyle(fontSize: 12, color: Colors.green.shade900)),
                                    ),
                                  const SizedBox(height: 8),
                                  SizedBox(
                                    width: double.infinity,
                                    child: ElevatedButton.icon(
                                      onPressed: () async {
                                        final sent = await RxQuoteBuilderSheet.open(
                                          context,
                                          order: o,
                                          isAdmin: false,
                                          riderPhone: widget.riderPhone,
                                        );
                                        if (sent == true) _loadOrders();
                                      },
                                      icon: const Icon(Icons.qr_code_scanner, size: 18),
                                      label: const Text(
                                        'প্রেসক্রিপশন দেখুন • স্ক্যান / বিল তৈরি করুন',
                                        style: TextStyle(fontWeight: FontWeight.bold),
                                      ),
                                      style: ElevatedButton.styleFrom(
                                        backgroundColor: Colors.teal.shade700,
                                        foregroundColor: Colors.white,
                                      ),
                                    ),
                                  ),
                                ],
                              ),
                            ),
                          );
                        },
                      ),
      ),
    );
  }
}
