import 'dart:convert';
import 'dart:typed_data';
import 'package:flutter/material.dart';
import '../services/api_service.dart';

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

    // 1. If multiple images separated by ' || ' or comma before next image scheme, take the first
    if (clean.contains(' || ')) {
      clean = clean.split(' || ').first.trim();
    }
    final multiImgReg = RegExp(r',\s*(?=data:image\/|https?:\/\/|\/static\/|\/uploads\/)', caseSensitive: false);
    if (clean.contains(multiImgReg)) {
      clean = clean.split(multiImgReg).first.trim();
    } else if (clean.contains(',') && !clean.startsWith('data:image/')) {
      clean = clean.split(',').first.trim();
    }

    // 2. Google Images imgurl extraction: match imgurl parameter anywhere in URL
    final imgUrlMatch = RegExp(r'[?&#]imgurl=([^&#]+)').firstMatch(clean);
    if (imgUrlMatch != null) {
      try {
        String extracted = Uri.decodeComponent(imgUrlMatch.group(1)!);
        // Sometimes URL is double-encoded (e.g. %253A)
        if (extracted.contains('%3A') || extracted.contains('%2F') || extracted.contains('%25')) {
          try { extracted = Uri.decodeComponent(extracted); } catch (_) {}
        }
        if (extracted.startsWith('http://') || extracted.startsWith('https://')) {
          clean = extracted;
        }
      } catch (_) {}
    }

    // 3. Google redirect: match url or q parameter in google.com / google.com.bd / images.google.com
    if (clean.contains('google.') || clean.contains('goo.gl')) {
      final urlMatch = RegExp(r'[?&#](?:url|q)=(https?(?:%3A|:)[^&#]+)').firstMatch(clean);
      if (urlMatch != null) {
        try {
          String extracted = Uri.decodeComponent(urlMatch.group(1)!);
          if (extracted.contains('%3A') || extracted.contains('%2F')) {
            try { extracted = Uri.decodeComponent(extracted); } catch (_) {}
          }
          if (extracted.startsWith('http://') || extracted.startsWith('https://')) {
            clean = extracted;
          }
        } catch (_) {}
      }
    }

    // 4. Google Drive direct embed link: https://drive.google.com/file/d/<id>/view...
    if (clean.contains('drive.google.com/file/d/')) {
      try {
        final parts = clean.split('/file/d/');
        if (parts.length > 1) {
          final id = parts[1].split('/')[0].split('?')[0];
          if (id.isNotEmpty) {
            clean = 'https://drive.google.com/uc?export=view&id=$id';
          }
        }
      } catch (_) {}
    } else if (clean.contains('drive.google.com/open?id=')) {
      try {
        final id = clean.split('id=')[1].split('&')[0];
        if (id.isNotEmpty) {
          clean = 'https://drive.google.com/uc?export=view&id=$id';
        }
      } catch (_) {}
    }

    // 5. Handle relative server paths using active dynamic ApiService.baseUrl
    bool isRawBase64 = clean.startsWith('/9j/') || clean.startsWith('iVBORw0KGgo');
    if (!clean.startsWith('data:image/') && !isRawBase64 && !clean.startsWith('http://') && !clean.startsWith('https://')) {
      final base = ApiService.baseUrl.replaceAll(RegExp(r'/+$'), '');
      if (clean.startsWith('/')) {
        clean = '$base$clean';
      } else {
        clean = '$base/$clean';
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
        // In case another image was appended with a comma
        if (base64Data.contains(',')) {
          base64Data = base64Data.split(',').first.trim();
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

    // 2. Handle Network Images with standard safe browser headers (NO AVIF to ensure Android Skia compatibility)
    return Image.network(
      clean,
      width: width,
      height: height,
      fit: fit,
      headers: const {
        'User-Agent':
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36',
        'Accept': 'image/jpeg,image/png,image/webp,*/*;q=0.8',
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
