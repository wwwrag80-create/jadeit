import 'package:flutter/material.dart';

import '../core/theme/app_theme.dart';

/// رسائل موحّدة للمستخدم بألوان دلالية واضحة.
class AppSnack {
  const AppSnack._();

  static void _show(BuildContext context, String message, Color color, IconData icon) {
    ScaffoldMessenger.of(context)
      ..hideCurrentSnackBar()
      ..showSnackBar(SnackBar(
        backgroundColor: color,
        duration: const Duration(seconds: 4),
        behavior: SnackBarBehavior.floating,
        content: Row(children: [
          Icon(icon, color: Colors.white, size: 20),
          const SizedBox(width: 10),
          Expanded(child: Text(message, style: const TextStyle(color: Colors.white))),
        ]),
      ));
  }

  static void success(BuildContext context, String message) =>
      _show(context, message, AppTheme.success, Icons.check_circle_outline);

  static void warn(BuildContext context, String message) =>
      _show(context, message, AppTheme.warn, Icons.warning_amber_outlined);

  static void error(BuildContext context, String message) =>
      _show(context, message, AppTheme.danger, Icons.error_outline);
}

/// حوار تأكيد موحّد — يُستخدم قبل أي عملية تمس الأرصدة.
Future<bool> confirmDialog(
  BuildContext context, {
  required String title,
  required String message,
  String confirmLabel = 'تأكيد',
  bool danger = false,
}) async {
  final result = await showDialog<bool>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: Text(title),
      content: Text(message),
      actions: [
        TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('إلغاء')),
        FilledButton(
          style: danger ? FilledButton.styleFrom(backgroundColor: AppTheme.danger) : null,
          onPressed: () => Navigator.pop(ctx, true),
          child: Text(confirmLabel),
        ),
      ],
    ),
  );
  return result ?? false;
}
