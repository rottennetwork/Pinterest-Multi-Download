========================================================================
PINCH — pinterest image grabber -> zip
doc file: pinch.txt   |   tool: pinch.py   |   written: 2026-10-07
========================================================================

WHAT IT IS
------------------------------------------------------------------------
pinch.py takes a search query ("megan fox 2007"), asks how many images
you want (default 50), downloads them into a throwaway temp directory,
zips the batch, hands you the zip path, and wipes the temp directory.
No install, no config file, no API keys.

    $ python3 pinch.py
    search query: megan fox 2007
    how many images? [50]: 50
    ...
    [+] zip ready: megan_fox_2007_20261007_171125.zip (50 images)

FLAGS (interactive prompts are skipped when flags are given)
------------------------------------------------------------------------
    -q / --query   search query            example: -q "megan fox 2007"
    -n / --count   how many images         clamp: 1..2000, default 50
    -o / --out     directory for the zip   default: current directory

    examples:
    python3 pinch.py -q "cyberpunk city" -n 100 -o ~/Desktop/zips
    python3 pinch.py                        # full interactive run


========================================================================
GETTING IT — DOWNLOAD + INSTALL PER PLATFORM
========================================================================
you need two things: python 3.10+, and the `requests` library.
nothing else. pick your platform.

------------------------------------------------------------------------
LINUX — DEBIAN / UBUNTU / LINUX MINT / POP!_OS (apt)
------------------------------------------------------------------------
    sudo apt update
    sudo apt install python3 python3-pip git
    git clone <your-repo-url>        # or just grab pinch.py (see below)
    cd pinch                          # folder containing pinch.py
    pip3 install requests
    # if pip refuses with "externally-managed-environment":
    pip3 install requests --break-system-packages
    # or the clean way (no system pollution):
    sudo apt install python3-venv
    python3 -m venv .venv && source .venv/bin/activate
    pip install requests
    python3 pinch.py -q "test" -n 3

------------------------------------------------------------------------
LINUX — FEDORA / RHEL / CENTOS (dnf)
------------------------------------------------------------------------
    sudo dnf install python3 python3-pip git
    git clone <your-repo-url>
    cd pinch
    pip3 install --user requests
    python3 pinch.py -q "test" -n 3

------------------------------------------------------------------------
LINUX — ARCH / MANJARO (pacman)
------------------------------------------------------------------------
    sudo pacman -S python python-pip git
    git clone <your-repo-url>
    cd pinch
    pip install requests --break-system-packages   # arch blocks system pip by default
    # or use a venv:  python -m venv .venv && source .venv/bin/activate
    python3 pinch.py -q "test" -n 3

------------------------------------------------------------------------
LINUX — OPENSUSE (zypper)
------------------------------------------------------------------------
    sudo zypper install python3 python3-pip git
    git clone <your-repo-url>
    cd pinch
    pip3 install --user requests
    python3 pinch.py -q "test" -n 3

------------------------------------------------------------------------
LINUX — ALPINE (apk)  [note: needs the compat package for some wheels]
------------------------------------------------------------------------
    sudo apk add python3 py3-pip git
    git clone <your-repo-url>
    cd pinch
    pip3 install requests
    python3 pinch.py -q "test" -n 3

------------------------------------------------------------------------
LINUX — UNIVERSAL FALLBACK (any distro, if the above fights you)
------------------------------------------------------------------------
every distro converges on this — it always works because the venv is
yours and the distro can't block it:

    python3 -m venv ~/pinch-venv
    source ~/pinch-venv/bin/activate
    pip install requests
    python3 pinch.py -q "test" -n 3
    # each future session:  source ~/pinch-venv/bin/activate

------------------------------------------------------------------------
WINDOWS 10 / 11
------------------------------------------------------------------------
step 1 — install python (pick ONE method):
    a) winget (easiest, open PowerShell or CMD):
         winget install Python.Python.3.12
    b) or download from https://www.python.org/downloads/
       IMPORTANT: during setup, tick "Add python.exe to PATH"
       (it is unchecked by default — this is why "python is not
       recognized" happens to everyone once)

step 2 — close and reopen your terminal, then verify:
    python --version        (should print 3.10 or higher)
    pip --version

step 3 — get pinch.py:
    a) git:    git clone <your-repo-url>
    b) no git: right-click the raw pinch.py on github ->
               "Save link as..." -> save into a folder you make,
               e.g. C:\tools\pinch\

step 4 — install the one dependency:
    pip install requests
    # if it errors about permissions:
    pip install --user requests

step 5 — run it:
    cd C:\tools\pinch
    python pinch.py -q "megan fox 2007" -n 50
    # `py` also works if `python` opens the microsoft store:
    py pinch.py -q "megan fox 2007" -n 50

WINDOWS NOTES
    - zip lands wherever you run it from (or -o path). find it in
      explorer or:  dir *.zip
    - if the store opens instead of python, you installed the stub —
      either click "get" (it installs the real thing) or redo step 1b
      with the PATH checkbox ticked
    - corporate laptops may block pip/requests downloads — try a
      personal machine before fighting the proxy

------------------------------------------------------------------------
DOWNLOADING JUST THE FILES (no git)
------------------------------------------------------------------------
with git (any platform):
    git clone <your-repo-url>
    cd pinch

without git — curl/wget the raw file:
    linux:   curl -LO <raw-url>/pinch.py
             curl -LO <raw-url>/pinch.txt
    windows: curl -LO <raw-url>/pinch.py        (curl ships with win10+)
    browser: open pinch.py on github -> "Raw" button -> Ctrl+S

verify you got a working copy before anything else:
    python3 -m py_compile pinch.py      # linux (python on windows)
    python3 -c "import requests"        # silent = installed, traceback = not


========================================================================
HOW IT WORKS
========================================================================
WHAT A RUN LOOKS LIKE (stages)
------------------------------------------------------------------------
[1] warm-up      visits pinterest.com once to pick up session cookies
[2] search       see "SEARCH SOURCES" below — native first, bridge second
[3] download     N parallel workers pull files into a temp dir,
                 showing [done/total] progress per file, dead ones "skipped"
[4] pack         temp dir zipped into <slug>_<timestamp>.zip
[5] cleanup      temp dir deleted automatically (python does it on exit)

SEARCH SOURCES
------------------------------------------------------------------------
the candidate list comes from a two-stage chain. each stage returns
direct image URLs on i.pinimg.com (real pinterest-hosted files).

SOURCE 1: NATIVE PINTEREST JSON  (function: collect_native)
    hits https://www.pinterest.com/resource/BaseSearchResource/get/
    with a JSON query payload. this is pinterest's own search — best
    quality (prefers /originals/ sizes), can page deep.
    -> if it answers, it fills the whole request and the bridge never runs.
    -> if pinterest returns 403/404/410 (bot wall / ip block), the
       Blocked exception fires IMMEDIATELY — no retries, no waiting —
       and we move to source 2. this is by design: don't burn 30 seconds
       retrying a wall.

SOURCE 2: BING BRIDGE  (functions: collect_bridge, bing_page)
    bing image search, query worded as "<your query> pinterest", walked
    through pagination via the `first=` parameter (35 results per page,
    stalls out after 4 empty pages). results are filtered hard:
    only murl values starting with https://i.pinimg.com/ with an image
    extension survive. query variants tried in order:
        "<q> pinterest"  ->  "<q> pinterest board"  ->  "<q> pin"
    this is the source that works from datacenter/walled IPs — it was
    the one that delivered the verified 50/50 run.

the chain merges both, dedupes by URL, trims to count.

DOWNLOAD LAYER
------------------------------------------------------------------------
collect_urls() hands its list to a ThreadPoolExecutor (8 workers):

  * url_variants(): if a url contains a thumbnail size path
    (/736x/ /564x/ /474x/ /236x/ /1200x/), it first tries swapping in
    /originals/ — same hash path, usually the full-res file. if that
    404s or errors, it falls back to the url as given. bing mostly
    serves /736x/, so this is where the quality upgrade happens.

  * fetch_bytes(): streams the file, decides the extension from the
    Content-Type header first (image/jpeg -> .jpg, image/png -> .png,
    image/gif, image/webp) and falls back to the url suffix
    (.jpg/.jpeg/.png/.gif/.webp). rejects anything under 8 KB or over
    40 MB — those are tracking pixels / broken files, not pins.

  * download_one(): up to 3 retries with backoff per url. success ->
    pin_0001.jpg naming, zero-padded, sorted order in the zip.

  * skip logic: a failed url just prints "skipped" and the run
    continues — one dead pin never kills a batch.

PACKAGING
------------------------------------------------------------------------
everything lands in tempfile.TemporaryDirectory(prefix="pinch_").
after downloads finish, all files go into a ZIP_DEFLATED archive named:

    <slugified query>_<YYYYMMDD_HHMMSS>.zip

slugify: lowercase, non-alphanumerics -> underscore, "megan fox 2007"
-> megan_fox_2007. timestamp means reruns never overwrite. the temp
dir is destroyed when the script exits whether the run succeeded or
not — nothing is left on disk except the zip.

VERIFIED BEHAVIOR (2026-10-07)
------------------------------------------------------------------------
run:  python3 pinch.py -q "megan fox 2007" -n 50
    - 50/50 files downloaded, 0 skipped
    - zip 8.1 MB, 50 entries, zipfile.testzip() -> None (clean)
    - every file signature checked: ff d8 ff (real JPEG), no html
      error pages masquerading as images
    - temp dir gone after exit


========================================================================
TROUBLESHOOTING
========================================================================
"python: command not found" / "python3 is not recognized"
    -> install skipped or PATH missing. linux: `sudo apt install
       python3`. windows: rerun the python.org installer and tick
       "Add python.exe to PATH".

"error: externally-managed-environment" (pip refuses)
    -> distros protect system python. use one of:
       pip3 install requests --break-system-packages
       OR the venv path (see UNIVERSAL FALLBACK above) — prefer venv.

"no module named requests"
    -> dependency not installed yet: pip3 install requests (linux)
       or pip install requests (windows). multiple pythons installed?
       use the same word to run as you used to install:
       `python -m pip install requests` then `python pinch.py`.

"no results from any source"
    -> pinterest AND bing both refused. usually a transient rate
       limit. wait 1-2 minutes, retry. if it persists, your ip is
       likely flagged — try a different network.

"[-] every download failed"
    -> search worked, CDN refused. rare; i.pinimg.com blocks almost
       nothing. check connectivity, retry.

zip has fewer images than asked
    -> the bridge dried up (bing stops paginating around 10-12 pages,
       ~100-150 unique pinimg urls per query). ask for fewer, or use
       a more specific/generic query — vague pop-culture queries
       return deeper results than rare ones.

slow search phase
    -> native source is being retried against a wall, or bing is
       rate-limiting (SLEEP between pages). see "tuning" below.

403s everywhere from a corporate/school network
    -> outbound filtering. run it from home or a different network.


========================================================================
HOW TO UPDATE IT IN THE FUTURE
========================================================================
everything worth touching lives in four places. find them by name:

1. THE SEARCH IS BROKEN / WANT A NEW SOURCE
   -> add a function that returns list[str] of direct image urls:
        def collect_newsource(session, query, count, quiet) -> list[str]
   -> hook it into collect_urls(): native -> bridge -> yours,
      or replace a dead stage with it.
   -> rule for every source: return DIRECT file urls (something
      ending in .jpg/.png/etc). page until `count` or until results
      repeat themselves. raise Blocked on a hard refusal so the chain
      moves on fast instead of hanging.

   candidate sources if both current ones die:
       - yandex images (murl-like json in its html, usually
         friendlier to scripts)
       - duckduckgo i.js (needs a vqd token scraped from duckduckgo.com
         first; currently 403s from this machine — worth retesting
         from a residential ip)
       - a headless browser via playwright rendering the real
         pinterest search page — heavyweight last resort, but it
         defeats client-side challenges nothing else does

2. PINTEREST CHANGES ITS JSON PAYLOAD
   -> the native parser reads:
        resource_response.data.results[].images.{orig,original,1200x,
        736x,564x,474x}.url
      if pinterest renames those keys, fix IMAGE_PREF (the size
      priority list) and the loop in search_native_page().

3. BING CHANGES ITS MARKUP
   -> bing_page() scrapes m=" JSON attributes out of the html:
        re.findall(r'm="(\{[^"]+\})"', text)
      then reads item["murl"]. if bing renames the attribute or the
      key, open one search page in a browser, view source, find where
      the full-size url (murl) hides now, update the regex/key.
      that's the single most likely thing to break over time.

4. TUNING CONSTANTS (top of file)
       WORKERS       parallel downloads (raise to 12 on fast lines,
                     lower to 3-4 if you start getting skips)
       SLEEP         seconds between search pages — raise if rate-
                     limited, lower to 0.2 if you're patient-proof
       MIN_BYTES     8 KB floor for real files, raise to 32 KB if
                     you want to filter out more junk
       BING_STALL    empty pages tolerated before giving up on a
                     query variant
       IMAGE_PREF    size preference order for native source
       MAX_RETRIES   download retries per file

HOW TO TEST A CHANGE
------------------------------------------------------------------------
always verify against a real run, not just syntax:

    python3 -m py_compile pinch.py                  # syntax
    python3 pinch.py -q "megan fox 2007" -n 5       # smoke test, ~30s

then audit the zip:

    unzip -l <zip>            # entry count matches -n?
    unzip -t <zip>            # integrity check
    file $(unzip -Z1 <zip> | head -3)   # real images, not html
    # windows:   tar -tf <zip>   or   python -m zipfile -l <zip>

a change is only done when a fresh run produces a clean zip whose
entry count matches the requested count (or is short by exactly the
"skipped" lines you saw — skips are honest, silent gaps are bugs).

IDEAS FOR FUTURE VERSIONS (not built yet)
------------------------------------------------------------------------
    -j / --json     dump candidate urls to a file instead of zipping
    --any-site      drop the i.pinimg.com filter (bridge returns any
                    host, useful when you want "the image" not
                    "the pinterest copy")
    resume          remember fetched urls in <slug>.seen next to the
                    zip so a second run adds 50 NEW images instead
                    of overlapping
    contact sheet   optionally build one preview grid image from the
                    batch using pillow (would add pillow as a second
                    dep — keep it optional)

========================================================================
tl;dr:
  linux:    python3 -m venv venv && source venv/bin/activate
            pip install requests && python3 pinch.py
  windows:  pip install requests && python pinch.py
  broken search? fix the source function. broken bing? fix one regex.
  everything else is a constant at the top of the file.
========================================================================
