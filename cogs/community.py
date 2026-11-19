"""Community Cog: Interactive polls with live progress bars, giveaways, reminders, and avatar tools."""

import asyncio
from datetime import datetime, timezone
import random
import re
from typing import Optional, Union
import discord
from discord import app_commands
from discord.ext import commands

from embeds import BRAND_COLOR, base_embed, error_embed, info_embed, success_embed


def parse_time_to_seconds(time_str: str) -> Optional[int]:
    """Converts strings like '10s', '5m', '2h', '1d' into total seconds."""
    match = re.match(r"^(\d+)\s*([smhd])$", time_str.strip().lower())
    if not match:
        return None
    val, unit = int(match.group(1)), match.group(2)
    multipliers = {"s": 1, "m": 60, "h": 3600, "d": 86400}
    return val * multipliers[unit]


class PollView(discord.ui.View):
    """Interactive Discord Button Poll with visual progress bars and live updates."""

    def __init__(self, question: str, options: list[str], author_id: int):
        super().__init__(timeout=86400)  # 24 hours
        self.question = question
        self.options = options
        self.author_id = author_id
        # user_id -> option_index
        self.votes: dict[int, int] = {}
        self.message: Optional[discord.Message] = None
        self._add_option_buttons()

    def _add_option_buttons(self):
        emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
        for idx, opt in enumerate(self.options[:5]):
            btn = discord.ui.Button(
                label=opt[:80],
                emoji=emojis[idx],
                style=discord.ButtonStyle.secondary,
                custom_id=f"poll_opt_{idx}",
            )
            btn.callback = self._create_vote_callback(idx)
            self.add_item(btn)

        # End Poll Button for author
        end_btn = discord.ui.Button(
            label="End Poll",
            emoji="🛑",
            style=discord.ButtonStyle.danger,
            custom_id="poll_end",
        )
        end_btn.callback = self._end_poll_callback
        self.add_item(end_btn)

    def _create_vote_callback(self, opt_idx: int):
        async def callback(interaction: discord.Interaction):
            prev = self.votes.get(interaction.user.id)
            if prev == opt_idx:
                del self.votes[interaction.user.id]
                msg = f"Removed your vote for **{self.options[opt_idx]}**."
            else:
                self.votes[interaction.user.id] = opt_idx
                msg = f"Voted for **{self.options[opt_idx]}**!"

            await interaction.response.send_message(msg, ephemeral=True)
            if self.message:
                try:
                    await self.message.edit(embed=self.build_embed())
                except (discord.NotFound, discord.HTTPException):
                    pass

        return callback

    async def _end_poll_callback(self, interaction: discord.Interaction):
        if interaction.user.id != self.author_id and not interaction.user.guild_permissions.manage_messages:
            await interaction.response.send_message("❌ Only the poll creator or moderators can end this poll.", ephemeral=True)
            return

        for child in self.children:
            child.disabled = True
        self.stop()
        embed = self.build_embed(ended=True)
        await interaction.response.edit_message(embed=embed, view=self)

    def build_embed(self, ended: bool = False) -> discord.Embed:
        total = len(self.votes)
        status = " (Closed)" if ended else ""
        embed = discord.Embed(
            title=f"📊 Poll: {self.question}{status}",
            color=0x2ECC71 if not ended else 0x95A5A6,
            timestamp=datetime.now(timezone.utc),
        )

        counts = [0] * len(self.options)
        for opt_idx in self.votes.values():
            if 0 <= opt_idx < len(counts):
                counts[opt_idx] += 1

        emojis = ["1️⃣", "2️⃣", "3️⃣", "4️⃣", "5️⃣"]
        for idx, (opt, count) in enumerate(zip(self.options, counts)):
            pct = (count / total * 100) if total > 0 else 0
            # Visual progress bar 10 blocks
            filled = round(pct / 10)
            bar = "█" * filled + "░" * (10 - filled)
            embed.add_field(
                name=f"{emojis[idx]} {opt}",
                value=f"`{bar}` **{pct:.1f}%** ({count} votes)",
                inline=False,
            )

        embed.set_footer(text=f"Total Votes: {total} • Click buttons below to vote")
        return embed


class GiveawayView(discord.ui.View):
    """Interactive Giveaway button view with countdown and participant tracking."""

    def __init__(self, prize: str, author_id: int, winners_count: int = 1):
        super().__init__(timeout=None)
        self.prize = prize
        self.author_id = author_id
        self.winners_count = winners_count
        self.entries: set[int] = set()
        self.message: Optional[discord.Message] = None

    @discord.ui.button(label="Enter Giveaway (0)", emoji="🎉", style=discord.ButtonStyle.success, custom_id="gw_enter")
    async def enter_button(self, interaction: discord.Interaction, button: discord.ui.Button):
        uid = interaction.user.id
        if uid in self.entries:
            self.entries.remove(uid)
            msg = "You have left the giveaway."
        else:
            self.entries.add(uid)
            msg = "🎉 You have entered the giveaway! Good luck!"

        button.label = f"Enter Giveaway ({len(self.entries)})"
        await interaction.response.edit_message(view=self)
        await interaction.followup.send(msg, ephemeral=True)


class Community(commands.Cog, name="Community"):
    """Interactive community engagement tools: Polls, Giveaways, Reminders, and Avatars."""

    def __init__(self, bot: commands.Bot):
        self.bot = bot

    # ---------------------------------------------------------
    # POLLS
    # ---------------------------------------------------------

    @app_commands.command(name="poll", description="Launch an interactive voting poll with visual progress bars")
    @app_commands.describe(
        question="Poll topic question",
        option1="First option",
        option2="Second option",
        option3="Third option (optional)",
        option4="Fourth option (optional)",
        option5="Fifth option (optional)",
    )
    @app_commands.guild_only()
    async def poll_slash(
        self,
        interaction: discord.Interaction,
        question: str,
        option1: str,
        option2: str,
        option3: Optional[str] = None,
        option4: Optional[str] = None,
        option5: Optional[str] = None,
    ):
        raw_options = [option1, option2, option3, option4, option5]
        options = [opt for opt in raw_options if opt and opt.strip()]

        if len(options) < 2:
            await interaction.response.send_message(
                embed=error_embed("Invalid Poll", "A poll must contain at least 2 options."), ephemeral=True
            )
            return

        view = PollView(question, options, interaction.user.id)
        embed = view.build_embed()
        await interaction.response.send_message(embed=embed, view=view)
        view.message = await interaction.original_response()

    @commands.command(name="poll", help="Create a poll. Example: !poll \"Cats or Dogs?\" Cats Dogs")
    @commands.guild_only()
    async def poll_prefix(self, ctx: commands.Context, question: str, *options: str):
        opts = list(options)
        if len(opts) < 2:
            opts = ["Yes", "No"]

        view = PollView(question, opts[:5], ctx.author.id)
        embed = view.build_embed()
        msg = await ctx.reply(embed=embed, view=view, mention_author=False)
        view.message = msg

    # ---------------------------------------------------------
    # GIVEAWAYS
    # ---------------------------------------------------------

    @app_commands.command(name="giveaway", description="Host an automated giveaway with button entry")
    @app_commands.describe(
        duration="Giveaway length (e.g. 30s, 10m, 2h, 1d)",
        prize="What are you giving away?",
        winners="Number of winners to pick",
    )
    @app_commands.guild_only()
    @app_commands.default_permissions(manage_guild=True)
    async def giveaway_slash(
        self, interaction: discord.Interaction, duration: str, prize: str, winners: Optional[int] = 1
    ):
        seconds = parse_time_to_seconds(duration)
        if not seconds or seconds < 10 or seconds > 604800:
            await interaction.response.send_message(
                embed=error_embed("Invalid Duration", "Provide duration between 10s and 7d (e.g. `10m`, `2h`, `1d`)."),
                ephemeral=True,
            )
            return

        winners_count = max(1, min(10, winners or 1))
        end_time_ts = int(datetime.now(timezone.utc).timestamp() + seconds)

        view = GiveawayView(prize, interaction.user.id, winners_count)
        embed = base_embed(
            title="🎉 GIVEAWAY 🎉",
            description=(
                f"**Prize:** {prize}\n"
                f"**Winners:** `{winners_count}`\n"
                f"**Hosted by:** {interaction.user.mention}\n"
                f"**Ends:** <t:{end_time_ts}:R> (<t:{end_time_ts}:T>)\n\n"
                "Click the button below to enter!"
            ),
            color=0xF1C40F,
            footer_text="SkillX Giveaways",
        )
        await interaction.response.send_message(embed=embed, view=view)
        msg = await interaction.original_response()
        view.message = msg

        # Background wait task
        self.bot.loop.create_task(self._run_giveaway_timer(seconds, view, msg, prize, winners_count, interaction.channel))

    async def _run_giveaway_timer(self, seconds: int, view: GiveawayView, msg, prize: str, winners_count: int, channel):
        await asyncio.sleep(seconds)
        for child in view.children:
            child.disabled = True

        if not view.entries:
            embed = error_embed("Giveaway Ended", f"No one entered the giveaway for **{prize}**.")
            try:
                await msg.edit(embed=embed, view=view)
            except Exception:
                pass
            return

        winner_ids = random.sample(list(view.entries), min(len(view.entries), winners_count))
        mentions = [f"<@{wid}>" for wid in winner_ids]

        embed = base_embed(
            title="🎉 GIVEAWAY ENDED 🎉",
            description=(
                f"**Prize:** {prize}\n"
                f"**Winners:** {', '.join(mentions)}\n"
                f"**Total Entries:** {len(view.entries)}"
            ),
            color=0x2ECC71,
            footer_text="Congratulations to the winners!",
        )
        try:
            await msg.edit(embed=embed, view=view)
            await channel.send(f"🎉 Congratulations {', '.join(mentions)}! You won the **{prize}**!")
        except Exception:
            pass

    # ---------------------------------------------------------
    # REMINDERS
    # ---------------------------------------------------------

    @app_commands.command(name="remind", description="Set a timer notification reminder")
    @app_commands.describe(time="Duration (e.g. 30s, 10m, 2h, 1d)", note="What should I remind you about?")
    async def remind_slash(self, interaction: discord.Interaction, time: str, note: str):
        seconds = parse_time_to_seconds(time)
        if not seconds or seconds < 5 or seconds > 2592000:
            await interaction.response.send_message(
                embed=error_embed("Invalid Duration", "Specify duration like `10m`, `1h`, `3d` (up to 30 days)."),
                ephemeral=True,
            )
            return

        end_ts = int(datetime.now(timezone.utc).timestamp() + seconds)
        embed = success_embed(
            "Reminder Scheduled",
            f"I will remind you about **{note}** in **{time}** (<t:{end_ts}:R>).",
        )
        await interaction.response.send_message(embed=embed)

        async def _remind_task():
            await asyncio.sleep(seconds)
            remind_embed = base_embed(
                title="⏰ Reminder Alert!",
                description=f"Hey {interaction.user.mention}, you asked to be reminded about:\n\n>>> **{note}**",
                color=BRAND_COLOR,
                user=interaction.user,
            )
            # Send in channel if available, else DM
            try:
                if interaction.channel:
                    await interaction.channel.send(content=interaction.user.mention, embed=remind_embed)
                else:
                    await interaction.user.send(embed=remind_embed)
            except Exception:
                try:
                    await interaction.user.send(embed=remind_embed)
                except Exception:
                    pass

        self.bot.loop.create_task(_remind_task())

    @commands.command(name="remind", help="Set a reminder. Example: !remind 10m Check the oven")
    async def remind_prefix(self, ctx: commands.Context, time: str, *, note: str):
        seconds = parse_time_to_seconds(time)
        if not seconds or seconds < 5 or seconds > 2592000:
            await ctx.reply(embed=error_embed("Invalid Duration", "Use formats like 10m, 2h, 1d."), delete_after=10)
            return

        end_ts = int(datetime.now(timezone.utc).timestamp() + seconds)
        embed = success_embed(
            "Reminder Scheduled",
            f"I will remind you about **{note}** in **{time}** (<t:{end_ts}:R>).",
        )
        await ctx.reply(embed=embed, mention_author=False)

        async def _remind_task():
            await asyncio.sleep(seconds)
            remind_embed = base_embed(
                title="⏰ Reminder Alert!",
                description=f"Hey {ctx.author.mention}, you asked to be reminded about:\n\n>>> **{note}**",
                color=BRAND_COLOR,
                user=ctx.author,
            )
            try:
                await ctx.channel.send(content=ctx.author.mention, embed=remind_embed)
            except Exception:
                try:
                    await ctx.author.send(embed=remind_embed)
                except Exception:
                    pass

        self.bot.loop.create_task(_remind_task())

    # ---------------------------------------------------------
    # AVATAR VIEWER
    # ---------------------------------------------------------

    @app_commands.command(name="avatar", description="View and download high-resolution user avatar")
    @app_commands.describe(member="Member whose avatar to view (defaults to yourself)")
    async def avatar_slash(self, interaction: discord.Interaction, member: Optional[discord.Member] = None):
        target = member or interaction.user
        avatar_url = target.display_avatar.url
        embed = base_embed(
            title=f"🖼️ Avatar: {target.display_name}",
            color=BRAND_COLOR,
            user=interaction.user,
        )
        embed.set_image(url=avatar_url)
        embed.add_field(
            name="Direct Links",
            value=f"[PNG]({target.display_avatar.with_format('png').url}) • [WebP]({target.display_avatar.with_format('webp').url}) • [Default]({avatar_url})",
            inline=False,
        )
        await interaction.response.send_message(embed=embed)

    @commands.command(name="avatar", aliases=["av", "pfp"], help="View member avatar. Example: !avatar @user")
    async def avatar_prefix(self, ctx: commands.Context, member: Optional[discord.Member] = None):
        target = member or ctx.author
        avatar_url = target.display_avatar.url
        embed = base_embed(
            title=f"🖼️ Avatar: {target.display_name}",
            color=BRAND_COLOR,
            user=ctx.author,
        )
        embed.set_image(url=avatar_url)
        embed.add_field(
            name="Direct Links",
            value=f"[PNG]({target.display_avatar.with_format('png').url}) • [WebP]({target.display_avatar.with_format('webp').url}) • [Default]({avatar_url})",
            inline=False,
        )
        await ctx.reply(embed=embed, mention_author=False)


async def setup(bot: commands.Bot):
    await bot.add_cog(Community(bot))
