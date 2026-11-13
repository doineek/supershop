import 'package:flutter/material.dart';
import 'package:mobile_scanner/mobile_scanner.dart';

/// Reusable bottom-sheet camera barcode / QR scanner with manual SKU fallback.
class BarcodeScannerSheet extends StatefulWidget {
  final String title;

  const BarcodeScannerSheet({
    super.key,
    this.title = 'বারকোড / SKU স্ক্যান করুন',
  });

  static Future<String?> scan(
    BuildContext context, {
    String title = 'বারকোড / SKU স্ক্যান করুন',
  }) {
    return showModalBottomSheet<String>(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => BarcodeScannerSheet(title: title),
    );
  }

  @override
  State<BarcodeScannerSheet> createState() => _BarcodeScannerSheetState();
}

class _BarcodeScannerSheetState extends State<BarcodeScannerSheet> {
  final MobileScannerController _scannerCtrl = MobileScannerController(
    detectionSpeed: DetectionSpeed.noDuplicates,
  );
  final TextEditingController _manualCtrl = TextEditingController();
  bool _handled = false;
  bool _torchOn = false;

  void _completeWithCode(String raw) {
    final code = raw.trim();
    if (code.isEmpty || _handled || !mounted) return;
    _handled = true;
    Navigator.of(context).pop(code);
  }

  @override
  void dispose() {
    _scannerCtrl.dispose();
    _manualCtrl.dispose();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final bottomInset = MediaQuery.of(context).viewInsets.bottom;
    return Container(
      height: MediaQuery.of(context).size.height * 0.68 + bottomInset,
      decoration: const BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.vertical(top: Radius.circular(18)),
      ),
      padding: EdgeInsets.only(bottom: bottomInset),
      child: Column(
        children: [
          Container(
            padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 10),
            decoration: BoxDecoration(
              color: Colors.teal.shade800,
              borderRadius: const BorderRadius.vertical(top: Radius.circular(18)),
            ),
            child: Row(
              children: [
                const Icon(Icons.qr_code_scanner, color: Colors.white),
                const SizedBox(width: 8),
                Expanded(
                  child: Text(
                    widget.title,
                    style: const TextStyle(color: Colors.white, fontWeight: FontWeight.bold, fontSize: 15),
                  ),
                ),
                IconButton(
                  tooltip: 'ফ্ল্যাশলাইট',
                  icon: Icon(_torchOn ? Icons.flash_on : Icons.flash_off, color: Colors.white),
                  onPressed: () async {
                    await _scannerCtrl.toggleTorch();
                    if (mounted) setState(() => _torchOn = !_torchOn);
                  },
                ),
                IconButton(
                  icon: const Icon(Icons.close, color: Colors.white),
                  onPressed: () => Navigator.of(context).pop(),
                ),
              ],
            ),
          ),
          Expanded(
            child: Stack(
              alignment: Alignment.center,
              children: [
                MobileScanner(
                  controller: _scannerCtrl,
                  onDetect: (capture) {
                    for (final b in capture.barcodes) {
                      final val = (b.rawValue ?? '').trim();
                      if (val.isNotEmpty) {
                        _completeWithCode(val);
                        break;
                      }
                    }
                  },
                ),
                Container(
                  width: 240,
                  height: 140,
                  decoration: BoxDecoration(
                    border: Border.all(color: Colors.greenAccent, width: 2.5),
                    borderRadius: BorderRadius.circular(12),
                  ),
                ),
                Positioned(
                  bottom: 12,
                  child: Container(
                    padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 6),
                    decoration: BoxDecoration(
                      color: Colors.black.withValues(alpha: 0.65),
                      borderRadius: BorderRadius.circular(20),
                    ),
                    child: const Text(
                      'প্যাকেট বা বোতলের বারকোড ফ্রেমের ভেতরে ধরুন',
                      style: TextStyle(color: Colors.white, fontSize: 12),
                    ),
                  ),
                ),
              ],
            ),
          ),
          Padding(
            padding: const EdgeInsets.all(12),
            child: Row(
              children: [
                Expanded(
                  child: TextField(
                    controller: _manualCtrl,
                    decoration: const InputDecoration(
                      labelText: 'অথবা বারকোড / SKU লিখুন',
                      isDense: true,
                      border: OutlineInputBorder(),
                    ),
                    onSubmitted: _completeWithCode,
                  ),
                ),
                const SizedBox(width: 8),
                ElevatedButton(
                  onPressed: () => _completeWithCode(_manualCtrl.text),
                  style: ElevatedButton.styleFrom(
                    backgroundColor: Colors.teal.shade700,
                    foregroundColor: Colors.white,
                    padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 13),
                  ),
                  child: const Text('খুঁজুন', style: TextStyle(fontWeight: FontWeight.bold)),
                ),
              ],
            ),
          ),
        ],
      ),
    );
  }
}
