import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';
import '../../localization/app_localizations.dart';
import '../../services/api_service.dart';
import '../../services/firebase_auth_service.dart';
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

    await FirebaseAuthService.sendFirebasePhoneOtp(
      rawPhone: phone,
      purpose: 'registration',
      onCodeSent: (verificationId, isFirebaseNative) {
        if (!mounted) return;
        setState(() {
          _isSendingOtp = false;
        });

        showDialog(
          context: context,
          barrierDismissible: false,
          builder: (dialogCtx) => AlertDialog(
            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
            title: const Row(
              children: [
                Icon(Icons.sms, color: Colors.green),
                SizedBox(width: 8),
                Text("Firebase Phone Verification"),
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
                        "An OTP verification code was sent to your phone. Check your SMS inbox and enter the code below.",
                        style: TextStyle(fontSize: 12, color: Colors.black87),
                      ),
                    ],
                  ),
                ),
                const SizedBox(height: 14),
                const Text("Enter OTP verification code below:"),
                const SizedBox(height: 8),
                TextField(
                  controller: _otpController,
                  keyboardType: TextInputType.number,
                  maxLength: 6,
                  textAlign: TextAlign.center,
                  style: const TextStyle(fontSize: 22, fontWeight: FontWeight.bold, letterSpacing: 4),
                  decoration: const InputDecoration(
                    hintText: "______",
                    border: OutlineInputBorder(),
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
                  String otp = _otpController.text.trim();
                  if (otp.length < 4) {
                    ScaffoldMessenger.of(dialogCtx).showSnackBar(
                      const SnackBar(content: Text("Please enter a valid OTP code"), backgroundColor: Colors.red),
                    );
                    return;
                  }

                  final nav = Navigator.of(dialogCtx);
                  var vRes = await FirebaseAuthService.verifyFirebasePhoneOtp(
                    rawPhone: phone,
                    verificationId: verificationId,
                    smsCode: otp,
                    isFirebaseNative: isFirebaseNative,
                  );
                  if (!mounted) return;

                  if (vRes['success'] == true) {
                    nav.pop();
                    setState(() {
                      _isPhoneVerified = true;
                    });
                    if (mounted) {
                      ScaffoldMessenger.of(context).showSnackBar(
                        const SnackBar(content: Text("Mobile number verified successfully! Complete your registration details."), backgroundColor: Colors.green),
                      );
                    }
                  } else {
                    if (dialogCtx.mounted) {
                      ScaffoldMessenger.of(dialogCtx).showSnackBar(
                        SnackBar(content: Text(vRes['message'] ?? "Invalid OTP code. Please check your SMS."), backgroundColor: Colors.red),
                      );
                    }
                  }
                },
                style: ElevatedButton.styleFrom(backgroundColor: Colors.green),
                child: const Text("Verify OTP", style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
              ),
            ],
          ),
        );
      },
      onError: (err) {
        if (!mounted) return;
        setState(() {
          _isSendingOtp = false;
        });

        if (err.startsWith("ALREADY_REGISTERED:")) {
          String cleanMsg = err.replaceFirst("ALREADY_REGISTERED:", "");
          _showAlreadyRegisteredDialog(phone, cleanMsg);
        } else {
          ScaffoldMessenger.of(context).showSnackBar(
            SnackBar(content: Text(err), backgroundColor: Colors.red),
          );
        }
      },
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
                                : "Step 1: Phone OTP Verification",
                            style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 14),
                          ),
                          const SizedBox(height: 2),
                          Text(
                            _isPhoneVerified
                                ? "Enter your name and password to finalize registration."
                                : "Enter your mobile number and verify via Firebase OTP.",
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
              decoration: InputDecoration(
                labelText: loc.translate('phone_number'),
                prefixIcon: const Icon(Icons.phone),
                suffixIcon: _isPhoneVerified
                    ? const Icon(Icons.check_circle, color: Colors.green)
                    : null,
                border: const OutlineInputBorder(),
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
                      : const Icon(Icons.security_sharp, color: Colors.white),
                  label: Text(
                    _isSendingOtp ? "Sending OTP..." : "Send Firebase Free OTP & Verify",
                    style: const TextStyle(fontSize: 15, fontWeight: FontWeight.bold, color: Colors.white),
                  ),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: Colors.green,
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
