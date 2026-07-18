"""Backend-maintained role hierarchy for the two team domains.

The hierarchy is a property of the *role type*, not of an individual team: every
Artist team ranks its Manager above its Tour Manager, and no team can reorder
that. Rank therefore lives here as a constant rather than in a table, which
keeps rank resolution a dict lookup instead of a join.

Rank 0 is the most senior level. A lower rank outranks a higher one.

Ranks are declared explicitly rather than derived from declaration order,
because **two roles may share a level**. Peers at the same rank neither outrank
nor report to each other - `Manager` and a hypothetical `Co-Manager` both at
rank 1 are equals. Ranks therefore need not be unique, contiguous, or gap-free;
leaving gaps (0, 10, 20) is a deliberate option that lets a level be inserted
later without renumbering everything below it.

Adding a role is a code change here plus a migration for the widened
``choices`` - deliberately, so a hierarchy change is reviewed rather than
configured at runtime.
"""

from django.core.exceptions import ImproperlyConfigured
from django.db import models


class TeamDomain(models.TextChoices):
    ARTIST = "artist", "Artist"
    VENUE = "venue", "Venue"


class ArtistRole(models.TextChoices):
    ARTIST = "artist", "Artist"
    MANAGER = "manager", "Manager"
    BUSINESS_MANAGER = "business_manager", "Business Manager"
    RESPONSIBLE_AGENT = "responsible_agent", "Responsible Agent"
    SEGMENT_AGENT = "segment_agent", "Segment Agent"
    TOUR_MANAGER = "tour_manager", "Tour Manager"
    LEGAL_REPRESENTATIVE = "legal_representative", "Legal Representative"


class VenueRole(models.TextChoices):
    CEO_GM = "ceo_gm", "CEO / GM"
    ENTERTAINMENT_MANAGER = "entertainment_manager", "Entertainment Manager"
    TALENT_BUYER = "talent_buyer", "Talent Buyer"
    PRODUCTION_DIRECTOR = "production_director", "Production Director"
    MARKETING_DIRECTOR = "marketing_director", "Marketing Director"
    FINANCE_TEAM = "finance_team", "Finance Team"
    LEGAL_TEAM = "legal_team", "Legal Team"


# role -> rank, per domain. Duplicate ranks are legal and mean "same level".
# To add a peer of Manager, declare it at the same rank:
#     ArtistRole.CO_MANAGER.value: 1,
ROLE_RANKS: dict[str, dict[str, int]] = {
    TeamDomain.ARTIST.value: {
        ArtistRole.ARTIST.value: 0,
        ArtistRole.MANAGER.value: 1,
        ArtistRole.BUSINESS_MANAGER.value: 2,
        ArtistRole.RESPONSIBLE_AGENT.value: 3,
        ArtistRole.SEGMENT_AGENT.value: 4,
        ArtistRole.TOUR_MANAGER.value: 5,
        ArtistRole.LEGAL_REPRESENTATIVE.value: 6,
    },
    TeamDomain.VENUE.value: {
        VenueRole.CEO_GM.value: 0,
        VenueRole.ENTERTAINMENT_MANAGER.value: 1,
        VenueRole.TALENT_BUYER.value: 2,
        VenueRole.PRODUCTION_DIRECTOR.value: 3,
        VenueRole.MARKETING_DIRECTOR.value: 4,
        VenueRole.FINANCE_TEAM.value: 5,
        VenueRole.LEGAL_TEAM.value: 6,
    },
}

# Every role value across both domains, for the model field's `choices`.
# Values are globally unique, so a role implies its domain unambiguously.
ROLE_CHOICES: list[tuple[str, str]] = ArtistRole.choices + VenueRole.choices

_ROLE_LABELS: dict[str, str] = dict(ROLE_CHOICES)

_ROLE_DOMAIN: dict[str, str] = {
    role: domain for domain, ranks in ROLE_RANKS.items() for role in ranks
}


def _assert_ranks_and_choices_agree() -> None:
    """Fail at import if a role is declared in one place but not the other.

    The enums and ROLE_RANKS are two hand-maintained lists that must describe
    the same set. Adding a role to one and forgetting the other would otherwise
    surface as a KeyError deep inside a request. Checking here turns that into a
    startup error that `manage.py check` catches before deploy.
    """
    ranked = {role for ranks in ROLE_RANKS.values() for role in ranks}
    labelled = set(_ROLE_LABELS)
    if ranked == labelled:
        return
    raise ImproperlyConfigured(
        "teams.roles is inconsistent: "
        f"roles with a rank but no enum entry: {sorted(ranked - labelled) or 'none'}; "
        f"roles with an enum entry but no rank: {sorted(labelled - ranked) or 'none'}."
    )


_assert_ranks_and_choices_agree()


def is_valid_role(domain: str, role: str) -> bool:
    return _ROLE_DOMAIN.get(role) == domain


def rank_of(domain: str, role: str) -> int:
    """Rank of `role` within `domain`. Raises KeyError for a mismatched pair."""
    return ROLE_RANKS[domain][role]


def outranks(domain: str, role: str, other: str) -> bool:
    """True if `role` sits strictly above `other`. False for peers."""
    return rank_of(domain, role) < rank_of(domain, other)


def same_level(domain: str, role: str, other: str) -> bool:
    """True if the two roles are peers - equal rank, neither outranking."""
    return rank_of(domain, role) == rank_of(domain, other)


def hierarchy(domain: str) -> list[dict]:
    """The domain's roles as flat rows, most senior first.

    Peers share a `rank`, so a client grouping on it renders them side by side.
    Sorted by label within a rank so output stays stable once peers exist.
    """
    return sorted(
        (
            {"role": role, "label": _ROLE_LABELS[role], "rank": rank}
            for role, rank in ROLE_RANKS[domain].items()
        ),
        key=lambda row: (row["rank"], row["label"]),
    )


def levels(domain: str) -> list[dict]:
    """The domain's hierarchy grouped by rank - one entry per level.

    The shape that makes peers explicit: ``{"rank": 1, "roles": [...]}``. A
    level with two roles in it is two peers.
    """
    grouped: dict[int, list[dict]] = {}
    for row in hierarchy(domain):
        grouped.setdefault(row["rank"], []).append(
            {"role": row["role"], "label": row["label"]}
        )
    return [{"rank": rank, "roles": roles} for rank, roles in sorted(grouped.items())]
