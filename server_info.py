# [file name]: server_info.py
import logging
from datetime import datetime
from xui_api import get_server_status as get_api_server_status, get_panel_update_info, get_panel_update_info

logger = logging.getLogger(__name__)

def format_uptime(seconds):
    """Форматирует время работы"""
    days = seconds // 86400
    hours = (seconds % 86400) // 3600
    minutes = (seconds % 3600) // 60
    
    if days > 0:
        return f"{days}д {hours}ч {minutes}м"
    elif hours > 0:
        return f"{hours}ч {minutes}м"
    else:
        return f"{minutes}м"

def format_traffic(bytes_count):
    """Форматирует трафик в читаемый вид"""
    if bytes_count == 0:
        return "0 B"
    
    for unit in ['B', 'KB', 'MB', 'GB', 'TB']:
        if bytes_count < 1024.0:
            return f"{bytes_count:.2f} {unit}"
        bytes_count /= 1024.0
    
    return f"{bytes_count:.2f} PB"

def format_memory(bytes_count):
    """Форматирует память в MB/GB"""
    if bytes_count < 1024 * 1024 * 1024:
        return f"{bytes_count / (1024 * 1024):.0f} MB"
    else:
        return f"{bytes_count / (1024 * 1024 * 1024):.2f} GB"

def get_server_status():
    """Получает полный статус сервера через API панели 3x-ui"""
    try:
        api = get_api_server_status()
        if not api:
            return "❌ <b>Не удалось получить данные от API панели</b>"
        
        now = datetime.now()
        months = ['Января', 'Февраля', 'Марта', 'Апреля', 'Мая', 'Июня',
                 'Июля', 'Августа', 'Сентября', 'Октября', 'Ноября', 'Декабря']
        current_time = f"{now.day} {months[now.month-1]} {now.year} {now.strftime('%H:%M:%S')}"

        
        # Основные метрики
        cpu = api.get('cpu', 0)
        cpu_cores = api.get('cpuCores', 0)
        logical_pro = api.get('logicalPro', 0)
        cpu_speed = api.get('cpuSpeedMhz', 0)
        
        mem = api.get('mem', {})
        mem_current = mem.get('current', 0)
        mem_total = mem.get('total', 0)
        mem_percent = (mem_current / mem_total * 100) if mem_total > 0 else 0
        
        swap = api.get('swap', {})
        swap_current = swap.get('current', 0)
        swap_total = swap.get('total', 0)
        
        disk = api.get('disk', {})
        disk_current = disk.get('current', 0)
        disk_total = disk.get('total', 0)
        disk_percent = (disk_current / disk_total * 100) if disk_total > 0 else 0
        
        xray = api.get('xray', {})
        xray_state = xray.get('state', 'unknown')
        xray_version = xray.get('version', '?')
        
        uptime_seconds = api.get('uptime', 0)
        loads = api.get('loads', [0, 0, 0])
        
        tcp_count = api.get('tcpCount', 0)
        udp_count = api.get('udpCount', 0)
        
        net_traffic = api.get('netTraffic', {})
        net_sent = net_traffic.get('sent', 0)
        net_recv = net_traffic.get('recv', 0)
        
        net_io = api.get('netIO', {})
        net_up = net_io.get('up', 0)
        net_down = net_io.get('down', 0)
        
        public_ip = api.get('publicIP', {})
        ipv4 = public_ip.get('ipv4', '?')
        ipv6 = public_ip.get('ipv6', '')
        
        app_stats = api.get('appStats', {})
        app_threads = app_stats.get('threads', 0)
        app_mem = app_stats.get('mem', 0)
        app_uptime = app_stats.get('uptime', 0)
        
        # Обновления панели
        update_info = get_panel_update_info()
        panel_version = update_info.get('currentVersion', '?') if update_info else '?'
        update_available = update_info.get('updateAvailable', False) if update_info else False
        
        # Формируем сообщение
        message = "🖥️ <b>СОСТОЯНИЕ СЕРВЕРА</b>\n\n"
        message += f"🕐 <b>Проверка:</b> {current_time}\n"
        message += f"🌐 <b>IPv4:</b> <code>{ipv4}</code>\n"
        
        if ipv6:
            message += f"🌍 <b>IPv6:</b> <code>{ipv6}</code>\n"
        
        import socket
        hostname = socket.gethostname()
        message += f"🏷️ <b>Хост:</b> <code>{hostname}</code>\n"
        
        # Домен из URL панели
        from panel_manager import get_active_panel
        panel = get_active_panel()
        from urllib.parse import urlparse
        domain = urlparse(panel['url']).hostname or ''
        message += f"🌐 <b>Домен:</b> <code>{domain}</code>\n"
        
        message += f"⏰ <b>Аптайм:</b> {format_uptime(uptime_seconds)}\n\n"
        
        # Ресурсы
        message += "📊 <b>РЕСУРСЫ:</b>\n"
        message += f"⚡ <b>CPU:</b> {cpu:.1f}% "
        message += f"({cpu_cores} ядер, {cpu_speed:.0f} MHz)\n"
        message += f"🧠 <b>RAM:</b> {mem_percent:.0f}% "
        message += f"({format_memory(mem_current)} / {format_memory(mem_total)})\n"
        
        if swap_total > 0:
            swap_percent = (swap_current / swap_total * 100) if swap_total > 0 else 0
            message += f"💿 <b>Swap:</b> {swap_percent:.0f}% "
            message += f"({format_memory(swap_current)} / {format_memory(swap_total)})\n"
        
        message += f"💾 <b>Диск:</b> {disk_percent:.0f}% "
        message += f"({format_memory(disk_current)} / {format_memory(disk_total)})"
        free = disk_total - disk_current
        message += f" | Свободно: {format_memory(free)}\n"
        
        message += f"📈 <b>Load:</b> {loads[0]:.2f} / {loads[1]:.2f} / {loads[2]:.2f}\n\n"
        
        # Сеть
        message += "🌐 <b>СЕТЬ:</b>\n"
        message += f"🔹 <b>TCP:</b> {tcp_count} | 🔸 <b>UDP:</b> {udp_count}\n"
        message += f"⬆️ <b>Отправлено:</b> {format_traffic(net_sent)}\n"
        message += f"⬇️ <b>Получено:</b> {format_traffic(net_recv)}\n"
        message += f"📡 <b>Скорость:</b> ↑{format_traffic(net_up)}/s ↓{format_traffic(net_down)}/s\n\n"
        
        # Xray
        xray_emoji = "🟢" if xray_state == 'running' else "🔴"
        message += "🚀 <b>XRAY:</b>\n"
        message += f"{xray_emoji} <b>Статус:</b> {'Работает' if xray_state == 'running' else xray_state}\n"
        message += f"📦 <b>Версия:</b> {xray_version}\n\n"
        
        # Панель
        update_emoji = "🔄" if update_available else "✅"
        message += "⚙️ <b>ПАНЕЛЬ 3X-UI:</b>\n"
        message += f"📦 <b>Версия:</b> {panel_version}\n"
        if update_available:
            new_ver = update_info.get('latestVersion', '?')
            message += f"🔄 <b>Обновление:</b> Доступна {new_ver}\n\n"
        else:
            message += f"✅ <b>Обновление:</b> Актуально\n\n"
        
        # Приложение (бот)
        message += "🤖 <b>БОТ:</b>\n"
        message += f"🧵 <b>Потоков:</b> {app_threads}\n"
        message += f"🧠 <b>RAM:</b> {format_memory(app_mem)}\n"
        message += f"⏰ <b>Аптайм:</b> {format_uptime(app_uptime)}\n"
        
        # Статус системы
        if xray_state == 'running' and cpu < 90 and mem_percent < 90:
            message += f"\n✅ <b>Система работает стабильно</b>"
        else:
            message += f"\n⚠️ <b>Требуется внимание</b>"
        
        return message
        
    except Exception as e:
        logger.error(f"Ошибка получения статуса сервера: {e}")
        return f"❌ <b>Ошибка при получении статуса сервера:</b> {str(e)}"
