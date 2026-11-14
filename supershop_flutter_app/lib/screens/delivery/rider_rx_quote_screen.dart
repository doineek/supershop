import 'package:flutter/material.dart';
import '../../services/api_service.dart';
import '../../widgets/rx_quote_builder_sheet.dart';
import '../../widgets/thermal_print_helper.dart';

/// Dedicated screen for Riders with Admin-granted `can_rx_quote_bill` permission
/// to inspect Pharmacy prescriptions, search/scan medicines, prepare quotes,
/// print receipts, and update Rx order status just like Admin.
class RiderRxQuoteScreen extends StatefulWidget {
  final String riderPhone;

  const RiderRxQuoteScreen({super.key, required this.riderPhone});

  @override
  State<RiderRxQuoteScreen> createState() => _RiderRxQuoteScreenState();
}

class _RiderRxQuoteScreenState extends State<RiderRxQuoteScreen> {
  bool _loading = true;
  String _errorMsg = '';
  String _statusFilter = '';
  List<Map<String, dynamic>> _orders = [];

  @override
  void initState() {
    super.initState();
    _loadOrders();
  }

  Future<void> _loadOrders() async {
    if (mounted) setState(() => _loading = true);
    final res = await ApiService.fetchRiderRxQuoteOrders(
      riderPhone: widget.riderPhone,
      status: _statusFilter,
    );
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

  Future<void> _openRiderStatusDialog(Map<String, dynamic> order) async {
    final int orderId = ((order['id'] ?? 0) as num).toInt();
    final updated = await RxQuoteBuilderSheet.showStatusUpdateDialog(
      context,
      orderId: orderId,
      orderNumber: (order['order_number'] ?? '').toString(),
      currentStatus: (order['order_status'] ?? 'pending').toString(),
      customerConfirmed: order['customer_confirmed'] == true,
      isAdmin: false,
      riderPhone: widget.riderPhone,
    );
    if (updated) _loadOrders();
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        backgroundColor: Colors.teal.shade800,
        foregroundColor: Colors.white,
        title: const Text('🔬 Rx প্রেসক্রিপশন ও বিল প্যানেল', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold)),
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
                : ListView(
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
                              {'k': 'packed', 'label': 'Packed'},
                              {'k': 'on_the_way', 'label': 'On The Way'},
                            ])
                              Padding(
                                padding: const EdgeInsets.only(right: 6),
                                child: ChoiceChip(
                                  label: Text(pair['label']!, style: const TextStyle(fontSize: 11.5)),
                                  selected: _statusFilter == pair['k'],
                                  onSelected: (_) {
                                    setState(() => _statusFilter = pair['k']!);
                                    _loadOrders();
                                  },
                                ),
                              ),
                          ],
                        ),
                      ),
                      const SizedBox(height: 8),
                      if (_orders.isEmpty)
                        const Padding(
                          padding: EdgeInsets.symmetric(vertical: 64),
                          child: Column(
                            children: [
                              Icon(Icons.medical_information_outlined, size: 54, color: Colors.grey),
                              SizedBox(height: 10),
                              Text('এই ফিল্টারে কোনো Rx অর্ডার নেই।', style: TextStyle(color: Colors.grey)),
                            ],
                          ),
                        )
                      else
                        ..._orders.map((o) {
                          final String st = (o['order_status'] ?? 'pending').toString();
                          final bool awaiting = st == 'awaiting_customer_confirmation';
                          final bool confirmed = st == 'confirmed';
                          final double total = ((o['total_amount'] ?? 0) as num).toDouble();
                          final int orderId = ((o['id'] ?? 0) as num).toInt();

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
                                          final sent = await RxQuoteBuilderSheet.open(
                                            context,
                                            order: o,
                                            isAdmin: false,
                                            riderPhone: widget.riderPhone,
                                          );
                                          if (sent == true) _loadOrders();
                                        },
                                        icon: const Icon(Icons.edit_note, size: 16),
                                        label: const Text('Rx ও বিল তৈরি', style: TextStyle(fontSize: 11.5, fontWeight: FontWeight.bold)),
                                        style: ElevatedButton.styleFrom(
                                          backgroundColor: Colors.teal.shade700,
                                          foregroundColor: Colors.white,
                                        ),
                                      ),
                                      OutlinedButton.icon(
                                        onPressed: () => _openRiderStatusDialog(o),
                                        icon: const Icon(Icons.sync_alt, size: 15),
                                        label: const Text('স্ট্যাটাস আপডেট', style: TextStyle(fontSize: 11.5)),
                                      ),
                                      OutlinedButton.icon(
                                        onPressed: () => ThermalPrintHelper.printAndConfirm(
                                          context,
                                          riderPhone: widget.riderPhone,
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
                    ],
                  ),
      ),
    );
  }
}
