import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../state/providers.dart';

/// اختيار الفترة المحاسبية. كل شاشة تقرأ الفترة من هنا، فبيانات كل شهر منفصلة تماماً.
class PeriodSelector extends ConsumerWidget {
  const PeriodSelector({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final period = ref.watch(periodProvider);
    final controller = ref.read(periodProvider.notifier);

    return Row(
      mainAxisSize: MainAxisSize.min,
      children: [
        IconButton(
          tooltip: 'الشهر السابق',
          icon: const Icon(Icons.chevron_right),
          onPressed: controller.previous,
        ),
        Container(
          padding: const EdgeInsets.symmetric(horizontal: 14, vertical: 7),
          decoration: BoxDecoration(
            color: Colors.white10,
            borderRadius: BorderRadius.circular(8),
          ),
          child: Text(period, style: const TextStyle(fontWeight: FontWeight.bold)),
        ),
        IconButton(
          tooltip: 'الشهر التالي',
          icon: const Icon(Icons.chevron_left),
          onPressed: controller.next,
        ),
      ],
    );
  }
}
