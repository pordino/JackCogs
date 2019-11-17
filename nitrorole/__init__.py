from .nitrorole import NitroRole


async def setup(bot):
    bot.add_cog(NitroRole(bot))
