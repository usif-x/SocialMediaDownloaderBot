import argparse
import json
import re
from urllib.parse import urlencode

import requests

HEADERS = {
    "User-Agent": "Mozilla/5.0",
    "Accept-Language": "en-US,en;q=0.9",
}

API_URL = "https://www.youtube.com/youtubei/v1/search"
API_KEY = "AIzaSyAO_FJ2SlqU8Q4STEHLGCilw_Y9_11qcW8"


def extract_yt_initial_data(html):
    m = re.search(r"var ytInitialData = ({.*?});</script>", html, re.DOTALL)
    if not m:
        raise Exception("ytInitialData not found")
    return json.loads(m.group(1))


def extract_continuation(data):
    # Try a few possible locations for the continuation token; be permissive
    def _find_token(obj):
        if isinstance(obj, dict):
            # common patterns
            if "continuationCommand" in obj and isinstance(
                obj["continuationCommand"], dict
            ):
                tok = obj["continuationCommand"].get("token")
                if tok:
                    return tok

            if "continuationEndpoint" in obj:
                ep = obj["continuationEndpoint"]
                if isinstance(ep, dict):
                    # some payloads put token under continuationCommand or directly
                    cmd = ep.get("continuationCommand") or ep
                    if isinstance(cmd, dict) and cmd.get("token"):
                        return cmd.get("token")

            for v in obj.values():
                tok = _find_token(v)
                if tok:
                    return tok

        elif isinstance(obj, list):
            for it in obj:
                tok = _find_token(it)
                if tok:
                    return tok

        return None

    try:
        # first try the expected path
        contents = data["contents"]["twoColumnSearchResultsRenderer"][
            "primaryContents"
        ]["sectionListRenderer"]["contents"]
        last = contents[-1]
        tok = _find_token(last)
        if tok:
            return tok
    except Exception:
        pass

    # fallback: search whole payload
    return _find_token(data)


def extract_videos_from_items(items):
    results = []
    for item in items:
        vr = item.get("videoRenderer")
        if not vr:
            continue

        # prefer video duration if present, otherwise published time
        time_text = vr.get("lengthText", {}).get("simpleText") or vr.get(
            "publishedTimeText", {}
        ).get("simpleText", "")

        results.append(
            {
                "title": vr["title"]["runs"][0]["text"],
                "url": f"https://www.youtube.com/watch?v={vr['videoId']}",
                "time": time_text,
                "views": vr.get("viewCountText", {}).get("simpleText", "0"),
                "image": vr["thumbnail"]["thumbnails"][-1]["url"],
            }
        )
    return results


def parse_first_page(html):
    data = extract_yt_initial_data(html)

    contents = data["contents"]["twoColumnSearchResultsRenderer"]["primaryContents"][
        "sectionListRenderer"
    ]["contents"]

    videos = []
    for section in contents:
        items = section.get("itemSectionRenderer", {}).get("contents", [])
        videos.extend(extract_videos_from_items(items))

    continuation = extract_continuation(data)
    return videos, continuation


def fetch_continuation(token):
    payload = {
        "context": {
            "client": {"clientName": "WEB", "clientVersion": "2.20240101.00.00"}
        },
        "continuation": token,
    }

    r = requests.post(
        f"{API_URL}?key={API_KEY}",
        headers={**HEADERS, "Content-Type": "application/json"},
        json=payload,
        timeout=15,
    )

    r.raise_for_status()
    return r.json()


def parse_continuation(data):
    # Collect video renderers and continuation token from various response shapes
    videos = []
    continuation = None

    def _traverse(obj):
        nonlocal continuation
        if isinstance(obj, dict):
            # videoRenderer entries
            if "videoRenderer" in obj:
                videos.extend(
                    extract_videos_from_items([{"videoRenderer": obj["videoRenderer"]}])
                )

            # continuation token
            if "continuationItemRenderer" in obj:
                tok = None
                try:
                    tok = obj["continuationItemRenderer"]["continuationEndpoint"][
                        "continuationCommand"
                    ]["token"]
                except Exception:
                    # try alternative locations
                    tok = extract_continuation(obj)
                if tok:
                    continuation = tok

            for v in obj.values():
                _traverse(v)

        elif isinstance(obj, list):
            for it in obj:
                _traverse(it)

    # common root keys
    for key in (
        "onResponseReceivedActions",
        "onResponseReceivedEndpoints",
        "continuationContents",
        "appendContinuationItemsAction",
    ):
        if key in data:
            _traverse(data[key])

    # fallback to traverse whole payload
    if not videos and not continuation:
        _traverse(data)

    return videos, continuation


def main():
    parser = argparse.ArgumentParser(description="YouTube Search with Pagination")
    parser.add_argument("query", help="Search query")
    parser.add_argument("--page", type=int, default=1)
    args = parser.parse_args()

    # الصفحة الأولى
    url = "https://www.youtube.com/results?" + urlencode({"search_query": args.query})
    html = requests.get(url, headers=HEADERS, timeout=15).text

    videos, continuation = parse_first_page(html)

    # paginate into fixed-size pages (10 results per page)
    page_size = 10
    buffer = list(videos)
    results = []

    for current_page in range(1, args.page + 1):
        # ensure buffer has at least one full page or until no continuation
        while len(buffer) < page_size and continuation:
            data = fetch_continuation(continuation)
            new_videos, continuation = parse_continuation(data)
            buffer.extend(new_videos)

        # take a page slice
        page_slice = buffer[:page_size]
        buffer = buffer[page_size:]

        if current_page == args.page:
            results = page_slice
            break

    print(
        json.dumps(
            {
                "ok": True,
                "query": args.query,
                "page": args.page,
                "count": len(results),
                "results": results,
            },
            indent=2,
            ensure_ascii=False,
        )
    )


if __name__ == "__main__":
    main()
