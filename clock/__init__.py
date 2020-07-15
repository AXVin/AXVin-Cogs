from .clock import Clock

def setup(bot):
    cog = Clock(bot)
    bot.add_cog(cog)