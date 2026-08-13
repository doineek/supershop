// File generated for FirebaseOptions configuration
import 'package:firebase_core/firebase_core.dart' show FirebaseOptions;
import 'package:flutter/foundation.dart' show defaultTargetPlatform, kIsWeb, TargetPlatform;

class DefaultFirebaseOptions {
  static FirebaseOptions get currentPlatform {
    if (kIsWeb) {
      return web;
    }
    switch (defaultTargetPlatform) {
      case TargetPlatform.android:
        return android;
      case TargetPlatform.iOS:
        return ios;
      default:
        return web;
    }
  }

  static const FirebaseOptions web = FirebaseOptions(
    apiKey: 'AIzaSyC_PlaceholderKeyDoineekPos',
    appId: '1:112429894315291040152:web:doineekpose4023',
    messagingSenderId: '112429894315291040152',
    projectId: 'doineek-pos-e4023',
    authDomain: 'doineek-pos-e4023.firebaseapp.com',
    storageBucket: 'doineek-pos-e4023.appspot.com',
  );

  static const FirebaseOptions android = FirebaseOptions(
    apiKey: 'AIzaSyC_PlaceholderKeyDoineekPos',
    appId: '1:112429894315291040152:android:doineekpose4023',
    messagingSenderId: '112429894315291040152',
    projectId: 'doineek-pos-e4023',
    storageBucket: 'doineek-pos-e4023.appspot.com',
  );

  static const FirebaseOptions ios = FirebaseOptions(
    apiKey: 'AIzaSyC_PlaceholderKeyDoineekPos',
    appId: '1:112429894315291040152:ios:doineekpose4023',
    messagingSenderId: '112429894315291040152',
    projectId: 'doineek-pos-e4023',
    storageBucket: 'doineek-pos-e4023.appspot.com',
    iosBundleId: 'com.doineek.supershop',
  );
}
