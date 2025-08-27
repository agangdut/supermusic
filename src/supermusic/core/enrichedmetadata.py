#!/usr/bin/env python3

"""
enrichedmetadata.py
Classify MP3 genre(s) via MusicBrainz (optionally AcoustID fingerprint lookup).

Features:
- Read artist/title from ID3 (mutagen)
- Lookup MusicBrainz recording/release-group and gather genres/tags
- Prefer official MB "genres" > user tags > release-group/artist fallbacks
- Optional AcoustID lookup from audio (requires CHROMAPRINT & API key)
- Write genre back to ID3 (optional)
- CSV summary + simple on-disk cache

Install:
  pip install mutagen musicbrainzngs acoustid pandas tqdm

AcoustID requires Chromaprint:
  - macOS: brew install chromaprint
  - Linux: apt-get install chromaprint
  - Windows: install Chromaprint/FPcalc binary and ensure it's on PATH
"""

import argparse
import hashlib
import json
import os
import sys
import time
from pathlib import Path

import pandas as pd
from tqdm import tqdm


# --- Optional deps (import when needed)
def _lazy_mutagen():
    from mutagen.easyid3 import EasyID3
    from mutagen.mp3 import MP3

    return EasyID3, MP3


def _lazy_mb():
    import musicbrainzngs as mb

    return mb


def _lazy_acoustid():
    import acoustid

    return acoustid


# ---------------------- MusicBrainz helpers ----------------------


def mb_init(app="EnrichedMetadata", version="0.1", contact=None):
    mb = _lazy_mb()
    # MusicBrainz requires a contact string; add your email if you can.
    mb.set_useragent(app, version, contact=contact or "contact@example.com")
    return mb


def _best_rg_from_recording(rec: dict) -> tuple[str | None, str | None]:
    """Pick a good release-group from a recording payload."""
    rg = rec.get("release-group")
    if rg and rg.get("id"):
        return rg["id"], rg.get("title")

    # fallback through releases
    for r in rec.get("releases", []) or []:
        rg2 = r.get("release-group", {})
        if rg2.get("id"):
            # prefer Album if possible
            if rg2.get("primary-type") == "Album":
                return rg2["id"], rg2.get("title")
    # final pass: first seen
    for r in rec.get("releases", []) or []:
        rg2 = r.get("release-group", {})
        if rg2.get("id"):
            return rg2["id"], rg2.get("title")
    return None, None


def _extract_genres_from_entity(ent: dict) -> list[str]:
    """
    MusicBrainz returns:
      - "genres": list of {"name": "...", "count": int}
      - "tags":   list of {"name": "...", "count": int}
    Prefer genres; fallback to tags.
    """
    out = []
    for k in ("genres", "tags"):
        items = ent.get(k, []) or []
        for it in items:
            name = it.get("name") or it.get("genre") or ""
            if name:
                out.append(name.strip())
        if out:  # prefer the first non-empty bucket
            break
    # Dedup, preserve order
    seen = set()
    res = []
    for g in out:
        key = g.lower()
        if key not in seen:
            seen.add(key)
            res.append(g)
    return res


def mb_lookup_by_artist_title(
    mb, artist: str, title: str
) -> tuple[dict | None, dict | None, dict | None]:
    """
    Return (recording, release-group, artist) payloads if found.
    """
    try:
        sr = mb.search_recordings(artist=artist, recording=title, limit=5)
        recs = sr.get("recording-list", [])
        # heuristic: prefer highest ext:score that has a release-group or releases
        best = None
        for rec in recs:
            try:
                score = int(rec.get("ext:score", 0))
            except Exception:
                score = 0
            tup = (score, rec)
            if best is None or tup > best:
                best = tup
        if not best:
            return None, None, None

        rec = best[1]
        # fetch full recording details
        rid = rec.get("id")
        if not rid:
            return rec, None, None
        full = mb.get_recording_by_id(
            rid, includes=["genres", "tags", "artists", "releases", "release-groups"]
        )
        rec_full = full.get("recording", {})

        # release-group details
        rgid, _ = _best_rg_from_recording(rec_full)
        rg_full = None
        if rgid:
            rg_full = mb.get_release_group_by_id(rgid, includes=["genres", "tags"]).get(
                "release-group", {}
            )

        # primary artist details (first credited)
        art_full = None
        arts = rec_full.get("artist-credit", [])
        if arts:
            aid = arts[0].get("artist", {}).get("id")
            if aid:
                art_full = mb.get_artist_by_id(aid, includes=["genres", "tags"]).get(
                    "artist", {}
                )

        return rec_full, rg_full, art_full
    except Exception:
        return None, None, None


def mb_lookup_by_acoustid(
    mb, acoustid_key: str, path: str
) -> tuple[dict | None, dict | None, dict | None]:
    """
    Use AcoustID fingerprint to identify the track and then pull MB data.
    Requires chromaprint (fpcalc) installed and acoustid_key.
    """
    acoustid = _lazy_acoustid()
    try:
        # identify() returns candidates with MBIDs
        res = acoustid.match(
            acoustid_key,
            path,
            parse=True,
            meta="recordings releases releasegroups artists",
        )
        # choose top candidate that has a recording MBID
        top = None
        for cand in res:
            score, recording_id = cand.get("score", 0), None
            for r in cand.get("recordings", []) or []:
                rid = r.get("id")
                if rid:
                    recording_id = rid
                    break
            if recording_id:
                t = (score, recording_id)
                if top is None or t > top:
                    top = t
        if not top:
            return None, None, None

        rid = top[1]
        rec_full = mb.get_recording_by_id(
            rid, includes=["genres", "tags", "artists", "releases", "release-groups"]
        ).get("recording", {})

        rgid, _ = _best_rg_from_recording(rec_full)
        rg_full = (
            mb.get_release_group_by_id(rgid, includes=["genres", "tags"]).get(
                "release-group", {}
            )
            if rgid
            else None
        )

        art_full = None
        arts = rec_full.get("artist-credit", [])
        if arts:
            aid = arts[0].get("artist", {}).get("id")
            if aid:
                art_full = mb.get_artist_by_id(aid, includes=["genres", "tags"]).get(
                    "artist", {}
                )

        return rec_full, rg_full, art_full
    except Exception:
        return None, None, None


def choose_genre(
    rec: dict | None, rg: dict | None, art: dict | None
) -> tuple[str, list[str], str]:
    """
    Decide a single label plus supporting list and provenance.
    Priority:
      recording.genres/tags > release-group.genres/tags > artist.genres/tags
    """
    for ent, src in ((rec, "recording"), (rg, "release-group"), (art, "artist")):
        if not ent:
            continue
        glist = _extract_genres_from_entity(ent)
        if glist:
            primary = glist[0]
            return primary, glist, src
    return "", [], ""  # unknown


# ---------------------- ID3 helpers ----------------------


def read_id3_artist_title(path: str) -> tuple[str | None, str | None]:
    EasyID3, MP3 = _lazy_mutagen()
    try:
        audio = EasyID3(path)
        artist = (audio.get("artist") or [None])[0]
        title = (audio.get("title") or [None])[0]
        return artist, title
    except Exception:
        # try full MP3 for safety
        try:
            audio = MP3(path)
            artist = None
            title = None
            if audio.tags:
                if "TPE1" in audio.tags:  # lead performer
                    artist = str(audio.tags["TPE1"])
                if "TIT2" in audio.tags:  # title
                    title = str(audio.tags["TIT2"])
            return artist, title
        except Exception:
            return None, None


def write_id3_genre(path: str, genre: str) -> bool:
    EasyID3, _ = _lazy_mutagen()
    try:
        audio = EasyID3(path)
        if genre:
            audio["genre"] = [genre]
            audio.save()
            return True
        return False
    except Exception:
        return False


# ---------------------- Cache ----------------------


def load_cache(cache_path: str) -> dict[str, dict]:
    if not cache_path or not os.path.exists(cache_path):
        return {}
    try:
        with open(cache_path, encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_cache(cache_path: str, cache: dict[str, dict]) -> None:
    if not cache_path:
        return
    try:
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


def cache_key_from_audio(artist: str | None, title: str | None, size_bytes: int) -> str:
    h = hashlib.sha1(
        f"{artist or ''}|||{title or ''}|||{size_bytes}".encode()
    ).hexdigest()
    return h


# ---------------------- Main pipeline ----------------------


def process_file(
    path: str,
    mb,
    acoustid_key: str | None,
    write_id3: bool,
    pause_sec: float,
    cache: dict[str, dict],
) -> dict:
    p = Path(path)
    size = p.stat().st_size if p.exists() else 0

    artist, title = read_id3_artist_title(path)
    ck = cache_key_from_audio(artist, title, size)

    if ck in cache:
        return cache[ck]

    rec, rg, art = None, None, None
    # First try: ID3 artist/title
    if artist and title:
        rec, rg, art = mb_lookup_by_artist_title(mb, artist, title)

    # Fallback: AcoustID fingerprint
    if not rec and acoustid_key:
        rec, rg, art = mb_lookup_by_acoustid(mb, acoustid_key, path)

    # Choose genre
    primary, all_genres, source = choose_genre(rec, rg, art)

    # Optionally write back to ID3
    wrote = False
    if write_id3 and primary:
        wrote = write_id3_genre(path, primary)

    # Be nice to MB servers
    time.sleep(pause_sec)

    result = {
        "file": str(p),
        "artist_id3": artist or "",
        "title_id3": title or "",
        "genre_primary": primary,
        "genres_all": "; ".join(all_genres) if all_genres else "",
        "genre_source": source,
        "wrote_id3": bool(wrote),
    }
    cache[ck] = result
    return result


def find_mp3s(inputs: list[str]) -> list[str]:
    out = []
    for inp in inputs:
        p = Path(inp)
        if p.is_dir():
            out += [str(x) for x in p.rglob("*.mp3")]
        elif p.suffix.lower() == ".mp3" and p.exists():
            out.append(str(p))
    return sorted(set(out))


def main():
    ap = argparse.ArgumentParser(
        description="Classify MP3 genre via MusicBrainz (with optional AcoustID fallback) and optionally write it to ID3."
    )
    ap.add_argument("inputs", nargs="+", help="MP3 files and/or folders")
    ap.add_argument("--csv", default="../csv/genres.csv", help="Output CSV path")
    ap.add_argument(
        "--write-id3",
        action="store_true",
        help="Write chosen genre back to the MP3 ID3 tag",
    )
    ap.add_argument(
        "--mb-contact", help="Email for MusicBrainz user-agent (recommended)"
    )
    ap.add_argument(
        "--pause",
        type=float,
        default=1.0,
        help="Sleep seconds between lookups (be nice to MB)",
    )
    ap.add_argument(
        "--cache", default=".mb_genre_cache.json", help="Path to JSON cache"
    )
    ap.add_argument(
        "--acoustid-key",
        help="AcoustID API key for audio fingerprint fallback (optional)",
    )
    args = ap.parse_args()

    files = find_mp3s(args.inputs)
    if not files:
        print("No MP3 files found.", file=sys.stderr)
        sys.exit(2)

    mb = mb_init(contact=args.mb_contact)
    cache = load_cache(args.cache)

    rows = []
    for f in tqdm(files, desc="Classifying", unit="file"):
        try:
            res = process_file(
                f,
                mb,
                acoustid_key=args.acoustid_key,
                write_id3=args.write_id3,
                pause_sec=args.pause,
                cache=cache,
            )
            rows.append(res)
        except KeyboardInterrupt:
            print("\nInterrupted.")
            break
        except Exception as e:
            rows.append(
                {
                    "file": f,
                    "artist_id3": "",
                    "title_id3": "",
                    "genre_primary": "",
                    "genres_all": "",
                    "genre_source": "",
                    "wrote_id3": False,
                    "error": str(e),
                }
            )

    # Save cache
    save_cache(args.cache, cache)

    # Emit CSV
    df = pd.DataFrame(rows)
    df.to_csv(args.csv, index=False)
    print(f"[OK] Wrote {len(df)} rows → {args.csv}")


if __name__ == "__main__":
    main()
