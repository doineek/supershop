import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../../localization/app_localizations.dart';
import '../../services/api_service.dart';
import '../../services/firebase_auth_service.dart';
import '../customer/home_screen.dart';
import '../delivery/delivery_home_screen.dart';
import 'register_screen.dart';

class LoginScreen extends StatefulWidget {
  final String? initialPhone;
  const LoginScreen({Key? key, this.initialPhone}) : super(key: key);

  @override
  State<LoginScreen> createState() => _LoginScreenState();
}

class _LoginScreenState extends State<LoginScreen> {
  late TextEditingController _phoneController;
  final TextEditingController _passwordController = TextEditingController();
  bool _isDeliveryMan = false;
  String _shopName = "DOINEEK";
  bool _isLoading = false;
  bool _obscurePassword = true;
  bool _staySignedIn = true;

  @override
  void initState() {
    super.initState();
    _phoneController = TextEditingController(text: widget.initialPhone ?? '');
    _loadShopName();
    _checkAutoLogin();
  }

  void _checkAutoLogin() async {
    final prefs = await SharedPreferences.getInstance();
    bool staySignedIn = prefs.getBool('stay_signed_in') ?? true;
    String userPhone = prefs.getString('user_phone') ?? '';
    bool isDelivery = prefs.getBool('is_delivery_man') ?? false;

    if (staySignedIn && userPhone.isNotEmpty) {
      if (!mounted) return;
      if (isDelivery) {
        Navigator.pushReplacement(
          context,
          MaterialPageRoute(builder: (_) => const DeliveryHomeScreen()),
        );
      } else {
        Navigator.pushReplacement(
          context,
          MaterialPageRoute(builder: (_) => const HomeScreen()),
        );
      }
    }
  }

  void _loadShopName() async {
    var settings = await ApiService.fetchShopSettings();
    if (!mounted) return;
    setState(() {
      _shopName = settings['shop_name'] ?? "DOINEEK";
    });
  }

  void _openForgotPasswordDialog() {
    final TextEditingController recoveryPhoneCtrl = TextEditingController(text: _phoneController.text.trim());
    final TextEditingController otpInputCtrl = TextEditingController();
    final TextEditingController newPassCtrl = TextEditingController();
    final TextEditingController confirmPassCtrl = TextEditingController();

    int otpStep = 1; // 1: Enter Phone, 2: Enter OTP, 3: Enter New Password
    String verificationId = "";
    bool isFirebaseNative = false;

    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (dialogCtx) => StatefulBuilder(
        builder: (context, setDialogState) {
          return AlertDialog(
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
            title: Row(
              children: [
                Icon(
                  otpStep == 3 ? Icons.check_circle : (otpStep == 2 ? Icons.sms : Icons.lock_reset),
                  color: Colors.green,
                ),
                const SizedBox(width: 8),
                Text(
                  otpStep == 1
                      ? "Forgot Password Recovery"
                      : (otpStep == 2 ? "Firebase Phone Verification" : "Set New Password"),
                ),
              ],
            ),
            content: SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  if (otpStep == 1) ...[
                    const Text("Enter your registered 11-digit mobile number:"),
                    const SizedBox(height: 12),
                    TextField(
                      controller: recoveryPhoneCtrl,
                      keyboardType: TextInputType.phone,
                      decoration: const InputDecoration(
                        labelText: "Registered Mobile Number",
                        prefixIcon: Icon(Icons.phone),
                        border: OutlineInputBorder(),
                      ),
                    ),
                  ] else if (otpStep == 2) ...[
                    Text("Mobile Number: ${recoveryPhoneCtrl.text.trim()}", style: const TextStyle(fontWeight: FontWeight.bold)),
                    const SizedBox(height: 10),
                    Container(
                      padding: const EdgeInsets.all(12),
                      decoration: BoxDecoration(
                        color: Colors.green.shade50,
                        borderRadius: BorderRadius.circular(8),
                        border: Border.all(color: Colors.green.shade200),
                      ),
                      child: const Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            children: [
                              Icon(Icons.mark_email_read, color: Colors.green, size: 20),
                              SizedBox(width: 6),
                              Text(
                                "Firebase SMS OTP Dispatched",
                                style: TextStyle(fontWeight: FontWeight.bold, fontSize: 13, color: Colors.green),
                              ),
                            ],
                          ),
                          SizedBox(height: 6),
                          Text(
                            "An OTP verification code was sent to your phone. Please check your SMS inbox or WhatsApp.",
                            style: TextStyle(fontSize: 12, color: Colors.black87),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 14),
                    const Text("Enter OTP verification code below:"),
                    const SizedBox(height: 8),
                    TextField(
                      controller: otpInputCtrl,
                      keyboardType: TextInputType.number,
                      maxLength: 6,
                      textAlign: TextAlign.center,
                      style: const TextStyle(fontSize: 22, fontWeight: FontWeight.bold, letterSpacing: 4),
                      decoration: const InputDecoration(
                        hintText: "______",
                        border: OutlineInputBorder(),
                      ),
                    ),
                  ] else if (otpStep == 3) ...[
                    Container(
                      padding: const EdgeInsets.all(10),
                      decoration: BoxDecoration(
                        color: Colors.green.shade50,
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: const Row(
                        children: [
                          Icon(Icons.verified, color: Colors.green),
                          SizedBox(width: 8),
                          Expanded(
                            child: Text(
                              "OTP verified successfully! Set your new account password.",
                              style: TextStyle(fontSize: 13, fontWeight: FontWeight.bold, color: Colors.green),
                            ),
                          ),
                        ],
                      ),
                    ),
                    const SizedBox(height: 14),
                    TextField(
                      controller: newPassCtrl,
                      obscureText: true,
                      decoration: const InputDecoration(
                        labelText: "New Password",
                        prefixIcon: Icon(Icons.lock_outline),
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
                ],
              ),
            ),
            actions: [
              TextButton(
                onPressed: () => Navigator.pop(dialogCtx),
                child: const Text("Cancel"),
              ),
              if (otpStep == 1)
                ElevatedButton(
                  onPressed: () async {
                    String phone = recoveryPhoneCtrl.text.trim();
                    if (phone.length != 11 || !phone.startsWith('01') || int.tryParse(phone) == null) {
                      ScaffoldMessenger.of(dialogCtx).showSnackBar(
                        const SnackBar(content: Text("Mobile number must be exactly 11 digits starting with '01'"), backgroundColor: Colors.red),
                      );
                      return;
                    }

                    await FirebaseAuthService.sendFirebasePhoneOtp(
                      rawPhone: phone,
                      purpose: 'forgot_password',
                      onCodeSent: (vId, isNative) {
                        setDialogState(() {
                          verificationId = vId;
                          isFirebaseNative = isNative;
                          otpStep = 2;
                        });
                        if (dialogCtx.mounted) {
                          ScaffoldMessenger.of(dialogCtx).showSnackBar(
                            const SnackBar(content: Text("Firebase SMS OTP sent to your mobile number. Check your SMS inbox."), backgroundColor: Colors.green),
                          );
                        }
                      },
                      onError: (err) {
                        if (dialogCtx.mounted) {
                          ScaffoldMessenger.of(dialogCtx).showSnackBar(
                            SnackBar(content: Text(err), backgroundColor: Colors.red),
                          );
                        }
                      },
                    );
                  },
                  style: ElevatedButton.styleFrom(backgroundColor: Colors.green),
                  child: const Text("Send Free Firebase OTP", style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
                )
              else if (otpStep == 2)
                ElevatedButton(
                  onPressed: () async {
                    String phone = recoveryPhoneCtrl.text.trim();
                    String otp = otpInputCtrl.text.trim();
                    if (otp.length < 4) {
                      ScaffoldMessenger.of(dialogCtx).showSnackBar(
                        const SnackBar(content: Text("Please enter valid OTP code"), backgroundColor: Colors.red),
                      );
                      return;
                    }

                    var res = await FirebaseAuthService.verifyFirebasePhoneOtp(
                      rawPhone: phone,
                      verificationId: verificationId,
                      smsCode: otp,
                      isFirebaseNative: isFirebaseNative,
                    );

                    if (res['success'] == true) {
                      setDialogState(() {
                        otpStep = 3;
                      });
                    } else {
                      if (dialogCtx.mounted) {
                        ScaffoldMessenger.of(dialogCtx).showSnackBar(
                          SnackBar(content: Text(res['message'] ?? "Invalid OTP code. Please try again."), backgroundColor: Colors.red),
                        );
                      }
                    }
                  },
                  style: ElevatedButton.styleFrom(backgroundColor: Colors.green),
                  child: const Text("Verify OTP", style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
                )
              else if (otpStep == 3)
                ElevatedButton(
                  onPressed: () async {
                    String phone = recoveryPhoneCtrl.text.trim();
                    String newPass = newPassCtrl.text.trim();
                    String confirmPass = confirmPassCtrl.text.trim();

                    if (newPass.isEmpty || newPass.length < 4) {
                      ScaffoldMessenger.of(dialogCtx).showSnackBar(
                        const SnackBar(content: Text("Password must be at least 4 characters long"), backgroundColor: Colors.red),
                      );
                      return;
                    }

                    if (newPass != confirmPass) {
                      ScaffoldMessenger.of(dialogCtx).showSnackBar(
                        const SnackBar(content: Text("New passwords do not match!"), backgroundColor: Colors.red),
                      );
                      return;
                    }

                    final nav = Navigator.of(dialogCtx);
                    var res = await ApiService.resetForgotPassword(phone: phone, newPassword: newPass);

                    if (res['success'] == true) {
                      nav.pop();
                    } else {
                      if (!dialogCtx.mounted) return;
                      showDialog(
                        context: dialogCtx,
                        builder: (errCtx) => AlertDialog(
                          title: const Text("Password Reset Failed"),
                          content: Text(res['message'] ?? "Could not update password. Please try again."),
                          actions: [
                            TextButton(onPressed: () => Navigator.pop(errCtx), child: const Text("OK")),
                          ],
                        ),
                      );
                    }
                  },
                  style: ElevatedButton.styleFrom(backgroundColor: Colors.green),
                  child: const Text("Reset & Save Password", style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
                ),
            ],
          );
        },
      ),
    );
  }

  void _login() async {
    String phone = _phoneController.text.trim();
    String password = _passwordController.text.trim();

    if (phone.isEmpty || password.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text("Please enter your mobile number and password")),
      );
      return;
    }

    if (!_isDeliveryMan) {
      phone = phone.replaceAll(RegExp(r'\D'), '');
      if (phone.startsWith('8801')) {
        phone = phone.substring(2);
      }
      if (phone.length != 11 || !phone.startsWith('01') || int.tryParse(phone) == null) {
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(
            content: Text("Mobile number must start with '01' and be exactly 11 digits (e.g. 01712345678)"),
            backgroundColor: Colors.red,
          ),
        );
        return;
      }
    }

    setState(() {
      _isLoading = true;
    });

    var res = await ApiService.login(
      phone: phone,
      password: password,
      isDeliveryMan: _isDeliveryMan,
    );

    if (!mounted) return;

    setState(() {
      _isLoading = false;
    });

    if (res['success'] == true) {
      var user = res['user'] ?? {};
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString('user_phone', user['phone'] ?? phone);
      await prefs.setString('user_name', user['name'] ?? (_isDeliveryMan ? 'Delivery Rider' : 'Customer User'));
      await prefs.setString('user_email', user['email'] ?? '');
      await prefs.setBool('is_delivery_man', _isDeliveryMan);
      await prefs.setBool('stay_signed_in', _staySignedIn);

      if (!mounted) return;

      if (_isDeliveryMan) {
        Navigator.pushReplacement(
          context,
          MaterialPageRoute(builder: (_) => const DeliveryHomeScreen()),
        );
      } else {
        Navigator.pushReplacement(
          context,
          MaterialPageRoute(builder: (_) => const HomeScreen()),
        );
      }
    } else {
      showDialog(
        context: context,
        builder: (ctx) => AlertDialog(
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
          title: const Row(
            children: [
              Icon(Icons.error_outline, color: Colors.red),
              SizedBox(width: 8),
              Text("Login Failed"),
            ],
          ),
          content: Text(res['message'] ?? "Invalid mobile number or password."),
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
  Widget build(BuildContext context) {
    final loc = AppLocalizations.of(context);

    return Scaffold(
      backgroundColor: Colors.grey[100],
      body: SafeArea(
        child: Stack(
          children: [
            // Top Left Corner Browse App Button
            Positioned(
              top: 12,
              left: 12,
              child: TextButton.icon(
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
                icon: const Icon(Icons.arrow_back, size: 18, color: Colors.green),
                label: const Text("Browse App", style: TextStyle(color: Colors.green, fontWeight: FontWeight.bold, fontSize: 13)),
              ),
            ),

            // Top Right Corner Rider Mode Button
            Positioned(
              top: 12,
              right: 12,
              child: InkWell(
                onTap: () {
                  setState(() {
                    _isDeliveryMan = !_isDeliveryMan;
                  });
                },
                child: AnimatedContainer(
                  duration: const Duration(milliseconds: 200),
                  padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 8),
                  decoration: BoxDecoration(
                    color: _isDeliveryMan ? Colors.orange.shade700 : Colors.white,
                    borderRadius: BorderRadius.circular(20),
                    border: Border.all(
                      color: _isDeliveryMan ? Colors.orange.shade800 : Colors.grey.shade400,
                      width: 1.5,
                    ),
                    boxShadow: [
                      BoxShadow(
                        color: _isDeliveryMan ? Colors.orange.withAlpha(76) : Colors.black12,
                        blurRadius: 6,
                        offset: const Offset(0, 3),
                      ),
                    ],
                  ),
                  child: Row(
                    mainAxisSize: MainAxisSize.min,
                    children: [
                      Icon(
                        Icons.two_wheeler,
                        size: 20,
                        color: _isDeliveryMan ? Colors.white : Colors.orange.shade800,
                      ),
                      const SizedBox(width: 6),
                      Text(
                        _isDeliveryMan ? "Rider Mode (ACTIVE)" : "Rider Mode",
                        style: TextStyle(
                          fontSize: 13,
                          fontWeight: FontWeight.bold,
                          color: _isDeliveryMan ? Colors.white : Colors.black87,
                        ),
                      ),
                    ],
                  ),
                ),
              ),
            ),

            Center(
              child: SingleChildScrollView(
                padding: const EdgeInsets.all(24.0),
                child: Column(
                  mainAxisAlignment: MainAxisAlignment.center,
                  children: [
                    const SizedBox(height: 20),
                    // Website Brand Logo Image with Crisp White Background Badge
                    Container(
                      padding: const EdgeInsets.symmetric(horizontal: 20, vertical: 12),
                      decoration: BoxDecoration(
                        color: Colors.white,
                        borderRadius: BorderRadius.circular(16),
                        boxShadow: const [
                          BoxShadow(color: Colors.black12, blurRadius: 8, offset: Offset(0, 3)),
                        ],
                      ),
                      child: Image.asset(
                        'assets/images/logo.png',
                        height: 140,
                        fit: BoxFit.contain,
                        errorBuilder: (_, __, ___) => const Icon(Icons.shopping_bag, size: 90, color: Color(0xFF6B21A8)),
                      ),
                    ),
                    const SizedBox(height: 12),

                    // Website Shop Name
                    Text(
                      _shopName,
                      style: const TextStyle(fontSize: 26, fontWeight: FontWeight.bold, color: Colors.green),
                    ),
                    const SizedBox(height: 6),
                    const Text("Supershop Real-time E-Commerce Store", style: TextStyle(color: Colors.grey)),
                    const SizedBox(height: 24),

                    Card(
                      elevation: 4,
                      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
                      child: Padding(
                        padding: const EdgeInsets.all(20.0),
                        child: Column(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            Row(
                              mainAxisAlignment: MainAxisAlignment.spaceBetween,
                              children: [
                                Text(
                                  _isDeliveryMan ? "Rider Login" : loc.translate('login'),
                                  style: const TextStyle(fontSize: 20, fontWeight: FontWeight.bold),
                                ),
                                if (_isDeliveryMan)
                                  Container(
                                    padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 4),
                                    decoration: BoxDecoration(
                                      color: Colors.orange.shade100,
                                      borderRadius: BorderRadius.circular(12),
                                    ),
                                    child: const Row(
                                      children: [
                                        Icon(Icons.two_wheeler, size: 14, color: Colors.deepOrange),
                                        SizedBox(width: 4),
                                        Text(
                                          "Delivery Rider",
                                          style: TextStyle(fontSize: 11, fontWeight: FontWeight.bold, color: Colors.deepOrange),
                                        ),
                                      ],
                                    ),
                                  ),
                              ],
                            ),
                            const SizedBox(height: 20),

                             TextField(
                              controller: _phoneController,
                              keyboardType: TextInputType.phone,
                              maxLength: 11,
                              inputFormatters: [
                                FilteringTextInputFormatter.digitsOnly,
                                LengthLimitingTextInputFormatter(11),
                              ],
                              decoration: InputDecoration(
                                labelText: _isDeliveryMan ? "Rider Mobile Number" : loc.translate('phone_number'),
                                prefixIcon: Icon(_isDeliveryMan ? Icons.badge : Icons.phone),
                                border: const OutlineInputBorder(),
                                counterText: "",
                              ),
                            ),
                            const SizedBox(height: 14),

                            TextField(
                              controller: _passwordController,
                              obscureText: _obscurePassword,
                              decoration: InputDecoration(
                                labelText: loc.translate('password'),
                                prefixIcon: const Icon(Icons.lock),
                                suffixIcon: IconButton(
                                  icon: Icon(_obscurePassword ? Icons.visibility_off : Icons.visibility),
                                  onPressed: () {
                                    setState(() {
                                      _obscurePassword = !_obscurePassword;
                                    });
                                  },
                                ),
                                border: const OutlineInputBorder(),
                              ),
                            ),

                            const SizedBox(height: 6),

                            Row(
                              mainAxisAlignment: MainAxisAlignment.spaceBetween,
                              children: [
                                Row(
                                  children: [
                                    Checkbox(
                                      value: _staySignedIn,
                                      activeColor: Colors.green,
                                      onChanged: (val) {
                                        setState(() {
                                          _staySignedIn = val ?? true;
                                        });
                                      },
                                    ),
                                    const Text("Stay Signed In", style: TextStyle(fontSize: 13, fontWeight: FontWeight.w600)),
                                  ],
                                ),
                                if (!_isDeliveryMan)
                                  TextButton(
                                    onPressed: _openForgotPasswordDialog,
                                    child: const Text(
                                      "Forgot Password?",
                                      style: TextStyle(fontSize: 12, color: Colors.red, fontWeight: FontWeight.bold),
                                    ),
                                  ),
                              ],
                            ),

                            const SizedBox(height: 16),

                            SizedBox(
                              width: double.infinity,
                              height: 48,
                              child: ElevatedButton(
                                onPressed: _isLoading ? null : _login,
                                style: ElevatedButton.styleFrom(
                                  backgroundColor: _isDeliveryMan ? Colors.orange.shade800 : Colors.green,
                                  shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                                ),
                                child: _isLoading
                                    ? const SizedBox(height: 24, width: 24, child: CircularProgressIndicator(color: Colors.white, strokeWidth: 2))
                                    : Text(
                                        _isDeliveryMan ? "Rider Login" : loc.translate('login'),
                                        style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: Colors.white),
                                      ),
                              ),
                            ),
                          ],
                        ),
                      ),
                    ),
                    const SizedBox(height: 12),

                    if (!_isDeliveryMan) ...[
                      Row(
                        mainAxisAlignment: MainAxisAlignment.spaceBetween,
                        children: [
                          TextButton(
                            onPressed: () {
                              Navigator.push(
                                context,
                                MaterialPageRoute(builder: (_) => const RegisterScreen()),
                              );
                            },
                            child: Text(loc.translate('register')),
                          ),
                          TextButton.icon(
                            onPressed: _openAdminLoginDialog,
                            icon: const Icon(Icons.admin_panel_settings, size: 16, color: Color(0xFF1E293B)),
                            label: const Text(
                              "🔑 Admin & Cashier Mode ➔",
                              style: TextStyle(
                                fontSize: 12,
                                fontWeight: FontWeight.bold,
                                color: Color(0xFF1E293B),
                              ),
                            ),
                          ),
                        ],
                      ),
                    ],
                  ],
                ),
              ),
            ),
          ],
        ),
      ),
    );
  }

  void _openAdminLoginDialog() {
    final TextEditingController adminUserCtrl = TextEditingController();
    final TextEditingController adminPassCtrl = TextEditingController();
    bool isLoggingIn = false;

    showDialog(
      context: context,
      builder: (dialogCtx) => StatefulBuilder(
        builder: (ctx, setDialogState) => AlertDialog(
          shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
          title: const Row(
            children: [
              Icon(Icons.shield_outlined, color: Color(0xFF1E293B)),
              SizedBox(width: 8),
              Text("Admin & Cashier Sign In", style: TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
            ],
          ),
          content: Column(
            mainAxisSize: MainAxisSize.min,
            children: [
              TextField(
                controller: adminUserCtrl,
                decoration: const InputDecoration(
                  labelText: "Admin / Cashier Username",
                  prefixIcon: Icon(Icons.person),
                  border: OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 12),
              TextField(
                controller: adminPassCtrl,
                obscureText: true,
                decoration: const InputDecoration(
                  labelText: "Password",
                  prefixIcon: Icon(Icons.lock),
                  border: OutlineInputBorder(),
                ),
              ),
            ],
          ),
          actions: [
            TextButton(
              onPressed: () => Navigator.pop(ctx),
              child: const Text("Cancel"),
            ),
            ElevatedButton(
              onPressed: isLoggingIn
                  ? null
                  : () async {
                      final u = adminUserCtrl.text.trim();
                      final p = adminPassCtrl.text.trim();
                      if (u.isEmpty || p.isEmpty) return;

                      setDialogState(() => isLoggingIn = true);
                      final res = await ApiService.login(phone: u, password: p, isDeliveryMan: false);
                      setDialogState(() => isLoggingIn = false);

                      if (res['success'] == true) {
                        Navigator.pop(ctx);
                        final prefs = await SharedPreferences.getInstance();
                        await prefs.setString('user_phone', u);
                        await prefs.setString('user_name', res['user']?['name'] ?? u);
                        await prefs.setBool('is_admin_mode', true);
                        if (!mounted) return;
                        Navigator.pushReplacement(
                          context,
                          MaterialPageRoute(builder: (_) => const HomeScreen()),
                        );
                      } else {
                        ScaffoldMessenger.of(context).showSnackBar(
                          SnackBar(content: Text(res['message'] ?? "Invalid admin/cashier credentials"), backgroundColor: Colors.red),
                        );
                      }
                    },
              style: ElevatedButton.styleFrom(backgroundColor: const Color(0xFF1E293B)),
              child: const Text("Sign In", style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
            ),
          ],
        ),
      ),
    );
  }
}
