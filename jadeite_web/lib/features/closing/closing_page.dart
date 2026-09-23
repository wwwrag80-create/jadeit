import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/constants/op_types.dart';
import '../../core/theme/app_theme.dart';
import '../../core/utils/formatters.dart';
import '../../data/models/models.dart';
import '../../state/providers.dart';
import '../../widgets/app_snack.dart';
import '../../widgets/data_table_card.dart';

/// حالة إقفال كل الصناديق للفترة المعروضة
final closingStatusProvider =
    FutureProvider.autoDispose<List<BoxClosingStatus>>((ref) async {
  ref.watch(dataRevisionProvider);
  final tenantId = ref.watch(activeTenantIdProvider);
  final period = ref.watch(periodProvider);
  if (tenantId == null) return const [];
  return ref.read(ledgerRepoProvider).boxesClosingStatus(tenantId, period);
});

/// شاشة إقفال الصناديق والخزينة.
///
/// الإقفال يرحّل رصيد الصندوق لحساب الخسائر بقيد مزدوج ويسجّله،
/// فلا يبقى الرصيد معلّقاً ولا يُحمَّل مرتين على الشهر التالي.
class ClosingPage extends ConsumerWidget {
  const ClosingPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final status = ref.watch(closingStatusProvider);
    final treasury = ref.watch(treasuryProvider);
    final period = ref.watch(periodProvider);

    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Card(
            child: Padding(
              padding: const EdgeInsets.all(16),
              child: Column(crossAxisAlignment: CrossAxisAlignment.start, children: [
                const Text('🔐 إقفال الصناديق والخزينة',
                    style: TextStyle(
                        fontSize: 17, fontWeight: FontWeight.bold, color: AppTheme.gold)),
                const SizedBox(height: 8),
                const Text(
                  'الإقفال ينقل رصيد خياس الصندوق إلى حساب الخسائر بقيد مزدوج، '
                  'ويُسجَّل باسم الفترة فلا يمكن تكراره. يمكن التراجع عنه إذا اكتُشف خطأ.',
                  style: TextStyle(fontSize: 12, color: Colors.grey),
                ),
                const SizedBox(height: 14),
                Row(children: [
                  treasury.when(
                    loading: () => const SizedBox(
                        height: 16, width: 16, child: CircularProgressIndicator(strokeWidth: 2)),
                    error: (_, __) => const Text('—'),
                    data: (v) => Text('رصيد الخزينة حتى $period: ${Fmt.weight(v)} جم',
                        style: const TextStyle(
                            fontSize: 16, fontWeight: FontWeight.bold, color: AppTheme.gold)),
                  ),
                ]),
              ]),
            ),
          ),
          const SizedBox(height: 16),
          status.when(
            loading: () => const Center(
                child: Padding(padding: EdgeInsets.all(30), child: CircularProgressIndicator())),
            error: (e, _) => Center(child: Text('$e')),
            data: (list) {
              double tKhayas = 0, tClosed = 0;
              final rows = list.map((b) {
                tKhayas += b.khayas;
                tClosed += b.closedKhayas;
                final icon = KhayasBox.byName(b.boxName)?.icon ?? '📦';

                return DataRow(cells: [
                  DataCell(Text('$icon ${b.boxName}')),
                  DataCell(Text(Fmt.weightOrDash(b.madin))),
                  DataCell(Text(Fmt.weightOrDash(b.daen))),
                  DataCell(Text(Fmt.weight(b.khayas),
                      style: TextStyle(
                        fontWeight: FontWeight.bold,
                        color: b.khayas > 0 ? AppTheme.danger : null,
                      ))),
                  DataCell(b.isClosed
                      ? const Row(mainAxisSize: MainAxisSize.min, children: [
                          Icon(Icons.lock_outline, size: 15, color: AppTheme.success),
                          SizedBox(width: 4),
                          Text('مُقفل', style: TextStyle(color: AppTheme.success)),
                        ])
                      : const Text('مفتوح', style: TextStyle(color: Colors.grey))),
                  DataCell(Text(b.isClosed ? Fmt.weight(b.closedKhayas) : '-')),
                  DataCell(Text(b.closedAt == null ? '-' : Fmt.dateTime(b.closedAt))),
                  DataCell(b.isClosed
                      ? TextButton.icon(
                          onPressed: () => _reopen(context, ref, b, period),
                          icon: const Icon(Icons.lock_open_outlined, size: 16),
                          label: const Text('تراجع'),
                        )
                      : FilledButton.icon(
                          onPressed: b.khayas == 0
                              ? null
                              : () => _close(context, ref, b, period),
                          icon: const Icon(Icons.lock_outline, size: 16),
                          label: const Text('إقفال'),
                        )),
                ]);
              }).toList();

              return DataTableCard(
                title: 'حالة إقفال الصناديق — $period',
                columns: const [
                  'الصندوق', 'مدين', 'دائن', 'الخياس', 'الحالة',
                  'المُقفل', 'تاريخ الإقفال', 'إجراء',
                ],
                rows: rows,
                totalsRow: rows.isEmpty
                    ? null
                    : [
                        'الإجمالي', '-', '-', Fmt.weight(tKhayas), '-',
                        Fmt.weight(tClosed), '-', '-',
                      ],
                actions: [
                  OutlinedButton.icon(
                    onPressed: () => _closeAll(context, ref, list, period),
                    icon: const Icon(Icons.lock_clock_outlined, size: 18),
                    label: const Text('إقفال كل الصناديق المفتوحة'),
                  ),
                ],
              );
            },
          ),
        ],
      ),
    );
  }

  Future<void> _close(
      BuildContext context, WidgetRef ref, BoxClosingStatus box, String period) async {
    final ok = await confirmDialog(
      context,
      title: 'إقفال ${box.boxName}',
      message: 'سيتم ترحيل رصيد الخياس (${Fmt.weight(box.khayas)} جم) '
          'إلى حساب الخسائر بقيد مزدوج، وتسجيل إقفال الصندوق لفترة $period.\n\n'
          'هل تريد المتابعة؟',
      confirmLabel: 'إقفال',
    );
    if (!ok) return;

    final tenantId = ref.read(activeTenantIdProvider);
    if (tenantId == null) return;
    try {
      final amount =
          await ref.read(closingRepoProvider).closeBox(tenantId, box.boxName, period);
      _refresh(ref);
      if (context.mounted) {
        AppSnack.success(context, 'تم إقفال ${box.boxName} بمبلغ ${Fmt.weight(amount)} جم.');
      }
    } catch (e) {
      if (context.mounted) AppSnack.error(context, '$e');
    }
  }

  Future<void> _reopen(
      BuildContext context, WidgetRef ref, BoxClosingStatus box, String period) async {
    final ok = await confirmDialog(
      context,
      title: 'التراجع عن الإقفال',
      message: 'سيتم حذف قيد إقفال (${box.boxName}) لفترة $period وإرجاع الرصيد كما كان.\n\n'
          'هل تريد المتابعة؟',
      confirmLabel: 'تراجع',
      danger: true,
    );
    if (!ok) return;

    final tenantId = ref.read(activeTenantIdProvider);
    if (tenantId == null) return;
    try {
      await ref.read(closingRepoProvider).reopenBox(tenantId, box.boxName, period);
      _refresh(ref);
      if (context.mounted) AppSnack.success(context, 'تم التراجع عن الإقفال.');
    } catch (e) {
      if (context.mounted) AppSnack.error(context, '$e');
    }
  }

  Future<void> _closeAll(BuildContext context, WidgetRef ref,
      List<BoxClosingStatus> list, String period) async {
    final pending = list.where((b) => !b.isClosed && b.khayas != 0).toList();
    if (pending.isEmpty) {
      AppSnack.warn(context, 'لا توجد صناديق مفتوحة عليها رصيد لإقفالها في $period.');
      return;
    }

    final total = pending.fold<double>(0, (s, b) => s + b.khayas);
    final ok = await confirmDialog(
      context,
      title: 'إقفال ${pending.length} صندوق',
      message: 'سيتم إقفال: ${pending.map((b) => b.boxName).join('، ')}\n'
          'بإجمالي ${Fmt.weight(total)} جم يُرحَّل لحساب الخسائر.\n\nهل تريد المتابعة؟',
      confirmLabel: 'إقفال الكل',
    );
    if (!ok) return;

    final tenantId = ref.read(activeTenantIdProvider);
    if (tenantId == null) return;

    var done = 0;
    final failures = <String>[];
    for (final box in pending) {
      try {
        await ref.read(closingRepoProvider).closeBox(tenantId, box.boxName, period);
        done++;
      } catch (e) {
        // نُكمل باقي الصناديق ولا نوقف العملية كلها بسبب صندوق واحد
        failures.add(box.boxName);
      }
    }
    _refresh(ref);

    if (!context.mounted) return;
    if (failures.isEmpty) {
      AppSnack.success(context, 'تم إقفال $done صندوق بنجاح.');
    } else {
      AppSnack.warn(context,
          'تم إقفال $done صندوق، وتعذّر إقفال: ${failures.join('، ')}');
    }
  }

  void _refresh(WidgetRef ref) => bumpDataRevision(ref);
}
