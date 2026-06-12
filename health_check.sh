#!/bin/bash
# SLK Health Check - Полная диагностика бота
# Запуск: bash /opt/SLV_Bot/health_check.sh

BOT_DIR="/opt/SLV_Bot"
REPORT="/tmp/slk_health_report.txt"
PASS=0
FAIL=0
WARN=0

echo "🔍 SLK HEALTH CHECK"
echo "===================="
echo ""

# Функции для отчёта
pass() { echo "✅ $1"; ((PASS++)); }
fail() { echo "❌ $1"; ((FAIL++)); }
warn() { echo "⚠️  $1"; ((WARN++)); }

# ============================================
# 1. ПРОВЕРКА СИНТАКСИСА PYTHON-ФАЙЛОВ
# ============================================
echo "📦 1. Проверка синтаксиса Python-файлов..."
for f in $BOT_DIR/*.py; do
    name=$(basename "$f")
    result=$(python3 -m py_compile "$f" 2>&1)
    if [ $? -eq 0 ]; then
        pass "$name - синтаксис OK"
    else
        fail "$name - ошибка синтаксиса: $result"
    fi
done

# ============================================
# 2. ПРОВЕРКА ИМПОРТОВ В bot.py
# ============================================
echo ""
echo "📥 2. Проверка импортов bot.py..."
# Извлекаем все импорты из handlers в bot.py
HANDLERS_IMPORTS=$(grep "from handlers import" $BOT_DIR/bot.py 2>/dev/null | tr ',' '\n' | grep -v "from handlers" | sed 's/^ *//;s/ *$//')

# Проверяем каждый импорт
for func in $HANDLERS_IMPORTS; do
    if grep -q "def $func" $BOT_DIR/handlers.py 2>/dev/null; then
        :  # Найдена
    elif [ "$func" = "BOT_VERSION" ]; then
        if grep -q "^BOT_VERSION" $BOT_DIR/handlers.py 2>/dev/null; then
            :
        else
            fail "BOT_VERSION не найден в handlers.py"
        fi
    else
        fail "Функция '$func' не найдена в handlers.py (импортируется в bot.py)"
    fi
done
[ $? -eq 0 ] && pass "Все импорты bot.py найдены в handlers.py"

# ============================================
# 3. ПРОВЕРКА КНОПОК И ОБРАБОТЧИКОВ
# ============================================
echo ""
echo "🔘 3. Проверка кнопок и обработчиков..."

# Извлекаем все callback_data из keyboards.py
CALLBACKS=$(grep -o 'callback_data="[^"]*"' $BOT_DIR/keyboards.py 2>/dev/null | cut -d'"' -f2 | sort -u)

# Извлекаем все обработчики из bot.py и handlers.py
HANDLERS_LIST=$(grep -o 'pattern="[^"]*"' $BOT_DIR/bot.py 2>/dev/null | cut -d'"' -f2)
HANDLERS_LIST="$HANDLERS_LIST $(grep -oP "query\.data\s*==\s*['\"]([^'\"]+)['\"]" $BOT_DIR/handlers.py 2>/dev/null | cut -d'"' -f2 | cut -d"'" -f2)"

for cb in $CALLBACKS; do
    if echo "$HANDLERS_LIST" | grep -qF "$cb"; then
        :  # Есть обработчик
    else
        warn "callback_data='$cb' - возможно нет обработчика"
    fi
done
pass "Callback-кнопки проверены"

# ============================================
# 4. ПОИСК МЁРТВЫХ ФУНКЦИЙ
# ============================================
echo ""
echo "👻 4. Поиск неиспользуемых функций..."

# Все функции из handlers.py
ALL_FUNCS=$(grep -oP "(?:async\s+)?def\s+\K\w+" $BOT_DIR/handlers.py 2>/dev/null | sort -u)

# Функции, используемые в bot.py
USED_IN_BOT=$(grep -oP '\b\w+\b' $BOT_DIR/bot.py 2>/dev/null | sort -u)

# Функции, используемые в keyboards.py
USED_IN_KB=$(grep -oP '\b\w+\b' $BOT_DIR/keyboards.py 2>/dev/null | sort -u)

# Функции, используемые внутри handlers.py (перекрёстные вызовы)
USED_IN_HANDLERS=$(grep -oP '\b\w+(?=\()' $BOT_DIR/handlers.py 2>/dev/null | sort -u)

for func in $ALL_FUNCS; do
    if echo "$USED_IN_BOT $USED_IN_KB $USED_IN_HANDLERS" | grep -qw "$func"; then
        :
    else
        warn "Функция '$func' возможно не используется нигде"
    fi
done
pass "Поиск мёртвых функций завершён"

# ============================================
# 5. ПРОВЕРКА BASH-СКРИПТОВ
# ============================================
echo ""
echo "📜 5. Проверка bash-скриптов..."
for f in $BOT_DIR/*.sh; do
    name=$(basename "$f")
    result=$(bash -n "$f" 2>&1)
    if [ $? -eq 0 ]; then
        pass "$name - синтаксис OK"
    else
        fail "$name - ошибка: $result"
    fi
done

# ============================================
# 6. ПРОВЕРКА СУЩЕСТВУЮЩИХ ПУТЕЙ В СКРИПТАХ
# ============================================
echo ""
echo "📁 6. Проверка путей в скриптах..."
for f in $BOT_DIR/*.sh; do
    # Ищем пути вида /opt/... или /etc/...
    # Исключаем health_check.sh из проверки
    [ "$(basename $f)" = "health_check.sh" ] && continue
    PATHS=$(grep -oP '(/(opt|etc|root|home|var)/[^\s"'\'']+)' "$f" 2>/dev/null | sort -u)
    for p in $PATHS; do
        if [ -e "$p" ]; then
            :
        else
            # Не все пути должны существовать (например, создаются позже)
            [[ "$p" == *"x-ui.service"* ]] || warn "Путь не существует: $p (в $(basename $f))"
        fi
    done
done
pass "Проверка путей завершена"

# ============================================
# 7. ПРОВЕРКА БАЗЫ ДАННЫХ
# ============================================
echo ""
echo "🗄️  7. Проверка базы данных..."
if [ -f $BOT_DIR/clients.db ]; then
    result=$(sqlite3 $BOT_DIR/clients.db "SELECT COUNT(*) FROM clients;" 2>&1)
    if [ $? -eq 0 ]; then
        pass "База данных OK (пользователей: $result)"
    else
        fail "Ошибка чтения базы: $result"
    fi
else
    warn "Файл clients.db не найден"
fi

# ============================================
# 8. ПРОВЕРКА .env
# ============================================
echo ""
echo "⚙️  8. Проверка конфигурации..."
REQUIRED_VARS="BOT_TOKEN ADMIN_IDS XUI_API_TOKEN XUI_PANEL_URL SUBSCRIPTION_URL"
for var in $REQUIRED_VARS; do
    if grep -q "^$var=" $BOT_DIR/.env 2>/dev/null; then
        val=$(grep "^$var=" $BOT_DIR/.env | cut -d= -f2)
        if [ -n "$val" ] && [ "$val" != '""' ]; then
            pass "$var - задан"
        else
            fail "$var - пустой"
        fi
    else
        fail "$var - отсутствует в .env"
    fi
done

# ============================================
# 9. ПРОВЕРКА СЕРВИСОВ
# ============================================
echo ""
echo "🔧 9. Проверка systemd сервисов..."
for srv in "SLV-bot" "slv-monitor"; do
    if systemctl status $srv > /dev/null 2>&1; then
        status=$(systemctl is-active $srv)
        if [ "$status" = "active" ]; then
            pass "$srv.service - активен"
        else
            fail "$srv.service - статус: $status"
        fi
    else
        warn "$srv.service - не найден"
    fi
done

# ============================================
# 10. ПРОВЕРКА РАЗМЕРА ФАЙЛОВ
# ============================================
echo ""
echo "📏 10. Размеры файлов..."
echo "handlers.py: $(wc -l < $BOT_DIR/handlers.py) строк"
echo "keyboards.py: $(wc -l < $BOT_DIR/keyboards.py) строк"
echo "bot.py: $(wc -l < $BOT_DIR/bot.py) строк"
echo ""


# ============================================
# 11. ПРОВЕРКА КНОПОК ОСНОВНОГО БОТА
# ============================================
echo ""
echo "🔘 11. Проверка кнопок основного бота..."
python3 /opt/SLV_Bot/check_buttons.py 2>/dev/null || echo "ℹ️  Запустите: python3 /opt/SLV_Bot/check_buttons.py"

# ============================================
# ИТОГО
# ============================================
TOTAL=$((PASS + FAIL + WARN))
echo "===================="
echo "📊 ИТОГО:"
echo "✅  Пройдено: $PASS"
echo "⚠️  Предупреждений: $WARN"
echo "❌  Ошибок: $FAIL"
echo "📋 Всего проверок: $TOTAL"

if [ $FAIL -eq 0 ]; then
    echo ""
    echo "🎉 Бот полностью исправен!"
else
    echo ""
    echo "🔧 Требуется исправление $FAIL ошибок"
fi
