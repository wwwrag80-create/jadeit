#!/usr/bin/env bash
# =============================================================================
#  بناء واجهة الويب للنشر — يُستدعى تلقائياً من Vercel/Netlify
#
#  المفاتيح تُقرأ من متغيرات البيئة في لوحة الاستضافة، ولا تُكتب في الكود.
#  لو لم تُضبط، يتوقف البناء برسالة واضحة بدل نشر نسخة لا تعمل.
# =============================================================================
set -euo pipefail

FLUTTER_VERSION="${FLUTTER_VERSION:-3.27.1}"

if [ -z "${SUPABASE_URL:-}" ] || [ -z "${SUPABASE_ANON_KEY:-}" ]; then
  echo "✘ متغيرا البيئة SUPABASE_URL و SUPABASE_ANON_KEY غير مضبوطين."
  echo "  اضبطهما في: Vercel → Settings → Environment Variables"
  exit 1
fi

# تثبيت Flutter لو لم يكن موجوداً في بيئة البناء
if ! command -v flutter >/dev/null 2>&1; then
  echo "→ تنزيل Flutter $FLUTTER_VERSION …"
  git clone --depth 1 --branch "$FLUTTER_VERSION" https://github.com/flutter/flutter.git "$HOME/flutter"
  export PATH="$HOME/flutter/bin:$PATH"
fi

flutter --version
flutter config --enable-web
flutter pub get

echo "→ بناء نسخة الإنتاج …"
flutter build web --release \
  --dart-define=SUPABASE_URL="$SUPABASE_URL" \
  --dart-define=SUPABASE_ANON_KEY="$SUPABASE_ANON_KEY"

echo "✔ تم البناء في build/web"
