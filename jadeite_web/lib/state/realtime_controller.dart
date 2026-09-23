import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:supabase_flutter/supabase_flutter.dart';

import '../core/config/supabase_config.dart';
import 'providers.dart';

/// حالة البث اللحظي: متصل؟ وكم حركة وصلت منذ فتح الشاشة؟
class RealtimeState {
  const RealtimeState({
    this.connected = false,
    this.eventCount = 0,
    this.lastEventAt,
  });

  final bool connected;
  final int eventCount;
  final DateTime? lastEventAt;

  RealtimeState copyWith({bool? connected, int? eventCount, DateTime? lastEventAt}) =>
      RealtimeState(
        connected: connected ?? this.connected,
        eventCount: eventCount ?? this.eventCount,
        lastEventAt: lastEventAt ?? this.lastEventAt,
      );
}

/// يشترك في تغييرات جدول الحركات **للمستأجر المعروض حالياً فقط**،
/// ويُبطل الـ providers المعنية فور وصول أي تغيير، فتتحدّث الشاشات لحظياً
/// دون أن يضغط المدير أي زر تحديث.
///
/// عند تبديل العميل (انتحال الشخصية) يُلغى الاشتراك القديم ويُفتح اشتراك جديد
/// مقيّد بالمستأجر الجديد — فلا تصل للمدير أحداث عميل غير الذي يشاهده.
class RealtimeController extends StateNotifier<RealtimeState> {
  RealtimeController(this._ref) : super(const RealtimeState()) {
    // نتابع تغيّر المستأجر النشط ونعيد ضبط الاشتراك تلقائياً
    _ref.listen<String?>(activeTenantIdProvider, (previous, next) {
      if (previous != next) subscribe(next);
    }, fireImmediately: true);
  }

  final Ref _ref;
  RealtimeChannel? _channel;
  Timer? _debounce;

  Future<void> subscribe(String? tenantId) async {
    await _unsubscribe();
    if (tenantId == null || tenantId.isEmpty) {
      state = const RealtimeState();
      return;
    }

    final channel = db.channel('tenant:$tenantId');

    for (final event in [
      PostgresChangeEvent.insert,
      PostgresChangeEvent.update,
      PostgresChangeEvent.delete,
    ]) {
      channel.onPostgresChanges(
        event: event,
        schema: 'public',
        table: 'transactions',
        filter: PostgresChangeFilter(
          type: PostgresChangeFilterType.eq,
          column: 'tenant_id',
          value: tenantId,
        ),
        callback: (_) => _onChange(),
      );
    }

    // حالة أجهزة العميل (نبضة المزامنة) تتحدّث لحظياً أيضاً
    channel.onPostgresChanges(
      event: PostgresChangeEvent.all,
      schema: 'public',
      table: 'tenant_devices',
      filter: PostgresChangeFilter(
        type: PostgresChangeFilterType.eq,
        column: 'tenant_id',
        value: tenantId,
      ),
      callback: (_) => _onDeviceChange(),
    );

    channel.subscribe((status, error) {
      state = state.copyWith(connected: status == RealtimeSubscribeStatus.subscribed);
    });

    _channel = channel;
  }

  /// تجميع الأحداث المتقاربة في تحديث واحد:
  /// رفع دفعة من ٢٠٠ حركة يُطلق ٢٠٠ حدثاً، وإعادة الحساب ٢٠٠ مرة تُجمّد الشاشة.
  void _onChange() {
    state = state.copyWith(
      eventCount: state.eventCount + 1,
      lastEventAt: DateTime.now(),
    );
    _debounce?.cancel();
    _debounce = Timer(const Duration(milliseconds: 700), _refreshData);
  }

  void _onDeviceChange() {
    _ref.invalidate(syncOverviewProvider);
    _ref.invalidate(adminTenantsProvider);
  }

  /// زيادة إصدار البيانات تُحدّث كل الشاشات المفتوحة معاً (الوارد، الصناديق،
  /// الكشوف…) لا الخزينة والفواتير فقط كما كان سابقاً
  void _refreshData() {
    _ref.read(dataRevisionProvider.notifier).state++;
  }

  Future<void> _unsubscribe() async {
    _debounce?.cancel();
    final channel = _channel;
    _channel = null;
    if (channel != null) {
      try {
        await db.removeChannel(channel);
      } catch (_) {
        // إغلاق القناة قد يفشل لو انقطعت الشبكة — لا يضر، القناة الجديدة ستحل محلها
      }
    }
  }

  @override
  void dispose() {
    _unsubscribe();
    super.dispose();
  }
}

final realtimeProvider =
    StateNotifierProvider<RealtimeController, RealtimeState>((ref) => RealtimeController(ref));
