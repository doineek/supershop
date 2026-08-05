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
      'bkash': 'bKash (Temporarily Unavailable)',
      'nagad': 'Nagad (Temporarily Unavailable)',
      'rocket': 'Rocket (Temporarily Unavailable)',
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
    }
  };

  String translate(String key) {
    return _localizedValues['en']?[key] ?? _localizedValues['bn']?[key] ?? key;
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
