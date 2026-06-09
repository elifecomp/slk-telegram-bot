# [file name]: traffic_cache.py
import logging
from collections import OrderedDict
from datetime import datetime, timedelta
import threading
import time

logger = logging.getLogger(__name__)

class LRUTrafficHistory:
    """
    LRU (Least Recently Used) кэш для истории трафика клиентов.
    Потокобезопасная реализация с автоматической очисткой.
    """
    
    def __init__(self, max_size=10000, max_age_hours=24, cleanup_interval=3600):
        """
        Инициализация LRU-кэша
        
        Args:
            max_size: Максимальное количество записей в кэше
            max_age_hours: Максимальный возраст записи в часах
            cleanup_interval: Интервал автоматической очистки в секундах
        """
        self.max_size = max_size
        self.max_age = timedelta(hours=max_age_hours)
        self.cleanup_interval = cleanup_interval
        
        # Основное хранилище с поддержкой LRU
        self._cache = OrderedDict()
        
        # Блокировка для потокобезопасности
        self._lock = threading.RLock()
        
        # Время последней очистки
        self._last_cleanup = datetime.now()
        
        # Статистика
        self._stats = {
            'hits': 0,
            'misses': 0,
            'evictions': 0,
            'age_cleanups': 0
        }
        
        logger.info(f"✅ LRU-кэш инициализирован: макс. {max_size} записей, "
                   f"время жизни {max_age_hours} ч, очистка каждые {cleanup_interval} с")
    
    def get(self, key):
        """
        Получает запись из кэша и помечает как использованную
        
        Args:
            key: Email клиента
            
        Returns:
            dict или None, если запись не найдена
        """
        with self._lock:
            if key in self._cache:
                # Перемещаем в конец (самый используемый)
                self._cache.move_to_end(key)
                self._stats['hits'] += 1
                
                # Обновляем время последнего доступа
                self._cache[key]['_last_accessed'] = datetime.now()
                
                return self._cache[key].copy()  # Возвращаем копию для безопасности
            else:
                self._stats['misses'] += 1
                return None
    
    def set(self, key, value):
        """
        Добавляет или обновляет запись в кэше
        
        Args:
            key: Email клиента
            value: Словарь с данными клиента
        """
        with self._lock:
            # Добавляем служебные поля
            value['_last_accessed'] = datetime.now()
            if 'first_seen' not in value:
                value['first_seen'] = datetime.now()
            
            # Добавляем или обновляем запись
            self._cache[key] = value
            self._cache.move_to_end(key)
            
            # Проверяем необходимость очистки
            self._maybe_cleanup()
    
    def update(self, key, **kwargs):
        """
        Обновляет существующую запись
        
        Args:
            key: Email клиента
            **kwargs: Поля для обновления
        """
        with self._lock:
            if key in self._cache:
                self._cache[key].update(kwargs)
                self._cache[key]['_last_accessed'] = datetime.now()
                self._cache.move_to_end(key)
                return True
        return False
    
    def remove(self, key):
        """
        Удаляет запись из кэша
        
        Args:
            key: Email клиента
        """
        with self._lock:
            if key in self._cache:
                del self._cache[key]
                logger.debug(f"Запись {key} удалена из кэша")
                return True
        return False
    
    def clear(self):
        """Полная очистка кэша"""
        with self._lock:
            self._cache.clear()
            logger.info("🧹 Кэш истории трафика полностью очищен")
    
    def _maybe_cleanup(self):
        """Проверяет необходимость очистки и выполняет её"""
        now = datetime.now()
        
        # Очистка по размеру
        if len(self._cache) > self.max_size:
            self._cleanup_by_size()
        
        # Очистка по времени
        if (now - self._last_cleanup).total_seconds() > self.cleanup_interval:
            self._cleanup_by_age()
            self._last_cleanup = now
    
    def _cleanup_by_size(self):
        """Удаляет самые старые записи при превышении лимита размера"""
        with self._lock:
            evicted = 0
            while len(self._cache) > self.max_size:
                # Удаляем самую старую запись (первый элемент OrderedDict)
                oldest_key, oldest_value = self._cache.popitem(last=False)
                evicted += 1
                logger.debug(f"Удалена старая запись (по размеру): {oldest_key}")
            
            self._stats['evictions'] += evicted
            if evicted > 0:
                logger.info(f"🧹 Очистка по размеру: удалено {evicted} записей")
    
    def _cleanup_by_age(self):
        """Удаляет записи старше max_age"""
        with self._lock:
            now = datetime.now()
            expired_keys = []
            
            for key, value in self._cache.items():
                last_seen = value.get('last_seen', value.get('_last_accessed', now))
                if now - last_seen > self.max_age:
                    expired_keys.append(key)
            
            for key in expired_keys:
                del self._cache[key]
            
            self._stats['age_cleanups'] += len(expired_keys)
            if expired_keys:
                logger.info(f"🧹 Очистка по возрасту: удалено {len(expired_keys)} записей")
    
    def get_stats(self):
        """
        Возвращает подробную статистику кэша
        """
        with self._lock:
            now = datetime.now()
            active_count = 0
            total_age = timedelta()
            ages = []
            
            for value in self._cache.values():
                if value.get('is_active', False):
                    active_count += 1
                
                last_seen = value.get('last_seen', value.get('_last_accessed', now))
                age = now - last_seen
                ages.append(age.total_seconds())
                total_age += age
            
            avg_age = total_age.total_seconds() / len(self._cache) if self._cache else 0
            hit_rate = (self._stats['hits'] / (self._stats['hits'] + self._stats['misses']) * 100 
                       if (self._stats['hits'] + self._stats['misses']) > 0 else 0)
            
            return {
                'size': len(self._cache),
                'max_size': self.max_size,
                'usage_percent': (len(self._cache) / self.max_size * 100) if self.max_size > 0 else 0,
                'active_records': active_count,
                'inactive_records': len(self._cache) - active_count,
                'avg_age_seconds': avg_age,
                'avg_age_minutes': avg_age / 60,
                'avg_age_hours': avg_age / 3600,
                'oldest_age_seconds': max(ages) if ages else 0,
                'newest_age_seconds': min(ages) if ages else 0,
                'stats': {
                    'hits': self._stats['hits'],
                    'misses': self._stats['misses'],
                    'hit_rate': hit_rate,
                    'evictions': self._stats['evictions'],
                    'age_cleanups': self._stats['age_cleanups']
                }
            }
    

# Создаем глобальный экземпляр с настройками
# Можно настроить под свои нужды
client_traffic_history = LRUTrafficHistory(
    max_size=10000,        # Максимум 10000 записей
    max_age_hours=24,      # Хранить не больше 24 часов
    cleanup_interval=3600  # Проверять каждые 3600 секунд (1 час)
)
