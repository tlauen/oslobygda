---
layout: standard
title: Budsjett
permalink: /om/budsjett/
---

# Budsjett

Styreforslag og vedtekne budsjett blir viste som eigne faste versjonar.

{% assign count = 0 %}
<ul>
{% if site.data.arsdokument %}{% assign years = site.data.arsdokument | sort %}{% for entry in years reversed %}{% assign budgets = entry[1].versions | where: 'kind', 'budsjett' %}{% if budgets.size > 0 %}{% assign count = count | plus: 1 %}<li><a href="{{ '/om/budsjett/' | append: entry[0] | append: '/' | relative_url }}">Budsjett {{ entry[0] | escape }}</a></li>{% endif %}{% endfor %}{% endif %}
</ul>
{% if count == 0 %}<p>Ingen budsjett er publiserte enno.</p>{% endif %}
