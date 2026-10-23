import unittest
import app as module
import test_styre_auth as fixtures


class PaymentRuleTests(unittest.TestCase):
    token = fixtures.BoardAuthTests.token

    def setUp(self):
        fixtures.BoardAuthTests.setUp(self)
        self.assertEqual(fixtures.BoardAuthTests.login(self).status_code,302)
        with module.get_db() as db:
            cur = db.execute('''INSERT INTO members(full_name,fornamn,etternamn,email,membership_type,payment_status,consent_at,created_at,updated_at)
                VALUES ('Test Member','Test','Member','test@example.org','vanleg','ikkje betalt','2026','2026','2026')''')
            self.mid=cur.lastrowid

    def tearDown(self):
        fixtures.BoardAuthTests.tearDown(self)

    def member(self):
        with module.get_db() as db:
            return dict(db.execute('SELECT * FROM members WHERE id=?',(self.mid,)).fetchone())

    def pay(self, amount):
        return self.client.post(f'/api/members/{self.mid}/payments',json={'amount_nok':amount},headers={'X-CSRF-Token':self.token()})

    def threshold(self, amount):
        return self.client.put('/api/innstillingar/kontingent',json={'superkul_grense_nok':amount},headers={'X-CSRF-Token':self.token()})

    def test_payment_marks_paid_and_uses_cumulative_total(self):
        self.assertEqual(self.pay('4').status_code,201)
        self.assertEqual(self.member()['payment_status'],'betalt')
        self.assertEqual(self.member()['membership_type'],'vanleg')
        self.assertEqual(self.pay('1').status_code,201)
        self.assertEqual(self.member()['membership_type'],'vanleg')
        self.assertEqual(self.pay('0,01').status_code,201)
        self.assertEqual(self.member()['membership_type'],'kul')

    def test_board_is_manual_but_payment_status_updates(self):
        with module.get_db() as db:
            db.execute("UPDATE members SET membership_type='styret' WHERE id=?",(self.mid,))
        self.assertEqual(self.pay('100').status_code,201)
        self.assertEqual(self.member()['membership_type'],'styret')
        self.assertEqual(self.member()['payment_status'],'betalt')
        self.assertEqual(self.threshold('200').status_code,200)
        self.assertEqual(self.member()['membership_type'],'styret')

    def test_threshold_recalculates_existing_current_payments_and_persists(self):
        self.pay('10')
        self.assertEqual(self.member()['membership_type'],'kul')
        self.assertEqual(self.threshold('10').status_code,200)
        self.assertEqual(self.member()['membership_type'],'vanleg')
        module.init_db()
        self.assertEqual(self.client.get('/api/innstillingar/kontingent').json['superkul_grense_ore'],1000)
        self.assertEqual(self.threshold('0').status_code,200)
        self.assertEqual(self.member()['membership_type'],'kul')

    def test_old_year_not_counted_and_unpaid_free_status_preserved(self):
        with module.get_db() as db:
            year=module._get_medlemsbetalingsar(db)
            db.execute("INSERT INTO payments(member_id,amount_ore,paid_at,created_at,for_year) VALUES (?,100000,'2025','2025',?)",(self.mid,year-1))
            db.execute("UPDATE members SET payment_status='gratis' WHERE id=?",(self.mid,))
        self.threshold('5')
        self.assertEqual(self.member()['payment_status'],'gratis')
        self.pay('5')
        self.assertEqual(self.member()['payment_status'],'betalt')
        self.assertEqual(self.member()['membership_type'],'vanleg')

    def test_backfills_existing_payments(self):
        with module.get_db() as db:
            year=module._get_medlemsbetalingsar(db)
            db.execute("INSERT INTO payments(member_id,amount_ore,paid_at,created_at,for_year) VALUES (?,501,'2026','2026',?)",(self.mid,year))
        module.init_db()
        self.assertEqual(self.member()['payment_status'],'betalt')
        self.assertEqual(self.member()['membership_type'],'kul')

    def test_invalid_amounts_and_access_controls(self):
        for amount in ('NaN','Infinity','-1','0','0.001','foo',True):
            self.assertEqual(self.pay(amount).status_code,400)
        with module.get_db() as db:
            self.assertEqual(db.execute('SELECT COUNT(*) FROM payments').fetchone()[0],0)
        for amount in ('NaN','-1','0.001','foo'):
            self.assertEqual(self.threshold(amount).status_code,400)
        self.assertEqual(self.client.put('/api/innstillingar/kontingent',json={'superkul_grense_nok':'10'}).status_code,400)
        anonymous=module.app.test_client()
        self.assertEqual(anonymous.get('/api/innstillingar/kontingent',headers={'Accept':'application/json'}).status_code,401)

    def remove(self, pid, mid=None):
        return self.client.delete(f'/api/members/{mid or self.mid}/payments/{pid}', headers={'X-CSRF-Token':self.token()})

    def test_delete_recalculates_sum_type_and_status(self):
        first=self.pay('5').json['id']
        last=self.pay('100').json['id']
        self.assertEqual(self.remove(last).status_code,200)
        self.assertEqual(self.member()['membership_type'],'vanleg')
        self.assertEqual(self.member()['payment_status'],'betalt')
        self.assertEqual(self.remove(first).status_code,200)
        self.assertEqual(self.member()['payment_status'],'ikkje betalt')
        self.assertEqual(self.member()['membership_type'],'vanleg')
        self.assertEqual(self.remove(first).status_code,404)

    def test_delete_preserves_board_and_protects_archive_and_other_members(self):
        with module.get_db() as db:
            db.execute("UPDATE members SET membership_type='styret' WHERE id=?",(self.mid,))
        pid=self.pay('100').json['id']
        self.assertEqual(self.remove(pid,mid=self.mid+999).status_code,404)
        self.assertEqual(self.remove(pid).status_code,200)
        self.assertEqual(self.member()['membership_type'],'styret')
        self.assertEqual(self.member()['payment_status'],'ikkje betalt')
        pid=self.pay('5').json['id']
        with module.get_db() as db:
            year=module._get_medlemsbetalingsar(db)
            db.execute('UPDATE payments SET for_year=? WHERE id=?',(year-1,pid))
        self.assertEqual(self.remove(pid).status_code,409)
        with module.get_db() as db:
            self.assertIsNotNone(db.execute('SELECT id FROM payments WHERE id=?',(pid,)).fetchone())
        self.assertEqual(self.client.delete(f'/api/members/{self.mid}/payments/{pid}').status_code,400)
