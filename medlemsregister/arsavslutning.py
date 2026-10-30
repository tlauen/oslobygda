"""Gjeremålsliste basert på dei same saldoane og kontrollane som årslåsen."""
from rekneskap import ACCOUNTS,balances

HELP={
'bank':('Kontroller bankkontoen','Finn kontoutskrifta per 31. desember. Skriv saldoen på kontoen, ikkje overskotet for året.'),
'vipps':('Kontroller pengar hos Vipps','Finn kor mykje Vipps enno ikkje hadde betalt vidare til banken per 31. desember. Skriv 0 dersom alt var oppgjort.'),
'cash':('Tel kontantane','Skriv kor mykje kontantar laget hadde ved årsslutt. Pengar som alt er betalte vidare via Vipps skal ikkje teljast her òg.'),
'private':('Kontroller private utlegg','Summer det laget framleis skulda alle som hadde lagt ut privat per 31. desember. Ta ikkje med utlegg som alt var refunderte.'),
'payable':('Kontroller ubetalte rekningar','Summer registrerte leverandørrekningar som enno ikkje var betalte ved årsslutt.'),
'prepaid':('Kontroller kostnader for seinare år','Samanlikn med oversikta over betalte kostnader som er fordelte til seinare år.'),
'receivable':('Kontroller pengar andre skuldar laget','Samanlikn med oversikta over ubetalte krav laget hadde ved årsslutt.')}

def closing_checklist(db,year):
    end=f'{year}-12-31';totals=balances(db,end)
    revision=db.execute("SELECT COALESCE(MAX(id),0) FROM ledger_journals WHERE state='posted'").fetchone()[0]
    rows=[]
    for account,(title,help_text) in HELP.items():
        expected=totals.get(account,0)*(-1 if ACCOUNTS[account][1]=='liability' else 1)
        if account not in ('bank','vipps','private') and expected==0:continue
        latest=db.execute("SELECT * FROM ledger_reconciliations WHERE year=? AND day=? AND account=? AND party='' ORDER BY id DESC LIMIT 1",(year,end,account)).fetchone()
        state='missing'
        if latest:
            state='difference' if latest['actual_ore']!=latest['book_ore'] else ('stale' if latest['ledger_revision']!=revision else 'done')
        rows.append(dict(account=account,title=title,help=help_text,expected=expected,state=state,latest=latest))
    opening=bool(db.execute('SELECT 1 FROM ledger_years WHERE year<=? AND opening_confirmed=1',(year,)).fetchone())
    earlier=bool(db.execute('SELECT 1 FROM ledger_years WHERE year<? AND closed=0',(year,)).fetchone())
    return dict(rows=rows,done=sum(r['state']=='done' for r in rows),total=len(rows),opening=opening,earlier=earlier,ready=opening and not earlier and all(r['state']=='done' for r in rows))
