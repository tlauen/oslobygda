#!/usr/bin/env python3
"""
Publiser nye arrangement frå `_data/kalender.yml` til:
- https://www.folkarr.no/?cat=589752
- https://www.aktivioslo.no/registrer-arrangement/

Dette er ein "førsteversjon" som bruker nettlesarautomatisering (Playwright)
fordi desse sidene typisk ikkje har offentleg API.

Idempotens:
- Vi lagrar `uid` som er sendt per plattform i ei tilstandsfil.
- Køyr med `--dry-run` for å sjå mapping utan å sende.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Optional

import yaml


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CALENDER_YML = REPO_ROOT / "_data" / "kalender.yml"
DEFAULT_STATE_PATH = REPO_ROOT / "skript" / ".publish_events_state.json"
DEFAULT_IMAGE_FALLBACK = REPO_ROOT / "lutar" / "bilete" / "arr-cover.png"

FOLKARR_URL = "https://www.folkarr.no/?cat=589752"
AKTIVIOSLO_URL = "https://www.aktivioslo.no/registrer-arrangement/"

OSLOBYGDA_ORG = "Oslobygda kulturlag"
OSLOBYGDA_EMAIL = "folk@oslobygda.no"
FOLKARR_CONTACT_NAME = "Torbjørn Bergwitz Lauen"

OSLOBYGDA_LINK = "https://oslobygda.no/kalender/"


def _parse_yaml_events(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        raise FileNotFoundError(f"Fann ikkje YAML: {path}")
    with path.open("r", encoding="utf-8") as f:
        data = yaml.safe_load(f)
    if not isinstance(data, list):
        raise ValueError("Forventa at kalender.yml er ei liste av arrangementsobjekt.")
    return data


def _load_state(path: Path) -> dict[str, dict[str, Any]]:
    if not path.exists():
        return {"folkarr": {}, "aktivioslo": {}}
    with path.open("r", encoding="utf-8") as f:
        state = json.load(f)
    state.setdefault("folkarr", {})
    state.setdefault("aktivioslo", {})
    return state


def _save_state(path: Path, state: dict[str, dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + ".tmp")
    with tmp.open("w", encoding="utf-8") as f:
        json.dump(state, f, ensure_ascii=False, indent=2, sort_keys=True)
    tmp.replace(path)


def _to_ddmmyyyy(d: str) -> str:
    dt = datetime.strptime(d, "%Y-%m-%d").date()
    return dt.strftime("%d.%m.%Y")


def _to_aktivioslo_datetime(d: str, start_hhmm: str) -> str:
    """
    Aktiv i Oslo ser ut til å ta ein streng, men vi veit ikkje nøyaktig format.
    Vi brukar dd.mm.yyyy HH:MM - det er eit vanleg akseptert format.
    """
    dt = datetime.strptime(f"{d} {start_hhmm}", "%Y-%m-%d %H:%M")
    return dt.strftime("%d.%m.%Y %H:%M")


def _pick_image_file(event: dict[str, Any]) -> Path:
    bilete = str(event.get("bilete") or "").strip()
    if not bilete:
        return DEFAULT_IMAGE_FALLBACK

    # bilete ser typisk ut som "/lutar/bilete/arr-cover.png"
    basename = os.path.basename(bilete)
    if not basename:
        return DEFAULT_IMAGE_FALLBACK

    candidate = REPO_ROOT / "lutar" / "bilete" / basename
    if candidate.exists():
        return candidate

    # Fallback
    return DEFAULT_IMAGE_FALLBACK


def _default_folkarr_type(event: dict[str, Any], override: Optional[str]) -> str:
    if override:
        return override

    # Mesteparten av kalenderen dykkar er pøbb-arrangement => "Dansefest".
    # Vi kan gjere dette meir sofistikert etter at de har bekrefta kva kategori
    # de vil bruke for alle variantane (kved/kviss/etc).
    tittel = str(event.get("tittel") or "").lower()
    uid = str(event.get("uid") or "")

    if "kved" in uid or "kved" in tittel:
        return "Konsert"
    if "kviss" in uid or "kviss" in tittel:
        return "Konsert"
    return "Dansefest"


def _regex(s: str) -> re.Pattern[str]:
    return re.compile(re.escape(s), re.IGNORECASE)


def _wait_for_success(page, *, patterns: list[re.Pattern[str]]) -> bool:
    for pat in patterns:
        try:
            page.get_by_text(pat).first.wait_for(timeout=8000)
            return True
        except Exception:
            continue
    return False


@dataclass(frozen=True)
class Event:
    uid: str
    dato: str
    start: str
    slutt: str
    tittel: str
    stad: str
    merknad: str
    bilete: str

    @staticmethod
    def from_dict(d: dict[str, Any]) -> "Event":
        return Event(
            uid=str(d.get("uid") or "").strip(),
            dato=str(d.get("dato") or "").strip(),
            start=str(d.get("start") or "").strip(),
            slutt=str(d.get("slutt") or "").strip(),
            tittel=str(d.get("tittel") or "").strip(),
            stad=str(d.get("stad") or "").strip(),
            merknad=str(d.get("merknad") or "").strip(),
            bilete=str(d.get("bilete") or "").strip(),
        )


def _iter_new_events(
    events: Iterable[Event],
    state: dict[str, dict[str, Any]],
    platform: str,
    limit: Optional[int],
    *,
    min_dato: date,
) -> list[Event]:
    seen = state.get(platform, {})
    out: list[Event] = []
    for e in events:
        if not e.uid or not e.dato:
            continue
        try:
            e_date = datetime.strptime(e.dato, "%Y-%m-%d").date()
        except Exception:
            continue
        if e_date < min_dato:
            continue
        if e.uid in seen:
            continue
        out.append(e)
        if limit is not None and len(out) >= limit:
            break
    return out


def _fill_input_by_label(page, label_regex: re.Pattern[str], value: str) -> None:
    loc = page.get_by_label(label_regex).first
    loc.wait_for(state="visible", timeout=15000)
    loc.fill(value)


def _fill_textarea_by_label(page, label_regex: re.Pattern[str], value: str) -> None:
    loc = page.get_by_label(label_regex).first
    loc.wait_for(state="visible", timeout=15000)
    loc.fill(value)


def submit_folkarr(
    page,
    event: Event,
    *,
    folkarr_type: str,
    debug_dir: Path,
    dry_run: bool,
    submit: bool,
) -> bool:
    debug_dir.mkdir(parents=True, exist_ok=True)

    if dry_run:
        print(f"[folkarr][DRY] {event.uid}: {event.tittel} ({event.dato} {event.start})")
        return True

    image_path = _pick_image_file(
        {
            "bilete": event.bilete,
            "uid": event.uid,
            "tittel": event.tittel,
        }
    )

    page.goto(FOLKARR_URL, wait_until="domcontentloaded")

    _fill_input_by_label(page, re.compile(r"Namn\s+på\s+arrangement", re.I), event.tittel)
    _fill_input_by_label(page, re.compile(r"Dato\s+for\s+arrangement", re.I), _to_ddmmyyyy(event.dato))
    _fill_input_by_label(page, re.compile(r"Klokkeslett\s+for\s+arrangement", re.I), event.start)
    _fill_input_by_label(page, re.compile(r"Namn\s+på\s+arrangør", re.I), OSLOBYGDA_ORG)
    _fill_input_by_label(page, re.compile(r"Stad", re.I), event.stad)
    _fill_input_by_label(page, re.compile(r"Namn\s+på\s+kontaktperson", re.I), FOLKARR_CONTACT_NAME)
    _fill_input_by_label(page, re.compile(r"E-?post\s+til\s+kontaktperson", re.I), OSLOBYGDA_EMAIL)
    _fill_textarea_by_label(page, re.compile(r"Beskrivelse\s+av\s+arrangement", re.I), event.merknad)

    # Type arrangement (avkryssing).
    # Skjemaet sin HTML varierer litt; vi prøver fleire selector-strategiar.
    selected_type = False

    # 1) Standard: label -> input, så vi kan kalle `.check()`.
    try:
        type_pat = re.compile(rf"^{re.escape(folkarr_type)}$", re.I)
        type_loc = page.get_by_label(type_pat).first
        type_loc.wait_for(state="visible", timeout=15000)
        type_loc.check()
        selected_type = True
    except Exception:
        pass

    # 2) Fallback: klikk på element som inneheld teksten (typisk label/knapp).
    if not selected_type:
        try:
            type_text = page.get_by_text(folkarr_type, exact=True).first
            type_text.wait_for(state="visible", timeout=15000)
            type_text.click()
            selected_type = True
        except Exception:
            pass

    # 3) Siste fallback: delvis match.
    if not selected_type:
        try:
            type_text = page.get_by_text(re.compile(re.escape(folkarr_type), re.I)).first
            type_text.wait_for(state="visible", timeout=15000)
            type_text.click()
            selected_type = True
        except Exception:
            pass

    if not selected_type:
        raise RuntimeError(f"Klarte ikkje velje Folkarr type: {folkarr_type}")

    _fill_input_by_label(page, re.compile(r"Webside\s+for\s+meir\s+informasjon", re.I), OSLOBYGDA_LINK)

    # Illustrasjonsbilete (file input)
    file_input = page.locator('input[type="file"]').first
    file_input.wait_for(state="visible", timeout=15000)
    file_input.set_input_files(str(image_path))

    # Samtykke: "Ja, det er greit..."
    try:
        consent = page.get_by_label(re.compile(r"Ja,\s*det\s*er\s*greit", re.I))
        consent.first.check()
    except Exception:
        # Kan vere at den er pre-checka eller litt ulik labeltekst.
        pass

    # Preview: vi treng ikkje vente på submit-knapp.
    if not submit:
        try:
            page.screenshot(path=str(debug_dir / f"folkarr_preview_{event.uid}.png"), full_page=True)
        except Exception:
            pass
        return True

    # Send inn (reell innsending)
    submit_btn = page.locator('button[type="submit"]').first
    submit_btn.wait_for(state="visible", timeout=20000)
    submit_btn.click()

    # Heuristikk for suksess
    ok = _wait_for_success(
        page,
        patterns=[
            re.compile(r"takk", re.I),
            re.compile(r"send", re.I),
        ],
    )
    try:
        page.screenshot(path=str(debug_dir / f"folkarr_last_{event.uid}.png"), full_page=True)
    except Exception:
        pass
    return ok


def submit_aktivioslo(
    page,
    event: Event,
    *,
    debug_dir: Path,
    dry_run: bool,
    submit: bool,
    manual_datetime: bool,
) -> bool:
    debug_dir.mkdir(parents=True, exist_ok=True)

    if dry_run:
        print(f"[aktivioslo][DRY] {event.uid}: {event.tittel} ({event.dato} {event.start})")
        return True

    image_path = _pick_image_file(
        {
            "bilete": event.bilete,
            "uid": event.uid,
            "tittel": event.tittel,
        }
    )

    page.goto(AKTIVIOSLO_URL, wait_until="domcontentloaded")

    # Aktiv i Oslo-skjemaet har placeholders som er meir stabile enn aria-label.
    # Vi brukar substring-lokatorar for å sleppe å vere avhengig av eksakt "å"-teikn.

    date_dt = datetime.strptime(event.dato, "%Y-%m-%d").date()
    date_str = date_dt.strftime("%d.%m.%Y")
    time_str = event.start

    def try_fill_input_css(selector: str, value: str, *, timeout_ms: int = 15000) -> bool:
        try:
            loc = page.locator(selector).first
            loc.wait_for(state="visible", timeout=timeout_ms)
            loc.fill(value)
            return True
        except Exception:
            return False

    def try_fill_input_placeholder(ph_regex: re.Pattern[str] | str, value: str, *, timeout_ms: int = 15000) -> bool:
        try:
            loc = page.get_by_placeholder(ph_regex).first
            loc.wait_for(state="visible", timeout=timeout_ms)
            loc.fill(value)
            return True
        except Exception:
            return False

    def try_fill_textarea_css(selector: str, value: str, *, timeout_ms: int = 15000) -> bool:
        try:
            loc = page.locator(selector).first
            loc.wait_for(state="visible", timeout=timeout_ms)
            loc.fill(value)
            return True
        except Exception:
            return False

    # Arrangør (tosidig): placeholderar frå screenshot: "Navn" + "Epost".
    try_fill_input_css('input[placeholder="Navn"]', OSLOBYGDA_ORG)
    try_fill_input_css('input[placeholder*="Epost"]', OSLOBYGDA_EMAIL)

    # Tittel: placeholder "Navn på arrangement"
    try_fill_input_css('input[placeholder*="Navn på arrangement"]', event.tittel)

    # Dato: frå skjermbildet: "dd.mm.åååå", men unicode/kasing kan variere.
    # Bruk regex for å vere robust.
    date_ok = try_fill_input_placeholder(re.compile(r"dd\.\s*mm", re.I), date_str)
    if not date_ok:
        # Viss placeholder ikkje matchar i get_by_placeholder, prøv CSS (men aldri kast).
        date_ok = try_fill_input_css('input[placeholder^="dd.mm"]', date_str)

    # Tid: placeholder er "--:--" (ofte bokstavelig).
    time_ok = try_fill_input_placeholder("--:--", time_str)
    if not time_ok:
        time_ok = try_fill_input_css('input[placeholder*=":"]', time_str)

    # Basert på screenshot ser dato ut til å ha placeholder "mm/dd/yyyy".
    # Vi prøver derfor å setje dato/time i forhold til dato-inputen.
    if not date_ok or not time_ok:
        try:
            date_us = datetime.strptime(event.dato, "%Y-%m-%d").strftime("%m/%d/%Y")
            # 12-timers format som ofte blir vist i UI.
            time_12h = datetime.strptime(event.start, "%H:%M").strftime("%I:%M %p")
        except Exception:
            date_us = ""
            time_12h = event.start

        if date_us:
            date_us_ok = try_fill_input_css('input[placeholder="mm/dd/yyyy"]', date_us)
        else:
            date_us_ok = False

        try:
            date_input = page.locator('input[placeholder="mm/dd/yyyy"]').first
            date_input.wait_for(state="visible", timeout=15000)
            # Tids-inputen ligg typisk rett ved dato-inputen.
            time_input = date_input.locator("xpath=following::input[1]").first
            time_input.wait_for(state="visible", timeout=15000)
            # Bruk click + Ctrl+A + type (ofte meir robust for maskerte inputs).
            date_input.click()
            date_input.press("Control+A")
            date_input.type(date_us, delay=5)

            time_input.click()
            time_input.press("Control+A")
            time_input.type(time_12h, delay=5)

            # Blur: klikk ein annan input/textarea.
            try:
                page.locator('textarea[placeholder*="Beskriv"]').first.click()
            except Exception:
                pass

            if not submit:
                try:
                    date_after = date_input.input_value()
                    time_after = time_input.input_value()
                    print(
                        f"[aktivioslo][DEBUG] uid={event.uid} date_after='{date_after}' time_after='{time_after}'"
                    )
                except Exception:
                    pass

            time_ok = True
            date_ok = True
        except Exception:
            # La dato/time stå om vi ikkje treff.
            pass

    if not submit and (not date_ok or not time_ok):
        # Vi har preview, men dato/tid trefte ikkje. Ta screenshot for å
        # hjelpe vidare justering.
        try:
            page.screenshot(
                path=str(debug_dir / f"aktivioslo_preview_miss_{event.uid}.png"),
                full_page=True,
            )
        except Exception:
            pass

    # Ekstra debug: sjå dato/tid rett etter forsøket (før resten av felta).
    if not submit:
        try:
            page.screenshot(
                path=str(debug_dir / f"aktivioslo_preview_datetime_{event.uid}.png"),
                full_page=True,
            )
        except Exception:
            pass

    # Skildring / beskrivelse (textarea): placeholder inneheld "Beskriv"
    description = event.merknad
    if event.stad and event.stad.lower() not in description.lower():
        description = f"{event.merknad}\n\nStad: {event.stad}"
    try:
        try_fill_textarea_css('textarea[placeholder*="Beskriv"]', description)
    except Exception:
        pass

    # Lenke til meir informasjon / mer informasjon (ikkje billettsalg)
    try:
        try_fill_input_css('input[placeholder*="mer informasjon"]', OSLOBYGDA_LINK)
    except Exception:
        try:
            try_fill_input_css('input[placeholder*="meir informasjon"]', OSLOBYGDA_LINK)
        except Exception:
            # fallback: første input i "Linker"-seksjonen (kan variere mellom visningar)
            pass

    # Preview: ta screenshot etter fylte felt (før fil-opplasting/checkbox), så vi ser
    # om mappingen vår treffer. Vi gjer dette også om vi misser dato/tid,
    # for å få debug-data.
    if not submit:
        try:
            page.screenshot(path=str(debug_dir / f"aktivioslo_preview_fields_{event.uid}.png"), full_page=True)
        except Exception:
            pass

    # I preview-modus er det nok å sjå at felta blir fylt.
    # Vi lastar difor ikkje opp bilete og klikkar ikkje checkbox/send.
    if not submit:
        return True

    # Bilete
    file_input = page.locator('input[type="file"]').first
    file_input.wait_for(state="visible", timeout=15000)
    file_input.set_input_files(str(image_path))

    # Rettigheter til bilde (checkbox)
    try:
        # Fleire sider brukar label-tekst eller skjema-labellar; vi prøver tekst først.
        page.get_by_text(re.compile(r"Jeg godkjenner", re.I)).first.click()
    except Exception:
        try:
            consent = page.get_by_label(re.compile(r"godkjenner\s+at\s+bildet", re.I))
            consent.first.check()
        except Exception:
            pass

    if manual_datetime:
        print(
            f"[aktivioslo] PAUSE: Set dato/klokkeslett manuelt i nettlesaren for uid={event.uid}, "
            "og trykk Enter her for å sende inn."
        )
        try:
            input()
        except EOFError:
            pass
    try:
        submit_btn = page.get_by_role("button", name=re.compile(r"Send\s+inn", re.I)).first
        submit_btn.click()
    except Exception:
        submit_btn = page.locator('button[type="submit"]').first
        submit_btn.click()

    ok = _wait_for_success(
        page,
        patterns=[
            re.compile(r"takk", re.I),
            re.compile(r"send", re.I),
        ],
    )
    try:
        page.screenshot(path=str(debug_dir / f"aktivioslo_last_{event.uid}.png"), full_page=True)
    except Exception:
        pass
    return ok


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--calender-yml", default=str(DEFAULT_CALENDER_YML), help="Vegen til _data/kalender.yml")
    parser.add_argument("--state", default=str(DEFAULT_STATE_PATH), help="Tilstandsfil for idempotens")
    parser.add_argument("--platform", choices=["folkarr", "aktivioslo", "both"], default="both")
    parser.add_argument("--limit", type=int, default=None, help="Maks tal på nye arrangement (per plattform ved both)")
    parser.add_argument("--dry-run", action="store_true", help="Berre vis kva som ville blitt sendt")
    parser.add_argument("--preview", action="store_true", help="Fyller inn formular, men sender ikkje inn (tek screenshot).")
    parser.add_argument("--headed", action="store_true", help="Køyr ikkje-headless")
    parser.add_argument("--folkarr-type", default=None, help="Tving Folkarr kategori (t.d. Dansefest)")
    parser.add_argument("--manual-datetime", action="store_true", help="Stopp før innsending i Aktiv i Oslo slik at dato/klokkeslett kan setjast manuelt i browseren.")
    parser.add_argument("--from-date", default=None, help="Startdato for kva som skal publiserast (YYYY-MM-DD). Standard: i dag.")
    parser.add_argument("--include-past", action="store_true", help="Inkluderer arrangement før startdato (tilbakevendande).")
    parser.add_argument("--debug-dir", default=str(REPO_ROOT / "scripts" / ".publish_debug"))
    args = parser.parse_args()

    cal_path = Path(args.calender_yml)
    state_path = Path(args.state)
    debug_dir = Path(args.debug_dir)

    raw_events = _parse_yaml_events(cal_path)
    events = [Event.from_dict(d) for d in raw_events]

    # sorter etter dato/start slik at "først i tid" blir sendt fyrst
    def sort_key(e: Event):
        return (e.dato, e.start)

    events.sort(key=sort_key)

    state = _load_state(state_path)

    today = datetime.now().date()
    if args.include_past:
        min_dato = date.min
    elif args.from_date:
        min_dato = datetime.strptime(args.from_date, "%Y-%m-%d").date()
    else:
        min_dato = today

    if args.platform in ("folkarr", "both"):
        platform = "folkarr"
    else:
        platform = "aktivioslo"

    targets = []
    if args.platform in ("folkarr", "both"):
        targets.append("folkarr")
    if args.platform in ("aktivioslo", "both"):
        targets.append("aktivioslo")

    # Dry-run skal vere “browser-free” slik at du kan validere mapping utan
    # å starte Chromium / laste ned Playwright-binarar.
    if args.dry_run:
        for tgt in targets:
            new_events = _iter_new_events(events, state, tgt, args.limit, min_dato=min_dato)
            if not new_events:
                print(f"[{tgt}] Ingen nye event.")
                continue

            for e in new_events:
                if tgt == "folkarr":
                    folkarr_type = _default_folkarr_type(
                        event={"uid": e.uid, "tittel": e.tittel},  # minimal
                        override=args.folkarr_type,
                    )
                    image_path = _pick_image_file(
                        {"bilete": e.bilete, "uid": e.uid, "tittel": e.tittel}
                    )
                    print(
                        f"[folkarr][DRY] uid={e.uid} | "
                        f"type={folkarr_type} | dato={e.dato} kl={e.start} | "
                        f"stad={e.stad} | bilete={image_path.name}"
                    )
                else:
                    image_path = _pick_image_file(
                        {"bilete": e.bilete, "uid": e.uid, "tittel": e.tittel}
                    )
                    aktivio_dt = _to_aktivioslo_datetime(e.dato, e.start)
                    desc = e.merknad
                    if e.stad and e.stad.lower() not in desc.lower():
                        desc = f"{e.merknad}\n\nStad: {e.stad}"
                    print(
                        f"[aktivioslo][DRY] uid={e.uid} | "
                        f"dt={aktivio_dt} | stad={e.stad} | "
                        f"bilete={image_path.name} | desc_len={len(desc)}"
                    )

        print("Ferdig.")
        return

    from playwright.sync_api import sync_playwright

    def _resolve_executable_path(*, want_headless: bool) -> Optional[str]:
        """
        Finn eit executable_path frå Playwright si lokale cache.
        Dette unngår problem med at Cursor/sandbox får andre stiar.
        """
        home = Path.home()
        candidates: list[Path] = []

        if want_headless:
            candidates.extend(
                [
                    home
                    / "Library/Caches/ms-playwright/chromium_headless_shell-1208/chrome-headless-shell-mac-arm64/chrome-headless-shell",
                    home
                    / "Library/Caches/ms-playwright/chromium_headless_shell-1208/chrome-headless-shell-mac-x64/chrome-headless-shell",
                ]
            )
        else:
            candidates.extend(
                [
                    home
                    / "Library/Caches/ms-playwright/chromium-1208/chrome-mac-arm64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing",
                    home
                    / "Library/Caches/ms-playwright/chromium-1208/chrome-mac-x64/Google Chrome for Testing.app/Contents/MacOS/Google Chrome for Testing",
                ]
            )

        for c in candidates:
            try:
                if c.exists():
                    return str(c)
            except Exception:
                continue
        return None

    with sync_playwright() as p:
        executable_path = _resolve_executable_path(want_headless=not args.headed)
        launch_kwargs: dict[str, Any] = {}
        if executable_path:
            launch_kwargs["executable_path"] = executable_path
        browser = p.chromium.launch(headless=not args.headed, **launch_kwargs)
        context = browser.new_context()
        page = context.new_page()

        for tgt in targets:
            new_events = _iter_new_events(events, state, tgt, args.limit, min_dato=min_dato)
            if not new_events:
                print(f"[{tgt}] Ingen nye event.")
                continue

            for e in new_events:
                try:
                    if tgt == "folkarr":
                        folkarr_type = _default_folkarr_type(
                            event={"uid": e.uid, "tittel": e.tittel},  # minimal
                            override=args.folkarr_type,
                        )
                        ok = submit_folkarr(
                            page,
                            e,
                            folkarr_type=folkarr_type,
                            debug_dir=debug_dir / "folkarr",
                            dry_run=args.dry_run,
                            submit=not args.preview,
                        )
                        if ok and not args.preview:
                            state["folkarr"][e.uid] = {"submitted_at": datetime.utcnow().isoformat() + "Z"}
                            _save_state(state_path, state)
                    else:
                        ok = submit_aktivioslo(
                            page,
                            e,
                            debug_dir=debug_dir / "aktivioslo",
                            dry_run=args.dry_run,
                            submit=not args.preview,
                            manual_datetime=args.manual_datetime,
                        )
                        if ok and not args.preview:
                            state["aktivioslo"][e.uid] = {"submitted_at": datetime.utcnow().isoformat() + "Z"}
                            _save_state(state_path, state)
                except Exception as ex:
                    debug_path = debug_dir / tgt / f"error_{e.uid}.png"
                    try:
                        page.screenshot(path=str(debug_path), full_page=True)
                    except Exception:
                        pass
                    print(f"[{tgt}] FEIL for uid={e.uid}: {ex}", file=sys.stderr)
                    raise

        context.close()
        browser.close()

    print("Ferdig.")


if __name__ == "__main__":
    main()

