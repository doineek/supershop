import 'dart:async';
import 'dart:convert';
import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:url_launcher/url_launcher.dart';
import '../../localization/app_localizations.dart';
import '../../models/product.dart';
import '../../providers/cart_provider.dart';
import '../../providers/locale_provider.dart';
import '../../services/api_service.dart';

import 'cart_screen.dart';
import '../../widgets/app_image_loader.dart';
import '../../widgets/location_selector_dialog.dart';
import '../../widgets/quantity_limit_dialog.dart';
import 'product_detail_screen.dart';
import 'profile_screen.dart';
import '../delivery/delivery_home_screen.dart';
import '../admin/admin_hub_screen.dart';
import '../auth/login_screen.dart';

class HomeScreen extends StatefulWidget {
  const HomeScreen({Key? key}) : super(key: key);

  @override
  State<HomeScreen> createState() => _HomeScreenState();
}

class _HomeScreenState extends State<HomeScreen> with WidgetsBindingObserver {
  String _selectedTab = 'all'; // all, trending, flash_sale, offers
  String _shopName = "DOINEEK Supershop";
  String _userAvatar = "👤";
  String _userImageBase64 = "";
  int _bottomNavIndex = 0;
  String _searchQuery = "";
  String _sortBy = "default";
  List<dynamic> _categoriesTree = [];
  bool _isLoadingCategories = false;
  List<Product> _allProducts = [];
  bool _isLoadingProducts = false;
  Timer? _retryTimer;
  int _retryCount = 0;

  final PageController _bannerController = PageController();
  Timer? _bannerTimer;
  int _bannerIndex = 0;
  int _promoIntervalSec = 2;
  List<dynamic> _promoList = [];

  final List<Map<String, String>> _promotions = [
    {"title": "🔥 20% OFF Flash Sale!", "subtitle": "Daily groceries at best prices!", "color": "0xFFE65100"},
    {"title": "🚀 Superfast 30-Min Delivery", "subtitle": "Nearest rider ready in your area!", "color": "0xFF1B5E20"},
    {"title": "🎁 Buy 1 Get 1 Free Offers", "subtitle": "Don't miss today's best deals!", "color": "0xFF4A148C"},
    {"title": "💳 Cash On Delivery Guaranteed", "subtitle": "Pay safely upon receiving products!", "color": "0xFF006064"},
  ];

  List<dynamic> _packagesList = [];
  bool _isAdminMode = false;

  @override
  void initState() {
    super.initState();
    WidgetsBinding.instance.addObserver(this);
    _loadCachedDataInstantly();
    _loadUserProfile();
    _loadAllData(retryIfEmpty: true);
  }

  @override
  void didChangeAppLifecycleState(AppLifecycleState state) {
    if (state == AppLifecycleState.resumed) {
      // Automatically refresh data when app returns from background
      _loadAllData(retryIfEmpty: true);
    }
  }

  void _loadCachedDataInstantly() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      
      // Load cached promotions
      final cachedPromo = prefs.getString('cached_promotions');
      if (cachedPromo != null && cachedPromo.isNotEmpty) {
        try {
          final data = jsonDecode(cachedPromo);
          final list = data['promotions'] as List<dynamic>? ?? [];
          final interval = data['interval_sec'] ?? 2;
          if (list.isNotEmpty && mounted) {
            setState(() {
              _promoList = list;
              _promoIntervalSec = interval > 0 ? interval : 2;
            });
            _startBannerTimer();
          }
        } catch (_) {}
      }

      // Load cached categories tree
      final cachedCats = prefs.getString('cached_categories_tree');
      if (cachedCats != null && cachedCats.isNotEmpty) {
        try {
          final list = jsonDecode(cachedCats) as List<dynamic>? ?? [];
          if (list.isNotEmpty && mounted) {
            setState(() {
              _categoriesTree = list;
            });
          }
        } catch (_) {}
      }

      // Load cached packages
      final cachedPkgs = prefs.getString('cached_packages');
      if (cachedPkgs != null && cachedPkgs.isNotEmpty) {
        try {
          final list = jsonDecode(cachedPkgs) as List<dynamic>? ?? [];
          if (list.isNotEmpty && mounted) {
            setState(() {
              _packagesList = list;
            });
          }
        } catch (_) {}
      }

      // Load cached settings
      final cachedSettings = prefs.getString('cached_shop_settings');
      if (cachedSettings != null && cachedSettings.isNotEmpty) {
        try {
          final map = jsonDecode(cachedSettings) as Map<String, dynamic>? ?? {};
          if (mounted) {
            setState(() {
              _shopName = map['shop_name'] ?? "DOINEEK Supershop";
              _facebookUrl = (map['facebook_url'] ?? '').toString();
              _youtubeUrl = (map['youtube_url'] ?? '').toString();
              _xUrl = (map['x_url'] ?? '').toString();
              _instagramUrl = (map['instagram_url'] ?? '').toString();
            });
          }
        } catch (_) {}
      }

      // Load cached products
      final cachedProds = prefs.getString('cached_products_json');
      if (cachedProds != null && cachedProds.isNotEmpty) {
        try {
          final list = jsonDecode(cachedProds) as List<dynamic>? ?? [];
          if (list.isNotEmpty && mounted) {
            setState(() {
              _allProducts = list.map((e) => Product.fromJson(Map<String, dynamic>.from(e))).toList();
            });
          }
        } catch (_) {}
      }
    } catch (_) {}
  }

  Future<void> _loadAllData({bool retryIfEmpty = true}) async {
    if (!mounted) return;
    setState(() {
      if (_categoriesTree.isEmpty) _isLoadingCategories = true;
      if (_allProducts.isEmpty) _isLoadingProducts = true;
    });

    try {
      // 1. Fetch Promotions
      final promoData = await ApiService.fetchPromotions();
      int interval = promoData['interval_sec'] ?? 2;
      List promoList = promoData['promotions'] ?? [];

      // 2. Fetch Category Tree
      final catTree = await ApiService.fetchCategoriesTree();

      // 3. Fetch Packages
      final pkgs = await ApiService.getPackages();

      // 4. Fetch Shop Settings
      final settings = await ApiService.fetchShopSettings();

      // 5. Fetch Products
      final prods = await ApiService.fetchProducts();

      if (!mounted) return;
      setState(() {
        _isLoadingCategories = false;
        _isLoadingProducts = false;
        if (promoList.isNotEmpty) {
          _promoList = promoList;
          _promoIntervalSec = interval > 0 ? interval : 2;
          _startBannerTimer();
        }
        if (catTree.isNotEmpty) {
          _categoriesTree = catTree;
        }
        if (pkgs.isNotEmpty) {
          _packagesList = pkgs;
        }
        if (prods.isNotEmpty) {
          _allProducts = prods;
        }
        if (settings.isNotEmpty) {
          _shopName = settings['shop_name'] ?? "DOINEEK Supershop";
          _facebookUrl = (settings['facebook_url'] ?? '').toString();
          _youtubeUrl = (settings['youtube_url'] ?? '').toString();
          _xUrl = (settings['x_url'] ?? '').toString();
          _instagramUrl = (settings['instagram_url'] ?? '').toString();
        }
      });

      if (prods.isNotEmpty) {
        try {
          final prefs = await SharedPreferences.getInstance();
          prefs.setString('cached_products_json', jsonEncode(prods.map((p) => p.toJson()).toList()));
        } catch (_) {}
      }

      // If data is still missing (e.g. server was sleeping during cold start), auto-retry in background
      bool hasMissingData = _promoList.isEmpty || _categoriesTree.isEmpty;
      if (hasMissingData && retryIfEmpty && _retryCount < 5) {
        _retryCount++;
        _retryTimer?.cancel();
        _retryTimer = Timer(Duration(seconds: 3 * _retryCount), () {
          if (mounted) {
            _loadAllData(retryIfEmpty: true);
          }
        });
      } else if (!hasMissingData) {
        _retryCount = 0;
      }
    } catch (e) {
      if (mounted) {
        setState(() {
          _isLoadingCategories = false;
        });
        if (retryIfEmpty && _retryCount < 5) {
          _retryCount++;
          _retryTimer?.cancel();
          _retryTimer = Timer(Duration(seconds: 3 * _retryCount), () {
            if (mounted) _loadAllData(retryIfEmpty: true);
          });
        }
      }
    }
  }

  void _startBannerTimer() {
    _bannerTimer?.cancel();
    int count = _promoList.isNotEmpty ? _promoList.length : _promotions.length;
    _bannerTimer = Timer.periodic(Duration(seconds: _promoIntervalSec), (timer) {
      if (_bannerController.hasClients && count > 0) {
        _bannerIndex = (_bannerIndex + 1) % count;
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
    WidgetsBinding.instance.removeObserver(this);
    _retryTimer?.cancel();
    _bannerTimer?.cancel();
    _bannerController.dispose();
    super.dispose();
  }

  String _facebookUrl = "";
  String _youtubeUrl = "";
  String _xUrl = "";
  String _instagramUrl = "";

  void _loadShopName() async {
    var settings = await ApiService.fetchShopSettings();
    if (!mounted) return;
    setState(() {
      _shopName = settings['shop_name'] ?? "DOINEEK Supershop";
      _facebookUrl = (settings['facebook_url'] ?? '').toString();
      _youtubeUrl = (settings['youtube_url'] ?? '').toString();
      _xUrl = (settings['x_url'] ?? '').toString();
      _instagramUrl = (settings['instagram_url'] ?? '').toString();
    });
  }

  void _loadUserProfile() async {
    final prefs = await SharedPreferences.getInstance();
    bool staySignedIn = prefs.getBool('stay_signed_in') ?? true;
    String userPhone = prefs.getString('user_phone') ?? '';
    bool isDelivery = prefs.getBool('is_delivery_man') ?? false;

    if (staySignedIn && userPhone.isNotEmpty && isDelivery) {
      if (!mounted) return;
      Navigator.pushReplacement(
        context,
        MaterialPageRoute(builder: (_) => const DeliveryHomeScreen()),
      );
      return;
    }

    String phoneImg = userPhone.isNotEmpty ? (prefs.getString('saved_img_$userPhone') ?? '') : '';
    String phoneAv = userPhone.isNotEmpty ? (prefs.getString('saved_av_$userPhone') ?? '') : '';

    if (!mounted) return;
    setState(() {
      _isAdminMode = prefs.getBool('is_admin_mode') ?? false;
      _userAvatar = prefs.getString('user_avatar') ?? (phoneAv.isNotEmpty ? phoneAv : '👤');
      _userImageBase64 = prefs.getString('user_image_base64') ?? phoneImg;
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

  Widget _buildProfileTabIcon() {
    if (_userImageBase64.isNotEmpty) {
      try {
        String cleanB64 = _userImageBase64.contains(',') ? _userImageBase64.split(',').last : _userImageBase64;
        return CircleAvatar(
          radius: 12,
          backgroundImage: MemoryImage(base64Decode(cleanB64)),
        );
      } catch (_) {}
    }
    if (_userAvatar.isNotEmpty && _userAvatar != '👤') {
      return Text(_userAvatar, style: const TextStyle(fontSize: 16));
    }
    return const Icon(Icons.person);
  }

  Future<void> _launchSocialUrl(String rawUrl, String name) async {
    String cleanUrl = rawUrl.trim();
    if (cleanUrl.isEmpty) {
      if (name.toLowerCase().contains("facebook")) {
        cleanUrl = "https://www.facebook.com/doineek";
      } else if (name.toLowerCase().contains("youtube")) {
        cleanUrl = "https://www.youtube.com";
      } else if (name.toLowerCase().contains("instagram")) {
        cleanUrl = "https://www.instagram.com";
      } else if (name.toLowerCase().contains("x") || name.toLowerCase().contains("twitter")) {
        cleanUrl = "https://x.com";
      } else {
        cleanUrl = "https://www.facebook.com";
      }
    }

    if (!cleanUrl.startsWith("http://") && !cleanUrl.startsWith("https://")) {
      cleanUrl = "https://$cleanUrl";
    }

    try {
      final Uri uri = Uri.parse(cleanUrl);
      // Launch external application (will automatically open the native app like Facebook/YouTube if installed, otherwise browser)
      final bool launched = await launchUrl(uri, mode: LaunchMode.externalApplication);
      if (!launched) {
        await launchUrl(uri, mode: LaunchMode.platformDefault);
      }
    } catch (e) {
      try {
        final Uri uri = Uri.parse(cleanUrl);
        await launchUrl(uri, mode: LaunchMode.platformDefault);
      } catch (err) {
        if (mounted) {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text("Could not open $name: $cleanUrl")),
          );
        }
      }
    }
  }

  Widget _buildSocialIcon(IconData icon, Color color, String url, String name) {
    return InkWell(
      onTap: () => _launchSocialUrl(url, name),
      child: Container(
        padding: const EdgeInsets.all(6),
        decoration: BoxDecoration(
          color: color.withOpacity(0.12),
          shape: BoxShape.circle,
        ),
        child: Icon(icon, color: color, size: 20),
      ),
    );
  }

  List<Product> _filterProducts(List<Product> allProducts) {
    List<Product> list = allProducts;
    if (_searchQuery.trim().isNotEmpty) {
      String q = _searchQuery.trim().toLowerCase();
      if (q == 'uncategorized') {
        list = list.where((p) => p.categoryId == null || p.categoryId == 0 || p.categoryName.trim().isEmpty || p.categoryName.trim().toLowerCase() == 'uncategorized').toList();
      } else {
        list = list.where((p) =>
          p.name.toLowerCase().contains(q) ||
          p.categoryName.toLowerCase().contains(q) ||
          p.subCategoryName.toLowerCase().contains(q) ||
          p.subSubCategoryName.toLowerCase().contains(q)
        ).toList();
      }
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
        backgroundColor: const Color(0xFF6B21A8),
        toolbarHeight: 70,
        title: Row(
          children: [
            // Website Brand Logo Image with Crisp White Background Badge (Tightly Cropped & Prominent)
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 6, vertical: 4),
              decoration: BoxDecoration(
                color: Colors.white,
                borderRadius: BorderRadius.circular(10),
                boxShadow: const [
                  BoxShadow(color: Colors.black26, blurRadius: 4, offset: Offset(0, 2)),
                ],
              ),
              child: Image.asset(
                'assets/images/logo.png',
                height: 44,
                fit: BoxFit.contain,
                errorBuilder: (_, __, ___) => const Icon(Icons.shopping_bag, color: Color(0xFF6B21A8), size: 32),
              ),
            ),
            const SizedBox(width: 10),
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
                    onTap: () async {
                      final prefs = await SharedPreferences.getInstance();
                      String phone = prefs.getString('user_phone') ?? '';
                      if (phone.isEmpty) {
                        if (!mounted) return;
                        ScaffoldMessenger.of(context).showSnackBar(
                          const SnackBar(
                            content: Text("Please log in first to change delivery location."),
                            duration: Duration(seconds: 2),
                          ),
                        );
                        Navigator.push(
                          context,
                          MaterialPageRoute(builder: (_) => LoginScreen()),
                        );
                      } else {
                        showDialog(
                          context: context,
                          builder: (_) => const LocationSelectorDialog(),
                        );
                      }
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
        actions: const [],
      ),
      body: Builder(
        builder: (context) {
          final allProducts = _allProducts;
          final filteredProducts = _filterProducts(allProducts);

          List<Product> sortedProducts = List.from(filteredProducts);
          if (_sortBy == 'price_low') {
            sortedProducts.sort((a, b) => a.effectivePrice.compareTo(b.effectivePrice));
          } else if (_sortBy == 'price_high') {
            sortedProducts.sort((a, b) => b.effectivePrice.compareTo(a.effectivePrice));
          } else if (_sortBy == 'newest') {
            sortedProducts.sort((a, b) => b.id.compareTo(a.id));
          }
          final displayProducts = sortedProducts.take(20).toList();

          return Stack(
            children: [
              IndexedStack(
                index: _bottomNavIndex,
                children: [
                  Column(
                    children: [
                      if (_isAdminMode)
                        Container(
                          color: const Color(0xFF0F172A),
                          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 7),
                          child: Row(
                            children: [
                              const Icon(Icons.shield, color: Colors.amber, size: 16),
                              const SizedBox(width: 8),
                              const Expanded(
                                child: Text(
                                  "Admin Mode Active (Customer View)",
                                  style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 11.5),
                                ),
                              ),
                              InkWell(
                                onTap: () {
                                  Navigator.pushReplacement(
                                    context,
                                    MaterialPageRoute(builder: (_) => const AdminHubScreen()),
                                  );
                                },
                                child: Container(
                                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                                  decoration: BoxDecoration(
                                    color: Colors.amber.shade700,
                                    borderRadius: BorderRadius.circular(6),
                                  ),
                                  child: const Row(
                                    children: [
                                      Icon(Icons.dashboard, size: 12, color: Colors.white),
                                      SizedBox(width: 4),
                                      Text("Admin Hub ➔", style: TextStyle(color: Colors.white, fontSize: 11, fontWeight: FontWeight.bold)),
                                    ],
                                  ),
                                ),
                              ),
                            ],
                          ),
                        ),
                      // Persistent Top Search Bar
                      Container(
                        color: const Color(0xFF6B21A8),
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
                              decoration: InputDecoration(
                                hintText: "Search products or categories...",
                                hintStyle: const TextStyle(fontSize: 13, color: Colors.grey),
                                prefixIcon: const Icon(Icons.search, color: Color(0xFF6B21A8)),
                                suffixIcon: _searchQuery.isNotEmpty
                                    ? IconButton(
                                        icon: const Icon(Icons.clear, size: 18),
                                        onPressed: () => setState(() => _searchQuery = ""),
                                      )
                                    : null,
                                border: InputBorder.none,
                                contentPadding: const EdgeInsets.symmetric(vertical: 10),
                              ),
                            ),
                          ),
                        ),

                        // Top 1/4 Screen Promotion Banner Carousel (50-50 Split: Left Image, Right Big Offer)
                        SizedBox(
                          height: 165,
                          child: PageView.builder(
                            controller: _bannerController,
                            itemCount: _promoList.isNotEmpty ? _promoList.length : _promotions.length,
                            itemBuilder: (context, index) {
                              if (_promoList.isNotEmpty) {
                                final item = _promoList[index];
                                String name = item["name"] ?? "Special Offer";
                                String offerTitle = item["offer_title"] != null && item["offer_title"].toString().trim().isNotEmpty
                                    ? item["offer_title"].toString().trim()
                                    : (item["offer_type"] == "bogo"
                                        ? (item["offer_value"] != null && item["offer_value"].toString().trim().isNotEmpty
                                            ? item["offer_value"].toString().trim()
                                            : "BUY 1 GET 1 FREE")
                                        : (item["is_package"] == 1 || item["is_package"]?.toString() == "1" || item["offer_type"] == "combo_package"
                                            ? "🎁 COMBO SPECIAL OFFER"
                                            : "🔥 SPECIAL OFFER"));
                                String rawImg = (item["image_url"] ?? "").toString().trim();
                                if (rawImg.isEmpty && item["images"] != null) {
                                  rawImg = item["images"].toString().trim();
                                }
                                String imgUrl = AppImageLoader.cleanUrl(rawImg);

                                double mrp = double.tryParse(item["mrp"]?.toString() ?? "0") ?? 0.0;
                                double sellPrice = double.tryParse(item["sell_price"]?.toString() ?? "0") ?? 0.0;
                                bool isCombo = item["is_package"] == 1 || item["is_package"]?.toString() == "1" || item["offer_type"] == "combo_package";

                                return InkWell(
                                  onTap: () {
                                    if (item["id"] == -999 || item["offer_type"] == "free_delivery") {
                                      ScaffoldMessenger.of(context).showSnackBar(
                                        SnackBar(
                                          content: Text("🚚 ${item['name'] ?? 'Free Delivery'} - ${item['description'] ?? 'Add items to cart to claim!'}"),
                                          backgroundColor: Colors.teal.shade800,
                                          duration: const Duration(seconds: 3),
                                        ),
                                      );
                                      return;
                                    }
                                    if (isCombo) {
                                      setState(() {
                                        _selectedTab = 'packages';
                                      });
                                      ScaffoldMessenger.of(context).showSnackBar(
                                        SnackBar(
                                          content: Text("${item['name'] ?? 'Combo Package'} - Showing Combo Deals!"),
                                          backgroundColor: Colors.purple.shade700,
                                          duration: const Duration(seconds: 2),
                                        ),
                                      );
                                      return;
                                    }
                                    try {
                                      final prod = Product.fromJson(Map<String, dynamic>.from(item));
                                      Navigator.push(
                                        context,
                                        MaterialPageRoute(builder: (_) => ProductDetailScreen(product: prod)),
                                      );
                                    } catch (_) {}
                                  },
                                  child: Container(
                                    margin: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
                                    padding: const EdgeInsets.all(10),
                                    decoration: BoxDecoration(
                                      gradient: LinearGradient(
                                        colors: isCombo
                                            ? [Colors.purple.shade800, Colors.deepPurple.shade900]
                                            : [Colors.green.shade800, Colors.teal.shade900],
                                        begin: Alignment.topLeft,
                                        end: Alignment.bottomRight,
                                      ),
                                      borderRadius: BorderRadius.circular(16),
                                      boxShadow: const [BoxShadow(color: Colors.black26, blurRadius: 6, offset: Offset(0, 3))],
                                    ),
                                    child: Row(
                                      children: [
                                        // Left Half (50%): Product Image Card
                                        Expanded(
                                          flex: 1,
                                          child: Container(
                                            decoration: BoxDecoration(
                                              color: Colors.white,
                                              borderRadius: BorderRadius.circular(12),
                                            ),
                                            padding: const EdgeInsets.all(6),
                                            child: ClipRRect(
                                              borderRadius: BorderRadius.circular(8),
                                              child: AppImageLoader(
                                                imageUrl: imgUrl,
                                                fit: BoxFit.contain,
                                              ),
                                            ),
                                          ),
                                        ),
                                        const SizedBox(width: 12),
                                        // Right Half (50%): Large Offer Text & Details
                                        Expanded(
                                          flex: 1,
                                          child: Column(
                                            mainAxisAlignment: MainAxisAlignment.center,
                                            crossAxisAlignment: CrossAxisAlignment.start,
                                            children: [
                                              Container(
                                                padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                                                decoration: BoxDecoration(
                                                  color: Colors.amber.shade700,
                                                  borderRadius: BorderRadius.circular(6),
                                                ),
                                                child: Text(
                                                  offerTitle,
                                                  maxLines: 1,
                                                  overflow: TextOverflow.ellipsis,
                                                  style: const TextStyle(
                                                    color: Colors.black,
                                                    fontSize: 11,
                                                    fontWeight: FontWeight.bold,
                                                  ),
                                                ),
                                              ),
                                              const SizedBox(height: 6),
                                              Text(
                                                name,
                                                maxLines: 2,
                                                overflow: TextOverflow.ellipsis,
                                                style: const TextStyle(
                                                  color: Colors.white,
                                                  fontSize: 14,
                                                  fontWeight: FontWeight.bold,
                                                  height: 1.2,
                                                ),
                                              ),
                                              const SizedBox(height: 6),
                                              Row(
                                                children: [
                                                  if (mrp > sellPrice && mrp > 0) ...[
                                                    Text(
                                                      "MRP: TK ${mrp.toStringAsFixed(0)}",
                                                      style: const TextStyle(
                                                        color: Color(0xFF4ADE80),
                                                        fontSize: 11,
                                                        fontWeight: FontWeight.bold,
                                                        decoration: TextDecoration.lineThrough,
                                                        decorationColor: Color(0xFFEF4444),
                                                        decorationThickness: 1.8,
                                                      ),
                                                    ),
                                                    const SizedBox(width: 6),
                                                  ],
                                                  Text(
                                                    "TK ${sellPrice.toStringAsFixed(0)}",
                                                    style: const TextStyle(
                                                      color: Colors.amberAccent,
                                                      fontSize: 17,
                                                      fontWeight: FontWeight.w900,
                                                    ),
                                                  ),
                                                ],
                                              ),
                                            ],
                                          ),
                                        ),
                                      ],
                                    ),
                                  ),
                                );
                              }

                              final promo = _promotions[index];
                              final colorVal = int.parse(promo["color"]!);
                              return Container(
                                margin: const EdgeInsets.symmetric(horizontal: 8, vertical: 6),
                                padding: const EdgeInsets.all(12),
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
                                      flex: 1,
                                      child: Container(
                                        decoration: BoxDecoration(
                                          color: Colors.white24,
                                          borderRadius: BorderRadius.circular(12),
                                        ),
                                        child: const Center(
                                          child: Icon(Icons.local_offer, size: 54, color: Colors.white),
                                        ),
                                      ),
                                    ),
                                    const SizedBox(width: 12),
                                    Expanded(
                                      flex: 1,
                                      child: Column(
                                        mainAxisAlignment: MainAxisAlignment.center,
                                        crossAxisAlignment: CrossAxisAlignment.start,
                                        children: [
                                          Text(
                                            promo["title"]!,
                                            style: const TextStyle(color: Colors.amberAccent, fontSize: 16, fontWeight: FontWeight.bold),
                                          ),
                                          const SizedBox(height: 6),
                                          Text(
                                            promo["subtitle"]!,
                                            style: const TextStyle(color: Colors.white, fontSize: 12),
                                          ),
                                        ],
                                      ),
                                    ),
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
                                _buildTabChip('🎁 Combo Packages', 'packages'),
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

                        // Sort By & Filter Status Bar
                        Container(
                          color: isDark ? Colors.grey[850] : Colors.grey[100],
                          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 2),
                          child: Row(
                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                            children: [
                              Expanded(
                                child: Text(
                                  _selectedTab == 'packages'
                                      ? 'Combo Packages (${_packagesList.length})'
                                      : (_searchQuery.isNotEmpty ? 'Category: $_searchQuery (${sortedProducts.length})' : 'Products (${sortedProducts.length})'),
                                  overflow: TextOverflow.ellipsis,
                                  style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 12),
                                ),
                              ),
                              Row(
                                children: [
                                  const Icon(Icons.sort, size: 15, color: Color(0xFF6B21A8)),
                                  const SizedBox(width: 4),
                                  DropdownButton<String>(
                                    value: _sortBy,
                                    underline: const SizedBox.shrink(),
                                    isDense: true,
                                    style: TextStyle(fontSize: 11.5, color: isDark ? Colors.white : Colors.black87, fontWeight: FontWeight.bold),
                                    items: const [
                                      DropdownMenuItem(value: 'default', child: Text('Sort: Featured')),
                                      DropdownMenuItem(value: 'price_low', child: Text('Price: Low to High')),
                                      DropdownMenuItem(value: 'price_high', child: Text('Price: High to Low')),
                                      DropdownMenuItem(value: 'newest', child: Text('Sort: Newest')),
                                    ],
                                    onChanged: (val) {
                                      if (val != null) {
                                        setState(() {
                                          _sortBy = val;
                                        });
                                      }
                                    },
                                  ),
                                ],
                              ),
                            ],
                          ),
                        ),

                        // Real-time Products / Packages Grid
                        Expanded(
                          child: RefreshIndicator(
                            onRefresh: () => _loadAllData(retryIfEmpty: false),
                            child: _selectedTab == 'packages'
                                ? (_packagesList.isEmpty
                                    ? ListView(
                                        physics: const AlwaysScrollableScrollPhysics(),
                                        children: [
                                          SizedBox(height: MediaQuery.of(context).size.height * 0.2),
                                          const Center(
                                            child: Column(
                                              mainAxisAlignment: MainAxisAlignment.center,
                                              children: [
                                                Icon(Icons.card_giftcard, size: 64, color: Colors.purple),
                                                SizedBox(height: 12),
                                                Text(
                                                  "🎁 Currently no combo package available.",
                                                  style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: Colors.grey),
                                                  textAlign: TextAlign.center,
                                                ),
                                              ],
                                            ),
                                          ),
                                        ],
                                      )
                                    : ListView.builder(
                                        physics: const AlwaysScrollableScrollPhysics(),
                                        padding: const EdgeInsets.all(12),
                                        itemCount: _packagesList.length,
                                        itemBuilder: (context, index) {
                                          final pkg = _packagesList[index];
                                          final name = pkg['name'] ?? 'Combo Bundle';
                                          final desc = pkg['description'] ?? '';
                                          final price = double.tryParse(pkg['package_price']?.toString() ?? '0') ?? 0.0;
                                          final items = pkg['items'] as List<dynamic>? ?? [];

                                          return Card(
                                          margin: const EdgeInsets.only(bottom: 12),
                                          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12), side: BorderSide(color: Colors.green.shade200)),
                                          child: Padding(
                                            padding: const EdgeInsets.all(14),
                                            child: Column(
                                              crossAxisAlignment: CrossAxisAlignment.start,
                                              children: [
                                                Row(
                                                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                                  children: [
                                                    Expanded(
                                                      child: Text("📦 $name", style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16, color: Colors.purple)),
                                                    ),
                                                    Text("TK ${price.toStringAsFixed(2)}", style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 17, color: Colors.green)),
                                                  ],
                                                ),
                                                if (desc.isNotEmpty) ...[
                                                  const SizedBox(height: 4),
                                                  Text(desc, style: const TextStyle(fontSize: 13, color: Colors.grey)),
                                                ],
                                                const Divider(height: 16),
                                                const Text("Included Items:", style: TextStyle(fontWeight: FontWeight.bold, fontSize: 12, color: Colors.black87)),
                                                const SizedBox(height: 4),
                                                ...items.map((it) => Padding(
                                                  padding: const EdgeInsets.symmetric(vertical: 2),
                                                  child: Text("• ${it['product_name']} × ${it['quantity']}", style: const TextStyle(fontSize: 13, color: Colors.black54)),
                                                )),
                                                Builder(
                                                  builder: (context) {
                                                    double regTotal = 0.0;
                                                    if (pkg['regular_total'] != null && double.tryParse(pkg['regular_total'].toString()) != null && double.tryParse(pkg['regular_total'].toString())! > 0) {
                                                      regTotal = double.tryParse(pkg['regular_total'].toString())!;
                                                    } else {
                                                      for (var it in items) {
                                                        int pQty = int.tryParse(it['quantity']?.toString() ?? '1') ?? 1;
                                                        double pMrp = double.tryParse(it['mrp']?.toString() ?? '0') ?? 0.0;
                                                        double pSell = double.tryParse(it['sell_price']?.toString() ?? '0') ?? 0.0;
                                                        double basePrice = pMrp > 0 ? pMrp : pSell;
                                                        regTotal += basePrice * pQty;
                                                      }
                                                    }
                                                    double savings = (regTotal - price) > 0 ? (regTotal - price) : 0.0;

                                                    return Container(
                                                      margin: const EdgeInsets.symmetric(vertical: 8),
                                                      padding: const EdgeInsets.all(10),
                                                      decoration: BoxDecoration(
                                                        color: const Color(0xFFF0FDF4),
                                                        borderRadius: BorderRadius.circular(8),
                                                        border: Border.all(color: const Color(0xFFBBF7D0)),
                                                      ),
                                                      child: Column(
                                                        crossAxisAlignment: CrossAxisAlignment.start,
                                                        children: [
                                                          Row(
                                                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                                            children: [
                                                              const Text("Total Regular Price", style: TextStyle(fontSize: 12, color: Color(0xFF64748B), fontWeight: FontWeight.w600)),
                                                              Text(
                                                                "TK ${regTotal > 0 ? regTotal.toStringAsFixed(2) : price.toStringAsFixed(2)}",
                                                                style: const TextStyle(fontSize: 12.5, color: Color(0xFF16A34A), decoration: TextDecoration.lineThrough, decorationColor: Color(0xFFDC2626), decorationThickness: 1.8, fontWeight: FontWeight.bold),
                                                              ),
                                                            ],
                                                          ),
                                                          const SizedBox(height: 3),
                                                          Row(
                                                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                                            children: [
                                                              const Text("Combo Special Price", style: TextStyle(fontSize: 13.5, color: Color(0xFF15803D), fontWeight: FontWeight.bold)),
                                                              Text("TK ${price.toStringAsFixed(2)}", style: const TextStyle(fontSize: 15.5, color: Color(0xFF15803D), fontWeight: FontWeight.w900)),
                                                            ],
                                                          ),
                                                          if (savings > 0) ...[
                                                            const SizedBox(height: 5),
                                                            Container(
                                                              width: double.infinity,
                                                              padding: const EdgeInsets.only(top: 5),
                                                              decoration: const BoxDecoration(
                                                                border: Border(top: BorderSide(color: Color(0xFFBBF7D0))),
                                                              ),
                                                              child: Text(
                                                                "🎁 Customer Savings / Discount: TK ${savings.toStringAsFixed(2)} OFF!",
                                                                style: const TextStyle(fontSize: 12, fontWeight: FontWeight.bold, color: Colors.red),
                                                              ),
                                                            ),
                                                          ],
                                                        ],
                                                      ),
                                                    );
                                                  },
                                                ),
                                                const SizedBox(height: 6),
                                                Builder(
                                                  builder: (context) {
                                                     int comboStock = 999;
                                                     String? outOfStockItemName;
                                                     for (var it in items) {
                                                       int pQty = int.tryParse(it['quantity']?.toString() ?? '1') ?? 1;
                                                       int itStock = int.tryParse(it['stock_qty']?.toString() ?? '0') ?? 0;
                                                       if (itStock <= 0) {
                                                         comboStock = 0;
                                                         outOfStockItemName = it['product_name'] ?? 'Item';
                                                         break;
                                                       }
                                                       int possible = itStock ~/ pQty;
                                                       if (possible < comboStock) {
                                                         comboStock = possible;
                                                         if (comboStock == 0) {
                                                           outOfStockItemName = it['product_name'] ?? 'Item';
                                                         }
                                                       }
                                                     }
                                                     if (comboStock == 999 || items.isEmpty) comboStock = 0;
                                                     if (pkg['stock_qty'] != null) {
                                                       int serverStock = int.tryParse(pkg['stock_qty'].toString()) ?? 0;
                                                       if (serverStock < comboStock) comboStock = serverStock;
                                                     }
                                                     if (pkg['is_out_of_stock'] == true) {
                                                       comboStock = 0;
                                                       if (pkg['out_of_stock_item'] != null) {
                                                         outOfStockItemName = pkg['out_of_stock_item'].toString();
                                                       }
                                                     }
                                                     bool isOutOfStock = comboStock <= 0;

                                                     return Column(
                                                       crossAxisAlignment: CrossAxisAlignment.start,
                                                       children: [
                                                         if (isOutOfStock)
                                                           Container(
                                                             width: double.infinity,
                                                             padding: const EdgeInsets.symmetric(vertical: 6, horizontal: 8),
                                                             margin: const EdgeInsets.only(bottom: 8),
                                                             decoration: BoxDecoration(
                                                               color: Colors.red.shade50,
                                                               borderRadius: BorderRadius.circular(6),
                                                               border: Border.all(color: Colors.red.shade200),
                                                             ),
                                                             child: Row(
                                                               children: [
                                                                 const Icon(Icons.error_outline, color: Colors.red, size: 16),
                                                                 const SizedBox(width: 6),
                                                                 const Expanded(
                                                                   child: Text(
                                                                     "Out of Stock",
                                                                     style: TextStyle(fontSize: 11.5, color: Colors.red, fontWeight: FontWeight.bold),
                                                                   ),
                                                                 ),
                                                               ],
                                                             ),
                                                           ),
                                                         SizedBox(
                                                           width: double.infinity,
                                                           child: ElevatedButton.icon(
                                                             onPressed: isOutOfStock
                                                                 ? null
                                                                 : () {
                                                                     List<String> itemSummaries = [];
                                                                     double regTotal = 0.0;
                                                                     for (var it in items) {
                                                                       String pSku = it['sku'] ?? 'SKU';
                                                                       String pName = it['product_name'] ?? 'Item';
                                                                       int pQty = int.tryParse(it['quantity']?.toString() ?? '1') ?? 1;
                                                                       double pMrp = double.tryParse(it['mrp']?.toString() ?? '0') ?? 0.0;
                                                                       double pPrice = double.tryParse(it['sell_price']?.toString() ?? '0') ?? 0.0;
                                                                       double basePrice = pMrp > 0 ? pMrp : pPrice;
                                                                       regTotal += basePrice * pQty;
                                                                       itemSummaries.add("$pSku $pName (Qty:$pQty)");
                                                                     }
                                                                     String skuSerialFormat = "$name (${itemSummaries.join(', ')})";

                                                                     Product pkgProduct = Product(
                                                                       id: pkg['id'],
                                                                       sku: skuSerialFormat,
                                                                       name: "📦 $name",
                                                                       sellPrice: price,
                                                                       mrp: regTotal > price ? regTotal : price,
                                                                       stockQty: comboStock,
                                                                     );

                                                                     bool added = cartProv.addToCart(pkgProduct);
                                                                     if (added) {
                                                                       ScaffoldMessenger.of(context).showSnackBar(
                                                                         SnackBar(
                                                                           content: Text("⚡ Combo Package '$name' added to cart!"),
                                                                           backgroundColor: Colors.green,
                                                                           action: SnackBarAction(
                                                                             label: "Checkout",
                                                                             textColor: Colors.white,
                                                                             onPressed: () {
                                                                               setState(() {
                                                                                 _bottomNavIndex = 2;
                                                                               });
                                                                             },
                                                                           ),
                                                                         ),
                                                                       );
                                                                     } else {
                                                                       showQuantityLimitDialog(context, cartProv.lastError ?? "Cannot add to cart: item is out of stock.");
                                                                     }
                                                                   },
                                                             icon: Icon(isOutOfStock ? Icons.block : Icons.bolt, color: Colors.white),
                                                             label: Text(
                                                               isOutOfStock ? "Out of Stock" : "Order Combo Package Now",
                                                               style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 14),
                                                             ),
                                                             style: ElevatedButton.styleFrom(
                                                               backgroundColor: isOutOfStock ? Colors.grey.shade400 : Colors.green,
                                                             ),
                                                           ),
                                                         ),
                                                       ],
                                                     );
                                                   },
                                                 ),
                                              ],
                                            ),
                                          ),
                                        );
                                      },
                                    ))
                              : _isLoadingProducts && _allProducts.isEmpty
                                  ? const Center(child: CircularProgressIndicator())
                                  : filteredProducts.isEmpty
                                      ? ListView(
                                          physics: const AlwaysScrollableScrollPhysics(),
                                          children: const [
                                            SizedBox(height: 80),
                                            Center(child: Text("No products found", style: TextStyle(color: Colors.grey, fontSize: 15))),
                                          ],
                                        )
                                      : CustomScrollView(
                                          physics: const AlwaysScrollableScrollPhysics(),
                                          slivers: [
                                        SliverPadding(
                                          padding: const EdgeInsets.all(10),
                                          sliver: SliverGrid(
                                            gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                                              crossAxisCount: 2,
                                              childAspectRatio: 0.59,
                                              crossAxisSpacing: 10,
                                              mainAxisSpacing: 10,
                                            ),
                                            delegate: SliverChildBuilderDelegate(
                                              (context, index) {
                                                final prod = displayProducts[index];
                                                final baseMrp = prod.mrp > 0 ? prod.mrp : prod.sellPrice;
                                                final savedAmount = (baseMrp > prod.effectivePrice)
                                                    ? (baseMrp - prod.effectivePrice)
                                                    : (prod.mrp > prod.sellPrice ? (prod.mrp - prod.sellPrice) : 0.0);

                                                return Container(
                                                  decoration: BoxDecoration(
                                                    color: isDark ? const Color(0xFF1E152A) : Colors.white,
                                                    borderRadius: BorderRadius.circular(16),
                                                    border: Border.all(
                                                      color: isDark ? Colors.purple.shade900.withOpacity(0.4) : Colors.purple.shade100.withOpacity(0.6),
                                                      width: 1,
                                                    ),
                                                    boxShadow: [
                                                      BoxShadow(
                                                        color: Colors.purple.withOpacity(isDark ? 0.2 : 0.05),
                                                        blurRadius: 8,
                                                        offset: const Offset(0, 3),
                                                      ),
                                                    ],
                                                  ),
                                                  child: InkWell(
                                                    borderRadius: BorderRadius.circular(16),
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
                                                          // Product Image Container
                                                          Expanded(
                                                            child: Container(
                                                              decoration: BoxDecoration(
                                                                color: isDark ? const Color(0xFF2D1F3F) : const Color(0xFFFAF5FF),
                                                                borderRadius: BorderRadius.circular(12),
                                                              ),
                                                              child: Stack(
                                                                children: [
                                                                  Center(
                                                                    child: ClipRRect(
                                                                      borderRadius: BorderRadius.circular(10),
                                                                      child: AppImageLoader(
                                                                        imageUrl: prod.imageList.isNotEmpty ? prod.imageList.first : prod.imageUrl,
                                                                        fit: BoxFit.contain,
                                                                      ),
                                                                    ),
                                                                  ),
                                                                  if (prod.stockQty <= 0)
                                                                    Positioned.fill(
                                                                      child: Container(
                                                                        decoration: BoxDecoration(
                                                                          color: Colors.white.withOpacity(0.75),
                                                                          borderRadius: BorderRadius.circular(10),
                                                                        ),
                                                                        alignment: Alignment.center,
                                                                        child: Container(
                                                                          padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                                                                          decoration: BoxDecoration(
                                                                            color: Colors.red.shade600,
                                                                            borderRadius: BorderRadius.circular(6),
                                                                          ),
                                                                          child: const Text(
                                                                            "Out of Stock",
                                                                            style: TextStyle(color: Colors.white, fontSize: 10, fontWeight: FontWeight.bold),
                                                                          ),
                                                                        ),
                                                                      ),
                                                                    ),
                                                                  if (prod.isOffer || prod.offerTitle.isNotEmpty || prod.offerType == 'bogo' || prod.offerType == 'buy_x_get_y' || savedAmount > 0)
                                                                    Positioned(
                                                                      top: 6,
                                                                      left: 6,
                                                                      child: Container(
                                                                        padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
                                                                        decoration: BoxDecoration(
                                                                          gradient: LinearGradient(
                                                                            colors: (prod.offerType == 'buy_x_get_y' || prod.offerType == 'bogo' || prod.offerTitle.toLowerCase().contains('buy'))
                                                                                ? [const Color(0xFFEA580C), const Color(0xFFF97316)]
                                                                                : [const Color(0xFFE11D48), const Color(0xFFF43F5E)],
                                                                          ),
                                                                          borderRadius: BorderRadius.circular(6),
                                                                          boxShadow: const [BoxShadow(color: Colors.black12, blurRadius: 3)],
                                                                        ),
                                                                        child: Text(
                                                                          prod.offerTitle.isNotEmpty
                                                                              ? prod.offerTitle
                                                                              : (prod.offerType == 'bogo'
                                                                                  ? (prod.offerValue.isNotEmpty ? prod.offerValue : 'Buy 1 Get 1 Free')
                                                                                  : (prod.offerType == 'percentage'
                                                                                      ? (prod.offerValue.isNotEmpty ? '${prod.offerValue}% OFF' : (savedAmount > 0 ? 'TK ${savedAmount.toStringAsFixed(0)} Save' : '% OFF'))
                                                                                      : (savedAmount > 0 ? 'TK ${savedAmount.toStringAsFixed(0)} Save' : 'Sale'))),
                                                                          style: const TextStyle(color: Colors.white, fontSize: 9, fontWeight: FontWeight.bold),
                                                                        ),
                                                                      ),
                                                                    ),
                                                                ],
                                                              ),
                                                            ),
                                                          ),
                                                          const SizedBox(height: 6),

                                                          // Product Title
                                                          Text(
                                                            prod.name,
                                                            maxLines: 1,
                                                            overflow: TextOverflow.ellipsis,
                                                            style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13, height: 1.2),
                                                          ),

                                                          const SizedBox(height: 4),

                                                          // Dual Price & Stock Row
                                                          Row(
                                                            mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                                            crossAxisAlignment: CrossAxisAlignment.end,
                                                            children: [
                                                              Expanded(
                                                                child: Column(
                                                                  crossAxisAlignment: CrossAxisAlignment.start,
                                                                  children: [
                                                                    Text(
                                                                      'MRP: TK ${(prod.mrp > 0 ? prod.mrp : prod.sellPrice).toStringAsFixed(0)}',
                                                                      style: const TextStyle(
                                                                        fontSize: 9.5,
                                                                        color: Color(0xFF16A34A),
                                                                        decoration: TextDecoration.lineThrough,
                                                                        decorationColor: Color(0xFFDC2626),
                                                                        decorationThickness: 1.8,
                                                                        fontWeight: FontWeight.bold,
                                                                      ),
                                                                    ),
                                                                    Text(
                                                                      'Doineek Price: TK ${prod.effectivePrice.toStringAsFixed(0)}',
                                                                      style: const TextStyle(
                                                                        fontSize: 12.5,
                                                                        fontWeight: FontWeight.w900,
                                                                        color: Color(0xFF6B21A8),
                                                                      ),
                                                                    ),
                                                                  ],
                                                                ),
                                                              ),
                                                              Container(
                                                                padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 2),
                                                                decoration: BoxDecoration(
                                                                  color: prod.stockQty > 0 ? const Color(0xFFF3E8FF) : Colors.red.shade50,
                                                                  borderRadius: BorderRadius.circular(6),
                                                                ),
                                                                child: Text(
                                                                  prod.stockQty > 0 ? 'Stock: ${prod.stockQty}' : 'Out of Stock',
                                                                  style: TextStyle(
                                                                    fontSize: 8.5,
                                                                    fontWeight: FontWeight.bold,
                                                                    color: prod.stockQty > 0 ? const Color(0xFF6B21A8) : Colors.red.shade800,
                                                                  ),
                                                                ),
                                                              ),
                                                            ],
                                                          ),

                                                          const SizedBox(height: 8),

                                                          // High-Contrast Buttons Row (Cart vs Buy Now)
                                                          Row(
                                                            children: prod.stockQty <= 0
                                                                ? [
                                                                    Expanded(
                                                                      child: SizedBox(
                                                                        height: 32,
                                                                        child: ElevatedButton(
                                                                          onPressed: null,
                                                                          style: ElevatedButton.styleFrom(
                                                                            backgroundColor: Colors.grey.shade300,
                                                                            elevation: 0,
                                                                            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                                                                            padding: EdgeInsets.zero,
                                                                          ),
                                                                          child: Text(
                                                                            "Out of Stock",
                                                                            style: TextStyle(fontSize: 11, fontWeight: FontWeight.bold, color: Colors.grey.shade600),
                                                                          ),
                                                                        ),
                                                                      ),
                                                                    ),
                                                                  ]
                                                                : [
                                                                    // Cart Button (Deep Royal Purple)
                                                                    Expanded(
                                                                      child: SizedBox(
                                                                        height: 32,
                                                                        child: ElevatedButton(
                                                                          onPressed: () {
                                                                            bool added = cartProv.addToCart(prod);
                                                                            if (added) {
                                                                              ScaffoldMessenger.of(context).showSnackBar(
                                                                                SnackBar(
                                                                                  content: Text('${prod.name} added to cart'),
                                                                                  duration: const Duration(seconds: 1),
                                                                                ),
                                                                              );
                                                                            } else {
                                                                              showQuantityLimitDialog(context, cartProv.lastError ?? 'Cannot add: item is out of stock.');
                                                                            }
                                                                          },
                                                                          style: ElevatedButton.styleFrom(
                                                                            backgroundColor: const Color(0xFF6B21A8),
                                                                            elevation: 0,
                                                                            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                                                                            padding: EdgeInsets.zero,
                                                                          ),
                                                                          child: const Row(
                                                                            mainAxisAlignment: MainAxisAlignment.center,
                                                                            children: [
                                                                              Icon(Icons.add_shopping_cart, size: 12, color: Colors.white),
                                                                              SizedBox(width: 3),
                                                                              Text(
                                                                                "Cart",
                                                                                style: TextStyle(fontSize: 11, fontWeight: FontWeight.bold, color: Colors.white),
                                                                              ),
                                                                            ],
                                                                          ),
                                                                        ),
                                                                      ),
                                                                    ),
                                                                    const SizedBox(width: 5),
                                                                    // Buy Now Button (Vibrant Coral Orange Gradient)
                                                                    Expanded(
                                                                      child: SizedBox(
                                                                        height: 32,
                                                                        child: ElevatedButton(
                                                                          onPressed: () {
                                                                            bool added = cartProv.addToCart(prod);
                                                                            if (added) {
                                                                              Navigator.push(
                                                                                context,
                                                                                MaterialPageRoute(builder: (_) => const CartScreen()),
                                                                              );
                                                                            } else {
                                                                              showQuantityLimitDialog(context, cartProv.lastError ?? 'Cannot proceed: item is out of stock.');
                                                                            }
                                                                          },
                                                                          style: ElevatedButton.styleFrom(
                                                                            backgroundColor: const Color(0xFFFF5722),
                                                                            elevation: 0,
                                                                            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                                                                            padding: EdgeInsets.zero,
                                                                          ),
                                                                          child: const Row(
                                                                            mainAxisAlignment: MainAxisAlignment.center,
                                                                            children: [
                                                                              Icon(Icons.bolt, size: 13, color: Colors.white),
                                                                              SizedBox(width: 2),
                                                                              Text(
                                                                                "Buy Now",
                                                                                style: TextStyle(fontSize: 11, fontWeight: FontWeight.bold, color: Colors.white),
                                                                              ),
                                                                            ],
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
                                                Row(
                                                  mainAxisAlignment: MainAxisAlignment.center,
                                                  children: [
                                                    const Text("Follow us on: ", style: TextStyle(fontWeight: FontWeight.bold, fontSize: 13, color: Colors.grey)),
                                                    const SizedBox(width: 8),
                                                    _buildSocialIcon(Icons.facebook, Colors.blue.shade800, _facebookUrl, "Facebook"),
                                                    const SizedBox(width: 10),
                                                    _buildSocialIcon(Icons.play_circle_fill, Colors.red, _youtubeUrl, "YouTube"),
                                                    const SizedBox(width: 10),
                                                    _buildSocialIcon(Icons.close, Colors.black, _xUrl, "X"),
                                                    const SizedBox(width: 10),
                                                    _buildSocialIcon(Icons.camera_alt, Colors.pink, _instagramUrl, "Instagram"),
                                                  ],
                                                ),
                                                const SizedBox(height: 12),
                                                const Text("© 2026 DOINEEK Supershop. All Rights Reserved.", style: TextStyle(fontSize: 11, color: Colors.grey)),
                                              ],
                                            ),
                                          ),
                                        ),
                                      ],
                                    ),
                                  ),
                                ),
                              ],
                            ),
                  _buildCategoryDirectoryView(),
                  const CartScreen(),
                  const ProfileScreen(),
                ],
              ),

              // Instant Search Dropdown Overlay
              if (_searchQuery.trim().isNotEmpty && _bottomNavIndex == 0)
                Positioned(
                  top: 52,
                  left: 12,
                  right: 12,
                  child: _buildSearchDropdownOverlay(allProducts),
                ),
            ],
          );
        },
      ),

      // 4-Tab Bottom Navigation Bar (Home, Category, Cart, Profile)
      bottomNavigationBar: BottomNavigationBar(
        currentIndex: _bottomNavIndex,
        selectedItemColor: const Color(0xFF6B21A8),
        unselectedItemColor: Colors.grey,
        type: BottomNavigationBarType.fixed,
        onTap: (index) {
          setState(() {
            _bottomNavIndex = index;
          });
          _loadUserProfile();
          if (index == 1) {
            setState(() {
              _selectedTab = 'all';
            });
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
          BottomNavigationBarItem(
            icon: _buildProfileTabIcon(),
            label: "Profile",
          ),
        ],
      ),
    );
  }

  Widget _buildSearchDropdownOverlay(List<Product> allProducts) {
    final matches = _filterProducts(allProducts);
    if (matches.isEmpty) return const SizedBox.shrink();

    return Material(
      elevation: 8,
      borderRadius: BorderRadius.circular(12),
      child: Container(
        constraints: const BoxConstraints(maxHeight: 250),
        decoration: BoxDecoration(
          color: Colors.white,
          borderRadius: BorderRadius.circular(12),
          border: Border.all(color: Colors.purple.shade200),
        ),
        child: ListView.separated(
          padding: const EdgeInsets.symmetric(vertical: 4),
          shrinkWrap: true,
          itemCount: matches.length,
          separatorBuilder: (_, __) => const Divider(height: 1),
          itemBuilder: (context, index) {
            final prod = matches[index];
            return ListTile(
              dense: true,
              leading: ClipRRect(
                borderRadius: BorderRadius.circular(4),
                child: SizedBox(
                  width: 36,
                  height: 36,
                  child: AppImageLoader(
                    imageUrl: prod.imageList.isNotEmpty ? prod.imageList.first : prod.imageUrl,
                    width: 36,
                    height: 36,
                    fit: BoxFit.contain,
                  ),
                ),
              ),
              title: Text(prod.name, style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13)),
              subtitle: Text("TK ${prod.effectivePrice.toStringAsFixed(0)}", style: const TextStyle(fontSize: 11, color: Colors.grey)),
              trailing: const Icon(Icons.arrow_forward_ios, size: 12, color: Color(0xFF6B21A8)),
              onTap: () {
                setState(() => _searchQuery = "");
                Navigator.push(
                  context,
                  MaterialPageRoute(builder: (_) => ProductDetailScreen(product: prod)),
                );
              },
            );
          },
        ),
      ),
    );
  }

  Widget _buildIconWidget(String iconStr, {double size = 20.0, IconData defaultIcon = Icons.category}) {
    final String cleanIcon = iconStr.trim();
    if (cleanIcon.startsWith('http://') || cleanIcon.startsWith('https://')) {
      return Image.network(
        cleanIcon,
        width: size,
        height: size,
        errorBuilder: (_, __, ___) => Icon(defaultIcon, size: size, color: const Color(0xFF6B21A8)),
      );
    } else if (cleanIcon.isNotEmpty) {
      return Text(
        cleanIcon,
        style: TextStyle(fontSize: size),
      );
    }
    return Icon(defaultIcon, size: size, color: const Color(0xFF6B21A8));
  }

  Widget _buildCategoryDirectoryView() {
    if (_isLoadingCategories && _categoriesTree.isEmpty) {
      return const Center(child: CircularProgressIndicator());
    }

    if (_categoriesTree.isEmpty) {
      return RefreshIndicator(
        onRefresh: () => _loadAllData(retryIfEmpty: false),
        child: ListView(
          children: [
            SizedBox(height: MediaQuery.of(context).size.height * 0.25),
            Center(
              child: Column(
                mainAxisAlignment: MainAxisAlignment.center,
                children: [
                  const Icon(Icons.category_outlined, size: 64, color: Colors.grey),
                  const SizedBox(height: 12),
                  const Text("No categories available", style: TextStyle(fontSize: 16, color: Colors.grey, fontWeight: FontWeight.bold)),
                  const SizedBox(height: 12),
                  ElevatedButton.icon(
                    onPressed: () => _loadAllData(retryIfEmpty: false),
                    icon: const Icon(Icons.refresh),
                    label: const Text("Tap to Refresh"),
                    style: ElevatedButton.styleFrom(backgroundColor: const Color(0xFF6B21A8), foregroundColor: Colors.white),
                  ),
                ],
              ),
            ),
          ],
        ),
      );
    }

    return RefreshIndicator(
      onRefresh: () => _loadAllData(retryIfEmpty: false),
      child: ListView.builder(
        padding: const EdgeInsets.all(12),
        itemCount: _categoriesTree.length,
        itemBuilder: (context, index) {
          final cat = _categoriesTree[index];
            final List subs = cat["sub_categories"] ?? [];
            final String catIcon = cat["icon"] ?? "";
            final int catProdCount = cat["product_count"] ?? 0;

            return Card(
              margin: const EdgeInsets.only(bottom: 10),
              elevation: 2,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
              child: ExpansionTile(
                leading: _buildIconWidget(catIcon, size: 22.0, defaultIcon: Icons.category),
                title: Text(
                  cat["name"] ?? "",
                  style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 15),
                ),
                subtitle: Text(
                  subs.isNotEmpty ? "${subs.length} Sub-Categories, $catProdCount Products" : "$catProdCount Products",
                  style: const TextStyle(fontSize: 12, color: Colors.grey),
                ),
                onExpansionChanged: (expanded) {
                  if (subs.isEmpty) {
                    Navigator.of(context, rootNavigator: true).push(
                      MaterialPageRoute(builder: (_) => CategoryProductsScreen(categoryName: cat["name"] ?? "Uncategorized")),
                    );
                  }
                },
                children: subs.map<Widget>((sub) {
                  final List subsubs = sub["sub_sub_categories"] ?? [];
                  final String subIcon = sub["icon"] ?? "";
                  final int subProdCount = sub["product_count"] ?? 0;

                  if (subsubs.isNotEmpty) {
                    return ExpansionTile(
                      tilePadding: const EdgeInsets.only(left: 36, right: 16),
                      leading: _buildIconWidget(subIcon, size: 18.0, defaultIcon: Icons.folder_open),
                      title: Text(
                        sub["name"] ?? "",
                        style: const TextStyle(fontWeight: FontWeight.w600, fontSize: 13.5),
                      ),
                      subtitle: Text(
                        "${subsubs.length} Sub-Categories, $subProdCount Products",
                        style: const TextStyle(fontSize: 11, color: Colors.grey),
                      ),
                      children: subsubs.map<Widget>((ss) {
                        final String ssIcon = ss["icon"] ?? "";
                        final int ssProdCount = ss["product_count"] ?? 0;
                        final String ssFormattedCount = ssProdCount.toString().padLeft(2, '0');

                        return ListTile(
                          contentPadding: const EdgeInsets.only(left: 64, right: 16),
                          leading: _buildIconWidget(ssIcon, size: 16.0, defaultIcon: Icons.subdirectory_arrow_right),
                          title: Text(ss["name"] ?? "", style: const TextStyle(fontSize: 12.5, fontWeight: FontWeight.w600)),
                          subtitle: Text("$ssFormattedCount Products", style: const TextStyle(fontSize: 10.5, color: Colors.grey)),
                          onTap: () {
                            Navigator.of(context, rootNavigator: true).push(
                              MaterialPageRoute(builder: (_) => CategoryProductsScreen(categoryName: ss["name"] ?? "")),
                            );
                          },
                        );
                      }).toList(),
                    );
                  }

                  return ListTile(
                    contentPadding: const EdgeInsets.only(left: 44, right: 16),
                    leading: _buildIconWidget(subIcon, size: 18.0, defaultIcon: Icons.subdirectory_arrow_right),
                    title: Text(sub["name"] ?? "", style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w600)),
                    subtitle: Text("$subProdCount Products", style: const TextStyle(fontSize: 11, color: Colors.grey)),
                    onTap: () {
                      Navigator.of(context, rootNavigator: true).push(
                        MaterialPageRoute(builder: (_) => CategoryProductsScreen(categoryName: sub["name"] ?? "")),
                      );
                    },
                  );
                }).toList(),
              ),
            );
          },
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
            title: Text(title, style: const TextStyle(fontWeight: FontWeight.bold, color: Color(0xFF6B21A8))),
            content: SingleChildScrollView(
              child: Text(content, style: const TextStyle(fontSize: 14, height: 1.4)),
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(dialogCtx),
                child: const Text("Close"),
              ),
            ],
          ),
        );
      },
      child: Text(
        title,
        style: const TextStyle(fontSize: 12, color: Color(0xFF6B21A8), fontWeight: FontWeight.bold, decoration: TextDecoration.underline),
      ),
    );
  }

  Widget _buildTabChip(String label, String key) {
    bool isSelected = _selectedTab == key;
    bool isDark = Theme.of(context).brightness == Brightness.dark;

    return ChoiceChip(
      label: Text(label),
      selected: isSelected,
      selectedColor: const Color(0xFF6B21A8),
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

// Dedicated Category Products Screen (No Bottom Navigation Bar)
class CategoryProductsScreen extends StatefulWidget {
  final String categoryName;
  const CategoryProductsScreen({Key? key, required this.categoryName}) : super(key: key);

  @override
  State<CategoryProductsScreen> createState() => _CategoryProductsScreenState();
}

class _CategoryProductsScreenState extends State<CategoryProductsScreen> {
  String _sortBy = 'default';
  late Future<List<Product>> _productsFuture;

  @override
  void initState() {
    super.initState();
    _productsFuture = ApiService.fetchProducts();
  }

  List<Product> _filterCategoryProducts(List<Product> allProducts) {
    List<Product> list = allProducts;
    String q = widget.categoryName.trim().toLowerCase();
    if (q == 'uncategorized') {
      list = list.where((p) => p.categoryId == null || p.categoryId == 0 || p.categoryName.trim().isEmpty || p.categoryName.trim().toLowerCase() == 'uncategorized').toList();
    } else {
      list = list.where((p) =>
        p.categoryName.trim().toLowerCase() == q ||
        p.subCategoryName.trim().toLowerCase() == q ||
        p.subSubCategoryName.trim().toLowerCase() == q ||
        p.name.toLowerCase().contains(q)
      ).toList();
    }

    List<Product> sortedProducts = List.from(list);
    if (_sortBy == 'price_low') {
      sortedProducts.sort((a, b) => a.effectivePrice.compareTo(b.effectivePrice));
    } else if (_sortBy == 'price_high') {
      sortedProducts.sort((a, b) => b.effectivePrice.compareTo(a.effectivePrice));
    } else if (_sortBy == 'newest') {
      sortedProducts.sort((a, b) => b.id.compareTo(a.id));
    }
    return sortedProducts;
  }

  @override
  Widget build(BuildContext context) {
    final loc = AppLocalizations.of(context);
    final cartProv = Provider.of<CartProvider>(context);
    final isDark = Theme.of(context).brightness == Brightness.dark;

    return Scaffold(
      appBar: AppBar(
        backgroundColor: const Color(0xFF6B21A8),
        leading: IconButton(
          icon: const Icon(Icons.arrow_back, color: Colors.white),
          onPressed: () => Navigator.pop(context),
        ),
        title: Text(
          widget.categoryName,
          style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 18, color: Colors.white),
        ),
      ),
      body: FutureBuilder<List<Product>>(
        future: _productsFuture,
        builder: (context, snapshot) {
          if (snapshot.connectionState == ConnectionState.waiting && !snapshot.hasData) {
            return const Center(child: CircularProgressIndicator());
          }
          final allProducts = snapshot.data ?? [];
          final displayProducts = _filterCategoryProducts(allProducts);

          if (displayProducts.isEmpty) {
            return RefreshIndicator(
              onRefresh: () async {
                setState(() {
                  _productsFuture = ApiService.fetchProducts();
                });
              },
              child: ListView(
                physics: const AlwaysScrollableScrollPhysics(),
                children: const [
                  SizedBox(height: 100),
                  Center(
                    child: Text(
                      "No products found in this category",
                      style: TextStyle(fontSize: 14, color: Colors.grey),
                    ),
                  ),
                ],
              ),
            );
          }

          return Column(
            children: [
              // Header bar with count & Sort By dropdown
              Container(
                color: isDark ? Colors.grey[850] : Colors.grey[100],
                padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 4),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text(
                      'Total Products (${displayProducts.length})',
                      style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 12.5),
                    ),
                    Row(
                      children: [
                        const Icon(Icons.sort, size: 15, color: Color(0xFF6B21A8)),
                        const SizedBox(width: 4),
                        DropdownButton<String>(
                          value: _sortBy,
                          underline: const SizedBox.shrink(),
                          isDense: true,
                          style: TextStyle(fontSize: 11.5, color: isDark ? Colors.white : Colors.black87, fontWeight: FontWeight.bold),
                          items: const [
                            DropdownMenuItem(value: 'default', child: Text('Sort: Featured')),
                            DropdownMenuItem(value: 'price_low', child: Text('Price: Low to High')),
                            DropdownMenuItem(value: 'price_high', child: Text('Price: High to Low')),
                            DropdownMenuItem(value: 'newest', child: Text('Sort: Newest')),
                          ],
                          onChanged: (val) {
                            if (val != null) {
                              setState(() {
                                _sortBy = val;
                              });
                            }
                          },
                        ),
                      ],
                    ),
                  ],
                ),
              ),

              // Product Grid
              Expanded(
                child: RefreshIndicator(
                  onRefresh: () async {
                    setState(() {
                      _productsFuture = ApiService.fetchProducts();
                    });
                  },
                  child: GridView.builder(
                    physics: const AlwaysScrollableScrollPhysics(),
                    padding: const EdgeInsets.all(10),
                  gridDelegate: const SliverGridDelegateWithFixedCrossAxisCount(
                    crossAxisCount: 2,
                    childAspectRatio: 0.59,
                    crossAxisSpacing: 10,
                    mainAxisSpacing: 10,
                  ),
                  itemCount: displayProducts.length,
                  itemBuilder: (context, index) {
                    final prod = displayProducts[index];
                    final baseMrp = prod.mrp > 0 ? prod.mrp : prod.sellPrice;
                    final savedAmount = (baseMrp > prod.effectivePrice)
                        ? (baseMrp - prod.effectivePrice)
                        : (prod.mrp > prod.sellPrice ? (prod.mrp - prod.sellPrice) : 0.0);

                    return Container(
                      decoration: BoxDecoration(
                        color: isDark ? const Color(0xFF1E152A) : Colors.white,
                        borderRadius: BorderRadius.circular(16),
                        border: Border.all(
                          color: isDark ? Colors.purple.shade900.withOpacity(0.4) : Colors.purple.shade100.withOpacity(0.6),
                          width: 1,
                        ),
                        boxShadow: [
                          BoxShadow(
                            color: Colors.purple.withOpacity(isDark ? 0.2 : 0.05),
                            blurRadius: 8,
                            offset: const Offset(0, 3),
                          ),
                        ],
                      ),
                      child: InkWell(
                        borderRadius: BorderRadius.circular(16),
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
                              // Product Image
                              Expanded(
                                child: Container(
                                  decoration: BoxDecoration(
                                    color: isDark ? const Color(0xFF2D1F3F) : const Color(0xFFFAF5FF),
                                    borderRadius: BorderRadius.circular(12),
                                  ),
                                  child: Stack(
                                    children: [
                                      Center(
                                        child: ClipRRect(
                                          borderRadius: BorderRadius.circular(10),
                                          child: AppImageLoader(
                                            imageUrl: prod.imageList.isNotEmpty ? prod.imageList.first : prod.imageUrl,
                                            fit: BoxFit.contain,
                                          ),
                                        ),
                                      ),
                                                                                       if (prod.stockQty <= 0)
                                         Positioned.fill(
                                           child: Container(
                                             decoration: BoxDecoration(
                                               color: Colors.white.withOpacity(0.75),
                                               borderRadius: BorderRadius.circular(10),
                                             ),
                                             alignment: Alignment.center,
                                             child: Container(
                                               padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                                               decoration: BoxDecoration(
                                                 color: Colors.red.shade600,
                                                 borderRadius: BorderRadius.circular(6),
                                               ),
                                               child: const Text(
                                                 "Out of Stock",
                                                 style: TextStyle(color: Colors.white, fontSize: 10, fontWeight: FontWeight.bold),
                                               ),
                                             ),
                                           ),
                                         ),
                                                 if (prod.isOffer || prod.offerTitle.isNotEmpty || prod.offerType == 'bogo' || prod.offerType == 'buy_x_get_y' || savedAmount > 0)
                                Positioned(
                                  top: 6,
                                  left: 6,
                                  child: Container(
                                    padding: const EdgeInsets.symmetric(horizontal: 7, vertical: 3),
                                    decoration: BoxDecoration(
                                      gradient: LinearGradient(
                                        colors: (prod.offerType == 'buy_x_get_y' || prod.offerType == 'bogo' || prod.offerTitle.toLowerCase().contains('buy'))
                                            ? [const Color(0xFFEA580C), const Color(0xFFF97316)]
                                            : [const Color(0xFFE11D48), const Color(0xFFF43F5E)],
                                      ),
                                      borderRadius: BorderRadius.circular(6),
                                      boxShadow: const [BoxShadow(color: Colors.black12, blurRadius: 3)],
                                    ),
                                    child: Text(
                                      prod.offerTitle.isNotEmpty
                                          ? prod.offerTitle
                                          : (prod.offerType == 'bogo'
                                              ? (prod.offerValue.isNotEmpty ? prod.offerValue : 'Buy 1 Get 1 Free')
                                              : (prod.offerType == 'percentage'
                                                  ? (prod.offerValue.isNotEmpty ? '${prod.offerValue}% OFF' : (savedAmount > 0 ? 'TK ${savedAmount.toStringAsFixed(0)} Save' : '% OFF'))
                                                  : (savedAmount > 0 ? 'TK ${savedAmount.toStringAsFixed(0)} Save' : 'Sale'))),
                                      style: const TextStyle(color: Colors.white, fontSize: 9, fontWeight: FontWeight.bold),
                                    ),
                                  ),
                                ),
                                    ],
                                  ),
                                ),
                              ),
                              const SizedBox(height: 6),

                              // Product Title
                              Text(
                                prod.name,
                                maxLines: 1,
                                overflow: TextOverflow.ellipsis,
                                style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13, height: 1.2),
                              ),

                              const SizedBox(height: 4),

                              // Dual Price & Stock Row
                              Row(
                                mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                crossAxisAlignment: CrossAxisAlignment.end,
                                children: [
                                  Expanded(
                                    child: Column(
                                      crossAxisAlignment: CrossAxisAlignment.start,
                                      children: [
                                        Text(
                                          'MRP: TK ${(prod.mrp > 0 ? prod.mrp : prod.sellPrice).toStringAsFixed(0)}',
                                          style: const TextStyle(
                                            fontSize: 9.5,
                                            color: Color(0xFF16A34A),
                                            decoration: TextDecoration.lineThrough,
                                            decorationColor: Color(0xFFDC2626),
                                            decorationThickness: 1.8,
                                            fontWeight: FontWeight.bold,
                                          ),
                                        ),
                                        Text(
                                          'Doineek Price: TK ${prod.effectivePrice.toStringAsFixed(0)}',
                                          style: const TextStyle(
                                            fontSize: 12.5,
                                            fontWeight: FontWeight.w900,
                                            color: Color(0xFF6B21A8),
                                          ),
                                        ),
                                      ],
                                    ),
                                  ),
                                  Container(
                                    padding: const EdgeInsets.symmetric(horizontal: 5, vertical: 2),
                                    decoration: BoxDecoration(
                                      color: prod.stockQty > 0 ? const Color(0xFFF3E8FF) : Colors.red.shade50,
                                      borderRadius: BorderRadius.circular(6),
                                    ),
                                    child: Text(
                                      prod.stockQty > 0 ? 'Stock: ${prod.stockQty}' : 'Out of Stock',
                                      style: TextStyle(
                                        fontSize: 8.5,
                                        fontWeight: FontWeight.bold,
                                        color: prod.stockQty > 0 ? const Color(0xFF6B21A8) : Colors.red.shade800,
                                      ),
                                    ),
                                  ),
                                ],
                              ),

                              const SizedBox(height: 8),

                              // Cart & Buy Now Buttons Row
                              Row(
                                children: prod.stockQty <= 0
                                    ? [
                                        Expanded(
                                          child: SizedBox(
                                            height: 32,
                                            child: ElevatedButton(
                                              onPressed: null,
                                              style: ElevatedButton.styleFrom(
                                                backgroundColor: Colors.grey.shade300,
                                                elevation: 0,
                                                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                                                padding: EdgeInsets.zero,
                                              ),
                                              child: Text(
                                                "Out of Stock",
                                                style: TextStyle(fontSize: 11, fontWeight: FontWeight.bold, color: Colors.grey.shade600),
                                              ),
                                            ),
                                          ),
                                        ),
                                      ]
                                    : [
                                        Expanded(
                                          child: SizedBox(
                                            height: 32,
                                            child: ElevatedButton(
                                              onPressed: () {
                                                bool added = cartProv.addToCart(prod);
                                                if (added) {
                                                  ScaffoldMessenger.of(context).showSnackBar(
                                                    SnackBar(
                                                      content: Text('${prod.name} added to cart'),
                                                      duration: const Duration(seconds: 1),
                                                    ),
                                                  );
                                                } else {
                                                  showQuantityLimitDialog(context, cartProv.lastError ?? 'Cannot add: item is out of stock.');
                                                }
                                              },
                                              style: ElevatedButton.styleFrom(
                                                backgroundColor: const Color(0xFF6B21A8),
                                                elevation: 0,
                                                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                                                padding: EdgeInsets.zero,
                                              ),
                                              child: const Row(
                                                mainAxisAlignment: MainAxisAlignment.center,
                                                children: [
                                                  Icon(Icons.add_shopping_cart, size: 12, color: Colors.white),
                                                  SizedBox(width: 3),
                                                  Text(
                                                    "Cart",
                                                    style: TextStyle(fontSize: 11, fontWeight: FontWeight.bold, color: Colors.white),
                                                  ),
                                                ],
                                              ),
                                            ),
                                          ),
                                        ),
                                        const SizedBox(width: 5),
                                        Expanded(
                                          child: SizedBox(
                                            height: 32,
                                            child: ElevatedButton(
                                              onPressed: () {
                                                bool added = cartProv.addToCart(prod);
                                                if (added) {
                                                  Navigator.push(
                                                    context,
                                                    MaterialPageRoute(builder: (_) => const CartScreen()),
                                                  );
                                                } else {
                                                  showQuantityLimitDialog(context, cartProv.lastError ?? 'Cannot proceed: item is out of stock.');
                                                }
                                              },
                                              style: ElevatedButton.styleFrom(
                                                backgroundColor: const Color(0xFFFF5722),
                                                elevation: 0,
                                                shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                                                padding: EdgeInsets.zero,
                                              ),
                                              child: const Row(
                                                mainAxisAlignment: MainAxisAlignment.center,
                                                children: [
                                                  Icon(Icons.bolt, size: 13, color: Colors.white),
                                                  SizedBox(width: 2),
                                                  Text(
                                                    "Buy Now",
                                                    style: TextStyle(fontSize: 11, fontWeight: FontWeight.bold, color: Colors.white),
                                                  ),
                                                ],
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
                ),
              ),
            ),
            ],
          );
        },
      ),
    );
  }
}
