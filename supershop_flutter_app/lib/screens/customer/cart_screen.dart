import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../../localization/app_localizations.dart';
import '../../providers/cart_provider.dart';
import '../../services/api_service.dart';
import '../../widgets/location_selector_dialog.dart';
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

    if (custPhone.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text("Please enter a valid phone number")),
      );
      return;
    }

    String address = _addressController.text.trim().isNotEmpty
        ? _addressController.text.trim()
        : (cartProv.addressDetails.isNotEmpty ? cartProv.addressDetails : "Delivery Location: ${cartProv.selectedArea}, ${cartProv.selectedDistrict}");

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
                            child: imgUrl.isNotEmpty
                                ? Image.network(
                                    imgUrl.split(',').first.trim(),
                                    width: 56,
                                    height: 56,
                                    fit: BoxFit.cover,
                                    errorBuilder: (_, __, ___) => Container(
                                      width: 56,
                                      height: 56,
                                      color: Colors.grey.shade200,
                                      child: const Icon(Icons.shopping_bag, size: 28, color: Colors.grey),
                                    ),
                                  )
                                : Container(
                                    width: 56,
                                    height: 56,
                                    color: Colors.grey.shade200,
                                    child: const Icon(Icons.shopping_bag, size: 28, color: Colors.grey),
                                  ),
                          ),
                          const SizedBox(width: 10),
                          Expanded(
                            child: Column(
                              crossAxisAlignment: CrossAxisAlignment.start,
                              children: [
                                Text(item.product.name, style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13)),
                                Text('TK ${item.product.sellPrice.toStringAsFixed(0)} × ${item.quantity}', style: const TextStyle(color: Colors.grey, fontSize: 12)),
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
                                onPressed: () => cartProv.updateQuantity(item.product.id, item.quantity + 1),
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
                              labelText: 'House/Road Number & Detailed Address',
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
                    decoration: InputDecoration(
                      labelText: loc.translate('phone_number'),
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

                  // Summary
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      const Text("Subtotal:"),
                      Text('TK ${cartProv.subtotal.toStringAsFixed(2)}'),
                    ],
                  ),
                  const SizedBox(height: 4),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(loc.translate('delivery_charge')),
                      Text('TK ${cartProv.deliveryCharge.toStringAsFixed(2)}'),
                    ],
                  ),
                  const Divider(),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text(loc.translate('total'), style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 18)),
                      Text(
                        'TK ${cartProv.grandTotal.toStringAsFixed(2)}',
                        style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 20, color: Colors.green),
                      ),
                    ],
                  ),
                  const SizedBox(height: 24),

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
