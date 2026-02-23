# Discord Music Bot (Python)

Simple Discord music bot using `discord.py`, `yt-dlp`, Spotify API, and FFmpeg.

## Features

- Slash commands
- Per-server music queue
- YouTube URL/search support
- Spotify track/album/playlist URL support
- Basic controls: join, play, queue, skip, stop, leave

## Requirements

- Python 3.12+
- FFmpeg installed and available on PATH
- A Discord bot token
- Spotify app credentials (client ID + secret)

## 1) Create the Discord Bot

1. Open the Discord Developer Portal: `https://discord.com/developers/applications`
2. Create a new application.
3. Go to **Bot** and click **Add Bot**.
4. Under **Privileged Gateway Intents**, message content intent is not required for this bot.
5. Copy the bot token.

## 2) Configure the Project

1. In this folder, create `.env` from `.env.example`.
2. Set your environment values:

```env
DISCORD_TOKEN=your_real_token_here
DISCORD_GUILD_ID=your_server_id_here
SPOTIFY_CLIENT_ID=your_spotify_client_id
SPOTIFY_CLIENT_SECRET=your_spotify_client_secret
```

## Spotify Setup

1. Go to `https://developer.spotify.com/dashboard`
2. Create an app.
3. Copy **Client ID** and **Client Secret** into `.env`.

## 3) Install Dependencies

```powershell
python -m pip install -r requirements.txt
```

## 4) Install FFmpeg (Windows)

If `ffmpeg` is not already available:

```powershell
winget install -e --id Gyan.FFmpeg
```

Then open a new terminal and confirm:

```powershell
ffmpeg -version
```

## 5) Run the Bot

```powershell
python .\bot.py
```

If startup succeeds, you'll see login output in the console.

## 6) Invite Bot to Your Server

1. In Developer Portal, go to **OAuth2 -> URL Generator**.
2. Scopes: select `bot` and `applications.commands`.
3. Bot Permissions: at least `Connect`, `Speak`, `Use Voice Activity`, `View Channels`.
4. Open the generated URL and add the bot to your server.

Or generate an exact invite URL from this repo:

```powershell
.\generate_invite.ps1 -ClientId YOUR_APPLICATION_ID
```

The script includes permissions for:
- View Channels
- Send Messages
- Read Message History
- Embed Links
- Connect
- Speak
- Use Voice Activity

## Slash Commands

- `/join` : join your voice channel
- `/play query:<url or search>` : play/queue from YouTube or Spotify
- `/queue` : view queue
- `/skip` : skip current song
- `/stop` : clear queue and stop playback
- `/leave` : disconnect and clear queue

## Notes

- This is a basic starter bot. Add moderation/permission checks before production use.
- Streaming from external platforms can break when providers change formats or policy.
- Spotify links are resolved to YouTube searches for playback.


## Bot Control App

- Double-click launch_bot_control.bat to open a small app.
- Use **Start Bot** to launch the bot in background.
- Use **Stop Bot** to stop it.
- Use **Status** to check if it is running.

## Deploy on Railway

1. Push this repo to GitHub.
2. Go to `https://railway.app` and create a new project.
3. Choose **Deploy from GitHub repo** and select this repo.
4. Railway will build using `Dockerfile` in this project.
5. In Railway project variables, set:
   - `DISCORD_TOKEN`
   - `DISCORD_GUILD_ID`
   - `SPOTIFY_CLIENT_ID`
   - `SPOTIFY_CLIENT_SECRET`
6. Deploy and keep one instance running.

Notes:
- Do not commit `.env` to GitHub.
- Rotate leaked secrets before deploying.

