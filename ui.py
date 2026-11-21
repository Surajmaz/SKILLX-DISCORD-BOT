"""Interactive Discord UI Components: Pagination, Confirmation, Translation, and Text Chunking."""

import re
import discord
from typing import Optional, Union, Any
from embeds import ai_response_embed


def split_response_into_pages(text: str, max_chars: int = 3800) -> list[str]:
    """
    Intelligently chunks text into pages preserving markdown code block syntax.
    If a page split occurs inside a fenced code block, it properly closes the block
    at the page end and reopens it on the subsequent page.
    """
    if len(text) <= max_chars:
        return [text]

    lines = text.split("\n")
    pages = []
    current_page = []
    current_len = 0
    in_code_block = False
    code_lang = ""

    for line in lines:
        line_len = len(line) + 1  # includes newline
        stripped = line.strip()

        # Check if line contains a code fence
        is_fence = stripped.startswith("```")
        if current_len + line_len > max_chars and current_page:
            if in_code_block:
                current_page.append("```")
            pages.append("\n".join(current_page))
            current_page = []
            current_len = 0
            if in_code_block:
                current_page.append(f"```{code_lang}")
                current_len += len(code_lang) + 4

        if is_fence:
            if not in_code_block:
                in_code_block = True
                code_lang = stripped[3:].strip()
            else:
                in_code_block = False
                code_lang = ""

        current_page.append(line)
        current_len += line_len

    if current_page:
        pages.append("\n".join(current_page))

    return pages or [text]


class PaginatedResponseView(discord.ui.View):
    """Interactive paginator view with prev/next navigation, page indicator, and timeout protection."""

    def __init__(
        self,
        pages: list[str],
        author_id: int,
        prompt: str,
        model: str,
        timeout: float = 180.0,
        elapsed_ms: Optional[int] = None,
    ):
        super().__init__(timeout=timeout)
        self.pages = pages
        self.current_page = 0
        self.author_id = author_id
        self.prompt = prompt
        self.model = model
        self.elapsed_ms = elapsed_ms
        self.message: Optional[Union[discord.Message, discord.WebhookMessage]] = None
        self._update_buttons()

    def _update_buttons(self) -> None:
        self.prev_button.disabled = self.current_page == 0
        self.page_indicator.label = f"{self.current_page + 1} / {len(self.pages)}"
        self.next_button.disabled = self.current_page >= len(self.pages) - 1

    def build_embed(self) -> discord.Embed:
        page_info = f"Page {self.current_page + 1}/{len(self.pages)}"
        return ai_response_embed(
            prompt=self.prompt,
            response=self.pages[self.current_page],
            model_used=self.model,
            page_info=page_info,
            elapsed_ms=self.elapsed_ms,
        )

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "❌ Only the command author can control this pagination.", ephemeral=True
            )
            return False
        return True

    async def on_timeout(self) -> None:
        for child in self.children:
            child.disabled = True
        if self.message:
            try:
                await self.message.edit(view=self)
            except (discord.NotFound, discord.HTTPException):
                pass

    @discord.ui.button(label="◀ Prev", style=discord.ButtonStyle.secondary, row=0)
    async def prev_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = max(0, self.current_page - 1)
        self._update_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="1 / 1", style=discord.ButtonStyle.secondary, disabled=True, row=0)
    async def page_indicator(self, interaction: discord.Interaction, button: discord.ui.Button):
        # Displays page count, non-interactive
        pass

    @discord.ui.button(label="Next ▶", style=discord.ButtonStyle.secondary, row=0)
    async def next_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.current_page = min(len(self.pages) - 1, self.current_page + 1)
        self._update_buttons()
        await interaction.response.edit_message(embed=self.build_embed(), view=self)

    @discord.ui.button(label="Translate", style=discord.ButtonStyle.primary, emoji="🌐", row=0)
    async def translate_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed = self.build_embed()
        view = LanguageSelectView(embed, interaction.client, interaction.user.id)
        prompt_embed = discord.Embed(
            title="🌐 Translate Response with Gemini AI",
            description=(
                "**Select your preferred language from the dropdown menu below.**\n\n"
                "• Powered by **Google Gemini AI** with multi-tier fallback resilience.\n"
                "• **Privacy Guaranteed:** This translation pop-up is completely private and visible only to you."
            ),
            color=0x6C5CE7,
        )
        prompt_embed.set_footer(text="Select a language below to begin instant AI translation")
        await interaction.response.send_message(embed=prompt_embed, view=view, ephemeral=True)
    @discord.ui.button(label="🗑️", style=discord.ButtonStyle.danger, row=0)
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.stop()
        await interaction.message.delete()


class ConfirmView(discord.ui.View):
    """Reusable two-button confirmation view (Confirm / Cancel)."""

    def __init__(self, author_id: int, timeout: float = 45.0):
        super().__init__(timeout=timeout)
        self.author_id = author_id
        self.value: Optional[bool] = None
        self.message: Optional[Union[discord.Message, discord.WebhookMessage]] = None

    async def interaction_check(self, interaction: discord.Interaction) -> bool:
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "❌ You do not have permission to confirm this action.", ephemeral=True
            )
            return False
        return True

    def _disable_all(self) -> None:
        for child in self.children:
            child.disabled = True

    async def on_timeout(self) -> None:
        self.value = False
        self._disable_all()
        if self.message:
            try:
                await self.message.edit(view=self)
            except (discord.NotFound, discord.HTTPException):
                pass

    @discord.ui.button(label="Confirm", style=discord.ButtonStyle.success, emoji="✅")
    async def confirm(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = True
        self._disable_all()
        self.stop()
        await interaction.response.edit_message(view=self)

    @discord.ui.button(label="Cancel", style=discord.ButtonStyle.secondary, emoji="❌")
    async def cancel(self, interaction: discord.Interaction, button: discord.ui.Button):
        self.value = False
        self._disable_all()
        self.stop()
        await interaction.response.edit_message(view=self)


# =========================================================
# MULTI-LANGUAGE TRANSLATION & FEATURE EXPLORER SYSTEM
# =========================================================

SUPPORTED_LANGUAGES: list[dict[str, str]] = [
    {
        "code": "es",
        "name": "Spanish",
        "native": "Español",
        "desc": "Español de España y Latinoamérica",
        "emoji": "🇪🇸",
    },
    {
        "code": "fr",
        "name": "French",
        "native": "Français",
        "desc": "Français standard et international",
        "emoji": "🇫🇷",
    },
    {
        "code": "de",
        "name": "German",
        "native": "Deutsch",
        "desc": "Standarddeutsch für Deutschland, Österreich, Schweiz",
        "emoji": "🇩🇪",
    },
    {
        "code": "hi",
        "name": "Hindi",
        "native": "हिन्दी",
        "desc": "भारत की आधिकारिक भाषा (हिंदी अनुवाद)",
        "emoji": "🇮🇳",
    },
    {
        "code": "ja",
        "name": "Japanese",
        "native": "日本語",
        "desc": "日本語の自然な翻訳とコマンド案内",
        "emoji": "🇯🇵",
    },
    {
        "code": "zh-cn",
        "name": "Simplified Chinese",
        "native": "简体中文",
        "desc": "简体中文，支持中国大陆与全球华人",
        "emoji": "🇨🇳",
    },
    {
        "code": "zh-tw",
        "name": "Traditional Chinese",
        "native": "繁體中文",
        "desc": "繁體中文，支持台灣與香港地區",
        "emoji": "🇹🇼",
    },
    {
        "code": "pt",
        "name": "Portuguese",
        "native": "Português",
        "desc": "Português do Brasil e de Portugal",
        "emoji": "🇧🇷",
    },
    {
        "code": "ru",
        "name": "Russian",
        "native": "Русский",
        "desc": "Русский язык и руководство по боту",
        "emoji": "🇷🇺",
    },
    {
        "code": "ar",
        "name": "Arabic",
        "native": "العربية",
        "desc": "العربية الفصحى ودليل الأوامر الكامل",
        "emoji": "🇸🇦",
    },
    {
        "code": "it",
        "name": "Italian",
        "native": "Italiano",
        "desc": "Lingua italiana per la community",
        "emoji": "🇮🇹",
    },
    {
        "code": "ko",
        "name": "Korean",
        "native": "한국어",
        "desc": "한국어 자연스러운 번역 및 명령어 안내",
        "emoji": "🇰🇷",
    },
    {
        "code": "id",
        "name": "Indonesian",
        "native": "Bahasa Indonesia",
        "desc": "Bahasa Indonesia untuk komunitas",
        "emoji": "🇮🇩",
    },
    {
        "code": "tr",
        "name": "Turkish",
        "native": "Türkçe",
        "desc": "Türkçe komut rehberi ve bot özellikleri",
        "emoji": "🇹🇷",
    },
    {
        "code": "vi",
        "name": "Vietnamese",
        "native": "Tiếng Việt",
        "desc": "Tiếng Việt cho cộng đồng người dùng",
        "emoji": "🇻🇳",
    },
    {
        "code": "bn",
        "name": "Bengali",
        "native": "বাংলা",
        "desc": "বাংলা ভাষা এবং সম্পূর্ণ কমান্ড নির্দেশিকা",
        "emoji": "🇧🇩",
    },
    {
        "code": "tl",
        "name": "Tagalog",
        "native": "Filipino",
        "desc": "Wikang Filipino para sa komunidad",
        "emoji": "🇵🇭",
    },
    {
        "code": "pl",
        "name": "Polish",
        "native": "Polski",
        "desc": "Język polski i przewodnik po funkcjach",
        "emoji": "🇵🇱",
    },
    {
        "code": "nl",
        "name": "Dutch",
        "native": "Nederlands",
        "desc": "Nederlandse taal en handleiding",
        "emoji": "🇳🇱",
    },
    {
        "code": "uk",
        "name": "Ukrainian",
        "native": "Українська",
        "desc": "Українська мова та опис команд",
        "emoji": "🇺🇦",
    },
    {
        "code": "sv",
        "name": "Swedish",
        "native": "Svenska",
        "desc": "Svenska för den nordiska gemenskapen",
        "emoji": "🇸🇪",
    },
    {
        "code": "el",
        "name": "Greek",
        "native": "Ελληνικά",
        "desc": "Ελληνική γλώσσα και οδηγός εντολών",
        "emoji": "🇬🇷",
    },
    {
        "code": "th",
        "name": "Thai",
        "native": "ภาษาไทย",
        "desc": "ภาษาไทยและคู่มือการใช้งานบอท",
        "emoji": "🇹🇭",
    },
    {
        "code": "ur",
        "name": "Urdu",
        "native": "اردو",
        "desc": "اردو زبان میں تمام فیچرز اور رہنمائی",
        "emoji": "🇵🇰",
    },
    {
        "code": "en",
        "name": "English",
        "native": "English",
        "desc": "Default English documentation and manual",
        "emoji": "🇬🇧",
    },
]

HELP_CATEGORIES: dict[str, dict] = {
    "overview": {
        "title": "📖 SkillX Command Directory & Feature Guide",
        "desc": (
            "⚡ **Prefix-less & Slash Command Suite**\n"
            "• **Slash Commands:** Type `/` to select from all available commands.\n"
            "• **Conversational AI:** Mention `@SkillX <prompt>` or reply to any bot message.\n"
            "• **Direct Words:** Standard commands like `ping`, `help`, and `serverinfo` work directly without prefixes."
        ),
        "fields": [
            ("🤖 Artificial Intelligence", "`/chat` • `/persona` • `/code` • `/summarize` • `/forget`\n*Conversational Gemini 3.x, code reviews, and chat recaps*", False),
            ("🛡️ Moderation & AutoMod", "`/kick` • `/ban` • `/timeout` • `/purge` • `/warn` • `/warnings` • `/clearwarns` • `/lock` • `/unlock` • `/slowmode`\n*Server safety suite with anti-spam, invite filters, and infractions*", False),
            ("🎉 Community & Engagement", "`/poll` • `/giveaway` • `/remind` • `/avatar`\n*Interactive button polls with live bars, automated giveaways, and timers*", False),
            ("🎮 Fun & Mini-Games", "`/trivia` • `/8ball` • `/coinflip` • `/dice` • `/rps` • `/joke` • `/fact` • `/rate` • `/ship` • `/roast` • `/compliment`\n*Interactive button trivia, dice, roasts, jokes, and games*", False),
            ("📈 Leveling & XP", "`/rank` • `/leaderboard` • `/setxp` • `/resetxp`\n*XP progression, visual rank cards, and competitive leaderboards*", False),
            ("🎫 Support Tickets", "`/ticket-setup` • `/ticket-add` • `/ticket-remove`\n*Channel-based private ticket system with transcript exports*", False),
            ("👋 Welcome & AutoRole", "`/setwelcome` • `/setgoodbye` • `/testwelcome` • `/autorole`\n*Automated join greetings, farewell embeds, and role assignment*", False),
            ("📋 Server Audit Logs", "`/setlogchannel` • `/clearlogchannel`\n*Automatic channel logging for deletes, edits, joins, bans, and voice activity*", False),
            ("🔧 Utilities & System", "`/ping` • `/serverinfo` • `/userinfo` • `/botinfo` • `/stresstest` • `/autoheal` • `/translate` • `/help`\n*Diagnostics, latency graphs, profile inspection, and system stress testing*", False),
        ],
    },
    "ai": {
        "title": "🤖 Artificial Intelligence Feature Guide",
        "desc": "Powered by multi-tier **Google Gemini 3.x / 2.5** models with automatic failover.",
        "fields": [
            ("💬 /chat <prompt>", "Start or continue a multi-turn conversation with memory. Also works by mentioning `@SkillX`.", False),
            ("🎭 /persona <name>", "Switch personality: `helpful`, `developer`, `concise`, `creative`, `sarcastic`, or `academic`.", False),
            ("💻 /code <code> [language]", "In-depth code review, complexity analysis, security vulnerability scan, and refactoring.", False),
            ("📝 /summarize [messages]", "Generate a structured executive summary of recent chat dialogue.", False),
            ("🧹 /forget", "Reset your AI conversational memory session and start fresh.", False),
            ("⚡ /aiping", "Benchmark real-time Gemini AI API generation latency and active model tier.", False),
        ],
    },
    "moderation": {
        "title": "🛡️ Moderation & AutoMod Feature Guide",
        "desc": "Comprehensive server security, automated content filtering, and moderation actions.",
        "fields": [
            ("🔨 /kick <user> [reason]", "Kick a member from the server.", True),
            ("⛔ /ban <user> [reason]", "Permanently ban a member and log infraction.", True),
            ("⏳ /timeout <user> <duration> [reason]", "Temporarily restrict a user from typing or talking.", True),
            ("🧹 /purge <amount>", "Bulk delete up to 100 messages at once.", True),
            ("⚠️ /warn <user> <reason>", "Issue an official warning logged in the infraction database.", True),
            ("📜 /warnings <user>", "View warning history and moderation notes for a member.", True),
            ("🔒 /lock & /unlock", "Lock down or reopen the current channel.", True),
            ("⏱️ /slowmode <seconds>", "Set custom message rate limiting in seconds.", True),
            ("🛡️ AutoMod Engine", "Automatic link filtering, invite blocking, anti-spam, and excessive mention defense.", False),
        ],
    },
    "community": {
        "title": "🎉 Community & Engagement Feature Guide",
        "desc": "Boost server engagement with interactive polls, timed giveaways, and reminders.",
        "fields": [
            ("📊 /poll <question> <options>", "Create rich interactive button polls with real-time percentage progress bars.", False),
            ("🎁 /giveaway <prize> <duration> [winners]", "Automated countdown giveaway with button entry and randomized winner draw.", False),
            ("⏰ /remind <time> <reminder>", "Set a smart asynchronous timer to remind you about any task.", False),
            ("🖼️ /avatar [user]", "Display high-resolution avatar and banner for any Discord member.", False),
        ],
    },
    "fun": {
        "title": "🎮 Fun & Mini-Games Feature Guide",
        "desc": "Interactive entertainment commands for server members.",
        "fields": [
            ("🧠 /trivia [category] [difficulty]", "Interactive 4-button trivia game with timers and live scoring.", False),
            ("🎱 /8ball <question>", "Ask the mystical 8-ball for answers to life's questions.", True),
            ("🪙 /coinflip", "Flip a virtual coin with animated suspense.", True),
            ("🎲 /dice [sides]", "Roll a multi-sided dice (d6, d20, d100).", True),
            ("✂️ /rps <choice>", "Play Rock-Paper-Scissors against the bot.", True),
            ("😂 /joke & /fact", "Generate funny jokes and fascinating trivia facts.", True),
            ("🔥 /roast & /compliment <user>", "Playfully roast or warmly compliment a server member.", True),
            ("💖 /ship <user1> <user2>", "Calculate romantic compatibility percentage.", True),
        ],
    },
    "leveling": {
        "title": "📈 Leveling & XP Feature Guide",
        "desc": "Rewarding active members with text & voice XP, visual rank cards, and leaderboards.",
        "fields": [
            ("💳 /rank [user]", "View your level card, XP progress bar, rank position, and total message count.", False),
            ("🏆 /leaderboard", "Browse the top 10 most active members on the server.", False),
            ("⚙️ /setxp & /resetxp", "Admin tools to adjust or reset member XP and levels.", False),
        ],
    },
    "tickets": {
        "title": "🎫 Support Ticket Feature Guide",
        "desc": "Private channel ticketing system with interactive button panels and transcripts.",
        "fields": [
            ("🚀 /ticket-setup", "Deploy an interactive support ticket panel in any channel.", False),
            ("➕ /ticket-add <user>", "Add a member to an existing support ticket.", False),
            ("➖ /ticket-remove <user>", "Remove a member from an existing support ticket.", False),
            ("🔒 Close & Transcript", "One-click ticket closure with automated transcript generation.", False),
        ],
    },
    "welcome": {
        "title": "👋 Welcome & AutoRole Feature Guide",
        "desc": "Customizable join greetings, farewell messages, and automatic role assignment.",
        "fields": [
            ("👋 /setwelcome <channel> [message]", "Set welcome channel and custom greeting embed with variables.", False),
            ("🚪 /setgoodbye <channel> [message]", "Set farewell channel and goodbye message.", False),
            ("🎭 /autorole <role>", "Automatically assign a role to new members upon joining.", False),
            ("🧪 /testwelcome", "Simulate a member join to preview welcome embed styling.", False),
        ],
    },
    "logs": {
        "title": "📋 Server Audit Logs Feature Guide",
        "desc": "Comprehensive channel logging for server events.",
        "fields": [
            ("📜 /setlogchannel <channel>", "Set channel for deleted messages, edits, member joins, and role changes.", False),
            ("❌ /clearlogchannel", "Disable audit logging on the server.", False),
        ],
    },
    "utility": {
        "title": "🔧 Utilities & System Diagnostics Feature Guide",
        "desc": "Diagnostics, latency monitoring, stress testing, and localization tools.",
        "fields": [
            ("🏓 /ping", "Check WebSocket gateway latency and Discord REST API roundtrip time.", True),
            ("🌐 /serverinfo & /userinfo", "Inspect server metrics or member account details.", True),
            ("🤖 /botinfo", "View bot fleet stats, memory usage, Python version, and loaded cogs.", True),
            ("⚡ /stresstest [intensity]", "Execute multi-subsystem stress test (Event Loop, I/O, Web API, AI Fleet).", True),
            ("🛠️ /autoheal", "Trigger instant garbage collection, memory reclamation, and model recalibration.", True),
            ("🌐 /translate <text> <language>", "Translate any text or feature guide into 25+ languages via Gemini AI.", True),
            ("📖 /help", "Open this interactive command directory with category browsing and instant AI translation.", True),
        ],
    },
}


def build_help_embed(category: str = "overview", user: Optional[discord.User] = None) -> discord.Embed:
    """Builds a beautifully formatted embed for the requested feature category."""
    data = HELP_CATEGORIES.get(category.lower(), HELP_CATEGORIES["overview"])
    embed = discord.Embed(
        title=data["title"],
        description=data["desc"],
        color=0x6C5CE7,
    )
    for name, value, inline in data["fields"]:
        embed.add_field(name=name, value=value, inline=inline)

    if user:
        embed.set_author(name=f"Manual for {user.display_name}", icon_url=user.display_avatar.url)
    embed.set_footer(text="SkillX Bot Manual • All commands rate-limited • Click 🌐 to Translate")
    return embed


async def translate_embed(
    embed: discord.Embed,
    gemini_client: Any,
    target_language: str,
) -> discord.Embed:
    """
    Translates a discord.Embed into the target language using Gemini AI.
    Batches title, description, fields, and footer into a single prompt for speed.
    """
    if not target_language or target_language.strip().title() in ("English", "En"):
        return embed

    sections = []
    if embed.title:
        sections.append(f"[[TITLE]] {embed.title}")
    if embed.description:
        sections.append(f"[[DESCRIPTION]]\n{embed.description}")
    for idx, field in enumerate(embed.fields):
        sections.append(f"[[FIELD_{idx}_NAME]] {field.name}")
        sections.append(f"[[FIELD_{idx}_VAL]] {field.value}")
    if embed.footer and embed.footer.text:
        sections.append(f"[[FOOTER]] {embed.footer.text}")

    full_text = "\n\n".join(sections)
    translated_text, model = await gemini_client.translate_text(full_text, target_language)
    if not translated_text:
        return embed

    new_embed = discord.Embed(color=embed.color or 0x6C5CE7)
    if embed.thumbnail and embed.thumbnail.url:
        new_embed.set_thumbnail(url=embed.thumbnail.url)
    if embed.author and embed.author.name:
        new_embed.set_author(name=embed.author.name, icon_url=embed.author.icon_url)

    title_m = re.search(r"\[\[TITLE\]\]\s*(.+?)(?=\n\[\[|\Z)", translated_text, re.DOTALL)
    title = title_m.group(1).strip() if title_m else embed.title

    desc_m = re.search(r"\[\[DESCRIPTION\]\]\s*(.+?)(?=\n\[\[|\Z)", translated_text, re.DOTALL)
    desc = desc_m.group(1).strip() if desc_m else embed.description

    new_fields = []
    for idx, f in enumerate(embed.fields):
        name_m = re.search(rf"\[\[FIELD_{idx}_NAME\]\]\s*(.+?)(?=\n\[\[|\Z)", translated_text, re.DOTALL)
        val_m = re.search(rf"\[\[FIELD_{idx}_VAL\]\]\s*(.+?)(?=\n\[\[|\Z)", translated_text, re.DOTALL)
        f_name = name_m.group(1).strip() if name_m else f.name
        f_val = val_m.group(1).strip() if val_m else f.value
        new_fields.append((f_name[:256], f_val[:1024], f.inline))

    footer_m = re.search(r"\[\[FOOTER\]\]\s*(.+?)(?=\n\[\[|\Z)", translated_text, re.DOTALL)
    footer_text = footer_m.group(1).strip() if footer_m else (embed.footer.text if embed.footer else "SkillX Manual")

    # Fallback if structure markers were stripped by AI
    if not title_m and not desc_m and not any(re.search(rf"\[\[FIELD_{i}_NAME\]\]", translated_text) for i in range(len(embed.fields))):
        new_embed.title = f"🌐 {target_language.title()}: {embed.title}" if embed.title else f"🌐 {target_language.title()}"
        new_embed.description = translated_text[:4000]
        new_embed.set_footer(text=f"Translated via Gemini ({model})")
        return new_embed

    new_embed.title = title[:256] if title else None
    new_embed.description = desc[:4096] if desc else None
    for f_name, f_val, inline in new_fields:
        new_embed.add_field(name=f_name, value=f_val, inline=inline)

    new_embed.set_footer(text=f"{footer_text} • 🌐 {target_language.title()} (Gemini {model})")
    return new_embed


class LanguageSelect(discord.ui.Select):
    """
    Discord Select Menu for choosing a translation language.
    Renders flag emoji, native name, and dialect description matching Discord's native category dropdowns.
    """

    def __init__(self, source_embed: discord.Embed, bot: Any, author_id: int):
        self.source_embed = source_embed
        self.bot = bot
        self.author_id = author_id

        options = [
            discord.SelectOption(
                label=f"{lang['native']} ({lang['name']})",
                value=lang["name"],
                description=lang["desc"][:100],
                emoji=lang["emoji"],
            )
            for lang in SUPPORTED_LANGUAGES
        ]

        super().__init__(
            placeholder="🌐 Select your preferred language...",
            min_values=1,
            max_values=1,
            options=options,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "❌ This translation menu belongs to another user. Click the Translate button on the original message to open your own private menu.",
                ephemeral=True,
            )
            return

        chosen_lang = self.values[0]

        if chosen_lang.lower() == "english":
            await interaction.response.edit_message(
                content="✅ Reverted to original **English** manual.",
                embed=self.source_embed,
                view=LanguageSelectView(self.source_embed, self.bot, self.author_id, current_lang="English"),
            )
            return

        await interaction.response.defer(ephemeral=True)

        ai_cog = self.bot.get_cog("AI Chat") if hasattr(self.bot, "get_cog") else None
        if ai_cog and hasattr(ai_cog, "gemini"):
            client = ai_cog.gemini
        else:
            from config import GEMINI_API_KEY
            from gemini_client import GeminiClient
            client = GeminiClient(GEMINI_API_KEY)

        translated_embed = await translate_embed(self.source_embed, client, chosen_lang)

        new_view = LanguageSelectView(self.source_embed, self.bot, self.author_id, current_lang=chosen_lang)
        await interaction.edit_original_response(
            content=f"🌐 **SkillX Features & Manual — Translated to {chosen_lang} via Gemini AI**",
            embed=translated_embed,
            view=new_view,
        )


class LanguageSelectView(discord.ui.View):
    """Ephemeral pop-up view containing the language dropdown, English reset, and dismissal buttons."""

    def __init__(
        self,
        source_embed: discord.Embed,
        bot: Any,
        author_id: int,
        current_lang: str = "English",
        timeout: float = 300.0,
    ):
        super().__init__(timeout=timeout)
        self.source_embed = source_embed
        self.bot = bot
        self.author_id = author_id
        self.current_lang = current_lang

        # Dropdown select menu on row 0
        self.add_item(LanguageSelect(source_embed, bot, author_id))

    @discord.ui.button(label="Reset to English", style=discord.ButtonStyle.secondary, emoji="🇬🇧", row=1)
    async def reset_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ This is not your menu.", ephemeral=True)
            return
        await interaction.response.edit_message(
            content="✅ Restored to original **English** documentation.",
            embed=self.source_embed,
            view=LanguageSelectView(self.source_embed, self.bot, self.author_id, current_lang="English"),
        )

    @discord.ui.button(label="Dismiss", style=discord.ButtonStyle.danger, emoji="🗑️", row=1)
    async def dismiss_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ This is not your menu.", ephemeral=True)
            return
        self.stop()
        await interaction.message.delete()


class FeatureCategorySelect(discord.ui.Select):
    """Category selector dropdown for browsing specific bot features."""

    def __init__(self, author_id: int):
        self.author_id = author_id
        options = [
            discord.SelectOption(
                label="Command Directory Overview",
                value="overview",
                description="Complete manual summary of all bot features and cogs",
                emoji="📖",
            ),
            discord.SelectOption(
                label="Artificial Intelligence",
                value="ai",
                description="Gemini 3.x chat, code reviews, personas, and summarization",
                emoji="🤖",
            ),
            discord.SelectOption(
                label="Moderation & AutoMod",
                value="moderation",
                description="Kick, ban, timeouts, infractions, anti-spam, and security",
                emoji="🛡️",
            ),
            discord.SelectOption(
                label="Community & Engagement",
                value="community",
                description="Interactive polls, automated giveaways, reminders, avatars",
                emoji="🎉",
            ),
            discord.SelectOption(
                label="Fun & Mini-Games",
                value="fun",
                description="Trivia, 8ball, coinflip, dice, rps, roasts, compliments",
                emoji="🎮",
            ),
            discord.SelectOption(
                label="Leveling & Leaderboards",
                value="leveling",
                description="XP progression, visual rank cards, and top 10 leaderboards",
                emoji="📈",
            ),
            discord.SelectOption(
                label="Support Tickets",
                value="tickets",
                description="Private channels, interactive panels, transcripts",
                emoji="🎫",
            ),
            discord.SelectOption(
                label="Welcome & AutoRole",
                value="welcome",
                description="Greeting embeds, farewells, and automatic role assignment",
                emoji="👋",
            ),
            discord.SelectOption(
                label="Server Audit Logs",
                value="logs",
                description="Event logging for deletes, edits, joins, bans, and voice",
                emoji="📋",
            ),
            discord.SelectOption(
                label="Utilities & Diagnostics",
                value="utility",
                description="Ping, system stats, stress test benchmarks, auto-healing",
                emoji="⚡",
            ),
        ]
        super().__init__(
            placeholder="📁 Select a feature category to explore...",
            min_values=1,
            max_values=1,
            options=options,
            row=0,
        )

    async def callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message(
                "❌ Use `/help` to open your own personal command directory.", ephemeral=True
            )
            return

        category = self.values[0]
        embed = build_help_embed(category, interaction.user)
        if hasattr(self.view, "current_embed"):
            self.view.current_embed = embed
        await interaction.response.edit_message(embed=embed, view=self.view)


class HelpMenuView(discord.ui.View):
    """Master interactive Help & Feature Explorer View with category browsing and Gemini translation."""

    def __init__(
        self,
        bot: Any,
        author_id: int,
        current_embed: Optional[discord.Embed] = None,
        timeout: float = 300.0,
    ):
        super().__init__(timeout=timeout)
        self.bot = bot
        self.author_id = author_id
        self.current_embed = current_embed or build_help_embed("overview")

        # Row 0: Category select dropdown
        self.add_item(FeatureCategorySelect(author_id))

    @discord.ui.button(label="Translate to Any Language", style=discord.ButtonStyle.primary, emoji="🌐", row=1)
    async def translate_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        embed_to_translate = self.current_embed or (interaction.message.embeds[0] if interaction.message.embeds else build_help_embed("overview"))
        bot = self.bot or interaction.client
        view = LanguageSelectView(embed_to_translate, bot, interaction.user.id)

        prompt_embed = discord.Embed(
            title="🌐 SkillX Multi-Language Feature Translator",
            description=(
                "**Select your preferred language from the dropdown menu below.**\n\n"
                "• All bot features, command guides, and parameter syntax will be translated.\n"
                "• Powered by **Google Gemini AI** with multi-tier fallback resilience.\n"
                "• **Privacy Guaranteed:** This translation pop-up is completely private and visible only to you."
            ),
            color=0x6C5CE7,
        )
        prompt_embed.set_footer(text="Select a language below to begin instant AI translation")
        await interaction.response.send_message(embed=prompt_embed, view=view, ephemeral=True)
    @discord.ui.button(label="Full Manual", style=discord.ButtonStyle.secondary, emoji="📖", row=1)
    async def overview_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ This is not your menu.", ephemeral=True)
            return
        embed = build_help_embed("overview", interaction.user)
        self.current_embed = embed
        await interaction.response.edit_message(embed=embed, view=self)

    @discord.ui.button(label="Close", style=discord.ButtonStyle.danger, emoji="🗑️", row=1)
    async def close_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        if interaction.user.id != self.author_id:
            await interaction.response.send_message("❌ This is not your menu.", ephemeral=True)
            return
        self.stop()
        await interaction.message.delete()


class TranslateFeaturesButton(discord.ui.Button):
    """Reusable standalone button to attach to any message/embed for instant multi-language translation."""

    def __init__(
        self,
        source_embed: Optional[discord.Embed] = None,
        bot: Optional[Any] = None,
        label: str = "Translate Features",
        style: discord.ButtonStyle = discord.ButtonStyle.primary,
        row: int = 0,
    ):
        super().__init__(label=label, style=style, emoji="🌐", row=row)
        self.source_embed = source_embed
        self.bot = bot

    async def callback(self, interaction: discord.Interaction):
        embed_to_translate = self.source_embed or (interaction.message.embeds[0] if interaction.message.embeds else build_help_embed("overview"))
        bot = self.bot or interaction.client
        view = LanguageSelectView(embed_to_translate, bot, interaction.user.id)

        prompt_embed = discord.Embed(
            title="🌐 SkillX Multi-Language Feature Translator",
            description=(
                "**Select your preferred language from the dropdown menu below.**\n\n"
                "• All bot features, command guides, and parameter syntax will be translated.\n"
                "• Powered by **Google Gemini AI** with multi-tier fallback resilience.\n"
                "• **Privacy Guaranteed:** This translation pop-up is completely private and visible only to you."
            ),
            color=0x6C5CE7,
        )
        prompt_embed.set_footer(text="Select a language below to begin instant AI translation")
        await interaction.response.send_message(embed=prompt_embed, view=view, ephemeral=True)
