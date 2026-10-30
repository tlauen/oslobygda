---
layout: standard
title: Rekneskap
permalink: /om/rekneskap/
---

<link rel="stylesheet" href="{{ '/lutar/offentleg-okonomi.css' | relative_url }}">
<p><a class="arsmelding-tilbake" href="{{ '/om/' | relative_url }}#arsmotesaker-tittel"><span aria-hidden="true">←</span> Om laget</a></p>

# Rekneskap

Løpande rekneskap er merkt **Førebels**. Sakspapir og godkjende årsrekneskap blir bevarte som faste versjonar.

{% assign count = 0 %}
<ul>
{% if site.data.arsdokument %}{% assign years = site.data.arsdokument | sort %}{% for entry in years reversed %}
{% assign fixed = entry[1].versions | where: 'kind', 'rekneskap' %}
{% if entry[1].ledger_latest or fixed.size > 0 %}{% assign count = count | plus: 1 %}<li><a href="{{ '/om/rekneskap/' | append: entry[0] | append: '/' | relative_url }}">Rekneskap {{ entry[0] | escape }}</a></li>{% endif %}
{% endfor %}{% endif %}
</ul>
{% if count == 0 %}<p>Ingen rekneskap er publisert enno.</p>{% endif %}
