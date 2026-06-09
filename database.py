# [file name]: database.py
import sqlite3
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

class Database:
    def __init__(self, db_path='clients.db'):
        self.db_path = db_path
        self.init_db()

    def init_db(self):
        """Инициализация базы данных"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Таблица клиентов
            cursor.execute('''
                CREATE TABLE IF NOT EXISTS clients (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    telegram_id INTEGER UNIQUE NOT NULL,
                    login TEXT UNIQUE NOT NULL,
                    phone TEXT NOT NULL,
                    name TEXT NOT NULL,
                    registration_date TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    is_active BOOLEAN DEFAULT TRUE
                )
            ''')
            
            conn.commit()
            conn.close()
            logger.info("База данных инициализирована успешно")
        except Exception as e:
            logger.error(f"Ошибка инициализации базы данных: {e}")

    def add_client(self, telegram_id, login, phone, name):
        """Добавление нового клиента"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                INSERT INTO clients (telegram_id, login, phone, name)
                VALUES (?, ?, ?, ?)
            ''', (telegram_id, login, phone, name))
            
            conn.commit()
            conn.close()
            logger.info(f"Клиент {login} добавлен в базу")
            return True
        except sqlite3.IntegrityError as e:
            logger.error(f"Ошибка добавления клиента (дубликат): {e}")
            return False
        except Exception as e:
            logger.error(f"Ошибка добавления клиента: {e}")
            return False

    def get_client_by_telegram_id(self, telegram_id):
        """Получение клиента по Telegram ID"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT * FROM clients WHERE telegram_id = ?
            ''', (telegram_id,))
            
            client = cursor.fetchone()
            conn.close()
            
            if client:
                return {
                    'id': client[0],
                    'telegram_id': client[1],
                    'login': client[2],
                    'phone': client[3],
                    'name': client[4],
                    'registration_date': client[5],
                    'is_active': bool(client[6]), 'login2': client[7] if len(client) > 7 else None, 'birthday': client[8] if len(client) > 8 else None, 'hwid': client[9] if len(client) > 9 else None, 'city': client[10] if len(client) > 10 else None,
                    'login2': client[7] if len(client) > 7 else None
                }
            return None
        except Exception as e:
            logger.error(f"Ошибка получения клиента: {e}")
            return None

    def get_client_by_id(self, client_id):
        """Получение клиента по ID"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT * FROM clients WHERE id = ?
            ''', (client_id,))
            
            client = cursor.fetchone()
            conn.close()
            if client:
                return {
                    'id': client[0],
                    'telegram_id': client[1],
                    'login': client[2],
                    'phone': client[3],
                    'name': client[4],
                    'registration_date': client[5],
                    'is_active': bool(client[6]),
                    'login2': client[7] if len(client) > 7 else None,
                    'birthday': client[8] if len(client) > 8 else None,
                    'hwid': client[9] if len(client) > 9 else None,
                    'city': client[10] if len(client) > 10 else None
                }
            return None
        except Exception as e:
            logger.error(f"Ошибка получения клиента по ID: {e}")
            return None

    def get_client_by_login(self, login):
        """Получение клиента по логину"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                SELECT * FROM clients WHERE login = ?
            ''', (login,))
            
            client = cursor.fetchone()
            conn.close()
            
            if client:
                return {
                    'id': client[0],
                    'telegram_id': client[1],
                    'login': client[2],
                    'phone': client[3],
                    'name': client[4],
                    'registration_date': client[5],
                    'is_active': bool(client[6]), 'login2': client[7] if len(client) > 7 else None, 'birthday': client[8] if len(client) > 8 else None, 'hwid': client[9] if len(client) > 9 else None, 'city': client[10] if len(client) > 10 else None,
                    'login2': client[7] if len(client) > 7 else None
                }
            return None
        except Exception as e:
            logger.error(f"Ошибка получения клиента по логину: {e}")
            return None

    def client_exists(self, telegram_id):
        """Проверка существования клиента"""
        return self.get_client_by_telegram_id(telegram_id) is not None

    def get_all_clients(self):
        """Получение всех клиентов"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('SELECT * FROM clients ORDER BY registration_date DESC')
            
            clients = []
            for row in cursor.fetchall():
                clients.append({
                    'id': row[0],
                    'telegram_id': row[1],
                    'login': row[2],
                    'phone': row[3],
                    'name': row[4],
                    'registration_date': row[5],
                    'is_active': bool(row[6]),
                    'birthday': row[8] if len(row) > 8 else None,
                    'hwid': row[9] if len(row) > 9 else None,
                    'login2': row[7] if len(row) > 7 else None,
                    'city': row[10] if len(row) > 10 else None,
                    'city': row[10] if len(row) > 10 else None,
                    'city': row[10] if len(row) > 10 else None
                })
            
            conn.close()
            return clients
        except Exception as e:
            logger.error(f"Ошибка получения всех клиентов: {e}")
            return []

    def update_client_login(self, client_id, new_login):
        """Обновление логина клиента"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE clients SET login = ? WHERE id = ?
            ''', (new_login, client_id))
            
            conn.commit()
            conn.close()
            logger.info(f"Логин клиента {client_id} обновлен на {new_login}")
            return True
        except sqlite3.IntegrityError as e:
            logger.error(f"Ошибка обновления логина (дубликат): {e}")
            return False
        except Exception as e:
            logger.error(f"Ошибка обновления логина: {e}")
            return False

    def update_client_phone(self, client_id, new_phone):
        """Обновление телефона клиента"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE clients SET phone = ? WHERE id = ?
            ''', (new_phone, client_id))
            
            conn.commit()
            conn.close()
            logger.info(f"Телефон клиента {client_id} обновлен на {new_phone}")
            return True
        except Exception as e:
            logger.error(f"Ошибка обновления телефона: {e}")
            return False

    def update_client_name(self, client_id, new_name):
        """Обновление имени клиента"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('''
                UPDATE clients SET name = ? WHERE id = ?
            ''', (new_name, client_id))
            
            conn.commit()
            conn.close()
            logger.info(f"Имя клиента {client_id} обновлено на {new_name}")
            return True
        except Exception as e:
            logger.error(f"Ошибка обновления имени: {e}")
            return False

    def toggle_client_active(self, client_id):
        """Блокировка/разблокировка клиента"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            # Получаем текущее состояние
            cursor.execute('SELECT is_active FROM clients WHERE id = ?', (client_id,))
            current_state = cursor.fetchone()[0]
            new_state = not current_state
            
            cursor.execute('''
                UPDATE clients SET is_active = ? WHERE id = ?
            ''', (new_state, client_id))
            
            conn.commit()
            conn.close()
            
            action = "разблокирован" if new_state else "заблокирован"
            logger.info(f"Клиент {client_id} {action}")
            return new_state
        except Exception as e:
            logger.error(f"Ошибка изменения статуса клиента: {e}")
            return None

    def delete_client(self, client_id):
        """Удаление клиента"""
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            
            cursor.execute('DELETE FROM clients WHERE id = ?', (client_id,))
            
            conn.commit()
            conn.close()
            logger.info(f"Клиент {client_id} удален из базы")
            return True
        except Exception as e:
            logger.error(f"Ошибка удаления клиента: {e}")
            return False

# Создаем глобальный экземпляр базы данных

    def get_groups(self):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute('SELECT id, name FROM client_groups ORDER BY name')
            groups = [{'id': row[0], 'name': row[1]} for row in cursor.fetchall()]
            conn.close()
            return groups
        except:
            return []

    def get_client_groups(self, client_id):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT g.id, g.name FROM client_groups g JOIN client_group_link l ON g.id = l.group_id WHERE l.client_id = ?", (client_id,))
            groups = [{'id': row[0], 'name': row[1]} for row in cursor.fetchall()]
            conn.close()
            return groups
        except:
            return []

    def add_client_to_group(self, client_id, group_id):
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute('INSERT OR IGNORE INTO client_group_link (client_id, group_id) VALUES (?, ?)', (client_id, group_id))
            conn.commit()
            conn.close()
            return True
        except:
            return False

    def remove_client_from_group(self, client_id, group_id):
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute('DELETE FROM client_group_link WHERE client_id = ? AND group_id = ?', (client_id, group_id))
            conn.commit()
            conn.close()
            return True
        except:
            return False

    def get_clients_in_group(self, group_id):
        try:
            conn = sqlite3.connect(self.db_path)
            cursor = conn.cursor()
            cursor.execute("SELECT c.* FROM clients c JOIN client_group_link l ON c.id = l.client_id WHERE l.group_id = ? ORDER BY c.name", (group_id,))
            clients = []
            for row in cursor.fetchall():
                clients.append({'id': row[0], 'telegram_id': row[1], 'login': row[2], 'phone': row[3], 'name': row[4], 'registration_date': row[5], 'is_active': bool(row[6]),
                    'birthday': row[8] if len(row) > 8 else None,
                    'hwid': row[9] if len(row) > 9 else None,
                    'login2': row[7] if len(row) > 7 else None,
                    'city': row[10] if len(row) > 10 else None,
                    'city': row[10] if len(row) > 10 else None,
                    'city': row[10] if len(row) > 10 else None})
            conn.close()
            return clients
        except:
            return []

    def update_client_login2(self, client_id, new_login2):
        """Обновление второго логина"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute('UPDATE clients SET login2 = ? WHERE id = ?', (new_login2, client_id))
            conn.commit()
            conn.close()
            return True
        except:
            return False



    def update_client_birthday(self, client_id, birthday):
        """Обновление даты рождения"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute('UPDATE clients SET birthday = ? WHERE id = ?', (birthday, client_id))
            conn.commit()
            conn.close()
            return True
        except:
            return False


    def update_client_hwid(self, client_id, hwid):
        """Обновление HWID"""
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute('UPDATE clients SET hwid = ? WHERE id = ?', (hwid, client_id))
            conn.commit()
            conn.close()
            return True
        except:
            return False


    def update_client_city(self, client_id, city):
        try:
            conn = sqlite3.connect(self.db_path)
            conn.execute('UPDATE clients SET city = ? WHERE id = ?', (city, client_id))
            conn.commit()
            conn.close()
            return True
        except:
            return False

db = Database()