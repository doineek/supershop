import 'dart:async';
import 'dart:convert';
import 'dart:typed_data';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:url_launcher/url_launcher.dart';
import '../../models/delivery_area.dart';
import '../../providers/cart_provider.dart';
import '../../services/api_service.dart';
import '../../widgets/app_image_loader.dart';
import '../../widgets/prescription_crop_scan_dialog.dart';
import '../auth/login_screen.dart';

class PharmacyScreen extends StatefulWidget {
  final VoidCallback? onBackToHome;
  final String? initialSearchQuery;

  const PharmacyScreen({
    Key? key,
    this.onBackToHome,
    this.initialSearchQuery,
  }) : super(key: key);

  @override
  State<PharmacyScreen> createState() => _PharmacyScreenState();
}

class _PharmacyScreenState extends State<PharmacyScreen> {
  final ImagePicker _picker = ImagePicker();
  final ScrollController _pageScrollController = ScrollController();
  final GlobalKey _medCatalogKey = GlobalKey();
  final TextEditingController _medSearchController = TextEditingController();
  final TextEditingController _notesController = TextEditingController();
  final TextEditingController _nameController = TextEditingController();
  final TextEditingController _phoneController = TextEditingController();
  final TextEditingController _addressController = TextEditingController();

  // Shop / Pharmacy Settings
  String _helplinePhone = "+8801700000000";
  double _pharmacyDeliveryCharge = 50.0;

  // Delivery Areas
  List<DeliveryArea> _deliveryAreas = [];
  String _selectedDistrict = "Tangail";
  String _selectedArea = "Tangail Sadar";

  // Prescription Image State (Original + Cropped/Scanned)
  Uint8List? _rxOriginalBytes;
  String? _rxOriginalBase64DataUri;
  Uint8List? _rxBytes;
  String? _rxBase64DataUri;
  String _rxFileName = "";
  String _rxFilterName = "magic_color";
  bool _rxWasCropped = false;

  // Duration State (Default: 0 -> "নোটে লিখবো")
  int _selectedDurationDays = 0;

  // Medicines Catalog & Cart State
  List<dynamic> _medicines = [];
  bool _isLoadingMeds = false;
  String _searchQuery = "";
  String _selectedDosage = "all";
  Timer? _searchDebounce;
  int _searchSeq = 0;

  // Selected medicines for pharmacy order: medId -> Map
  final List<Map<String, dynamic>> _selectedItems = [];
  bool _isSubmitting = false;
  bool _isLoggedIn = false;

  static const List<Map<String, String>> _dosageForms = [
    {'label': 'সব ঔষধ', 'val': 'all'},
    {'label': '💊 Tablet', 'val': 'Tablet'},
    {'label': '💊 Capsule', 'val': 'Capsule'},
    {'label': '🍯 Syrup', 'val': 'Syrup'},
    {'label': '🧪 Suspension', 'val': 'Suspension'},
    {'label': '💉 Injection', 'val': 'Injection'},
    {'label': '🩹 Bandage', 'val': 'Bandage/First Aid'},
    {'label': '💧 Drops', 'val': 'Drops'},
    {'label': '🧴 Ointment', 'val': 'Ointment/Cream'},
    {'label': '💨 Inhaler', 'val': 'Inhaler'},
  ];

  @override
  void initState() {
    super.initState();
    final q = (widget.initialSearchQuery ?? '').trim();
    if (q.isNotEmpty) {
      _searchQuery = q;
      _medSearchController.text = q;
    }
    _initScreenData();
  }

  @override
  void didUpdateWidget(covariant PharmacyScreen oldWidget) {
    super.didUpdateWidget(oldWidget);
    final q = (widget.initialSearchQuery ?? '').trim();
    if (q.isNotEmpty && q != (oldWidget.initialSearchQuery ?? '').trim()) {
      setState(() {
        _searchQuery = q;
        _medSearchController.text = q;
      });
      _loadMedicines();
    }
  }

  @override
  void dispose() {
    _searchDebounce?.cancel();
    _pageScrollController.dispose();
    _medSearchController.dispose();
    _notesController.dispose();
    _nameController.dispose();
    _phoneController.dispose();
    _addressController.dispose();
    super.dispose();
  }

  Future<void> _initScreenData() async {
    await Future.wait([
      _loadCustomerAndSettings(),
      _loadDeliveryAreas(),
      _loadMedicines(),
    ]);
    if ((widget.initialSearchQuery ?? '').trim().isNotEmpty && mounted) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        _scrollToMedicineCatalog();
      });
    }
  }

  void _scrollToMedicineCatalog() {
    final ctx = _medCatalogKey.currentContext;
    if (ctx != null) {
      Scrollable.ensureVisible(
        ctx,
        duration: const Duration(milliseconds: 350),
        curve: Curves.easeOut,
      );
    }
  }

  Future<void> _loadCustomerAndSettings() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      final String phone = (prefs.getString('user_phone') ?? '').trim();
      final String name = (prefs.getString('user_name') ?? '').trim();
      final String addr = (prefs.getString('user_address') ?? '').trim();

      if (mounted) {
        setState(() {
          _isLoggedIn = phone.isNotEmpty;
          _phoneController.text = phone;
          _nameController.text = name;
          if (addr.isNotEmpty && _addressController.text.isEmpty) {
            _addressController.text = addr;
          }
        });
      }

      final settings = await ApiService.fetchShopSettings();
      if (mounted) {
        setState(() {
          final sup = (settings['customer_support_phone'] ?? settings['shop_phone'] ?? '').toString().trim();
          if (sup.isNotEmpty) _helplinePhone = sup;
          final pharmCharge = double.tryParse(settings['pharmacy_delivery_charge']?.toString() ?? '');
          final genCharge = double.tryParse(settings['delivery_charge']?.toString() ?? '');
          _pharmacyDeliveryCharge = pharmCharge ?? genCharge ?? 50.0;
        });
      }

      if (phone.isNotEmpty) {
        final prof = await ApiService.getCustomerProfile(phone);
        if (mounted && prof['success'] == true && prof['customer'] is Map) {
          final cust = prof['customer'] as Map;
          setState(() {
            final cName = (cust['name'] ?? '').toString().trim();
            final cAddr = (cust['address'] ?? '').toString().trim();
            final cDist = (cust['district'] ?? '').toString().trim();
            final cArea = (cust['area'] ?? '').toString().trim();
            if (cName.isNotEmpty) {
              _nameController.text = cName;
              prefs.setString('user_name', cName);
            }
            if (cAddr.isNotEmpty && _addressController.text.isEmpty) _addressController.text = cAddr;
            if (cDist.isNotEmpty) _selectedDistrict = cDist;
            if (cArea.isNotEmpty) _selectedArea = cArea;
          });
        }
      }
    } catch (e) {
      debugPrint("Pharmacy settings/profile load error: $e");
    }
  }

  Future<void> _loadDeliveryAreas() async {
    try {
      final areas = await ApiService.fetchDeliveryAreas();
      if (!mounted) return;
      final cartProv = Provider.of<CartProvider>(context, listen: false);
      setState(() {
        _deliveryAreas = areas;
        if (cartProv.selectedDistrict.isNotEmpty) {
          _selectedDistrict = cartProv.selectedDistrict;
        }
        if (cartProv.selectedArea.isNotEmpty) {
          _selectedArea = cartProv.selectedArea;
        }
      });
    } catch (_) {}
  }

  Future<void> _loadMedicines() async {
    if (!mounted) return;
    final int seq = ++_searchSeq;
    setState(() => _isLoadingMeds = true);
    try {
      final meds = await ApiService.fetchPharmacyMedicines(
        query: _searchQuery,
        dosage: _selectedDosage,
      );
      if (mounted && seq == _searchSeq) {
        setState(() {
          _medicines = meds;
          _isLoadingMeds = false;
        });
      }
    } catch (e) {
      if (mounted && seq == _searchSeq) {
        setState(() => _isLoadingMeds = false);
      }
    }
  }

  void _onSearchChanged(String val) {
    _searchDebounce?.cancel();
    _searchDebounce = Timer(const Duration(milliseconds: 140), () {
      if (mounted) {
        setState(() => _searchQuery = val);
        _loadMedicines();
      }
    });
  }

  Future<void> _pickPrescriptionImage(ImageSource source) async {
    try {
      final XFile? file = await _picker.pickImage(
        source: source,
        maxWidth: 2200,
        maxHeight: 2200,
        imageQuality: 92,
      );
      if (file == null) return;
      final Uint8List origBytes = await file.readAsBytes();
      final String origB64 = "data:image/jpeg;base64,${base64Encode(origBytes)}";

      if (!mounted) return;
      setState(() {
        _rxOriginalBytes = origBytes;
        _rxOriginalBase64DataUri = origB64;
        _rxBytes = origBytes;
        _rxBase64DataUri = origB64;
        _rxFileName = file.name;
        _rxFilterName = 'original';
        _rxWasCropped = false;
      });

      final edited = await PrescriptionCropScanDialog.show(context, origBytes);
      if (edited != null && mounted) {
        setState(() {
          _rxBytes = edited.processedBytes;
          _rxBase64DataUri = edited.processedDataUri;
          _rxFilterName = edited.filterName;
          _rxWasCropped = edited.isCropped;
        });
      }
    } catch (e) {
      if (!mounted) return;
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(
            source == ImageSource.camera
                ? "ক্যামেরা চালু করা যায়নি — অনুগ্রহ করে অ্যাপ সেটিংস থেকে ক্যামেরার অনুমতি দিন অথবা গ্যালারি ব্যবহার করুন।"
                : "গ্যালারি থেকে ছবি নেওয়া যায়নি: $e",
          ),
          backgroundColor: Colors.red.shade700,
        ),
      );
    }
  }

  Future<void> _editCurrentPrescription() async {
    final src = _rxOriginalBytes ?? _rxBytes;
    if (src == null) return;
    final edited = await PrescriptionCropScanDialog.show(context, src);
    if (edited != null && mounted) {
      setState(() {
        _rxBytes = edited.processedBytes;
        _rxBase64DataUri = edited.processedDataUri;
        _rxFilterName = edited.filterName;
        _rxWasCropped = edited.isCropped;
      });
    }
  }

  void _showFullPrescriptionPreview() {
    if (_rxBytes == null) return;
    showDialog(
      context: context,
      builder: (_) => Dialog(
        backgroundColor: Colors.black,
        insetPadding: const EdgeInsets.all(12),
        child: Stack(
          children: [
            InteractiveViewer(
              minScale: 0.5,
              maxScale: 4.0,
              child: Center(
                child: Image.memory(_rxBytes!, fit: BoxFit.contain),
              ),
            ),
            Positioned(
              top: 10,
              right: 10,
              child: CircleAvatar(
                backgroundColor: Colors.white,
                child: IconButton(
                  icon: const Icon(Icons.close, color: Colors.black),
                  onPressed: () => Navigator.pop(context),
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  void _addMedicineToOrder(Map<String, dynamic> med) {
    final int id = int.tryParse(med['id']?.toString() ?? '0') ?? 0;
    final int stock = int.tryParse(med['stock_qty']?.toString() ?? '999') ?? 999;
    if (stock <= 0) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text("দুঃখিত, এই ওষুধটি বর্তমানে স্টকে নেই।")),
      );
      return;
    }

    final int idx = _selectedItems.indexWhere((it) => it['medicine_id'] == id);
    setState(() {
      if (idx >= 0) {
        final int cur = _selectedItems[idx]['quantity'] as int;
        if (cur < stock) {
          _selectedItems[idx]['quantity'] = cur + 1;
        }
      } else {
        final double unitPrice = double.tryParse(
                med['sell_price']?.toString() ?? med['unit_price']?.toString() ?? '0') ??
            0.0;
        _selectedItems.add({
          'medicine_id': id,
          'name': med['name']?.toString() ?? 'Medicine',
          'generic_name': med['generic_name']?.toString() ?? '',
          'dosage_form': med['dosage_form']?.toString() ?? 'Tablet',
          'strength': med['strength']?.toString() ?? '',
          'manufacturer': med['manufacturer']?.toString() ?? '',
          'unit_price': unitPrice,
          'unit': 'পিস',
          'stock_qty': stock,
          'quantity': 1,
        });
      }
    });

    ScaffoldMessenger.of(context).hideCurrentSnackBar();
    ScaffoldMessenger.of(context).showSnackBar(
      SnackBar(
        duration: const Duration(milliseconds: 1200),
        backgroundColor: const Color(0xFF047857),
        behavior: SnackBarBehavior.floating,
        content: Text("💊 '${med['name']}' তালিকায় যোগ করা হয়েছে"),
      ),
    );
  }

  void _updateSelectedItemQty(int idx, int delta) {
    if (idx < 0 || idx >= _selectedItems.length) return;
    setState(() {
      final int cur = _selectedItems[idx]['quantity'] as int;
      final int stock = _selectedItems[idx]['stock_qty'] as int? ?? 999;
      final int next = cur + delta;
      if (next <= 0) {
        _selectedItems.removeAt(idx);
      } else if (next <= stock) {
        _selectedItems[idx]['quantity'] = next;
      }
    });
  }

  Future<void> _showSubstitutesSheet(Map<String, dynamic> med) async {
    final String generic = (med['generic_name'] ?? '').toString().trim();
    final int medId = int.tryParse(med['id']?.toString() ?? '0') ?? 0;
    if (generic.isEmpty) return;

    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (_) => _SubstitutesModal(
        brandName: med['name']?.toString() ?? '',
        genericName: generic,
        excludeId: medId,
        onSelectSubstitute: (sub) {
          Navigator.pop(context);
          _addMedicineToOrder(sub);
        },
      ),
    );
  }

  double get _itemsSubtotal {
    double sum = 0.0;
    for (final it in _selectedItems) {
      sum += (it['unit_price'] as double) * (it['quantity'] as int);
    }
    return sum;
  }

  Future<void> _submitOrder() async {
    final prefs = await SharedPreferences.getInstance();
    final String savedPhoneRaw = (prefs.getString('user_phone') ?? '').trim();
    final String savedNameRaw = (prefs.getString('user_name') ?? '').trim();

    if (savedPhoneRaw.isEmpty) {
      if (!mounted) return;
      showDialog(
        context: context,
        builder: (dialogCtx) => AlertDialog(
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
          title: const Row(
            children: [
              Icon(Icons.lock, color: Color(0xFF047857)),
              SizedBox(width: 8),
              Text("লগইন প্রয়োজন"),
            ],
          ),
          content: const Text("অর্ডার করতে অনুগ্রহ করে আপনার একাউন্টে লগইন বা রেজিস্ট্রেশন করুন। আপনার একাউন্টের নাম ও মোবাইল নম্বর স্বয়ংক্রিয়ভাবে ব্যবহৃত হবে।"),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogCtx),
              child: const Text("বাতিল"),
            ),
            ElevatedButton(
              onPressed: () async {
                Navigator.pop(dialogCtx);
                await Navigator.push(
                  context,
                  MaterialPageRoute(builder: (_) => const LoginScreen()),
                );
                _loadCustomerAndSettings();
              },
              style: ElevatedButton.styleFrom(backgroundColor: const Color(0xFF047857), foregroundColor: Colors.white),
              child: const Text("লগইন / রেজিস্টার"),
            ),
          ],
        ),
      );
      return;
    }

    String phone = savedPhoneRaw.replaceAll(RegExp(r'[^\d]'), '');
    if (phone.startsWith('88') && phone.length == 13) {
      phone = phone.substring(2);
    }
    final String name = savedNameRaw.isNotEmpty ? savedNameRaw : _nameController.text.trim();
    final String address = _addressController.text.trim();
    final String notes = _notesController.text.trim();

    if (_rxBase64DataUri == null && _selectedItems.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          backgroundColor: Colors.red,
          content: Text("অনুগ্রহ করে প্রেসক্রিপশনের ছবি আপলোড করুন অথবা ওষুধ নির্বাচন করুন।"),
        ),
      );
      return;
    }

    if (_rxBase64DataUri != null && _selectedItems.isEmpty && _selectedDurationDays <= 0 && notes.length < 2) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          backgroundColor: Colors.orange,
          content: Text("প্রেসক্রিপশনের সাথে অবশ্যই কত দিনের ওষুধ লাগবে সিলেক্ট করুন বা নোট লিখুন।"),
        ),
      );
      return;
    }

    if (phone.length != 11 || !phone.startsWith('01')) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          backgroundColor: Colors.red,
          content: Text("আপনার লগইন করা মোবাইল নম্বরটি সঠিক ১১ ডিজিটের নয়।"),
        ),
      );
      return;
    }

    if (address.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          backgroundColor: Colors.red,
          content: Text("অনুগ্রহ করে আপনার সম্পূর্ণ ডেলিভারি ঠিকানা লিখুন।"),
        ),
      );
      return;
    }

    setState(() => _isSubmitting = true);

    final String email = prefs.getString('user_email') ?? '';

    final List<Map<String, dynamic>> orderItems = _selectedItems
        .map((it) => {
              'medicine_id': it['medicine_id'],
              'name': it['name'],
              'generic_name': it['generic_name'],
              'dosage_form': it['dosage_form'],
              'strength': it['strength'],
              'quantity': it['quantity'],
              'unit': it['unit'],
              'unit_price': it['unit_price'],
              'duration_days': _selectedDurationDays > 0 ? '$_selectedDurationDays দিন' : 'নোটে উল্লিখিত',
            })
        .toList();

    final res = await ApiService.placePharmacyOrder(
      customerName: name.isEmpty ? "সম্মানিত গ্রাহক" : name,
      customerPhone: phone,
      customerEmail: email,
      district: _selectedDistrict,
      area: _selectedArea,
      deliveryAddress: address,
      overallDurationDays: _selectedDurationDays,
      customerNotes: notes,
      prescriptionBase64: _rxBase64DataUri,
      prescriptionOriginalBase64: _rxOriginalBase64DataUri ?? _rxBase64DataUri,
      items: orderItems,
    );

    if (!mounted) return;
    setState(() => _isSubmitting = false);

    if (res['success'] == true) {
      final String orderNum = res['order_number']?.toString() ?? '';
      final String otp = res['delivery_otp']?.toString() ?? '';

      setState(() {
        _rxOriginalBytes = null;
        _rxOriginalBase64DataUri = null;
        _rxBytes = null;
        _rxBase64DataUri = null;
        _rxFileName = "";
        _rxWasCropped = false;
        _selectedDurationDays = 0;
        _selectedItems.clear();
        _notesController.clear();
      });

      _showOrderSuccessDialog(orderNum, otp, res['message']?.toString() ?? '');
    } else {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          backgroundColor: Colors.red.shade700,
          content: Text(res['message']?.toString() ?? "অর্ডার সম্পন্ন করা যায়নি।"),
        ),
      );
    }
  }

  void _showOrderSuccessDialog(String orderNum, String otp, String msg) {
    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (ctx) => AlertDialog(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(18)),
        title: Row(
          children: const [
            CircleAvatar(
              backgroundColor: Color(0xFFECFDF5),
              child: Text("🎉", style: TextStyle(fontSize: 22)),
            ),
            SizedBox(width: 10),
            Expanded(
              child: Text(
                "অর্ডার সফলভাবে গৃহীত হয়েছে!",
                style: TextStyle(fontSize: 16, fontWeight: FontWeight.w800, color: Color(0xFF047857)),
              ),
            ),
          ],
        ),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(msg, style: const TextStyle(fontSize: 13)),
            const SizedBox(height: 12),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: const Color(0xFFF0FDF4),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: const Color(0xFFA7F3D0)),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text("অর্ডার নম্বর: $orderNum",
                      style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 14, color: Color(0xFF065F46))),
                  if (otp.isNotEmpty) ...[
                    const SizedBox(height: 4),
                    Text("ডেলিভারি OTP কোড: $otp",
                        style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 14, color: Color(0xFFB91C1C))),
                  ],
                ],
              ),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () {
              Navigator.pop(ctx);
              _openMyOrdersModal(initialOrderNum: orderNum);
            },
            child: const Text("📋 অর্ডার স্ট্যাটাস দেখুন", style: TextStyle(fontWeight: FontWeight.bold, color: Color(0xFF047857))),
          ),
          ElevatedButton(
            onPressed: () => Navigator.pop(ctx),
            style: ElevatedButton.styleFrom(backgroundColor: const Color(0xFF047857), foregroundColor: Colors.white),
            child: const Text("ঠিক আছে"),
          ),
        ],
      ),
    );
  }

  void _openMyOrdersModal({String initialOrderNum = ""}) {
    final phoneToUse = _phoneController.text.trim();
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      shape: const RoundedRectangleBorder(
        borderRadius: BorderRadius.vertical(top: Radius.circular(20)),
      ),
      builder: (_) => _PharmacyOrdersModal(
        initialPhone: phoneToUse,
        initialOrderNum: initialOrderNum,
        onSelectMedicine: (medName) {
          Navigator.pop(context);
          final q = medName.trim();
          if (q.isNotEmpty) {
            setState(() {
              _medSearchController.text = q;
              _searchQuery = q;
              _selectedDosage = 'all';
            });
            _loadMedicines();
            WidgetsBinding.instance.addPostFrameCallback((_) {
              _scrollToMedicineCatalog();
            });
          }
        },
      ),
    );
  }

  Future<void> _callHelpline() async {
    final clean = _helplinePhone.replaceAll(RegExp(r'[^0-9+]'), '');
    final uri = Uri.parse('tel:$clean');
    if (await canLaunchUrl(uri)) {
      await launchUrl(uri);
    }
  }

  @override
  Widget build(BuildContext context) {
    final bool isDark = Theme.of(context).brightness == Brightness.dark;
    final List<String> districtList = _deliveryAreas
        .map((e) => e.district.trim())
        .where((e) => e.isNotEmpty)
        .toSet()
        .toList()
      ..sort();
    if (!districtList.contains(_selectedDistrict)) {
      districtList.insert(0, _selectedDistrict);
    }

    final List<String> areaList = _deliveryAreas
        .where((e) => e.district.trim() == _selectedDistrict)
        .map((e) => e.area.trim())
        .where((e) => e.isNotEmpty)
        .toSet()
        .toList()
      ..sort();
    if (!areaList.contains(_selectedArea)) {
      areaList.insert(0, _selectedArea);
    }

    return Column(
      children: [
        // Top Emerald Header Bar
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
          decoration: const BoxDecoration(
            gradient: LinearGradient(
              colors: [Color(0xFF047857), Color(0xFF059669)],
              begin: Alignment.topLeft,
              end: Alignment.bottomRight,
            ),
          ),
          child: Column(
            children: [
              Row(
                children: [
                  if (widget.onBackToHome != null)
                    IconButton(
                      onPressed: widget.onBackToHome,
                      icon: const Icon(Icons.arrow_back, color: Colors.white, size: 22),
                      tooltip: "হোম স্ক্রিনে ফিরুন",
                      padding: EdgeInsets.zero,
                      constraints: const BoxConstraints(),
                    ),
                  if (widget.onBackToHome != null) const SizedBox(width: 8),
                  Container(
                    padding: const EdgeInsets.all(7),
                    decoration: BoxDecoration(
                      color: Colors.white.withValues(alpha: 0.2),
                      shape: BoxShape.circle,
                    ),
                    child: const Text("💊", style: TextStyle(fontSize: 18)),
                  ),
                  const SizedBox(width: 8),
                  const Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        Text(
                          "ফার্মেসী ও প্রেসক্রিপশন সেবা",
                          style: TextStyle(color: Colors.white, fontWeight: FontWeight.w800, fontSize: 14),
                        ),
                        Text(
                          "● ফার্মেসী খোলা আছে • দ্রুত হোম ডেলিভারি",
                          style: TextStyle(color: Color(0xFFCCFBF1), fontSize: 10.5, fontWeight: FontWeight.w600),
                        ),
                      ],
                    ),
                  ),
                  InkWell(
                    onTap: () => _openMyOrdersModal(),
                    borderRadius: BorderRadius.circular(18),
                    child: Container(
                      padding: const EdgeInsets.symmetric(horizontal: 9, vertical: 5),
                      decoration: BoxDecoration(
                        color: Colors.white,
                        borderRadius: BorderRadius.circular(18),
                      ),
                      child: const Row(
                        children: [
                          Icon(Icons.receipt_long, size: 14, color: Color(0xFF047857)),
                          SizedBox(width: 4),
                          Text("আমার অর্ডার", style: TextStyle(color: Color(0xFF047857), fontSize: 11, fontWeight: FontWeight.w800)),
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(width: 6),
                  InkWell(
                    onTap: _callHelpline,
                    borderRadius: BorderRadius.circular(18),
                    child: Container(
                      padding: const EdgeInsets.all(6),
                      decoration: BoxDecoration(
                        color: Colors.white.withValues(alpha: 0.2),
                        shape: BoxShape.circle,
                      ),
                      child: const Icon(Icons.call, size: 16, color: Colors.white),
                    ),
                  ),
                ],
              ),
            ],
          ),
        ),

        // Scrollable Native Body
        Expanded(
          child: RefreshIndicator(
            onRefresh: _initScreenData,
            child: ListView(
              controller: _pageScrollController,
              padding: const EdgeInsets.all(12),
              children: [
                // STEP 1: PRESCRIPTION PHOTO CAPTURE & UPLOAD
                _buildStepCard(
                  isDark: isDark,
                  stepNum: "১",
                  title: "প্রেসক্রিপশনের ছবি তুলুন অথবা আপলোড করুন",
                  subtitle: "ডাক্তারের প্রেসক্রিপশন সরাসরি ক্যামেরায় তুলুন বা গ্যালারি থেকে সিলেক্ট করুন",
                  child: Column(
                    children: [
                      Row(
                        children: [
                          Expanded(
                            child: ElevatedButton.icon(
                              onPressed: () => _pickPrescriptionImage(ImageSource.camera),
                              icon: const Icon(Icons.camera_alt, size: 18),
                              label: const Text("ক্যামেরা", style: TextStyle(fontWeight: FontWeight.w800, fontSize: 13)),
                              style: ElevatedButton.styleFrom(
                                backgroundColor: const Color(0xFF047857),
                                foregroundColor: Colors.white,
                                padding: const EdgeInsets.symmetric(vertical: 12),
                                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                              ),
                            ),
                          ),
                          const SizedBox(width: 10),
                          Expanded(
                            child: OutlinedButton.icon(
                              onPressed: () => _pickPrescriptionImage(ImageSource.gallery),
                              icon: const Icon(Icons.photo_library, size: 18),
                              label: const Text("গ্যালারি", style: TextStyle(fontWeight: FontWeight.w800, fontSize: 13)),
                              style: OutlinedButton.styleFrom(
                                foregroundColor: const Color(0xFF047857),
                                side: const BorderSide(color: Color(0xFF059669), width: 1.5),
                                padding: const EdgeInsets.symmetric(vertical: 12),
                                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                              ),
                            ),
                          ),
                        ],
                      ),

                      if (_rxBytes != null) ...[
                        const SizedBox(height: 12),
                        GestureDetector(
                          onTap: _showFullPrescriptionPreview,
                          child: Stack(
                            children: [
                              Container(
                                width: double.infinity,
                                constraints: const BoxConstraints(maxHeight: 260),
                                decoration: BoxDecoration(
                                  color: Colors.black87,
                                  borderRadius: BorderRadius.circular(12),
                                  border: Border.all(color: const Color(0xFF10B981), width: 1.5),
                                ),
                                child: ClipRRect(
                                  borderRadius: BorderRadius.circular(10),
                                  child: Image.memory(_rxBytes!, fit: BoxFit.contain),
                                ),
                              ),
                              Positioned(
                                top: 8,
                                left: 8,
                                child: Container(
                                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                                  decoration: BoxDecoration(
                                    color: Colors.black.withValues(alpha: 0.7),
                                    borderRadius: BorderRadius.circular(8),
                                    border: Border.all(color: const Color(0xFF34D399)),
                                  ),
                                  child: Text(
                                    _rxFilterName == 'original' && !_rxWasCropped
                                        ? "🖼️ অরিজিনাল"
                                        : "✨ স্ক্যান${_rxWasCropped ? ' ও ক্রপড' : ''}",
                                    style: const TextStyle(color: Colors.white, fontSize: 10.5, fontWeight: FontWeight.bold),
                                  ),
                                ),
                              ),
                            ],
                          ),
                        ),
                        const SizedBox(height: 8),
                        Wrap(
                          spacing: 6,
                          runSpacing: 6,
                          crossAxisAlignment: WrapCrossAlignment.center,
                          children: [
                            Text(
                              "✅ $_rxFileName",
                              overflow: TextOverflow.ellipsis,
                              style: const TextStyle(fontSize: 11.5, color: Color(0xFF047857), fontWeight: FontWeight.w700),
                            ),
                            ElevatedButton.icon(
                              onPressed: _editCurrentPrescription,
                              icon: const Icon(Icons.crop, size: 15),
                              label: const Text("ক্রপ ও স্ক্যান", style: TextStyle(fontSize: 11.5, fontWeight: FontWeight.bold)),
                              style: ElevatedButton.styleFrom(
                                backgroundColor: const Color(0xFF047857),
                                foregroundColor: Colors.white,
                                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 6),
                                minimumSize: const Size(0, 32),
                              ),
                            ),
                            OutlinedButton.icon(
                              onPressed: _showFullPrescriptionPreview,
                              icon: const Icon(Icons.fullscreen, size: 15),
                              label: const Text("ফুল সাইজ", style: TextStyle(fontSize: 11.5, fontWeight: FontWeight.bold)),
                              style: OutlinedButton.styleFrom(
                                foregroundColor: const Color(0xFF047857),
                                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
                                minimumSize: const Size(0, 32),
                              ),
                            ),
                            TextButton.icon(
                              onPressed: () {
                                setState(() {
                                  _rxOriginalBytes = null;
                                  _rxOriginalBase64DataUri = null;
                                  _rxBytes = null;
                                  _rxBase64DataUri = null;
                                  _rxFileName = "";
                                  _rxWasCropped = false;
                                });
                              },
                              icon: const Icon(Icons.delete_outline, size: 16, color: Colors.red),
                              label: const Text("মুছুন", style: TextStyle(fontSize: 11.5, color: Colors.red, fontWeight: FontWeight.bold)),
                            ),
                          ],
                        ),
                      ],
                    ],
                  ),
                ),

                const SizedBox(height: 12),

                // STEP 2: DURATION & MEDICINE SELECTION
                _buildStepCard(
                  isDark: isDark,
                  stepNum: "২",
                  title: "কয়দিনের ঔষধ ও অতিরিক্ত নির্দেশনা",
                  subtitle: "সবগুলো ঔষধ সাধারণত কয়দিনের লাগবে তা সিলেক্ট করুন অথবা নিচে নোটে লিখে দিন",
                  child: Column(
                    crossAxisAlignment: CrossAxisAlignment.start,
                    children: [
                      Wrap(
                        spacing: 6,
                        runSpacing: 6,
                        children: [0, 3, 5, 7, 10, 14, 30].map((days) {
                          final bool isSel = _selectedDurationDays == days;
                          final bool isNoteOption = days == 0;
                          final String label = isNoteOption ? "📝 নোটে লিখবো" : "$days দিন";
                          final Color activeBg = isNoteOption
                              ? const Color(0xFFD97706)
                              : const Color(0xFF047857);
                          final Color idleBg = isNoteOption
                              ? (isDark ? const Color(0xFF451A03) : const Color(0xFFFEF3C7))
                              : (isDark ? Colors.grey[800]! : const Color(0xFFF1F5F9));
                          return ChoiceChip(
                            label: Text(
                              isNoteOption && isSel ? "$label ✓" : label,
                              style: TextStyle(
                                fontSize: isNoteOption ? 12 : 11.5,
                                fontWeight: FontWeight.w800,
                                color: isSel
                                    ? Colors.white
                                    : (isNoteOption
                                        ? (isDark ? const Color(0xFFFCD34D) : const Color(0xFF92400E))
                                        : (isDark ? Colors.white70 : Colors.black87)),
                              ),
                            ),
                            selected: isSel,
                            selectedColor: activeBg,
                            backgroundColor: idleBg,
                            side: isNoteOption
                                ? BorderSide(
                                    color: isSel ? const Color(0xFFB45309) : const Color(0xFFF59E0B),
                                    width: isSel ? 1.8 : 1.2,
                                  )
                                : BorderSide(
                                    color: isSel ? const Color(0xFF047857) : Colors.grey.shade300,
                                  ),
                            onSelected: (_) => setState(() => _selectedDurationDays = days),
                          );
                        }).toList(),
                      ),
                      const SizedBox(height: 10),
                      AnimatedContainer(
                        duration: const Duration(milliseconds: 200),
                        padding: _selectedDurationDays == 0 ? const EdgeInsets.all(8) : EdgeInsets.zero,
                        decoration: _selectedDurationDays == 0
                            ? BoxDecoration(
                                color: isDark ? const Color(0xFF451A03).withValues(alpha: 0.4) : const Color(0xFFFFFBEB),
                                borderRadius: BorderRadius.circular(12),
                                border: Border.all(color: const Color(0xFFF59E0B), width: 1.5),
                              )
                            : null,
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            if (_selectedDurationDays == 0)
                              const Padding(
                                padding: EdgeInsets.only(bottom: 6),
                                child: Text(
                                  "✏️ 'নোটে লিখবো' সিলেক্ট করা আছে — কয়দিনের ওষুধ বা পরিমাণ এখানে লিখুন:",
                                  style: TextStyle(
                                    fontSize: 11.5,
                                    fontWeight: FontWeight.w800,
                                    color: Color(0xFFB45309),
                                  ),
                                ),
                              ),
                            TextField(
                              controller: _notesController,
                              maxLines: 2,
                              decoration: InputDecoration(
                                hintText: "অতিরিক্ত নোট (যেমন: প্যারাসিটামল ২ পাতা, গ্যাস্ট্রিকের ১ পাতা)...",
                                hintStyle: const TextStyle(fontSize: 12),
                                filled: true,
                                fillColor: isDark ? Colors.grey[900] : Colors.white,
                                border: OutlineInputBorder(borderRadius: BorderRadius.circular(10)),
                                enabledBorder: OutlineInputBorder(
                                  borderRadius: BorderRadius.circular(10),
                                  borderSide: BorderSide(
                                    color: _selectedDurationDays == 0 ? const Color(0xFFF59E0B) : Colors.grey.shade400,
                                  ),
                                ),
                                contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ],
                  ),
                ),

                if (_selectedItems.isNotEmpty) ...[
                  const SizedBox(height: 12),
                  _buildSelectedItemsCard(isDark),
                ],

                const SizedBox(height: 12),

                // MEDICINE CATALOG SEARCH & BROWSE CARD
                Container(
                  key: _medCatalogKey,
                  child: _buildStepCard(
                    isDark: isDark,
                    stepNum: "💊",
                    title: "সরাসরি ঔষধের তালিকা থেকে বাছাই করুন",
                    subtitle: "ওষুধের নাম, জেনেরিক বা কোম্পানি লিখে খুঁজুন",
                    child: Column(
                      children: [
                        TextField(
                          controller: _medSearchController,
                          onChanged: _onSearchChanged,
                          decoration: InputDecoration(
                            hintText: "ঔষধ খুঁজুন (যেমন: Napa, Seclo, Sergel)...",
                            hintStyle: const TextStyle(fontSize: 12.5),
                            prefixIcon: const Icon(Icons.search, color: Color(0xFF047857)),
                            suffixIcon: _medSearchController.text.isNotEmpty
                                ? IconButton(
                                    icon: const Icon(Icons.clear, size: 18),
                                    onPressed: () {
                                      _medSearchController.clear();
                                      _onSearchChanged("");
                                    },
                                  )
                                : null,
                            filled: true,
                            fillColor: isDark ? Colors.grey[850] : const Color(0xFFECFDF5),
                            border: OutlineInputBorder(
                              borderRadius: BorderRadius.circular(12),
                              borderSide: const BorderSide(color: Color(0xFF10B981)),
                            ),
                            contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                          ),
                        ),
                        const SizedBox(height: 8),
                        SingleChildScrollView(
                          scrollDirection: Axis.horizontal,
                          child: Row(
                            children: _dosageForms.map((d) {
                              final bool isSel = _selectedDosage.toLowerCase() == d['val']!.toLowerCase();
                              return Padding(
                                padding: const EdgeInsets.only(right: 6),
                                child: ChoiceChip(
                                  label: Text(
                                    d['label']!,
                                    style: TextStyle(
                                      fontSize: 11,
                                      fontWeight: FontWeight.bold,
                                      color: isSel ? Colors.white : (isDark ? Colors.white70 : Colors.black87),
                                    ),
                                  ),
                                  selected: isSel,
                                  selectedColor: const Color(0xFF047857),
                                  backgroundColor: isDark ? Colors.grey[800] : Colors.grey[100],
                                  onSelected: (sel) {
                                    if (sel) {
                                      setState(() => _selectedDosage = d['val']!);
                                      _loadMedicines();
                                    }
                                  },
                                ),
                              );
                            }).toList(),
                          ),
                        ),
                        const SizedBox(height: 8),
                        if (_isLoadingMeds)
                          const Padding(
                            padding: EdgeInsets.symmetric(vertical: 20),
                            child: Center(child: CircularProgressIndicator()),
                          )
                        else if (_medicines.isEmpty)
                          const Padding(
                            padding: EdgeInsets.symmetric(vertical: 18),
                            child: Text(
                              "কোনো ওষুধ পাওয়া যায়নি। অন্য নাম লিখে খুঁজুন।",
                              style: TextStyle(color: Colors.grey, fontSize: 12.5, fontWeight: FontWeight.w600),
                            ),
                          )
                        else ...[
                          Container(
                            width: double.infinity,
                            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 5),
                            margin: const EdgeInsets.only(bottom: 6),
                            decoration: BoxDecoration(
                              color: isDark ? const Color(0xFF064E3B) : const Color(0xFFECFDF5),
                              borderRadius: BorderRadius.circular(8),
                            ),
                            child: Row(
                              mainAxisAlignment: MainAxisAlignment.spaceBetween,
                              children: [
                                Text(
                                  "📋 ${_medicines.length}টি ঔষধ পাওয়া গেছে",
                                  style: TextStyle(
                                    fontSize: 11.5,
                                    fontWeight: FontWeight.w800,
                                    color: isDark ? const Color(0xFF6EE7B7) : const Color(0xFF065F46),
                                  ),
                                ),
                                if (_medicines.length > 3)
                                  Text(
                                    "নিচে স্ক্রল করুন ↓",
                                    style: TextStyle(
                                      fontSize: 11,
                                      fontWeight: FontWeight.w700,
                                      color: isDark ? const Color(0xFFA7F3D0) : const Color(0xFF047857),
                                    ),
                                  ),
                              ],
                            ),
                          ),
                          ConstrainedBox(
                            constraints: const BoxConstraints(maxHeight: 335),
                            child: Scrollbar(
                              thumbVisibility: _medicines.length > 3,
                              child: ListView.separated(
                                shrinkWrap: true,
                                physics: const AlwaysScrollableScrollPhysics(),
                                itemCount: _medicines.length,
                                separatorBuilder: (_, __) => const Divider(height: 12),
                                itemBuilder: (_, idx) {
                                  final med = _medicines[idx] as Map<String, dynamic>;
                                  return _buildMedicineRow(med, isDark);
                                },
                              ),
                            ),
                          ),
                        ],
                      ],
                    ),
                  ),
                ),

                const SizedBox(height: 12),

                // STEP 3: CUSTOMER DELIVERY DETAILS & ORDER SUBMIT
                _buildStepCard(
                  isDark: isDark,
                  stepNum: "৩",
                  title: "ডেলিভারি তথ্য ও অর্ডার সম্পন্ন করুন",
                  subtitle: _isLoggedIn
                      ? "আপনার প্রোফাইল থেকে তথ্য স্বয়ংক্রিয়ভাবে পূরণ করা হয়েছে"
                      : "ডেলিভারির জন্য আপনার নাম, মোবাইল নম্বর ও ঠিকানা দিন",
                  child: Column(
                    children: [
                      if (!_isLoggedIn) ...[
                        SizedBox(
                          width: double.infinity,
                          child: OutlinedButton.icon(
                            onPressed: () async {
                              await Navigator.push(
                                context,
                                MaterialPageRoute(builder: (_) => const LoginScreen()),
                              );
                              _loadCustomerAndSettings();
                            },
                            icon: const Icon(Icons.login, size: 16),
                            label: const Text("একাউন্টে লগইন করে অটো-ফিল করুন"),
                            style: OutlinedButton.styleFrom(
                              foregroundColor: const Color(0xFF047857),
                              side: const BorderSide(color: Color(0xFF10B981)),
                            ),
                          ),
                        ),
                        const SizedBox(height: 10),
                      ],
                      TextField(
                        controller: _nameController,
                        readOnly: true,
                        enabled: false,
                        style: TextStyle(
                          fontWeight: FontWeight.w700,
                          color: isDark ? Colors.white : Colors.black87,
                        ),
                        decoration: InputDecoration(
                          labelText: "আপনার নাম (একাউন্ট থেকে অটো-ফিল্ড • পরিবর্তনযোগ্য নয়)",
                          prefixIcon: const Icon(Icons.person_outline, size: 19),
                          suffixIcon: const Icon(Icons.lock_outline, size: 17),
                          filled: true,
                          fillColor: isDark ? Colors.grey[850] : const Color(0xFFF1F5F9),
                          border: OutlineInputBorder(borderRadius: BorderRadius.circular(10)),
                          isDense: true,
                        ),
                      ),
                      const SizedBox(height: 10),
                      TextField(
                        controller: _phoneController,
                        readOnly: true,
                        enabled: false,
                        style: TextStyle(
                          fontWeight: FontWeight.w700,
                          color: isDark ? Colors.white : Colors.black87,
                        ),
                        keyboardType: TextInputType.phone,
                        decoration: InputDecoration(
                          labelText: "মোবাইল নম্বর (একাউন্ট থেকে অটো-ফিল্ড • পরিবর্তনযোগ্য নয়)",
                          prefixIcon: const Icon(Icons.phone_outlined, size: 19),
                          suffixIcon: const Icon(Icons.lock_outline, size: 17),
                          filled: true,
                          fillColor: isDark ? Colors.grey[850] : const Color(0xFFF1F5F9),
                          border: OutlineInputBorder(borderRadius: BorderRadius.circular(10)),
                          isDense: true,
                        ),
                      ),
                      const SizedBox(height: 10),
                      Row(
                        children: [
                          Expanded(
                            child: DropdownButtonFormField<String>(
                              value: _selectedDistrict,
                              isExpanded: true,
                              decoration: InputDecoration(
                                labelText: "জেলা",
                                border: OutlineInputBorder(borderRadius: BorderRadius.circular(10)),
                                isDense: true,
                              ),
                              items: districtList
                                  .map((d) => DropdownMenuItem(value: d, child: Text(d, overflow: TextOverflow.ellipsis)))
                                  .toList(),
                              onChanged: (val) {
                                if (val != null) {
                                  setState(() {
                                    _selectedDistrict = val;
                                    final nextAreas = _deliveryAreas
                                        .where((e) => e.district.trim() == val)
                                        .map((e) => e.area.trim())
                                        .where((e) => e.isNotEmpty)
                                        .toList();
                                    if (nextAreas.isNotEmpty && !nextAreas.contains(_selectedArea)) {
                                      _selectedArea = nextAreas.first;
                                    }
                                  });
                                }
                              },
                            ),
                          ),
                          const SizedBox(width: 8),
                          Expanded(
                            child: DropdownButtonFormField<String>(
                              value: _selectedArea,
                              isExpanded: true,
                              decoration: InputDecoration(
                                labelText: "এলাকা",
                                border: OutlineInputBorder(borderRadius: BorderRadius.circular(10)),
                                isDense: true,
                              ),
                              items: areaList
                                  .map((a) => DropdownMenuItem(value: a, child: Text(a, overflow: TextOverflow.ellipsis)))
                                  .toList(),
                              onChanged: (val) {
                                if (val != null) setState(() => _selectedArea = val);
                              },
                            ),
                          ),
                        ],
                      ),
                      const SizedBox(height: 10),
                      TextField(
                        controller: _addressController,
                        maxLines: 2,
                        decoration: InputDecoration(
                          labelText: "বিস্তারিত ডেলিভারি ঠিকানা (বাসা/রোড নং) *",
                          prefixIcon: const Icon(Icons.location_on_outlined, size: 19),
                          border: OutlineInputBorder(borderRadius: BorderRadius.circular(10)),
                          isDense: true,
                        ),
                      ),
                      const SizedBox(height: 12),

                      // Order Summary Box
                      Container(
                        width: double.infinity,
                        padding: const EdgeInsets.all(12),
                        decoration: BoxDecoration(
                          color: isDark ? Colors.grey[850] : const Color(0xFFF0FDF4),
                          borderRadius: BorderRadius.circular(12),
                          border: Border.all(color: const Color(0xFFA7F3D0)),
                        ),
                        child: Column(
                          children: [
                            Row(
                              mainAxisAlignment: MainAxisAlignment.spaceBetween,
                              children: [
                                const Text("নির্বাচিত ওষুধের মূল্য:", style: TextStyle(fontSize: 12.5)),
                                Text("৳ ${_itemsSubtotal.toStringAsFixed(2)}",
                                    style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13)),
                              ],
                            ),
                            const SizedBox(height: 4),
                            Row(
                              mainAxisAlignment: MainAxisAlignment.spaceBetween,
                              children: [
                                const Text("ডেলিভারি চার্জ:", style: TextStyle(fontSize: 12.5)),
                                Text("৳ ${_pharmacyDeliveryCharge.toStringAsFixed(2)}",
                                    style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13)),
                              ],
                            ),
                            const Divider(height: 14),
                            Row(
                              mainAxisAlignment: MainAxisAlignment.spaceBetween,
                              children: [
                                const Text("সম্ভাব্য সর্বমোট বিল:",
                                    style: TextStyle(fontWeight: FontWeight.w800, fontSize: 13.5, color: Color(0xFF047857))),
                                Text(
                                  _selectedItems.isEmpty && _rxBytes != null
                                      ? "ফার্মাসিস্ট যাচাইয়ের পর"
                                      : "৳ ${(_itemsSubtotal + _pharmacyDeliveryCharge).toStringAsFixed(2)}",
                                  style: const TextStyle(fontWeight: FontWeight.w900, fontSize: 15, color: Color(0xFF047857)),
                                ),
                              ],
                            ),
                          ],
                        ),
                      ),
                      const SizedBox(height: 14),

                      SizedBox(
                        width: double.infinity,
                        height: 48,
                        child: ElevatedButton.icon(
                          onPressed: _isSubmitting ? null : _submitOrder,
                          icon: _isSubmitting
                              ? const SizedBox(
                                  width: 18,
                                  height: 18,
                                  child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                                )
                              : const Icon(Icons.check_circle_outline),
                          label: Text(
                            _isSubmitting ? "অর্ডার পাঠানো হচ্ছে..." : "অর্ডার কনফার্ম করুন",
                            style: const TextStyle(fontWeight: FontWeight.w900, fontSize: 15),
                          ),
                          style: ElevatedButton.styleFrom(
                            backgroundColor: const Color(0xFF047857),
                            foregroundColor: Colors.white,
                            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                          ),
                        ),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 24),
              ],
            ),
          ),
        ),
      ],
    );
  }

  Widget _buildStepCard({
    required bool isDark,
    required String stepNum,
    required String title,
    required String subtitle,
    required Widget child,
  }) {
    return Card(
      elevation: 1.5,
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(14),
        side: BorderSide(color: isDark ? Colors.grey[700]! : const Color(0xFFD1FAE5)),
      ),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              children: [
                CircleAvatar(
                  radius: 13,
                  backgroundColor: const Color(0xFF047857),
                  child: Text(stepNum, style: const TextStyle(color: Colors.white, fontSize: 12, fontWeight: FontWeight.w800)),
                ),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(title, style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 14)),
                ),
              ],
            ),
            const SizedBox(height: 4),
            Text(subtitle, style: TextStyle(fontSize: 11.5, color: Colors.grey[600])),
            const SizedBox(height: 12),
            child,
          ],
        ),
      ),
    );
  }

  Widget _buildSelectedItemsCard(bool isDark) {
    return Card(
      elevation: 1.5,
      color: isDark ? const Color(0xFF064E3B) : const Color(0xFFECFDF5),
      shape: RoundedRectangleBorder(
        borderRadius: BorderRadius.circular(14),
        side: const BorderSide(color: Color(0xFF10B981), width: 1.5),
      ),
      child: Padding(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Text(
                  "🛒 নির্বাচিত ওষুধসমূহ (${_selectedItems.length})",
                  style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 14, color: Color(0xFF047857)),
                ),
                TextButton(
                  onPressed: () => setState(() => _selectedItems.clear()),
                  child: const Text("সব মুছুন", style: TextStyle(color: Colors.red, fontSize: 12, fontWeight: FontWeight.bold)),
                ),
              ],
            ),
            const Divider(height: 10),
            ...List.generate(_selectedItems.length, (idx) {
              final it = _selectedItems[idx];
              final double lineTotal = (it['unit_price'] as double) * (it['quantity'] as int);
              return Padding(
                padding: const EdgeInsets.symmetric(vertical: 6),
                child: Row(
                  children: [
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text("${it['name']} ${it['strength']}",
                              style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 13)),
                          Text("৳ ${(it['unit_price'] as double).toStringAsFixed(2)} / পিস",
                              style: TextStyle(fontSize: 11, color: Colors.grey[700])),
                        ],
                      ),
                    ),
                    Row(
                      children: [
                        IconButton(
                          onPressed: () => _updateSelectedItemQty(idx, -1),
                          icon: const Icon(Icons.remove_circle_outline, size: 20, color: Color(0xFF047857)),
                          padding: EdgeInsets.zero,
                          constraints: const BoxConstraints(),
                        ),
                        Padding(
                          padding: const EdgeInsets.symmetric(horizontal: 8),
                          child: Text("${it['quantity']}", style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 14)),
                        ),
                        IconButton(
                          onPressed: () => _updateSelectedItemQty(idx, 1),
                          icon: const Icon(Icons.add_circle_outline, size: 20, color: Color(0xFF047857)),
                          padding: EdgeInsets.zero,
                          constraints: const BoxConstraints(),
                        ),
                      ],
                    ),
                    const SizedBox(width: 8),
                    Text("৳ ${lineTotal.toStringAsFixed(2)}",
                        style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 13, color: Color(0xFF047857))),
                  ],
                ),
              );
            }),
          ],
        ),
      ),
    );
  }

  Widget _buildMedicineRow(Map<String, dynamic> med, bool isDark) {
    final String name = med['name']?.toString() ?? 'Medicine';
    final String strength = med['strength']?.toString() ?? '';
    final String generic = med['generic_name']?.toString() ?? '';
    final String dosage = med['dosage_form']?.toString() ?? 'Medicine';
    final String manufacturer = med['manufacturer']?.toString() ?? '';
    final double mrp = double.tryParse(med['mrp']?.toString() ?? '0') ?? 0.0;
    final double unitPrice =
        double.tryParse(med['sell_price']?.toString() ?? med['unit_price']?.toString() ?? '0') ?? mrp;
    final double disc = double.tryParse(med['discount_percent']?.toString() ?? '0') ?? 0.0;
    final int stock = int.tryParse(med['stock_qty']?.toString() ?? '999') ?? 999;
    final bool isOut = stock <= 0;

    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      children: [
        Row(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              width: 38,
              height: 38,
              decoration: BoxDecoration(
                color: const Color(0xFFECFDF5),
                borderRadius: BorderRadius.circular(10),
                border: Border.all(color: const Color(0xFFA7F3D0)),
              ),
              child: const Center(child: Text("💊", style: TextStyle(fontSize: 18))),
            ),
            const SizedBox(width: 10),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(strength.isNotEmpty ? "$name $strength" : name,
                      style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 13.5)),
                  if (generic.isNotEmpty)
                    Text(generic,
                        style: TextStyle(
                            fontSize: 11,
                            fontStyle: FontStyle.italic,
                            color: isDark ? Colors.teal[300] : const Color(0xFF047857),
                            fontWeight: FontWeight.w600)),
                  Text("$dosage • $manufacturer", style: TextStyle(fontSize: 10.5, color: Colors.grey[600])),
                ],
              ),
            ),
            Column(
              crossAxisAlignment: CrossAxisAlignment.end,
              children: [
                Text("৳ ${unitPrice.toStringAsFixed(2)}",
                    style: const TextStyle(fontWeight: FontWeight.w900, fontSize: 14, color: Color(0xFF047857))),
                if (mrp > unitPrice)
                  Text("৳ ${mrp.toStringAsFixed(2)}",
                      style: TextStyle(fontSize: 10, decoration: TextDecoration.lineThrough, color: Colors.grey[500])),
                if (disc > 0)
                  Text("${disc.toStringAsFixed(0)}% OFF",
                      style: const TextStyle(fontSize: 9.5, color: Colors.red, fontWeight: FontWeight.bold)),
              ],
            ),
          ],
        ),
        const SizedBox(height: 8),
        Row(
          children: [
            if (generic.isNotEmpty)
              OutlinedButton.icon(
                onPressed: () => _showSubstitutesSheet(med),
                icon: const Icon(Icons.swap_horiz, size: 14),
                label: const Text("বিকল্প ব্র্যান্ড", style: TextStyle(fontSize: 11, fontWeight: FontWeight.bold)),
                style: OutlinedButton.styleFrom(
                  foregroundColor: const Color(0xFF047857),
                  side: const BorderSide(color: Color(0xFFA7F3D0)),
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                  minimumSize: const Size(0, 32),
                ),
              ),
            const Spacer(),
            ElevatedButton.icon(
              onPressed: isOut ? null : () => _addMedicineToOrder(med),
              icon: Icon(isOut ? Icons.block : Icons.add, size: 15),
              label: Text(isOut ? "স্টক নেই" : "তালিকায় যোগ করুন", style: const TextStyle(fontSize: 11.5, fontWeight: FontWeight.w800)),
              style: ElevatedButton.styleFrom(
                backgroundColor: isOut ? Colors.grey : const Color(0xFF047857),
                foregroundColor: Colors.white,
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 4),
                minimumSize: const Size(0, 32),
                elevation: 0,
              ),
            ),
          ],
        ),
      ],
    );
  }
}

class _SubstitutesModal extends StatefulWidget {
  final String brandName;
  final String genericName;
  final int excludeId;
  final void Function(Map<String, dynamic>) onSelectSubstitute;

  const _SubstitutesModal({
    required this.brandName,
    required this.genericName,
    required this.excludeId,
    required this.onSelectSubstitute,
  });

  @override
  State<_SubstitutesModal> createState() => _SubstitutesModalState();
}

class _SubstitutesModalState extends State<_SubstitutesModal> {
  List<dynamic> _subs = [];
  bool _loading = true;

  @override
  void initState() {
    super.initState();
    _load();
  }

  Future<void> _load() async {
    final res = await ApiService.fetchPharmacySubstitutes(
      genericName: widget.genericName,
      excludeId: widget.excludeId,
    );
    if (mounted) {
      setState(() {
        _subs = res;
        _loading = false;
      });
    }
  }

  @override
  Widget build(BuildContext context) {
    return DraggableScrollableSheet(
      expand: false,
      initialChildSize: 0.6,
      maxChildSize: 0.85,
      builder: (_, scrollCtrl) => Column(
        children: [
          Padding(
            padding: const EdgeInsets.all(16),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  "🔄 ${widget.brandName}-এর বিকল্প ব্র্যান্ডসমূহ",
                  style: const TextStyle(fontSize: 15, fontWeight: FontWeight.w800, color: Color(0xFF047857)),
                ),
                const SizedBox(height: 2),
                Text("জেনেরিক: ${widget.genericName}", style: TextStyle(fontSize: 12, color: Colors.grey[600])),
              ],
            ),
          ),
          const Divider(height: 1),
          Expanded(
            child: _loading
                ? const Center(child: CircularProgressIndicator())
                : _subs.isEmpty
                    ? const Center(child: Text("একই জেনেরিকের অন্য কোনো ব্র্যান্ড পাওয়া যায়নি।"))
                    : ListView.separated(
                        controller: scrollCtrl,
                        padding: const EdgeInsets.all(12),
                        itemCount: _subs.length,
                        separatorBuilder: (_, __) => const Divider(),
                        itemBuilder: (_, idx) {
                          final s = _subs[idx] as Map<String, dynamic>;
                          final double price = double.tryParse(s['sell_price']?.toString() ?? s['unit_price']?.toString() ?? '0') ?? 0.0;
                          return ListTile(
                            contentPadding: EdgeInsets.zero,
                            title: Text("${s['name']} ${s['strength'] ?? ''}", style: const TextStyle(fontWeight: FontWeight.bold)),
                            subtitle: Text("${s['dosage_form'] ?? ''} • ${s['manufacturer'] ?? ''}"),
                            trailing: ElevatedButton(
                              onPressed: () => widget.onSelectSubstitute(s),
                              style: ElevatedButton.styleFrom(backgroundColor: const Color(0xFF047857), foregroundColor: Colors.white),
                              child: Text("৳ ${price.toStringAsFixed(2)} +"),
                            ),
                          );
                        },
                      ),
          ),
        ],
      ),
    );
  }
}

class _PharmacyOrdersModal extends StatefulWidget {
  final String initialPhone;
  final String initialOrderNum;
  final void Function(String medicineName)? onSelectMedicine;

  const _PharmacyOrdersModal({
    required this.initialPhone,
    this.initialOrderNum = "",
    this.onSelectMedicine,
  });

  @override
  State<_PharmacyOrdersModal> createState() => _PharmacyOrdersModalState();
}

class _PharmacyOrdersModalState extends State<_PharmacyOrdersModal> {
  final TextEditingController _phoneSearchCtrl = TextEditingController();
  List<dynamic> _orders = [];
  bool _loading = true;
  bool _isRefreshing = false;
  final Set<String> _expandedOrders = {};
  Timer? _livePollTimer;

  @override
  void initState() {
    super.initState();
    _phoneSearchCtrl.text = widget.initialPhone;
    if (widget.initialOrderNum.isNotEmpty) {
      _expandedOrders.add(widget.initialOrderNum);
    }
    _loadCachedThenFetch();
    _livePollTimer = Timer.periodic(const Duration(seconds: 5), (_) {
      if (mounted) _fetchOrders(silent: true);
    });
  }

  @override
  void dispose() {
    _livePollTimer?.cancel();
    _phoneSearchCtrl.dispose();
    super.dispose();
  }

  String _cacheKeyForPhone(String phone) =>
      'cached_pharmacy_orders_${phone.replaceAll(RegExp(r'\D'), '')}';

  Future<void> _loadCachedThenFetch() async {
    final phone = _phoneSearchCtrl.text.trim();
    if (phone.isNotEmpty) {
      try {
        final prefs = await SharedPreferences.getInstance();
        final cachedRaw = prefs.getString(_cacheKeyForPhone(phone));
        if (cachedRaw != null && cachedRaw.isNotEmpty && mounted) {
          final decoded = jsonDecode(cachedRaw);
          if (decoded is List && decoded.isNotEmpty) {
            setState(() {
              _orders = decoded;
              _loading = false;
              if (_expandedOrders.isEmpty) {
                final firstNum = (decoded.first as Map)['order_number']?.toString() ?? '';
                if (firstNum.isNotEmpty) _expandedOrders.add(firstNum);
              }
            });
          }
        }
      } catch (_) {}
    }
    await _fetchOrders(silent: _orders.isNotEmpty);
  }

  Future<void> _fetchOrders({bool silent = false}) async {
    if (_isRefreshing) return;
    _isRefreshing = true;
    try {
      if (!silent && _orders.isEmpty && mounted) {
        setState(() => _loading = true);
      }
      final phone = _phoneSearchCtrl.text.trim();
      final list = phone.isNotEmpty ? await ApiService.fetchMyPharmacyOrders(phone) : <dynamic>[];
      if (phone.isNotEmpty && list.isNotEmpty) {
        try {
          final prefs = await SharedPreferences.getInstance();
          await prefs.setString(_cacheKeyForPhone(phone), jsonEncode(list));
        } catch (_) {}
      }
      if (mounted) {
        setState(() {
          if (list.isNotEmpty || !silent) {
            _orders = list;
          }
          _loading = false;
          if (_expandedOrders.isEmpty && _orders.isNotEmpty) {
            final firstNum = (_orders.first as Map)['order_number']?.toString() ?? '';
            if (firstNum.isNotEmpty) _expandedOrders.add(firstNum);
          }
        });
      }
    } finally {
      _isRefreshing = false;
    }
  }

  String _translateStatus(String status) {
    switch (status) {
      case 'reviewing':
        return '⏳ ফার্মাসিস্ট যাচাই করছে';
      case 'awaiting_customer_confirmation':
        return '🔔 বিল কনফার্ম করুন';
      case 'confirmed':
        return '✅ বিল কনফার্মড';
      case 'packed':
        return '📦 প্যাকিং সম্পন্ন';
      case 'on_the_way':
        return '🛵 ডেলিভারির পথে';
      case 'delivered':
        return '🎉 ডেলিভারি সম্পন্ন';
      case 'cancelled':
        return '❌ বাতিল';
      default:
        return status;
    }
  }

  void _openPrescriptionZoom(String primaryUrl, String originalUrl) {
    final bool isPdf = primaryUrl.toLowerCase().contains('.pdf') ||
        primaryUrl.startsWith('data:application/pdf');
    if (isPdf) {
      final clean = AppImageLoader.cleanUrl(primaryUrl);
      launchUrl(Uri.parse(clean), mode: LaunchMode.externalApplication);
      return;
    }
    bool showOriginal = false;
    final bool hasBoth = originalUrl.isNotEmpty && originalUrl != primaryUrl;
    showDialog(
      context: context,
      builder: (_) => StatefulBuilder(
        builder: (ctx, setDlgState) {
          final activeUrl = (showOriginal && originalUrl.isNotEmpty) ? originalUrl : primaryUrl;
          return Dialog(
            backgroundColor: Colors.black,
            insetPadding: const EdgeInsets.all(10),
            child: Stack(
              children: [
                InteractiveViewer(
                  minScale: 0.5,
                  maxScale: 5.0,
                  child: Center(
                    child: AppImageLoader(imageUrl: activeUrl, fit: BoxFit.contain),
                  ),
                ),
                Positioned(
                  top: 10,
                  right: 10,
                  child: CircleAvatar(
                    backgroundColor: Colors.white,
                    child: IconButton(
                      icon: const Icon(Icons.close, color: Colors.black),
                      onPressed: () => Navigator.pop(ctx),
                    ),
                  ),
                ),
                if (hasBoth)
                  Positioned(
                    bottom: 14,
                    left: 14,
                    right: 14,
                    child: Row(
                      mainAxisAlignment: MainAxisAlignment.center,
                      children: [
                        ChoiceChip(
                          label: const Text("✨ স্ক্যান / এডিটেড"),
                          selected: !showOriginal,
                          selectedColor: const Color(0xFF059669),
                          labelStyle: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold),
                          backgroundColor: Colors.grey.shade800,
                          onSelected: (_) => setDlgState(() => showOriginal = false),
                        ),
                        const SizedBox(width: 8),
                        ChoiceChip(
                          label: const Text("🖼️ অরিজিনাল ছবি"),
                          selected: showOriginal,
                          selectedColor: const Color(0xFF059669),
                          labelStyle: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold),
                          backgroundColor: Colors.grey.shade800,
                          onSelected: (_) => setDlgState(() => showOriginal = true),
                        ),
                      ],
                    ),
                  ),
              ],
            ),
          );
        },
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    return DraggableScrollableSheet(
      expand: false,
      initialChildSize: 0.82,
      maxChildSize: 0.94,
      builder: (_, scrollCtrl) => Column(
        children: [
          Padding(
            padding: const EdgeInsets.fromLTRB(16, 14, 16, 10),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text("📋 আমার ফার্মেসী ও প্রেসক্রিপশন অর্ডারসমূহ",
                    style: TextStyle(fontSize: 15.5, fontWeight: FontWeight.w800, color: Color(0xFF047857))),
                const SizedBox(height: 8),
                Row(
                  children: [
                    Expanded(
                      child: TextField(
                        controller: _phoneSearchCtrl,
                        keyboardType: TextInputType.phone,
                        decoration: InputDecoration(
                          hintText: "মোবাইল নম্বর লিখে খুঁজুন...",
                          isDense: true,
                          border: OutlineInputBorder(borderRadius: BorderRadius.circular(10)),
                          contentPadding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
                        ),
                      ),
                    ),
                    const SizedBox(width: 8),
                    ElevatedButton(
                      onPressed: _fetchOrders,
                      style: ElevatedButton.styleFrom(backgroundColor: const Color(0xFF047857), foregroundColor: Colors.white),
                      child: const Text("খুঁজুন"),
                    ),
                  ],
                ),
              ],
            ),
          ),
          const Divider(height: 1),
          Expanded(
            child: _loading
                ? const Center(child: CircularProgressIndicator())
                : _orders.isEmpty
                    ? const Center(
                        child: Text(
                          "কোনো ফার্মেসী অর্ডার পাওয়া যায়নি।",
                          style: TextStyle(color: Colors.grey, fontWeight: FontWeight.w600),
                        ),
                      )
                    : ListView.builder(
                        controller: scrollCtrl,
                        padding: const EdgeInsets.all(12),
                        itemCount: _orders.length,
                        itemBuilder: (_, idx) {
                          final o = _orders[idx] as Map<String, dynamic>;
                          final String orderNum = (o['order_number'] ?? '').toString();
                          final String st = (o['order_status'] ?? 'reviewing').toString();
                          final String rxUrl = (o['prescription_enhanced_url'] ?? o['prescription_url'] ?? '').toString();
                          final String rxOrig = (o['prescription_original_url'] ?? o['prescription_url'] ?? '').toString();
                          final double subtotal = double.tryParse(o['subtotal']?.toString() ?? '0') ?? 0.0;
                          final double delChg = double.tryParse(o['delivery_charge']?.toString() ?? '50') ?? 50.0;
                          final double total = double.tryParse(o['total_amount']?.toString() ?? '0') ?? 0.0;
                          final int durDays = int.tryParse(o['overall_duration_days']?.toString() ?? '0') ?? 0;
                          final String custNotes = (o['customer_notes'] ?? '').toString().trim();
                          final String adminNotes = (o['admin_notes'] ?? '').toString().trim();
                          final List<dynamic> appItems = (o['approved_items'] is List && (o['approved_items'] as List).isNotEmpty)
                              ? (o['approved_items'] as List)
                              : ((o['requested_items'] is List) ? (o['requested_items'] as List) : const []);
                          final bool isExpanded = _expandedOrders.contains(orderNum);
                          final bool isPdf = rxUrl.toLowerCase().contains('.pdf') || rxUrl.startsWith('data:application/pdf');

                          return Card(
                            margin: const EdgeInsets.only(bottom: 12),
                            shape: RoundedRectangleBorder(
                              borderRadius: BorderRadius.circular(14),
                              side: BorderSide(color: isExpanded ? const Color(0xFF10B981) : const Color(0xFFD1FAE5), width: isExpanded ? 1.6 : 1.0),
                            ),
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                InkWell(
                                  borderRadius: BorderRadius.circular(14),
                                  onTap: () {
                                    setState(() {
                                      if (isExpanded) {
                                        _expandedOrders.remove(orderNum);
                                      } else {
                                        _expandedOrders.add(orderNum);
                                      }
                                    });
                                  },
                                  child: Padding(
                                    padding: const EdgeInsets.all(12),
                                    child: Column(
                                      crossAxisAlignment: CrossAxisAlignment.start,
                                      children: [
                                        Row(
                                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                          children: [
                                            Text(orderNum, style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 13.5)),
                                            Container(
                                              padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                                              decoration: BoxDecoration(
                                                color: const Color(0xFFECFDF5),
                                                borderRadius: BorderRadius.circular(8),
                                              ),
                                              child: Text(_translateStatus(st),
                                                  style: const TextStyle(fontSize: 11, fontWeight: FontWeight.w800, color: Color(0xFF047857))),
                                            ),
                                          ],
                                        ),
                                        const SizedBox(height: 6),
                                        Row(
                                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                          children: [
                                            Expanded(
                                              child: Text(
                                                "মোট বিল: ${total > 0 ? '৳ ${total.toStringAsFixed(2)}' : 'যাচাই চলছে'} • OTP: ${o['delivery_otp'] ?? ''}",
                                                style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600),
                                              ),
                                            ),
                                            Row(
                                              children: [
                                                Text(
                                                  isExpanded ? "সংক্ষিপ্ত" : "বিস্তারিত",
                                                  style: const TextStyle(fontSize: 11.5, fontWeight: FontWeight.w800, color: Color(0xFF047857)),
                                                ),
                                                Icon(
                                                  isExpanded ? Icons.keyboard_arrow_up : Icons.keyboard_arrow_down,
                                                  size: 18,
                                                  color: const Color(0xFF047857),
                                                ),
                                              ],
                                            ),
                                          ],
                                        ),
                                      ],
                                    ),
                                  ),
                                ),

                                if (isExpanded) ...[
                                  const Divider(height: 1),
                                  Padding(
                                    padding: const EdgeInsets.all(12),
                                    child: Column(
                                      crossAxisAlignment: CrossAxisAlignment.start,
                                      children: [
                                        Text(
                                          "👤 ${o['customer_name'] ?? ''} (${o['customer_phone'] ?? ''})",
                                          style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w700),
                                        ),
                                        const SizedBox(height: 3),
                                        Text(
                                          "📍 ${o['delivery_address'] ?? ''}, ${o['area'] ?? ''}, ${o['district'] ?? ''}",
                                          style: TextStyle(fontSize: 11.5, color: Colors.grey[700]),
                                        ),
                                        const SizedBox(height: 6),
                                        Container(
                                          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                                          decoration: BoxDecoration(
                                            color: durDays > 0 ? const Color(0xFFECFDF5) : const Color(0xFFFEF3C7),
                                            borderRadius: BorderRadius.circular(6),
                                          ),
                                          child: Text(
                                            durDays > 0 ? "⏱️ চাহিদা: $durDays দিনের ওষুধ" : "📝 চাহিদা: নোটে উল্লিখিত",
                                            style: TextStyle(
                                              fontSize: 11.5,
                                              fontWeight: FontWeight.w800,
                                              color: durDays > 0 ? const Color(0xFF047857) : const Color(0xFF92400E),
                                            ),
                                          ),
                                        ),
                                        if (custNotes.isNotEmpty) ...[
                                          const SizedBox(height: 6),
                                          Text("💬 আপনার নোট: $custNotes", style: const TextStyle(fontSize: 12)),
                                        ],
                                        if (adminNotes.isNotEmpty) ...[
                                          const SizedBox(height: 4),
                                          Text("👨‍⚕️ ফার্মাসিস্ট নোট: $adminNotes",
                                              style: const TextStyle(fontSize: 12, fontWeight: FontWeight.w600, color: Color(0xFF047857))),
                                        ],
                                        if (rxUrl.isNotEmpty) ...[
                                          const SizedBox(height: 10),
                                          const Text("📄 আপলোডকৃত প্রেসক্রিপশন (বড় করে দেখতে ট্যাপ করুন):",
                                              style: TextStyle(fontSize: 12, fontWeight: FontWeight.w800, color: Color(0xFF065F46))),
                                          const SizedBox(height: 6),
                                          InkWell(
                                            onTap: () => _openPrescriptionZoom(rxUrl, rxOrig),
                                            child: isPdf
                                                ? Container(
                                                    width: double.infinity,
                                                    padding: const EdgeInsets.all(12),
                                                    decoration: BoxDecoration(
                                                      color: Colors.red.shade50,
                                                      borderRadius: BorderRadius.circular(10),
                                                      border: Border.all(color: Colors.red.shade200),
                                                    ),
                                                    child: const Row(
                                                      children: [
                                                        Icon(Icons.picture_as_pdf, color: Colors.red, size: 28),
                                                        SizedBox(width: 8),
                                                        Expanded(child: Text("PDF প্রেসক্রিপশন দেখুন", style: TextStyle(fontWeight: FontWeight.bold, color: Colors.red))),
                                                        Icon(Icons.open_in_new, color: Colors.red, size: 18),
                                                      ],
                                                    ),
                                                  )
                                                : ClipRRect(
                                                    borderRadius: BorderRadius.circular(10),
                                                    child: Container(
                                                      width: double.infinity,
                                                      height: 180,
                                                      color: Colors.black87,
                                                      child: AppImageLoader(imageUrl: rxUrl, fit: BoxFit.contain),
                                                    ),
                                                  ),
                                          ),
                                        ],
                                        if (appItems.isNotEmpty) ...[
                                          const SizedBox(height: 10),
                                          const Text("💊 অর্ডারকৃত ঔষধসমূহ (ক্লিক করলে ঔষধে যাবে):",
                                              style: TextStyle(fontSize: 12, fontWeight: FontWeight.w800, color: Color(0xFF065F46))),
                                          const SizedBox(height: 6),
                                          ...appItems.whereType<Map>().map((it) {
                                            final mName = (it['name'] ?? it['product_name'] ?? 'Medicine').toString();
                                            final mQty = int.tryParse(it['quantity']?.toString() ?? '1') ?? 1;
                                            final mTotal = double.tryParse(it['total_price']?.toString() ?? '0') ?? 0.0;
                                            return InkWell(
                                              onTap: () {
                                                if (widget.onSelectMedicine != null) {
                                                  widget.onSelectMedicine!(mName);
                                                }
                                              },
                                              borderRadius: BorderRadius.circular(8),
                                              child: Container(
                                                margin: const EdgeInsets.only(bottom: 5),
                                                padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 7),
                                                decoration: BoxDecoration(
                                                  color: const Color(0xFFF0FDF4),
                                                  borderRadius: BorderRadius.circular(8),
                                                  border: Border.all(color: const Color(0xFFA7F3D0)),
                                                ),
                                                child: Row(
                                                  children: [
                                                    const Text("💊 ", style: TextStyle(fontSize: 13)),
                                                    Expanded(
                                                      child: Text(
                                                        "$mName ${it['strength'] ?? ''} × $mQty",
                                                        style: const TextStyle(fontSize: 12.5, fontWeight: FontWeight.w700),
                                                      ),
                                                    ),
                                                    if (mTotal > 0)
                                                      Text("৳ ${mTotal.toStringAsFixed(0)}",
                                                          style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 12.5, color: Color(0xFF047857))),
                                                    const SizedBox(width: 4),
                                                    const Icon(Icons.arrow_forward_ios, size: 12, color: Color(0xFF047857)),
                                                  ],
                                                ),
                                              ),
                                            );
                                          }),
                                        ],
                                        const Divider(height: 16),
                                        Row(
                                          mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                          children: [
                                            Text("সাবটোটাল: ৳${subtotal.toStringAsFixed(0)} + ডেলিভারি: ৳${delChg.toStringAsFixed(0)}",
                                                style: TextStyle(fontSize: 11.5, color: Colors.grey[700])),
                                            Text("মোট: ${total > 0 ? '৳${total.toStringAsFixed(2)}' : 'যাচাই চলছে'}",
                                                style: const TextStyle(fontWeight: FontWeight.w900, fontSize: 13.5, color: Color(0xFF047857))),
                                          ],
                                        ),
                                        if (st == 'awaiting_customer_confirmation') ...[
                                          const SizedBox(height: 12),
                                          Container(
                                            padding: const EdgeInsets.all(10),
                                            decoration: BoxDecoration(
                                              color: const Color(0xFFFFFBEB),
                                              borderRadius: BorderRadius.circular(10),
                                              border: Border.all(color: const Color(0xFFF59E0B), width: 1.5),
                                            ),
                                            child: Column(
                                              crossAxisAlignment: CrossAxisAlignment.start,
                                              children: [
                                                const Text(
                                                  "🔔 আপনার প্রেসক্রিপশন যাচাই করে বিল প্রস্তুত হয়েছে!",
                                                  style: TextStyle(fontWeight: FontWeight.w800, fontSize: 12.5, color: Color(0xFF92400E)),
                                                ),
                                                const SizedBox(height: 4),
                                                Text(
                                                  "মোট প্রদেয় ৳${total.toStringAsFixed(2)} — আপনি কনফার্ম করলেই কেবল প্যাকিং ও ডেলিভারি শুরু হবে।",
                                                  style: const TextStyle(fontSize: 11.5, color: Color(0xFF78350F)),
                                                ),
                                                const SizedBox(height: 8),
                                                Row(
                                                  children: [
                                                    Expanded(
                                                      child: ElevatedButton.icon(
                                                        onPressed: () async {
                                                          final res = await ApiService.confirmPharmacyQuote(
                                                            orderNumber: orderNum,
                                                            customerPhone: (o['customer_phone'] ?? '').toString(),
                                                            action: 'confirm',
                                                          );
                                                          if (!mounted) return;
                                                          ScaffoldMessenger.of(context).showSnackBar(
                                                            SnackBar(
                                                              content: Text(res['message']?.toString() ?? 'কনফার্ম সম্পন্ন'),
                                                              backgroundColor: res['success'] == true ? Colors.green : Colors.red,
                                                            ),
                                                          );
                                                          if (res['success'] == true) _fetchOrders();
                                                        },
                                                        icon: const Icon(Icons.check_circle, size: 16, color: Colors.white),
                                                        label: const Text("বিল কনফার্ম করুন", style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 12)),
                                                        style: ElevatedButton.styleFrom(backgroundColor: const Color(0xFF059669)),
                                                      ),
                                                    ),
                                                    const SizedBox(width: 8),
                                                    OutlinedButton(
                                                      onPressed: () async {
                                                        final res = await ApiService.confirmPharmacyQuote(
                                                          orderNumber: orderNum,
                                                          customerPhone: (o['customer_phone'] ?? '').toString(),
                                                          action: 'cancel',
                                                        );
                                                        if (!mounted) return;
                                                        ScaffoldMessenger.of(context).showSnackBar(
                                                          SnackBar(
                                                            content: Text(res['message']?.toString() ?? 'বাতিল হয়েছে'),
                                                            backgroundColor: res['success'] == true ? Colors.orange : Colors.red,
                                                          ),
                                                        );
                                                        if (res['success'] == true) _fetchOrders();
                                                      },
                                                      child: const Text("বাতিল", style: TextStyle(color: Colors.red, fontWeight: FontWeight.bold, fontSize: 12)),
                                                    ),
                                                  ],
                                                ),
                                              ],
                                            ),
                                          ),
                                        ],
                                      ],
                                    ),
                                  ),
                                ],
                              ],
                            ),
                          );
                        },
                      ),
          ),
        ],
      ),
    );
  }
}
