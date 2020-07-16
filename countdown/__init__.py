from .countdown import CountdownCog

def setup(bot):
    cog = CountdownCog(bot)
    bot.add_cog(cog)
