---
layout: standard
title: Sakliste og møtereglar
permalink: /om/saklister/
---
<link rel="stylesheet" href="{{ '/lutar/arsmelding.css' | relative_url }}">
<p><a class="arsmelding-tilbake" href="{{ '/om/' | relative_url }}#arsmote">← Om laget</a></p>
<h1>Sakliste og møtereglar</h1>
<h2>Saklister til årsmøte</h2>
{% assign count = 0 %}
<ul>{% assign years = site.data.arsdokument | sort %}{% for entry in years reversed %}{% assign agendas = entry[1].versions | where: 'kind', 'sakliste' %}{% assign protocols = entry[1].versions | where: 'kind', 'protokoll' | where: 'status', 'approved' %}{% if agendas.size > 0 or protocols.size > 0 %}{% assign count = count | plus: 1 %}<li><a href="{{ '/om/saklister/' | append: entry[0] | append: '/' | relative_url }}">{% if agendas.size > 0 %}Sakliste til årsmøtet{% else %}Årsmøtet{% endif %} {{ entry[0] | escape }}</a>{% if protocols.size > 0 %} · <a href="{{ '/om/saklister/' | append: entry[0] | append: '/#protokoll' | relative_url }}">Godkjend protokoll</a>{% endif %}</li>{% endif %}{% endfor %}</ul>
{% if count == 0 %}<p>Ingen saklister er publiserte enno.</p>{% endif %}
<h2 id="motereglar">Møtereglar</h2>
{% assign rules = site.data.motereglar.body %}
{% assign rule_versions = '' | split: ',' %}
{% for entry in site.data.arsdokument %}{% assign candidates = entry[1].versions | where: 'kind', 'motereglar' %}{% assign rule_versions = rule_versions | concat: candidates %}{% endfor %}
{% assign latest = rule_versions | sort: 'source_revision' | last %}
{% if latest %}{% assign rules = latest.content.body %}{% endif %}
{% capture newline %}
{% endcapture %}
<div class="motereglar">{% assign lines = rules | split: newline %}{% for line in lines %}{% assign prefix = line | slice: 0, 3 %}{% assign clean = line | strip %}{% if prefix == '## ' %}<h3>{{ line | remove_first: '## ' | escape }}</h3>{% elsif clean != '' %}<p>{{ line | escape }}</p>{% endif %}{% endfor %}</div>
