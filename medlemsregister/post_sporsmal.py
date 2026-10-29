"""Omset menneskelege svar til dei eksisterande, validerte føringstypane."""
def post_values(form):
    values=dict(form)
    if form.get('guided')!='yes': return values
    purpose=form.get('purpose')
    if purpose!='other':
        for name in ('payment_id','event_uid','original_id'):
            values.pop(name,None)
    if purpose in ('membership','donations','other_income'):
        payment=form.get('payment_method')
        if payment not in ('vipps','bank','cash'): raise ValueError('Vel korleis pengane vart betalte.')
        values.update(kind='income',account=payment)
        if purpose in ('membership','donations'):values['category']=purpose
        elif values.get('category') not in ('grants','event_income','interest','other_income'):
            raise ValueError('Vel kva innkoma gjeld.')
        if payment=='vipps':
            state=form.get('vipps_state')
            if state not in ('waiting','settled_new','settled_booked'):raise ValueError('Vel om Vipps har betalt pengane vidare, og om innkoma alt er registrert.')
            if state=='settled_new':
                if purpose not in ('membership','donations'):raise ValueError('For denne innkometypen: registrer innkoma til Vipps først, og overføringa separat.')
                values['kind']='vipps_income_settled'
            elif state=='settled_booked':values['kind']='vipps_settlement'
    elif purpose=='expense':
        paid=form.get('expense_paid')
        if paid=='private':values['kind']='private_expense'
        elif paid=='unpaid':values['kind']='invoice'
        elif paid in ('bank','cash','vipps'):values.update(kind='expense',account=paid)
        else:raise ValueError('Vel kven som betalte utgifta, eller at rekninga ikkje er betalt.')
    elif purpose=='repayment':values['kind']='private_refund'
    elif purpose=='pay_invoice':values['kind']='pay_invoice'
    elif purpose=='other':pass
    else:raise ValueError('Vel kva du ønskjer å registrere.')
    return values
