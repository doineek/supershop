import 'package:flutter/material.dart';

class LocaleProvider extends ChangeNotifier {
  Locale _locale = const Locale('en'); // Default English

  Locale get locale => _locale;

  void setLocale(Locale locale) {
    if (!['en', 'bn'].contains(locale.languageCode)) return;
    _locale = locale;
    notifyListeners();
  }

  void toggleLanguage() {
    if (_locale.languageCode == 'bn') {
      _locale = const Locale('en');
    } else {
      _locale = const Locale('bn');
    }
    notifyListeners();
  }
}
