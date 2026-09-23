import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/app_theme.dart';
import '../../core/utils/formatters.dart';
import '../../data/models/models.dart';
import '../../printing/statement_pdf.dart';
import '../../state/providers.dart';
import '../../widgets/app_snack.dart';
import '../../widgets/data_table_card.dart';

/// تفصيل الخسائر والهالك للفترة المعروضة (صناديق + عمال)
final lossesBreakdownProvider = FutureProvider.autoDispose<List<LossRow>>((ref) async {
  ref.watch(dataRevisionProvider);
  final tenantId = ref.watch(activeTenantIdProvider);
  final period = ref.watch(periodProvider);
  if (tenantId == null) return const [];
  return ref.read(ledgerRepoProvider).lossesBreakdown(tenantId, period);
});

/// شاشة الخسائر والهالك: من أين يضيع الذهب، وبكم.
class LossesPage extends ConsumerWidget {
  const LossesPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final losses = ref.watch(lossesBreakdownProvider);
    final totalLosses = ref.watch(workshopLossesProvider);
    final period = ref.watch(periodProvider);

    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(children: [
            Text('⚠️ الخسائر والهالك — $period',
                style: const TextStyle(
                    fontSize: 18, fontWeight: FontWeight.bold, color: AppTheme.gold)),
            const Spacer(),
            OutlinedButton.icon(
              onPressed: () => _print(context, ref),
              icon: const Icon(Icons.print_outlined),
              label: const Text('طباعة التقرير'),
            ),
          ]),
          const SizedBox(height: 14),

          losses.when(
            loading: () => const Center(
                child: Padding(padding: EdgeInsets.all(30), child: CircularProgressIndicator())),
            error: (e, _) => Center(child: Text('$e')),
            data: (list) {
              final boxes = list.where((l) => l.sourceKind == 'صندوق').toList();
              final workers = list.where((l) => l.sourceKind == 'عامل').toList();

              final waste = list.where((l) => l.isWaste).fold<double>(0, (s, l) => s + l.amount);
              final surplus =
                  list.where((l) => !l.isWaste).fold<double>(0, (s, l) => s + l.amount);
              final worst = workers.isEmpty
                  ? null
                  : workers.reduce((a, b) => a.amount > b.amount ? a : b);

              return Column(
                crossAxisAlignment: CrossAxisAlignment.stretch,
                children: [
                  // ---------- مؤشرات ----------
                  Card(
                    child: Padding(
                      padding: const EdgeInsets.all(18),
                      child: Wrap(spacing: 34, runSpacing: 16, children: [
                        _Kpi(
                          label: 'إجمالي فواقد الورشة',
                          value: totalLosses.maybeWhen(
                              data: (v) => '${Fmt.weight(v)} جم', orElse: () => '...'),
                          color: AppTheme.warn,
                        ),
                        _Kpi(
                          label: 'الهالك (فاقد موجب)',
                          value: '${Fmt.weight(waste)} جم',
                          color: AppTheme.danger,
                        ),
                        _Kpi(
                          label: 'الفائض (لصالح الورشة)',
                          value: '${Fmt.weight(surplus.abs())} جم',
                          color: AppTheme.success,
                        ),
                        _Kpi(
                          label: 'الأعلى هالكاً',
                          value: worst == null || worst.amount <= 0
                              ? 'لا يوجد'
                              : '${worst.sourceName} (${Fmt.weight(worst.amount)})',
                          color: AppTheme.blue,
                        ),
                      ]),
                    ),
                  ),
                  const SizedBox(height: 16),

                  // ---------- الصناديق ----------
                  DataTableCard(
                    title: 'الهالك حسب صناديق الخياس',
                    columns: const ['الصندوق', 'الخياس', 'الحالة'],
                    rows: boxes
                        .map((l) => DataRow(cells: [
                              DataCell(Text(l.sourceName)),
                              DataCell(Text(Fmt.weight(l.amount),
                                  style: TextStyle(
                                    fontWeight: FontWeight.bold,
                                    color: l.isWaste ? AppTheme.danger : AppTheme.success,
                                  ))),
                              DataCell(Text(l.isClosed ? '🔒 مُقفل' : 'مفتوح',
                                  style: TextStyle(
                                      color: l.isClosed ? AppTheme.success : Colors.grey))),
                            ]))
                        .toList(),
                    totalsRow: boxes.isEmpty
                        ? null
                        : [
                            'الإجمالي',
                            Fmt.weight(boxes.fold<double>(0, (s, l) => s + l.amount)),
                            '-',
                          ],
                    emptyMessage: 'لا يوجد هالك مسجّل على الصناديق في $period',
                  ),
                  const SizedBox(height: 16),

                  // ---------- العمال ----------
                  DataTableCard(
                    title: 'الفاقد الفعلي حسب العمال',
                    columns: const ['الاسم', 'القسم', 'الفاقد', 'التقييم'],
                    rows: workers
                        .map((l) => DataRow(cells: [
                              DataCell(Text(l.sourceName)),
                              DataCell(Text(l.category)),
                              DataCell(Text(Fmt.weight(l.amount),
                                  style: TextStyle(
                                    fontWeight: FontWeight.bold,
                                    color: l.isWaste ? AppTheme.danger : AppTheme.success,
                                  ))),
                              DataCell(Text(
                                l.isWaste ? 'هالك' : 'فائض لصالح الورشة',
                                style: TextStyle(
                                    fontSize: 12,
                                    color: l.isWaste ? AppTheme.danger : AppTheme.success),
                              )),
                            ]))
                        .toList(),
                    totalsRow: workers.isEmpty
                        ? null
                        : [
                            'الإجمالي', '-',
                            Fmt.weight(workers.fold<double>(0, (s, l) => s + l.amount)),
                            '-',
                          ],
                    emptyMessage: 'لا توجد حركات تصنيع في $period',
                  ),
                ],
              );
            },
          ),
        ],
      ),
    );
  }

  Future<void> _print(BuildContext context, WidgetRef ref) async {
    final period = ref.read(periodProvider);
    final tenant = ref.read(sessionProvider).activeTenant;
    try {
      final list = await ref.read(lossesBreakdownProvider.future);
      final total = await ref.read(workshopLossesProvider.future);

      final rows = list
          .map((l) => [
                l.sourceKind,
                l.sourceName,
                l.category,
                Fmt.weight(l.amount),
                l.isWaste ? 'هالك' : 'فائض',
              ])
          .toList();

      await const StatementPdf().print(
        businessName: tenant?.businessName ?? 'جاديت',
        title: 'تقرير الخسائر والهالك',
        subtitle: 'الفترة: $period   |   إجمالي فواقد الورشة: ${Fmt.weight(total)} جم',
        columns: const ['المصدر', 'الاسم', 'القسم', 'المبلغ', 'التقييم'],
        rows: rows,
        totalsRow: [
          'الإجمالي', '-', '-',
          Fmt.weight(list.fold<double>(0, (s, l) => s + l.amount)), '-',
        ],
        columnWidths: const [1.0, 2.0, 1.6, 1.2, 1.2],
      );
    } catch (e) {
      if (context.mounted) AppSnack.error(context, '$e');
    }
  }
}

class _Kpi extends StatelessWidget {
  const _Kpi({required this.label, required this.value, required this.color});
  final String label;
  final String value;
  final Color color;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(label, style: const TextStyle(fontSize: 12, color: Colors.grey)),
        const SizedBox(height: 6),
        Text(value,
            style: TextStyle(fontSize: 20, fontWeight: FontWeight.bold, color: color)),
      ],
    );
  }
}
