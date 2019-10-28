from string import Template
from typing import Union
import asyncio
import os
import random

from redbot.core import commands, checks
from redbot.core.utils.chat_formatting import box, pagify
from redbot.core.config import Config
from redbot.core.data_manager import cog_data_path
from redbot.core.utils.predicates import MessagePredicate
import discord


class BanMessage(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(
            self, identifier=176070082584248320, force_registration=True
        )
        self.config.register_guild(channel=None, message_templates=[])
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
                await self.config.guild(guild_obj).message_templates.set(
                    [maybe_message_template]
                )

    @commands.group()
    @checks.admin()
    async def banmessageset(self, ctx: commands.Context):
        """BanMessage settings."""

    @banmessageset.command(name="channel")
    async def banmessageset_channel(
        self, ctx: commands.Context, channel: discord.TextChannel = None
    ):
        """Set channel for ban messages. Leave empty to disable."""
        if channel is None:
            await self.config.guild(ctx.guild).channel.clear()
            await ctx.send("Ban messages are now disabled.")
            return
        await self.config.guild(ctx.guild).channel.set(channel.id)
        await ctx.send(f"Ban messages will now be sent in {channel.mention}")

    @banmessageset.command(name="addmessage")
    async def banmessageset_addmessage(self, ctx: commands.Context, *, message: str):
        """Add ban message.

        Those fields will get replaced automatically:
        $username - The banned user's name
        $server - The name of the server

        Note: Ban message can also have image.
        To set it, use `[p]banmessageset setimage`
        """
        async with self.config.guild(ctx.guild).message_templates as templates:
            templates.append(message)
        content = Template(message).safe_substitute(
            username=str(ctx.author), server=ctx.guild.name
        )
        filename = next(self.message_images.glob(f"{ctx.guild.id}.*"), None)
        if filename is not None:
            file = discord.File(filename)
        else:
            file = None
        await ctx.send("Ban message set, sending a test message here...")
        await ctx.send(content, file=file)

    @banmessageset.command(name="removemessage")
    async def banmessageset_removemessage(self, ctx: commands.Context):
        """Remove ban message."""
        templates = await self.config.guild(ctx.guild).message_templates
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

    @banmessageset.command(name="setimage")
    async def banmessageset_setimage(self, ctx: commands.Context):
        """Set image for ban message."""
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

    @banmessageset.command(name="unsetimage")
    async def banmessageset_unsetimage(self, ctx: commands.Context):
        """Unset image for ban message."""
        for file in self.message_images.glob(f"{ctx.guild.id}.*"):
            file.unlink()
        await ctx.send("Image unset.")

    @commands.Cog.listener()
    async def on_member_ban(
        self, guild: discord.Guild, user: Union[discord.User, discord.Member]
    ):
        channel_id = await self.config.guild(guild).channel()
        if channel_id is None:
            return
        channel = guild.get_channel(channel_id)
        if channel is None:
            return
        message_templates = await self.config.guild(guild).message_templates()
        if not message_templates:
            return
        message_template = random.choice(message_templates)

        content = Template(message_template).safe_substitute(
            username=str(user), server=guild.name
        )
        filename = next(self.message_images.glob(f"{guild.id}.*"), None)
        if filename is not None:
            await channel.send(content, file=discord.File(filename))
            return
        await channel.send(content)


def setup(bot):
    bot.add_cog(BanMessage(bot))
