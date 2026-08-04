import 'package:flutter/material.dart';
import 'package:provider/provider.dart';
import '../models/delivery_area.dart';
import '../services/api_service.dart';
import '../providers/cart_provider.dart';
import '../localization/app_localizations.dart';

class LocationSelectorDialog extends StatefulWidget {
  const LocationSelectorDialog({Key? key}) : super(key: key);

  @override
  State<LocationSelectorDialog> createState() => _LocationSelectorDialogState();
}

class _LocationSelectorDialogState extends State<LocationSelectorDialog> {
  List<DeliveryArea> _allowedAreas = [];
  bool _isLoading = true;

  final String _selectedCountry = 'Bangladesh';
  String? _selectedDistrict;
  String? _selectedArea;
  final TextEditingController _addressController = TextEditingController();

  // Fallback active areas configured by Admin
  final List<DeliveryArea> _defaultFallbackAreas = [
    DeliveryArea(id: 1, country: 'Bangladesh', district: 'Tangail', area: 'Akur Takur Para', isActive: true),
    DeliveryArea(id: 2, country: 'Bangladesh', district: 'Tangail', area: 'College Para', isActive: true),
    DeliveryArea(id: 3, country: 'Bangladesh', district: 'Tangail', area: 'Victoria Road', isActive: true),
    DeliveryArea(id: 4, country: 'Bangladesh', district: 'Dhaka', area: 'Dhanmondi', isActive: true),
    DeliveryArea(id: 5, country: 'Bangladesh', district: 'Dhaka', area: 'Mirpur', isActive: true),
  ];

  @override
  void initState() {
    super.initState();
    _loadAreas();
  }

  void _loadAreas() async {
    List<DeliveryArea> areas = await ApiService.fetchDeliveryAreas();
    if (!mounted) return;
    setState(() {
      if (areas.isNotEmpty) {
        _allowedAreas = areas;
      } else {
        _allowedAreas = _defaultFallbackAreas;
      }
      _isLoading = false;

      _selectedDistrict = _districts.first;
      _selectedArea = _areasForDistrict(_selectedDistrict!).first;
    });
  }

  List<String> get _districts {
    List<String> dists = _allowedAreas.map((a) => a.district).toSet().toList();
    return dists.isNotEmpty ? dists : ['Tangail'];
  }

  List<String> _areasForDistrict(String district) {
    List<String> areas = _allowedAreas
        .where((a) => a.district.toLowerCase() == district.toLowerCase())
        .map((a) => a.area)
        .toSet()
        .toList();
    return areas.isNotEmpty ? areas : ['Akur Takur Para'];
  }

  @override
  Widget build(BuildContext context) {
    final loc = AppLocalizations.of(context);
    final cartProv = Provider.of<CartProvider>(context, listen: false);

    List<String> availableDistricts = _districts;
    List<String> availableAreas = _selectedDistrict != null
        ? _areasForDistrict(_selectedDistrict!)
        : ['Akur Takur Para'];

    return AlertDialog(
      shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
      title: Row(
        children: [
          const Icon(Icons.location_on, color: Colors.red),
          const SizedBox(width: 8),
          Text(loc.translate('select_location'), style: const TextStyle(fontSize: 18, fontWeight: FontWeight.bold)),
        ],
      ),
      content: _isLoading
          ? const SizedBox(height: 120, child: Center(child: CircularProgressIndicator()))
          : SingleChildScrollView(
              child: Column(
                mainAxisSize: MainAxisSize.min,
                crossAxisAlignment: CrossAxisAlignment.start,
                children: [
                  Text(loc.translate('country'), style: const TextStyle(fontWeight: FontWeight.bold)),
                  const SizedBox(height: 4),
                  Container(
                    width: double.infinity,
                    padding: const EdgeInsets.all(12),
                    decoration: BoxDecoration(
                      color: Colors.grey[200],
                      borderRadius: BorderRadius.circular(8),
                    ),
                    child: Text(_selectedCountry, style: const TextStyle(fontWeight: FontWeight.bold, fontSize: 15)),
                  ),
                  const SizedBox(height: 14),

                  // District Dropdown
                  Text(loc.translate('district'), style: const TextStyle(fontWeight: FontWeight.bold)),
                  const SizedBox(height: 4),
                  DropdownButtonFormField<String>(
                    initialValue: availableDistricts.contains(_selectedDistrict) ? _selectedDistrict : availableDistricts.first,
                    decoration: InputDecoration(
                      contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                      border: OutlineInputBorder(borderRadius: BorderRadius.circular(8)),
                    ),
                    items: availableDistricts.map((d) {
                      return DropdownMenuItem<String>(
                        value: d,
                        child: Text(d, style: const TextStyle(fontWeight: FontWeight.w600)),
                      );
                    }).toList(),
                    onChanged: (val) {
                      if (val != null) {
                        setState(() {
                          _selectedDistrict = val;
                          List<String> newAreas = _areasForDistrict(val);
                          _selectedArea = newAreas.isNotEmpty ? newAreas.first : null;
                        });
                      }
                    },
                  ),
                  const SizedBox(height: 14),

                  // Area / Para Dropdown
                  Text(loc.translate('area'), style: const TextStyle(fontWeight: FontWeight.bold)),
                  const SizedBox(height: 4),
                  DropdownButtonFormField<String>(
                    initialValue: availableAreas.contains(_selectedArea) ? _selectedArea : availableAreas.first,
                    decoration: InputDecoration(
                      contentPadding: const EdgeInsets.symmetric(horizontal: 12, vertical: 10),
                      border: OutlineInputBorder(borderRadius: BorderRadius.circular(8)),
                    ),
                    items: availableAreas.map((a) {
                      return DropdownMenuItem<String>(
                        value: a,
                        child: Text(a, style: const TextStyle(fontWeight: FontWeight.w600, color: Colors.blue)),
                      );
                    }).toList(),
                    onChanged: (val) {
                      if (val != null) {
                        setState(() {
                          _selectedArea = val;
                        });
                      }
                    },
                  ),
                  const SizedBox(height: 14),

                  Text(loc.translate('address_details'), style: const TextStyle(fontWeight: FontWeight.bold)),
                  const SizedBox(height: 4),
                  TextField(
                    controller: _addressController,
                    decoration: InputDecoration(
                      hintText: 'e.g. House #12, Road #4, Akur Takur Para',
                      border: OutlineInputBorder(borderRadius: BorderRadius.circular(8)),
                    ),
                  ),
                ],
              ),
            ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(context),
          child: const Text('Cancel'),
        ),
        ElevatedButton(
          onPressed: () {
            if (_selectedDistrict != null && _selectedArea != null) {
              cartProv.setLocation(
                _selectedCountry,
                _selectedDistrict!,
                _selectedArea!,
                details: _addressController.text,
              );
              Navigator.pop(context);
            }
          },
          style: ElevatedButton.styleFrom(backgroundColor: Colors.green),
          child: const Text('Save Location', style: TextStyle(color: Colors.white, fontWeight: FontWeight.bold)),
        ),
      ],
    );
  }
}
