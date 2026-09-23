import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../core/theme/app_theme.dart';
import '../../data/models/models.dart';
import '../../state/providers.dart';
import '../../widgets/app_snack.dart';

/// شجرة الحسابات: العمال، الموردين، الصناديق، والحسابات العامة.
class AccountsPage extends ConsumerWidget {
  const AccountsPage({super.key});

  static const List<String> categories = [
    'المصنعين',
    'المركبين',
    'الآلة/المكائن',
    'الموردين',
    'صناديق الخياس',
    'حسابات عامة',
  ];

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final accounts = ref.watch(accountsProvider);

    return SingleChildScrollView(
      padding: const EdgeInsets.all(16),
      child: Column(
        crossAxisAlignment: CrossAxisAlignment.stretch,
        children: [
          Row(children: [
            const Text('🗂️ شجرة الحسابات',
                style: TextStyle(
                    fontSize: 18, fontWeight: FontWeight.bold, color: AppTheme.gold)),
            const Spacer(),
            FilledButton.icon(
              onPressed: () => _addAccount(context, ref),
              icon: const Icon(Icons.add),
              label: const Text('إضافة حساب'),
            ),
          ]),
          const SizedBox(height: 14),
          accounts.when(
            loading: () => const Center(
                child: Padding(padding: EdgeInsets.all(30), child: CircularProgressIndicator())),
            error: (e, _) => Center(child: Text('$e')),
            data: (list) => Column(
              children: categories.map((cat) {
                final items = list.where((a) => a.category == cat).toList();
                return Card(
                  margin: const EdgeInsets.only(bottom: 12),
                  child: ExpansionTile(
                    initiallyExpanded: items.isNotEmpty,
                    title: Text('$cat  (${items.length})',
                        style: const TextStyle(fontWeight: FontWeight.bold)),
                    children: items.isEmpty
                        ? const [
                            ListTile(
                                dense: true,
                                title: Text('لا توجد حسابات في هذا القسم',
                                    style: TextStyle(color: Colors.grey)))
                          ]
                        : items.map((a) => _accountTile(context, ref, a)).toList(),
                  ),
                );
              }).toList(),
            ),
          ),
        ],
      ),
    );
  }

  Widget _accountTile(BuildContext context, WidgetRef ref, Account account) {
    return ListTile(
      dense: true,
      leading: const Icon(Icons.person_outline, size: 18),
      title: Text(account.name),
      subtitle: account.isSystem
          ? const Text('حساب نظامي — لا يمكن حذفه', style: TextStyle(fontSize: 11))
          : null,
      trailing: account.isSystem
          ? null
          : IconButton(
              icon: const Icon(Icons.delete_outline, color: AppTheme.danger, size: 20),
              onPressed: () async {
                final ok = await confirmDialog(
                  context,
                  title: 'حذف الحساب',
                  message: 'حذف الحساب (${account.name})؟\n'
                      'الحركات المسجّلة باسمه تبقى محفوظة ولا تُحذف.',
                  danger: true,
                );
                if (!ok) return;
                try {
                  await ref.read(accountRepoProvider).remove(account.id);
                  bumpDataRevision(ref);
                  if (context.mounted) AppSnack.success(context, 'تم حذف الحساب.');
                } catch (e) {
                  if (context.mounted) AppSnack.error(context, '$e');
                }
              },
            ),
    );
  }

  Future<void> _addAccount(BuildContext context, WidgetRef ref) async {
    final name = TextEditingController();
    String category = categories.first;

    final ok = await showDialog<bool>(
      context: context,
      builder: (ctx) => StatefulBuilder(
        builder: (ctx, setState) => AlertDialog(
          title: const Text('إضافة حساب جديد'),
          content: SizedBox(
            width: 340,
            child: Column(mainAxisSize: MainAxisSize.min, children: [
              TextField(
                  controller: name,
                  autofocus: true,
                  decoration: const InputDecoration(labelText: 'اسم الحساب')),
              const SizedBox(height: 12),
              DropdownButtonFormField<String>(
                value: category,
                decoration: const InputDecoration(labelText: 'القسم'),
                items: categories
                    .map((c) => DropdownMenuItem(value: c, child: Text(c)))
                    .toList(),
                onChanged: (v) => setState(() => category = v ?? categories.first),
              ),
            ]),
          ),
          actions: [
            TextButton(onPressed: () => Navigator.pop(ctx, false), child: const Text('إلغاء')),
            FilledButton(onPressed: () => Navigator.pop(ctx, true), child: const Text('إضافة')),
          ],
        ),
      ),
    );
    if (ok != true || name.text.trim().isEmpty) return;

    final tenantId = ref.read(activeTenantIdProvider);
    if (tenantId == null) return;
    try {
      await ref.read(accountRepoProvider).add(tenantId, name.text.trim(), category);
      bumpDataRevision(ref);
      if (context.mounted) AppSnack.success(context, 'تمت إضافة الحساب.');
    } catch (e) {
      if (context.mounted) AppSnack.error(context, '$e');
    }
  }
}
