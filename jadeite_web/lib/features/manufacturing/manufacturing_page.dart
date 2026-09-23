import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/constants/op_types.dart';
import '../../core/theme/app_theme.dart';
import '../../core/utils/formatters.dart';
import '../../data/models/models.dart';
import '../../state/providers.dart';
import '../../widgets/app_snack.dart';
import '../../widgets/data_table_card.dart';

/// القسم المختار حالياً في شاشة مراحل التصنيع
final stageSelectionProvider = StateProvider<String>((_) => 'المصنعين');

/// العامل المختار في قسمي المصنعين/المركبين
final selectedWorkerProvider = StateProvider<String?>((_) => null);

/// كشف حركة العامل (يُحسب في قاعدة البيانات لضمان رقم واحد لكل الأجهزة)
final workerLedgerProvider =
    FutureProvider.autoDispose<List<WorkerLedgerRow>>((ref) async {
  ref.watch(dataRevisionProvider);
  final tenantId = ref.watch(activeTenantIdProvider);
  final worker = ref.watch(selectedWorkerProvider);
  final period = ref.watch(periodProvider);
  if (tenantId == null || worker == null) return const [];
  return ref.read(ledgerRepoProvider).workerLedger(tenantId, worker, period);
});

/// حركات صندوق (كاستنج/تلميع/بف) للفترة المعروضة، مجمّعة في صفوف
final stageRowsProvider = FutureProvider.autoDispose<List<StageRow>>((ref) async {
  ref.watch(dataRevisionProvider);
  final tenantId = ref.watch(activeTenantIdProvider);
  final period = ref.watch(periodProvider);
  final stage = ref.watch(stageSelectionProvider);
  final box = KhayasBox.byName(stage);
  if (tenantId == null || box == null) return const [];

  final txns = await ref
      .read(txnRepoProvider)
      .byPeriod(tenantId, period, opTypes: [box.madinType, box.qabdType]);
  return StageRow.group(txns, box.madinType, box.qabdType);
});

class ManufacturingPage extends ConsumerWidget {
  const ManufacturingPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final stage = ref.watch(stageSelectionProvider);
    final stages = [
      'المصنعين',
      'المركبين',
      ...KhayasBox.all.where((b) => b.name != 'خياس الطقوم').map((b) => b.name),
    ];

    return Column(
      crossAxisAlignment: CrossAxisAlignment.stretch,
      children: [
        Padding(
          padding: const EdgeInsets.fromLTRB(16, 16, 16, 6),
          child: Wrap(
            spacing: 8,
            runSpacing: 8,
            children: stages.map((s) {
              final selected = s == stage;
              return ChoiceChip(
                label: Text(s),
                selected: selected,
                onSelected: (_) {
                  ref.read(stageSelectionProvider.notifier).state = s;
                  ref.read(selectedWorkerProvider.notifier).state = null;
                },
              );
            }).toList(),
          ),
        ),
        Expanded(
          child: (stage == 'المصنعين' || stage == 'المركبين')
              ? _WorkerSection(category: stage)
              : _StageSection(stageName: stage),
        ),
      ],
    );
  }
}

// ============================================================================
//  قسم المصنعين/المركبين — كشف حركة العامل بالصفوف
// ============================================================================
class _WorkerSection extends ConsumerWidget {
  const _WorkerSection({required this.category});
  final String category;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final accounts = ref.watch(accountsProvider);
    final worker = ref.watch(selectedWorkerProvider);
    final ledger = ref.watch(workerLedgerProvider);
    final isAssembler = category == 'المركبين';

    final names = accounts.maybeWhen(
      data: (list) => list.where((a) => a.category == category).map((a) => a.name).toList(),
      orElse: () => <String>[],
    );

    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Card(
            child: Padding(
              padding: const EdgeInsets.all(14),
              child: Row(children: [
                const Text('العامل: ', style: TextStyle(fontWeight: FontWeight.bold)),
                const SizedBox(width: 8),
                SizedBox(
                  width: 240,
                  child: DropdownButtonFormField<String>(
                    value: names.contains(worker) ? worker : null,
                    isExpanded: true,
                    decoration: const InputDecoration(isDense: true),
                    items: names
                        .map((n) => DropdownMenuItem(value: n, child: Text(n)))
                        .toList(),
                    onChanged: (v) =>
                        ref.read(selectedWorkerProvider.notifier).state = v,
                  ),
                ),
                const Spacer(),
                if (worker != null)
                  FilledButton.icon(
                    onPressed: () => _openOpsDialog(context, ref, worker, isAssembler),
                    icon: const Icon(Icons.add),
                    label: const Text('تسجيل عملية'),
                  ),
              ]),
            ),
          ),
          const SizedBox(height: 14),
          if (worker == null)
            const Padding(
              padding: EdgeInsets.all(40),
              child: Center(child: Text('اختر عاملاً لعرض كشف حركته')),
            )
          else
            ledger.when(
              loading: () => const Center(
                  child: Padding(padding: EdgeInsets.all(30), child: CircularProgressIndicator())),
              error: (e, _) => Center(child: Text('$e')),
              data: (rows) => _workerTable(context, ref, rows, isAssembler),
            ),
        ],
      ),
    );
  }

  Widget _workerTable(
      BuildContext context, WidgetRef ref, List<WorkerLedgerRow> rows, bool isAssembler) {
    final columns = isAssembler
        ? ['الصف', 'رقم التشغيل', 'صرف', 'قبض', 'ليز', 'سلك راجع', 'عيار', 'الفاقد اللحظي', 'البيان']
        : ['الصف', 'رقم التشغيل', 'صرف', 'قبض/كسر', 'قبض/٨', 'قبض/٤', 'بوليش', 'ليز',
           'سلك راجع', 'عيار', 'الفاقد اللحظي', 'البيان'];

    double tSarf = 0, tQabd = 0, tLaiz = 0, tWire = 0, tLoss = 0, tM8 = 0, tM4 = 0, tPolish = 0;

    // الترتيب تدريجي برقم الصف في كل العمليات والشاشات
    final sorted = [...rows]..sort((a, b) => Fmt.compareRowNumbers(a.rowNumber, b.rowNumber));

    final dataRows = sorted.map((r) {
      tSarf += r.sarf;
      tQabd += r.qabd;
      tLaiz += r.laiz;
      tWire += r.wireBack;
      tLoss += r.instantLoss;
      tM8 += r.mufanish8;
      tM4 += r.mufanish4;
      tPolish += r.polish;

      // لون واحد لكل الصفوف، عدا الصف الذي فاقده اللحظي سالب فيظهر بالأحمر
      final style = r.instantLoss < 0
          ? const TextStyle(color: AppTheme.danger, fontWeight: FontWeight.bold)
          : null;
      Widget cell(String text) => Text(text, style: style);

      return DataRow(cells: [
        DataCell(cell(r.rowNumber.isEmpty ? 'بدون ترقيم' : r.rowNumber)),
        DataCell(cell(r.setNumber.isEmpty ? '-' : r.setNumber)),
        DataCell(cell(Fmt.weightOrDash(r.sarf))),
        DataCell(cell(Fmt.weightOrDash(r.qabd))),
        if (!isAssembler) DataCell(cell(Fmt.weightOrDash(r.mufanish8))),
        if (!isAssembler) DataCell(cell(Fmt.weightOrDash(r.mufanish4))),
        if (!isAssembler) DataCell(cell(Fmt.weightOrDash(r.polish))),
        DataCell(cell(Fmt.weightOrDash(r.laiz))),
        DataCell(cell(Fmt.weightOrDash(r.wireBack))),
        DataCell(cell(r.carat > 0 ? Fmt.carat(r.carat) : '-')),
        DataCell(cell(Fmt.weight(r.instantLoss))),
        DataCell(cell(r.note)),
      ]);
    }).toList();

    final totals = isAssembler
        ? ['الإجمالي', '-', Fmt.weight(tSarf), Fmt.weight(tQabd), Fmt.weight(tLaiz),
           Fmt.weight(tWire), '-', Fmt.weight(tLoss), '-']
        : ['الإجمالي', '-', Fmt.weight(tSarf), Fmt.weight(tQabd), Fmt.weight(tM8),
           Fmt.weight(tM4), Fmt.weight(tPolish), Fmt.weight(tLaiz), Fmt.weight(tWire),
           '-', Fmt.weight(tLoss), '-'];

    return DataTableCard(
      title: 'كشف حركة: ${ref.watch(selectedWorkerProvider)} — ${ref.watch(periodProvider)}',
      columns: columns,
      rows: dataRows,
      totalsRow: dataRows.isEmpty ? null : totals,
    );
  }

  Future<void> _openOpsDialog(
      BuildContext context, WidgetRef ref, String worker, bool isAssembler) async {
    final ops = isAssembler ? OpTypes.assemblerOps : OpTypes.manufacturerOps;
    final controllers = {for (final op in ops) op: TextEditingController()};
    final rowNo = TextEditingController();
    final setNo = TextEditingController();
    final note = TextEditingController();
    // التاريخ حقيقي (الآن)، والفترة المعروضة تُرسل صراحةً مع الحركة
    final period = ref.read(periodProvider);
    final date = DateTime.now();

    final confirmed = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('تسجيل عملية — $worker'),
        content: SizedBox(
          width: 460,
          child: SingleChildScrollView(
            child: Column(mainAxisSize: MainAxisSize.min, children: [
              Row(children: [
                Expanded(
                  child: TextField(
                      controller: rowNo,
                      decoration: const InputDecoration(labelText: 'رقم الصف *')),
                ),
                const SizedBox(width: 10),
                Expanded(
                  child: TextField(
                      controller: setNo,
                      decoration: const InputDecoration(labelText: 'رقم التشغيل')),
                ),
              ]),
              const SizedBox(height: 12),
              Wrap(
                spacing: 10,
                runSpacing: 10,
                children: ops
                    .map((op) => SizedBox(
                          width: 130,
                          child: TextField(
                            controller: controllers[op],
                            keyboardType: TextInputType.number,
                            decoration: InputDecoration(labelText: op),
                          ),
                        ))
                    .toList(),
              ),
              const SizedBox(height: 12),
              TextField(
                  controller: note, decoration: const InputDecoration(labelText: 'البيان')),
            ]),
          ),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('إلغاء')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('ترحيل')),
        ],
      ),
    );

    if (confirmed != true) return;

    if (rowNo.text.trim().isEmpty) {
      if (context.mounted) AppSnack.warn(context, 'رقم الصف إلزامي في المصنعين والمركبين.');
      return;
    }

    final tenantId = ref.read(activeTenantIdProvider);
    if (tenantId == null) return;

    final entries = <Txn>[];
    for (final op in ops) {
      final value = double.tryParse(controllers[op]!.text.trim()) ?? 0;
      // العيار قد يُسجَّل بأي قيمة موجبة، وباقي الأنواع تتطلب قيمة أكبر من صفر
      if (value <= 0) continue;
      entries.add(Txn.newEntry(
        date: date,
        accountName: worker,
        opType: op,
        weight: value,
        note: note.text.trim(),
        setNumber: setNo.text.trim(),
        rowNumber: rowNo.text.trim(),
        period: period,
      ));
    }

    if (entries.isEmpty) {
      if (context.mounted) AppSnack.warn(context, 'لم تُدخل أي قيمة للترحيل.');
      return;
    }

    try {
      await ref.read(txnRepoProvider).postMany(tenantId, entries);
      bumpDataRevision(ref);
      if (context.mounted) AppSnack.success(context, 'تم ترحيل ${entries.length} حركة.');
    } catch (e) {
      if (context.mounted) AppSnack.error(context, '$e');
    }
  }
}

// ============================================================================
//  أقسام الصناديق (الكاستنج / التلميع / البف) — صفوف مدين ودائن وخياس
// ============================================================================
class _StageSection extends ConsumerWidget {
  const _StageSection({required this.stageName});
  final String stageName;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final rows = ref.watch(stageRowsProvider);
    final box = KhayasBox.byName(stageName)!;
    final withTrees = stageName == 'الكاستنج';

    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Align(
            alignment: AlignmentDirectional.centerStart,
            child: FilledButton.icon(
              onPressed: () => _openStageDialog(context, ref, box, withTrees),
              icon: const Icon(Icons.add),
              label: Text('تسجيل حركة ${box.name}'),
            ),
          ),
          const SizedBox(height: 14),
          rows.when(
            loading: () => const Center(
                child: Padding(padding: EdgeInsets.all(30), child: CircularProgressIndicator())),
            error: (e, _) => Center(child: Text('$e')),
            data: (list) {
              final sorted = [...list]
                ..sort((a, b) => Fmt.compareRowNumbers(a.rowNumber, b.rowNumber));

              double tMadin = 0, tDaen = 0, tTrees = 0;
              final dataRows = sorted.map((r) {
                final khayas = r.madin - r.daen;
                tMadin += r.madin;
                tDaen += r.daen;
                tTrees += r.trees;

                // الأحمر لأي صف يكون فيه الدائن (القبض) أكبر من المدين (الصرف)
                final style = r.daen > r.madin
                    ? const TextStyle(color: AppTheme.danger, fontWeight: FontWeight.bold)
                    : null;
                Widget cell(String t) => Text(t, style: style);

                return DataRow(cells: [
                  DataCell(cell(r.rowNumber.isEmpty ? 'بدون ترقيم' : r.rowNumber)),
                  DataCell(cell(r.accountName)),
                  DataCell(cell(Fmt.weightOrDash(r.madin))),
                  DataCell(cell(Fmt.weightOrDash(r.daen))),
                  DataCell(cell(Fmt.weight(khayas))),
                  if (withTrees) DataCell(cell(r.trees > 0 ? Fmt.carat(r.trees) : '-')),
                  if (withTrees)
                    DataCell(cell(r.trees > 0 ? Fmt.weight(khayas / r.trees) : '-')),
                  DataCell(cell(r.note)),
                  DataCell(IconButton(
                    icon: const Icon(Icons.delete_outline, size: 18, color: AppTheme.danger),
                    onPressed: () async {
                      final ok = await confirmDialog(context,
                          title: 'حذف الصف',
                          message: 'حذف كل حركات هذا الصف (${r.ids.length} حركة)؟',
                          danger: true);
                      if (!ok) return;
                      try {
                        await ref.read(txnRepoProvider).deleteMany(r.ids);
                        bumpDataRevision(ref);
                      } catch (e) {
                        if (context.mounted) AppSnack.error(context, '$e');
                      }
                    },
                  )),
                ]);
              }).toList();

              final tKhayas = tMadin - tDaen;
              return DataTableCard(
                title: '${box.icon} ${box.name} — ${ref.watch(periodProvider)}',
                columns: [
                  'الصف', 'الاسم', 'مدين', 'دائن', 'الخياس',
                  if (withTrees) 'عدد الأشجار',
                  if (withTrees) 'خياس كل شجرة',
                  'البيان', 'إجراءات',
                ],
                rows: dataRows,
                totalsRow: dataRows.isEmpty
                    ? null
                    : [
                        'إجمالي الشهر', '-', Fmt.weight(tMadin), Fmt.weight(tDaen),
                        Fmt.weight(tKhayas),
                        if (withTrees) Fmt.carat(tTrees),
                        if (withTrees) (tTrees > 0 ? Fmt.weight(tKhayas / tTrees) : '-'),
                        '-', '-',
                      ],
              );
            },
          ),
        ],
      ),
    );
  }

  Future<void> _openStageDialog(
      BuildContext context, WidgetRef ref, KhayasBox box, bool withTrees) async {
    final name = TextEditingController();
    final rowNo = TextEditingController();
    final sarf = TextEditingController();
    final qabd = TextEditingController();
    final trees = TextEditingController();
    final note = TextEditingController();
    final period = ref.read(periodProvider);
    final date = DateTime.now();

    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: Text('تسجيل حركة ${box.name}'),
        content: SizedBox(
          width: 420,
          child: Column(mainAxisSize: MainAxisSize.min, children: [
            TextField(controller: name, decoration: const InputDecoration(labelText: 'الاسم')),
            const SizedBox(height: 10),
            Row(children: [
              Expanded(
                  child: TextField(
                      controller: rowNo,
                      decoration: const InputDecoration(labelText: 'رقم الصف'))),
              const SizedBox(width: 10),
              Expanded(
                  child: TextField(
                      controller: sarf,
                      keyboardType: TextInputType.number,
                      decoration: const InputDecoration(labelText: 'الصرف (مدين)'))),
              const SizedBox(width: 10),
              Expanded(
                  child: TextField(
                      controller: qabd,
                      keyboardType: TextInputType.number,
                      decoration: const InputDecoration(labelText: 'القبض (دائن)'))),
            ]),
            if (withTrees) ...[
              const SizedBox(height: 10),
              TextField(
                  controller: trees,
                  keyboardType: TextInputType.number,
                  decoration: const InputDecoration(labelText: 'عدد الأشجار')),
            ],
            const SizedBox(height: 10),
            TextField(controller: note, decoration: const InputDecoration(labelText: 'البيان')),
          ]),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('إلغاء')),
          FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('ترحيل')),
        ],
      ),
    );
    if (ok != true) return;

    final tenantId = ref.read(activeTenantIdProvider);
    if (tenantId == null) return;
    final sarfV = double.tryParse(sarf.text.trim()) ?? 0;
    final qabdV = double.tryParse(qabd.text.trim()) ?? 0;
    final treesV = double.tryParse(trees.text.trim()) ?? 0;

    if (name.text.trim().isEmpty) {
      if (context.mounted) AppSnack.warn(context, 'الرجاء إدخال الاسم.');
      return;
    }
    if (sarfV <= 0 && qabdV <= 0) {
      if (context.mounted) AppSnack.warn(context, 'الرجاء إدخال قيمة الصرف أو القبض.');
      return;
    }

    final entries = <Txn>[
      if (sarfV > 0)
        Txn.newEntry(
          date: date,
          accountName: name.text.trim(),
          opType: box.madinType,
          weight: sarfV,
          note: note.text.trim(),
          rowNumber: rowNo.text.trim(),
          treesCount: treesV,
          period: period,
        ),
      if (qabdV > 0)
        Txn.newEntry(
          date: date,
          accountName: name.text.trim(),
          opType: box.qabdType,
          weight: qabdV,
          note: note.text.trim(),
          rowNumber: rowNo.text.trim(),
          treesCount: treesV,
          period: period,
        ),
    ];

    try {
      await ref.read(txnRepoProvider).postMany(tenantId, entries);
      bumpDataRevision(ref);
      if (context.mounted) AppSnack.success(context, 'تم الترحيل وتحديث الأرصدة.');
    } catch (e) {
      if (context.mounted) AppSnack.error(context, '$e');
    }
  }
}
