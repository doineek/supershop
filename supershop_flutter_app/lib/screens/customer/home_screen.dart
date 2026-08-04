import 'dart:async';
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
  int _bottomNavIndex = 0;
  String _searchQuery = "";

  final PageController _bannerController = PageController();
  Timer? _bannerTimer;
  int _bannerIndex = 0;

  final List<Map<String, String>> _promotions = [
    {"title": "🔥 20% OFF Flash Sale!", "subtitle": "দৈনন্দিন মুদি বাজার সেরা মূল্যে!", "color": "0xFFE65100"},
    {"title": "🚀 Superfast 30-Min Delivery", "subtitle": "আপনার এলাকার নিকটস্থ রাইডার প্রস্তুত!", "color": "0xFF1B5E20"},
    {"title": "🎁 Buy 1 Get 1 Free Offers", "subtitle": "আজকের সেরা ডিল মিস করবেন না!", "color": "0xFF4A148C"},
    {"title": "💳 Cash On Delivery Guaranteed", "subtitle": "পণ্য হাতে পেয়ে নিশ্চিন্তে পেমেন্ট করুন!", "color": "0xFF006064"},
  ];

  @override
  void initState() {
    super.initState();
    _loadShopName();
    _loadUserProfile();
    _startBannerTimer();
  }

  void _startBannerTimer() {
    _bannerTimer = Timer.periodic(const Duration(seconds: 2), (timer) {
      if (_bannerController.hasClients) {
        _bannerIndex = (_bannerIndex + 1) % _promotions.length;
        _bannerController.animateToPage(
          _bannerIndex,
          duration: const Duration(milliseconds: 500),
          curve: Curves.easeInOut,
        );
      }
    });
  }

  @override
  void dispose() {
    _bannerTimer?.cancel();
    _bannerController.dispose();
    super.dispose();
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
    List<Product> list = allProducts;
    if (_searchQuery.trim().isNotEmpty) {
      String q = _searchQuery.trim().toLowerCase();
      list = list.where((p) => p.name.toLowerCase().contains(q) || p.categoryName.toLowerCase().contains(q)).toList();
    }
    if (_selectedTab == 'trending') {
      return list.where((p) => p.isTrending).toList();
    } else if (_selectedTab == 'flash_sale') {
      return list.where((p) => p.isFlashSale).toList();
    } else if (_selectedTab == 'offers') {
      return list.where((p) => p.isOffer).toList();
    }
    return list;
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
          // Persistent Top Search Bar
          Container(
            color: Colors.green,
            padding: const EdgeInsets.fromLTRB(12, 0, 12, 10),
            child: Container(
              height: 42,
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(24),
                boxShadow: const [BoxShadow(color: Colors.black12, blurRadius: 4)],
              ),
              child: TextField(
                onChanged: (val) => setState(() => _searchQuery = val),
                decoration: const InputDecoration(
                  hintText: "পণ্য বা ক্যাটাগরির নাম দিয়ে খুঁজুন...",
                  hintStyle: TextStyle(fontSize: 13, color: Colors.grey),
                  prefixIcon: Icon(Icons.search, color: Colors.green),
                  border: InputBorder.none,
                  contentPadding: EdgeInsets.symmetric(vertical: 10),
                ),
              ),
            ),
          ),

          // Top 1/4 Screen Promotion Banner Carousel (Auto-slide every 2 seconds)
          SizedBox(
            height: MediaQuery.of(context).size.height * 0.22,
            child: PageView.builder(
              controller: _bannerController,
              itemCount: _promotions.length,
              itemBuilder: (context, index) {
                final promo = _promotions[index];
                final colorVal = int.parse(promo["color"]!);
                return Container(
                  margin: const EdgeInsets.all(8),
                  padding: const EdgeInsets.all(16),
                  decoration: BoxDecoration(
                    gradient: LinearGradient(
                      colors: [Color(colorVal), Color(colorVal).withValues(alpha: 0.75)],
                      begin: Alignment.topLeft,
                      end: Alignment.bottomRight,
                    ),
                    borderRadius: BorderRadius.circular(16),
                    boxShadow: const [BoxShadow(color: Colors.black26, blurRadius: 6, offset: Offset(0, 3))],
                  ),
                  child: Row(
                    children: [
                      Expanded(
                        child: Column(
                          mainAxisAlignment: MainAxisAlignment.center,
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Text(
                              promo["title"]!,
                              style: const TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.bold),
                            ),
                            const SizedBox(height: 6),
                            Text(
                              promo["subtitle"]!,
                              style: const TextStyle(color: Colors.white70, fontSize: 12),
                            ),
                          ],
                        ),
                      ),
                      const Icon(Icons.shopping_basket, size: 56, color: Colors.white38),
                    ],
                  ),
                );
              },
            ),
          ),

          // Section Tabs: Trending, Flash Sale, Offers
          Container(
            color: isDark ? Colors.grey[900] : Colors.white,
            padding: const EdgeInsets.symmetric(vertical: 6, horizontal: 12),
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

          // Real-time Products Grid (Max 20 Products Limit)
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

                // Show max 20 products on front page as requested
                final displayProducts = filteredProducts.take(20).toList();

                return CustomScrollView(
                  slivers: [
                    SliverPadding(
                      padding: const EdgeInsets.all(10),
                      sliver: SliverGrid(
                        gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                          crossAxisCount: 2,
                          childAspectRatio: 0.58,
                          crossAxisSpacing: 10,
                          mainAxisSpacing: 10,
                        ),
                        delegate: SliverChildBuilderDelegate(
                          (context, index) {
                            final prod = displayProducts[index];
                            final savedAmount = prod.mrp > prod.sellPrice ? prod.mrp - prod.sellPrice : 0.0;

                            return Card(
                              elevation: 2,
                              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                              child: InkWell(
                                onTap: () {
                                  Navigator.push(
                                    context,
                                    MaterialPageRoute(builder: (_) => ProductDetailScreen(product: prod)),
                                  );
                                },
                                child: Padding(
                                  padding: const EdgeInsets.all(8.0),
                                  child: Column(
                                    crossAxisAlignment: CrossAxisAlignment.start,
                                    children: [
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
                                                        child: const Icon(Icons.shopping_bag, size: 40, color: Colors.grey),
                                                      ),
                                                    )
                                                  : Container(
                                                      color: isDark ? Colors.grey[800] : Colors.grey[200],
                                                      child: const Icon(Icons.shopping_bag, size: 40, color: Colors.grey),
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
                                                    style: const TextStyle(color: Colors.white, fontSize: 9, fontWeight: FontWeight.bold),
                                                  ),
                                                ),
                                              ),
                                          ],
                                        ),
                                      ),
                                      const SizedBox(height: 4),

                                      Text(
                                        prod.name,
                                        maxLines: 1,
                                        overflow: TextOverflow.ellipsis,
                                        style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13),
                                      ),

                                      if (prod.categoryName.isNotEmpty)
                                        Text(
                                          prod.categoryName,
                                          style: const TextStyle(fontSize: 10, color: Colors.grey),
                                        ),

                                      const SizedBox(height: 4),

                                      Row(
                                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                        children: [
                                          Text(
                                            '৳${prod.effectivePrice.toStringAsFixed(0)}',
                                            style: const TextStyle(fontSize: 13, fontWeight: FontWeight.bold, color: Colors.green),
                                          ),
                                          Container(
                                            padding: const EdgeInsets.symmetric(horizontal: 4, vertical: 2),
                                            decoration: BoxDecoration(
                                              color: prod.stockQty > 0 ? Colors.green.shade50 : Colors.red.shade50,
                                              borderRadius: BorderRadius.circular(4),
                                            ),
                                            child: Text(
                                              prod.stockQty > 0 ? 'Stock: ${prod.stockQty}' : 'Out',
                                              style: TextStyle(
                                                fontSize: 8,
                                                fontWeight: FontWeight.bold,
                                                color: prod.stockQty > 0 ? Colors.green.shade800 : Colors.red.shade800,
                                              ),
                                            ),
                                          ),
                                        ],
                                      ),

                                      const SizedBox(height: 6),

                                      // Add to Cart & Buy Now Buttons Row
                                      Row(
                                        children: [
                                          Expanded(
                                            child: SizedBox(
                                              height: 30,
                                              child: ElevatedButton(
                                                onPressed: () {
                                                  cartProv.addToCart(prod);
                                                  ScaffoldMessenger.of(context).showSnackBar(
                                                    SnackBar(
                                                      content: Text('${prod.name} added to cart'),
                                                      duration: const Duration(seconds: 1),
                                                    ),
                                                  );
                                                },
                                                style: ElevatedButton.styleFrom(
                                                  backgroundColor: Colors.green,
                                                  padding: EdgeInsets.zero,
                                                ),
                                                child: const Text(
                                                  "Cart",
                                                  style: TextStyle(fontSize: 11, fontWeight: FontWeight.bold, color: Colors.white),
                                                ),
                                              ),
                                            ),
                                          ),
                                          const SizedBox(width: 4),
                                          Expanded(
                                            child: SizedBox(
                                              height: 30,
                                              child: ElevatedButton(
                                                onPressed: () {
                                                  cartProv.addToCart(prod);
                                                  Navigator.push(
                                                    context,
                                                    MaterialPageRoute(builder: (_) => const CartScreen()),
                                                  );
                                                },
                                                style: ElevatedButton.styleFrom(
                                                  backgroundColor: Colors.deepOrange,
                                                  padding: EdgeInsets.zero,
                                                ),
                                                child: const Text(
                                                  "Buy Now",
                                                  style: TextStyle(fontSize: 11, fontWeight: FontWeight.bold, color: Colors.white),
                                                ),
                                              ),
                                            ),
                                          ),
                                        ],
                                      ),
                                    ],
                                  ),
                                ),
                              ),
                            );
                          },
                          childCount: displayProducts.length,
                        ),
                      ),
                    ),

                    // CartUp.com Style Footer Section with Policy Links
                    SliverToBoxAdapter(
                      child: Container(
                        color: isDark ? Colors.grey.shade900 : Colors.grey.shade100,
                        padding: const EdgeInsets.all(16),
                        child: Column(
                          children: [
                            const Divider(),
                            Text(_shopName, style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
                            const SizedBox(height: 4),
                            const Text("Your Trusted Online Shopping Destination", style: TextStyle(fontSize: 12, color: Colors.grey)),
                            const SizedBox(height: 12),
                            Wrap(
                              alignment: WrapAlignment.center,
                              spacing: 12,
                              runSpacing: 8,
                              children: [
                                _buildPolicyLink("About Us", "about_us"),
                                _buildPolicyLink("Blog", "blog"),
                                _buildPolicyLink("Cookies Policy", "cookies_policy"),
                                _buildPolicyLink("Return Policy", "return_refund_policy"),
                                _buildPolicyLink("Privacy Policy", "privacy_policy"),
                                _buildPolicyLink("Terms & Conditions", "terms_conditions"),
                                _buildPolicyLink("Warranty Policy", "warranty_policy"),
                                _buildPolicyLink("Help Center", "help_center"),
                              ],
                            ),
                            const SizedBox(height: 16),
                            const Text("© 2026 DOINEEK Supershop. All Rights Reserved.", style: TextStyle(fontSize: 11, color: Colors.grey)),
                          ],
                        ),
                      ),
                    ),
                  ],
                );
              },
            ),
          ),
        ],
      ),

      // 4-Tab Bottom Navigation Bar (Home, Category, Cart, Profile)
      bottomNavigationBar: BottomNavigationBar(
        currentIndex: _bottomNavIndex,
        selectedItemColor: Colors.green,
        unselectedItemColor: Colors.grey,
        type: BottomNavigationBarType.fixed,
        onTap: (index) {
          setState(() {
            _bottomNavIndex = index;
          });
          if (index == 1) {
            // Category tab
            setState(() {
              _selectedTab = 'all';
            });
          } else if (index == 2) {
            // Cart tab
            Navigator.push(context, MaterialPageRoute(builder: (_) => const CartScreen()));
          } else if (index == 3) {
            // Profile tab
            Navigator.push(context, MaterialPageRoute(builder: (_) => const ProfileScreen()));
          }
        },
        items: [
          const BottomNavigationBarItem(icon: Icon(Icons.home), label: "Home"),
          const BottomNavigationBarItem(icon: Icon(Icons.category), label: "Category"),
          BottomNavigationBarItem(
            icon: Badge(
              label: Text('${cartProv.totalItemCount}'),
              isLabelVisible: cartProv.totalItemCount > 0,
              child: const Icon(Icons.shopping_cart),
            ),
            label: "Cart",
          ),
          const BottomNavigationBarItem(icon: Icon(Icons.person), label: "Profile"),
        ],
      ),
    );
  }

  Widget _buildPolicyLink(String title, String key) {
    return InkWell(
      onTap: () async {
        showDialog(
          context: context,
          builder: (_) => const Center(child: CircularProgressIndicator()),
        );
        var policies = await ApiService.fetchStorePolicies();
        if (!mounted) return;
        Navigator.pop(context); // Close loading dialog

        String content = policies[key] ?? "Information will be updated soon.";
        showDialog(
          context: context,
          builder: (dialogCtx) => AlertDialog(
            title: Text(title, style: const TextStyle(fontWeight: FontWeight.bold, color: Colors.green)),
            content: SingleChildScrollView(
              child: Text(content, style: const TextStyle(fontSize: 14, height: 1.4)),
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(dialogCtx),
                child: const Text("বন্ধ করুন"),
              ),
            ],
          ),
        );
      },
      child: Text(
        title,
        style: const TextStyle(fontSize: 12, color: Colors.green, fontWeight: FontWeight.bold, decoration: TextDecoration.underline),
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
