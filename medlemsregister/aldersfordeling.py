"""Aldersgrupper utan personopplysningar i resultatet."""
from datetime import date


def age_distribution(rows, as_of):
    counts = dict(age_0_14=0, age_15_25=0, age_26_plus=0, unknown=0)
    for row in rows:
        try:
            born = date.fromisoformat(row['birth_date'] or '')
            if born > as_of:
                raise ValueError('Framtidig fødselsdato')
        except (ValueError, TypeError):
            counts['unknown'] += 1
            continue
        age = as_of.year - born.year - ((as_of.month, as_of.day) < (born.month, born.day))
        counts['age_0_14' if age <= 14 else 'age_15_25' if age <= 25 else 'age_26_plus'] += 1
    return dict(counts, as_of=as_of.isoformat())
