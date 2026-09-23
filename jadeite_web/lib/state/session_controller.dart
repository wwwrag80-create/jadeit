import 'dart:async';

import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../core/config/supabase_config.dart';
import '../core/utils/error_text.dart';
import '../data/models/models.dart';
import '../data/repositories/repositories.dart';

/// حالة الجلسة: من أنا، وأي مستأجر أعمل عليه الآن.
///
/// انتحال الشخصية (Impersonation): المدير يختار عميلاً فيتغيّر [activeTenantId]
/// فقط — وكل الاستعلامات في التطبيق مبنية على هذا المعرّف، فينتقل فوراً لواجهة
/// العميل ويرى بياناته لحظياً كما يراها هو، بدون تسجيل خروج ولا كلمة مرور.
class SessionState {
  const SessionState({
    this.user,
    this.activeTenant,
    this.canEdit = true,
    this.loading = false,
    this.error,
  });

  final AppUser? user;
  final Tenant? activeTenant;
  final bool canEdit;
  final bool loading;
  final String? error;

  bool get isSignedIn => user != null;
  bool get isAdmin => user?.isAdmin ?? false;
  String? get activeTenantId => activeTenant?.id;

  /// المدير أثناء انتحال شخصية عميل
  bool get isImpersonating => isAdmin && activeTenant != null;

  /// التعديل مقفول؟ المدير غير مقيّد إطلاقاً
  bool get isEditLocked => !isAdmin && !canEdit;

  SessionState copyWith({
    AppUser? user,
    Tenant? activeTenant,
    bool? canEdit,
    bool? loading,
    String? error,
    bool clearTenant = false,
    bool clearError = false,
  }) =>
      SessionState(
        user: user ?? this.user,
        activeTenant: clearTenant ? null : (activeTenant ?? this.activeTenant),
        canEdit: canEdit ?? this.canEdit,
        loading: loading ?? this.loading,
        error: clearError ? null : (error ?? this.error),
      );
}

class SessionController extends StateNotifier<SessionState> {
  SessionController(this._auth, this._tenants) : super(const SessionState()) {
    restore();
  }

  final AuthRepository _auth;
  final TenantRepository _tenants;

  Timer? _heartbeat;
  Timer? _permissionPoll;

  /// استعادة الجلسة عند فتح التطبيق (المتصفح يحتفظ بها)
  Future<void> restore() async {
    state = state.copyWith(loading: true);
    try {
      final user = await _auth.currentAppUser();
      if (user == null) {
        state = const SessionState();
        return;
      }
      state = state.copyWith(user: user, loading: false);
      if (!user.isAdmin && user.tenantId != null) {
        await enterTenant(user.tenantId!, isLogin: false);
      }
    } catch (e) {
      state = state.copyWith(loading: false, error: ErrorText.friendly(e));
    }
  }

  Future<bool> signIn(String email, String password) async {
    state = state.copyWith(loading: true, clearError: true);
    try {
      final user = await _auth.signIn(email, password);
      if (user == null) {
        // الدخول نجح في المصادقة لكن لا يوجد سجل مقابل في app_users
        state = state.copyWith(
          loading: false,
          error: 'تم التحقق من الحساب، لكنه غير مربوط بالنظام بعد.\n\n'
              'الحل: شغّل الملف 01_create_admin.sql في Supabase بعد وضع بريدك فيه.',
        );
        return false;
      }
      state = state.copyWith(user: user, loading: false);
      if (!user.isAdmin && user.tenantId != null) {
        await enterTenant(user.tenantId!, isLogin: true);
      }
      return true;
    } catch (e) {
      state = state.copyWith(loading: false, error: ErrorText.friendly(e));
      return false;
    }
  }

  /// الدخول لمستأجر: يستخدمه العميل عند تسجيل دخوله، ويستخدمه المدير للانتحال.
  Future<void> enterTenant(String tenantId, {bool isLogin = false}) async {
    final tenant = await _tenants.byId(tenantId);
    if (tenant == null) {
      state = state.copyWith(error: 'تعذّر الوصول لهذا المصنع — تأكد أنه موجود ومفعّل.');
      return;
    }
    state = state.copyWith(activeTenant: tenant, canEdit: tenant.canEdit, clearError: true);

    await _tenants.touchActivity(tenantId, isLogin: isLogin);
    _startTimers(tenantId);
  }

  /// خروج المدير من واجهة العميل والعودة للوحته
  void exitTenant() {
    if (!state.isAdmin) return;
    _stopTimers();
    state = state.copyWith(clearTenant: true);
  }

  Future<void> refreshPermission() async {
    final tenantId = state.activeTenantId;
    if (tenantId == null) return;
    final value = await _tenants.canEdit(tenantId);
    if (value != state.canEdit) {
      state = state.copyWith(canEdit: value);
    }
  }

  void _startTimers(String tenantId) {
    _stopTimers();

    // نبض الحضور: يجعل المدير يرى "متصل الآن"، وهو استعلام خفيف جداً
    _heartbeat = Timer.periodic(SupabaseConfig.heartbeatInterval, (_) {
      _tenants.touchActivity(tenantId);
    });

    // قفل/فتح التعديل من المدير يصل للعميل خلال ثوانٍ بدون إعادة تشغيل
    _permissionPoll = Timer.periodic(SupabaseConfig.permissionPollInterval, (_) {
      refreshPermission();
    });
  }

  void _stopTimers() {
    _heartbeat?.cancel();
    _permissionPoll?.cancel();
    _heartbeat = null;
    _permissionPoll = null;
  }

  Future<void> signOut() async {
    _stopTimers();
    await _auth.signOut();
    state = const SessionState();
  }

  @override
  void dispose() {
    _stopTimers();
    super.dispose();
  }
}
