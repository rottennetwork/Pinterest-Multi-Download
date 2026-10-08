# language: Python 3.10+, file: pinch.py, runtime: CPython, dep: requests (2.x)
# requests gotcha: decodes gzip/deflate but not brotli, so we never advertise br
import argparse
import json
import re
import sys
import tempfile
import time
import zipfile
from concurrent.futures import ThreadPoolExecutor, as_completed
from html import unescape as html_unescape
from pathlib import Path
from urllib.parse import quote

import requests

SEARCH_URL = "https://www.pinterest.com/resource/BaseSearchResource/get/"
BING_IMAGES = "https://www.bing.com/images/search"
HOME_URL = "https://www.pinterest.com/"
UA = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/126.0.0.0 Safari/537.36"
)
IMG_EXTS = {".jpg", ".jpeg", ".png", ".gif", ".webp"}
CT_EXT = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/gif": ".gif",
    "image/webp": ".webp",
}
IMAGE_PREF = ["orig", "original", "1200x", "736x", "564x", "474x"]
BIG_SIZES = ("/1200x/", "/736x/", "/564x/", "/474x/", "/236x/")
MIN_BYTES = 8 * 1024
PAGE_SIZE = 100
BING_PAGE = 35
BING_STALL = 4
TIMEOUT = 20
MAX_RETRIES = 3
WORKERS = 8
SLEEP = 0.5


class Blocked(Exception):
    """source refused this client outright (403/404/410) — don't retry"""


def make_session() -> requests.Session:
    s = requests.Session()
    s.headers.update(
        {
            "User-Agent": UA,
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate",
            "Referer": HOME_URL,
        }
    )
    return s


def get_json(session: requests.Session, params: dict) -> dict | None:
    for attempt in range(MAX_RETRIES):
        try:
            r = session.get(SEARCH_URL, params=params, timeout=TIMEOUT)
            if r.status_code == 200:
                return r.json()
            if r.status_code in (403, 404, 410):
                raise Blocked(f"status {r.status_code}")
        except (requests.RequestException, ValueError):
            pass
        time.sleep(2**attempt)
    return None


def search_native_page(
    session: requests.Session, query: str, bookmark: str | None
) -> tuple[list[str], str | None]:
    options = {
        "query": query,
        "scope": "pins",
        "page_size": PAGE_SIZE,
        "page": bookmark or "",
        "query_from_signal": False,
    }
    data = {"options": options, "context": {}}
    params = {
        "source_url": f"/search/pins/?q={quote(query)}",
        "data": json.dumps(data, separators=(",", ":")),
        "_": str(int(time.time() * 1000)),
    }
    payload = get_json(session, params)
    if not payload:
        return [], None
    res = payload.get("resource_response") or {}
    results = ((res.get("data") or {}).get("results")) or []
    urls: list[str] = []
    for pin in results:
        if not isinstance(pin, dict):
            continue
        images = pin.get("images") or {}
        for key in IMAGE_PREF:
            entry = images.get(key)
            if isinstance(entry, dict) and entry.get("url"):
                urls.append(entry["url"])
                break
        else:
            for entry in (pin.get("files") or {}).values():
                if isinstance(entry, dict) and entry.get("url"):
                    urls.append(entry["url"])
                    break
    return urls, res.get("bookmark")


def collect_native(
    session: requests.Session, query: str, count: int, quiet: bool
) -> list[str]:
    urls: list[str] = []
    seen: set[str] = set()
    bookmark: str | None = None
    try:
        while len(urls) < count:
            page, bookmark = search_native_page(session, query, bookmark)
            if not page:
                break
            for url in page:
                base = url.split("?")[0]
                if base not in seen:
                    seen.add(base)
                    urls.append(base)
                    if len(urls) >= count:
                        break
            if not quiet:
                print(f"  [native] {len(urls)}/{count}", file=sys.stderr)
            if not bookmark:
                break
            time.sleep(SLEEP)
    except Blocked:
        if not quiet:
            print("  [native] blocked, switching to bridge", file=sys.stderr)
    return urls[:count]


def bing_page(session: requests.Session, query: str, first: int) -> list[str]:
    try:
        r = session.get(
            BING_IMAGES,
            params={"q": query, "first": first, "count": BING_PAGE},
            timeout=TIMEOUT,
        )
        if r.status_code != 200:
            return []
    except requests.RequestException:
        return []
    out: list[str] = []
    for raw in re.findall(r'm="(\{[^"]+\})"', r.text):
        try:
            item = json.loads(html_unescape(raw))
        except (json.JSONDecodeError, TypeError):
            continue
        url = (item.get("murl") or "").split("?")[0]
        if url.startswith("https://i.pinimg.com/") and (
            Path(url).suffix.lower() in IMG_EXTS
        ):
            out.append(url)
    return out


def collect_bridge(
    session: requests.Session, query: str, count: int, quiet: bool
) -> list[str]:
    variants = [f"{query} pinterest", f"{query} pinterest board", f"{query} pin"]
    urls: list[str] = []
    seen: set[str] = set()
    for variant in variants:
        if len(urls) >= count:
            break
        first, stall = 1, 0
        while len(urls) < count and stall < BING_STALL:
            fresh = [u for u in bing_page(session, variant, first) if u not in seen]
            if fresh:
                stall = 0
                seen.update(fresh)
                urls.extend(fresh)
            else:
                stall += 1
            if not quiet:
                print(
                    f"  [bridge] '{variant}' first={first}: {len(urls)}/{count}",
                    file=sys.stderr,
                )
            first += BING_PAGE
            time.sleep(SLEEP)
    return urls[:count]


def collect_urls(
    session: requests.Session, query: str, count: int, quiet: bool
) -> list[str]:
    native = collect_native(session, query, count, quiet)
    if len(native) >= count:
        return native
    seen = set(native)
    for url in collect_bridge(session, query, count, quiet):
        if url not in seen:
            seen.add(url)
            native.append(url)
        if len(native) >= count:
            break
    return native[:count]


def ext_for(url: str, content_type: str) -> str | None:
    ct = content_type.split(";")[0].strip().lower()
    if ct in CT_EXT:
        return CT_EXT[ct]
    suffix = Path(url.split("?")[0]).suffix.lower()
    return suffix if suffix in IMG_EXTS else None


def url_variants(url: str) -> list[str]:
    for size in BIG_SIZES:
        if size in url:
            return [url.replace(size, "/originals/"), url]
    return [url]


def fetch_bytes(session: requests.Session, url: str) -> tuple[bytes, str] | None:
    r = session.get(url, timeout=TIMEOUT, stream=True)
    if r.status_code != 200:
        return None
    ext = ext_for(url, r.headers.get("Content-Type", ""))
    if not ext:
        return None
    buf = bytearray()
    for chunk in r.iter_content(65536):
        buf.extend(chunk)
        if len(buf) > 40 * 1024 * 1024:
            break
    if len(buf) < MIN_BYTES:
        return None
    return bytes(buf), ext


def download_one(
    session: requests.Session, url: str, dest_dir: Path, index: int
) -> tuple[int, str | None]:
    for attempt in range(MAX_RETRIES):
        for variant in url_variants(url):
            try:
                got = fetch_bytes(session, variant)
            except requests.RequestException:
                got = None
            if got:
                data, ext = got
                name = f"pin_{index:04d}{ext}"
                (dest_dir / name).write_bytes(data)
                return index, name
        time.sleep(0.5 * (attempt + 1))
    return index, None


def slugify(text: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "_", text.lower()).strip("_")
    return slug or "pins"


def run(query: str, count: int, out_dir: Path) -> Path:
    session = make_session()
    try:
        session.get(HOME_URL, timeout=TIMEOUT)
    except requests.RequestException:
        pass

    print(f'[+] searching "{query}" for {count} images', file=sys.stderr)
    urls = collect_urls(session, query, count, quiet=False)
    if not urls:
        print("[-] no results from any source", file=sys.stderr)
        sys.exit(1)
    print(f"[+] {len(urls)} candidates, downloading", file=sys.stderr)

    names: list[str] = []
    with tempfile.TemporaryDirectory(prefix="pinch_") as tmp:
        tmp_dir = Path(tmp)
        done = 0
        with ThreadPoolExecutor(max_workers=WORKERS) as pool:
            futures = [
                pool.submit(download_one, session, url, tmp_dir, i + 1)
                for i, url in enumerate(urls)
            ]
            for fut in as_completed(futures):
                _, name = fut.result()
                done += 1
                if name:
                    names.append(name)
                print(f"  [{done}/{len(urls)}] {name or 'skipped'}", file=sys.stderr)

        if not names:
            print("[-] every download failed", file=sys.stderr)
            sys.exit(1)

        out_dir.mkdir(parents=True, exist_ok=True)
        stamp = time.strftime("%Y%m%d_%H%M%S")
        zip_path = out_dir / f"{slugify(query)}_{stamp}.zip"
        with zipfile.ZipFile(zip_path, "w", zipfile.ZIP_DEFLATED) as zf:
            for name in sorted(names):
                zf.write(tmp_dir / name, arcname=name)

    print(f"[+] zip ready: {zip_path} ({len(names)} images)", file=sys.stderr)
    return zip_path


def main() -> None:
    ap = argparse.ArgumentParser(description="pinterest image grabber -> zip")
    ap.add_argument("-q", "--query", help='search query, e.g. "megan fox 2007"')
    ap.add_argument("-n", "--count", type=int, help="how many images to gather")
    ap.add_argument("-o", "--out", default=".", help="output directory for the zip")
    args = ap.parse_args()

    query = args.query or input("search query: ").strip()
    if not query:
        print("[-] empty query", file=sys.stderr)
        sys.exit(1)

    count = args.count
    if not count:
        raw = input("how many images? [50]: ").strip() or "50"
        try:
            count = int(raw)
        except ValueError:
            print("[-] count must be a number", file=sys.stderr)
            sys.exit(1)
    count = max(1, min(count, 2000))

    run(query, count, Path(args.out).expanduser())


if __name__ == "__main__":
    main()
