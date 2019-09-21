from string import Template
import os

from redbot.core import commands, checks
from redbot.core.config import Config
from redbot.core.data_manager import cog_data_path
import discord


class BanMessage(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(
            self, identifier=176070082584248320, force_registration=True
        )
        self.config.register_guild(channel=None, message_template=None)
        self.message_images = cog_data_path(self) / "message_images"
        os.makedirs(self.message_images, exist_ok=True)

    @commands.group()
    @checks.admin()
    async def banmessageset(self, ctx):
        """BanMessage settings."""

    @banmessageset.command(name="channel")
    async def banmessageset_channel(self, ctx, channel: discord.TextChannel = None):
        """Set channel for ban messages. Leave empty to disable."""
        if channel is None:
            await self.config.guild(channel.guild).channel.clear()
        await self.config.guild(channel.guild).channel.set(channel.id)
        await ctx.send(f"Ban messages will now be sent in {channel.mention}")

    @banmessageset.command(name="message")
    async def banmessageset_message(self, ctx, *, message):
        """Set ban message. You can attach image to the message.

        Those fields will get replaced automatically:
        $username - The banned user's name
        $server - The name of the server
        """
        await self.config.guild(ctx.guild).message_template.set(message)
        content = Template(message).safe_substitute(
            username=str(ctx.author),
            server=ctx.guild.name,
        )
        if len(ctx.message.attachments) > 1:
            await ctx.send("You can send only one attachment.")
            return
        file = None
        if ctx.message.attachments:
            a = ctx.message.attachments[0]
            if a.width is None:
                await ctx.send("The attachment has to be an image.")
                return
            ext = a.url.rpartition('.')[2]
            filename = self.message_images / f"{ctx.guild.id}.{ext}"
            with open(filename, "wb") as fp:
                await a.save(fp)
            file = discord.File(filename)
        else:
            for file in self.message_images.glob(f"{ctx.guild.id}.*"):
                file.unlink()
        await ctx.send("Ban message set, sending a test message here...")
        await ctx.send(content, file=file)

    @commands.Cog.listener()
    async def on_member_ban(self, guild, user):
        channel_id = await self.config.guild(guild).channel()
        if channel_id is None:
            return
        channel = guild.get_channel(channel_id)
        if channel is None:
            return
        message_template = await self.config.guild(guild).message_template()
        if not message_template:
            return

        content = Template(message_template).safe_substitute(
            username=str(user),
            server=guild.name,
        )
        filename = next(self.message_images.glob(f"{guild.id}.*"), None)
        if filename is not None:
            await channel.send(content, file=discord.File(filename))
            return
        await channel.send(content)


def setup(bot):
    bot.add_cog(BanMessage(bot))
