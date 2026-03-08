---
layout: default
title: Medlemsregister
permalink: /medlemsregister/
---

# Medlemsregister

Medlemsregisteret er tilgjengeleg for styret i Oslobygda kulturlag. Her kan du logge inn og handtere medlemsliste, betalingsstatus og GDPR-eksport/sletting.

{% if site.medlemsregister_url != nil and site.medlemsregister_url != "" %}
- **[Bli medlem]({{ site.medlemsregister_url }}/innmelding)** – offentleg innmeldingsskjema (registrerer i Bygdelista og MailerLite).
- **[Logg inn i medlemsregisteret]({{ site.medlemsregister_url }})** – for styret.
{% else %}
*Innlogging er ikkje satt opp enno. For å opne registeret på nett: deploy Flask-appen i mappa `medlemsregister/` til ein teneste (t.d. Render eller Fly.io), sett custom domain til `medlemsregister.oslobygda.no`, og fyll ut `medlemsregister_url` i `_config.yml`. Sjå `medlemsregister/README.md` i repoet.*
{% endif %}
