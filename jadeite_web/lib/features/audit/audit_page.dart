import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/app_theme.dart';
import '../../core/utils/formatters.dart';
import '../../data/models/models.dart';
import '../../state/providers.dart';
import '../../widgets/data_table_card.dart';

/// تصفية السجل حسب نوع العملية (null = الكل)
final auditActionFilterProvider = StateProvider<String?>((_) => null);

final auditEntriesProvider = FutureProvider.autoDispose<List<AuditEntry>>((ref) async {
  ref.watch(dataRevisionProvider);
  final tenantId = ref.watch(activeTenantIdProvider);
  final action = ref.watch(auditActionFilterProvider);
  if (tenantId == null) return const [];
  return ref.read(auditRepoProvider).latest(tenantId, action: action);
});

/// سجل التعديلات: كل إضافة وتعديل وحذف على حركات المصنع — من الويب أو من
/// برنامج سطح المكتب — بوقتها وما تغيّر فيها. يُحفظ ١٨٠ يوماً (run_maintenance).
class AuditPage extends ConsumerWidget {
  const AuditPage({super.key});

  static const _actions = <({String? key, String label})>[
    (key: null, label: 'الكل'),
    (key: 'INSERT', label: 'إضافة'),
    (key: 'UPDATE', label: 'تعديل'),
    (key: 'DELETE', label: 'حذف'),
  ];

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final entries = ref.watch(auditEntriesProvider);
    final filter = ref.watch(auditActionFilterProvider);

    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Card(
            child: Padding(
              padding: const EdgeInsets.all(14),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                const Text('🕵️ سجل التعديلات',
                    style: TextStyle(
                        fontSize: 17, fontWeight: FontWeight.bold, color: AppTheme.gold)),
                const SizedBox(height: 6),
                const Text(
                  'آخر ٣٠٠ تغيير على حركات هذا المصنع. التعديل يُحفظ بالحقول التي تغيّرت '
                  'فقط، والحذف بالحركة كاملة — فيمكن معرفة ما حُذف وإعادته.',
                  style: TextStyle(fontSize: 12, color: Colors.grey),
                ),
                const SizedBox(height: 12),
                Wrap(
                  spacing: 8,
                  children: [
                    for (final a in _actions)
                      ChoiceChip(
                        label: Text(a.label),
                        selected: filter == a.key,
                        onSelected: (_) =>
                            ref.read(auditActionFilterProvider.notifier).state = a.key,
                      ),
                  ],
                ),
              ]),
            ),
          ),
          const SizedBox(height: 14),
          entries.when(
            loading: () => const Center(
                child: Padding(padding: EdgeInsets.all(30), child: CircularProgressIndicator())),
            error: (e, _) => Center(child: Text('$e')),
            data: (list) => DataTableCard(
              title: 'السجل (${list.length})',
              columns: const ['الوقت', 'العملية', 'رقم الحركة', 'المصدر', 'التفاصيل'],
              emptyMessage: 'لا توجد تغييرات مسجّلة',
              rows: list.map((e) {
                final color = switch (e.action) {
                  'DELETE' => AppTheme.danger,
                  'UPDATE' => AppTheme.warn,
                  _ => AppTheme.success,
                };
                final label = switch (e.action) {
                  'DELETE' => 'حذف',
                  'UPDATE' => 'تعديل',
                  _ => 'إضافة',
                };
                return DataRow(cells: [
                  DataCell(Text(Fmt.dateTime(e.createdAt))),
                  DataCell(Text(label,
                      style: TextStyle(color: color, fontWeight: FontWeight.bold))),
                  DataCell(Text(e.seqNo)),
                  DataCell(Text(e.fromDesktop ? 'برنامج سطح المكتب' : 'لوحة الويب')),
                  DataCell(SizedBox(
                    width: 420,
                    child: Text(e.summary, maxLines: 2, overflow: TextOverflow.ellipsis),
                  )),
                ]);
              }).toList(),
            ),
          ),
        ],
      ),
    );
  }
}
