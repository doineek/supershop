import 'dart:async';
import 'package:flutter/material.dart';
import '../services/api_service.dart';

/// Shared helper to trigger PC thermal prints and show live Firestore print confirmation.
class ThermalPrintHelper {
  static Future<void> printAndConfirm(
    BuildContext context, {
    required String riderPhone,
    required String sourceType,
    required int sourceId,
    String invoiceNumber = '',
  }) async {
    final messenger = ScaffoldMessenger.of(context);
    messenger.showSnackBar(
      const SnackBar(
        content: Text('🖨️ দোকানের PC প্রিন্টারে কমান্ড পাঠানো হচ্ছে...'),
        duration: Duration(seconds: 1),
      ),
    );
    final res = await ApiService.printOnPcThermal(
      riderPhone: riderPhone,
      sourceType: sourceType,
      sourceId: sourceId,
      invoiceNumber: invoiceNumber,
    );
    if (!context.mounted) return;
    await trackJobDialog(
      context,
      initialResult: res,
      title: invoiceNumber.isNotEmpty
          ? 'PC প্রিন্ট • $invoiceNumber'
          : 'PC থার্মাল প্রিন্ট কনফার্মেশন',
    );
  }

  static Future<void> runTestPrintAndConfirm(BuildContext context) async {
    final res = await ApiService.testThermalPrint();
    if (!context.mounted) return;
    await trackJobDialog(
      context,
      initialResult: res,
      title: 'PC প্রিন্টার টেস্ট প্রিন্ট',
    );
  }

  static Future<void> trackJobDialog(
    BuildContext context, {
    required Map<String, dynamic> initialResult,
    String title = 'PC থার্মাল প্রিন্ট কনফার্মেশন',
  }) async {
    if (!context.mounted) return;
    await showDialog<void>(
      context: context,
      barrierDismissible: true,
      builder: (_) => _ThermalPrintTrackDialog(
        initialResult: initialResult,
        title: title,
      ),
    );
  }
}

class _ThermalPrintTrackDialog extends StatefulWidget {
  final Map<String, dynamic> initialResult;
  final String title;

  const _ThermalPrintTrackDialog({
    required this.initialResult,
    required this.title,
  });

  @override
  State<_ThermalPrintTrackDialog> createState() => _ThermalPrintTrackDialogState();
}

class _ThermalPrintTrackDialogState extends State<_ThermalPrintTrackDialog> {
  Timer? _timer;
  late String _status;
  late String _printerName;
  String _printedAt = '';
  String _errorMsg = '';
  String _jobUuid = '';
  bool _pcOnline = false;
  String _pcPrinter = '';
  String _pcLastSeen = '';
  int _attempts = 0;
  bool _polling = false;

  @override
  void initState() {
    super.initState();
    final res = widget.initialResult;
    final bool ok = res['success'] == true;
    final bool direct = res['printed_directly'] == true;
    _jobUuid = (res['job_uuid'] ?? '').toString().trim();
    _printerName = (res['printer_name'] ?? '').toString().trim();
    _pcPrinter = _printerName;

    if (!ok) {
      _status = 'failed';
      _errorMsg = (res['message'] ?? 'প্রিন্ট রিকুয়েস্ট ব্যর্থ হয়েছে।').toString();
    } else if (direct) {
      _status = 'printed';
      _pcOnline = true;
    } else if (_jobUuid.isNotEmpty) {
      _status = 'pending';
      _startPolling();
    } else {
      _status = 'pending';
      _errorMsg = (res['message'] ?? '').toString();
    }
  }

  void _startPolling() {
    _timer?.cancel();
    _attempts = 0;
    _polling = true;
    _pollOnce();
    _timer = Timer.periodic(const Duration(milliseconds: 1300), (_) => _pollOnce());
  }

  Future<void> _pollOnce() async {
    if (!_polling || !mounted) return;
    _attempts++;
    final stRes = await ApiService.pollThermalPrintJobStatus(_jobUuid);
    if (!mounted) return;

    final String st = (stRes['status'] ?? 'pending').toString().toLowerCase();
    setState(() {
      _status = st;
      _pcOnline = stRes['pc_agent_online'] == true;
      _pcPrinter = (stRes['pc_printer_name'] ?? _pcPrinter).toString();
      _printerName = (stRes['printer_name'] ?? _printerName).toString();
      _printedAt = (stRes['printed_at'] ?? '').toString();
      _pcLastSeen = (stRes['pc_last_seen'] ?? '').toString();
      _errorMsg = (stRes['error_msg'] ?? _errorMsg).toString();
    });

    if (st == 'printed' || st == 'failed' || _attempts >= 15) {
      _timer?.cancel();
      if (mounted) {
        setState(() => _polling = false);
      }
    }
  }

  @override
  void dispose() {
    _timer?.cancel();
    super.dispose();
  }

  @override
  Widget build(BuildContext context) {
    final bool isPrinted = _status == 'printed';
    final bool isFailed = _status == 'failed';

    Color accent = Colors.orange.shade800;
    IconData icon = Icons.hourglass_top;
    String headline = _polling
        ? 'দোকানের PC-তে প্রিন্ট পাঠানো হচ্ছে...'
        : 'প্রিন্ট কিউতে সংরক্ষিত আছে (অপেক্ষমাণ)';

    if (isPrinted) {
      accent = Colors.green.shade700;
      icon = Icons.check_circle;
      headline = 'দোকানের PC প্রিন্টারে প্রিন্ট সম্পন্ন হয়েছে!';
    } else if (isFailed) {
      accent = Colors.red.shade700;
      icon = Icons.error;
      headline = 'থার্মাল প্রিন্ট ব্যর্থ হয়েছে';
    }

    return AlertDialog(
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(14)),
      title: Row(
        children: [
          Icon(icon, color: accent, size: 26),
          const SizedBox(width: 8),
          Expanded(
            child: Text(
              widget.title,
              style: TextStyle(fontSize: 15, fontWeight: FontWeight.bold, color: accent),
            ),
          ),
        ],
      ),
      content: Column(
        mainAxisSize: MainAxisSize.min,
        crossAxisAlignment: CrossAxisAlignment.start,
        children: [
          Container(
            width: double.infinity,
            padding: const EdgeInsets.all(10),
            decoration: BoxDecoration(
              color: accent.withValues(alpha: 0.08),
              borderRadius: BorderRadius.circular(10),
              border: Border.all(color: accent.withValues(alpha: 0.3)),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(headline, style: TextStyle(fontWeight: FontWeight.bold, color: accent, fontSize: 13)),
                if (_printerName.isNotEmpty) ...[
                  const SizedBox(height: 4),
                  Text('প্রিন্টার: $_printerName', style: const TextStyle(fontSize: 12)),
                ],
                if (_printedAt.isNotEmpty) ...[
                  const SizedBox(height: 2),
                  Text('প্রিন্টের সময়: $_printedAt', style: const TextStyle(fontSize: 11, color: Colors.black54)),
                ],
                if (_errorMsg.isNotEmpty) ...[
                  const SizedBox(height: 4),
                  Text(_errorMsg, style: TextStyle(fontSize: 12, color: Colors.red.shade800)),
                ],
                if (_polling) ...[
                  const SizedBox(height: 8),
                  const LinearProgressIndicator(minHeight: 3),
                  const SizedBox(height: 4),
                  Text('কনফার্মেশন চেক চলছে ($_attempts/15)...', style: const TextStyle(fontSize: 11, color: Colors.black54)),
                ],
              ],
            ),
          ),
          const SizedBox(height: 10),
          Container(
            width: double.infinity,
            padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 8),
            decoration: BoxDecoration(
              color: _pcOnline ? Colors.green.shade50 : Colors.amber.shade50,
              borderRadius: BorderRadius.circular(8),
              border: Border.all(color: _pcOnline ? Colors.green.shade200 : Colors.amber.shade300),
            ),
            child: Column(
              crossAxisAlignment: CrossAxisAlignment.start,
              children: [
                Text(
                  _pcOnline
                      ? '🟢 দোকানের PC এজেন্ট অনলাইন${_pcPrinter.isNotEmpty ? ' ($_pcPrinter)' : ''}'
                      : '🔴 দোকানের Windows PC এজেন্ট অফলাইন / সংযুক্ত নয়',
                  style: TextStyle(
                    fontSize: 11.5,
                    fontWeight: FontWeight.bold,
                    color: _pcOnline ? Colors.green.shade900 : Colors.amber.shade900,
                  ),
                ),
                if (!_pcOnline)
                  const Padding(
                    padding: EdgeInsets.only(top: 3),
                    child: Text(
                      'Render ক্লাউড Linux সার্ভারে প্রিন্টার সংযুক্ত নয়। দোকানের Windows PC-তে pc_print_agent.py বা লোকাল app.py চালু করলেই কিউতে থাকা রশিদ সাথে সাথে প্রিন্ট হবে।',
                      style: TextStyle(fontSize: 10.5, color: Colors.black87),
                    ),
                  ),
                if (_pcOnline && _pcLastSeen.isNotEmpty)
                  Text('সর্বশেষ সাড়া: $_pcLastSeen', style: const TextStyle(fontSize: 10, color: Colors.black54)),
              ],
            ),
          ),
        ],
      ),
      actions: [
        if (!isPrinted && _jobUuid.isNotEmpty && !_polling)
          TextButton.icon(
            onPressed: _startPolling,
            icon: const Icon(Icons.refresh, size: 16),
            label: const Text('আবার চেক করুন'),
          ),
        ElevatedButton(
          onPressed: () => Navigator.of(context).pop(),
          style: ElevatedButton.styleFrom(backgroundColor: accent, foregroundColor: Colors.white),
          child: const Text('ঠিক আছে'),
        ),
      ],
    );
  }
}
