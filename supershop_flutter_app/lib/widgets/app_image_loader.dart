import 'dart:convert';
import 'dart:typed_data';
import 'package:flutter/material.dart';

class AppImageLoader extends StatelessWidget {
  final String imageUrl;
  final double? width;
  final double? height;
  final BoxFit fit;
  final String placeholderAsset;

  const AppImageLoader({
    Key? key,
    required this.imageUrl,
    this.width,
    this.height,
    this.fit = BoxFit.contain,
    this.placeholderAsset = 'assets/images/logo.png',
  }) : super(key: key);

  @override
  Widget build(BuildContext context) {
    final String clean = imageUrl.trim();
    if (clean.isEmpty) {
      return _buildPlaceholder();
    }

    // 1. Handle Base64 Data URI
    if (clean.startsWith('data:image/')) {
      try {
        final int commaIdx = clean.indexOf(',');
        if (commaIdx != -1) {
          final String base64Data = clean.substring(commaIdx + 1);
          final Uint8List bytes = base64Decode(base64Data);
          return Image.memory(
            bytes,
            width: width,
            height: height,
            fit: fit,
            errorBuilder: (ctx, err, stack) => _buildPlaceholder(),
          );
        }
      } catch (_) {
        return _buildPlaceholder();
      }
    }

    // 2. Handle HTTP/HTTPS or relative URLs
    String finalUrl = clean;
    if (!finalUrl.startsWith('http://') && !finalUrl.startsWith('https://')) {
      if (finalUrl.startsWith('/')) {
        finalUrl = 'https://doineek.onrender.com';
      }
    }

    return Image.network(
      finalUrl,
      width: width,
      height: height,
      fit: fit,
      errorBuilder: (ctx, err, stack) => _buildPlaceholder(),
      loadingBuilder: (ctx, child, progress) {
        if (progress == null) return child;
        return Center(
          child: SizedBox(
            width: 18,
            height: 18,
            child: CircularProgressIndicator(
              strokeWidth: 2,
              value: progress.expectedTotalBytes != null
                  ? progress.cumulativeBytesLoaded / (progress.expectedTotalBytes ?? 1)
                  : null,
            ),
          ),
        );
      },
    );
  }

  Widget _buildPlaceholder() {
    return Image.asset(
      placeholderAsset,
      width: width,
      height: height,
      fit: fit,
      errorBuilder: (ctx, err, stack) => Icon(
        Icons.shopping_bag_outlined,
        size: (width != null && width! > 0) ? width! * 0.45 : 28,
        color: Colors.grey[400],
      ),
    );
  }
}
