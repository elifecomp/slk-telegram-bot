#!/bin/bash
echo "══════════════════════════════════════════"
echo "  🔍 ГЛУБОКИЙ АУДИТ КОДА SLK БОТА"
echo "  $(date '+%d.%m.%Y %H:%M:%S')"
echo "══════════════════════════════════════════"

BOT_DIR="/opt/SLV_Bot"
PASS=0
FAIL=0
WARN=0

pass() { echo "✅ $1"; ((PASS++)); }
fail() { echo "❌ $1"; ((FAIL++)); }
warn() { echo "⚠️  $1"; ((WARN++)); }

# 1. СИНТАКСИС PYTHON
echo ""
echo "📌 1. СИНТАКСИС PYTHON"
for f in $BOT_DIR/*.py; do
    python3 -m py_compile "$f" 2>/dev/null && pass "$(basename $f)" || fail "$(basename $f)"
done

# 2. ЛИШНИЕ ПРОБЕЛЫ
echo ""
echo "📌 2. ПРОБЕЛЫ В КОНЦЕ СТРОК"
TRAILING=$(grep -rn '[[:space:]]$' $BOT_DIR/*.py 2>/dev/null | wc -l)
[ "$TRAILING" -eq 0 ] && pass "Нет пробелов в конце строк" || warn "Пробелов в конце строк: $TRAILING"

# 3. ТАБЫ ВМЕСТО ПРОБЕЛОВ
echo ""
echo "📌 3. ТАБЫ"
TABS=$(grep -rnP '\t' $BOT_DIR/*.py 2>/dev/null | wc -l)
[ "$TABS" -eq 0 ] && pass "Нет табов" || warn "Табов: $TABS"

# 4. ДЛИННЫЕ СТРОКИ (>120 символов)
echo ""
echo "📌 4. ДЛИННЫЕ СТРОКИ (>120)"
LONG=$(awk 'length>120' $BOT_DIR/*.py 2>/dev/null | wc -l)
[ "$LONG" -eq 0 ] && pass "Нет длинных строк" || warn "Длинных строк: $LONG"

# 5. КНОПКИ БЕЗ ОБРАБОТЧИКОВ
echo ""
echo "📌 5. КНОПКИ БЕЗ ОБРАБОТЧИКОВ"
python3 << 'PYEOF'
import re, os
bot_dir = '/opt/SLV_Bot'

# Все callback_data из keyboards.py
with open(f'{bot_dir}/keyboards.py') as f:
    kb = f.read()
callbacks_in_kb = set(re.findall(r'callback_data\s*=\s*"([^"]+)"', kb))
callbacks_in_kb.update(re.findall(r"callback_data\s*=\s*'([^']+)'", kb))

# Все pattern из bot.py
with open(f'{bot_dir}/bot.py') as f:
    bot = f.read()
patterns_in_bot = set(re.findall(r'pattern\s*=\s*"([^"]+)"', bot))

# Все обработки data == в handlers.py
with open(f'{bot_dir}/handlers.py') as f:
    handlers = f.read()
data_checks = set(re.findall(r'data\s*==\s*"([^"]+)"', handlers))
data_checks.update(re.findall(r"data\s*==\s*'([^']+)'", handlers))
data_checks.update(re.findall(r'data\.startswith\("([^"]+)"', handlers))

no_handler = set()
for cb in callbacks_in_kb:
    found = False
    for p in patterns_in_bot:
        if re.match(p, cb):
            found = True
            break
    if cb in data_checks:
        found = True
    if not found:
        no_handler.add(cb)

if no_handler:
    print(f"   ⚠️ Кнопок без обработчиков: {len(no_handler)}")
    for c in sorted(no_handler):
        print(f"      • {c}")
else:
    print("   ✅ Все кнопки имеют обработчики")
PYEOF

# 6. МЁРТВЫЕ ФУНКЦИИ
echo ""
echo "📌 6. МЁРТВЫЕ ФУНКЦИИ"
python3 << 'PYEOF'
import re, os
bot_dir = '/opt/SLV_Bot'

with open(f'{bot_dir}/handlers.py') as f:
    handlers = f.read()

# Все определения функций
all_funcs = set(re.findall(r'(?:async\s+)?def\s+(\w+)\(', handlers))

# Все вызовы функций во всех .py файлах
all_calls = set()
for fname in os.listdir(bot_dir):
    if fname.endswith('.py') and not fname.startswith('__'):
        with open(f'{bot_dir}/{fname}') as f:
            all_calls.update(re.findall(r'\b(\w+)\s*\(', f.read()))

unused = all_funcs - all_calls
# Исключаем стандартные
std = {'__init__', '__name__', '__main__', 'main', 'logger', 'super', 'isinstance'}
unused = unused - std

if unused:
    print(f"   ⚠️ Неиспользуемых функций: {len(unused)}")
    for u in sorted(unused):
        # Найдём строку
        for i, line in enumerate(handlers.split('\n'), 1):
            if f'def {u}(' in line:
                print(f"      • {u} (строка {i})")
                break
else:
    print("   ✅ Все функции используются")
PYEOF

# 7. ИМПОРТЫ БЕЗ ИСПОЛЬЗОВАНИЯ
echo ""
echo "📌 7. НЕИСПОЛЬЗУЕМЫЕ ИМПОРТЫ"
python3 << 'PYEOF'
import re, os
bot_dir = '/opt/SLV_Bot'

with open(f'{bot_dir}/handlers.py') as f:
    content = f.read()
    lines = content.split('\n')

# Первые 30 строк — импорты
imports = []
for i, line in enumerate(lines[:35]):
    if line.startswith('import ') or line.startswith('from '):
        imports.append((i+1, line))

for num, line in imports:
    # Извлекаем модуль
    if line.startswith('import '):
        mod = line.replace('import ', '').split(' as ')[0].strip().split(',')[0].strip()
        count = content.count(mod)
        if count <= 1:
            print(f"   ⚠️ {mod} (строка {num}) — возможно не используется")
    elif line.startswith('from '):
        what = line.split(' import ')[1].strip()
        for item in what.split(','):
            item = item.strip().split(' as ')[0].strip()
            if item == '*':
                continue
            count = content.count(item)
            if count <= 1:
                print(f"   ⚠️ {item} (строка {num}) — возможно не используется")
PYEOF

# 8. РАЗМЕРЫ ФАЙЛОВ
echo ""
echo "📌 8. РАЗМЕРЫ"
echo "   Файл                Строк"
for f in $BOT_DIR/*.py; do
    printf "   %-20s %s\n" "$(basename $f)" "$(wc -l < $f)"
done

# 9. КОММЕНТАРИИ
echo ""
echo "📌 9. КОММЕНТАРИИ"
TOTAL_LINES=$(cat $BOT_DIR/*.py | wc -l)
COMMENT_LINES=$(grep -c "^[[:space:]]*#" $BOT_DIR/*.py 2>/dev/null | awk -F: '{sum+=$2} END {print sum}')
echo "   Всего строк: $TOTAL_LINES"
echo "   Комментариев: ${COMMENT_LINES:-0}"

# ИТОГО
echo ""
echo "══════════════════════════════════════════"
echo "📊 ИТОГО:"
echo "✅  Пройдено: $PASS"
echo "⚠️  Предупреждений: $WARN"
echo "❌  Ошибок: $FAIL"
TOTAL=$((PASS + WARN + FAIL))
echo "📋 Всего проверок: $TOTAL"
[ "$FAIL" -eq 0 ] && echo "🎉 Код в порядке!" || echo "🔧 Требуется исправление $FAIL ошибок"
