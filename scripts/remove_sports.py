"""
Remove sports & similar performers/events from the NeonDB database.

Strategy: Identify sports content by matching performer names and event names
against known sports teams, leagues, and patterns — NOT by genre.

Usage:
    # Discover — shows what genres/performers/events exist (helps tune keywords):
    python scripts/remove_sports.py --discover

    # Dry-run (default) — shows what WOULD be deleted, changes nothing:
    python scripts/remove_sports.py

    # Actually delete:
    python scripts/remove_sports.py --execute
"""

import os
import sys
import argparse

import psycopg2
from dotenv import load_dotenv

# ── Load .env from project root ──────────────────────────────────────────────
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
load_dotenv(os.path.join(ROOT_DIR, ".env"))

DATABASE_URL = os.environ.get("DATABASE_URL")
if not DATABASE_URL:
    print("ERROR: DATABASE_URL not found in environment or .env file.")
    sys.exit(1)

# ── Sports-related keywords for PERFORMER names ─────────────────────────────
# These match against performer names (case-insensitive).
SPORTS_PERFORMER_KEYWORDS = [
    # NFL teams
    "49ers", "bears", "bengals", "bills", "broncos", "browns", "buccaneers",
    "cardinals", "chargers", "chiefs", "colts", "commanders", "cowboys",
    "dolphins", "eagles", "falcons", "giants", "jaguars", "jets", "lions",
    "packers", "panthers", "patriots", "raiders", "rams", "ravens", "saints",
    "seahawks", "steelers", "texans", "titans", "vikings",

    # NBA teams
    "76ers", "sixers", "bucks", "bulls", "cavaliers", "cavs", "celtics",
    "clippers", "grizzlies", "hawks", "heat", "hornets", "jazz", "kings",
    "knicks", "lakers", "magic", "mavericks", "mavs", "nets", "nuggets",
    "pacers", "pelicans", "pistons", "raptors", "rockets", "spurs", "suns",
    "thunder", "timberwolves", "trail blazers", "warriors", "wizards",

    # MLB teams
    "astros", "athletics", "blue jays", "braves", "brewers", "cubs",
    "diamondbacks", "d-backs", "dodgers", "guardians", "mariners", "marlins",
    "mets", "nationals", "orioles", "padres", "phillies", "pirates",
    "rangers", "rays", "red sox", "reds", "rockies", "royals",
    "tigers", "twins", "white sox", "yankees",

    # NHL teams
    "avalanche", "blackhawks", "blue jackets", "blues", "bruins",
    "canadiens", "canucks", "capitals", "coyotes", "devils", "ducks",
    "flames", "flyers", "golden knights", "hurricanes", "islanders",
    "kraken", "lightning", "maple leafs", "oilers", "penguins",
    "predators", "red wings", "sabres", "senators", "sharks", "stars",
    "wild", "utah hockey",

    # MLS teams
    "atlanta united", "austin fc", "charlotte fc", "cf montreal",
    "chicago fire", "colorado rapids", "columbus crew", "fc cincinnati",
    "fc dallas", "houston dynamo", "inter miami", "la galaxy",
    "lafc", "minnesota united", "nashville sc", "new england revolution",
    "new york city fc", "new york red bulls", "orlando city",
    "philadelphia union", "portland timbers", "real salt lake",
    "san jose earthquakes", "seattle sounders", "sporting kansas city",
    "st. louis city", "toronto fc", "vancouver whitecaps",

    # WNBA
    "aces", "dream", "fever", "liberty", "lynx", "mercury", "mystics",
    "sky", "sparks", "storm", "sun", "wings",

    # Soccer / International
    "arsenal", "barcelona", "bayern munich", "borussia dortmund",
    "chelsea", "inter milan", "juventus", "liverpool", "man city",
    "manchester city", "manchester united", "man united", "napoli",
    "psg", "paris saint-germain", "real madrid", "tottenham",

    # College sports (common patterns)
    "crimson tide", "wolverines", "buckeyes", "fighting irish",
    "bulldogs", "wildcats", "longhorns", "sooners", "gators",
    "seminoles", "tar heels", "blue devils", "hoosiers",
    "nittany lions", "spartans", "badgers", "hawkeyes",
    "cornhuskers", "volunteers", "razorbacks", "aggies",
    "jayhawks", "mountaineers", "cyclones", "sun devils",

    # Other sports
    "ufc", "wwe", "aew",
]

# ── Sports-related keywords for EVENT names ──────────────────────────────────
SPORTS_EVENT_KEYWORDS = [
    # League / competition names
    "nfl", "nba", "mlb", "nhl", "mls", "wnba", "ncaa", "pga", "nascar",
    "formula 1", "f1 grand prix", "ufc", "wwe", "aew",
    "premier league", "champions league", "world cup", "copa america",
    "euro 2", "bundesliga", "la liga", "serie a", "ligue 1",
    "super bowl", "world series", "stanley cup", "nba finals",
    "march madness", "final four", "college football playoff",
    "bowl game", "all-star game", "pro bowl",
    "grand slam", "us open tennis", "wimbledon", "french open", "australian open",
    "olympics", "olympic games",
    "kentucky derby", "preakness", "belmont stakes", "triple crown",
    "daytona 500", "indy 500", "indianapolis 500",
    "ryder cup", "masters tournament", "the masters",
    "wrestlemania", "royal rumble", "summerslam",

    # Sport types
    "football game", "basketball game", "baseball game", "hockey game",
    "soccer match", "tennis match", "golf tournament", "boxing match",
    "mma fight", "wrestling event",

    # Patterns
    "spring training",
    "preseason", "regular season", "postseason", "playoff",
    "doubleheader",
]

# ── Patterns that strongly indicate a sports event (regex-style) ────────────
# We'll use SQL patterns for these
SPORTS_EVENT_SQL_PATTERNS = [
    # "Team vs Team" or "Team vs. Team" or "Team at Team"
    # These will be checked via SQL LIKE / SIMILAR TO
    "% vs %",
    "% vs. %",
    "% at %",  # Be careful — this is too broad, we'll use it combined with other signals
]


def build_ilike_or(column: str, keywords: list[str]) -> tuple[str, list[str]]:
    """Build a SQL OR chain of ILIKE conditions."""
    if not keywords:
        return "FALSE", []
    clauses = [f"{column} ILIKE %s" for _ in keywords]
    params = [f"%{kw}%" for kw in keywords]
    return " OR ".join(clauses), params


def main():
    parser = argparse.ArgumentParser(description="Remove sports performers/events from NeonDB")
    parser.add_argument(
        "--discover",
        action="store_true",
        help="Show sample data from the database to help tune keywords.",
    )
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually delete rows. Without this flag, the script only prints what it would do.",
    )
    args = parser.parse_args()

    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    cur = conn.cursor()

    try:
        if args.discover:
            _discover(cur)
            return

        dry_run = not args.execute
        _remove_sports(cur, conn, dry_run)

    except Exception as e:
        conn.rollback()
        print(f"\n❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
    finally:
        cur.close()
        conn.close()


def _discover(cur):
    """Show what data exists in the DB to help understand the schema."""
    print("=" * 70)
    print("DISCOVERY: SeatGeek Genres")
    print("=" * 70)
    cur.execute("SELECT id, name, slug, \"primary\" FROM seatgeek_genres ORDER BY name")
    genres = cur.fetchall()
    print(f"  Total: {len(genres)}")
    for gid, name, slug, primary in genres:
        print(f"    {'[P]' if primary else '   '} {name} (slug={slug})")

    print()
    print("=" * 70)
    print("DISCOVERY: Distinct performer_genres.genre values")
    print("=" * 70)
    cur.execute("SELECT DISTINCT genre FROM performer_genres ORDER BY genre LIMIT 100")
    pgenres = cur.fetchall()
    print(f"  Total distinct: {len(pgenres)}")
    for (g,) in pgenres:
        print(f"    - {g}")

    print()
    print("=" * 70)
    print("DISCOVERY: Sample performers (first 50 by name)")
    print("=" * 70)
    cur.execute("SELECT id, name, url FROM performers ORDER BY name LIMIT 50")
    performers = cur.fetchall()
    for pid, pname, purl in performers:
        print(f"    - {pname} ({purl[:60]}...)" if len(purl) > 60 else f"    - {pname} ({purl})")

    print()
    print("=" * 70)
    print("DISCOVERY: Sample events (first 50 by name)")
    print("=" * 70)
    cur.execute("SELECT id, name, url FROM events ORDER BY name LIMIT 50")
    events = cur.fetchall()
    for eid, ename, eurl in events:
        print(f"    - {ename}")

    print()
    print("=" * 70)
    print("TOTALS")
    print("=" * 70)
    for table in ["performers", "events", "venues", "performer_events",
                   "performer_genres", "performer_seatgeek_genres", "seatgeek_genres"]:
        cur.execute(f"SELECT COUNT(*) FROM {table}")
        count = cur.fetchone()[0]
        print(f"  {table}: {count:,} rows")


def _remove_sports(cur, conn, dry_run: bool):
    """Identify and remove sports performers & events."""

    # ── 1. Find sports performers by name ────────────────────────────────
    print("=" * 70)
    print("STEP 1: Identifying sports performers by name")
    print("=" * 70)

    perf_where, perf_params = build_ilike_or("name", SPORTS_PERFORMER_KEYWORDS)
    cur.execute(f"SELECT id, name FROM performers WHERE {perf_where} ORDER BY name", perf_params)
    sports_performers = cur.fetchall()
    sports_performer_ids = [row[0] for row in sports_performers]

    print(f"  Found {len(sports_performers)} sports performer(s):")
    for pid, pname in sports_performers[:50]:
        print(f"    - {pname} (id={pid})")
    if len(sports_performers) > 50:
        print(f"    ... and {len(sports_performers) - 50} more")

    # ── 2. Find sports events by name ────────────────────────────────────
    print()
    print("=" * 70)
    print("STEP 2: Identifying sports events by name")
    print("=" * 70)

    ev_where, ev_params = build_ilike_or("name", SPORTS_EVENT_KEYWORDS)
    cur.execute(f"SELECT id, name FROM events WHERE {ev_where} ORDER BY name", ev_params)
    keyword_events = cur.fetchall()
    keyword_event_ids = {row[0] for row in keyword_events}

    print(f"  Found {len(keyword_events)} event(s) matching sports keywords:")
    for eid, ename in keyword_events[:30]:
        print(f"    - {ename}")
    if len(keyword_events) > 30:
        print(f"    ... and {len(keyword_events) - 30} more")

    # ── 3. Find events linked to sports performers ───────────────────────
    print()
    print("=" * 70)
    print("STEP 3: Finding events linked to sports performers")
    print("=" * 70)

    performer_event_ids = set()
    if sports_performer_ids:
        placeholders = ", ".join(["%s"] * len(sports_performer_ids))
        cur.execute(
            f"SELECT DISTINCT event_id FROM performer_events WHERE performer_id IN ({placeholders})",
            sports_performer_ids,
        )
        performer_event_ids = {row[0] for row in cur.fetchall()}

    print(f"  Found {len(performer_event_ids)} event(s) linked to sports performers")

    # ── 4. Union all sports events ───────────────────────────────────────
    all_sports_event_ids = list(keyword_event_ids | performer_event_ids)

    # Also find any additional performers linked to sports events
    # (catches performers that aren't in our keyword list but only appear at sports events)
    extra_performer_ids = set()
    if all_sports_event_ids:
        ev_placeholders = ", ".join(["%s"] * len(all_sports_event_ids))
        cur.execute(
            f"SELECT DISTINCT performer_id FROM performer_events WHERE event_id IN ({ev_placeholders})",
            all_sports_event_ids,
        )
        all_event_performers = {row[0] for row in cur.fetchall()}

        # Check if these performers have ANY non-sports events
        for pid in all_event_performers - set(sports_performer_ids):
            cur.execute(
                "SELECT COUNT(*) FROM performer_events WHERE performer_id = %s AND event_id NOT IN ("
                + ", ".join(["%s"] * len(all_sports_event_ids)) + ")",
                [pid] + all_sports_event_ids,
            )
            non_sports_count = cur.fetchone()[0]
            if non_sports_count == 0:
                extra_performer_ids.add(pid)

    if extra_performer_ids:
        extra_placeholders = ", ".join(["%s"] * len(extra_performer_ids))
        cur.execute(
            f"SELECT id, name FROM performers WHERE id IN ({extra_placeholders}) ORDER BY name",
            list(extra_performer_ids),
        )
        extra_performers = cur.fetchall()
        print()
        print(f"  Found {len(extra_performers)} additional performer(s) linked ONLY to sports events:")
        for pid, pname in extra_performers[:20]:
            print(f"    - {pname}")
        if len(extra_performers) > 20:
            print(f"    ... and {len(extra_performers) - 20} more")

    all_sports_performer_ids = list(set(sports_performer_ids) | extra_performer_ids)

    print()
    print("=" * 70)
    print("TOTALS")
    print("=" * 70)
    print(f"  Total sports performers:  {len(all_sports_performer_ids)}")
    print(f"  Total sports events:      {len(all_sports_event_ids)}")

    if not all_sports_performer_ids and not all_sports_event_ids:
        print("\nNo sports data found. Nothing to do.")
        print("TIP: Run with --discover to see what data is actually in the database.")
        conn.rollback()
        return

    # ── 5. Find favorites referencing sports performers ──────────────────
    fav_count = 0
    if all_sports_performer_ids:
        perf_placeholders = ", ".join(["%s"] * len(all_sports_performer_ids))
        cur.execute(
            f"SELECT COUNT(*) FROM favorites WHERE seatgeek_performer_id IN ({perf_placeholders})",
            all_sports_performer_ids,
        )
        fav_count = cur.fetchone()[0]

    # ── 6. Find orphaned venues ──────────────────────────────────────────
    orphan_venue_ids = []
    if all_sports_event_ids:
        ev_placeholders = ", ".join(["%s"] * len(all_sports_event_ids))
        cur.execute(
            f"""SELECT DISTINCT venue_id FROM events
                WHERE id IN ({ev_placeholders}) AND venue_id IS NOT NULL""",
            all_sports_event_ids,
        )
        candidate_venue_ids = [row[0] for row in cur.fetchall()]

        if candidate_venue_ids:
            v_placeholders = ", ".join(["%s"] * len(candidate_venue_ids))
            cur.execute(
                f"""SELECT v.id, v.name FROM venues v
                    WHERE v.id IN ({v_placeholders})
                    AND NOT EXISTS (
                        SELECT 1 FROM events e
                        WHERE e.venue_id = v.id
                        AND e.id NOT IN ({ev_placeholders})
                    )""",
                candidate_venue_ids + all_sports_event_ids,
            )
            orphan_venues = cur.fetchall()
            orphan_venue_ids = [row[0] for row in orphan_venues]

    # ── 7. Find sports SeatGeek genres (genres only linked to sports performers)
    sports_sg_genre_ids = []
    if all_sports_performer_ids:
        perf_placeholders = ", ".join(["%s"] * len(all_sports_performer_ids))
        cur.execute(
            f"""SELECT DISTINCT sg.id, sg.name FROM seatgeek_genres sg
                JOIN performer_seatgeek_genres psg ON psg.seatgeek_genre_id = sg.id
                WHERE psg.performer_id IN ({perf_placeholders})
                AND NOT EXISTS (
                    SELECT 1 FROM performer_seatgeek_genres psg2
                    WHERE psg2.seatgeek_genre_id = sg.id
                    AND psg2.performer_id NOT IN ({perf_placeholders})
                )""",
            all_sports_performer_ids + all_sports_performer_ids,
        )
        sg_results = cur.fetchall()
        sports_sg_genre_ids = [row[0] for row in sg_results]
        if sg_results:
            print(f"\n  SeatGeek genres exclusive to sports performers:")
            for gid, gname in sg_results:
                print(f"    - {gname}")

    # ── SUMMARY ──────────────────────────────────────────────────────────
    print()
    print("=" * 70)
    print("DELETION SUMMARY")
    print("=" * 70)
    print(f"  Favorites to delete:               {fav_count}")
    print(f"  Performer-event links to delete:    (all for {len(all_sports_performer_ids)} performers + event-side)")
    print(f"  Performer-genre links to delete:    (all for {len(all_sports_performer_ids)} performers)")
    print(f"  Performer-SG-genre links to delete: (all for {len(all_sports_performer_ids)} performers)")
    print(f"  Performers to delete:               {len(all_sports_performer_ids)}")
    print(f"  Events to delete:                   {len(all_sports_event_ids)}")
    print(f"  Orphaned venues to delete:          {len(orphan_venue_ids)}")
    print(f"  SeatGeek genres to delete:          {len(sports_sg_genre_ids)}")

    if dry_run:
        print()
        print(">>> DRY RUN — no rows were deleted. Run with --execute to apply. <<<")
        conn.rollback()
        return

    # ── EXECUTE DELETIONS (proper order to respect FK constraints) ───────
    print()
    print("=" * 70)
    print("EXECUTING DELETIONS...")
    print("=" * 70)

    # 1) Favorites referencing sports performers
    if all_sports_performer_ids:
        perf_placeholders = ", ".join(["%s"] * len(all_sports_performer_ids))
        cur.execute(
            f"DELETE FROM favorites WHERE seatgeek_performer_id IN ({perf_placeholders})",
            all_sports_performer_ids,
        )
        print(f"  ✓ Deleted {cur.rowcount} favorite(s)")

    # 2) performer_events for sports performers AND sports events
    if all_sports_performer_ids:
        cur.execute(
            f"DELETE FROM performer_events WHERE performer_id IN ({perf_placeholders})",
            all_sports_performer_ids,
        )
        print(f"  ✓ Deleted {cur.rowcount} performer_event link(s) (by performer)")

    if all_sports_event_ids:
        ev_placeholders = ", ".join(["%s"] * len(all_sports_event_ids))
        cur.execute(
            f"DELETE FROM performer_events WHERE event_id IN ({ev_placeholders})",
            all_sports_event_ids,
        )
        print(f"  ✓ Deleted {cur.rowcount} performer_event link(s) (by event)")

    # 3) performer_genres for sports performers
    if all_sports_performer_ids:
        cur.execute(
            f"DELETE FROM performer_genres WHERE performer_id IN ({perf_placeholders})",
            all_sports_performer_ids,
        )
        print(f"  ✓ Deleted {cur.rowcount} performer_genre link(s)")

    # 4) performer_seatgeek_genres for sports performers
    if all_sports_performer_ids:
        cur.execute(
            f"DELETE FROM performer_seatgeek_genres WHERE performer_id IN ({perf_placeholders})",
            all_sports_performer_ids,
        )
        print(f"  ✓ Deleted {cur.rowcount} performer_seatgeek_genre link(s)")

    # 5) performers
    if all_sports_performer_ids:
        cur.execute(
            f"DELETE FROM performers WHERE id IN ({perf_placeholders})",
            all_sports_performer_ids,
        )
        print(f"  ✓ Deleted {cur.rowcount} performer(s)")

    # 6) Events
    if all_sports_event_ids:
        ev_placeholders = ", ".join(["%s"] * len(all_sports_event_ids))
        cur.execute(
            f"DELETE FROM events WHERE id IN ({ev_placeholders})",
            all_sports_event_ids,
        )
        print(f"  ✓ Deleted {cur.rowcount} event(s)")

    # 7) Orphaned venues
    if orphan_venue_ids:
        v_del_placeholders = ", ".join(["%s"] * len(orphan_venue_ids))
        cur.execute(
            f"DELETE FROM venues WHERE id IN ({v_del_placeholders})",
            orphan_venue_ids,
        )
        print(f"  ✓ Deleted {cur.rowcount} orphaned venue(s)")
    else:
        print(f"  ✓ No orphaned venues to delete")

    # 8) Sports SeatGeek genres
    if sports_sg_genre_ids:
        sg_placeholders = ", ".join(["%s"] * len(sports_sg_genre_ids))
        cur.execute(
            f"DELETE FROM seatgeek_genres WHERE id IN ({sg_placeholders})",
            sports_sg_genre_ids,
        )
        print(f"  ✓ Deleted {cur.rowcount} SeatGeek genre(s)")

    conn.commit()
    print()
    print("✅ All sports data successfully removed!")


if __name__ == "__main__":
    main()
