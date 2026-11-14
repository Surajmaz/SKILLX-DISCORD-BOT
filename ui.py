"""Interactive Discord UI Components: Pagination, Confirmation, and Text Chunking."""

import discord
from typing import Optional, Union
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
    ):
        super().__init__(timeout=timeout)
        self.pages = pages
        self.current_page = 0
        self.author_id = author_id
        self.prompt = prompt
        self.model = model
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
