import asyncio
import yt_dlp
from urllib.parse import urlparse, parse_qs, urlunparse, urlencode


async def get_video_urls_from_playlist(playlist_url: str) -> list:
    """Get video URLs from a YouTube playlist using yt-dlp (async, non-blocking)."""
    ydl_opts = {
        "quiet": True,
        "extract_flat": True,
        "skip_download": True,
    }

    def _do_extract():
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            return ydl.extract_info(playlist_url, download=False)

    try:
        info = await asyncio.wait_for(asyncio.to_thread(_do_extract), timeout=30)
    except asyncio.TimeoutError:
        print("Playlist extraction timed out")
        return []
    except Exception as e:
        print(f"Error al obtener la playlist: {e}")
        return []

    return [
        f"https://www.youtube.com/watch?v={entry['id']}"
        for entry in info.get("entries", [])
        if "id" in entry
    ]


def clean_yt_link(link: str) -> str:
    """Cleans a YouTube link by removing unnecessary query args."""
    parsed_link = urlparse(link)
    query_params = {
        k: v
        for k, v in parse_qs(parsed_link.query).items()
        if k not in {"list", "start_radio", "index", "t"}
    }
    new_query = urlencode(query_params, doseq=True)
    new_link = urlunparse(parsed_link._replace(query=new_query))
    return new_link
