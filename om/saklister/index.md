---
layout: standard
title: Sakliste og møtereglar
permalink: /om/saklister/
---
<link rel="stylesheet" href="{{ '/lutar/arsmelding.css' | relative_url }}">
<p><a class="arsmelding-tilbake" href="{{ '/om/' | relative_url }}#arsmote">← Om laget</a></p>
<h1>Sakliste og møtereglar</h1>
{% assign count = 0 %}
<ul class="arsdokument-oversikt">
{% assign years = site.data.arsdokument | sort %}
{% for entry in years reversed %}
  {% assign agendas = entry[1].versions | where: 'kind', 'sakliste' %}
  {% assign protocols = entry[1].versions | where: 'kind', 'protokoll' | where: 'status', 'approved' %}
  {% if agendas.size > 0 or protocols.size > 0 %}
    {% assign count = count | plus: 1 %}
    <li class="arsdokument-mote">
    {% capture agenda_path %}/om/saklister/{{ entry[0] }}/{% endcapture %}
    {% capture agenda_title %}{% if agendas.size > 0 %}Sakliste for årsmøtet{% else %}Årsmøtet{% endif %} {{ entry[0] }}{% endcapture %}
    {% assign document_year = entry[0] %}{% include arsdokument-lenkje.html path=agenda_path title=agenda_title year=document_year hint='Saker og årsmøtepapir' %}
    {% if protocols.size > 0 %}
      {% capture protocol_path %}/om/saklister/{{ entry[0] }}/#protokoll{% endcapture %}
      {% capture protocol_title %}Godkjend protokoll {{ entry[0] }}{% endcapture %}
      {% assign document_year = entry[0] %}{% include arsdokument-lenkje.html path=protocol_path title=protocol_title hint='Godkjend av begge underskrivarane' %}
    {% endif %}
    </li>
  {% endif %}
{% endfor %}
</ul>
{% if count == 0 %}<p>Ingen saklister er publiserte enno.</p>{% endif %}
{% assign rules = site.data.motereglar.body %}
{% assign rule_versions = '' | split: ',' %}
{% for entry in site.data.arsdokument %}{% assign candidates = entry[1].versions | where: 'kind', 'motereglar' %}{% assign rule_versions = rule_versions | concat: candidates %}{% endfor %}
{% assign latest = rule_versions | sort: 'source_revision' | last %}
{% if latest %}{% assign rules = latest.content.body %}{% endif %}
{% capture newline %}
{% endcapture %}
<article class="lovdokument motereglar" aria-labelledby="motereglar">
<header class="lovdokument-topp">
<p class="modul-etikett">Oslobygda kulturlag · Årsmøte</p>
<h2 id="motereglar" tabindex="-1">Møtereglar</h2>
</header>
<div class="lovdokument-paragrafar">
{% assign section_open = false %}
{% assign lines = rules | split: newline %}
{% for line in lines %}
  {% assign prefix = line | slice: 0, 3 %}
  {% assign clean = line | strip %}
  {% if prefix == '## ' %}
    {% if section_open %}</section>{% endif %}
    <section class="lovparagraf" aria-labelledby="moteregel-{{ forloop.index }}">
    <h3 id="moteregel-{{ forloop.index }}">{{ line | remove_first: '## ' | escape }}</h3>
    {% assign section_open = true %}
  {% elsif clean != '' %}
    {% unless section_open %}<section class="lovparagraf">{% assign section_open = true %}{% endunless %}
    <p>{{ line | escape }}</p>
  {% endif %}
{% endfor %}
{% if section_open %}</section>{% endif %}
</div>
</article>
