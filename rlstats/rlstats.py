import discord
from discord.ext import commands

import asyncio
import aiohttp
import xml.etree.ElementTree as ET
import os
from .utils import checks
from .utils.dataIO import fileIO
import math
from collections import defaultdict
import re
import logging
from enum import Enum

try:
    from PIL import Image, ImageDraw, ImageFont, ImageColor, ImageOps
except:
    raise RuntimeError("Can't load pillow. Do 'pip3 install pillow'.")

try:
    from babel.numbers import format_decimal
except:
    raise RuntimeError("Can't load Babel. Do 'pip3 install Babel'.")

log = logging.getLogger('red.rlstats')

RANKS = (
    'Unranked',
    'Bronze I',
    'Bronze II',
    'Bronze III',
    'Silver I',
    'Silver II',
    'Silver III',
    'Gold I',
    'Gold II',
    'Gold III',
    'Platinum I',
    'Platinum II',
    'Platinum III',
    'Diamond I',
    'Diamond II',
    'Diamond III',
    'Champion I',
    'Champion II',
    'Champion III',
    'Grand Champion'
)
DIVISIONS = ('I', 'II', 'III', 'IV')


class Error(Exception):
    """RLStats base error"""


class UnallowedCharactersError(Error):
    """Username has unallowed characters"""


class NoChoiceError(Error):
    """User didn't choose profile which he wants to check"""


class PlayerNotFoundError(Error):
    """Username could not be found"""


class ServerError(Error):
    """Server returned 5xx HTTP error"""


class PlaylistKey(Enum):
    SOLO_DUEL = 10
    DOUBLES = 11
    SOLO_STANDARD = 12
    STANDARD = 13
    HOOPS = 27
    RUMBLE = 28
    DROPSHOT = 29
    SNOW_DAY = 30

    def __str__(self):
        return self.name.replace('_', ' ').title()


class TierEstimates:
    __slots__ = ['playlist', 'tier', 'division', 'div_down', 'div_up',
                 'tier_down', 'tier_up']
    tier_breakdown = None

    def __init__(self, playlist):
        self.playlist = playlist
        if playlist.tier == 0:
            self._estimate_current_tier()
        else:
            self.tier = playlist.tier
            self.division = playlist.division
        self._estimate_div_down()
        self._estimate_div_up()
        self._estimate_tier_down()
        self._estimate_tier_up()

    def _estimate_div_down(self):
        playlist = self.playlist
        if (
            self.tier == 1 and self.division == 0 or
            playlist.key not in self.tier_breakdown or
            self.tier == 0
        ):
            self.div_down = None
        else:
            try:
                divisions = self.tier_breakdown[playlist.key][self.tier]
                self.div_down = int(
                    math.ceil(
                        divisions[self.division][0] - playlist.skill
                    )
                )
            except KeyError as e:
                self.div_down = None
                log.debug(str(e))
                return
            if self.div_down > 0:
                self.div_down = -1

    def _estimate_div_up(self):
        playlist = self.playlist
        if (
            self.tier == self.playlist.tier_max or
            playlist.key not in self.tier_breakdown or
            self.tier == 0
        ):
            self.div_up = None
        else:
            try:
                divisions = self.tier_breakdown[playlist.key][self.tier]
                if self.tier == self.division == 0:
                    value = divisions[1][0]
                else:
                    value = divisions[self.division][1]
                self.div_up = int(
                    math.ceil(
                        value - playlist.skill
                    )
                )
            except KeyError as e:
                self.div_up = None
                log.debug(str(e))
                return
            if self.div_up < 0:
                self.div_up = 1

    def _estimate_tier_down(self):
        playlist = self.playlist
        if (
            self.tier == 1 or
            playlist.key not in self.tier_breakdown or
            self.tier == 0
        ):
            self.tier_down = None
        else:
            try:
                divisions = self.tier_breakdown[playlist.key][self.tier]
                self.tier_down = int(
                    math.ceil(
                        divisions[0][0] - playlist.skill
                    )
                )
            except KeyError as e:
                self.tier_down = None
                log.debug(str(e))
                return
            if self.tier_down > 0:
                self.tier_down = -1

    def _estimate_tier_up(self):
        playlist = self.playlist
        if (
            self.tier == self.playlist.tier_max or
            playlist.key not in self.tier_breakdown or
            self.tier == 0
        ):
            self.tier_up = None
        else:
            try:
                divisions = self.tier_breakdown[playlist.key][self.tier]
                self.tier_up = int(
                    math.ceil(
                        divisions[3][1] - playlist.skill
                    )
                )
            except KeyError as e:
                self.tier_up = None
                log.debug(str(e))
                return
            if self.tier_up < 0:
                self.tier_up = 1

    def _estimate_current_tier(self):
        playlist = self.playlist
        if playlist.key not in self.tier_breakdown:
            self.tier = playlist.tier
            self.division = playlist.division
            return
        breakdown = self.tier_breakdown[playlist.key]
        if playlist.skill < breakdown[1][1][0]:
            self.tier = 1
            self.division = 0
            return
        elif playlist.skill > breakdown[playlist.tier_max][0][1]:
            self.tier = playlist.tier_max
            self.division = 0
            return
        else:
            for tier, divisions in breakdown.items():
                for division, data in divisions.items():
                    if data[0] <= playlist.skill <= data[1]:
                        self.tier = tier
                        self.division = division
                        return
        self.tier = playlist.tier
        self.division = playlist.division

    @classmethod
    def load_tier_breakdown(cls, bot, update=False):
        if not os.path.isfile("data/rlstats/tier_breakdown.json") or update:
            print("Creating tier_breakdown.json...")
            bot.loop.create_task(cls.get_tier_breakdown())
        cls.tier_breakdown = cls._fix_numbers_dict(fileIO("data/rlstats/tier_breakdown.json", "load"))
        for k in cls.tier_breakdown.keys():
            try:
                playlist_key = PlaylistKey(k)
                cls.tier_breakdown[playlist_key] = cls.tier_breakdown.pop(k)
            except ValueError:
                pass

    @classmethod
    async def get_tier_breakdown(cls):
        # {10:{},11:{},12:{},13:{}}
        cls.tier_breakdown = defaultdict(lambda: defaultdict(dict))

        session = aiohttp.ClientSession()
        for i in range(1, 20):
            try:
                async with session.get('http://rltracker.pro/tier_breakdown/get_division_stats?tier_id={}'.format(i)) as resp:
                    tier = await resp.json()
            except (aiohttp.ClientResponseError, aiohttp.ClientError):
                log.error('Downloading tier breakdown did not succeed.')
                raise

            for breakdown in tier:
                cls.tier_breakdown[breakdown['playlist_id']][i][breakdown['division']] = [breakdown['from'], breakdown['to']]

        fileIO("data/rlstats/tier_breakdown.json", "save", cls.tier_breakdown)

    @classmethod
    def _fix_numbers_dict(cls, d: dict):
        """Converts (recursively) dictionary's keys with numbers to integers"""
        new = {}
        for k, v in d.items():
            if isinstance(v, dict):
                v = cls._fix_numbers_dict(v)
            elif isinstance(v, list):
                v = cls._fix_numbers_list(v)
            new[int(k)] = v
        return new

    @classmethod
    def _fix_numbers_list(cls, l: list):
        """Converts (recursively) list's values with numbers to floats"""
        new = []
        for v in l:
            if isinstance(v, dict):
                v = cls._fix_numbers_dict(v)
            elif isinstance(v, list):
                v = cls._fix_numbers_list(v)
            new.append(float(v))
        return new


class Playlist:
    __slots__ = ['key', 'tier', 'division', 'mu', 'skill',  'sigma',
                 'win_streak', 'matches_played', 'tier_max', 'tier_estimates']

    def __init__(self, **kwargs):
        self.key = kwargs.get('key')
        self.tier = kwargs.get('tier', 0)
        self.division = kwargs.get('division', 0)
        self.mu = kwargs.get('mu', 25)
        self.skill = kwargs.get('skill', self.mu*20+100)
        self.sigma = kwargs.get('sigma', 8.333)
        self.win_streak = kwargs.get('win_streak', 0)
        self.matches_played = kwargs.get('matches_played', 0)
        self.tier_max = kwargs.get('tier_max', 19)
        self.tier_estimates = TierEstimates(self)

    def __str__(self):
        try:
            if self.tier in [0, self.tier_max]:
                return RANKS[self.tier]
            else:
                return '{} Div {}'.format(
                    RANKS[self.tier], DIVISIONS[self.division]
                )
        except IndexError:
            return 'Unknown'


class Platform(Enum):
    steam = 'Steam'
    ps4 = 'Playstation 4'
    xboxone = 'Xbox One'

    def __str__(self):
        return self.value


class PlatformPatterns:
    steam = re.compile('[a-zA-Z0-9_-]{2,32}')
    ps4 = re.compile('[a-zA-Z][a-zA-Z0-9_-]{2,15}')
    xboxone = re.compile('[a-zA-Z](?=.{0,15}$)([a-zA-Z0-9-_]+ ?)+')


class SeasonRewards:
    __slots__ = ['level', 'wins', 'reward_ready']

    def __init__(self, **kwargs):
        self.level = kwargs.get('level', 0)
        if self.level is None:
            self.level = 0
        self.wins = kwargs.get('wins', 0)
        if self.wins is None:
            self.wins = 0
        highest_tier = kwargs.get('highest_tier', 0)
        if self.level == 0 or self.level * 3 < highest_tier:
            self.reward_ready = True
        else:
            self.reward_ready = False


class Player:
    """Represents Rocket League Player

    Attributes
    -----------
    platform : Platform
        Player's platform. There is a chance that the type will be ``int`` if
        the platform type is not within the ones recognised by the enumerator.

    """
    __slots__ = ['platform', 'user_name', 'user_id', 'playlists',
                 'highest_tier', 'season_rewards']

    def __init__(self, **kwargs):
        self.platform = kwargs.get('platform')
        try:
            self.platform = Platform[self.platform]
        except KeyError:
            pass
        self.user_name = kwargs.get('user_name')
        self.user_id = kwargs.get('user_id', self.user_name)
        self.playlists = {}
        self._prepare_playlists(kwargs.get('player_skills', []))
        if self.playlists:
            self.highest_tier = []
            for playlist in self.playlists.values():
                self.highest_tier.append(playlist.tier)
            self.highest_tier = max(self.highest_tier)
        else:
            self.highest_tier = 0
        self.season_rewards = kwargs.get('season_rewards', {})
        self.season_rewards['highest_tier'] = self.highest_tier
        self.season_rewards = SeasonRewards(**self.season_rewards)

    def get_playlist(self, playlist_key):
        return self.playlists.get(playlist_key)

    def add_playlist(self, playlist):
        playlist['key'] = playlist.pop('playlist')
        try:
            playlist['key'] = PlaylistKey(playlist['key'])
        except ValueError:
            pass

        self.playlists[playlist['key']] = Playlist(**playlist)

    def _prepare_playlists(self, player_skills):
        for playlist in player_skills:
            self.add_playlist(playlist)


class RLStats:
    """Get your Rocket League stats with a single command!"""
    # TODO:
    # add rltracker cog functionality to this cog
    # rest of TODO in rlstats method

    def __init__(self, bot):
        self.bot = bot
        self.check_folders()
        self.settings = fileIO("data/rlstats/settings.json", "load")
        self.session = aiohttp.ClientSession()
        self.emoji = {
            1: "1⃣",
            2: "2⃣",
            3: "3⃣",
            4: "4⃣"
        }
        self.size = (1920, 1080)
        self.fonts = {
            'RobotoCondensedBold90': ImageFont.truetype("data/rlstats/fonts/RobotoCondensedBold.ttf", 90),
            'RobotoBold45': ImageFont.truetype("data/rlstats/fonts/RobotoBold.ttf", 45),
            'RobotoLight45': ImageFont.truetype("data/rlstats/fonts/RobotoLight.ttf", 45),
            'RobotoRegular74': ImageFont.truetype("data/rlstats/fonts/RobotoRegular.ttf", 74)
        }
        self.offsets = {
            PlaylistKey.SOLO_DUEL: (0, 0),
            PlaylistKey.DOUBLES: (960, 0),
            PlaylistKey.SOLO_STANDARD: (0, 383),
            PlaylistKey.STANDARD: (960, 383)
        }
        self.coords = {
            'username': (960, 71),
            'playlist_name': (243, 197),
            'rank_image': (153, 248),
            'rank_text': (242, 453),  # center of rank text
            'matches_played': (822, 160),
            'win_streak': (492, 216),
            'skill': (729, 272),
            'gain': (715, 328),
            'div_down': (552, 384),
            'div_up': (727, 384),
            'tier_down': (492, 446),
            'tier_up': (667, 446),
            'rewards': (914, 921)
        }
        self.rank_size = (179, 179)
        self.tier_size = (49, 49)

    def check_folders(self):
        if not os.path.exists("data/rlstats"):
            print("Creating data/rlstats folder...")
            os.makedirs("data/rlstats")

        if not os.path.exists("data/rlstats/temp"):
            print("Creating data/rlstats/temp folder...")
            os.makedirs("data/rlstats/temp")

        self.check_files()

    def check_files(self):
        if not os.path.isfile("data/rlstats/settings.json"):
            default = {
                "USERS": {},
                "token": ""
            }
            print("Creating default rlstats settings.json...")
            fileIO("data/rlstats/settings.json", "save", default)

    async def _reaction_menu(self, ctx, content, choices, **kwargs):
        """menu control logic for this taken from
           https://github.com/Lunar-Dust/Dusty-Cogs/blob/master/menu/menu.py"""
        timeout = kwargs.get('timeout', 15)
        emoji = kwargs.get('emoji', self.emoji)

        if type(content) == discord.Embed:
            message = await self.bot.send_message(ctx.message.channel,
                                                  embed=content)
        else:
            message = await self.bot.say(content)

        for idx, i in enumerate(choices, 1):
            await self.bot.add_reaction(message, str(emoji[idx]))

        r = await self.bot.wait_for_reaction(
            emoji=list(emoji.values()),
            message=message,
            user=ctx.message.author,
            timeout=timeout)

        try:
            await self.bot.delete_message(message)
        except discord.Forbidden:
            pass

        if r is None:
            return None

        reacts = {v: k for k, v in emoji.items()}
        react = reacts[r.reaction.emoji]
        choice = choices[react-1]
        return choice

    def _add_coords(self, coords1, coords2):
        """Adds two tuples with coordinates (x,y)"""
        x = coords1[0] + coords2[0]
        y = coords1[1] + coords2[1]
        return (x, y)

    def _get_coords(self, playlist_id, coords_name):
        """Gets coords for given element in chosen playlist"""
        coords = self.coords[coords_name]
        offset = self.offsets[playlist_id]
        return self._add_coords(coords, offset)

    async def _get_player(self, ctx, id):
        players = []
        for platform in Platform:
            try:
                players += await self._find_profile(platform, id)
            except UnallowedCharactersError as e:
                log.debug(str(e))
        # Remove it after creating everything
        if not players:
            return None
        elif len(players) > 1:
            description = ''
            for idx, player in enumerate(players, 1):
                description += "\n{}. {} account with username: {}".format(
                    idx, player.platform, player.user_name
                )

            choice = await self._reaction_menu(
                ctx, discord.Embed(
                    title="There are multiple accounts with provided name:",
                    description=description
                ), choices=players
            )
            if choice is None:
                raise NoChoiceError("User didn't choose profile he wants to check")
            return choice
        else:
            return players[0]

    async def _find_profile(self, platform, id):
        pattern = getattr(PlatformPatterns, platform.name)
        if not pattern.fullmatch(id):
            raise UnallowedCharactersError(
                "Provided username doesn't match provided pattern: {}"
                .format(pattern)
            )

        players = []
        if platform == Platform.steam:
            ids = await self._find_steam_ids(id)
        else:
            ids = [id]

        for id in ids:
            try:
                player = await self._get_stats(platform, id)
                if player not in players:
                    players.append(player)
            except PlayerNotFoundError as e:
                log.debug(
                    str(e)
                )

        return players

    async def _find_steam_ids(self, id):
        search_types = ['profiles', 'id']
        ids = []
        for search_type in search_types:
            try:
                async with self.session.get('https://steamcommunity.com/{}/{}/?xml=1'.format(search_type, id)) as resp:
                    steam_profile = ET.fromstring(await resp.text())
            except (aiohttp.ClientResponseError, aiohttp.ClientError):
                await self.bot.say(
                    "An error occured while searching for Steam profile. "
                    "If this will happen again, please inform bot owner about the issue."
                )
                raise

            error = steam_profile.find('error')
            if error is None:
                ids.append(steam_profile.find('steamID64').text)
            elif error.text != 'The specified profile could not be found.':
                log.debug(
                    "Steam threw error while searching profile using '{}' method: {}"
                    .format(search_type, error.text)
                )

        return ids

    async def _get_stats(self, platform, id):
        try:
            async with self.session.get(
                'https://api.rocketleague.com/api/v1/{}/playerskills/{}/'.format(platform.name, id),
                headers={
                    'Authorization': 'Token {}'.format(self.settings['token'])
                }
            ) as resp:
                if resp.status >= 500:
                    raise ServerError(
                        "RL API threw server error (status code: {}) during request: {}"
                        .format(resp.status, await resp.text())
                    )
                player = await resp.json()
                if resp.status == 400 and 'not found' in player['detail']:
                    raise PlayerNotFoundError("Player with provided username could not be found.")
                elif resp.status >= 400:
                    log.error(
                        "RL API threw client error (status code: {}) during request: {}"
                        .format(resp.status, player['detail'])
                    )
                    await self.bot.say(
                        "An error occured while checking Rocket League Stats. "
                        "If this will happen again, please inform bot owner about the issue."
                    )
                    return
        except (aiohttp.ClientResponseError, aiohttp.ClientError):
            await self.bot.say(
                "An error occured while checking Rocket League Stats. "
                "If this will happen again, please inform bot owner about the issue."
            )
            raise

        player[0]['platform'] = platform
        return Player(**player[0])

    @checks.is_owner()
    @commands.group(pass_context=True, name="rlset")
    async def rlset(self, ctx):
        """Commands for setting Rocket League API settings.
        You can obtain your user token by
        requesting for API access in a ticket on https://support.rocketleague.com
        Under "Issue" you need to select Installation and setup > I need API access"""
        if ctx.invoked_subcommand is None:
            await self.bot.send_cmd_help(ctx)

    @checks.is_owner()
    @rlset.command(pass_context=True, name="token")
    async def set_token(self, ctx, token):
        """Sets the user token. USE THIS COMMAND IN PM"""
        if ctx.message.channel.is_private:
            self.settings["token"] = token
            fileIO("data/rlstats/settings.json", "save", self.settings)
            await self.bot.say("User token set successfully! You should probably remove your message with token for safety.")
        else:
            await self.bot.delete_message(ctx.message)
            await self.bot.say("You can't set token from server channel! Use this command in PM instead.")

    async def _is_token_set(self):
        """Checks if token is set"""
        if 'token' not in list(self.settings.keys()) or self.settings['token'] == "":
            return False
        else:
            return True

    async def _get_player_id_by_member_id(self, member_id):
        """nwm"""
        if member_id in self.settings['USERS']:
            userdata = dict(self.settings['USERS'][member_id])
            userdata['platform'] = Platform[userdata['platform']]
            return userdata
        else:
            return None

    @commands.command(pass_context=True)
    async def rlstats(self, ctx, *, id=None):
        """Checks for your or given player's Rocket League stats"""
        # TODO:
        # add icons for platforms
        # add ranked sports
        # add number of wins (there's no text right now, only bars)
        # make Tier and division estimates shorter (create some additional methods)

        await self.bot.send_typing(ctx.message.channel)

        if not await self._is_token_set():
            await self.bot.say((
                "`This cog wasn't configured properly. "
                "If you're the owner, setup the cog using {}rlset`"
            ).format(ctx.prefix))
            return

        if id is None:
            id = await self._get_player_id_by_member_id(ctx.message.author.id)
            if id is None:
                await self.bot.say((
                    "Your game account is not connected with Discord. "
                    "If you want to get stats, either give your ID after a command: "
                    "`{0}rlstats <ID>`"
                    " or connect your account using command: "
                    "`{0}rlconnect <ID>`"
                ).format(ctx.prefix))
                return
        else:
            converter = commands.MemberConverter(ctx, id)
            try:
                member = converter.convert()
                if member.id in self.settings['USERS']:
                    id = self.settings['USERS'][member.id]
                else:
                    await self.bot.say((
                        "This user hasn't connected his game account with Discord. "
                        "You need to search for his stats using his ID: "
                        "`{0}rlstats <ID>`"
                    ).format(ctx.prefix))
                    return
            except commands.errors.BadArgument:
                pass

        playlists = [PlaylistKey.SOLO_DUEL, PlaylistKey.DOUBLES,
                     PlaylistKey.SOLO_STANDARD, PlaylistKey.STANDARD]

        try:
            if isinstance(id, dict):
                player = await self._get_stats(id['platform'], id['id'])
            else:
                player = await self._get_player(ctx, id)
        except ServerError as e:
            log.error(str(e))
            await self.bot.say(
                "Rocket League API experiences some issues right now. Try again later."
            )
            return
        except NoChoiceError as e:
            log.debug(str(e))
            await self.bot.say(
                "You didn't choose profile you want to check."
            )
            return
        except PlayerNotFoundError as e:
            log.debug(str(e))
            await self.bot.say(
                "The specified profile could not be found."
            )
            return

        if player is None:
            log.debug("The specified profile could not be found.")
            await self.bot.say(
                "The specified profile could not be found."
            )
            return

        for playlist_key in playlists:
            if playlist_key not in player.playlists:
                player.add_playlist({'playlist': playlist_key})

        result = Image.open('data/rlstats/rank_bg.png').convert('RGBA')
        process = Image.new('RGBA', self.size)
        draw = ImageDraw.Draw(process)

        # Draw - username
        w, h = self.fonts["RobotoCondensedBold90"].getsize(player.user_name)
        coords = self._add_coords(self.coords['username'], (-w/2, -h/2))
        draw.text(coords, player.user_name,
                  font=self.fonts["RobotoCondensedBold90"], fill="white")

        # Draw - rank details
        for playlist_key in playlists:
            # Draw - playlist name
            w, h = self.fonts["RobotoRegular74"].getsize(str(playlist_key))
            coords = self._get_coords(playlist_key, 'playlist_name')
            coords = self._add_coords(coords, (-w/2, -h/2))
            draw.text(coords, str(playlist_key), font=self.fonts["RobotoRegular74"], fill="white")

            # Draw - rank image
            playlist = player.get_playlist(playlist_key)
            temp = Image.new('RGBA', self.size)
            temp_image = Image.open('data/rlstats/images/ranks/{}.png'.format(playlist.tier)).convert('RGBA')
            temp_image.thumbnail(self.rank_size, Image.ANTIALIAS)
            coords = self._get_coords(playlist_key, 'rank_image')
            temp.paste(temp_image, coords)
            process = Image.alpha_composite(process, temp)
            draw = ImageDraw.Draw(process)

            # Draw - rank name (e.g. Diamond 3 Div 1)

            w, h = self.fonts["RobotoLight45"].getsize(str(playlist))
            coords = self._get_coords(playlist_key, 'rank_text')
            coords = self._add_coords(coords, (-w/2, -h/2))
            draw.text(coords, str(playlist), font=self.fonts["RobotoLight45"], fill="white")

            # Draw - matches played
            coords = self._get_coords(playlist_key, 'matches_played')
            draw.text(coords, str(playlist.matches_played), font=self.fonts["RobotoBold45"], fill="white")

            # Draw - Win/Losing Streak
            if playlist.win_streak < 0:
                text = "Losing Streak:"
            else:
                text = "Win Streak:"
            w, h = self.fonts["RobotoLight45"].getsize(text)
            coords_text = self._get_coords(playlist_key, 'win_streak')
            coords_amount = self._add_coords(coords_text, (11+w, 0))
            # Draw - "Win Streak" or "Losing Streak"
            draw.text(coords_text, text, font=self.fonts["RobotoLight45"], fill="white")
            # Draw - amount of won/lost games
            draw.text(coords_amount, str(playlist.win_streak), font=self.fonts["RobotoBold45"], fill="white")

            # Draw - Skill Rating
            coords = self._get_coords(playlist_key, 'skill')
            draw.text(coords, str(playlist.skill), font=self.fonts["RobotoBold45"], fill="white")

            # Draw - Gain/Loss
            if os.path.isfile('data/rltracker/{}_{}.txt'.format(id, playlist_key)):
                with open('data/rltracker/{}_{}.txt'.format(id, playlist_key)) as file:
                    lines = file.readlines()
                    before = lines[-2].split(";")[3]
                    after = lines[-1].split(";")[3]
                    if before == "Mu":
                        gain = 0
                    else:
                        gain = abs((float(after) - float(before))*20)
            else:
                gain = 0

            coords = self._get_coords(playlist_key, 'gain')
            if gain == 0:
                draw.text(coords, "N/A", font=self.fonts["RobotoBold45"], fill="white")
            else:
                draw.text(coords, str(format_decimal((gain), format='#.###', locale='pl_PL')), font=self.fonts["RobotoBold45"], fill="white")

            # Draw - Tier and division estimates
            # Draw - Division Down
            coords = self._get_coords(playlist_key, 'div_down')
            if playlist.tier_estimates.div_down is None:
                div_down = 'N/A'
            else:
                div_down = '{0:+d}'.format(playlist.tier_estimates.div_down)
            draw.text(coords, div_down, font=self.fonts["RobotoBold45"], fill="white")

            # Draw - Tier Down
            # Icon
            tier = playlist.tier_estimates.tier
            tier_down = 'data/rlstats/images/ranks/{}.png'.format(
                tier-1 if tier > 0 else 0
            )
            tier_down_temp = Image.new('RGBA', self.size)
            tier_down_image = Image.open(tier_down).convert('RGBA')
            tier_down_image.thumbnail(self.tier_size, Image.ANTIALIAS)
            coords_image = self._get_coords(playlist_key, 'tier_down')
            tier_down_temp.paste(tier_down_image, coords_image)
            process = Image.alpha_composite(process, tier_down_temp)
            draw = ImageDraw.Draw(process)
            # Points
            if playlist.tier_estimates.tier_down is None:
                tier_down = 'N/A'
            else:
                tier_down = '{0:+d}'.format(playlist.tier_estimates.tier_down)
            coords_text = self._add_coords(coords_image, (self.tier_size[0]+11, -5))
            draw.text(coords_text, tier_down, font=self.fonts["RobotoBold45"], fill="white")

            # Draw - Division Up
            coords = self._get_coords(playlist_key, 'div_up')
            if playlist.tier_estimates.div_up is None:
                div_up = 'N/A'
            else:
                div_up = '{0:+d}'.format(playlist.tier_estimates.div_up)
            draw.text(coords, div_up, font=self.fonts["RobotoBold45"], fill="white")

            # Draw - Tier Up
            # Icon
            tier = playlist.tier_estimates.tier
            tier_up = 'data/rlstats/images/ranks/{}.png'.format(
                tier+1 if 0 < tier < playlist.tier_max else 0
            )
            tier_up_temp = Image.new('RGBA', self.size)
            tier_up_image = Image.open(tier_up).convert('RGBA')
            tier_up_image.thumbnail(self.tier_size, Image.ANTIALIAS)
            coords_image = self._get_coords(playlist_key, 'tier_up')
            tier_up_temp.paste(tier_up_image, coords_image)
            process = Image.alpha_composite(process, tier_up_temp)
            draw = ImageDraw.Draw(process)
            # Points
            coords_text = self._add_coords(coords_image, (self.tier_size[0]+11, -5))
            if playlist.tier_estimates.tier_up is None:
                tier_up = 'N/A'
            else:
                tier_up = '{0:+d}'.format(playlist.tier_estimates.tier_up)
            draw.text(coords_text, tier_up, font=self.fonts["RobotoBold45"], fill="white")

        # Season Reward Level
        rewards = player.season_rewards

        reward_temp = Image.new('RGBA', self.size)
        reward_image = Image.open(
            'data/rlstats/images/rewards/{:d}_{:d}.png'.format(
                rewards.level, rewards.reward_ready
            )
        ).convert('RGBA')
        reward_temp.paste(reward_image, (150, 886))
        process = Image.alpha_composite(process, reward_temp)
        draw = ImageDraw.Draw(process)
        # Season Reward Bars
        if player.season_rewards.level != 7:
            reward_bars_win_image = Image.open(
                'data/rlstats/images/rewards/bars/Bar_{:d}_Win.png'
                .format(rewards.level)
            ).convert('RGBA')
            if player.season_rewards.reward_ready:
                reward_bars_nowin_image = Image.open(
                    'data/rlstats/images/rewards/bars/Bar_{:d}_NoWin.png'
                    .format(rewards.level)
                ).convert('RGBA')
            else:
                reward_bars_nowin_image = Image.open(
                    'data/rlstats/images/rewards/bars/BarRed.png'
                ).convert('RGBA')
            for win in range(0, 10):
                reward_bars_temp = Image.new('RGBA', self.size)
                coords = self._add_coords(self.coords['rewards'], (win*83, 0))
                if rewards.wins > win:
                    reward_bars_temp.paste(reward_bars_win_image, coords)
                else:
                    reward_bars_temp.paste(reward_bars_nowin_image, coords)
                process = Image.alpha_composite(process, reward_bars_temp)
                draw = ImageDraw.Draw(process)

        # save result
        result = Image.alpha_composite(result, process)
        result.save('data/rlstats/temp/{}_profile.png'.format(id), 'PNG', quality=100)
        await self.bot.send_file(
            ctx.message.channel,
            'data/rlstats/temp/{}_profile.png'.format(id),
            content='Rocket League Stats for **{}** _(arrows show amount of points for division down/up)_'.format(player.user_name)
        )
        os.remove('data/rlstats/temp/{}_profile.png'.format(id))

    @commands.command(pass_context=True)
    async def rlconnect(self, ctx, id):
        """Connects game profile with Discord."""
        try:
            player = await self._get_player(ctx, id)
        except ServerError as e:
            log.error(str(e))
            await self.bot.say(
                "Rocket League API expierences some issues right now. Try again later."
            )
            return
        except NoChoiceError as e:
            log.debug(str(e))
            await self.bot.say(
                "You didn't choose profile you want to connect."
            )
            return

        if player is None:
            await self.bot.say(
                "The specified profile could not be found."
            )
            return

        self.settings["USERS"][ctx.message.author.id] = {
            'platform': player.platform,
            'id': player.user_id
        }
        fileIO("data/rlstats/settings.json", "save", self.settings)
        await self.bot.say(
            "You successfully connected your {} account with Discord!"
            .format(player.platform)
        )

    @checks.is_owner()
    @rlset.command(pass_context=True, name="updatebreakdown")
    async def updatebreakdown(self, ctx):
        """Update tier breakdown"""
        await self.bot.say("Updating tier breakdown...")
        await TierEstimates.get_tier_breakdown(self.bot, update=True)
        await self.bot.say("Tier breakdown updated.")


def setup(bot):
    TierEstimates.load_tier_breakdown(bot)
    bot.add_cog(RLStats(bot))