import 'dart:async';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:url_launcher/url_launcher.dart';
import '../../localization/app_localizations.dart';
import '../../models/online_order.dart';
import '../../services/api_service.dart';
import '../auth/login_screen.dart';
import 'home_screen.dart';

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
        return 'Pending';
      case 'verified':
        return 'Verified';
      case 'packed':
        return 'Packed';
      case 'on_the_way':
        return 'On the way';
      case 'delivered':
        return 'Delivered';
      default:
        return 'Cancelled';
    }
  }

  String _formatSeconds(int totalSec) {
    if (totalSec <= 0) return '00:00';
    int mins = totalSec ~/ 60;
    int secs = totalSec % 60;
    return '${mins.toString().padLeft(2, '0')}:${secs.toString().padLeft(2, '0')}';
  }

  String _formatTimelineTime(String isoStr) {
    if (isoStr.isEmpty) return '';
    try {
      final dt = DateTime.parse(isoStr).toLocal();
      final months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
      final month = months[dt.month - 1];
      final day = dt.day;
      final hour = dt.hour % 12 == 0 ? 12 : dt.hour % 12;
      final min = dt.minute.toString().padLeft(2, '0');
      final ampm = dt.hour >= 12 ? 'PM' : 'AM';
      return '$day $month\n$hour:$min $ampm';
    } catch (_) {
      return isoStr.length >= 16 ? isoStr.substring(5, 16).replaceAll('T', ' ') : isoStr;
    }
  }

  Widget _buildDeliveryTimeline(OnlineOrder order) {
    List<OrderTimelineStep> steps = order.timeline;
    if (steps.isEmpty) {
      final st = order.orderStatus.toLowerCase();
      final isVerified = ['verified', 'packed', 'on_the_way', 'delivered'].contains(st);
      final isPacked = ['packed', 'on_the_way', 'delivered'].contains(st);
      final isOtw = ['on_the_way', 'delivered'].contains(st);
      final isDelivered = (st == 'delivered');
      final isCancelled = (st == 'cancelled');

      if (isCancelled) {
        steps = [
          OrderTimelineStep(stage: 'placed', title: 'Placed', time: order.createdAt, done: true, active: false),
          OrderTimelineStep(stage: 'cancelled', title: 'Cancelled', time: order.cancelledAt, done: true, active: true),
        ];
      } else {
        steps = [
          OrderTimelineStep(stage: 'placed', title: 'Placed', time: order.createdAt, done: true, active: st == 'new' || st == 'pending'),
          OrderTimelineStep(stage: 'verified', title: 'Confirmed', time: order.confirmedAt, done: isVerified, active: st == 'verified'),
          OrderTimelineStep(stage: 'packed', title: 'Packed', time: order.packedAt, done: isPacked, active: st == 'packed'),
          OrderTimelineStep(stage: 'on_the_way', title: 'On Way', time: order.onTheWayAt, done: isOtw, active: st == 'on_the_way'),
          OrderTimelineStep(stage: 'delivered', title: 'Delivered', time: order.deliveredAt, done: isDelivered, active: st == 'delivered'),
        ];
      }
    }

    return Container(
      margin: const EdgeInsets.symmetric(vertical: 10),
      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 10),
      decoration: BoxDecoration(
        color: const Color(0xFFF8FAFC),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: const Color(0xFFE2E8F0)),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            mainAxisAlignment: MainAxisAlignment.spaceBetween,
            children: [
              const Row(
                children: [
                  Icon(Icons.access_time_rounded, size: 14, color: Color(0xFF475569)),
                  SizedBox(width: 4),
                  Text(
                    "DELIVERY TIMELINE",
                    style: TextStyle(
                      fontSize: 10.5,
                      fontWeight: FontWeight.w800,
                      color: Color(0xFF475569),
                      letterSpacing: 0.5,
                    ),
                  ),
                ],
              ),
              Text(
                _getStatusText(order.orderStatus),
                style: TextStyle(
                  fontSize: 10.5,
                  fontWeight: FontWeight.bold,
                  color: _getStatusColor(order.orderStatus),
                ),
              ),
            ],
          ),
          const SizedBox(height: 10),
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            child: IntrinsicWidth(
              child: Row(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: List.generate(steps.length * 2 - 1, (idx) {
                  if (idx.isOdd) {
                    final prevStep = steps[idx ~/ 2];
                    final nextStep = steps[(idx ~/ 2) + 1];
                    final isConnectorDone = prevStep.done && (nextStep.done || nextStep.active);
                    return Container(
                      width: 22,
                      height: 2.5,
                      margin: const EdgeInsets.only(top: 10),
                      color: isConnectorDone ? const Color(0xFF16A34A) : const Color(0xFFCBD5E1),
                    );
                  }

                  final sIdx = idx ~/ 2;
                  final step = steps[sIdx];
                  final isDone = step.done;
                  final isActive = step.active;
                  final isCancelled = step.stage == 'cancelled';

                  Color iconBg = const Color(0xFFE2E8F0);
                  Color iconFg = const Color(0xFF64748B);
                  IconData iconData = Icons.circle;
                  double iconSize = 8;

                  if (isCancelled) {
                    iconBg = Colors.red;
                    iconFg = Colors.white;
                    iconData = Icons.close;
                    iconSize = 12;
                  } else if (isDone) {
                    iconBg = const Color(0xFF16A34A);
                    iconFg = Colors.white;
                    iconData = Icons.check;
                    iconSize = 12;
                  } else if (isActive) {
                    iconBg = const Color(0xFF2563EB);
                    iconFg = Colors.white;
                    iconData = Icons.radio_button_checked;
                    iconSize = 12;
                  }

                  return SizedBox(
                    width: 58,
                    child: Column(
                      children: [
                        Container(
                          width: 22,
                          height: 22,
                          decoration: BoxDecoration(
                            color: iconBg,
                            shape: BoxShape.circle,
                            boxShadow: isActive
                                ? [BoxShadow(color: const Color(0xFF2563EB).withValues(alpha: 0.35), blurRadius: 6, spreadRadius: 1)]
                                : null,
                          ),
                          child: Icon(iconData, size: iconSize, color: iconFg),
                        ),
                        const SizedBox(height: 4),
                        Text(
                          step.title,
                          textAlign: TextAlign.center,
                          maxLines: 1,
                          overflow: TextOverflow.ellipsis,
                          style: TextStyle(
                            fontSize: 9.5,
                            fontWeight: (isDone || isActive) ? FontWeight.bold : FontWeight.normal,
                            color: isDone
                                ? const Color(0xFF16A34A)
                                : (isActive ? const Color(0xFF2563EB) : const Color(0xFF64748B)),
                          ),
                        ),
                        const SizedBox(height: 2),
                        Text(
                          step.time.isNotEmpty ? _formatTimelineTime(step.time) : (isDone ? 'Done' : 'Pending'),
                          textAlign: TextAlign.center,
                          style: const TextStyle(
                            fontSize: 8,
                            color: Color(0xFF64748B),
                            fontWeight: FontWeight.w500,
                            height: 1.15,
                          ),
                        ),
                      ],
                    ),
                  );
                }),
              ),
            ),
          ),
        ],
      ),
    );
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
            Text("Confirm Order Cancellation"),
          ],
        ),
        content: Text("Are you sure you want to cancel order #$orderNumber?"),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogCtx),
            child: const Text("No"),
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
                    content: Text(res['message'] ?? "Order cancelled successfully."),
                    backgroundColor: Colors.green,
                  ),
                );
              } else {
                messenger.showSnackBar(
                  SnackBar(
                    content: Text(res['message'] ?? "Could not cancel order."),
                    backgroundColor: Colors.red,
                  ),
                );
              }
            },
            style: ElevatedButton.styleFrom(backgroundColor: Colors.red),
            child: const Text("Yes, Cancel Order", style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
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
        leading: IconButton(
          icon: const Icon(Icons.arrow_back, color: Colors.white),
          tooltip: "Back to All Products",
          onPressed: () {
            if (Navigator.canPop(context)) {
              Navigator.pop(context);
            } else {
              Navigator.pushAndRemoveUntil(
                context,
                MaterialPageRoute(builder: (_) => const HomeScreen()),
                (route) => false,
              );
            }
          },
        ),
        title: Text(loc.translate('my_orders')),
        backgroundColor: Colors.green,
      ),
      body: _isLoadingPhone
          ? const Center(child: CircularProgressIndicator())
          : _userPhone.isEmpty
              ? Center(
                  child: Padding(
                    padding: const EdgeInsets.all(24.0),
                    child: Column(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        const Icon(Icons.shopping_bag_outlined, size: 64, color: Colors.grey),
                        const SizedBox(height: 12),
                        const Text(
                          "Sign in to view your order history",
                          style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
                        ),
                        const SizedBox(height: 6),
                        const Text(
                          "You must be logged in to track current or past purchases.",
                          textAlign: TextAlign.center,
                          style: TextStyle(color: Colors.grey, fontSize: 13),
                        ),
                        const SizedBox(height: 16),
                        ElevatedButton.icon(
                          onPressed: () async {
                            await Navigator.push(
                              context,
                              MaterialPageRoute(builder: (_) => const LoginScreen()),
                            );
                            _loadUserPhone();
                          },
                          icon: const Icon(Icons.login, color: Colors.white),
                          label: const Text("Sign In / Register Now", style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
                          style: ElevatedButton.styleFrom(backgroundColor: Colors.green),
                        ),
                      ],
                    ),
                  ),
                )
              : StreamBuilder<List<OnlineOrder>>(
                  stream: ApiService.myOrdersStream(_userPhone),
                  builder: (context, snapshot) {
                    if (snapshot.connectionState == ConnectionState.waiting && !snapshot.hasData) {
                      return const Center(child: CircularProgressIndicator());
                    }

                    final orders = snapshot.data ?? [];

                    if (orders.isEmpty) {
                      return const Center(child: Text("You have no previous orders"));
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

                        return Container(
                          margin: const EdgeInsets.only(bottom: 16),
                          decoration: BoxDecoration(
                            color: Colors.white,
                            borderRadius: BorderRadius.circular(14),
                            border: Border.all(color: Colors.grey.shade300),
                            boxShadow: [
                              BoxShadow(
                                color: Colors.black.withValues(alpha: 0.04),
                                blurRadius: 8,
                                offset: const Offset(0, 3),
                              ),
                            ],
                          ),
                          child: ClipRRect(
                            borderRadius: BorderRadius.circular(14),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                // Distinct Header Band with Left Stripe & Status Tone
                                Container(
                                  padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                                  decoration: BoxDecoration(
                                    color: statusColor.withValues(alpha: 0.08),
                                    border: Border(
                                      left: BorderSide(color: statusColor, width: 6),
                                      bottom: BorderSide(color: Colors.grey.shade200),
                                    ),
                                  ),
                                  child: Row(
                                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                    children: [
                                      Row(
                                        children: [
                                          Container(
                                            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                                            decoration: BoxDecoration(
                                              color: Colors.white,
                                              borderRadius: BorderRadius.circular(6),
                                              border: Border.all(color: Colors.grey.shade300),
                                            ),
                                            child: Text(
                                              "#${orders.length - index}",
                                              style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 11, color: Colors.blueGrey),
                                            ),
                                          ),
                                          const SizedBox(width: 8),
                                          Text(
                                            order.orderNumber,
                                            style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 15, color: Color(0xFF1E293B)),
                                          ),
                                        ],
                                      ),
                                      Container(
                                        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                                        decoration: BoxDecoration(
                                          color: statusColor,
                                          borderRadius: BorderRadius.circular(16),
                                        ),
                                        child: Text(
                                          _getStatusText(order.orderStatus).toUpperCase(),
                                          style: const TextStyle(color: Colors.white, fontSize: 11, fontWeight: FontWeight.w800),
                                        ),
                                      ),
                                    ],
                                  ),
                                ),

                                Padding(
                                  padding: const EdgeInsets.all(14.0),
                                  child: Column(
                                    crossAxisAlignment: CrossAxisAlignment.start,
                                    children: [
                                      // Date & Payment
                                      Row(
                                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                        children: [
                                          Text(
                                            '📅 ${order.createdAt.length >= 16 ? order.createdAt.substring(0, 16).replaceAll('T', ' ') : order.createdAt}',
                                            style: const TextStyle(color: Colors.grey, fontSize: 12),
                                          ),
                                          Text(
                                            order.paymentMethod == 'cod' ? '💵 Cash on Delivery' : '💳 Online Payment',
                                            style: const TextStyle(color: Colors.grey, fontSize: 12, fontWeight: FontWeight.w600),
                                          ),
                                        ],
                                      ),

                                      // Real-time Delivery Timeline Stepper
                                      _buildDeliveryTimeline(order),

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
                                          Text('TK ${item.totalPrice.toStringAsFixed(0)}'),
                                        ],
                                      ),
                                    );
                                  }).toList(),
                                ),
                                const Divider(),

                                Row(
                                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                  children: [
                                    const Text("Total Payable:", style: TextStyle(fontWeight: FontWeight.bold)),
                                    Text(
                                      'TK ${order.totalAmount.toStringAsFixed(2)}',
                                      style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16, color: Colors.green),
                                    ),
                                  ],
                                ),

                                // Delivery Rider Info Box
                                if (order.assignedRiderName.isNotEmpty || order.assignedRiderPhone.isNotEmpty)
                                  Container(
                                    margin: const EdgeInsets.only(top: 10),
                                    padding: const EdgeInsets.all(10),
                                    decoration: BoxDecoration(
                                      color: Colors.blue.shade50,
                                      borderRadius: BorderRadius.circular(8),
                                      border: Border.all(color: Colors.blue.shade200),
                                    ),
                                    child: Row(
                                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                      children: [
                                        Expanded(
                                          child: Column(
                                            crossAxisAlignment: CrossAxisAlignment.start,
                                            children: [
                                              Text(
                                                "🛵 Delivery Rider: ${order.assignedRiderName.isNotEmpty ? order.assignedRiderName : 'Assigned'}",
                                                style: const TextStyle(fontWeight: FontWeight.bold, color: Colors.blue, fontSize: 13),
                                              ),
                                              if (order.assignedRiderPhone.isNotEmpty)
                                                Text(
                                                  "📞 ${order.assignedRiderPhone}",
                                                  style: const TextStyle(color: Colors.black87, fontSize: 13),
                                                ),
                                            ],
                                          ),
                                        ),
                                        if (order.assignedRiderPhone.isNotEmpty)
                                          ElevatedButton.icon(
                                            onPressed: () async {
                                              final Uri telUri = Uri.parse('tel:${order.assignedRiderPhone}');
                                              if (await canLaunchUrl(telUri)) {
                                                await launchUrl(telUri);
                                              }
                                            },
                                            icon: const Icon(Icons.phone, size: 14),
                                            label: const Text("Call Rider", style: TextStyle(fontSize: 12)),
                                            style: ElevatedButton.styleFrom(
                                              backgroundColor: Colors.green,
                                              padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                                            ),
                                          ),
                                      ],
                                    ),
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
                                                    'Cancel Window: ${_formatSeconds(remainingSeconds)}',
                                                    style: const TextStyle(fontWeight: FontWeight.bold, color: Colors.orange, fontSize: 12),
                                                  ),
                                                ],
                                              ),
                                              ElevatedButton.icon(
                                                onPressed: () => _confirmCancelOrder(order.orderNumber),
                                                icon: const Icon(Icons.cancel, size: 16, color: Colors.white),
                                                label: const Text('Cancel Order', style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 12)),
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
                                                'Cancellation window closed (10 minutes passed)',
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
                                              "Your Delivery OTP:",
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
