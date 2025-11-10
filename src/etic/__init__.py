__doc__ ="""
Download '.bib'-ready citations from DOI.

Usage:
    etic <DOI>

Options:
    -h --help Print this message.

"""

__version__ = '0.1.12'

from docopt import docopt
from pathlib import Path

from os import environ, makedirs
import sys

from aiohttp import ClientSession, ClientError
import aiofiles
import asyncio

import gzip
import datetime
import bibtexparser
import re

from dataclasses import dataclass

from typing import Dict, Any, List, Optional, Union, AnyStr, TypeAlias, TypedDict

Url: TypeAlias = Union[Path, AnyStr]

class Configuration:
    month_regex: AnyStr
    latest_issn: Url
    issn_upd: AnyStr
    url_base: Url
    headers: Dict
    
    def __init__(self, config_path: Url) -> None:
        from yaml import load, Loader
        with open(config_path, 'r') as ycfg:
            data = load(ycfg, Loader=Loader)
            self.month_regex = data['MONTH_REGEX']
            self.latest_issn = data['LATEST_ISSN']
            self.issn_upd = datetime.date(*tuple(int(val) for val in data['ISSN_UPD'].split('-')))
            self.url_base = data.get('URL_BASE', 'https://dx.doi.org/')
            self.headers = {'Accept': data.get('HEADERS', "text/x-bibliography;style=bibtex")}
  
@dataclass
class Result:
    success: bool
    data: Union[Any, None] = None
    error: Optional[Union[Any, AnyStr]] = None
  
__IGNORELIST = [
    "of", "and", "in", "at", "on", "the", "&",
    "für", "ab", "um"
]  

def unix_data_home() -> Url:
    try:
        return Url(environ['XDG_DATA_HOME'])
    except KeyError:
        return Url(environ['HOME']) / '.local' / 'share'

def windows_data_home() -> Url:
    return Url(environ['APPDATA'])

def darwin_data_home():
    return Path(environ['HOME']) / 'Library' / 'Application Support'

def key_from_phrase(title):
    return "".join([x[0] for x in title.split()]).strip().lower()

def data_home(folder: Optional[Url] = None) -> Url:
    platform = sys.platform

    if platform == 'win32':
        data_dir = windows_data_home()
    elif platform == 'darwin':
        data_dir = darwin_data_home()
    else:
        data_dir = unix_data_home()

    if folder is None:
        return data_dir
    else:
        return data_dir / folder

async def dl_abbrev(fname='abbrev.txt.gz', url: Url = None) -> None:
    directory = data_home('etic')
    makedirs(directory, exist_ok=True)

    async with ClientSession() as session:
        async with session.get(url) as response:
            if response.status != 200:
                raise Exception(f"Failed to download: {response.status}")
            data = await response.read()

    output_path = directory / fname
    async with aiofiles.open(output_path, 'wb') as f:
        await f.write(data)

async def load_abbrev(fname: Url = None, cfg: Optional[Configuration] = None) -> Result:
    """
    Loads the abbreviation database
    """
    # Define target file path using pathlib
    target = data_home('etic') / fname

    # Check if abbreviation file exists or is outdated
    if not target.is_file():
        print(f"{target} not found; downloading...", file=sys.stderr)
        await dl_abbrev(fname, cfg.latest_issn)
    else:
        # Check for outdated abbreviation list only if the file exists
        mtime = datetime.date.fromtimestamp(target.stat().st_mtime)
        if mtime <= cfg.issn_upd:
            print(f"{target} is out of date; redownloading...", file=sys.stderr)
            await dl_abbrev(fname, cfg.latest_issn)

    # Load the abbreviations database into memory efficiently
    data: Dict = {}
    try:
        with gzip.open(target, 'rt', encoding="utf-16") as f:
            for line in f:
                # Skip lines starting with 'WORD'
                if line.startswith('WORD'):
                    continue
                # Process valid data lines
                parts = line.strip().split("\t")
                if len(parts) >= 3:
                    jname = parts[0].strip()
                    jabbrev = parts[1].strip()
                    # Only add valid entries (e.g., skip malformed lines)
                    if jname and jabbrev:
                        langs = parts[2].split(", ")  # Could use langs if necessary
                        data[jname.lower()] = jabbrev.lower()
        return Result(success=True, data=data)
    except Exception as e:
        return Result(success=False, error=f'{e}')

async def journal_abbrev(name: AnyStr, cfg: Optional[Configuration] = None) -> Result:
    """
    Abbreviates a journal title
    """
    result = await load_abbrev("abbrev.txt.gz", cfg)
    if not result.success:
        return Result(success=True, data=name, error=f"Warning: Abbreviation data could not be loaded: {result.error}")

    data = result.data
    n_abbrev = []

    (name, _, _) = name.partition(":")
    parts = re.split("\s+", name)

    if len(parts) == 1 and len(parts[0]) < 12:
        return Result(success=True, data=name)
    for word in parts:
        # Do not abbreviate wordsin the IGNORELIST
        if word.lower() in __IGNORELIST:
            continue
        for (k,v) in data.items():
            found = False

            # If the key ends with - it means we are checking for a prefix
            if k.endswith("-"):
                if word.lower().startswith(k[:-1]):
                    if v != "n.a.":
                        n_abbrev.append(v.capitalize())
                    else:
                        n_abbrev.append(word.lower().capitalize())
                    found = True
                    break
            # Else we are checking for a whole match
            else:
                if word.lower() == k:
                    if v != "n.a.":
                        n_abbrev.append(v.capitalize())
                    else:
                        n_abbrev.append(word.lower().capitalize())
                    found = True
                    break

        if not found:
            # If all characters are uppercase leave as is
            if not word.isupper():
                n_abbrev.append(word.capitalize())
            else:
                n_abbrev.append(word)
    return Result(success=True, data=" ".join(n_abbrev))

async def get_entry(doi: Url, cfg: Optional[Configuration] = None) -> Result:
    """
    Asynchronously fetches and processes a BibTeX entry for the given DOI.
    - Abbreviates journal name
    - Normalizes month field
    - Adds 'shortjournal' and BibTeX 'ID'
    """
    if 'https://' in doi:
        print("Warning: Full URL provided; using as is.", file=sys.stdwerr)
        url: Url = doi
    else:
        url: Url = cfg.url_base + f"{doi}"
    headers: Dict = cfg.headers
    
    try:
        async with ClientSession() as session:
            async with session.get(url, headers=headers, timeout=2) as response:
                if response.status != 200:
                    return f"Failed to fetch entry: HTTP {response.status}"
                content = await response.text()
    except ClientError as e:
        return Result(success=False, error=f"Network error: {e}")
    except asyncio.TimeoutError:
        return Result(success=False, error="Request timed out.")

    try:
        bib_data = bibtexparser.loads(content)
        entry = bib_data.entries[0]
    except Exception as e:
        return Result(success=False, error=f"Error parsing BibTeX data: {e}")

    # Abbreviate journal title
    journal = entry.get("journal")
    if journal:
        jabbr = await journal_abbrev(journal, cfg)
        if jabbr.success:
            jabbr = jabbr.data
        else: return jabbr
        if jabbr != journal:
            entry["shortjournal"] = jabbr

    # Normalize month to 3-letter lowercase
    if "month" in entry:
        entry["month"] = entry["month"].lower()[:3]

    # Generate BibTeX ID
    try:
        authors = entry.get("author", "").split(" and ")
        first_author = authors[0].split(",")[0] if authors else "unknown"
        year = entry.get("year", "xxxx")

        if "shortjournal" in entry:
            suffix = key_from_phrase(entry["shortjournal"])
        elif "journal" in entry:
            suffix = key_from_phrase(entry["journal"])
        elif "publisher" in entry:
            suffix = key_from_phrase(entry["publisher"])
        else:
            suffix = ""

        entry["ID"] = f"{first_author}{year}{suffix}"
    except Exception as e:
        return Result(success=False, error=f"Warning: could not generate ID: {e}")

    # Format the BibTeX and normalize the month line
    raw_result = bibtexparser.dumps(bib_data).strip()
    cleaned_lines = []

    MONTH_REGEX = re.compile(cfg.month_regex)
    for line in raw_result.splitlines():
        match = MONTH_REGEX.match(line)
        if match:
            month_str = match.group(1).lower()[:3]
            line = f"  month = {month_str}," if line.strip().endswith(",") else f"  month = {month_str}"
        cleaned_lines.append(line)

    return Result(success=True, data="\n".join(cleaned_lines))

def main() -> None:
    args = docopt(__doc__, version='etic v{__version__}')
    cfg_path = Path(Path(__file__).parent / 'config.yml')
    cfg = None
    if cfg_path.is_file():
        cfg = Configuration(cfg_path)
    else:
        print(f'No file was found: {cfg_path}', file=sys.stderr)
        sys.exit(0)
    doi = args.get('<DOI>', None)
    result = asyncio.run(get_entry(doi, cfg))
    if result.success:
        data = result.data
        print(data)
        sys.exit(0)
    print(result.error, file=sys.stderr)
    sys.exit(1)
    
    