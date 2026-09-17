import 'package:flutter/material.dart';
import '../models/notification_model.dart';
import '../models/product.dart';
import '../screens/customer/my_orders_screen.dart';
import '../screens/customer/product_detail_screen.dart';
import '../services/api_service.dart';
import '../services/notification_service.dart';

class NotificationDropdownDialog extends StatefulWidget {
  final Function(String tab)? onSelectTab;
  final List<Product>? allProducts;

  const NotificationDropdownDialog({
    Key? key,
    this.onSelectTab,
    this.allProducts,
  }) : super(key: key);

  static void show(BuildContext context, {Function(String tab)? onSelectTab, List<Product>? allProducts}) {
    showModalBottomSheet(
      context: context,
      isScrollControlled: true,
      backgroundColor: Colors.transparent,
      builder: (_) => NotificationDropdownDialog(
        onSelectTab: onSelectTab,
        allProducts: allProducts,
      ),
    );
  }

  @override
  State<NotificationDropdownDialog> createState() => _NotificationDropdownDialogState();
}

class _NotificationDropdownDialogState extends State<NotificationDropdownDialog> {
  String _selectedFilter = 'all'; // all, order, offer, suggestion

  String _formatTimeAgo(String dtStr) {
    if (dtStr.isEmpty) return 'Just now';
    try {
      final dt = DateTime.parse(dtStr);
      final diff = DateTime.now().difference(dt);
      if (diff.inSeconds < 60) return 'Just now';
      if (diff.inMinutes < 60) return '${diff.inMinutes}m ago';
      if (diff.inHours < 24) return '${diff.inHours}h ago';
      if (diff.inDays == 1) return 'Yesterday';
      if (diff.inDays < 7) return '${diff.inDays}d ago';
      return '${dt.day}/${dt.month}/${dt.year}';
    } catch (_) {
      return 'Recently';
    }
  }

  IconData _getIconForType(String type, String title) {
    if (type == 'order') {
      if (title.contains('Delivered')) return Icons.task_alt;
      if (title.contains('Way')) return Icons.delivery_dining;
      if (title.contains('Packed')) return Icons.inventory_2;
      if (title.contains('Confirmed')) return Icons.check_circle;
      if (title.contains('Cancelled')) return Icons.cancel;
      return Icons.shopping_bag;
    } else if (type == 'offer') {
      return Icons.local_offer;
    } else if (type == 'suggestion') {
      return Icons.lightbulb;
    }
    return Icons.notifications;
  }

  Color _getColorForType(String type, String title) {
    if (type == 'order') {
      if (title.contains('Delivered')) return const Color(0xFF059669);
      if (title.contains('Way')) return const Color(0xFF2563EB);
      if (title.contains('Packed')) return const Color(0xFFD97706);
      if (title.contains('Confirmed')) return const Color(0xFF16A34A);
      if (title.contains('Cancelled')) return const Color(0xFFDC2626);
      return const Color(0xFF6B21A8);
    } else if (type == 'offer') {
      return const Color(0xFF9333EA);
    } else if (type == 'suggestion') {
      return const Color(0xFFEA580C);
    }
    return const Color(0xFF6B21A8);
  }

  String _cleanTitle(String title) {
    if (title.isEmpty) return 'Notification';
    return title.replaceFirst(RegExp(r'^[^\w\d\s\u0980-\u09FF]+\s*'), '').trim();
  }

  void _handleNotificationTap(AppNotification notif) async {
    // 1. Mark as read immediately (unhighlights card and decrements badge)
    await NotificationService.instance.markAsRead(notif.id);
    if (!mounted) return;

    // 2. Action based on type
    if (notif.type == 'order') {
      Navigator.pop(context);
      Navigator.push(
        context,
        MaterialPageRoute(builder: (_) => const MyOrdersScreen()),
      );
    } else if (notif.type == 'offer') {
      Navigator.pop(context);
      if (widget.onSelectTab != null) {
        widget.onSelectTab!('offers');
      }
    } else if (notif.type == 'suggestion') {
      Navigator.pop(context);
      Product? foundProduct;
      if (widget.allProducts != null && notif.referenceId.isNotEmpty) {
        try {
          final pid = int.tryParse(notif.referenceId);
          if (pid != null) {
            foundProduct = widget.allProducts!.firstWhere(
              (p) => p.id == pid,
              orElse: () => widget.allProducts!.first,
            );
          }
        } catch (_) {}
      }

      if (foundProduct != null) {
        Navigator.push(
          context,
          MaterialPageRoute(builder: (_) => ProductDetailScreen(product: foundProduct!)),
        );
      } else {
        // Fallback: fetch products if not provided
        try {
          final products = await ApiService.fetchProducts();
          final pid = int.tryParse(notif.referenceId);
          if (pid != null && products.isNotEmpty) {
            final p = products.firstWhere((item) => item.id == pid, orElse: () => products.first);
            if (mounted) {
              Navigator.push(
                context,
                MaterialPageRoute(builder: (_) => ProductDetailScreen(product: p)),
              );
            }
          }
        } catch (_) {}
      }
    }
  }

  @override
  Widget build(BuildContext context) {
    final size = MediaQuery.of(context).size;

    return Container(
      height: size.height * 0.78,
      decoration: const BoxDecoration(
        color: Colors.white,
        borderRadius: BorderRadius.vertical(top: Radius.circular(24)),
      ),
      child: Column(
        children: [
          // Drag indicator
          Container(
            margin: const EdgeInsets.only(top: 10, bottom: 6),
            width: 44,
            height: 4,
            decoration: BoxDecoration(
              color: Colors.grey[300],
              borderRadius: BorderRadius.circular(2),
            ),
          ),

          // Header
          Padding(
            padding: const EdgeInsets.symmetric(horizontal: 18, vertical: 10),
            child: Row(
              children: [
                Container(
                  padding: const EdgeInsets.all(8),
                  decoration: BoxDecoration(
                    color: const Color(0xFFF3E8FF),
                    borderRadius: BorderRadius.circular(12),
                  ),
                  child: const Icon(Icons.notifications_active, color: Color(0xFF6B21A8), size: 22),
                ),
                const SizedBox(width: 12),
                Expanded(
                  child: ValueListenableBuilder<int>(
                    valueListenable: NotificationService.instance.unreadCountNotifier,
                    builder: (context, unread, _) {
                      return Column(
                        crossAxisAlignment: CrossAxisAlignment.start,
                        children: [
                          Row(
                            children: [
                              const Text(
                                "Notifications",
                                style: TextStyle(
                                  fontSize: 18,
                                  fontWeight: FontWeight.bold,
                                  color: Color(0xFF0F172A),
                                ),
                              ),
                              if (unread > 0) ...[
                                const SizedBox(width: 8),
                                Container(
                                  padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 2),
                                  decoration: BoxDecoration(
                                    color: const Color(0xFFEF4444),
                                    borderRadius: BorderRadius.circular(12),
                                  ),
                                  child: Text(
                                    "$unread New",
                                    style: const TextStyle(
                                      color: Colors.white,
                                      fontSize: 11,
                                      fontWeight: FontWeight.bold,
                                    ),
                                  ),
                                ),
                              ],
                            ],
                          ),
                          Text(
                            unread > 0 ? "You have unread updates" : "All caught up",
                            style: TextStyle(fontSize: 12, color: Colors.grey[600]),
                          ),
                        ],
                      );
                    },
                  ),
                ),
                TextButton.icon(
                  onPressed: () => NotificationService.instance.markAllAsRead(),
                  icon: const Icon(Icons.done_all, size: 16, color: Color(0xFF6B21A8)),
                  label: const Text(
                    "Read all",
                    style: TextStyle(fontSize: 12, fontWeight: FontWeight.bold, color: Color(0xFF6B21A8)),
                  ),
                  style: TextButton.styleFrom(
                    padding: const EdgeInsets.symmetric(horizontal: 8, vertical: 4),
                    visualDensity: VisualDensity.compact,
                  ),
                ),
                IconButton(
                  icon: const Icon(Icons.close, color: Colors.grey),
                  onPressed: () => Navigator.pop(context),
                  visualDensity: VisualDensity.compact,
                ),
              ],
            ),
          ),

          // Filter Chips
          SingleChildScrollView(
            scrollDirection: Axis.horizontal,
            padding: const EdgeInsets.symmetric(horizontal: 16, vertical: 4),
            child: Row(
              children: [
                _buildFilterChip('all', 'All'),
                _buildFilterChip('order', '📦 Orders'),
                _buildFilterChip('offer', '🏷️ Offers'),
                _buildFilterChip('suggestion', '💡 Suggestions'),
              ],
            ),
          ),
          const Divider(height: 16, thickness: 1),

          // Notification List
          Expanded(
            child: ValueListenableBuilder<List<AppNotification>>(
              valueListenable: NotificationService.instance.notificationsNotifier,
              builder: (context, allNotifs, _) {
                final filtered = allNotifs.where((n) {
                  if (_selectedFilter == 'all') return true;
                  return n.type == _selectedFilter;
                }).toList();

                if (filtered.isEmpty) {
                  return Center(
                    child: Padding(
                      padding: const EdgeInsets.all(24.0),
                      child: Column(
                        mainAxisAlignment: MainAxisAlignment.center,
                        children: [
                          Icon(Icons.notifications_none, size: 56, color: Colors.grey[400]),
                          const SizedBox(height: 12),
                          Text(
                            _selectedFilter == 'all'
                                ? "No notifications yet"
                                : "No ${_selectedFilter}s found",
                            style: const TextStyle(fontSize: 16, fontWeight: FontWeight.bold, color: Color(0xFF334155)),
                          ),
                          const SizedBox(height: 6),
                          Text(
                            "Updates regarding your orders, everyday suggestions, and special offers will appear here.",
                            textAlign: TextAlign.center,
                            style: TextStyle(fontSize: 12, color: Colors.grey[500]),
                          ),
                        ],
                      ),
                    ),
                  );
                }

                return ListView.separated(
                  padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 6),
                  itemCount: filtered.length,
                  separatorBuilder: (_, __) => const SizedBox(height: 8),
                  itemBuilder: (context, index) {
                    final notif = filtered[index];
                    final isUnread = !notif.isRead;
                    final icon = _getIconForType(notif.type, notif.title);
                    final color = _getColorForType(notif.type, notif.title);
                    final timeAgo = _formatTimeAgo(notif.createdAt);

                    return InkWell(
                      onTap: () => _handleNotificationTap(notif),
                      borderRadius: BorderRadius.circular(14),
                      child: Container(
                        padding: const EdgeInsets.all(12),
                        decoration: BoxDecoration(
                          // Highlighted state: soft purple/indigo background + border
                          color: isUnread ? const Color(0xFFFAF5FF) : Colors.white,
                          borderRadius: BorderRadius.circular(14),
                          border: Border.all(
                            color: isUnread ? const Color(0xFFD8B4FE) : const Color(0xFFE2E8F0),
                            width: isUnread ? 1.5 : 1.0,
                          ),
                          boxShadow: [
                            BoxShadow(
                              color: isUnread ? Colors.purple.withOpacity(0.06) : Colors.black.withOpacity(0.02),
                              blurRadius: 6,
                              offset: const Offset(0, 2),
                            ),
                          ],
                        ),
                        child: Row(
                          crossAxisAlignment: CrossAxisAlignment.start,
                          children: [
                            // Type Icon
                            Container(
                              padding: const EdgeInsets.all(9),
                              decoration: BoxDecoration(
                                color: color.withOpacity(isUnread ? 0.15 : 0.08),
                                shape: BoxShape.circle,
                              ),
                              child: Icon(icon, color: color, size: 22),
                            ),
                            const SizedBox(width: 12),

                            // Content
                            Expanded(
                              child: Column(
                                crossAxisAlignment: CrossAxisAlignment.start,
                                children: [
                                  Row(
                                    children: [
                                      Expanded(
                                        child: Text(
                                          _cleanTitle(notif.title),
                                          style: TextStyle(
                                            fontSize: 14,
                                            fontWeight: isUnread ? FontWeight.w800 : FontWeight.w600,
                                            color: isUnread ? const Color(0xFF0F172A) : const Color(0xFF334155),
                                          ),
                                        ),
                                      ),
                                      if (isUnread) ...[
                                        const SizedBox(width: 6),
                                        Container(
                                          width: 8,
                                          height: 8,
                                          decoration: const BoxDecoration(
                                            color: Color(0xFF6B21A8),
                                            shape: BoxShape.circle,
                                          ),
                                        ),
                                      ],
                                    ],
                                  ),
                                  const SizedBox(height: 4),
                                  Text(
                                    notif.message,
                                    style: TextStyle(
                                      fontSize: 12.5,
                                      color: isUnread ? const Color(0xFF475569) : Colors.grey[600],
                                      height: 1.35,
                                    ),
                                  ),
                                  const SizedBox(height: 6),
                                  Row(
                                    mainAxisAlignment: MainAxisAlignment.spaceBetween,
                                    children: [
                                      Text(
                                        timeAgo,
                                        style: TextStyle(
                                          fontSize: 11,
                                          color: Colors.grey[500],
                                          fontWeight: FontWeight.w500,
                                        ),
                                      ),
                                      Text(
                                        "Tap to view →",
                                        style: TextStyle(
                                          fontSize: 11,
                                          color: color,
                                          fontWeight: FontWeight.w600,
                                        ),
                                      ),
                                    ],
                                  ),
                                ],
                              ),
                            ),
                          ],
                        ),
                      ),
                    );
                  },
                );
              },
            ),
          ),
        ],
      ),
    );
  }

  Widget _buildFilterChip(String filterKey, String label) {
    final isSelected = _selectedFilter == filterKey;
    return Padding(
      padding: const EdgeInsets.only(right: 6),
      child: ChoiceChip(
        label: Text(
          label,
          style: TextStyle(
            fontSize: 12,
            fontWeight: isSelected ? FontWeight.bold : FontWeight.w500,
            color: isSelected ? Colors.white : const Color(0xFF475569),
          ),
        ),
        selected: isSelected,
        selectedColor: const Color(0xFF6B21A8),
        backgroundColor: const Color(0xFFF1F5F9),
        shape: RoundedRectangleBorder(borderRadius: BorderRadius.circular(16)),
        onSelected: (val) {
          if (val) setState(() => _selectedFilter = filterKey);
        },
      ),
    );
  }
}
