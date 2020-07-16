
# stdlib
import datetime
import asyncio

# discord.py
import discord
from discord.ext import tasks
from discord.ext.commands.errors import CommandInvokeError

# Red-DiscordBot
from redbot.core import Config, commands, checks

# Current Plugin
from .time import human_timedelta, UserFriendlyTime

__author__ = 'AXVin'
__version__ = '1.2.0'


global_defaults = {
    "interval": 5
}

guild_defaults = {
    "countdowns": [],
    "datetime_formatting": None
}
# countdowns: [{
#     channel_id: int,      - where the countdown will be
#     message_id: int,      - the countdown message
#     author_id: int,       - who started this countdown
#     title: str,            - what this countdown is for
#     ending_message: str,  - the message on countdown end
#     end_time: str        - when it will end, see below
# }]

# We will use datetime.timestamp() to store it and datetime.fromtimestamp() to retrieve


class CountdownAborted(Exception):
    pass



class Countdown:

    def __init__(self,
                 bot, *,
                 config,
                 author: discord.User,
                 title: str,
                 ending_message: str,
                 end_time: datetime.datetime,
                 message: discord.Message=None,
                 channel: discord.TextChannel=None,
                 guild: discord.Guild=None):
        self.bot = bot
        self.config = config
        self.message = message
        if message:
            self.channel = channel or message.channel
            self.guild = guild or message.guild
        else:
            self.channel = channel
            self.guild = guild
        self.author = author
        self.title = title
        self.ending_message = ending_message
        self.end_time = end_time


    def __repr__(self):
        return (
            f"<Countdown title={self.title}, message={self.message!r}, "
            f"author={self.author!r}, channel={self.channel!r}"
        )


    @classmethod
    async def create(cls, *,
                     bot,
                     config,
                     author:discord.User,
                     channel:discord.TextChannel,
                     title: str,
                     ending_message: str,
                     end_time: datetime.datetime,
                     guild:discord.Guild=None,
                     update_config=True):
        '''
        Creates a countdown from the given information along with message
        '''
        guild = guild or channel.guild
        countdown  = cls(bot=bot,
                         config=config,
                         author=author,
                         channel=channel,
                         guild=guild,
                         title=title,
                         ending_message=ending_message,
                         end_time=end_time)

        content = "\N{PARTY POPPER} New Countdown Started! \N{PARTY POPPER}"
        embed = await countdown.create_embed()
        message = await channel.send(content=content,
                                     embed=embed)
        countdown.message = message

        if update_config:
            async with config.guild(guild).countdowns() as countdowns:
                countdowns.append(countdown.to_record())

        return countdown


    @classmethod
    async def convert(cls, ctx, arg):
        arg = arg.replace("discord.com", "discordapp.com")
        message = await commands.MessageConverter().convert(ctx, arg)
        try:
            countdown = [countdown for countdown in ctx.cog.running_countdowns if countdown.message.id == message.id][0]
        except IndexError:
            raise commands.BadArgument("Couldn't find a running countdown on that message")
        return countdown


    @classmethod
    async def from_record(cls, bot: commands.Bot, config, record: dict):
        channel = bot.get_channel(record['channel_id'])
        message = await channel.fetch_message(record['message_id'])
        guild = channel.guild
        author = bot.get_user(record['author_id'])
        end_time = datetime.datetime.fromtimestamp(record['end_time'])
        return cls(bot=bot,
                   config=config,
                   message=message,
                   channel=channel,
                   author=author,
                   title=record['title'],
                   ending_message=record['ending_message'],
                   end_time=end_time)


    def to_record(self) -> dict:
        return {
            "channel_id": self.channel.id,
            "message_id": self.message.id,
            "author_id": self.author.id,
            "title": self.title,
            "ending_message": self.ending_message,
            "end_time": self.end_time.timestamp()
        }

    async def create_embed(self, *, force_ended:bool=False) -> discord.Embed:
        '''
        Creates an embed

        Parameters:
        -----------
        force_ended: bool
            If the countdown was forcefully ended

        Returns:
        --------
        discord.Embed
            The created Embed
        '''
        now = datetime.datetime.utcnow()
        datetime_formatting = await self.config.guild(self.guild).datetime_formatting()

        embed = discord.Embed(title=self.title)
        if self.end_time <= now or force_ended:
            embed.color = 0xff0000
            embed.add_field(name="\u200b", value="\u200b")
            if datetime_formatting:
                fmt = now.strftime(datetime_formatting)
                embed.set_footer(text=f"Ended at: {fmt}")
            else:
                embed.set_footer(text=f"Ended at")
                embed.timestamp = now
        else:
            embed.color = 0x00ff00
            if datetime_formatting:
                fmt = self.end_time.strftime(datetime_formatting)
                embed.set_footer(text=f"Ends at: {fmt}")
            else:
                embed.timestamp=self.end_time
                embed.set_footer(text="Ends at")
            embed.add_field(name="\u200b", value="\u200b")
            ignore_seconds = True if (self.end_time - now).total_seconds() > 60 else False
            delta = human_timedelta(self.end_time, source=now, ignore_seconds=ignore_seconds)
            embed.add_field(name="Time Remaining:",
                            value=delta)

        return embed


    async def end(self, *, update_config:bool=True, force:bool=False):
        '''
        Ends the countdown

        Parameters:
        -----------
        update_config: bool
            if remove the countdown from config or not
        force: bool
            if the countdown was forcefully ended
        '''
        if update_config:
            async with self.config.guild(self.guild).countdowns() as countdowns:
                countdowns.remove(self.to_record())

        now = datetime.datetime.utcnow()

        message = await self.channel.send(self.ending_message)

        embed = await self.create_embed(force_ended=force)
        content = ("\N{HEAVY EXCLAMATION MARK SYMBOL} Countdown Ended! "
                   "\N{HEAVY EXCLAMATION MARK SYMBOL}")
        await self.message.edit(content=content,
                                embed=embed)




BaseCog = getattr(commands, "Cog", object)

class CountdownCog(BaseCog, name="Countdown"):

    def __init__(self, bot):
        self.bot = bot
        self.db = Config.get_conf(self, 208813050617266176, force_registration=True)
        self.db.register_guild(**guild_defaults)
        self.db.register_global(**global_defaults)
        self.running_countdowns: List[Countdown] = []
        self.countdown_handler.start()


    def cog_unload(self):
        self.countdown_handler.stop()


    @tasks.loop(seconds=5)
    async def countdown_handler(self):
        now = datetime.datetime.utcnow()
        for countdown in self.running_countdowns:
            embed = await countdown.create_embed()
            if countdown.end_time <= now:
                self.running_countdowns.remove(countdown)
                await countdown.end()
            else:
                content = "\N{PARTY POPPER} New Countdown Started! \N{PARTY POPPER}"
                if embed.to_dict() != countdown.message.embeds[0].to_dict():
                    await countdown.message.edit(content=content, embed=embed)
            


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
            for record in countdowns:
                try:
                    countdown = await Countdown.from_record(self.bot, self.db, record)
                except discord.errors.NotFound:
                    async with self.db.guild(guild).countdowns() as countdowns:
                        countdowns.remove(record)
                    continue

                if now > countdown.end_time:
                    async with self.db.guild(guild).countdowns() as countdowns:
                        countdowns.remove(record)
                    continue

                self.running_countdowns.append(countdown)



    @commands.group(invoke_without_command=True)
    @checks.mod_or_permissions(manage_guild=True)
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
        # to compensate the computing loss, we add 15 seconds to the end time
        # This shouldn't affect long countdowns much but might be great for short
        # ones
        end_time = end_time.dt + datetime.timedelta(seconds=15)


        countdown = await Countdown.create(
            bot=self.bot,
            config=self.db,
            author=ctx.author,
            channel=channel,
            title=title,
            ending_message=ending_message,
            end_time=end_time
        )

        self.running_countdowns.append(countdown)

        await ctx.send(f"Successfully created countdown in {channel.mention}!")


    @countdown.command(name="end")
    @checks.mod_or_permissions(manage_guild=True)
    async def countdown_end(self, ctx, message:Countdown):
        """
        Pre-maturely ends a countdown. message can be a jump url to the countdown message
        """
        countdown = message
        self.running_countdowns.remove(countdown)
        await countdown.end(force=True)
        await ctx.send("Ended that countdown!")




    @countdown.error
    async def countdown_error(self, ctx, error):
        if isinstance(error, CommandInvokeError):
            original = error.original
            if isinstance(original, CountdownAborted):
                await ctx.send("Aborted!")
            else:
                await self.bot.on_command_error(ctx,
                                                original,
                                                unhandled_by_cog=True)
        elif isinstance(error, asyncio.exceptions.TimeoutError):
            await ctx.send("Timed Out!")
        elif isinstance(error, commands.BadArgument):
            await ctx.send(error)



    @commands.group(autohelp=True)
    @checks.mod_or_permissions(manage_guild=True)
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


    @countdownset.command(name="datetime")
    @checks.mod_or_permissions(manage_guild=True)
    async def set_datetime_format(self, ctx, *, formatting:str=None):
        """
        Changes the datetime formatting for the footer in the countdown message
        Run without formatting to reset it to use timestamps instead of footer
        Check format variables @ https://strftime.org
        An example for this is "%I:%M:%S%p %d/%m/%Y" which might give "5:22:36pm 15/7/2020"
        """
        await self.db.guild(ctx.guild).datetime_formatting.set(formatting)
        msg = f"Set the new datetime formatting to {formatting}!"
        if formatting is not None:
            now = datetime.datetime.utcnow()
            fmt = now.strftime(formatting)
            msg += f"\nAn example of your set formatting for right now is {fmt}"
        await ctx.send(msg)
