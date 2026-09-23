import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/app_theme.dart';
import '../../core/utils/formatters.dart';
import '../../data/models/models.dart';
import '../../state/providers.dart';
import '../../widgets/app_snack.dart';

/// شاشة متابعة المزامنة: تُظهر للمدير حالة كل عميل وأجهزته لحظة بلحظة —
/// من متصل الآن، وكم حركة عالقة عنده، وآخر خطأ واجهه برنامجه.
class SyncMonitorPage extends ConsumerWidget {
  const SyncMonitorPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final overview = ref.watch(syncOverviewProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('متابعة المزامنة — أجهزة العملاء'),
        actions: [
          IconButton(
            tooltip: 'تحديث',
            icon: const Icon(Icons.refresh),
            onPressed: () => ref.invalidate(syncOverviewProvider),
          ),
          const SizedBox(width: 8),
        ],
      ),
      body: overview.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(
          child: Padding(
            padding: const EdgeInsets.all(24),
            child: Text('تعذّر تحميل حالة المزامنة:\n$e', textAlign: TextAlign.center),
          ),
        ),
        data: (list) {
          if (list.isEmpty) {
            return const Center(child: Text('لا يوجد عملاء مسجّلون بعد'));
          }

          final online = list.where((t) => t.isOnline).length;
          final stuck = list.where((t) => t.pendingCount > 0).length;
          final failing = list.where((t) => !t.isHealthy).length;

          return Column(
            children: [
              Padding(
                padding: const EdgeInsets.all(16),
                child: Card(
                  child: Padding(
                    padding: const EdgeInsets.all(18),
                    child: Wrap(spacing: 34, runSpacing: 14, children: [
                      _Kpi(label: 'إجمالي العملاء', value: '${list.length}', color: AppTheme.blue),
                      _Kpi(label: 'متصل الآن', value: '$online', color: AppTheme.success),
                      _Kpi(label: 'عنده حركات معلّقة', value: '$stuck', color: AppTheme.warn),
                      _Kpi(label: 'مزامنته متعثّرة', value: '$failing', color: AppTheme.danger),
                    ]),
                  ),
                ),
              ),
              Expanded(
                child: ListView.separated(
                  padding: const EdgeInsets.fromLTRB(16, 0, 16, 16),
                  itemCount: list.length,
                  separatorBuilder: (_, __) => const SizedBox(height: 10),
                  itemBuilder: (_, i) => _SyncCard(row: list[i]),
                ),
              ),
            ],
          );
        },
      ),
    );
  }
}

class _SyncCard extends ConsumerWidget {
  const _SyncCard({required this.row});
  final SyncOverview row;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final statusColor = !row.isActive
        ? Colors.grey
        : !row.isHealthy
            ? AppTheme.danger
            : row.isOnline
                ? AppTheme.success
                : Colors.grey;

    final statusText = !row.isActive
        ? '⛔ الحساب موقوف'
        : row.isOnline
            ? '🟢 متصل الآن'
            : row.lastSyncAt == null
                ? '⚪ لم يزامن بعد'
                : '⚫ آخر مزامنة ${Fmt.since(row.lastSyncAt!)}';

    return Card(
      child: Padding(
        padding: const EdgeInsets.all(16),
        child: Column(
          crossAxisAlignment: CrossAxisAlignment.start,
          children: [
            Row(children: [
              Container(width: 10, height: 10,
                  decoration: BoxDecoration(color: statusColor, shape: BoxShape.circle)),
              const SizedBox(width: 10),
              Expanded(
                child: Text(row.businessName,
                    style: const TextStyle(fontSize: 17, fontWeight: FontWeight.bold)),
              ),
              Text(statusText, style: TextStyle(color: statusColor, fontWeight: FontWeight.bold)),
            ]),
            const SizedBox(height: 12),
            Wrap(spacing: 26, runSpacing: 10, children: [
              _Chip(label: 'الحركات في السحابة', value: '${row.txnCount}'),
              _Chip(label: 'الأجهزة', value: '${row.devices}'),
              _Chip(
                label: 'معلّق للرفع',
                value: '${row.pendingCount}',
                color: row.pendingCount > 0 ? AppTheme.warn : null,
              ),
              _Chip(
                label: 'آخر حركة',
                value: row.lastTxnAt == null ? '—' : Fmt.date(row.lastTxnAt!),
              ),
              _Chip(
                label: 'المزامنة',
                value: row.syncEnabled ? 'مفعّلة' : 'موقوفة',
                color: row.syncEnabled ? null : AppTheme.danger,
              ),
            ]),
            if (row.lastError != null && row.lastError!.isNotEmpty) ...[
              const SizedBox(height: 12),
              Container(
                width: double.infinity,
                padding: const EdgeInsets.all(10),
                decoration: BoxDecoration(
                  color: AppTheme.danger.withValues(alpha: 0.10),
                  borderRadius: BorderRadius.circular(8),
                ),
                child: Text('آخر خطأ عند العميل: ${row.lastError}',
                    style: const TextStyle(color: AppTheme.danger, fontSize: 12)),
              ),
            ],
            const SizedBox(height: 12),
            Row(children: [
              FilledButton.icon(
                onPressed: () => ref.read(sessionProvider.notifier).enterTenant(row.tenantId),
                icon: const Icon(Icons.login, size: 18),
                label: const Text('دخول على حسابه'),
              ),
              const SizedBox(width: 8),
              OutlinedButton.icon(
                onPressed: () => _rotate(context, ref),
                icon: const Icon(Icons.key_outlined, size: 18),
                label: const Text('تجديد رمز المزامنة'),
              ),
            ]),
          ],
        ),
      ),
    );
  }

  Future<void> _rotate(BuildContext context, WidgetRef ref) async {
    final ok = await confirmDialog(
      context,
      title: 'تجديد رمز المزامنة',
      message: 'سيتوقف رفع البيانات من **كل** أجهزة (${row.businessName}) فوراً '
          'حتى تضع الرمز الجديد في ملف device_session.json على كل جهاز.\n\n'
          'استخدمها فقط عند تسريب الرمز أو فقدان جهاز. هل تريد المتابعة؟',
      confirmLabel: 'تجديد',
      danger: true,
    );
    if (!ok) return;

    try {
      final token = await ref.read(tenantRepoProvider).rotateSyncToken(row.tenantId);
      ref.invalidate(syncOverviewProvider);
      if (!context.mounted) return;
      await showDialog<void>(
        context: context,
        builder: (ctx) => AlertDialog(
          title: const Text('الرمز الجديد'),
          content: SelectableText(
            'ضع هذا في device_session.json على أجهزة العميل:\n\n'
            '"tenant_id": "${row.tenantId}",\n"sync_token": "$token"',
            style: const TextStyle(fontFamily: 'monospace', fontSize: 12),
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('تم')),
          ],
        ),
      );
    } catch (e) {
      if (context.mounted) AppSnack.error(context, '$e');
    }
  }
}

class _Chip extends StatelessWidget {
  const _Chip({required this.label, required this.value, this.color});
  final String label;
  final String value;
  final Color? color;

  @override
  Widget build(BuildContext context) {
    return Column(
      crossAxisAlignment: CrossAxisAlignment.start,
      mainAxisSize: MainAxisSize.min,
      children: [
        Text(label, style: const TextStyle(fontSize: 11, color: Colors.grey)),
        const SizedBox(height: 2),
        Text(value,
            style: TextStyle(fontSize: 15, fontWeight: FontWeight.bold, color: color)),
      ],
    );
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
            style: TextStyle(fontSize: 24, fontWeight: FontWeight.bold, color: color)),
      ],
    );
  }
}
