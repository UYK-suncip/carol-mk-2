import discord
from discord import app_commands
from discord.ext import commands
import json
import os
from datetime import datetime
from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
GUILD_ID = 1279004325028302848
ROLE_ID = 1279004669062021201
VERIFY_ROLE_ID = 1279009654738911242

DATA_FILE = "members.json"
COUNTRIES_FILE = "countries.json"
VERIFY_CONFIG_FILE = "verify_config.json"
WELCOME_CONFIG_FILE = "welcome_config.json"

COLOR_MAP = {
    "초록": discord.Color.green(),
    "빨강": discord.Color.red(),
    "파랑": discord.Color.blue(),
    "금색": discord.Color.gold(),
    "보라": discord.Color.purple(),
    "주황": discord.Color.orange(),
    "기본": discord.Color.blurple(),
}

intents = discord.Intents.default()
intents.members = True
intents.reactions = True

bot = commands.Bot(command_prefix="!", intents=intents)

# ── 데이터 로드/저장 ──────────────────────────────────────────


def load_members():
    if not os.path.exists(DATA_FILE):
        return {}
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_members(data):
    with open(DATA_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_countries():
    if not os.path.exists(COUNTRIES_FILE):
        return []
    with open(COUNTRIES_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return data
    # 카테고리 딕셔너리인 경우 평탄화
    result = []
    for countries in data.values():
        result.extend(countries)
    return result


def load_countries_by_category():
    if not os.path.exists(COUNTRIES_FILE):
        return {}
    with open(COUNTRIES_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    if isinstance(data, list):
        return {"전체": data}
    return data


def get_available_countries():
    all_countries = load_countries()
    members = load_members()
    taken = {info.get("국가") for info in members.values()}
    return [c for c in all_countries if c not in taken]


def get_available_by_category():
    categories = load_countries_by_category()
    members = load_members()
    taken = {info.get("국가") for info in members.values()}
    result = {}
    for cat, countries in categories.items():
        available = [c for c in countries if c not in taken]
        if available:
            result[cat] = available
    return result


def load_verify_config():
    if not os.path.exists(VERIFY_CONFIG_FILE):
        return {}
    with open(VERIFY_CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_verify_config(data):
    with open(VERIFY_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_welcome_config():
    if not os.path.exists(WELCOME_CONFIG_FILE):
        return {}
    with open(WELCOME_CONFIG_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def save_welcome_config(data):
    with open(WELCOME_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def format_message(template: str, member: discord.Member) -> str:
    return (
        template.replace("{user}", member.mention)
        .replace("{username}", member.display_name)
        .replace("{server}", member.guild.name)
        .replace("{count}", str(member.guild.member_count))
    )


def build_embed(cfg: dict, member: discord.Member) -> discord.Embed:
    color = COLOR_MAP.get(cfg.get("color", "기본"), discord.Color.blurple())
    embed = discord.Embed(
        title=format_message(cfg.get("title", ""), member),
        description=format_message(cfg.get("message", ""), member),
        color=color,
    )
    embed.set_thumbnail(url=member.display_avatar.url)
    embed.set_footer(text=format_message(cfg.get("footer", "{server}"), member))
    return embed


# ── 입장/퇴장 설정 모달 ──────────────────────────────────────


class WelcomeSetupModal(discord.ui.Modal):
    def __init__(self, kind: str, channel_id: int, existing: dict):
        label = "입장" if kind == "welcome" else "퇴장"
        super().__init__(title=f"{label} 메시지 설정")
        self.kind = kind
        self.channel_id = channel_id

        self.title_input = discord.ui.TextInput(
            label="제목",
            default=existing.get(
                "title", "환영합니다!" if kind == "welcome" else "퇴장"
            ),
            required=True,
            max_length=100,
        )
        self.message_input = discord.ui.TextInput(
            label="본문 ({user} {username} {server} {count} 사용 가능)",
            style=discord.TextStyle.paragraph,
            default=existing.get(
                "message",
                "{user}님이 입장하셨습니다. 현재 {count}명!"
                if kind == "welcome"
                else "{username}님이 서버를 떠났습니다.",
            ),
            required=True,
            max_length=500,
        )
        self.footer_input = discord.ui.TextInput(
            label="푸터 (선택)",
            default=existing.get("footer", "{server}"),
            required=False,
            max_length=100,
        )
        self.color_input = discord.ui.TextInput(
            label="색상 (초록/빨강/파랑/금색/보라/주황/기본)",
            default=existing.get("color", "초록" if kind == "welcome" else "빨강"),
            required=False,
            max_length=10,
        )
        self.add_item(self.title_input)
        self.add_item(self.message_input)
        self.add_item(self.footer_input)
        self.add_item(self.color_input)

    async def on_submit(self, interaction: discord.Interaction):
        color = self.color_input.value.strip() if self.color_input.value else "기본"
        if color not in COLOR_MAP:
            color = "기본"

        cfg = load_welcome_config()
        cfg[self.kind] = {
            "channel_id": self.channel_id,
            "title": self.title_input.value,
            "message": self.message_input.value,
            "footer": self.footer_input.value or "{server}",
            "color": color,
        }
        save_welcome_config(cfg)

        kind_label = "입장" if self.kind == "welcome" else "퇴장"
        channel = interaction.guild.get_channel(self.channel_id)
        ch_mention = channel.mention if channel else f"(ID: {self.channel_id})"

        await interaction.response.send_message(
            f"✅ **{kind_label} 메시지** 설정 완료!\n"
            f"> 📢 채널: {ch_mention}\n"
            f"> 📌 제목: {self.title_input.value}\n"
            f"> 💬 본문: {self.message_input.value[:80]}{'...' if len(self.message_input.value) > 80 else ''}\n"
            f"> 🎨 색상: {color}",
            ephemeral=True,
        )
        print(f"[{kind_label}메시지설정] 채널={self.channel_id} 색상={color}")


# ── 모달: 닉네임 + 플레이타임 ────────────────────────────────


class InfoModal(discord.ui.Modal, title="참여 정보 입력"):
    인게임닉네임 = discord.ui.TextInput(
        label="인게임 닉네임",
        placeholder="호이4 내에서 사용하는 닉네임을 입력하세요",
        required=True,
        max_length=64,
    )
    플레이타임 = discord.ui.TextInput(
        label="플레이타임 (선택)",
        placeholder="예) 500시간, 1000시간 ...",
        required=False,
        max_length=50,
    )

    def __init__(self, selected_country: str):
        super().__init__()
        self.selected_country = selected_country

    async def on_submit(self, interaction: discord.Interaction):
        user = interaction.user
        members = load_members()

        if str(user.id) in members:
            await interaction.response.send_message(
                f"⚠️ **{user.display_name}**님은 이미 참여하셨습니다!", ephemeral=True
            )
            return

        # 국가 중복 재확인 (동시 접근 방지)
        taken = {info.get("국가") for info in members.values()}
        if self.selected_country in taken:
            await interaction.response.send_message(
                f"❌ **{self.selected_country}** 는 방금 다른 분이 선택하셨습니다. 다시 시도해주세요.",
                ephemeral=True,
            )
            return

        members[str(user.id)] = {
            "id": user.id,
            "username": user.name,
            "display_name": user.display_name,
            "국가": self.selected_country,
            "인게임닉네임": self.인게임닉네임.value,
            "플레이타임": self.플레이타임.value if self.플레이타임.value else "미입력",
            "joined_at": datetime.now().isoformat(),
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
                f"> 🌍 국가: {self.selected_country}\n"
                f"> 🎮 닉네임: {self.인게임닉네임.value}\n"
                f"> ⏱️ 플레이타임: {self.플레이타임.value or '미입력'}",
                ephemeral=True,
            )
            print(
                f"[역할 지급] {user.name} ({user.id}) 국가={self.selected_country} 닉네임={self.인게임닉네임.value}"
            )
        except discord.Forbidden:
            await interaction.response.send_message(
                "❌ 봇에게 역할 지급 권한이 없습니다. 관리자에게 문의해주세요.",
                ephemeral=True,
            )
        except Exception as e:
            await interaction.response.send_message(
                f"❌ 오류 발생: {e}", ephemeral=True
            )


# ── 드롭다운: 국가 선택 (페이지 지원) ────────────────────────

PAGE_SIZE = 25


class CountrySelect(discord.ui.Select):
    def __init__(self, countries: list[str]):
        options = [discord.SelectOption(label=c) for c in countries]
        super().__init__(
            placeholder="국가를 선택하세요", options=options, min_values=1, max_values=1
        )

    async def callback(self, interaction: discord.Interaction):
        selected = self.values[0]
        await interaction.response.send_modal(InfoModal(selected))


class CountryView(discord.ui.View):
    def __init__(self, available: list[str], page: int = 0):
        super().__init__(timeout=60)
        self.available = available
        self.page = page
        self._build(page)

    def _build(self, page: int):
        self.clear_items()
        start = page * PAGE_SIZE
        end = start + PAGE_SIZE
        chunk = self.available[start:end]
        self.add_item(CountrySelect(chunk))

        if page > 0:
            prev_btn = discord.ui.Button(
                label="◀ 이전", style=discord.ButtonStyle.secondary
            )

            async def prev_cb(interaction: discord.Interaction):
                new_view = CountryView(self.available, page - 1)
                await interaction.response.edit_message(
                    content=new_view._header(),
                    view=new_view
                )

            prev_btn.callback = prev_cb
            self.add_item(prev_btn)

        if end < len(self.available):
            next_btn = discord.ui.Button(
                label="다음 ▶", style=discord.ButtonStyle.secondary
            )

            async def next_cb(interaction: discord.Interaction):
                new_view = CountryView(self.available, page + 1)
                await interaction.response.edit_message(
                    content=new_view._header(),
                    view=new_view
                )

            next_btn.callback = next_cb
            self.add_item(next_btn)

    def _header(self) -> str:
        total = len(self.available)
        start = self.page * PAGE_SIZE + 1
        end = min((self.page + 1) * PAGE_SIZE, total)
        return (
            f"🌍 **선택 가능한 국가** ({total}개 남음) — {start}~{end}번\n"
            "아래 드롭다운에서 원하는 국가를 선택하면 추가 정보 입력창이 열립니다."
        )

    async def on_timeout(self):
        for item in self.children:
            item.disabled = True


# ── 수정용 모달: 닉네임 + 플레이타임 (현재값 pre-fill) ──────────


class EditInfoModal(discord.ui.Modal, title="정보 수정"):
    def __init__(self, target_id: str, info: dict):
        super().__init__()
        self.target_id = target_id
        self.info = info

        current_pt = info.get("플레이타임", "")
        if current_pt == "미입력":
            current_pt = ""

        self.닉네임_input = discord.ui.TextInput(
            label="인게임 닉네임",
            default=info.get("인게임닉네임", ""),
            required=True,
            max_length=64,
        )
        self.플레이타임_input = discord.ui.TextInput(
            label="플레이타임 (선택)",
            default=current_pt,
            required=False,
            max_length=50,
        )
        self.add_item(self.닉네임_input)
        self.add_item(self.플레이타임_input)

    async def on_submit(self, interaction: discord.Interaction):
        members = load_members()
        if self.target_id not in members:
            await interaction.followup.send (
                "❌ 해당 유저가 목록에 없습니다.", ephemeral=True
            )
            return

        old_nick = members[self.target_id].get("인게임닉네임", "미입력")
        old_pt = members[self.target_id].get("플레이타임", "미입력")

        members[self.target_id]["인게임닉네임"] = self.닉네임_input.value
        members[self.target_id]["플레이타임"] = (
            self.플레이타임_input.value if self.플레이타임_input.value else "미입력"
        )
        save_members(members)

        new_nick = members[self.target_id]["인게임닉네임"]
        new_pt = members[self.target_id]["플레이타임"]
        name = members[self.target_id]["display_name"]
        print(
            f"[수정] {name} ({self.target_id}) 닉네임={old_nick}→{new_nick} 플레이타임={old_pt}→{new_pt}"
        )

        await interaction.followup.send (
            f"✅ **{name}** 님의 정보가 수정되었습니다!\n"
            f"> 🎮 닉네임: {old_nick} → **{new_nick}**\n"
            f"> ⏱️ 플레이타임: {old_pt} → **{new_pt}**",
            ephemeral=True,
        )


# ── 수정용 국가 드롭다운 ──────────────────────────────────────


class EditCountrySelect(discord.ui.Select):
    def __init__(self, target_id: str, info: dict, countries: list[str]):
        self.target_id = target_id
        self.info = info
        current = info.get("국가", "")
        options = [
            discord.SelectOption(
                label=c,
                description="현재 선택된 국가" if c == current else None,
            )
            for c in countries
        ]
        super().__init__(
            placeholder="새 국가를 선택하세요",
            options=options,
            min_values=1,
            max_values=1,
        )

    async def callback(self, interaction: discord.Interaction):
        new_country = self.values[0]
        old_country = self.info.get("국가", "미입력")
        members = load_members()

        if self.target_id not in members:
            await interaction.response.edit_message(
                content="❌ 해당 유저가 목록에 없습니다.", view=None
            )
            return

        if new_country != old_country:
            taken = {
                inf.get("국가") for uid, inf in members.items() if uid != self.target_id
            }
            if new_country in taken:
                await interaction.followup.send(
                    f"❌ **{new_country}** 는 이미 다른 분이 선택하셨습니다.",
                    ephemeral=True,
                )
                return

        members[self.target_id]["국가"] = new_country
        save_members(members)
        name = members[self.target_id]["display_name"]
        print(f"[수정] {name} ({self.target_id}) 국가={old_country}→{new_country}")

        await interaction.response.edit_message(
            content=f"✅ **{name}** 님의 국가가 **{old_country}** → **{new_country}** 로 변경되었습니다!",
            view=None,
        )


class EditCountryView(discord.ui.View):
    def __init__(self, target_id: str, info: dict, available: list[str], page: int = 0):
        super().__init__(timeout=60)
        self.target_id = target_id
        self.info = info
        self.available = available
        self.page = page
        self._build(page)

    def _build(self, page: int):
        self.clear_items()
        start = page * PAGE_SIZE
        end = start + PAGE_SIZE
        chunk = self.available[start:end]
        self.add_item(EditCountrySelect(self.target_id, self.info, chunk))

        if page > 0:
            prev_btn = discord.ui.Button(
                label="◀ 이전", style=discord.ButtonStyle.secondary
            )

            async def prev_cb(interaction: discord.Interaction):
                new_view = EditCountryView(
                    self.target_id, self.info, self.available, page - 1
                )
                await interaction.response.edit_message (
                    content=new_view._header(),
                    view=new_view
                )

            prev_btn.callback = prev_cb
            self.add_item(prev_btn)

        if end < len(self.available):
            next_btn = discord.ui.Button(
                label="다음 ▶", style=discord.ButtonStyle.secondary
            )

            async def next_cb(interaction: discord.Interaction):
                new_view = EditCountryView(
                    self.target_id, self.info, self.available, page + 1
                )
                await interaction.response.edit_message(
                    content=new_view._header(),
                    view=new_view
                )

            next_btn.callback = next_cb
            self.add_item(next_btn)

    def _header(self) -> str:
        current = self.info.get("국가", "미입력")
        total = len(self.available)
        start = self.page * PAGE_SIZE + 1
        end = min((self.page + 1) * PAGE_SIZE, total)
        return (
            f"🌍 **국가 변경** (현재: **{current}**) — {total}개 중 {start}~{end}번\n"
            "새로운 국가를 선택하세요:"
        )


# ── 수정 메뉴 View ────────────────────────────────────────────


class EditMenuView(discord.ui.View):
    def __init__(self, target_id: str, info: dict):
        super().__init__(timeout=60)
        self.target_id = target_id
        self.info = info

    @discord.ui.button(label="🌍 국가 변경", style=discord.ButtonStyle.primary)
    async def change_country(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        current_country = self.info.get("국가")
        available = get_available_countries()
        # 현재 국가는 이미 본인이 갖고 있으므로 선택 가능 목록 앞에 추가
        if current_country and current_country not in available:
            available = [current_country] + available

        view = EditCountryView(self.target_id, self.info, available)
        await interaction.response.edit_message(content=view._header(), view=view)

    @discord.ui.button(
        label="🎮 닉네임/플레이타임 변경", style=discord.ButtonStyle.primary
    )
    async def change_info(
        self, interaction: discord.Interaction, button: discord.ui.Button
    ):
        await interaction.response.send_modal(EditInfoModal(self.target_id, self.info))


# ── 봇 이벤트 ─────────────────────────────────────────────────


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


@bot.event
async def on_member_join(member: discord.Member):
    cfg = load_welcome_config().get("welcome")
    if not cfg:
        return
    channel = member.guild.get_channel(cfg["channel_id"])
    if channel is None:
        return
    embed = build_embed(cfg, member)
    await channel.send(embed=embed)
    print(f"[입장] {member.name} ({member.id})")


@bot.event
async def on_member_remove(member: discord.Member):
    cfg = load_welcome_config().get("leave")
    if not cfg:
        return
    channel = member.guild.get_channel(cfg["channel_id"])
    if channel is None:
        return
    embed = build_embed(cfg, member)
    await channel.send(embed=embed)
    print(f"[퇴장] {member.name} ({member.id})")


@bot.event
async def on_raw_reaction_add(payload: discord.RawReactionActionEvent):
    if payload.user_id == bot.user.id:
        return

    config = load_verify_config()
    if not config:
        return

    if payload.message_id != config.get("message_id"):
        return
    if str(payload.emoji) != config.get("emoji"):
        return

    guild = bot.get_guild(payload.guild_id)
    if guild is None:
        return

    role = guild.get_role(VERIFY_ROLE_ID)
    if role is None:
        return

    member = guild.get_member(payload.user_id)
    if member is None:
        return

    if role not in member.roles:
        await member.add_roles(role, reason="이모지 인증")
        print(f"[인증] {member.name} ({member.id}) 인증 역할 지급")


@bot.event
async def on_raw_reaction_remove(payload: discord.RawReactionActionEvent):
    if payload.user_id == bot.user.id:
        return

    config = load_verify_config()
    if not config:
        return

    if payload.message_id != config.get("message_id"):
        return
    if str(payload.emoji) != config.get("emoji"):
        return

    guild = bot.get_guild(payload.guild_id)
    if guild is None:
        return

    role = guild.get_role(VERIFY_ROLE_ID)
    if role is None:
        return

    member = guild.get_member(payload.user_id)
    if member is None:
        return

    if role in member.roles:
        await member.remove_roles(role, reason="이모지 인증 취소")
        print(f"[인증취소] {member.name} ({member.id}) 인증 역할 제거")


# ── 슬래시 명령어 ─────────────────────────────────────────────


@bot.tree.command(name="참여", description="서버에 참여하고 역할을 받습니다.")
async def 참여(interaction: discord.Interaction):

    print("참여 실행됨", interaction.id)

    try:
        # 🔥 무조건 즉시 defer (조건 없이!)
        await interaction.response.defer(ephemeral=True)
    except:
        # 이미 응답됐으면 무시
        pass

    members = load_members()

    if str(interaction.user.id) in members:
        await interaction.followup.send(
            f"⚠️ **{interaction.user.display_name}**님은 이미 참여하셨습니다!",
            ephemeral=True,
        )
        return

    available = get_available_countries()

    if not available:
        await interaction.followup.send(
            "❌ 현재 선택 가능한 국가가 없습니다. 관리자에게 문의해주세요.",
            ephemeral=True,
        )
        return

    view = CountryView(available)

    await interaction.followup.send(
        view._header(),
        view=view,
        ephemeral=True
    )

@bot.tree.command(
    name="남은국가",
    description="아직 선택되지 않은 국가 목록을 카테고리별로 보여줍니다.",
)
async def 남은국가(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)  # 🔥 추가
    all_countries = load_countries()
    available_by_cat = get_available_by_category()
    available_total = sum(len(v) for v in available_by_cat.values())
    taken_count = len(all_countries) - available_total

    if not all_countries:
        await interaction.followup.send(
            "❌ 국가 목록 파일이 비어 있습니다.", ephemeral=True
        )
        return

    if not available_by_cat:
        await interaction.followup.send(
            f"🌍 모든 국가가 선택되었습니다! (총 {len(all_countries)}개)",
            ephemeral=True,
        )
        return

    lines = [
        f"🌍 **선택 가능한 국가** ({available_total}개 남음 / 전체 {len(all_countries)}개, {taken_count}개 선택됨)\n"
    ]
    for cat, countries in available_by_cat.items():
        lines.append(f"**[ {cat} ]**")
        lines.append("  " + "  /  ".join(countries))

    message = "\n".join(lines)
    if len(message) > 2000:
        message = message[:1990] + "\n..."

    await interaction.followup.send(message)


@bot.tree.command(
    name="목록", description="참여한 멤버 목록을 확인합니다. (관리자 전용)"
)
@app_commands.checks.has_permissions(administrator=True)
async def 목록(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)  # 🔥 추가
    members = load_members()

    if not members:
        await interaction.followup.send(
            "📋 아직 참여한 멤버가 없습니다.", ephemeral=True
        )
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

    await interaction.followup.send(message, ephemeral=True)


@bot.tree.command(
    name="역할일괄지급",
    description="JSON에 저장된 모든 멤버에게 역할을 지급합니다. (관리자 전용)",
)
@app_commands.checks.has_permissions(administrator=True)
async def 역할일괄지급(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)
    members = load_members()

    if not members:
        await interaction.followup.send(
            "📋 아직 참여한 멤버가 없습니다.", ephemeral=True
        )
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
        f"✅ 일괄 지급 완료!\n성공: {success}명 / 실패: {failed}명", ephemeral=True
    )


@bot.tree.command(
    name="제거", description="특정 유저를 목록에서 제거합니다. (관리자 전용)"
)
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(유저id="제거할 유저의 ID")
async def 제거(interaction: discord.Interaction, 유저id: str):
    await interaction.response.defer(ephemeral=True)  # 🔥 추가
    members = load_members()

    if 유저id not in members:
        await interaction.followup.send(
            f"⚠️ ID `{유저id}` 는 목록에 없습니다.", ephemeral=True
        )
        return

    info = members.pop(유저id)
    save_members(members)
    print(f"[제거] {info['display_name']} ({유저id}) 목록에서 제거됨")

    await interaction.followup.send(
        f"🗑️ **{info['display_name']}** (`{유저id}`) 님이 목록에서 제거되었습니다. "
        f"(국가 **{info.get('국가', '미입력')}** 반환됨)",
        ephemeral=True,
    )

    user = interaction.user

    guild = interaction.guild
    role = guild.get_role(ROLE_ID)

    try:
        await user.remove_roles(role, reason="슬래시 명령어 /제거 사용")

    except Exception as e:
        await interaction.followup.send(f"❌ 오류 발생: {e}", ephemeral=True)


@bot.tree.command(
    name="일괄제거", description="목록의 모든 멤버를 제거합니다. (관리자 전용)"
)
@app_commands.checks.has_permissions(administrator=True)
async def 일괄제거(interaction: discord.Interaction):
    await interaction.response.defer(ephemeral=True)  # 🔥 추가
    members = load_members()

    if not members:
        await interaction.followup.send(
            "📋 목록이 이미 비어 있습니다.", ephemeral=True
        )
        return

    count = len(members)
    save_members({})
    print(f"[일괄제거] 총 {count}명 목록에서 제거됨")

    await interaction.followup.send(
        f"🗑️ 총 **{count}명** 의 멤버가 목록에서 제거되었습니다. (모든 국가 반환됨)",
        ephemeral=True,
    )


@bot.tree.command(
    name="입장메시지설정",
    description="멤버 입장 시 전송할 메시지를 설정합니다. (관리자 전용)",
)
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(채널="입장 메시지를 보낼 채널")
async def 입장메시지설정(interaction: discord.Interaction, 채널: discord.TextChannel):
    cfg = load_welcome_config()
    existing = cfg.get("welcome", {})
    existing["channel_id"] = 채널.id
    modal = WelcomeSetupModal("welcome", 채널.id, existing)
    await interaction.response.send_modal(modal)


@bot.tree.command(
    name="퇴장메시지설정",
    description="멤버 퇴장 시 전송할 메시지를 설정합니다. (관리자 전용)",
)
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(채널="퇴장 메시지를 보낼 채널")
async def 퇴장메시지설정(interaction: discord.Interaction, 채널: discord.TextChannel):
    cfg = load_welcome_config()
    existing = cfg.get("leave", {})
    existing["channel_id"] = 채널.id
    modal = WelcomeSetupModal("leave", 채널.id, existing)
    await interaction.response.send_modal(modal)


@bot.tree.command(
    name="인증설정",
    description="이모지 인증 메시지를 이 채널에 전송합니다. (관리자 전용)",
)
@app_commands.checks.has_permissions(administrator=True)
@app_commands.describe(
    이모지="인증에 사용할 이모지 (기본값: ✅)",
    제목="인증 메시지 제목 (기본값: 서버 인증)",
    설명="인증 메시지 본문 (기본값: 아래 이모지를 클릭하여 인증하세요.)",
)
async def 인증설정(
    interaction: discord.Interaction,
    이모지: str = "✅",
    제목: str = "서버 인증",
    설명: str = "아래 이모지를 클릭하여 인증하세요.",
):
    if VERIFY_ROLE_ID == 0:
        await interaction.response.send_message(
            "❌ VERIFY_ROLE_ID 환경변수가 설정되지 않았습니다.", ephemeral=True
        )
        return

    embed = discord.Embed(
        title=f"🔐 {제목}",
        description=f"{설명}\n\n{이모지} 이모지를 눌러 **인증**하세요.",
        color=discord.Color.green(),
    )
    embed.set_footer(text="반응을 취소하면 인증이 해제됩니다.")

    await interaction.response.send_message(
        "✅ 인증 메시지를 전송했습니다.", ephemeral=True
    )
    msg = await interaction.channel.send(embed=embed)
    await msg.add_reaction(이모지)

    save_verify_config(
        {
            "channel_id": interaction.channel.id,
            "message_id": msg.id,
            "emoji": 이모지,
        }
    )
    print(f"[인증설정] 채널={interaction.channel.id} 메시지={msg.id} 이모지={이모지}")


@bot.tree.command(
    name="수정",
    description="참여 정보를 수정합니다. 관리자는 유저ID를 지정할 수 있습니다.",
)
@app_commands.describe(유저id="수정할 유저의 ID (관리자 전용, 생략 시 본인)")
async def 수정(interaction: discord.Interaction, 유저id: str = None):
    await interaction.response.defer(ephemeral=True)  # 🔥 추가
    members = load_members()
    is_admin = interaction.user.guild_permissions.administrator

    if 유저id:
        if not is_admin:
            await interaction.followup.send(
                "❌ 다른 유저의 정보는 관리자만 수정할 수 있습니다.", ephemeral=True
            )
            return
        target_id = 유저id
    else:
        target_id = str(interaction.user.id)

    if target_id not in members:
        await interaction.followup.send(
            "⚠️ 해당 유저는 참여 목록에 없습니다.", ephemeral=True
        )
        return

    info = members[target_id]
    view = EditMenuView(target_id, info)
    await interaction.followup.send(
        f"✏️ **{info['display_name']}** 님의 현재 정보\n"
        f"> 🌍 국가: {info.get('국가', '미입력')}\n"
        f"> 🎮 닉네임: {info.get('인게임닉네임', '미입력')}\n"
        f"> ⏱️ 플레이타임: {info.get('플레이타임', '미입력')}\n\n"
        "수정할 항목을 선택하세요:",
        view=view,
        ephemeral=True,
    )


@목록.error
@역할일괄지급.error
@제거.error
@일괄제거.error
@인증설정.error
@입장메시지설정.error
@퇴장메시지설정.error
async def permission_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.followup.send(
            "❌ 관리자만 사용할 수 있는 명령어입니다.", ephemeral=True
        )


if __name__ == "__main__":
    if not TOKEN:
        print("오류: DISCORD_TOKEN 환경변수가 설정되지 않았습니다.")
    elif GUILD_ID == 0:
        print("오류: DISCORD_GUILD_ID 환경변수가 설정되지 않았습니다.")
    elif ROLE_ID == 0:
        print("오류: ROLE_ID 환경변수가 설정되지 않았습니다.")
    else:
        bot.run(TOKEN)
