import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../../models/product.dart';
import '../../providers/cart_provider.dart';
import '../../services/api_service.dart';
import '../../widgets/app_image_loader.dart';
import '../../widgets/quantity_limit_dialog.dart';
import 'cart_screen.dart';
import 'product_detail_screen.dart';

class PackageDetailScreen extends StatelessWidget {
  final Map<String, dynamic> packageData;

  const PackageDetailScreen({Key? key, required this.packageData}) : super(key: key);

  int _toInt(dynamic v, [int fb = 0]) {
    if (v == null) return fb;
    if (v is int) return v;
    if (v is num) return v.toInt();
    return int.tryParse(v.toString()) ?? fb;
  }

  double _toDouble(dynamic v, [double fb = 0.0]) {
    if (v == null) return fb;
    if (v is double) return v;
    if (v is num) return v.toDouble();
    return double.tryParse(v.toString()) ?? fb;
  }

  Product _buildPackageCartProduct() {
    final String name = (packageData['name'] ?? 'Combo Package').toString();
    final double price = _toDouble(packageData['package_price']);
    final List<dynamic> items = packageData['items'] as List<dynamic>? ?? [];
    int comboStock = _toInt(packageData['stock_qty'], 99);
    if (packageData['is_out_of_stock'] == true) comboStock = 0;

    final List<String> itemSummaries = [];
    double regTotal = _toDouble(packageData['regular_total']);
    double calcReg = 0.0;
    String pkgImg = (packageData['image_url'] ?? '').toString().trim();

    for (final it in items) {
      if (it is Map) {
        final String pSku = (it['sku'] ?? 'SKU').toString();
        final String pName = (it['product_name'] ?? it['prod_name'] ?? 'Item').toString();
        final int pQty = _toInt(it['quantity'] ?? it['item_qty'], 1);
        final double pMrp = _toDouble(it['mrp']);
        final double pSell = _toDouble(it['sell_price']);
        final double basePrice = pMrp > 0 ? pMrp : pSell;
        calcReg += basePrice * pQty;
        itemSummaries.add("$pSku $pName (Qty:$pQty)");
        if (pkgImg.isEmpty) {
          final cand = (it['image_url'] ?? '').toString().trim();
          if (cand.isNotEmpty) pkgImg = cand;
        }
      }
    }
    if (regTotal <= 0) regTotal = calcReg;
    final int rawPkgId = _toInt(packageData['id'], 1).abs();

    return Product(
      id: -rawPkgId,
      packageId: rawPkgId,
      sku: "$name (${itemSummaries.join(', ')})",
      name: "📦 $name",
      sellPrice: price,
      mrp: regTotal > price ? regTotal : price,
      stockQty: comboStock > 0 ? comboStock : 1,
      imageUrl: pkgImg,
    );
  }

  Future<void> _openIncludedProduct(BuildContext context, Map<String, dynamic> item) async {
    final int pid = _toInt(item['product_id']);
    final String pName = (item['product_name'] ?? item['prod_name'] ?? '').toString();
    final products = await ApiService.fetchProducts();
    if (!context.mounted) return;
    Product? found;
    if (pid > 0) {
      for (final p in products) {
        if (p.id == pid) {
          found = p;
          break;
        }
      }
    }
    if (found == null && pName.isNotEmpty) {
      final low = pName.trim().toLowerCase();
      for (final p in products) {
        if (p.name.trim().toLowerCase() == low) {
          found = p;
          break;
        }
      }
    }
    if (found != null) {
      Navigator.push(
        context,
        MaterialPageRoute(builder: (_) => ProductDetailScreen(product: found!)),
      );
    } else {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text("Product details are currently unavailable.")),
      );
    }
  }

  @override
  Widget build(BuildContext context) {
    final cartProv = Provider.of<CartProvider>(context);
    final String name = (packageData['name'] ?? 'Combo Package').toString();
    final String desc = (packageData['description'] ?? '').toString();
    final double price = _toDouble(packageData['package_price']);
    final double regTotal = _toDouble(packageData['regular_total']);
    final List<dynamic> items = packageData['items'] as List<dynamic>? ?? [];
    final bool isOut = packageData['is_out_of_stock'] == true || _toInt(packageData['stock_qty'], 99) <= 0;

    String pkgImg = (packageData['image_url'] ?? '').toString().trim();
    if (pkgImg.isEmpty) {
      for (final it in items) {
        if (it is Map) {
          final cand = (it['image_url'] ?? '').toString().trim();
          if (cand.isNotEmpty) {
            pkgImg = cand;
            break;
          }
        }
      }
    }

    final double savings = regTotal > price ? (regTotal - price) : 0.0;

    return Scaffold(
      appBar: AppBar(
        title: const Text("🎁 Combo Package"),
        backgroundColor: const Color(0xFF6B21A8),
        foregroundColor: Colors.white,
        actions: [
          IconButton(
            onPressed: () {
              Navigator.push(context, MaterialPageRoute(builder: (_) => const CartScreen()));
            },
            icon: Badge(
              label: Text('${cartProv.totalItemCount}'),
              isLabelVisible: cartProv.totalItemCount > 0,
              child: const Icon(Icons.shopping_cart),
            ),
          ),
        ],
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(14),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              width: double.infinity,
              height: 220,
              decoration: BoxDecoration(
                color: const Color(0xFFFAF5FF),
                borderRadius: BorderRadius.circular(14),
                border: Border.all(color: Colors.purple.shade100),
              ),
              child: ClipRRect(
                borderRadius: BorderRadius.circular(14),
                child: pkgImg.isNotEmpty
                    ? AppImageLoader(imageUrl: pkgImg, fit: BoxFit.contain)
                    : const Center(
                        child: Icon(Icons.card_giftcard, size: 72, color: Colors.purple),
                      ),
              ),
            ),
            const SizedBox(height: 14),
            Row(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Expanded(
                  child: Text(
                    name,
                    style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w900, color: Color(0xFF1E293B)),
                  ),
                ),
                const SizedBox(width: 8),
                Container(
                  padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                  decoration: BoxDecoration(
                    color: Colors.purple.shade50,
                    borderRadius: BorderRadius.circular(8),
                    border: Border.all(color: Colors.purple.shade200),
                  ),
                  child: const Text(
                    "COMBO",
                    style: TextStyle(fontWeight: FontWeight.w800, color: Color(0xFF6B21A8), fontSize: 11),
                  ),
                ),
              ],
            ),
            const SizedBox(height: 8),
            Row(
              children: [
                Text(
                  "TK ${price.toStringAsFixed(0)}",
                  style: const TextStyle(fontSize: 22, fontWeight: FontWeight.w900, color: Color(0xFF6B21A8)),
                ),
                if (savings > 0) ...[
                  const SizedBox(width: 10),
                  Text(
                    "TK ${regTotal.toStringAsFixed(0)}",
                    style: const TextStyle(
                      fontSize: 14,
                      color: Colors.grey,
                      decoration: TextDecoration.lineThrough,
                      fontWeight: FontWeight.bold,
                    ),
                  ),
                  const SizedBox(width: 8),
                  Container(
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                    decoration: BoxDecoration(
                      color: Colors.green.shade100,
                      borderRadius: BorderRadius.circular(6),
                    ),
                    child: Text(
                      "Save TK ${savings.toStringAsFixed(0)}",
                      style: const TextStyle(color: Colors.green, fontWeight: FontWeight.w800, fontSize: 11.5),
                    ),
                  ),
                ],
              ],
            ),
            if (desc.isNotEmpty) ...[
              const SizedBox(height: 10),
              Text(desc, style: TextStyle(color: Colors.grey.shade700, fontSize: 13.5, height: 1.4)),
            ],
            const SizedBox(height: 16),
            const Text(
              "📦 এই কম্বো প্যাকেজে যা থাকছে (ট্যাপ করলে বিস্তারিত দেখা যাবে):",
              style: TextStyle(fontWeight: FontWeight.w800, fontSize: 13.5, color: Color(0xFF4C1D95)),
            ),
            const SizedBox(height: 8),
            ...items.whereType<Map>().map((it) {
              final String pName = (it['product_name'] ?? it['prod_name'] ?? 'Product').toString();
              final int qty = _toInt(it['quantity'] ?? it['item_qty'], 1);
              final double pPrice = _toDouble(it['sell_price'] ?? it['mrp']);
              final String img = (it['image_url'] ?? '').toString();
              return Card(
                margin: const EdgeInsets.only(bottom: 8),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(10),
                  side: BorderSide(color: Colors.grey.shade200),
                ),
                child: ListTile(
                  onTap: () => _openIncludedProduct(context, Map<String, dynamic>.from(it)),
                  leading: ClipRRect(
                    borderRadius: BorderRadius.circular(6),
                    child: SizedBox(
                      width: 44,
                      height: 44,
                      child: AppImageLoader(imageUrl: img, fit: BoxFit.contain),
                    ),
                  ),
                  title: Text(pName, style: const TextStyle(fontWeight: FontWeight.w700, fontSize: 13)),
                  subtitle: Text("Qty: $qty × TK ${pPrice.toStringAsFixed(0)}", style: const TextStyle(fontSize: 12)),
                  trailing: const Icon(Icons.arrow_forward_ios, size: 14, color: Colors.purple),
                ),
              );
            }),
            const SizedBox(height: 18),
            if (isOut)
              SizedBox(
                width: double.infinity,
                height: 46,
                child: ElevatedButton.icon(
                  onPressed: null,
                  icon: const Icon(Icons.block),
                  label: const Text("Out of Stock"),
                ),
              )
            else
              Row(
                children: [
                  Expanded(
                    child: SizedBox(
                      height: 46,
                      child: ElevatedButton.icon(
                        onPressed: () {
                          final prod = _buildPackageCartProduct();
                          if (cartProv.addToCart(prod)) {
                            ScaffoldMessenger.of(context).showSnackBar(
                              SnackBar(
                                content: Text("⚡ '$name' কার্টে যোগ করা হয়েছে"),
                                backgroundColor: Colors.green,
                              ),
                            );
                          } else {
                            showQuantityLimitDialog(context, cartProv.lastError ?? "Out of stock");
                          }
                        },
                        icon: const Icon(Icons.add_shopping_cart, size: 18, color: Colors.white),
                        label: const Text("Add to Cart", style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
                        style: ElevatedButton.styleFrom(
                          backgroundColor: const Color(0xFF6B21A8),
                          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                        ),
                      ),
                    ),
                  ),
                  const SizedBox(width: 10),
                  Expanded(
                    child: SizedBox(
                      height: 46,
                      child: ElevatedButton.icon(
                        onPressed: () {
                          final prod = _buildPackageCartProduct();
                          if (cartProv.addToCart(prod)) {
                            Navigator.push(context, MaterialPageRoute(builder: (_) => const CartScreen()));
                          } else {
                            showQuantityLimitDialog(context, cartProv.lastError ?? "Out of stock");
                          }
                        },
                        icon: const Icon(Icons.bolt, size: 18, color: Colors.white),
                        label: const Text("Order Now", style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
                        style: ElevatedButton.styleFrom(
                          backgroundColor: Colors.green,
                          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                        ),
                      ),
                    ),
                  ),
                ],
              ),
          ],
        ),
      ),
    );
  }
}
