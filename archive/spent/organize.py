"""
organize.py — put per-league material where it belongs, and keep it there.

    python organize.py --check      # report only, exit 1 if anything is out of place
    python organize.py --dry-run    # show what it would move
    python organize.py              # move it

Run it whenever you like. It is idempotent — that is the whole point.

WHY THIS EXISTS. migrate.py sorted this repo on the morning of 8/13.
By that evening `lg05_brief.md` and `lg05_emoji_brief.md` were
back at the root as SECOND copies, shadowing the ones in leagues/, and
`idp_brief.md` had been written to the root because
`leagues/lg06/` had never been created — the folder list in
migrate.py was a one-time constant and a league had been added since.

Two documents each claiming to be the draft card for a draft five days
out is the 8/11 failure wearing a different hat: nothing was broken,
and the sentence on top was wrong.

The lesson is not "sort it again." A sort is a snapshot. Folders do not
hold; rules do. paths.py survived the same six hours untouched because
code calls it on every write. leagues/ did not, because nothing did.
So this file is a rule, smoke.py runs `--check` on every pass, and the
league folders are generated from leagues/_index.json rather than a
list somebody has to remember to update.

Placement rules, all derived from _index.json:

    leagues/<slug>/            exists for every league in the index
    leagues/<slug>/brief.md    the ONLY home for a league's draft card
    root                       no *_brief.md, ever

When both a root brief and a leagues/ brief exist, the NEWER one by
mtime wins and the older is kept in archive/superseded/ with a stamp.
Nothing is deleted.
"""

import datetime
import io
import json
import os
import pathlib
import re
import shutil
import subprocess
import sys

import paths

CHECK = "--check" in sys.argv
DRY = "--dry-run" in sys.argv
REPO = paths.REPO

C_OK, C_BAD, C_WARN, C_DIM, C_END = (
    "\033[32m", "\033[31m", "\033[33m", "\033[90m", "\033[0m")
if os.name == "nt" and not os.environ.get("WT_SESSION"):
    try:
        import ctypes
        ctypes.windll.kernel32.SetConsoleMode(
            ctypes.windll.kernel32.GetStdHandle(-11), 7)
    except Exception:
        C_OK = C_BAD = C_WARN = C_DIM = C_END = ""

problems = []
actions = []


def slug_from_filename(stem):
    """'lg05_emoji_brief' -> the lg05-emoji slug, via _index aliases.

    Underscores become hyphens first: paths._norm drops underscores
    entirely, so 'lg05_emoji' would normalize to 'hybrid12emoji' and
    match nothing.
    """
    base = re.sub(r"[_\s-]*brief$", "", stem).replace("_", "-")
    lid = paths.id_for(base)
    return paths.slug_for(lid) if lid else None


def git_mv(src, dst):
    dst.parent.mkdir(parents=True, exist_ok=True)
    r = subprocess.run(["git", "mv", str(src.relative_to(REPO)),
                        str(dst.relative_to(REPO))],
                       cwd=str(REPO), capture_output=True, text=True)
    if r.returncode != 0:
        shutil.move(str(src), str(dst))


def stamp(p):
    t = datetime.datetime.fromtimestamp(p.stat().st_mtime)
    return t.strftime("%Y%m%d-%H%M")


def main():
    lgs = paths.leagues()
    if not lgs:
        sys.exit("leagues/_index.json is missing or empty — nothing to key on.")

    print(f"\n{len(lgs)} leagues in the index: {', '.join(lgs)}")

    # ---- 1. a folder for every league, generated from the index
    print("\nleague folders:")
    for slug in lgs:
        d = paths.LEAGUES / slug
        if d.is_dir():
            print(f"  {C_DIM}ok{C_END}     {slug}/")
            continue
        problems.append(f"leagues/{slug}/ does not exist")
        actions.append(f"mkdir leagues/{slug}/")
        print(f"  {C_WARN}create{C_END} leagues/{slug}/")
        if not (CHECK or DRY):
            d.mkdir(parents=True, exist_ok=True)
            (d / ".gitkeep").touch()

    # ---- 2. no brief at the repo root
    print("\nbriefs:")
    # Only a file that RESOLVES to a league in the index is a stray league
    # brief. design_brief.md ends in "brief" too and is a document about the
    # dashboard's visual design — a rule that cannot tell those apart would
    # fire on the majority of a correct repo, and a warning that fires on
    # everything is noise (CLAUDE.md, on the THIN flag).
    candidates = sorted(p for p in REPO.glob("*.md")
                        if re.search(r"_?brief$", p.stem, re.I))
    strays = [p for p in candidates if slug_from_filename(p.stem)]
    unmatched = [p for p in candidates if p not in strays]
    for p in strays:
        slug = slug_from_filename(p.stem)
        dest = paths.LEAGUES / slug / "brief.md"
        if not dest.exists():
            problems.append(f"{p.name} belongs at leagues/{slug}/brief.md")
            actions.append(f"{p.name} -> leagues/{slug}/brief.md")
            print(f"  {C_WARN}move{C_END}   {p.name} -> leagues/{slug}/brief.md")
            if not (CHECK or DRY):
                git_mv(p, dest)
            continue

        # both exist: newer wins, older is kept
        root_newer = p.stat().st_mtime > dest.stat().st_mtime
        keep, drop = (p, dest) if root_newer else (dest, p)
        older = paths.ARCHIVE / "superseded" / f"{slug}-brief-{stamp(drop)}.md"
        problems.append(
            f"two copies of the {slug} brief: {p.name} "
            f"({p.stat().st_size} b, {stamp(p)}) and "
            f"leagues/{slug}/brief.md ({dest.stat().st_size} b, {stamp(dest)})")
        print(f"  {C_BAD}XX{C_END}     {slug}: TWO copies")
        print(f"           root      {p.stat().st_size:>7} b  {stamp(p)}"
              + ("   <- newer" if root_newer else ""))
        print(f"           leagues/  {dest.stat().st_size:>7} b  {stamp(dest)}"
              + ("" if root_newer else "   <- newer"))
        actions.append(f"keep {'root' if root_newer else 'leagues/'} copy as "
                       f"leagues/{slug}/brief.md; "
                       f"archive the other as {older.name}")
        print(f"           keep the newer, archive the other as "
              f"archive/superseded/{older.name}")
        if not (CHECK or DRY):
            older.parent.mkdir(parents=True, exist_ok=True)
            if root_newer:
                git_mv(dest, older)
                git_mv(p, dest)
            else:
                git_mv(p, older)

    if not strays:
        print(f"  {C_DIM}ok{C_END}     no league brief at the repo root")
    for p in unmatched:
        print(f"  {C_DIM}--{C_END}     {p.name}: ends in 'brief' but matches no "
              f"league — treated as an ordinary document")

    # ---- 3. every league folder's brief is where the index says
    print("\nindex vs disk:")
    for slug in lgs:
        b = paths.LEAGUES / slug / "brief.md"
        mark = f"{C_OK}has brief{C_END}" if b.exists() else f"{C_DIM}none{C_END}"
        print(f"  {slug:18s} {mark}")

    # ---- 4. soft report: loose material at the root
    known_md = {"README.md", "CLAUDE.md", "HANDOFF.md", "DECISIONS.md",
                "ROADMAP.md", "CHANGELOG.md", "DEPENDENCIES.md", "roster.md"}
    loose = sorted(p.name for p in REPO.glob("*.md")
                   if p.name not in known_md and p not in strays)
    loose = [n for n in loose if n not in {x.name for x in strays}]
    if loose:
        print(f"\n{C_WARN}loose .md at the root (not an error, but decide "
              f"where they live):{C_END}")
        for n in loose:
            print(f"    {n}")

    # ---- verdict
    print(f"\n{'-' * 62}")
    if not problems:
        print(f"{C_OK}organized{C_END} — every league has a folder and every "
              f"brief is in it")
        return 0
    if CHECK:
        print(f"{C_BAD}{len(problems)} placement problem(s){C_END}")
        for p in problems:
            print(f"  - {p}")
        print("\nRun `python organize.py` to fix.")
        return 1
    if DRY:
        print(f"{len(actions)} action(s) — rerun without --dry-run to apply")
        return 0
    print(f"{C_OK}fixed {len(actions)} thing(s){C_END}")
    for a in actions:
        print(f"  - {a}")
    print("\nNothing was deleted. Superseded copies are in "
          "archive/superseded/.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
