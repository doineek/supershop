import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:url_launcher/url_launcher.dart';
import '../../services/api_service.dart';
import '../auth/login_screen.dart';
import '../customer/home_screen.dart';

class AdminHubScreen extends StatefulWidget {
  final String? username;
  final String? role;

  const AdminHubScreen({super.key, this.username, this.role});

  @override
  State<AdminHubScreen> createState() => _AdminHubScreenState();
}

class _AdminHubScreenState extends State<AdminHubScreen> {
  String _displayName = "Admin / Cashier";
  String _role = "admin";
  String _activeServerUrl = "https://doineek.onrender.com";

  @override
  void initState() {
    super.initState();
    _loadAdminData();
  }

  Future<void> _loadAdminData() async {
    final prefs = await SharedPreferences.getInstance();
    setState(() {
      _displayName = widget.username ?? prefs.getString('user_name') ?? prefs.getString('user_phone') ?? "Admin";
      _role = widget.role ?? prefs.getString('user_role') ?? "admin";
      if (ApiService.candidateUrls.isNotEmpty) {
        _activeServerUrl = ApiService.candidateUrls.first;
      }
    });
  }

  Future<void> _launchAdminRoute(String path) async {
    String cleanBase = _activeServerUrl.trim().replaceAll(RegExp(r'/+$'), '');
    String targetUrl = "$cleanBase$path";
    final uri = Uri.parse(targetUrl);

    try {
      final launched = await launchUrl(uri, mode: LaunchMode.externalApplication);
      if (!launched) {
        await launchUrl(uri, mode: LaunchMode.platformDefault);
      }
    } catch (e) {
      if (mounted) {
        ScaffoldMessenger.of(context).showSnackBar(
          SnackBar(
            content: Text("Could not open web portal: $e"),
            backgroundColor: Colors.red,
          ),
        );
      }
    }
  }

  Future<void> _logout() async {
    final prefs = await SharedPreferences.getInstance();
    await prefs.remove('user_phone');
    await prefs.remove('user_name');
    await prefs.remove('user_role');
    await prefs.remove('is_admin_mode');
    await prefs.remove('stay_signed_in');

    if (!mounted) return;
    Navigator.pushAndRemoveUntil(
      context,
      MaterialPageRoute(builder: (_) => const LoginScreen()),
      (route) => false,
    );
  }

  @override
  Widget build(BuildContext context) {
    return Scaffold(
      backgroundColor: const Color(0xFF0F172A),
      appBar: AppBar(
        backgroundColor: const Color(0xFF1E293B),
        elevation: 2,
        title: Row(
          children: [
            Container(
              padding: const EdgeInsets.all(6),
              decoration: BoxDecoration(
                color: Colors.amber.shade700,
                borderRadius: BorderRadius.circular(8),
              ),
              child: const Icon(Icons.shield, color: Colors.white, size: 20),
            ),
            const SizedBox(width: 10),
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                const Text(
                  "Admin & Cashier Portal",
                  style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: Colors.white),
                ),
                Text(
                  "$_displayName (${_role.toUpperCase()})",
                  style: const TextStyle(fontSize: 11, color: Colors.amberAccent),
                ),
              ],
            ),
          ],
        ),
        actions: [
          IconButton(
            tooltip: "Logout",
            icon: const Icon(Icons.logout, color: Colors.redAccent),
            onPressed: _logout,
          ),
        ],
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Container(
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
              decoration: BoxDecoration(
                color: const Color(0xFE1E293B),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: const Color(0xFF334155)),
              ),
              child: Row(
                children: [
                  const Icon(Icons.cloud_done, color: Colors.greenAccent, size: 20),
                  const SizedBox(width: 10),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: [
                        const Text(
                          "Live Cloud Server Connected",
                          style: TextStyle(fontSize: 12, fontWeight: FontWeight.bold, color: Colors.white),
                        ),
                        Text(
                          _activeServerUrl,
                          style: const TextStyle(fontSize: 11, color: Colors.white60),
                          overflow: TextOverflow.ellipsis,
                        ),
                      ],
                    ),
                  ),
                  TextButton.icon(
                    onPressed: () => _launchAdminRoute('/admin'),
                    icon: const Icon(Icons.open_in_browser, size: 16, color: Colors.cyanAccent),
                    label: const Text("Open Web", style: TextStyle(color: Colors.cyanAccent, fontSize: 12, fontWeight: FontWeight.bold)),
                  ),
                ],
              ),
            ),

            const SizedBox(height: 18),

            const Text(
              "Management & Operations",
              style: TextStyle(fontSize: 14, fontWeight: FontWeight.bold, color: Colors.white70),
            ),
            const SizedBox(height: 12),

            GridView.count(
              shrinkWrap: true,
              physics: const NeverScrollableScrollPhysics(),
              crossAxisCount: 2,
              mainAxisSpacing: 12,
              crossAxisSpacing: 12,
              childAspectRatio: 1.25,
              children: [
                _buildActionCard(
                  title: "POS Billing Terminal",
                  subtitle: "POS Sales Counter",
                  icon: Icons.point_of_sale,
                  color: const Color(0xFF16A34A),
                  onTap: () => _launchAdminRoute('/pos'),
                ),
                _buildActionCard(
                  title: "Combo Packages",
                  subtitle: "Combo & AI Collage",
                  icon: Icons.card_giftcard,
                  color: const Color(0xFF9333EA),
                  onTap: () => _launchAdminRoute('/packages'),
                ),
                _buildActionCard(
                  title: "Products & Stock",
                  subtitle: "Products & Inventory",
                  icon: Icons.inventory_2,
                  color: const Color(0xFF2563EB),
                  onTap: () => _launchAdminRoute('/products'),
                ),
                _buildActionCard(
                  title: "Online Orders",
                  subtitle: "Orders & Delivery",
                  icon: Icons.delivery_dining,
                  color: const Color(0xFFEA580C),
                  onTap: () => _launchAdminRoute('/orders'),
                ),
                _buildActionCard(
                  title: "Sales & Accounts",
                  subtitle: "Daily Sales & Profit",
                  icon: Icons.analytics,
                  color: const Color(0xFF0D9488),
                  onTap: () => _launchAdminRoute('/reports'),
                ),
                _buildActionCard(
                  title: "Store Settings",
                  subtitle: "System & App Config",
                  icon: Icons.settings,
                  color: const Color(0xFF475569),
                  onTap: () => _launchAdminRoute('/settings'),
                ),
              ],
            ),

            const SizedBox(height: 20),

            Container(
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: const Color(0xFE1E293B),
                borderRadius: BorderRadius.circular(14),
                border: Border.all(color: Colors.green.shade800),
              ),
              child: Row(
                children: [
                  Container(
                    padding: const EdgeInsets.all(10),
                    decoration: BoxDecoration(
                      color: Colors.green.withAlpha(50),
                      borderRadius: BorderRadius.circular(10),
                    ),
                    child: const Icon(Icons.storefront, color: Colors.greenAccent, size: 28),
                  ),
                  const SizedBox(width: 14),
                  Expanded(
                    child: Column(
                      crossAxisAlignment: CrossAxisAlignment.start,
                      children: const [
                        Text(
                          "Customer Storefront View",
                          style: TextStyle(fontSize: 14, fontWeight: FontWeight.bold, color: Colors.white),
                        ),
                        SizedBox(height: 2),
                        Text(
                          "View homescreen as a customer",
                          style: TextStyle(fontSize: 11.5, color: Colors.white60),
                        ),
                      ],
                    ),
                  ),
                  ElevatedButton(
                    onPressed: () {
                      Navigator.push(
                        context,
                        MaterialPageRoute(builder: (_) => const HomeScreen()),
                      );
                    },
                    style: ElevatedButton.styleFrom(
                      backgroundColor: Colors.green,
                      padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                    ),
                    child: const Text("View App", style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 13)),
                  ),
                ],
              ),
            ),

            const SizedBox(height: 24),
          ],
        ),
      ),
    );
  }

  Widget _buildActionCard({
    required String title,
    required String subtitle,
    required IconData icon,
    required Color color,
    required VoidCallback onTap,
  }) {
    return InkWell(
      onTap: onTap,
      borderRadius: BorderRadius.circular(14),
      child: Container(
        padding: const EdgeInsets.all(12),
        decoration: BoxDecoration(
          color: const Color(0xFE1E293B),
          borderRadius: BorderRadius.circular(14),
          border: Border.all(color: color.withAlpha(90), width: 1.5),
          boxShadow: [
            BoxShadow(
              color: color.withAlpha(30),
              blurRadius: 8,
              offset: const Offset(0, 4),
            ),
          ],
        ),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          mainAxisAlignment: MainAxisAlignment.spaceBetween,
          children: [
            Row(
              mainAxisAlignment: MainAxisAlignment.spaceBetween,
              children: [
                Container(
                  padding: const EdgeInsets.all(8),
                  decoration: BoxDecoration(
                    color: color.withAlpha(50),
                    borderRadius: BorderRadius.circular(8),
                  ),
                  child: Icon(icon, color: color, size: 22),
                ),
                Icon(Icons.arrow_forward, color: color, size: 16),
              ],
            ),
            Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  title,
                  style: const TextStyle(
                    fontSize: 13.5,
                    fontWeight: FontWeight.bold,
                    color: Colors.white,
                  ),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
                const SizedBox(height: 2),
                Text(
                  subtitle,
                  style: const TextStyle(
                    fontSize: 10.5,
                    color: Colors.white60,
                  ),
                  maxLines: 1,
                  overflow: TextOverflow.ellipsis,
                ),
              ],
            ),
          ],
        ),
      ),
    );
  }
}
