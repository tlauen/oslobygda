"""Bygg berre validerte offentlege dokument til sjølvstendig HTML og PDF."""
import json
import sys
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'medlemsregister'))
from dokumentvising import render_document
from publisering import validate_envelope

def build():
    from playwright.sync_api import sync_playwright
    output=ROOT/'lutar/arsdokument'
    expected=set()
    with sync_playwright() as p:
        browser=p.chromium.launch()
        try:
            page=browser.new_page()
            for source in sorted((ROOT/'_data/arsdokument').glob('*.json')):
                data=json.loads(source.read_text());validate_envelope(data,int(source.stem))
                docs=list(data['versions'])+([data['ledger_latest']] if data['ledger_latest'] else [])
                for doc in docs:
                    if doc['kind'] in ('sakliste','motereglar','protokoll'): continue
                    version=doc['snapshot_number'] if doc['kind']!='arsmelding' else doc['version_id']
                    path=output/str(doc['report_year'])/f'{doc["kind"]}-{version}.html'
                    path.parent.mkdir(parents=True,exist_ok=True)
                    expected.update((path,path.with_suffix('.pdf')))
                    html=render_document(doc)
                    if not path.exists() or path.read_text()!=html or not path.with_suffix('.pdf').exists():
                        path.write_text(html)
                        page.goto(path.as_uri(),wait_until='networkidle')
                        page.evaluate('document.fonts.ready')
                        page.locator('img').evaluate_all('(images)=>Promise.all(images.map(img=>img.decode().catch(()=>{})))')
                        page.pdf(path=str(path.with_suffix('.pdf')),format='A4',print_background=True,prefer_css_page_size=True,display_header_footer=False)
        finally:browser.close()
    for path in output.glob('*/*'):
        if path.suffix in ('.html','.pdf') and path not in expected:path.unlink()

if __name__=='__main__':build()
