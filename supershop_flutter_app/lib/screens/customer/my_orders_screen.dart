import 'dart:async';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../../localization/app_localizations.dart';
import '../../models/online_order.dart';
import '../../services/api_service.dart';

class MyOrdersScreen extends StatefulWidget {
  const MyOrdersScreen({Key? key}) : super(key: key);

  @override
  State<MyOrdersScreen> createState() => _MyOrdersScreenState();
}

class _MyOrdersScreenState extends State<MyOrdersScreen> {
  String _userPhone = '';
  bool _isLoadingPhone = true;
  Timer? _countdownTimer;

  @override
  void initState() {
    super.initState();
    _loadUserPhone();
    _countdownTimer = Timer.periodic(const Duration(seconds: 1), (_) {
      if (mounted) {
        setState(() {});
      }
    });
  }

  @override
  void dispose() {
    _countdownTimer?.cancel();
    super.dispose();
  }

  void _loadUserPhone() async {
    final prefs = await SharedPreferences.getInstance();
    if (!mounted) return;
    setState(() {
      _userPhone = prefs.getString('user_phone') ?? '';
      _isLoadingPhone = false;
    });
  }

  Color _getStatusColor(String status) {
    switch (status) {
      case 'new':
      case 'pending':
        return Colors.blue;
      case 'verified':
        return Colors.purple;
      case 'packed':
        return Colors.orange;
      case 'on_the_way':
        return Colors.cyan;
      case 'delivered':
        return Colors.green;
      default:
        return Colors.red;
    }
  }

  String _getStatusText(String status) {
    switch (status) {
      case 'new':
      case 'pending':
        return 'অপেক্ষমান (Pending)';
      case 'verified':
        return 'যাচাইকৃত (Verified)';
      case 'packed':
        return 'প্যাকড (Packed)';
      case 'on_the_way':
        return 'রাস্তায় (On the way)';
      case 'delivered':
        return 'ডেলিভারি সম্পন্ন (Delivered)';
      default:
        return 'বাতিল (Cancelled)';
    }
  }

  String _formatSeconds(int totalSec) {
    if (totalSec <= 0) return '00:00';
    int mins = totalSec ~/ 60;
    int secs = totalSec % 60;
    return '${mins.toString().padLeft(2, '0')}:${secs.toString().padLeft(2, '0')}';
  }

  void _confirmCancelOrder(String orderNumber) {
    final messenger = ScaffoldMessenger.of(context);

    showDialog(
      context: context,
      builder: (dialogCtx) => AlertDialog(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        title: const Row(
          children: [
            Icon(Icons.warning, color: Colors.red),
            SizedBox(width: 8),
            Text("অর্ডার বাতিলের নিশ্চিতকরণ"),
          ],
        ),
        content: Text("আপনি কি নিশ্চিত যে অর্ডার #$orderNumber বাতিল করতে চান?"),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogCtx),
            child: const Text("না"),
          ),
          ElevatedButton(
            onPressed: () async {
              final nav = Navigator.of(dialogCtx);
              var res = await ApiService.cancelOrder(
                orderNumber: orderNumber,
                phone: _userPhone,
              );

              nav.pop();
              if (res['success'] == true) {
                messenger.showSnackBar(
                  SnackBar(
                    content: Text(res['message'] ?? "অর্ডারটি সফলভাবে বাতিল করা হয়েছে।"),
                    backgroundColor: Colors.green,
                  ),
                );
              } else {
                messenger.showSnackBar(
                  SnackBar(
                    content: Text(res['message'] ?? "বাতিল করা সম্ভব হয়নি"),
                    backgroundColor: Colors.red,
                  ),
                );
              }
            },
            style: ElevatedButton.styleFrom(backgroundColor: Colors.red),
            child: const Text("হ্যাঁ, বাতিল করুন", style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
          ),
        ],
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final loc = AppLocalizations.of(context);

    return Scaffold(
      appBar: AppBar(
        title: Text(loc.translate('my_orders')),
        backgroundColor: Colors.green,
      ),
      body: _isLoadingPhone
          ? const Center(child: CircularProgressIndicator())
          : _userPhone.isEmpty
              ? const Center(child: Text("লগইন ফোন নম্বর পাওয়া যায়নি"))
              : StreamBuilder<List<OnlineOrder>>(
                  stream: ApiService.myOrdersStream(_userPhone),
                  builder: (context, snapshot) {
                    if (snapshot.connectionState == ConnectionState.waiting && !snapshot.hasData) {
                      return const Center(child: CircularProgressIndicator());
                    }

                    final orders = snapshot.data ?? [];

                    if (orders.isEmpty) {
                      return const Center(child: Text("আপনার কোনো পূর্ববর্তী অর্ডার নেই"));
                    }

                    return ListView.builder(
                      padding: const EdgeInsets.all(12),
                      itemCount: orders.length,
                      itemBuilder: (context, index) {
                        final order = orders[index];
                        Color statusColor = _getStatusColor(order.orderStatus);

                        DateTime createdDt = DateTime.tryParse(order.createdAt) ?? DateTime.now();
                        int elapsedSeconds = DateTime.now().difference(createdDt).inSeconds;
                        int remainingSeconds = 600 - elapsedSeconds;
                        bool canCancel = remainingSeconds > 0 &&
                            (order.orderStatus == 'new' || order.orderStatus == 'pending' || order.orderStatus == 'verified');

                        return Card(
                          margin: const EdgeInsets.only(bottom: 12),
                          elevation: 3,
                          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                          child: Padding(
                            padding: const EdgeInsets.all(16.0),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                // Order Header & Status Badge
                                Row(
                                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                  children: [
                                    Text(
                                      order.orderNumber,
                                      style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16),
                                    ),
                                    Container(
                                      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                                      decoration: BoxDecoration(
                                        color: statusColor,
                                        borderRadius: BorderRadius.circular(12),
                                      ),
                                      child: Text(
                                        _getStatusText(order.orderStatus),
                                        style: const TextStyle(color: Colors.white, fontSize: 12, fontWeight: FontWeight.bold),
                                      ),
                                    ),
                                  ],
                                ),
                                const SizedBox(height: 6),
                                Text(
                                  'তারিখ: ${order.createdAt.length >= 19 ? order.createdAt.substring(0, 19).replaceAll('T', ' ') : order.createdAt}',
                                  style: const TextStyle(color: Colors.grey, fontSize: 12),
                                ),
                                const Divider(),

                                // Order Items
                                Column(
                                  children: order.items.map((item) {
                                    return Padding(
                                      padding: const EdgeInsets.symmetric(vertical: 2.0),
                                      child: Row(
                                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                        children: [
                                          Text('${item.productName} × ${item.quantity}'),
                                          Text('৳${item.totalPrice.toStringAsFixed(0)}'),
                                        ],
                                      ),
                                    );
                                  }).toList(),
                                ),
                                const Divider(),

                                Row(
                                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                  children: [
                                    const Text("মোট পরিশোধযোগ্য:", style: TextStyle(fontWeight: FontWeight.bold)),
                                    Text(
                                      '৳${order.totalAmount.toStringAsFixed(2)}',
                                      style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16, color: Colors.green),
                                    ),
                                  ],
                                ),
                                const SizedBox(height: 12),

                                // 10-Minute Live Cancel Timer Box / Cancellation Closed Notice
                                if (order.orderStatus != 'delivered' && order.orderStatus != 'cancelled')
                                  Column(
                                    children: [
                                      if (canCancel)
                                        Container(
                                          padding: const EdgeInsets.all(10),
                                          decoration: BoxDecoration(
                                            color: Colors.orange.shade50,
                                            borderRadius: BorderRadius.circular(8),
                                            border: Border.all(color: Colors.orange.shade300),
                                          ),
                                          child: Row(
                                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                            children: [
                                              Row(
                                                children: [
                                                  const Icon(Icons.timer, color: Colors.orange, size: 20),
                                                  const SizedBox(width: 6),
                                                  Text(
                                                    'বাতিল বাকী: ${_formatSeconds(remainingSeconds)}',
                                                    style: const TextStyle(fontWeight: FontWeight.bold, color: Colors.orange, fontSize: 12),
                                                  ),
                                                ],
                                              ),
                                              ElevatedButton.icon(
                                                onPressed: () => _confirmCancelOrder(order.orderNumber),
                                                icon: const Icon(Icons.cancel, size: 16, color: Colors.white),
                                                label: const Text('বাতিল করুন', style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 12)),
                                                style: ElevatedButton.styleFrom(backgroundColor: Colors.red, padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6)),
                                              ),
                                            ],
                                          ),
                                        )
                                      else
                                        Container(
                                          width: double.infinity,
                                          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                                          decoration: BoxDecoration(
                                            color: Colors.grey.shade100,
                                            borderRadius: BorderRadius.circular(8),
                                            border: Border.all(color: Colors.grey.shade300),
                                          ),
                                          child: const Row(
                                            mainAxisAlignment: MainAxisAlignment.center,
                                            children: [
                                              Icon(Icons.lock_clock, color: Colors.grey, size: 16),
                                              SizedBox(width: 6),
                                              Text(
                                                'অর্ডার বাতিলের সময় পার হয়ে গেছে (১০ মিনিট অতিক্রান্ত)',
                                                style: TextStyle(color: Colors.grey, fontSize: 11, fontWeight: FontWeight.w600),
                                              ),
                                            ],
                                          ),
                                        ),
                                      const SizedBox(height: 10),
                                    ],
                                  ),

                                // Highlighted Delivery OTP Box
                                if (order.orderStatus != 'delivered' && order.orderStatus != 'cancelled')
                                  Container(
                                    width: double.infinity,
                                    padding: const EdgeInsets.all(12),
                                    decoration: BoxDecoration(
                                      color: Colors.red[50],
                                      borderRadius: BorderRadius.circular(8),
                                      border: Border.all(color: Colors.red.shade300),
                                    ),
                                    child: Column(
                                      children: [
                                        const Row(
                                          mainAxisAlignment: MainAxisAlignment.center,
                                          children: [
                                            Icon(Icons.vpn_key, color: Colors.red, size: 18),
                                            SizedBox(width: 6),
                                            Text(
                                              "আপনার ডেলিভারি ওটিপি (OTP):",
                                              style: TextStyle(fontWeight: FontWeight.bold, color: Colors.red),
                                            ),
                                          ],
                                        ),
                                        const SizedBox(height: 4),
                                        Text(
                                          order.deliveryOtp,
                                          style: const TextStyle(
                                            fontSize: 26,
                                            fontWeight: FontWeight.bold,
                                            color: Colors.red,
                                            letterSpacing: 4,
                                          ),
                                        ),
                                        const SizedBox(height: 4),
                                        Text(
                                          loc.translate('delivery_otp_desc'),
                                          textAlign: TextAlign.center,
                                          style: const TextStyle(fontSize: 11, color: Colors.grey),
                                        ),
                                      ],
                                    ),
                                  ),
                              ],
                            ),
                          ),
                        );
                      },
                    );
                  },
                ),
    );
  }
}
