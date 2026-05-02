import discord
from discord.commands import slash_command, Option
import json
import asyncio
import os
import logging
import sys

# --- 1. ڕێکخستنی Logging (بۆ تۆمارکردنی ڕووداوەکان) ---
# ئەمە یارمەتیت دەدات بۆ تێگەیشتن لەوەی بۆتەکە چی دەکات و کاتێک کێشەیەک ڕوو دەدات
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
                    handlers=[logging.FileHandler("bot.log", encoding='utf-8'), logging.StreamHandler(sys.stdout)])
logger = logging.getLogger('SovereignArchitect')

# --- 2. لۆدکردنی تۆکنی بۆتەکە ---
try:
    from config import BOT_TOKEN
except ImportError:
    logger.warning("config.py not found. Trying to load BOT_TOKEN from environment variables.")
    BOT_TOKEN = os.environ.get("BOT_TOKEN")
    if not BOT_TOKEN:
        logger.error("ERROR: BOT_TOKEN not found in config.py or environment variables. Exiting.")
        sys.exit(1) # داوای لێبووردن دەکەم مەتین گیان، بەڵام بێ تۆکن بۆتەکە ناتوانێت کار بکات.

# --- 3. ڕێکخستنە گشتییەکان ---
DATABASE_FILE = 'database.json'
db_data = {"accounts": [], "servers": []} # داتای سەرەکی، لە بیرگەدا
active_user_clients = {} # {account_id: UserClientInstance} - بۆ ئەکاونتە چالاکەکان
active_user_tasks = {}   # {account_id: asyncio.Task} - بۆ پڕۆسەی asynchronousی ئەکاونتەکان

# --- 4. فەنکشنەکانی داتابەیس (خوێندنەوە و نووسین) ---
def load_database():
    global db_data
    if not os.path.exists(DATABASE_FILE):
        logger.warning(f"Database file '{DATABASE_FILE}' not found. Creating an empty one.")
        save_database() # گەر فایلەکە نەبوو، دروستی دەکەین
    try:
        with open(DATABASE_FILE, 'r', encoding='utf-8') as f:
            db_data = json.load(f)
        logger.info("Database loaded successfully.")
    except json.JSONDecodeError as e:
        logger.error(f"Error decoding JSON from database file. It might be corrupted: {e}")
        # گەر داتابەیسەکە تێکچوو بوو، بە پۆش نایخوێنینەوە
        db_data = {"accounts": [], "servers": []}
        save_database() # ڕەنگە باشتر بێت سفر بکرێتەوە
    except Exception as e:
        logger.error(f"An unexpected error occurred while loading the database: {e}")

def save_database():
    try:
        with open(DATABASE_FILE, 'w', encoding='utf-8') as f:
            json.dump(db_data, f, indent=2, ensure_ascii=False)
        logger.info("Database saved successfully.")
    except Exception as e:
        logger.error(f"An error occurred while saving the database: {e}")

# --- 5. کڵاسی UserClient (بۆ بەڕێوەبردنی هەر ئەکاونتێک) ---
class UserClient(discord.Client):
    def __init__(self, token, account_id, username, *args, **kwargs):
        # Intents بۆ کڵاینتی بەکارهێنەر
        # بە شێوەیەکی گشتی، UserClient هەموو Intents ی هەیە، بەڵام بۆ دڵنیایی
        user_intents = discord.Intents.all() # هەموو ئینتێنتەکان چالاک دەکەین
        super().__init__(intents=user_intents, *args, **kwargs)
        self.token = token
        self.account_id = str(account_id)
        self.username = username
        self.task = None # ئەمە تاسکی asynchronousـی ئەم کڵاینتە دەگرێت
        logger.info(f"Initialized UserClient for {self.username} ({self.account_id})")

    async def on_ready(self):
        logger.info(f"UserClient for {self.username} ({self.account_id}) is online!")
        try:
            # ستاتسی مۆبایل دادەنێین وەک داواکارییەکەی تۆ مەتین گیان
            await self.change_presence(status=discord.Status.online, activity=None, mobile_status=True)
            logger.info(f"Set mobile status for {self.username}.")
        except Exception as e:
            logger.error(f"Failed to set mobile status for {self.username}: {e}")

    async def start_client(self):
        # ئەم فەنکشنە کڵاینتەکە وەک تاسکێک asynchronous دەخاتە کار
        self.task = asyncio.create_task(self.start(self.token))
        logger.info(f"Created and started client task for {self.username}.")
        return self.task

    async def stop_client(self):
        if self.task and not self.task.done():
            self.task.cancel() # تاسکەکە ڕادەگرین
            logger.info(f"Cancelled task for {self.username}.")
        
        # دڵنیایی دەدەین کە پەیوەندییەکە بە باشی دادەخرێت
        if not self.is_closed():
            try:
                await self.close() 
                logger.info(f"Closed Discord connection for {self.username}.")
            except Exception as e:
                logger.error(f"Error gracefully closing user client {self.username}: {e}")
        logger.info(f"Fully stopped client for {self.username} ({self.account_id}).")


# --- 6. ئینیشیالایزکردنی بۆتی سەرەکی ---
# Intents پێویستن بۆ بۆتەکە. Intents.default() زۆربەی پێویستییەکان دابین دەکات.
bot = discord.Bot(intents=discord.Intents.default())

# --- 7. ڕووداوی on_ready بۆ بۆتی سەرەکی ---
@bot.event
async def on_ready():
    logger.info(f"Bot '{bot.user}' (ID: {bot.user.id}) is online!")
    load_database() # داتابەیس لۆد دەکەین لە کاتی کارکردنی بۆتەکە

    # هەوڵدەدەین هەموو ئەکاونتە پاشەکەوتکراوەکان (لە داتابەیسدا) دووبارە دەستپێبکەینەوە
    logger.info("Attempting to restart previously added user clients...")
    for account_data in db_data["accounts"]:
        # گەر ئەکاونتەکە پێشتر چالاک بوو (لە کاتی دووبارە لۆدکردندا)، دووبارە دەستی پێنەکەینەوە
        if account_data["id"] in active_user_clients:
            logger.info(f"Account {account_data['username']} ({account_data['id']}) is already active, skipping restart.")
            continue

        try:
            user_client = UserClient(account_data["token"], account_data["id"], account_data["username"])
            active_user_clients[account_data["id"]] = user_client
            task = await user_client.start_client()
            active_user_tasks[account_data["id"]] = task
            logger.info(f"Successfully started UserClient for {account_data['username']} ({account_data['id']}).")
        except Exception as e:
            logger.error(f"Failed to restart UserClient for {account_data['username']} ({account_data['id']}): {e}", exc_info=True)
            # دەتوانین لێرە هەڵیبگرین وەک 'offline' لە داتابەیسدا گەر بەردەوام فەیل بوو.

    logger.info("All stored user clients restart attempts completed.")

# --- 8. کۆماندەکانی سلاش ---

@bot.slash_command(name="add_account", description="زیادکردنی ئەکاونتێکی نوێی دیسکۆرد بە بەکارهێنانی تۆکنەکەی.")
async def add_account(ctx, token: Option(str, "تۆکنی بەکارهێنەر بۆ ئەکاونتەکە", required=True)):
    await ctx.defer(ephemeral=True) # وەڵامدانەوەی نهێنی، تەنها بۆ تۆ دەردەکەوێت

    # ١. دڵنیابوونەوە لەوەی تۆکنەکە پێشتر زیاد نەکراوە
    for acc in db_data["accounts"]:
        if acc["token"] == token:
            await ctx.followup.send("ئەم تۆکنە پێشتر زیاد کراوە.")
            return

    # ٢. کڵاینتێکی کاتی بۆ پشکنینی تۆکن و وەرگرتنی زانیاری بەکارهێنەر
    temp_client = discord.Client(user=True)
    account_id = None
    username = None

    try:
        # هەوڵی چوونەژوورەوە و وەرگرتنی زانیاری بەکارهێنەر.
        # کاتێکی دیاریکراو (timeout) دادەنێین بۆ ڕێگریکردن لە وەستاندنێکی زۆر
        await asyncio.wait_for(temp_client.start(token), timeout=15)
        await asyncio.wait_for(temp_client.wait_until_ready(), timeout=5)
        
        account_id = str(temp_client.user.id)
        username = str(temp_client.user)
        logger.info(f"Token validated for {username} ({account_id}).")

    except asyncio.TimeoutError:
        logger.warning(f"Timeout occurred during token validation for a potential account.")
        await ctx.followup.send("پشکنینی تۆکنەکە کاتی زۆری خایاند. ڕەنگە تۆکنەکە هەڵە بێت یان کێشەی پەیوەندیکردن هەبێت.")
        return
    except discord.LoginFailure:
        logger.warning(f"Login failure for a potential account with token: {token[:10]}...")
        await ctx.followup.send("نەتوانرا بە تۆکنەکە بچینە ژوورەوە. تکایە دڵنیابەرەوە کە تۆکنەکە دروستە.")
        return
    except Exception as e:
        logger.error(f"An unexpected error occurred during token validation: {e}", exc_info=True)
        await ctx.followup.send(f"هەڵەیەک ڕوویدا لە کاتی پشکنینی تۆکنەکە: {e}")
        return
    finally:
        # دڵنیایی دەدەین کە کڵاینتی کاتی دادەخرێت
        if not temp_client.is_closed():
            await temp_client.close()

    # ٣. دڵنیابوونەوە لەوەی IDـی بەکارهێنەرەکە پێشتر لە داتابەیسدا نییە
    if account_id in [acc['id'] for acc in db_data["accounts"]]:
        await ctx.followup.send(f"ئەکاونتی `{username}` (ID: `{account_id}`) پێشتر لە داتابەیسدا هەیە.")
        return
    if account_id in active_user_clients:
         await ctx.followup.send(f"ئەکاونتی `{username}` (ID: `{account_id}`) پێشتر چالاکە.")
         return

    # ٤. دروستکردن و دەستپێکردنی UserClient ی بەردەوام
    try:
        user_client = UserClient(token, account_id, username)
        active_user_clients[account_id] = user_client
        task = await user_client.start_client()
        active_user_tasks[account_id] = task

        # ٥. پاشەکەوتکردن لە داتابەیس
        db_data["accounts"].append({
            "id": account_id,
            "username": username,
            "token": token, # تۆکنەکە لێرەدا هەڵدەگیرێت، دەتوانرێت بە شێوەی شیفارشکراو هەڵبگیرێت بۆ ئاسایشی زیاتر
            "joined_servers": []
        })
        save_database()
        await ctx.followup.send(f"ئەکاونتی `{username}` (ID: `{account_id}`) زیاد کرا و ئێستا بە ستاتسی مۆبایل ئۆنلاینە!")
    except Exception as e:
        logger.error(f"Error starting persistent UserClient or saving to DB for {username}: {e}", exc_info=True)
        await ctx.followup.send(f"هەڵەیەک ڕوویدا لە کاتی چالاککردنی ئەکاونتەکە: {e}")


@bot.slash_command(name="remove_account", description="سڕینەوەی ئەکاونتێکی دیسکۆرد بە ئایدییەکەی.")
async def remove_account(ctx, account_id: Option(str, "ئایدی ئەکاونتەکە بۆ سڕینەوە", required=True)):
    await ctx.defer(ephemeral=True)

    found_in_db = False
    original_username = "N/A"
    
    # ١. سڕینەوە لە داتابەیس
    # بە ئایدییەکەی دەیدۆزینەوە و دەیسڕینەوە
    for i, acc in enumerate(db_data["accounts"]):
        if acc["id"] == account_id:
            original_username = acc["username"]
            db_data["accounts"].pop(i)
            found_in_db = True
            break

    if not found_in_db:
        await ctx.followup.send(f"ئەکاونتێک بە ئایدی `{account_id}` لە داتابەیسدا نەدۆزرایەوە.")
        return

    # ٢. وەستاندنی کڵاینتە چالاکەکە گەر هەبێت
    if account_id in active_user_clients:
        user_client = active_user_clients.pop(account_id)
        task = active_user_tasks.pop(account_id, None) 
        
        if task:
            task.cancel() # تاسکی ڕاکردوو ڕادەگرین
        
        try:
            await user_client.close() # دڵنیایی دەدەین کە کڵاینتەکە دادەخرێت بە باشی
            logger.info(f"UserClient {user_client.username} ({account_id}) stopped and closed.")
        except Exception as e:
            logger.error(f"Error gracefully stopping user client {account_id}: {e}")

    # ٣. لابردنی ئایدی ئەکاونتەکە لە لیستەکانی سێرڤەردا
    for server in db_data["servers"]:
        if account_id in server["joined_by_accounts"]:
            server["joined_by_accounts"].remove(account_id)
    
    # ٤. سڕینەوەی ئەو سێرڤەرانەی کە هیچ ئەکاونتێکی تریان تێدا نەماوە (بۆ پاکژکردنەوە)
    db_data["servers"] = [s for s in db_data["servers"] if s["joined_by_accounts"]]

    save_database() # داتابەیس پاشەکەوت دەکەین دوای گۆڕانکارییەکان
    await ctx.followup.send(f"ئەکاونتی `{original_username}` (ID: `{account_id}`) بە سەرکەوتوویی سڕایەوە.")


@bot.slash_command(name="list_accounts", description="پیشاندانی لیستی هەموو ئەکاونتە زیادکراوەکان.")
async def list_accounts(ctx):
    await ctx.defer(ephemeral=True)

    if not db_data["accounts"]:
        await ctx.followup.send("هیچ ئەکاونتێک زیاد نەکراوە.")
        return

    response = "## ئەکاونتە زیادکراوەکانت:\n"
    for acc in db_data["accounts"]:
        status = "🟢 ئۆنلاین" if acc["id"] in active_user_clients else "🔴 ئۆفلاین"
        response += f"- `{acc['username']}` (ID: `{acc['id']}`) - {status}\n"
    
    # گەر وەڵامەکە زۆر درێژ بوو، دابەشی دەکەین بۆ چەند پەیامێک (سنووری دیسکۆرد 2000 کاراکتەرە)
    if len(response) > 1950: # کەمتر لە 2000 دادەنێین بۆ دڵنیایی
        parts = []
        while len(response) > 0:
            parts.append(response[:1950])
            response = response[1950:]
        for part in parts:
            await ctx.followup.send(part)
    else:
        await ctx.followup.send(response)


@bot.slash_command(name="join_server", description="کردنەوەی ئەکاونتەکان بە سێرڤەرێکەوە.")
async def join_server(ctx, invite_link: Option(str, "لینکی بانگهێشتنامەی سێرڤەرەکە", required=True),
                                  num_accounts: Option(int, "ژمارەی ئەو ئەکاونتانەی جۆین دەکەن", min_value=1, required=True)):
    await ctx.defer() # وەڵامدانەوەی گشتی، تا بەکارهێنەران ببینن پرۆسەکە کار دەکات

    if num_accounts <= 0:
        await ctx.followup.send("ژمارەی ئەکاونتەکان دەبێت لانی کەم 1 بێت.")
        return

    # ١. وەرگرتنی زانیاری بانگهێشتنامەکە بە بۆتە سەرەکییەکە (باشتر و سەلامەتترە)
    invite_code = invite_link.replace("https://discord.gg/", "").replace("discord.gg/", "")
    invite = None
    try:
        invite = await bot.fetch_invite(invite_code)
    except discord.NotFound:
        await ctx.followup.send("لینکی بانگهێشتنامەکە نادروستە یان ماوەی بەسەرچووە.")
        return
    except discord.HTTPException as e:
        logger.error(f"HTTPException fetching invite: {e}", exc_info=True)
        await ctx.followup.send(f"هەڵەیەک ڕوویدا لە کاتی وەرگرتنی بانگهێشتنامەکە: {e.status} {e.text}")
        return
    except Exception as e:
        logger.error(f"Error fetching invite: {e}", exc_info=True)
        await ctx.followup.send(f"هەڵەیەکی چاوەڕواننەکراو ڕوویدا لە کاتی وەرگرتنی بانگهێشتنامەکە: {e}")
        return

    server_id = str(invite.guild.id)
    server_name = invite.guild.name

    # ٢. هەڵبژاردنی ئەو ئەکاونتانەی کە ئۆنلاینن و پێشتر جۆینی ئەم سێرڤەرەیان نەکردووە
    eligible_accounts = []
    for acc_data in db_data["accounts"]:
        if acc_data["id"] in active_user_clients and server_id not in acc_data["joined_servers"]:
            eligible_accounts.append(active_user_clients[acc_data["id"]])
    
    if not eligible_accounts:
        await ctx.followup.send("هیچ ئەکاونتێکی گونجاو نەدۆزرایەوە بۆ جۆینکردنی ئەم سێرڤەرە (یان ئۆفلاینن یان پێشتر جۆینیان کردووە).")
        return

    # ژمارەی ئەو ئەکاونتانە دیاری دەکەین کە جۆین دەکەن
    accounts_to_join = eligible_accounts[:min(num_accounts, len(eligible_accounts))]
    
    if not accounts_to_join:
        await ctx.followup.send("هیچ ئەکاونتێک بەردەست نییە بۆ جۆینکردنی سێرڤەرەکە.")
        return

    joined_count = 0
    failed_count = 0

    # ٣. زیادکردنی سێرڤەرەکە بۆ داتابەیس گەر نەبوو
    server_db_entry = next((s for s in db_data["servers"] if s['server_id'] == server_id), None)
    if not server_db_entry:
        new_server_entry = {"server_id": server_id, "server_name": server_name, "joined_by_accounts": []}
        db_data["servers"].append(new_server_entry)
        server_db_entry = new_server_entry # نوێی دەکەینەوە بۆ ئەوەی ئاماژە بێت بۆ لیستی سەرەکی
        save_database()

    await ctx.followup.send(f"هەوڵدەدەین `{server_name}` (ID: `{server_id}`) بە {len(accounts_to_join)} ئەکاونت جۆین بکەین. تکایە چاوەڕێ بکە...\n**هەر ٣٠ چرکە جارێک ئەکاونتێک جۆین دەکات.**")

    # ٤. پڕۆسەی جۆینکردن بە دواکەوتنی 30 چرکەیی
    for i, user_client in enumerate(accounts_to_join):
        try:
            await user_client.join_guild(invite_code)
            joined_count += 1
            
            # نوێکردنەوەی داتابەیس بۆ ئەکاونتەکە
            for acc_data in db_data["accounts"]:
                if acc_data["id"] == user_client.account_id:
                    if server_id not in acc_data["joined_servers"]:
                        acc_data["joined_servers"].append(server_id)
                    break
            
            # نوێکردنەوەی داتابەیس بۆ سێرڤەرەکە
            if server_db_entry and user_client.account_id not in server_db_entry["joined_by_accounts"]:
                server_db_entry["joined_by_accounts"].append(user_client.account_id)
            
            logger.info(f"Account {user_client.username} ({user_client.account_id}) joined {server_name}.")
            await ctx.send(f"🟢 `{user_client.username}` بە سەرکەوتوویی جۆینی `{server_name}`ی کرد. ({joined_count}/{len(accounts_to_join)})")

        except discord.HTTPException as e:
            failed_count += 1
            logger.error(f"Account {user_client.username} failed to join {server_name}: {e}", exc_info=True)
            await ctx.send(f"🔴 `{user_client.username}` نەیتوانی جۆینی `{server_name}` بکات: {e.text} ({joined_count}/{len(accounts_to_join)})")
        except Exception as e:
            failed_count += 1
            logger.error(f"Account {user_client.username} encountered an unexpected error joining {server_name}: {e}", exc_info=True)
            await ctx.send(f"🔴 `{user_client.username}` هەڵەیەکی تووش بوو لە کاتی جۆینکردنی `{server_name}`: {e} ({joined_count}/{len(accounts_to_join)})")
        
        finally:
            save_database() # داتابەیس پاشەکەوت دەکەین دوای هەر هەوڵێکی جۆینکردن
        
        # دواکەوتنی 30 چرکەیی وەک داواکارییەکەی تۆ مەتین گیان
        if i < len(accounts_to_join) - 1: # تەنها گەر ئەکاونتی تر مابێت بۆ جۆینکردن
            logger.info(f"Waiting 30 seconds before next account joins...")
            await asyncio.sleep(30) 
            
    final_message = f"پرۆسەی جۆینکردن تەواو بوو. {joined_count} ئەکاونت بە سەرکەوتوویی جۆینیان کرد، {failed_count} دانە فەیل بوون."
    await ctx.send(final_message)


@bot.slash_command(name="leave_server", description="لابردنی ئەکاونتەکان لە سێرڤەرێک.")
async def leave_server(ctx, server_id: Option(str, "ئایدی سێرڤەرەکە بۆ لێفتکردن", required=True),
                                   num_accounts: Option(int, "ژمارەی ئەو ئەکاونتانەی لێفت دەکەن", min_value=1, required=True)):
    await ctx.defer() # وەڵامدانەوەی گشتی

    if num_accounts <= 0:
        await ctx.followup.send("ژمارەی ئەکاونتەکان دەبێت لانی کەم 1 بێت.")
        return

    # ١. دڵنیابوونەوە لەوەی سێرڤەرەکە لە داتابەیسدا هەیە
    server_entry = next((s for s in db_data["servers"] if s['server_id'] == server_id), None)
    if not server_entry:
        await ctx.followup.send(f"سێرڤەرێک بە ئایدی `{server_id}` لە داتابەیسدا نەدۆزرایەوە.")
        return

    server_name = server_entry["server_name"]

    # ٢. هەڵبژاردنی ئەو ئەکاونتانەی کە ئۆنلاینن و لەم سێرڤەرەدان
    eligible_accounts = []
    for acc_id in server_entry["joined_by_accounts"]:
        if acc_id in active_user_clients: # دڵنیابوونەوە لەوەی ئەکاونتەکە چالاکە
            eligible_accounts.append(active_user_clients[acc_id])
    
    if not eligible_accounts:
        await ctx.followup.send(f"هیچ ئەکاونتێکی چالاک لە لیستی تۆدا لە سێرڤەری `{server_name}` (ID: `{server_id}`) نەدۆزرایەوە.")
        return

    accounts_to_leave = eligible_accounts[:min(num_accounts, len(eligible_accounts))]

    if not accounts_to_leave:
        await ctx.followup.send("هیچ ئەکاونتێک بەردەست نییە بۆ لێفتکردنی سێرڤەرەکە.")
        return

    left_count = 0
    failed_count = 0
    
    await ctx.followup.send(f"هەوڵدەدەین `{server_name}` (ID: `{server_id}`) بە {len(accounts_to_leave)} ئەکاونت لێفت بکەین. تکایە چاوەڕێ بکە...")

    # ٣. پڕۆسەی لێفتکردن
    for user_client in accounts_to_leave:
        try:
            guild = user_client.get_guild(int(server_id)) # سێرڤەرەکە لە ڕێگەی کڵاینتی بەکارهێنەرەوە وەردەگرین
            if guild:
                await guild.leave() # ئەکاونتەکە سێرڤەرەکە جێدەهێڵێت
                left_count += 1
                
                # نوێکردنەوەی داتابەیس بۆ ئەکاونتەکە
                for acc_data in db_data["accounts"]:
                    if acc_data["id"] == user_client.account_id and server_id in acc_data["joined_servers"]:
                        acc_data["joined_servers"].remove(server_id)
                        break
                
                # نوێکردنەوەی داتابەیس بۆ سێرڤەرەکە
                if server_entry and user_client.account_id in server_entry["joined_by_accounts"]:
                    server_entry["joined_by_accounts"].remove(user_client.account_id)
                
                logger.info(f"Account {user_client.username} ({user_client.account_id}) left {server_name}.")
                await ctx.send(f"🟢 `{user_client.username}` بە سەرکەوتوویی `{server_name}`ی جێهێشت. ({left_count}/{len(accounts_to_leave)})")
            else:
                failed_count += 1
                logger.warning(f"UserClient {user_client.username} did not find guild {server_id} to leave (perhaps already left).")
                await ctx.send(f"🟡 `{user_client.username}` (ID: {user_client.account_id}) لە سێرڤەری `{server_name}` (ID: `{server_id}`) نەدۆزرایەوە یان پێشتر لێفتی کردووە. ({left_count}/{len(accounts_to_leave)})")

        except discord.HTTPException as e:
            failed_count += 1
            logger.error(f"Account {user_client.username} failed to leave {server_name}: {e}", exc_info=True)
            await ctx.send(f"🔴 `{user_client.username}` نەیتوانی `{server_name}` جێبهێڵێت: {e.text} ({left_count}/{len(accounts_to_leave)})")
        except Exception as e:
            failed_count += 1
            logger.error(f"Account {user_client.username} encountered an unexpected error leaving {server_name}: {e}", exc_info=True)
            await ctx.send(f"🔴 `{user_client.username}` هەڵەیەکی تووش بوو لە کاتی جێهێشتنی `{server_name}`: {e} ({left_count}/{len(accounts_to_leave)})")
        finally:
            save_database() # داتابەیس پاشەکەوت دەکەین دوای هەر هەوڵێکی لێفتکردن
    
    # ٤. گەر سێرڤەرێک هیچ ئەکاونتێکی تێدا نەما، لە داتابەیسدا دەیسڕینەوە
    db_data["servers"] = [s for s in db_data["servers"] if s["joined_by_accounts"]]
    save_database()

    final_message = f"پرۆسەی لێفتکردن تەواو بوو. {left_count} ئەکاونت بە سەرکەوتوویی لێفتیان کرد، {failed_count} دانە فەیل بوون."
    await ctx.send(final_message)


@bot.slash_command(name="list_servers", description="پیشاندانی لیستی سێرڤەرەکان کە ئەکاونتەکانت جۆینیان کردووە.")
async def list_servers(ctx):
    await ctx.defer(ephemeral=True)

    if not db_data["servers"]:
        await ctx.followup.send("هیچ سێرڤەرێک لەلایەن ئەکاونتەکانتەوە جۆین نەکراوە.")
        return

    response = "## ئەو سێرڤەرانەی ئەکاونتەکانت جۆینیان کردووە:\n"
    for server in db_data["servers"]:
        online_joined_count = 0
        for acc_id in server["joined_by_accounts"]:
            if acc_id in active_user_clients: # دڵنیابوونەوە لەوەی ئەکاونتەکە چالاکە
                online_joined_count += 1

        response += (
            f"- `{server['server_name']}` (ID: `{server['server_id']}`)\n"
            f"  - جۆینکراوە لەلایەن: **{len(server['joined_by_accounts'])}** ئەکاونتەوە (لە ئێستادا **{online_joined_count}** ئۆنلاینن)\n"
        )
    
    if len(response) > 1950:
        parts = []
        while len(response) > 0:
            parts.append(response[:1950])
            response = response[1950:]
        for part in parts:
            await ctx.followup.send(part)
    else:
        await ctx.followup.send(response)


@bot.slash_command(name="status", description="بینینی زانیاری دەربارەی بۆتەکە و ئەکاونتەکان.")
async def get_status(ctx):
    await ctx.defer(ephemeral=True)

    total_accounts_in_db = len(db_data["accounts"])
    active_online_user_clients = len(active_user_clients) # ئەوانەی کە بەسەرکەوتوویی کار دەکەن
    total_servers_tracked = len(db_data["servers"])
    
    response = "## Sovereign Architect Bot Status:\n"
    response += f"- بۆتی سەرەکی: **{bot.user}** (ID: `{bot.user.id}`) - {'🟢 ئۆنلاین' if bot.is_ready() else '🔴 ئۆفلاین'}\n"
    response += f"- کۆی گشتی ئەکاونتەکان لە داتابەیسدا: **{total_accounts_in_db}**\n"
    response += f"- ئەکاونتە چالاکەکان (ئۆنلاین): **{active_online_user_clients}**\n"
    response += f"- کۆی گشتی سێرڤەرەکان کە بەدواداچوونیان بۆ کراوە: **{total_servers_tracked}**\n\n"
    response += "تێبینی: 'ئەکاونتە چالاکەکان' ئەوانەن کە تۆکنەکانیان بە سەرکەوتوویی چوونەتە ژوورەوە و لە ئێستادا کار دەکەن."

    await ctx.followup.send(response)

# --- 9. ڕانکردنی بۆتەکە ---
if __name__ == "__main__":
    logger.info("Starting Sovereign Architect Bot...")
    # دڵنیابوونەوە لەوەی فایلی داتابەیسەکە هەیە یان دروستی دەکەین
    if not os.path.exists(DATABASE_FILE):
        logger.info(f"Creating an empty database file: {DATABASE_FILE}")
        save_database() # ئەمە فایلێکی بەتاڵ دروست دەکات گەر نەبوو
    
    bot.run(BOT_TOKEN)
