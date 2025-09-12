#!/usr/bin/env python3
import os
import re
import sys
from urllib.parse import urljoin, urlparse, unquote
from concurrent.futures import ThreadPoolExecutor, as_completed
import requests

# -------- CONFIG ----------
DOWNLOAD_DIR = os.path.join(os.path.expanduser("~"), "Downloads", "FF_downloader")
LINKS_FILE = "links.txt"
MAX_WORKERS = 4
USER_AGENT = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
              "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/115 Safari/537.36")
# --------------------------

os.makedirs(DOWNLOAD_DIR, exist_ok=True)

def read_links():
    if not os.path.exists(LINKS_FILE):
        print(f"No {LINKS_FILE} found. Created an example and exiting.")
        with open(LINKS_FILE, "w", encoding="utf-8") as f:
            f.write("- https://fuckingfast.co/example.iso\n")
        sys.exit(1)
    links = []
    with open(LINKS_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            if line.startswith("- "):
                links.append(line[2:].strip())
            else:
                links.append(line)
    return links

def find_direct_link(session, page_url):
    """Return a /dl/ URL if found on the landing page, else None."""
    # quick path: if url already looks like /dl/ assume it's direct
    if "/dl/" in page_url:
        return page_url
    try:
        r = session.get(page_url, headers={"User-Agent": USER_AGENT}, timeout=15)
    except Exception as e:
        print(f"⚠️  Error fetching page {page_url}: {e}")
        return None
    text = r.text

    # common patterns seen in scripts: window.open("https://fuckingfast.co/dl/...")
    m = re.search(r'window\.open\((["\'])(https?://fuckingfast\.co/dl/[^"\']+)\1', text)
    if m:
        return m.group(2)

    # href="https://fuckingfast.co/dl/..."
    m = re.search(r'href=(["\'])(https?://fuckingfast\.co/dl/[^"\']+)\1', text)
    if m:
        return m.group(2)

    # any absolute /dl/ URL found in page
    m = re.search(r'(https?://fuckingfast\.co/dl/[^\s"\'<>]+)', text)
    if m:
        return m.group(1)

    # relative /dl/ link like '/dl/xyz'
    m = re.search(r'(?:["\'])(/dl/[^"\']+)(?:["\'])', text)
    if m:
        return urljoin(page_url, m.group(1))

    return None

def get_filename_from_cd(cd):
    """Parse Content-Disposition header for filename."""
    if not cd:
        return None
    # handle filename* and filename forms
    m = re.search(r"filename\*=UTF-8''([^;]+)", cd)
    if m:
        return unquote(m.group(1).strip().strip('"'))
    m = re.search(r'filename=(?:"([^"]+)"|([^;]+))', cd)
    if m:
        return (m.group(1) or m.group(2)).strip().strip('"')
    return None

def safe_filename_from_url(url):
    path = urlparse(url).path
    name = os.path.basename(path)
    return name or "downloaded_file"

def download_one(orig_url):
    session = requests.Session()
    try:
        direct = find_direct_link(session, orig_url)
        if direct:
            headers = {"User-Agent": USER_AGENT, "Referer": orig_url}
            resp = session.get(direct, headers=headers, stream=True, allow_redirects=True, timeout=30)
        else:
            # fallback: try downloading original URL (some links are direct)
            headers = {"User-Agent": USER_AGENT}
            resp = session.get(orig_url, headers=headers, stream=True, allow_redirects=True, timeout=30)

        resp.raise_for_status()

        # Determine filename
        fname = get_filename_from_cd(resp.headers.get("content-disposition"))
        if not fname:
            fname = safe_filename_from_url(resp.url)

        out_path = os.path.join(DOWNLOAD_DIR, fname)
        base, ext = os.path.splitext(out_path)
        i = 1
        while os.path.exists(out_path):
            out_path = f"{base} ({i}){ext}"
            i += 1

        print(f"⬇️  Downloading: {orig_url} -> {out_path}")
        with open(out_path, "wb") as out_f:
            for chunk in resp.iter_content(chunk_size=8192):
                if chunk:
                    out_f.write(chunk)
        print(f"✅ Finished: {out_path}")
    except Exception as e:
        print(f"❌ Failed: {orig_url} — {e}")

def main():
    links = read_links()
    if not links:
        print("No links to download.")
        return
    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as ex:
        futures = [ex.submit(download_one, u) for u in links]
        for fut in as_completed(futures):
            # we don't need the result; errors are printed inside download_one
            pass

if __name__ == "__main__":
    main()
