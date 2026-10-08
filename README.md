# Pinch

Pinterest image grabber that zips the results.

Give it a query, tell it how many, get a zip. Downloads go to a temp folder that cleans itself up, so the zip is the only thing left behind.

```console
$ python3 pinch.py
search query: megan fox 2007
how many images? [50]: 50
[+] zip ready: megan_fox_2007_20261007_171125.zip (50 images)
```

## Install

You need **Python 3.10+** and one package: `requests`.

**Linux**

```bash
sudo apt install python3 python3-pip git     # debian/ubuntu (dnf/pacman/zypper on others)
git clone <your-repo-url> && cd pinch
pip3 install requests
```

If pip complains about `externally-managed-environment`, either add `--break-system-packages` or use a venv:

```bash
python3 -m venv venv && source venv/bin/activate
pip install requests
```

**Windows**

1. Install Python from [python.org](https://www.python.org/downloads/) and tick **"Add python.exe to PATH"** (or `winget install Python.Python.3.12`).
2. Open a new terminal:

```powershell
git clone <your-repo-url>     # or grab pinch.py via the Raw button
cd pinch
pip install requests
```

No git? Just open `pinch.py`, hit **Raw**, and save it somewhere.

## Usage

```bash
python3 pinch.py                                      # asks you for query + count
python3 pinch.py -q "megan fox 2007" -n 50            # skip the prompts
python3 pinch.py -q "cyberpunk city" -n 100 -o ~/zips # pick the output folder
```

| Flag | What it does | Default |
|------|--------------|---------|
| `-q`, `--query` | search query | prompted |
| `-n`, `--count` | how many images (1â€“2000) | `50` |
| `-o`, `--out` | where the zip lands | current folder |

The zip is named after your query plus a timestamp (`megan_fox_2007_20261007_171125.zip`), so reruns never overwrite each other.

## How it works

It searches Pinterest directly, and if Pinterest blocks your IP (it likes to), it falls back to pulling Pinterest-hosted images through Bing. The files download in parallel into a temp folder, get zipped, and the temp folder is deleted. That's the whole thing.

Want the details? Read `pinch.py`, or see `pinch.txt` for full docs.

## Troubleshooting

- **`externally-managed-environment`** â†’ use a venv, or `--break-system-packages`
- **`No module named requests`** â†’ `pip install requests` with the same python you run the script with
- **`no results from any source`** â†’ rate-limited. Wait a minute and retry
- **Fewer images than asked** â†’ Bing runs dry around 100â€“150 per query. Ask for less
