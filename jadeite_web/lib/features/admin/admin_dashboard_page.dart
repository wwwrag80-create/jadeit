import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/app_theme.dart';
import '../../core/utils/formatters.dart';
import '../../data/models/models.dart';
import '../../state/providers.dart';
import 'sync_monitor_page.dart';

/// لوحة المدير: قائمة العملاء مع حالتهم، والضغط على أي عميل يدخل لواجهته فوراً.
class AdminDashboardPage extends ConsumerWidget {
  const AdminDashboardPage({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final tenantsAsync = ref.watch(adminTenantsProvider);

    return Scaffold(
      appBar: AppBar(
        title: const Text('لوحة الإدارة — عملاء جاديت'),
        actions: [
          IconButton(
            tooltip: 'متابعة المزامنة',
            icon: const Icon(Icons.cloud_sync_outlined),
            onPressed: () => Navigator.of(context).push(
              MaterialPageRoute(builder: (_) => const SyncMonitorPage()),
            ),
          ),
          IconButton(
            tooltip: 'تحديث',
            icon: const Icon(Icons.refresh),
            onPressed: () {
              ref.invalidate(adminTenantsProvider);
              ref.invalidate(syncOverviewProvider);
            },
          ),
          IconButton(
            tooltip: 'خروج',
            icon: const Icon(Icons.logout),
            onPressed: () => ref.read(sessionProvider.notifier).signOut(),
          ),
          const SizedBox(width: 8),
        ],
      ),
      floatingActionButton: FloatingActionButton.extended(
        onPressed: () => _createTenant(context, ref),
        icon: const Icon(Icons.add_business),
        label: const Text('إضافة عميل'),
      ),
      body: tenantsAsync.when(
        loading: () => const Center(child: CircularProgressIndicator()),
        error: (e, _) => Center(child: Text('تعذّر تحميل العملاء:\n$e', textAlign: TextAlign.center)),
        data: (tenants) => tenants.isEmpty
            ? const Center(child: Text('لا يوجد عملاء مسجّلون بعد'))
            : ListView.separated(
                padding: const EdgeInsets.all(20),
                itemCount: tenants.length,
                separatorBuilder: (_, __) => const SizedBox(height: 10),
                itemBuilder: (_, i) => _TenantCard(tenant: tenants[i]),
              ),
      ),
    );
  }

  Future<void> _createTenant(BuildContext context, WidgetRef ref) async {
    final controller = TextEditingController();
    final name = await showDialog<String>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('إضافة عميل جديد'),
        content: TextField(
          controller: controller,
          autofocus: true,
          decoration: const InputDecoration(labelText: 'اسم المصنع'),
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx), child: const Text('إلغاء')),
          FilledButton(
            onPressed: () => Navigator.pop(ctx, controller.text.trim()),
            child: const Text('إنشاء'),
          ),
        ],
      ),
    );
    if (name == null || name.isEmpty) return;
    await ref.read(tenantRepoProvider).create(name);
    ref.invalidate(adminTenantsProvider);
  }
}

class _TenantCard extends ConsumerWidget {
  const _TenantCard({required this.tenant});

  final Tenant tenant;

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    return Card(
      child: InkWell(
        borderRadius: BorderRadius.circular(14),
        // انتحال الشخصية: تغيير المستأجر الفعّال ينقل المدير فوراً لواجهة العميل
        onTap: () => ref.read(sessionProvider.notifier).enterTenant(tenant.id),
        child: Padding(
          padding: const EdgeInsets.all(14),
          // على الجوال تنزل الأزرار تحت البيانات بدل أن تنضغط بجانبها
          child: Flex(
            direction: MediaQuery.sizeOf(context).width < 620
                ? Axis.vertical
                : Axis.horizontal,
            crossAxisAlignment: CrossAxisAlignment.start,
            children: [
              Flexible(
                fit: FlexFit.loose,
                child: Column(
                  crossAxisAlignment: CrossAxisAlignment.start,
                  children: [
                    // Wrap بدل Row: الشارات تنزل لسطر جديد على الجوال بدل أن تفيض
                    Wrap(
                      spacing: 8,
                      runSpacing: 6,
                      crossAxisAlignment: WrapCrossAlignment.center,
                      children: [
                        Text(
                          tenant.businessName,
                          style: const TextStyle(fontSize: 17, fontWeight: FontWeight.bold),
                        ),
                        _Chip(
                          label: tenant.isOnline ? 'متصل الآن' : Fmt.since(tenant.lastSeen),
                          color: tenant.isOnline ? AppTheme.success : Colors.grey,
                        ),
                        _Chip(
                          label: tenant.isActive ? 'نشط' : 'موقوف',
                          color: tenant.isActive ? AppTheme.blue : AppTheme.danger,
                        ),
                        _Chip(
                          label: tenant.canEdit ? 'التعديل مفتوح' : 'التعديل مقفول',
                          color: tenant.canEdit ? AppTheme.success : AppTheme.warn,
                        ),
                      ],
                    ),
                    const SizedBox(height: 8),
                    Text(
                      '🔑 آخر دخول: ${Fmt.dateTime(tenant.lastLogin)}\n'
                      '📊 عدد الحركات: ${tenant.txnCount}',
                      style: const TextStyle(color: Colors.grey, fontSize: 12),
                    ),
                  ],
                ),
              ),
              const SizedBox(height: 10, width: 10),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                children: [
                  // زر انتحال الشخصية: كبير وواضح ليعمل باللمس بسهولة
                  FilledButton.icon(
                    style: FilledButton.styleFrom(
                      minimumSize: const Size(150, 46),
                      textStyle: const TextStyle(fontWeight: FontWeight.bold),
                    ),
                    onPressed: () => ref.read(sessionProvider.notifier).enterTenant(tenant.id),
                    icon: const Icon(Icons.login, size: 18),
                    label: const Text('دخول كالعميل'),
                  ),
                  OutlinedButton.icon(
                    style: OutlinedButton.styleFrom(minimumSize: const Size(130, 46)),
                    onPressed: () async {
                      await ref.read(tenantRepoProvider).setCanEdit(tenant.id, !tenant.canEdit);
                      ref.invalidate(adminTenantsProvider);
                    },
                    icon: Icon(tenant.canEdit ? Icons.lock_outline : Icons.lock_open, size: 18),
                    label: Text(tenant.canEdit ? 'إغلاق التعديل' : 'فتح التعديل'),
                  ),
                  IconButton(
                    tooltip: 'حذف الحساب نهائياً',
                    color: AppTheme.danger,
                    icon: const Icon(Icons.delete_outline),
                    onPressed: () => _confirmDelete(context, ref),
                  ),
                ],
              ),
            ],
          ),
        ),
      ),
    );
  }

  Future<void> _confirmDelete(BuildContext context, WidgetRef ref) async {
    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => AlertDialog(
        title: const Text('⚠️ حذف نهائي'),
        content: Text(
          'سيتم حذف حساب "${tenant.businessName}" وكل حركاته وحساباته نهائياً.\n'
          'هذا الإجراء لا يمكن التراجع عنه.',
        ),
        actions: [
          TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('إلغاء')),
          FilledButton(
            style: FilledButton.styleFrom(backgroundColor: AppTheme.danger),
            onPressed: () => Navigator.pop(ctx, true),
            child: const Text('حذف'),
          ),
        ],
      ),
    );
    if (ok != true) return;
    await ref.read(tenantRepoProvider).delete(tenant.id);
    ref.invalidate(adminTenantsProvider);
  }
}

class _Chip extends StatelessWidget {
  const _Chip({required this.label, required this.color});

  final String label;
  final Color color;

  @override
  Widget build(BuildContext context) => Container(
        padding: const EdgeInsets.symmetric(horizontal: 10, vertical: 3),
        decoration: BoxDecoration(
          color: color.withValues(alpha: 0.15),
          borderRadius: BorderRadius.circular(20),
          border: Border.all(color: color.withValues(alpha: 0.4)),
        ),
        child: Text(label, style: TextStyle(color: color, fontSize: 12, fontWeight: FontWeight.bold)),
      );
}
