import sqlite3
import os
from datetime import datetime
from typing import Optional, List, Dict, Tuple


class Database:
    def __init__(self, db_path: str = None):
        # Используем путь из переменной окружения или значение по умолчанию
        import os
        self.db_path = db_path or os.getenv("DB_PATH", "travel_wallet.db")
        # Создаем директорию для базы данных, если её нет
        db_dir = os.path.dirname(self.db_path)
        if db_dir and not os.path.exists(db_dir):
            os.makedirs(db_dir, exist_ok=True)
        self.init_database()
    
    def get_connection(self):
        """Создает соединение с базой данных"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        return conn
    
    def init_database(self):
        """Инициализирует таблицы базы данных"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        # Таблица путешествий
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS trips (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id INTEGER NOT NULL,
                from_country TEXT NOT NULL,
                to_country TEXT NOT NULL,
                from_currency TEXT NOT NULL,
                to_currency TEXT NOT NULL,
                rate REAL NOT NULL,
                balance_from REAL NOT NULL DEFAULT 0,
                balance_to REAL NOT NULL DEFAULT 0,
                is_active INTEGER NOT NULL DEFAULT 0,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                UNIQUE(user_id, from_country, to_country)
            )
        """)
        
        # Таблица расходов
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS expenses (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                trip_id INTEGER NOT NULL,
                amount_from REAL NOT NULL,
                amount_to REAL NOT NULL,
                timestamp TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                description TEXT,
                FOREIGN KEY (trip_id) REFERENCES trips(id) ON DELETE CASCADE
            )
        """)
        
        # Таблица состояний пользователей (для FSM)
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_states (
                user_id INTEGER PRIMARY KEY,
                state TEXT,
                data TEXT
            )
        """)
        
        # Таблица для хранения message_id главного меню
        cursor.execute("""
            CREATE TABLE IF NOT EXISTS user_menu_messages (
                user_id INTEGER PRIMARY KEY,
                message_id INTEGER NOT NULL
            )
        """)
        
        conn.commit()
        conn.close()
    
    def create_trip(self, user_id: int, from_country: str, to_country: str,
                   from_currency: str, to_currency: str, rate: float,
                   initial_amount: float) -> Optional[int]:
        """Создает новое путешествие"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # Деактивируем все другие путешествия пользователя
            cursor.execute("""
                UPDATE trips SET is_active = 0 WHERE user_id = ?
            """, (user_id,))
            
            # Конвертируем начальную сумму
            # rate - это сколько to_currency за 1 from_currency
            balance_to = initial_amount * rate
            
            # Создаем новое путешествие
            cursor.execute("""
                INSERT INTO trips (user_id, from_country, to_country, 
                                 from_currency, to_currency, rate, 
                                 balance_from, balance_to, is_active)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, 1)
            """, (user_id, from_country, to_country, from_currency, 
                  to_currency, rate, initial_amount, balance_to))
            
            trip_id = cursor.lastrowid
            conn.commit()
            return trip_id
        except sqlite3.IntegrityError:
            return None
        finally:
            conn.close()
    
    def get_active_trip(self, user_id: int) -> Optional[Dict]:
        """Получает активное путешествие пользователя"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM trips WHERE user_id = ? AND is_active = 1
        """, (user_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return dict(row)
        return None
    
    def get_user_trips(self, user_id: int) -> List[Dict]:
        """Получает все путешествия пользователя"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM trips WHERE user_id = ? ORDER BY created_at DESC
        """, (user_id,))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def switch_trip(self, user_id: int, trip_id: int) -> bool:
        """Переключает активное путешествие"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # Деактивируем все путешествия пользователя
            cursor.execute("""
                UPDATE trips SET is_active = 0 WHERE user_id = ?
            """, (user_id,))
            
            # Активируем выбранное
            cursor.execute("""
                UPDATE trips SET is_active = 1 WHERE id = ? AND user_id = ?
            """, (trip_id, user_id))
            
            conn.commit()
            return cursor.rowcount > 0
        finally:
            conn.close()
    
    def add_expense(self, trip_id: int, amount_to: float, amount_from: float,
                   description: Optional[str] = None) -> bool:
        """Добавляет расход к путешествию"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            
            # Добавляем запись о расходе
            cursor.execute("""
                INSERT INTO expenses (trip_id, amount_from, amount_to, description)
                VALUES (?, ?, ?, ?)
            """, (trip_id, amount_from, amount_to, description))
            
            # Обновляем баланс путешествия
            cursor.execute("""
                UPDATE trips 
                SET balance_from = balance_from - ?, 
                    balance_to = balance_to - ?
                WHERE id = ?
            """, (amount_from, amount_to, trip_id))
            
            conn.commit()
            
            
            return True
        except Exception as e:
            print(f"Ошибка при добавлении расхода: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            conn.close()
    
    def update_trip_rate(self, trip_id: int, new_rate: float) -> bool:
        """Обновляет курс обмена для путешествия"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # Получаем текущий баланс в валюте назначения
            cursor.execute("SELECT balance_to FROM trips WHERE id = ?", (trip_id,))
            row = cursor.fetchone()
            
            if row:
                balance_to = row[0]
                # Пересчитываем баланс в домашней валюте
                balance_from = balance_to / new_rate
                
                cursor.execute("""
                    UPDATE trips 
                    SET rate = ?, balance_from = ?
                    WHERE id = ?
                """, (new_rate, balance_from, trip_id))
                
                conn.commit()
                return True
            return False
        finally:
            conn.close()
    
    def get_expenses(self, trip_id: int, limit: int = 10) -> List[Dict]:
        """Получает историю расходов для путешествия"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM expenses 
            WHERE trip_id = ? 
            ORDER BY timestamp DESC 
            LIMIT ?
        """, (trip_id, limit))
        
        rows = cursor.fetchall()
        conn.close()
        
        return [dict(row) for row in rows]
    
    def set_user_state(self, user_id: int, state: Optional[str], data: Optional[str] = None):
        """Устанавливает состояние пользователя для FSM"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        if state is None:
            cursor.execute("DELETE FROM user_states WHERE user_id = ?", (user_id,))
        else:
            cursor.execute("""
                INSERT OR REPLACE INTO user_states (user_id, state, data)
                VALUES (?, ?, ?)
            """, (user_id, state, data))
        
        conn.commit()
        conn.close()
    
    def get_user_state(self, user_id: int) -> Optional[Tuple[str, Optional[str]]]:
        """Получает состояние пользователя"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT state, data FROM user_states WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return (row[0], row[1])
        return None
    
    def delete_trip(self, user_id: int, trip_id: int) -> bool:
        """Удаляет путешествие пользователя"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        try:
            # Проверяем, что путешествие принадлежит пользователю
            cursor.execute("SELECT id FROM trips WHERE id = ? AND user_id = ?", (trip_id, user_id))
            if not cursor.fetchone():
                return False
            
            # Удаляем путешествие (расходы удалятся автоматически из-за CASCADE)
            cursor.execute("DELETE FROM trips WHERE id = ? AND user_id = ?", (trip_id, user_id))
            
            conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            print(f"Ошибка при удалении путешествия: {e}")
            return False
        finally:
            conn.close()
    
    def get_trip_by_id(self, user_id: int, trip_id: int) -> Optional[Dict]:
        """Получает путешествие по ID"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT * FROM trips WHERE id = ? AND user_id = ?
        """, (trip_id, user_id))
        
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return dict(row)
        return None
    
    def save_menu_message_id(self, user_id: int, message_id: int):
        """Сохраняет message_id главного меню пользователя"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            INSERT OR REPLACE INTO user_menu_messages (user_id, message_id)
            VALUES (?, ?)
        """, (user_id, message_id))
        
        conn.commit()
        conn.close()
    
    def get_menu_message_id(self, user_id: int) -> Optional[int]:
        """Получает message_id главного меню пользователя"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("SELECT message_id FROM user_menu_messages WHERE user_id = ?", (user_id,))
        row = cursor.fetchone()
        conn.close()
        
        if row:
            return row[0]
        return None
    
    def get_total_expenses(self, trip_id: int) -> tuple[float, float]:
        """Получает общую сумму расходов для путешествия"""
        conn = self.get_connection()
        cursor = conn.cursor()
        
        cursor.execute("""
            SELECT COALESCE(SUM(amount_from), 0), COALESCE(SUM(amount_to), 0)
            FROM expenses WHERE trip_id = ?
        """, (trip_id,))
        
        row = cursor.fetchone()
        conn.close()
        
        return (float(row[0]), float(row[1])) if row else (0.0, 0.0)
