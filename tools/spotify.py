"""Spotify music control tool."""

from __future__ import annotations

import asyncio
import difflib
import logging
import os
import re
from typing import Optional

import spotipy
from dotenv import load_dotenv
from spotipy.oauth2 import SpotifyOAuth

from utils.env_config import env_bool

from .pioneer_avr import setup_avr
from .tool_registry import tool, tool_registry

load_dotenv()

logger = logging.getLogger(__name__)

SCOPE = "user-read-playback-state user-modify-playback-state user-read-currently-playing"
SIMILARITY_THRESHOLD = 0.6

SPOTIPY_CLIENT_ID = os.getenv("SPOTIPY_CLIENT_ID", "").strip()
SPOTIPY_CLIENT_SECRET = os.getenv("SPOTIPY_CLIENT_SECRET", "").strip()
SPOTIPY_REDIRECT_URI = os.getenv("SPOTIPY_REDIRECT_URI", "http://localhost:8888/callback").strip()
SPOTIFY_DEVICE_NAME = os.getenv("SPOTIFY_DEVICE_ID", "").strip()
SPOTIFY_USE_AVR = env_bool("SPOTIFY_USE_AVR", False)

_sp_client = None


def _get_spotify_client():
    """Create Spotify client lazily so missing env does not crash imports."""
    global _sp_client
    if _sp_client is not None:
        return _sp_client

    if not (SPOTIPY_CLIENT_ID and SPOTIPY_CLIENT_SECRET and SPOTIPY_REDIRECT_URI):
        return None

    try:
        auth_manager = SpotifyOAuth(
            client_id=SPOTIPY_CLIENT_ID,
            client_secret=SPOTIPY_CLIENT_SECRET,
            redirect_uri=SPOTIPY_REDIRECT_URI,
            scope=SCOPE,
        )
        _sp_client = spotipy.Spotify(auth_manager=auth_manager)
        return _sp_client
    except Exception as exc:
        logger.error("Spotify initialization failed: %s", exc)
        return None


def get_active_device(sp_client) -> Optional[str]:
    """Get the active Spotify device ID."""
    devices = sp_client.devices()

    # Prefer configured device name when provided
    if SPOTIFY_DEVICE_NAME:
        for device in devices.get("devices", []):
            if device.get("name") == SPOTIFY_DEVICE_NAME:
                return device.get("id")

    # Fall back to currently active device
    for device in devices.get("devices", []):
        if device.get("is_active"):
            return device.get("id")

    return None


@tool(
    name="play_song",
    description="Play a song by artist and title, or search for a song by query",
    aliases=["play", "play_music", "start_music"],
)
def play_song(artist_query: Optional[str] = None, song: Optional[str] = None) -> str:
    """Play a song or playlist on Spotify."""
    sp_client = _get_spotify_client()
    if sp_client is None:
        return "Spotify not configured. Set SPOTIPY_CLIENT_ID, SPOTIPY_CLIENT_SECRET, and SPOTIPY_REDIRECT_URI."

    if SPOTIFY_USE_AVR:
        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            asyncio.run(setup_avr("Music"))
        else:
            loop.create_task(setup_avr("Music"))

    if artist_query and re.search(r"\s+by\s+", artist_query):
        parts = artist_query.split(" by ")
        if len(parts) == 2:
            artist_query, song = parts[1].strip(), parts[0].strip()

    if (re.sub(r"[^A-Za-z]+", "", str(artist_query).lower()) == "music") or (artist_query is None):
        pause()
        sp_client.start_playback(device_id=get_active_device(sp_client))
        return "Playing music on spotify"

    playlists = sp_client.current_user_playlists(limit=50).get("items", [])

    playlist_names = [pl.get("name") for pl in playlists if pl.get("name")]
    matches = difflib.get_close_matches(artist_query or "", playlist_names, n=1, cutoff=SIMILARITY_THRESHOLD)
    if matches:
        for playlist in playlists:
            if playlist.get("name") == matches[0]:
                pause()
                sp_client.start_playback(
                    device_id=get_active_device(sp_client),
                    context_uri=playlist.get("uri"),
                )
                return f"Playing your playlist \"{playlist.get('name')}\""

    for playlist in playlists[:5]:
        results = sp_client.playlist_tracks(playlist.get("id"))
        for item in results.get("items", []):
            track = item.get("track") or {}
            artists = track.get("artists") or [{}]
            artist_name = artists[0].get("name", "")

            if (song and song.lower() in track.get("name", "").lower()) or (
                artist_query and artist_query.lower() in artist_name.lower()
            ):
                pause()
                sp_client.start_playback(device_id=get_active_device(sp_client), uris=[track.get("uri")])
                return f"Playing {track.get('name')} by {artist_name} from your playlist \"{playlist.get('name')}\""

    if artist_query and song:
        results = sp_client.search(q=f"artist:{artist_query} track:{song}", type="track", limit=1)
    elif artist_query:
        results = sp_client.search(q=artist_query, type="track", limit=1)
    else:
        return "Please provide either artist and song, playlist name, or a search query"

    try:
        tracks = results.get("tracks", {}).get("items", [])
        uris = [track["uri"] for track in tracks if "uri" in track]

        if not uris:
            pause()
            sp_client.start_playback(device_id=get_active_device(sp_client))
            return "No tracks found, starting playback"

        pause()
        sp_client.start_playback(device_id=get_active_device(sp_client), uris=uris)
        track = tracks[0]
        artist_name = (track.get("artists") or [{}])[0].get("name", "Unknown artist")
        return f"Playing {track.get('name')} by {artist_name}"
    except Exception:
        return "Unable to play your request"


def is_playing() -> bool:
    """Check if Spotify is currently playing."""
    sp_client = _get_spotify_client()
    if sp_client is None:
        return False

    playback = sp_client.current_playback()
    return bool(playback and playback.get("is_playing"))


@tool(
    name="pause",
    description="Pause the currently playing music",
    aliases=["stop"],
)
def pause() -> str:
    """Pause currently playing music on Spotify."""
    sp_client = _get_spotify_client()
    if sp_client is None:
        return "Spotify not configured."

    playback = sp_client.current_playback()
    if playback and playback.get("is_playing"):
        sp_client.pause_playback()
    return "Playback paused."


@tool(
    name="resume",
    description="Resume the currently paused music",
    aliases=["play", "unpause"],
)
def resume() -> str:
    """Resume paused Spotify playback."""
    sp_client = _get_spotify_client()
    if sp_client is None:
        return "Spotify not configured."

    playback = sp_client.current_playback()
    if playback and not playback.get("is_playing"):
        sp_client.start_playback(device_id=get_active_device(sp_client))
    return "Playback resumed."


@tool(
    name="skip",
    description="Skip to the next track",
    aliases=["next", "next_track"],
)
def skip() -> str:
    """Skip to next track."""
    sp_client = _get_spotify_client()
    if sp_client is None:
        return "Spotify not configured."

    sp_client.next_track()
    return "Skipped to next track."


if __name__ == "__main__":
    print("Spotify Music Controller")
    client = _get_spotify_client()
    print(client.current_playback() if client else "Spotify not configured")

    print("\nAvailable tools:")
    for schema in tool_registry.get_all_schemas():
        print(f"  {schema.name}: {schema.description}")
        for param in schema.parameters:
            print(f"    - {param.name} ({param.type.value}): {param.description}")

    print("\nTesting function calling:")
    result = tool_registry.execute_tool("play_song", kwargs={"artist_query": "old mervs cellphone"})
    print(f"Result: {result}")
