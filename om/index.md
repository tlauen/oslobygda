---
layout: standard
title: Om Oslobygda kulturlag
kontingentoversikt: true
sidetekst: om
---

{% assign tekst = site.data.sidetekstar.om %}
<h1>{{ tekst.source.title | escape }}</h1>
{% capture frilynt %}{% include kontekstlenkje.html %}{% endcapture %}
{{ tekst.html.body | replace: '[[frilynt]]', frilynt }}

<p>{{ tekst.source.join_text | escape }} <a href="{{ site.innmelding_url | escape }}">{{ tekst.source.join_button | escape }}</a> {% include kontingent-kort.html %}</p>

{% include styret.html %}

{% include dokument.html %}

{% include arsmotesaker.html %}
