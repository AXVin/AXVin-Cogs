from .watch2gether import Watch2Gether

def setup(bot):
    cog = Watch2Gether(bot)
    bot.add_cog(cog)
