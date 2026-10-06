# -*- coding: utf-8 -*-
# محاكاة أقفال ملفات ويندوز على لينكس (يفعّلها run_all_checks.py على لينكس وCI وحدهما):
# حذف ملف أو استبداله أو إعادة تسميته وهو مفتوح يُرفض — كما في ويندوز، حيث لا تسمح SQLite ولا
# open() بـ FILE_SHARE_DELETE. فالفحص الذي يترك قاعدة مفتوحة ثم يحذفها يفشل هنا أيضاً، لا عند
# بناء exe على جهاز المستخدم وحده (كما حدث مع test_admin_isolation في 1.61.0).
# لا يُضمَّن في exe: ليس على مسار البرنامج، ولا يُفعَّل على ويندوز.
import os
_REAL = {n: getattr(os, n) for n in ("remove", "unlink", "replace", "rename")}
_LOG = os.environ.get("WINLOCK_LOG")


def _open_paths():
    out = set()
    try:
        for fd in os.listdir("/proc/self/fd"):
            try:
                out.add(os.path.realpath(os.readlink(f"/proc/self/fd/{fd}")))
            except OSError:
                pass
    except OSError:
        pass
    return out


def _guard(name):
    real = _REAL[name]

    def wrapper(*args, **kwargs):
        targets = [a for a in args[:2] if isinstance(a, (str, os.PathLike))]
        if targets:
            held = _open_paths()
            for p in targets:
                if os.path.realpath(p) in held:
                    if _LOG:
                        with open(_LOG, "a") as f:
                            f.write(f"{name}: {p}\n")
                    raise PermissionError(32, "[WinError 32] The process cannot access the file because "
                                              "it is being used by another process (محاكاة ويندوز)", str(p))
        return real(*args, **kwargs)
    return wrapper


for _n in _REAL:
    setattr(os, _n, _guard(_n))
