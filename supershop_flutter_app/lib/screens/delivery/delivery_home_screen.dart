import 'dart:async';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../../models/online_order.dart';
import '../../services/api_service.dart';
import '../auth/login_screen.dart';
import 'rider_billing_sheet.dart';

class DeliveryHomeScreen extends StatefulWidget {
  const DeliveryHomeScreen({Key? key}) : super(key: key);

  @override
  State<DeliveryHomeScreen> createState() => _DeliveryHomeScreenState();
}

class _DeliveryHomeScreenState extends State<DeliveryHomeScreen> {
  List<OnlineOrder> _deliveryOrders = [];
  Map<String, dynamic>? _riderEarnings;
  bool _isLoadingOrders = true;
  bool _isLoadingEarnings = true;
  Timer? _refreshTimer;
  String _riderName = 'Delivery Rider';
  String _riderPhone = '';
  final Set<int> _notifiedOrderIds = {};
  int _viewMode = 0; // 0 = 2 Columns (Side-by-side), 1 = Orders only, 2 = Earnings only
  String _deptFilter = 'all'; // 'all', 'regular', 'pharmacy'

  @override
  void initState() {
    super.initState();
    _loadRiderPrefs();
    _refreshTimer = Timer.periodic(const Duration(seconds: 5), (_) => _loadAllData(silent: true));
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
    _loadAllData();
  }

  Future<void> _loadAllData({bool silent = false}) async {
    if (!silent) {
      setState(() {
        _isLoadingOrders = true;
        _isLoadingEarnings = true;
      });
    }

    await Future.wait([
      _loadDeliveryOrders(),
      _loadRiderEarnings(),
    ]);
  }

  Future<void> _loadDeliveryOrders() async {
    try {
      List<OnlineOrder> orders = await ApiService.fetchDeliveryOrders(riderPhone: _riderPhone);
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
        _isLoadingOrders = false;
      });
    } catch (e) {
      if (mounted) setState(() => _isLoadingOrders = false);
    }
  }

  Future<void> _loadRiderEarnings() async {
    if (_riderPhone.isEmpty) {
      if (mounted) setState(() => _isLoadingEarnings = false);
      return;
    }
    try {
      var earnings = await ApiService.fetchRiderEarnings(riderPhone: _riderPhone);
      if (!mounted) return;
      setState(() {
        _riderEarnings = earnings;
        _isLoadingEarnings = false;
      });
    } catch (e) {
      if (mounted) setState(() => _isLoadingEarnings = false);
    }
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
                  Text("💵 Cash Collection: TK ${order.totalAmount.toStringAsFixed(0)}", style: const TextStyle(fontWeight: FontWeight.bold, color: Colors.green, fontSize: 15)),
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
      _loadAllData();
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
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        title: Row(
          children: [
            const Icon(Icons.verified_user, color: Colors.green),
            const SizedBox(width: 8),
            Expanded(child: Text("Deliver Order #${order.orderNumber}", style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold))),
          ],
        ),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text("Customer: ${order.customerName}", style: const TextStyle(fontWeight: FontWeight.w600)),
            Text("Phone: ${order.customerPhone}", style: const TextStyle(color: Colors.blue)),
            Text("Cash Collection: TK ${order.totalAmount.toStringAsFixed(0)}", style: const TextStyle(fontWeight: FontWeight.bold, color: Colors.green)),
            const SizedBox(height: 12),
            const Text("Enter 4-digit Delivery OTP given by customer:"),
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
                  SnackBar(content: Text(res['message'] ?? 'Delivered successfully! Earnings updated.'), backgroundColor: Colors.green),
                );
                _loadAllData();
              } else {
                ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(content: Text(res['message'] ?? 'Invalid OTP code'), backgroundColor: Colors.red),
                );
              }
            },
            style: ElevatedButton.styleFrom(backgroundColor: Colors.green),
            child: const Text("Verify OTP & Complete Delivery", style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
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
      _loadAllData();
    } else {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(content: Text(res['message'] ?? 'Failed to update status'), backgroundColor: Colors.red),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    double balanceDue = 0.0;
    if (_riderEarnings != null && _riderEarnings!['balance_due'] != null) {
      balanceDue = (_riderEarnings!['balance_due'] as num).toDouble();
    }

    return Scaffold(
      appBar: AppBar(
        title: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            const Text("🚴 Rider Mode", style: TextStyle(fontWeight: FontWeight.bold, fontSize: 18, color: Colors.white)),
            Text(
              "$_riderName (${_riderPhone.isNotEmpty ? _riderPhone : 'Active'})",
              style: const TextStyle(fontSize: 12, color: Colors.white70),
            ),
          ],
        ),
        backgroundColor: Colors.orange.shade800,
        actions: [
          TextButton.icon(
            onPressed: () => showRiderBillingModal(
              context,
              riderPhone: _riderPhone,
              onBillCreated: () => _loadAllData(silent: true),
            ),
            icon: const Icon(Icons.receipt_long, color: Colors.white, size: 18),
            label: const Text('বিল', style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
          ),
          IconButton(
            icon: const Icon(Icons.refresh, color: Colors.white),
            tooltip: "Refresh Data",
            onPressed: () => _loadAllData(),
          ),
          IconButton(
            icon: const Icon(Icons.logout, color: Colors.white),
            tooltip: "Log Out",
            onPressed: () async {
              final nav = Navigator.of(context);
              _refreshTimer?.cancel();
              final prefs = await SharedPreferences.getInstance();
              await prefs.remove('user_phone');
              await prefs.remove('user_name');
              await prefs.remove('is_delivery_man');
              await prefs.setBool('stay_signed_in', false);
              if (!mounted) return;
              nav.pushAndRemoveUntil(
                MaterialPageRoute(builder: (_) => const LoginScreen()),
                (route) => false,
              );
            },
          )
        ],
      ),
      body: LayoutBuilder(
        builder: (context, constraints) {
          bool isWide = constraints.maxWidth >= 720;

          return Column(
            children: [
              // Responsive Top View Selector on compact screens
              if (!isWide)
                Container(
                  color: Colors.orange.shade50,
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                  child: Row(
                    children: [
                      Expanded(
                        child: _buildViewModeButton(
                          modeIndex: 0,
                          label: "⊞ ২ কলাম ভিউ",
                          badge: null,
                        ),
                      ),
                      const SizedBox(width: 6),
                      Expanded(
                        child: _buildViewModeButton(
                          modeIndex: 1,
                          label: "📦 চলতি অর্ডার",
                          badge: "${_deliveryOrders.length}",
                        ),
                      ),
                      const SizedBox(width: 6),
                      Expanded(
                        child: _buildViewModeButton(
                          modeIndex: 2,
                          label: "💰 আয় ও বকেয়া",
                          badge: "TK ${balanceDue.toStringAsFixed(0)}",
                          badgeColor: balanceDue > 0 ? Colors.red : Colors.green,
                        ),
                      ),
                    ],
                  ),
                ),

              // Main 2-Column or Single-Column Content Area
              Expanded(
                child: (isWide || _viewMode == 0)
                    ? Row(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          // Column 1: Active Online Orders
                          Expanded(
                            flex: isWide ? 6 : 5,
                            child: _buildOrdersColumn(isCompact: !isWide),
                          ),
                          VerticalDivider(width: 1, thickness: 1, color: Colors.grey.shade300),
                          // Column 2: Rider Earnings, Paid & Due
                          Expanded(
                            flex: isWide ? 5 : 5,
                            child: _buildEarningsColumn(isCompact: !isWide),
                          ),
                        ],
                      )
                    : (_viewMode == 1
                        ? _buildOrdersColumn(isCompact: false)
                        : _buildEarningsColumn(isCompact: false)),
              ),
            ],
          );
        },
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => showRiderBillingModal(
          context,
          riderPhone: _riderPhone,
          onBillCreated: () => _loadAllData(silent: true),
        ),
        backgroundColor: Colors.teal.shade700,
        foregroundColor: Colors.white,
        icon: const Icon(Icons.add_shopping_cart),
        label: const Text('নতুন বিল', style: TextStyle(fontWeight: FontWeight.bold)),
      ),
    );
  }

  Widget _buildViewModeButton({
    required int modeIndex,
    required String label,
    String? badge,
    Color? badgeColor,
  }) {
    bool isSelected = _viewMode == modeIndex;
    return InkWell(
      onTap: () => setState(() => _viewMode = modeIndex),
      borderRadius: BorderRadius.circular(8),
      child: Container(
        padding: const EdgeInsets.symmetric(vertical: 6, horizontal: 4),
        decoration: BoxDecoration(
          color: isSelected ? Colors.orange.shade800 : Colors.white,
          borderRadius: BorderRadius.circular(8),
          border: Border.all(
            color: isSelected ? Colors.orange.shade800 : Colors.grey.shade300,
            width: 1.5,
          ),
        ),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Text(
              label,
              style: TextStyle(
                fontSize: 11,
                fontWeight: FontWeight.bold,
                color: isSelected ? Colors.white : Colors.grey.shade800,
              ),
              textAlign: TextAlign.center,
              maxLines: 1,
              overflow: TextOverflow.ellipsis,
            ),
            if (badge != null) ...[
              const SizedBox(height: 2),
              Container(
                padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1),
                decoration: BoxDecoration(
                  color: isSelected ? Colors.white : (badgeColor ?? Colors.orange.shade700),
                  borderRadius: BorderRadius.circular(10),
                ),
                child: Text(
                  badge,
                  style: TextStyle(
                    fontSize: 9,
                    fontWeight: FontWeight.bold,
                    color: isSelected ? Colors.orange.shade900 : Colors.white,
                  ),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }

  // =========================================================================
  // COLUMN 1: Active Online Orders (Unconfirmed new + assigned/deployed orders)
  // =========================================================================
  String _resolveMediaUrl(String raw) {
    final trimmed = raw.trim();
    if (trimmed.isEmpty) return '';
    if (trimmed.startsWith('http://') || trimmed.startsWith('https://')) return trimmed;
    final base = ApiService.baseUrl;
    return trimmed.startsWith('/') ? '$base$trimmed' : '$base/$trimmed';
  }

  void _showPrescriptionModal(OnlineOrder order) {
    final url = _resolveMediaUrl(
      order.prescriptionUrl.isNotEmpty ? order.prescriptionUrl : order.prescriptionOriginalUrl,
    );
    if (url.isEmpty) return;
    showDialog(
      context: context,
      builder: (ctx) => Dialog(
        insetPadding: const EdgeInsets.all(14),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
              color: Colors.green.shade800,
              child: Row(
                children: [
                  const Icon(Icons.medication, color: Colors.white),
                  const SizedBox(width: 8),
                  Expanded(
                    child: Text(
                      'প্রেসক্রিপশন #${order.orderNumber}',
                      style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold),
                    ),
                  ),
                  IconButton(
                    icon: const Icon(Icons.close, color: Colors.white),
                    onPressed: () => Navigator.of(ctx).pop(),
                  ),
                ],
              ),
            ),
            ConstrainedBox(
              constraints: BoxConstraints(maxHeight: MediaQuery.of(ctx).size.height * 0.7),
              child: InteractiveViewer(
                minScale: 0.8,
                maxScale: 4.0,
                child: Image.network(
                  url,
                  fit: BoxFit.contain,
                  errorBuilder: (_, __, ___) => const Padding(
                    padding: EdgeInsets.all(24),
                    child: Text('প্রেসক্রিপশন লোড করা যায়নি।'),
                  ),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  Future<void> _printOrderThermal(OnlineOrder order) async {
    final bool usePharm = order.isPharmacyOrder && order.pharmacyOrderId > 0;
    final res = await ApiService.printOnPcThermal(
      riderPhone: _riderPhone,
      sourceType: usePharm ? 'pharmacy_order' : 'online_order',
      sourceId: usePharm ? order.pharmacyOrderId : order.id,
      invoiceNumber: order.orderNumber,
    );
    if (!mounted) return;
    final bool ok = res['success'] == true;
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        content: Text(res['message']?.toString() ?? (ok ? 'PC প্রিন্টারে পাঠানো হয়েছে!' : 'প্রিন্ট ব্যর্থ হয়েছে')),
        backgroundColor: ok ? Colors.teal.shade700 : Colors.red,
      ),
    );
  }

  Widget _buildDeptFilterChip(String key, String label, Color color) {
    final bool selected = _deptFilter == key;
    return Expanded(
      child: InkWell(
        onTap: () => setState(() => _deptFilter = key),
        borderRadius: BorderRadius.circular(8),
        child: Container(
          padding: const EdgeInsets.symmetric(vertical: 6, horizontal: 4),
          decoration: BoxDecoration(
            color: selected ? color : Colors.white,
            borderRadius: BorderRadius.circular(8),
            border: Border.all(color: selected ? color : Colors.grey.shade300),
          ),
          alignment: Alignment.center,
          child: Text(
            label,
            overflow: TextOverflow.ellipsis,
            style: TextStyle(
              fontSize: 10.5,
              fontWeight: FontWeight.bold,
              color: selected ? Colors.white : Colors.grey.shade800,
            ),
          ),
        ),
      ),
    );
  }

  Widget _buildOrdersColumn({required bool isCompact}) {
    final int regCount = _deliveryOrders.where((o) => !o.isPharmacyOrder).length;
    final int pharmCount = _deliveryOrders.where((o) => o.isPharmacyOrder).length;
    final List<OnlineOrder> visibleOrders = _deptFilter == 'pharmacy'
        ? _deliveryOrders.where((o) => o.isPharmacyOrder).toList()
        : (_deptFilter == 'regular'
            ? _deliveryOrders.where((o) => !o.isPharmacyOrder).toList()
            : _deliveryOrders);

    return Container(
      color: const Color(0xFFF8FAFC),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Column 1 Header Banner
          Container(
            padding: EdgeInsets.symmetric(horizontal: isCompact ? 10 : 16, vertical: 10),
            decoration: BoxDecoration(
              color: Colors.blue.shade50,
              border: Border(bottom: BorderSide(color: Colors.blue.shade200)),
            ),
            child: Column(
              children: [
                Row(
                  children: [
                    const Icon(Icons.list_alt, color: Colors.blue, size: 20),
                    const SizedBox(width: 8),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            "কলাম ১: চলতি অর্ডার সমূহ",
                            style: TextStyle(
                              fontSize: isCompact ? 13 : 15,
                              fontWeight: FontWeight.bold,
                              color: Colors.blue.shade900,
                            ),
                          ),
                          Text(
                            "সাধারণ পণ্য ও ফার্মেসী অর্ডার আলাদা দেখুন",
                            style: TextStyle(fontSize: isCompact ? 10 : 11, color: Colors.blue.shade700),
                          ),
                        ],
                      ),
                    ),
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                      decoration: BoxDecoration(
                        color: Colors.blue.shade700,
                        borderRadius: BorderRadius.circular(12),
                      ),
                      child: Text(
                        "${visibleOrders.length}",
                        style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 12),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 8),
                Row(
                  children: [
                    _buildDeptFilterChip('all', 'সব (${_deliveryOrders.length})', Colors.blueGrey.shade800),
                    const SizedBox(width: 6),
                    _buildDeptFilterChip('regular', '🛒 অন্যান্য ($regCount)', Colors.blue.shade700),
                    const SizedBox(width: 6),
                    _buildDeptFilterChip('pharmacy', '💊 ফার্মেসী ($pharmCount)', Colors.green.shade700),
                  ],
                ),
              ],
            ),
          ),

          // Orders List
          Expanded(
            child: _isLoadingOrders
                ? const Center(child: CircularProgressIndicator())
                : visibleOrders.isEmpty
                    ? Center(
                        child: Padding(
                          padding: const EdgeInsets.all(20.0),
                          child: Column(
                            mainAxisAlignment: MainAxisAlignment.center,
                            children: [
                              Icon(Icons.inventory_2_outlined, size: 48, color: Colors.grey.shade400),
                              const SizedBox(height: 12),
                              const Text(
                                "কোনো চলতি ডেলিভারি অর্ডার নেই",
                                style: TextStyle(fontWeight: FontWeight.bold, fontSize: 14, color: Colors.grey),
                              ),
                              const SizedBox(height: 4),
                              Text(
                                "নতুন অনলাইন অর্ডার আসলে এখানে দেখাবে",
                                style: TextStyle(fontSize: 12, color: Colors.grey.shade500),
                              ),
                            ],
                          ),
                        ),
                      )
                    : RefreshIndicator(
                        onRefresh: () => _loadAllData(),
                        child: ListView.builder(
                          padding: EdgeInsets.all(isCompact ? 8 : 12),
                          itemCount: visibleOrders.length,
                          itemBuilder: (context, index) {
                            final order = visibleOrders[index];
                            return _buildOrderCard(order, isCompact);
                          },
                        ),
                      ),
          ),
        ],
      ),
    );
  }

  Widget _buildOrderCard(OnlineOrder order, bool isCompact) {
    String timeStr = order.createdAt.isNotEmpty
        ? order.createdAt.substring(0, 16).replaceFirst('T', ' ')
        : '—';

    Color statusColor;
    String statusLabel;
    switch (order.orderStatus) {
      case 'new':
        statusColor = Colors.purple;
        statusLabel = "NEW (নতুন)";
        break;
      case 'verified':
        statusColor = Colors.blue;
        statusLabel = "ACCEPTED";
        break;
      case 'packed':
        statusColor = Colors.orange;
        statusLabel = "PACKED";
        break;
      case 'on_the_way':
        statusColor = Colors.teal;
        statusLabel = "ON THE WAY";
        break;
      default:
        statusColor = Colors.grey;
        statusLabel = order.orderStatus.toUpperCase();
    }

    return Card(
      margin: const EdgeInsets.only(bottom: 10),
      elevation: 2,
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
      child: Padding(
        padding: EdgeInsets.all(isCompact ? 10 : 14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Top Row: Order Number, Dept Badge & Status
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Wrap(
                        spacing: 6,
                        runSpacing: 4,
                        crossAxisAlignment: WrapCrossAlignment.center,
                        children: [
                          Text(
                            "${order.isPharmacyOrder ? '💊' : '📦'} #${order.orderNumber}",
                            style: TextStyle(
                              fontWeight: FontWeight.bold,
                              fontSize: isCompact ? 13 : 15,
                              color: order.isPharmacyOrder ? Colors.green.shade900 : Colors.blue.shade900,
                            ),
                          ),
                          Container(
                            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                            decoration: BoxDecoration(
                              color: order.isPharmacyOrder ? Colors.green.shade50 : Colors.blue.shade50,
                              borderRadius: BorderRadius.circular(5),
                              border: Border.all(
                                color: order.isPharmacyOrder ? Colors.green.shade300 : Colors.blue.shade200,
                              ),
                            ),
                            child: Text(
                              order.isPharmacyOrder ? "💊 ফার্মেসী" : "🛒 সাধারণ",
                              style: TextStyle(
                                fontSize: 10,
                                fontWeight: FontWeight.bold,
                                color: order.isPharmacyOrder ? Colors.green.shade800 : Colors.blue.shade800,
                              ),
                            ),
                          ),
                        ],
                      ),
                      Text(
                        "📅 $timeStr",
                        style: TextStyle(fontSize: isCompact ? 10 : 11, color: Colors.grey.shade600),
                      ),
                    ],
                  ),
                ),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
                  decoration: BoxDecoration(
                    color: statusColor,
                    borderRadius: BorderRadius.circular(6),
                  ),
                  child: Text(
                    statusLabel,
                    style: TextStyle(
                      color: Colors.white,
                      fontSize: isCompact ? 10 : 11,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                ),
              ],
            ),
            const Divider(height: 14),

            // Customer Details
            Text(
              "👤 ${order.customerName}",
              style: TextStyle(fontWeight: FontWeight.bold, fontSize: isCompact ? 12 : 13),
            ),
            Text(
              "📞 ${order.customerPhone}",
              style: TextStyle(color: Colors.blue.shade800, fontWeight: FontWeight.bold, fontSize: isCompact ? 11 : 12),
            ),
            const SizedBox(height: 3),
            Text(
              "📍 ${order.area}, ${order.district}",
              style: TextStyle(fontSize: isCompact ? 11 : 12, fontWeight: FontWeight.w600, color: Colors.grey.shade800),
            ),
            if (order.addressDetails.isNotEmpty)
              Text(
                "🏠 ${order.addressDetails}",
                style: TextStyle(color: Colors.grey.shade600, fontSize: isCompact ? 10 : 11),
                maxLines: 2,
                overflow: TextOverflow.ellipsis,
              ),
            if (order.customerIp.isNotEmpty || order.ipLocation.isNotEmpty)
              Padding(
                padding: const EdgeInsets.only(top: 3),
                child: Text(
                  "🌐 IP: ${order.customerIp.isNotEmpty ? order.customerIp : '—'}${order.ipLocation.isNotEmpty ? ' • ${order.ipLocation}' : ''}",
                  style: TextStyle(fontSize: 10, color: Colors.blueGrey.shade600),
                ),
              ),
            if (order.items.isNotEmpty) ...[
              const SizedBox(height: 6),
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(6),
                decoration: BoxDecoration(
                  color: Colors.grey.shade50,
                  borderRadius: BorderRadius.circular(6),
                  border: Border.all(color: Colors.grey.shade200),
                ),
                child: Text(
                  order.items.map((it) => "• ${it.productName} × ${it.quantity}").join('\n'),
                  style: TextStyle(fontSize: 10.5, color: Colors.grey.shade800),
                  maxLines: 4,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
            ],
            if (order.isPharmacyOrder && (order.prescriptionUrl.isNotEmpty || order.customerNotes.isNotEmpty || order.overallDurationDays > 0)) ...[
              const SizedBox(height: 6),
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(6),
                decoration: BoxDecoration(
                  color: Colors.green.shade50,
                  borderRadius: BorderRadius.circular(6),
                  border: Border.all(color: Colors.green.shade200),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    if (order.overallDurationDays > 0)
                      Text('⏱️ মেয়াদ: ${order.overallDurationDays} দিন', style: TextStyle(fontSize: 10.5, fontWeight: FontWeight.bold, color: Colors.green.shade900)),
                    if (order.customerNotes.isNotEmpty)
                      Text('📝 নোট: ${order.customerNotes}', style: TextStyle(fontSize: 10.5, color: Colors.green.shade800)),
                    if (order.prescriptionUrl.isNotEmpty)
                      Align(
                        alignment: Alignment.centerLeft,
                        child: TextButton.icon(
                          onPressed: () => _showPrescriptionModal(order),
                          icon: const Icon(Icons.image_search, size: 15),
                          label: const Text('📄 প্রেসক্রিপশন দেখুন', style: TextStyle(fontSize: 11, fontWeight: FontWeight.bold)),
                          style: TextButton.styleFrom(
                            foregroundColor: Colors.green.shade800,
                            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                            minimumSize: Size.zero,
                            tapTargetSize: MaterialTapTargetSize.shrinkWrap,
                          ),
                        ),
                      ),
                  ],
                ),
              ),
            ],
            const SizedBox(height: 8),

            // Cash Collection and Action
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
              decoration: BoxDecoration(
                color: Colors.green.shade50,
                borderRadius: BorderRadius.circular(6),
                border: Border.all(color: Colors.green.shade200),
              ),
              child: Row(
                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                children: [
                  Text(
                    "Cash Collection:",
                    style: TextStyle(fontSize: isCompact ? 11 : 12, color: Colors.green.shade900),
                  ),
                  Text(
                    "TK ${order.totalAmount.toStringAsFixed(0)}",
                    style: TextStyle(
                      fontWeight: FontWeight.bold,
                      color: Colors.green.shade900,
                      fontSize: isCompact ? 12 : 14,
                    ),
                  ),
                ],
              ),
            ),
            const SizedBox(height: 8),

            // Action Buttons + PC Thermal Print
            Row(
              children: [
                Expanded(child: _buildOrderActionButton(order, isCompact)),
                const SizedBox(width: 6),
                ElevatedButton.icon(
                  onPressed: () => _printOrderThermal(order),
                  icon: const Icon(Icons.print, size: 15, color: Colors.white),
                  label: Text(
                    isCompact ? "PC প্রিন্ট" : "🖨️ PC প্রিন্ট",
                    style: TextStyle(fontSize: isCompact ? 10 : 11, fontWeight: FontWeight.bold, color: Colors.white),
                  ),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: Colors.blueGrey.shade800,
                    padding: EdgeInsets.symmetric(horizontal: isCompact ? 8 : 12, vertical: 9),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
                  ),
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }

  Widget _buildOrderActionButton(OnlineOrder order, bool isCompact) {
    final bool isUnassignedPool = order.assignedRiderPhone.trim().isEmpty &&
        (order.orderStatus == 'new' || order.orderStatus == 'verified' || order.orderStatus == 'packed');
    if (order.orderStatus == 'new' || isUnassignedPool) {
      return ElevatedButton.icon(
        onPressed: () => _acceptOrder(order),
        icon: const Icon(Icons.check_circle, size: 16, color: Colors.white),
        label: Text(
          "Accept Delivery",
          style: TextStyle(fontWeight: FontWeight.bold, fontSize: isCompact ? 11 : 13, color: Colors.white),
        ),
        style: ElevatedButton.styleFrom(
          backgroundColor: Colors.blue.shade700,
          padding: const EdgeInsets.symmetric(vertical: 8),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
        ),
      );
    } else if (order.orderStatus == 'verified') {
      return ElevatedButton.icon(
        onPressed: () => _updateRiderStatus(order, 'packed'),
        icon: const Icon(Icons.inventory_2, size: 16, color: Colors.white),
        label: Text(
          "Mark Packed",
          style: TextStyle(fontWeight: FontWeight.bold, fontSize: isCompact ? 11 : 13, color: Colors.white),
        ),
        style: ElevatedButton.styleFrom(
          backgroundColor: Colors.orange.shade700,
          padding: const EdgeInsets.symmetric(vertical: 8),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
        ),
      );
    } else if (order.orderStatus == 'packed') {
      return ElevatedButton.icon(
        onPressed: () => _updateRiderStatus(order, 'on_the_way'),
        icon: const Icon(Icons.directions_bike, size: 16, color: Colors.white),
        label: Text(
          "Send On The Way",
          style: TextStyle(fontWeight: FontWeight.bold, fontSize: isCompact ? 11 : 13, color: Colors.white),
        ),
        style: ElevatedButton.styleFrom(
          backgroundColor: Colors.cyan.shade800,
          padding: const EdgeInsets.symmetric(vertical: 8),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
        ),
      );
    } else if (order.orderStatus == 'on_the_way') {
      return ElevatedButton.icon(
        onPressed: () => _showOtpDialog(order),
        icon: const Icon(Icons.key, size: 16, color: Colors.white),
        label: Text(
          "Verify OTP & Deliver",
          style: TextStyle(fontWeight: FontWeight.bold, fontSize: isCompact ? 11 : 13, color: Colors.white),
        ),
        style: ElevatedButton.styleFrom(
          backgroundColor: Colors.green.shade700,
          padding: const EdgeInsets.symmetric(vertical: 8),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(6)),
        ),
      );
    }
    return const SizedBox.shrink();
  }

  // =========================================================================
  // COLUMN 2: Rider Earnings, Total Paid & Balance Due (Matches Admin Panel)
  // =========================================================================
  Widget _buildEarningsColumn({required bool isCompact}) {
    double totalEarned = 0.0;
    double totalPaid = 0.0;
    double balanceDue = 0.0;
    int totalDelivered = 0;
    double totalCollected = 0.0;
    double defaultFee = 40.0;
    List<dynamic> payouts = [];
    List<dynamic> deliveredOrders = [];
    Map<String, dynamic> regularStats = {};
    Map<String, dynamic> pharmacyStats = {};

    if (_riderEarnings != null) {
      totalEarned = ((_riderEarnings!['total_earned'] ?? 0) as num).toDouble();
      totalPaid = ((_riderEarnings!['total_paid'] ?? 0) as num).toDouble();
      balanceDue = ((_riderEarnings!['balance_due'] ?? 0) as num).toDouble();
      totalDelivered = ((_riderEarnings!['total_delivered'] ?? 0) as num).toInt();
      totalCollected = ((_riderEarnings!['total_collected'] ?? 0) as num).toDouble();
      defaultFee = ((_riderEarnings!['default_rider_fee'] ?? 40) as num).toDouble();
      payouts = _riderEarnings!['payouts'] ?? [];
      deliveredOrders = _riderEarnings!['delivered_orders'] ?? [];
      if (_riderEarnings!['regular_stats'] is Map) {
        regularStats = Map<String, dynamic>.from(_riderEarnings!['regular_stats']);
      }
      if (_riderEarnings!['pharmacy_stats'] is Map) {
        pharmacyStats = Map<String, dynamic>.from(_riderEarnings!['pharmacy_stats']);
      }
    }

    return Container(
      color: const Color(0xFFFAFAFA),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          // Column 2 Header Banner
          Container(
            padding: EdgeInsets.symmetric(horizontal: isCompact ? 10 : 16, vertical: 10),
            decoration: BoxDecoration(
              color: Colors.green.shade50,
              border: Border(bottom: BorderSide(color: Colors.green.shade200)),
            ),
            child: Row(
              children: [
                const Icon(Icons.account_balance_wallet, color: Colors.green, size: 20),
                const SizedBox(width: 8),
                Expanded(
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Text(
                        "কলাম ২: রাইডার আয় ও হিসাব",
                        style: TextStyle(
                          fontSize: isCompact ? 13 : 15,
                          fontWeight: FontWeight.bold,
                          color: Colors.green.shade900,
                        ),
                      ),
                      Text(
                        "এডমিন প্যানেলের খরচের সাথে সমন্বিত",
                        style: TextStyle(fontSize: isCompact ? 10 : 11, color: Colors.green.shade700),
                      ),
                    ],
                  ),
                ),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                  decoration: BoxDecoration(
                    color: balanceDue > 0 ? Colors.red.shade700 : Colors.green.shade700,
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: Text(
                    balanceDue > 0 ? "Due" : "Settled",
                    style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 11),
                  ),
                ),
              ],
            ),
          ),

          // Column 2 Content Area
          Expanded(
            child: _isLoadingEarnings
                ? const Center(child: CircularProgressIndicator())
                : RefreshIndicator(
                    onRefresh: () => _loadAllData(),
                    child: SingleChildScrollView(
                      padding: EdgeInsets.all(isCompact ? 8 : 12),
                      physics: const AlwaysScrollableScrollPhysics(),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          // 1. Primary Highlight Card: Balance Due
                          Container(
                            width: double.infinity,
                            padding: EdgeInsets.all(isCompact ? 12 : 16),
                            decoration: BoxDecoration(
                              gradient: LinearGradient(
                                colors: balanceDue > 0
                                    ? [const Color(0xFFFEF2F2), const Color(0xFFFEE2E2)]
                                    : [const Color(0xFFF0FDF4), const Color(0xFFDCFCE7)],
                                begin: Alignment.topLeft,
                                end: Alignment.bottomRight,
                              ),
                              borderRadius: BorderRadius.circular(12),
                              border: Border.all(
                                color: balanceDue > 0 ? Colors.red.shade300 : Colors.green.shade300,
                                width: 1.5,
                              ),
                              boxShadow: const [
                                BoxShadow(
                                  color: Color(0x0A000000),
                                  blurRadius: 6,
                                  offset: Offset(0, 2),
                                ),
                              ],
                            ),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Row(
                                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                  children: [
                                    Text(
                                      "⚠️ বর্তমান বকেয়া (Balance Due):",
                                      style: TextStyle(
                                        fontSize: isCompact ? 11 : 13,
                                        fontWeight: FontWeight.bold,
                                        color: balanceDue > 0 ? Colors.red.shade900 : Colors.green.shade900,
                                      ),
                                    ),
                                    Container(
                                      padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                                      decoration: BoxDecoration(
                                        color: balanceDue > 0 ? Colors.red : Colors.green,
                                        borderRadius: BorderRadius.circular(6),
                                      ),
                                      child: Text(
                                        balanceDue > 0 ? "পাওনা বাকি" : "পরিশোধিত",
                                        style: const TextStyle(color: Colors.white, fontSize: 10, fontWeight: FontWeight.bold),
                                      ),
                                    ),
                                  ],
                                ),
                                const SizedBox(height: 6),
                                Text(
                                  "TK ${balanceDue.toStringAsFixed(2)}",
                                  style: TextStyle(
                                    fontSize: isCompact ? 22 : 26,
                                    fontWeight: FontWeight.w900,
                                    color: balanceDue > 0 ? Colors.red.shade800 : Colors.green.shade800,
                                  ),
                                ),
                                const SizedBox(height: 4),
                                Text(
                                  balanceDue > 0
                                      ? "এডমিন প্যানেল থেকে এই টাকা পরিশোধ করা হবে"
                                      : "সব ডেলিভারির কমিশন সম্পূর্ণ পরিশোধ করা হয়েছে",
                                  style: TextStyle(
                                    fontSize: isCompact ? 10 : 11,
                                    color: balanceDue > 0 ? Colors.red.shade700 : Colors.green.shade700,
                                  ),
                                ),
                              ],
                            ),
                          ),

                          const SizedBox(height: 10),

                          // 2. Earnings & Payment Stats Grid
                          Row(
                            children: [
                              Expanded(
                                child: _buildStatMetricCard(
                                  title: "মোট অর্জিত আয়",
                                  value: "TK ${totalEarned.toStringAsFixed(0)}",
                                  subtitle: "কমিশন ($totalDelivered ডেলিভারি)",
                                  icon: Icons.monetization_on,
                                  color: Colors.purple,
                                  isCompact: isCompact,
                                ),
                              ),
                              const SizedBox(width: 8),
                              Expanded(
                                child: _buildStatMetricCard(
                                  title: "পরিশোধ করা হয়েছে",
                                  value: "TK ${totalPaid.toStringAsFixed(0)}",
                                  subtitle: "এডমিনের খরচ হিসেবে পেইড",
                                  icon: Icons.check_circle,
                                  color: Colors.teal,
                                  isCompact: isCompact,
                                ),
                              ),
                            ],
                          ),

                          const SizedBox(height: 8),

                          Row(
                            children: [
                              Expanded(
                                child: _buildStatMetricCard(
                                  title: "ডেলিভার্ড অর্ডার",
                                  value: "$totalDelivered টি",
                                  subtitle: "রেট: TK ${defaultFee.toStringAsFixed(0)}/অর্ডার",
                                  icon: Icons.local_shipping,
                                  color: Colors.blue,
                                  isCompact: isCompact,
                                ),
                              ),
                              const SizedBox(width: 8),
                              Expanded(
                                child: _buildStatMetricCard(
                                  title: "ক্যাশ কালেকশন",
                                  value: "TK ${totalCollected.toStringAsFixed(0)}",
                                  subtitle: "গ্রাহকদের থেকে সংগৃহীত",
                                  icon: Icons.payments,
                                  color: Colors.deepOrange,
                                  isCompact: isCompact,
                                ),
                              ),
                            ],
                          ),

                          const SizedBox(height: 8),

                          // Regular vs Pharmacy Earnings Split
                          Row(
                            children: [
                              Expanded(
                                child: _buildStatMetricCard(
                                  title: "🛒 সাধারণ ডেলিভারি",
                                  value: "${(regularStats['delivered'] ?? 0)} টি",
                                  subtitle:
                                      "আয়: TK ${((regularStats['earned'] ?? 0) as num).toStringAsFixed(0)} | ক্যাশ: TK ${((regularStats['collected'] ?? 0) as num).toStringAsFixed(0)}",
                                  icon: Icons.shopping_bag,
                                  color: Colors.indigo,
                                  isCompact: isCompact,
                                ),
                              ),
                              const SizedBox(width: 8),
                              Expanded(
                                child: _buildStatMetricCard(
                                  title: "💊 ফার্মেসী ডেলিভারি",
                                  value: "${(pharmacyStats['delivered'] ?? 0)} টি",
                                  subtitle:
                                      "আয়: TK ${((pharmacyStats['earned'] ?? 0) as num).toStringAsFixed(0)} | ক্যাশ: TK ${((pharmacyStats['collected'] ?? 0) as num).toStringAsFixed(0)}",
                                  icon: Icons.local_pharmacy,
                                  color: Colors.green,
                                  isCompact: isCompact,
                                ),
                              ),
                            ],
                          ),

                          const SizedBox(height: 16),

                          // 3. Payout History Section (Matches Admin Panel Ledger)
                          Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: [
                              Text(
                                "💵 পরিশোধের ইতিহাস (Payouts)",
                                style: TextStyle(
                                  fontWeight: FontWeight.bold,
                                  fontSize: isCompact ? 12 : 14,
                                  color: Colors.grey.shade900,
                                ),
                              ),
                              Text(
                                "${payouts.length} টি রেকর্ড",
                                style: TextStyle(fontSize: isCompact ? 10 : 12, color: Colors.grey.shade600),
                              ),
                            ],
                          ),
                          const SizedBox(height: 6),

                          if (payouts.isEmpty)
                            Container(
                              width: double.infinity,
                              padding: const EdgeInsets.all(12),
                              decoration: BoxDecoration(
                                color: Colors.white,
                                borderRadius: BorderRadius.circular(8),
                                border: Border.all(color: Colors.grey.shade200),
                              ),
                              child: const Text(
                                "এখনও কোনো পরিশোধ রেকর্ড নেই। এডমিন প্যানেল থেকে পরিশোধ করলে এখানে স্বয়ংক্রিয়ভাবে খরচ ও পেমেন্ট আপডেট হবে।",
                                style: TextStyle(fontSize: 11, color: Colors.grey),
                                textAlign: TextAlign.center,
                              ),
                            )
                          else
                            ...payouts.map((p) {
                              String pDate = (p['payout_date'] ?? '').toString();
                              if (pDate.length > 10) pDate = pDate.substring(0, 10);
                              return Card(
                                margin: const EdgeInsets.only(bottom: 6),
                                elevation: 1,
                                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                                child: ListTile(
                                  dense: true,
                                  contentPadding: const EdgeInsets.symmetric(horizontal: 10, vertical: 2),
                                  leading: const CircleAvatar(
                                    radius: 16,
                                    backgroundColor: Color(0xFFDCFCE7),
                                    child: Icon(Icons.arrow_downward, color: Colors.green, size: 16),
                                  ),
                                  title: Text(
                                    "TK ${(p['amount'] as num).toStringAsFixed(2)}",
                                    style: const TextStyle(fontWeight: FontWeight.bold, color: Colors.green, fontSize: 13),
                                  ),
                                  subtitle: Text(
                                    "তারিখ: $pDate | মাধ্যম: ${p['payment_method'] ?? 'Cash'}${p['note'] != null && p['note'].toString().isNotEmpty ? ' (${p['note']})' : ''}",
                                    style: const TextStyle(fontSize: 10),
                                  ),
                                  trailing: const Text(
                                    "PAID",
                                    style: TextStyle(fontWeight: FontWeight.bold, color: Colors.green, fontSize: 11),
                                  ),
                                ),
                              );
                            }),

                          const SizedBox(height: 16),

                          // 4. Delivered Orders History Section
                          Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: [
                              Text(
                                "📦 ডেলিভার্ড অর্ডার ও কমিশন",
                                style: TextStyle(
                                  fontWeight: FontWeight.bold,
                                  fontSize: isCompact ? 12 : 14,
                                  color: Colors.grey.shade900,
                                ),
                              ),
                              Text(
                                "${deliveredOrders.length} টি সম্পন্ন",
                                style: TextStyle(fontSize: isCompact ? 10 : 12, color: Colors.grey.shade600),
                              ),
                            ],
                          ),
                          const SizedBox(height: 6),

                          if (deliveredOrders.isEmpty)
                            Container(
                              width: double.infinity,
                              padding: const EdgeInsets.all(12),
                              decoration: BoxDecoration(
                                color: Colors.white,
                                borderRadius: BorderRadius.circular(8),
                                border: Border.all(color: Colors.grey.shade200),
                              ),
                              child: const Text(
                                "এখনও কোনো ডেলিভার্ড অর্ডার নেই। কলাম ১ থেকে অর্ডার ডেলিভার সম্পন্ন করলে তার কমিশন এখানে যোগ হবে।",
                                style: TextStyle(fontSize: 11, color: Colors.grey),
                                textAlign: TextAlign.center,
                              ),
                            )
                          else
                            ...deliveredOrders.take(15).map((o) {
                              String dDate = (o['delivered_at'] ?? o['created_at'] ?? '').toString();
                              if (dDate.length > 16) dDate = dDate.substring(0, 16).replaceFirst('T', ' ');
                              final bool isPharmDel = o['is_pharmacy_order'] == true ||
                                  (o['order_number'] ?? '').toString().toUpperCase().startsWith('RX-');
                              return Card(
                                margin: const EdgeInsets.only(bottom: 6),
                                elevation: 1,
                                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                                child: Padding(
                                  padding: const EdgeInsets.all(8),
                                  child: Row(
                                    children: [
                                      Expanded(
                                        child: Column(
                                          crossAxisAlignment: CrossAxisAlignment.start,
                                          children: [
                                            Text(
                                              "${isPharmDel ? '💊' : '📦'} #${o['order_number']} (${isPharmDel ? 'ফার্মেসী' : 'সাধারণ'})",
                                              style: TextStyle(
                                                fontWeight: FontWeight.bold,
                                                fontSize: 12,
                                                color: isPharmDel ? Colors.green.shade800 : Colors.black87,
                                              ),
                                            ),
                                            Text(
                                              "👤 ${o['customer_name']} | 📍 ${o['area']}",
                                              style: TextStyle(fontSize: 10, color: Colors.grey.shade700),
                                            ),
                                            Text(
                                              "সময়: $dDate",
                                              style: TextStyle(fontSize: 9, color: Colors.grey.shade500),
                                            ),
                                          ],
                                        ),
                                      ),
                                      Column(
                                        crossAxisAlignment: CrossAxisAlignment.end,
                                        children: [
                                          Container(
                                            padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                                            decoration: BoxDecoration(
                                              color: Colors.purple.shade50,
                                              border: Border.all(color: Colors.purple.shade200),
                                              borderRadius: BorderRadius.circular(4),
                                            ),
                                            child: Text(
                                              "+TK ${(o['rider_fee'] as num).toStringAsFixed(0)}",
                                              style: TextStyle(
                                                fontWeight: FontWeight.bold,
                                                color: Colors.purple.shade800,
                                                fontSize: 11,
                                              ),
                                            ),
                                          ),
                                          const SizedBox(height: 2),
                                          Text(
                                            "COD: TK ${(o['total_amount'] as num).toStringAsFixed(0)}",
                                            style: TextStyle(fontSize: 10, color: Colors.grey.shade600),
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
                  ),
          ),
        ],
      ),
    );
  }

  Widget _buildStatMetricCard({
    required String title,
    required String value,
    required String subtitle,
    required IconData icon,
    required Color color,
    required bool isCompact,
  }) {
    return Container(
      padding: EdgeInsets.all(isCompact ? 8 : 10),
      decoration: BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: Colors.grey.shade200),
        boxShadow: const [
          BoxShadow(color: Color(0x05000000), blurRadius: 4, offset: Offset(0, 1)),
        ],
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              Icon(icon, size: isCompact ? 14 : 16, color: color),
              const SizedBox(width: 4),
              Expanded(
                child: Text(
                  title,
                  style: TextStyle(fontSize: isCompact ? 10 : 11, color: Colors.grey.shade600, fontWeight: FontWeight.w600),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ),
            ],
          ),
          const SizedBox(height: 4),
          Text(
            value,
            style: TextStyle(
              fontSize: isCompact ? 14 : 16,
              fontWeight: FontWeight.w800,
              color: color,
            ),
          ),
          const SizedBox(height: 2),
          Text(
            subtitle,
            style: TextStyle(fontSize: isCompact ? 8.5 : 9.5, color: Colors.grey.shade500),
            maxLines: 1,
            overflow: TextOverflow.ellipsis,
          ),
        ],
      ),
    );
  }
}
