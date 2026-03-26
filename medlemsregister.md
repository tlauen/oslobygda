---
layout: standard
title: Medlemsregister
permalink: /medlemsregister/
---

# Medlemsregister

Medlemsregisteret er tilgjengeleg for styret i Oslobygda kulturlag. Her kan du logge inn og handtere medlemsliste, betalingsstatus og GDPR-eksport/sletting.

{% if site.medlemsregister_url != nil and site.medlemsregister_url != "" %}
- **[Bli medlem]({{ site.medlemsregister_url }}/innmelding)** – offentleg innmeldingsskjema (registrerer i Bygdelista og MailerLite).
- **[Logg inn i medlemsregisteret]({{ site.medlemsregister_url }})** – for styret.
{% else %}
*Innlogging er ikkje sett opp enno. For å opne registeret på nett: set Flask-appen i drift frå mappa `medlemsregister/` på ei teneste (t.d. Render eller Fly.io), set eige domene til `medlemsregister.oslobygda.no`, og fyll ut `medlemsregister_url` i `_config.yml`. Sjå `medlemsregister/README.md` i repoet.*
{% endif %}
