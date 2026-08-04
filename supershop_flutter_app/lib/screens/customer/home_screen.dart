import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../../localization/app_localizations.dart';
import '../../models/product.dart';
import '../../providers/cart_provider.dart';
import '../../providers/locale_provider.dart';
import '../../services/api_service.dart';

import 'cart_screen.dart';
import '../../widgets/location_selector_dialog.dart';
import 'my_orders_screen.dart';
import 'product_detail_screen.dart';
import 'profile_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({Key? key}) : super(key: key);

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> {
  String _selectedTab = 'all'; // all, trending, flash_sale, offers
  String _shopName = "DOINEEK (দৈনিক) Supershop";
  String _userAvatar = "👤";
  String _userImageBase64 = "";

  @override
  void initState() {
    super.initState();
    _loadShopName();
    _loadUserProfile();
  }

  void _loadShopName() async {
    var settings = await ApiService.fetchShopSettings();
    if (!mounted) return;
    setState(() {
      _shopName = settings['shop_name'] ?? "DOINEEK (দৈনিক) Supershop";
    });
  }

  void _loadUserProfile() async {
    final prefs = await SharedPreferences.getInstance();
    if (!mounted) return;
    setState(() {
      _userAvatar = prefs.getString('user_avatar') ?? '👤';
      _userImageBase64 = prefs.getString('user_image_base64') ?? '';
    });
  }

  ImageProvider? _getTopBarImageProvider() {
    if (_userImageBase64.isNotEmpty) {
      if (_userImageBase64.startsWith('http://') || _userImageBase64.startsWith('https://')) {
        return NetworkImage(_userImageBase64);
      }
      try {
        String cleanB64 = _userImageBase64.contains(',')
            ? _userImageBase64.split(',').last
            : _userImageBase64;
        return MemoryImage(base64Decode(cleanB64));
      } catch (e) {
        debugPrint("Error decoding top bar image: $e");
      }
    }
    return null;
  }

  List<Product> _filterProducts(List<Product> allProducts) {
    if (_selectedTab == 'trending') {
      return allProducts.where((p) => p.isTrending).toList();
    } else if (_selectedTab == 'flash_sale') {
      return allProducts.where((p) => p.isFlashSale).toList();
    } else if (_selectedTab == 'offers') {
      return allProducts.where((p) => p.isOffer).toList();
    }
    return allProducts;
  }

  @override
  Widget build(BuildContext context) {
    final loc = AppLocalizations.of(context);
    final localeProv = Provider.of<LocaleProvider>(context);
    final cartProv = Provider.of<CartProvider>(context);
    final isDark = Theme.of(context).brightness == Brightness.dark;

    return Scaffold(
      appBar: AppBar(
        backgroundColor: Colors.green,
        title: Row(
          children: [
            // Website Brand Logo Image
            Image.asset(
              'assets/images/logo.png',
              height: 32,
              fit: BoxFit.contain,
              errorBuilder: (_, __, ___) => const Icon(Icons.shopping_bag, color: Colors.white, size: 28),
            ),
            const SizedBox(width: 8),
            Expanded(
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(
                    _shopName,
                    overflow: TextOverflow.ellipsis,
                    style: const TextStyle(fontSize: 15, fontWeight: FontWeight.bold, color: Colors.white),
                  ),
                  GestureDetector(
                    onTap: () {
                      showDialog(
                        context: context,
                        builder: (_) => const LocationSelectorDialog(),
                      );
                    },
                    child: Row(
                      children: [
                        const Icon(Icons.location_on, size: 12, color: Colors.yellowAccent),
                        const SizedBox(width: 2),
                        Text(
                          '${cartProv.selectedArea}, ${cartProv.selectedDistrict}',
                          style: const TextStyle(fontSize: 11, color: Colors.white70),
                        ),
                        const Icon(Icons.arrow_drop_down, size: 14, color: Colors.white70),
                      ],
                    ),
                  )
                ],
              ),
            ),
          ],
        ),
        actions: [
          // Language Switch Button
          IconButton(
            icon: Container(
              padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
              decoration: BoxDecoration(
                border: Border.all(color: Colors.white),
                borderRadius: BorderRadius.circular(8),
              ),
              child: Text(
                localeProv.locale.languageCode == 'bn' ? 'EN' : 'বাংলা',
                style: const TextStyle(fontSize: 11, fontWeight: FontWeight.bold, color: Colors.white),
              ),
            ),
            onPressed: () {
              localeProv.toggleLanguage();
            },
          ),

          // Cart Icon Button (Right beside My Orders)
          Stack(
            alignment: Alignment.center,
            children: [
              IconButton(
                icon: const Icon(Icons.shopping_cart, color: Colors.white),
                tooltip: 'Cart',
                onPressed: () {
                  Navigator.push(
                    context,
                    MaterialPageRoute(builder: (_) => const CartScreen()),
                  );
                },
              ),
              if (cartProv.totalItemCount > 0)
                Positioned(
                  right: 4,
                  top: 4,
                  child: Container(
                    padding: const EdgeInsets.all(3),
                    decoration: const BoxDecoration(
                      color: Colors.red,
                      shape: BoxShape.circle,
                    ),
                    constraints: const BoxConstraints(minWidth: 16, minHeight: 16),
                    child: Text(
                      '${cartProv.totalItemCount}',
                      style: const TextStyle(color: Colors.white, fontSize: 9, fontWeight: FontWeight.bold),
                      textAlign: TextAlign.center,
                    ),
                  ),
                ),
            ],
          ),

          // My Orders Button (Right beside Cart Icon)
          IconButton(
            icon: const Icon(Icons.receipt_long, color: Colors.white),
            tooltip: loc.translate('my_orders'),
            onPressed: () {
              Navigator.push(
                context,
                MaterialPageRoute(builder: (_) => const MyOrdersScreen()),
              );
            },
          ),

          // Top Right Profile Avatar (Real-time Synced with Profile Updates)
          GestureDetector(
            onTap: () async {
              await Navigator.push(
                context,
                MaterialPageRoute(builder: (_) => const ProfileScreen()),
              );
              _loadUserProfile();
            },
            child: Padding(
              padding: const EdgeInsets.only(right: 10.0, left: 2.0),
              child: CircleAvatar(
                radius: 16,
                backgroundColor: Colors.white24,
                backgroundImage: _getTopBarImageProvider(),
                child: _getTopBarImageProvider() == null
                    ? Text(_userAvatar, style: const TextStyle(fontSize: 15))
                    : null,
              ),
            ),
          ),
        ],
      ),
      body: Column(
        children: [
          // Section Tabs: Trending, Flash Sale, Offers (Dark Mode Adaptive Colors)
          Container(
            color: isDark ? Colors.grey[900] : Colors.white,
            padding: const EdgeInsets.symmetric(vertical: 8, horizontal: 12),
            child: SingleChildScrollView(
              scrollDirection: Axis.horizontal,
              child: Row(
                children: [
                  _buildTabChip(loc.translate('all_products'), 'all'),
                  const SizedBox(width: 8),
                  _buildTabChip(loc.translate('trending'), 'trending'),
                  const SizedBox(width: 8),
                  _buildTabChip(loc.translate('flash_sale'), 'flash_sale'),
                  const SizedBox(width: 8),
                  _buildTabChip(loc.translate('offers'), 'offers'),
                ],
              ),
            ),
          ),

          // Real-time Auto Stream Products Grid
          Expanded(
            child: StreamBuilder<List<Product>>(
              stream: ApiService.productsStream(),
              builder: (context, snapshot) {
                if (snapshot.connectionState == ConnectionState.waiting && !snapshot.hasData) {
                  return const Center(child: CircularProgressIndicator());
                }

                final allProducts = snapshot.data ?? [];
                final filteredProducts = _filterProducts(allProducts);

                if (filteredProducts.isEmpty) {
                  return const Center(child: Text("কোনো পণ্য পাওয়া যায়নি"));
                }

                return GridView.builder(
                  padding: const EdgeInsets.all(12),
                  gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                    crossAxisCount: 2,
                    childAspectRatio: 0.68,
                    crossAxisSpacing: 12,
                    mainAxisSpacing: 12,
                  ),
                  itemCount: filteredProducts.length,
                  itemBuilder: (context, index) {
                    final prod = filteredProducts[index];
                    final savedAmount = prod.mrp > prod.sellPrice ? prod.mrp - prod.sellPrice : 0.0;

                    return Card(
                      elevation: 2,
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                      child: InkWell(
                        onTap: () {
                          Navigator.push(
                            context,
                            MaterialPageRoute(
                              builder: (_) => ProductDetailScreen(product: prod),
                            ),
                          );
                        },
                        child: Padding(
                          padding: const EdgeInsets.all(8.0),
                          child: Column(
                            crossAxisAlignment: CrossAxisAlignment.start,
                            children: [
                              // Image & Offer Tag
                              Expanded(
                                child: Stack(
                                  children: [
                                    Center(
                                      child: prod.imageUrl.isNotEmpty
                                          ? Image.network(
                                              prod.imageList.isNotEmpty ? prod.imageList.first : prod.imageUrl,
                                              fit: BoxFit.cover,
                                              errorBuilder: (_, __, ___) => Container(
                                                color: isDark ? Colors.grey[800] : Colors.grey[200],
                                                child: const Icon(Icons.shopping_bag, size: 50, color: Colors.grey),
                                              ),
                                            )
                                          : Container(
                                              color: isDark ? Colors.grey[800] : Colors.grey[200],
                                              child: const Icon(Icons.shopping_bag, size: 50, color: Colors.grey),
                                            ),
                                    ),
                                    if (prod.isOffer || prod.offerTitle.isNotEmpty || savedAmount > 0)
                                      Positioned(
                                        top: 0,
                                        left: 0,
                                        child: Container(
                                          padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 2),
                                          decoration: BoxDecoration(
                                            color: prod.offerType == 'buy_x_get_y' ? Colors.purple : Colors.red,
                                            borderRadius: BorderRadius.circular(4),
                                          ),
                                          child: Text(
                                            prod.offerTitle.isNotEmpty
                                                ? prod.offerTitle
                                                : (prod.offerType == 'percentage'
                                                    ? '${prod.offerValue}% OFF'
                                                    : '৳${savedAmount.toStringAsFixed(0)} ${loc.translate('save')}'),
                                            style: const TextStyle(color: Colors.white, fontSize: 10, fontWeight: FontWeight.bold),
                                          ),
                                        ),
                                      ),
                                  ],
                                ),
                              ),
                              const SizedBox(height: 6),

                              // Product Name
                              Text(
                                prod.name,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 14),
                              ),

                              // Category Name
                              if (prod.categoryName.isNotEmpty)
                                Text(
                                  prod.categoryName,
                                  style: const TextStyle(fontSize: 11, color: Colors.grey),
                                ),

                              const SizedBox(height: 4),

                              // Price & Stock Row
                              Row(
                                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                children: [
                                  Row(
                                    children: [
                                      if (prod.effectivePrice < prod.sellPrice)
                                        Text(
                                          '৳${prod.sellPrice.toStringAsFixed(0)}',
                                          style: const TextStyle(
                                            fontSize: 11,
                                            color: Colors.grey,
                                            decoration: TextDecoration.lineThrough,
                                          ),
                                        )
                                      else if (prod.mrp > 0 && prod.mrp > prod.sellPrice)
                                        Text(
                                          '৳${prod.mrp.toStringAsFixed(0)}',
                                          style: const TextStyle(
                                            fontSize: 11,
                                            color: Colors.grey,
                                            decoration: TextDecoration.lineThrough,
                                          ),
                                        ),
                                      if (prod.effectivePrice < prod.sellPrice || (prod.mrp > 0 && prod.mrp > prod.sellPrice))
                                        const SizedBox(width: 4),
                                      Text(
                                        '৳${prod.effectivePrice.toStringAsFixed(0)}',
                                        style: const TextStyle(
                                          fontSize: 14,
                                          fontWeight: FontWeight.bold,
                                          color: Colors.green,
                                        ),
                                      ),
                                    ],
                                  ),

                                  // Current Stock Badge Beside Price
                                  Container(
                                    padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 2),
                                    decoration: BoxDecoration(
                                      color: prod.stockQty > 0
                                          ? (isDark ? Colors.green.shade900 : Colors.green.shade50)
                                          : (isDark ? Colors.red.shade900 : Colors.red.shade50),
                                      borderRadius: BorderRadius.circular(4),
                                      border: Border.all(
                                        color: prod.stockQty > 0
                                            ? (isDark ? Colors.green.shade700 : Colors.green.shade300)
                                            : (isDark ? Colors.red.shade700 : Colors.red.shade300),
                                      ),
                                    ),
                                    child: Text(
                                      prod.stockQty > 0 ? 'Stock: ${prod.stockQty}' : 'Out of Stock',
                                      style: TextStyle(
                                        fontSize: 9,
                                        fontWeight: FontWeight.bold,
                                        color: prod.stockQty > 0
                                            ? (isDark ? Colors.green.shade200 : Colors.green.shade800)
                                            : (isDark ? Colors.red.shade200 : Colors.red.shade800),
                                      ),
                                    ),
                                  ),
                                ],
                              ),

                              const SizedBox(height: 6),

                              // Add to Cart Button
                              SizedBox(
                                width: double.infinity,
                                height: 32,
                                child: ElevatedButton(
                                  onPressed: () {
                                    cartProv.addToCart(prod);
                                    ScaffoldMessenger.of(context).showSnackBar(
                                      SnackBar(
                                        content: Text('${prod.name} added to the cart'),
                                        duration: const Duration(seconds: 1),
                                      ),
                                    );
                                  },
                                  style: ElevatedButton.styleFrom(
                                    backgroundColor: Colors.green,
                                    padding: EdgeInsets.zero,
                                  ),
                                  child: Text(
                                    loc.translate('add_to_cart'),
                                    style: const TextStyle(fontSize: 12, fontWeight: FontWeight.bold, color: Colors.white),
                                  ),
                                ),
                              ),
                            ],
                          ),
                        ),
                      ),
                    );
                  },
                );
              },
            ),
          ),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () {
          Navigator.push(
            context,
            MaterialPageRoute(builder: (_) => const CartScreen()),
          );
        },
        backgroundColor: Colors.orange,
        icon: const Icon(Icons.shopping_cart),
        label: Text(
          '${cartProv.totalItemCount} | ৳${cartProv.subtotal.toStringAsFixed(0)}',
          style: const TextStyle(fontWeight: FontWeight.bold),
        ),
      ),
    );
  }

  Widget _buildTabChip(String label, String key) {
    bool isSelected = _selectedTab == key;
    bool isDark = Theme.of(context).brightness == Brightness.dark;

    return ChoiceChip(
      label: Text(label),
      selected: isSelected,
      selectedColor: Colors.green,
      backgroundColor: isDark ? Colors.grey.shade800 : Colors.grey.shade200,
      labelStyle: TextStyle(
        color: isSelected
            ? Colors.white
            : (isDark ? Colors.white : Colors.black87),
        fontWeight: FontWeight.bold,
      ),
      onSelected: (selected) {
        if (selected) {
          setState(() {
            _selectedTab = key;
          });
        }
      },
    );
  }
}
