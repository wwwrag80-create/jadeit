/*
 * Jadeit.exe — مشغّل جاديت بنقرة واحدة (ويندوز 7 / 8 / 10 / 11، 32 و 64 بت).
 *
 * يشغّل بايثون المضمَّن (python\pythonw.exe) بالملف app\desktop.py دون أي نافذة أوامر،
 * ويمرّر مجلده في المتغير JADEIT_HOME حتى تُحفظ البيانات في data بجوار البرنامج.
 * مكتوب بواجهات Win32 الأساسية فقط حتى يعمل على ويندوز 7 دون أي تحديثات إضافية.
 */
#ifndef UNICODE
#define UNICODE
#endif
#ifndef _UNICODE
#define _UNICODE
#endif
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <wchar.h>

#define TITLE L"جاديت"
#define MB_FLAGS_ERR (MB_OK | MB_ICONERROR | MB_RTLREADING | MB_RIGHT | MB_SETFOREGROUND)

static void fail(const wchar_t *msg)
{
    MessageBoxW(NULL, msg, TITLE, MB_FLAGS_ERR);
}

static int file_exists(const wchar_t *path)
{
    DWORD a = GetFileAttributesW(path);
    return a != INVALID_FILE_ATTRIBUTES && !(a & FILE_ATTRIBUTE_DIRECTORY);
}

int WINAPI wWinMain(HINSTANCE hInst, HINSTANCE hPrev, PWSTR cmd, int show)
{
    (void)hInst; (void)hPrev; (void)cmd; (void)show;
    wchar_t exe[MAX_PATH * 2], home[MAX_PATH * 2], python[MAX_PATH * 2], script[MAX_PATH * 2];
    wchar_t cmdline[MAX_PATH * 6], msg[MAX_PATH * 4];

    DWORD n = GetModuleFileNameW(NULL, exe, MAX_PATH * 2);
    if (n == 0 || n >= MAX_PATH * 2) { fail(L"تعذر تحديد مسار البرنامج."); return 1; }
    wcscpy(home, exe);
    wchar_t *slash = wcsrchr(home, L'\\');
    if (slash) *slash = 0;

    _snwprintf(python, MAX_PATH * 2, L"%ls\\python\\pythonw.exe", home);
    _snwprintf(script, MAX_PATH * 2, L"%ls\\app\\desktop.py", home);
    python[MAX_PATH * 2 - 1] = 0;
    script[MAX_PATH * 2 - 1] = 0;

    if (!file_exists(python) || !file_exists(script)) {
        _snwprintf(msg, MAX_PATH * 4,
                   L"ملفات النظام غير مكتملة.\n\nيجب أن يكون Jadeit.exe بجوار المجلدين python و app كما في ملف ZIP الأصلي.\n"
                   L"فك الضغط عن الملف كاملاً ثم شغّل Jadeit.exe من داخل المجلد.\n\nالمجلد الحالي:\n%ls", home);
        msg[MAX_PATH * 4 - 1] = 0;
        fail(msg);
        return 1;
    }

    SetEnvironmentVariableW(L"JADEIT_HOME", home);
    SetEnvironmentVariableW(L"PYTHONIOENCODING", L"utf-8");
    SetEnvironmentVariableW(L"PYTHONDONTWRITEBYTECODE", NULL);
    /* لا نسمح لإعدادات بايثون أخرى على الجهاز بالتأثير على النسخة المضمّنة */
    SetEnvironmentVariableW(L"PYTHONHOME", NULL);
    SetEnvironmentVariableW(L"PYTHONPATH", NULL);

    _snwprintf(cmdline, MAX_PATH * 6, L"\"%ls\" -E -s \"%ls\"", python, script);
    cmdline[MAX_PATH * 6 - 1] = 0;

    STARTUPINFOW si;
    PROCESS_INFORMATION pi;
    ZeroMemory(&si, sizeof(si));
    ZeroMemory(&pi, sizeof(pi));
    si.cb = sizeof(si);
    if (!CreateProcessW(python, cmdline, NULL, NULL, FALSE, CREATE_NO_WINDOW, NULL, home, &si, &pi)) {
        _snwprintf(msg, MAX_PATH * 4, L"تعذر تشغيل النظام (رمز الخطأ %lu).\n\n%ls", GetLastError(), python);
        msg[MAX_PATH * 4 - 1] = 0;
        fail(msg);
        return 1;
    }

    /* إن خرج بايثون خلال ثوانٍ برمز خطأ فهذا يعني نقص مكوّن في ويندوز: نوضح السبب */
    DWORD wait = WaitForSingleObject(pi.hProcess, 4000);
    if (wait == WAIT_OBJECT_0) {
        DWORD code = 0;
        GetExitCodeProcess(pi.hProcess, &code);
        if (code != 0 && code != 1) {
            _snwprintf(msg, MAX_PATH * 4,
                       L"توقف النظام عند البدء (الرمز 0x%08lX).\n\n"
                       L"على ويندوز 7 تأكد من تثبيت Service Pack 1.\n"
                       L"التفاصيل في الملف data\\jadeit.log داخل مجلد البرنامج.", code);
            msg[MAX_PATH * 4 - 1] = 0;
            fail(msg);
        }
    }
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    return 0;
}
