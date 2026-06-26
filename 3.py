import asyncio
import os
from datetime import datetime
import warnings
import discord
from discord import app_commands
from discord.ext import commands, tasks

# Appwrite SDKのインポート
from appwrite.client import Client
from appwrite.services.databases import Databases
from appwrite.id import ID

# ログに出る非推奨警告(DeprecationWarning)を非表示にする
warnings.filterwarnings("ignore", category=DeprecationWarning)

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="k.", intents=intents)

# --- Appwriteの設定 ---
APPWRITE_ENDPOINT = os.getenv("APPWRITE_ENDPOINT")  
APPWRITE_PROJECT_ID = os.getenv("APPWRITE_PROJECT_ID")
APPWRITE_API_KEY = os.getenv("APPWRITE_API_KEY")      
DATABASE_ID = os.getenv("APPWRITE_DATABASE_ID")

COLLECTION_KADAI = "kadai_tasks"      
COLLECTION_GAKUSHOKU = "gakushoku_links" 

client = Client()
client.set_endpoint(APPWRITE_ENDPOINT)
client.set_project(APPWRITE_PROJECT_ID)
client.set_key(APPWRITE_API_KEY)

databases = Databases(client)

# メモリ保持用のリスト
kadai_tasks = []
gakushoku_links = []

async def load_data_from_appwrite():
    """起動時にAppwriteからデータを【非同期で】読み込んでリストを同期する関数"""
    global kadai_tasks, gakushoku_links
    kadai_tasks = []
    gakushoku_links = []

    try:
        # 💡 asyncio.to_thread を使い、メインループをフリーズさせずに裏でデータを取得する
        response_kadai = await asyncio.to_thread(databases.list_documents, DATABASE_ID, COLLECTION_KADAI)
        for doc in response_kadai['documents']:
            dt_str = doc['remind_at'].split('.')[0].replace('T', ' ') 
            kadai_tasks.append({
                "document_id": doc['$id'], 
                "title": doc['title'],
                "remind_at": datetime.strptime(dt_str, "%Y-%m-%d %H:%M:%S"),
                "user_id": int(doc['user_id']),
                "channel_id": int(doc['channel_id'])
            })

        response_gaku = await asyncio.to_thread(databases.list_documents, DATABASE_ID, COLLECTION_GAKUSHOKU)
        for doc in response_gaku['documents']:
            gakushoku_links.append({
                "document_id": doc['$id'],
                "link": doc['link'],
                "channel_id": int(doc['channel_id'])
            })
        print("Appwriteデータベースからデータを同期しました。")
    except Exception as e:
        print(f"Appwriteからのデータ読み込みエラー: {e}")

# ----------------------------------

@bot.event
async def on_ready():
    print(f"ログインしました: {bot.user.name}")
    new_activity = f"at NNCT" 
    await bot.change_presence(activity=discord.Game(new_activity))

    # 💡 バックグラウンドタスクとして走らせることで起動時のタイムアウトを完全回避
    asyncio.create_task(load_data_from_appwrite())

    try:
        synced = await bot.tree.sync()
        print(f"スラッシュコマンドを {len(synced)} 個同期しました。")
    except Exception as e:
        print(f"コマンドの同期中にエラーが発生しました: {e}")
    
    if not check_schedule.is_running():
        reset_gakushoku_menu.start()
        check_schedule.start()


class KadaiGroup(app_commands.Group):

    @app_commands.command(name="add", description="課題の通知を登録します")
    @app_commands.describe(
        title="課題のタイトル（例: レポート）",
        date_str="年月日（例: 2026/07/25）",
        time_str="時間（例: 18:30）",
    )
    async def kadai_add(
        self,
        interaction: discord.Interaction,
        title: str,
        date_str: str,
        time_str: str,
    ):
        # 💡 最初に応答を保留(defer)する
        await interaction.response.defer()

        try:
            full_date_str = f"{date_str} {time_str}"
            target_datetime = datetime.strptime(full_date_str, "%Y/%m/%d %H:%M")
            now = datetime.now()

            if target_datetime < now:
                await interaction.followup.send("❌ 過去の日時は指定できません。未来の日時を入力してください。")
                return

            data = {
                "title": title,
                "remind_at": target_datetime.isoformat(), 
                "user_id": str(interaction.user.id),
                "channel_id": str(interaction.channel_id)
            }
            
            # 💡 Appwriteとの通信を別スレッドに逃がす
            doc = await asyncio.to_thread(databases.create_document, DATABASE_ID, COLLECTION_KADAI, ID.unique(), data)

            task_info = {
                "document_id": doc['$id'],
                "title": title,
                "remind_at": target_datetime,
                "user_id": interaction.user.id,
                "channel_id": interaction.channel_id,
            }
            kadai_tasks.append(task_info)

            formatted_time = target_datetime.strftime("%Y/%m/%d %H:%M")
            await interaction.followup.send(
                f"✅ 課題を登録しました！\n"
                f"**タイトル:** {title}\n"
                f"**通知日時:** {formatted_time} にメンションします。"
            )

        except ValueError:
            await interaction.followup.send(
                "❌ 入力形式が正しくありません。\n"
                "日付は `YYYY/MM/DD`、時間は `HH:MM` の形式で入力してください。\n"
                "例: `2026/07/25` と `23:59`"
            )

bot.tree.add_command(KadaiGroup(name="kadai", description="課題管理コマンド"))


@tasks.loop(minutes=1.0)
async def check_schedule():
    now = datetime.now()
    completed_tasks = []

    for task in kadai_tasks:
        if now >= task["remind_at"]:
            channel = bot.get_channel(task["channel_id"])
            if channel:
                user_mention = f"<@{task['user_id']}>"
                await channel.send(
                    f"⏰ {user_mention} 設定された時間になりました！\n"
                    f"登録されていた課題: **{task['title']}**"
                )
            completed_tasks.append(task)

    for task in completed_tasks:
        try:
            await asyncio.to_thread(databases.delete_document, DATABASE_ID, COLLECTION_KADAI, task["document_id"])
            kadai_tasks.remove(task)
        except Exception as e:
            print(f"課題の削除エラー: {e}")


class gakushokuGroup(app_commands.Group):

    @app_commands.command(name="add", description="学食のメニューを追加します")
    @app_commands.describe(link="Discord上での画像リンク")
    async def gakushoku_add(self, interaction: discord.Interaction, link: str):
        await interaction.response.defer()

        try:
            data = {
                "link": link,
                "channel_id": str(interaction.channel_id)
            }
            doc = await asyncio.to_thread(databases.create_document, DATABASE_ID, COLLECTION_GAKUSHOKU, ID.unique(), data)

            link_info = {
                "document_id": doc['$id'],
                "link": link,
                "channel_id": interaction.channel_id,
            }
            gakushoku_links.append(link_info)
            
            await interaction.followup.send(f"✅ 学食メニューを登録しました！\nリンク: {link}")
        except Exception as e:
            await interaction.followup.send(f"❌ 登録中にエラーが発生しました: {e}")

    @app_commands.command(name="list", description="学食のメニューを表示します")
    async def gakushoku_list(self, interaction: discord.Interaction):
        await interaction.response.defer()

        if not gakushoku_links:
            await interaction.followup.send("📝 学食のメニューは登録されていません。")
            return

        menu_messages = []
        for link_info in gakushoku_links:
            menu_messages.append(f"🔗 {link_info['link']}")

        await interaction.followup.send("\n".join(menu_messages))


@tasks.loop(minutes=1.0)
async def reset_gakushoku_menu():
    now = datetime.now()

    if now.weekday() == 6 and now.hour == 23 and now.minute == 59:
        for link_info in gakushoku_links:
            try:
                await asyncio.to_thread(databases.delete_document, DATABASE_ID, COLLECTION_GAKUSHOKU, link_info["document_id"])
            except Exception as e:
                print(f"学食データの削除エラー: {e}")
                
        gakushoku_links.clear()
        print(f"[{now.strftime('%Y/%m/%d %H:%M')}] 学食メニューのリストを自動削除しました。")


bot.tree.add_command(gakushokuGroup(name="gakushoku", description="学食について"))

bot.run(os.getenv('DISCORD_TOKEN'))
