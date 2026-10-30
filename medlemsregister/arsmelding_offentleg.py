"""Eksplisitt offentleg presentasjon; ingen interne kjeldefelt eller brukarhistorikk."""
import re
from datetime import date

def presentation(report):
    value={key:report.get(key,'') for key in ('intro','organization','conclusion','hero_title','activities_title','organization_title','conclusion_title')}
    value['activities']=[]
    for item in report.get('activities',[]):
        if not item['included']:continue
        source=item['source']
        value['activities'].append(dict(date=source['dato'],title=item.get('display_title') or source['tittel'],place=source['stad'],description=source['merknad'],status=item['status'],comment=item['comment'],guests=item['participants']))
    member=report.get('membership')
    value['membership_count']=member['count'] if member else None
    if member and member.get('ages'):
        value['ages'] = dict(member['ages'])
    if member and member.get('includes_free'):
        value['includes_free'] = True
    board=report.get('board')
    value['board']=[{k:person.get(k,'') for k in ('namn','rolle','bilete','bilete_posisjon')} for person in board['people']] if board else []
    validate_presentation(value)
    return value

def validate_presentation(value):
    textfields=('intro','organization','conclusion','hero_title','activities_title','organization_title','conclusion_title')
    if not isinstance(value,dict) or set(value)-{'ages','includes_free'}!=set(textfields)|{'activities','membership_count','board'}:raise ValueError('Ugyldig offentleg årsmeldingspresentasjon.')
    if any(not isinstance(value[k],str) or len(value[k])>30000 for k in textfields):raise ValueError('Ugyldig offentleg tekst.')
    if 'ages' in value:
        ages = value['ages']
        if not isinstance(ages, dict) or set(ages) != {'age_0_14','age_15_25','age_26_plus','unknown','as_of'}:
            raise ValueError('Ugyldig aldersfordeling.')
        if any(type(ages[k]) is not int or ages[k] < 0 for k in ('age_0_14','age_15_25','age_26_plus','unknown')):
            raise ValueError('Ugyldige alderstal.')
        date.fromisoformat(ages['as_of'])
    if 'includes_free' in value and type(value['includes_free']) is not bool:
        raise ValueError('Ugyldig medlemsgrunnlag.')
    count=value['membership_count']
    if count is not None and (type(count) is not int or count<0):raise ValueError('Ugyldig medlemstal.')
    if not isinstance(value['activities'],list) or not isinstance(value['board'],list):raise ValueError('Ugyldig offentleg liste.')
    for item in value['activities']:
        if not isinstance(item,dict) or set(item)!={'date','title','place','description','status','comment','guests'}:raise ValueError('Ugyldig offentleg tilskiping.')
        if any(not isinstance(item[k],str) or len(item[k])>30000 for k in ('date','title','place','description','status','comment')):raise ValueError('Ugyldig tilskipingstekst.')
        date.fromisoformat(item['date'])
        if item['status'] not in ('completed','cancelled','unconfirmed'):raise ValueError('Ugyldig tilskipingsstatus.')
        if item['guests'] is not None and (type(item['guests']) is not int or not 0<=item['guests']<=1000000):raise ValueError('Ugyldig gjesteoverslag.')
    for person in value['board']:
        if not isinstance(person,dict) or set(person) not in ({'namn','rolle','bilete'},{'namn','rolle','bilete','bilete_posisjon'}) or any(not isinstance(x,str) for x in person.values()):raise ValueError('Ugyldig offentleg styremedlem.')
        if person['bilete'] and not re.fullmatch(r'/lutar/bilete/styret/[^/]+\.(jpg|jpeg|png|webp)',person['bilete'],re.I):raise ValueError('Ugyldig offentleg portrettsti.')
        if person.get('bilete_posisjon') and not re.fullmatch(r'(center|top|bottom|left|right|\d+%)( (center|top|bottom|left|right|\d+%))?',person['bilete_posisjon']):raise ValueError('Ugyldig biletplassering.')
