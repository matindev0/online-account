import sqlite3
import asyncio
import logging
from datetime import datetime

# ڕێکخستنی Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('DatabaseManager')

class DatabaseManager:
    def __init__(self, db_path='database.db'):
        self.db_path = db_path
        self._initialize_db()

    def _initialize_db(self):
        """
        داتابەیسەکە دروست دەکات و خشتەکان (tables) پێکدەهێنێت ئەگەر نەبوون.
        ئەمە لە کاتی دەستپێکردندا ڕوودەدات.
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row # ڕێگە دەدات بە ستوونەکان بە ناوی خۆیانەوە دەستڕاگەیشتن
        try:
            cursor = conn.cursor()
            # خشتەی ئەکاونتەکان: تۆکن، بارودۆخ، دوایین چالاکی، IDـی سێرڤەری ئێستا
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS accounts (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    token TEXT UNIQUE NOT NULL,
                    status TEXT DEFAULT 'offline',
                    last_activity TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                    current_guild_id INTEGER NULL
                )
            """)
            # خشتەی سێرڤەرەکان: IDـی سێرڤەر، ناو، کۆدی بانگێشت
            cursor.execute("""
                CREATE TABLE IF NOT EXISTS guilds (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    guild_id INTEGER UNIQUE NOT NULL,
                    name TEXT NOT NULL,
                    invite_code TEXT UNIQUE NOT NULL
                )
            """)
            conn.commit()
            logger.info("Database initialized successfully at %s.", self.db_path)
        except sqlite3.Error as e:
            logger.error(f"Error initializing database: {e}")
        finally:
            conn.close()

    async def _execute_query(self, query, params=(), fetchone=False, fetchall=False):
        """
        کاتی پرسیارەکانی SQL بە شێوەیەکی ناهاوکات (asynchronously) جێبەجێ دەکات.
        بۆ هەر کارێک پەیوەندییەکی نوێ بە داتابەیسەوە دەکات بۆ دڵنیابوون لە سەلامەتی.
        """
        conn = sqlite3.connect(self.db_path) # پەیوەندییەکی نوێ بۆ هەر کردارێکی ناهاوکات
        conn.row_factory = sqlite3.Row
        try:
            cursor = conn.cursor()
            # کرداری بلۆککەری داتابەیس لە سڕێدێکی جیاوازدا جێبەجێ دەکات
            await asyncio.to_thread(cursor.execute, query, params) 
            if fetchone:
                result = await asyncio.to_thread(cursor.fetchone)
                return dict(result) if result else None
            elif fetchall:
                result = await asyncio.to_thread(cursor.fetchall)
                return [dict(row) for row in result]
            else:
                await asyncio.to_thread(conn.commit)
                return True
        except sqlite3.IntegrityError as e:
            logger.warning(f"Integrity error (e.g., duplicate entry) executing query '{query}' with params {params}: {e}")
            return False # Return False for specific integrity errors
        except sqlite3.Error as e:
            logger.error(f"Database error executing query '{query}' with params {params}: {e}")
            return False
        finally:
            conn.close()

    async def add_account(self, token: str):
        """ئەکاونتێکی نوێ زیاد دەکات بۆ داتابەیسەکە."""
        query = "INSERT INTO accounts (token) VALUES (?)"
        return await self._execute_query(query, (token,))

    async def get_account(self, token: str):
        """ئەکاونتێک بە تۆکنەکەی دەهێنێتەوە."""
        query = "SELECT * FROM accounts WHERE token = ?"
        return await self._execute_query(query, (token,), fetchone=True)

    async def get_all_accounts(self):
        """هەموو ئەکاونتەکان لە داتابەیسەکە دەهێنێتەوە."""
        query = "SELECT * FROM accounts"
        return await self._execute_query(query, fetchall=True)

    async def update_account_status(self, token: str, status: str, current_guild_id: int = None):
        """
        بارودۆخی ئەکاونتێک و دوایین چالاکییەکەی نوێ دەکاتەوە.
        ئەگەر current_guild_id هەبوو، ئەوەش نوێ دەکاتەوە.
        """
        current_time = datetime.now().isoformat()
        if current_guild_id is not None:
            query = "UPDATE accounts SET status = ?, last_activity = ?, current_guild_id = ? WHERE token = ?"
            params = (status, current_time, current_guild_id, token)
        else:
            query = "UPDATE accounts SET status = ?, last_activity = ? WHERE token = ?"
            params = (status, current_time, token)
        return await self._execute_query(query, params)

    async def delete_account(self, token: str):
        """ئەکاونتێک لە داتابەیسەکە دەسڕێتەوە."""
        query = "DELETE FROM accounts WHERE token = ?"
        return await self._execute_query(query, (token,))

    async def add_guild(self, guild_id: int, name: str, invite_code: str):
        """لینکی بانگێشتکردنی سێرڤەرێک زیاد دەکات بۆ داتابەیسەکە."""
        query = "INSERT INTO guilds (guild_id, name, invite_code) VALUES (?, ?, ?)"
        return await self._execute_query(query, (guild_id, name, invite_code))

    async def get_all_guild_invites(self):
        """هەموو لینکە بانگێشتکراوەکانی سێرڤەر لە داتابەیسەکە دەهێنێتەوە."""
        query = "SELECT * FROM guilds"
        return await self._execute_query(query, fetchall=True)

    async def delete_guild(self, invite_code: str):
        """لینکی بانگێشتکردنی سێرڤەرێک لە داتابەیسەکە دەسڕێتەوە."""
        query = "DELETE FROM guilds WHERE invite_code = ?"
        return await self._execute_query(query, (invite_code,))

    async def get_random_guild_invite(self):
        """لینکی بانگێشتکردنی سێرڤەرێکی هەڕەمەکی دەهێنێتەوە."""
        query = "SELECT * FROM guilds ORDER BY RANDOM() LIMIT 1"
        return await self._execute_query(query, fetchone=True)
