import discord
from discord.ext import commands
import asyncio
import logging
from datetime import datetime

# هاوردەکردنی ڕێکخستنەکان، داتابەیس، و بەڕێوەبەری ئەکاونت
from config import BOT_TOKEN, GUILD_ID, SELF_BOT_WARNING
from database import DatabaseManager
from account_manager import AccountManager

# ڕێکخستنی Logging بۆ main bot
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger('MainBot')

# دیاریکردنی Intentsـی بۆتەکە
intents = discord.Intents.default()
intents.message_content = True # پێویستە ئەگەر فەرمانی ئاسایی (نەک سلاش کۆماند) بەکار بهێنیت
intents.members = True       # بۆ دەستڕاگەیشتن بە زانیاری ئەندامان
intents.guilds = True        # بۆ دەستڕاگەیشتن بە زانیاری سێرڤەرەکان
intents.presences = True     # بۆ وەرگرتنی نوێکارییەکانی پرێزنس

# دەستپێکردنی بۆتە سەرەکییەکە
# command_prefix تەنها بۆ فەرمانە کۆنەکانە، بەڵام بۆ slash commands پێویست نییە
bot = commands.Bot(command_prefix="/", intents=intents)

# دەستپێکردنی بەڕێوەبەری داتابەیس و بەڕێوەبەری ئەکاونت
db_manager = DatabaseManager()
account_manager = AccountManager(bot, db_manager)

@bot.event
async def on_ready():
    """کاتێک بۆتە سەرەکییەکە پەیوەندی بە دیسکۆردەوە دەکات و ئامادە دەبێت."""
    logger.info(f"Main bot logged in as {bot.user} (ID: {bot.user.id})")
    
    # سینکرۆنایزکردنی سلاش کۆماندەکان
    try:
        if GUILD_ID:
            guild = discord.Object(id=GUILD_ID)
            bot.tree.copy_global_to(guild=guild) # بۆ خێراکردن، global commands بۆ ئەم guildـە کۆپی دەکات
            await bot.tree.sync(guild=guild)
            logger.info(f"Slash commands synced to guild {GUILD_ID}.")
        else:
            await bot.tree.sync() # سینکرۆنایزکردنی گڵۆباڵ (کاتی زیاتری دەوێت)
            logger.info("Global slash commands synced.")
    except Exception as e:
        logger.error(f"Error syncing slash commands: {e}")

    # بارکردن و دەستپێکردنی هەموو ئەکاونتەکانی بەکارهێنەری هەبوو لە داتابەیسدا
    await account_manager.load_accounts()
    
    # دەستپێکردنی Taskـی چوونە ژوورەوەی سێرڤەری خولیی (هەر 30 چرکە جارێک)
    account_manager.start_join_guild_task()
    
    # ناردنی هۆشداری Self-Botting بۆ کۆنسۆڵ
    print("\n" + "#" * 50)
    print(SELF_BOT_WARNING)
    print("#" * 50 + "\n")


# --------------------------------------------------------------------------------------
# سلاش کۆماندەکان بۆ بەڕێوەبردنی ئەکاونتەکانی بەکارهێنەر
# --------------------------------------------------------------------------------------

@bot.tree.command(name="add_account", description="زیادکردنی ئەکاونتێک بە تۆکن (تێبینی: دژی مەرجەکانی دیسکۆردە)")
async def add_account(interaction: discord.Interaction, token: str):
    """
    ئەکاونتێکی بەکارهێنەری نوێ زیاد دەکات بۆ بەڕێوەبردن لەلایەن بۆتەکەوە.
    **هۆشداری:** بەکارهێنانی تۆکنی بەکارهێنەر دژی مەرجەکانی دیسکۆردە.
    """
    await interaction.response.defer(ephemeral=True) # وەڵامدانەوەی خێرای فەرمانەکە (تەنها بۆ تۆ دەردەکەوێت)

    # دووبارە هۆشدارییەکە دەردەبڕینەوە
    warning_message = "تێبینی: بەکارهێنانی ئەکاونتی بەکارهێنەر (نەک بۆت) دژی مەرجەکانی دیسکۆردە و دەکرێت ببێتە هۆی بلۆککردنی ئەکاونتەکانت. تکایە بە ئاگابە."
    await interaction.followup.send(warning_message, ephemeral=True)

    # پشتڕاستکردنەوەی سەرەتایی بۆ درێژی تۆکنەکە
    if len(token) < 50 or " " in token: # تۆکنەکان بە گشتی درێژن و بۆشاییان تێدا نییە
        await interaction.followup.send("تۆکنەکە بە دروستی دەرناکەوێت. تکایە دڵنیابەرەوە لە تۆکنەکە.", ephemeral=True)
        return

    success, message = await account_manager.add_account(token)
    if success:
        await interaction.followup.send(f"ئەکاونتەکە زیاد کرا و کارا کرا: {token[:10]}... \n{message}", ephemeral=True)
    else:
        await interaction.followup.send(f"ناتوانرێت ئەکاونتەکە زیاد بکرێت: {message}", ephemeral=True)

@bot.tree.command(name="remove_account", description="سڕینەوەی ئەکاونتێک بە تۆکن")
async def remove_account(interaction: discord.Interaction, token: str):
    """ئەکاونتێکی بەکارهێنەر لە بەڕێوەبردن لادەبات."""
    await interaction.response.defer(ephemeral=True)

    if len(token) < 50 or " " in token:
        await interaction.followup.send("تۆکنەکە بە دروستی دەرناکەوێت. تکایە دڵنیابەرەوە لە تۆکنەکە.", ephemeral=True)
        return

    success, message = await account_manager.remove_account(token)
    if success:
        await interaction.followup.send(f"ئەکاونتەکە سڕایەوە و ڕاگیرا: {token[:10]}... \n{message}", ephemeral=True)
    else:
        await interaction.followup.send(f"ناتوانرێت ئەکاونتەکە بسڕدرێتەوە: {message}", ephemeral=True)

@bot.tree.command(name="list_accounts", description="لیستی هەموو ئەکاونتە بەڕێوەبراوەکان")
async def list_accounts(interaction: discord.Interaction):
    """لیستی هەموو ئەکاونتە بەڕێوەبراوەکان و بارودۆخەکانیان پیشان دەدات."""
    await interaction.response.defer(ephemeral=True)

    accounts_data = await db_manager.get_all_accounts()
    if not accounts_data:
        await interaction.followup.send("هیچ ئەکاونتێک لە داتابەیسدا نییە.", ephemeral=True)
        return

    embed = discord.Embed(title="لیستی ئەکاونتە بەڕێوەبراوەکان", color=0x00ff00)
    for acc in accounts_data:
        token_snippet = acc['token'][:10] + "..."
        status = acc['status']
        
        # گۆڕینی کاتی ISO format بۆ datetime object
        last_activity = datetime.fromisoformat(acc['last_activity']) if acc['last_activity'] else None
        last_activity_str = last_activity.strftime('%Y-%m-%d %H:%M:%S') if last_activity else "N/A"
        
        current_guild = acc['current_guild_id'] if acc['current_guild_id'] else "هیچ سێرڤەرێک"
        
        # پشکنینی ئەگەر clientـی ئەکاونتەکە لە AccountManagerـدا چالاک بێت
        is_active = "✅ (چالاک)" if acc['token'] in account_manager.managed_accounts and account_manager.managed_accounts[acc['token']].is_ready else "❌ (ناچالاک)"
        
        embed.add_field(
            name=f"ئەکاونت: {token_snippet}",
            value=f"**بارودۆخ:** {status} {is_active}\n**دوایین چالاکی:** {last_activity_str}\n**سێرڤەری ئێستا:** {current_guild}",
            inline=False
        )
    await interaction.followup.send(embed=embed, ephemeral=True)

@bot.tree.command(name="add_guild", description="زیادکردنی لینکی بانگێشتکردنی سێرڤەر")
async def add_guild(interaction: discord.Interaction, invite_link: str):
    """لینکی بانگێشتکردنی سێرڤەرێک زیاد دەکات بۆ داتابەیسەکە بۆ ئەوەی ئەکاونتەکان پەیوەندی پێوە بکەن."""
    await interaction.response.defer(ephemeral=True)

    try:
        # دەرهێنانی کۆدی بانگێشتکردن لە لینکەکە
        invite_code = invite_link.split('/')[-1]
        if invite_code.startswith("https://discord.gg/"): # بۆ حاڵەتێک کە کۆدەکه link بێت نەک تەنها code
             invite_code = invite_code[len("https://discord.gg/"):]
        elif invite_code.startswith("discord.gg/"):
            invite_code = invite_code[len("discord.gg/"):]


        # بەکارهێنانی بۆتە سەرەکییەکە بۆ هێنانی زانیاری بانگێشتکردنەکە
        invite = await bot.fetch_invite(invite_code)
        
        success = await db_manager.add_guild(invite.guild.id, invite.guild.name, invite_code)
        if success:
            await interaction.followup.send(f"لینکی بانگێشتکردنی سێرڤەری '{invite.guild.name}' ({invite.guild.id}) زیاد کرا.", ephemeral=True)
        else:
            await interaction.followup.send(f"ناتوانرێت لینکی بانگێشتکردنی سێرڤەری '{invite.guild.name}' زیاد بکرێت (لەوانەیە پێشتر زیاد کرابێت).", ephemeral=True)
    except discord.errors.NotFound:
        await interaction.followup.send("لینکی بانگێشتکردنەکە نادروستە یان بەسەرچووە.", ephemeral=True)
    except discord.HTTPException as e:
        await interaction.followup.send(f"هەڵەی دیسکۆرد: {e}", ephemeral=True)
    except Exception as e:
        logger.error(f"Error in add_guild command: {e}", exc_info=True)
        await interaction.followup.send(f"هەڵەیەکی نەناسراو ڕوویدا: {e}", ephemeral=True)


@bot.tree.command(name="remove_guild", description="سڕینەوەی لینکی بانگێشتکردنی سێرڤەر")
async def remove_guild(interaction: discord.Interaction, invite_code: str):
    """لینکی بانگێشتکردنی سێرڤەرێک لە داتابەیسەکە دەسڕێتەوە."""
    await interaction.response.defer(ephemeral=True)

    success = await db_manager.delete_guild(invite_code)
    if success:
        await interaction.followup.send(f"لینکی بانگێشتکردنی '{invite_code}' سڕایەوە.", ephemeral=True)
    else:
        await interaction.followup.send(f"ناتوانرێت لینکی بانگێشتکردنی '{invite_code}' بدۆزرێتەوە یان بسڕدرێتەوە.", ephemeral=True)

@bot.tree.command(name="list_guilds", description="لیستی هەموو لینکە بانگێشتکراوەکانی سێرڤەر")
async def list_guilds(interaction: discord.Interaction):
    """لیستی هەموو لینکە بانگێشتکراوەکانی سێرڤەر پیشان دەدات."""
    await interaction.response.defer(ephemeral=True)

    guilds_data = await db_manager.get_all_guild_invites()
    if not guilds_data:
        await interaction.followup.send("هیچ لینکێکی بانگێشتکردنی سێرڤەر لە داتابەیسدا نییە.", ephemeral=True)
        return

    embed = discord.Embed(title="لیستی لینکە بانگێشتکراوەکانی سێرڤەر", color=0x0000ff)
    for guild in guilds_data:
        embed.add_field(
            name=f"سێرڤەر: {guild['name']}",
            value=f"**ID:** {guild['guild_id']}\n**کۆدی بانگێشت:** {guild['invite_code']}",
            inline=False
        )
    await interaction.followup.send(embed=embed, ephemeral=True)

@bot.tree.command(name="start_all_accounts", description="دەستپێکردنی هەموو ئەکاونتە بەڕێوەبراوەکان")
async def start_all_accounts(interaction: discord.Interaction):
    """هەموو ئەکاونتە بەڕێوەبراوەکان دەستپێدەکات."""
    await interaction.response.defer(ephemeral=True)
    success, message = await account_manager.start_all_accounts()
    await interaction.followup.send(message, ephemeral=True)

@bot.tree.command(name="stop_all_accounts", description="ڕاگرتنی هەموو ئەکاونتە بەڕێوەبراوەکان")
async def stop_all_accounts(interaction: discord.Interaction):
    """هەموو ئەکاونتە بەڕێوەبراوەکان ڕادەگرێت."""
    await interaction.response.defer(ephemeral=True)
    success, message = await account_manager.stop_all_accounts()
    await interaction.followup.send(message, ephemeral=True)

@bot.tree.command(name="help_bot", description="زانیاری دەربارەی بۆتەکە و فەرمانەکان")
async def help_bot(interaction: discord.Interaction):
    """زانیاری یارمەتی دەربارەی بۆتەکە و فەرمانەکانی پێشکەش دەکات."""
    await interaction.response.defer(ephemeral=True)
    
    help_text = f"""
**بەخێربێیت بۆ بۆتی Sovereign Architect!** 
ئەم بۆتە بۆ بەڕێوەبردنی چەندین ئەکاونتی بەکارهێنەری دیسکۆرد دروست کراوە.

**تێبینییەکی زۆر گرنگ:** 
**بەکارهێنانی ئەکاونتی بەکارهێنەر (نەک بۆت) دژی مەرجەکانی دیسکۆردە و دەکرێت ببێتە هۆی بلۆککردنی ئەکاونتەکانت.**
**تکایە بە ئاگابە و بەرپرسیارییەتییەکەی لە ئەستۆ بگرە.**
    
**لیستی فەرمانەکان:**
*   `/add_account <تۆکن>`: ئەکاونتێکی نوێ زیاد دەکات بۆ بەڕێوەبردن. (پێویستە تۆکنەکە بە دەستی بهێنیت و بیدەیتێ.)
*   `/remove_account <تۆکن>`: ئەکاونتێک دەسڕێتەوە لە بەڕێوەبردن.
*   `/list_accounts`: لیستی هەموو ئەکاونتە بەڕێوەبراوەکان و بارودۆخەکانیان پیشان دەدات.
*   `/add_guild <لینکی بانگێشت>`: لینکی بانگێشتکردنی سێرڤەرێک زیاد دەکات بۆ ئەوەی ئەکاونتەکان پەیوەندی پێوە بکەن.
*   `/remove_guild <کۆدی بانگێشت>`: لینکی بانگێشتکردنی سێرڤەرێک دەسڕێتەوە.
*   `/list_guilds`: لیستی هەموو لینکە بانگێشتکراوەکانی سێرڤەر پیشان دەدات.
*   `/start_all_accounts`: هەموو ئەکاونتە بەڕێوەبراوەکان دەستپێدەکات.
*   `/stop_all_accounts`: هەموو ئەکاونتە بەڕێوەبراوەکان ڕادەگرێت.

**تایبەتمەندییەکان:**
*   **داتابەیس:** `SQLite` بەکار دەهێنێت بۆ هەڵگرتنی داتا بە شێوەیەکی تۆکمە و بێ کێشە، بەتایبەتی بۆ ژمارەیەکی زۆر ئەکاونت (تاوەکو 1000 ئەکاونت یان زیاتر).
*   **چاڵاکی 24/7:** ئەکاونتەکان بەردەوام ئۆنڵاین دەبن، بە ستاتسێکی custom بۆ دەرکەوتنی مۆبایل.
*   **جووڵەی سێرڤەر:** هەموو 30 چرکە جارێک، ئەکاونتێکی چالاک هەوڵ دەدات بچێتە سێرڤەرێکی هەڕەمەکی لە لیستی سێرڤەرەکان.

**مێژووی چالاکبوون:** 2026-05-01
"""
    embed = discord.Embed(
        title="زانیاری بۆت",
        description=help_text,
        color=discord.Color.blue()
    )
    await interaction.followup.send(embed=embed, ephemeral=True)


# کارپێکردنی بۆتە سەرەکییەکە
if __name__ == "__main__":
    if not BOT_TOKEN or BOT_TOKEN == "لێرە تۆکنی بۆتە سەرەکییەکەت دابنێ":
        logger.critical("تۆکنی بۆت دانەنراوە. تکایە Environment Variableـی DISCORD_BOT_TOKEN دابنێ یان 'لێرە تۆکنی بۆتە سەرەکییەکەت دابنێ' لە config.py بگۆڕە.")
    else:
        try:
            bot.run(BOT_TOKEN)
        except discord.errors.LoginFailure:
            logger.critical("شکستی هێنا لە چوونە ژوورەوەی بۆتە سەرەکییەکە. دڵنیابەرەوە لەوەی BOT_TOKEN دروستە و بۆ ئەکاونتێکی BOT دروست کراوە، نەک ئەکاونتی USER.")
        except Exception as e:
            logger.critical(f"هەڵەیەکی چاوەڕواننەکراو ڕوویدا لە کاتی کارپێکردنی بۆتەکە: {e}", exc_info=True)
