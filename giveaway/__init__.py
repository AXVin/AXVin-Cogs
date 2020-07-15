from .giveaway import GiveawayCog

def setup(bot):
    cog = GiveawayCog(bot)
    bot.add_cog(cog)
