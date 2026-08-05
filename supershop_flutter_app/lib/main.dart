import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:provider/provider.dart';

import 'package:firebase_core/firebase_core.dart';
import 'localization/app_localizations.dart';
import 'providers/cart_provider.dart';
import 'providers/locale_provider.dart';
import 'providers/theme_provider.dart';
import 'screens/auth/login_screen.dart';
import 'screens/customer/home_screen.dart';

void main() async {
  WidgetsFlutterBinding.ensureInitialized();
  try {
    if (Firebase.apps.isEmpty) {
      await Firebase.initializeApp();
    }
  } catch (e) {
    debugPrint("Firebase initializeApp note: $e");
  }
  runApp(const SupershopApp());
}

class SupershopApp extends StatelessWidget {
  const SupershopApp({Key? key}) : super(key: key);

  @override
  Widget build(BuildContext context) {
    return MultiProvider(
      providers: [
        ChangeNotifierProvider(create: (_) => LocaleProvider()),
        ChangeNotifierProvider(create: (_) => CartProvider()),
        ChangeNotifierProvider(create: (_) => ThemeProvider()),
      ],
      child: Consumer2<LocaleProvider, ThemeProvider>(
        builder: (context, localeProv, themeProv, child) {
          return MaterialApp(
            title: 'DOINEEK Supershop',
            debugShowCheckedModeBanner: false,
            themeMode: themeProv.themeMode,
            theme: ThemeData(
              brightness: Brightness.light,
              primarySwatch: Colors.purple,
              primaryColor: const Color(0xFF6B21A8),
              useMaterial3: true,
              scaffoldBackgroundColor: const Color(0xFFFAF5FF),
              appBarTheme: const AppBarTheme(
                backgroundColor: Color(0xFF6B21A8),
                foregroundColor: Colors.white,
                elevation: 0,
              ),
              cardTheme: const CardThemeData(
                color: Colors.white,
                elevation: 2,
              ),
            ),
            darkTheme: ThemeData(
              brightness: Brightness.dark,
              primarySwatch: Colors.purple,
              primaryColor: const Color(0xFFA855F7),
              useMaterial3: true,
              scaffoldBackgroundColor: const Color(0xFF0F0716),
              appBarTheme: const AppBarTheme(
                backgroundColor: Color(0xFF2E1065),
                foregroundColor: Colors.white,
                elevation: 1,
                titleTextStyle: TextStyle(color: Colors.white, fontSize: 18, fontWeight: FontWeight.bold),
              ),
              cardTheme: CardThemeData(
                color: const Color(0xFF1E1033),
                elevation: 3,
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(12),
                  side: const BorderSide(color: Color(0xFF4C1D95), width: 1.2),
                ),
              ),
              dialogTheme: DialogThemeData(
                backgroundColor: const Color(0xFF1E1033),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(16),
                  side: const BorderSide(color: Color(0xFF6B21A8), width: 1.5),
                ),
              ),
              textTheme: const TextTheme(
                bodyLarge: TextStyle(color: Color(0xFFF3E8FF), fontSize: 16),
                bodyMedium: TextStyle(color: Color(0xFFE9D5FF), fontSize: 14),
                titleLarge: TextStyle(color: Colors.white, fontWeight: FontWeight.bold),
                titleMedium: TextStyle(color: Colors.white, fontWeight: FontWeight.w600),
                labelLarge: TextStyle(color: Colors.white, fontWeight: FontWeight.bold),
              ),
            ),
            locale: localeProv.locale,
            supportedLocales: const [
              Locale('bn', 'BD'),
              Locale('en', 'US'),
            ],
            localizationsDelegates: const [
              AppLocalizations.delegate,
              GlobalMaterialLocalizations.delegate,
              GlobalWidgetsLocalizations.delegate,
              GlobalCupertinoLocalizations.delegate,
            ],
            home: const HomeScreen(),
          );
        },
      ),
    );
  }
}
