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
{% assign years = site.data.arsdokument | sort %}
{% for entry in years reversed %}
  {% assign protocols = entry[1].versions | where: 'kind', 'protokoll' | where: 'status', 'approved' | sort: 'source_revision' %}
  {% assign year_heading = false %}
  {% for protocol in protocols reversed %}
    {% if protocol.approved_by.size == 2 %}
      {% unless year_heading %}<h2>Årsmøtet {{ entry[0] | escape }}</h2>{% assign year_heading = true %}{% endunless %}
      {% assign published_count = published_count | plus: 1 %}
      {% capture protocol_id %}protokoll-{{ entry[0] }}-{{ protocol.version_id }}{% endcapture %}
      <details id="{{ protocol_id | escape }}">
      <summary>{{ protocol.content.title | escape }} – godkjend {{ protocol.generated_at | date: '%d.%m.%Y' }}</summary>
      {% capture document_id %}{{ protocol_id }}-dokument{% endcapture %}
      {% include protokoll.html id=document_id %}
      </details>
    {% endif %}
  {% endfor %}
{% endfor %}
{% if published_count == 0 %}<p>Ingen godkjende og underskrivne protokollar er publiserte enno.</p>{% endif %}
</div>
