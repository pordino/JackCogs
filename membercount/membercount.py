"""
Copyright 2018-2020 Jakub Kuczys (https://github.com/jack1142)

Licensed under the Apache License, Version 2.0 (the "License");
you may not use this file except in compliance with the License.
You may obtain a copy of the License at

    https://www.apache.org/licenses/LICENSE-2.0

Unless required by applicable law or agreed to in writing, software
distributed under the License is distributed on an "AS IS" BASIS,
WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
See the License for the specific language governing permissions and
limitations under the License.
"""

from datetime import datetime

import discord
from redbot.core import commands

from .typings import GuildContext


class MemberCount(commands.Cog):
    """Get count of all members + humans and bots separately."""

    @commands.guild_only()
    @commands.command()
    async def membercount(self, ctx: GuildContext) -> None:
        """Get count of all members + humans and bots separately."""
        guild = ctx.guild
        member_count = 0
        human_count = 0
        bot_count = 0
        for member in guild.members:
            if member.bot:
                bot_count += 1
            else:
                human_count += 1
            member_count += 1
        if await ctx.embed_requested():
            embed = discord.Embed(
                timestamp=datetime.utcnow(), color=await ctx.embed_color()
            )
            embed.add_field(name="Members", value=str(member_count))
            embed.add_field(name="Humans", value=str(human_count))
            embed.add_field(name="Bots", value=str(bot_count))
            await ctx.send(embed=embed)
        else:
            await ctx.send(
                f"**Members:** {member_count}\n"
                f"**Humans:** {human_count}\n"
                f"**Bots:** {bot_count}"
            )
