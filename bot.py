import asyncio
import json
import os
import re
from collections import deque
from dataclasses import dataclass
from typing import Deque, Optional
from urllib.parse import quote_plus
from urllib.request import Request, urlopen

import discord
from discord import app_commands
from discord.errors import NotFound
from discord.ext import commands
from dotenv import load_dotenv
import spotipy
from spotipy.oauth2 import SpotifyClientCredentials
import yt_dlp
from yt_dlp.utils import DownloadError


load_dotenv()

DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
DISCORD_GUILD_ID = os.getenv("DISCORD_GUILD_ID")
DISCORD_GUILD_IDS = os.getenv("DISCORD_GUILD_IDS", "")
SPOTIFY_CLIENT_ID = os.getenv("SPOTIFY_CLIENT_ID")
SPOTIFY_CLIENT_SECRET = os.getenv("SPOTIFY_CLIENT_SECRET")
YTDLP_COOKIEFILE = os.getenv("YTDLP_COOKIEFILE")
MAX_SPOTIFY_TRACKS = 25
IDLE_TIMEOUT_SECONDS = 60 * 60

YDL_OPTIONS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "default_search": "ytsearch",
    # Try multiple YouTube client profiles to reduce "sign in" blocks.
    "extractor_args": {
        "youtube": {
            "player_client": ["android", "web", "tv_embedded"],
        }
    },
}

if YTDLP_COOKIEFILE:
    YDL_OPTIONS["cookiefile"] = YTDLP_COOKIEFILE

SC_YDL_OPTIONS = {
    "format": "bestaudio/best",
    "noplaylist": True,
    "quiet": True,
    "default_search": "scsearch",
}

FFMPEG_OPTIONS = {
    "before_options": "-reconnect 1 -reconnect_streamed 1 -reconnect_delay_max 5",
    "options": "-vn",
}


@dataclass
class Song:
    title: str
    stream_url: str
    webpage_url: str
    requester_id: int


class GuildPlayer:
    def __init__(self) -> None:
        self.queue: Deque[Song] = deque()
        self.lock = asyncio.Lock()
        self.voice_lock = asyncio.Lock()
        self.now_playing: Optional[Song] = None
        self.idle_task: Optional[asyncio.Task] = None


players: dict[int, GuildPlayer] = {}
spotify_client: Optional[spotipy.Spotify] = None


def get_player(guild_id: int) -> GuildPlayer:
    player = players.get(guild_id)
    if player is None:
        player = GuildPlayer()
        players[guild_id] = player
    return player


def cancel_idle_disconnect(player: GuildPlayer) -> None:
    if player.idle_task and not player.idle_task.done():
        player.idle_task.cancel()
    player.idle_task = None


def schedule_idle_disconnect(guild: discord.Guild) -> None:
    player = get_player(guild.id)
    cancel_idle_disconnect(player)

    async def _idle_disconnect() -> None:
        try:
            await asyncio.sleep(IDLE_TIMEOUT_SECONDS)
            vc = guild.voice_client
            if vc and vc.is_connected() and not vc.is_playing() and not vc.is_paused() and not player.queue:
                await vc.disconnect()
                player.now_playing = None
                print(f"Idle timeout reached in guild {guild.id}; disconnected from voice.")
        except asyncio.CancelledError:
            pass

    player.idle_task = asyncio.create_task(_idle_disconnect())


intents = discord.Intents.default()
intents.guilds = True
intents.voice_states = True

bot = commands.Bot(command_prefix="!", intents=intents)


def parse_guild_ids(raw: str) -> tuple[list[int], list[str]]:
    parsed: list[int] = []
    invalid: list[str] = []
    for item in raw.split(","):
        value = item.strip()
        if not value:
            continue
        try:
            parsed.append(int(value))
        except ValueError:
            invalid.append(value)
    return parsed, invalid


def get_spotify_client() -> spotipy.Spotify:
    global spotify_client
    if spotify_client:
        return spotify_client
    if not SPOTIFY_CLIENT_ID or not SPOTIFY_CLIENT_SECRET:
        raise RuntimeError("Spotify is not configured. Set SPOTIFY_CLIENT_ID and SPOTIFY_CLIENT_SECRET in .env.")
    credentials = SpotifyClientCredentials(
        client_id=SPOTIFY_CLIENT_ID,
        client_secret=SPOTIFY_CLIENT_SECRET,
    )
    spotify_client = spotipy.Spotify(auth_manager=credentials)
    return spotify_client


def parse_spotify_url(url: str) -> tuple[str, str]:
    match = re.search(r"open\.spotify\.com/(track|album|playlist)/([A-Za-z0-9]+)", url)
    if not match:
        raise RuntimeError("Unsupported Spotify URL. Use track, album, or playlist links.")
    return match.group(1), match.group(2)


def spotify_queries_from_url(url: str) -> list[str]:
    sp = get_spotify_client()
    kind, resource_id = parse_spotify_url(url)
    queries: list[str] = []

    def _to_query(track: dict) -> Optional[str]:
        name = (track or {}).get("name")
        artists = (track or {}).get("artists") or []
        artist_names = ", ".join([a.get("name", "") for a in artists if a and a.get("name")]).strip()
        if not name:
            return None
        return f"{name} {artist_names}".strip()

    if kind == "track":
        track = sp.track(resource_id)
        query = _to_query(track)
        if query:
            queries.append(query)
    elif kind == "album":
        offset = 0
        while len(queries) < MAX_SPOTIFY_TRACKS:
            page = sp.album_tracks(resource_id, limit=50, offset=offset)
            items = page.get("items", [])
            if not items:
                break
            for track in items:
                query = _to_query(track)
                if query:
                    queries.append(query)
                if len(queries) >= MAX_SPOTIFY_TRACKS:
                    break
            if not page.get("next"):
                break
            offset += 50
    else:
        offset = 0
        while len(queries) < MAX_SPOTIFY_TRACKS:
            page = sp.playlist_items(
                resource_id,
                limit=100,
                offset=offset,
                fields="items(track(name,artists(name))),next",
            )
            items = page.get("items", [])
            if not items:
                break
            for item in items:
                track = (item or {}).get("track")
                query = _to_query(track)
                if query:
                    queries.append(query)
                if len(queries) >= MAX_SPOTIFY_TRACKS:
                    break
            if not page.get("next"):
                break
            offset += 100

    if not queries:
        raise RuntimeError("No playable tracks found in that Spotify link.")
    return queries


async def extract_song(query: str) -> Song:
    loop = asyncio.get_running_loop()

    def _extract_with_options(local_query: str, options: dict) -> dict:
        try:
            with yt_dlp.YoutubeDL(options) as ydl:
                info = ydl.extract_info(local_query, download=False)
                if "entries" in info:
                    entries = [entry for entry in info["entries"] if entry]
                    if not entries:
                        raise ValueError("No results found.")
                    info = entries[0]
                return info
        except DownloadError as exc:
            msg = str(exc).lower()
            if "drm" in msg:
                raise RuntimeError("This video is DRM-protected and cannot be played.") from exc
            if "sign in to confirm" in msg:
                raise RuntimeError("YouTube blocked this request. Try another video.") from exc
            raise RuntimeError("Failed to fetch audio from YouTube.") from exc

    def _extract() -> dict:
        def _youtube_oembed_title(url: str) -> Optional[str]:
            if "youtube.com" not in url and "youtu.be" not in url:
                return None
            try:
                endpoint = "https://www.youtube.com/oembed?url=" + quote_plus(url) + "&format=json"
                req = Request(endpoint, headers={"User-Agent": "Mozilla/5.0"})
                with urlopen(req, timeout=8) as response:
                    payload = json.loads(response.read().decode("utf-8"))
                title = payload.get("title")
                return title.strip() if isinstance(title, str) and title.strip() else None
            except Exception:
                return None

        # First attempt: YouTube
        try:
            return _extract_with_options(query, YDL_OPTIONS)
        except Exception as yt_exc:
            # Fallback attempt: SoundCloud search for better resilience.
            try:
                if query.lower().startswith("http"):
                    title = _youtube_oembed_title(query)
                    sc_query = f"scsearch1:{title}" if title else f"scsearch1:{query}"
                else:
                    sc_query = f"scsearch1:{query}"
                return _extract_with_options(sc_query, SC_YDL_OPTIONS)
            except Exception:
                raise yt_exc

    info = await loop.run_in_executor(None, _extract)
    stream_url = info.get("url")
    if not stream_url:
        raise ValueError("Could not get audio stream URL.")

    return Song(
        title=info.get("title", "Unknown title"),
        stream_url=stream_url,
        webpage_url=info.get("webpage_url", query),
        requester_id=0,
    )


async def ensure_voice(interaction: discord.Interaction) -> discord.VoiceClient:
    if interaction.guild is None:
        raise RuntimeError("This command can only be used in a server.")
    if not interaction.user or not isinstance(interaction.user, discord.Member):
        raise RuntimeError("Could not resolve your member information.")
    if not interaction.user.voice or not interaction.user.voice.channel:
        raise RuntimeError("Join a voice channel first.")

    guild = interaction.guild
    voice_channel = interaction.user.voice.channel
    player = get_player(guild.id)

    async def _connect_with_retry() -> discord.VoiceClient:
        last_exc: Optional[Exception] = None
        for _ in range(3):
            try:
                vc = await voice_channel.connect(timeout=20.0, reconnect=True)
                if vc.is_connected():
                    return vc
            except Exception as exc:
                last_exc = exc
                await asyncio.sleep(1.5)
        raise RuntimeError(f"Voice connection failed: {last_exc}")

    async with player.voice_lock:
        voice_client = guild.voice_client
        if voice_client is None:
            voice_client = await _connect_with_retry()
            if not voice_client.is_connected():
                raise RuntimeError("I could not stay connected to voice.")
            return voice_client

        if not voice_client.is_connected():
            await voice_client.disconnect(force=True)
            voice_client = await _connect_with_retry()
            if not voice_client.is_connected():
                raise RuntimeError("Voice connection failed.")
            return voice_client

        if voice_client.channel != voice_channel:
            if voice_client.is_playing() or voice_client.is_paused():
                raise RuntimeError(
                    f"I'm already active in **{voice_client.channel}**. Join that channel or use /leave first."
                )
            await voice_client.move_to(voice_channel)

        return voice_client


async def play_next(guild: discord.Guild) -> None:
    voice_client = guild.voice_client
    if voice_client is None:
        return

    player = get_player(guild.id)
    async with player.lock:
        if voice_client.is_playing() or voice_client.is_paused():
            cancel_idle_disconnect(player)
            return
        if not player.queue:
            player.now_playing = None
            schedule_idle_disconnect(guild)
            return

        song = player.queue.popleft()
        player.now_playing = song
        cancel_idle_disconnect(player)
        try:
            source = discord.FFmpegPCMAudio(song.stream_url, **FFMPEG_OPTIONS)
        except Exception as exc:
            print(f"FFmpeg source error in guild {guild.id}: {exc}")
            player.now_playing = None
            await play_next(guild)
            return

        def _after_playback(error: Optional[Exception]) -> None:
            if error:
                print(f"Playback error in guild {guild.id}: {error}")
            asyncio.run_coroutine_threadsafe(play_next(guild), bot.loop)

        voice_client.play(source, after=_after_playback)


@bot.event
async def on_ready() -> None:
    print(f"Logged in as {bot.user} (ID: {bot.user.id})")

    if DISCORD_GUILD_IDS.strip():
        guild_ids, invalid_ids = parse_guild_ids(DISCORD_GUILD_IDS)
        if invalid_ids:
            print(f"Ignoring invalid DISCORD_GUILD_IDS entries: {', '.join(invalid_ids)}")

        total_synced = 0
        for guild_id in guild_ids:
            guild = discord.Object(id=guild_id)
            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)
            total_synced += len(synced)
            print(f"Synced {len(synced)} guild slash commands to {guild_id}.")

        if not guild_ids:
            synced = await bot.tree.sync()
            print(f"No valid DISCORD_GUILD_IDS. Synced {len(synced)} global slash commands.")
        else:
            print(f"Guild sync complete across {len(guild_ids)} guild(s), total commands synced: {total_synced}.")
    elif DISCORD_GUILD_ID:
        try:
            guild_id = int(DISCORD_GUILD_ID)
            guild = discord.Object(id=guild_id)
            bot.tree.copy_global_to(guild=guild)
            synced = await bot.tree.sync(guild=guild)
            print(f"Synced {len(synced)} guild slash commands to {guild_id}.")
        except ValueError:
            synced = await bot.tree.sync()
            print(f"Synced {len(synced)} global slash commands.")
    else:
        synced = await bot.tree.sync()
        print(f"Synced {len(synced)} global slash commands.")


@bot.tree.error
async def on_app_command_error(interaction: discord.Interaction, error: app_commands.AppCommandError) -> None:
    print(f"Slash command error: {error}")
    try:
        if interaction.response.is_done():
            await interaction.followup.send(f"Error: {error}", ephemeral=True)
        else:
            await interaction.response.send_message(f"Error: {error}", ephemeral=True)
    except NotFound:
        pass


@bot.tree.command(name="join", description="Join your current voice channel.")
async def join(interaction: discord.Interaction) -> None:
    try:
        await interaction.response.defer(thinking=True, ephemeral=True)
        vc = await ensure_voice(interaction)
        if not vc.is_connected():
            raise RuntimeError("I could not connect to voice.")
        schedule_idle_disconnect(interaction.guild)
        await interaction.followup.send("Joined your voice channel.", ephemeral=True)
    except Exception as exc:
        if interaction.response.is_done():
            try:
                await interaction.followup.send(str(exc), ephemeral=True)
            except NotFound:
                pass
        else:
            try:
                await interaction.response.send_message(str(exc), ephemeral=True)
            except NotFound:
                pass


@bot.tree.command(name="play", description="Play a song from YouTube URL or search terms.")
@app_commands.describe(query="YouTube/Spotify URL or search terms")
async def play(interaction: discord.Interaction, query: str) -> None:
    try:
        await interaction.response.defer(thinking=True)
        vc = await ensure_voice(interaction)
        if not vc.is_connected():
            raise RuntimeError("Voice connection failed. I did not queue your song.")

        player = get_player(interaction.guild_id)
        cancel_idle_disconnect(player)
        if "open.spotify.com/" in query.lower():
            spotify_queries = await asyncio.to_thread(spotify_queries_from_url, query)
            added = 0
            failed = 0
            first_title: Optional[str] = None

            for spotify_query in spotify_queries:
                try:
                    song = await extract_song(spotify_query)
                    if interaction.user:
                        song.requester_id = interaction.user.id
                    if not first_title:
                        first_title = song.title
                    player.queue.append(song)
                    added += 1
                except Exception:
                    failed += 1

            if added == 0:
                raise RuntimeError("Could not resolve any Spotify tracks to playable sources.")

            await play_next(interaction.guild)
            if player.now_playing and first_title and player.now_playing.title == first_title:
                await interaction.followup.send(
                    f"Now playing from Spotify: **{player.now_playing.title}**\n"
                    f"Queued {added - 1} more track(s)."
                    + (f" Skipped {failed} track(s)." if failed else "")
                )
            else:
                await interaction.followup.send(
                    f"Queued {added} track(s) from Spotify."
                    + (f" Skipped {failed} track(s)." if failed else "")
                    + (
                        f" (Limited to first {MAX_SPOTIFY_TRACKS} tracks.)"
                        if added + failed >= MAX_SPOTIFY_TRACKS
                        else ""
                    )
                )
        else:
            song = await extract_song(query)
            if interaction.user:
                song.requester_id = interaction.user.id

            player.queue.append(song)
            await play_next(interaction.guild)

            if player.now_playing and player.now_playing.title == song.title:
                await interaction.followup.send(f"Now playing: **{song.title}**\n{song.webpage_url}")
            else:
                await interaction.followup.send(f"Queued: **{song.title}**")
    except Exception as exc:
        if interaction.response.is_done():
            try:
                await interaction.followup.send(f"Error: {exc}", ephemeral=True)
            except NotFound:
                pass
        else:
            try:
                await interaction.response.send_message(f"Error: {exc}", ephemeral=True)
            except NotFound:
                pass


@bot.tree.command(name="skip", description="Skip the current song.")
async def skip(interaction: discord.Interaction) -> None:
    if interaction.guild is None or interaction.guild.voice_client is None:
        await interaction.response.send_message("I'm not connected to voice.", ephemeral=True)
        return
    vc = interaction.guild.voice_client
    if vc.is_playing() or vc.is_paused():
        vc.stop()
        await interaction.response.send_message("Skipped.")
    else:
        await interaction.response.send_message("Nothing is playing.", ephemeral=True)


@bot.tree.command(name="stop", description="Stop playback and clear queue.")
async def stop(interaction: discord.Interaction) -> None:
    if interaction.guild is None:
        await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
        return
    player = get_player(interaction.guild.id)
    player.queue.clear()
    player.now_playing = None
    vc = interaction.guild.voice_client
    if vc and (vc.is_playing() or vc.is_paused()):
        vc.stop()
    if vc and vc.is_connected():
        schedule_idle_disconnect(interaction.guild)
    await interaction.response.send_message("Stopped playback and cleared the queue.")


@bot.tree.command(name="queue", description="Show the current queue.")
async def queue(interaction: discord.Interaction) -> None:
    if interaction.guild is None:
        await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
        return
    player = get_player(interaction.guild.id)
    lines = []
    if player.now_playing:
        lines.append(f"Now playing: **{player.now_playing.title}**")
    if player.queue:
        lines.append("Up next:")
        for idx, song in enumerate(list(player.queue)[:10], start=1):
            lines.append(f"{idx}. {song.title}")
    if not lines:
        lines.append("Queue is empty.")
    await interaction.response.send_message("\n".join(lines), ephemeral=True)


@bot.tree.command(name="leave", description="Leave voice channel and clear queue.")
async def leave(interaction: discord.Interaction) -> None:
    if interaction.guild is None:
        await interaction.response.send_message("This command can only be used in a server.", ephemeral=True)
        return
    vc = interaction.guild.voice_client
    player = get_player(interaction.guild.id)
    player.queue.clear()
    player.now_playing = None
    cancel_idle_disconnect(player)
    if vc:
        await vc.disconnect()
        await interaction.response.send_message("Disconnected and cleared queue.")
    else:
        await interaction.response.send_message("I'm not connected to voice.", ephemeral=True)


if __name__ == "__main__":
    if not DISCORD_TOKEN:
        raise RuntimeError("DISCORD_TOKEN is missing. Add it to your .env file.")
    bot.run(DISCORD_TOKEN)
