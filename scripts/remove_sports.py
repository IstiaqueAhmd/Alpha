"""
Remove sports & similar performers/events from the NeonDB database.

Usage:
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

# ── Sports-related genre keywords ────────────────────────────────────────────
# These are matched case-insensitively against both `performer_genres.genre`
# and `seatgeek_genres.name` / `seatgeek_genres.slug`.
SPORTS_KEYWORDS = [
    # Major US leagues
    "nfl", "nba", "mlb", "nhl", "mls", "wnba", "ncaa",
    # Sports
    "football", "basketball", "baseball", "hockey", "soccer",
    "tennis", "golf", "boxing", "mma", "wrestling", "rugby",
    "cricket", "lacrosse", "volleyball", "softball", "motorsport",
    "racing", "nascar", "f1", "formula", "auto racing",
    "horse racing", "rodeo", "polo",
    # Generic
    "sports", "sport", "athletic", "athletics",
    # Other sporting events
    "fight", "ufc", "wwe", "aew",
    "cycling", "swimming", "track and field",
    "figure skating", "skiing", "snowboarding",
    "surfing", "skateboarding", "esports", "e-sports",
    "minor league", "minor_league",
    "college football", "college basketball",
    "world cup", "champions league", "premier league",
    "bundesliga", "la liga", "serie a", "ligue 1",
    "olympic", "olympics",
]


def build_ilike_conditions(column: str) -> str:
    """Build a SQL OR chain of ILIKE conditions for the given column."""
    clauses = [f"{column} ILIKE %s" for _ in SPORTS_KEYWORDS]
    return " OR ".join(clauses)


def ilike_params() -> list[str]:
    """Return parameter values for ILIKE matching (wrapped in %)."""
    return [f"%{kw}%" for kw in SPORTS_KEYWORDS]


def main():
    parser = argparse.ArgumentParser(description="Remove sports performers/events from NeonDB")
    parser.add_argument(
        "--execute",
        action="store_true",
        help="Actually delete rows. Without this flag, the script only prints what it would do.",
    )
    args = parser.parse_args()
    dry_run = not args.execute

    conn = psycopg2.connect(DATABASE_URL)
    conn.autocommit = False
    cur = conn.cursor()

    try:
        # ── 1. Find sports-related SeatGeek genres ───────────────────────────
        print("=" * 70)
        print("STEP 1: Identifying sports-related SeatGeek genres")
        print("=" * 70)

        sg_genre_where = build_ilike_conditions("name") + " OR " + build_ilike_conditions("slug")
        cur.execute(
            f"SELECT id, name, slug FROM seatgeek_genres WHERE {sg_genre_where}",
            ilike_params() + ilike_params(),
        )
        sports_sg_genres = cur.fetchall()
        sports_sg_genre_ids = [row[0] for row in sports_sg_genres]

        print(f"  Found {len(sports_sg_genres)} sports SeatGeek genre(s):")
        for gid, name, slug in sports_sg_genres:
            print(f"    - {name} (slug={slug}, id={gid})")

        # ── 2. Find performers linked to sports SeatGeek genres ──────────────
        print()
        print("=" * 70)
        print("STEP 2: Identifying performers via seatgeek_genres linkage")
        print("=" * 70)

        performers_via_sg = set()
        if sports_sg_genre_ids:
            placeholders = ", ".join(["%s"] * len(sports_sg_genre_ids))
            cur.execute(
                f"SELECT DISTINCT performer_id FROM performer_seatgeek_genres WHERE seatgeek_genre_id IN ({placeholders})",
                sports_sg_genre_ids,
            )
            performers_via_sg = {row[0] for row in cur.fetchall()}
        print(f"  Found {len(performers_via_sg)} performer(s) via SeatGeek genre linkage")

        # ── 3. Find performers linked to sports performer_genres ─────────────
        print()
        print("=" * 70)
        print("STEP 3: Identifying performers via performer_genres")
        print("=" * 70)

        pg_where = build_ilike_conditions("genre")
        cur.execute(
            f"SELECT DISTINCT performer_id FROM performer_genres WHERE {pg_where}",
            ilike_params(),
        )
        performers_via_pg = {row[0] for row in cur.fetchall()}
        print(f"  Found {len(performers_via_pg)} performer(s) via performer_genres")

        # ── 4. Union of all sports performer IDs ─────────────────────────────
        all_sports_performer_ids = list(performers_via_sg | performers_via_pg)
        print()
        print("=" * 70)
        print(f"TOTAL SPORTS PERFORMERS TO REMOVE: {len(all_sports_performer_ids)}")
        print("=" * 70)

        if not all_sports_performer_ids:
            print("\nNo sports performers found. Nothing to do.")
            return

        # Show a sample
        placeholders = ", ".join(["%s"] * len(all_sports_performer_ids))
        cur.execute(
            f"SELECT id, name FROM performers WHERE id IN ({placeholders}) ORDER BY name LIMIT 30",
            all_sports_performer_ids,
        )
        sample = cur.fetchall()
        print(f"\n  Sample performers (showing up to 30):")
        for pid, pname in sample:
            print(f"    - {pname} (id={pid})")
        if len(all_sports_performer_ids) > 30:
            print(f"    ... and {len(all_sports_performer_ids) - 30} more")

        # ── 5. Find events linked ONLY to sports performers ─────────────────
        print()
        print("=" * 70)
        print("STEP 5: Finding events linked to sports performers")
        print("=" * 70)

        cur.execute(
            f"SELECT DISTINCT event_id FROM performer_events WHERE performer_id IN ({placeholders})",
            all_sports_performer_ids,
        )
        sports_event_ids = [row[0] for row in cur.fetchall()]
        print(f"  Found {len(sports_event_ids)} event(s) linked to sports performers")

        # Check which events are ALSO linked to non-sports performers
        shared_event_ids = set()
        if sports_event_ids:
            ev_placeholders = ", ".join(["%s"] * len(sports_event_ids))
            perf_placeholders = ", ".join(["%s"] * len(all_sports_performer_ids))
            cur.execute(
                f"""SELECT DISTINCT event_id FROM performer_events
                    WHERE event_id IN ({ev_placeholders})
                    AND performer_id NOT IN ({perf_placeholders})""",
                sports_event_ids + all_sports_performer_ids,
            )
            shared_event_ids = {row[0] for row in cur.fetchall()}

        # Only delete events that are exclusively linked to sports performers
        events_to_delete = [eid for eid in sports_event_ids if eid not in shared_event_ids]
        print(f"  Events exclusively linked to sports performers (will delete): {len(events_to_delete)}")
        print(f"  Events shared with non-sports performers (will keep): {len(shared_event_ids)}")

        # ── 6. Find favorites referencing sports performers ──────────────────
        print()
        print("=" * 70)
        print("STEP 6: Finding favorites referencing sports performers")
        print("=" * 70)

        cur.execute(
            f"SELECT COUNT(*) FROM favorites WHERE seatgeek_performer_id IN ({placeholders})",
            all_sports_performer_ids,
        )
        fav_count = cur.fetchone()[0]
        print(f"  Found {fav_count} favorite(s) referencing sports performers")

        # ── 7. Find orphaned venues (venues whose events are all being deleted)
        orphan_venue_ids = []
        if events_to_delete:
            ev_del_placeholders = ", ".join(["%s"] * len(events_to_delete))
            cur.execute(
                f"""SELECT DISTINCT venue_id FROM events
                    WHERE id IN ({ev_del_placeholders})
                    AND venue_id IS NOT NULL""",
                events_to_delete,
            )
            candidate_venue_ids = [row[0] for row in cur.fetchall()]

            if candidate_venue_ids:
                v_placeholders = ", ".join(["%s"] * len(candidate_venue_ids))
                cur.execute(
                    f"""SELECT v.id FROM venues v
                        WHERE v.id IN ({v_placeholders})
                        AND NOT EXISTS (
                            SELECT 1 FROM events e
                            WHERE e.venue_id = v.id
                            AND e.id NOT IN ({ev_del_placeholders})
                        )""",
                    candidate_venue_ids + events_to_delete,
                )
                orphan_venue_ids = [row[0] for row in cur.fetchall()]

        print()
        print("=" * 70)
        print("STEP 7: Orphaned venues (all events being deleted)")
        print("=" * 70)
        print(f"  Found {len(orphan_venue_ids)} venue(s) that would become orphaned")

        # ── SUMMARY ──────────────────────────────────────────────────────────
        print()
        print("=" * 70)
        print("DELETION SUMMARY")
        print("=" * 70)
        print(f"  Favorites to delete:               {fav_count}")
        print(f"  Performer-event links to delete:    (all for {len(all_sports_performer_ids)} sports performers)")
        print(f"  Performer-genre links to delete:    (all for {len(all_sports_performer_ids)} sports performers)")
        print(f"  Performer-SG-genre links to delete: (all for {len(all_sports_performer_ids)} sports performers)")
        print(f"  Events to delete:                   {len(events_to_delete)}")
        print(f"  Performers to delete:               {len(all_sports_performer_ids)}")
        print(f"  Orphaned venues to delete:          {len(orphan_venue_ids)}")
        print(f"  Sports SeatGeek genres to delete:   {len(sports_sg_genre_ids)}")

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
        cur.execute(
            f"DELETE FROM favorites WHERE seatgeek_performer_id IN ({placeholders})",
            all_sports_performer_ids,
        )
        print(f"  ✓ Deleted {cur.rowcount} favorite(s)")

        # 2) performer_events for sports performers
        cur.execute(
            f"DELETE FROM performer_events WHERE performer_id IN ({placeholders})",
            all_sports_performer_ids,
        )
        print(f"  ✓ Deleted {cur.rowcount} performer_event link(s)")

        # 3) performer_genres for sports performers
        cur.execute(
            f"DELETE FROM performer_genres WHERE performer_id IN ({placeholders})",
            all_sports_performer_ids,
        )
        print(f"  ✓ Deleted {cur.rowcount} performer_genre link(s)")

        # 4) performer_seatgeek_genres for sports performers
        cur.execute(
            f"DELETE FROM performer_seatgeek_genres WHERE performer_id IN ({placeholders})",
            all_sports_performer_ids,
        )
        print(f"  ✓ Deleted {cur.rowcount} performer_seatgeek_genre link(s)")

        # 5) performers
        cur.execute(
            f"DELETE FROM performers WHERE id IN ({placeholders})",
            all_sports_performer_ids,
        )
        print(f"  ✓ Deleted {cur.rowcount} performer(s)")

        # 6) Events (only those exclusive to sports performers)
        if events_to_delete:
            ev_del_placeholders = ", ".join(["%s"] * len(events_to_delete))
            cur.execute(
                f"DELETE FROM events WHERE id IN ({ev_del_placeholders})",
                events_to_delete,
            )
            print(f"  ✓ Deleted {cur.rowcount} event(s)")
        else:
            print(f"  ✓ No events to delete")

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

        # 8) Sports SeatGeek genres (only ones no longer referenced)
        if sports_sg_genre_ids:
            sg_placeholders = ", ".join(["%s"] * len(sports_sg_genre_ids))
            cur.execute(
                f"""DELETE FROM seatgeek_genres WHERE id IN ({sg_placeholders})
                    AND NOT EXISTS (
                        SELECT 1 FROM performer_seatgeek_genres psg
                        WHERE psg.seatgeek_genre_id = seatgeek_genres.id
                    )""",
                sports_sg_genre_ids,
            )
            print(f"  ✓ Deleted {cur.rowcount} SeatGeek genre(s)")

        conn.commit()
        print()
        print("✅ All sports data successfully removed!")

    except Exception as e:
        conn.rollback()
        print(f"\n❌ ERROR: {e}")
        raise
    finally:
        cur.close()
        conn.close()


if __name__ == "__main__":
    main()
