import '../../widgets/quantity_limit_dialog.dart';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../../localization/app_localizations.dart';
import '../../providers/cart_provider.dart';
import '../../services/api_service.dart';
import '../../widgets/app_image_loader.dart';
import '../../widgets/location_selector_dialog.dart';
import 'home_screen.dart';
import 'my_orders_screen.dart';
import '../auth/login_screen.dart';

class CartScreen extends StatefulWidget {
  const CartScreen({Key? key}) : super(key: key);

  @override
  State<CartScreen> createState() => _CartScreenState();
}

class _CartScreenState extends State<CartScreen> {
  String _selectedPayment = 'cod';
  bool _isSubmitting = false;

  final TextEditingController _nameController = TextEditingController();
  final TextEditingController _phoneController = TextEditingController();
  final TextEditingController _addressController = TextEditingController();
  final TextEditingController _voucherController = TextEditingController();

  double _productVoucherDiscount = 0.0;
  double _deliveryVoucherDiscount = 0.0;
  String _appliedVoucherCode = '';
  String _appliedVoucherType = '';
  bool _isVerifyingVoucher = false;
  bool _isVoucherExpanded = false;

  void _applyVoucher() async {
    String code = _voucherController.text.trim().toUpperCase();
    if (code.isEmpty) return;

    final cartProv = Provider.of<CartProvider>(context, listen: false);

    // Instant check: Coupons are not applicable to Combo Package items
    bool hasComboPackage = cartProv.items.any((item) => item.product.isComboPackage);

    if (hasComboPackage) {
      showDialog(
        context: context,
        builder: (ctx) => AlertDialog(
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
          title: const Row(
            children: [
              Icon(Icons.info_outline, color: Colors.orange, size: 28),
              SizedBox(width: 8),
              Text("Coupon Not Applicable"),
            ],
          ),
          content: const Text(
            "Coupons or Vouchers cannot be applied to Combo Package orders."
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(ctx),
              child: const Text("OK", style: TextStyle(fontWeight: FontWeight.bold)),
            ),
          ],
        ),
      );
      return;
    }

    List cartItems = cartProv.items.map((item) => {
      'product_id': item.product.id,
      'product_name': item.product.name,
      'unit': item.product.unit,
      'quantity': item.quantity,
      'price': item.product.sellPrice,
    }).toList();

    setState(() {
      _isVerifyingVoucher = true;
    });

    var res = await ApiService.httpPost(
      '/api/vouchers/apply',
      body: jsonEncode({
        'code': code,
        'cart_items': cartItems,
        'delivery_charge': cartProv.deliveryCharge,
      }),
      timeout: const Duration(seconds: 3),
    );

    if (!mounted) return;
    setState(() {
      _isVerifyingVoucher = false;
    });

    if (res != null && res.statusCode == 200) {
      var data = jsonDecode(res.body);
      if (data['success'] == true) {
        double amt = ((data['discount_amount'] ?? 0) as num).toDouble();
        if (amt <= 0) {
          showDialog(
            context: context,
            builder: (ctx) => AlertDialog(
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
              title: const Row(
                children: [
                  Icon(Icons.error_outline, color: Colors.red),
                  SizedBox(width: 8),
                  Text("Coupon Not Applicable"),
                ],
              ),
              content: Text(data['message'] ?? "Voucher '$code' is not valid for items in your cart."),
              actions: [
                TextButton(
                  onPressed: () => Navigator.pop(ctx),
                  child: const Text("OK"),
                ),
              ],
            ),
          );
          return;
        }

        String type = data['target_type'] ?? 'product_discount';
        setState(() {
          _appliedVoucherCode = code;
          _appliedVoucherType = type;
          if (type == 'delivery_discount') {
            _deliveryVoucherDiscount = amt;
            _productVoucherDiscount = 0.0;
          } else {
            _productVoucherDiscount = amt;
            _deliveryVoucherDiscount = 0.0;
          }
        });
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text(data['message'] ?? "Voucher applied successfully!"),
            backgroundColor: Colors.green,
          ),
        );
      }
    } else {
      String errMsg = "Voucher is not valid for items in your cart.";
      if (res != null) {
        try {
          var errData = jsonDecode(res.body);
          if (errData['message'] != null) errMsg = errData['message'];
        } catch (_) {}
      }
      showDialog(
        context: context,
        builder: (ctx) => AlertDialog(
          title: const Row(
            children: [
              Icon(Icons.error_outline, color: Colors.red),
              SizedBox(width: 8),
              Text("Voucher Cannot Be Applied"),
            ],
          ),
          content: Text(errMsg),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(ctx),
              child: const Text("OK"),
            ),
          ],
        ),
      );
    }
  }

  @override
  void initState() {
    super.initState();
    _loadUserData();
    WidgetsBinding.instance.addPostFrameCallback((_) {
      Provider.of<CartProvider>(context, listen: false).refreshDeliveryCharge();
    });
  }

  void _loadUserData() async {
    final prefs = await SharedPreferences.getInstance();
    if (!mounted) return;
    setState(() {
      _nameController.text = prefs.getString('user_name') ?? '';
      _phoneController.text = prefs.getString('user_phone') ?? '';
    });
  }

  void _placeOrder() async {
    final cartProv = Provider.of<CartProvider>(context, listen: false);
    final loc = AppLocalizations.of(context);

    if (cartProv.items.isEmpty) return;

    // Check stock for all items before placing order
    for (var item in cartProv.items) {
      if (item.product.stockQty <= 0) {
        showDialog(
          context: context,
          builder: (dialogCtx) => AlertDialog(
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
            title: const Row(
              children: [
                Icon(Icons.error_outline, color: Colors.red),
                SizedBox(width: 8),
                Text("Out of Stock Item"),
              ],
            ),
            content: Text('Item "${item.product.name}" is OUT OF STOCK. Please remove it from your shopping bag before placing the order.'),
            actions: [
              ElevatedButton(
                onPressed: () => Navigator.pop(dialogCtx),
                style: ElevatedButton.styleFrom(backgroundColor: Colors.red),
                child: const Text("OK", style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
              ),
            ],
          ),
        );
        return;
      }
      if (item.quantity > item.product.stockQty) {
        showDialog(
          context: context,
          builder: (dialogCtx) => AlertDialog(
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
            title: const Row(
              children: [
                Icon(Icons.error_outline, color: Colors.orange),
                SizedBox(width: 8),
                Text("Insufficient Stock"),
              ],
            ),
            content: Text('Item "${item.product.name}" has only ${item.product.stockQty} in stock, but ${item.quantity} requested. Please reduce the quantity in your bag.'),
            actions: [
              ElevatedButton(
                onPressed: () => Navigator.pop(dialogCtx),
                style: ElevatedButton.styleFrom(backgroundColor: Colors.orange),
                child: const Text("OK", style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
              ),
            ],
          ),
        );
        return;
      }
    }

    final prefs = await SharedPreferences.getInstance();
    String savedPhone = prefs.getString('user_phone') ?? '';

    if (savedPhone.isEmpty) {
      showDialog(
        context: context,
        builder: (dialogCtx) => AlertDialog(
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
          title: const Row(
            children: [
              Icon(Icons.lock, color: Colors.green),
              SizedBox(width: 8),
              Text("Sign In Required"),
            ],
          ),
          content: const Text("You must be signed in to place an order. Please sign in or register to complete your purchase."),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(dialogCtx),
              child: const Text("Cancel"),
            ),
            ElevatedButton(
              onPressed: () async {
                Navigator.pop(dialogCtx);
                await Navigator.push(
                  context,
                  MaterialPageRoute(builder: (_) => const LoginScreen()),
                );
                _loadUserData();
              },
              style: ElevatedButton.styleFrom(backgroundColor: Colors.green),
              child: const Text("Sign In / Register", style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
            ),
          ],
        ),
      );
      return;
    }

    String savedName = prefs.getString('user_name') ?? '';
    String custName = _nameController.text.trim().isNotEmpty 
        ? _nameController.text.trim() 
        : (savedName.isNotEmpty ? savedName : 'Customer User');

    String custPhone = _phoneController.text.trim().isNotEmpty
        ? _phoneController.text.trim()
        : savedPhone;

    custPhone = custPhone.replaceAll(RegExp(r'[^\d+]'), '');
    if (custPhone.startsWith('+88')) {
      custPhone = custPhone.substring(3);
    } else if (custPhone.startsWith('88') && custPhone.length == 13) {
      custPhone = custPhone.substring(2);
    }

    if (custPhone.isEmpty || custPhone.length != 11 || !custPhone.startsWith('01')) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text("Mobile number must start with '01' and be exactly 11 digits (e.g. 01700000000). Current: '$custPhone'"),
          backgroundColor: Colors.red,
        ),
      );
      return;
    }

    String detailAddress = _addressController.text.trim();
    if (detailAddress.isEmpty && cartProv.addressDetails.trim().isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text("House/Road Number & Detailed Address cannot be blank. Please enter your address details."),
          backgroundColor: Colors.red,
        ),
      );
      return;
    }

    String address = detailAddress.isNotEmpty
        ? detailAddress
        : cartProv.addressDetails;

    setState(() {
      _isSubmitting = true;
    });

    List<Map<String, dynamic>> cartPayload = cartProv.items.map((item) {
      return {
        'product_id': item.product.id,
        'id': item.product.id,
        'product_name': item.product.name,
        'name': item.product.name,
        'quantity': item.quantity,
        'unit_price': item.product.sellPrice,
        'mrp_price': item.product.mrp,
      };
    }).toList();

    var res = await ApiService.placeOrder(
      customerName: custName,
      customerPhone: custPhone,
      customerEmail: '',
      country: cartProv.selectedCountry,
      district: cartProv.selectedDistrict,
      area: cartProv.selectedArea,
      addressDetails: address,
      paymentMethod: _selectedPayment,
      cartItems: cartPayload,
    );

    if (!mounted) return;

    setState(() {
      _isSubmitting = false;
    });

    if (res['success'] == true) {
      cartProv.clearCart();
      showDialog(
        context: context,
        barrierDismissible: false,
        builder: (ctx) => AlertDialog(
          title: const Row(
            children: [
              Icon(Icons.check_circle, color: Colors.green),
              SizedBox(width: 8),
              Text("Order Placed Successfully!"),
            ],
          ),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text("Order Number: ${res['order_number']}"),
              if (res['requires_call_confirmation'] == true || (res['call_notice'] != null && res['call_notice'].toString().isNotEmpty)) ...[
                const SizedBox(height: 8),
                Container(
                  padding: const EdgeInsets.all(10),
                  decoration: BoxDecoration(
                    color: const Color(0xFFFFF7ED),
                    borderRadius: BorderRadius.circular(8),
                    border: Border.all(color: const Color(0xFFFED7AA)),
                  ),
                  child: Row(
                    children: [
                      const Icon(Icons.phone_in_talk, color: Color(0xFFEA580C), size: 20),
                      const SizedBox(width: 8),
                      Expanded(
                        child: Text(
                          res['call_notice']?.toString() ?? "Our store helpline will call your mobile number to confirm your address before delivery dispatch.",
                          style: const TextStyle(fontSize: 12, color: Color(0xFF9A3412), fontWeight: FontWeight.bold),
                        ),
                      ),
                    ],
                  ),
                ),
              ],
              const SizedBox(height: 8),
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: Colors.red[50],
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: Colors.red.shade200),
                ),
                child: Column(
                  children: [
                    const Text(
                      "🔑 Delivery OTP:",
                      style: TextStyle(fontWeight: FontWeight.bold, fontSize: 13),
                    ),
                    const SizedBox(height: 4),
                    Text(
                      res['delivery_otp'].toString(),
                      style: const TextStyle(
                        fontSize: 24,
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
          actions: [
            ElevatedButton(
              onPressed: () {
                Navigator.pop(ctx);
                Navigator.pushReplacement(
                  context,
                  MaterialPageRoute(builder: (_) => const MyOrdersScreen()),
                );
              },
              style: ElevatedButton.styleFrom(backgroundColor: Colors.green),
              child: const Text("Track Order Status"),
            ),
          ],
        ),
      );
    } else {
      showDialog(
        context: context,
        builder: (ctx) => AlertDialog(
          title: const Row(
            children: [
              Icon(Icons.error, color: Colors.red),
              SizedBox(width: 8),
              Text("Could Not Place Order"),
            ],
          ),
          content: Text(res['message'] ?? 'Error placing order'),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(ctx),
              child: const Text("OK"),
            ),
          ],
        ),
      );
    }
  }

  Widget _buildPaymentOption({required String value, required String title, String? subtitle, bool enabled = true}) {
    bool isSelected = _selectedPayment == value && enabled;
    return InkWell(
      onTap: enabled ? () => setState(() => _selectedPayment = value) : null,
      child: Container(
        padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 12),
        decoration: BoxDecoration(
          color: !enabled ? Colors.grey.shade100 : (isSelected ? Colors.green.shade50 : Colors.white),
          border: Border.all(color: isSelected ? Colors.green : Colors.grey.shade300, width: isSelected ? 2 : 1),
          borderRadius: BorderRadius.circular(8),
        ),
        child: Row(
          children: [
            Icon(
              !enabled ? Icons.block : (isSelected ? Icons.radio_button_checked : Icons.radio_button_off),
              color: !enabled ? Colors.grey : (isSelected ? Colors.green : Colors.grey),
            ),
            const SizedBox(width: 12),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    title,
                    style: TextStyle(
                      fontWeight: FontWeight.bold,
                      color: !enabled ? Colors.grey : (isSelected ? Colors.green.shade900 : Colors.black),
                    ),
                  ),
                  if (subtitle != null)
                    Text(subtitle, style: TextStyle(fontSize: 12, color: !enabled ? Colors.grey.shade500 : Colors.grey)),
                ],
              ),
            ),
          ],
        ),
      ),
    );
  }

  @override
  Widget build(BuildContext context) {
    final loc = AppLocalizations.of(context);
    final cartProv = Provider.of<CartProvider>(context);

    return Scaffold(
      appBar: AppBar(
        leading: IconButton(
          icon: const Icon(Icons.arrow_back, color: Colors.white),
          tooltip: "Back to All Products",
          onPressed: () {
            if (Navigator.canPop(context)) {
              Navigator.pop(context);
            } else {
              Navigator.pushReplacement(
                context,
                MaterialPageRoute(builder: (_) => const HomeScreen()),
              );
            }
          },
        ),
        title: Text(loc.translate('cart')),
        backgroundColor: Colors.green,
      ),
      body: cartProv.items.isEmpty
          ? const Center(child: Text("Your shopping cart is empty"))
          : SingleChildScrollView(
              padding: const EdgeInsets.all(16.0),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  // Item List
                  ListView.separated(
                    shrinkWrap: true,
                    physics: const NeverScrollableScrollPhysics(),
                    itemCount: cartProv.items.length,
                    separatorBuilder: (_, __) => const Divider(),
                    itemBuilder: (context, index) {
                      final item = cartProv.items[index];
                      String imgUrl = item.product.imageList.isNotEmpty
                          ? item.product.imageList.first
                          : item.product.imageUrl;

                      return Row(
                        children: [
                          ClipRRect(
                            borderRadius: BorderRadius.circular(8),
                            child: SizedBox(
                              width: 56,
                              height: 56,
                              child: AppImageLoader(
                                imageUrl: imgUrl,
                                width: 56,
                                height: 56,
                                fit: BoxFit.contain,
                              ),
                            ),
                          ),
                          const SizedBox(width: 10),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(item.product.name, style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13)),
                                Text('TK ${item.product.sellPrice.toStringAsFixed(0)} × ${item.quantity}', style: const TextStyle(color: Colors.grey, fontSize: 12)),
                                if (item.product.stockQty <= 0)
                                  Container(
                                    margin: const EdgeInsets.only(top: 3),
                                    padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                                    decoration: BoxDecoration(color: Colors.red.shade50, borderRadius: BorderRadius.circular(4), border: Border.all(color: Colors.red.shade200)),
                                    child: const Text("⚠️ OUT OF STOCK", style: TextStyle(fontSize: 10, fontWeight: FontWeight.bold, color: Colors.red)),
                                  ),
                                if (item.isBuyOffer) ...[
                                  const SizedBox(height: 2),
                                  Text(
                                    item.freeQuantity > 0
                                        ? "🎁 BOGO Offer: ${item.freeQuantity} Free Item(s) Included!"
                                        : (item.product.offerTitle.isNotEmpty
                                            ? "💡 ${item.product.offerTitle} Available"
                                            : "💡 Buy ${item.buyQuantity} Get ${item.freePerSetQuantity} FREE Offer Available"),
                                    style: TextStyle(
                                      fontSize: 11,
                                      fontWeight: FontWeight.bold,
                                      color: item.freeQuantity > 0 ? Colors.purple : Colors.orange.shade800,
                                    ),
                                  ),
                                ],
                              ],
                            ),
                          ),
                          Row(
                            children: [
                              IconButton(
                                icon: const Icon(Icons.remove_circle_outline, size: 20),
                                onPressed: () => cartProv.updateQuantity(item.product.id, item.quantity - 1),
                              ),
                              Text('${item.quantity}', style: const TextStyle(fontWeight: FontWeight.bold)),
                              IconButton(
                                icon: const Icon(Icons.add_circle_outline, size: 20),
                                onPressed: () {
                                  bool ok = cartProv.updateQuantity(item.product.id, item.quantity + 1);
                                  if (!ok) {
                                    showQuantityLimitDialog(context, cartProv.lastError ?? 'Cannot add more: only ${item.product.stockQty} available in stock.');
                                  }
                                },
                              ),
                            ],
                          ),
                          Text('TK ${item.totalPrice.toStringAsFixed(0)}', style: const TextStyle(fontWeight: FontWeight.bold, color: Colors.green, fontSize: 13)),
                        ],
                      );
                    },
                  ),
                  const Divider(thickness: 2),

                  // Delivery Location Card
                  Card(
                    color: Colors.blue[50],
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                    child: Padding(
                      padding: const EdgeInsets.all(12.0),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: [
                              const Row(
                                children: [
                                  Icon(Icons.location_on, color: Colors.blue),
                                  SizedBox(width: 6),
                                  Text("Delivery Location:", style: TextStyle(fontWeight: FontWeight.bold)),
                                ],
                              ),
                              TextButton(
                                onPressed: () {
                                  showDialog(
                                    context: context,
                                    builder: (_) => const LocationSelectorDialog(),
                                  );
                                },
                                child: const Text("Change"),
                              )
                            ],
                          ),
                          Text('📍 ${cartProv.selectedArea}, ${cartProv.selectedDistrict}, ${cartProv.selectedCountry}'),
                          const SizedBox(height: 8),
                          TextField(
                            controller: _addressController,
                            decoration: const InputDecoration(
                              labelText: 'House/Road Number & Detailed Address *',
                              hintText: 'e.g. House 12, Road 5, Block B',
                              border: OutlineInputBorder(),
                              isDense: true,
                            ),
                          ),
                        ],
                      ),
                    ),
                  ),
                  const SizedBox(height: 16),

                  // Customer Details
                  TextField(
                    controller: _nameController,
                    decoration: InputDecoration(
                      labelText: loc.translate('name'),
                      border: const OutlineInputBorder(),
                      isDense: true,
                    ),
                  ),
                  const SizedBox(height: 10),

                  TextField(
                    controller: _phoneController,
                    keyboardType: TextInputType.phone,
                    maxLength: 11,
                    inputFormatters: [
                      FilteringTextInputFormatter.digitsOnly,
                      LengthLimitingTextInputFormatter(11),
                    ],
                    decoration: InputDecoration(
                      labelText: loc.translate('phone_number'),
                      hintText: "01700000000",
                      counterText: "",
                      border: const OutlineInputBorder(),
                      isDense: true,
                    ),
                  ),
                  const SizedBox(height: 16),

                  // Payment Method Options
                  Text(loc.translate('payment_method'), style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
                  const SizedBox(height: 8),

                  Column(
                    children: [
                      _buildPaymentOption(
                        value: 'cod',
                        title: loc.translate('cod'),
                        subtitle: "Pay cash upon receiving product",
                        enabled: true,
                      ),
                      const SizedBox(height: 8),
                      _buildPaymentOption(
                        value: 'bkash',
                        title: loc.translate('bkash'),
                        subtitle: "Online payment gateway temporarily disabled",
                        enabled: false,
                      ),
                      const SizedBox(height: 8),
                      _buildPaymentOption(
                        value: 'nagad',
                        title: loc.translate('nagad'),
                        subtitle: "Online payment gateway temporarily disabled",
                        enabled: false,
                      ),
                    ],
                  ),

                  const SizedBox(height: 16),

                  // Expandable Voucher / Coupon Field
                  Card(
                    color: Colors.purple.shade50,
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10), side: BorderSide(color: Colors.purple.shade200)),
                    child: Padding(
                      padding: const EdgeInsets.all(12.0),
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          InkWell(
                            onTap: () {
                              setState(() {
                                _isVoucherExpanded = !_isVoucherExpanded;
                              });
                            },
                            child: Row(
                              mainAxisAlignment: MainAxisAlignment.spaceBetween,
                              children: [
                                const Row(
                                  children: [
                                    Icon(Icons.confirmation_number, color: Colors.purple),
                                    SizedBox(width: 6),
                                    Text("Have a Voucher / Coupon Code?", style: TextStyle(fontWeight: FontWeight.bold, color: Colors.purple)),
                                  ],
                                ),
                                Icon(
                                  _isVoucherExpanded ? Icons.keyboard_arrow_up : Icons.keyboard_arrow_down,
                                  color: Colors.purple,
                                  size: 24,
                                ),
                              ],
                            ),
                          ),
                          if (_isVoucherExpanded || _appliedVoucherCode.isNotEmpty) ...[
                            const SizedBox(height: 10),
                            Row(
                              children: [
                                Expanded(
                                  child: TextField(
                                    controller: _voucherController,
                                    textCapitalization: TextCapitalization.characters,
                                    decoration: const InputDecoration(
                                      hintText: "Enter Voucher (e.g. SAVE50)",
                                      border: OutlineInputBorder(),
                                      isDense: true,
                                      fillColor: Colors.white,
                                      filled: true,
                                    ),
                                  ),
                                ),
                                const SizedBox(width: 8),
                                ElevatedButton(
                                  onPressed: _isVerifyingVoucher ? null : _applyVoucher,
                                  style: ElevatedButton.styleFrom(backgroundColor: Colors.purple),
                                  child: _isVerifyingVoucher
                                      ? const SizedBox(width: 16, height: 16, child: CircularProgressIndicator(color: Colors.white, strokeWidth: 2))
                                      : const Text("Apply", style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
                                ),
                              ],
                            ),
                            if (_appliedVoucherCode.isNotEmpty) ...[
                              const SizedBox(height: 6),
                              Text(
                                _appliedVoucherType == 'delivery_discount'
                                    ? "✓ Delivery Voucher '$_appliedVoucherCode' Applied (-TK ${_deliveryVoucherDiscount.toStringAsFixed(2)})"
                                    : "✓ Voucher '$_appliedVoucherCode' Applied (-TK ${_productVoucherDiscount.toStringAsFixed(2)})",
                                style: const TextStyle(color: Colors.green, fontWeight: FontWeight.bold, fontSize: 13),
                              ),
                            ],
                          ],
                        ],
                      ),
                    ),
                  ),

                  const SizedBox(height: 16),

                  // Summary
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      const Text("Subtotal:"),
                      Text('TK ${cartProv.subtotal.toStringAsFixed(2)}'),
                    ],
                  ),
                  if (_productVoucherDiscount > 0) ...[
                    const SizedBox(height: 4),
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        const Text("Voucher Discount:", style: TextStyle(color: Colors.purple, fontWeight: FontWeight.bold)),
                        Text('-TK ${_productVoucherDiscount.toStringAsFixed(2)}', style: const TextStyle(color: Colors.purple, fontWeight: FontWeight.bold)),
                      ],
                    ),
                  ],
                  const SizedBox(height: 4),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(loc.translate('delivery_charge')),
                      cartProv.isFreeDelivery
                          ? Row(
                              children: [
                                Text(
                                  'TK ${cartProv.baseDeliveryCharge.toStringAsFixed(2)}',
                                  style: const TextStyle(
                                    decoration: TextDecoration.lineThrough,
                                    color: Colors.grey,
                                    fontSize: 12,
                                  ),
                                ),
                                const SizedBox(width: 6),
                                Container(
                                  padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                                  decoration: BoxDecoration(
                                    color: Colors.green.shade100,
                                    borderRadius: BorderRadius.circular(6),
                                    border: Border.all(color: Colors.green.shade300),
                                  ),
                                  child: const Text(
                                    'FREE (TK 0)',
                                    style: TextStyle(color: Colors.green, fontWeight: FontWeight.bold, fontSize: 13),
                                  ),
                                ),
                              ],
                            )
                          : Text(
                              _deliveryVoucherDiscount > 0
                                  ? 'TK ${(cartProv.deliveryCharge - _deliveryVoucherDiscount).clamp(0, double.infinity).toStringAsFixed(2)} (Discounted)'
                                  : 'TK ${cartProv.deliveryCharge.toStringAsFixed(2)}',
                              style: TextStyle(
                                color: _deliveryVoucherDiscount > 0 ? Colors.green : Colors.black,
                                fontWeight: _deliveryVoucherDiscount > 0 ? FontWeight.bold : FontWeight.normal,
                              ),
                            ),
                    ],
                  ),
                  if (cartProv.freeDeliveryActive && !cartProv.isFreeDelivery && cartProv.subtotal > 0) ...[
                    const SizedBox(height: 4),
                    Text(
                      '🚚 Add TK ${(cartProv.freeDeliveryMinAmount - cartProv.subtotal).toStringAsFixed(2)} more for FREE Delivery!',
                      style: TextStyle(color: Colors.indigo.shade600, fontSize: 11.5, fontWeight: FontWeight.bold),
                    ),
                  ],
                  if (_deliveryVoucherDiscount > 0) ...[
                    const SizedBox(height: 4),
                    Row(
                      mainAxisAlignment: MainAxisAlignment.spaceBetween,
                      children: [
                        const Text("Delivery Discount:", style: TextStyle(color: Colors.blue, fontWeight: FontWeight.bold)),
                        Text('-TK ${_deliveryVoucherDiscount.toStringAsFixed(2)}', style: const TextStyle(color: Colors.blue, fontWeight: FontWeight.bold)),
                      ],
                    ),
                  ],
                  const Divider(),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(loc.translate('total'), style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 18)),
                      Text(
                        'TK ${(((cartProv.subtotal - _productVoucherDiscount)) + (cartProv.deliveryCharge - _deliveryVoucherDiscount)).clamp(0, double.infinity).toStringAsFixed(2)}',
                        style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 20, color: Colors.green),
                      ),
                    ],
                  ),
                  const SizedBox(height: 12),
                  const Center(
                    child: Text(
                      "By clicking 'Confirm Order', you agree to our Terms and Conditions",
                      textAlign: TextAlign.center,
                      style: TextStyle(fontSize: 11, color: Colors.grey, fontWeight: FontWeight.w500),
                    ),
                  ),
                  const SizedBox(height: 8),

                  // Place Order Button
                  SizedBox(
                    width: double.infinity,
                    height: 50,
                    child: ElevatedButton(
                      onPressed: _isSubmitting ? null : _placeOrder,
                      style: ElevatedButton.styleFrom(backgroundColor: Colors.green),
                      child: _isSubmitting
                          ? const CircularProgressIndicator(color: Colors.white)
                          : Text(
                              loc.translate('place_order'),
                              style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: Colors.white),
                            ),
                    ),
                  ),
                ],
              ),
            ),
    );
  }
}
