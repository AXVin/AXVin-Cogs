
# stdlib
import datetime
import asyncio
import traceback
from pprint import pprint

# discord.py
import discord
from discord.ext import tasks
from discord.ext.commands.errors import CommandInvokeError

# Red-DiscordBot
from redbot.core import Config, commands, checks

# Current Plugin
from .time import human_timedelta, UserFriendlyTime

__author__ = 'AXVin'
__version__ = '1.1.1'


global_defaults = {
    "interval": 5
}

guild_defaults = {
    "countdowns": []
}
# countdowns: [{
#     channel_id: int,
#     message_id: int,
#     author_id: int,
#     title: str,
#     ending_message: str,
#     end_time: str
# }]

# We will use datetime.timestamp() to store it and datetime.fromtimestamp() to retrieve


class CountdownAborted(Exception):
    pass


def create_embed(*, title, end_time):
    '''
    Creates an embed with the given information

    Parameters:
    -----------
    title: str
        Title of the Countdown
    end_time: datetime.datetime
        When the countdown ends or ended

    Returns:
    --------
    discord.Embed
        The created Embed
    '''
    ended = False
    now = datetime.datetime.utcnow()
    if end_time <= now:
        ended = True

    embed = discord.Embed(timestamp=end_time,
                          title=title)
    if ended:
        embed.color = 0xff0000
        embed.add_field(name="\u200b", value="\u200b")
        embed.set_footer(text="Ended at")
    else:
        embed.color = 0x00ff00
        embed.add_field(name="\u200b", value="\u200b")
        ignore_seconds = True if (end_time - now).total_seconds() > 60 else False
        delta = human_timedelta(end_time, source=now, ignore_seconds=ignore_seconds)
        embed.add_field(name="Time Remaining:",
                        value=delta)
        embed.set_footer(text="Ends at")

    return embed


BaseCog = getattr(commands, "Cog", object)

class Countdown(BaseCog):

    def __init__(self, bot):
        self.bot = bot
        self.db = Config.get_conf(self, 208813050617266176, force_registration=True)
        self.db.register_guild(**guild_defaults)
        self.db.register_global(**global_defaults)
        self.running_countdowns = []
        # (message, author, title, ending_message, end_time)
        self.countdown_handler.start()

    def cog_unload(self):
        self.countdown_handler.stop()


    @tasks.loop(seconds=5)
    async def countdown_handler(self):
        now = datetime.datetime.utcnow()
        for countdown in self.running_countdowns:
            message, author, title, ending_message, end_time = countdown
            embed = create_embed(title=title,
                                 end_time=end_time)
            if end_time <= now:
                content = "\N{HEAVY EXCLAMATION MARK SYMBOL} Countdown Ended! " \
                          "\N{HEAVY EXCLAMATION MARK SYMBOL}"
                async with self.db.guild(message.guild).countdowns() as countdowns:
                    countdowns.remove({
                        "channel_id": message.channel.id,
                        "message_id": message.id,
                        "author_id": author.id,
                        "title": title,
                        "ending_message": ending_message,
                        "end_time": end_time.timestamp()
                    })
                self.running_countdowns.remove(countdown)
                await message.channel.send(ending_message)
            else:
                content = "\N{PARTY POPPER} New Countdown Started! \N{PARTY POPPER}"
            if embed.to_dict() != message.embeds[0].to_dict():
                await message.edit(content=content, embed=embed)
            


    @countdown_handler.before_loop
    async def before_countdown_handler(self):
        seconds = await self.db.interval()
        self.countdown_handler.change_interval(seconds=seconds)
        await self.bot.wait_until_ready()
        now = datetime.datetime.utcnow()

        guilds = await self.db.all_guilds()
        for guild in guilds:
            countdowns = guilds[guild]["countdowns"]

            if not countdowns:
                continue

            guild = self.bot.get_guild(guild)
            for countdown in countdowns:
                end_time = datetime.datetime.fromtimestamp(countdown["end_time"])
                if now > end_time:
                    async with self.db.guild(guild).countdowns() as countdowns:
                        countdowns.remove(countdown)
                    continue

                channel = self.bot.get_channel(countdown["channel_id"])
                if channel is None:
                    continue

                message = await channel.fetch_message(countdown["message_id"])
                author = channel.guild.get_member(countdown["author_id"])

                self.running_countdowns.append((
                    message,
                    author,
                    countdown["title"],
                    countdown["ending_message"],
                    end_time
                ))



    @commands.command()
    @checks.admin_or_permissions(administrator=True)
    async def countdown(self, ctx):
        """Starts a Countdown"""

        def message_check(message):
            if message.author.id != ctx.author.id:
                return False
            if message.channel != ctx.channel:
                return False
            if message.content.lower() == "cancel":
                raise CountdownAborted()
            return True

        await ctx.send('You have initiated the countdown interactive menu. '
                       'You have 60 seconds to answer each question and you '
                       'can cancel this anytime by replying with `cancel` to any '
                       'question.\nWhat is the title of this countdown?')
        title = await self.bot.wait_for('message', check=message_check, timeout=60)
        title = title.content

        await ctx.send(f'Ok, so the title will be `{title}`\n'
                       'What should be the message that is sent at the end of the countdown?')
        ending_message = await self.bot.wait_for('message', check=message_check, timeout=60)
        ending_message = ending_message.content

        await ctx.send("In which channel do you want to run this countdown?")
        channel = await self.bot.wait_for('message', check=message_check, timeout=60)
        channel = await commands.TextChannelConverter(
                            ).convert(ctx, channel.content)

        text = '''When will the countdown end?
The time can be any direct date (e.g. YYYY-MM-DD) or a human readable offset.
Examples:

- "next thursday at 3pm"
- "tomorrow"
- "in 3 days"
- "2d"

Times are in UTC.'''
        await ctx.send(text)
        end_time = await self.bot.wait_for('message', check=message_check, timeout=60)
        end_time = await UserFriendlyTime(
                    commands.clean_content,
                    default='\u2026'
                ).convert(ctx, end_time.content)


        embed = create_embed(title=title, end_time=end_time.dt)
        content = "\N{PARTY POPPER} New Countdown Started! \N{PARTY POPPER}"
        message = await channel.send(content, embed=embed)
        countdown = {
            "message_id": message.id,
            "author_id": ctx.author.id,
            "channel_id": channel.id,
            "title": title,
            "ending_message": ending_message,
            "end_time": end_time.dt.timestamp()
        }
        async with self.db.guild(ctx.guild).countdowns() as countdowns:
            countdowns.append(countdown)
        self.running_countdowns.append((
            message,
            ctx.author,
            title,
            ending_message,
            end_time.dt
        ))


    @countdown.error
    async def countdown_error(self, ctx, error):
        if isinstance(error, CommandInvokeError):
            original = error.original
            if isinstance(original, CountdownAborted):
                await ctx.send("Aborted!")
        elif isinstance(error, asyncio.exceptions.TimeoutError):
            await ctx.send("Timed Out!")
        elif isinstance(error, commands.BadArgument):
            await ctx.send(error)



    @commands.group(autohelp=True)
    @checks.admin_or_permissions(administrator=True)
    async def countdownset(self, ctx):
        """Commands for configuring Countdown cog"""
        pass


    @countdownset.command(name="interval")
    @checks.is_owner()
    async def set_interval(self, ctx, seconds:int=None):
        """
        Change the time after which each countdown message is edited
        seconds will default to 5 if set to less than 5
        Run the command without seconds to display the current interval

        Note: The interval is actually for the background loop.
        So basically, this won't show any effect unless the countdown timer is below 60 seconds
        Lower intervals also increase the accuracy of timer but imcreases CPU usage
        """
        if seconds is None:
            seconds = await self.db.interval()
            return await ctx.send(f"Current Interval is set to {seconds:,d} seconds!")
        seconds = max(seconds, 5)
        await self.db.interval.set(seconds)
        self.countdown_handler.change_interval(seconds=seconds)
        await ctx.send(f"Set the new interval time to {seconds:,d} seconds!")
