from .countdown import Countdown

def setup(bot):
    cog = Countdown(bot)
    bot.add_cog(cog)
