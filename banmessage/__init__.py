from .banmessage import BanMessage


def setup(bot):
    bot.add_cog(BanMessage(bot))
