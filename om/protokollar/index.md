---
layout: standard
title: Protokollar
permalink: /om/protokollar/
---
<link rel="stylesheet" href="{{ '/lutar/arsmelding.css' | relative_url }}">
<link rel="stylesheet" href="{{ '/lutar/offentleg-okonomi.css' | relative_url }}">
<p><a class="arsmelding-tilbake" href="{{ '/om/' | relative_url }}#arsmote">← Om laget</a></p>
<div class="offentleg-okonomi">
<h1>Protokollar</h1>
<p>Her finn du protokollar frå årsmøta som er godkjende av begge protokollunderskrivarane.</p>
{% assign published_count = 0 %}
<ul class="arsdokument-oversikt protokoll-oversikt">
{% assign years = site.data.arsdokument | sort %}
{% for entry in years reversed %}
  {% assign protocols = entry[1].versions | where: 'kind', 'protokoll' | where: 'status', 'approved' | sort: 'source_revision' | reverse %}
  {% for protocol in protocols %}
    {% if protocol.approved_by.size == 2 %}
      {% assign published_count = published_count | plus: 1 %}
      {% assign document_year = entry[0] %}
      {% capture protocol_path %}/om/protokollar/{{ document_year }}/{% endcapture %}
      {% capture approval_hint %}Godkjend {{ protocol.generated_at | date: '%d.%m.%Y' }} · Opne protokollen{% endcapture %}
      <li>{% include arsdokument-lenkje.html path=protocol_path title=protocol.content.title year=document_year hint=approval_hint %}</li>
      {% break %}
    {% endif %}
  {% endfor %}
{% endfor %}
</ul>
{% if published_count == 0 %}<p>Ingen godkjende og underskrivne protokollar er publiserte enno.</p>{% endif %}
</div>
