import asyncio
import os
from datetime import datetime
import discord
from discord import app_commands  # スラッシュコマンドに必要
from discord.ext import commands, tasks

intents = discord.Intents.default()
intents.message_content = True

bot = commands.Bot(command_prefix="k.", intents=intents)

# 課題タスクを一時的に保存するリスト
kadai_tasks = []
gakushoku_links = []


@bot.event
async def on_ready():
    print(f"ログインしました: {bot.user.name}")

    # スラッシュコマンドをDiscord側に登録（同期）する処理
    try:
        synced = await bot.tree.sync()
        print(f"スラッシュコマンドを {len(synced)} 個同期しました。")
    except Exception as e:
        print(f"コマンドの同期中にエラーが発生しました: {e}")

    # バックグラウンドタスクの開始
    
    if not check_schedule.is_running():
        reset_gakushoku_menu.start()
        check_schedule.start()


# スラッシュコマンドのグループ（/kadai ...）を定義
class KadaiGroup(app_commands.Group):

    # /kadai add コマンドの定義
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
        # スラッシュコマンドでは ctx の代わりに interaction を使います
        try:
            # 日時の解析
            full_date_str = f"{date_str} {time_str}"
            target_datetime = datetime.strptime(full_date_str, "%Y/%m/%d %H:%M")

            now = datetime.now()

            # 過去日付のチェック
            if target_datetime < now:
                await interaction.response.send_message(
                    "❌ 過去の日時は指定できません。未来の日時を入力してください。",
                    ephemeral=True,
                )
                return

            # タスク情報の保存（interaction からIDを取得）
            task_info = {
                "title": title,
                "remind_at": target_datetime,
                "user_id": interaction.user.id,
                "channel_id": interaction.channel_id,
            }
            kadai_tasks.append(task_info)

            # 登録完了メッセージ
            formatted_time = target_datetime.strftime("%Y/%m/%d %H:%M")
            await interaction.response.send_message(
                f"✅ 課題を登録しました！\n"
                f"**タイトル:** {title}\n"
                f"**通知日時:** {formatted_time} にメンションします。"
            )

        except ValueError:
            # 入力形式が違っていた場合のエラーハンドリング
            await interaction.response.send_message(
                "❌ 入力形式が正しくありません。\n"
                "日付は `YYYY/MM/DD`、時間は `HH:MM` の形式で入力してください。\n"
                "例: `2026/07/25` と `23:59`",
                ephemeral=True,
            )


# 作成したグループコマンドをBotのツリーに追加
bot.tree.add_command(KadaiGroup(name="kadai", description="課題管理コマンド"))


# 1分ごとにスケジュールをチェックするバックグラウンドタスク（変更なし）
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
        kadai_tasks.remove(task)

class gakushokuGroup(app_commands.Group):

    @app_commands.command(name="add", description="学食のメニューを追加します")
    @app_commands.describe(
        link="Discord上での画像リンク（https://cdn.discord~）",
    )
    async def gakushoku_add(
        self,
        interaction: discord.Interaction,
        link: str,
    ):
        link_info = {
            "link": link,
            "channel_id": interaction.channel_id,
        }
        gakushoku_links.append(link_info)
        await interaction.response.send_message(
            f"✅ 学食メニューを登録しました！\n"
            f"リンク: {link}"
        )

    @app_commands.command(name="list", description="学食のメニューを表示します")
    async def gakushoku_list(
        self,
        interaction: discord.Interaction,
    ):
        if not gakushoku_links:
            await interaction.response.send_message("📝 学食のメニューは登録されていません。", ephemeral=True)
            return

        menu_messages = []
        for link_info in gakushoku_links:
            menu_messages.append(f"🔗 {link_info['link']}")

        await interaction.response.send_message("\n".join(menu_messages))
@tasks.loop(minutes=1.0)
async def reset_gakushoku_menu():
    now = datetime.now()

    # weekday() が 6 = 日曜日、23時59分 のタイミングで実行
    if now.weekday() == 6 and now.hour == 23 and now.minute == 59:
        gakushoku_links.clear()  # リストを空にする
        print(f"[{now.strftime('%Y/%m/%d %H:%M')}] 学食メニューのリストを自動削除しました。")



bot.tree.add_command(gakushokuGroup(name="gakushoku", description="学食について"))

bot.run(os.getenv('DISCORD_TOKEN'))