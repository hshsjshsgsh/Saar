import discord
from discord.ext import commands
import json
import random
import asyncio
import os
from threading import Thread
from keep_alive import keep_alive
from datetime import datetime

# Configuration and bot setup
bot = commands.Bot(command_prefix="!", intents=discord.Intents.all())

# Global data structures
rp_data = {}
crown_data = {}
tournaments = {}
role_permissions = {}
bracket_roles = {}
log_channels = {}

class Tournament:

    def __init__(self):
        self.players = []
        self.max_players = 0
        self.active = False
        self.started = False
        self.current_round = 1
        self.rounds = []
        self.settings = {
            "map": "Default Map",
            "abilities": "Enabled",
            "title": "Stumble Guys Tournament",
            "prize": "Victory Crown 👑",
            "rp_1st": 100,
            "rp_2nd": 50,
            "rp_3rd": 30,
            "rp_4th": 30
        }


def get_tournament(guild_id):
    """Get tournament for specific guild"""
    if guild_id not in tournaments:
        tournaments[guild_id] = Tournament()
    return tournaments[guild_id]


def reset_tournament(guild_id):
    """Reset tournament for specific guild"""
    tournaments[guild_id] = Tournament()


def add_bracket_role(guild_id, user_id, emoji):
    """Add bracket role emoji to user"""
    guild_str = str(guild_id)
    user_str = str(user_id)
    
    if guild_str not in bracket_roles:
        bracket_roles[guild_str] = {}
    
    if user_str not in bracket_roles[guild_str]:
        bracket_roles[guild_str][user_str] = []
    
    if emoji not in bracket_roles[guild_str][user_str]:
        bracket_roles[guild_str][user_str].append(emoji)


def get_player_display_name(player, guild_id=None):
    """Get player display name with bracket emojis"""
    if isinstance(player, FakePlayer):
        return player.user.name

    # Get base name (Priority: nick > display_name > name > str(player))
    if hasattr(player, 'user.name') and player.user.name:
        base_name = player.user.name
    elif hasattr(player, 'user.name') and player.user.name:
        base_name = player.user.name
    elif hasattr(player, 'user.name') and player.user.name:
        base_name = player.user.name
    else:
        base_name = str(player)

    # Add bracket emojis if they exist
    if guild_id and str(guild_id) in bracket_roles:
        user_id = str(player.id) if hasattr(player, 'id') else str(player)
        if user_id in bracket_roles[str(guild_id)]:
            emojis = ''.join(bracket_roles[str(guild_id)][user_id])
            return f"{base_name} {emojis}"

    return base_name


def load_data():
    global rp_data, crown_data, role_permissions, bracket_roles, log_channels
    try:
        with open('user_data.json', 'r') as f:
            data = json.load(f)
            # Support both old TP data and new RP data for migration
            rp_data = data.get('rp_data', data.get('tp_data', {}))
            crown_data = data.get('crown_data', {})
            role_permissions = data.get('role_permissions', {})
            bracket_roles = data.get('bracket_roles', {})
            log_channels = data.get('log_channels', {})
            print("✅ Data loaded successfully")
    except FileNotFoundError:
        print("📂 No data file found, starting fresh")
        rp_data = {}
        crown_data = {}
        role_permissions = {}
        bracket_roles = {}
        log_channels = {}
    except Exception as e:
        print(f"⚠️ Error loading data: {e}")
        rp_data = {}
        crown_data = {}
        role_permissions = {}
        bracket_roles = {}
        log_channels = {}


def save_data():
    try:
        data = {
            'rp_data': rp_data,
            'crown_data': crown_data,
            'role_permissions': role_permissions,
            'bracket_roles': bracket_roles,
            'log_channels': log_channels
        }
        
        # Create backup
        try:
            with open('user_data_backup.json', 'w') as f:
                json.dump(data, f, indent=2)
        except:
            pass
        
        # Save main file
        with open('user_data.json', 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"⚠️ Error saving data: {e}")


def add_rp(guild_id, user_id, rp):
    guild_str = str(guild_id)
    user_str = str(user_id)

    if guild_str not in rp_data:
        rp_data[guild_str] = {}

    if user_str not in rp_data[guild_str]:
        rp_data[guild_str][user_str] = 0

    rp_data[guild_str][user_str] += rp
    save_data()
    
    # Auto-update leaderboard
    asyncio.create_task(log_reward_update(guild_id, user_id, rp, 0))

def add_crown(guild_id, user_id, crowns=1):
    guild_str = str(guild_id)
    user_str = str(user_id)

    if guild_str not in crown_data:
        crown_data[guild_str] = {}

    if user_str not in crown_data[guild_str]:
        crown_data[guild_str][user_str] = 0

    crown_data[guild_str][user_str] += crowns
    save_data()
    
    # Auto-update leaderboard
    asyncio.create_task(log_reward_update(guild_id, user_id, 0, crowns))

async def parse_leaderboard_data(channel, limit=50):
    """Parse previous leaderboard messages to restore RP/Crown/bracket data"""
    global rp_data, crown_data, bracket_roles
    
    if not isinstance(channel, discord.TextChannel):
        return False
    
    try:
        # Look for recent bot messages with leaderboard data
        async for message in channel.history(limit=limit):
            if message.author == bot.user and message.embeds:
                embed = message.embeds[0]
                if "Server Leaderboard" in embed.title and embed.description:
                    guild_str = str(channel.guild.id)
                    
                    # Initialize data structures if not exist
                    if guild_str not in rp_data:
                        rp_data[guild_str] = {}
                    if guild_str not in crown_data:
                        crown_data[guild_str] = {}
                    if guild_str not in bracket_roles:
                        bracket_roles[guild_str] = {}
                    
                    # Parse each line in the description
                    lines = embed.description.split('\n')
                    for line in lines:
                        if '<:Ranked:' in line:
                            # Extract user data from line format: "1. Username - 100<:Ranked:...> 5<:Crown:...> ⏱️ 🥇"
                            try:
                                # Remove ranking emoji and get the rest
                                if '.' in line:
                                    parts = line.split('.', 1)
                                    if len(parts) > 1:
                                        content = parts[1].strip()
                                    else:
                                        content = line
                                else:
                                    content = line
                                
                                # Extract username (before " - ")
                                if ' - ' in content:
                                    username_part = content.split(' - ')[0].strip()
                                    data_part = content.split(' - ')[1]
                                    
                                    # Find member by username
                                    member = None
                                    for m in channel.guild.members:
                                        if (m.name == username_part or 
                                            m.display_name == username_part or
                                            get_player_display_name(m, channel.guild.id) == username_part):
                                            member = m
                                            break
                                    
                                    if member:
                                        user_str = str(member.id)
                                        
                                        # Extract RP
                                        if '<:Ranked:' in data_part:
                                            rp_match = data_part.split('<:Ranked:')[0].strip()
                                            try:
                                                rp_value = int(rp_match.split()[-1])
                                                rp_data[guild_str][user_str] = max(rp_value, rp_data[guild_str].get(user_str, 0))
                                            except:
                                                pass
                                        
                                        # Extract crowns
                                        if '<:Crown:' in data_part:
                                            crown_parts = data_part.split('<:Crown:')
                                            if len(crown_parts) > 1:
                                                crown_match = crown_parts[0].split()[-1]
                                                try:
                                                    crown_value = int(crown_match)
                                                    crown_data[guild_str][user_str] = max(crown_value, crown_data[guild_str].get(user_str, 0))
                                                except:
                                                    pass
                                        
                                        # Extract bracket emojis
                                        if '⏱️' in data_part:
                                            emoji_part = data_part.split('⏱️')[1].strip()
                                            if emoji_part and user_str not in bracket_roles[guild_str]:
                                                bracket_roles[guild_str][user_str] = list(emoji_part.split())
                                        
                                        # Check for medal emojis in username
                                        for emoji in ['🥇', '🥈', '🥉']:
                                            if emoji in username_part:
                                                if user_str not in bracket_roles[guild_str]:
                                                    bracket_roles[guild_str][user_str] = []
                                                if emoji not in bracket_roles[guild_str][user_str]:
                                                    bracket_roles[guild_str][user_str].append(emoji)
                                        
                            except Exception as e:
                                print(f"Error parsing line: {line}, Error: {e}")
                                continue
                    
                    # Save the restored data
                    save_data()
                    print(f"✅ Restored data from previous leaderboard message")
                    return True
                    
    except Exception as e:
        print(f"Error parsing leaderboard data: {e}")
    
    return False


async def update_log_embed(guild_id, channel):
    """Update or create log embed with current RP and crown leaderboard for ALL server members"""
    guild_str = str(guild_id)
    guild_rp_data = rp_data.get(guild_str, {})
    guild_crown_data = crown_data.get(guild_str, {})
    
    # Initialize leaderboard_text early to avoid UnboundLocalError
    leaderboard_text = ""
    
    # Get ALL server members, not just those with RP/crowns
    guild = bot.get_guild(guild_id)
    if not guild:
        return
    
    # Ensure member cache is populated
    try:
        await guild.chunk(cache=True)
    except Exception:
        pass  # Fallback if chunk fails
        
    combined_data = []
    for member in guild.members:
        # Skip bots
        if member.bot:
            continue
            
        user_id = str(member.id)
        rp = guild_rp_data.get(user_id, 0)
        crowns = guild_crown_data.get(user_id, 0)
        
        # Get bracket roles for this member
        user_brackets = []
        if guild_str in bracket_roles and user_id in bracket_roles[guild_str]:
            user_brackets = bracket_roles[guild_str][user_id]
        
        # Only include members who have RP, crowns, or bracket roles
        if rp > 0 or crowns > 0 or user_brackets:
            combined_data.append((user_id, rp, crowns, member))
    
    # Sort by RP (highest first), then by crowns, then by display name
    combined_data.sort(key=lambda x: (x[1], x[2], x[3].display_name.lower()), reverse=True)
    
    # Create embed
    embed = discord.Embed(
        title="🏆 Server Leaderboard", 
        color=0xffd700,
        timestamp=datetime.now()
    )
    
    if not combined_data:
        embed.description = "No members with RP, Crowns, or Bracket roles found."
    else:
        for i, (user_id, rp, crowns, member) in enumerate(combined_data, 1):  # Show ALL members
            # Add ranking emojis (only gold/silver/bronze for those with RP > 0)
            if i == 1 and rp > 0:
                emoji = "🥇"
            elif i == 2 and rp > 0:
                emoji = "🥈"
            elif i == 3 and rp > 0:
                emoji = "🥉"
            else:
                emoji = f"**{i}.**"
            
            # Use get_player_display_name for consistent naming
            display_name = get_player_display_name(member, guild_id)
            line = f"{emoji} {display_name} - {rp}<:Ranked:1411317994847473695>"
            if crowns > 0:
                line += f" {crowns}<:Crown:1394255336310968434>"
            
            # Add bracket role if exists (already included in get_player_display_name but kept for clarity)
            if guild_str in bracket_roles and user_id in bracket_roles[guild_str]:
                emojis = ''.join(bracket_roles[guild_str][user_id])
                if emojis not in line:  # Avoid duplication
                    line += f" ⏱️ {emojis}"
            
            leaderboard_text += line + "\n"
        
        # Handle Discord's embed character limit (4096 characters)
        if len(leaderboard_text) > 4000:
            # Split into multiple embeds if too long
            lines = leaderboard_text.strip().split("\n")
            chunks = []
            current_chunk = ""
            
            for line in lines:
                if len(current_chunk + line + "\n") > 4000:
                    chunks.append(current_chunk.strip())
                    current_chunk = line + "\n"
                else:
                    current_chunk += line + "\n"
            
            if current_chunk.strip():
                chunks.append(current_chunk.strip())
            
            # Set first chunk as main embed
            embed.description = chunks[0]
        else:
            embed.description = leaderboard_text
    
    embed.set_footer(text="Last updated")
    
    # Try to edit the last embed, or send a new one
    try:
        async for message in channel.history(limit=1):
            if message.author == bot.user and message.embeds:
                await message.edit(embed=embed)
                
                # Send additional embeds if needed for long leaderboards
                if len(leaderboard_text) > 4000:
                    lines = leaderboard_text.strip().split("\n")
                    chunks = []
                    current_chunk = ""
                    
                    for line in lines:
                        if len(current_chunk + line + "\n") > 4000:
                            chunks.append(current_chunk.strip())
                            current_chunk = line + "\n"
                        else:
                            current_chunk += line + "\n"
                    
                    if current_chunk.strip():
                        chunks.append(current_chunk.strip())
                    
                    # Send additional pages if needed
                    for i, chunk in enumerate(chunks[1:], 2):
                        additional_embed = discord.Embed(
                            title=f"🏆 Server Leaderboard (Page {i})",
                            description=chunk,
                            color=0xffd700,
                            timestamp=datetime.now()
                        )
                        additional_embed.set_footer(text="Last updated")
                        await channel.send(embed=additional_embed)
                return
    except:
        pass
    
    # Send new embed if editing failed
    new_message = await channel.send(embed=embed)
    
    # Send additional embeds if needed for long leaderboards
    if len(leaderboard_text) > 4000:
        lines = leaderboard_text.strip().split("\n")
        chunks = []
        current_chunk = ""
        
        for line in lines:
            if len(current_chunk + line + "\n") > 4000:
                chunks.append(current_chunk.strip())
                current_chunk = line + "\n"
            else:
                current_chunk += line + "\n"
        
        if current_chunk.strip():
            chunks.append(current_chunk.strip())
        
        # Send additional pages
        for i, chunk in enumerate(chunks[1:], 2):
            additional_embed = discord.Embed(
                title=f"🏆 Server Leaderboard (Page {i})",
                description=chunk,
                color=0xffd700,
                timestamp=datetime.now()
            )
            additional_embed.set_footer(text="Last updated")
            await channel.send(embed=additional_embed)

async def log_reward_update(guild_id, user_id, rp_gained=0, crowns_gained=0):
    """Log when a player gains RP or crowns"""
    guild_str = str(guild_id)
    if guild_str in log_channels:
        channel_id = log_channels[guild_str]
        channel = bot.get_channel(channel_id)
        if channel:
            await update_log_embed(guild_id, channel)


def has_permission(user, guild_id, permission_type):
    """Check if user has specific permission type"""
    guild_str = str(guild_id)
    if guild_str not in role_permissions:
        return False

    if permission_type not in role_permissions[guild_str]:
        return False

    user_role_ids = [role.id for role in getattr(user, 'roles', [])]
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
    
    # Auto-restore data from existing log channels
    for guild_str, channel_id in log_channels.items():
        try:
            channel = bot.get_channel(channel_id)
            if isinstance(channel, discord.TextChannel):
                restored = await parse_leaderboard_data(channel)
                if restored:
                    print(f"✅ Auto-restored data for guild {guild_str} from {channel.name}")
        except Exception as e:
            print(f"⚠️ Could not restore data for guild {guild_str}: {e}")


class TournamentConfigModal(discord.ui.Modal,
                            title="Tournament Configuration"):

    def __init__(self, target_channel):
        super().__init__()
        self.target_channel = target_channel

    title_field = discord.ui.TextInput(label="🏆 Tournament Title",
                                       placeholder="Enter tournament title...",
                                       default="",
                                       max_length=100)

    max_players_field = discord.ui.TextInput(
        label="👥 Max Players",
        placeholder="Enter max players (e.g., 16)...",
        default="",
        max_length=3)

    map_field = discord.ui.TextInput(label="🗺️ Tournament Map",
                                     placeholder="Enter map name...",
                                     default="",
                                     max_length=50)

    abilities_field = discord.ui.TextInput(
        label="⚡ Abilities",
        placeholder="Enter abilities setting...",
        default="",
        max_length=20)

    prize_field = discord.ui.TextInput(label="🎁 Prize",
                                       placeholder="Enter prize description...",
                                       default="",
                                       max_length=100)

    async def on_submit(self, interaction: discord.Interaction):
        try:
            max_players = int(self.max_players_field.value)
            if max_players < 2 or max_players > 64:
                await interaction.response.send_message(
                    "❌ Max players must be between 2 and 64!", ephemeral=True)
                return

            tournament = get_tournament(interaction.guild.id)
            tournament.max_players = max_players
            tournament.settings.update({
                "title": self.title_field.value,
                "map": self.map_field.value,
                "abilities": self.abilities_field.value,
                "prize": self.prize_field.value
            })

            embed = discord.Embed(
                title="<:info:1407789948219691122> Tournament Created",
                description=
                f"**🏆 {tournament.settings['title']}**\n\n"
                f"**<:sgmap:1394258088575635601> Map:** {tournament.settings['map']}\n"
                f"**⚡ Abilities:** {tournament.settings['abilities']}\n"
                f"**👥 Max Players:** {tournament.max_players}\n"
                f"**🎁 Prize:** {tournament.settings['prize']}\n\n"
                f"**💰 RP Rewards:**\n"
                f"🥇 1st Place: {tournament.settings['rp_1st']} RP + 1 Crown\n"
                f"🥈 2nd Place: {tournament.settings['rp_2nd']} RP\n"
                f"🥉 3rd Place: {tournament.settings['rp_3rd']} RP\n"
                f"🏅 4th Place: {tournament.settings['rp_4th']} RP\n\n"
                f"**Players:** 0/{tournament.max_players}",
                color=0x00ff00)

            # Add tournament management view
            view = TournamentView()
            await interaction.response.edit_message(embed=embed, view=view)

        except ValueError:
            await interaction.response.send_message(
                "❌ Max players must be a valid number!", ephemeral=True)
        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error creating tournament: {str(e)}", ephemeral=True)


class TournamentConfigView(discord.ui.View):

    def __init__(self, target_channel=None):
        super().__init__(timeout=None)
        self.target_channel = target_channel

    @discord.ui.button(label="⚙️ Configure Tournament",
                       style=discord.ButtonStyle.primary,
                       custom_id="configure_tournament")
    async def configure_tournament(self, interaction: discord.Interaction,
                                   button: discord.ui.Button):
        if not has_permission(interaction.user, interaction.guild.id,
                              'tournament_host'):
            await interaction.response.send_message(
                "❌ You don't have permission to configure tournaments!",
                ephemeral=True)
            return

        modal = TournamentConfigModal(self.target_channel)
        await interaction.response.send_modal(modal)

    @discord.ui.button(label="❌ Cancel",
                       style=discord.ButtonStyle.secondary,
                       custom_id="cancel_config")
    async def cancel_config(self, interaction: discord.Interaction,
                            button: discord.ui.Button):
        await interaction.response.edit_message(
            content="Tournament configuration cancelled.", embed=None, view=None)


class TournamentView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)  # Prevent auto-canceling

    async def interaction_check(self,
                                interaction: discord.Interaction) -> bool:
        return True  # Allow all users to interact

    @discord.ui.button(label="✅ Register",
                       style=discord.ButtonStyle.success,
                       custom_id="register_tournament")
    async def register(self, interaction: discord.Interaction,
                       button: discord.ui.Button):
        try:
            tournament = get_tournament(interaction.guild.id)

            if tournament.started:
                await interaction.response.send_message(
                    "❌ Tournament has already started!", ephemeral=True)
                return

            if len(tournament.players) >= tournament.max_players:
                await interaction.response.send_message(
                    "❌ Tournament is full!", ephemeral=True)
                return

            user_already_registered = any(
                player and hasattr(player, 'id') and player.id == interaction.user.id 
                for player in tournament.players)

            if user_already_registered:
                await interaction.response.send_message(
                    "❌ You are already registered!", ephemeral=True)
                return

            tournament.players.append(interaction.user)

            # Updated registration confirmation with simple format
            await interaction.response.send_message(
                "Successfully registered! ✅", ephemeral=True)

            # Update main embed with new player count
            embed = discord.Embed(
                title="<:info:1407789948219691122> Tournament Created",
                description=
                f"**🏆 {tournament.settings['title']}**\n\n"
                f"**<:sgmap:1394258088575635601> Map:** {tournament.settings['map']}\n"
                f"**⚡ Abilities:** {tournament.settings['abilities']}\n"
                f"**👥 Max Players:** {tournament.max_players}\n"
                f"**🎁 Prize:** {tournament.settings['prize']}\n\n"
                f"**💰 RP Rewards:**\n"
                f"🥇 1st Place: {tournament.settings['rp_1st']} RP + 1 Crown\n"
                f"🥈 2nd Place: {tournament.settings['rp_2nd']} RP\n"
                f"🥉 3rd Place: {tournament.settings['rp_3rd']} RP\n"
                f"🏅 4th Place: {tournament.settings['rp_4th']} RP\n\n"
                f"**Players:** {len(tournament.players)}/{tournament.max_players}",
                color=0x00ff00)

            # Add list of registered players if any
            if tournament.players:
                player_list = "\n".join([
                    f"{i+1}. {get_player_display_name(player, interaction.guild.id)}"
                    for i, player in enumerate(tournament.players)
                ])
                embed.add_field(name="📋 Registered Players",
                                value=player_list,
                                inline=False)

            await interaction.edit_original_response(embed=embed, view=self)

        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error during registration: {str(e)}", ephemeral=True)

    @discord.ui.button(label="❌ Unregister",
                       style=discord.ButtonStyle.danger,
                       custom_id="unregister_tournament")
    async def unregister(self, interaction: discord.Interaction,
                         button: discord.ui.Button):
        try:
            tournament = get_tournament(interaction.guild.id)

            if tournament.started:
                await interaction.response.send_message(
                    "❌ Cannot unregister after tournament has started!",
                    ephemeral=True)
                return

            user_registered = False
            for i, player in enumerate(tournament.players):
                if player and hasattr(player, 'id') and player.id == interaction.user.id:
                    tournament.players.pop(i)
                    user_registered = True
                    break

            if not user_registered:
                await interaction.response.send_message(
                    "❌ You are not registered!", ephemeral=True)
                return

            await interaction.response.send_message(
                "Successfully unregistered! ❌", ephemeral=True)

            # Update main embed
            embed = discord.Embed(
                title="<:info:1407789948219691122> Tournament Created",
                description=
                f"**🏆 {tournament.settings['title']}**\n\n"
                f"**<:sgmap:1394258088575635601> Map:** {tournament.settings['map']}\n"
                f"**⚡ Abilities:** {tournament.settings['abilities']}\n"
                f"**👥 Max Players:** {tournament.max_players}\n"
                f"**🎁 Prize:** {tournament.settings['prize']}\n\n"
                f"**💰 RP Rewards:**\n"
                f"🥇 1st Place: {tournament.settings['rp_1st']} RP + 1 Crown\n"
                f"🥈 2nd Place: {tournament.settings['rp_2nd']} RP\n"
                f"🥉 3rd Place: {tournament.settings['rp_3rd']} RP\n"
                f"🏅 4th Place: {tournament.settings['rp_4th']} RP\n\n"
                f"**Players:** {len(tournament.players)}/{tournament.max_players}",
                color=0x00ff00)

            # Add list of registered players if any
            if tournament.players:
                player_list = "\n".join([
                    f"{i+1}. {get_player_display_name(player, interaction.guild.id)}"
                    for i, player in enumerate(tournament.players)
                ])
                embed.add_field(name="📋 Registered Players",
                                value=player_list,
                                inline=False)

            await interaction.edit_original_response(embed=embed, view=self)

        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error during unregistration: {str(e)}", ephemeral=True)

    @discord.ui.button(label="🚀 Start Tournament",
                       style=discord.ButtonStyle.primary,
                       custom_id="start_tournament")
    async def start_tournament(self, interaction: discord.Interaction,
                               button: discord.ui.Button):
        if not has_permission(interaction.user, interaction.guild.id,
                              'tournament_host'):
            await interaction.response.send_message(
                "❌ You don't have permission to start tournaments!",
                ephemeral=True)
            return

        tournament = get_tournament(interaction.guild.id)

        if tournament.started:
            await interaction.response.send_message(
                "❌ Tournament has already started!", ephemeral=True)
            return

        if len(tournament.players) < 2:
            await interaction.response.send_message(
                "❌ Need at least 2 players to start!", ephemeral=True)
            return

        tournament.started = True
        tournament.active = True

        # Create bracket pairs for Round 1
        players = tournament.players.copy()
        random.shuffle(players)

        round_1_matches = []
        while len(players) >= 2:
            player1 = players.pop(0)
            player2 = players.pop(0)
            round_1_matches.append([player1, player2])

        # Handle odd player (bye)
        if players:
            bye_player = players[0]
            round_1_matches.append([bye_player, "BYE"])

        tournament.rounds = [round_1_matches]

        # Create bracket display
        bracket_text = "**🏆 TOURNAMENT BRACKET - Round 1**\n\n"
        for i, match in enumerate(round_1_matches, 1):
            player1_name = get_player_display_name(match[0],
                                                   interaction.guild.id)
            if match[1] == "BYE":
                bracket_text += f"**Match {i}:** {player1_name} vs BYE (Auto-advance) ✅\n"
            else:
                player2_name = get_player_display_name(match[1],
                                                       interaction.guild.id)
                bracket_text += f"**Match {i}:** {player1_name} vs {player2_name}\n"

        embed = discord.Embed(title="🚀 Tournament Started!",
                              description=bracket_text,
                              color=0xff6b35)
        embed.add_field(
            name="ℹ️ Instructions",
            value=
            "Moderators can use `!winner @player` to advance players to the next round.",
            inline=False)

        await interaction.response.edit_message(embed=embed, view=None)

    @discord.ui.button(label="🗑️ Delete Tournament",
                       style=discord.ButtonStyle.danger,
                       custom_id="delete_tournament")
    async def delete_tournament(self, interaction: discord.Interaction,
                                button: discord.ui.Button):
        if not has_permission(interaction.user, interaction.guild.id,
                              'tournament_host'):
            await interaction.response.send_message(
                "❌ You don't have permission to delete tournaments!",
                ephemeral=True)
            return

        reset_tournament(interaction.guild.id)
        await interaction.response.edit_message(
            content="🗑️ Tournament deleted successfully!",
            embed=None,
            view=None)


class HosterRegistrationView(discord.ui.View):

    def __init__(self):
        super().__init__(timeout=None)  # Prevent auto-canceling

    async def interaction_check(self,
                                interaction: discord.Interaction) -> bool:
        return True  # Allow all users to interact

    @discord.ui.button(label="✅ Register as Hoster",
                       style=discord.ButtonStyle.success,
                       custom_id="register_hoster")
    async def register_hoster(self, interaction: discord.Interaction,
                              button: discord.ui.Button):
        try:
            # Check if user already has tournament_host permission
            if has_permission(interaction.user, interaction.guild.id,
                              'tournament_host'):
                await interaction.response.send_message(
                    "✅ You are already registered as a tournament hoster!",
                    ephemeral=True)
                return

            # Check if user has any of the allowed roles for tournament hosting
            guild_str = str(interaction.guild.id)
            if (guild_str not in role_permissions
                    or 'tournament_host' not in role_permissions[guild_str]):
                await interaction.response.send_message(
                    "❌ No hoster roles have been configured for this server! Ask an admin to set them up with `!htr @role`.",
                    ephemeral=True)
                return

            user_role_ids = [role.id for role in getattr(interaction.user, 'roles', [])]
            allowed_role_ids = role_permissions[guild_str]['tournament_host']

            if not any(role_id in allowed_role_ids
                       for role_id in user_role_ids):
                await interaction.response.send_message(
                    "❌ You don't have the required roles to become a tournament hoster!",
                    ephemeral=True)
                return

            await interaction.response.send_message(
                "✅ You are now registered as a tournament hoster! You can create and manage tournaments.",
                ephemeral=True)

        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error during hoster registration: {str(e)}",
                ephemeral=True)

    @discord.ui.button(label="❌ Unregister",
                       style=discord.ButtonStyle.danger,
                       custom_id="unregister_hoster")
    async def unregister_hoster(self, interaction: discord.Interaction,
                                button: discord.ui.Button):
        try:
            if not has_permission(interaction.user, interaction.guild.id,
                                  'tournament_host'):
                await interaction.response.send_message(
                    "❌ You are not registered as a tournament hoster!",
                    ephemeral=True)
                return

            await interaction.response.send_message(
                "❌ You can't unregister from being a hoster - this is based on your server roles. Contact an admin if you need role changes.",
                ephemeral=True)

        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error during hoster unregistration: {str(e)}",
                ephemeral=True)

    @discord.ui.button(label="ℹ️ View Requirements",
                       style=discord.ButtonStyle.secondary,
                       custom_id="view_requirements")
    async def view_requirements(self, interaction: discord.Interaction,
                                button: discord.ui.Button):
        try:
            guild_str = str(interaction.guild.id)
            if (guild_str not in role_permissions
                    or 'tournament_host' not in role_permissions[guild_str]):
                await interaction.response.send_message(
                    "❌ No hoster requirements have been configured for this server!",
                    ephemeral=True)
                return

            allowed_role_ids = role_permissions[guild_str]['tournament_host']
            role_names = []

            for role_id in allowed_role_ids:
                if interaction.guild:
                    role = interaction.guild.get_role(role_id)
                    if role:
                        role_names.append(role.name)

            if not role_names:
                await interaction.response.send_message(
                    "❌ No valid hoster roles found!", ephemeral=True)
                return

            embed = discord.Embed(
                title="🏆 Tournament Hoster Requirements",
                description=
                f"To become a tournament hoster, you need one of these roles:\n\n"
                + "\n".join([f"• **{role}**" for role in role_names]),
                color=0x3498db)

            await interaction.response.send_message(embed=embed,
                                                    ephemeral=True)

        except Exception as e:
            await interaction.response.send_message(
                f"❌ Error viewing requirements: {str(e)}", ephemeral=True)


# Tournament Commands

@bot.command(name="create")
@commands.guild_only()
async def create(ctx, channel: discord.TextChannel):
    try:
        await ctx.message.delete()
    except:
        pass

    if not has_permission(ctx.author, ctx.guild.id, 'tournament_host'):
        await ctx.send(
            "❌ You don't have permission to create tournaments! Use `!hoster` to check your status.",
            delete_after=5)
        return

    embed = discord.Embed(title="⚙️ Tournament Setup",
                          description="Click the button below to configure your tournament.",
                          color=0x3498db)

    view = TournamentConfigView(channel)
    await channel.send(embed=embed, view=view)


@bot.command(name="start")
@commands.guild_only()
async def start(ctx):
    try:
        await ctx.message.delete()
    except:
        pass

    if not has_permission(ctx.author, ctx.guild.id, 'tournament_host'):
        await ctx.send(
            "❌ You don't have permission to start tournaments!",
            delete_after=5)
        return

    tournament = get_tournament(ctx.guild.id)

    if not tournament.players:
        await ctx.send("❌ No tournament found or no players registered!",
                       delete_after=5)
        return

    if tournament.started:
        await ctx.send("❌ Tournament has already started!", delete_after=5)
        return

    if len(tournament.players) < 2:
        await ctx.send("❌ Need at least 2 players to start!", delete_after=5)
        return

    tournament.started = True
    tournament.active = True

    # Create bracket pairs for Round 1
    players = tournament.players.copy()
    random.shuffle(players)

    round_1_matches = []
    while len(players) >= 2:
        player1 = players.pop(0)
        player2 = players.pop(0)
        round_1_matches.append([player1, player2])

    # Handle odd player (bye)
    if players:
        bye_player = players[0]
        round_1_matches.append([bye_player, "BYE"])

    tournament.rounds = [round_1_matches]

    # Create bracket display
    bracket_text = "**🏆 TOURNAMENT BRACKET - Round 1**\n\n"
    for i, match in enumerate(round_1_matches, 1):
        player1_name = get_player_display_name(match[0], ctx.guild.id)
        if match[1] == "BYE":
            bracket_text += f"**Match {i}:** {player1_name} vs BYE (Auto-advance) ✅\n"
        else:
            player2_name = get_player_display_name(match[1], ctx.guild.id)
            bracket_text += f"**Match {i}:** {player1_name} vs {player2_name}\n"

    embed = discord.Embed(title="🚀 Tournament Started!",
                          description=bracket_text,
                          color=0xff6b35)
    embed.add_field(
        name="ℹ️ Instructions",
        value=
        "Moderators can use `!winner @player` to advance players to the next round.",
        inline=False)

    await ctx.send(embed=embed)


@bot.command(name="winner")
@commands.guild_only()
async def winner(ctx, member: discord.Member):
    try:
        await ctx.message.delete()
    except:
        pass

    if not has_permission(ctx.author, ctx.guild.id, 'tournament_host'):
        await ctx.send("❌ You don't have permission to manage tournaments!",
                       delete_after=5)
        return

    tournament = get_tournament(ctx.guild.id)

    if not tournament.started:
        await ctx.send("❌ No active tournament!", delete_after=5)
        return

    if not tournament.rounds:
        await ctx.send("❌ No tournament rounds found!", delete_after=5)
        return

    current_round = tournament.rounds[-1]
    winner_found = False

    # Find the match with this player and mark them as winner
    for match in current_round:
        if match[1] == "BYE":
            continue

        if ((hasattr(match[0], 'id') and match[0] and match[0].id == member.id) or 
            (hasattr(match[1], 'id') and match[1] and match[1].id == member.id)):
            # Mark the winner
            if hasattr(match[0], 'id') and match[0] and match[0].id == member.id:
                match.append(match[0])  # Winner is player 1
                winner_found = True
            elif hasattr(match[1], 'id') and match[1] and match[1].id == member.id:
                match.append(match[1])  # Winner is player 2
                winner_found = True
            break

    if not winner_found:
        await ctx.send("❌ Player not found in current round!", delete_after=5)
        return

    # Check if all matches in current round are complete
    all_matches_complete = True
    winners = []

    for match in current_round:
        if match[1] == "BYE":
            winners.append(match[0])  # Bye player auto-advances
        elif len(match) >= 3:  # Match has a winner
            winners.append(match[2])
        else:
            all_matches_complete = False

    if all_matches_complete:
        # Create bracket display with winners marked
        round_num = len(tournament.rounds)
        bracket_text = f"**🏆 TOURNAMENT BRACKET - Round {round_num} COMPLETE!**\n\n"

        for i, match in enumerate(current_round, 1):
            player1_name = get_player_display_name(match[0], ctx.guild.id)
            if match[1] == "BYE":
                bracket_text += f"**Match {i}:** {player1_name} vs BYE ✅ **Winner: {player1_name}**\n"
            else:
                player2_name = get_player_display_name(match[1], ctx.guild.id)
                if len(match) >= 3:
                    winner_name = get_player_display_name(match[2], ctx.guild.id)
                    bracket_text += f"**Match {i}:** {player1_name} vs {player2_name} ✅ **Winner: {winner_name}**\n"

        if len(winners) == 1:
            # Tournament is complete!
            final_winner = winners[0]
            winner_name = get_player_display_name(final_winner, ctx.guild.id)

            # Award RP and crowns
            add_rp(ctx.guild.id, final_winner.id, tournament.settings['rp_1st'])
            add_crown(ctx.guild.id, final_winner.id, 1)
            add_bracket_role(ctx.guild.id, final_winner.id, "🥇")

            # Award other places if we can determine them
            if len(tournament.rounds) >= 2:
                # Find runner-up (loser of final)
                final_match = current_round[0]
                if len(final_match) >= 3 and final_match[2] and final_match[1]:
                    runner_up = final_match[0] if (final_match[2] and final_match[1] and final_match[2].id == final_match[1].id) else final_match[1]
                    add_rp(ctx.guild.id, runner_up.id,
                           tournament.settings['rp_2nd'])
                    add_bracket_role(ctx.guild.id, runner_up.id, "🥈")

            bracket_text += f"\n🎉 **TOURNAMENT COMPLETE!**\n🏆 **CHAMPION: {winner_name}**"

            embed = discord.Embed(title="🏆 Tournament Complete!",
                                  description=bracket_text,
                                  color=0xffd700)

            # Reset tournament
            reset_tournament(ctx.guild.id)

            # Log the reward update
            await log_reward_update(ctx.guild.id, final_winner.id,
                                    tournament.settings['rp_1st'], 1)

        elif len(winners) >= 2:
            # Create next round
            next_round_matches = []
            round_winners = winners.copy()
            random.shuffle(round_winners)

            while len(round_winners) >= 2:
                player1 = round_winners.pop(0)
                player2 = round_winners.pop(0)
                next_round_matches.append([player1, player2])

            # Handle odd player (bye to next round)
            if round_winners:
                bye_player = round_winners[0]
                next_round_matches.append([bye_player, "BYE"])

            tournament.rounds.append(next_round_matches)

            # Display current round complete + next round
            next_round_num = len(tournament.rounds)
            bracket_text += f"\n\n**🔄 NEXT ROUND - Round {next_round_num}**\n\n"

            for i, match in enumerate(next_round_matches, 1):
                player1_name = get_player_display_name(match[0], ctx.guild.id)
                if match[1] == "BYE":
                    bracket_text += f"**Match {i}:** {player1_name} vs BYE (Auto-advance) ✅\n"
                else:
                    player2_name = get_player_display_name(match[1],
                                                           ctx.guild.id)
                    bracket_text += f"**Match {i}:** {player1_name} vs {player2_name}\n"

            embed = discord.Embed(title="🚀 Round Complete - Next Round!",
                                  description=bracket_text,
                                  color=0xff6b35)

        await ctx.send(embed=embed)
    else:
        # Just announce this match winner
        winner_name = get_player_display_name(member, ctx.guild.id)
        await ctx.send(f"✅ **{winner_name}** wins their match! 🎉")


# Fake Player class for testing
class FakePlayer:

    def __init__(self, name, user_id):
        self.display_name = name
        self.name = name
        self.nick = name
        self.id = user_id


@bot.command(name="add_fake_player")
async def add_fake_player(ctx, name: str):
    try:
        await ctx.message.delete()
    except:
        pass

    if not has_permission(ctx.author, ctx.guild.id, 'tournament_host'):
        await ctx.send(
            "❌ You don't have permission to manage tournaments!",
            delete_after=5)
        return

    tournament = get_tournament(ctx.guild.id)

    if tournament.started:
        await ctx.send("❌ Cannot add players after tournament started!",
                       delete_after=5)
        return

    if len(tournament.players) >= tournament.max_players:
        await ctx.send("❌ Tournament is full!", delete_after=5)
        return

    # Create fake player with unique ID
    fake_id = hash(name) % 1000000  # Simple hash for unique ID
    fake_player = FakePlayer(name, fake_id)
    tournament.players.append(fake_player)

    await ctx.send(f"✅ Added fake player: **{name}**", delete_after=3)


# RP and Crown Commands

@bot.command(name="rp_lb")
async def rp_lb(ctx):
    try:
        await ctx.message.delete()
    except:
        pass

    guild_str = str(ctx.guild.id)
    guild_rp_data = rp_data.get(guild_str, {})
    guild_crown_data = crown_data.get(guild_str, {})

    if not guild_rp_data and not guild_crown_data:
        await ctx.send("No RP or crown data found for this server!",
                       delete_after=5)
        return

    # Combine and sort players by RP
    combined_data = []
    for user_id in set(list(guild_rp_data.keys()) +
                       list(guild_crown_data.keys())):
        rp = guild_rp_data.get(user_id, 0)
        crowns = guild_crown_data.get(user_id, 0)
        if rp > 0 or crowns > 0:
            combined_data.append((user_id, rp, crowns))

    combined_data.sort(key=lambda x: x[1], reverse=True)  # Sort by RP

    if not combined_data:
        await ctx.send("No players with RP or crowns found!", delete_after=5)
        return

    # Create leaderboard
    leaderboard_text = ""
    for i, (user_id, rp, crowns) in enumerate(combined_data[:10], 1):
        user = ctx.guild.get_member(int(user_id))
        if user:
            # Add ranking emojis
            if i == 1:
                emoji = "🥇"
            elif i == 2:
                emoji = "🥈"
            elif i == 3:
                emoji = "🥉"
            else:
                emoji = f"**{i}.**"

            line = f"{emoji} {get_player_display_name(user, ctx.guild.id)} - {rp}<:Ranked:1411317994847473695>"
            if crowns > 0:
                line += f" {crowns}<:Crown:1394255336310968434>"
            leaderboard_text += line + "\n"

    embed = discord.Embed(title="🏆 RP Leaderboard",
                          description=leaderboard_text,
                          color=0xffd700)
    await ctx.send(embed=embed)


@bot.command(name="rp_rst")
async def rp_rst(ctx):
    try:
        await ctx.message.delete()
    except:
        pass

    if not has_permission(ctx.author, ctx.guild.id, 'admin'):
        await ctx.send("❌ You don't have admin permissions!", delete_after=5)
        return

    guild_str = str(ctx.guild.id)
    if guild_str in rp_data:
        rp_data[guild_str] = {}
    if guild_str in crown_data:
        crown_data[guild_str] = {}
    if guild_str in bracket_roles:
        bracket_roles[guild_str] = {}

    save_data()
    await ctx.send("✅ All RP, crowns, and bracket roles have been reset!",
                   delete_after=5)


@bot.command(name="rp_add")
async def rp_add(ctx, member: discord.Member, amount: int = 1):
    try:
        await ctx.message.delete()
    except:
        pass

    if not has_permission(ctx.author, ctx.guild.id, 'admin'):
        await ctx.send("❌ You don't have admin permissions!", delete_after=5)
        return

    add_rp(ctx.guild.id, member.id, amount)
    await ctx.send(
        f"✅ Added {amount} RP to {get_player_display_name(member, ctx.guild.id)}!",
        delete_after=5)

    # Log the reward update
    await log_reward_update(ctx.guild.id, member.id, amount, 0)


@bot.command(name="rp_rmv")
async def rp_rmv(ctx, member: discord.Member, amount: int = 1):
    try:
        await ctx.message.delete()
    except:
        pass

    if not has_permission(ctx.author, ctx.guild.id, 'admin'):
        await ctx.send("❌ You don't have admin permissions!", delete_after=5)
        return

    add_rp(ctx.guild.id, member.id, -amount)
    await ctx.send(
        f"✅ Removed {amount} RP from {get_player_display_name(member, ctx.guild.id)}!",
        delete_after=5)

    # Log the reward update
    await log_reward_update(ctx.guild.id, member.id, -amount, 0)


@bot.command(name="crwn_add")
async def crwn_add(ctx, member: discord.Member, amount: int = 1):
    try:
        await ctx.message.delete()
    except:
        pass

    if not has_permission(ctx.author, ctx.guild.id, 'admin'):
        await ctx.send("❌ You don't have admin permissions!", delete_after=5)
        return

    add_crown(ctx.guild.id, member.id, amount)
    await ctx.send(
        f"✅ Added {amount} crown(s) to {get_player_display_name(member, ctx.guild.id)}!",
        delete_after=5)

    # Log the reward update
    await log_reward_update(ctx.guild.id, member.id, 0, amount)


@bot.command(name="crwn_rmv")
async def crwn_rmv(ctx, member: discord.Member, amount: int = 1):
    try:
        await ctx.message.delete()
    except:
        pass

    if not has_permission(ctx.author, ctx.guild.id, 'admin'):
        await ctx.send("❌ You don't have admin permissions!", delete_after=5)
        return

    add_crown(ctx.guild.id, member.id, -amount)
    await ctx.send(
        f"✅ Removed {amount} crown(s) from {get_player_display_name(member, ctx.guild.id)}!",
        delete_after=5)

    # Log the reward update
    await log_reward_update(ctx.guild.id, member.id, 0, -amount)


@bot.command(name="crowns")
async def crowns(ctx):
    try:
        await ctx.message.delete()
    except:
        pass

    guild_str = str(ctx.guild.id)
    guild_crown_data = crown_data.get(guild_str, {})

    if not guild_crown_data:
        await ctx.send("No crown data found for this server!", delete_after=5)
        return

    # Sort players by crowns
    sorted_players = sorted(guild_crown_data.items(),
                            key=lambda x: x[1],
                            reverse=True)

    # Create leaderboard
    leaderboard_text = ""
    for i, (user_id, crowns) in enumerate(sorted_players[:10], 1):
        user = ctx.guild.get_member(int(user_id))
        if user and crowns > 0:
            # Add ranking emojis
            if i == 1:
                emoji = "🥇"
            elif i == 2:
                emoji = "🥈"
            elif i == 3:
                emoji = "🥉"
            else:
                emoji = f"**{i}.**"

            leaderboard_text += f"{emoji} {get_player_display_name(user, ctx.guild.id)} - {crowns}<:Crown:1394255336310968434>\n"

    if not leaderboard_text:
        await ctx.send("No players with crowns found!", delete_after=5)
        return

    embed = discord.Embed(title="👑 Crown Leaderboard",
                          description=leaderboard_text,
                          color=0xffd700)
    await ctx.send(embed=embed)


@bot.command(name="brkt_add")
async def brkt_add(ctx, member: discord.Member, emoji: str):
    try:
        await ctx.message.delete()
    except:
        pass

    if not has_permission(ctx.author, ctx.guild.id, 'admin'):
        await ctx.send("❌ You don't have admin permissions!", delete_after=5)
        return

    add_bracket_role(ctx.guild.id, member.id, emoji)
    save_data()
    await ctx.send(
        f"✅ Added bracket emoji {emoji} to {get_player_display_name(member, ctx.guild.id)}!",
        delete_after=5)

    # Log the reward update
    await log_reward_update(ctx.guild.id, member.id, 0, 0)


@bot.command(name="brkt_rmv")
async def brkt_rmv(ctx, member: discord.Member, emoji: str = None):
    try:
        await ctx.message.delete()
    except:
        pass

    if not has_permission(ctx.author, ctx.guild.id, 'admin'):
        await ctx.send("❌ You don't have admin permissions!", delete_after=5)
        return

    guild_str = str(ctx.guild.id)
    user_str = str(member.id)
    
    if guild_str in bracket_roles and user_str in bracket_roles[guild_str]:
        if emoji:
            # Remove specific emoji
            if emoji in bracket_roles[guild_str][user_str]:
                bracket_roles[guild_str][user_str].remove(emoji)
                if not bracket_roles[guild_str][user_str]:  # Remove empty list
                    del bracket_roles[guild_str][user_str]
                save_data()
                await ctx.send(
                    f"✅ Removed bracket emoji {emoji} from {get_player_display_name(member, ctx.guild.id)}!",
                    delete_after=5)
            else:
                await ctx.send(f"❌ {get_player_display_name(member, ctx.guild.id)} doesn't have emoji {emoji}!", delete_after=5)
        else:
            # Remove all bracket emojis
            del bracket_roles[guild_str][user_str]
            save_data()
            await ctx.send(
                f"✅ Removed all bracket emojis from {get_player_display_name(member, ctx.guild.id)}!",
                delete_after=5)
        
        # Log the reward update
        await log_reward_update(ctx.guild.id, member.id, 0, 0)
    else:
        await ctx.send(f"❌ {get_player_display_name(member, ctx.guild.id)} has no bracket emojis!", delete_after=5)


# Log and Update Commands

@bot.command(name="rb_log")
@commands.guild_only()
async def rb_log(ctx, channel: discord.TextChannel):
    try:
        await ctx.message.delete()
    except:
        pass

    if not has_permission(ctx.author, ctx.guild.id, 'admin'):
        await ctx.send("❌ You don't have admin permissions!", delete_after=5)
        return

    guild_str = str(ctx.guild.id)
    log_channels[guild_str] = channel.id
    save_data()

    await ctx.send(f"✅ Log channel set to {channel.mention}!", delete_after=5)

    # Try to restore data from previous messages
    restored = await parse_leaderboard_data(channel)
    if restored:
        await ctx.send("✅ Restored data from previous messages!", delete_after=3)

    # Create initial embed
    await update_log_embed(ctx.guild.id, channel)


@bot.command(name="update")
@commands.guild_only()
async def update(ctx, number: int = 50):
    # Validate number parameter
    if number < 1 or number > 1000:
        await ctx.send("❌ Number must be between 1 and 1000!", delete_after=5)
        return
    try:
        await ctx.message.delete()
    except:
        pass

    if not has_permission(ctx.author, ctx.guild.id, 'admin'):
        await ctx.send("❌ You don't have admin permissions!", delete_after=5)
        return

    guild_str = str(ctx.guild.id)
    
    # Use current channel if no log channel is set
    if guild_str not in log_channels:
        channel = ctx.channel
        log_channels[guild_str] = channel.id
        save_data()
        await ctx.send("✅ Using current channel as log channel!", delete_after=3)
        
        # Try to restore data from previous messages in this channel
        restored = await parse_leaderboard_data(channel, number)
        if restored:
            await ctx.send(f"✅ Restored data from last {number} messages!", delete_after=3)
    else:
        channel_id = log_channels[guild_str]
        channel = bot.get_channel(channel_id)
        if not channel:
            # Fallback to current channel if saved channel not found
            channel = ctx.channel
            log_channels[guild_str] = channel.id
            save_data()
            await ctx.send("✅ Previous log channel not found, using current channel!", delete_after=3)
            
        # Parse messages from the channel
        restored = await parse_leaderboard_data(channel, number)
        if restored:
            await ctx.send(f"✅ Restored data from last {number} messages!", delete_after=3)

    await update_log_embed(ctx.guild.id, channel)
    await ctx.send("✅ Leaderboard updated - showing only members with RP/Crowns/Brackets!", delete_after=3)


# Role Permission Commands

@bot.command(name="htr")
async def htr(ctx, *roles: discord.Role):
    try:
        await ctx.message.delete()
    except:
        pass

    if not ctx.author.guild_permissions.administrator:
        await ctx.send("❌ You need Administrator permissions!", delete_after=5)
        return

    if not roles:
        await ctx.send("❌ Please mention at least one role!", delete_after=5)
        return

    guild_str = str(ctx.guild.id)
    if guild_str not in role_permissions:
        role_permissions[guild_str] = {}

    role_permissions[guild_str]['tournament_host'] = [role.id for role in roles]
    save_data()

    role_mentions = [role.mention for role in roles]
    await ctx.send(
        f"✅ Tournament host roles set to: {', '.join(role_mentions)}!",
        delete_after=5)


@bot.command(name="adr")
async def adr(ctx, role: discord.Role):
    try:
        await ctx.message.delete()
    except:
        pass

    if not ctx.author.guild_permissions.administrator:
        await ctx.send("❌ You need Administrator permissions!", delete_after=5)
        return

    guild_str = str(ctx.guild.id)
    if guild_str not in role_permissions:
        role_permissions[guild_str] = {}

    role_permissions[guild_str]['admin'] = [role.id]
    save_data()

    await ctx.send(f"✅ Admin role set to: {role.mention}!", delete_after=5)


@bot.command(name="tlr")
async def tlr(ctx, *roles: discord.Role):
    try:
        await ctx.message.delete()
    except:
        pass

    if not ctx.author.guild_permissions.administrator:
        await ctx.send("❌ You need Administrator permissions!", delete_after=5)
        return

    if not roles:
        await ctx.send("❌ Please mention at least one role!", delete_after=5)
        return

    guild_str = str(ctx.guild.id)
    if guild_str not in role_permissions:
        role_permissions[guild_str] = {}

    role_permissions[guild_str]['tournament_leader'] = [
        role.id for role in roles
    ]
    save_data()

    role_mentions = [role.mention for role in roles]
    await ctx.send(
        f"✅ Tournament leader roles set to: {', '.join(role_mentions)}!",
        delete_after=5)


@bot.command(name="hoster")
async def hoster(ctx):
    try:
        await ctx.message.delete()
    except:
        pass

    embed = discord.Embed(
        title="🏆 Tournament Hoster Registration",
        description="Register to become a tournament hoster or view requirements.",
        color=0x3498db
    )

    view = HosterRegistrationView()
    await ctx.send(embed=embed, view=view)


# Run the bot
if __name__ == "__main__":
    keep_alive()

    # Load token from environment
    token = os.getenv('TOKEN')
    if not token:
        print("❌ No bot token found! Please set the TOKEN environment variable.")
        exit(1)

    print("🚀 Starting Discord Tournament Bot...")
    bot.run(token)
