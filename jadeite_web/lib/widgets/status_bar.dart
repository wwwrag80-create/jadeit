import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/theme/app_theme.dart';
import '../state/providers.dart';

/// مؤشر حالة التعديل: مفتوح / مقفول (والحذف يبقى متاحاً في الحالتين).
class StatusBar extends ConsumerWidget {
  const StatusBar({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final session = ref.watch(sessionProvider);
    final locked = session.isEditLocked;

    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 7),
          decoration: BoxDecoration(
            color: (locked ? AppTheme.warn : AppTheme.success).withValues(alpha: 0.15),
            borderRadius: BorderRadius.circular(8),
            border: Border.all(color: (locked ? AppTheme.warn : AppTheme.success).withValues(alpha: 0.5)),
          ),
          child: Row(
            mainAxisSize: MainAxisSize.min,
            children: [
              Icon(locked ? Icons.lock : Icons.lock_open,
                  size: 15, color: locked ? AppTheme.warn : AppTheme.success),
              const SizedBox(width: 6),
              Text(
                locked ? 'التعديل مقفول (الحذف متاح)' : 'التعديل مفتوح',
                style: TextStyle(
                  fontSize: 12,
                  fontWeight: FontWeight.bold,
                  color: locked ? AppTheme.warn : AppTheme.success,
                ),
              ),
            ],
          ),
        ),
        IconButton(
          tooltip: 'تحديث الصلاحية',
          icon: const Icon(Icons.refresh, size: 18),
          onPressed: () => ref.read(sessionProvider.notifier).refreshPermission(),
        ),
        IconButton(
          tooltip: 'خروج',
          icon: const Icon(Icons.logout, size: 18),
          onPressed: () => ref.read(sessionProvider.notifier).signOut(),
        ),
      ],
    );
  }
}
