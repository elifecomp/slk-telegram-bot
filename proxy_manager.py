# [file name]: proxy_manager.py
"""Управление SOCKS5 прокси Dante"""

import subprocess
import logging

logger = logging.getLogger(__name__)

def get_proxy_status():
    """Получает статус прокси"""
    try:
        # Статус сервиса
        result = subprocess.run(['systemctl', 'is-active', 'danted'],
                               capture_output=True, text=True, timeout=5)
        status = result.stdout.strip()

        # Активные подключения
        result2 = subprocess.run(['ss', '-tn'],
                                capture_output=True, text=True, timeout=5)
        connections = len([l for l in result2.stdout.split('\n') if ':54985' in l])

        # Логи (последние 5 строк)
        try:
            log = subprocess.run(['journalctl', '-u', 'danted', '--no-pager', '-n', '5'],
                                capture_output=True, text=True, timeout=5)
            logs = log.stdout.strip().split('\n')[-3:]
        except:
            logs = ['Лог недоступен']

        # Конфиг
        try:
            with open('/etc/danted.conf', 'r') as f:
                config_lines = [l.strip() for l in f.readlines() if not l.startswith('#') and l.strip()]
        except:
            config_lines = ['Конфиг не найден']

        return {
            'status': status,
            'connections': connections,
            'port': 54985,
            'logs': logs,
            'config': config_lines
        }
    except Exception as e:
        return {'status': 'error', 'error': str(e)}

def restart_proxy():
    """Перезагружает прокси"""
    try:
        subprocess.run(['systemctl', 'restart', 'danted'], timeout=10)
        return True
    except:
        return False

def get_proxy_users():
    """Получает список пользователей прокси (системные)"""
    try:
        import subprocess
        result = subprocess.run(['awk', '-F:', '$3>=1000 && $3<65534 {print $1}', '/etc/passwd'],
                               capture_output=True, text=True, timeout=5)
        users = [{'login': u.strip()} for u in result.stdout.strip().split('\n') if u.strip()]
        return users
    except:
        return []

def add_proxy_user(login, password):
    """Добавляет пользователя прокси (системного)"""
    try:
        import subprocess
        # Создаём пользователя без домашней папки
        subprocess.run(['useradd', '-M', '-s', '/usr/sbin/nologin', login],
                      capture_output=True, timeout=10)
        # Устанавливаем пароль
        subprocess.run(['chpasswd'], input=f"{login}:{password}".encode(),
                      capture_output=True, timeout=10)
        return True
    except:
        return False
