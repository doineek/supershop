import 'dart:convert';
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:image_picker/image_picker.dart';
import 'package:package_info_plus/package_info_plus.dart';
import 'package:provider/provider.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:url_launcher/url_launcher.dart';
import '../../providers/cart_provider.dart';
import '../../providers/locale_provider.dart';
import '../../providers/theme_provider.dart';
import '../../services/api_service.dart';
import '../../widgets/location_selector_dialog.dart';
import '../auth/login_screen.dart';
import '../admin/admin_hub_screen.dart';
import 'my_orders_screen.dart';

class ProfileScreen extends StatefulWidget {
  const ProfileScreen({Key? key}) : super(key: key);

  @override
  State<ProfileScreen> createState() => _ProfileScreenState();
}

class _ProfileScreenState extends State<ProfileScreen> {
  String _userName = '';
  String _userPhone = '';
  String _userEmail = '';
  String _userAvatar = '👤';
  String _userImageBase64 = '';
  String _supportPhone = '+880-1700-000000';
  String _shopName = 'DOINEEK';
  String _shopAddress = 'House 12, Road 5, Tangail';
  bool _isLoading = false;
  bool _isAdminMode = false;
  String _appVersion = '1.0.11';
  String _buildNumber = '12';

  final List<String> _presetAvatars = ['👤', '🧔', '👩', '🧑‍💼', '🐱', '🦊', '🚀', '💎', '👑', '🦸'];

  @override
  void initState() {
    super.initState();
    _loadLocalProfileImmediately();
    _loadProfileDataAsync();
    _loadAppVersion();
  }

  void _loadProfileData() {
    _loadLocalProfileImmediately();
    _loadProfileDataAsync();
    _loadAppVersion();
  }

  Future<void> _loadAppVersion() async {
    try {
      final info = await PackageInfo.fromPlatform();
      if (!mounted) return;
      setState(() {
        if (info.version.isNotEmpty) {
          _appVersion = info.version;
        }
        if (info.buildNumber.isNotEmpty) {
          _buildNumber = info.buildNumber;
        }
      });
    } catch (e) {
      debugPrint("Error loading package info: $e");
    }
  }

  String _getPlatformDisplayName() {
    if (kIsWeb) return 'Web Application';
    switch (defaultTargetPlatform) {
      case TargetPlatform.android:
        return 'Android Native (APK)';
      case TargetPlatform.iOS:
        return 'iOS App';
      case TargetPlatform.windows:
        return 'Windows App';
      case TargetPlatform.macOS:
        return 'macOS App';
      case TargetPlatform.linux:
        return 'Linux App';
      default:
        return 'Native App';
    }
  }

  void _loadLocalProfileImmediately() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      String userPhone = prefs.getString('user_phone') ?? '';
      String phoneImg = userPhone.isNotEmpty ? (prefs.getString('saved_img_$userPhone') ?? '') : '';
      String phoneAv = userPhone.isNotEmpty ? (prefs.getString('saved_av_$userPhone') ?? '') : '';
      String imgB64 = prefs.getString('user_image_base64') ?? phoneImg;
      String av = prefs.getString('user_avatar') ?? (phoneAv.isNotEmpty ? phoneAv : '👤');

      if (!mounted) return;
      setState(() {
        _isAdminMode = prefs.getBool('is_admin_mode') ?? false;
        _userName = prefs.getString('user_name') ?? 'Customer User';
        _userPhone = userPhone;
        _userEmail = prefs.getString('user_email') ?? '';
        _userAvatar = av;
        _userImageBase64 = imgB64;
      });
    } catch (_) {}
  }

  Future<void> _loadProfileDataAsync() async {
    try {
      final prefs = await SharedPreferences.getInstance();
      String userPhone = prefs.getString('user_phone') ?? '';
      String phoneImg = userPhone.isNotEmpty ? (prefs.getString('saved_img_$userPhone') ?? '') : '';
      String phoneAv = userPhone.isNotEmpty ? (prefs.getString('saved_av_$userPhone') ?? '') : '';
      String imgB64 = prefs.getString('user_image_base64') ?? phoneImg;
      String av = prefs.getString('user_avatar') ?? (phoneAv.isNotEmpty ? phoneAv : '👤');

      var settings = await ApiService.fetchShopSettings();

      if (!mounted) return;
      setState(() {
        _userName = prefs.getString('user_name') ?? 'Customer User';
        _userPhone = userPhone;
        _userEmail = prefs.getString('user_email') ?? '';
        _userAvatar = av;
        _userImageBase64 = imgB64;
        String supPhone = (settings['customer_support_phone'] ?? settings['shop_phone'] ?? '').toString();
        if (supPhone.isNotEmpty) {
          _supportPhone = supPhone;
        }
        _shopName = (settings['shop_name'] ?? _shopName).toString();
        _shopAddress = (settings['shop_address'] ?? _shopAddress).toString();
      });
    } catch (_) {}
  }

  Future<void> _pickImage(ImageSource source) async {
    final messenger = ScaffoldMessenger.of(context);
    try {
      final ImagePicker picker = ImagePicker();
      final XFile? image = await picker.pickImage(
        source: source,
        maxWidth: 800,
        maxHeight: 800,
        imageQuality: 85,
      );

      if (image != null) {
        final bytes = await image.readAsBytes();
        String base64String = 'data:image/png;base64,${base64Encode(bytes)}';

        final prefs = await SharedPreferences.getInstance();
        await prefs.setString('user_image_base64', base64String);
        await prefs.setString('user_avatar', '');
        if (_userPhone.isNotEmpty) {
          await prefs.setString('saved_img_$_userPhone', base64String);
          await prefs.remove('saved_av_$_userPhone');
          ApiService.httpPost('/api/customer/update-profile', body: jsonEncode({
            'phone': _userPhone,
            'name': _userName,
            'profile_image': base64String,
          }));
        }

        if (!mounted) return;
        setState(() {
          _userImageBase64 = base64String;
          _userAvatar = '';
        });

        messenger.showSnackBar(
          const SnackBar(
            content: Text("Profile photo uploaded successfully!"),
            backgroundColor: Colors.green,
          ),
        );
      }
    } catch (e) {
      debugPrint("Error picking image: $e");
    }
  }

  void _changeAvatarDialog() {
    showDialog(
      context: context,
      builder: (dialogCtx) => AlertDialog(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        title: const Row(
          children: [
            Icon(Icons.photo_camera, color: Colors.green),
            SizedBox(width: 8),
            Text("Profile Photo Options"),
          ],
        ),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              // Option 1: Gallery Pick
              SizedBox(
                width: double.infinity,
                height: 48,
                child: ElevatedButton.icon(
                  onPressed: () {
                    Navigator.pop(dialogCtx);
                    _pickImage(ImageSource.gallery);
                  },
                  icon: const Icon(Icons.photo_library, color: Colors.white),
                  label: const Text("Choose Photo from Mobile / PC", style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
                  style: ElevatedButton.styleFrom(backgroundColor: Colors.green),
                ),
              ),
              const SizedBox(height: 10),

              // Option 2: Camera Pick
              SizedBox(
                width: double.infinity,
                height: 48,
                child: OutlinedButton.icon(
                  onPressed: () {
                    Navigator.pop(dialogCtx);
                    _pickImage(ImageSource.camera);
                  },
                  icon: const Icon(Icons.camera_alt, color: Colors.green),
                  label: const Text("Take Photo with Camera", style: TextStyle(color: Colors.green, fontWeight: FontWeight.bold)),
                  style: OutlinedButton.styleFrom(side: const BorderSide(color: Colors.green)),
                ),
              ),

              const SizedBox(height: 16),
              const Divider(),
              const SizedBox(height: 8),
              const Text("Or Select a Default Avatar:", style: TextStyle(fontWeight: FontWeight.bold)),
              const SizedBox(height: 10),
              Wrap(
                spacing: 12,
                runSpacing: 12,
                children: _presetAvatars.map((av) {
                  bool isSelected = _userAvatar == av && _userImageBase64.isEmpty;
                  return InkWell(
                    onTap: () async {
                      final nav = Navigator.of(dialogCtx);
                      final prefs = await SharedPreferences.getInstance();
                      await prefs.setString('user_avatar', av);
                      await prefs.setString('user_image_base64', '');
                      if (_userPhone.isNotEmpty) {
                        await prefs.setString('saved_av_$_userPhone', av);
                        await prefs.remove('saved_img_$_userPhone');
                      }

                      setState(() {
                        _userAvatar = av;
                        _userImageBase64 = '';
                      });
                      nav.pop();
                    },
                    child: Container(
                      padding: const EdgeInsets.all(10),
                      decoration: BoxDecoration(
                        color: isSelected ? Colors.green.shade100 : Colors.grey.shade100,
                        border: Border.all(color: isSelected ? Colors.green : Colors.transparent, width: 2),
                        shape: BoxShape.circle,
                      ),
                      child: Text(av, style: const TextStyle(fontSize: 28)),
                    ),
                  );
                }).toList(),
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogCtx),
            child: const Text("Close"),
          ),
        ],
      ),
    );
  }

  void _editAddressDialog(CartProvider cartProv) {
    final TextEditingController addressCtrl = TextEditingController(text: cartProv.addressDetails);
    final messenger = ScaffoldMessenger.of(context);

    showDialog(
      context: context,
      builder: (dialogCtx) => AlertDialog(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        title: const Row(
          children: [
            Icon(Icons.edit_location_alt, color: Colors.green),
            SizedBox(width: 8),
            Text("Edit Default Delivery Address"),
          ],
        ),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: Colors.blue[50],
                  borderRadius: BorderRadius.circular(8),
                  border: Border.all(color: Colors.blue.shade200),
                ),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Expanded(
                      child: Text(
                        '${cartProv.selectedArea}, ${cartProv.selectedDistrict}, ${cartProv.selectedCountry}',
                        style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13, color: Colors.black87),
                      ),
                    ),
                    TextButton(
                      onPressed: () {
                        Navigator.pop(dialogCtx);
                        showDialog(
                          context: context,
                          builder: (_) => const LocationSelectorDialog(),
                        );
                      },
                      child: const Text("Change Area"),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 16),
              const Text("House / Road / Details Address:"),
              const SizedBox(height: 6),
              TextField(
                controller: addressCtrl,
                maxLines: 2,
                decoration: const InputDecoration(
                  hintText: "e.g. House 12, Road 5, Akur Takur Para",
                  border: OutlineInputBorder(),
                ),
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogCtx),
            child: const Text("Cancel"),
          ),
          ElevatedButton(
            onPressed: () async {
              String details = addressCtrl.text.trim();
              cartProv.setLocation(
                cartProv.selectedCountry,
                cartProv.selectedDistrict,
                cartProv.selectedArea,
                details: details,
              );

              final nav = Navigator.of(dialogCtx);
              final prefs = await SharedPreferences.getInstance();
              await prefs.setString('user_address', details);

              nav.pop();
              messenger.showSnackBar(
                const SnackBar(content: Text("Default delivery address updated successfully!"), backgroundColor: Colors.green),
              );
            },
            style: ElevatedButton.styleFrom(backgroundColor: Colors.green),
            child: const Text("Save Address", style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
          ),
        ],
      ),
    );
  }

  void _showCustomerSupportDialog() {
    showDialog(
      context: context,
      builder: (dialogCtx) => AlertDialog(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        title: const Row(
          children: [
            Icon(Icons.support_agent, color: Colors.purple, size: 28),
            SizedBox(width: 8),
            Text("Customer Support"),
          ],
        ),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text(_shopName, style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 16)),
            const SizedBox(height: 4),
            Text(_shopAddress, style: const TextStyle(color: Colors.grey, fontSize: 13)),
            const SizedBox(height: 16),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.all(16),
              decoration: BoxDecoration(
                color: Colors.purple.shade50,
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: Colors.purple.shade200),
              ),
              child: Column(
                children: [
                  const Text("Helpline Number:", style: TextStyle(fontSize: 13, fontWeight: FontWeight.bold, color: Colors.purple)),
                  const SizedBox(height: 6),
                  SelectableText(
                    _supportPhone,
                    style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold, color: Colors.purple),
                  ),
                  const SizedBox(height: 12),
                  SizedBox(
                    width: double.infinity,
                    height: 44,
                    child: ElevatedButton.icon(
                      onPressed: () async {
                        final cleanPhone = _supportPhone.replaceAll(RegExp(r'[^0-9+]'), '');
                        final Uri launchUri = Uri(scheme: 'tel', path: cleanPhone);
                        try {
                          if (await canLaunchUrl(launchUri)) {
                            await launchUrl(launchUri);
                          } else {
                            await launchUrl(launchUri, mode: LaunchMode.externalApplication);
                          }
                        } catch (e) {
                          debugPrint("Could not dial phone: $e");
                        }
                      },
                      icon: const Icon(Icons.phone, color: Colors.white, size: 20),
                      label: const Text("Call / Dial Now", style: TextStyle(fontWeight: FontWeight.bold, color: Colors.white, fontSize: 15)),
                      style: ElevatedButton.styleFrom(
                        backgroundColor: Colors.purple,
                        elevation: 0,
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                      ),
                    ),
                  ),
                  const SizedBox(height: 6),
                  const Text("Tap to call for order assistance & support", style: TextStyle(fontSize: 11, color: Colors.grey)),
                ],
              ),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogCtx),
            child: const Text("Close"),
          ),
        ],
      ),
    );
  }

  void _showAboutAppDialog() {
    showDialog(
      context: context,
      builder: (dialogCtx) => AlertDialog(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        title: const Row(
          children: [
            Icon(Icons.info_outline, color: Colors.teal, size: 28),
            SizedBox(width: 8),
            Text("About / App Version"),
          ],
        ),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.center,
          children: [
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: Colors.teal.shade50,
                shape: BoxShape.circle,
                border: Border.all(color: Colors.teal.shade200, width: 2),
              ),
              child: const Icon(Icons.shopping_bag, color: Colors.teal, size: 40),
            ),
            const SizedBox(height: 12),
            Text(_shopName, style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 18)),
            const SizedBox(height: 2),
            const Text("Online E-Commerce & Retail Supershop", style: TextStyle(color: Colors.grey, fontSize: 12)),
            const SizedBox(height: 14),
            Container(
              width: double.infinity,
              padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 12),
              decoration: BoxDecoration(
                color: const Color(0xFFF8FAFC),
                borderRadius: BorderRadius.circular(12),
                border: Border.all(color: const Color(0xFFE2E8F0)),
              ),
              child: Column(
                children: [
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      const Text("App Version:", style: TextStyle(color: Color(0xFF64748B), fontSize: 13, fontWeight: FontWeight.w600)),
                      Container(
                        padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 3),
                        decoration: BoxDecoration(
                          color: Colors.green.shade100,
                          borderRadius: BorderRadius.circular(10),
                          border: Border.all(color: Colors.green.shade300),
                        ),
                        child: Text(
                          _buildNumber.isNotEmpty
                              ? "v$_appVersion (Build $_buildNumber)"
                              : "v$_appVersion",
                          style: const TextStyle(color: Color(0xFF15803D), fontWeight: FontWeight.bold, fontSize: 12),
                        ),
                      ),
                    ],
                  ),
                  const SizedBox(height: 8),
                  const Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      Text("Release Status:", style: TextStyle(color: Color(0xFF64748B), fontSize: 13, fontWeight: FontWeight.w600)),
                      Text("Latest Official Release", style: TextStyle(fontWeight: FontWeight.bold, fontSize: 13, color: Color(0xFF0F172A))),
                    ],
                  ),
                  const SizedBox(height: 8),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      const Text("Platform:", style: TextStyle(color: Color(0xFF64748B), fontSize: 13, fontWeight: FontWeight.w600)),
                      Text(_getPlatformDisplayName(), style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13, color: Color(0xFF0F172A))),
                    ],
                  ),
                  const SizedBox(height: 8),
                  Row(
                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                    children: [
                      const Text("Customer Support:", style: TextStyle(color: Color(0xFF64748B), fontSize: 13, fontWeight: FontWeight.w600)),
                      Text(_supportPhone, style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13, color: Colors.teal)),
                    ],
                  ),
                ],
              ),
            ),
            const SizedBox(height: 16),
            SizedBox(
              width: double.infinity,
              height: 44,
              child: ElevatedButton.icon(
                onPressed: () async {
                  final Uri apkUri = Uri.parse('${ApiService.baseUrl}/download-apk');
                  try {
                    if (await canLaunchUrl(apkUri)) {
                      await launchUrl(apkUri, mode: LaunchMode.externalApplication);
                    }
                  } catch (e) {
                    debugPrint("Could not open APK URL: $e");
                  }
                },
                icon: const Icon(Icons.download_for_offline, color: Colors.white, size: 20),
                label: const Text("Download Latest APK Update", style: TextStyle(fontWeight: FontWeight.bold, color: Colors.white, fontSize: 14)),
                style: ElevatedButton.styleFrom(
                  backgroundColor: Colors.teal.shade700,
                  elevation: 0,
                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                ),
              ),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogCtx),
            child: const Text("Close"),
          ),
        ],
      ),
    );
  }

  void _showChangePasswordDialog() {
    final TextEditingController oldPassCtrl = TextEditingController();
    final TextEditingController newPassCtrl = TextEditingController();
    final TextEditingController confirmPassCtrl = TextEditingController();

    showDialog(
      context: context,
      builder: (dialogCtx) => AlertDialog(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        title: const Row(
          children: [
            Icon(Icons.key, color: Colors.blue),
            SizedBox(width: 8),
            Text("Change Password"),
          ],
        ),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              TextField(
                controller: oldPassCtrl,
                obscureText: true,
                decoration: const InputDecoration(
                  labelText: "Current Password",
                  prefixIcon: Icon(Icons.lock_outline),
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: newPassCtrl,
                obscureText: true,
                decoration: const InputDecoration(
                  labelText: "New Password",
                  prefixIcon: Icon(Icons.lock_reset),
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: confirmPassCtrl,
                obscureText: true,
                decoration: const InputDecoration(
                  labelText: "Confirm New Password",
                  prefixIcon: Icon(Icons.lock),
                  border: OutlineInputBorder(),
                ),
              ),
            ],
          ),
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogCtx),
            child: const Text("Cancel"),
          ),
          ElevatedButton(
            onPressed: () async {
              String oldPass = oldPassCtrl.text.trim();
              String newPass = newPassCtrl.text.trim();
              String confirmPass = confirmPassCtrl.text.trim();

              if (oldPass.isEmpty || newPass.isEmpty) {
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(content: Text("Please fill in all password fields"), backgroundColor: Colors.red),
                );
                return;
              }

              if (newPass.length < 4) {
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(content: Text("New password must be at least 4 characters long"), backgroundColor: Colors.red),
                );
                return;
              }

              if (newPass != confirmPass) {
                ScaffoldMessenger.of(context).showSnackBar(
                  const SnackBar(content: Text("New passwords do not match!"), backgroundColor: Colors.red),
                );
                return;
              }

              final nav = Navigator.of(dialogCtx);
              var res = await ApiService.changePassword(
                phone: _userPhone,
                oldPassword: oldPass,
                newPassword: newPass,
              );

              if (!mounted) return;

              if (res['success'] == true) {
                nav.pop();
                ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(content: Text(res['message'] ?? "Password updated successfully!"), backgroundColor: Colors.green),
                );
              } else {
                ScaffoldMessenger.of(context).showSnackBar(
                  SnackBar(content: Text(res['message'] ?? "Failed to update password."), backgroundColor: Colors.red),
                );
              }
            },
            style: ElevatedButton.styleFrom(backgroundColor: Colors.blue),
            child: const Text("Update Password", style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
          ),
        ],
      ),
    );
  }

  void _logout() async {
    final prefs = await SharedPreferences.getInstance();
    String savedImage = prefs.getString('user_image_base64') ?? '';
    String savedAvatar = prefs.getString('user_avatar') ?? '';

    if (_userPhone.isNotEmpty) {
      if (savedImage.isNotEmpty) await prefs.setString('saved_img_$_userPhone', savedImage);
      if (savedAvatar.isNotEmpty) await prefs.setString('saved_av_$_userPhone', savedAvatar);
    }

    await prefs.remove('is_logged_in');
    await prefs.remove('auth_token');
    await prefs.remove('user_name');
    await prefs.remove('user_phone');
    await prefs.remove('user_email');
    await prefs.remove('customer_id');

    if (!mounted) return;
    Navigator.pushAndRemoveUntil(
      context,
      MaterialPageRoute(builder: (_) => const LoginScreen()),
      (route) => false,
    );
  }

  ImageProvider? _getProfileImageProvider() {
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
        debugPrint("Error decoding profile image: $e");
      }
    }
    return null;
  }

  @override
  Widget build(BuildContext context) {
    final localeProv = Provider.of<LocaleProvider>(context);
    final themeProv = Provider.of<ThemeProvider>(context);
    final cartProv = Provider.of<CartProvider>(context);

    String fullAddress = cartProv.addressDetails.isNotEmpty
        ? '${cartProv.addressDetails}, ${cartProv.selectedArea}, ${cartProv.selectedDistrict}'
        : '${cartProv.selectedArea}, ${cartProv.selectedDistrict}, ${cartProv.selectedCountry}';

    ImageProvider? imageProvider = _getProfileImageProvider();

    return Scaffold(
      appBar: AppBar(
        title: const Text('My Profile'),
        backgroundColor: Colors.green,
      ),
      body: RefreshIndicator(
        onRefresh: () => _loadProfileDataAsync(),
        child: SingleChildScrollView(
          physics: const AlwaysScrollableScrollPhysics(),
          padding: const EdgeInsets.all(16.0),
              child: Column(
                children: [
                  if (_userPhone.isEmpty)
                    Card(
                      elevation: 3,
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
                      child: Padding(
                        padding: const EdgeInsets.all(20.0),
                        child: Column(
                          children: [
                            const Icon(Icons.account_circle, size: 64, color: Colors.green),
                            const SizedBox(height: 10),
                            const Text(
                              "Welcome Guest Customer!",
                              style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold),
                            ),
                            const SizedBox(height: 6),
                            const Text(
                              "Sign in or register an account to view your orders, save delivery address, and place orders smoothly.",
                              textAlign: TextAlign.center,
                              style: TextStyle(color: Colors.grey, fontSize: 13),
                            ),
                            const SizedBox(height: 16),
                            SizedBox(
                              width: double.infinity,
                              height: 44,
                              child: ElevatedButton.icon(
                                onPressed: () async {
                                  await Navigator.push(
                                    context,
                                    MaterialPageRoute(builder: (_) => const LoginScreen()),
                                  );
                                  _loadProfileData();
                                },
                                icon: const Icon(Icons.login, color: Colors.white),
                                label: const Text("Sign In / Register Now", style: TextStyle(fontWeight: FontWeight.bold, color: Colors.white)),
                                style: ElevatedButton.styleFrom(backgroundColor: Colors.green),
                              ),
                            ),
                          ],
                        ),
                      ),
                    )
                  else
                    Card(
                      elevation: 3,
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
                      child: Padding(
                        padding: const EdgeInsets.all(20.0),
                        child: Row(
                          children: [
                            Stack(
                              children: [
                                GestureDetector(
                                  onTap: _changeAvatarDialog,
                                  child: CircleAvatar(
                                    radius: 38,
                                    backgroundColor: Colors.green.shade100,
                                    backgroundImage: imageProvider,
                                    child: imageProvider == null
                                        ? Text(_userAvatar, style: const TextStyle(fontSize: 36))
                                        : null,
                                  ),
                                ),
                                Positioned(
                                  bottom: 0,
                                  right: 0,
                                  child: GestureDetector(
                                    onTap: _changeAvatarDialog,
                                    child: Container(
                                      padding: const EdgeInsets.all(4),
                                      decoration: const BoxDecoration(
                                        color: Colors.green,
                                        shape: BoxShape.circle,
                                      ),
                                      child: const Icon(Icons.camera_alt, color: Colors.white, size: 14),
                                    ),
                                  ),
                                ),
                              ],
                            ),
                            const SizedBox(width: 16),
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Text(
                                    _userName.isNotEmpty ? _userName : 'Customer User',
                                    style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
                                  ),
                                  const SizedBox(height: 4),
                                  Text(_userPhone, style: const TextStyle(color: Colors.blue, fontWeight: FontWeight.w600)),
                                  if (_userEmail.isNotEmpty)
                                    Text(_userEmail, style: const TextStyle(color: Colors.grey, fontSize: 13)),
                                ],
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                  const SizedBox(height: 16),

                  // Location & Default Delivery Address Card (Clean: Exactly 1 icon)
                  Card(
                    elevation: 2,
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                    child: ListTile(
                      leading: const Icon(Icons.location_on, color: Colors.red, size: 28),
                      title: const Text('Default Delivery Address', style: TextStyle(fontWeight: FontWeight.bold)),
                      subtitle: Text(fullAddress, style: const TextStyle(fontSize: 13)),
                      trailing: TextButton(
                        onPressed: () => _editAddressDialog(cartProv),
                        child: const Text('Change'),
                      ),
                    ),
                  ),
                  const SizedBox(height: 16),

                  if (_isAdminMode) ...[
                    Card(
                      elevation: 3,
                      shape: RoundedRectangleBorder(
                        borderRadius: BorderRadius.circular(12),
                        side: const BorderSide(color: Colors.amber, width: 1.5),
                      ),
                      color: const Color(0xFF1E293B),
                      child: ListTile(
                        leading: const Icon(Icons.shield, color: Colors.amber, size: 28),
                        title: const Text(
                          'Admin & Cashier Workspace',
                          style: TextStyle(fontWeight: FontWeight.bold, color: Colors.white),
                        ),
                        subtitle: const Text(
                          'Products, Packages, Cashier POS & Sales Reports',
                          style: TextStyle(color: Colors.white70, fontSize: 12),
                        ),
                        trailing: const Icon(Icons.arrow_forward_ios, color: Colors.amber, size: 16),
                        onTap: () {
                          Navigator.push(
                            context,
                            MaterialPageRoute(builder: (_) => const AdminHubScreen()),
                          );
                        },
                      ),
                    ),
                    const SizedBox(height: 16),
                  ],

                  // Settings & Navigation Options List (Clean: Exactly 1 icon per item)
                  Card(
                    elevation: 2,
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
                    child: Column(
                      children: [
                        ListTile(
                          leading: const Icon(Icons.receipt_long, color: Colors.green),
                          title: const Text('Order History', style: TextStyle(fontWeight: FontWeight.w600)),
                          subtitle: const Text('View previous purchases'),
                          onTap: () {
                            Navigator.push(
                              context,
                              MaterialPageRoute(builder: (_) => const MyOrdersScreen()),
                            );
                          },
                        ),
                        const Divider(height: 1),
                        ListTile(
                          leading: const Icon(Icons.key, color: Colors.blue),
                          title: const Text('Change Password', style: TextStyle(fontWeight: FontWeight.w600)),
                          subtitle: const Text('Update your account security password'),
                          onTap: _showChangePasswordDialog,
                        ),
                        const Divider(height: 1),
                        SwitchListTile(
                          secondary: Icon(
                            themeProv.isDarkMode ? Icons.dark_mode : Icons.light_mode,
                            color: themeProv.isDarkMode ? Colors.yellow : Colors.orange,
                          ),
                          title: const Text('App Dark Mode', style: TextStyle(fontWeight: FontWeight.w600)),
                          subtitle: Text(themeProv.isDarkMode ? 'Dark theme active' : 'Light theme active'),
                          value: themeProv.isDarkMode,
                          activeThumbColor: Colors.green,
                          onChanged: (val) {
                            themeProv.toggleTheme(val);
                          },
                        ),

                        const Divider(height: 1),
                        ListTile(
                          leading: const Icon(Icons.support_agent, color: Colors.purple),
                          title: const Text('Customer Support', style: TextStyle(fontWeight: FontWeight.w600)),
                          subtitle: Text(_supportPhone.isNotEmpty ? 'Helpline: $_supportPhone' : 'Help & Helpline'),
                          onTap: _showCustomerSupportDialog,
                        ),
                        const Divider(height: 1),
                        ListTile(
                          leading: const Icon(Icons.info_outline, color: Colors.teal),
                          title: const Text('About / App Version', style: TextStyle(fontWeight: FontWeight.w600)),
                          subtitle: Text(
                            _buildNumber.isNotEmpty
                                ? 'Version $_appVersion (Build $_buildNumber) • Official Release'
                                : 'Version $_appVersion • Official Release',
                          ),
                          trailing: Container(
                            padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                            decoration: BoxDecoration(
                              color: Colors.teal.shade50,
                              borderRadius: BorderRadius.circular(8),
                              border: Border.all(color: Colors.teal.shade200),
                            ),
                            child: Text(
                              'v$_appVersion',
                              style: const TextStyle(fontSize: 12, fontWeight: FontWeight.bold, color: Colors.teal),
                            ),
                          ),
                          onTap: _showAboutAppDialog,
                        ),
                      ],
                    ),
                  ),
                  const SizedBox(height: 24),

                  if (_userPhone.isNotEmpty) ...[
                    SizedBox(
                      width: double.infinity,
                      height: 50,
                      child: ElevatedButton.icon(
                        onPressed: () {
                          showDialog(
                            context: context,
                            builder: (ctx) => AlertDialog(
                              title: const Text('Confirm Logout'),
                              content: const Text('Are you sure you want to log out?'),
                              actions: [
                                TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('Cancel')),
                                ElevatedButton(
                                  onPressed: () {
                                    Navigator.pop(ctx);
                                    _logout();
                                  },
                                  style: ElevatedButton.styleFrom(backgroundColor: Colors.red),
                                  child: const Text('Log Out', style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
                                ),
                              ],
                            ),
                          );
                        },
                        icon: const Icon(Icons.logout, color: Colors.white),
                        label: const Text('Log Out', style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: Colors.white)),
                        style: ElevatedButton.styleFrom(backgroundColor: Colors.red),
                      ),
                    ),
                  ],
                ],
              ),
            ),
        ),
    );
  }
}
