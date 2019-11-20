import asyncio
import logging
import os
import random
from string import Template

import discord
from redbot.core import commands
from redbot.core.config import Config
from redbot.core.data_manager import cog_data_path
from redbot.core.utils.chat_formatting import box, pagify
from redbot.core.utils.predicates import MessagePredicate

log = logging.getLogger("red.jackcogs.nitrorole")


class NitroRole(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(
            self, identifier=176070082584248320, force_registration=True
        )
        self.config.register_guild(role_id=None, channel_id=None, message_templates=[])
        self.message_images = cog_data_path(self) / "message_images"
        os.makedirs(self.message_images, exist_ok=True)

    async def initialize(self):
        # gonna keep this for now, but technically this cog is still under limited support
        await self._maybe_update_config()

    async def _maybe_update_config(self):
        # I'll just use Liz's code from core Red here
        all_guild_data = await self.config.all_guilds()
        for guild_id, guild_data in all_guild_data.items():
            guild_obj = discord.Object(id=guild_id)
            maybe_message_template = guild_data.get("message_template")
            if maybe_message_template:
                scope = self.config.guild(guild_obj)
                await scope.message_templates.set([maybe_message_template])
                await scope.clear_raw("message_template")

    @commands.group()
    @commands.admin_or_permissions(manage_roles=True)
    async def nitrorole(self, ctx: commands.Context):
        """NitroRole settings."""

    @nitrorole.command(name="autoassignrole")
    async def nitrorole_autoassignrole(
        self, ctx: commands.Context, role: discord.Role = None
    ):
        """Set role that will be autoassigned after someone boosts server.

        Leave empty to not assign any role."""
        if role is None:
            await self.config.guild(ctx.guild).role_id.set(None)
            await ctx.send(
                "Role will not be autoassigned anymore when someone boosts server."
            )
        else:
            await self.config.guild(ctx.guild).role_id.set(role.id)
            await ctx.send(f"Nitro boosters will now be assigned {role.name} role.")

    @nitrorole.command(name="channel")
    async def nitrorole_channel(
        self, ctx: commands.Context, channel: discord.TextChannel = None
    ):
        """Set channel for new boost messages. Leave empty to disable."""
        if channel is None:
            await self.config.guild(ctx.guild).channel_id.clear()
            await ctx.send("New booster messages disabled.")
            return
        await self.config.guild(ctx.guild).channel_id.set(channel.id)
        await ctx.send(f"New booster messages will now be sent in {channel.mention}")

    @nitrorole.command(name="addmessage")
    async def nitrorole_addmessage(self, ctx: commands.Context, *, message: str):
        """Add new boost message.

        Those fields will get replaced automatically:
        $mention - Mention the user who boosted
        $username - The user's display name
        $server - The name of the server
        $count - The number of boosts server has
        (this doesn't equal amount of users that boost this server)
        $plural - Empty if count is 1. 's' otherwise

        Note: New boost message can also have image.
        To set it, use `[p]nitrorole setimage`
        """
        async with self.config.guild(ctx.guild).message_templates() as templates:
            templates.append(message)
        content = Template(message).safe_substitute(
            mention=ctx.author.mention,
            username=ctx.author.display_name,
            server=ctx.guild.name,
            count="2",
            plural="s",
        )
        filename = next(self.message_images.glob(f"{ctx.guild.id}.*"), None)
        if filename is not None:
            file = discord.File(filename)
        else:
            file = None
        await ctx.send("New booster message set, sending a test message here...")
        await ctx.send(content, file=file)

    @nitrorole.command(name="removemessage")
    async def nitrorole_removemessage(self, ctx: commands.Context):
        """Remove new boost message."""
        templates = await self.config.guild(ctx.guild).message_templates()
        if not templates:
            await ctx.send("This guild doesn't have any ban message set.")
            return

        msg = "Choose a ban message to delete:\n\n"
        for idx, template in enumerate(templates):
            msg += f"  {idx}. {template}\n"
        for page in pagify(msg):
            await ctx.send(box(page))

        pred = MessagePredicate.valid_int(ctx)
        try:
            await self.bot.wait_for(
                "message", check=lambda m: pred(m) and pred.result >= 0, timeout=30
            )
        except asyncio.TimeoutError:
            await ctx.send("Okay, no messages will be removed.")
            return
        try:
            templates.pop(pred.result)
        except IndexError:
            await ctx.send("Wow! That's a big number. Too big...")
            return
        await self.config.guild(ctx.guild).message_templates.set(templates)
        await ctx.send("Message removed.")

    @nitrorole.command(name="setimage")
    async def nitrorole_setimage(self, ctx: commands.Context):
        """Set image for new boost message."""
        if len(ctx.message.attachments) != 1:
            await ctx.send("You have to send exactly one attachment.")
            return
        a = ctx.message.attachments[0]
        if a.width is None:
            await ctx.send("The attachment has to be an image.")
            return
        ext = a.url.rpartition(".")[2]
        filename = self.message_images / f"{ctx.guild.id}.{ext}"
        with open(filename, "wb") as fp:
            await a.save(fp)
        for file in self.message_images.glob(f"{ctx.guild.id}.*"):
            if not file == filename:
                file.unlink()
        await ctx.send("Image set.")

    @nitrorole.command(name="unsetimage")
    async def nitrorole_unsetimage(self, ctx: commands.Context):
        """Unset image for new boost message."""
        for file in self.message_images.glob(f"{ctx.guild.id}.*"):
            file.unlink()
        await ctx.send("Image unset.")

    @commands.Cog.listener()
    async def on_member_update(self, before: discord.Member, after: discord.Member):
        if before.premium_since is None and after.premium_since is not None:
            await self.maybe_assign_role(after)
            await self.maybe_announce(after)

    async def maybe_assign_role(self, member: discord.Member):
        guild = member.guild
        role_id = await self.config.guild(guild).role_id()
        if role_id is None:
            return
        role = guild.get_role(role_id)
        if role is None:
            log.error(
                "Role with ID %s can't be found in guild with ID %s.", role_id, guild.id
            )
            return
        if role >= guild.me.top_role:
            log.error(
                "Role with ID %s (guild ID: %s) is higher in hierarchy"
                " than any bot's role.",
                role_id,
                guild.id,
            )
            return
        if role in member.roles:
            return
        await member.add_roles(role, reason="Nitro booster - role autoassigned.")

    async def maybe_announce(self, member):
        guild = member.guild
        config_scope = self.config.guild(guild)
        channel_id = await config_scope.channel_id()
        if channel_id is None:
            return
        channel = guild.get_channel(channel_id)
        if channel is None:
            log.error(
                "Channel with ID %s can't be found in guild with ID %s.",
                channel_id,
                guild.id,
            )
            return
        message_templates = await config_scope.message_templates()
        if not message_templates:
            return
        message_template = random.choice(message_templates)

        count = guild.premium_subscription_count
        content = Template(message_template).safe_substitute(
            mention=member.mention,
            username=member.display_name,
            server=guild.name,
            count=str(count),
            plural="" if count == 1 else "s",
        )
        filename = next(self.message_images.glob(f"{guild.id}.*"), None)
        if filename is not None:
            file = discord.File(filename)
        else:
            file = None
        try:
            await channel.send(content, file=file)
        except discord.Forbidden:
            log.error(
                "Bot can't send messages in channel with ID %s (guild ID: %s)",
                channel_id,
                guild.id,
            )
