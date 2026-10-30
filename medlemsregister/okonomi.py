"""Styret sitt interne økonomigrensesnitt og lokale driftskommandoar."""
from io import BytesIO
import os
from pathlib import Path
import sqlite3
import uuid

import click
from flask import abort, redirect, render_template, request, send_file, session, jsonify, flash

from arsdokument import today
from database import managed_db
from rekneskap import Ledger, ACCOUNTS, balances, year_balances, now
from bilag import store_receipt, verified_receipt, receipt_lock
from offentleg_rekneskap import PublicLedger
from publisering import Publisher, PublicationError


def install_ledger(app,get_db,require_admin,db_path):
    service=Ledger(get_db)
    app.extensions['ledger']=service
    public_service=PublicLedger(get_db)
    app.extensions['public_ledger']=public_service
    publisher=Publisher(get_db,public_service)
    import json
    app.jinja_env.globals['category_notes']=json.loads((Path(__file__).resolve().parent.parent/'_data'/'rekneskapskategoriar.json').read_text())
    app.jinja_env.globals['balance_notes']=json.loads((Path(__file__).resolve().parent.parent/'_data'/'balanseforklaringar.json').read_text())
    app.extensions['document_publisher']=publisher
    app.config.setdefault('BILAG_DIR',os.environ.get('BYGDELISTA_BILAG_DIR',str(Path.home()/'bygdelista-data'/'bilag')))

    @app.get('/arsmote/hjelp')
    @require_admin
    def annual_help():
        response=app.make_response(render_template('arsmote_hjelp.html'))
        response.headers['Cache-Control']='no-store'
        return response

    def receipt_dir():
        root=Path(app.config['BILAG_DIR']).expanduser().resolve()
        repo=Path(__file__).resolve().parent.parent
        if root==repo or repo in root.parents:
            raise ValueError('Bilag må lagrast utanfor kode- og nettsidemappene.')
        return root

    @app.before_request
    def ledger_request_limit():
        limit={'ledger_upload':20*1024*1024,'annual_document':1024*1024,
               'budget_editor':256*1024}.get(request.endpoint,65536)
        if request.content_length and request.content_length>limit: abort(413)

    from dokumentvising import tidspunkt as lesbart_tidspunkt
    app.jinja_env.filters['lesbart_tidspunkt']=lesbart_tidspunkt
    app.jinja_env.filters['kroner']=lambda value: f'{value/100:,.2f}'.replace(',',' ').replace('.',',')+' kr'

    @app.get('/okonomi/foringsstatus')
    @require_admin
    def ledger_post_status():
        try: selected=int(request.args.get('year',today().year))
        except ValueError: abort(400)
        if not 1900<=selected<=2200: abort(400)
        with managed_db(get_db) as db:
            first=db.execute('SELECT MIN(year) FROM ledger_years WHERE opening_confirmed=1').fetchone()[0]
            closed=bool(db.execute('SELECT 1 FROM ledger_years WHERE year>=? AND closed=1',(selected,)).fetchone())
        reason=('Stadfest inngåande balanse før du bokfører den første posten.' if first is None else
                ('Datoen er før det første opningsåret.' if selected<first else
                 ('Rekneskapsåret er avslutta. Opne året att før du bokfører.' if closed else '')))
        response=jsonify(ready=not reason,reason=reason)
        response.headers['Cache-Control']='no-store'
        return response

    @app.route('/okonomi',methods=['GET','POST'])
    @require_admin
    def ledger_index():
        error=None;status=200
        try: selected=int(request.values.get('year',today().year))
        except ValueError: abort(400)
        if not 1900<=selected<=2200: abort(400)
        parts={'oversikt','registrer','bilag','postar','kontroll'}
        active_part=request.args.get('del','oversikt')
        if active_part not in parts: abort(400)
        action_parts={'post':'registrer','attach':'bilag','reverse':'postar','periodize':'kontroll','reconcile':'kontroll','close':'kontroll','reopen':'kontroll','opening':'oversikt','opening_correction':'oversikt'}
        if request.method=='POST':
            try:
                actor=session['board_username'];action=request.form.get('action');key=request.form.get('request_key','')
                active_part=action_parts.get(action,active_part)
                if action=='post':
                    from post_sporsmal import post_values
                    post_id=service.post(post_values(request.form),actor,key)
                    flash(f'Post P{post_id} er bokført. Du kan registrere ein ny post.','bokfort')
                elif action in ('opening','opening_correction'):
                    service.opening(selected,request.form,request.form.get('party'),request.form.get('note'),actor,key,correction=action=='opening_correction')
                elif action=='attach':
                    service.attach(int(request.form.get('journal_id','')),int(request.form.get('receipt_id','')),actor)
                elif action=='reverse':
                    service.reverse(int(request.form.get('journal_id','')),request.form.get('day'),request.form.get('reason'),actor,key)
                elif action=='reconcile':
                    service.reconcile(selected,request.form.get('day'),request.form.get('account'),request.form.get('actual'),
                                      request.form.get('party'),request.form.get('note'),actor)
                elif action in ('close','reopen'):
                    service.year_state(selected,action=='close',request.form.get('reason'),actor)
                elif action=='periodize':
                    service.periodize(int(request.form.get('journal_id','')),request.form.get('start'),request.form.get('end'),actor,key)
                else: raise ValueError('Ugyldig handling.')
                try: public_service.refresh_enabled(actor)
                except (ValueError,sqlite3.DatabaseError): app.logger.warning('Offentleg økonomikø må kontrollerast. Intern bokføring er lagra.')
                return redirect(app.jinja_env.globals['prefix_url']('ledger_index')+'?year='+str(selected)+'&del='+active_part+('#registrer-post' if action=='post' else ('&bilagdel=knytt' if action=='attach' else '')))
            except (ValueError,sqlite3.IntegrityError) as exc:
                error=str(exc) if isinstance(exc,ValueError) else 'Posten kunne ikkje lagrast. Kontroller at kjelda ikkje er bokført frå før og at året er ope.'
                status=400
        with managed_db(get_db) as db:
            journals=db.execute("SELECT * FROM ledger_journals WHERE state='posted' AND day BETWEEN ? AND ? ORDER BY day DESC,id DESC",(f'{selected}-01-01',f'{selected}-12-31')).fetchall()
            lines={row['id']:db.execute('SELECT * FROM ledger_lines WHERE journal_id=?',(row['id'],)).fetchall() for row in journals}
            receipts=db.execute('SELECT * FROM ledger_receipts ORDER BY id DESC').fetchall()
            attachments={row['id']:db.execute('SELECT receipt_id FROM ledger_attachments WHERE journal_id=?',(row['id'],)).fetchall() for row in journals}
            totals=year_balances(db,selected);ending=balances(db,f'{selected}-12-31')
            result=-sum(amount for account,amount in totals.items() if ACCOUNTS[account][1] in ('income','expense'))
            parties=db.execute('''SELECT l.account,l.party,SUM(l.amount_ore) amount_ore FROM ledger_lines l
                JOIN ledger_journals j ON j.id=l.journal_id WHERE j.state='posted' AND j.day<=?
                AND l.account IN ('private','payable') GROUP BY l.account,l.party''',(f'{selected}-12-31',)).fetchall()
            reconciliations=db.execute('SELECT * FROM ledger_reconciliations WHERE year=? ORDER BY id DESC',(selected,)).fetchall()
            year_row=db.execute('SELECT * FROM ledger_years WHERE year=?',(selected,)).fetchone()
            opening_exists=db.execute('SELECT 1 FROM ledger_years WHERE opening_confirmed=1 LIMIT 1').fetchone()
            from arsavslutning import closing_checklist
            closing=closing_checklist(db,selected)
            has_public_version=bool(db.execute('SELECT 1 FROM public_ledger_versions WHERE year=? LIMIT 1',(selected,)).fetchone())
        return render_template('okonomi.html',year=selected,journals=journals,lines=lines,receipts=receipts,totals=totals,
                               ending=ending,result=result,parties=parties,attachments=attachments,reconciliations=reconciliations,year_row=year_row,
                               opening_exists=opening_exists,accounts=ACCOUNTS,key=(request.form.get('request_key','').split('-')[0] or uuid.uuid4().hex),
                               error=error,values=request.form,ledger_part=active_part,closing=closing,has_public_version=has_public_version,public_year_allowed=selected<=today().year),status

    @app.route('/okonomi/offentleg/<int:year>',methods=['GET','POST'])
    @require_admin
    def public_ledger_preview(year):
        error=None;status=200
        if not 1900<=year<=today().year: abort(400)
        if request.method=='POST':
            try:
                actor=session['board_username'];action=request.form.get('action')
                if action in ('activate','freeze'):
                    if request.form.get('confirmed')!='yes': raise ValueError('Stadfest at innhaldet er kontrollert for offentleg publisering.')
                    if request.form.get('as_of')!=min(today().isoformat(),f'{year}-12-31'):
                        raise ValueError('Rapportdatoen er endra. Sjå førehandsvisinga på nytt.')
                    if action=='activate': vid=public_service.activate(year,actor,request.form.get('revision'))
                    else: vid=public_service.freeze(year,request.form.get('status'),request.form.get('meeting_year'),request.form.get('decision_date'),actor,request.form.get('revision'))
                    from publisering import publish_from_button
                    publish_from_button(app,('ledger','rekneskap-'+str(vid)))
                elif action=='publish':
                    if request.form.get('confirmed')!='yes': raise ValueError('Stadfest at dokumentet kan publiserast.')
                    vid=int(request.form.get('version_id',''))
                    with managed_db(get_db) as db:
                        if not db.execute('SELECT 1 FROM public_ledger_versions WHERE id=? AND year=?',(vid,year)).fetchone(): raise ValueError('Vel ein versjon frå dette året.')
                    from publisering import publish_from_button
                    publish_from_button(app,('ledger','rekneskap-'+str(vid)))
                elif action=='pause':
                    with managed_db(get_db) as db:
                        db.execute('BEGIN IMMEDIATE')
                        db.execute('UPDATE public_ledger_settings SET enabled=0,actor=?,updated_at=? WHERE year=?',(actor,now(),year))
                        db.execute("UPDATE public_ledger_queue SET status='superseded' WHERE status IN ('pending','failed','sending') AND version_id IN (SELECT id FROM public_ledger_versions WHERE year=? AND status='provisional')",(year,))
                else: raise ValueError('Ugyldig handling.')
                return redirect(app.jinja_env.globals['prefix_url']('public_ledger_preview',year=year))
            except (ValueError,TypeError) as exc: error=str(exc);status=400
        try: preview=public_service.preview(year)
        except ValueError as exc: abort(409,str(exc))
        with managed_db(get_db) as db:
            enabled=db.execute('SELECT enabled FROM public_ledger_settings WHERE year=?',(year,)).fetchone()
            jobs=db.execute('''SELECT v.id,v.status document_status,v.payload,q.status,q.attempts,q.last_error
                FROM public_ledger_versions v JOIN public_ledger_queue q ON q.version_id=v.id
                WHERE v.year=? ORDER BY v.id DESC LIMIT 30''',(year,)).fetchall()
        return render_template('offentleg_rekneskap.html',report=preview,error=error,enabled=bool(enabled and enabled[0]),jobs=jobs,has_public_version=bool(jobs),public_year_allowed=True),status

    @app.route('/okonomi/offentleg/versjon/<int:version_id>')
    @require_admin
    def public_ledger_version(version_id):
        import json
        with managed_db(get_db) as db:
            row=db.execute('SELECT payload FROM public_ledger_versions WHERE id=?',(version_id,)).fetchone()
            if not row: abort(404)
        return render_template('offentleg_rekneskap.html',report=json.loads(row[0]),fixed=True,jobs=[])

    @app.cli.command('publiser-arsdokument')
    @click.option('--limit',default=20,type=click.IntRange(min=1,max=100))
    def publish_documents(limit):
        """Send offentlege køjobbar til GitHub og kontroller offentleg datafil."""
        try: result=publisher.run(limit=limit)
        except (ValueError,sqlite3.DatabaseError) as exc: raise click.ClickException(str(exc)) from None
        click.echo(f"Publisering: lagra {result['stored']}, synlege {result['visible']}, feila {result['failed']}, oppteken {result['busy']}.")
        if result['failed']: raise click.ClickException('Publiseringskøa har feil. Kontroller intern oversikt og prøv igjen.')

    @app.route('/okonomi/bilag',methods=['POST'])
    @require_admin
    def ledger_upload():
        upload=request.files.get('file')
        if not upload: abort(400,'Vel eit bilag.')
        try:
            replaces=int(request.form['replaces_id']) if request.form.get('replaces_id') else None
            receipt_id=store_receipt(get_db,receipt_dir(),upload,session['board_username'],replaces,request.form.get('reason',''))
        except (ValueError,OSError) as exc:
            abort(400,str(exc) if isinstance(exc,ValueError) else 'Bilaget kunne ikkje lagrast. Kontroller diskplass og tilgang.')
        if request.accept_mimetypes.best=='application/json':
            with managed_db(get_db) as db:
                row=db.execute('SELECT original_name FROM ledger_receipts WHERE id=?',(receipt_id,)).fetchone()
            return jsonify(id=receipt_id,name=row['original_name']),201
        return redirect(app.jinja_env.globals['prefix_url']('ledger_index')+'?del=bilag')

    @app.route('/okonomi/bilag/<int:receipt_id>')
    @require_admin
    def ledger_receipt(receipt_id):
        with managed_db(get_db) as db:
            row=db.execute('SELECT * FROM ledger_receipts WHERE id=?',(receipt_id,)).fetchone()
            if not row: abort(404)
        try:
            with receipt_lock(receipt_dir()): data=verified_receipt(receipt_dir(),row)
        except (OSError,ValueError): abort(409,'Bilaget manglar eller har feil kontrollsum. Kontroller backup før vidare bruk.')
        response=send_file(BytesIO(data),mimetype=row['media_type'],download_name=row['original_name'],as_attachment=True)
        response.headers['Cache-Control']='no-store'
        return response

    @app.cli.command('okonomi-backup')
    @click.option('--directory',required=True,type=click.Path(path_type=Path))
    @click.option('--keep',default=30,type=click.IntRange(min=1))
    def backup_command(directory,keep):
        """Lag verifisert, lokal backup av database og bilag (ikkje kryptert)."""
        from okonomi_backup import create_bundle
        try:
            result=create_bundle(db_path(),receipt_dir(),directory,keep,include_board=True)
        except (ValueError,OSError,sqlite3.DatabaseError,RuntimeError) as exc:
            raise click.ClickException(str(exc)) from None
        click.echo(f'Samla backup og gjenopprettingsprøve OK: {result}')

    @app.cli.command('okonomi-verifiser-backup')
    @click.argument('directory',type=click.Path(exists=True,path_type=Path))
    def verify_command(directory):
        from okonomi_backup import verify_bundle_restore
        try: verify_bundle_restore(directory)
        except (ValueError,OSError,sqlite3.DatabaseError,RuntimeError) as exc: raise click.ClickException(str(exc)) from None
        click.echo('Gjenopprettingsprøve med database og bilag: OK.')

    @app.cli.command('okonomi-kontroller-bilag')
    def receipt_check():
        """Kontroller bilag og tel foreldrelause filer; slettar ingenting."""
        from bilag import file_path
        with receipt_lock(receipt_dir(),exclusive=True) as root:
            with managed_db(get_db) as db: rows=db.execute('SELECT * FROM ledger_receipts').fetchall()
            known={row['file_key'] for row in rows};bad=0
            for row in rows:
                try: verified_receipt(root,row)
                except (OSError,ValueError): bad+=1
            orphans=sum(1 for path in root.iterdir() if not path.name.startswith('.') and path.name not in known)
        click.echo(f'Bilag: {len(rows)}. Manglande/endra: {bad}. Ukjende filer: {orphans}. Ingen filer sletta.')
        if bad: raise click.ClickException('Bilagskontrollen feila.')


    @app.cli.command('okonomi-krypter-backup')
    @click.argument('directory',type=click.Path(exists=True,path_type=Path))
    @click.option('--output',required=True,type=click.Path(path_type=Path))
    def encrypt_backup_command(directory,output):
        """Lag kryptert fil for manuell ekstern backup. Ingen opplasting."""
        from kryptert_backup import encrypt_bundle
        password=click.prompt('Eiga backuppassfrase (minst 16 teikn)',hide_input=True,confirmation_prompt=True)
        try: result=encrypt_bundle(directory,output,password)
        except (ValueError,OSError,RuntimeError) as exc: raise click.ClickException(str(exc)) from None
        click.echo(f'Kryptert backup og faktisk gjenopprettingsprøve OK: {result}')

    @app.cli.command('okonomi-prove-kryptert-backup')
    @click.argument('path',type=click.Path(exists=True,path_type=Path))
    def verify_encrypted_command(path):
        """Prøv dekryptering og gjenoppretting isolert; rør aldri aktiv database."""
        from kryptert_backup import verified_archive
        password=click.prompt('Backuppassfrase',hide_input=True)
        try:
            with verified_archive(path,password): pass
        except (ValueError,OSError,RuntimeError) as exc: raise click.ClickException(str(exc)) from None
        click.echo('Dekryptering og gjenopprettingsprøve: OK. Aktiv database er uendra.')
