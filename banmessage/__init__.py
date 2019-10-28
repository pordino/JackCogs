from .banmessage import BanMessage


async def setup(bot):
    cog = BanMessage(bot)
    await cog.initialize()
    bot.add_cog(cog)
