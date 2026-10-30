"""Éin offentleg dokumentmal for nett, intern førehandvising og PDF-bygg."""
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo
from jinja2 import Environment,FileSystemLoader,select_autoescape

ROOT=Path(__file__).resolve().parent
MONTHS=('januar','februar','mars','april','mai','juni','juli','august','september','oktober','november','desember')

def tidspunkt(value,med_klokkeslett=True):
    try:
        moment=datetime.fromisoformat(str(value).replace('Z','+00:00'))
        if moment.tzinfo: moment=moment.astimezone(ZoneInfo('Europe/Oslo'))
        return f'{moment.day}. {MONTHS[moment.month-1]} {moment.year}'+(f' kl. {moment:%H:%M}' if med_klokkeslett else '')
    except ValueError:return str(value or '')

def structured(payload):
    p=payload.get('presentation')
    if not p:return None
    result={k:v for k,v in p.items() if k not in ('activities','board','membership_count')}
    result['activities']=[dict(included=True,source=dict(dato=a['date'],tittel=a['title'],stad=a['place'],merknad=a['description']),status=a['status'],comment=a['comment'],participants=a['guests']) for a in p['activities']]
    result['membership']=dict(count=p['membership_count'],year=payload['report_year']) if p['membership_count'] is not None else None
    if result['membership'] is not None and p.get('ages'):
        result['membership']['ages'] = p['ages']
    # Eldre offentlege eksportar mangla utsnitt. Bruk same offentlege årskjelde
    # som Om laget, berre når både person og bilete stemmer.
    import yaml
    board_file=ROOT.parent/'_data/styre.yml'
    reference=yaml.safe_load(board_file.read_text()).get('ar',{}).get(str(payload['report_year']),[]) if board_file.exists() else []
    people=[]
    for person in p['board']:
        old=next((r for r in reference if r.get('namn')==person['namn'] and r.get('bilete')==person['bilete']),{})
        people.append(dict(person,bilete_posisjon=person.get('bilete_posisjon') or old.get('bilete_posisjon','center')))
    result['board']=dict(year=payload['report_year'],people=people) if people else None
    return result

def render_document(payload):
    # Valider før noko HTML blir laga; berre den offentlege eksporten er tillaten.
    from publisering import validate_document
    if payload.get('kind')=='rekneskap' and payload.get('version_id')=='preview':
        from offentleg_rekneskap import validate_ledger
        validate_ledger(payload,allow_preview=True)
    else:validate_document(payload)
    env=Environment(loader=FileSystemLoader(ROOT/'malar'),autoescape=select_autoescape(['html']))
    env.filters['kroner']=lambda value:f'{value/100:,.2f}'.replace(',',' ').replace('.',',')+' kr'
    env.filters['lesbart_tidspunkt']=tidspunkt
    env.globals['prefix_url']=lambda endpoint,**kw: 'https://oslobygda.no/lutar/bilete/styret/'+kw['filename'] if endpoint=='annual_board_photo' else ''
    env.globals['category_notes']=__import__('json').loads((ROOT.parent/'_data/rekneskapskategoriar.json').read_text())
    env.globals['balance_notes']=__import__('json').loads((ROOT.parent/'_data/balanseforklaringar.json').read_text())
    html=env.get_template('arsmote_utskrift.html').render(kind=payload['kind'],report=payload,title=payload.get('title',f'Rekneskap {payload["report_year"]}'),structured_report=structured(payload))
    import re
    html=re.sub(r'<link rel="stylesheet" href="">','',html)
    styles='\n'.join((ROOT/'fast'/name).read_text() for name in ('arsmote-utskrift.css','arsmelding-tilskipingar.css'))
    return html.replace('</head>','<!-- arsmote-utskrift.css + arsmelding-tilskipingar.css --><style>'+styles+'</style></head>')
