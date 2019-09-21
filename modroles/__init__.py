from .modroles import ModRoles


async def setup(bot):
    bot.add_cog(ModRoles(bot))
