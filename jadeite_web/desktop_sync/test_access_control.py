# -*- coding: utf-8 -*-
"""
مدة اشتراك كل مصنع وعدد أجهزته (1.68.0 — مع supabase/21_access_control.sql):

  • المدة: اليوم الأخير بتوقيت الجهاز حتى نهايته، والتجديد يبدأ من نهاية المدة الحالية أو من اليوم،
    ووصفها للمدير والعميل (مفتوح / حتى … باقي … / ينتهي اليوم / منتهي).
  • الأجهزة: المسموح أقدمها تسجيلاً بقدر العدد — القاعدة نفسها في السحابة.
  • بصمة الجهاز: ثابتة، ٣٢ حرفاً، لا تكشف معرّف ويندوز، ومعرّف احتياطي يُحفظ مرة واحدة.
  • الدخول: الدالة الأحدث أولاً، والسبب واضح (منتهي / الأجهزة مكتملة / موقوف) بلا رمز مزامنة،
    والأقدم فقط إن لم تكن الأحدث مثبّتة — لا عند انقطاع الإنترنت (وإلا تُتجاوز الفحوص).
  • البرنامج المفتوح: يُقفل عند انتهاء المدة أو إزالة الجهاز — وبلا إنترنت بساعة الجهاز —
    ويُفتح حين يجدّد المدير. برنامج المدير لا يُقفل ولا يشغل مكان جهاز.
"""
import ast, datetime, hashlib, io, os, re, shutil, sys, tempfile, threading, types, calendar

TARGET = sys.argv[1] if len(sys.argv) > 1 else "rageh-1-34-14-cloud.py"
src = io.open(TARGET, encoding="utf-8").read()
tree = ast.parse(src)
IS_ADMIN = bool(re.search(r"^IS_ADMIN_BUILD = True", src, re.M))
cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "GoldSystemApp")
admin_cls = next(n for n in tree.body if isinstance(n, ast.ClassDef) and n.name == "AdminPanel")


def module_src(name):
    n = next(x for x in tree.body if (isinstance(x, ast.FunctionDef) and x.name == name)
             or (isinstance(x, ast.Assign) and getattr(x.targets[0], "id", "") == name))
    return ast.get_source_segment(src, n)


def method_src(klass, name):
    n = next(x for x in klass.body if isinstance(x, ast.FunctionDef) and x.name == name)
    return ast.get_source_segment(src, n)


tmp = tempfile.mkdtemp(prefix="jadeite_access_test_")
errors = []
g = {"os": os, "re": re, "sys": sys, "datetime": datetime, "hashlib": hashlib, "calendar": calendar,
     "threading": threading, "IS_ADMIN_BUILD": IS_ADMIN, "APP_VERSION": "1.68.0", "APP_DATA_DIR": tmp,
     "SUPABASE_SECRET_KEY": None, "CURRENT_SYNC_TOKEN": None,
     "log_cloud_error": lambda msg, e=None: errors.append((msg, str(e))),
     "hash_password": lambda pw: "H(" + pw + ")"}
for name in ("ACCESS_BLOCKING", "ACCESS_WARN_DAYS", "ACCESS_POPUP_DAYS", "ACCESS_EXTEND_CHOICES",
             "ACCESS_DEVICE_CHOICES", "ACCESS_UNLIMITED", "CLIENT_LOGIN_VIA", "_DEVICE_IDENTITY",
             "_read_machine_guid", "_device_display_name", "device_identity", "parse_cloud_timestamp",
             "access_end_of_day", "access_local_date", "add_months", "extend_access", "arabic_days",
             "arabic_devices", "access_days_left", "describe_access", "device_rows", "describe_devices",
             "access_denial_message", "_rpc_missing", "cloud_client_login", "cloud_verify_client_login",
             "cloud_client_access_check", "cloud_touch_client_activity", "_ACTIVITY_TRACKING_SUPPORTED"):
    exec(module_src(name), g)

try:
    D = datetime.date
    UTC = datetime.timezone.utc

    # ═══ ١) المدة والتجديد ═══
    assert g["add_months"](D(2026, 1, 31), 1) == D(2026, 2, 28) and g["add_months"](D(2028, 1, 31), 1) == D(2028, 2, 29)
    assert g["add_months"](D(2026, 11, 15), 3) == D(2027, 2, 15) and g["add_months"](D(2026, 10, 7), 12) == D(2027, 10, 7)
    today = D(2026, 10, 7)
    ext = g["extend_access"]
    assert ext(None, 1, today) == D(2026, 11, 7), "حساب مفتوح: شهر من اليوم"
    assert ext(D(2026, 12, 1), 1, today) == D(2027, 1, 1), "التجديد من نهاية المدة الحالية"
    assert ext(D(2026, 9, 1), 3, today) == D(2027, 1, 7), "المنتهي: التجديد من اليوم لا من التاريخ القديم"
    end = g["access_end_of_day"](D(2026, 12, 1))
    assert end.tzinfo is not None and g["access_local_date"](end) == D(2026, 12, 1), "اليوم الأخير يبقى نفسه عند العرض"
    assert end.astimezone().time() == datetime.time(23, 59, 59), "يعمل حتى نهاية يومه الأخير"
    assert ext(end, 1, today) == D(2027, 1, 1), "التجديد يقبل وقت النهاية كما في السحابة"

    pt = g["parse_cloud_timestamp"]
    assert pt("2026-12-01T20:59:59+00:00") == datetime.datetime(2026, 12, 1, 20, 59, 59, tzinfo=UTC)
    assert pt("2026-12-01T20:59:59.12345+00:00").microsecond == 123450, "كسور الثانية بخمسة أرقام (Supabase)"
    assert pt("2026-12-01 20:59:59Z") == datetime.datetime(2026, 12, 1, 20, 59, 59, tzinfo=UTC)
    assert pt(None) is None and pt("") is None and pt("غير صالح") is None

    now = datetime.datetime.now(UTC)
    da = g["describe_access"]
    assert da(None) == ("♾️ مفتوح بلا حد", "open")
    assert da(None, is_active=False)[1] == "inactive"
    t, s = da(g["access_end_of_day"](datetime.date.today() + datetime.timedelta(days=40)))
    assert s == "ok" and "باقي 40 يوماً" in t and t.startswith("✔ حتى "), t
    t, s = da(g["access_end_of_day"](datetime.date.today() + datetime.timedelta(days=5)))
    assert s == "soon" and "باقي 5 أيام" in t and t.startswith("⏳"), t
    t, s = da(g["access_end_of_day"](datetime.date.today()))
    assert s == "soon" and "ينتهي اليوم" in t, t
    t, s = da(now - datetime.timedelta(minutes=1))
    assert s == "expired" and t.startswith("⛔ منتهي منذ "), t
    assert g["access_days_left"](now - datetime.timedelta(seconds=1)) == -1 and g["access_days_left"](None) is None
    assert [g["arabic_days"](n) for n in (1, 2, 3, 10, 11)] == ["يوم واحد", "يومان", "3 أيام", "10 أيام", "11 يوماً"]
    assert [g["arabic_devices"](n) for n in (1, 2, 5, 12)] == ["جهاز واحد", "جهازان", "5 أجهزة", "12 جهازاً"]

    # ═══ ٢) الأجهزة: الأقدم مسموح بقدر العدد (قاعدة السحابة نفسها) ═══
    devs = [{"device_id": "b", "first_seen": "2026-10-02T10:00:00+00:00"},
            {"device_id": "a", "first_seen": "2026-10-01T10:00:00+00:00"},
            {"device_id": "c", "first_seen": "2026-10-03T10:00:00+00:00"}]
    rows = g["device_rows"](devs, 2)
    assert [r["device_id"] for r in rows] == ["a", "b", "c"] and [r["allowed"] for r in rows] == [True, True, False]
    assert all(r["allowed"] for r in g["device_rows"](devs, None)), "بلا حد: كلها مسموحة"
    assert g["describe_devices"](devs, None) == "📱 الأجهزة: 3 (بلا حد)"
    assert g["describe_devices"](devs, 2) == "📱 الأجهزة: 3 من 2 ⚠️ زائدة عن الحد"
    assert g["describe_devices"](devs[:1], 2) == "📱 الأجهزة: 1 من 2"

    # ═══ ٣) بصمة الجهاز ═══
    g["_read_machine_guid"] = lambda: "1234-ABCD-SECRET-GUID"
    g["_DEVICE_IDENTITY"] = None
    dev_id, dev_name = g["device_identity"]()
    assert re.fullmatch(r"[0-9a-f]{32}", dev_id) and "SECRET" not in dev_id and dev_name
    assert g["device_identity"]() == (dev_id, dev_name), "ثابتة في كل تشغيل"
    g["_read_machine_guid"] = lambda: None
    g["_DEVICE_IDENTITY"] = None
    fallback = g["device_identity"]()[0]
    assert os.path.exists(os.path.join(tmp, "device.id")) and fallback != dev_id
    g["_DEVICE_IDENTITY"] = None
    assert g["device_identity"]()[0] == fallback, "المعرّف الاحتياطي يُحفظ مرة واحدة ويبقى"
    g["_DEVICE_IDENTITY"] = (dev_id, dev_name)

    # ═══ ٤) الدخول ═══
    class APIError(Exception):
        def __init__(self, msg, code=None):
            super().__init__(msg)
            self.code = code

    class FakeSB:
        def __init__(self, answers):
            self.answers, self.calls = answers, []

        def rpc(self, fn, params):
            self.calls.append((fn, params))
            ans = self.answers.get(fn, APIError("Could not find the function public.%s" % fn, "PGRST202"))
            return types.SimpleNamespace(execute=lambda: self._run(ans))

        @staticmethod
        def _run(ans):
            if isinstance(ans, Exception):
                raise ans
            return types.SimpleNamespace(data=ans)

    touched = []
    g["touch_client_login_async"] = lambda cid: touched.append(cid)

    def login(answers, admin=False):
        sb = FakeSB(answers)
        g["get_supabase_login_client"] = lambda: sb
        g["IS_ADMIN_BUILD"] = admin
        g["CURRENT_SYNC_TOKEN"], g["CLIENT_LOGIN_VIA"] = None, None
        info = g["cloud_client_login"]("factory", "pw")
        return info, sb

    ok_row = {"out_client_id": "C1", "out_business_name": "مصنع", "out_can_edit": True, "out_sync_token": "T1",
              "out_sync_enabled": True, "out_status": "ok", "out_access_until": "2026-12-01T20:59:59+00:00",
              "out_max_devices": 2, "out_devices_used": 1}
    info, sb = login({"client_login_v2": [ok_row]})
    assert info["client_id"] == "C1" and info["status"] == "ok" and g["CURRENT_SYNC_TOKEN"] == "T1"
    assert g["CLIENT_LOGIN_VIA"] == "v2" and len(sb.calls) == 1
    params = sb.calls[0][1]
    assert params["p_device_id"] == dev_id and params["p_device_name"] == dev_name and params["p_app_version"] == "1.68.0"
    assert params["p_password_hash"] == "H(pw)" and "pw" not in params.values(), "كلمة المرور لا تُرسل نصاً"

    for status, words in (("expired", "انتهت مدة اشتراك «مصنع» في 2026-"), ("device_limit", "على جهازان فقط"),
                          ("inactive", "موقوف من المدير")):
        row = dict(ok_row, out_client_id=None, out_sync_token=None, out_status=status,
                   out_access_until="2026-09-30T20:59:59+00:00")
        info, sb = login({"client_login_v2": [row]})
        assert info["client_id"] is None and info["status"] == status and g["CURRENT_SYNC_TOKEN"] is None
        msg = g["access_denial_message"](info)
        assert words in msg and "المدير" in msg, (status, msg)
        assert len(sb.calls) == 1, "لا رجوع للدالة القديمة عند الرفض"

    info, sb = login({"client_login_v2": []})
    assert info is None and len(sb.calls) == 1, "كلمة مرور خاطئة: لا محاولة بدالة أقدم"
    assert g["access_denial_message"](info) is None

    info, sb = login({"client_login_full": [dict(ok_row, out_status=None)]})
    assert info["client_id"] == "C1" and info["via"] == "full" and [c[0] for c in sb.calls] == ["client_login_v2", "client_login_full"]
    assert g["CLIENT_LOGIN_VIA"] == "full", "السحابة قبل 21: الدخول القديم يعمل كما كان"

    info, sb = login({"client_login_v2": APIError("ConnectError: [Errno 11001] getaddrinfo failed")})
    assert info is None and len(sb.calls) == 1, "انقطاع الإنترنت لا يحوّل للدالة القديمة (تتجاوز الفحوص)"

    info, sb = login({"client_login_v2": [ok_row]}, admin=True)
    assert sb.calls[0][1]["p_device_id"] is None, "برنامج المدير لا يشغل مكان جهاز في حساب العميل"
    msg = g["access_denial_message"]({"status": "update_required"})
    assert "فتح الحساب" in msg and "لوحة" in msg
    g["IS_ADMIN_BUILD"] = IS_ADMIN

    touched.clear()
    g["get_supabase_login_client"] = lambda: FakeSB({"client_login_v2": [ok_row]})
    assert g["cloud_verify_client_login"]("f", "p") == ("C1", "مصنع", True) and touched == [], "الدخول الأحدث يسجّل وقته في السحابة"
    g["get_supabase_login_client"] = lambda: FakeSB({"client_login_full": [ok_row]})
    assert g["cloud_verify_client_login"]("f", "p")[0] == "C1" and touched == ["C1"]

    # ═══ ٥) الفحص الدوري ═══
    can_edit_calls = []
    g["cloud_check_can_edit"] = lambda cid: (can_edit_calls.append(cid), False)[1]
    pub = FakeSB({"client_access_check": [{"out_status": "expired", "out_can_edit": True,
                                           "out_access_until": "2026-09-30T20:59:59+00:00",
                                           "out_max_devices": None, "out_devices_used": 1}]})
    g["get_supabase_public_client"] = lambda: pub
    g["CURRENT_SYNC_TOKEN"], g["CLIENT_LOGIN_VIA"] = "T1", "v2"
    st = g["cloud_client_access_check"]("C1")
    assert st["status"] == "expired" and st["can_edit"] is True and not can_edit_calls
    assert pub.calls[0][1] == {"p_client_id": "C1", "p_sync_token": "T1", "p_device_id": dev_id}

    g["CLIENT_LOGIN_VIA"] = "full"
    st = g["cloud_client_access_check"]("C1")
    assert st == {"status": None, "can_edit": False} and can_edit_calls == ["C1"], "دخول قديم: صلاحية التعديل فقط"
    g["CLIENT_LOGIN_VIA"] = "v2"
    pub.answers = {"client_access_check": [{"out_status": "unauthorized"}]}
    assert g["cloud_client_access_check"]("C1")["status"] is None, "رمز غير مقبول لا يُقفل البرنامج"
    pub.answers = {"client_access_check": APIError("ConnectError: timed out")}
    assert g["cloud_client_access_check"]("C1") is None, "انقطاع: لا جواب (والقرار لساعة الجهاز)"

    # «آخر ظهور»: السحابة الأحدث تسجّله مع الفحص — لا كتابة في جدول العملاء بالمفتاح العام
    g["get_supabase_admin_client"] = lambda: None
    writes = []
    pub.table = lambda name: (writes.append(name), None)[1]
    assert g["cloud_touch_client_activity"]("C1") is True and writes == []

    # ═══ ٦) قفل البرنامج المفتوح وفتحه ═══
    ns = {"datetime": datetime, "IS_ADMIN_BUILD": False, "ACCESS_BLOCKING": g["ACCESS_BLOCKING"],
          "parse_cloud_timestamp": g["parse_cloud_timestamp"]}
    exec(method_src(cls, "apply_access_state").replace("\n    ", "\n"), ns)
    apply_state = ns["apply_access_state"]
    events = []
    app = types.SimpleNamespace(client_id="C1", is_admin_session=False, _access_until=None,
                                show_access_lock=lambda s, st=None: events.append(("lock", s)),
                                hide_access_lock=lambda: events.append(("unlock",)),
                                update_access_ui=lambda: events.append(("ui",)), warn_access_expiry=lambda: None)
    apply_state(app, {"status": "ok", "access_until": "2027-01-01T20:59:59+00:00", "max_devices": 2})
    assert events == [("unlock",), ("ui",)] and app._access_until.year == 2027
    for status in ("expired", "inactive", "device_limit", "device_removed"):
        events.clear()
        apply_state(app, {"status": status})
        assert events[0] == ("lock", status), status
    events.clear()
    app._access_until = datetime.datetime.now(UTC) - datetime.timedelta(seconds=5)
    apply_state(app, None)
    assert events[0] == ("lock", "expired"), "بلا إنترنت: ساعة الجهاز تُقفله عند انتهاء المدة"
    events.clear()
    app._access_until = datetime.datetime.now(UTC) + datetime.timedelta(days=3)
    apply_state(app, None)
    assert events == [("ui",)], "بلا إنترنت والمدة سارية: لا شيء"
    events.clear()
    apply_state(app, {"status": None, "can_edit": True})
    assert events == [("ui",)], "سحابة قبل 21: لا قفل"
    events.clear()
    app.is_admin_session = True
    apply_state(app, {"status": "expired"})
    assert events == [], "جلسة المدير لا تُقفل"
    ns["IS_ADMIN_BUILD"] = True
    app.is_admin_session = False
    apply_state(app, {"status": "expired"})
    assert events == [], "برنامج المدير لا يُقفل"

    # ═══ ٧) الواجهات موصولة ═══
    lock = method_src(cls, "show_access_lock")
    assert "grab_set()" in lock and "withdraw()" in lock and "on_app_closing" in lock and "check_access_now" in lock
    assert "deiconify()" in method_src(cls, "hide_access_lock")
    for handler in ("_on_escape_key", "_on_ctrl_number_key", "open_shortcuts_help"):
        assert "_access_locked" in method_src(cls, handler), f"{handler}: لا تنقّل تحت غطاء الإيقاف"
    refresh = method_src(cls, "refresh_edit_permission")
    assert "cloud_client_access_check" in refresh and "apply_access_state" in refresh and "_in_background" in refresh
    # النتيجة تُستلم في خيط الواجهة بفحص دوري — الخيط الخلفي لا يلمس أدوات الواجهة
    bg = method_src(cls, "_in_background")
    assert "threading.Thread" in bg and "self.after(100, poll)" in bg and "done(box.get(\"value\"))" in bg
    assert "_in_background" in method_src(cls, "check_access_now")
    warn = method_src(cls, "warn_access_expiry")
    assert "self._intro_cv is not None" in warn and "self.after(3000" in warn and "ACCESS_POPUP_DAYS" in warn
    assert "access=info" in src and "access_denial_message(info)" in src
    assert "self.lbl_access = ctk.CTkLabel(self.gold_bar" in method_src(cls, "build_gold_price_bar"), \
        "سطر الاشتراك في الشريط السفلي الظاهر على كل الشاشات"
    assert "self.update_access_ui()" in src
    dialog = method_src(admin_cls, "open_access_dialog")
    for piece in ("cloud_set_client_access", "cloud_remove_client_devices", "ACCESS_EXTEND_CHOICES",
                  "access_end_of_day", "device_rows", "⛔ إيقاف الحساب الآن", "💾 حفظ"):
        assert piece in dialog, piece
    add_dialog = method_src(admin_cls, "open_add_client_dialog")
    assert "cloud_set_client_access" in add_dialog and "ACCESS_DEVICE_CHOICES" in add_dialog
    ns2 = {"ACCESS_UNLIMITED": "بلا حد"}
    exec(method_src(admin_cls, "parse_device_limit").replace("\n    ", "\n"), ns2)
    ns2["f"] = ns2["parse_device_limit"]
    assert ns2["f"]("بلا حد") is None and ns2["f"]("") is None and ns2["f"]("٣") == 3 and ns2["f"](" 2 ") == 2
    for bad in ("0", "1001", "abc", "-1"):
        try:
            ns2["f"](bad)
            raise AssertionError(f"قُبل عدد أجهزة غير صالح: {bad}")
        except ValueError:
            pass
    assert '"client_devices"' in module_src("cloud_delete_client"), "حذف الحساب يحذف أجهزته"
    listing = module_src("cloud_list_clients_checked")
    assert "access_until, max_devices" in listing and "client_devices" in listing and "device_rows" in listing

    # ═══ ٨) ملف السحابة ═══
    sql_path = os.path.join(os.path.dirname(os.path.abspath(TARGET)), "..", "supabase", "21_access_control.sql")
    sql = io.open(sql_path, encoding="utf-8").read()
    for piece in ("client_login_v2", "client_access_check", "client_devices", "access_until", "max_devices",
                  "revoke all on public.clients from anon, authenticated", "pg_advisory_xact_lock"):
        assert piece in sql, piece
    # الخطآن الوحيدان في السجل: انقطاعا الإنترنت المقصودان أعلاه
    assert [m for m, _ in errors] == ["تعذر التحقق من بيانات الدخول عبر السحابة", "تعذر فحص حالة الحساب"], errors
finally:
    shutil.rmtree(tmp, ignore_errors=True)

print("✔ مدة الاشتراك وعدد الأجهزة: الحساب، والتجديد، والأجهزة، والدخول، والقفل، ولوحة المدير")
