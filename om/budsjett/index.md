---
layout: standard
title: Budsjett
permalink: /om/budsjett/
---

<link rel="stylesheet" href="{{ '/lutar/offentleg-okonomi.css' | relative_url }}">
<p><a class="arsmelding-tilbake" href="{{ '/om/' | relative_url }}#arsmote"><span aria-hidden="true">←</span> Om laget</a></p>

# Budsjett

For kvart år viser me siste vedtekne budsjett, eller siste styreforslag dersom budsjettet ikkje er vedteke enno.

{% assign count = 0 %}
<ul>
{% if site.data.arsdokument %}{% assign years = site.data.arsdokument | sort %}{% for entry in years reversed %}{% assign budgets = entry[1].versions | where: 'kind', 'budsjett' %}{% if budgets.size > 0 %}{% assign count = count | plus: 1 %}<li><a href="{{ '/om/budsjett/' | append: entry[0] | append: '/' | relative_url }}">Budsjett {{ entry[0] | escape }}</a></li>{% endif %}{% endfor %}{% endif %}
</ul>
{% if count == 0 %}<p>Ingen budsjett er publiserte enno.</p>{% endif %}
