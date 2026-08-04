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

    for (var o in orders) {
      if (o.orderStatus == 'new' && !_notifiedOrderIds.contains(o.id)) {
        _notifiedOrderIds.add(o.id);
        _showNewOrderAlertModal(o);
        break;
      }
    }

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
        title: Row(
          children: const [
            Icon(Icons.notifications_active, color: Colors.orange, size: 28),
            SizedBox(width: 8),
            Expanded(
              child: Text(
                "🔔 নতুন অনলাইন অর্ডার এসেছে!",
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
                  Text("📦 অর্ডার নম্বর: ${order.orderNumber}", style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16, color: Colors.blue)),
                  const SizedBox(height: 4),
                  Text("👤 কাস্টমার: ${order.customerName}", style: const TextStyle(fontWeight: FontWeight.bold)),
                  Text("📞 ফোন: ${order.customerPhone}", style: const TextStyle(color: Colors.blue)),
                  Text("📍 ঠিকানা: ${order.addressDetails}, ${order.area}"),
                  const Divider(),
                  Text("💵 ক্যাশ কালেকশন: ৳${order.totalAmount.toStringAsFixed(0)}", style: const TextStyle(fontWeight: FontWeight.bold, color: Colors.green, fontSize: 15)),
                ],
              ),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(alertCtx),
            child: const Text("এখন নয়", style: TextStyle(color: Colors.grey)),
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
            Text("গ্রাহক: ${order.customerName}"),
            Text("ফোন: ${order.customerPhone}"),
            const SizedBox(height: 12),
            const Text("কাস্টমার অ্যাপের ভেতরে থাকা OTP টি সংগ্রহ করে লিখুন:"),
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
            child: const Text("বাতিল"),
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
            child: const Text("ওটিপি ভেরিফাই ও ডেলিভারি সম্পন্ন"),
          ),
        ],
      ),
    );
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
            onPressed: () {
              Navigator.pushReplacement(
                context,
                MaterialPageRoute(builder: (_) => const LoginScreen()),
              );
            },
          )
        ],
      ),
      body: _isLoading
          ? const Center(child: CircularProgressIndicator())
          : _deliveryOrders.isEmpty
              ? const Center(child: Text("ডেলিভারির জন্য কোনো সক্রিয় অর্ডার নেই"))
              : RefreshIndicator(
                  onRefresh: () async => _loadDeliveryOrders(),
                  child: ListView.builder(
                    padding: const EdgeInsets.all(12),
                    itemCount: _deliveryOrders.length,
                    itemBuilder: (context, index) {
                      final order = _deliveryOrders[index];

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
                                  Text(order.orderNumber, style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
                                  Container(
                                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                                    decoration: BoxDecoration(
                                      color: order.orderStatus == 'new' ? Colors.purple : Colors.blue,
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

                              Text("👤 কাস্টমার: ${order.customerName}", style: const TextStyle(fontWeight: FontWeight.bold)),
                              Text("📞 ফোন: ${order.customerPhone}", style: const TextStyle(color: Colors.blue, fontWeight: FontWeight.bold)),
                              const SizedBox(height: 4),
                              Text("📍 এলাকা: ${order.area}, ${order.district}"),
                              Text("🏠 ঠিকানা: ${order.addressDetails}", style: const TextStyle(color: Colors.grey)),
                              const SizedBox(height: 8),

                              Wrap(
                                alignment: WrapAlignment.spaceBetween,
                                crossAxisAlignment: WrapCrossAlignment.center,
                                spacing: 8,
                                runSpacing: 8,
                                children: [
                                  Text("ক্যাশ কালেকশন: ৳${order.totalAmount.toStringAsFixed(0)}", style: const TextStyle(fontWeight: FontWeight.bold, color: Colors.green)),
                                  Row(
                                    mainAxisSize: MainAxisSize.min,
                                    children: [
                                      ElevatedButton.icon(
                                        onPressed: () => _acceptOrder(order),
                                        icon: const Icon(Icons.check_circle, size: 15),
                                        label: const Text("Accept"),
                                        style: ElevatedButton.styleFrom(backgroundColor: Colors.blue, padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6)),
                                      ),
                                      const SizedBox(width: 6),
                                      ElevatedButton.icon(
                                        onPressed: () => _showOtpDialog(order),
                                        icon: const Icon(Icons.key, size: 15),
                                        label: const Text("OTP"),
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
