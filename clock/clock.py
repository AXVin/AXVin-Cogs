
# stdlib
import asyncio
from typing import Optional
from datetime import datetime

# discord.py
import discord
from discord.ext import tasks

# Red-DiscordBot
from redbot.core import Config, commands, checks

# Current Plugin
import pytz
from pytz import all_timezones
from pytz import country_timezones


__author__ = 'AXVin'
__version__ = '1.0.0'


channel_defaults = {
    "time": None,
    "time_format": "%A, %I:%M %p (%Z)"
}


class TimeZoneConverter(commands.Converter):

    async def convert(self, ctx, arg):
        exist = True if arg.title() in all_timezones else False
        if exist is False:
            raise commands.BadArgument(
                "**Error:** Unrecognized timezone. Try ""`[p]clock set Continent/City`: "
                "see <https://en.wikipedia.org/wiki/List_of_tz_database_time_zones>"
            )
        if "'" in arg:
            arg = arg.replace("'", "")
        return arg


class Clock(commands.Cog):
    """Display time for timezones as voice channels"""

    def __init__(self, bot):
        self.bot = bot
        self.db = Config.get_conf(self, 675875687587, force_registration=True)
        self.db.register_channel(**channel_defaults)
        self.update_channels.start()


    async def cog_unload(self):
        self.update_channels.stop()


    @tasks.loop(seconds=60)
    async def update_channels(self):
        channels = await self.db.all_channels()
        for channel_id in channels:
            channel = self.bot.get_channel(channel_id)
            if channel is None:
                continue

            time = channels[channel_id]["time"]
            time = datetime.now(pytz.timezone(time))
            fmt = channels[channel_id]["time_format"]
            time = time.strftime(fmt)

            await channel.edit(name=time)


    @update_channels.before_loop
    async def before_update_channels(self):
        await self.bot.wait_until_ready()


    @commands.guild_only()
    @commands.group()
    async def clock(self, ctx):
        """
        Checks the time and sets the channel's time
        For the list of supported timezones, see here:
        https://en.wikipedia.org/wiki/List_of_tz_database_time_zones
        """
        pass


    @clock.command()
    async def tz(self, ctx, *, tz: Optional[str] = None):
        """
        Gets the time in any timezone
        """
        try:
            if tz is None:
                time = datetime.now()
                fmt = "**%H:%M** %d-%B-%Y"
                await ctx.send(f"Current system time: {time.strftime(fmt)}")
            else:
                if "'" in tz:
                    tz = tz.replace("'", "")
                if len(tz) > 4 and "/" not in tz:
                    await ctx.send(
                        "Error: Incorrect format. Use:\n **Continent/City** with correct capitals. "
                        "e.g. `America/New_York`\n See the full list of supported timezones here:\n "
                        "<https://en.wikipedia.org/wiki/List_of_tz_database_time_zones>"
                    )
                else:
                    fmt = "**%H:%M** %d-%B-%Y **%Z (UTC %z)**"
                    time = datetime.now(pytz.timezone(tz.title()))
                    await ctx.send(time.strftime(fmt))
        except Exception as e:
            await ctx.send(f"**Error:** {str(e)} is an unsupported timezone.")


    @clock.command()
    async def iso(self, ctx, *, code=None):
        """
        Looks up ISO3166 country codes and gives you a supported timezone
        """
        if code is None:
            await ctx.send("That doesn't look like a country code!")
        else:
            exist = True if code in country_timezones else False
            if exist is True:
                tz = str(country_timezones(code))
                msg = (
                    f"Supported timezones for **{code}:**\n{tz[:-1][1:]}"
                    f"\n**Use** `[p]time tz Continent/City` **to display the current time in that timezone.**"
                )
                await ctx.send(msg)
            else:
                await ctx.send(
                    "That code isn't supported. For a full list, see here: "
                    "<https://en.wikipedia.org/wiki/List_of_tz_database_time_zones>"
                )


    @clock.command()
    @checks.admin_or_permissions(manage_guild=True)
    async def create(self, ctx, tz:TimeZoneConverter, *, format=None):
        """
        Create timezones for VoiceChannels. Wrap tz in quotes if it has spaces inside of it.
        For format, check out: https://strftime.org. Default is "%A, %I:%M %p (%Z)"
        """
        try:
            channel = await ctx.guild.create_voice_channel(name=tz)
        except Exception as e:
            await ctx.send(e)
            return
        await self.db.channel(channel).time.set(tz)
        if format:
            await self.db.channel(channel).time_format.set(format)
        await ctx.send(f"Successfully created a channel with **{tz}** timezone"
                       ". It should be resolved on next cycle(60 seconds)")


    @clock.command(hidden=True)
    @commands.is_owner()
    async def clear_all(self, ctx):
        await self.db.clear_all()
