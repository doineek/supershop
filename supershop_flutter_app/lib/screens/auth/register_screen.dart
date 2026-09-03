import 'package:flutter/material.dart';
import 'package:flutter/services.dart';
import 'package:shared_preferences/shared_preferences.dart';
import 'package:url_launcher/url_launcher.dart';
import '../../localization/app_localizations.dart';
import '../../services/api_service.dart';
import '../customer/home_screen.dart';
import 'login_screen.dart';

class RegisterScreen extends StatefulWidget {
  const RegisterScreen({Key? key}) : super(key: key);

  @override
  State<RegisterScreen> createState() => _RegisterScreenState();
}

class _RegisterScreenState extends State<RegisterScreen> {
  final TextEditingController _nameController = TextEditingController();
  final TextEditingController _phoneController = TextEditingController();
  final TextEditingController _emailController = TextEditingController();
  final TextEditingController _passwordController = TextEditingController();
  final TextEditingController _otpController = TextEditingController();

  bool _isPhoneVerified = false;
  bool _isSendingOtp = false;

  void _sendFreeOtpAndVerify() async {
    String phone = _phoneController.text.trim();

    if (phone.length != 11 || !phone.startsWith('01') || int.tryParse(phone) == null) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(
          content: Text("Mobile number must start with '01' and be exactly 11 digits (e.g. 01712345678)"),
          backgroundColor: Colors.red,
        ),
      );
      return;
    }

    setState(() {
      _isSendingOtp = true;
    });

    _otpController.clear();

    final res = await ApiService.sendCustomerOtp(phone: phone, purpose: 'registration');
    if (!mounted) return;

    setState(() {
      _isSendingOtp = false;
    });

    if (res['already_registered'] == true) {
      _showAlreadyRegisteredDialog(phone, res['message'] ?? "Already registered with this mobile number or email.");
      return;
    }

    if (res['success'] != true) {
      ScaffoldMessenger.of(context).showSnackBar(
        SnackBar(
          content: Text(res['message'] ?? "Could not send WhatsApp OTP. Please try again."),
          backgroundColor: Colors.red,
        ),
      );
      return;
    }

    final String adminPhone = (res['admin_phone'] ?? 'Admin').toString().trim();
    final String whatsappUrl = (res['whatsapp_url'] ?? '').toString().trim();
    final bool sentViaGateway = res['sent_via_gateway'] == true;
    final int? metaErrorCode = res['meta_error_code'] != null ? int.tryParse(res['meta_error_code'].toString()) : null;
    final String otpCode = (res['otp_code'] ?? '').toString();

    if (!mounted) return;

    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (dialogCtx) => AlertDialog(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        title: const Row(
          children: [
            Icon(Icons.chat, color: Color(0xFF25D366)),
            SizedBox(width: 8),
            Text("WhatsApp Verification", style: TextStyle(fontWeight: FontWeight.bold)),
          ],
        ),
        content: SingleChildScrollView(
          child: Column(
            mainAxisSize: MainAxisSize.min,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Text("Mobile Number: $phone", style: const TextStyle(fontWeight: FontWeight.bold)),
              const SizedBox(height: 10),
              Container(
                padding: const EdgeInsets.all(12),
                decoration: BoxDecoration(
                  color: const Color(0xFFDCFCE7),
                  borderRadius: BorderRadius.circular(10),
                  border: Border.all(color: const Color(0xFF86EFAC)),
                ),
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    Row(
                      children: [
                        const Icon(Icons.verified_user, color: Color(0xFF15803D), size: 18),
                        const SizedBox(width: 6),
                        Expanded(
                          child: Text(
                            "Sender: Admin WhatsApp ($adminPhone)",
                            style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 13, color: Color(0xFF15803D)),
                          ),
                        ),
                      ],
                    ),
                    const SizedBox(height: 6),
                    if (sentViaGateway)
                      const Text(
                        "✅ A 4-digit verification code has been dispatched to your WhatsApp. Enter the code below.",
                        style: TextStyle(fontSize: 12, color: Color(0xFF15803D), fontWeight: FontWeight.bold),
                      )
                    else if (metaErrorCode == 131030)
                      Text(
                        "⚠️ Meta Developer Mode: Test number is pending in whitelist.\nYour Test OTP Code: $otpCode",
                        style: const TextStyle(fontSize: 12, color: Color(0xFFB45309), fontWeight: FontWeight.bold),
                      )
                    else
                      const Text(
                        "Please click the button below to message Admin on WhatsApp or enter the 4-digit code.",
                        style: TextStyle(fontSize: 12, color: Colors.black87),
                      ),
                    if (whatsappUrl.isNotEmpty) ...[
                      const SizedBox(height: 10),
                      SizedBox(
                        width: double.infinity,
                        child: ElevatedButton.icon(
                          onPressed: () async {
                            final uri = Uri.parse(whatsappUrl);
                            if (await canLaunchUrl(uri)) {
                              await launchUrl(uri, mode: LaunchMode.externalApplication);
                            }
                          },
                          icon: const Icon(Icons.chat_bubble_outline, size: 16, color: Colors.white),
                          label: const Text("Message Admin on WhatsApp", style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 12)),
                          style: ElevatedButton.styleFrom(
                            backgroundColor: const Color(0xFF16A34A),
                            padding: const EdgeInsets.symmetric(vertical: 8),
                            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                          ),
                        ),
                      ),
                    ],
                    const SizedBox(height: 8),
                    Center(
                      child: TextButton.icon(
                        onPressed: () {
                          Navigator.pop(dialogCtx);
                          _showMissedCallDialog(phone, adminPhone);
                        },
                        icon: const Icon(Icons.phone_forwarded, size: 14, color: Color(0xFF0284C7)),
                        label: const Text(
                          "Don't have WhatsApp? Verify via Helpline Call",
                          style: TextStyle(color: Color(0xFF0284C7), fontSize: 11, fontWeight: FontWeight.bold),
                        ),
                      ),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 14),
              const Text("Enter 4-digit WhatsApp OTP:", style: TextStyle(fontWeight: FontWeight.w600, fontSize: 13)),
              const SizedBox(height: 8),
              TextField(
                controller: _otpController,
                keyboardType: TextInputType.number,
                maxLength: 4,
                textAlign: TextAlign.center,
                style: const TextStyle(fontSize: 24, fontWeight: FontWeight.bold, letterSpacing: 8),
                decoration: const InputDecoration(
                  hintText: "____",
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
              String otp = _otpController.text.trim();
              if (otp.length != 4) {
                ScaffoldMessenger.of(dialogCtx).showSnackBar(
                  const SnackBar(content: Text("Please enter the 4-digit OTP code"), backgroundColor: Colors.red),
                );
                return;
              }

              final nav = Navigator.of(dialogCtx);
              var vRes = await ApiService.verifyCustomerOtp(phone: phone, otp: otp);
              if (!mounted) return;

              if (vRes['success'] == true) {
                nav.pop();
                setState(() {
                  _isPhoneVerified = true;
                });
                if (mounted) {
                  ScaffoldMessenger.of(context).showSnackBar(
                    const SnackBar(content: Text("✅ WhatsApp OTP verified successfully! Complete your registration details."), backgroundColor: Colors.green),
                  );
                }
              } else {
                if (dialogCtx.mounted) {
                  ScaffoldMessenger.of(dialogCtx).showSnackBar(
                    SnackBar(content: Text(vRes['message'] ?? "Invalid OTP code. Please check WhatsApp."), backgroundColor: Colors.red),
                  );
                }
              }
            },
            style: ElevatedButton.styleFrom(backgroundColor: const Color(0xFF16A34A)),
            child: const Text("Verify OTP", style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
          ),
        ],
      ),
    );
  }

  void _showMissedCallDialog(String phone, String adminPhone) {
    showDialog(
      context: context,
      barrierDismissible: false,
      builder: (dialogCtx) => AlertDialog(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        title: const Row(
          children: [
            Icon(Icons.phone_in_talk, color: Color(0xFF0284C7)),
            SizedBox(width: 8),
            Text("Helpline Verification", style: TextStyle(fontWeight: FontWeight.bold)),
          ],
        ),
        content: Column(
          mainAxisSize: MainAxisSize.min,
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Text("Mobile Number: $phone", style: const TextStyle(fontWeight: FontWeight.bold)),
            const SizedBox(height: 10),
            Container(
              padding: const EdgeInsets.all(12),
              decoration: BoxDecoration(
                color: const Color(0xFFF0F9FF),
                borderRadius: BorderRadius.circular(10),
                border: Border.all(color: const Color(0xFF7DD3FC)),
              ),
              child: Column(
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  const Text(
                    "To confirm that your phone number is active and genuine, please place a free missed-call (give 1 ring and disconnect) to our Helpline:",
                    style: TextStyle(fontSize: 12, color: Color(0xFF0C4A6E), height: 1.4),
                  ),
                  const SizedBox(height: 8),
                  Center(
                    child: Text(
                      adminPhone,
                      style: const TextStyle(fontSize: 20, fontWeight: FontWeight.w900, color: Color(0xFF0284C7), letterSpacing: 1),
                    ),
                  ),
                  const SizedBox(height: 10),
                  SizedBox(
                    width: double.infinity,
                    child: ElevatedButton.icon(
                      onPressed: () async {
                        final uri = Uri.parse("tel:$adminPhone");
                        if (await canLaunchUrl(uri)) {
                          await launchUrl(uri);
                        }
                      },
                      icon: const Icon(Icons.call, size: 16, color: Colors.white),
                      label: const Text("Call Helpline Now", style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 12)),
                      style: ElevatedButton.styleFrom(
                        backgroundColor: const Color(0xFF0284C7),
                        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(8)),
                      ),
                    ),
                  ),
                ],
              ),
            ),
          ],
        ),
        actions: [
          TextButton(
            onPressed: () => Navigator.pop(dialogCtx),
            child: const Text("Cancel"),
          ),
          ElevatedButton(
            onPressed: () async {
              final nav = Navigator.of(dialogCtx);
              var res = await ApiService.verifyMissedCall(phone: phone);
              if (!mounted) return;

              if (res['success'] == true) {
                nav.pop();
                setState(() {
                  _isPhoneVerified = true;
                });
                if (mounted) {
                  ScaffoldMessenger.of(context).showSnackBar(
                    const SnackBar(
                      content: Text("✅ Phone verified via Helpline Call! Please complete your registration details."),
                      backgroundColor: Colors.green,
                    ),
                  );
                }
              } else {
                if (dialogCtx.mounted) {
                  ScaffoldMessenger.of(dialogCtx).showSnackBar(
                    SnackBar(content: Text(res['message'] ?? "Verification failed."), backgroundColor: Colors.red),
                  );
                }
              }
            },
            style: ElevatedButton.styleFrom(backgroundColor: const Color(0xFF047857)),
            child: const Text("I Have Placed the Missed Call", style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
          ),
        ],
      ),
    );
  }

  void _showAlreadyRegisteredDialog(String phone, String message) {
    showDialog(
      context: context,
      builder: (dialogCtx) => AlertDialog(
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        title: const Row(
          children: [
            Icon(Icons.warning_amber_rounded, color: Colors.orange, size: 28),
            SizedBox(width: 8),
            Expanded(
              child: Text(
                "Already Registered",
                style: TextStyle(fontSize: 15, fontWeight: FontWeight.bold),
              ),
            ),
          ],
        ),
        content: Text(
          "$message\n\nWould you like to log in now or recover your password?",
          style: const TextStyle(height: 1.4),
        ),
        actions: [
          OutlinedButton(
            onPressed: () {
              Navigator.pop(dialogCtx);
              Navigator.pushReplacement(
                context,
                MaterialPageRoute(builder: (_) => LoginScreen(initialPhone: phone)),
              );
            },
            child: const Text("Forgot Password?"),
          ),
          ElevatedButton(
            onPressed: () {
              Navigator.pop(dialogCtx);
              Navigator.pushReplacement(
                context,
                MaterialPageRoute(builder: (_) => LoginScreen(initialPhone: phone)),
              );
            },
            style: ElevatedButton.styleFrom(backgroundColor: Colors.green),
            child: const Text("Login Now", style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
          ),
        ],
      ),
    );
  }

  void _completeRegistration() async {
    String phone = _phoneController.text.trim();
    String name = _nameController.text.trim();
    String email = _emailController.text.trim();
    String password = _passwordController.text.trim();

    if (name.isEmpty || password.isEmpty) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text("Please fill in your name and password")),
      );
      return;
    }

    if (password.length < 4) {
      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text("Password must be at least 4 characters long")),
      );
      return;
    }

    var res = await ApiService.register(
      phone: phone,
      name: name,
      email: email,
      password: password,
    );

    if (!mounted) return;

    if (res['success'] == true) {
      final prefs = await SharedPreferences.getInstance();
      await prefs.setString('user_phone', phone);
      await prefs.setString('user_name', name);
      await prefs.setString('user_email', email);
      await prefs.setBool('is_delivery_man', false);

      if (!mounted) return;

      ScaffoldMessenger.of(context).showSnackBar(
        const SnackBar(content: Text("Registration completed successfully! Welcome."), backgroundColor: Colors.green),
      );

      Navigator.pushAndRemoveUntil(
        context,
        MaterialPageRoute(builder: (_) => const HomeScreen()),
        (route) => false,
      );
    } else {
      if (res['already_registered'] == true) {
        _showAlreadyRegisteredDialog(phone, res['message'] ?? "This phone or email is already registered.");
      } else {
        showDialog(
          context: context,
          builder: (ctx) => AlertDialog(
            title: const Text("Registration Issue"),
            content: Text(res['message'] ?? "Could not complete registration."),
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
  }

  @override
  Widget build(BuildContext context) {
    final loc = AppLocalizations.of(context);

    return Scaffold(
      appBar: AppBar(
        title: Text(loc.translate('register')),
        backgroundColor: Colors.green,
      ),
      body: SingleChildScrollView(
        padding: const EdgeInsets.all(20.0),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            // Registration Progress Indicator Card
            Card(
              elevation: 2,
              shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(12)),
              color: Colors.green.shade50,
              child: Padding(
                padding: const EdgeInsets.all(16.0),
                child: Row(
                  children: [
                    CircleAvatar(
                      radius: 18,
                      backgroundColor: _isPhoneVerified ? Colors.green : Colors.orange,
                      child: Text(
                        _isPhoneVerified ? "2" : "1",
                        style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold),
                      ),
                    ),
                    const SizedBox(width: 12),
                    Expanded(
                      child: Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Text(
                            _isPhoneVerified
                                ? "Step 2: Complete Profile Details"
                                : "Step 1: Phone Verification (Free)",
                            style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 14),
                          ),
                          const SizedBox(height: 2),
                          Text(
                            _isPhoneVerified
                                ? "Enter your name and password to finalize registration."
                                : "Verify your mobile number via WhatsApp or Free Missed Call.",
                            style: const TextStyle(fontSize: 12, color: Colors.black54),
                          ),
                        ],
                      ),
                    ),
                  ],
                ),
              ),
            ),
            const SizedBox(height: 20),

            // Step 1: Mobile Phone Verification Section
            TextField(
              controller: _phoneController,
              enabled: !_isPhoneVerified && !_isSendingOtp,
              keyboardType: TextInputType.phone,
              maxLength: 11,
              inputFormatters: [
                FilteringTextInputFormatter.digitsOnly,
                LengthLimitingTextInputFormatter(11),
              ],
              decoration: InputDecoration(
                labelText: loc.translate('phone_number'),
                prefixIcon: const Icon(Icons.phone),
                suffixIcon: _isPhoneVerified
                    ? const Icon(Icons.check_circle, color: Colors.green)
                    : null,
                border: const OutlineInputBorder(),
                counterText: "",
              ),
            ),
            const SizedBox(height: 16),

            if (!_isPhoneVerified) ...[
              SizedBox(
                width: double.infinity,
                height: 50,
                child: ElevatedButton.icon(
                  onPressed: _isSendingOtp ? null : _sendFreeOtpAndVerify,
                  icon: _isSendingOtp
                      ? const SizedBox(
                          height: 20,
                          width: 20,
                          child: CircularProgressIndicator(color: Colors.white, strokeWidth: 2),
                        )
                      : const Icon(Icons.chat, color: Colors.white),
                  label: Text(
                    _isSendingOtp ? "Connecting..." : "Verify via WhatsApp (Free)",
                    style: const TextStyle(fontSize: 15, fontWeight: FontWeight.bold, color: Colors.white),
                  ),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: const Color(0xFF16A34A),
                    shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                  ),
                ),
              ),
              const SizedBox(height: 10),
              Center(
                child: TextButton.icon(
                  onPressed: () {
                    String phone = _phoneController.text.trim();
                    if (phone.length != 11 || !phone.startsWith('01') || int.tryParse(phone) == null) {
                      ScaffoldMessenger.of(context).showSnackBar(
                        const SnackBar(
                          content: Text("Mobile number must start with '01' and be exactly 11 digits (e.g. 01712345678)"),
                          backgroundColor: Colors.red,
                        ),
                      );
                      return;
                    }
                    _showMissedCallDialog(phone, "01922606444");
                  },
                  icon: const Icon(Icons.phone_in_talk, size: 16, color: Color(0xFF0284C7)),
                  label: const Text(
                    "Don't have WhatsApp? Verify via Free Missed Call",
                    style: TextStyle(color: Color(0xFF0284C7), fontWeight: FontWeight.bold, fontSize: 12),
                  ),
                ),
              ),
            ],

            // Step 2: Full Profile Information Section (Unlocked after OTP verified)
            if (_isPhoneVerified) ...[
              Container(
                margin: const EdgeInsets.only(bottom: 16),
                padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
                decoration: BoxDecoration(
                  color: Colors.green.shade100,
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Row(
                  mainAxisAlignment: MainAxisAlignment.spaceBetween,
                  children: [
                    Text(
                      "✅ Verified Phone: ${_phoneController.text.trim()}",
                      style: const TextStyle(fontWeight: FontWeight.bold, color: Colors.green),
                    ),
                    TextButton(
                      onPressed: () {
                        setState(() {
                          _isPhoneVerified = false;
                        });
                      },
                      child: const Text("Change Number", style: TextStyle(fontSize: 12, color: Colors.blue)),
                    ),
                  ],
                ),
              ),

              TextField(
                controller: _nameController,
                decoration: InputDecoration(
                  labelText: loc.translate('name'),
                  prefixIcon: const Icon(Icons.person),
                  border: const OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 16),

              TextField(
                controller: _emailController,
                keyboardType: TextInputType.emailAddress,
                decoration: InputDecoration(
                  labelText: loc.translate('email'),
                  prefixIcon: const Icon(Icons.email),
                  border: const OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 16),

              TextField(
                controller: _passwordController,
                obscureText: true,
                decoration: InputDecoration(
                  labelText: loc.translate('password'),
                  prefixIcon: const Icon(Icons.lock),
                  border: const OutlineInputBorder(),
                ),
              ),
              const SizedBox(height: 24),

              SizedBox(
                width: double.infinity,
                height: 50,
                child: ElevatedButton.icon(
                  onPressed: _completeRegistration,
                  icon: const Icon(Icons.app_registration, color: Colors.white),
                  label: const Text(
                    "Complete Registration",
                    style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: Colors.white),
                  ),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: Colors.green,
                  ),
                ),
              ),
            ],
          ],
        ),
      ),
    );
  }
}
