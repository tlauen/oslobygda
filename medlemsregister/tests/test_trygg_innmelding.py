from contextlib import closing
from unittest.mock import patch, Mock
import unittest
import os
from cryptography.fernet import Fernet
from flask import Flask, request
from werkzeug.middleware.proxy_fix import ProxyFix

import app as module
from database import managed_db
import test_ny_innmelding as signup_fixtures
import test_styre_auth as auth_fixtures
from totp_kryptering import migrate, protect, reveal


class EditTests(unittest.TestCase):
    setUp = auth_fixtures.BoardAuthTests.setUp
    tearDown = auth_fixtures.BoardAuthTests.tearDown
    token = auth_fixtures.BoardAuthTests.token
    fields = signup_fixtures.SignupTests.fields
    service = signup_fixtures.SignupTests.service
    new = signup_fixtures.SignupTests.new

    def test_corrected_contact_and_amount_survive_payment_creation(self):
        ref=self.new()
        self.service.edit(ref,self.fields(email='corrected@example.org',phone='88888888',amount='200'))
        order=self.service.order(ref)
        self.assertEqual(order['email'],'corrected@example.org')
        self.assertEqual(order['amount_ore'],20000)
        with patch('ny_innmelding.client_for') as factory:
            factory.return_value.create.return_value={'redirectUrl':'https://api.vipps.no/pay'}
            self.service.create(ref,'https://example.org/status')
            self.assertEqual(factory.return_value.create.call_args.args[1],20000)
        with self.assertRaises(ValueError):self.service.edit(ref,self.fields())

    def test_uncertain_create_blocks_edits_even_with_new_status(self):
        ref=self.new()
        with managed_db(module.get_db) as db:
            db.execute('UPDATE signup_orders SET create_attempted=1')
        with self.assertRaises(ValueError):self.service.edit(ref,self.fields())
        self.assertEqual(self.service.order(ref)['status'],'new')

    def test_edit_ownership_csrf_and_display(self):
        with patch.dict(os.environ,{'VIPPS_SIGNUP_MODE':'test'}),patch('ny_innmelding.credentials',return_value={'VIPPS_MSN':'123456'}):
            self.client.post('/bli-medlem',data={**self.fields(),'csrf_token':self.token()})
            self.assertEqual(module.app.test_client().get('/bli-medlem/rediger').status_code,404)
            self.assertEqual(self.client.post('/bli-medlem/rediger',data=self.fields()).status_code,400)
            page=self.client.get('/bli-medlem/status').get_data(as_text=True)
            self.assertIn('test@example.org',page)
            self.assertIn('Feil e-postadresse? Endre her.',page)
            response=self.client.post('/bli-medlem/rediger',data={**self.fields(email='changed@example.org'),'csrf_token':self.token()})
            self.assertEqual(response.status_code,303)
            self.assertIn('changed@example.org',self.client.get('/bli-medlem/status').get_data(as_text=True))


class TotpEncryptionTests(unittest.TestCase):
    setUp = auth_fixtures.BoardAuthTests.setUp
    tearDown = auth_fixtures.BoardAuthTests.tearDown
    login = auth_fixtures.BoardAuthTests.login
    token = auth_fixtures.BoardAuthTests.token

    def test_existing_totp_migrates_and_login_works_without_rotating_secret(self):
        with patch.dict(os.environ,{'MEDLEMSREGISTER_TOTP_KEY':Fernet.generate_key().decode()}):
            with managed_db(module.get_db) as db:migrate(db)
            with managed_db(module.get_db) as db:
                stored=db.execute('SELECT totp_secret FROM board_users').fetchone()[0]
            self.assertNotEqual(stored,self.secret)
            self.assertEqual(reveal(stored),self.secret)
            self.assertEqual(self.login().status_code,302)
            with patch.dict(os.environ,{'MEDLEMSREGISTER_TOTP_KEY':Fernet.generate_key().decode()}):
                with self.assertRaises(RuntimeError):reveal(stored)
            with patch.dict(os.environ,{'MEDLEMSREGISTER_TOTP_KEY':''}):
                with self.assertRaises(RuntimeError):reveal(stored)

    def test_bad_key_rolls_back_all_migrations_and_enrollment_is_encrypted(self):
        key=Fernet.generate_key().decode()
        with patch.dict(os.environ,{'MEDLEMSREGISTER_TOTP_KEY':key}):
            encrypted=protect(self.secret)
            with managed_db(module.get_db) as db:
                db.execute("INSERT INTO board_enrollment VALUES ('id',99,'e@example.org','hash',?,9999999999,0,0)",(encrypted,))
            with patch.dict(os.environ,{'MEDLEMSREGISTER_TOTP_KEY':Fernet.generate_key().decode()}):
                with self.assertRaises(RuntimeError):
                    with managed_db(module.get_db) as db:migrate(db)
            with managed_db(module.get_db) as db:
                self.assertEqual(db.execute('SELECT totp_secret FROM board_users').fetchone()[0],self.secret)
            with managed_db(module.get_db) as db:migrate(db)
            self.assertEqual(reveal(encrypted),self.secret)


class EncryptedRegistrationTests(unittest.TestCase):
    token=auth_fixtures.BoardAuthTests.token
    def setUp(self):
        import test_styre_registrering
        test_styre_registrering.RegistrationTests.setUp(self)
    def tearDown(self):
        import test_styre_registrering
        test_styre_registrering.RegistrationTests.tearDown(self)
    def test_enrollment_qr_and_completed_account_keep_secret_encrypted(self):
        import pyotp
        with patch.dict(os.environ,{'MEDLEMSREGISTER_TOTP_KEY':Fernet.generate_key().decode()}):
            with managed_db(module.get_db) as db:migrate(db)
            self.client.post('/registrer',data={'email':'board@example.org','csrf_token':self.token()})
            module.app.extensions['auth_mail'].process()
            self.client.post('/registrer/stadfest',data={'email_code':self.send.call_args.args[1],'csrf_token':self.token()})
            self.assertEqual(self.client.get('/registrer/konto').status_code,200)
            with managed_db(module.get_db) as db:
                stored=db.execute('SELECT totp_secret FROM board_enrollment').fetchone()[0]
            self.assertTrue(stored.startswith('enc:v1:'))
            response=self.client.post('/registrer/konto',data={'password':'a very long new password','confirmation':'a very long new password','code':pyotp.TOTP(reveal(stored)).now(),'csrf_token':self.token()})
            self.assertEqual(response.status_code,200)
            with managed_db(module.get_db) as db:
                self.assertEqual(db.execute("SELECT totp_secret FROM board_users WHERE username='board@example.org'").fetchone()[0],stored)


class EncryptedResetTests(unittest.TestCase):
    token=auth_fixtures.BoardAuthTests.token
    def setUp(self):
        import test_passord_reset
        test_passord_reset.PasswordResetTests.setUp(self)
    def tearDown(self):
        import test_passord_reset
        test_passord_reset.PasswordResetTests.tearDown(self)
    def test_reset_validates_encrypted_totp_without_changing_it(self):
        import pyotp
        with patch.dict(os.environ,{'MEDLEMSREGISTER_TOTP_KEY':Fernet.generate_key().decode()}):
            with managed_db(module.get_db) as db:migrate(db)
            self.client.post('/gløymt-passord',data={'email':'board@example.org','csrf_token':self.token()})
            module.app.extensions['auth_mail'].process()
            response=self.client.post('/gløymt-passord/byt',data={'email_code':self.send.call_args.args[1],'password':'a new sufficiently long password','confirmation':'a new sufficiently long password','code':pyotp.TOTP(self.secret).now(),'csrf_token':self.token()})
            self.assertEqual(response.status_code,200)
            with managed_db(module.get_db) as db:
                stored=db.execute('SELECT totp_secret FROM board_users').fetchone()[0]
            self.assertTrue(stored.startswith('enc:v1:'))
            self.assertEqual(reveal(stored),self.secret)


class TotpSetupTests(unittest.TestCase):
    def test_existing_key_is_preserved_and_never_printed(self):
        import contextlib, io, tempfile
        from pathlib import Path
        import konfigurer_totp
        from dotenv import dotenv_values
        with tempfile.TemporaryDirectory() as folder:
            env=Path(folder)/'.env';env.write_text('OTHER=value\n')
            output=io.StringIO()
            with patch.object(konfigurer_totp,'__file__',str(Path(folder)/'konfigurer_totp.py')),contextlib.redirect_stdout(output):
                konfigurer_totp.main()
                first=env.read_text()
                key=dotenv_values(env)['MEDLEMSREGISTER_TOTP_KEY']
                konfigurer_totp.main()
                self.assertEqual(env.read_text(),first)
            self.assertNotIn(key,output.getvalue())
            self.assertEqual(env.stat().st_mode & 0o777,0o600)


class ProxyTests(unittest.TestCase):
    def test_last_proxy_value_is_used_and_other_headers_are_not_trusted(self):
        app=Flask(__name__)
        app.wsgi_app=ProxyFix(app.wsgi_app,x_for=1,x_proto=0)
        @app.get('/')
        def view():return {'ip':request.remote_addr,'scheme':request.scheme,'host':request.host}
        client=app.test_client()
        for ip in ('192.0.2.1','192.0.2.2'):
            result=client.get('/',headers={'X-Forwarded-For':'forged, '+ip,'X-Forwarded-Proto':'https','X-Forwarded-Host':'evil.example'},environ_base={'REMOTE_ADDR':'10.0.0.1'}).get_json()
            self.assertEqual(result,{'ip':ip,'scheme':'http','host':'localhost'})
