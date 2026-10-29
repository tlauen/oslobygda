import unittest
from post_sporsmal import post_values

class QuestionMappingTests(unittest.TestCase):
    def test_membership_and_gifts_choose_correct_accounting_without_manual_type(self):
        for purpose in ('membership','donations'):
            base=dict(guided='yes',purpose=purpose,category='wrong-hidden-value',payment_method='vipps')
            for state,kind in [('waiting','income'),('settled_new','vipps_income_settled'),('settled_booked','vipps_settlement')]:
                mapped=post_values(dict(base,vipps_state=state))
                self.assertEqual(mapped['kind'],kind);self.assertEqual(mapped['category'],purpose)
                self.assertEqual(mapped['account'],'vipps')
            self.assertEqual(post_values(dict(base,payment_method='bank'))['kind'],'income')

    def test_expenses_and_repayments(self):
        for paid,kind in [('private','private_expense'),('unpaid','invoice'),('bank','expense'),('cash','expense')]:
            self.assertEqual(post_values(dict(guided='yes',purpose='expense',expense_paid=paid))['kind'],kind)
        self.assertEqual(post_values(dict(guided='yes',purpose='repayment'))['kind'],'private_refund')

    def test_incomplete_answers_are_rejected_by_server(self):
        for answers in ({},{'purpose':'membership'},{'purpose':'membership','payment_method':'vipps'},
                        {'purpose':'expense'},{'purpose':'other_income','payment_method':'bank','category':'membership'}):
            with self.assertRaises(ValueError):post_values(dict(answers,guided='yes'))
