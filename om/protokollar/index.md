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
  {% assign protocols = entry[1].versions | where: 'kind', 'protokoll' | where: 'status', 'approved' | sort: 'source_revision' %}
  {% for protocol in protocols reversed %}
    {% if protocol.approved_by.size == 2 %}
      {% assign published_count = published_count | plus: 1 %}
      {% capture protocol_id %}protokoll-{{ entry[0] }}-{{ protocol.version_id }}{% endcapture %}
      <li><details id="{{ protocol_id | escape }}">
      {% assign document_year = entry[0] %}
      {% capture approval_hint %}Godkjend {{ protocol.generated_at | date: '%d.%m.%Y' }} · Opne protokollen{% endcapture %}
      {% include arsdokument-lenkje.html disclosure=true title=protocol.content.title year=document_year hint=approval_hint %}
      {% capture protocol_navigation %}<p class="dokument-tilbake-lenkjer"><a class="arsmelding-tilbake" href="{{ '/om/protokollar/' | relative_url }}">← Alle protokollar</a><a class="arsmelding-tilbake" href="{{ '/om/saklister/' | append: entry[0] | append: '/' | relative_url }}">Til saklista for {{ entry[0] | escape }}</a></p>{% endcapture %}
      {{ protocol_navigation }}
      {% capture document_id %}{{ protocol_id }}-dokument{% endcapture %}
      {% include protokoll.html id=document_id %}
      {{ protocol_navigation }}
      </details></li>
    {% endif %}
  {% endfor %}
{% endfor %}
</ul>
{% if published_count == 0 %}<p>Ingen godkjende og underskrivne protokollar er publiserte enno.</p>{% endif %}
</div>
