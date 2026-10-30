"""Intern betalingsimport. Manuelle val er skilde frå opt-in vedlikehald."""
import click
from flask import abort,redirect,render_template,request,session
from arsdokument import today
from database import managed_db
from betalingsimport import PaymentImport
from vipps_client import VippsError


def install_payment_import(app,get_db,require_admin):
    service=PaymentImport(get_db);app.extensions['payment_import']=service

    @app.route('/okonomi/betalingar',methods=['GET','POST'])
    @require_admin
    def payment_import_index():
        error=None;status=200
        if request.method=='POST':
            try:
                action=request.form.get('action');actor=session['board_username']
                if action=='configure':
                    enabled=request.form.get('enabled')=='yes'
                    if enabled and request.form.get('confirmed')!='yes': raise ValueError('Stadfest at opningsbalanse og historiske føringar er kontrollerte.')
                    service.configure(enabled,request.form.get('from_day'),actor)
                else:
                    pid=int(request.form.get('payment_id',''))
                    if action=='attest':
                        if request.form.get('confirmed')!='yes': raise ValueError('Stadfest kjeldekontrollen.')
                        service.attest(pid,request.form.get('day'),request.form.get('account'),request.form.get('note'),actor)
                    elif action=='fetch': service.fetch(pid,actor)
                    elif action=='book':
                        if request.form.get('no_duplicate')!='yes': raise ValueError('Stadfest at betalinga ikkje alt er bokført, heller ikkje som del av ein samla post.')
                        service.book(pid,request.form.get('evidence_id'),actor,True)
                    elif action=='link': service.link(pid,request.form.get('evidence_id'),int(request.form.get('journal_id','')),actor)
                    else: raise ValueError('Ugyldig handling.')
                try: app.extensions['public_ledger'].refresh_enabled(actor)
                except ValueError: app.logger.warning('Offentleg kø krev kontroll etter betalingsimport.')
                return redirect(app.jinja_env.globals['prefix_url']('payment_import_index')+('?betaling='+str(int(request.form['payment_id']))+'#betaling-'+str(int(request.form['payment_id'])) if request.form.get('payment_id','').isdigit() else ''))
            except (ValueError,VippsError,TypeError) as exc: error=str(exc);status=400
        with managed_db(get_db) as db:
            rows=[]
            for payment in db.execute('SELECT p.*,m.full_name AS member_name FROM payments p LEFT JOIN members m ON m.id=p.member_id ORDER BY p.id DESC LIMIT 200'):
                item=dict(payment)
                try:
                    _,order=service._source(db,payment['id']);item['order']=order
                    evidence=db.execute('SELECT * FROM payment_evidence WHERE payment_id=? ORDER BY revision DESC LIMIT 1',(payment['id'],)).fetchone()
                    item['evidence']=dict(evidence) if evidence else None
                    item['linked']=service._linked(db,payment['id'])
                    item['candidates']=service._candidates(db,payment,evidence) if evidence else []
                    item['problem']=''
                    if item['linked']:
                        journal=db.execute('SELECT day FROM ledger_journals WHERE id=?',(item['linked'],)).fetchone()
                        if not journal or (evidence and journal['day']!=evidence['day']): item['problem']='Bokført dato avvik frå kjeldedato. Rett med sporbar korrigering.'
                        if db.execute('SELECT 1 FROM ledger_journals WHERE reversal_of=?',(item['linked'],)).fetchone(): item['problem']='Kopla post er reversert. Manuell avstemming er nødvendig.'
                    if evidence and evidence['refunded_ore']: item['problem']='Vipps-refusjon observert. Kontroller og registrer refusjon mot originalposten.'
                    err=db.execute('SELECT message FROM payment_import_errors WHERE payment_id=?',(payment['id'],)).fetchone()
                    if err and not item['problem']: item['problem']=err[0]
                except ValueError as exc:
                    item.update(order=None,evidence=None,linked=None,candidates=[],problem=str(exc))
                rows.append(item)
            settings=db.execute('SELECT * FROM payment_import_settings WHERE id=1').fetchone()
        return render_template('betalingsimport.html',rows=rows,settings=settings,error=error,today=today().isoformat()),status

    @app.cli.command('importer-medlemsbetalingar')
    @click.option('--hent-vipps',is_flag=True,help='Les produksjonsstatus og hendingslogg frå Vipps. Ingen trekk/refusjon.')
    @click.option('--limit',default=50,type=click.IntRange(min=1,max=200))
    def payment_import_command(hent_vipps,limit):
        """Bokfør kvalifiserte medlemsinntekter berre etter aktivering i Bygdelista."""
        counts=service.run(fetch=hent_vipps,limit=limit)
        app.extensions['public_ledger'].refresh_enabled()
        click.echo(f"Kjeldekontroller: {counts['checked']}; bokførte: {counts['booked']}; til kontroll: {counts['review']}.")
