import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

class AppLocalizations {
  final Locale locale;

  AppLocalizations(this.locale);

  static AppLocalizations of(BuildContext context) {
    return Localizations.of<AppLocalizations>(context, AppLocalizations)!;
  }

  static const LocalizationsDelegate<AppLocalizations> delegate =
      _AppLocalizationsDelegate();

  static final Map<String, Map<String, String>> _localizedValues = {
    'en': {
      'app_title': 'Supershop Express',
      'login': 'Sign In',
      'register': 'Register Account',
      'phone_number': 'Mobile Phone Number',
      'password': 'Password',
      'name': 'Full Name',
      'email': 'Email Address (Optional)',
      'select_location': 'Select Delivery Location',
      'country': 'Country',
      'district': 'District',
      'area': 'Area / Para',
      'address_details': 'Detailed Home Address',
      'trending': '🔥 Trending',
      'flash_sale': '⚡ Flash Sale',
      'offers': '🎁 Current Offers',
      'categories': 'Categories',
      'all_products': 'All Products',
      'mrp': 'MRP',
      'doineek_price': 'Doineek Price',
      'save': 'Save',
      'add_to_cart': 'Add to Cart',
      'cart': 'Shopping Cart',
      'checkout': 'Proceed to Checkout',
      'total': 'Total',
      'delivery_charge': 'Delivery Charge',
      'payment_method': 'Payment Method',
      'cod': 'Cash on Delivery (COD)',
      'bkash': 'bKash (Coming Soon)',
      'nagad': 'Nagad (Coming Soon)',
      'rocket': 'Rocket (Coming Soon)',
      'card': 'Credit / Debit Card',
      'place_order': 'Place Order Now',
      'my_orders': 'My Orders',
      'order_status': 'Order Status',
      'delivery_otp': 'Delivery OTP',
      'delivery_otp_desc': 'Give this OTP to delivery man upon receiving products:',
      'delivery_man_mode': 'Switch to Delivery Man Mode',
      'customer_mode': 'Switch to Customer Mode',
      'enter_otp': 'Enter Delivery OTP',
      'verify': 'Verify Delivery',
      'out_of_delivery_area': 'Delivery unavailable in your area!',
    },
    'bn': {
      'app_title': 'সুপারশপ এক্সপ্রেস',
      'login': 'লগইন করুন',
      'register': 'রেজিস্ট্রেশন করুন',
      'phone_number': 'মোবাইল নম্বর',
      'password': 'পাসওয়ার্ড',
      'name': 'আপনার নাম',
      'email': 'ইমেইল অ্যাড্রেস (ঐচ্ছিক)',
      'select_location': 'ডেলিভারি লোকেশন সিলেক্ট করুন',
      'country': 'দেশ',
      'district': 'জেলা',
      'area': 'এলাকা / পাড়া',
      'address_details': 'বাসার বিস্তারিত ঠিকানা',
      'trending': '🔥 ট্রেন্ডিং',
      'flash_sale': '⚡ ফ্ল্যাশ সেল',
      'offers': '🎁 বিশেষ অফার',
      'categories': 'ক্যাটাগরি সমূহ',
      'all_products': 'সকল পণ্য',
      'mrp': 'এম.আর.পি',
      'doineek_price': 'দৈনিক প্রাইজ',
      'save': 'সাশ্রয়',
      'add_to_cart': 'কার্টে যোগ করুন',
      'cart': 'শপিং কার্ট',
      'checkout': 'অর্ডার সম্পন্ন করুন',
      'total': 'মোট টাকার পরিমাণ',
      'delivery_charge': 'ডেলিভারি চার্জ',
      'payment_method': 'পেমেন্ট পদ্ধতি',
      'cod': 'ক্যাশ অন ডেলিভারি (COD)',
      'bkash': 'বিকাশ (শীঘ্রই আসছে)',
      'nagad': 'নগদ (শীঘ্রই আসছে)',
      'rocket': 'রকেট (শীঘ্রই আসছে)',
      'card': 'কার্ড পেমেন্ট',
      'place_order': 'অর্ডার কনফার্ম করুন',
      'my_orders': 'আমার অর্ডারসমূহ',
      'order_status': 'অর্ডারের বর্তমান অবস্থা',
      'delivery_otp': 'ডেলিভারি ওটিপি',
      'delivery_otp_desc': 'পণ্য পাওয়ার পর ডেলিভারি ম্যানকে এই ওটিপি দিন:',
      'delivery_man_mode': 'ডেলিভারি ম্যান মোড',
      'customer_mode': 'কাস্টমার মোড',
      'enter_otp': 'ডেলিভারি OTP দিন',
      'verify': 'ভেরিফাই করুন',
      'out_of_delivery_area': 'আপনার এলাকায় ডেলিভারি সুবিধা বন্ধ রয়েছে!',
    }
  };

  String translate(String key) {
    return _localizedValues[locale.languageCode]?[key] ?? key;
  }
}

class _AppLocalizationsDelegate
    extends LocalizationsDelegate<AppLocalizations> {
  const _AppLocalizationsDelegate();

  @override
  bool isSupported(Locale locale) => ['en', 'bn'].contains(locale.languageCode);

  @override
  Future<AppLocalizations> load(Locale locale) {
    return SynchronousFuture<AppLocalizations>(AppLocalizations(locale));
  }

  @override
  bool shouldReload(_AppLocalizationsDelegate old) => false;
}
