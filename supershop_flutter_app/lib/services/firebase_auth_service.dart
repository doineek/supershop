import 'package:flutter/foundation.dart';
import 'package:firebase_core/firebase_core.dart';
import 'package:firebase_auth/firebase_auth.dart';
import 'api_service.dart';

class FirebaseAuthService {
  static bool _initialized = false;

  static Future<void> ensureInitialized() async {
    if (_initialized) return;
    try {
      if (Firebase.apps.isEmpty) {
        await Firebase.initializeApp();
      }
      _initialized = true;
    } catch (e) {
      debugPrint("Firebase initializeApp note: $e");
    }
  }

  /// Sends Free Cellular SMS OTP to user's mobile number (+8801XXXXXXXXX) via Firebase Phone Auth or Backend API
  static Future<void> sendFirebasePhoneOtp({
    required String rawPhone,
    required String purpose,
    required Function(String verificationId, bool isFirebaseNative) onCodeSent,
    required Function(String errorMsg) onError,
  }) async {
    await ensureInitialized();

    // Helper for backend fallback
    Future<void> triggerBackendOtpFallback() async {
      var res = await ApiService.sendCustomerOtp(phone: rawPhone, purpose: purpose);
      if (res['already_registered'] == true) {
        onError("ALREADY_REGISTERED:${res['message']}");
      } else if (res['success'] == true) {
        onCodeSent("BACKEND_OTP_SENT", false);
      } else {
        onError(res['message'] ?? "Failed to send OTP. Please try again.");
      }
    }

    // Format to international phone format (+8801XXXXXXXXX)
    String phoneWithCode = rawPhone.trim();
    if (!phoneWithCode.startsWith('+88')) {
      if (phoneWithCode.startsWith('88')) {
        phoneWithCode = '+$phoneWithCode';
      } else {
        phoneWithCode = '+88$phoneWithCode';
      }
    }

    bool codeDispatched = false;

    try {
      if (_initialized && !kIsWeb) {
        await FirebaseAuth.instance.verifyPhoneNumber(
          phoneNumber: phoneWithCode,
          timeout: const Duration(seconds: 15),
          verificationCompleted: (PhoneAuthCredential credential) async {
            debugPrint("Firebase Phone verificationCompleted auto-credential");
          },
          verificationFailed: (FirebaseAuthException e) async {
            debugPrint("Firebase Phone verificationFailed: ${e.message}. Falling back to Backend OTP Server.");
            if (!codeDispatched) {
              codeDispatched = true;
              await triggerBackendOtpFallback();
            }
          },
          codeSent: (String verificationId, int? resendToken) {
            if (!codeDispatched) {
              codeDispatched = true;
              onCodeSent(verificationId, true);
            }
          },
          codeAutoRetrievalTimeout: (String verificationId) {
            debugPrint("Firebase Phone codeAutoRetrievalTimeout: $verificationId");
          },
        );

        // Wait up to 3 seconds for Firebase callback, if delayed, trigger backend fallback so user is never stuck
        await Future.delayed(const Duration(seconds: 3));
        if (!codeDispatched) {
          codeDispatched = true;
          await triggerBackendOtpFallback();
        }
        return;
      }
    } catch (e) {
      debugPrint("Firebase verifyPhoneNumber exception: $e. Falling back to Backend OTP Server.");
    }

    if (!codeDispatched) {
      codeDispatched = true;
      await triggerBackendOtpFallback();
    }
  }

  /// Verifies 6-digit SMS OTP from Firebase or 4-digit code
  static Future<Map<String, dynamic>> verifyFirebasePhoneOtp({
    required String rawPhone,
    required String verificationId,
    required String smsCode,
    required bool isFirebaseNative,
  }) async {
    if (isFirebaseNative && verificationId != "BACKEND_OTP_SENT") {
      try {
        PhoneAuthCredential credential = PhoneAuthProvider.credential(
          verificationId: verificationId,
          smsCode: smsCode,
        );
        UserCredential userCredential = await FirebaseAuth.instance.signInWithCredential(credential);
        if (userCredential.user != null) {
          return {"success": true, "message": "Firebase SMS Phone Verification Successful!"};
        }
      } on FirebaseAuthException catch (e) {
        debugPrint("Firebase verify error: ${e.message}. Attempting backend verification...");
      } catch (e) {
        debugPrint("Firebase verify exception: $e");
      }
    }

    // Always fallback verification via backend OTP API
    return await ApiService.verifyCustomerOtp(phone: rawPhone, otp: smsCode);
  }
}
