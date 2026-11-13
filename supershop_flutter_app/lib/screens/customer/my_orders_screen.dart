import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:url_launcher/url_launcher.dart';
import '../../localization/app_localizations.dart';
import '../../models/online_order.dart';
import '../../models/product.dart';
import '../../services/api_service.dart';
import '../../widgets/app_image_loader.dart';
import '../auth/login_screen.dart';
import 'home_screen.dart';
import 'package_detail_screen.dart';
import 'pharmacy_screen.dart';
import 'product_detail_screen.dart';

class MyOrdersScreen extends StatefulWidget {
  final String? targetOrderNumber;
  const MyOrdersScreen({Key? key, this.targetOrderNumber}) : super(key: key);

  @override
  State<MyOrdersScreen> createState() => _MyOrdersScreenState();
}

class _MyOrdersScreenState extends State<MyOrdersScreen> with WidgetsBindingObserver {
  String _userPhone = '';
  bool _isLoadingPhone = true;
  bool _isFetchingOrders = false;
  bool _hasLoadedOrdersOnce = false;
  List<OnlineOrder> _orders = [];
  Timer? _countdownTimer;
  Timer? _livePollTimer;
  String? _currentTargetOrder;
  final Set<String> _expandedOrders = <String>{};
  List<Product>? _cachedProducts;
  List<dynamic>? _cachedPackages;
  bool _isNavigatingItem = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _currentTargetOrder = widget.targetOrderNumber?.trim();
    if (_currentTargetOrder != null && _currentTargetOrder!.isNotEmpty) {
      _expandedOrders.add(_currentTargetOrder!);
    }
    _loadUserPhone();
    _countdownTimer = Timer.periodic(const Duration(seconds: 1), (_) {
      if (!mounted) return;
      final hasActiveCancel = _orders.any((o) {
        if (!['new', 'pending', 'verified'].contains(o.orderStatus)) return false;
        final dt = DateTime.tryParse(o.createdAt);
        return dt != null && DateTime.now().difference(dt).inSeconds < 600;
      });
      if (hasActiveCancel) {
        setState(() {});
      }
    });
    _livePollTimer = Timer.periodic(const Duration(seconds: 4), (_) {
      if (_userPhone.isNotEmpty) {
        _fetchOrders(silent: true);
      }
    });
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed && _userPhone.isNotEmpty) {
      _fetchOrders(silent: true);
    }
  }

  @override
  void dispose() {
    WidgetsBinding.instance.removeObserver(this);
    _countdownTimer?.cancel();
    _livePollTimer?.cancel();
    super.dispose();
  }

  int _asIntVal(dynamic v, [int fb = 0]) {
    if (v == null) return fb;
    if (v is int) return v;
    if (v is num) return v.toInt();
    return int.tryParse(v.toString()) ?? fb;
  }

  String _cleanItemName(String raw) {
    return raw
        .replaceAll(
          RegExp(r'^[\s📦💊🏥🛍️]+|\[(PHARMACY|COMBO|PACKAGE|RX)\]', caseSensitive: false),
          ' ',
        )
        .replaceAll(RegExp(r'\s+'), ' ')
        .trim();
  }

  Future<void> _openPharmacySearch([String query = '']) async {
    if (!mounted) return;
    await Navigator.push(
      context,
      MaterialPageRoute(
        builder: (ctx) => Scaffold(
          body: SafeArea(
            child: PharmacyScreen(
              initialSearchQuery: query,
              onBackToHome: () => Navigator.of(ctx).pop(),
            ),
          ),
        ),
      ),
    );
  }

  Future<void> _openOrderItem(OrderItem item, OnlineOrder order) async {
    if (_isNavigatingItem) return;
    setState(() => _isNavigatingItem = true);

    try {
      final cleanName = _cleanItemName(item.productName);
      final lowerName = cleanName.toLowerCase();
      final bool isPkg = item.isPackage ||
          item.packageId > 0 ||
          item.productName.contains('📦') ||
          lowerName.contains('package') ||
          lowerName.contains('combo');
      final bool isMed = item.isMedicine ||
          item.medicineId > 0 ||
          item.productName.contains('💊') ||
          (order.isPharmacyOrder && !isPkg && item.productId <= 0);

      if (isMed) {
        String medQuery = cleanName
            .replaceAll(RegExp(r'\s*\([^)]*\)\s*'), ' ')
            .replaceAll(
              RegExp(r'\s+\d+(?:\.\d+)?\s*(?:mg|ml|mcg|gm|g|iu|%)\b', caseSensitive: false),
              '',
            )
            .replaceAll(RegExp(r'\s+'), ' ')
            .trim();
        if (medQuery.isEmpty) medQuery = cleanName;
        if (medQuery.toLowerCase().contains('prescription order') ||
            medQuery.contains('প্রেসক্রিপশন') ||
            medQuery.contains('প্রেশক্রিপশন')) {
          medQuery = '';
        }
        await _openPharmacySearch(medQuery);
        return;
      }

      if (isPkg) {
        _cachedPackages ??= await ApiService.getPackages();
        final packages = _cachedPackages ?? [];
        Map<String, dynamic>? matchedPkg;
        final targetPkgName = (item.packageName.isNotEmpty ? item.packageName : cleanName).toLowerCase();

        for (final rawPkg in packages) {
          if (rawPkg is! Map) continue;
          final pkg = Map<String, dynamic>.from(rawPkg);
          final pid = _asIntVal(pkg['id']);
          if ((item.packageId > 0 && pid == item.packageId) ||
              (item.productId > 0 && pid == item.productId)) {
            matchedPkg = pkg;
            break;
          }
          final pName = (pkg['package_name'] ?? pkg['name'] ?? '').toString().trim().toLowerCase();
          if (pName.isNotEmpty && pName == targetPkgName) {
            matchedPkg = pkg;
            break;
          }
        }
        if (matchedPkg == null && targetPkgName.isNotEmpty) {
          for (final rawPkg in packages) {
            if (rawPkg is! Map) continue;
            final pkg = Map<String, dynamic>.from(rawPkg);
            final pName = (pkg['package_name'] ?? pkg['name'] ?? '').toString().trim().toLowerCase();
            if (pName.isNotEmpty && (pName.contains(targetPkgName) || targetPkgName.contains(pName))) {
              matchedPkg = pkg;
              break;
            }
          }
        }

        if (matchedPkg == null && (item.packageItems.isNotEmpty || item.packageId > 0)) {
          matchedPkg = <String, dynamic>{
            'id': item.packageId > 0 ? item.packageId : item.productId,
            'package_name': item.packageName.isNotEmpty ? item.packageName : cleanName,
            'package_price': item.packagePrice > 0 ? item.packagePrice : item.unitPrice,
            'image_url': item.packageImage.isNotEmpty ? item.packageImage : item.imageUrl,
            'description': item.packageDescription,
            'items': item.packageItems,
          };
        }

        if (!mounted) return;
        if (matchedPkg != null) {
          await Navigator.push(
            context,
            MaterialPageRoute(
              builder: (_) => PackageDetailScreen(packageData: matchedPkg!),
            ),
          );
        } else {
          ScaffoldMessenger.of(context).showSnackBar(
            const SnackBar(content: Text('এই কম্বো প্যাকেজটি বর্তমানে পাওয়া যায়নি')),
          );
        }
        return;
      }

      // Normal retail product
      _cachedProducts ??= await ApiService.fetchProducts();
      final products = _cachedProducts ?? [];
      Product? matchedProduct;

      if (item.productId > 0) {
        for (final p in products) {
          if (p.id == item.productId) {
            matchedProduct = p;
            break;
          }
        }
      }
      if (matchedProduct == null && lowerName.isNotEmpty) {
        for (final p in products) {
          if (p.name.trim().toLowerCase() == lowerName) {
            matchedProduct = p;
            break;
          }
        }
      }
      if (matchedProduct == null && lowerName.isNotEmpty) {
        for (final p in products) {
          final pn = p.name.trim().toLowerCase();
          if (pn.isNotEmpty && (pn.contains(lowerName) || lowerName.contains(pn))) {
            matchedProduct = p;
            break;
          }
        }
      }

      if (!mounted) return;
      if (matchedProduct != null) {
        await Navigator.push(
          context,
          MaterialPageRoute(
            builder: (_) => ProductDetailScreen(product: matchedProduct!),
          ),
        );
      } else {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text('প্রোডাক্টটি বর্তমানে স্টকে বা ক্যাটালগে পাওয়া যায়নি')),
        );
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(content: Text('বিস্তারিত খোলা যায়নি: $e')),
        );
      }
    } finally {
      if (mounted) setState(() => _isNavigatingItem = false);
    }
  }

  bool _isPdfUrl(String url) {
    final low = url.trim().toLowerCase();
    return low.endsWith('.pdf') || low.contains('/pdf') || low.startsWith('data:application/pdf');
  }

  Future<void> _openPrescriptionZoom(String primaryUrl, {String originalUrl = ''}) async {
    final cleanPrimary = AppImageLoader.cleanUrl(primaryUrl);
    final cleanOriginal = originalUrl.trim().isNotEmpty ? AppImageLoader.cleanUrl(originalUrl) : '';
    final target = cleanPrimary.isNotEmpty ? cleanPrimary : cleanOriginal;
    if (target.isEmpty) return;

    if (_isPdfUrl(target)) {
      final uri = Uri.tryParse(target);
      if (uri != null && await canLaunchUrl(uri)) {
        await launchUrl(uri, mode: LaunchMode.externalApplication);
      }
      return;
    }

    if (!mounted) return;
    final hasDual = cleanPrimary.isNotEmpty && cleanOriginal.isNotEmpty && cleanPrimary != cleanOriginal;
    String activeUrl = target;

    await showDialog<void>(
      context: context,
      barrierColor: Colors.black87,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setModalState) => Dialog(
          backgroundColor: Colors.black,
          insetPadding: const EdgeInsets.all(10),
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
          child: Column(
            children: [
              Padding(
                padding: const EdgeInsets.fromLTRB(14, 10, 8, 6),
                child: Row(
                  children: [
                    const Expanded(
                      child: Text(
                        '📋 প্রেসক্রিপশন প্রিভিউ',
                        style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 15),
                      ),
                    ),
                    IconButton(
                      onPressed: () => Navigator.of(ctx).pop(),
                      icon: const Icon(Icons.close, color: Colors.white),
                    ),
                  ],
                ),
              ),
              if (hasDual)
                Padding(
                  padding: const EdgeInsets.only(bottom: 8),
                  child: Wrap(
                    spacing: 8,
                    children: [
                      ChoiceChip(
                        label: const Text('✨ স্ক্যান / এডিটেড'),
                        selected: activeUrl == cleanPrimary,
                        onSelected: (_) => setModalState(() => activeUrl = cleanPrimary),
                      ),
                      ChoiceChip(
                        label: const Text('📷 অরিজিনাল ছবি'),
                        selected: activeUrl == cleanOriginal,
                        onSelected: (_) => setModalState(() => activeUrl = cleanOriginal),
                      ),
                    ],
                  ),
                ),
              Expanded(
                child: ClipRRect(
                  borderRadius: BorderRadius.circular(10),
                  child: InteractiveViewer(
                    minScale: 0.8,
                    maxScale: 5.0,
                    child: Center(
                      child: AppImageLoader(
                        imageUrl: activeUrl,
                        fit: BoxFit.contain,
                      ),
                    ),
                  ),
                ),
              ),
              const Padding(
                padding: EdgeInsets.symmetric(vertical: 8),
                child: Text(
                  'দুই আঙুলে জুম করে প্রেসক্রিপশন ভালোভাবে দেখুন',
                  style: TextStyle(color: Colors.white70, fontSize: 11.5),
                ),
              ),
            ],
          ),
        ),
      ),
    );
  }

  Widget _buildPrescriptionPreviewSection(OnlineOrder order) {
    final primaryRx = order.prescriptionUrl.isNotEmpty
        ? order.prescriptionUrl
        : (order.prescriptionEnhancedUrl.isNotEmpty
            ? order.prescriptionEnhancedUrl
            : order.prescriptionOriginalUrl);
    final originalRx = order.prescriptionOriginalUrl;
    if (primaryRx.isEmpty && originalRx.isEmpty) {
      return const SizedBox.shrink();
    }

    final displayUrl = primaryRx.isNotEmpty ? primaryRx : originalRx;
    final isPdf = _isPdfUrl(displayUrl);
    final hasOriginalSeparate =
        originalRx.isNotEmpty && primaryRx.isNotEmpty && originalRx != primaryRx && !_isPdfUrl(originalRx);

    return Container(
      margin: const EdgeInsets.only(top: 10, bottom: 8),
      padding: const EdgeInsets.all(10),
      decoration: BoxDecoration(
        color: const Color(0xFFF0FDFA),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(color: Colors.teal.shade200),
      ),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Row(
            children: [
              const Icon(Icons.medical_information, size: 17, color: Color(0xFF0F766E)),
              const SizedBox(width: 6),
              const Expanded(
                child: Text(
                  'সংযুক্ত প্রেসক্রিপশন',
                  style: TextStyle(
                    fontWeight: FontWeight.bold,
                    fontSize: 12.5,
                    color: Color(0xFF0F766E),
                  ),
                ),
              ),
              if (hasOriginalSeparate)
                InkWell(
                  onTap: () => _openPrescriptionZoom(originalRx, originalUrl: originalRx),
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                    decoration: BoxDecoration(
                      color: Colors.white,
                      borderRadius: BorderRadius.circular(12),
                      border: Border.all(color: Colors.teal.shade300),
                    ),
                    child: const Text(
                      '📷 অরিজিনাল',
                      style: TextStyle(fontSize: 10.5, fontWeight: FontWeight.w700, color: Color(0xFF0F766E)),
                    ),
                  ),
                ),
            ],
          ),
          const SizedBox(height: 8),
          if (isPdf)
            InkWell(
              onTap: () => _openPrescriptionZoom(displayUrl, originalUrl: originalRx),
              borderRadius: BorderRadius.circular(8),
              child: Container(
                width: double.infinity,
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                decoration: BoxDecoration(
                  color: Colors.white,
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: Colors.teal.shade200),
                ),
                child: const Row(
                  children: [
                    Icon(Icons.picture_as_pdf, color: Colors.redAccent, size: 22),
                    SizedBox(width: 8),
                    Expanded(
                      child: Text(
                        'প্রেসক্রিপশন PDF দেখুন / ডাউনলোড করুন',
                        style: TextStyle(fontSize: 12.5, fontWeight: FontWeight.w600, color: Color(0xFF0F172A)),
                      ),
                    ),
                    Icon(Icons.open_in_new, size: 16, color: Colors.teal),
                  ],
                ),
              ),
            )
          else
            InkWell(
              onTap: () => _openPrescriptionZoom(displayUrl, originalUrl: originalRx),
              borderRadius: BorderRadius.circular(8),
              child: Stack(
                children: [
                  ClipRRect(
                    borderRadius: BorderRadius.circular(8),
                    child: AppImageLoader(
                      imageUrl: displayUrl,
                      height: 145,
                      width: double.infinity,
                      fit: BoxFit.cover,
                    ),
                  ),
                  Positioned(
                    right: 8,
                    bottom: 8,
                    child: Container(
                      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 4),
                      decoration: BoxDecoration(
                        color: Colors.black.withValues(alpha: 0.72),
                        borderRadius: BorderRadius.circular(14),
                      ),
                      child: const Row(
                        mainAxisSize: MainAxisSize.min,
                        children: [
                          Icon(Icons.zoom_in, color: Colors.white, size: 14),
                          SizedBox(width: 4),
                          Text(
                            'ট্যাপ করে বড় করুন',
                            style: TextStyle(color: Colors.white, fontSize: 10.5, fontWeight: FontWeight.w600),
                          ),
                        ],
                      ),
                    ),
                  ),
                ],
              ),
            ),
        ],
      ),
    );
  }

  Widget _buildFullOrderDetailsSection(OnlineOrder order) {
    final fullAddress = [
      order.addressDetails,
      order.area,
      order.district,
      order.country,
    ].map((e) => e.trim()).where((e) => e.isNotEmpty).join(', ');
    final computedSubtotal =
        order.subtotal > 0 ? order.subtotal : (order.totalAmount - order.deliveryCharge);
    final isExpanded = _expandedOrders.contains(order.orderNumber);

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        const SizedBox(height: 8),
        InkWell(
          onTap: () {
            setState(() {
              if (isExpanded) {
                _expandedOrders.remove(order.orderNumber);
              } else {
                _expandedOrders.add(order.orderNumber);
              }
            });
          },
          borderRadius: BorderRadius.circular(8),
          child: Container(
            width: double.infinity,
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
            decoration: BoxDecoration(
              color: const Color(0xFFF8FAFC),
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: const Color(0xFFE2E8F0)),
            ),
            child: Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                const Text(
                  '📋 সম্পূর্ণ অর্ডার বিবরণ (ঠিকানা ও বিল)',
                  style: TextStyle(fontSize: 12, fontWeight: FontWeight.w700, color: Color(0xFF334155)),
                ),
                Icon(
                  isExpanded ? Icons.keyboard_arrow_up : Icons.keyboard_arrow_down,
                  size: 18,
                  color: const Color(0xFF475569),
                ),
              ],
            ),
          ),
        ),
        if (isExpanded)
          Container(
            width: double.infinity,
            margin: const EdgeInsets.only(top: 6),
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              color: const Color(0xFFF8FAFC),
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: const Color(0xFFE2E8F0)),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                if (order.customerName.isNotEmpty || order.customerPhone.isNotEmpty)
                  Text(
                    '👤 ${order.customerName} (${order.customerPhone})',
                    style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: Color(0xFF1E293B)),
                  ),
                if (fullAddress.isNotEmpty) ...[
                  const SizedBox(height: 4),
                  Text(
                    '📍 ঠিকানা: $fullAddress',
                    style: const TextStyle(fontSize: 12, color: Color(0xFF475569), height: 1.35),
                  ),
                ],
                if (order.isPharmacyOrder || order.overallDurationDays > 0) ...[
                  const SizedBox(height: 4),
                  Text(
                    order.overallDurationDays > 0
                        ? '⏱️ কয়দিনের ঔষধ: ${order.overallDurationDays} দিন'
                        : '⏱️ কয়দিনের ঔষধ: 📝 নোটে উল্লিখিত',
                    style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: Color(0xFF0F766E)),
                  ),
                ],
                if (order.customerNotes.isNotEmpty) ...[
                  const SizedBox(height: 4),
                  Text(
                    '📝 নোট: ${order.customerNotes}',
                    style: const TextStyle(fontSize: 12, color: Color(0xFF334155), height: 1.35),
                  ),
                ],
                const Divider(height: 14),
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    const Text('আইটেম মূল্য (Subtotal):', style: TextStyle(fontSize: 12, color: Color(0xFF475569))),
                    Text('TK ${computedSubtotal.toStringAsFixed(0)}', style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600)),
                  ],
                ),
                const SizedBox(height: 3),
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    const Text('ডেলিভারি চার্জ:', style: TextStyle(fontSize: 12, color: Color(0xFF475569))),
                    Text('TK ${order.deliveryCharge.toStringAsFixed(0)}', style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600)),
                  ],
                ),
                const SizedBox(height: 3),
                Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    const Text('পেমেন্ট স্ট্যাটাস:', style: TextStyle(fontSize: 12, color: Color(0xFF475569))),
                    Text(
                      order.paymentStatus.isNotEmpty ? order.paymentStatus.toUpperCase() : 'PENDING',
                      style: TextStyle(
                        fontSize: 11.5,
                        fontWeight: FontWeight.bold,
                        color: order.paymentStatus.toLowerCase() == 'paid' ? Colors.green : Colors.orange.shade800,
                      ),
                    ),
                  ],
                ),
              ],
            ),
          ),
      ],
    );
  }

  void _loadUserPhone() async {
    final prefs = await SharedPreferences.getInstance();
    final phone = (prefs.getString('user_phone') ?? '').trim();
    List<OnlineOrder> cachedOrders = [];
    if (phone.isNotEmpty) {
      final raw = prefs.getString('cached_my_orders_$phone') ?? '';
      if (raw.isNotEmpty) {
        try {
          final list = jsonDecode(raw);
          if (list is List) {
            cachedOrders = list
                .whereType<Map>()
                .map((m) => OnlineOrder.fromJson(Map<String, dynamic>.from(m)))
                .toList();
          }
        } catch (_) {}
      }
    }
    if (!mounted) return;
    setState(() {
      _userPhone = phone;
      _isLoadingPhone = false;
      if (cachedOrders.isNotEmpty) {
        _orders = cachedOrders;
        _hasLoadedOrdersOnce = true;
      }
    });
    if (phone.isNotEmpty) {
      await _fetchOrders(silent: cachedOrders.isNotEmpty);
    }
  }

  Future<void> _fetchOrders({bool silent = false}) async {
    if (_userPhone.isEmpty || _isFetchingOrders) return;
    _isFetchingOrders = true;
    try {
      final res = await ApiService.fetchMyOrdersNullable(_userPhone);
      if (!mounted) return;
      if (res != null) {
        setState(() {
          _orders = res;
          _hasLoadedOrdersOnce = true;
        });
        try {
          final prefs = await SharedPreferences.getInstance();
          final rawList = res.map((o) => {
            'id': o.id,
            'order_number': o.orderNumber,
            'customer_name': o.customerName,
            'customer_phone': o.customerPhone,
            'customer_email': o.customerEmail,
            'country': o.country,
            'district': o.district,
            'area': o.area,
            'address_details': o.addressDetails,
            'payment_method': o.paymentMethod,
            'payment_status': o.paymentStatus,
            'subtotal': o.subtotal,
            'delivery_charge': o.deliveryCharge,
            'total_amount': o.totalAmount,
            'order_status': o.orderStatus,
            'delivery_otp': o.deliveryOtp,
            'assigned_rider_name': o.assignedRiderName,
            'assigned_rider_phone': o.assignedRiderPhone,
            'created_at': o.createdAt,
            'created_at_bd': o.createdAtBd,
            'confirmed_at': o.confirmedAt,
            'packed_at': o.packedAt,
            'on_the_way_at': o.onTheWayAt,
            'delivered_at': o.deliveredAt,
            'cancelled_at': o.cancelledAt,
            'is_pharmacy_order': o.isPharmacyOrder,
            'prescription_url': o.prescriptionUrl,
            'prescription_original_url': o.prescriptionOriginalUrl,
            'prescription_enhanced_url': o.prescriptionEnhancedUrl,
            'overall_duration_days': o.overallDurationDays,
            'customer_notes': o.customerNotes,
            'pharmacy_order_type': o.pharmacyOrderType,
            'timeline': o.timeline.map((t) => {
              'stage': t.stage,
              'title': t.title,
              'time': t.time,
              'time_bd': t.timeBd,
              'done': t.done,
              'active': t.active,
            }).toList(),
            'items': o.items.map((it) => {
              'id': it.id,
              'product_id': it.productId,
              'product_name': it.productName,
              'unit_price': it.unitPrice,
              'mrp_price': it.mrpPrice,
              'quantity': it.quantity,
              'total_price': it.totalPrice,
              'is_package': it.isPackage,
              'package_id': it.packageId,
              'package_name': it.packageName,
              'package_price': it.packagePrice,
              'package_image': it.packageImage,
              'package_description': it.packageDescription,
              'package_items': it.packageItems,
              'is_medicine': it.isMedicine,
              'medicine_id': it.medicineId,
              'generic_name': it.genericName,
              'strength': it.strength,
              'dosage_form': it.dosageForm,
              'image_url': it.imageUrl,
            }).toList(),
          }).toList();
          await prefs.setString('cached_my_orders_$_userPhone', jsonEncode(rawList));
        } catch (_) {}
      } else if (!silent && mounted) {
        setState(() {
          _hasLoadedOrdersOnce = true;
        });
      }
    } finally {
      _isFetchingOrders = false;
    }
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

  String _formatTimelineTime(OrderTimelineStep step) {
    if (step.timeBd.isNotEmpty) {
      return step.timeBd.replaceAll(', ', '\n');
    }
    if (step.time.isEmpty) return '';
    try {
      DateTime dt = DateTime.parse(step.time).toUtc().add(const Duration(hours: 6));
      final months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
      final month = months[dt.month - 1];
      final day = dt.day;
      final hour = dt.hour % 12 == 0 ? 12 : dt.hour % 12;
      final min = dt.minute.toString().padLeft(2, '0');
      final ampm = dt.hour >= 12 ? 'PM' : 'AM';
      return '$day $month\n$hour:$min $ampm';
    } catch (_) {
      return step.time.length >= 16 ? step.time.substring(5, 16).replaceAll('T', ' ') : step.time;
    }
  }

  String _formatBdDate(String isoStr, [String bdFormatted = '']) {
    if (bdFormatted.isNotEmpty) return bdFormatted;
    if (isoStr.isEmpty) return '';
    try {
      DateTime dt = DateTime.parse(isoStr).toUtc().add(const Duration(hours: 6));
      final months = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
      final month = months[dt.month - 1];
      final day = dt.day;
      final year = dt.year;
      final hour = dt.hour % 12 == 0 ? 12 : dt.hour % 12;
      final min = dt.minute.toString().padLeft(2, '0');
      final ampm = dt.hour >= 12 ? 'PM' : 'AM';
      return '$day $month $year, $hour:$min $ampm';
    } catch (_) {
      return isoStr.length >= 16 ? isoStr.substring(0, 16).replaceAll('T', ' ') : isoStr;
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
          OrderTimelineStep(stage: 'placed', title: 'Placed', time: order.createdAt, timeBd: order.createdAtBd, done: true, active: false),
          OrderTimelineStep(stage: 'cancelled', title: 'Cancelled', time: order.cancelledAt, done: true, active: true),
        ];
      } else {
        steps = [
          OrderTimelineStep(stage: 'placed', title: 'Placed', time: order.createdAt, timeBd: order.createdAtBd, done: true, active: st == 'new' || st == 'pending'),
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
                          (step.time.isNotEmpty || step.timeBd.isNotEmpty)
                              ? _formatTimelineTime(step)
                              : (isDone ? 'Done' : 'Pending'),
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
        actions: [
          if (_userPhone.isNotEmpty)
            IconButton(
              icon: const Icon(Icons.refresh, color: Colors.white),
              tooltip: "Refresh Orders",
              onPressed: () => _fetchOrders(silent: false),
            ),
        ],
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
              : (!_hasLoadedOrdersOnce && _orders.isEmpty)
                  ? const Center(child: CircularProgressIndicator())
                  : _orders.isEmpty
                      ? RefreshIndicator(
                          onRefresh: () => _fetchOrders(silent: false),
                          child: ListView(
                            physics: const AlwaysScrollableScrollPhysics(),
                            children: const [
                              SizedBox(height: 160),
                              Center(
                                child: Text(
                                  "You have no previous orders",
                                  style: TextStyle(fontSize: 15, color: Colors.grey),
                                ),
                              ),
                            ],
                          ),
                        )
                      : Builder(
                          builder: (context) {
                            List<OnlineOrder> orders = List.from(_orders);
                            if (_currentTargetOrder != null && _currentTargetOrder!.isNotEmpty) {
                              int targetIdx = orders.indexWhere((o) {
                                final t = _currentTargetOrder!.toLowerCase();
                                return o.orderNumber.toLowerCase() == t ||
                                    o.id.toString() == t ||
                                    o.orderNumber.toLowerCase().contains(t) ||
                                    t.contains(o.orderNumber.toLowerCase());
                              });
                              if (targetIdx > 0) {
                                final targetOrder = orders.removeAt(targetIdx);
                                orders.insert(0, targetOrder);
                              }
                            }

                            return RefreshIndicator(
                              onRefresh: () => _fetchOrders(silent: false),
                              child: ListView.builder(
                                padding: const EdgeInsets.all(12),
                                itemCount: orders.length,
                                itemBuilder: (context, index) {
                                  final order = orders[index];
                        final bool isTargetOrder = _currentTargetOrder != null &&
                            _currentTargetOrder!.isNotEmpty &&
                            (order.orderNumber.toLowerCase() == _currentTargetOrder!.toLowerCase() ||
                             order.id.toString() == _currentTargetOrder!.toLowerCase() ||
                             order.orderNumber.toLowerCase().contains(_currentTargetOrder!.toLowerCase()) ||
                             _currentTargetOrder!.toLowerCase().contains(order.orderNumber.toLowerCase()));

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
                            border: Border.all(
                              color: isTargetOrder ? Colors.blue.shade600 : Colors.grey.shade300,
                              width: isTargetOrder ? 2.5 : 1.0,
                            ),
                            boxShadow: [
                              BoxShadow(
                                color: isTargetOrder
                                    ? Colors.blue.withValues(alpha: 0.18)
                                    : Colors.black.withValues(alpha: 0.04),
                                blurRadius: isTargetOrder ? 12 : 8,
                                spreadRadius: isTargetOrder ? 2 : 0,
                                offset: const Offset(0, 3),
                              ),
                            ],
                          ),
                          child: ClipRRect(
                            borderRadius: BorderRadius.circular(12),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                if (isTargetOrder)
                                  Container(
                                    width: double.infinity,
                                    padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                                    decoration: BoxDecoration(
                                      color: Colors.blue.shade50,
                                      border: Border(bottom: BorderSide(color: Colors.blue.shade200)),
                                    ),
                                    child: Row(
                                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                      children: [
                                        Row(
                                          children: [
                                            const Icon(Icons.notifications_active, color: Colors.blue, size: 16),
                                            const SizedBox(width: 6),
                                            Text(
                                              "Viewing Order: #${order.orderNumber}",
                                              style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 12, color: Colors.blue),
                                            ),
                                          ],
                                        ),
                                        InkWell(
                                          onTap: () {
                                            setState(() {
                                              _currentTargetOrder = null;
                                            });
                                          },
                                          child: Container(
                                            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                                            decoration: BoxDecoration(
                                              color: Colors.white,
                                              borderRadius: BorderRadius.circular(4),
                                              border: Border.all(color: Colors.blue.shade300),
                                            ),
                                            child: const Text(
                                              "Show All Orders",
                                              style: TextStyle(fontSize: 11, color: Colors.blue, fontWeight: FontWeight.bold),
                                            ),
                                          ),
                                        ),
                                      ],
                                    ),
                                  ),

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
                                            '📅 ${_formatBdDate(order.createdAt, order.createdAtBd)}',
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

                                      // Attached Prescription Image / PDF Preview
                                      _buildPrescriptionPreviewSection(order),

                                      // Quick Pharmacy Requirement / Note summary pill
                                      if (order.isPharmacyOrder || order.customerNotes.isNotEmpty)
                                        Container(
                                          width: double.infinity,
                                          margin: const EdgeInsets.only(bottom: 8),
                                          padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
                                          decoration: BoxDecoration(
                                            color: const Color(0xFFFFFBEB),
                                            borderRadius: BorderRadius.circular(8),
                                            border: Border.all(color: Colors.amber.shade200),
                                          ),
                                          child: Column(
                                            crossAxisAlignment: CrossAxisAlignment.start,
                                            children: [
                                              Text(
                                                order.overallDurationDays > 0
                                                    ? '⏱️ কয়দিনের ঔষধ: ${order.overallDurationDays} দিন'
                                                    : '⏱️ কয়দিনের ঔষধ: 📝 নোটে উল্লিখিত',
                                                style: const TextStyle(
                                                  fontSize: 12,
                                                  fontWeight: FontWeight.w700,
                                                  color: Color(0xFF92400E),
                                                ),
                                              ),
                                              if (order.customerNotes.isNotEmpty) ...[
                                                const SizedBox(height: 3),
                                                Text(
                                                  '📝 নোট: ${order.customerNotes}',
                                                  style: const TextStyle(
                                                    fontSize: 12,
                                                    color: Color(0xFF78350F),
                                                    height: 1.3,
                                                  ),
                                                ),
                                              ],
                                            ],
                                          ),
                                        ),

                                      const Divider(),

                                // Order Items (Clickable -> Product / Combo / Medicine)
                                if (order.items.isEmpty && order.isPharmacyOrder)
                                  InkWell(
                                    onTap: () => _openPharmacySearch(''),
                                    borderRadius: BorderRadius.circular(8),
                                    child: Container(
                                      margin: const EdgeInsets.symmetric(vertical: 4),
                                      padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 9),
                                      decoration: BoxDecoration(
                                        color: const Color(0xFFF0FDFA),
                                        borderRadius: BorderRadius.circular(8),
                                        border: Border.all(color: Colors.teal.shade200),
                                      ),
                                      child: const Row(
                                        children: [
                                          Text('💊', style: TextStyle(fontSize: 16)),
                                          SizedBox(width: 8),
                                          Expanded(
                                            child: Text(
                                              'প্রেসক্রিপশন অর্ডার (ফার্মেসি পেইজ দেখুন)',
                                              style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600, color: Color(0xFF0F766E)),
                                            ),
                                          ),
                                          Icon(Icons.chevron_right, size: 18, color: Color(0xFF0F766E)),
                                        ],
                                      ),
                                    ),
                                  )
                                else
                                  Column(
                                    children: order.items.map((item) {
                                      final lowerName = item.productName.toLowerCase();
                                      final isPkg = item.isPackage ||
                                          item.packageId > 0 ||
                                          item.productName.contains('📦') ||
                                          lowerName.contains('package') ||
                                          lowerName.contains('combo');
                                      final isMed = item.isMedicine ||
                                          item.medicineId > 0 ||
                                          item.productName.contains('💊') ||
                                          (order.isPharmacyOrder && !isPkg && item.productId <= 0);
                                      final thumb = item.packageImage.isNotEmpty
                                          ? item.packageImage
                                          : item.imageUrl;

                                      return Container(
                                        margin: const EdgeInsets.symmetric(vertical: 3.5),
                                        decoration: BoxDecoration(
                                          color: const Color(0xFFF8FAFC),
                                          borderRadius: BorderRadius.circular(8),
                                          border: Border.all(color: const Color(0xFFE2E8F0)),
                                        ),
                                        child: InkWell(
                                          onTap: () => _openOrderItem(item, order),
                                          borderRadius: BorderRadius.circular(8),
                                          child: Padding(
                                            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 7),
                                            child: Row(
                                              crossAxisAlignment: CrossAxisAlignment.center,
                                              children: [
                                                if (thumb.isNotEmpty) ...[
                                                  ClipRRect(
                                                    borderRadius: BorderRadius.circular(6),
                                                    child: AppImageLoader(
                                                      imageUrl: thumb,
                                                      width: 34,
                                                      height: 34,
                                                      fit: BoxFit.cover,
                                                    ),
                                                  ),
                                                  const SizedBox(width: 8),
                                                ],
                                                Expanded(
                                                  child: Row(
                                                    crossAxisAlignment: CrossAxisAlignment.start,
                                                    children: [
                                                      if (isPkg)
                                                        Container(
                                                          margin: const EdgeInsets.only(right: 6, top: 2),
                                                          padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1.5),
                                                          decoration: BoxDecoration(
                                                            color: Colors.amber.shade100,
                                                            borderRadius: BorderRadius.circular(4),
                                                            border: Border.all(color: Colors.amber.shade300),
                                                          ),
                                                          child: const Text(
                                                            "COMBO",
                                                            style: TextStyle(fontSize: 9.5, fontWeight: FontWeight.bold, color: Colors.brown),
                                                          ),
                                                        )
                                                      else if (isMed)
                                                        Container(
                                                          margin: const EdgeInsets.only(right: 6, top: 2),
                                                          padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 1.5),
                                                          decoration: BoxDecoration(
                                                            color: Colors.teal.shade50,
                                                            borderRadius: BorderRadius.circular(4),
                                                            border: Border.all(color: Colors.teal.shade200),
                                                          ),
                                                          child: const Text(
                                                            "💊 Rx",
                                                            style: TextStyle(fontSize: 9.5, fontWeight: FontWeight.bold, color: Color(0xFF0F766E)),
                                                          ),
                                                        ),
                                                      Expanded(
                                                        child: Text(
                                                          '${item.productName} × ${item.quantity}',
                                                          style: const TextStyle(
                                                            fontSize: 13,
                                                            height: 1.35,
                                                            color: Color(0xFF1E293B),
                                                            fontWeight: FontWeight.w500,
                                                          ),
                                                          softWrap: true,
                                                        ),
                                                      ),
                                                    ],
                                                  ),
                                                ),
                                                const SizedBox(width: 8),
                                                Text(
                                                  'TK ${item.totalPrice.toStringAsFixed(0)}',
                                                  style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13, color: Color(0xFF0F172A)),
                                                ),
                                                const SizedBox(width: 4),
                                                const Icon(Icons.chevron_right, size: 17, color: Color(0xFF64748B)),
                                              ],
                                            ),
                                          ),
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

                                _buildFullOrderDetailsSection(order),

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
                    ),
                  );
                  },
                ),
    );
  }
}
