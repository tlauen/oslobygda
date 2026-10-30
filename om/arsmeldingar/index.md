---
layout: standard
title: Årsmeldingar
permalink: /om/arsmeldingar/
---

<link rel="stylesheet" href="{{ '/lutar/arsmelding.css' | relative_url }}">
<p><a class="arsmelding-tilbake" href="{{ '/om/' | relative_url }}#arsmote"><span aria-hidden="true">←</span> Om laget</a></p>

# Årsmeldingar

Her finn du publiserte årsmeldingar og sakspapir frå Oslobygda kulturlag.

{% assign published_count = 0 %}
<ul>
{% if site.data.arsdokument %}
{% assign report_years = site.data.arsdokument | sort %}
{% for entry in report_years reversed %}
  {% assign has_report = false %}
  {% for version in entry[1].versions %}
    {% if version.kind == 'arsmelding' %}{% assign has_report = true %}{% endif %}
  {% endfor %}
  {% if has_report %}
    {% assign published_count = published_count | plus: 1 %}
    <li><a href="{{ '/om/arsmeldingar/' | append: entry[0] | append: '/' | relative_url }}">Årsmelding {{ entry[0] | escape }}</a></li>
  {% endif %}
{% endfor %}
{% endif %}
</ul>
{% if published_count == 0 %}<p>Ingen årsmeldingar er publiserte enno.</p>{% endif %}
