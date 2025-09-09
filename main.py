import discord
from discord.ext import commands
import os
import random
import asyncio
import json
from datetime import datetime, timedelta
from keep_alive import keep_alive

TOKEN = os.getenv("TOKEN")

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)


class Tournament:

    def __init__(self):
        self.players = []
        self.max_players = 0
        self.active = False
        self.channel = None
        self.target_channel = None
        self.message = None
        self.rounds = []
        self.results = []
        self.eliminated = []
        self.fake_count = 1
        self.map = ""
        self.abilities = ""
        self.prize = ""
        self.title = ""


def get_tournament(guild_id):
    """Get tournament for specific guild"""
    if guild_id not in tournaments:
        tournaments[guild_id] = Tournament()
    return tournaments[guild_id]


# Store user data (all server-specific)
rp_data = {}  # {guild_id: {user_id: rp_amount}}
crown_data = {}  # {guild_id: {user_id: crown_count}}
log_channels = {}  # {guild_id: channel_id}
tournaments = {}  # {guild_id: Tournament}
role_permissions = {
}  # {guild_id: {'htr': [role_ids], 'adr': [role_ids], 'tlr': [role_ids]}}


def get_player_display_name(player, guild_id=None):
    """Get player display name with bracket emojis"""
    if isinstance(player, FakePlayer):
        return player.display_name

    # Get base name (Priority: nick > display_name > name > str(player))
    base_name = ""
    if hasattr(player, 'nick') and player.nick:
        base_name = player.nick
    elif hasattr(player, 'display_name') and player.display_name:
        base_name = player.display_name
    elif hasattr(player, 'name') and player.name:
        base_name = player.name
    else:
        base_name = str(player)

    # Add bracket role emojis if available
    if guild_id and hasattr(player, 'id'):
        guild_str = str(guild_id)
        if guild_str in bracket_roles and str(
                player.id) in bracket_roles[guild_str]:
            emojis = ''.join(bracket_roles[guild_str][str(player.id)])
            return f"{base_name} {emojis}"

    return base_name


# Load data
def load_data():
    global rp_data, crown_data, role_permissions, bracket_roles, log_channels
    try:
        with open('user_data.json', 'r') as f:
            data = json.load(f)
            # Support both old TP data and new RP data for migration
            rp_data = data.get('rp_data', data.get('tp_data', data.get('sp_data', {})))
            crown_data = data.get('crown_data', {})
            role_permissions = data.get('role_permissions', {})
            bracket_roles = data.get('bracket_roles', {})
            log_channels = data.get('log_channels', {})
    except FileNotFoundError:
        pass


def save_data():
    data = {
        'rp_data': rp_data,
        'crown_data': crown_data,
        'role_permissions': role_permissions,
        'bracket_roles': bracket_roles,
        'log_channels': log_channels
    }
    with open('user_data.json', 'w') as f:
        json.dump(data, f)


def add_rp(guild_id, user_id, rp):
    guild_str = str(guild_id)
    user_str = str(user_id)

    if guild_str not in rp_data:
        rp_data[guild_str] = {}

    if user_str not in rp_data[guild_str]:
        rp_data[guild_str][user_str] = 0

    rp_data[guild_str][user_str] += rp
    save_data()

def add_crown(guild_id, user_id, crowns=1):
    guild_str = str(guild_id)
    user_str = str(user_id)

    if guild_str not in crown_data:
        crown_data[guild_str] = {}

    if user_str not in crown_data[guild_str]:
        crown_data[guild_str][user_str] = 0

    crown_data[guild_str][user_str] += crowns
    save_data()

async def update_log_message(guild_id, channel):
    """Update or create log message with current RP and crown leaderboard"""
    guild_str = str(guild_id)
    guild_rp_data = rp_data.get(guild_str, {})
    guild_crown_data = crown_data.get(guild_str, {})
    
    # Combine and sort players by RP
    combined_data = []
    for user_id in set(list(guild_rp_data.keys()) + list(guild_crown_data.keys())):
        rp = guild_rp_data.get(user_id, 0)
        crowns = guild_crown_data.get(user_id, 0)
        if rp > 0 or crowns > 0:
            combined_data.append((user_id, rp, crowns))
    
    combined_data.sort(key=lambda x: x[1], reverse=True)  # Sort by RP
    
    log_text = "**Current Leaderboard:**\n"
    for user_id, rp, crowns in combined_data:
        guild = bot.get_guild(guild_id)
        user = guild.get_member(int(user_id)) if guild else None
        if user:
            log_text += f"{user.display_name} - {rp}<:Ranked:1411317994847473695>"
            if crowns > 0:
                log_text += f" {crowns}<:Crown:1394255336310968434>"
            
            # Add bracket role if exists
            if guild_str in bracket_roles and user_id in bracket_roles[guild_str]:
                emojis = ''.join(bracket_roles[guild_str][user_id])
                log_text += f" {emojis}"
            
            log_text += "\n"
    
    if not combined_data:
        log_text += "No players with RP or crowns yet."
    
    # Try to edit the last message, or send a new one
    try:
        async for message in channel.history(limit=1):
            if message.author == bot.user:
                await message.edit(content=log_text)
                return
    except:
        pass
    
    # Send new message if editing failed
    await channel.send(log_text)

async def log_reward_update(guild_id, user_id, rp_gained=0, crowns_gained=0):
    """Log when a player gains RP or crowns"""
    guild_str = str(guild_id)
    if guild_str in log_channels:
        channel_id = log_channels[guild_str]
        channel = bot.get_channel(channel_id)
        if channel:
            await update_log_message(guild_id, channel)


def has_permission(user, guild_id, permission_type):
    """Check if user has specific permission type"""
    guild_str = str(guild_id)
    if guild_str not in role_permissions:
        return False

    if permission_type not in role_permissions[guild_str]:
        return False

    user_role_ids = [role.id for role in user.roles]
    allowed_role_ids = role_permissions[guild_str][permission_type]

    return any(role_id in allowed_role_ids for role_id in user_role_ids)


@bot.event
async def on_ready():
    print(f"✅ Bot is online as {bot.user}")
    load_data()

    # Add persistent views for buttons to work after restart
    bot.add_view(TournamentView())
    bot.add_view(TournamentConfigView(None))
    bot.add_view(HosterRegistrationView())

    print("🔧 Bot is ready and all systems operational!")


class TournamentConfigModal(discord.ui.Modal,
                            title="Tournament Configuration"):

    def __init__(self, target_channel):
        super().__init__()
        self.target_channel = target_channel

    title_field = discord.ui.TextInput(label="🏆 Tournament Title",
                                       placeholder="Enter tournament title...",
                                       default="",
                                       max_length=100)

    map_field = discord.ui.TextInput(label="🗺️ Map",
                                     placeholder="Enter map name...",
                                     default="",
                                     max_length=50)

    abilities_field = discord.ui.TextInput(label="💥 Abilities",
                                           placeholder="Enter abilities...",
                                           default="",
                                           max_length=100)

    mode_and_players_field = discord.ui.TextInput(
        label="🎮 Mode & Max Players",
        placeholder="1v1 8 (format: mode maxplayers - only 1v1 mode allowed)",
        default="",
        max_length=20)

    prize_field = discord.ui.TextInput(label="💶 Prize",
                                       placeholder="Enter prize...",
                                       default="",
                                       max_length=50)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            # Validate target channel
            if not self.target_channel:
                await interaction.response.send_message(
                    "❌ Invalid target channel. Please try again.",
                    ephemeral=True)
                return

            # Parse mode and max players
            mode_players_parts = self.mode_and_players_field.value.strip(
            ).split()
            if len(mode_players_parts) != 2:
                await interaction.response.send_message(
                    "❌ Format should be: mode maxplayers (e.g., '1v1 8')",
                    ephemeral=True)
                return

            mode = mode_players_parts[0].lower()
            max_players = int(mode_players_parts[1])

            # Check if mode is valid (only 1v1 allowed)
            if mode not in ['1v1']:
                await interaction.response.send_message(
                    "❌ Only 1v1 mode is allowed! 2v2 mode has been eliminated.",
                    ephemeral=True)
                return

            if max_players not in [2, 4, 8, 16, 32]:
                await interaction.response.send_message(
                    "❌ Max players must be 2, 4, 8, 16 or 32!", ephemeral=True)
                return
        except ValueError:
            await interaction.response.send_message(
                "❌ Invalid format! Use: mode maxplayers (e.g., '1v1 8')",
                ephemeral=True)
            return
        except Exception as e:
            print(f"Error in tournament config modal: {e}")
            await interaction.response.send_message(
                "❌ An error occurred. Please try again.", ephemeral=True)
            return

        # Get server-specific tournament and reset it
        tournament = get_tournament(interaction.guild.id)
        tournament.__init__()
        tournament.max_players = max_players
        tournament.channel = self.target_channel
        tournament.target_channel = self.target_channel
        tournament.title = self.title_field.value
        tournament.map = self.map_field.value
        tournament.abilities = self.abilities_field.value
        tournament.prize = self.prize_field.value
        tournament.players = []
        tournament.eliminated = []
        tournament.active = False

        embed = discord.Embed(title=f"🏆 {tournament.title}", color=0x00ff00)
        embed.add_field(name="🗺️ Map", value=tournament.map, inline=True)
        embed.add_field(name="💥 Abilities",
                        value=tournament.abilities,
                        inline=True)
        embed.add_field(name="🎮 Mode", value=mode, inline=True)
        embed.add_field(name="💶 Prize", value=tournament.prize, inline=True)
        embed.add_field(name="👥 Max Players",
                        value=str(max_players),
                        inline=True)

        # Enhanced Stumble Guys rules with updated emojis
        rules_text = (
            "🔹 **NO TEAMING** - Teams are only allowed in designated team modes\n"
            "🔸 **NO GRIEFING** - Don't intentionally sabotage other players\n"
            "🔹 **NO EXPLOITING** - Use of glitches or exploits will result in disqualification\n"
            "🔸 **FAIR PLAY** - Respect all players and play honorably\n"
            "🔹 **NO RAGE QUITTING** - Leaving mid-match counts as a forfeit\n"
            "🔸 **FOLLOW HOST** - Listen to tournament host instructions\n"
            "🔹 **NO TOXICITY** - Keep chat friendly and respectful\n"
            "🔸 **BE READY** - Join matches promptly when called\n"
            "🔹 **NO ALTS** - One account per player only")

        embed.add_field(
            name=
            "<:notr:1409923674387251280> **Stumble Guys Tournament Rules**",
            value=rules_text,
            inline=False)

        view = TournamentView()
        # Update the participant count button to show correct max players
        for item in view.children:
            if hasattr(item,
                       'custom_id') and item.custom_id == "participant_count":
                item.label = f"0/{max_players}"
                break

        # Send tournament message
        tournament.message = await self.target_channel.send(embed=embed,
                                                            view=view)

        # Respond with success
        await interaction.response.send_message(
            "✅ Tournament created successfully!", ephemeral=True)

        print(
            f"✅ Tournament created: {max_players} max players, Map: {tournament.map}"
        )


class TournamentConfigView(discord.ui.View):

    def __init__(self, target_channel=None):
        super().__init__(timeout=None)
        self.target_channel = target_channel

    @discord.ui.button(label="Set Tournament",
                       style=discord.ButtonStyle.primary,
                       custom_id="set_tournament_config")
    async def set_tournament(self, interaction: discord.Interaction,
                             button: discord.ui.Button):
        try:
            # Use the channel where the interaction happened if no target channel is set
            target_channel = self.target_channel or interaction.channel

            # Ensure we have a valid channel
            if not target_channel:
                return await interaction.response.send_message(
                    "❌ Unable to determine target channel. Please try again.",
                    ephemeral=True)

            modal = TournamentConfigModal(target_channel)
            await interaction.response.send_modal(modal)
        except Exception as e:
            print(f"Error in set_tournament: {e}")
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "❌ An error occurred. Please try again.",
                        ephemeral=True)
                else:
                    await interaction.followup.send(
                        "❌ An error occurred. Please try again.",
                        ephemeral=True)
            except Exception as follow_error:
                print(f"Failed to send error message: {follow_error}")


class TournamentView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)  # Prevent auto-canceling

    async def interaction_check(self,
                                interaction: discord.Interaction) -> bool:
        return True

    @discord.ui.button(label="Register",
                       style=discord.ButtonStyle.green,
                       custom_id="tournament_register")
    async def register_button(self, interaction: discord.Interaction,
                              button: discord.ui.Button):
        try:
            tournament = get_tournament(interaction.guild.id)

            # Check tournament state
            if tournament.max_players == 0:
                return await interaction.response.send_message(
                    "❌ No tournament has been created yet.", ephemeral=True)
            if tournament.active:
                return await interaction.response.send_message(
                    "⚠️ Tournament already started.", ephemeral=True)
            if interaction.user in tournament.players:
                return await interaction.response.send_message(
                    "❌ You are already registered.", ephemeral=True)

            # Check if there's space
            if len(tournament.players) >= tournament.max_players:
                return await interaction.response.send_message(
                    "❌ Tournament is full.", ephemeral=True)

            tournament.players.append(interaction.user)

            for item in self.children:
                if hasattr(
                        item,
                        'custom_id') and item.custom_id == "participant_count":
                    item.label = f"{len(tournament.players)}/{tournament.max_players}"
                    break

            await interaction.response.edit_message(view=self)
            
            # Create detailed registration confirmation message
            registration_message = f"""Sucesfully registered!✅"""
            
            await interaction.followup.send(registration_message, ephemeral=True)

        except Exception as e:
            print(f"Error in register_button: {e}")
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "❌ An error occurred. Please try again.",
                        ephemeral=True)
                else:
                    await interaction.followup.send(
                        "❌ An error occurred. Please try again.",
                        ephemeral=True)
            except Exception as follow_error:
                print(f"Failed to send error message: {follow_error}")

    @discord.ui.button(label="Unregister",
                       style=discord.ButtonStyle.red,
                       custom_id="tournament_unregister")
    async def unregister_button(self, interaction: discord.Interaction,
                                button: discord.ui.Button):
        try:
            tournament = get_tournament(interaction.guild.id)

            if tournament.max_players == 0:
                return await interaction.response.send_message(
                    "❌ No tournament has been created yet.", ephemeral=True)
            if tournament.active:
                return await interaction.response.send_message(
                    "⚠️ Tournament already started.", ephemeral=True)
            if interaction.user not in tournament.players:
                return await interaction.response.send_message(
                    "❌ You are not registered.", ephemeral=True)

            tournament.players.remove(interaction.user)

            for item in self.children:
                if hasattr(
                        item,
                        'custom_id') and item.custom_id == "participant_count":
                    item.label = f"{len(tournament.players)}/{tournament.max_players}"
                    break

            await interaction.response.edit_message(view=self)
            await interaction.followup.send(
                f"✅ {interaction.user.display_name} unregistered! ({len(tournament.players)}/{tournament.max_players})",
                ephemeral=True)

        except Exception as e:
            print(f"Error in unregister_button: {e}")
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "❌ An error occurred. Please try again.",
                        ephemeral=True)
                else:
                    await interaction.followup.send(
                        "❌ An error occurred. Please try again.",
                        ephemeral=True)
            except Exception as follow_error:
                print(f"Failed to send error message: {follow_error}")

    @discord.ui.button(label="0/0",
                       style=discord.ButtonStyle.secondary,
                       disabled=True,
                       custom_id="participant_count")
    async def participant_count(self, interaction: discord.Interaction,
                                button: discord.ui.Button):
        pass

    @discord.ui.button(label="🚀 Start Tournament",
                       style=discord.ButtonStyle.primary,
                       custom_id="start_tournament")
    async def start_tournament(self, interaction: discord.Interaction,
                               button: discord.ui.Button):
        try:
            tournament = get_tournament(interaction.guild.id)

            if not has_permission(
                    interaction.user, interaction.guild.id, 'tlr'
            ) and not interaction.user.guild_permissions.manage_channels:
                return await interaction.response.send_message(
                    "❌ You don't have permission to start tournaments.",
                    ephemeral=True)

            if tournament.max_players == 0:
                return await interaction.response.send_message(
                    "❌ No tournament has been created yet.", ephemeral=True)

            if tournament.active:
                return await interaction.response.send_message(
                    "❌ Tournament already started.", ephemeral=True)

            # Allow tournament to start even without max players
            if len(tournament.players) < 2:
                return await interaction.response.send_message(
                    "❌ Not enough players to start tournament (minimum 2 players).",
                    ephemeral=True)

            await interaction.response.send_message("🚀 Starting tournament...",
                                                    ephemeral=True)

            # Shuffle players
            random.shuffle(tournament.players)

            # Handle odd number of players by adding None
            if len(tournament.players) % 2 == 1:
                none_player = FakePlayer("None", 999999999)
                tournament.players.append(none_player)

            tournament.active = True
            tournament.results = []
            tournament.rounds = []

            round_pairs = [(tournament.players[i], tournament.players[i + 1])
                           for i in range(0, len(tournament.players), 2)]
            tournament.rounds.append(round_pairs)

            embed = discord.Embed(
                title=f"🏆 {tournament.title} - Round 1",
                description=
                f"**Map:** {tournament.map}\n**Abilities:** {tournament.abilities}",
                color=0x3498db)

            for i, match in enumerate(round_pairs, 1):
                a, b = match
                player_a = get_player_display_name(a, interaction.guild.id)
                player_b = get_player_display_name(b, interaction.guild.id)
                embed.add_field(
                    name=f"⚔️ Match {i}",
                    value=
                    f"**{player_a}** <:vs:1394257911642984568> **{player_b}**\n<:StumbleStar:1394254979988197458>Winner: *Waiting...*",
                    inline=False)

            embed.set_footer(
                text="Use !winner @player to record match results")

            # Create a new view without the registration buttons for active tournament
            active_tournament_view = discord.ui.View(
                timeout=None)  # Prevent auto-canceling
            tournament.message = await interaction.channel.send(
                embed=embed, view=active_tournament_view)
            await interaction.followup.send(
                "✅ Tournament started successfully!", ephemeral=True)

        except Exception as e:
            print(f"Error in start_tournament: {e}")
            try:
                if not interaction.response.is_done():
                    await interaction.response.send_message(
                        "❌ An error occurred while starting the tournament.",
                        ephemeral=True)
                else:
                    await interaction.followup.send(
                        "❌ An error occurred while starting the tournament.",
                        ephemeral=True)
            except Exception as follow_error:
                print(f"Failed to send error message: {follow_error}")


class HosterRegistrationView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)  # Prevent auto-canceling

    async def interaction_check(self,
                                interaction: discord.Interaction) -> bool:
        return True

    @discord.ui.button(label="Register",
                       style=discord.ButtonStyle.green,
                       custom_id="hoster_register")
    async def register_hoster(self, interaction: discord.Interaction,
                              button: discord.ui.Button):
        if not host_registrations['active']:
            return await interaction.response.send_message(
                "❌ Hoster registration is not active.", ephemeral=True)

        if interaction.user in host_registrations['hosters']:
            return await interaction.response.send_message(
                "❌ You are already registered as a hoster.", ephemeral=True)

        if len(host_registrations['hosters']
               ) >= host_registrations['max_hosters']:
            return await interaction.response.send_message(
                "❌ Maximum number of hosters reached.", ephemeral=True)

        host_registrations['hosters'].append(interaction.user)

        # Update the embed
        embed = discord.Embed(
            title="🎯 Hoster Registration",
            description="Here the hosters will register to host tournaments!",
            color=0x00ff00)

        if host_registrations['hosters']:
            hoster_list = ""
            for i, hoster in enumerate(host_registrations['hosters'], 1):
                hoster_name = hoster.nick if hoster.nick else hoster.display_name
                hoster_list += f"{i}. {hoster_name}\n"
            embed.add_field(name="Hosters registered:",
                            value=hoster_list,
                            inline=False)
        else:
            embed.add_field(name="Hosters registered:",
                            value="None yet",
                            inline=False)

        embed.add_field(
            name="Slots:",
            value=
            f"{len(host_registrations['hosters'])}/{host_registrations['max_hosters']}",
            inline=True)

        await interaction.response.edit_message(embed=embed, view=self)
        await interaction.followup.send(
            f"✅ {interaction.user.display_name} registered as a hoster!",
            ephemeral=True)

    @discord.ui.button(label="Unregister",
                       style=discord.ButtonStyle.red,
                       custom_id="hoster_unregister")
    async def unregister_hoster(self, interaction: discord.Interaction,
                                button: discord.ui.Button):
        if not host_registrations['active']:
            return await interaction.response.send_message(
                "❌ Hoster registration is not active.", ephemeral=True)

        if interaction.user not in host_registrations['hosters']:
            return await interaction.response.send_message(
                "❌ You are not registered as a hoster.", ephemeral=True)

        host_registrations['hosters'].remove(interaction.user)

        # Update the embed
        embed = discord.Embed(
            title="🎯 Hoster Registration",
            description="Here the hosters will register to host tournaments!",
            color=0x00ff00)

        if host_registrations['hosters']:
            hoster_list = ""
            for i, hoster in enumerate(host_registrations['hosters'], 1):
                hoster_name = hoster.nick if hoster.nick else hoster.display_name
                hoster_list += f"{i}. {hoster_name}\n"
            embed.add_field(name="Hosters registered:",
                            value=hoster_list,
                            inline=False)
        else:
            embed.add_field(name="Hosters registered:",
                            value="None yet",
                            inline=False)

        embed.add_field(
            name="Slots:",
            value=
            f"{len(host_registrations['hosters'])}/{host_registrations['max_hosters']}",
            inline=True)

        await interaction.response.edit_message(embed=embed, view=self)
        await interaction.followup.send(
            f"✅ {interaction.user.display_name} unregistered from hosting.",
            ephemeral=True)

    @discord.ui.button(label="End Register",
                       style=discord.ButtonStyle.secondary,
                       custom_id="end_hoster_register")
    async def end_registration(self, interaction: discord.Interaction,
                               button: discord.ui.Button):
        if not has_permission(
                interaction.user, interaction.guild.id, 'tlr'
        ) and not interaction.user.guild_permissions.manage_channels:
            return await interaction.response.send_message(
                "❌ You don't have permission to end registration.",
                ephemeral=True)

        host_registrations['active'] = False

        # Keep the existing embed but disable all buttons
        embed = discord.Embed(
            title="🎯 Hoster Registration - CLOSED",
            description="Hoster registration has been closed by a moderator.",
            color=0xff0000)

        if host_registrations['hosters']:
            hoster_list = ""
            for i, hoster in enumerate(host_registrations['hosters'], 1):
                hoster_name = hoster.nick if hoster.nick else hoster.display_name
                hoster_list += f"{i}. {hoster_name}\n"
            embed.add_field(name="Final Hosters registered:",
                            value=hoster_list,
                            inline=False)
        else:
            embed.add_field(name="Final Hosters registered:",
                            value="None",
                            inline=False)

        embed.add_field(
            name="Final Slots:",
            value=
            f"{len(host_registrations['hosters'])}/{host_registrations['max_hosters']}",
            inline=True)

        # Disable all buttons
        for item in self.children:
            item.disabled = True

        await interaction.response.edit_message(embed=embed, view=self)


# Global host registrations
host_registrations = {
    'active': False,
    'max_hosters': 0,
    'hosters': [],
    'channel': None,
    'message': None
}

# Bracket roles data
bracket_roles = {}


@bot.command()
async def create(ctx, channel: discord.TextChannel):
    try:
        await ctx.message.delete()
    except:
        pass

    if not has_permission(
            ctx.author, ctx.guild.id,
            'tlr') and not ctx.author.guild_permissions.manage_channels:
        return await ctx.send(
            "❌ You don't have permission to create tournaments.",
            delete_after=5)

    tournament = get_tournament(ctx.guild.id)
    tournament.target_channel = channel

    embed = discord.Embed(
        title="🏆 Tournament Setup",
        description="Press the button to configure the tournament settings.",
        color=0x00ff00)

    view = TournamentConfigView(channel)
    await ctx.send(embed=embed, view=view)


@bot.command()
async def start(ctx):
    try:
        await ctx.message.delete()
    except:
        pass

    if not has_permission(
            ctx.author, ctx.guild.id,
            'tlr') and not ctx.author.guild_permissions.manage_channels:
        return await ctx.send(
            "❌ You don't have permission to start tournaments.",
            delete_after=5)

    tournament = get_tournament(ctx.guild.id)

    if tournament.max_players == 0:
        return await ctx.send(
            "❌ No tournament has been created yet. Use `!create #channel` first.",
            delete_after=5)

    if tournament.active:
        return await ctx.send("❌ Tournament already started.", delete_after=5)

    if len(tournament.players) < 2:
        return await ctx.send(
            "❌ Not enough players to start tournament (minimum 2 players).",
            delete_after=5)

    # Add fake players if needed to fill up the tournament
    players_to_add = tournament.max_players - len(tournament.players)

    if players_to_add > 0:
        await ctx.send(
            f"Adding {players_to_add} bot player(s) to fill the tournament...",
            delete_after=5)
        # Add fake players as proper objects
        fake_players_added = []
        for i in range(players_to_add):
            fake_name = f"Bot{tournament.fake_count}"
            fake_id = 761557952975420886 + tournament.fake_count
            fake_player = FakePlayer(fake_name, fake_id)
            fake_players_added.append(fake_player)
            tournament.fake_count += 1
        tournament.players.extend(fake_players_added)

    # Shuffle players
    random.shuffle(tournament.players)

    tournament.active = True
    tournament.results = []
    tournament.rounds = []

    round_pairs = [(tournament.players[i], tournament.players[i + 1])
                   for i in range(0, len(tournament.players), 2)]
    tournament.rounds.append(round_pairs)

    embed = discord.Embed(
        title=f"🏆 {tournament.title} - Round 1",
        description=
        f"**Map:** {tournament.map}\n**Abilities:** {tournament.abilities}",
        color=0x3498db)

    for i, match in enumerate(round_pairs, 1):
        a, b = match
        player_a = get_player_display_name(a, ctx.guild.id)
        player_b = get_player_display_name(b, ctx.guild.id)
        embed.add_field(
            name=f"⚔️ Match {i}",
            value=
            f"**{player_a}** <:vs:1394257911642984568> **{player_b}**\n<:StumbleStar:1394254979988197458>Winner: *Waiting...*",
            inline=False)

    embed.set_footer(text="Use !winner @player to record match results")

    # Create a new view without buttons for active tournament
    active_tournament_view = discord.ui.View()
    tournament.message = await ctx.send(embed=embed,
                                        view=active_tournament_view)


@bot.command()
async def winner(ctx, member: discord.Member):
    try:
        await ctx.message.delete()
    except:
        pass

    if not has_permission(
            ctx.author, ctx.guild.id, 'htr') and not has_permission(
                ctx.author, ctx.guild.id,
                'tlr') and not ctx.author.guild_permissions.manage_channels:
        return await ctx.send("❌ You don't have permission to set winners.",
                              delete_after=5)

    tournament = get_tournament(ctx.guild.id)

    if not tournament.active:
        return await ctx.send("❌ No active tournament.", delete_after=5)

    current_round = tournament.rounds[-1]
    winner_name = get_player_display_name(member, ctx.guild.id)

    # Find and update the match
    match_found = False
    eliminated_players = []
    match_index = -1

    for i, match in enumerate(current_round):
        a, b = match
        # Handle automatic advancement when player faces None
        if isinstance(a, FakePlayer) and a.display_name == "None":
            tournament.results.append(b)
            match_found = True
            match_index = i
            member = b  # Set member to the advancing player for display
            break
        elif isinstance(b, FakePlayer) and b.display_name == "None":
            tournament.results.append(a)
            match_found = True
            match_index = i
            member = a  # Set member to the advancing player for display
            break
        elif member == a or member == b:
            tournament.results.append(member)
            eliminated_players.extend([a if member == b else b])
            match_found = True
            match_index = i
            break

    if not match_found:
        return await ctx.send("❌ This player is not in the current round.",
                              delete_after=5)

    # Add eliminated players to elimination list
    tournament.eliminated.extend(eliminated_players)

    # Update current tournament message to show the winner
    if tournament.message:
        try:
            current_embed = tournament.message.embeds[0]

            # Find and update the specific match field
            if match_index >= 0 and match_index < len(current_embed.fields):
                field = current_embed.fields[match_index]
                if "Match" in field.name:
                    field_value = field.value
                    lines = field_value.split('\n')
                    lines[
                        1] = f"<:StumbleStar:1394254979988197458>Winner: **{get_player_display_name(member, ctx.guild.id)}**"

                    current_embed.set_field_at(match_index,
                                               name=field.name,
                                               value='\n'.join(lines),
                                               inline=field.inline)
                    await tournament.message.edit(embed=current_embed)

        except Exception as e:
            print(f"Error updating tournament message: {e}")

    # Check if round is complete
    if len(tournament.results) == len(current_round):
        if len(tournament.results) == 1:
            # Tournament finished - determine placements and award TP
            winner_data = tournament.results[0]

            # Calculate placements based on elimination order
            all_eliminated = tournament.eliminated

            # Get the final 4 placements
            placements = []  # List of (place, player, rp_reward, crown_reward)

            # 1st place (winner) - 100 RP + 1 Crown
            placements.append((1, winner_data, 100, 1))
            if hasattr(winner_data,
                       'id') and not isinstance(winner_data, FakePlayer):
                add_rp(ctx.guild.id, winner_data.id, 100)
                add_crown(ctx.guild.id, winner_data.id, 1)
                await log_reward_update(ctx.guild.id, winner_data.id, 100, 1)

            # 2nd place (last eliminated) - 50 RP
            if len(all_eliminated) >= 1:
                placements.append((2, all_eliminated[-1], 50, 0))
                player = all_eliminated[-1]
                if hasattr(player,
                           'id') and not isinstance(player, FakePlayer):
                    add_rp(ctx.guild.id, player.id, 50)
                    await log_reward_update(ctx.guild.id, player.id, 50, 0)

            # 3rd and 4th place - 30 RP each
            if len(all_eliminated) >= 2:
                placements.append((3, all_eliminated[-2], 30, 0))
                player = all_eliminated[-2]
                if hasattr(player,
                           'id') and not isinstance(player, FakePlayer):
                    add_rp(ctx.guild.id, player.id, 30)
                    await log_reward_update(ctx.guild.id, player.id, 30, 0)
            if len(all_eliminated) >= 3:
                placements.append((4, all_eliminated[-3], 30, 0))
                player = all_eliminated[-3]
                if hasattr(player,
                           'id') and not isinstance(player, FakePlayer):
                    add_rp(ctx.guild.id, player.id, 30)
                    await log_reward_update(ctx.guild.id, player.id, 30, 0)

            # Create styled tournament winners embed
            winner_display = get_player_display_name(winner_data, ctx.guild.id)

            embed = discord.Embed(
                title="🏆 Tournament Winners!",
                description=
                f"Congratulations to **{winner_display}** for winning the\n**{tournament.title}** tournament! 🎉",
                color=0xffd700)

            # Add tournament info with emojis
            embed.add_field(name="🗺️ Map", value=tournament.map, inline=True)
            embed.add_field(name="💥 Abilities",
                            value=tournament.abilities,
                            inline=True)
            embed.add_field(name="🎮 Mode", value="1v1", inline=True)

            # Create results text
            results_display = ""
            for place, player_obj, rp, crowns in placements:
                if place == 1:
                    emoji = "🥇"
                elif place == 2:
                    emoji = "🥈"
                elif place == 3:
                    emoji = "🥉"
                elif place == 4:
                    emoji = "4️⃣"
                else:
                    emoji = "📍"

                player_str = get_player_display_name(player_obj, ctx.guild.id)
                results_display += f"{emoji} {player_str}\n"

            embed.add_field(name="🏆 Final Rankings",
                            value=results_display,
                            inline=False)

            # Add prizes section with RP and Crowns
            prize_text = ""
            for place, player_obj, rp, crowns in placements:
                if place == 1:
                    emoji = "🥇"
                elif place == 2:
                    emoji = "🥈"
                elif place == 3:
                    emoji = "🥉"
                elif place == 4:
                    emoji = "4️⃣"
                else:
                    emoji = "📍"

                place_suffix = "st" if place == 1 else "nd" if place == 2 else "rd" if place == 3 else "th"
                reward_text = f"{rp}<:Ranked:1411317994847473695>"
                if crowns > 0:
                    reward_text += f"+{crowns}<:Crown:1394255336310968434>"
                prize_text += f"{emoji} {place}{place_suffix}: {reward_text}\n"

            embed.add_field(name="🏆 Prizes", value=prize_text, inline=False)

            # Add winner's avatar if it's a real player
            winner_player_obj = winner_data
            if hasattr(winner_player_obj, 'display_avatar') and not isinstance(
                    winner_player_obj, FakePlayer):
                embed.set_thumbnail(url=winner_player_obj.display_avatar.url)

            # Add footer with tournament ID and timestamp
            embed.set_footer(
                text=
                f"Tournament completed • {datetime.now().strftime('%d.%m.%Y %H:%M')}"
            )

            # Create a new view without buttons for the completed tournament
            completed_view = discord.ui.View()
            await ctx.send(embed=embed, view=completed_view)

            # Reset tournament
            tournament.__init__()
        else:
            # Create next round
            # Handle odd number of winners by adding None
            if len(tournament.results) % 2 == 1:
                none_player = FakePlayer("None", 999999999)
                tournament.results.append(none_player)

            next_round_pairs = []
            for i in range(0, len(tournament.results), 2):
                if i + 1 < len(tournament.results):
                    next_round_pairs.append(
                        (tournament.results[i], tournament.results[i + 1]))

            tournament.rounds.append(next_round_pairs)
            tournament.results = []

            round_num = len(tournament.rounds)
            embed = discord.Embed(
                title=f"🏆 {tournament.title} - Round {round_num}",
                description=
                f"**Map:** {tournament.map}\n**Abilities:** {tournament.abilities}",
                color=0x3498db)

            for i, match in enumerate(next_round_pairs, 1):
                a, b = match
                player_a = get_player_display_name(a, ctx.guild.id)
                player_b = get_player_display_name(b, ctx.guild.id)
                embed.add_field(
                    name=f"⚔️ Match {i}",
                    value=
                    f"**{player_a}** <:vs:1394257911642984568> **{player_b}**\n<:StumbleStar:1394254979988197458>Winner: *Waiting...*",
                    inline=False)

            embed.set_footer(
                text="Use !winner @player to record match results")

            # Create a new view without buttons for active tournament
            active_tournament_view = discord.ui.View()
            tournament.message = await ctx.send(embed=embed,
                                                view=active_tournament_view)

    await ctx.send(f"✅ {winner_name} wins their match!", delete_after=5)


class FakePlayer:

    def __init__(self, name, user_id):
        self.display_name = name
        self.name = name
        self.nick = name
        self.id = user_id
        self.mention = f"<@{user_id}>"

    def __str__(self):
        return self.mention


@bot.command()
async def fake(ctx, number: int = 1):
    try:
        await ctx.message.delete()
    except:
        pass

    if not has_permission(
            ctx.author, ctx.guild.id,
            'tlr') and not ctx.author.guild_permissions.manage_channels:
        return await ctx.send(
            "❌ You don't have permission to add fake players.", delete_after=5)

    tournament = get_tournament(ctx.guild.id)

    if number < 1 or number > 16:
        return await ctx.send("❌ Number must be between 1 and 16.",
                              delete_after=5)

    if tournament.max_players == 0:
        return await ctx.send("❌ No tournament created yet.", delete_after=5)

    if tournament.active:
        return await ctx.send("❌ Tournament already started.", delete_after=5)

    available_spots = tournament.max_players - len(tournament.players)

    if number > available_spots:
        return await ctx.send(f"❌ Only {available_spots} spots available.",
                              delete_after=5)

    # Create fake players as proper objects
    fake_players = []
    for i in range(number):
        fake_name = f"FakePlayer{tournament.fake_count}"
        fake_id = 761557952975420886 + tournament.fake_count
        fake_player = FakePlayer(fake_name, fake_id)
        fake_players.append(fake_player)
        tournament.fake_count += 1

    tournament.players.extend(fake_players)

    fake_list = ", ".join([f.display_name for f in fake_players])
    await ctx.send(
        f"🤖 Added {number} fake player{'s' if number > 1 else ''}: {fake_list}\nTotal players: {len(tournament.players)}/{tournament.max_players}",
        delete_after=10)


@bot.command()
async def code(ctx, code: str, member: discord.Member = None):
    try:
        await ctx.message.delete()
    except:
        pass

    if not has_permission(
            ctx.author, ctx.guild.id, 'htr') and not has_permission(
                ctx.author, ctx.guild.id,
                'tlr') and not ctx.author.guild_permissions.manage_channels:
        return await ctx.send("❌ You don't have permission to send codes.",
                              delete_after=5)

    tournament = get_tournament(ctx.guild.id)

    if not tournament.active:
        return await ctx.send("❌ No active tournament.", delete_after=5)

    # Get all match players (all players currently participating in the tournament)
    all_match_players = set()  # Use set to prevent duplicates

    # Get all players from current round matches
    current_round = tournament.rounds[-1]
    for match in current_round:
        a, b = match
        # Add both real players from this match
        for player in [a, b]:
            if hasattr(player, 'id') and not isinstance(player, FakePlayer):
                all_match_players.add(player)

    if not all_match_players:
        return await ctx.send("❌ No real players found in current matches.",
                              delete_after=5)

    # Send code to all match players
    host_name = ctx.author.nick if ctx.author.nick else ctx.author.display_name
    code_message = f"🔐 **The room code is:** ```{code}```\n**Hosted by:** {host_name}"

    sent_count = 0
    failed_players = []

    for player in all_match_players:
        try:
            await player.send(code_message)
            sent_count += 1
        except discord.Forbidden:
            player_name = player.nick if player.nick else player.display_name
            failed_players.append(player_name)
        except Exception:
            player_name = player.nick if player.nick else player.display_name
            failed_players.append(player_name)

    if failed_players:
        await ctx.send(
            f"✅ Code sent to {sent_count} players via DM!\n❌ Failed to send to: {', '.join(failed_players)}",
            delete_after=10)
    else:
        await ctx.send(
            f"✅ Code sent to all {sent_count} match players via DM!",
            delete_after=5)


@bot.command()
async def cancel(ctx):
    try:
        await ctx.message.delete()
    except:
        pass

    if not has_permission(
            ctx.author, ctx.guild.id,
            'tlr') and not ctx.author.guild_permissions.manage_channels:
        return await ctx.send(
            "❌ You don't have permission to cancel tournaments.",
            delete_after=5)

    tournament = get_tournament(ctx.guild.id)
    tournament.__init__()
    await ctx.send("❌ Tournament cancelled.", delete_after=5)


@bot.command()
async def hosterregist(ctx, max_hosters: int):
    try:
        await ctx.message.delete()
    except:
        pass

    if not has_permission(
            ctx.author, ctx.guild.id,
            'tlr') and not ctx.author.guild_permissions.manage_channels:
        return await ctx.send(
            "❌ You don't have permission to start hoster registration.",
            delete_after=5)

    if max_hosters < 1 or max_hosters > 20:
        return await ctx.send("❌ Maximum hosters must be between 1 and 20.",
                              delete_after=5)

    host_registrations['active'] = True
    host_registrations['max_hosters'] = max_hosters
    host_registrations['hosters'] = []
    host_registrations['channel'] = ctx.channel

    embed = discord.Embed(
        title="🎯 Hoster Registration",
        description="Here the hosters will register to host tournaments!",
        color=0x00ff00)

    embed.add_field(name="Hosters registered:", value="None yet", inline=False)
    embed.add_field(name="Slots:", value=f"0/{max_hosters}", inline=True)

    view = HosterRegistrationView()
    host_registrations['message'] = await ctx.send(embed=embed, view=view)


@bot.command()
@commands.has_permissions(manage_roles=True)
async def bracketrole(ctx,
                      member: discord.Member,
                      emoji1: str,
                      emoji2: str = "",
                      emoji3: str = ""):
    try:
        await ctx.message.delete()
    except:
        pass

    emojis = [emoji1, emoji2, emoji3]
    # Filter out empty emojis
    emojis = [e for e in emojis if e.strip()]

    if len(emojis) > 3:
        return await ctx.send("❌ You can only set up to 3 emojis!",
                              delete_after=5)

    if len(emojis) == 0:
        return await ctx.send("❌ You must provide at least one emoji!",
                              delete_after=5)

    guild_str = str(ctx.guild.id)
    if guild_str not in bracket_roles:
        bracket_roles[guild_str] = {}

    bracket_roles[guild_str][str(member.id)] = emojis
    save_data()

    emoji_display = ''.join(emojis)
    player_name = member.nick if member.nick else member.display_name

    await ctx.send(
        f"✅ Bracket role set for {member.mention}! Their bracket name: {player_name} {emoji_display}",
        delete_after=10)


@bot.command()
async def bracketname(ctx):
    try:
        await ctx.message.delete()
    except:
        pass

    guild_str = str(ctx.guild.id)
    if guild_str in bracket_roles and str(
            ctx.author.id) in bracket_roles[guild_str]:
        emojis = ''.join(bracket_roles[guild_str][str(ctx.author.id)])
        player_name = ctx.author.nick if ctx.author.nick else ctx.author.display_name
        bracket_name = f"{player_name} {emojis}"
    else:
        player_name = ctx.author.nick if ctx.author.nick else ctx.author.display_name
        bracket_name = player_name

    embed = discord.Embed(title="🏷️ Your Bracket Name",
                          description=f"**Bracket Name:** {bracket_name}",
                          color=0x3498db)

    try:
        await ctx.author.send(embed=embed)
        await ctx.send("📨 Bracket name sent via DM!", delete_after=3)
    except discord.Forbidden:
        await ctx.send(embed=embed, delete_after=10)


@bot.command()
@commands.has_permissions(manage_roles=True)
async def bracketrolereset(ctx, member: discord.Member = None):
    try:
        await ctx.message.delete()
    except:
        pass

    if member is None:
        member = ctx.author

    guild_str = str(ctx.guild.id)
    if guild_str in bracket_roles and str(
            member.id) in bracket_roles[guild_str]:
        del bracket_roles[guild_str][str(member.id)]
        # Clean up guild entry if it becomes empty
        if not bracket_roles[guild_str]:
            del bracket_roles[guild_str]
        save_data()

        if member == ctx.author:
            await ctx.send(
                "✅ Your bracket role reset! Your emojis have been removed.",
                delete_after=5)
        else:
            await ctx.send(
                f"✅ Bracket role reset for {member.mention}! Their emojis have been removed.",
                delete_after=5)
    else:
        if member == ctx.author:
            await ctx.send("❌ You don't have any bracket emojis set.",
                           delete_after=5)
        else:
            await ctx.send(
                f"❌ {member.mention} doesn't have any bracket emojis set.",
                delete_after=5)


# Ranked Points commands
@bot.command()
async def rp(ctx, member: discord.Member = None):
    try:
        await ctx.message.delete()
    except:
        pass

    if member is None:
        member = ctx.author

    guild_str = str(ctx.guild.id)
    rp = rp_data.get(guild_str, {}).get(str(member.id), 0)
    crowns = crown_data.get(guild_str, {}).get(str(member.id), 0)

    embed = discord.Embed(
        title="🏆 Ranked Points",
        description=f"**Player:** {member.display_name}\n**<:Ranked:1411317994847473695>RP:** {rp}\n**<:Crown:1394255336310968434>Crowns:** {crowns}",
        color=0xe74c3c)

    try:
        await ctx.author.send(embed=embed)
        await ctx.send("📨 RP information sent via DM!", delete_after=3)
    except discord.Forbidden:
        await ctx.send(embed=embed, delete_after=10)


@bot.command()
async def rp_lb(ctx):
    try:
        await ctx.message.delete()
    except:
        pass

    guild_str = str(ctx.guild.id)
    guild_rp_data = rp_data.get(guild_str, {})

    # Sort players by RP
    sorted_players = sorted(guild_rp_data.items(),
                            key=lambda x: x[1],
                            reverse=True)[:10]

    embed = discord.Embed(title="🏆 Ranked Points Leaderboard",
                          color=0xf1c40f)

    if not sorted_players:
        embed.description = "No players have RP yet!"
    else:
        leaderboard_text = ""
        for i, (user_id, rp) in enumerate(sorted_players, 1):
            user = ctx.guild.get_member(int(user_id))
            if user:
                crowns = crown_data.get(guild_str, {}).get(str(user_id), 0)
                # Add ranking emojis
                if i == 1:
                    emoji = "🥇"
                elif i == 2:
                    emoji = "🥈"
                elif i == 3:
                    emoji = "🥉"
                elif i == 4:
                    emoji = "4️⃣"
                else:
                    emoji = f"**{i}.**"
                leaderboard_text += f"{emoji} {user.display_name} - {rp}<:Ranked:1411317994847473695> {crowns}<:Crown:1394255336310968434>\n"

        embed.description = leaderboard_text

    await ctx.send(embed=embed, delete_after=30)


@bot.command()
@commands.has_permissions(administrator=True)
async def rp_rst(ctx):
    try:
        await ctx.message.delete()
    except:
        pass

    guild_str = str(ctx.guild.id)
    if guild_str in rp_data:
        rp_data[guild_str] = {}
        save_data()
        await ctx.send(
            "✅ All Ranked Points have been reset for this server!",
            delete_after=5)
    else:
        await ctx.send("✅ No Ranked Points to reset in this server!",
                       delete_after=5)

@bot.command()
async def crowns(ctx):
    try:
        await ctx.message.delete()
    except:
        pass

    guild_str = str(ctx.guild.id)
    guild_crown_data = crown_data.get(guild_str, {})

    # Sort players by crowns
    sorted_players = sorted(guild_crown_data.items(),
                            key=lambda x: x[1],
                            reverse=True)[:5]

    embed = discord.Embed(title="👑 Crown Leaderboard",
                          color=0xffd700)

    if not sorted_players:
        embed.description = "No players have crowns yet!"
    else:
        leaderboard_text = ""
        for i, (user_id, crowns) in enumerate(sorted_players, 1):
            user = ctx.guild.get_member(int(user_id))
            if user:
                rp = rp_data.get(guild_str, {}).get(str(user_id), 0)
                # Add ranking emojis
                if i == 1:
                    emoji = "🥇"
                elif i == 2:
                    emoji = "🥈"
                elif i == 3:
                    emoji = "🥉"
                else:
                    emoji = f"**{i}.**"
                leaderboard_text += f"{emoji} {user.display_name} - {crowns}<:Crown:1394255336310968434> {rp}<:Ranked:1411317994847473695>\n"

        embed.description = leaderboard_text

    await ctx.send(embed=embed, delete_after=30)

@bot.command()
@commands.has_permissions(administrator=True)
async def rb_log(ctx, channel: discord.TextChannel):
    try:
        await ctx.message.delete()
    except:
        pass

    guild_str = str(ctx.guild.id)
    log_channels[guild_str] = channel.id
    save_data()
    
    await ctx.send(f"✅ Bracket role, RP, and crown logs will be sent to {channel.mention}", delete_after=10)

@bot.command()
async def update(ctx):
    try:
        await ctx.message.delete()
    except:
        pass
    
    # This command will read the previous message and update with current information
    guild_str = str(ctx.guild.id)
    if guild_str in log_channels:
        channel_id = log_channels[guild_str]
        channel = bot.get_channel(channel_id)
        if channel:
            # Get the last message in the log channel
            async for message in channel.history(limit=1):
                if message.author == bot.user:
                    # Update the message with current leaderboard info
                    await update_log_message(ctx.guild.id, channel)
                    await ctx.send("✅ Log message updated!", delete_after=5)
                    return
    
    await ctx.send("❌ No log channel configured or no previous message found.", delete_after=5)


# Role permission commands
@bot.command()
@commands.has_permissions(administrator=True)
async def htr(ctx, *roles: discord.Role):
    try:
        await ctx.message.delete()
    except:
        pass

    if not roles:
        return await ctx.send("❌ Please mention at least one role.",
                              delete_after=5)

    guild_str = str(ctx.guild.id)
    if guild_str not in role_permissions:
        role_permissions[guild_str] = {}

    role_permissions[guild_str]['htr'] = [role.id for role in roles]
    save_data()

    role_mentions = [role.mention for role in roles]
    await ctx.send(f"✅ HTR permissions granted to: {', '.join(role_mentions)}",
                   delete_after=10)


@bot.command()
@commands.has_permissions(administrator=True)
async def adr(ctx, role: discord.Role):
    try:
        await ctx.message.delete()
    except:
        pass

    guild_str = str(ctx.guild.id)
    if guild_str not in role_permissions:
        role_permissions[guild_str] = {}

    role_permissions[guild_str]['adr'] = [role.id]
    save_data()

    await ctx.send(f"✅ ADR permissions granted to: {role.mention}",
                   delete_after=10)


@bot.command()
@commands.has_permissions(administrator=True)
async def tlr(ctx, *roles: discord.Role):
    try:
        await ctx.message.delete()
    except:
        pass

    if not roles:
        return await ctx.send("❌ Please mention at least one role.",
                              delete_after=5)

    guild_str = str(ctx.guild.id)
    if guild_str not in role_permissions:
        role_permissions[guild_str] = {}

    role_permissions[guild_str]['tlr'] = [role.id for role in roles]
    save_data()

    role_mentions = [role.mention for role in roles]
    await ctx.send(f"✅ TLR permissions granted to: {', '.join(role_mentions)}",
                   delete_after=10)


# Run the bot
if __name__ == "__main__":
    if not TOKEN:
        print(
            "❌ No Discord token found! Please add your bot token to the Secrets."
        )
        print("Go to the Secrets tool and add:")
        print("Key: TOKEN")
        print("Value: Your Discord bot token")
    else:
        try:
            keep_alive()
            bot.run(TOKEN)
        except Exception as e:
            print(f"❌ Error starting bot: {e}")
