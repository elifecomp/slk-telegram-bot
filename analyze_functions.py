#!/usr/bin/env python3
"""Глубокий анализатор использования функций"""
import os, re

BOT_DIR = "/opt/SLV_Bot"

# 1. Все функции из handlers.py
with open(f"{BOT_DIR}/handlers.py") as f:
    handlers_code = f.read()

all_funcs = {}
for m in re.finditer(r'(?:async\s+)?def\s+(\w+)\(', handlers_code):
    all_funcs[m.group(1)] = m.start()

print("=" * 60)
print("📊 ГЛУБОКИЙ АНАЛИЗ ИСПОЛЬЗОВАНИЯ ФУНКЦИЙ")
print("=" * 60)

# 2. Собираем все способы вызова
used_funcs = set()

# Прямые вызовы во всех .py файлах
for fname in os.listdir(BOT_DIR):
    if fname.endswith('.py') and not fname.startswith('__'):
        with open(f"{BOT_DIR}/{fname}") as f:
            code = f.read()
        for m in re.finditer(r'(?<!def\s)(?<!\.)\b(\w+)\s*\(', code):
            used_funcs.add(m.group(1))

# Callback_data в keyboards.py
with open(f"{BOT_DIR}/keyboards.py") as f:
    kb = f.read()
for cb in re.findall(r'callback_data\s*=\s*"([^"]+)"', kb):
    # Ищем обработчики в handlers.py
    for func in all_funcs:
        if func.startswith(cb) or cb.startswith(func):
            used_funcs.add(func)

# Pattern-ы в bot.py
with open(f"{BOT_DIR}/bot.py") as f:
    bot = f.read()
for pattern in re.findall(r'pattern\s*=\s*"([^"]+)"', bot):
    # Проверяем, есть ли функция с таким именем
    for func in all_funcs:
        if func == pattern.replace('^', '').replace('$', '') or pattern in func:
            used_funcs.add(func)

# Импорты из handlers в bot.py
for imp in re.findall(r'from handlers import\s+(.+?)(?:\n|$)', bot):
    for func in imp.split(','):
        func = func.strip()
        if func in all_funcs:
            used_funcs.add(func)

# Текстовые команды (ReplyKeyboardMarkup)
for text in re.findall(r'"([^"]+)"', kb):
    # Ищем в handlers.py упоминания этого текста
    for func in all_funcs:
        # Проверяем, есть ли в теле функции этот текст
        func_start = all_funcs[func]
        func_end = list(all_funcs.values())[list(all_funcs.keys()).index(func)+1] if list(all_funcs.keys()).index(func)+1 < len(all_funcs) else len(handlers_code)
        func_body = handlers_code[func_start:func_end]
        if f'"{text}"' in func_body or f"'{text}'" in func_body:
            used_funcs.add(func)

# 3. Результат
unused = set(all_funcs.keys()) - used_funcs

print(f"\n📌 Всего функций: {len(all_funcs)}")
print(f"📌 Используется: {len(used_funcs)}")
print(f"\n❌ НЕ ИСПОЛЬЗУЕТСЯ: {len(unused)}")
print("-" * 40)

# Группируем по категориям
really_dead = []
maybe_alive = []

for func in sorted(unused):
    # Найдём строку
    for m in re.finditer(rf'^(?:async\s+)?def\s+{func}\(', handlers_code, re.MULTILINE):
        line = handlers_code[:m.start()].count('\n') + 1
        break
    
    # Проверим, может вызываться динамически
    if func in handlers_code.replace(f'def {func}(', ''):  # упоминается где-то ещё
        maybe_alive.append((func, line))
    else:
        really_dead.append((func, line))

if really_dead:
    print("\n🔴 ТОЧНО МЁРТВЫЕ (нет упоминаний нигде):")
    for func, line in really_dead:
        print(f"  • {func} (строка {line})")

if maybe_alive:
    print("\n🟡 ВОЗМОЖНО ЖИВЫЕ (упоминаются в коде):")
    for func, line in maybe_alive:
        print(f"  • {func} (строка {line})")

print("\n" + "=" * 60)
print("✅ Анализ завершён")
