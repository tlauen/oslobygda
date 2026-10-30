import unittest
from datetime import date
from aldersfordeling import age_distribution


class AgeDistributionTests(unittest.TestCase):
    def test_boundaries_unknown_and_future(self):
        rows = [{'birth_date': x} for x in ['2012-12-31', '2011-12-31', '2001-12-31', '2000-12-31', None, 'invalid', '2027-01-01']]
        self.assertEqual(age_distribution(rows, date(2026, 12, 31)), dict(age_0_14=1, age_15_25=2, age_26_plus=1, unknown=3, as_of='2026-12-31'))

    def test_before_birthday(self):
        result = age_distribution([{'birth_date': '2011-11-01'}], date(2026, 10, 31))
        self.assertEqual(result['age_0_14'], 1)
