import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/constants/op_types.dart';
import '../../core/theme/app_theme.dart';
import '../../core/utils/formatters.dart';
import '../../data/models/models.dart';
import '../../state/providers.dart';
import '../../widgets/data_table_card.dart';

final selectedBoxProvider = StateProvider<String>((_) => 'الكاستنج');

/// إجماليات الصندوق للفترة المعروضة (مدين/دائن/الخياس)
final boxTotalsProvider =
    FutureProvider.autoDispose<({double madin, double daen, double khayas})>((ref) async {
  ref.watch(dataRevisionProvider);
  final tenantId = ref.watch(activeTenantIdProvider);
  final period = ref.watch(periodProvider);
  final box = ref.watch(selectedBoxProvider);
  if (tenantId == null) return (madin: 0.0, daen: 0.0, khayas: 0.0);
  return ref.read(ledgerRepoProvider).boxTotals(tenantId, box, period);
});

/// تفاصيل حركات الصندوق للفترة المعروضة
final boxDetailProvider = FutureProvider.autoDispose<List<Txn>>((ref) async {
  ref.watch(dataRevisionProvider);
  final tenantId = ref.watch(activeTenantIdProvider);
  final period = ref.watch(periodProvider);
  final boxName = ref.watch(selectedBoxProvider);
  final box = KhayasBox.byName(boxName);
  if (tenantId == null || box == null) return const [];
  return ref
      .read(txnRepoProvider)
      .byPeriod(tenantId, period, opTypes: [box.madinType, box.qabdType]);
});

/// شاشة صناديق الخياس: كل صندوق ببياناته الشهرية المستقلة.
class BoxesPage extends ConsumerWidget {
  const BoxesPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final selected = ref.watch(selectedBoxProvider);
    final totals = ref.watch(boxTotalsProvider);
    final losses = ref.watch(workshopLossesProvider);
    final details = ref.watch(boxDetailProvider);
    final period = ref.watch(periodProvider);
    final box = KhayasBox.byName(selected)!;

    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          // ---------- بطاقات الصناديق ----------
          Wrap(
            spacing: 10,
            runSpacing: 10,
            children: KhayasBox.all.map((b) {
              final isSelected = b.name == selected;
              return SizedBox(
                width: 210,
                child: Card(
                  color: isSelected ? AppTheme.gold.withValues(alpha: 0.14) : null,
                  child: InkWell(
                    borderRadius: BorderRadius.circular(14),
                    onTap: () => ref.read(selectedBoxProvider.notifier).state = b.name,
                    child: Padding(
                      padding: const EdgeInsets.all(14),
                      child: Row(children: [
                        Text(b.icon, style: const TextStyle(fontSize: 22)),
                        const SizedBox(width: 10),
                        Expanded(
                          child: Text(
                            b.name,
                            style: TextStyle(
                              fontWeight: FontWeight.bold,
                              color: isSelected ? AppTheme.gold : null,
                            ),
                          ),
                        ),
                      ]),
                    ),
                  ),
                ),
              );
            }).toList(),
          ),
          const SizedBox(height: 16),

          // ---------- ملخّص الصندوق المختار ----------
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: totals.when(
                loading: () => const Center(child: CircularProgressIndicator()),
                error: (e, _) => Text('$e'),
                data: (t) => Wrap(
                  spacing: 26,
                  runSpacing: 12,
                  children: [
                    _Metric(label: 'مدين (صرف)', value: Fmt.weight(t.madin)),
                    _Metric(label: 'دائن (قبض/مسترجع)', value: Fmt.weight(t.daen)),
                    _Metric(
                      label: 'الذهب عند ${box.name}',
                      value: '${Fmt.weight(t.khayas)} جم',
                      highlight: true,
                    ),
                    losses.when(
                      loading: () => const SizedBox.shrink(),
                      error: (_, __) => const SizedBox.shrink(),
                      data: (v) => _Metric(
                          label: 'إجمالي فواقد الورشة ($period)', value: '${Fmt.weight(v)} جم'),
                    ),
                  ],
                ),
              ),
            ),
          ),
          const SizedBox(height: 16),

          // ---------- تفاصيل حركات الشهر ----------
          details.when(
            loading: () => const Center(
                child: Padding(padding: EdgeInsets.all(30), child: CircularProgressIndicator())),
            error: (e, _) => Center(child: Text('$e')),
            data: (list) {
              double tMadin = 0, tDaen = 0;
              final rows = list.map((t) {
                final isMadin = t.opType == box.madinType;
                if (isMadin) {
                  tMadin += t.weight;
                } else {
                  tDaen += t.weight;
                }
                return DataRow(cells: [
                  DataCell(Text(Fmt.dateTime(t.date))),
                  DataCell(Text(t.setNumber.isEmpty ? '-' : t.setNumber)),
                  DataCell(Text(t.rowNumber.isEmpty ? '-' : t.rowNumber)),
                  DataCell(Text(t.accountName)),
                  DataCell(Text(isMadin ? Fmt.weight(t.weight) : '-')),
                  DataCell(Text(isMadin ? '-' : Fmt.weight(t.weight))),
                  DataCell(Text(t.note)),
                ]);
              }).toList();

              return DataTableCard(
                title: '${box.icon} تفاصيل ${box.name} — $period',
                columns: const [
                  'التاريخ', 'رقم التشغيل', 'الصف', 'الاسم', 'الخياس (مدين)',
                  'المسترجع/القبض', 'البيان',
                ],
                rows: rows,
                totalsRow: rows.isEmpty
                    ? null
                    : [
                        'إجمالي الشهر', '-', '-', '-', Fmt.weight(tMadin),
                        Fmt.weight(tDaen), Fmt.weight(tMadin - tDaen),
                      ],
                emptyMessage: 'لا توجد حركات في هذا الصندوق خلال $period',
              );
            },
          ),
        ],
      ),
    );
  }
}

class _Metric extends StatelessWidget {
  const _Metric({required this.label, required this.value, this.highlight = false});
  final String label;
  final String value;
  final bool highlight;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(label, style: const TextStyle(fontSize: 12, color: Colors.grey)),
        const SizedBox(height: 4),
        Text(
          value,
          style: TextStyle(
            fontSize: highlight ? 20 : 16,
            fontWeight: FontWeight.bold,
            color: highlight ? AppTheme.gold : null,
          ),
        ),
      ],
    );
  }
}
