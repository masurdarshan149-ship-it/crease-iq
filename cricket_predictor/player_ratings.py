"""Recency-weighted player ratings: an input to the win model since 17 Nov 2026.

For every player, per format: runs and balls faced, dismissals, runs conceded, legal balls bowled and wickets, with
older matches fading (half-life HALF_LIFE days) and every number pulled toward the format's average player until
there is enough evidence (PULL pseudo-balls). From the ticked XI, each side gets four numbers:
  sr   scoring rate of its best 7 batters (runs per ball)
  bpd  log of balls per dismissal of those 7 (staying in)
  ec   runs per ball conceded by the 5 who bowl most
  wk   wickets per ball of those 5
Inputs: prb_* for the side batting first, prc_* for the chasing side.

scripts/player_ratings_experiment.py chose the settings on 2024 and backtested them (17 Nov 2026): better log loss
in 3 of 4 seasons overall and 4 of 4 before the match.

build() reads every men's T20 / ODI match ball by ball in date order and writes:
  data/ml/player_ratings.csv.gz      each match's ratings just before it started (for training and Replay)
  data/ml/player_ratings_state.json  every player's latest totals (for predictions in the app)
"""

from __future__ import annotations

import json
import math
import zipfile
from datetime import date
from pathlib import Path
from typing import Any, Iterable

from .once import locked_cache

ROOT = Path(__file__).resolve().parents[1]
ML_DIR = ROOT / "data" / "ml"
MATCHES_PATH = ML_DIR / "player_ratings.csv.gz"
STATE_PATH = ML_DIR / "player_ratings_state.json"
ARCHIVES = [ROOT / "data" / n for n in ("cricsheet_all_json_full.zip", "cricsheet_ipl.zip", "cricsheet_t20s.zip", "cricsheet_odis.zip")]

HALF_LIFE = 365  # days (chosen on 2024: 1 year beat 2 and 4)
PULL = 60        # pseudo-balls of "average player" (chosen on 2024)
PRIOR = {
    "t20": {"sr": 1.22, "bpd": 21.0, "ec": 1.30, "wk": 0.050},
    "odi": {"sr": 0.84, "bpd": 34.0, "ec": 0.90, "wk": 0.032},
}
COLUMNS = ["prb_sr", "prb_bpd", "prb_ec", "prb_wk", "prc_sr", "prc_bpd", "prc_ec", "prc_wk"]
MONOTONE = {"prb_sr": 1, "prb_bpd": 1, "prb_ec": -1, "prb_wk": 1, "prc_sr": -1, "prc_bpd": -1, "prc_ec": 1, "prc_wk": -1}
# pairs for "even teams" / "what the playing XIs add" (same quantity for the two sides)
PAIRS = [("prb_sr", "prc_sr"), ("prb_bpd", "prc_bpd"), ("prb_ec", "prc_ec"), ("prb_wk", "prc_wk")]
NOT_BOWLERS_WICKET = {"run out", "retired hurt", "retired out", "obstructing the field", "retired not out"}


def _decay(rec: list[float], day: int) -> list[float]:
    f = 0.5 ** ((day - rec[6]) / HALF_LIFE)
    return [v * f for v in rec[:6]]


def side(totals: Iterable[list[float] | None], fam: str) -> tuple[float, float, float, float]:
    """(sr, log bpd, ec, wk) for one XI from each player's decayed totals [runs, balls, outs, conceded, bowled, wickets]."""
    pr = PRIOR.get(fam, PRIOR["t20"])
    k = PULL
    players = []
    for v in list(totals)[:12]:  # 12: the IPL impact player counts as extra depth, as in the other XI inputs
        runs, balls, outs, conc, bowled, wk = v if v else (0.0,) * 6
        players.append({"sr": (runs + k * pr["sr"]) / (balls + k), "bpd": (balls + k) / (outs + k / pr["bpd"]),
                        "ec": (conc + k * pr["ec"]) / (bowled + k), "wk": (wk + k * pr["wk"]) / (bowled + k), "bowled": bowled})
    while len(players) < 11:
        players.append({"sr": pr["sr"], "bpd": pr["bpd"], "ec": pr["ec"], "wk": pr["wk"], "bowled": 0.0})
    bats = sorted(players, key=lambda p: p["sr"] * p["bpd"], reverse=True)[:7]
    bowls = sorted(players, key=lambda p: p["bowled"], reverse=True)[:5]
    return (round(sum(p["sr"] for p in bats) / 7, 5), round(math.log(sum(p["bpd"] for p in bats) / 7), 5),
            round(sum(p["ec"] for p in bowls) / 5, 5), round(sum(p["wk"] for p in bowls) / 5, 5))


def neutral(fam: str) -> dict[str, float]:
    """The inputs for two sides of average, unknown players (used if a match has no ratings)."""
    a = side([], fam)
    return dict(zip(COLUMNS, a + a))


# --------------------------------------------------------------------------- build (data update / retrain)
def build(log=print) -> int:
    """Rate every player before every match; write the per-match file and the latest state. Returns matches rated."""
    found: dict[str, tuple[str, str, Path, str]] = {}  # match id -> (date, fam, archive, file)  (later archives win)
    for arc in ARCHIVES:
        if not arc.exists():
            continue
        with zipfile.ZipFile(arc) as zf:
            for name in zf.namelist():
                if not name.endswith(".json"):
                    continue
                info = json.loads(zf.read(name)).get("info", {})
                mt = str(info.get("match_type", "")).upper()
                if info.get("gender") != "male" or mt not in {"T20", "IT20", "ODI"} or info.get("balls_per_over", 6) != 6:
                    continue
                mid = name.split("/")[-1].removesuffix(".json")
                found[mid] = ((info.get("dates") or ["0000-00-00"])[0], "odi" if mt == "ODI" else "t20", arc, name)
        log(f"LOG player ratings: {arc.name} read ({len(found):,} matches so far)")
    order = sorted(found.items(), key=lambda kv: (kv[1][0], kv[0]))
    state: dict[str, dict[str, list[float]]] = {"t20": {}, "odi": {}}
    rows = []
    open_zips: dict[Path, zipfile.ZipFile] = {}
    try:
        for j, (mid, (d, fam, arc, name)) in enumerate(order):
            if j and j % 4000 == 0:
                log(f"LOG player ratings: rated {j:,} of {len(order):,} matches (now at {d})")
            zf = open_zips.get(arc) or open_zips.setdefault(arc, zipfile.ZipFile(arc))
            data = json.loads(zf.read(name))
            info = data["info"]
            day = date.fromisoformat(d).toordinal()
            reg = (info.get("registry") or {}).get("people", {})
            xi = {t: [reg.get(n, n) for n in ps] for t, ps in (info.get("players") or {}).items()}
            inns = [x for x in data.get("innings", []) if not x.get("super_over")]
            tab = state[fam]
            if inns and len(xi) == 2:
                bat = inns[0]["team"]
                chase = next((t for t in xi if t != bat), None)
                if chase and bat in xi:
                    tot = lambda ids: [_decay(tab[p], day) if p in tab else None for p in ids]  # noqa: E731
                    rows.append({"match_id": mid, **dict(zip(COLUMNS, side(tot(xi[bat]), fam) + side(tot(xi[chase]), fam)))})
            delta: dict[str, list[float]] = {}
            for inn in inns:
                for over in inn.get("overs", []):
                    for dl in over.get("deliveries", []):
                        ex = dl.get("extras", {}) or {}
                        rb = delta.setdefault(reg.get(dl["batter"], dl["batter"]), [0.0] * 6)
                        rw = delta.setdefault(reg.get(dl["bowler"], dl["bowler"]), [0.0] * 6)
                        runs_bat = (dl.get("runs") or {}).get("batter", 0)
                        if "wides" not in ex:
                            rb[0] += runs_bat
                            rb[1] += 1
                        rw[3] += runs_bat + ex.get("wides", 0) + ex.get("noballs", 0)
                        if "wides" not in ex and "noballs" not in ex:
                            rw[4] += 1
                        for w in dl.get("wickets", []) or []:
                            out = w.get("player_out", "")
                            delta.setdefault(reg.get(out, out), [0.0] * 6)[2] += 1
                            if w.get("kind") not in NOT_BOWLERS_WICKET:
                                rw[5] += 1
            for pid, dv in delta.items():
                base = _decay(tab[pid], day) if pid in tab else [0.0] * 6
                tab[pid] = [round(a + b, 4) for a, b in zip(base, dv)] + [day]
    finally:
        for z in open_zips.values():
            z.close()
    import pandas as pd

    tmp = MATCHES_PATH.with_name(MATCHES_PATH.name + ".tmp")
    pd.DataFrame(rows).to_csv(tmp, index=False, compression="gzip")
    tmp.replace(MATCHES_PATH)
    tmp = STATE_PATH.with_name(STATE_PATH.name + ".tmp")
    tmp.write_text(json.dumps({"half_life": HALF_LIFE, "pull": PULL, "players": state}), encoding="utf-8")
    tmp.replace(STATE_PATH)
    load_state.cache_clear()
    log(f"LOG player ratings: wrote {len(rows):,} matches and {sum(len(v) for v in state.values()):,} player records")
    return len(rows)


# --------------------------------------------------------------------------- training / Replay
def add_columns(df):
    """The 8 rating inputs for a frame of match states (by match_id); matches without ratings get average players."""
    import pandas as pd

    if MATCHES_PATH.exists():
        pr = pd.read_csv(MATCHES_PATH, dtype={"match_id": str})
        df = df.drop(columns=[c for c in COLUMNS if c in df.columns])
        ids = df["match_id"].astype(str)
        df = df.assign(_mid=ids).merge(pr.rename(columns={"match_id": "_mid"}), on="_mid", how="left").drop(columns="_mid")
    for c in COLUMNS:
        if c not in df.columns:
            df[c] = float("nan")
    for fam in ("t20", "odi"):
        m = df["fam"] == fam if "fam" in df.columns else (df["is_odi"] == (1 if fam == "odi" else 0))
        for c, v in neutral(fam).items():
            df.loc[m & df[c].isna(), c] = v
    return df


@locked_cache
def by_match() -> dict[str, dict[str, float]]:
    """match id -> the 8 inputs (for Replay, which scores rows one match at a time)."""
    import pandas as pd

    if not MATCHES_PATH.exists():
        return {}
    pr = pd.read_csv(MATCHES_PATH, dtype={"match_id": str})
    return {r.pop("match_id"): r for r in pr.to_dict("records")}


# --------------------------------------------------------------------------- the app (today's ratings)
@locked_cache
def load_state() -> dict[str, Any]:
    try:
        return json.loads(STATE_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}


def for_xis(bat_ids: list[str | None], chase_ids: list[str | None], fam: str, day: int | None = None) -> dict[str, float]:
    """The 8 inputs for two XIs today (decayed to `day`). Unknown players count as average."""
    tab = (load_state().get("players") or {}).get(fam) or {}
    day = day or date.today().toordinal()
    tot = lambda ids: [_decay(tab[p], day) if p and p in tab else None for p in ids]  # noqa: E731
    return dict(zip(COLUMNS, side(tot(bat_ids), fam) + side(tot(chase_ids), fam)))


def reload() -> None:
    load_state.cache_clear()
    by_match.cache_clear()
