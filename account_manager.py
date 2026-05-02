import discord
import asyncio
import random
import logging
from datetime import datetime

from database import DatabaseManager

# ڕێکخستنی Logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('AccountManager')

class ManagedAccount(discord.Client):
    """
    نوێنەرایەتی ئەکاونتێکی بەکارهێنەری دیسکۆرد دەکات کە لەلایەن بۆتەکەوە بەڕێوە دەبرێت.
    هەر ManagedAccountێک دیسکۆرد Clientـێکی تایبەت بە خۆی هەیە.
    """
    def __init__(self, token: str, bot_instance, db_manager: DatabaseManager):
        # Intents بۆ ئەکاونتەکانی بەکارهێنەر (پێویستی بە Intents کەمترە لە بۆتە فەرمییەکان)
        intents = discord.Intents.none() # دەستپێک بە Intentsـی سفر
        intents.guilds = True # بۆ بینین و پەیوەندیکردن بە سێرڤەرەکان
        intents.members = False # پێویست نییە ئەگەر تەنها بۆ جوڵەی سادە بێت
        intents.presences = False # بۆ ناردنی پرێزنس، وەرگرتنی پێویست نییە

        super().__init__(intents=intents)
        self.token = token
        self.db_manager = db_manager
        self.bot_instance = bot_instance # ئاماژە بە بۆتە سەرەکییەکە
        self.is_running = False # ئایا clientـەکە کار دەکات
        self.is_ready = False   # ئایا clientـەکە پەیوەندی بە دیسکۆردەوە کردووە و ئامادەیە
        self.user_id = None     # IDـی بەکارهێنەرەکە، لە کاتی on_ready دادەنرێت
        
        # ئەمە تەنها ئاڵایەکە بۆ چالاککردنی emulation.
        # بارودۆخی مۆبایلی ڕاستەقینە بۆ self-botting لە discord.pyـدا زۆر ئاڵۆزە و مەترسیدارە.
        self.mobile_status_emulation_active = True 

    async def on_ready(self):
        """کاتێک ئەکاونتی بەکارهێنەرەکە پەیوەندی بە دیسکۆردەوە دەکات و ئامادە دەبێت."""
        self.user_id = self.user.id
        self.is_ready = True
        self.is_running = True
        logger.info(f"User account {self.user.name} ({self.user.id}) is online!")
        await self.db_manager.update_account_status(self.token, 'online')
        
        # دانانی بارودۆخی مۆبایل (emulation بە Activityـی Custom)
        # تێبینی: clientـی discord.py بۆ ئەکاونتەکانی بەکارهێنەر بە گشتی زانیاری Clientـی دیسکتاپ بەکار دەهێنێت.
        # بارودۆخی مۆبایلی ڕاستەقینە پێویستی بە manipulationـی قوڵی websocket هەیە کە بە ئاسانی لێرەدا ناکرێت.
        # ئەمە Custom Statusـێک دادەنێت کە ئاماژە بە 'Mobile' دەکات.
        if self.mobile_status_emulation_active:
            mobile_activity = discord.CustomActivity(name="Mobile Status Emulation", emoji_name="📱")
            try:
                await self.change_presence(status=discord.Status.online, activity=mobile_activity)
                logger.info(f"Set custom 'Mobile Status' for {self.user.name}")
            except discord.HTTPException as e:
                logger.warning(f"Could not set custom mobile presence for {self.user.name}: {e}")
        else:
            try:
                await self.change_presence(status=discord.Status.online)
            except discord.HTTPException as e:
                logger.warning(f"Could not set online presence for {self.user.name}: {e}")

    async def on_connect(self):
        """کاتێک ئەکاونتی بەکارهێنەرەکە دەست بە پەیوەندیکردن دەکات."""
        logger.info(f"User account for token {self.token[:10]}... is connecting...")
        await self.db_manager.update_account_status(self.token, 'connecting')

    async def on_disconnect(self):
        """کاتێک ئەکاونتی بەکارهێنەرەکە دەپچڕێت."""
        self.is_ready = False
        self.is_running = False
        user_info = f"{self.user.name} ({self.user.id})" if self.user else f"token {self.token[:10]}..."
        logger.warning(f"User account {user_info} disconnected!")
        await self.db_manager.update_account_status(self.token, 'offline')

    async def on_resumed(self):
        """کاتێک ئەکاونتی بەکارهێنەرەکە پەیوەندییەکەی دەستپێدەکاتەوە."""
        self.is_ready = True
        self.is_running = True
        user_info = f"{self.user.name} ({self.user.id})" if self.user else f"token {self.token[:10]}..."
        logger.info(f"User account {user_info} resumed!")
        await self.db_manager.update_account_status(self.token, 'online')

    async def start(self):
        """دەستپێکردنی clientـی بەکارهێنەر."""
        if self.is_running:
            user_info = f"{self.user.name} ({self.user.id})" if self.user else f"token {self.token[:10]}..."
            logger.info(f"Account {user_info} is already running.")
            return

        try:
            # clientـەکە لە taskـێکی جیاوازدا کارا دەکەین بۆ ئەوەی main event loop بلۆک نەکات.
            self.loop.create_task(self.run(self.token, reconnect=True)) # دڵنیابە لەوەی reconnect چالاکە
            logger.info(f"Attempting to start user client for token {self.token[:10]}...")
            # is_running دەبێت لە on_ready بگۆڕدرێت بۆ true, بەڵام لێرەش دادەنرێت بۆ ئەوەی ڕاستەوخۆ دیار بێت
            self.is_running = True 
        except Exception as e:
            logger.error(f"Error starting user client for token {self.token[:10]}...: {e}")
            await self.db_manager.update_account_status(self.token, 'error')
            self.is_running = False

    async def stop(self):
        """ڕاگرتنی clientـی بەکارهێنەر."""
        if not self.is_running:
            user_info = f"{self.user.name} ({self.user.id})" if self.user else f"token {self.token[:10]}..."
            logger.info(f"Account {user_info} is already stopped.")
            return

        try:
            await self.logout()
            user_info = f"{self.user.name} ({self.user.id})" if self.user else f"token {self.token[:10]}..."
            logger.info(f"User client for {user_info} stopped.")
            await self.db_manager.update_account_status(self.token, 'offline')
            self.is_running = False
            self.is_ready = False
        except Exception as e:
            user_info = f"{self.user.name} ({self.user.id})" if self.user else f"token {self.token[:10]}..."
            logger.error(f"Error stopping user client for {user_info}: {e}")
            await self.db_manager.update_account_status(self.token, 'error')
            
    async def join_guild(self, invite_code: str):
        """هەوڵ دەدات بچێتە ناو سێرڤەرێک بە کۆدی بانگێشتکردنەکە."""
        if not self.is_ready:
            user_info = f"{self.user.name}" if self.user else f"token {self.token[:10]}..."
            logger.warning(f"Account {user_info} is not ready to join guild {invite_code}.")
            return False

        try:
            # گۆڕینی لینکی بانگێشت بۆ Invite object
            invite = await self.fetch_invite(invite_code)
            # چوونە ژوورەوەی ئەکاونتی بەکارهێنەرەکە بۆ سێرڤەرەکە
            guild = await invite.accept()
            logger.info(f"Account {self.user.name} ({self.user.id}) successfully joined guild '{guild.name}' ({guild.id}) via invite {invite_code}.")
            await self.db_manager.update_account_status(self.token, 'online', current_guild_id=guild.id)
            return True
        except discord.errors.NotFound:
            logger.warning(f"Invite '{invite_code}' for account {self.user.name} not found or expired.")
        except discord.errors.Forbidden:
            logger.warning(f"Account {self.user.name} is forbidden from joining guild with invite '{invite_code}'. (E.g., Banned, captcha, already in max guilds)")
        except discord.HTTPException as e:
            logger.error(f"HTTP error joining guild with invite '{invite_code}' for account {self.user.name}: {e}")
        except Exception as e:
            logger.error(f"An unexpected error occurred while joining guild with invite '{invite_code}' for account {self.user.name}: {e}")
        return False


class AccountManager:
    """
    بەرپرسە لە بەڕێوەبردنی کۆمەڵێک ئەکاونتی بەکارهێنەر (ManagedAccount).
    لۆجیکی بارکردن، زیادکردن، سڕینەوە، و دەستپێکردنی کارەکانیان دەگرێتەوە.
    """
    def __init__(self, bot_instance, db_manager: DatabaseManager):
        self.bot_instance = bot_instance
        self.db_manager = db_manager
        self.managed_accounts = {} # {token: ManagedAccount_instance}
        self.join_guild_task = None
        self.join_interval_seconds = 30 # داواکاریی بەکارهێنەر: هەر 30 چرکە جارێک ئەکاونتێک جۆین بکات

    async def load_accounts(self):
        """هەموو ئەکاونتەکان لە داتابەیسەکە بار دەکات و دەست بە کارپێکردنیان دەکات."""
        accounts_data = await self.db_manager.get_all_accounts()
        if not accounts_data:
            logger.info("No accounts found in the database to load.")
            return

        tasks = []
        for acc_data in accounts_data:
            token = acc_data['token']
            if token not in self.managed_accounts:
                account_client = ManagedAccount(token, self.bot_instance, self.db_manager)
                self.managed_accounts[token] = account_client
                tasks.append(account_client.start()) # دەستپێکردنی هەر clientێک وەک taskێک
            else:
                logger.info(f"Account {token[:10]}... already loaded.")
        
        if tasks:
            # هەموو tasksـەکان بە شێوەیەکی هاوکات جێبەجێ دەکات
            await asyncio.gather(*tasks, return_exceptions=True) 
            logger.info(f"Attempted to start {len(tasks)} user accounts from database.")
        else:
            logger.info("All accounts already loaded and potentially running.")

    async def add_account(self, token: str):
        """ئەکاونتێکی نوێ زیاد دەکات، لە داتابەیسدا هەڵیدەگرێت، و دەستی پێدەکات."""
        if token in self.managed_accounts:
            return False, "ئەم ئەکاونتە پێشتر بەڕێوە دەبرێت."
        
        # هەوڵدەدات ئەکاونتەکە لە داتابەیسدا هەڵبگرێت
        success = await self.db_manager.add_account(token)
        if success:
            account_client = ManagedAccount(token, self.bot_instance, self.db_manager)
            self.managed_accounts[token] = account_client
            await account_client.start() # دەستپێکردنی clientـی نوێ
            return True, f"ئەکاونت {token[:10]}... بە سەرکەوتوویی زیاد کرا و دەستی پێکرا."
        else:
            return False, "شکستی هێنا لە زیادکردنی ئەکاونت بۆ داتابەیس (لەوانەیە تۆکنەکە پێشتر هەبووبێت)."

    async def remove_account(self, token: str):
        """ئەکاونتێک ڕادەگرێت، لە بەڕێوەبردن لای دەبات، و لە داتابەیس دەیسڕێتەوە."""
        if token not in self.managed_accounts:
            return False, "ئەکاونتەکە لە لیستی ئەکاونتە بەڕێوەبراوەکاندا نەدۆزرایەوە."
        
        account_client = self.managed_accounts[token]
        await account_client.stop() # ڕاگرتنی clientـی ئەکاونتەکە
        del self.managed_accounts[token] # سڕینەوەی لە لیستی بەڕێوەبراوەکان
        
        success = await self.db_manager.delete_account(token) # سڕینەوەی لە داتابەیس
        if success:
            return True, f"ئەکاونت {token[:10]}... سڕایەوە و ڕاگیرا."
        else:
            return False, "شکستی هێنا لە سڕینەوەی ئەکاونت لە داتابەیسدا."

    async def start_all_accounts(self):
        """هەموو ئەکاونتە بەڕێوەبراوەکان دەستپێدەکات."""
        tasks = []
        for token, account_client in self.managed_accounts.items():
            tasks.append(account_client.start())
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
            logger.info(f"Attempted to start all {len(tasks)} managed user accounts.")
            return True, "هەموو ئەکاونتە بەڕێوەبراوەکان دەست بەکاربوون."
        return False, "هیچ ئەکاونتێک نییە بۆ دەستپێکردن."

    async def stop_all_accounts(self):
        """هەموو ئەکاونتە بەڕێوەبراوەکان ڕادەگرێت."""
        tasks = []
        for token, account_client in self.managed_accounts.items():
            tasks.append(account_client.stop())
        
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
            logger.info(f"Attempted to stop all {len(tasks)} managed user accounts.")
            return True, "هەموو ئەکاونتە بەڕێوەبراوەکان ڕاگیران."
        return False, "هیچ ئەکاونتێک نییە بۆ ڕاگرتن."

    async def _join_guild_loop(self):
        """
        لۆپێکی بەردەوام کە هەر 30 چرکە جارێک هەوڵ دەدات ئەکاونتێکی چالاک بچێتە ناو سێرڤەرێکی هەڕەمەکی.
        """
        while True:
            await asyncio.sleep(self.join_interval_seconds) # چاوەڕێ 30 چرکە
            
            active_accounts = [acc for acc in self.managed_accounts.values() if acc.is_ready]
            if not active_accounts:
                logger.debug("هیچ ئەکاونتێکی چالاک نییە بۆ چوونە ژوورەوەی سێرڤەرەکان.")
                continue

            guild_invites = await self.db_manager.get_all_guild_invites()
            if not guild_invites:
                logger.debug("هیچ لینکی بانگێشتکردنی سێرڤەرێک لە داتابەیسدا نەدۆزرایەوە.")
                continue

            random_account = random.choice(active_accounts) # ئەکاونتێکی هەڕەمەکی هەڵدەبژێرێت
            random_invite_data = random.choice(guild_invites) # لینکی بانگێشتکردنێکی هەڕەمەکی هەڵدەبژێرێت
            invite_code = random_invite_data['invite_code']

            user_info = f"{random_account.user.name}" if random_account.user else f"token {random_account.token[:10]}..."
            logger.info(f"Attempting for account {user_info} to join guild with invite {invite_code}...")
            await random_account.join_guild(invite_code)

    def start_join_guild_task(self):
        """Taskـی چوونە ژوورەوەی سێرڤەری خولیی دەستپێدەکات."""
        if self.join_guild_task is None or self.join_guild_task.done():
            logger.info("Starting periodic guild joining task.")
            self.join_guild_task = self.bot_instance.loop.create_task(self._join_guild_loop())
        else:
            logger.info("Periodic guild joining task is already running.")

    def stop_join_guild_task(self):
        """Taskـی چوونە ژوورەوەی سێرڤەری خولیی ڕادەگرێت."""
        if self.join_guild_task and not self.join_guild_task.done():
            self.join_guild_task.cancel()
            logger.info("Periodic guild joining task cancelled.")
            self.join_guild_task = None
        else:
            logger.info("Periodic guild joining task is not running or already stopped.")
