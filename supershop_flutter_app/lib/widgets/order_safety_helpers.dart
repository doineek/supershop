import 'package:flutter/material.dart';
import '../models/delivery_area.dart';
import '../services/api_service.dart';

/// Shared address/geofence validation, Terms & Conditions agreement widget,
/// and address availability confirmation dialog for all customer order flows.
class OrderAddressValidation {
  static const Set<String> _placeholderWords = {
    'test',
    'testing',
    'asdf',
    'qwer',
    'qwerty',
    'fake',
    'demo',
    'sample',
    'none',
    'null',
    'na',
    'ok',
    'okay',
    'abc',
    'xyz',
    'aaa',
    'bbb',
    'home',
    'house',
    'office',
    'address',
    'bd',
    'tangail',
    'dhaka',
    'bangladesh',
    'ঠিকানা',
    'বাসা',
    'বাড়ি',
    'বাড়ি',
  };

  /// Verifies that [district] and [area] belong to the shop's active [activeAreas].
  static String? validateServiceArea({
    required String district,
    required String area,
    required List<DeliveryArea> activeAreas,
  }) {
    final String d = district.trim().toLowerCase();
    final String a = area.trim().toLowerCase();

    if (activeAreas.isEmpty) {
      return 'বর্তমানে সক্রিয় ডেলিভারি এলাকা লোড করা যায়নি বা চালু নেই। অনুগ্রহ করে ইন্টারনেট যাচাই করে আবার চেষ্টা করুন।';
    }

    if (d.isEmpty || a.isEmpty) {
      return 'অনুগ্রহ করে জেলা ও সক্রিয় ডেলিভারি এলাকা নির্বাচন করুন।';
    }

    final bool matched = activeAreas.any(
      (item) =>
          item.isActive &&
          item.district.trim().toLowerCase() == d &&
          item.area.trim().toLowerCase() == a,
    );

    if (!matched) {
      return 'দুঃখিত! "$area, $district" বর্তমানে আমাদের সক্রিয় ডেলিভারি এলাকার মধ্যে নেই। অনুগ্রহ করে তালিকা থেকে সক্রিয় ডেলিভারি এলাকা নির্বাচন করুন।';
    }
    return null;
  }

  /// Verifies that [address] contains meaningful multi-word delivery details.
  static String? validateDetailedAddress(String address) {
    final String clean = address.trim().replaceAll(RegExp(r'\s+'), ' ');
    final List<String> tokens = RegExp(r'[A-Za-z0-9\u0980-\u09FF]+')
        .allMatches(clean)
        .map((m) => m.group(0)!)
        .toList();
    final List<String> alphaTokens = RegExp(r'[A-Za-z\u0980-\u09FF]{2,}')
        .allMatches(clean)
        .map((m) => m.group(0)!)
        .toList();
    final int uniqueChars = clean
        .toLowerCase()
        .replaceAll(RegExp(r'\s+'), '')
        .split('')
        .toSet()
        .length;
    final bool hasRealWord = alphaTokens.any(
      (w) => !_placeholderWords.contains(w.toLowerCase()),
    );

    if (clean.length < 8 ||
        tokens.length < 2 ||
        alphaTokens.isEmpty ||
        uniqueChars <= 2 ||
        !hasRealWord) {
      return 'অনুগ্রহ করে বাসা/হোল্ডিং নম্বর, রোড/পাড়া ও পরিচিত ল্যান্ডমার্কসহ সঠিক বিস্তারিত ডেলিভারি ঠিকানা লিখুন (কমপক্ষে ৮ অক্ষর ও ২টি শব্দ)।';
    }
    return null;
  }
}

Future<void> showTermsAndConditionsDialog(BuildContext context) async {
  showDialog(
    context: context,
    builder: (ctx) => AlertDialog(
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      title: const Row(
        children: [
          Icon(Icons.policy_outlined, color: Color(0xFF047857)),
          SizedBox(width: 8),
          Expanded(
            child: Text(
              'Terms & Conditions',
              style: TextStyle(fontSize: 16, fontWeight: FontWeight.bold),
            ),
          ),
        ],
      ),
      content: SizedBox(
        width: double.maxFinite,
        child: FutureBuilder<Map<String, String>>(
          future: ApiService.fetchStorePolicies(),
          builder: (context, snapshot) {
            if (snapshot.connectionState == ConnectionState.waiting) {
              return const Padding(
                padding: EdgeInsets.symmetric(vertical: 20),
                child: Center(child: CircularProgressIndicator()),
              );
            }
            final String text =
                snapshot.data?['terms_conditions']?.trim().isNotEmpty == true
                    ? snapshot.data!['terms_conditions']!
                    : 'By placing an order, you agree to provide a reachable delivery address and valid contact number within our active service areas.';
            return SingleChildScrollView(
              child: Text(
                text,
                style: const TextStyle(fontSize: 13, height: 1.5),
              ),
            );
          },
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(ctx),
          child: const Text('বন্ধ করুন', style: TextStyle(fontWeight: FontWeight.bold)),
        ),
      ],
    ),
  );
}

class TermsAgreementRow extends StatelessWidget {
  final bool agreed;
  final ValueChanged<bool> onChanged;
  final bool compact;

  const TermsAgreementRow({
    Key? key,
    required this.agreed,
    required this.onChanged,
    this.compact = false,
  }) : super(key: key);

  @override
  Widget build(BuildContext context) {
    return Container(
      padding: EdgeInsets.symmetric(
        horizontal: compact ? 8 : 10,
        vertical: compact ? 4 : 6,
      ),
      decoration: BoxDecoration(
        color: agreed ? const Color(0xFFECFDF5) : const Color(0xFFFEF2F2),
        borderRadius: BorderRadius.circular(10),
        border: Border.all(
          color: agreed ? const Color(0xFFA7F3D0) : const Color(0xFFFCA5A5),
        ),
      ),
      child: Row(
        children: [
          SizedBox(
            width: 24,
            height: 24,
            child: Checkbox(
              value: agreed,
              activeColor: const Color(0xFF059669),
              materialTapTargetSize: MaterialTapTargetSize.shrinkWrap,
              onChanged: (v) => onChanged(v ?? false),
            ),
          ),
          const SizedBox(width: 6),
          Expanded(
            child: Wrap(
              crossAxisAlignment: WrapCrossAlignment.center,
              children: [
                GestureDetector(
                  onTap: () => onChanged(!agreed),
                  child: Text(
                    'Agreed to ',
                    style: TextStyle(
                      fontSize: compact ? 11.5 : 12.5,
                      fontWeight: FontWeight.w700,
                      color: agreed
                          ? const Color(0xFF065F46)
                          : const Color(0xFF991B1B),
                    ),
                  ),
                ),
                GestureDetector(
                  onTap: () => showTermsAndConditionsDialog(context),
                  child: Text(
                    'terms and conditions',
                    style: TextStyle(
                      fontSize: compact ? 11.5 : 12.5,
                      fontWeight: FontWeight.w800,
                      color: const Color(0xFF047857),
                      decoration: TextDecoration.underline,
                    ),
                  ),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}

Future<bool> showAddressAvailabilityConfirmationDialog(
  BuildContext context, {
  required String district,
  required String area,
  required String address,
  required String phone,
  String? totalLabel,
}) async {
  final bool? confirmed = await showDialog<bool>(
    context: context,
    barrierDismissible: false,
    builder: (ctx) => AlertDialog(
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      title: const Row(
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Icon(Icons.location_on, color: Colors.orange, size: 28),
          SizedBox(width: 8),
          Expanded(
            child: Text(
              'এই ঠিকানায় কি আপনাকে পাওয়া যাবে?',
              style: TextStyle(fontSize: 16, fontWeight: FontWeight.w900),
            ),
          ),
        ],
      ),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          const Text(
            'আমাদের ডেলিভারি ম্যান নিচের ঠিকানায় গেলে আপনাকে বা আপনার প্রতিনিধিকে পাবেন এবং ফোনে যোগাযোগ করা যাবে তা নিশ্চিত হয়ে অর্ডার কনফার্ম করুন।',
            style: TextStyle(fontSize: 12.5, color: Colors.black87, height: 1.4),
          ),
          const SizedBox(height: 12),
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              color: const Color(0xFFF8FAFC),
              borderRadius: BorderRadius.circular(10),
              border: Border.all(color: const Color(0xFFCBD5E1)),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text('জেলা: $district', style: const TextStyle(fontSize: 12.5, fontWeight: FontWeight.w600)),
                const SizedBox(height: 3),
                Text('এলাকা / থানা: $area', style: const TextStyle(fontSize: 12.5, fontWeight: FontWeight.w600)),
                const SizedBox(height: 3),
                Text('বিস্তারিত ঠিকানা: $address', style: const TextStyle(fontSize: 12.5, fontWeight: FontWeight.bold, color: Color(0xFF0F172A))),
                const SizedBox(height: 3),
                Text('মোবাইল নম্বর: $phone', style: const TextStyle(fontSize: 12.5, fontWeight: FontWeight.w600)),
                if (totalLabel != null && totalLabel.trim().isNotEmpty) ...[
                  const Divider(height: 12),
                  Text(
                    'মোট বিল: $totalLabel',
                    style: const TextStyle(fontSize: 13, fontWeight: FontWeight.w900, color: Color(0xFF047857)),
                  ),
                ],
              ],
            ),
          ),
        ],
      ),
      actions: [
        OutlinedButton(
          onPressed: () => Navigator.pop(ctx, false),
          child: const Text('ঠিকানা পরিবর্তন করুন', style: TextStyle(fontWeight: FontWeight.bold)),
        ),
        ElevatedButton(
          onPressed: () => Navigator.pop(ctx, true),
          style: ElevatedButton.styleFrom(backgroundColor: const Color(0xFF059669)),
          child: const Text(
            'হ্যাঁ, এই ঠিকানায় পাওয়া যাবে',
            style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold),
          ),
        ),
      ],
    ),
  );
  return confirmed == true;
}
