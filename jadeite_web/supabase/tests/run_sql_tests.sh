#!/usr/bin/env bash
# =============================================================================
#  يشغّل اختبارات قاعدة البيانات على PostgreSQL محلي أو في CI:
#    ١) محاكاة بيئة Supabase   ٢) INSTALL_ALL.sql مرتين (إعادة التشغيل آمنة)
#    ٣) اختبارات العزل والصلاحيات والمنطق المحاسبي
#
#  المتغيرات: PGHOST PGPORT PGUSER PGPASSWORD (اتصال psql المعتاد)
#             TEST_DB (افتراضياً jadeit_test — تُحذف وتُعاد في كل تشغيل)
#
#  ⚠️ لا تشغّله على مشروع Supabase حقيقي — يحذف قاعدة الاختبار ويعيد إنشاءها.
# =============================================================================
set -euo pipefail

cd "$(dirname "$0")/../.."
DB="${TEST_DB:-jadeit_test}"

psql -v ON_ERROR_STOP=1 -q -d postgres -c "drop database if exists \"$DB\"" -c "create database \"$DB\""

echo "→ محاكاة Supabase"
psql -v ON_ERROR_STOP=1 -q -d "$DB" -f supabase/tests/00_supabase_stub.sql 2>&1 | grep -v -e wal_level -e HINT || true

echo "→ التثبيت (المرة الأولى)"
psql -v ON_ERROR_STOP=1 -q -d "$DB" -f supabase/INSTALL_ALL.sql > /dev/null

echo "→ التثبيت (المرة الثانية — يجب أن ينجح دون أخطاء)"
psql -v ON_ERROR_STOP=1 -q -d "$DB" -f supabase/INSTALL_ALL.sql > /dev/null

echo "→ الاختبارات"
psql -v ON_ERROR_STOP=1 -q -d "$DB" -f supabase/tests/10_security_and_logic_tests.sql
