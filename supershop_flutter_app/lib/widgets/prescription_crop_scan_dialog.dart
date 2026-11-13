import 'dart:async';
import 'dart:convert';
import 'dart:math' as math;
import 'dart:typed_data';
import 'dart:ui' as ui;
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

/// Interactive pure-Flutter Prescription Crop, Rotate & CamScan Enhancer dialog.
/// Adds zero native binary overhead while giving full crop handles, 90° rotation,
/// full-size reset, and CamScan visual document enhancement filters.
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

  // Normalized crop rectangle in rotated display space (0..1)
  double _left = 0.0;
  double _top = 0.0;
  double _right = 1.0;
  double _bottom = 1.0;
  int _quarterTurns = 0;
  String _selectedFilter = 'magic_color';

  static const double _minCropSpan = 0.12;

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
        // CamScan Magic Color: crisp contrast boost + brightened paper background
        const double c = 1.38;
        const double t = -32.0;
        return <double>[
          c, 0, 0, 0, t,
          0, c, 0, 0, t,
          0, 0, c, 0, t,
          0, 0, 0, 1, 0,
        ];
      case 'bw_scan':
        // High-contrast B&W document scan matrix
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
        // Soft brightness + clarity boost for low-light photos
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
      _left = 0.0;
      _top = 0.0;
      _right = 1.0;
      _bottom = 1.0;
    });
  }

  void _rotate90() {
    setState(() {
      _quarterTurns = (_quarterTurns + 1) % 4;
      _left = 0.0;
      _top = 0.0;
      _right = 1.0;
      _bottom = 1.0;
    });
  }

  bool get _hasCrop =>
      _left > 0.01 || _top > 0.01 || _right < 0.99 || _bottom < 0.99;

  Future<void> _applyAndReturn() async {
    final src = _decodedImage;
    if (src == null || _isSaving) return;

    // If uncropped, unrotated, and original filter is chosen, return raw bytes directly
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

      // 1. Render rotated base image into rotated coordinates if rotated, otherwise use src directly
      ui.Image rotatedImg = src;
      if (_quarterTurns != 0) {
        final rotRecorder = ui.PictureRecorder();
        final rotCanvas = Canvas(
          rotRecorder,
          Rect.fromLTWH(0, 0, rotW, rotH),
        );
        rotCanvas.translate(rotW / 2, rotH / 2);
        rotCanvas.rotate(_quarterTurns * math.pi / 2);
        rotCanvas.translate(-src.width / 2, -src.height / 2);
        rotCanvas.drawImage(src, Offset.zero, Paint());
        rotatedImg = await rotRecorder
            .endRecording()
            .toImage(rotW.round(), rotH.round());
      }

      // 2. Crop & apply CamScan ColorFilter into final bounded canvas (max 1400px longest side)
      final double srcLeft = (_left * rotW).clamp(0.0, rotW - 10);
      final double srcTop = (_top * rotH).clamp(0.0, rotH - 10);
      final double srcRight = (_right * rotW).clamp(srcLeft + 10, rotW);
      final double srcBottom = (_bottom * rotH).clamp(srcTop + 10, rotH);
      final double cropW = srcRight - srcLeft;
      final double cropH = srcBottom - srcTop;

      const double maxOutDim = 1400.0;
      double outW = cropW;
      double outH = cropH;
      if (outW > maxOutDim || outH > maxOutDim) {
        final double scale = maxOutDim / math.max(outW, outH);
        outW = (outW * scale).roundToDouble();
        outH = (outH * scale).roundToDouble();
      }
      final int finalW = math.max(16, outW.round());
      final int finalH = math.max(16, outH.round());

      final outRecorder = ui.PictureRecorder();
      final outCanvas = Canvas(
        outRecorder,
        Rect.fromLTWH(0, 0, finalW.toDouble(), finalH.toDouble()),
      );
      final paint = Paint()..filterQuality = FilterQuality.high;
      final matrix = _colorMatrixFor(_selectedFilter);
      if (matrix != null) {
        paint.colorFilter = ColorFilter.matrix(matrix);
      }

      outCanvas.drawImageRect(
        rotatedImg,
        Rect.fromLTWH(srcLeft, srcTop, cropW, cropH),
        Rect.fromLTWH(0, 0, finalW.toDouble(), finalH.toDouble()),
        paint,
      );

      final outImage = await outRecorder.endRecording().toImage(finalW, finalH);
      final byteData = await outImage.toByteData(format: ui.ImageByteFormat.png);
      if (rotatedImg != src) rotatedImg.dispose();
      outImage.dispose();

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
          "✂️ প্রেসক্রিপশন ক্রপ ও CamScan",
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
          // Top hint bar
          Container(
            width: double.infinity,
            padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
            color: const Color(0xFF1E293B),
            child: Text(
              _hasCrop
                  ? "সবুজ কোণাগুলো টেনে প্রেসক্রিপশনের অংশ ঠিক করুন • নিচ থেকে CamScan ফিল্টার বেছে নিন"
                  : "সম্পূর্ণ ছবি সিলেক্ট আছে • চাইলে কোণা টেনে ক্রপ বা CamScan ফিল্টার দিন",
              textAlign: TextAlign.center,
              style: const TextStyle(color: Color(0xFFCBD5E1), fontSize: 11.5),
            ),
          ),

          // Interactive Image + Crop Handle Area
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

                        final Rect cropPx = Rect.fromLTRB(
                          _left * dispW,
                          _top * dispH,
                          _right * dispW,
                          _bottom * dispH,
                        );

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

                                // Dark mask + crisp emerald crop frame + grid lines
                                Positioned.fill(
                                  child: IgnorePointer(
                                    child: CustomPaint(
                                      painter: _CropOverlayPainter(cropPx),
                                    ),
                                  ),
                                ),

                                // Drag inside crop box to move crop window
                                Positioned.fromRect(
                                  rect: cropPx,
                                  child: GestureDetector(
                                    onPanUpdate: (d) {
                                      final dx = d.delta.dx / dispW;
                                      final dy = d.delta.dy / dispH;
                                      final spanX = _right - _left;
                                      final spanY = _bottom - _top;
                                      setState(() {
                                        final newL = (_left + dx).clamp(0.0, 1.0 - spanX);
                                        final newT = (_top + dy).clamp(0.0, 1.0 - spanY);
                                        _left = newL;
                                        _right = newL + spanX;
                                        _top = newT;
                                        _bottom = newT + spanY;
                                      });
                                    },
                                    child: Container(color: Colors.transparent),
                                  ),
                                ),

                                // 4 Corner Drag Handles
                                _buildCornerHandle(
                                  x: cropPx.left,
                                  y: cropPx.top,
                                  onDrag: (dx, dy) {
                                    setState(() {
                                      _left = (_left + dx / dispW).clamp(0.0, _right - _minCropSpan);
                                      _top = (_top + dy / dispH).clamp(0.0, _bottom - _minCropSpan);
                                    });
                                  },
                                ),
                                _buildCornerHandle(
                                  x: cropPx.right,
                                  y: cropPx.top,
                                  onDrag: (dx, dy) {
                                    setState(() {
                                      _right = (_right + dx / dispW).clamp(_left + _minCropSpan, 1.0);
                                      _top = (_top + dy / dispH).clamp(0.0, _bottom - _minCropSpan);
                                    });
                                  },
                                ),
                                _buildCornerHandle(
                                  x: cropPx.left,
                                  y: cropPx.bottom,
                                  onDrag: (dx, dy) {
                                    setState(() {
                                      _left = (_left + dx / dispW).clamp(0.0, _right - _minCropSpan);
                                      _bottom = (_bottom + dy / dispH).clamp(_top + _minCropSpan, 1.0);
                                    });
                                  },
                                ),
                                _buildCornerHandle(
                                  x: cropPx.right,
                                  y: cropPx.bottom,
                                  onDrag: (dx, dy) {
                                    setState(() {
                                      _right = (_right + dx / dispW).clamp(_left + _minCropSpan, 1.0);
                                      _bottom = (_bottom + dy / dispH).clamp(_top + _minCropSpan, 1.0);
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
                            _isSaving ? "প্রসেস হচ্ছে..." : "✓ ক্রপ ও স্ক্যান সেভ করুন",
                            style: const TextStyle(fontWeight: FontWeight.w800, fontSize: 13.5),
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
    required void Function(double dx, double dy) onDrag,
  }) {
    const double hitSize = 34.0;
    return Positioned(
      left: x - hitSize / 2,
      top: y - hitSize / 2,
      width: hitSize,
      height: hitSize,
      child: GestureDetector(
        behavior: HitTestBehavior.opaque,
        onPanUpdate: (d) => onDrag(d.delta.dx, d.delta.dy),
        child: Center(
          child: Container(
            width: 18,
            height: 18,
            decoration: BoxDecoration(
              color: const Color(0xFF10B981),
              shape: BoxShape.circle,
              border: Border.all(color: Colors.white, width: 2.5),
              boxShadow: const [BoxShadow(color: Colors.black54, blurRadius: 4)],
            ),
          ),
        ),
      ),
    );
  }
}

class _CropOverlayPainter extends CustomPainter {
  final Rect cropRect;
  _CropOverlayPainter(this.cropRect);

  @override
  void paint(Canvas canvas, Size size) {
    final outer = Path()..addRect(Offset.zero & size);
    final inner = Path()..addRect(cropRect);
    final mask = Path.combine(PathOperation.difference, outer, inner);
    canvas.drawPath(mask, Paint()..color = Colors.black.withValues(alpha: 0.52));

    // Crop border
    canvas.drawRect(
      cropRect,
      Paint()
        ..color = const Color(0xFF10B981)
        ..style = PaintingStyle.stroke
        ..strokeWidth = 2.0,
    );

    // Subtle 3x3 guide grid
    final gridPaint = Paint()
      ..color = Colors.white.withValues(alpha: 0.32)
      ..strokeWidth = 0.8;
    for (int i = 1; i <= 2; i++) {
      final dx = cropRect.left + cropRect.width * i / 3;
      final dy = cropRect.top + cropRect.height * i / 3;
      canvas.drawLine(Offset(dx, cropRect.top), Offset(dx, cropRect.bottom), gridPaint);
      canvas.drawLine(Offset(cropRect.left, dy), Offset(cropRect.right, dy), gridPaint);
    }
  }

  @override
  bool shouldRepaint(covariant _CropOverlayPainter oldDelegate) =>
      oldDelegate.cropRect != cropRect;
}
