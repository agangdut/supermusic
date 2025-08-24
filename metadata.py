#!/usr/bin/env python3
import os, csv, re, argparse
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import json, sys
from yt_dlp import YoutubeDL

def yt_dlp_info(video_id: str) -> dict:
    """Return extra metadata from yt-dlp without downloading."""
    url = f"https://www.youtube.com/watch?v={video_id}"
    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "noplaylist": True,
        # Avoid network retries spamming output; adjust if needed:
        "retries": 2,
    }
    try:
        with YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            # Keep only fields we care about
            return {
                "track": info.get("track"),
                "artist": info.get("artist"),
                "album": info.get("album"),
                "release_year": info.get("release_year"),
                "genres": info.get("genres"),          # may be None or a list
                "channel": info.get("channel"),
                "uploader": info.get("uploader"),
                "uploader_id": info.get("uploader_id"),
                "uploader_url": info.get("uploader_url"),
                "categories": info.get("categories"),  # list of high-level categories, sometimes includes 'Music'
                "tags": info.get("tags"),              # alternative tag source
                "thumbnail": info.get("thumbnail"),    # best single thumbnail
                "thumbnails": info.get("thumbnails"),  # list of thumbnails
                "duration": info.get("duration"),      # seconds (int)
                "chapters": info.get("chapters"),      # list of {start_time, end_time, title}
                "is_live": info.get("is_live"),
                "availability": info.get("availability"),
            }
    except Exception:
        return {}


def explain_http_error(e: HttpError, where: str):
    try:
        err = json.loads(e.content.decode("utf-8"))
    except Exception:
        err = {"raw": e.content.decode("utf-8", "ignore")}
    print(f"\nYouTube API HttpError in {where}:", file=sys.stderr)
    print(json.dumps(err, indent=2), file=sys.stderr)


# Map YouTube topic IDs -> genres
TOPIC_TO_GENRE = {
    "/m/0ggq0m": "Hip hop",
    "/m/0glt670": "Pop",
    "/m/02mscn": "Rock",
    "/m/01lyv": "Jazz",
    "/m/028sqc": "Classical",
    "/m/06cqb": "Electronic",
    "/m/02lkt": "Country",
    "/m/064t9": "Reggae",
    "/m/0gywn": "R&B",
    "/m/02xw9": "Blues",
    "/m/0dls3": "Gospel",
}
YEAR_RE = re.compile(r"\b(19\d{2}|20\d{2})\b")

def build_client(api_key: str):
    return build("youtube", "v3", developerKey=api_key)

def fetch_categories_map(youtube, region_code="US"):
    out = {}
    resp = youtube.videoCategories().list(part="snippet", regionCode=region_code).execute()
    for item in resp.get("items", []):
        out[item["id"]] = item["snippet"]["title"]
    return out

def videos_details(youtube, ids):
    details = []
    for i in range(0, len(ids), 50):  # API max batch = 50
        resp = youtube.videos().list(
            part="snippet,contentDetails,topicDetails,statistics",
            id=",".join(ids[i:i+50])
        ).execute()
        details.extend(resp.get("items", []))
    return details

def guess_year(*texts):
    for t in texts:
        if not t: continue
        m = YEAR_RE.search(t)
        if m:
            return m.group(1)
    return None

def guess_genre(item):
    topics = item.get("topicDetails", {}).get("topicIds", [])
    for t in topics:
        if t in TOPIC_TO_GENRE:
            return TOPIC_TO_GENRE[t]

    # Fallback: tags
    tags = item.get("snippet", {}).get("tags", [])
    for tag in tags:
        low = tag.lower()
        for key, val in TOPIC_TO_GENRE.items():
            if val.lower() in low:
                return val

    # Fallback: title/description keyword search
    title = item.get("snippet", {}).get("title", "").lower()
    desc = item.get("snippet", {}).get("description", "").lower()
    for val in TOPIC_TO_GENRE.values():
        if val.lower() in title or val.lower() in desc:
            return val

    return "Unknown"

def parse_music_info(snippet):
    title = snippet.get("title", "")
    # crude regex to split "Artist - Song" or "Song - Artist"
    m = re.match(r"^(.*?)\s*-\s*(.*?)$", title)
    if m:
        left, right = m.groups()
        return left.strip(), right.strip()
    return None, None

def merge_metadata(original_row, yt_item, catmap, yt_dlp_extra=None):
    sn = yt_item.get("snippet", {})
    stats = yt_item.get("statistics", {})
    cd = yt_item.get("contentDetails", {})
    year = guess_year(sn.get("title"), sn.get("description"))
    genre = guess_genre(yt_item)

    # yt-dlp extras (all optional)
    td_track = (yt_dlp_extra or {}).get("track")
    td_artist = (yt_dlp_extra or {}).get("artist")
    td_album = (yt_dlp_extra or {}).get("album")
    td_release_year = (yt_dlp_extra or {}).get("release_year")
    td_genres = (yt_dlp_extra or {}).get("genres") or []
    td_thumbnail = (yt_dlp_extra or {}).get("thumbnail")
    td_duration_s = (yt_dlp_extra or {}).get("duration")
    td_tags = (yt_dlp_extra or {}).get("tags") or []
    td_chapters = (yt_dlp_extra or {}).get("chapters") or []

    # Prefer explicit music fields from yt-dlp if we don't already have them
    # Song/Artist parsing fallback remains, but yt-dlp often gives structured fields.
    artist_guess, song_guess = None, None
    if td_artist or td_track:
        artist_guess = td_artist
        song_guess = td_track
    else:
        # fallback to parsing title (your earlier approach)
        artist_guess, song_guess = parse_music_info(sn)

    # Prefer release year from yt-dlp if we didn't guess one
    year_guess = str(td_release_year) if td_release_year and not year else year

    # Combine tags (YouTube API + yt-dlp)
    api_tags = sn.get("tags", [])
    all_tags = list(dict.fromkeys(api_tags + td_tags))  # unique, preserve order

    # Duration: keep ISO8601 but also expose seconds if yt-dlp gave it
    duration_iso8601 = cd.get("duration")
    duration_seconds = td_duration_s

    merged = dict(original_row)
    merged.update({
        "YouTube Title": sn.get("title"),
        "YouTube Channel": sn.get("channelTitle"),
        "Published At": sn.get("publishedAt"),
        "Category": catmap.get(sn.get("categoryId", ""), ""),
        "Genre Guess": genre or (td_genres[0] if td_genres else None),
        "Year Guess": year_guess,
        "Artist Guess": artist_guess or sn.get("channelTitle"),
        "Song Guess": song_guess,
        "Album Guess": td_album,
        "Tags": ";".join(all_tags),
        "Duration": duration_iso8601,
        "Duration (s)": duration_seconds,
        "Views": stats.get("viewCount"),
        "Likes": stats.get("likeCount"),
        "Comments": stats.get("commentCount"),
        "Thumbnail": td_thumbnail or sn.get("thumbnails", {}).get("high", {}).get("url"),
    })

    # Optional: include chapters as a compact string column
    if td_chapters:
        def _fmt(ch):
            st = ch.get("start_time"); et = ch.get("end_time"); tt = ch.get("title", "")
            return f"{st}-{et}:{tt}"
        merged["Chapters"] = " | ".join(_fmt(c) for c in td_chapters)

    return merged


def fetch_categories_map(youtube, region_code="US"):
    out = {}
    try:
        resp = youtube.videoCategories().list(
            part="snippet", regionCode=region_code
        ).execute()
    except HttpError as e:
        explain_http_error(e, "videoCategories.list")
        # Keep going with empty mapping so the rest can still run
        return {}
    for item in resp.get("items", []):
        out[item["id"]] = item["snippet"]["title"]
    return out

def videos_details(youtube, ids):
    details = []
    for i in range(0, len(ids), 50):
        try:
            resp = youtube.videos().list(
                part="snippet,contentDetails,topicDetails,statistics",
                id=",".join(ids[i:i+50])
            ).execute()
        except HttpError as e:
            explain_http_error(e, "videos.list")
            continue
        details.extend(resp.get("items", []))
    return details


def main():
    ap = argparse.ArgumentParser(description="Enrich a CSV of YouTube video IDs with YouTube metadata.")
    ap.add_argument("--input", required=True, help="Input CSV with Video ID column")
    ap.add_argument("--output", required=True, help="Output CSV with metadata")
    ap.add_argument("--region", default="US", help="Region for category names")
    ap.add_argument("--use-yt-dlp", action="store_true",
                help="Use yt-dlp to enrich missing music metadata (artist, track, album, year, genres)")
    args = ap.parse_args()


    api_key = os.environ.get("YOUTUBE_API_KEY")
    #REMOVED_API_KEY
    if not api_key:
        raise SystemExit("Set YOUTUBE_API_KEY environment variable")

    yt = build_client(api_key)
    catmap = fetch_categories_map(yt, args.region)

    # Read input CSV
    with open(args.input, newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        input_rows = list(reader)

    ids = [row["Video ID"] for row in input_rows if row.get("Video ID")]
    yt_items = {item["id"]: item for item in videos_details(yt, ids)}

    # Merge and write output CSV
    enriched = []
    for row in input_rows:
        vid = row.get("Video ID")
        if vid in yt_items:
            extra = yt_dlp_info(vid) if args.use_yt_dlp else None
            merged = merge_metadata(row, yt_items[vid], catmap, yt_dlp_extra=extra)
        else:
            merged = dict(row)
            merged.update({"Error": "Video not found"})
        enriched.append(merged)

    # Columns to omit from the OUTPUT CSV
    DROP_COLS = {
        "YouTube Title",
        "YouTube Channel",
        "Category",
        "Genre Guess",
        "Year Guess",
        "Artist Guess",
        "Song Guess",
        "Album Guess",
        "Tags",
        "Duration",          # keep "Duration (s)" instead
    }


    # Write out
    with open(args.output, "w", newline="", encoding="utf-8") as f:
        # Keep column order from the first row, minus the drops and any empty header
        fieldnames = [k for k in enriched[0].keys() if k and k not in DROP_COLS]
        writer = csv.DictWriter(f, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in enriched:
            writer.writerow(row)

    print(f"Wrote enriched metadata for {len(enriched)} rows to {args.output}")


if __name__ == "__main__":
    main()
