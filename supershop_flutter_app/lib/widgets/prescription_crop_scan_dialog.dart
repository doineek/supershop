import 'dart:async';
import 'dart:convert';
import 'dart:math' as math;
import 'dart:ui' as ui;
import 'package:flutter/foundation.dart';
import 'package:flutter/material.dart';

class PrescriptionEditResult {
  final Uint8List processedBytes;
  final String processedDataUri;
  final String filterName;
  final bool isCropped;

  const PrescriptionEditResult({
    required this.processedBytes,
    required this.processedDataUri,
    required this.filterName,
    required this.isCropped,
  });
}

class _PerspectiveWarpTask {
  final Uint8List srcRgba;
  final int srcW;
  final int srcH;
  final List<double> cornerPts; // [x0,y0, x1,y1, x2,y2, x3,y3] in src px
  final int dstW;
  final int dstH;

  const _PerspectiveWarpTask({
    required this.srcRgba,
    required this.srcW,
    required this.srcH,
    required this.cornerPts,
    required this.dstW,
    required this.dstH,
  });
}

List<double> _solveHomography8x8(List<double> cornerPts, int dstW, int dstH) {
  final src = <List<double>>[
    [cornerPts[0], cornerPts[1]],
    [cornerPts[2], cornerPts[3]],
    [cornerPts[4], cornerPts[5]],
    [cornerPts[6], cornerPts[7]],
  ];
  final dst = <List<double>>[
    [0.0, 0.0],
    [dstW.toDouble(), 0.0],
    [dstW.toDouble(), dstH.toDouble()],
    [0.0, dstH.toDouble()],
  ];

  final A = <List<double>>[];
  final B = <double>[];
  for (int i = 0; i < 4; i++) {
    final double sx = src[i][0];
    final double sy = src[i][1];
    final double dx = dst[i][0];
    final double dy = dst[i][1];
    A.add([dx, dy, 1.0, 0.0, 0.0, 0.0, -dx * sx, -dy * sx]);
    B.add(sx);
    A.add([0.0, 0.0, 0.0, dx, dy, 1.0, -dx * sy, -dy * sy]);
    B.add(sy);
  }

  for (int i = 0; i < 8; i++) {
    int maxRow = i;
    for (int r = i + 1; r < 8; r++) {
      if (A[r][i].abs() > A[maxRow][i].abs()) maxRow = r;
    }
    final tmpA = A[i];
    A[i] = A[maxRow];
    A[maxRow] = tmpA;
    final tmpB = B[i];
    B[i] = B[maxRow];
    B[maxRow] = tmpB;

    for (int r = i + 1; r < 8; r++) {
      final double denom = A[i][i].abs() < 1e-12 ? 1e-12 : A[i][i];
      final double c = A[r][i] / denom;
      for (int j = i; j < 8; j++) {
        A[r][j] -= c * A[i][j];
      }
      B[r] -= c * B[i];
    }
  }

  final h = List<double>.filled(8, 0.0);
  for (int i = 7; i >= 0; i--) {
    double s = B[i];
    for (int j = i + 1; j < 8; j++) {
      s -= A[i][j] * h[j];
    }
    final double denom = A[i][i].abs() < 1e-12 ? 1e-12 : A[i][i];
    h[i] = s / denom;
  }
  return h;
}

Uint8List _warpPerspectiveIsolate(_PerspectiveWarpTask task) {
  final int sw = task.srcW;
  final int sh = task.srcH;
  final int dw = task.dstW;
  final int dh = task.dstH;
  final src = task.srcRgba;
  final dst = Uint8List(dw * dh * 4);

  final h = _solveHomography8x8(task.cornerPts, dw, dh);
  final double h0 = h[0], h1 = h[1], h2 = h[2], h3 = h[3];
  final double h4 = h[4], h5 = h[5], h6 = h[6], h7 = h[7];

  final int maxX = sw - 1;
  final int maxY = sh - 1;
  int idx = 0;

  for (int y = 0; y < dh; y++) {
    final double hy1 = h1 * y + h2;
    final double hy4 = h4 * y + h5;
    final double hy7 = h7 * y + 1.0;
    for (int x = 0; x < dw; x++) {
      final double w = 1.0 / (h6 * x + hy7);
      double u = (h0 * x + hy1) * w;
      double v = (h3 * x + hy4) * w;
      if (u < 0.0) {
        u = 0.0;
      } else if (u > maxX) {
        u = maxX.toDouble();
      }
      if (v < 0.0) {
        v = 0.0;
      } else if (v > maxY) {
        v = maxY.toDouble();
      }

      final int x0 = u.floor();
      final int y0 = v.floor();
      final int x1 = x0 < maxX ? x0 + 1 : maxX;
      final int y1 = y0 < maxY ? y0 + 1 : maxY;
      final double fx = u - x0;
      final double fy = v - y0;
      final double w00 = (1.0 - fx) * (1.0 - fy);
      final double w10 = fx * (1.0 - fy);
      final double w01 = (1.0 - fx) * fy;
      final double w11 = fx * fy;

      final int row0 = y0 * sw;
      final int row1 = y1 * sw;
      final int i00 = (row0 + x0) << 2;
      final int i10 = (row0 + x1) << 2;
      final int i01 = (row1 + x0) << 2;
      final int i11 = (row1 + x1) << 2;

      dst[idx] = (src[i00] * w00 + src[i10] * w10 + src[i01] * w01 + src[i11] * w11 + 0.5).toInt().clamp(0, 255);
      dst[idx + 1] = (src[i00 + 1] * w00 + src[i10 + 1] * w10 + src[i01 + 1] * w01 + src[i11 + 1] * w11 + 0.5).toInt().clamp(0, 255);
      dst[idx + 2] = (src[i00 + 2] * w00 + src[i10 + 2] * w10 + src[i01 + 2] * w01 + src[i11 + 2] * w11 + 0.5).toInt().clamp(0, 255);
      dst[idx + 3] = 255;
      idx += 4;
    }
  }
  return dst;
}

/// Interactive pure-Flutter Prescription 4-Corner Perspective Rectifier, Free Crop,
/// 90° Rotation & CamScan Enhancer dialog.
class PrescriptionCropScanDialog extends StatefulWidget {
  final Uint8List imageBytes;

  const PrescriptionCropScanDialog({
    Key? key,
    required this.imageBytes,
  }) : super(key: key);

  static Future<PrescriptionEditResult?> show(
    BuildContext context,
    Uint8List imageBytes,
  ) {
    return Navigator.of(context).push<PrescriptionEditResult>(
      MaterialPageRoute(
        fullscreenDialog: true,
        builder: (_) => PrescriptionCropScanDialog(imageBytes: imageBytes),
      ),
    );
  }

  @override
  State<PrescriptionCropScanDialog> createState() =>
      _PrescriptionCropScanDialogState();
}

class _PrescriptionCropScanDialogState
    extends State<PrescriptionCropScanDialog> {
  ui.Image? _decodedImage;
  bool _isSaving = false;

  // 'perspective' = 4-corner free tilt warp | 'free' = free rectangular draw/resize
  String _cropMode = 'perspective';

  // Normalized corner points in rotated display space (0..1): TL, TR, BR, BL
  List<Offset> _corners = const [
    Offset(0.0, 0.0),
    Offset(1.0, 0.0),
    Offset(1.0, 1.0),
    Offset(0.0, 1.0),
  ];

  int _quarterTurns = 0;
  String _selectedFilter = 'magic_color';
  Offset? _freeDrawAnchor;
  int? _activeCornerIdx;

  static const double _minCropSpan = 0.08;

  @override
  void initState() {
    super.initState();
    _decodeSourceImage();
  }

  Future<void> _decodeSourceImage() async {
    final completer = Completer<ui.Image>();
    ui.decodeImageFromList(widget.imageBytes, (img) => completer.complete(img));
    final img = await completer.future;
    if (mounted) {
      setState(() => _decodedImage = img);
    }
  }

  List<double>? _colorMatrixFor(String fx) {
    switch (fx) {
      case 'magic_color':
        const double c = 1.38;
        const double t = -32.0;
        return <double>[
          c, 0, 0, 0, t,
          0, c, 0, 0, t,
          0, 0, c, 0, t,
          0, 0, 0, 1, 0,
        ];
      case 'bw_scan':
        const double c = 1.65;
        const double t = -68.0;
        const double r = 0.299 * c;
        const double g = 0.587 * c;
        const double b = 0.114 * c;
        return <double>[
          r, g, b, 0, t,
          r, g, b, 0, t,
          r, g, b, 0, t,
          0, 0, 0, 1, 0,
        ];
      case 'bright':
        const double c = 1.15;
        const double t = 18.0;
        return <double>[
          c, 0, 0, 0, t,
          0, c, 0, 0, t,
          0, 0, c, 0, t,
          0, 0, 0, 1, 0,
        ];
      default:
        return null;
    }
  }

  void _resetFullSize() {
    setState(() {
      _corners = const [
        Offset(0.0, 0.0),
        Offset(1.0, 0.0),
        Offset(1.0, 1.0),
        Offset(0.0, 1.0),
      ];
    });
  }

  void _rotate90() {
    setState(() {
      _quarterTurns = (_quarterTurns + 1) % 4;
      _corners = const [
        Offset(0.0, 0.0),
        Offset(1.0, 0.0),
        Offset(1.0, 1.0),
        Offset(0.0, 1.0),
      ];
    });
  }

  void _setCropMode(String mode) {
    setState(() {
      _cropMode = mode;
      if (mode == 'free') {
        final s = _sortQuadClockwise(_corners);
        final minX = s.map((p) => p.dx).reduce(math.min).clamp(0.0, 1.0 - _minCropSpan);
        final maxX = s.map((p) => p.dx).reduce(math.max).clamp(minX + _minCropSpan, 1.0);
        final minY = s.map((p) => p.dy).reduce(math.min).clamp(0.0, 1.0 - _minCropSpan);
        final maxY = s.map((p) => p.dy).reduce(math.max).clamp(minY + _minCropSpan, 1.0);
        _corners = [
          Offset(minX, minY),
          Offset(maxX, minY),
          Offset(maxX, maxY),
          Offset(minX, maxY),
        ];
      }
    });
  }

  bool get _hasCrop {
    const eps = 0.012;
    return (_corners[0] - const Offset(0, 0)).distance > eps ||
        (_corners[1] - const Offset(1, 0)).distance > eps ||
        (_corners[2] - const Offset(1, 1)).distance > eps ||
        (_corners[3] - const Offset(0, 1)).distance > eps;
  }

  List<Offset> _sortQuadClockwise(List<Offset> pts) {
    if (pts.length != 4) return pts;
    double cx = 0, cy = 0;
    for (final p in pts) {
      cx += p.dx;
      cy += p.dy;
    }
    cx /= 4.0;
    cy /= 4.0;
    final sorted = List<Offset>.from(pts)
      ..sort((a, b) => math.atan2(a.dy - cy, a.dx - cx).compareTo(math.atan2(b.dy - cy, b.dx - cx)));
    int tlIdx = 0;
    double best = double.infinity;
    for (int i = 0; i < 4; i++) {
      final score = sorted[i].dx + sorted[i].dy;
      if (score < best) {
        best = score;
        tlIdx = i;
      }
    }
    return [
      sorted[tlIdx],
      sorted[(tlIdx + 1) % 4],
      sorted[(tlIdx + 2) % 4],
      sorted[(tlIdx + 3) % 4],
    ];
  }

  bool _isAxisAlignedRect(List<Offset> c) {
    const tol = 0.008;
    return (c[0].dy - c[1].dy).abs() < tol &&
        (c[3].dy - c[2].dy).abs() < tol &&
        (c[0].dx - c[3].dx).abs() < tol &&
        (c[1].dx - c[2].dx).abs() < tol;
  }

  bool _pointInPoly(Offset p, List<Offset> poly) {
    bool inside = false;
    for (int i = 0, j = poly.length - 1; i < poly.length; j = i++) {
      final xi = poly[i].dx, yi = poly[i].dy;
      final xj = poly[j].dx, yj = poly[j].dy;
      final denom = (yj - yi).abs() < 1e-9 ? 1e-9 : (yj - yi);
      final intersect = ((yi > p.dy) != (yj > p.dy)) &&
          (p.dx < (xj - xi) * (p.dy - yi) / denom + xi);
      if (intersect) inside = !inside;
    }
    return inside;
  }

  Future<ui.Image> _decodeRgbaImage(Uint8List rgba, int w, int h) {
    final c = Completer<ui.Image>();
    ui.decodeImageFromPixels(rgba, w, h, ui.PixelFormat.rgba8888, c.complete);
    return c.future;
  }

  Future<void> _applyAndReturn() async {
    final src = _decodedImage;
    if (src == null || _isSaving) return;

    if (!_hasCrop && _quarterTurns == 0 && _selectedFilter == 'original') {
      final b64 = "data:image/jpeg;base64,${base64Encode(widget.imageBytes)}";
      Navigator.pop(
        context,
        PrescriptionEditResult(
          processedBytes: widget.imageBytes,
          processedDataUri: b64,
          filterName: _selectedFilter,
          isCropped: false,
        ),
      );
      return;
    }

    setState(() => _isSaving = true);
    try {
      final bool isOddTurn = _quarterTurns % 2 == 1;
      final double rotW = (isOddTurn ? src.height : src.width).toDouble();
      final double rotH = (isOddTurn ? src.width : src.height).toDouble();

      ui.Image rotatedImg = src;
      if (_quarterTurns != 0) {
        final rotRecorder = ui.PictureRecorder();
        final rotCanvas = Canvas(rotRecorder, Rect.fromLTWH(0, 0, rotW, rotH));
        rotCanvas.translate(rotW / 2, rotH / 2);
        rotCanvas.rotate(_quarterTurns * math.pi / 2);
        rotCanvas.translate(-src.width / 2, -src.height / 2);
        rotCanvas.drawImage(src, Offset.zero, Paint()..filterQuality = FilterQuality.high);
        rotatedImg = await rotRecorder.endRecording().toImage(rotW.round(), rotH.round());
      }

      final ordered = _sortQuadClockwise(_corners);
      final bool straightRect = _isAxisAlignedRect(ordered);
      const double maxOutDim = 2000.0;

      late ui.Image baseOutImage;

      if (straightRect) {
        final double srcL = (ordered[0].dx * rotW).clamp(0.0, rotW - 10);
        final double srcT = (ordered[0].dy * rotH).clamp(0.0, rotH - 10);
        final double srcR = (ordered[2].dx * rotW).clamp(srcL + 10, rotW);
        final double srcB = (ordered[2].dy * rotH).clamp(srcT + 10, rotH);
        double outW = srcR - srcL;
        double outH = srcB - srcT;
        if (outW > maxOutDim || outH > maxOutDim) {
          final double sc = maxOutDim / math.max(outW, outH);
          outW = (outW * sc).roundToDouble();
          outH = (outH * sc).roundToDouble();
        }
        final int finalW = math.max(16, outW.round());
        final int finalH = math.max(16, outH.round());

        final rec = ui.PictureRecorder();
        final cvs = Canvas(rec, Rect.fromLTWH(0, 0, finalW.toDouble(), finalH.toDouble()));
        final paint = Paint()..filterQuality = FilterQuality.high;
        final matrix = _colorMatrixFor(_selectedFilter);
        if (matrix != null) {
          paint.colorFilter = ColorFilter.matrix(matrix);
        }
        cvs.drawImageRect(
          rotatedImg,
          Rect.fromLTWH(srcL, srcT, srcR - srcL, srcB - srcT),
          Rect.fromLTWH(0, 0, finalW.toDouble(), finalH.toDouble()),
          paint,
        );
        baseOutImage = await rec.endRecording().toImage(finalW, finalH);
      } else {
        // 4-Corner Perspective Homography Rectification via Isolate bilinear sampling
        final rgbaData = await rotatedImg.toByteData(format: ui.ImageByteFormat.rawRgba);
        if (rgbaData == null) {
          throw Exception('RGBA read failed');
        }
        final List<double> pxPts = [
          ordered[0].dx * rotW, ordered[0].dy * rotH,
          ordered[1].dx * rotW, ordered[1].dy * rotH,
          ordered[2].dx * rotW, ordered[2].dy * rotH,
          ordered[3].dx * rotW, ordered[3].dy * rotH,
        ];
        final double wTop = math.sqrt(math.pow(pxPts[2] - pxPts[0], 2) + math.pow(pxPts[3] - pxPts[1], 2));
        final double wBot = math.sqrt(math.pow(pxPts[4] - pxPts[6], 2) + math.pow(pxPts[5] - pxPts[7], 2));
        final double hLeft = math.sqrt(math.pow(pxPts[6] - pxPts[0], 2) + math.pow(pxPts[7] - pxPts[1], 2));
        final double hRight = math.sqrt(math.pow(pxPts[4] - pxPts[2], 2) + math.pow(pxPts[5] - pxPts[3], 2));

        double outW = math.max(120.0, math.max(wTop, wBot));
        double outH = math.max(120.0, math.max(hLeft, hRight));
        if (outW > maxOutDim || outH > maxOutDim) {
          final double sc = maxOutDim / math.max(outW, outH);
          outW = (outW * sc).roundToDouble();
          outH = (outH * sc).roundToDouble();
        }
        final int finalW = math.max(16, outW.round());
        final int finalH = math.max(16, outH.round());

        final warpedRgba = await compute(
          _warpPerspectiveIsolate,
          _PerspectiveWarpTask(
            srcRgba: rgbaData.buffer.asUint8List(),
            srcW: rotW.round(),
            srcH: rotH.round(),
            cornerPts: pxPts,
            dstW: finalW,
            dstH: finalH,
          ),
        );
        final warpedImg = await _decodeRgbaImage(warpedRgba, finalW, finalH);
        final matrix = _colorMatrixFor(_selectedFilter);
        if (matrix != null) {
          final rec = ui.PictureRecorder();
          final cvs = Canvas(rec, Rect.fromLTWH(0, 0, finalW.toDouble(), finalH.toDouble()));
          cvs.drawImage(
            warpedImg,
            Offset.zero,
            Paint()
              ..filterQuality = FilterQuality.high
              ..colorFilter = ColorFilter.matrix(matrix),
          );
          baseOutImage = await rec.endRecording().toImage(finalW, finalH);
          warpedImg.dispose();
        } else {
          baseOutImage = warpedImg;
        }
      }

      final byteData = await baseOutImage.toByteData(format: ui.ImageByteFormat.png);
      if (rotatedImg != src) rotatedImg.dispose();
      baseOutImage.dispose();

      if (byteData == null) {
        if (mounted) setState(() => _isSaving = false);
        return;
      }

      final pngBytes = byteData.buffer.asUint8List();
      final dataUri = "data:image/png;base64,${base64Encode(pngBytes)}";
      if (!mounted) return;
      Navigator.pop(
        context,
        PrescriptionEditResult(
          processedBytes: pngBytes,
          processedDataUri: dataUri,
          filterName: _selectedFilter,
          isCropped: _hasCrop,
        ),
      );
    } catch (e) {
      debugPrint("Prescription edit error: $e");
      if (mounted) {
        setState(() => _isSaving = false);
        ScaffoldMessenger.of(context).showSnackBar(
          const SnackBar(content: Text("ছবি প্রসেস করতে সমস্যা হয়েছে। আবার চেষ্টা করুন।")),
        );
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final matrix = _colorMatrixFor(_selectedFilter);

    return Scaffold(
      backgroundColor: const Color(0xFF020617),
      appBar: AppBar(
        backgroundColor: const Color(0xFF0F172A),
        foregroundColor: Colors.white,
        title: const Text(
          "✂️ ৪-কোনা ক্রপ ও CamScan",
          style: TextStyle(fontSize: 15, fontWeight: FontWeight.w800),
        ),
        actions: [
          TextButton.icon(
            onPressed: _isSaving ? null : _resetFullSize,
            icon: const Icon(Icons.fit_screen, color: Color(0xFF6EE7B7), size: 18),
            label: const Text(
              "ফুল সাইজ",
              style: TextStyle(color: Color(0xFF6EE7B7), fontWeight: FontWeight.bold, fontSize: 12),
            ),
          ),
          IconButton(
            onPressed: _isSaving ? null : _rotate90,
            icon: const Icon(Icons.rotate_90_degrees_cw, color: Colors.white),
            tooltip: "ঘোরান (90°)",
          ),
        ],
      ),
      body: Column(
        children: [
          // Mode Selector: 4-Corner Tilt Crop vs Free Draw Crop
          Container(
            color: const Color(0xFF1E293B),
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 8),
            child: Column(
              children: [
                Row(
                  children: [
                    Expanded(
                      child: InkWell(
                        onTap: () => _setCropMode('perspective'),
                        child: Container(
                          padding: const EdgeInsets.symmetric(vertical: 7),
                          decoration: BoxDecoration(
                            color: _cropMode == 'perspective'
                                ? const Color(0xFF059669)
                                : const Color(0xFF0F172A),
                            borderRadius: BorderRadius.circular(8),
                            border: Border.all(
                              color: _cropMode == 'perspective'
                                  ? const Color(0xFF34D399)
                                  : const Color(0xFF334155),
                            ),
                          ),
                          child: Text(
                            "📐 ৪-কোনা ক্রপ (আঁকাবাঁকা)",
                            textAlign: TextAlign.center,
                            style: TextStyle(
                              color: _cropMode == 'perspective' ? Colors.white : const Color(0xFFCBD5E1),
                              fontSize: 11.5,
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                        ),
                      ),
                    ),
                    const SizedBox(width: 8),
                    Expanded(
                      child: InkWell(
                        onTap: () => _setCropMode('free'),
                        child: Container(
                          padding: const EdgeInsets.symmetric(vertical: 7),
                          decoration: BoxDecoration(
                            color: _cropMode == 'free'
                                ? const Color(0xFF059669)
                                : const Color(0xFF0F172A),
                            borderRadius: BorderRadius.circular(8),
                            border: Border.all(
                              color: _cropMode == 'free'
                                  ? const Color(0xFF34D399)
                                  : const Color(0xFF334155),
                            ),
                          ),
                          child: Text(
                            "⬜ ফ্রি ক্রপ (টেনে মাপ)",
                            textAlign: TextAlign.center,
                            style: TextStyle(
                              color: _cropMode == 'free' ? Colors.white : const Color(0xFFCBD5E1),
                              fontSize: 11.5,
                              fontWeight: FontWeight.bold,
                            ),
                          ),
                        ),
                      ),
                    ),
                  ],
                ),
                const SizedBox(height: 5),
                Text(
                  _cropMode == 'perspective'
                      ? "যেকোনো বাঁকা প্রেসক্রিপশনের ৪ কোণা ধরে কোণায় বসান — অটো সোজা হয়ে যাবে"
                      : "ছবির যেকোনো অংশে আঙুল টেনে আপনার খুশিমতো মাপে ক্রপ করুন",
                  textAlign: TextAlign.center,
                  style: const TextStyle(color: Color(0xFF94A3B8), fontSize: 10.5),
                ),
              ],
            ),
          ),

          // Interactive Image + 4-Corner / Free Crop Area
          Expanded(
            child: _decodedImage == null
                ? const Center(
                    child: CircularProgressIndicator(color: Color(0xFF10B981)),
                  )
                : Padding(
                    padding: const EdgeInsets.all(14),
                    child: LayoutBuilder(
                      builder: (context, constraints) {
                        final src = _decodedImage!;
                        final bool odd = _quarterTurns % 2 == 1;
                        final double imgW = (odd ? src.height : src.width).toDouble();
                        final double imgH = (odd ? src.width : src.height).toDouble();
                        final double imgAspect = imgW / imgH;

                        double dispW = constraints.maxWidth;
                        double dispH = dispW / imgAspect;
                        if (dispH > constraints.maxHeight) {
                          dispH = constraints.maxHeight;
                          dispW = dispH * imgAspect;
                        }

                        final cPx = _corners
                            .map((c) => Offset(c.dx * dispW, c.dy * dispH))
                            .toList();

                        return Center(
                          child: SizedBox(
                            width: dispW,
                            height: dispH,
                            child: Stack(
                              clipBehavior: Clip.none,
                              children: [
                                // Preview image with live Rotation + CamScan filter
                                Positioned.fill(
                                  child: ColorFiltered(
                                    colorFilter: matrix != null
                                        ? ColorFilter.matrix(matrix)
                                        : const ColorFilter.mode(
                                            Colors.transparent,
                                            BlendMode.dst,
                                          ),
                                    child: RotatedBox(
                                      quarterTurns: _quarterTurns,
                                      child: Image.memory(
                                        widget.imageBytes,
                                        fit: BoxFit.fill,
                                      ),
                                    ),
                                  ),
                                ),

                                // Dark mask + crisp emerald quad frame + bilinear 3x3 guide lines
                                Positioned.fill(
                                  child: IgnorePointer(
                                    child: CustomPaint(
                                      painter: _QuadOverlayPainter(cPx),
                                    ),
                                  ),
                                ),

                                // Surface drag: draw new box in free mode OR move quad body
                                Positioned.fill(
                                  child: GestureDetector(
                                    behavior: HitTestBehavior.translucent,
                                    onPanStart: (d) {
                                      final nx = (d.localPosition.dx / dispW).clamp(0.0, 1.0);
                                      final ny = (d.localPosition.dy / dispH).clamp(0.0, 1.0);
                                      final pt = Offset(nx, ny);
                                      if (_cropMode == 'free' &&
                                          (!_hasCrop || !_pointInPoly(pt, _corners))) {
                                        _freeDrawAnchor = pt;
                                      } else {
                                        _freeDrawAnchor = null;
                                      }
                                    },
                                    onPanUpdate: (d) {
                                      if (_cropMode == 'free' && _freeDrawAnchor != null) {
                                        final curX = (d.localPosition.dx / dispW).clamp(0.0, 1.0);
                                        final curY = (d.localPosition.dy / dispH).clamp(0.0, 1.0);
                                        final minX = math.min(_freeDrawAnchor!.dx, curX);
                                        final maxX = math.max(minX + _minCropSpan, math.max(_freeDrawAnchor!.dx, curX)).clamp(0.0, 1.0);
                                        final minY = math.min(_freeDrawAnchor!.dy, curY);
                                        final maxY = math.max(minY + _minCropSpan, math.max(_freeDrawAnchor!.dy, curY)).clamp(0.0, 1.0);
                                        setState(() {
                                          _corners = [
                                            Offset(minX, minY),
                                            Offset(maxX, minY),
                                            Offset(maxX, maxY),
                                            Offset(minX, maxY),
                                          ];
                                        });
                                        return;
                                      }

                                      final dx = d.delta.dx / dispW;
                                      final dy = d.delta.dy / dispH;
                                      final minX = _corners.map((p) => p.dx).reduce(math.min);
                                      final maxX = _corners.map((p) => p.dx).reduce(math.max);
                                      final minY = _corners.map((p) => p.dy).reduce(math.min);
                                      final maxY = _corners.map((p) => p.dy).reduce(math.max);
                                      final clampedDx = dx.clamp(-minX, 1.0 - maxX);
                                      final clampedDy = dy.clamp(-minY, 1.0 - maxY);
                                      setState(() {
                                        _corners = _corners
                                            .map((p) => Offset(
                                                  (p.dx + clampedDx).clamp(0.0, 1.0),
                                                  (p.dy + clampedDy).clamp(0.0, 1.0),
                                                ))
                                            .toList();
                                      });
                                    },
                                    onPanEnd: (_) => _freeDrawAnchor = null,
                                  ),
                                ),

                                // 4 Independent Corner Drag Handles
                                for (int idx = 0; idx < 4; idx++)
                                  _buildCornerHandle(
                                    x: cPx[idx].dx,
                                    y: cPx[idx].dy,
                                    isActive: _activeCornerIdx == idx,
                                    onStart: () => setState(() => _activeCornerIdx = idx),
                                    onEnd: () => setState(() => _activeCornerIdx = null),
                                    onDrag: (dx, dy) {
                                      setState(() {
                                        final updated = List<Offset>.from(_corners);
                                        final nx = (updated[idx].dx + dx / dispW).clamp(0.0, 1.0);
                                        final ny = (updated[idx].dy + dy / dispH).clamp(0.0, 1.0);
                                        if (_cropMode == 'free') {
                                          // Keep rectangular when dragging corners in Free Crop mode
                                          updated[idx] = Offset(nx, ny);
                                          if (idx == 0) {
                                            updated[1] = Offset(updated[1].dx, ny);
                                            updated[3] = Offset(nx, updated[3].dy);
                                          } else if (idx == 1) {
                                            updated[0] = Offset(updated[0].dx, ny);
                                            updated[2] = Offset(nx, updated[2].dy);
                                          } else if (idx == 2) {
                                            updated[3] = Offset(updated[3].dx, ny);
                                            updated[1] = Offset(nx, updated[1].dy);
                                          } else if (idx == 3) {
                                            updated[2] = Offset(updated[2].dx, ny);
                                            updated[0] = Offset(nx, updated[0].dy);
                                          }
                                        } else {
                                          // 4-Corner free perspective corner placement
                                          updated[idx] = Offset(nx, ny);
                                        }
                                        _corners = updated;
                                      });
                                    },
                                  ),
                              ],
                            ),
                          ),
                        );
                      },
                    ),
                  ),
          ),

          // Bottom CamScan Filters & Confirm Bar
          Container(
            padding: const EdgeInsets.fromLTRB(12, 10, 12, 14),
            decoration: const BoxDecoration(
              color: Color(0xFF0F172A),
              border: Border(top: BorderSide(color: Color(0xFF334155))),
            ),
            child: SafeArea(
              top: false,
              child: Column(
                mainAxisSize: MainAxisSize.min,
                children: [
                  SingleChildScrollView(
                    scrollDirection: Axis.horizontal,
                    child: Row(
                      children: [
                        _buildFilterChip('magic_color', '✨ CamScan স্পষ্ট'),
                        const SizedBox(width: 8),
                        _buildFilterChip('bw_scan', '📄 সাদা-কালো'),
                        const SizedBox(width: 8),
                        _buildFilterChip('bright', '☀️ উজ্জ্বল'),
                        const SizedBox(width: 8),
                        _buildFilterChip('original', '🖼️ অরিজিনাল'),
                      ],
                    ),
                  ),
                  const SizedBox(height: 12),
                  Row(
                    children: [
                      Expanded(
                        child: OutlinedButton(
                          onPressed: _isSaving ? null : () => Navigator.pop(context),
                          style: OutlinedButton.styleFrom(
                            foregroundColor: Colors.white70,
                            side: const BorderSide(color: Color(0xFF475569)),
                            padding: const EdgeInsets.symmetric(vertical: 12),
                            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                          ),
                          child: const Text("বাতিল", style: TextStyle(fontWeight: FontWeight.bold)),
                        ),
                      ),
                      const SizedBox(width: 10),
                      Expanded(
                        flex: 2,
                        child: ElevatedButton.icon(
                          onPressed: _isSaving ? null : _applyAndReturn,
                          icon: _isSaving
                              ? const SizedBox(
                                  width: 16,
                                  height: 16,
                                  child: CircularProgressIndicator(strokeWidth: 2, color: Colors.white),
                                )
                              : const Icon(Icons.check_circle, size: 18),
                          label: Text(
                            _isSaving ? "প্রসেস হচ্ছে..." : "ক্রপ ও সোজা করে সেভ করুন",
                            style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 13),
                          ),
                          style: ElevatedButton.styleFrom(
                            backgroundColor: const Color(0xFF059669),
                            foregroundColor: Colors.white,
                            padding: const EdgeInsets.symmetric(vertical: 12),
                            shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(10)),
                          ),
                        ),
                      ),
                    ],
                  ),
                ],
              ),
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildFilterChip(String key, String label) {
    final bool isSel = _selectedFilter == key;
    return ChoiceChip(
      label: Text(
        label,
        style: TextStyle(
          fontSize: 12,
          fontWeight: FontWeight.w800,
          color: isSel ? Colors.white : const Color(0xFFCBD5E1),
        ),
      ),
      selected: isSel,
      selectedColor: const Color(0xFF059669),
      backgroundColor: const Color(0xFF1E293B),
      side: BorderSide(color: isSel ? const Color(0xFF34D399) : const Color(0xFF334155)),
      onSelected: (_) => setState(() => _selectedFilter = key),
    );
  }

  Widget _buildCornerHandle({
    required double x,
    required double y,
    required bool isActive,
    required VoidCallback onStart,
    required VoidCallback onEnd,
    required void Function(double dx, double dy) onDrag,
  }) {
    const double hitSize = 38.0;
    return Positioned(
      left: x - hitSize / 2,
      top: y - hitSize / 2,
      width: hitSize,
      height: hitSize,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onPanStart: (_) => onStart(),
        onPanEnd: (_) => onEnd(),
        onPanCancel: onEnd,
        onPanUpdate: (d) => onDrag(d.delta.dx, d.delta.dy),
        child: Center(
          child: AnimatedContainer(
            duration: const Duration(milliseconds: 80),
            width: isActive ? 24 : 20,
            height: isActive ? 24 : 20,
            decoration: BoxDecoration(
              color: isActive ? const Color(0xFF34D399) : const Color(0xFF10B981),
              shape: BoxShape.circle,
              border: Border.all(color: Colors.white, width: 2.5),
              boxShadow: const [BoxShadow(color: Colors.black54, blurRadius: 5)],
            ),
          ),
        ),
      ),
    );
  }
}

class _QuadOverlayPainter extends CustomPainter {
  final List<Offset> pts;
  _QuadOverlayPainter(this.pts);

  Offset _lerp(Offset a, Offset b, double t) =>
      Offset(a.dx + (b.dx - a.dx) * t, a.dy + (b.dy - a.dy) * t);

  @override
  void paint(Canvas canvas, Size size) {
    if (pts.length != 4) return;
    final outer = Path()..addRect(Offset.zero & size);
    final inner = Path()..addPolygon(pts, true);
    final mask = Path.combine(PathOperation.difference, outer, inner);
    canvas.drawPath(mask, Paint()..color = Colors.black.withValues(alpha: 0.54));

    // Quad outline
    canvas.drawPath(
      inner,
      Paint()
        ..color = const Color(0xFF10B981)
        ..style = PaintingStyle.stroke
        ..strokeWidth = 2.2,
    );

    // Subtle 3x3 perspective grid lines inside the quadrilateral
    final gridPaint = Paint()
      ..color = Colors.white.withValues(alpha: 0.35)
      ..strokeWidth = 0.9;
    for (int i = 1; i <= 2; i++) {
      final double t = i / 3.0;
      canvas.drawLine(_lerp(pts[0], pts[1], t), _lerp(pts[3], pts[2], t), gridPaint);
      canvas.drawLine(_lerp(pts[0], pts[3], t), _lerp(pts[1], pts[2], t), gridPaint);
    }
  }

  @override
  bool shouldRepaint(covariant _QuadOverlayPainter oldDelegate) => true;
}
