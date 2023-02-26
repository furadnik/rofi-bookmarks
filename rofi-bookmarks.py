#!/usr/bin/env python3
"""Get bookmarks from firefox and print them in rofi readable format."""
from typing import Iterator
from functools import partial
import sqlite3
import subprocess
from argparse import ArgumentParser
from configparser import ConfigParser
from os import environ
from pathlib import Path
from hashlib import sha256
from contextlib import closing, contextmanager, suppress
from tempfile import NamedTemporaryFile
from shutil import copyfile

cache_dir = Path(environ.get('XDG_CACHE_HOME', Path.home() / '.cache')) / 'rofi-bookmarks'
firefox_dir = Path.home() / '.mozilla/firefox'


def title_gen_full_path(path: Iterator[str], separator=' / ') -> str:
    """Generate full path."""
    return separator.join(filter(lambda x: x is not None, path))


def title_gen_only_name(path: Iterator[str]) -> str:
    """Generate full path."""
    return list(filter(lambda x: x is not None, path))[-1]


@contextmanager
def temp_sqlite(path: Path | str) -> sqlite3.Connection:
    """Copy sqlite database to temporary location and connect to it there."""
    with NamedTemporaryFile() as temp_loc:
        copyfile(path, temp_loc.name)
        with closing(sqlite3.connect(temp_loc.name)) as conn:
            yield conn


@contextmanager
def favicons_generator(profile_path: Path):
    """Return generator for favicons."""
    with temp_sqlite(profile_path / 'favicons.sqlite') as favicons:
        yield favicons


def default_profile_path() -> Path:
    """Get first firefox profile."""
    installs = ConfigParser()
    installs.read(firefox_dir / 'installs.ini')
    for i in installs.values():
        with suppress(KeyError):
            return firefox_dir / i['Default']
    raise Exception("could not find a default profile in installs.ini")


def path_from_name(name: str) -> Path:
    """Get path of profile with given name."""
    profiles = ConfigParser()
    profiles.read(firefox_dir / 'profiles.ini')
    for i in profiles.values():
        with suppress(KeyError):
            if i['Name'] == name:
                return firefox_dir / i['Path']
    raise Exception("no profile with this name")


def cache_icon(icon: str) -> Path:
    """Add icon to cache."""
    loc = cache_dir / sha256(icon).hexdigest()
    if not cache_dir.exists():
        cache_dir.mkdir()
    if not loc.exists():
        loc.write_bytes(icon)
    return loc

# main function, finds all bookmaks inside of search_path and their corresponding icons and prints them in a rofi readable form


def get_bookmarks_from_db(profile_loc: Path):
    """Get bookmarks from firefox database."""
    with temp_sqlite(profile_loc / 'places.sqlite') as places:
        return places.execute("""SELECT moz_bookmarks.id, moz_bookmarks.parent, moz_bookmarks.type, moz_bookmarks.title, moz_places.url
                                     FROM moz_bookmarks LEFT JOIN moz_places ON moz_bookmarks.fk=moz_places.id
                                  """).fetchall()


def parent_generator(i, by_id):
    """Generate parents."""
    while i > 1:
        title, i = by_id[i]
        yield title


def write_rofi_input(bookmarks, favicons_gen, title_gen, search_path=[]):
    """Write rofi input."""
    by_id = {i: (title, parent) for i, parent, _, title, _ in bookmarks}

    for index, parent, t, title, url in bookmarks:
        if t != 1:  # type one means bookmark
            continue

        path_arr = reversed(list(parent_generator(index, by_id)))

        if all(name == next(path_arr) for name in search_path):
            path = title_gen(path_arr)
            print(f"{path}\x00info\x1f{url}")


if __name__ == "__main__":
    parser = ArgumentParser(description="generate list of bookmarks with icons for rofi")
    parser.add_argument('path', default="", nargs='?', help="restrict list to a bookmark folder")
    parser.add_argument('-s', '--separator', default=" / ", metavar='sep', help="seperator for paths")
    parser.add_argument('-p', '--profile', metavar='prof', help="firefox profile to use")
    args, _ = parser.parse_known_args()   # rofi gives us selected entry as additional argument -> ignore (not useful)

    if environ.get('ROFI_RETV') == '1':
        prof = [] if args.profile is None else ["-P", args.profile]
        subprocess.Popen(["firefox", "-new-window", environ['ROFI_INFO']] + prof,
                         close_fds=True, start_new_session=True, stdout=subprocess.DEVNULL)
    else:
        search_path = [i for i in args.path.split('/') if i != '']
        profile_path = default_profile_path() if args.profile is None else path_from_name(args.profile)

        print("\x00prompt\x1f ")  # change prompt
        # write_rofi_input(get_bookmarks_from_db(profile_path), favicons_generator(profile_path),
        #                  partial(title_gen_full_path, separator=args.separator), search_path=search_path)
        write_rofi_input(get_bookmarks_from_db(profile_path), favicons_generator(profile_path),
                         title_gen_only_name, search_path=search_path)
