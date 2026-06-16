#!/bin/bash
echo "🔍 Полный анализ кода SLK бота"
echo "================================"

BOT_DIR="/opt/SLV_Bot"

echo ""
echo "📌 1. СИНТАКСИС PYTHON"
for f in $BOT_DIR/*.py; do
    python3 -m py_compile "$f" 2>/dev/null && echo "✅ $(basename $f)" || echo "❌ $(basename $f) — ОШИБКА"
done

echo ""
echo "📌 2. ПРОБЕЛЫ В КОНЦЕ СТРОК"
for f in $BOT_DIR/*.py $BOT_DIR/*.sh; do
    c=$(grep -c '[[:space:]]$' "$f" 2>/dev/null)
    [ "$c" -gt 0 ] && echo "⚠️ $(basename $f): $c строк"
done

echo ""
echo "📌 3. ВСЕ ФУНКЦИИ"
echo "handlers.py: $(grep -c '^async def \|^def ' $BOT_DIR/handlers.py) функций"
grep -n "^async def \|^def " $BOT_DIR/handlers.py | head -30
echo "... (показаны первые 30)"

echo ""
echo "📌 4. РАЗМЕРЫ"
wc -l $BOT_DIR/*.py | sort -n

echo ""
echo "✅ Анализ завершён"
