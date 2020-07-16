
# stdlib
from datetime import datetime

# discord.py
import discord
from discord.ext import tasks

# Red-DiscordBot
from redbot.core import Config, commands, checks

# Current Plugin
import pytz
from pytz import all_timezones


__author__ = 'AXVin'
__version__ = '1.0.1'


channel_defaults = {
    "timezone": None,
    "time_format": "%A, %I:%M %p (%Z)"
}


class TimeZone(commands.Converter):

    async def convert(self, ctx, argument):
        if argument.title() not in all_timezones:
            raise commands.BadArgument("Couldn't find that timezone. Look for it in "
                                       "https://en.wikipedia.org/wiki/List_of_tz_database_time_zones")
        return argument


class Clock(commands.Cog):
    """Display time for timezones as voice channels"""

    def __init__(self, bot):
        self.bot = bot
        self.db = Config.get_conf(self, 675875687587, force_registration=True)
        self.db.register_channel(**channel_defaults)
        self.update_channels.start()


    async def cog_unload(self):
        self.update_channels.stop()


    @tasks.loop(seconds=300)
    async def update_channels(self):
        channels = await self.db.all_channels()
        for channel_id in channels:
            channel = self.bot.get_channel(channel_id)
            if channel is None:
                continue

            time = channels[channel_id]["timezone"]
            time = datetime.now(pytz.timezone(time))
            fmt = channels[channel_id]["time_format"]
            time = time.strftime(fmt)

            await channel.edit(name=time)


    @update_channels.before_loop
    async def before_update_channels(self):
        await self.bot.wait_until_ready()


    @commands.guild_only()
    @commands.group(autohelp=True)
    async def clock(self, ctx):
        """
        Commands for creating new clocks
        """
        pass



    @clock.command()
    @checks.admin_or_permissions(manage_guild=True)
    async def create(self, ctx, timezone:TimeZone, *, format=None):
        """
        Create timezones for VoiceChannels. Wrap tz in quotes if it has spaces inside of it.
        For timezone, check out: https://en.wikipedia.org/wiki/List_of_tz_database_time_zones
        For format, check out: https://strftime.org. Default is "%A, %I:%M %p (%Z)"
        """
        try:
            channel = await ctx.guild.create_voice_channel(name=timezone)
        except Exception as e:
            await ctx.send(e)
            return
        await self.db.channel(channel).timezone.set(timezone)
        if format:
            await self.db.channel(channel).time_format.set(format)
        await ctx.send(f"Successfully created a channel with **{tz}** timezone"
                       ". It should be resolved on next cycle(5 minutes)")


    @clock.command(hidden=True)
    @commands.is_owner()
    async def clear_all(self, ctx):
        await self.db.clear_all()
