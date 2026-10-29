import unittest
from styremodul import load_board,ROOT

class BoardModuleTests(unittest.TestCase):
    def test_year_specific_public_board_and_existing_portraits(self):
        board=load_board(2026)
        self.assertEqual(board['year'],2026)
        self.assertEqual(len(board['people']),3)
        for person in board['people']:
            self.assertTrue(person['namn']);self.assertTrue(person['rolle'])
            self.assertTrue((ROOT/person['bilete'].lstrip('/')).is_file())
        with self.assertRaises(ValueError):load_board(1900)
