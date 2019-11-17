from string import Template
import logging

from redbot.core import commands
from redbot.core.config import Config
import discord

log = logging.getLogger("redbot.jackcogs.nitrorole")


class NitroRole(commands.Cog):
    def __init__(self, bot):
        self.bot = bot
        self.config = Config.get_conf(
            self, identifier=176070082584248320, force_registration=True
        )
        self.config.register_guild(role_id=None, channel_id=None, message_template=None)

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
        """Set channel for new booster messages.

        Leave empty to not assign any role."""
        if channel is None:
            await self.config.guild(ctx.guild).channel_id.set(None)
            await ctx.send("New booster messages disabled.")
        else:
            await self.config.guild(ctx.guild).channel_id.set(channel.id)
            await ctx.send(
                f"New booster messages will now be sent in {channel.mention}"
            )

    @nitrorole.command("message")
    async def nitrorole_message(self, ctx, *, message):
        """Set new booster message.

        Those fields will get replaced automatically:
        $mention - Mention the user who boosted
        $username - The user's display name
        $server - The name of the server
        $count - The number of users who boosted the server
        $plural - Empty if count is 1. 's' otherwise
        """
        await self.config.guild(ctx.guild).message_template.set(message)
        content = Template(message).safe_substitute(
            mention=ctx.author.mention,
            username=ctx.author.display_name,
            server=ctx.guild.name,
            count=2,
            plural="s"
        )
        await ctx.send("New booster message set, sending a test message here...")
        await ctx.send(content)

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
                "Role with ID %s can't be found in guild with ID %s.",
                role_id,
                guild.id
            )
            return
        if role >= guild.me.top_role:
            log.error(
                "Role with ID %s (guild ID: %s) is higher in hierarchy"
                " than any bot's role.",
                role_id,
                guild.id
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
                guild.id
            )
            return
        message_template = await config_scope.message_template()
        if not message_template:
            return
        count = guild.premium_subscription_count
        content = Template(message_template).safe_substitute(
            mention=member.mention,
            username=member.display_name,
            server=guild.name,
            count=count,
            plural="" if count == 1 else "s"
        )
        try:
            await channel.send(content)
        except discord.Forbidden:
            log.error(
                "Bot can't send messages in channel with ID %s (guild ID: %s)",
                channel_id,
                guild.id
            )
