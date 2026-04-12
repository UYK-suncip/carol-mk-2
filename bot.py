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
COUNTRIES_FILE = "countries.json"

intents = discord.Intents.default()
intents.members = True

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
                    content=new_view._header(), view=new_view
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
                    content=new_view._header(), view=new_view
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
            await interaction.response.send_message(
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
        print(f"[수정] {name} ({self.target_id}) 닉네임={old_nick}→{new_nick} 플레이타임={old_pt}→{new_pt}")

        await interaction.response.send_message(
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
            placeholder="새 국가를 선택하세요", options=options, min_values=1, max_values=1
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
                inf.get("국가")
                for uid, inf in members.items()
                if uid != self.target_id
            }
            if new_country in taken:
                await interaction.response.send_message(
                    f"❌ **{new_country}** 는 이미 다른 분이 선택하셨습니다.", ephemeral=True
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
            prev_btn = discord.ui.Button(label="◀ 이전", style=discord.ButtonStyle.secondary)

            async def prev_cb(interaction: discord.Interaction):
                new_view = EditCountryView(self.target_id, self.info, self.available, page - 1)
                await interaction.response.edit_message(content=new_view._header(), view=new_view)

            prev_btn.callback = prev_cb
            self.add_item(prev_btn)

        if end < len(self.available):
            next_btn = discord.ui.Button(label="다음 ▶", style=discord.ButtonStyle.secondary)

            async def next_cb(interaction: discord.Interaction):
                new_view = EditCountryView(self.target_id, self.info, self.available, page + 1)
                await interaction.response.edit_message(content=new_view._header(), view=new_view)

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

    @discord.ui.button(label="🎮 닉네임/플레이타임 변경", style=discord.ButtonStyle.primary)
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


# ── 슬래시 명령어 ─────────────────────────────────────────────


@bot.tree.command(name="참여", description="서버에 참여하고 역할을 받습니다.")
async def 참여(interaction: discord.Interaction):
    members = load_members()
    if str(interaction.user.id) in members:
        await interaction.response.send_message(
            f"⚠️ **{interaction.user.display_name}**님은 이미 참여하셨습니다!",
            ephemeral=True,
        )
        return

    available = get_available_countries()
    if not available:
        await interaction.response.send_message(
            "❌ 현재 선택 가능한 국가가 없습니다. 관리자에게 문의해주세요.",
            ephemeral=True,
        )
        return

    view = CountryView(available)
    await interaction.response.send_message(view._header(), view=view, ephemeral=True)


@bot.tree.command(
    name="남은국가",
    description="아직 선택되지 않은 국가 목록을 카테고리별로 보여줍니다.",
)
async def 남은국가(interaction: discord.Interaction):
    all_countries = load_countries()
    available_by_cat = get_available_by_category()
    available_total = sum(len(v) for v in available_by_cat.values())
    taken_count = len(all_countries) - available_total

    if not all_countries:
        await interaction.response.send_message(
            "❌ 국가 목록 파일이 비어 있습니다.", ephemeral=True
        )
        return

    if not available_by_cat:
        await interaction.response.send_message(
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

    await interaction.response.send_message(message)


@bot.tree.command(
    name="목록", description="참여한 멤버 목록을 확인합니다. (관리자 전용)"
)
@app_commands.checks.has_permissions(administrator=True)
async def 목록(interaction: discord.Interaction):
    members = load_members()

    if not members:
        await interaction.response.send_message(
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

    await interaction.response.send_message(message, ephemeral=True)


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
        f"🗑️ **{info['display_name']}** (`{유저id}`) 님이 목록에서 제거되었습니다. "
        f"(국가 **{info.get('국가', '미입력')}** 반환됨)",
        ephemeral=True,
    )


@bot.tree.command(
    name="일괄제거", description="목록의 모든 멤버를 제거합니다. (관리자 전용)"
)
@app_commands.checks.has_permissions(administrator=True)
async def 일괄제거(interaction: discord.Interaction):
    members = load_members()

    if not members:
        await interaction.response.send_message(
            "📋 목록이 이미 비어 있습니다.", ephemeral=True
        )
        return

    count = len(members)
    save_members({})
    print(f"[일괄제거] 총 {count}명 목록에서 제거됨")

    await interaction.response.send_message(
        f"🗑️ 총 **{count}명** 의 멤버가 목록에서 제거되었습니다. (모든 국가 반환됨)",
        ephemeral=True,
    )


@bot.tree.command(name="수정", description="참여 정보를 수정합니다. 관리자는 유저ID를 지정할 수 있습니다.")
@app_commands.describe(유저id="수정할 유저의 ID (관리자 전용, 생략 시 본인)")
async def 수정(interaction: discord.Interaction, 유저id: str = None):
    members = load_members()
    is_admin = interaction.user.guild_permissions.administrator

    if 유저id:
        if not is_admin:
            await interaction.response.send_message(
                "❌ 다른 유저의 정보는 관리자만 수정할 수 있습니다.", ephemeral=True
            )
            return
        target_id = 유저id
    else:
        target_id = str(interaction.user.id)

    if target_id not in members:
        await interaction.response.send_message(
            "⚠️ 해당 유저는 참여 목록에 없습니다.", ephemeral=True
        )
        return

    info = members[target_id]
    view = EditMenuView(target_id, info)
    await interaction.response.send_message(
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
async def permission_error(interaction: discord.Interaction, error):
    if isinstance(error, app_commands.MissingPermissions):
        await interaction.response.send_message(
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
