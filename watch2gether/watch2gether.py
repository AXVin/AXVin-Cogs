
# stdlib
from datetime import datetime

# discord.py
import aiohttp
import discord
import logging

# Red-DiscordBot
from redbot.core import Config, commands
from redbot.core.utils.predicates import ReactionPredicate
from redbot.core.utils.menus import start_adding_reactions



log = logging.getLogger("red.watch2gether")

__author__ = 'AXVin'
__version__ = '1.0.0'



guild_defaults = {
    "rooms": []
}

# rooms: [{
#     room_key: str,
#     author_id: int,
#     message_id: int,   = To know when it was created coz snowflakes
#     room_url: str
# }]


BaseCog = getattr(commands, "Cog", object)

class Watch2Gether(BaseCog):

    def __init__(self, bot):
        self.bot = bot
        self.db = Config.get_conf(self, 233059161401720832, force_registration=True)
        self.db.register_guild(**guild_defaults)
        self.session = aiohttp.ClientSession()


    async def cog_unload(self):
        self.session.close()


    @commands.command(aliases=["w2g"])
    @commands.guild_only()
    # @commands.has_permissions(administrator=True)
    async def watch2gether(self, ctx, link=None):
        '''
        Create a watch2gether room. If a link is provided then the room will be opened for that resource
        '''
        api_keys = await self.bot.get_shared_api_tokens("watch2gether")
        if api_keys.get("api_key") is None:
            return await ctx.send("The Watch2Gether API key has not been set. Set it with "
                                  f"`{ctx.prefix}set api watch2gether api_key,<api_key>` command")
        api_key = api_keys["api_key"]

        running_rooms = await self.db.guild(ctx.guild).rooms()
        if running_rooms:
            now = datetime.utcnow()
            room_strs = []
            for room in running_rooms:
                created_at = discord.Object(id=room["message_id"]).created_at
                if (now - created_at).total_seconds() > 43200:  # 12 hours
                    async with self.db.guild(ctx.guild).rooms() as rooms:
                        rooms.remove(room)
                        running_rooms.remove(room)
                else:
                    string = f"[Room URL]({room['room_url']}) (Created By - <@{room['author_id']}>)"
                    room_strs.append(string)
                if room_strs:
                    embed = discord.Embed(color=ctx.embed_color,
                                          title="Currently running rooms:")
                    embed.description = "\n".join(room_strs)
                    embed.set_footer(text="Click on any of the URLs above to enter the room.\n"
                                          'If you want to create a new room, react with "+" on this message')
                    message = await ctx.send(embed=embed)
                    
                    emojis = ["\N{HEAVY PLUS SIGN}", "\N{HEAVY MULTIPLICATION X}\N{VARIATION SELECTOR-16}"]
                    start_adding_reactions(message, emojis)
                    pred = ReactionPredicate.with_emojis(emojis,
                                                         message=message,
                                                         user=ctx.author)
                    await self.bot.wait_for("reaction_add", check=pred, timeout=60.0)
                    if pred.result == 1:
                        return await ctx.send("Aborted!")

        url = "https://www.watch2gether.com/rooms/create.json"
        data = {
            "api_key": api_key,
            "share": link
        }
        async with self.session.post(url, data=data) as resp:
            jsondata = await resp.json()

        room_key = jsondata["streamkey"]
        room_url = f"https://www.watch2gether.com/rooms/{room_key}"
        async with self.db.guild(ctx.guild).rooms() as rooms:
            rooms.append({
                "room_key": room_key,
                "room_url": room_url,
                "message_id": ctx.message.id,
                "author_id": ctx.author.id
            })

        await ctx.send(f"New Watch2Gether room created! You can access it through this "
                       "link: {stream_url}")

