import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';
import 'package:flutter_localizations/flutter_localizations.dart';
import 'package:provider/provider.dart';

import 'package:firebase_core/firebase_core.dart';
import 'firebase_options.dart';
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
      await Firebase.initializeApp(
        options: DefaultFirebaseOptions.currentPlatform,
      );
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
              scaffoldBackgroundColor: const Color(0xFF121215), // Soothing Slate Black
              appBarTheme: const AppBarTheme(
                backgroundColor: Color(0xFF1C1C21),
                foregroundColor: Color(0xFFF4F4F5),
                elevation: 0,
                titleTextStyle: TextStyle(color: Color(0xFFF4F4F5), fontSize: 18, fontWeight: FontWeight.bold),
              ),
              cardTheme: CardThemeData(
                color: const Color(0xFF1E1E24), // Soothing Slate Container
                elevation: 1,
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(12),
                  side: const BorderSide(color: Color(0xFF2E2E36), width: 1.0),
                ),
              ),
              dialogTheme: DialogThemeData(
                backgroundColor: const Color(0xFF1E1E24),
                shape: RoundedRectangleBorder(
                  borderRadius: BorderRadius.circular(16),
                  side: const BorderSide(color: Color(0xFF3F3F46), width: 1.0),
                ),
              ),
              bottomNavigationBarTheme: const BottomNavigationBarThemeData(
                backgroundColor: Color(0xFF1C1C21),
                selectedItemColor: Color(0xFFA855F7),
                unselectedItemColor: Color(0xFF71717A),
              ),
              dividerColor: const Color(0xFF27272A),
              textTheme: const TextTheme(
                bodyLarge: TextStyle(color: Color(0xFFF4F4F5), fontSize: 16),
                bodyMedium: TextStyle(color: Color(0xFFA1A1AA), fontSize: 14),
                titleLarge: TextStyle(color: Color(0xFFFAFAFA), fontWeight: FontWeight.bold),
                titleMedium: TextStyle(color: Color(0xFFF4F4F5), fontWeight: FontWeight.w600),
                labelLarge: TextStyle(color: Color(0xFFFAFAFA), fontWeight: FontWeight.bold),
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
