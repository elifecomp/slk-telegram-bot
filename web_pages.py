#!/usr/bin/env python3
"""SLK Дашборд — в стиле 3x-ui"""
import sys, os, json
sys.path.insert(0, '/opt/SLV_Bot')
from config import BOT_TOKEN, ADMIN_IDS
from flask import Flask, jsonify, request, redirect, session
from functools import wraps
from datetime import datetime

app = Flask(__name__)
app.config['SECRET_KEY'] = 'slk-dashboard-2026'
USERS = {'Alexa': 'Alexa0319677'}

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect('/login')
        return f(*args, **kwargs)
    return decorated

def fb(b):
    if not b: return '0 B'
    for u in ['B', 'KB', 'MB', 'GB', 'TB']:
        if b < 1024: return f"{b:.2f} {u}"
        b /= 1024
    return f"{b:.2f} PB"

def get_all_data():
    from panel_manager import get_panels_list, set_active_panel, get_active_panel
    from xui_api import get_online_clients, get_inbounds_list, get_server_status
    panels = get_panels_list()
    original = get_active_panel()['id']
    result = {'panels': [], 'server': {}, 'top10': [], 'total_up': 0, 'total_down': 0, 'total_clients': 0, 'total_online': 0}
    try:
        srv = get_server_status()
        result['server'] = {
            'cpu': srv.get('cpu', 0), 'mem': round(srv.get('mem', {}).get('current', 0) / srv.get('mem', {}).get('total', 1) * 100),
            'disk': round(srv.get('disk', {}).get('current', 0) / srv.get('disk', {}).get('total', 1) * 100),
            'uptime': srv.get('uptime', 0), 'load': srv.get('loads', [0,0,0])[0],
            'tcp': srv.get('tcpCount', 0), 'udp': srv.get('udpCount', 0),
            'xray': srv.get('xray', {}).get('state', '?'),
            'ip': srv.get('publicIP', {}).get('ipv4', '?'),
            'xray_ver': srv.get('xray', {}).get('version', '?'),
            'panel_ver': '3.0.2', 'host': 'elifecomp.ru',
            'net_sent': srv.get('netTraffic', {}).get('sent', 0),
            'net_recv': srv.get('netTraffic', {}).get('recv', 0),
        }
    except: pass
    all_clients = []
    for panel in panels:
        set_active_panel(panel['id'])
        online = get_online_clients()
        inbounds = get_inbounds_list()
        clients = []
        up = 0; down = 0
        for inbound in inbounds:
            for c in inbound.get('clientStats', []):
                email = c.get('email', '')
                total = c.get('up', 0) + c.get('down', 0)
                up += c.get('up', 0); down += c.get('down', 0)
                clients.append({'email': email, 'up': c.get('up', 0), 'down': c.get('down', 0), 'total': total, 'inbound': inbound.get('remark', '?'), 'enable': c.get('enable', True), 'online': email in online})
                if total > 0:
                    all_clients.append({'email': email, 'total': total, 'panel': panel['name'], 'emoji': panel['emoji']})
        result['panels'].append({'name': panel['name'], 'emoji': panel['emoji'], 'online': len(online), 'clients': len(clients), 'inbounds': len(inbounds), 'client_list': clients[:30], 'up': up, 'down': down})
        result['total_up'] += up; result['total_down'] += down
        result['total_clients'] += len(clients); result['total_online'] += len(online)
    set_active_panel(original)
    all_clients.sort(key=lambda x: x['total'], reverse=True)
    result['top10'] = all_clients[:10]
    return result

PAGE = r"""<!DOCTYPE html><html lang=ru><head><meta charset=UTF-8><meta name=viewport content="width=device-width,initial-scale=1"><title>SLK Панель</title>
<style>
*{margin:0;padding:0;box-sizing:border-box}
body{background:#0d0d0d;color:#e0e0e0;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}
.topbar{background:#111;padding:14px 24px;border-bottom:1px solid #222;display:flex;justify-content:space-between;align-items:center}
.topbar h1{font-size:18px;font-weight:600;color:#fff}.topbar a{color:#c4a35a;text-decoration:none;font-size:12px}
.tabs{display:flex;gap:0;background:#111;border-bottom:1px solid #222;padding:0 24px}
.tab{padding:12px 18px;cursor:pointer;color:#888;border:none;background:transparent;font-size:12px;font-weight:500;transition:all .2s;border-bottom:2px solid transparent}
.tab:hover{color:#fff}.tab.active{color:#c4a35a;border-bottom:2px solid #c4a35a}
.content{padding:20px;max-width:1100px;margin:0 auto}
.stats-grid{display:grid;grid-template-columns:repeat(auto-fit,minmax(140px,1fr));gap:10px;margin-bottom:16px}
.stat-card{background:#141414;padding:14px;border-radius:10px;border:1px solid #1a1a1a}
.stat-value{font-size:24px;font-weight:700;color:#fff}
.stat-label{color:#666;font-size:10px;margin-top:2px;text-transform:uppercase}
.stat-up{color:#4caf50}.stat-down{color:#2196f3}
.panel-card{background:#141414;border-radius:10px;padding:16px;margin-bottom:10px;border:1px solid #1a1a1a}
.panel-header{display:flex;justify-content:space-between;align-items:center;margin-bottom:10px}
.panel-name{font-size:15px;font-weight:600;color:#fff}
.panel-stats{display:flex;gap:16px;font-size:12px;color:#888}
.panel-stats span{color:#e0e0e0;font-weight:500}
.client-list{font-size:12px}
.client-row{display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid #1a1a1a}
.client-email{color:#c4a35a}.client-traffic{color:#888}
.online-dot{display:inline-block;width:6px;height:6px;border-radius:50%;margin-right:6px}
.online-dot.on{background:#4caf50;box-shadow:0 0 6px #4caf50}.online-dot.off{background:#444}
.top-row{display:flex;align-items:center;gap:10px;padding:8px 0;border-bottom:1px solid #1a1a1a}
.top-rank{font-size:20px;font-weight:700;width:30px;color:#c4a35a}
.top-email{flex:1;font-size:13px;font-weight:500}.top-total{color:#fff;font-weight:700;font-size:13px}
.server-grid{display:grid;grid-template-columns:1fr 1fr;gap:8px}.server-2col{display:grid;grid-template-columns:1fr 1fr;gap:12px}
.server-item{background:#1a1a1a;padding:12px;border-radius:8px}
.server-label{color:#888;font-size:10px;text-transform:uppercase}
.server-value{color:#fff;font-size:18px;font-weight:700;margin-top:3px}
.loading{text-align:center;color:#555;padding:40px}
@media(max-width:600px){.tab{padding:8px 10px;font-size:10px}.server-grid{grid-template-columns:1fr}}
</style></head><body>
<div class=topbar><h1>🇷🇺 -SLK- 🇷🇺 Панель управления</h1><a href=/logout>Выход</a></div>
<div class=tabs>
<button class=tab active onclick="showTab('dashboard')">📊 Обзор</button>
<button class=tab onclick="showTab('online')">🟢 Онлайн</button>
<button class=tab onclick="showTab('clients')">👥 Клиенты</button>
<button class=tab onclick="showTab('top10')">🏆 ТОП-10</button>
<button class=tab onclick="showTab('server')">🖥️ Сервер</button>
</div>
<div class=content id=content><div class=loading>Загрузка...</div></div>
<script>
let data=null;let currentTab='dashboard';
function fb(b){if(!b)return'0 B';const u=['B','KB','MB','GB','TB'];let i=0;while(b>=1024&&i<4){b/=1024;i++}return b.toFixed(2)+' '+u[i]}
function uptime(s){const d=Math.floor(s/86400);const h=Math.floor((s%86400)/3600);const m=Math.floor((s%3600)/60);return d+'д '+h+'ч '+m+'м'}
async function load(){const r=await fetch('/api/all');data=await r.json();showTab('dashboard')}
function showTab(tab){currentTab=tab;
document.querySelectorAll('.tab').forEach(t=>t.classList.remove('active'));
event.target.classList.add('active');
const c=document.getElementById('content');
if(!data){c.innerHTML='<div class=loading>Загрузка...</div>';return}
let h='';const s=data.server||{};const p=data.panels||[];const t10=data.top10||[];
if(tab==='dashboard'){
h=`<div class=stats-grid>
<div class=stat-card><div class=stat-value>${data.total_clients}</div><div class=stat-label>👥 Всего клиентов</div></div>
<div class=stat-card><div class=stat-value style=color:#4caf50>${data.total_online}</div><div class=stat-label>🟢 Онлайн</div></div>
<div class=stat-card><div class=stat-value class=stat-up>${fb(data.total_up)}</div><div class=stat-label>⬆ Отправлено</div></div>
<div class=stat-card><div class=stat-value class=stat-down>${fb(data.total_down)}</div><div class=stat-label>⬇ Получено</div></div>
<div class=stat-card><div class=stat-value>${fb(data.total_up + data.total_down)}</div><div class=stat-label>📊 Всего трафика</div></div>
<div class=stat-card><div class=stat-value style=color:${s.xray==='running'?'#4caf50':'#f44336'}>${s.xray==='running'?'✅ Работает':'❌ Остановлен'}</div><div class=stat-label>🚀 Xray</div></div>
<div class=stat-card><div class=stat-value>${(s.cpu||0).toFixed(1)}%</div><div class=stat-label>⚡ CPU</div></div>
<div class=stat-card><div class=stat-value>${s.mem||0}%</div><div class=stat-label>🧠 RAM</div></div>
</div>`;
p.forEach(x=>{
h+=`<div class=panel-card><div class=panel-header><div class=panel-name>${x.emoji} ${x.name}</div><div class=panel-stats>👥<span>${x.clients}</span> 🟢<span>${x.online}</span> 📡<span>${x.inbounds}</span> ⬆<span>${fb(x.up)}</span> ⬇<span>${fb(x.down)}</span></div></div></div></div>`})}
if(tab==='online'){p.forEach(x=>{h+=`<div class=panel-card><div class=panel-header><div class=panel-name>${x.emoji} ${x.name} — ${x.online} онлайн</div></div>`;x.client_list.filter(c=>c.online).forEach(c=>{h+=`<div class=client-row><span class=client-email><span class="online-dot on"></span>${c.email}</span><span class=client-traffic>${fb(c.up)} / ${fb(c.down)}</span></div>`});h+='</div>'})}
if(tab==='clients'){p.forEach(x=>{h+=`<div class=panel-card><div class=panel-header><div class=panel-name>${x.emoji} ${x.name} — ${x.clients} клиентов</div></div>`;x.client_list.forEach(c=>{h+=`<div class=client-row><span class=client-email><span class="online-dot ${c.online?'on':'off'}"></span>${c.email}</span><span class=client-traffic>${fb(c.total)}</span></div>`});h+='</div>'})}
if(tab==='top10'){const m=['🥇','🥈','🥉','4','5','6','7','8','9','10'];h='<div class=panel-card><div class=panel-header><div class=panel-name>🏆 ТОП-10 клиентов по трафику</div></div>';t10.forEach((c,i)=>{h+=`<div class=top-row><div class=top-rank>${m[i]}</div><div class=top-email>${c.email}<div style=font-size:10px;color:#888>${c.emoji} ${c.panel}</div></div><div class=top-total>${fb(c.total)}</div></div></div>`});h+='</div>'}
if(tab==='server'){h=`<div class=server-2col><div class=panel-card><div class=panel-header><div class=panel-name>🖥️ Сервер</div></div><div class=server-grid>
<div class=server-item><div class=server-label>⚡ CPU</div><div class=server-value>${(s.cpu||0).toFixed(1)}%</div></div>
<div class=server-item><div class=server-label>🧠 RAM</div><div class=server-value>${s.mem||0}%</div></div>
<div class=server-item><div class=server-label>💾 Диск</div><div class=server-value>${s.disk||0}%</div></div>
<div class=server-item><div class=server-label>📈 Load</div><div class=server-value>${s.load||0}</div></div>
<div class=server-item><div class=server-label>🔗 TCP/UDP</div><div class=server-value>${s.tcp||0}/${s.udp||0}</div></div>
<div class=server-item><div class=server-label>⏰ Аптайм</div><div class=server-value>${uptime(s.uptime||0)}</div></div>
<div class=server-item><div class=server-label>🌐 IPv4</div><div class=server-value style=font-size:12px>${s.ip||'?'}</div></div>
<div class=server-item><div class=server-label>🏷️ Хост</div><div class=server-value style=font-size:13px>elifecomp.ru</div></div>
</div></div>
<div class=panel-card style=margin-top:10px><div class=panel-header><div class=panel-name>🚀 Сервисы</div></div><div class=server-grid>
<div class=server-item><div class=server-label>Xray статус</div><div class=server-value style=color:${s.xray==='running'?'#4caf50':'#f44336'}>${s.xray==='running'?'✅ Работает':'❌ Остановлен'}</div></div>
<div class=server-item><div class=server-label>Xray версия</div><div class=server-value style=font-size:14px>${s.xray_ver||'?'}</div></div>
<div class=server-item><div class=server-label>3x-ui версия</div><div class=server-value style=font-size:14px>${s.panel_ver||'?'}</div></div>
<div class=server-item><div class=server-label>Бот Telegram</div><div class=server-value style=color:#4caf50;font-size:14px>✅ Работает</div></div>
</div></div></div>`}
c.innerHTML=h||'<div class=loading>Нет данных</div>'}
setTimeout(load,100);setInterval(()=>{if(data)showTab(currentTab)},5000)
</script></body></html>"""

LOGIN_PAGE = """<!DOCTYPE html><html lang=ru><head><meta charset=UTF-8><meta name=viewport content="width=device-width,initial-scale=1"><title>SLK Вход</title>
<style>*{margin:0;padding:0;box-sizing:border-box}body{background:#0d0d0d;display:flex;justify-content:center;align-items:center;min-height:100vh;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',sans-serif}
.box{background:#141414;padding:48px;border-radius:16px;border:1px solid #1a1a1a;width:380px;text-align:center}
h1{color:#fff;margin-bottom:8px;font-size:24px;font-weight:600}p{color:#888;margin-bottom:24px;font-size:14px}
input{width:100%;padding:14px;background:#1a1a1a;border:1px solid #222;border-radius:8px;color:#fff;font-size:15px;margin-bottom:12px;outline:none;transition:border .2s}
input:focus{border-color:#c4a35a}
button{width:100%;padding:14px;background:#c4a35a;color:#0d0d0d;border:none;border-radius:8px;font-size:15px;font-weight:600;cursor:pointer;transition:opacity .2s}
button:hover{opacity:.9}
.flag{font-size:40px;margin-bottom:20px}</style></head><body>
<div class=box><div class=flag>🇷🇺</div><h1>SLK Панель</h1><p>Введите логин и пароль</p>
<form method=post><input name=username placeholder=Логин><input name=password type=password placeholder=Пароль><button>Войти</button></form></div></body></html>"""

@app.route('/')
def index(): return redirect('/dashboard#loaded')

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        if USERS.get(request.form.get('username')) == request.form.get('password'):
            session['logged_in'] = True
            # Уведомление в Telegram
            try:
                import asyncio
                from telegram import Bot
                from datetime import datetime
                bot = Bot(token=BOT_TOKEN)
                now = datetime.now()
                ip = request.remote_addr or '?'
                isp = ''
                try:
                    import requests as req
                    r = req.get(f"http://ip-api.com/json/{ip}?fields=isp", timeout=3)
                    if r.status_code == 200:
                        isp = r.json().get('isp', '')
                except: pass
                isp_info = ""
                try:
                    import requests as req
                    r = req.get(f"http://ip-api.com/json/{ip}?fields=isp", timeout=3)
                    if r.status_code == 200:
                        isp = r.json().get('isp', '')
                        if isp: isp_info = f"\n📡 <b>Оператор:</b> {isp}"
                except: pass
                msg = f"🛡️ <b>ВХОД В АДМИН-ПАНЕЛЬ</b>\n\n👤 <b>Alexa</b>\n🌐 <b>IP:</b> <code>{ip}</code>{isp_info}\n🕐 {now.strftime('%H:%M')} | {now.day}.{now.month}.{now.year}"
                for aid in ADMIN_IDS:
                    try:
                        asyncio.new_event_loop().run_until_complete(bot.send_message(aid, msg, parse_mode='HTML'))
                    except: pass
            except: pass
            return redirect('/dashboard#loaded')
        return LOGIN_PAGE.replace('</form>', '<p style=color:#f44336;margin-top:12px>Неверный логин или пароль</p></form>')
    return LOGIN_PAGE

@app.route('/logout')
def logout():
    session.clear()
    return redirect('/login')

@app.route('/dashboard')
@login_required
def dashboard(): return PAGE

@app.route('/online')
@login_required
def online(): return PAGE

@app.route('/top10')
@login_required
def top10(): return PAGE

@app.route('/api/all')
@login_required
def api_all(): return jsonify(get_all_data())

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5001)
