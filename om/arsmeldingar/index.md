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
<ul class="arsdokument-oversikt">
{% if site.data.arsdokument %}
{% assign report_years = site.data.arsdokument | sort %}
{% for entry in report_years reversed %}
  {% assign has_report = false %}
  {% for version in entry[1].versions %}
    {% if version.kind == 'arsmelding' %}{% assign has_report = true %}{% endif %}
  {% endfor %}
  {% if has_report %}
    {% assign published_count = published_count | plus: 1 %}
    <li>{% capture document_path %}/om/arsmeldingar/{{ entry[0] }}/{% endcapture %}{% capture document_title %}Årsmelding {{ entry[0] }}{% endcapture %}{% assign document_year = entry[0] %}{% include arsdokument-lenkje.html path=document_path title=document_title year=document_year %}</li>
  {% endif %}
{% endfor %}
{% endif %}
</ul>
{% if published_count == 0 %}<p>Ingen årsmeldingar er publiserte enno.</p>{% endif %}
