"""Named periods the assistant understands ("ce mois", "la semaine dernière"...)."""

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Literal

Period = Literal[
    "aujourdhui",
    "hier",
    "cette_semaine",
    "semaine_derniere",
    "ce_mois",
    "mois_dernier",
    "7_derniers_jours",
    "30_derniers_jours",
    "3_derniers_mois",
    "depuis_le_debut",
    "personnalisee",
]

PERIOD_HELP = (
    "Période analysée. « personnalisee » utilise date_debut et date_fin ; "
    "pour toute autre valeur, mettre date_debut et date_fin à null."
)

_MONTHS = (
    "janvier",
    "février",
    "mars",
    "avril",
    "mai",
    "juin",
    "juillet",
    "août",
    "septembre",
    "octobre",
    "novembre",
    "décembre",
)


@dataclass(frozen=True)
class Range:
    start: datetime  # included
    end: datetime  # excluded
    label: str  # French, shown on screen

    def as_dict(self) -> dict[str, str]:
        last_day = (self.end - timedelta(seconds=1)).date()
        return {
            "libelle": self.label,
            "debut": self.start.date().isoformat(),
            "fin": last_day.isoformat(),
        }


class PeriodError(ValueError):
    """Message sent back to the model so it can correct its call."""


def _day(d: date) -> datetime:
    return datetime.combine(d, time.min)


def _month_start(d: date) -> date:
    return d.replace(day=1)


def fr_date(d: date) -> str:
    return f"{d.day} {_MONTHS[d.month - 1]} {d.year}"


def resolve(
    period: Period, start: str | None, end: str | None, today: date, first_day: date
) -> Range:
    tomorrow = today + timedelta(days=1)
    match period:
        case "aujourdhui":
            return Range(_day(today), _day(tomorrow), "aujourd'hui")
        case "hier":
            return Range(_day(today - timedelta(days=1)), _day(today), "hier")
        case "cette_semaine":
            monday = today - timedelta(days=today.weekday())
            return Range(_day(monday), _day(tomorrow), "cette semaine")
        case "semaine_derniere":
            monday = today - timedelta(days=today.weekday() + 7)
            return Range(_day(monday), _day(monday + timedelta(days=7)), "la semaine dernière")
        case "ce_mois":
            first = _month_start(today)
            return Range(_day(first), _day(tomorrow), f"{_MONTHS[today.month - 1]} {today.year}")
        case "mois_dernier":
            this_month = _month_start(today)
            previous = _month_start(this_month - timedelta(days=1))
            label = f"{_MONTHS[previous.month - 1]} {previous.year}"
            return Range(_day(previous), _day(this_month), label)
        case "7_derniers_jours":
            return Range(_day(today - timedelta(days=6)), _day(tomorrow), "les 7 derniers jours")
        case "30_derniers_jours":
            return Range(_day(today - timedelta(days=29)), _day(tomorrow), "les 30 derniers jours")
        case "3_derniers_mois":
            return Range(_day(today - timedelta(days=89)), _day(tomorrow), "les 3 derniers mois")
        case "depuis_le_debut":
            return Range(_day(first_day), _day(tomorrow), "depuis l'ouverture du registre")
        case "personnalisee":
            if not start or not end:
                raise PeriodError("periode=personnalisee exige date_debut et date_fin (AAAA-MM-JJ)")
            try:
                d1, d2 = date.fromisoformat(start), date.fromisoformat(end)
            except ValueError as exc:
                raise PeriodError("dates attendues au format AAAA-MM-JJ") from exc
            if d2 < d1:
                d1, d2 = d2, d1
            label = f"du {fr_date(d1)} au {fr_date(d2)}"
            return Range(_day(d1), _day(d2 + timedelta(days=1)), label)
    raise PeriodError(f"période inconnue : {period}")
