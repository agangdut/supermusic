from __future__ import annotations

import os
from typing import Dict, Any, Optional
import requests

# External API integrations for metadata enrichment


def fetch_youtube_metadata(video_id: str) -> Dict[str, Any]:
    """
    Fetch metadata from YouTube (requires YouTube Data API key).
    Set YOUTUBE_API_KEY environment variable.
    """
    api_key = os.getenv("YOUTUBE_API_KEY")
    if not api_key:
        return {}
    
    try:
        url = f"https://www.googleapis.com/youtube/v3/videos"
        params = {
            "id": video_id,
            "key": api_key,
            "part": "snippet,contentDetails,statistics"
        }
        response = requests.get(url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if data.get("items"):
            item = data["items"][0]
            snippet = item.get("snippet", {})
            return {
                "title": snippet.get("title"),
                "description": snippet.get("description"),
                "channel": snippet.get("channelTitle"),
                "published_at": snippet.get("publishedAt"),
                "duration": item.get("contentDetails", {}).get("duration"),
                "view_count": item.get("statistics", {}).get("viewCount"),
            }
    except Exception as e:
        print(f"Warning: YouTube API error: {e}")
    
    return {}


def fetch_musicbrainz_metadata(artist: str, title: str) -> Dict[str, Any]:
    """
    Fetch metadata from MusicBrainz API.
    """
    try:
        # Search for recording
        url = "https://musicbrainz.org/ws/2/recording"
        params = {
            "query": f'artist:"{artist}" AND recording:"{title}"',
            "fmt": "json",
            "limit": 1
        }
        headers = {
            "User-Agent": "SuperMusic/1.0 (https://github.com/agangdut/supermusic)"
        }
        response = requests.get(url, params=params, headers=headers, timeout=10)
        response.raise_for_status()
        data = response.json()
        
        if data.get("recordings"):
            recording = data["recordings"][0]
            return {
                "mbid": recording.get("id"),
                "title": recording.get("title"),
                "artist": recording.get("artist-credit", [{}])[0].get("name") if recording.get("artist-credit") else None,
                "release_date": recording.get("first-release-date"),
                "tags": [tag.get("name") for tag in recording.get("tags", [])],
            }
    except Exception as e:
        print(f"Warning: MusicBrainz API error: {e}")
    
    return {}


def enrich_with_external_apis(record: Dict[str, Any]) -> Dict[str, Any]:
    """
    Enrich a track record with external API data.
    """
    enriched = record.copy()
    
    # Try YouTube if we have a URL
    youtube_url = record.get("youtube_url") or record.get("url", "")
    if "youtube.com" in youtube_url or "youtu.be" in youtube_url:
        # Extract video ID
        video_id = None
        if "v=" in youtube_url:
            video_id = youtube_url.split("v=")[1].split("&")[0]
        elif "youtu.be/" in youtube_url:
            video_id = youtube_url.split("youtu.be/")[1].split("?")[0]
        
        if video_id:
            youtube_data = fetch_youtube_metadata(video_id)
            enriched.update({f"youtube_{k}": v for k, v in youtube_data.items()})
    
    # Try MusicBrainz if we have artist and title
    artist = record.get("artist") or record.get("artist_name")
    title = record.get("title") or record.get("track_name")
    if artist and title:
        mb_data = fetch_musicbrainz_metadata(artist, title)
        enriched.update({f"musicbrainz_{k}": v for k, v in mb_data.items()})
    
    return enriched

