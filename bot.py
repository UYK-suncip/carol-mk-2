import discord
from discord import app_commands
from discord.ext import commands
import json
import os
from datetime import datetime

TOKEN = os.environ.get("DISCORD_TOKEN")
GUILD_ID = int(os.environ.get("DISCORD_GUILD_ID", "0"))
ROLE_ID = int(os.environ.get("ROLE_ID", "0"))

DATA_FILE = "members.json"

intents = discord.Intents.default()
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)


def load_members():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_members(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


class 참여Modal(discord.ui.Modal, title="참여 정보 입력"):
    국가 = discord.ui.TextInput(
        label="국가",
        placeholder="예) 대한민국, Korea, Japan ...",
        required=True,
        max_length=50
    )
    인게임닉네임 = discord.ui.TextInput(
        label="인게임 닉네임",
        placeholder="게임 내에서 사용하는 닉네임을 입력하세요",
        required=True,
        max_length=64
    )
    플레이타임 = discord.ui.TextInput(
        label="플레이타임 (선택)",
        placeholder="예) 500시간, 1000h ...",
        required=False,
        max_length=50
    )

    async def on_submit(self, interaction: discord.Interaction):
        user = interaction.user
        members = load_members()

        if str(user.id) in members:
            await interaction.response.send_message(
                f"⚠️ **{user.display_name}**님은 이미 참여하셨습니다!", ephemeral=True
            )
            return

        members[str(user.id)] = {
            "id": user.id,
            "username": user.name,
            "display_name": user.display_name,
            "국가": self.국가.value,
            "인게임닉네임": self.인게임닉네임.value,
            "플레이타임": self.플레이타임.value if self.플레이타임.value else "미입력",
            "joined_at": datetime.now().isoformat()
        }
        save_members(members)

        guild = interaction.guild
        role = guild.get_role(ROLE_ID)

        if role is None:
            await interaction.response.send_message(
                "❌ 역할을 찾을 수 없습니다. 관리자에게 문의해주세요.", ephemeral=True
            )
            return

        try:
            await user.add_roles(role, reason="슬래시 명령어 /참여 사용")
            await interaction.response.send_message(
                f"✅ **{user.display_name}**님, 참여 완료! **{role.name}** 역할이 지급되었습니다!\n"
                f"> 🌍 국가: {self.국가.value}\n"
                f"> 🎮 닉네임: {self.인게임닉네임.value}\n"
                f"> ⏱️ 플레이타임: {self.플레이타임.value or '미입력'}",
                ephemeral=True
            )
            print(f"[역할 지급] {user.name} ({user.id}) 닉네임={self.인게임닉네임.value} 국가={self.국가.value}")
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ 봇에게 역할 지급 권한이 없습니다. 관리자에게 문의해주세요.", ephemeral=True
            )
        except Exception as e:
            await interaction.response.send_message(
                f"❌ 오류 발생: {e}", ephemeral=True
            )


@bot.event
async def on_ready():
    print(f"봇 로그인 완료: {bot.user} (ID: {bot.user.id})")
    try:
        guild = discord.Object(id=GUILD_ID)
        bot.tree.copy_global_to(guild=guild)
        synced = await bot.tree.sync(guild=guild)
        print(f"슬래시 명령어 {len(synced)}개 동기화 완료")
    except Exception as e:
        print(f"명령어 동기화 오류: {e}")


@bot.tree.command(name="참여", description="서버에 참여하고 역할을 받습니다.")
async def 참여(interaction: discord.Interaction):
    members = load_members()
    if str(interaction.user.id) in members:
        await interaction.response.send_message(
            f"⚠️ **{interaction.user.display_name}**님은 이미 참여하셨습니다!", ephemeral=True
        )
        return
    await interaction.response.send_modal(참여Modal())


@bot.tree.command(name="목록", description="참여한 멤버 목록을 확인합니다. (관리자 전용)")
@app_commands.checks.has_permissions(administrator=True)
async def 목록(interaction: discord.Interaction):
    members = load_members()

    if not members:
        await interaction.response.send_message("📋 아직 참여한 멤버가 없습니다.", ephemeral=True)
        return

    lines = [f"📋 **참여 멤버 목록** (총 {len(members)}명)\n"]
    for i, (uid, info) in enumerate(members.items(), 1):
        joined = info.get("joined_at", "알 수 없음")[:10]
        nickname = info.get("인게임닉네임", "미입력")
        country = info.get("국가", "미입력")
        playtime = info.get("플레이타임", "미입력")
        lines.append(
            f"`{i}.` **{info['display_name']}** (`{uid}`)\n"
            f"　🌍 {country} | 🎮 {nickname} | ⏱️ {playtime} | 📅 {joined}"
        )

    message = "\n".join(lines)
    if len(message) > 2000:
        message = message[:1990] + "\n..."

    await interaction.response.send_message(message, ephemeral=True)


@bot.tree.command(name="역할일괄지급", description="JSON에 저장된 모든 멤버에게 역할을 지급합니다. (관리자 전용)")
@app_commands.checks.has_permissions(administrator=True)
async def 역할일괄지급(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    members = load_members()

    if not members:
        await interaction.followup.send("📋 아직 참여한 멤버가 없습니다.", ephemeral=True)
        return

    guild = interaction.guild
    role = guild.get_role(ROLE_ID)

    if role is None:
        await interaction.followup.send("❌ 역할을 찾을 수 없습니다.", ephemeral=True)
        return

    success = 0
    failed = 0

    for uid, info in members.items():
        try:
            member = guild.get_member(int(uid))
            if member is None:
                member = await guild.fetch_member(int(uid))
            if role not in member.roles:
                await member.add_roles(role, reason="일괄 역할 지급")
            success += 1
        except Exception as e:
            print(f"역할 지급 실패 {uid}: {e}")
            failed += 1

    await interaction.followup.send(
        f"✅ 일괄 지급 완료!\n성공: {success}명 / 실패: {failed}명",
        ephemeral=True
    )


@bot.tree.command(name="제거", description="특정 유저를 목록에서 제거합니다. (관리자 전용)")
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(유저id="제거할 유저의 ID")
async def 제거(interaction: discord.Interaction, 유저id: str):
    members = load_members()

    if 유저id not in members:
        await interaction.response.send_message(
            f"⚠️ ID `{유저id}` 는 목록에 없습니다.", ephemeral=True
        )
        return

    info = members.pop(유저id)
    save_members(members)
    print(f"[제거] {info['display_name']} ({유저id}) 목록에서 제거됨")

    await interaction.response.send_message(
        f"🗑️ **{info['display_name']}** (`{유저id}`) 님이 목록에서 제거되었습니다.",
        ephemeral=True
    )


@bot.tree.command(name="일괄제거", description="목록의 모든 멤버를 제거합니다. (관리자 전용)")
@app_commands.checks.has_permissions(administrator=True)
async def 일괄제거(interaction: discord.Interaction):
    members = load_members()

    if not members:
        await interaction.response.send_message("📋 목록이 이미 비어 있습니다.", ephemeral=True)
        return

    count = len(members)
    save_members({})
    print(f"[일괄제거] 총 {count}명 목록에서 제거됨")

    await interaction.response.send_message(
        f"🗑️ 총 **{count}명** 의 멤버가 목록에서 제거되었습니다.",
        ephemeral=True
    )


@목록.error
@역할일괄지급.error
@제거.error
@일괄제거.error
async def permission_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message("❌ 관리자만 사용할 수 있는 명령어입니다.", ephemeral=True)


if __name__ == "__main__":
    if not TOKEN:
        print("오류: DISCORD_TOKEN 환경변수가 설정되지 않았습니다.")
    elif GUILD_ID == 0:
        print("오류: DISCORD_GUILD_ID 환경변수가 설정되지 않았습니다.")
    elif ROLE_ID == 0:
        print("오류: ROLE_ID 환경변수가 설정되지 않았습니다.")
    else:
        bot.run(TOKEN)
