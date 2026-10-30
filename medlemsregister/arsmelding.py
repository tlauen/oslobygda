"""Strukturert årsmelding. Kjeldeimport skal ikkje overskrive redaksjonelle val."""
from copy import deepcopy
from datetime import date
import json
import uuid

FIELDS = ('dato', 'tittel', 'stad', 'merknad')
STATUSES = {'unconfirmed': 'Ikkje stadfesta', 'completed': 'Gjennomført', 'cancelled': 'Avlyst'}


def report_from(doc):
    report = json.loads(doc['report_json'])
    if not report:
        report = dict(intro=doc['body'], organization='', conclusion='', activities=[], source_revision=None,
                      membership=None)
    return report


def bounded(value, maximum=3000):
    value = str(value or '').strip()
    if len(value) > maximum:
        raise ValueError(f'Teksten er for lang (maks {maximum} teikn).')
    return value


def merge_calendar(report, events, report_year, source_revision):
    result = deepcopy(report)
    selected = []
    seen = set()
    for event in events:
        try:
            day = date.fromisoformat(str(event.get('dato', '')))
        except ValueError:
            raise ValueError('Kalenderen inneheld ein ugyldig dato. Ingen import er lagra.') from None
        if day.year != report_year:
            continue
        uid = str(event.get('uid', ''))
        if not uid or uid in seen:
            raise ValueError('Kalenderen har manglande eller duplisert UID for året.')
        seen.add(uid)
        source = {key: bounded(event.get(key), 3000 if key == 'merknad' else 500) for key in FIELDS}
        cancelled = event.get('avlyst') is True or 'AVLYST' in source['tittel'].upper()
        selected.append((uid, source, cancelled))
    existing = {item['uid']: item for item in result['activities'] if item.get('origin') == 'calendar'}
    for item in existing.values():
        item['source_missing'] = item['uid'] not in seen
    for uid, source, cancelled in selected:
        if uid in existing:
            item = existing[uid]
            item['source_changed'] = item.get('source_changed', False) or item['source'] != source or item.get('source_cancelled', False) != cancelled
            item['source'] = source
            item['source_cancelled'] = cancelled
            item['source_missing'] = False
        else:
            result['activities'].append(dict(key=uuid.uuid4().hex, uid=uid, origin='calendar', source=source,
                                             source_cancelled=cancelled, source_missing=False, source_changed=False,
                                             included=True, status='cancelled' if cancelled else 'unconfirmed',
                                             comment='', participants=None))
    result['source_revision'] = source_revision
    return result


def edit_report(report, form):
    result = deepcopy(report)
    for key in ('hero_title','activities_title','organization_title','conclusion_title'):
        if key in form: result[key] = bounded(form.get(key),200)
    for key in ('intro', 'organization', 'conclusion'):
        result[key] = bounded(form.get(key), 30000 if key == 'intro' else 10000)
    for item in result['activities']:
        prefix = 'activity_' + item['key'] + '_'
        item['included'] = form.get(prefix + 'included') == 'yes'
        item['status'] = form.get(prefix + 'status', 'unconfirmed')
        if item['status'] not in STATUSES:
            raise ValueError('Ugyldig gjennomføringsstatus.')
        if prefix+'display_title' in form: item['display_title']=bounded(form.get(prefix+'display_title'),500)
        item['comment'] = bounded(form.get(prefix + 'comment'))
        number = form.get(prefix + 'participants', '').strip()
        if number and (not number.isdecimal() or not 0 <= int(number) <= 1000000):
            raise ValueError('Deltakartal må vere eit heiltal mellom 0 og 1 000 000.')
        item['participants'] = int(number) if number else None
        if item['origin'] == 'manual':
            item['source'] = {key: bounded(form.get(prefix + key), 3000 if key == 'merknad' else 500) for key in FIELDS}
            date.fromisoformat(item['source']['dato'])
            if not item['source']['tittel']:
                raise ValueError('Manuell aktivitet må ha tittel.')
    return result


def add_manual(report, form, report_year):
    result = deepcopy(report)
    source = {key: bounded(form.get('manual_' + key), 3000 if key == 'merknad' else 500) for key in FIELDS}
    if date.fromisoformat(source['dato']).year != report_year or not source['tittel']:
        raise ValueError('Aktiviteten må ha tittel og dato i rapportåret.')
    result['activities'].append(dict(key=uuid.uuid4().hex, uid=None, origin='manual', source=source,
                                     source_missing=False, source_changed=False, source_cancelled=False,
                                     included=True, status='unconfirmed', comment='', participants=None))
    return result


def compose(report):
    sections = [report['intro']]
    if report.get('membership'):
        item = report['membership']
        label = 'Medlemmar' if item.get('includes_free') else 'Medlemmar med registrert betaling'
        sections.append(f"{label} for medlemsåret {item['year']}: {item['count']}.\n"
                        + ('Medlemer med «Gratis» ved uttrekket er med; ikkje medlemstal ved årsskiftet.' if item.get('includes_free') else 'Dette er eit betalingstal, ikkje medlemstal ved årsskiftet.'))
    ages = (report.get('membership') or {}).get('ages')
    if ages:
        sections.append(f"Aldersfordeling av registrerte medlemer ved uttrekk: 0–14 år: {ages['age_0_14']}, "
                        f"15–25 år: {ages['age_15_25']}, 26+ år: {ages['age_26_plus']}, ukjend alder: {ages['unknown']}. "
                        f"Alder rekna per {ages['as_of']}. Dette er ikkje historisk medlemstal ved årsskiftet.")
    activities = [item for item in report['activities'] if item['included']]
    if activities:
        sections.append(report.get('activities_title') or 'Aktivitetar gjennom året')
    for item in sorted(activities, key=lambda a: (a['source']['dato'], a['source']['tittel'], a['key'])):
        source = item['source']
        lines = [f"{source['dato']} – {item.get('display_title') or source['tittel']}", STATUSES[item['status']]]
        if source['stad']: lines.append(source['stad'])
        if source['merknad']: lines.append(source['merknad'])
        if item['participants'] is not None: lines.append(f"Omlag {item['participants']} gjestar.")
        if item['comment']: lines.append(item['comment'])
        sections.append('\n'.join(lines))
    if report.get('board'):
        sections.append('Styret i '+str(report['board']['year'])+'\n'+'\n'.join(p['rolle']+': '+p['namn'] for p in report['board']['people']))
    if report['organization']: sections.append((report.get('organization_title') or 'Styret og organisasjonen')+'\n' + report['organization'])
    if report['conclusion']: sections.append((report.get('conclusion_title') or 'Avslutning')+'\n' + report['conclusion'])
    return '\n\n'.join(section for section in sections if section)


def check_ready(report,allow_unconfirmed=False):
    for item in report['activities']:
        if item['included'] and item['status'] == 'unconfirmed' and not allow_unconfirmed:
            raise ValueError('Stadfest status for alle valde aktivitetar før du lagrar ein godkjend årsversjon.')
        if item['included'] and (item.get('source_missing') or item.get('source_changed')):
            raise ValueError('Kontroller og stadfest endra eller fjerna kalenderoppføringar før du lagrar ein godkjend årsversjon.')
