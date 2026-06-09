#!/usr/bin/env python3
import os, sys, json, sqlite3
sys.path.insert(0, '/opt/SLV_Bot')
from datetime import datetime
from flask import Flask, request, jsonify, render_template_string, redirect, session
from functools import wraps

app = Flask(__name__)
app.config['SECRET_KEY'] = 'slk-client-2026'
BOT_DIR = '/opt/SLV_Bot'
DB_PATH = f'{BOT_DIR}/clients.db'

def get_user_by_phone(phone):
    try:
        conn = sqlite3.connect(DB_PATH)
        c = conn.cursor()
        c.execute('SELECT * FROM clients WHERE phone=? AND is_active=1', (phone,))
        row = c.fetchone()
        conn.close()
        if row:
            return {'id': row[0], 'telegram_id': row[1], 'login': row[2], 'phone': row[3], 'name': row[4]}
    except: pass
    return None

def get_all_subscriptions(login, telegram_id):
    try:
        from panel_manager import get_panels_list, set_active_panel, get_active_panel
        from xui_api import get_inbounds_list
        panels = get_panels_list()
        original = get_active_panel()['id']
        results = []
        found_emails = set()
        search_logins = [login]
        try:
            conn = sqlite3.connect(DB_PATH)
            c = conn.cursor()
            c.execute('SELECT login, login2 FROM clients WHERE telegram_id=?', (telegram_id,))
            row = c.fetchone()
            if row and row[1]: search_logins.append(row[1])
            conn.close()
        except: pass
        for panel in panels:
            set_active_panel(panel['id'])
            inbounds = get_inbounds_list()
            for inbound in inbounds:
                settings = inbound.get('settings', {})
                if isinstance(settings, str):
                    try: settings = json.loads(settings) if settings.strip() else {}
                    except: settings = {}
                for c in inbound.get('clientStats', []):
                    email = c.get('email', '')
                    found = email in search_logins
                    if isinstance(settings, dict):
                        for sc in settings.get('clients', []):
                            if sc.get('email') == email and str(sc.get('tgId', '')) == str(telegram_id):
                                found = True
                    sub_id = ''
                    if isinstance(settings, dict):
                        for sc in settings.get('clients', []):
                            if sc.get('email') == email:
                                sub_id = sc.get('subId', '')
                                break
                    if found and email not in found_emails:
                        found_emails.add(email)
                        results.append({
                            'panel': panel['name'], 'emoji': panel['emoji'],
                            'inbound': inbound.get('remark', '?'),
                            'protocol': inbound.get('protocol', '?').upper(),
                            'port': inbound.get('port', '?'),
                            'up': c.get('up', 0), 'down': c.get('down', 0),
                            'total': c.get('total', 0), 'enable': c.get('enable', True),
                            'flow': c.get('flow', ''), 'email': email,
                            'sub_id': sub_id,
                            'sub_link': f"https://elifecomp.ru:8543/sub/finlyandiya2026elifecomp/{sub_id}" if sub_id else '',
                            'json_link': f"https://elifecomp.ru:8543/json/IOS-Android_SLK/{sub_id}" if sub_id else ''
                        })
        set_active_panel(original)
        return results
    except: return []

def get_last_ip_info(login):
    try:
        from xui_api import get_client_ips
        import requests as req
        ips = get_client_ips(login)
        if ips:
            ip = str(ips[0]).split(' ')[0].strip()
            if ip and '.' in ip:
                r = req.get(f"http://ip-api.com/json/{ip}?fields=country,isp", timeout=3)
                if r.status_code == 200:
                    d = r.json()
                    flags = {'Russia': '🇷🇺', 'Finland': '🇫🇮'}
                    return ip, flags.get(d.get('country', ''), '🌍') + ' ' + d.get('country', '?'), d.get('isp', '?')
                return ip, '🌍', '?'
        return None, None, None
    except: return None, None, None

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('user'): return redirect('/login')
        return f(*args, **kwargs)
    return decorated

def fb(b):
    if not b: return '0 B'
    for u in ['B', 'KB', 'MB', 'GB', 'TB']:
        if b < 1024: return f"{b:.2f} {u}"
        b /= 1024
    return f"{b:.2f} PB"

LOGIN_HTML = """<!DOCTYPE html><html lang=ru><head><meta charset=UTF-8><title>SLK Вход</title>
<style>*{margin:0;padding:0;box-sizing:border-box}body{background:#0a0a0a;display:flex;justify-content:center;align-items:center;min-height:100vh;font-family:sans-serif}
.box{background:#111;padding:40px;border-radius:16px;border:1px solid #222;width:350px;text-align:center}
h1{color:#fff;margin-bottom:10px;font-size:22px}p{color:#888;margin-bottom:20px;font-size:13px}
input{width:100%;padding:14px;background:#1a1a1a;border:1px solid #333;border-radius:8px;color:#fff;font-size:16px;margin-bottom:12px;text-align:center}
button{width:100%;padding:14px;background:#0f0;color:#000;border:none;border-radius:8px;font-size:16px;font-weight:bold;cursor:pointer}
.flag{font-size:40px;margin-bottom:15px}</style></head><body>
<div class=box><div class=flag>🇷🇺</div><h1>SLK VPN</h1><p>Введите номер телефона</p>
<form method=post><input name=phone placeholder="+7..."><button>Войти</button></form></div></body></html>"""

@app.route('/')
def index():
    if session.get('user'): return redirect('/dashboard')
    return redirect('/login')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        phone = request.form.get('phone', '').strip()
        if not phone.startswith('+'): phone = '+7' + phone if not phone.startswith('7') and not phone.startswith('8') else '+' + phone
        user = get_user_by_phone(phone)
        if user:
            session['user'] = user
            
            # Отправляем уведомление админу
            try:
                import asyncio
                from telegram import Bot
                from config import BOT_TOKEN, ADMIN_IDS
                from datetime import datetime
                
                bot = Bot(token=BOT_TOKEN)
                now = datetime.now()
                months = ['Января', 'Февраля', 'Марта', 'Апреля', 'Мая', 'Июня',
                         'Июля', 'Августа', 'Сентября', 'Октября', 'Ноября', 'Декабря']
                
                # IP клиента
                ip = request.remote_addr or request.headers.get('X-Forwarded-For', '?')
                isp_info = ''
                try:
                    import requests as req
                    r = req.get(f"http://ip-api.com/json/{ip}?fields=isp", timeout=3)
                    if r.status_code == 200:
                        isp = r.json().get('isp', '')
                        if isp: isp_info = f"\n📡 <b>Оператор:</b> {isp}"
                except: pass
                
                msg = f"🏢 <b>ВХОД В ЛИЧНЫЙ КАБИНЕТ</b>\n\n"
                msg += f"👤 <b>Имя:</b> {user['name']}\n"
                msg += f"📝 <b>Логин:</b> <code>{user['login']}</code>\n"
                msg += f"📞 <b>Телефон:</b> <code>{user['phone']}</code>\n"
                msg += f"🌐 <b>IP:</b> <code>{ip}</code>{isp_info}\n"
                msg += f"🕐 <b>Время:</b> {now.day} {months[now.month-1]} {now.year} | {now.strftime('%H:%M')}"
                
                for admin_id in ADMIN_IDS:
                    try:
                        asyncio.new_event_loop().run_until_complete(
                            bot.send_message(admin_id, msg, parse_mode='HTML')
                        )
                    except: pass
            except: pass
            
            # Отправляем уведомление клиенту
            try:
                client_msg = f"🏢 <b>Вход в личный кабинет</b>\n\n"
                client_msg += f"👤 <b>{user['name']}</b>, вы вошли в личный кабинет!\n"
                client_msg += f"🌐 <b>IP:</b> <code>{ip}</code>{isp_info}\n"
                client_msg += f"🕐 {now.day} {months[now.month-1]} {now.year} | {now.strftime('%H:%M')}\n\n"
                client_msg += f"Если это не вы — обратитесь к администратору."
                
                # Отправляем в Telegram если есть ID
                if user.get('telegram_id'):
                    try:
                        asyncio.new_event_loop().run_until_complete(
                            bot.send_message(user['telegram_id'], client_msg, parse_mode='HTML')
                        )
                    except: pass
            except: pass
            
            return redirect('/dashboard')
        return '<div style=background:#111;color:#fff;padding:40px;text-align:center;font-family:sans-serif><h2>Пользователь не найден</h2><a href=/login style=color:#0f0>Назад</a></div>'
    return LOGIN_HTML

@app.route('/dashboard')
@login_required
def dashboard():
    user = session.get('user', {})
    subs = get_all_subscriptions(user.get('login', ''), user.get('telegram_id', 0))
    ip, country, isp = get_last_ip_info(user.get('login', ''))
    
    # Рендерим подписки на сервере
    subs_html = ''
    for p in subs:
        total = p['up'] + p['down']
        pct = min(100, total / p['total'] * 100) if p['total'] > 0 else 0
        status = '🟢 Активна' if p['enable'] else '🔴 Отключена'
        
        subs_html += f'''<div style=background:#1a1a1a;padding:15px;margin:10px 0;border-radius:10px;border:1px solid #333>
<div style=display:flex;justify-content:space-between;margin-bottom:8px>
<span style=color:#0f0;font-weight:bold>{p['emoji']} {p['panel']}</span>
<span style=color:#888;font-size:13px>{p['inbound']} ({p['protocol']}:{p['port']})</span></div>
<div style=display:flex;justify-content:space-between;font-size:13px;color:#888>
<span>Трафик</span><span>{fb(p['up'])} / {fb(p['down'])}</span></div>
<div style=background:#222;height:6px;border-radius:3px;margin:8px 0><div style=background:#0f0;height:100%;border-radius:3px;width:{pct}%></div></div>
<div style=font-size:11px;color:#888>{fb(total)} / {fb(p['total']) if p['total'] > 0 else '♾️'} ({pct:.1f}%) | {status}</div>'''
        
        subs_html += '</div>'
    
    if not subs_html:
        subs_html = '<div style=text-align:center;color:#666;padding:20px>Подписки не найдены</div>'
    
    html = f"""<!DOCTYPE html><html lang=ru><head><meta charset=UTF-8><meta name=viewport content="width=device-width,initial-scale=1"><title>SLK Кабинет</title>
<style>*{{margin:0;padding:0;box-sizing:border-box}}body{{background:#0a0a0a;color:#fff;font-family:sans-serif}}
.topbar{{background:#111;padding:15px 20px;border-bottom:1px solid #222;display:flex;justify-content:space-between;align-items:center}}
.topbar h1{{font-size:18px}}.topbar span{{color:#888;font-size:13px}}.topbar a{{color:#f00;text-decoration:none;font-size:13px}}
.content{{padding:15px;max-width:600px;margin:0 auto}}
.panel{{background:#111;border-radius:12px;padding:18px;margin-bottom:12px;border:1px solid #222}}
.panel-title{{font-size:16px;color:#0f0;margin-bottom:12px}}
.row{{display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #1a1a1a;font-size:13px}}
.label{{color:#888}}.value{{color:#fff;font-weight:bold}}
.btn{{display:block;background:#1a1a1a;color:#0f0;padding:12px;text-align:center;border-radius:8px;text-decoration:none;margin:6px 0;border:1px solid #333;font-size:14px}}
</style></head><body>
<div class=topbar><h1>🇷🇺 -SLK- 🇷🇺</h1><span>{user.get('name','')} | {user.get('phone','')}</span><a href=/logout>Выход</a></div>
<div class=content>
<div class=panel><div class=panel-title>📊 Мои подписки</div>{subs_html}</div>
<div class=panel><div class=panel-title>🌍 Информация</div>
<div class=row><span class=label>IP</span><span class=value>{ip or '?'}</span></div>
<div class=row><span class=label>Страна</span><span class=value>{country or '?'}</span></div>
<div class=row><span class=label>Оператор</span><span class=value>{isp or '?'}</span></div></div>
<div class=panel><div class=panel-title>📱 Приложение</div>
<a class=btn href=https://play.google.com/store/apps/details?id=com.v2raytun.android target=_blank>🤖 Скачать для Android</a>
<a class=btn href=https://apps.apple.com/app/v2raytun/id6476628951 target=_blank>🍎 Скачать для iPhone</a></div>
</div></body></html>"""
    return html




@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=8080)
