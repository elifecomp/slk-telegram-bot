#!/bin/bash
echo "🔍 ГЛУБОКИЙ АНАЛИЗ КОДА SLK БОТА"
echo "================================="
echo ""

cd /opt/SLV_Bot

# 1. Все функции в handlers.py
echo "📌 1. ВСЕ ФУНКЦИИ В handlers.py"
ALL_FUNCS=$(grep -oP "(?:async\s+)?def\s+\K\w+" handlers.py | sort -u)
echo "   Всего функций: $(echo "$ALL_FUNCS" | wc -l)"

# 2. Функции, которые вызываются
echo ""
echo "📌 2. АНАЛИЗ ИСПОЛЬЗОВАНИЯ ФУНКЦИЙ"
# Собираем все вызовы функций из всех .py файлов (кроме handlers.py)
USED=$(grep -oP '\b\w+(?=\s*\()' *.py | grep -v "def\|if\|for\|while\|with\|return\|import\|from\|print\|elif\|else\|except\|class\|None\|True\|False\|str\|int\|list\|dict\|set\|len\|range\|open\|super\|all\|any\|isinstance\|hasattr\|getattr\|setattr\|enumerate\|zip\|filter\|map\|sorted\|reversed\|format\|join\|split\|replace\|strip\|append\|update\|get\|pop\|items\|keys\|values\|copy\|clear" | sort -u)

echo "   Уникальных вызовов в .py файлах: $(echo "$USED" | wc -l)"

# 3. Ищем функции handlers.py, которые НЕ вызываются нигде
echo ""
echo "📌 3. НЕИСПОЛЬЗУЕМЫЕ ФУНКЦИИ (возможно мёртвый код):"
UNUSED=""
for func in $ALL_FUNCS; do
    # Ищем в bot.py
    if grep -q "$func" bot.py 2>/dev/null; then continue; fi
    # Ищем в handlers.py (кроме определения)
    if [ $(grep -c "$func" handlers.py) -gt 1 ]; then continue; fi
    # Ищем в других .py файлах
    if grep -q "$func" *.py 2>/dev/null | grep -v handlers.py | grep -q .; then continue; fi
    # Ищем в keyboards.py
    if grep -q "$func" keyboards.py 2>/dev/null; then continue; fi
    UNUSED="$UNUSED $func"
done

UNUSED_COUNT=$(echo "$UNUSED" | wc -w)
if [ "$UNUSED_COUNT" -gt 0 ]; then
    echo "   ⚠️ Найдено $UNUSED_COUNT неиспользуемых функций:"
    for f in $UNUSED; do
        LINE=$(grep -n "def $f" handlers.py | head -1 | cut -d: -f1)
        echo "      • $f (строка $LINE)"
    done
else
    echo "   ✅ Все функции используются"
fi

# 4. Ищем переменные/состояния BotState, которые не используются
echo ""
echo "📌 4. СОСТОЯНИЯ BotState без обработчиков:"
grep -oP 'BotState\.\K\w+' handlers.py | sort -u > /tmp/bot_states.txt
grep -oP 'current_state\s*==\s*BotState\.\K\w+' handlers.py | sort -u > /tmp/used_states.txt
UNUSED_STATES=$(comm -23 /tmp/bot_states.txt /tmp/used_states.txt)
if [ -n "$UNUSED_STATES" ]; then
    echo "   ⚠️ Состояния без проверки:"
    for s in $UNUSED_STATES; do
        echo "      • BotState.$s"
    done
else
    echo "   ✅ Все состояния используются"
fi

# 5. Ищем импорты, которые не используются
echo ""
echo "📌 5. НЕИСПОЛЬЗУЕМЫЕ ИМПОРТЫ В handlers.py:"
# Берём первую строку импорта
head -30 handlers.py | grep "import " | while read line; do
    mod=$(echo "$line" | grep -oP 'import\s+\K\w+')
    if [ -n "$mod" ]; then
        count=$(grep -c "$mod" handlers.py)
        if [ "$count" -le 1 ]; then
            echo "   ⚠️ $mod (используется только в импорте)"
        fi
    fi
done

echo ""
echo "================================="
echo "✅ ГЛУБОКИЙ АНАЛИЗ ЗАВЕРШЁН"
