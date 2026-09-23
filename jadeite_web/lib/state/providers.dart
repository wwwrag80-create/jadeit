import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/utils/formatters.dart';
import '../data/models/models.dart';
import '../data/repositories/repositories.dart';
import 'session_controller.dart';

// ---------- المستودعات ----------
final authRepoProvider = Provider((_) => AuthRepository());
final tenantRepoProvider = Provider((_) => TenantRepository());
final accountRepoProvider = Provider((_) => AccountRepository());
final txnRepoProvider = Provider((_) => TxnRepository());
final ledgerRepoProvider = Provider((_) => LedgerRepository());
final journalRepoProvider = Provider((_) => JournalRepository());
final closingRepoProvider = Provider((_) => ClosingRepository());

// ---------- الجلسة ----------
final sessionProvider = StateNotifierProvider<SessionController, SessionState>(
  (ref) => SessionController(ref.read(authRepoProvider), ref.read(tenantRepoProvider)),
);

/// المستأجر الفعّال — كل استعلامات البيانات تمر من هنا
final activeTenantIdProvider = Provider<String?>(
  (ref) => ref.watch(sessionProvider).activeTenantId,
);

// ---------- الفترة المحاسبية المعروضة ----------
class PeriodController extends StateNotifier<String> {
  PeriodController() : super(Fmt.currentPeriod());

  void set(String period) => state = period;
  void previous() => state = Fmt.shiftPeriod(state, -1);
  void next() => state = Fmt.shiftPeriod(state, 1);
  void resetToCurrent() => state = Fmt.currentPeriod();
}

final periodProvider = StateNotifierProvider<PeriodController, String>(
  (_) => PeriodController(),
);

// ---------- بيانات مشتقّة ----------
final accountsProvider = FutureProvider.autoDispose<List<Account>>((ref) async {
  final tenantId = ref.watch(activeTenantIdProvider);
  if (tenantId == null) return const [];
  return ref.read(accountRepoProvider).list(tenantId);
});

final treasuryProvider = FutureProvider.autoDispose<double>((ref) async {
  final tenantId = ref.watch(activeTenantIdProvider);
  final period = ref.watch(periodProvider);
  if (tenantId == null) return 0;
  return ref.read(ledgerRepoProvider).treasuryBalance(tenantId, untilPeriod: period);
});

final workshopLossesProvider = FutureProvider.autoDispose<double>((ref) async {
  final tenantId = ref.watch(activeTenantIdProvider);
  final period = ref.watch(periodProvider);
  if (tenantId == null) return 0;
  return ref.read(ledgerRepoProvider).workshopLosses(tenantId, period);
});

final salesInvoicesProvider =
    FutureProvider.autoDispose<List<SalesInvoiceSummary>>((ref) async {
  final tenantId = ref.watch(activeTenantIdProvider);
  final period = ref.watch(periodProvider);
  if (tenantId == null) return const [];
  return ref.read(ledgerRepoProvider).salesInvoices(tenantId, period);
});

final adminTenantsProvider = FutureProvider.autoDispose<List<Tenant>>((ref) async {
  return ref.read(tenantRepoProvider).adminOverview();
});

/// حالة جهاز العميل المعروض حالياً — يعرفها المدير قبل أن يعدّل بياناته
final activeTenantSyncProvider = FutureProvider.autoDispose<SyncOverview?>((ref) async {
  final tenantId = ref.watch(activeTenantIdProvider);
  final session = ref.watch(sessionProvider);
  if (tenantId == null || !(session.user?.isAdmin ?? false)) return null;
  final all = await ref.watch(syncOverviewProvider.future);
  for (final row in all) {
    if (row.tenantId == tenantId) return row;
  }
  return null;
});

/// حالة مزامنة كل العملاء — تتحدّث لحظياً مع نبضات أجهزتهم
final syncOverviewProvider = FutureProvider.autoDispose<List<SyncOverview>>((ref) async {
  final session = ref.watch(sessionProvider);
  if (!(session.user?.isAdmin ?? false)) return const [];
  return ref.read(tenantRepoProvider).syncOverview();
});
