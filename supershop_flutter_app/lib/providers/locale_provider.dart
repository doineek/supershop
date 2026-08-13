import 'package:flutter/material.dart';
import 'package:shared_preferences/shared_preferences.dart';

class LocaleProvider extends ChangeNotifier {
  Locale _locale = const Locale('en');

  Locale get locale => _locale;
  String get currentLanguageName => _locale.languageCode == 'bn' ? 'বাংলা (Bengali)' : 'English (US)';
  bool get isBengali => _locale.languageCode == 'bn';

  LocaleProvider() {
    _loadLocaleFromPrefs();
  }

  void _loadLocaleFromPrefs() async {
    final prefs = await SharedPreferences.getInstance();
    String code = prefs.getString('app_language_code') ?? 'en';
    _locale = Locale(code);
    notifyListeners();
  }

  void setLocale(Locale locale) async {
    if (!['en', 'bn'].contains(locale.languageCode)) return;
    _locale = locale;
    final prefs = await SharedPreferences.getInstance();
    await prefs.setString('app_language_code', locale.languageCode);
    notifyListeners();
  }

  void toggleLanguage() async {
    if (_locale.languageCode == 'bn') {
      setLocale(const Locale('en'));
    } else {
      setLocale(const Locale('bn'));
    }
  }
}
