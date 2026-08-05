import 'dart:async';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../../models/online_order.dart';
import '../../services/api_service.dart';
import '../auth/login_screen.dart';

class DeliveryHomeScreen extends StatefulWidget {
  const DeliveryHomeScreen({Key? key}) : super(key: key);

  @override
  State<DeliveryHomeScreen> createState() => _DeliveryHomeScreenState();
}

class _DeliveryHomeScreenState extends State<DeliveryHomeScreen> {
  List<OnlineOrder> _deliveryOrders = [];
  bool _isLoading = true;
  Timer? _refreshTimer;
  String _riderName = 'Delivery Rider';
  String _riderPhone = '';
  final Set<int> _notifiedOrderIds = {};

  @override
  void initState() {
    super.initState();
    _loadRiderPrefs();
    _loadDeliveryOrders();
    _refreshTimer = Timer.periodic(const Duration(seconds: 4), (_) => _loadDeliveryOrders());
  }

  @override
  void dispose() {
    _refreshTimer?.cancel();
    super.dispose();
  }

  void _loadRiderPrefs() async {
    final prefs = await SharedPreferences.getInstance();
    if (!mounted) return;
    setState(() {
      _riderName = prefs.getString('user_name') ?? 'Delivery Rider';
      _riderPhone = prefs.getString('user_phone') ?? '';
    });
  }

  void _loadDeliveryOrders() async {
    List<OnlineOrder> orders = await ApiService.fetchDeliveryOrders();
    if (!mounted) return;

    setState(() {
      _deliveryOrders = orders;
      _isLoading = false;
    });
  }

  void _showNewOrderAlertModal(OnlineOrder order) {
    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (alertCtx) => AlertDialog(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        title: const Row(
          children: [
            Icon(Icons.notifications_active, color: Colors.orange, size: 28),
            SizedBox(width: 8),
            Expanded(
              child: Text(
                "🔔 New Online Order Received!",
                style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: Colors.deepOrange),
              ),
            ),
          ],
        ),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              padding: const EdgeInsets.all(10),
              decoration: BoxDecoration(
                color: Colors.orange.shade50,
                borderRadius: BorderRadius.circular(8),
                border: Border.all(color: Colors.orange.shade200),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text("📦 Order #${order.orderNumber}", style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16, color: Colors.blue)),
                  const SizedBox(height: 4),
                  Text("👤 Customer: ${order.customerName}", style: const TextStyle(fontWeight: FontWeight.bold)),
                  Text("📞 Phone: ${order.customerPhone}", style: const TextStyle(color: Colors.blue)),
                  Text("📍 Address: ${order.addressDetails}, ${order.area}"),
                  const Divider(),
                  Text("💵 Cash Collection: ৳${order.totalAmount.toStringAsFixed(0)}", style: const TextStyle(fontWeight: FontWeight.bold, color: Colors.green, fontSize: 15)),
                ],
              ),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(alertCtx),
            child: const Text("Not Now", style: TextStyle(color: Colors.grey)),
          ),
          ElevatedButton.icon(
            onPressed: () {
              Navigator.pop(alertCtx);
              _acceptOrder(order);
            },
            icon: const Icon(Icons.delivery_dining, color: Colors.white),
            label: const Text("🚀 ACCEPT DELIVERY", style: TextStyle(fontWeight: FontWeight.bold, color: Colors.white)),
            style: ElevatedButton.styleFrom(backgroundColor: Colors.green, padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8)),
          ),
        ],
      ),
    );
  }

  void _acceptOrder(OnlineOrder order) async {
    var res = await ApiService.acceptRiderOrder(
      orderId: order.id,
      riderName: _riderName,
      riderPhone: _riderPhone,
    );
    if (!mounted) return;
    if (res['success'] == true) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(res['message'] ?? 'Delivery accepted!'), backgroundColor: Colors.green),
      );
      _loadDeliveryOrders();
    } else {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(res['message'] ?? 'Failed to accept delivery'), backgroundColor: Colors.red),
      );
    }
  }

  void _showOtpDialog(OnlineOrder order) {
    final TextEditingController otpController = TextEditingController();

    showDialog(
      context: context,
      builder: (dialogCtx) => AlertDialog(
        title: Row(
          children: [
            const Icon(Icons.verified_user, color: Colors.green),
            const SizedBox(width: 8),
            Text("Order #${order.orderNumber}"),
          ],
        ),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text("Customer: ${order.customerName}"),
            Text("Phone: ${order.customerPhone}"),
            const SizedBox(height: 12),
            const Text("Enter OTP provided by the customer:"),
            const SizedBox(height: 8),
            TextField(
              controller: otpController,
              keyboardType: TextInputType.number,
              maxLength: 4,
              style: const TextStyle(fontSize: 22, fontWeight: FontWeight.bold, letterSpacing: 4),
              textAlign: TextAlign.center,
              decoration: const InputDecoration(
                hintText: "____",
                border: OutlineInputBorder(),
              ),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogCtx),
            child: const Text("Cancel"),
          ),
          ElevatedButton(
            onPressed: () async {
              String otp = otpController.text.trim();
              if (otp.isEmpty) return;

              var res = await ApiService.verifyDeliveryOtp(order.orderNumber, otp);

              if (!dialogCtx.mounted) return;
              Navigator.pop(dialogCtx);

              if (!mounted) return;
              if (res['success'] == true) {
                ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(content: Text(res['message'] ?? 'Delivered successfully')),
                );
                _loadDeliveryOrders();
              } else {
                ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(content: Text(res['message'] ?? 'Invalid OTP'), backgroundColor: Colors.red),
                );
              }
            },
            style: ElevatedButton.styleFrom(backgroundColor: Colors.green),
            child: const Text("Verify OTP & Complete Delivery"),
          ),
        ],
      ),
    );
  }

  void _updateRiderStatus(OnlineOrder order, String nextStatus) async {
    var res = await ApiService.updateRiderOrderStatus(
      orderId: order.id,
      status: nextStatus,
    );
    if (!mounted) return;
    if (res['success'] == true) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(res['message'] ?? 'Order status updated'), backgroundColor: Colors.green),
      );
      _loadDeliveryOrders();
    } else {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(res['message'] ?? 'Failed to update status'), backgroundColor: Colors.red),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      appBar: AppBar(
        title: const Text("🚴 Delivery Rider Mode"),
        backgroundColor: Colors.orange,
        actions: [
          IconButton(
            icon: const Icon(Icons.refresh),
            onPressed: _loadDeliveryOrders,
          ),
          IconButton(
            icon: const Icon(Icons.logout),
            tooltip: "Log Out",
            onPressed: () async {
              _refreshTimer?.cancel();
              final prefs = await SharedPreferences.getInstance();
              await prefs.remove('user_phone');
              await prefs.remove('user_name');
              await prefs.remove('is_delivery_man');
              await prefs.setBool('stay_signed_in', false);
              if (!mounted) return;
              Navigator.pushAndRemoveUntil(
                context,
                MaterialPageRoute(builder: (_) => const LoginScreen()),
                (route) => false,
              );
            },
          )
        ],
      ),
      body: _isLoading
          ? const Center(child: CircularProgressIndicator())
          : _deliveryOrders.isEmpty
              ? const Center(child: Text("No active orders for delivery"))
              : RefreshIndicator(
                  onRefresh: () async => _loadDeliveryOrders(),
                  child: ListView.builder(
                    padding: const EdgeInsets.all(12),
                    itemCount: _deliveryOrders.length,
                    itemBuilder: (context, index) {
                      final order = _deliveryOrders[index];
                      String timeStr = order.createdAt.isNotEmpty
                          ? order.createdAt.substring(0, 16).replaceFirst('T', ' ')
                          : '—';

                      return Card(
                        margin: const EdgeInsets.only(bottom: 12),
                        elevation: 3,
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                        child: Padding(
                          padding: const EdgeInsets.all(16.0),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              Row(
                                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                children: [
                                  Column(
                                    crossAxisAlignment: CrossAxisAlignment.start,
                                    children: [
                                      Text("📦 Order #${order.orderNumber}", style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
                                      const SizedBox(height: 2),
                                      Text("📅 Time: $timeStr", style: const TextStyle(fontSize: 12, color: Colors.grey, fontWeight: FontWeight.w600)),
                                    ],
                                  ),
                                  Container(
                                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                                    decoration: BoxDecoration(
                                      color: order.orderStatus == 'new'
                                          ? Colors.purple
                                          : (order.orderStatus == 'verified'
                                              ? Colors.blue
                                              : (order.orderStatus == 'packed' ? Colors.orange : Colors.teal)),
                                      borderRadius: BorderRadius.circular(8),
                                    ),
                                    child: Text(
                                      order.orderStatus.toUpperCase(),
                                      style: const TextStyle(color: Colors.white, fontSize: 11, fontWeight: FontWeight.bold),
                                    ),
                                  ),
                                ],
                              ),
                              const Divider(),

                              Text("👤 Customer: ${order.customerName}", style: const TextStyle(fontWeight: FontWeight.bold)),
                              Text("📞 Phone: ${order.customerPhone}", style: const TextStyle(color: Colors.blue, fontWeight: FontWeight.bold)),
                              const SizedBox(height: 4),
                              Text("📍 Area: ${order.area}, ${order.district}"),
                              Text("🏠 Address: ${order.addressDetails}", style: const TextStyle(color: Colors.grey)),
                              const SizedBox(height: 8),

                              Wrap(
                                alignment: WrapAlignment.spaceBetween,
                                crossAxisAlignment: WrapCrossAlignment.center,
                                spacing: 8,
                                runSpacing: 8,
                                children: [
                                  Text("Cash Collection: ৳${order.totalAmount.toStringAsFixed(0)}", style: const TextStyle(fontWeight: FontWeight.bold, color: Colors.green)),
                                  Row(
                                    mainAxisSize: MainAxisSize.min,
                                    children: [
                                      if (order.orderStatus == 'new')
                                        ElevatedButton.icon(
                                          onPressed: () => _acceptOrder(order),
                                          icon: const Icon(Icons.check_circle, size: 15),
                                          label: const Text("Accept Delivery"),
                                          style: ElevatedButton.styleFrom(backgroundColor: Colors.blue, padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6)),
                                        )
                                      else if (order.orderStatus == 'verified')
                                        ElevatedButton.icon(
                                          onPressed: () => _updateRiderStatus(order, 'packed'),
                                          icon: const Icon(Icons.inventory_2, size: 15),
                                          label: const Text("Mark Packed"),
                                          style: ElevatedButton.styleFrom(backgroundColor: Colors.orange, padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6)),
                                        )
                                      else if (order.orderStatus == 'packed')
                                        ElevatedButton.icon(
                                          onPressed: () => _updateRiderStatus(order, 'on_the_way'),
                                          icon: const Icon(Icons.directions_bike, size: 15),
                                          label: const Text("Send On The Way"),
                                          style: ElevatedButton.styleFrom(backgroundColor: Colors.cyan.shade700, padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6)),
                                        )
                                      else if (order.orderStatus == 'on_the_way')
                                        ElevatedButton.icon(
                                          onPressed: () => _showOtpDialog(order),
                                          icon: const Icon(Icons.key, size: 15),
                                          label: const Text("Verify OTP & Deliver"),
                                          style: ElevatedButton.styleFrom(backgroundColor: Colors.green, padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6)),
                                        ),
                                    ],
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
    );
  }
}
