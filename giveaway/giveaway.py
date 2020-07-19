
# stdlib
import random
import asyncio
import datetime
import traceback
from io import BytesIO
from typing import List, Union

# discord.py
import discord
from discord.ext import tasks
from discord.ext.commands import Greedy
from discord.ext.commands.errors import CommandInvokeError

# Red-DiscordBot
from redbot.core import Config, commands, checks

# Current Plugin
from .time import human_timedelta, UserFriendlyTime
from .formats import human_join

__author__ = 'AXVin'
__version__ = '1.0.1'


global_defaults = {
    "interval": 5,
    "file_threshold": 20
}

guild_defaults = {
    "giveaways": [],
    "config": {
        "channel_id": None,
        "author_id": None,
        "ending_message": None,
        "winners": None,
        "roles": [],
        "join_days": None
    },
    "datetime_formatting": None
}
# giveaways: [{
#     channel_id: int,      - where the giveaway will be
#     message_id: int,      - the giveaway message
#     author_id: int,       - who started this giveaway
#     item: str,            - what this giveaway is for
#     ending_message: str,  - the message on giveaway end
#     end_time: str,        - when it will end, see below
#     winners: int,         - number of winners
#     roles: List[int]      - a list of role IDs required to enter
#     join_days: int        - how old the account must be for entering the giveaway
# }]
# We will use datetime.timestamp() to store time and datetime.fromtimestamp() to retrieve

class GiveawayAborted(Exception):
    pass



class Giveaway:

    def __init__(self,
                 bot, *,
                 config,
                 author: discord.User,
                 item: str,
                 ending_message: str,
                 end_time: datetime.datetime,
                 winners: int,
                 message: discord.Message=None,
                 channel: discord.TextChannel=None,
                 guild: discord.Guild=None,
                 roles: List[discord.Role]=None,
                 join_days: int=None):
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
        self.item = item
        self.ending_message = ending_message
        self.end_time = end_time
        self.winners = winners
        self.roles = roles
        self.join_days = join_days

    def __repr__(self):
        return (
            f"<Giveaway item={self.item}, message={self.message!r}, "
            f"author={self.author!r}, channel={self.channel!r}, "
            f"winners={self.winners}>"
        )


    @classmethod
    async def create(cls, *,
                     bot,
                     config,
                     author:discord.User,
                     channel:discord.TextChannel,
                     item: str,
                     ending_message: str,
                     end_time: datetime.datetime,
                     winners: int,
                     guild:discord.Guild=None,
                     roles: List[discord.Role]=None,
                     join_days: int=None,
                     update_config=True):
        '''
        Creates a giveaway from the given information along with message
        '''
        guild = guild or channel.guild
        giveaway  = cls(bot=bot,
                        config=config,
                        author=author,
                        channel=channel,
                        guild=guild,
                        item=item,
                        ending_message=ending_message,
                        end_time=end_time,
                        winners=winners,
                        roles=roles,
                        join_days=join_days)

        content = "\N{PARTY POPPER} New Giveaway Started! \N{PARTY POPPER}"
        embed = await giveaway.create_embed()
        message = await channel.send(content=content,
                                     embed=embed)
        giveaway.message = message

        if update_config:
            async with config.guild(guild).giveaways() as giveaways:
                giveaways.append(giveaway.to_record())

        # sometimes it doesn't add the reaction coz it's too new
        # idk, just monkey patching it
        await asyncio.sleep(0.5)
        await message.add_reaction("\N{PARTY POPPER}")
        return giveaway


    @classmethod
    async def convert(cls, ctx, arg):
        arg = arg.replace("discord.com", "discordapp.com")
        message = await commands.MessageConverter().convert(ctx, arg)
        try:
            giveaway = [giveaway for giveaway in ctx.cog.running_giveaways if giveaway.message.id == message.id][0]
        except IndexError:
            raise commands.BadArgument("Couldn't find a running giveaway on that message")
        return giveaway


    @classmethod
    async def from_record(cls, bot: commands.Bot, config, record: dict):
        channel = bot.get_channel(record['channel_id'])
        message = await channel.fetch_message(record['message_id'])
        guild = channel.guild
        author = bot.get_user(record['author_id'])
        end_time = datetime.datetime.fromtimestamp(record['end_time'])
        roles = [guild.get_role(role) for role in record['roles']] if record['roles'] else None
        return cls(bot=bot,
                   config=config,
                   message=message,
                   channel=channel,
                   author=author,
                   item=record['item'],
                   ending_message=record['ending_message'],
                   end_time=end_time,
                   roles=roles,
                   join_days=record['join_days'],
                   winners=record['winners'])


    def to_record(self) -> dict:
        return {
            "channel_id": self.channel.id,
            "message_id": self.message.id,
            "author_id": self.author.id,
            "item": self.item,
            "ending_message": self.ending_message,
            "end_time": self.end_time.timestamp(),
            "winners": self.winners,
            "roles": [role.id for role in self.roles] if self.roles else None,
            "join_days": self.join_days
        }

    async def create_embed(self,
                           winners:Union[discord.Attachment, List[discord.User]]=None):
        '''
        Creates an embed

        Parameters:
        -----------
        winners: Union[Attachment, List[discord.User]]
            The users who won the giveaway
            If provided, giveaway end embed will be generated

        Returns:
        --------
        discord.Embed
            The created Embed
        '''
        embed = discord.Embed(title=self.item)
        embed.add_field(name=f"Giveaway by:",
                        value=self.author.mention,
                        inline=True)

        now = datetime.datetime.utcnow()
        datetime_formatting = await self.config.guild(self.guild).datetime_formatting()

        if winners is not None:
            embed.color = 0xffffff
            if type(winners) == list:
                winners_list = [str(user.mention) for user in winners]
                winners_str = human_join(winners_list, final='and')
            else:
                winners_str = f"[winners.txt]({str(winners.url)})"
            embed.add_field(name="Winners:",
                            value=winners_str,
                            inline=True)
            if datetime_formatting:
                fmt = now.strftime(datetime_formatting)
                embed.set_footer(text=f"Ended at: {fmt}")
            else:
                embed.set_footer(text=f"Ended at")
                embed.timestamp = now
        else:
            embed.color = 0x00ff00
            embed.description = "React with :tada: to enter"

            if datetime_formatting:
                fmt = self.end_time.strftime(datetime_formatting)
                embed.set_footer(text=f"{self.winners} winners | Ends at: {fmt}")
            else:
                embed.timestamp=self.end_time
                embed.set_footer(text=f"{self.winners} winners | Ends at")

            ignore_seconds = True if (self.end_time - now).total_seconds() > 60 else False
            delta = human_timedelta(self.end_time, source=now, ignore_seconds=ignore_seconds)
            embed.add_field(name="Time Remaining:",
                            value=delta,
                            inline=True)
            requirements = []
            if self.roles:
                requirements.append(f"Roles: {' '.join([role.mention for role in self.roles])}")
            if self.join_days:
                requirements.append(f"Days in Server: {self.join_days}")
            if requirements:
                embed.add_field(name="Requirements",
                                value='\n'.join(requirements))
        return embed


    async def end(self, *, update_config=True):
        if update_config:
            async with self.config.guild(self.guild).giveaways() as giveaways:
                giveaways.remove(self.to_record())
        # Fetch message again to get fresh reactions
        message = await self.channel.fetch_message(self.message.id)
        reaction = discord.utils.get(message.reactions,
                                     emoji="\N{PARTY POPPER}")
        if reaction is None:
            return

        users = await reaction.users().flatten()
        try:
            users.remove(self.guild.me)
        except ValueError:
            pass

        now = datetime.datetime.utcnow()

        for user in users:
            if user.bot:
                users.remove(user)
                continue
            if self.roles:
                for role in self.roles:
                    if role not in user.roles:
                        users.remove(user)
                        continue

            if self.join_days:
                on_server = now - user.joined_at
                if on_server.days < self.join_days:
                    users.remove(user)


        winners_list = []
        if len(users) < self.winners:
            winners_list = users
        else:
            for n in range(self.winners):
                winner = random.choice(users)
                users.remove(winner)
                winners_list.append(winner)

        file_threshold = await self.config.file_threshold()

        file = None
        winners_str = ''
        if len(winners_list) <= file_threshold:
            winners_str = [str(member.mention) for member in winners_list]
            winners_str = human_join(winners_str, final='and')
        else:
            _winners_str = '\n'.join([f"{i}. - {member.id} - {member}" for i, member in enumerate(winners_list, start=1)])
            file = discord.File(fp=BytesIO(_winners_str.encode('utf8')),
                                filename=f'winners - {self.item}.txt')

        message = await self.channel.send(f"{self.ending_message}\n"
                                          f"**Giveaway Title:** {self.item}\n"
                                          f"**Giveaway Link:** {self.message.jump_url}\n"
                                          f"**Winners:** {winners_str}",
                                          file=file)

        winners = winners_list if len(winners_list) <= file_threshold else message.attachments[0]
        embed = await self.create_embed(winners=winners)
        content="\N{PARTY POPPER} Giveaway Ended \N{PARTY POPPER}"
        await self.message.edit(content=content,
                                embed=embed)





BaseCog = getattr(commands, "Cog", object)

class GiveawayCog(BaseCog, name="Giveaway"):

    def __init__(self, bot):
        self.bot = bot
        self.db = Config.get_conf(self, 624031920988094464, force_registration=True)
        self.db.register_guild(**guild_defaults)
        self.db.register_global(**global_defaults)
        self.running_giveaways: List[Giveaway] = []
        self.giveaway_handler.start()

    def cog_unload(self):
        self.giveaway_handler.stop()


    @tasks.loop(seconds=5)
    async def giveaway_handler(self):
        now = datetime.datetime.utcnow()

        for giveaway in self.running_giveaways:
            if giveaway.end_time <= now:
                self.running_giveaways.remove(giveaway)
                try:
                    await giveaway.end()
                except discord.errors.NotFound:
                    continue
            else:
                content = "\N{PARTY POPPER} New Giveaway Started! \N{PARTY POPPER}"
                embed = await giveaway.create_embed()
                if embed.to_dict() != giveaway.message.embeds[0].to_dict():
                    try:
                        await giveaway.message.edit(content=content,
                                                    embed=embed)
                    except discord.errors.NotFound:
                        async with self.db.guild(giveaway.guild).giveaways() as giveaways:
                            giveaways.remove(giveaway.to_record())
                        self.running_giveaways.remove(giveaway)
                        continue
                    # giveaway.message = message


    @giveaway_handler.before_loop
    async def before_countdown_handler(self):
        seconds = await self.db.interval()
        self.giveaway_handler.change_interval(seconds=seconds)
        await self.bot.wait_until_ready()
        now = datetime.datetime.utcnow()

        guilds = await self.db.all_guilds()
        for guild in guilds:
            giveaways = guilds[guild]["giveaways"]

            if not giveaways:
                continue

            guild = self.bot.get_guild(guild)
            for record in giveaways:
                try:
                    giveaway = await Giveaway.from_record(self.bot, self.db, record)
                except discord.errors.NotFound:
                    async with self.db.guild(guild).giveaways() as giveaways:
                        giveaways.remove(record)
                    continue

                if now > giveaway.end_time:
                    async with self.db.guild(guild).giveaways() as giveaways:
                        giveaways.remove(record)
                    continue

                self.running_giveaways.append(giveaway)



    @commands.group(autohelp=True)
    @checks.mod_or_permissions(manage_guild=True)
    async def giveaway(self, ctx):
        '''
        Commands for starting giveaways
        '''
        pass


    @giveaway.command(name='make')
    @checks.mod_or_permissions(manage_guild=True)
    async def giveaway_make(self, ctx):
        """Starts a giveaway interactive menu"""

        def message_check(message):
            if message.author.id != ctx.author.id:
                return False
            if message.channel != ctx.channel:
                return False
            if message.content.lower() == "cancel":
                raise GiveawayAborted()
            return True

        await ctx.send('You have initiated the giveaway interactive menu. '
                       'You have 60 seconds to answer each question and you '
                       'can cancel this anytime by replying with `cancel` to any '
                       'question.\nWhat is the title of this giveaway(the item '
                       'to be given away)?')
        item = await self.bot.wait_for('message', check=message_check, timeout=60)
        item = item.content


        await ctx.send(f'Ok, so the giveaway will be for `{item}`\n'
                       'How many winners would there be?')
        winners = await self.bot.wait_for('message', check=message_check, timeout=60)
        winners = winners.content
        try:
            winners = int(winners)
        except ValueError:
            return await ctx.send('This input must be a number. Aborted!')

        if winners < 1:
            winners = 1
            await ctx.send('The number of winners could not be less than 1 '
                           'so it was set to 1')

        file_threshold = await self.db.file_threshold()
        await ctx.send('What should be the message that is sent at the end of the '
                       'giveaway?\n\nNote: The winners will be mentioned in this '
                       F'at the end if they are <{file_threshold} in number'
                       ' otherwise a file with their names will be attached!')
        ending_message = await self.bot.wait_for('message', check=message_check, timeout=60)
        ending_message = ending_message.content

        await ctx.send("Who should be the author of this giveaway?")
        author = await self.bot.wait_for('message', check=message_check, timeout=60)
        author = await commands.UserConverter(
                            ).convert(ctx, author.content)

        await ctx.send("Do users require any roles to enter this giveaway?\n"
                       "If yes, then send the roles separated by spaces. "
                       "Otherwise send `None`\n\n"
                       "Note: For roles with spaces in their name, either "
                       "mention them or use their ID")
        roles = await self.bot.wait_for('message', check=message_check, timeout=60)
        roles = roles.content
        if roles.lower() == 'none':
            roles = None
        else:
            _roles = roles.split(' ')
            roles = []
            converter = commands.RoleConverter()
            for role in _roles:
                role = await converter.convert(ctx, role)
                roles.append(role)


        await ctx.send("How many days should the user have been in the server "
                       "to enter this giveaway?\nIf  you don't want to set this "
                       "requirement then just send `None`")
        join_days = await self.bot.wait_for('message', check=message_check, timeout=60)
        join_days = join_days.content
        if join_days.lower() == 'none':
            join_days = None
        else:
            try:
                join_days = int(join_days)
            except ValueError:
                return await ctx.send('This input must be a number. Aborted!')

            if join_days < 1:
                join_days = None
                await ctx.send('The number of join_days could not be less than 1 '
                               'so it was set to None')


        await ctx.send("In which channel do you want to run this giveaway?")
        channel = await self.bot.wait_for('message', check=message_check, timeout=60)
        channel = await commands.TextChannelConverter(
                            ).convert(ctx, channel.content)

        text = '''When will the giveaway end?
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
        # This shouldn't affect long giveaways much but might be great for short
        # ones
        end_time = end_time.dt + datetime.timedelta(seconds=15)


        giveaway = await Giveaway.create(
            bot=self.bot,
            config=self.db,
            author=author,
            channel=channel,
            item=item,
            ending_message=ending_message,
            end_time=end_time,
            winners=winners,
            roles=roles,
            join_days=join_days
        )
        self.running_giveaways.append(giveaway)
        await ctx.send(f"Successfully created giveaway in {channel.mention}!")





    @giveaway.command(name='quick')
    @checks.mod_or_permissions(manage_guild=True)
    async def giveaway_quick(self, ctx):
        """Starts a quick giveaway which uses the set config values"""

        def message_check(message):
            if message.author.id != ctx.author.id:
                return False
            if message.channel != ctx.channel:
                return False
            if message.content.lower() == "cancel":
                raise GiveawayAborted()
            return True

        config = await self.db.guild(ctx.guild).config()

        await ctx.send('You have initiated the giveaway interactive menu. '
                       'You have 60 seconds to answer each question and you '
                       'can cancel this anytime by replying with `cancel` to any '
                       'question.\nWhat is the title of this giveaway(the item '
                       'to be given away)?')
        item = await self.bot.wait_for('message', check=message_check, timeout=60)
        item = item.content


        if config['winners']:
            winners = config['winners']
        else:
            await ctx.send(f'Ok, so the giveaway will be for `{item}`\n'
                           'How many winners would there be?')
            winners = await self.bot.wait_for('message', check=message_check, timeout=60)
            winners = winners.content
            try:
                winners = int(winners)
            except ValueError:
                return await ctx.send('This input must be a number. Aborted!')

            if winners < 1:
                winners = 1
                await ctx.send('The number of winners could not be less than 1 '
                               'so it was set to 1')


        if config['ending_message']:
            ending_message = config['ending_message']
        else:
            file_threshold = await self.db.file_threshold()
            await ctx.send('What should be the message that is sent at the end of the '
                           'giveaway?\n\nNote: The winners will be mentioned in this '
                           f'at the end if they are <{file_threshold} in number'
                           ' otherwise a file with their names will be attached!')
            ending_message = await self.bot.wait_for('message', check=message_check, timeout=60)
            ending_message = ending_message.content


        if config['author_id']:
            author = self.bot.get_user(config['author_id'])
        else:
            await ctx.send("Who should be the author of this giveaway?")
            author = await self.bot.wait_for('message', check=message_check, timeout=60)
            author = await commands.UserConverter(
                                ).convert(ctx, author.content)

        if config['roles']:
            roles = [ctx.guild.get_role(role) for role in config['roles']]
            roles = [role for role in roles if role]
        else:
            await ctx.send("Do users require any roles to enter this giveaway?\n"
                           "If yes, then send the roles separated by spaces. "
                           "Otherwise send `None`\n\n"
                           "Note: For roles with spaces in their name, either "
                           "mention them or use their ID")
            roles = await self.bot.wait_for('message', check=message_check, timeout=60)
            roles = roles.content
            if roles.lower() == 'none':
                roles = None
            else:
                _roles = roles.split(' ')
                roles = []
                converter = commands.RoleConverter()
                for role in _roles:
                    role = await converter.convert(ctx, role)
                    roles.append(role)


        if config['join_days'] is None:
            await ctx.send("How many days should the user have been in the server "
                           "to enter this giveaway?\nIf  you don't want to set this "
                           "requirement then just send `None`")
            join_days = await self.bot.wait_for('message', check=message_check, timeout=60)
            join_days = join_days.content
            if join_days.lower() == 'none':
                join_days = None
            else:
                try:
                    join_days = int(join_days)
                except ValueError:
                    return await ctx.send('This input must be a number. Aborted!')

                if join_days < 1:
                    join_days = None
                    await ctx.send('The number of join_days could not be less than 1 '
                                   'so it was set to None')
        elif config['join_days'] == 0:
            join_days = None
        else:
            join_days = config['join_days']


        if config['channel_id']:
            channel = ctx.guild.get_channel(config['channel_id'])
        else:
            await ctx.send("In which channel do you want to run this giveaway?")
            channel = await self.bot.wait_for('message', check=message_check, timeout=60)
            channel = await commands.TextChannelConverter(
                                ).convert(ctx, channel.content)

        text = '''When will the giveaway end?
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
        # This shouldn't affect long giveaways much but might be great for short
        # ones
        end_time = end_time.dt + datetime.timedelta(seconds=15)


        giveaway = await Giveaway.create(
            bot=self.bot,
            config=self.db,
            author=author,
            channel=channel,
            item=item,
            ending_message=ending_message,
            end_time=end_time,
            winners=winners,
            roles=roles,
            join_days=join_days
        )
        self.running_giveaways.append(giveaway)
        await ctx.send(f"Successfully created giveaway in {channel.mention}!")



    @giveaway.command(name="end")
    @checks.mod_or_permissions(manage_guild=True)
    async def giveaway_end(self, ctx, message:Giveaway):
        """
        Pre-maturely ends a giveaway. message can be a jump url to the giveaway message
        """
        giveaway = message
        self.running_giveaways.remove(giveaway)
        await giveaway.end()
        await ctx.send("Ended that giveaway!")



    @giveaway_make.error
    @giveaway_quick.error
    async def giveaway_error(self, ctx, error):
        if isinstance(error, CommandInvokeError):
            original = error.original
            if isinstance(original, GiveawayAborted):
                await ctx.send("Aborted!")
            else:
                await self.bot.on_command_error(ctx, original, unhandled_by_cog=True)
        elif isinstance(error, asyncio.exceptions.TimeoutError):
            await ctx.send("Timed Out!")
        elif isinstance(error, commands.BadArgument):
            await ctx.send(error)



    @giveaway.group(autohelp=True)
    @checks.mod_or_permissions(manage_guild=True)
    async def config(self, ctx):
        '''
        Commands to set the default config for `[p]giveaway quick` command
        '''
        pass


    @config.command(name="show")
    @checks.mod_or_permissions(manage_guild=True)
    async def config_show(self, ctx):
        '''
        Shows the current config
        '''
        config = await self.db.guild(ctx.guild).config()

        author = self.bot.get_user(config['author_id']) if config['author_id'] else None
        author = author.mention if author else None

        channel = self.bot.get_user(config['channel_id']) if config['channel_id'] else None
        channel = channel.mention if channel else None

        roles = [ctx.guild.get_role(role) for role in config['roles']]
        roles = ', '.join([role.mention for role in roles if role])

        msg = f'''Author: {author}
Channel: {channel}
Winners: {config['winners']}
Join Days: {config['join_days']}
Roles: {roles}
Ending Message: {config['ending_message']}
'''
        await ctx.send(embed=discord.Embed(description=msg))



    @config.command(name="channel")
    @checks.mod_or_permissions(manage_guild=True)
    async def config_channel(self, ctx, channel:discord.TextChannel=None):
        '''
        Sets the default channel where giveaways will be held and announced
        Run without channel to reset it
        '''
        channel_id = channel.id if channel else None
        await self.db.guild(ctx.guild).config.channel_id.set(channel_id)
        await ctx.send(f"Set default channel to {channel}")


    @config.command(name="author")
    @checks.mod_or_permissions(manage_guild=True)
    async def config_author(self, ctx, user:discord.User=None):
        '''
        Set the default host/author for the giveaway
        Run without user to reset it
        '''
        author_id = user.id if user else None
        await self.db.guild(ctx.guild).config.author_id.set(author_id)
        await ctx.send(f"Set default author to {user}")


    @config.command(name="days", aliases=['join', 'join_days'])
    @checks.mod_or_permissions(manage_guild=True)
    async def config_join_days(self, ctx, days:int=None):
        '''
        Set the default requirement for number of days required to be in the server
        to join the giveaway. Run without days to remove the requirement
        '''
        await self.db.guild(ctx.guild).config.join_days.set(days)
        await ctx.send("Set default days required to be in server "
                       f"requirement to {days}")


    @config.command(name="end", aliases=['ending_message', 'endmessage'])
    @checks.mod_or_permissions(manage_guild=True)
    async def config_end_message(self, ctx, *, text:str=None):
        '''
        Set the default ending message
        Run without days to remove the requirement
        '''
        await self.db.guild(ctx.guild).config.ending_message.set(text)
        msg = "given value" if text else "None"
        await ctx.send(f"Set default end message to {msg}")



    @config.command(name="roles")
    @checks.mod_or_permissions(manage_guild=True)
    async def config_roles(self, ctx, *, roles:Greedy[discord.Role]=None):
        '''
        Set the default requirement for roles required to be in the server
        Run without roles to remove the requirement
        '''
        if roles is None:
            roles = []
        elif isinstance(roles, discord.Role):
            roles = [roles]
        
        role_ids = [role.id for role in roles]

        await self.db.guild(ctx.guild).config.roles.set(role_ids)
        if roles:
            role_str = ', '.join([role.name for role in roles])
        else:
            role_str = None
        await ctx.send(f"Set default roles required requirement to {role_str}")


    @config.command(name="winners")
    @checks.mod_or_permissions(manage_guild=True)
    async def config_winners(self, ctx, winners:int=None):
        '''
        Set the default number of winners. Run without days to remove the requirement
        '''
        await self.db.guild(ctx.guild).config.winners.set(winners)
        await ctx.send(f"Set default winners to {winners}")




    @commands.group(autohelp=True)
    @checks.mod_or_permissions(manage_guild=True)
    async def giveawayset(self, ctx):
        """Commands for configuring Countdown cog"""
        pass


    @giveawayset.command(name="interval")
    @checks.is_owner()
    async def set_interval(self, ctx, seconds:int=None):
        """
        Changes the time after which each giveaway message is edited
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
        self.giveaway_handler.change_interval(seconds=seconds)
        await ctx.send(f"Set the new interval time to {seconds:,d} seconds!")


    @giveawayset.command(name="file", aliases=['file_threshold'])
    @checks.is_owner()
    async def set_file(self, ctx, threshold:int=20):
        """
        Changes the threshold after which winners are sent as file attached to
        giveaway end message. Defaults to 20 and max is 50

        Note: It's adviced to keep this threshold low to avoid
        hitting 2000 character limit
        """
        seconds = max(threshold, 50)
        await self.db.file_threshold.set(threshold)
        await ctx.send(f"Set the new file threshold to {threshold}!")


    @giveawayset.command(name="datetime")
    @checks.mod_or_permissions(manage_guild=True)
    async def set_datetime_format(self, ctx, *, formatting:str=None):
        """
        Changes the datetime formatting for the footer in the giveaway message
        Run without formatting to reset it to use timestamps instead of footer
        Check format variables @ https://strftime.org
        An example for this is "%I:%M:%S%p %d/%m/%Y"
        which might give "5:22:36pm 15/7/2020"
        """
        await self.db.guild(ctx.guild).datetime_formatting.set(formatting)
        msg = f"Set the new datetime formatting to {formatting}!"
        if formatting is not None:
            now = datetime.datetime.utcnow()
            fmt = now.strftime(formatting)
            msg += f"\nAn example of your set formatting for right now is {fmt}"
        await ctx.send(msg)



    @commands.Cog.listener()
    async def on_raw_reaction_add(self, payload):
        if str(payload.emoji) != "\N{PARTY POPPER}":
            return

        guild = self.bot.get_guild(payload.guild_id)

        if guild is None:
            return

        member = payload.member or guild.get_member(payload.user_id)
        if member.bot:
            return

        giveaway = [giveaway for giveaway in self.running_giveaways if giveaway.message.id == payload.message_id]
        if not giveaway:
            return

        giveaway = giveaway[0]

        if giveaway.roles:
            for role in giveaway.roles:
                if role not in member.roles:
                    try:
                        await giveaway.message.remove_reaction(payload.emoji, member)
                    except:
                        break
                    else:
                        try:
                            await member.send(f"You need the {role.name} to "
                                              "enter this giveaway!")
                            break
                        except:
                            continue

        if giveaway.join_days:
            on_server = datetime.datetime.utcnow() - member.joined_at
            if on_server.days < giveaway.join_days:
                try:
                    await giveaway.message.remove_reaction(payload.emoji, member)
                except:
                    return
                else:
                    try:
                        return await member.send(
                            "You need to be in the server for atleast "
                            f"{giveaway.join_days}! You have been in it for "
                            f"only {on_server.days} days.")
                    except:
                        return
