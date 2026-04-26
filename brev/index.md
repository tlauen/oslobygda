---
layout: standard
title: Meld deg på nyhendebrevet
brevo_skjema: true
---

# Nyhendebrev frå Oslobygda kulturlag

<p class="kjeks-merknad">Skjemaet brukar kjeks (leverandør Brevo). <a href="{{ '/personvern/' | relative_url }}">Les meir om kjeks og personvern</a>.</p>

{% if site.brevo_newsletter_form_url != nil and site.brevo_newsletter_form_url != "" %}
{% include brevo-skjema-nyhendebrev.html %}
{% else %}
<p><em>Brevo-skjema for nyhendebrev er ikkje sett opp enno. Legg inn <code>brevo_newsletter_form_url</code> i <code>_config.yml</code>.</em></p>
{% endif %}

## Nerde-greier:

- **Komande tilskipingar (tekst)**: <a href="{{ '/api/tilskipingar.txt' | absolute_url }}">{{ '/api/tilskipingar.txt' | absolute_url }}</a>
- **Komande tilskipingar (JSON)**: <a href="{{ '/api/tilskipingar.json' | absolute_url }}">{{ '/api/tilskipingar.json' | absolute_url }}</a>
- **Tekstgenerator (manuell backup)**: <a href="{{ '/brev/tekstgenerator/' | absolute_url }}">{{ '/brev/tekstgenerator/' | absolute_url }}</a>
- **Førehandvising av epost** <a href="{{ '/skript/forehandsvising_nyhendebrev.html' | absolute_url }}">{{ '/skript/forehandsvising_nyhendebrev.html' | absolute_url }}</a>
- **Kalender**: <a href="{{ '/kalender/' | absolute_url }}">{{ '/kalender/' | absolute_url }}</a>
- **Kalender (ICS)**: <a href="{{ '/kalender.ics' | absolute_url }}">{{ '/kalender.ics' | absolute_url }}</a>