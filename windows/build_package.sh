#!/usr/bin/env bash
# يبني حزمة ويندوز المحمولة  dist/Jadeit-Windows.zip  (تشغيل بنقرة واحدة على ويندوز 7 / 8 / 10 / 11).
#
# المتطلبات على جهاز البناء (لينكس): mingw-w64 (i686-w64-mingw32-gcc)، curl، python3 + pip، zip.
# المكوّنات تُنزَّل من مصادر رسمية وتُخزَّن في windows/.cache :
#   - بايثون 3.7.9 (32 بت) الرسمي من python.org عبر NuGet (حزمة pythonx86) — آخر إصدار يعمل على ويندوز 7
#     دون تحديث KB2533623.
#   - مكتبة Universal C Runtime للنشر المحلي (ucrtbase.dll و api-ms-win-*.dll) من حزمة تشغيل .NET Core 3.1
#     الرسمية لـ x86، حتى يعمل بايثون على ويندوز 7 دون تحديث KB2999226.
#   - حزم PyInstaller 5.13.2 (آخر إصدار يدعم بايثون 3.7) لأداة التحويل إلى ملف تنفيذي واحد دون إنترنت.
#   - (اختياري) PY37 : مسار بايثون 3.7 على جهاز البناء لتجهيز ملفات pyc مسبقاً (تشغيل أسرع على الأجهزة القديمة).
set -euo pipefail

ROOT="$(cd "$(dirname "$0")/.." && pwd)"
CACHE="${CACHE:-$ROOT/windows/.cache}"
OUT="${OUT:-$ROOT/dist}"
STAGE="$OUT/Jadeit"
NUGET="https://api.nuget.org/v3-flatcontainer"
mkdir -p "$CACHE" "$OUT"

fetch() { [ -s "$CACHE/$2" ] || curl -sSfL --retry 3 -o "$CACHE/$2" "$1"; }
fetch "$NUGET/pythonx86/3.7.9/pythonx86.3.7.9.nupkg" pythonx86.3.7.9.nupkg
fetch "$NUGET/microsoft.netcore.app.runtime.win-x86/3.1.32/microsoft.netcore.app.runtime.win-x86.3.1.32.nupkg" ucrt-x86.nupkg

if [ ! -d "$CACHE/wheels" ]; then
  W=(--platform win32 --python-version 3.7 --implementation cp --abi cp37m --only-binary=:all: -d "$CACHE/wheels")
  pip download -q "${W[@]}" "pyinstaller==5.13.2"
  pip download -q --no-deps "${W[@]}" "importlib-metadata==6.7.0" "zipp==3.15.0" "typing-extensions==4.7.1" \
    "pefile==2023.2.7" "pywin32-ctypes==0.2.2"
fi

echo "==> Jadeit.exe"
i686-w64-mingw32-windres -I "$ROOT/windows" "$ROOT/windows/launcher.rc" -O coff -o "$CACHE/launcher.res"
i686-w64-mingw32-gcc -O2 -s -municode -mwindows -finput-charset=UTF-8 -Wall \
  -o "$CACHE/Jadeit.exe" "$ROOT/windows/launcher.c" "$CACHE/launcher.res" -static-libgcc \
  -Wl,--major-subsystem-version,6,--minor-subsystem-version,1,--major-os-version,6,--minor-os-version,1

echo "==> staging"
rm -rf "$STAGE" "$OUT/Jadeit-Windows.zip"
mkdir -p "$STAGE/app" "$STAGE/python" "$STAGE/prereqs"
TMP="$(mktemp -d)"
unzip -q "$CACHE/pythonx86.3.7.9.nupkg" 'tools/*' -d "$TMP"
cp -a "$TMP/tools/." "$STAGE/python/"
rm -rf "$TMP"
( cd "$STAGE/python" && rm -rf include libs Tools Lib/test Lib/idlelib Lib/tkinter Lib/turtledemo \
    Lib/unittest/test Lib/distutils/tests Lib/ctypes/test Lib/sqlite3/test Lib/lib2to3/tests Lib/tkinter \
  && find . -name "__pycache__" -type d -prune -exec rm -rf {} + )
# Universal CRT للنشر المحلي (ويندوز 7 دون KB2999226)
unzip -q -j -o "$CACHE/ucrt-x86.nupkg" 'runtimes/win-x86/native/ucrtbase.dll' 'runtimes/win-x86/native/api-ms-win-*' \
  'runtimes/win-x86/native/API-MS-Win-*' -d "$STAGE/python/"

cp "$ROOT/run.py" "$ROOT/desktop.py" "$STAGE/app/"
cp -a "$ROOT/server" "$ROOT/web" "$STAGE/app/"
cp "$ROOT/windows/jadeit.ico" "$STAGE/app/jadeit.ico"
find "$STAGE/app" -name "__pycache__" -type d -prune -exec rm -rf {} +

if [ -n "${PY37:-}" ]; then
  echo "==> precompiling (Python 3.7 bytecode)"
  "$PY37" -m compileall -q -j 0 --invalidation-mode unchecked-hash -d "Lib" "$STAGE/python/Lib" >/dev/null || true
fi

cp "$CACHE/Jadeit.exe" "$STAGE/Jadeit.exe"
cp -a "$CACHE/wheels" "$STAGE/prereqs/wheels"
# ملفات ويندوز بنهايات أسطر CRLF، والملف العربي بترميز UTF-8 مع BOM حتى يظهر صحيحاً في Notepad على ويندوز 7
sed 's/$/\r/' "$ROOT/windows/Build-Single-EXE.bat" > "$STAGE/Build-Single-EXE.bat"
sed 's/$/\r/' "$ROOT/windows/Create-Desktop-Shortcut.vbs" > "$STAGE/Create-Desktop-Shortcut.vbs"
{ printf '\xEF\xBB\xBF'; sed 's/$/\r/' "$ROOT/windows/README-AR.txt"; } > "$STAGE/README-AR.txt"

echo "==> zip"
( cd "$OUT" && zip -q -r -9 -X Jadeit-Windows.zip Jadeit )
ls -la "$OUT/Jadeit-Windows.zip"
