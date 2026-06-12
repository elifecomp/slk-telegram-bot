import re

with open('/opt/SLV_Bot/handlers.py') as f:
    handlers = f.read()
with open('/opt/SLV_Bot/bot.py') as f:
    bot = f.read()

callbacks_in_code = set(re.findall(r'data\s*==\s*["\']([^"\']+)["\']', handlers))
callbacks_in_bot = set(re.findall(r'pattern\s*=\s*"([^"]+)"', bot))

system_cb = {'backup_delete_cancel', 'backup_delete_confirm'}
no_handler = set()
for cb in callbacks_in_bot:
    if cb not in callbacks_in_code and not any(cb.startswith(s) for s in system_cb):
        no_handler.add(cb)

if no_handler:
    print(f"❌ Кнопок без обработчиков: {len(no_handler)}")
    for c in sorted(no_handler):
        print(f"   • {c}")
else:
    print("✅ Все кнопки основного бота имеют обработчики")
