from redbot.core.bot import Red

from .banmessage import BanMessage


async def notify_owners(bot: Red) -> None:
    await bot.wait_until_ready()
    await bot.send_to_owners(
        "BanMessage cog was installed from `unfinished-cogs/banmessage` branch"
        " of JackCogs repo which is no longer active"
        " and it's due to be removed on 29.02.2020.\n"
        "BanMessage cog is now in main branch of the repo.\n"
        "Please readd the repo to Downloader under"
        " the same name with `v3` branch instead.\n\n"
        "If you have any questions,"
        " ask on Cog Support server in #support_othercogs channel.\n"
        "https://discord.gg/GET4DVk"
    )


async def setup(bot: Red) -> None:
    cog = BanMessage(bot)
    bot.add_cog(cog)
    bot.loop.create_task(notify_owners(bot))
