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

  /// Cleans and resolves any image URL (Google Images, Google Drive, relative paths, comma lists)
  static String cleanUrl(String raw) {
    String clean = raw.trim();
    if (clean.isEmpty) return clean;

    // 1. If multiple comma-separated URLs, take the first one
    if (clean.contains(',') && !clean.startsWith('data:image/')) {
      clean = clean.split(',').first.trim();
    }

    // 2. Google Images imgurl extraction: https://www.google.com/imgres?imgurl=...
    if (clean.contains('google.') && clean.contains('imgres')) {
      try {
        final uri = Uri.parse(clean);
        final imgParam = uri.queryParameters['imgurl'];
        if (imgParam != null && imgParam.isNotEmpty) {
          clean = Uri.decodeComponent(imgParam);
        }
      } catch (_) {}
    }

    // 3. Google redirect: https://www.google.com/url?url=... or q=...
    if (clean.contains('google.') && clean.contains('/url')) {
      try {
        final uri = Uri.parse(clean);
        final u = uri.queryParameters['url'] ?? uri.queryParameters['q'];
        if (u != null && u.isNotEmpty) {
          clean = Uri.decodeComponent(u);
        }
      } catch (_) {}
    }

    // 4. Google Drive direct embed link: https://drive.google.com/file/d/<id>/view...
    if (clean.contains('drive.google.com/file/d/')) {
      try {
        final parts = clean.split('/file/d/');
        if (parts.length > 1) {
          final id = parts[1].split('/')[0];
          if (id.isNotEmpty) {
            clean = 'https://drive.google.com/uc?export=view&id=$id';
          }
        }
      } catch (_) {}
    }

    // 5. Handle relative server paths
    if (!clean.startsWith('data:image/') && !clean.startsWith('http://') && !clean.startsWith('https://')) {
      if (clean.startsWith('/')) {
        clean = 'https://doineek.onrender.com$clean';
      } else {
        clean = 'https://doineek.onrender.com/$clean';
      }
    }

    return clean;
  }

  @override
  Widget build(BuildContext context) {
    final String clean = cleanUrl(imageUrl);
    if (clean.isEmpty) {
      return _buildPlaceholder();
    }

    // 1. Handle Base64 Data URI or raw base64 string
    if (clean.startsWith('data:image/') ||
        (clean.length > 100 &&
            !clean.startsWith('http') &&
            (clean.startsWith('/9j/') || clean.startsWith('iVBORw')))) {
      try {
        String base64Data = clean;
        final int commaIdx = clean.indexOf(',');
        if (commaIdx != -1) {
          base64Data = clean.substring(commaIdx + 1);
        }
        base64Data = base64Data.replaceAll(RegExp(r'\s+'), '');
        final Uint8List bytes = base64Decode(base64Data);
        return Image.memory(
          bytes,
          width: width,
          height: height,
          fit: fit,
          errorBuilder: (ctx, err, stack) => _buildPlaceholder(),
        );
      } catch (_) {
        return _buildPlaceholder();
      }
    }

    // 2. Handle Network Images with standard browser headers so Google / CDNs never block requests
    return Image.network(
      clean,
      width: width,
      height: height,
      fit: fit,
      headers: const {
        'User-Agent':
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36',
        'Accept': 'image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
      },
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
