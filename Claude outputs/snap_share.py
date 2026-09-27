"""snap_share.py — who is actually on the field, for every IDP on the board.

WHY THIS AND NOT PRODUCTION. Tackles, sacks and the per-game bonus thresholds
all price what a defender DID. Snap share prices whether he was out there to do
it, and the two come apart in exactly the case that costs you a pick: a
rotational player whose per-snap rate looks fine and whose season totals never
arrive, and a three-down player on a bad defence whose totals look ordinary
because his team was never on the field.

It also answers the question 2025 production cannot. Devin Lloyd recorded ZERO
qualifying bonus games in fifteen played, which reads as a dead player -- until
you notice he changed teams. If his 2025 snap share was rotational and his 2026
job is every-down, the zero measures a role he no longer has. Snap share is how
you tell those apart before spending a pick on the guess.

NO NETWORK. Reads the 2025 week-by-week lines bonus_audit.py already cached and
the board bonus_adjust.py already wrote. Run bonus_audit.py once first if
~/.sleeper_cache/weekstats_2025.json is missing.

    python snap_share.py                 # every IDP on the board, by position
    python snap_share.py --pos DL
    python snap_share.py --min 0         # include players with no 2025 snaps
    python snap_share.py --csv out.csv

READ THE LAST5 COLUMN, NOT THE MEAN. A player benched in September and starting
by December has a mean that describes neither. The gap between mean and last5
is the trend, and trend is what carries into next season.
"""
import csv
import json
import os
import statistics
import sys

CACHE = next((c for c in (os.path.expanduser('~/.sleeper_cache'),
                          os.path.expanduser('~/mnt/.sleeper_cache'))
              if os.path.isdir(c)), None)
HERE = os.path.dirname(os.path.abspath(__file__))
IDP = ('DL', 'LB', 'DB')


def find_board():
    for rel in (('board_adj_rate.json',), ('board_adj.json',), ('board.json',),
                (os.pardir, 'fz', 'board_adj_rate.json')):
        p = os.path.join(HERE, *rel)
        if os.path.exists(p):
            return p, json.load(open(p, encoding='utf-8'))
    raise SystemExit('no board json found beside this script')


def snap_keys(hist):
    """Discover the snap fields rather than assuming their names. Sleeper has
    changed stat vocabulary before and a hard-coded key that silently misses is
    worse than a loud failure."""
    seen = set()
    for wk in hist.values():
        for line in wk.values():
            seen |= {k for k in line if 'snp' in k or 'snap' in k}
        if seen:
            break
    player = next((k for k in ('def_snp', 'def_snaps', 'snp_def') if k in seen), None)
    team = next((k for k in ('tm_def_snp', 'team_def_snp', 'tm_def_snaps')
                 if k in seen), None)
    return player, team, sorted(seen)


def main(argv):
    posf = argv[argv.index('--pos') + 1].upper() if '--pos' in argv else None
    floor = float(argv[argv.index('--min') + 1]) if '--min' in argv else 1
    if CACHE is None:
        raise SystemExit('no .sleeper_cache found')
    hp = os.path.join(CACHE, 'weekstats_2025.json')
    if not os.path.exists(hp):
        raise SystemExit(f'{hp} missing -- run bonus_audit.py once to cache it')
    hist = json.load(open(hp, encoding='utf-8'))
    bpath, board = find_board()

    pk, tk, allsnap = snap_keys(hist)
    print(f'board: {os.path.basename(bpath)}   snap fields seen: '
          f'{", ".join(allsnap) or "NONE"}')
    if not pk:
        raise SystemExit('no per-player snap field in the cache -- nothing to do')
    print(f'using player={pk}' + (f', team={tk}' if tk else
          ', NO team-snap field: reporting raw snaps, not share') + '\n')

    rows = []
    for pid, p in board.items():
        if p['pos'] not in IDP or (posf and p['pos'] != posf):
            continue
        shares, snaps = [], []
        for w in sorted(hist, key=int):
            line = (hist[w] or {}).get(pid)
            if not line:
                continue
            s = line.get(pk)
            if s is None:
                continue
            snaps.append(float(s))
            t = float(line.get(tk) or 0) if tk else 0.0
            if t > 0:
                shares.append(100.0 * float(s) / t)
        if len(snaps) < floor:
            continue
        rows.append({
            'name': p['name'], 'pos': p['pos'], 'team': p['team'] or '',
            'vorp': p['vorp'], 'raw': p.get('vorp_raw'),
            'adp': p['adp'] if p['adp'] < 400 else None,
            'bonus': p.get('bonus_2025') or 0, 'g': len(snaps),
            'mean': statistics.mean(shares) if shares else None,
            'last5': statistics.mean(shares[-5:]) if shares else None,
            'hi': max(shares) if shares else None,
            'snaps': sum(snaps), 'inj': p.get('inj') or ''})

    if '--csv' in argv:
        dest = argv[argv.index('--csv') + 1]
        with open(dest, 'w', newline='', encoding='utf-8') as f:
            w = csv.DictWriter(f, fieldnames=list(rows[0]))
            w.writeheader(); w.writerows(rows)
        print(f'-> {dest}  ({len(rows)} players)')

    for pos in ([posf] if posf else IDP):
        sel = [r for r in rows if r['pos'] == pos]
        sel.sort(key=lambda r: -(r['last5'] if r['last5'] is not None else -1))
        print(f'\n=== {pos} — {len(sel)} with 2025 snaps, sorted by LAST-5 share ===')
        print(f"{'snap%':>6} {'last5':>6} {'peak':>6} {'g':>3} {'value':>7} "
              f"{'adp':>6} {'bonus':>6}  player")
        for r in sel:
            f2 = lambda v: f'{v:.0f}' if v is not None else '  -'
            flag = ''
            if r['last5'] is not None and r['mean'] is not None:
                if r['last5'] - r['mean'] >= 12:
                    flag = '   <-- ROLE GREW late in the year'
                elif r['mean'] - r['last5'] >= 12:
                    flag = '   <-- role SHRANK'
            if r['last5'] is not None and r['last5'] >= 75 and not r['bonus']:
                flag = '   <-- every-down and still no bonus game: volume without production'
            if r['last5'] is not None and r['last5'] < 45 and r['vorp'] > 15:
                flag = '   <-- priced as a starter, snapped like a rotation'
            print(f"{f2(r['mean']):>6} {f2(r['last5']):>6} {f2(r['hi']):>6} {r['g']:>3} "
                  f"{r['vorp']:>7.1f} {f2(r['adp']):>6} {r['bonus']:>6.0f}  "
                  f"{r['name']} ({r['team']}) {r['inj']}{flag}")

    print('\nCAVEAT: 2025 snaps, 2026 roles. A player who changed team or scheme '
          'carries his old usage here, which is the whole reason to read it '
          'beside the value column rather than instead of it.')


if __name__ == '__main__':
    main(sys.argv[1:])
