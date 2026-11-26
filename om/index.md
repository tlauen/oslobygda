---
layout: standard
title: Om Oslobygda kulturlag
kontingentoversikt: true
sidetekst: om
---

{% assign tekst = site.data.sidetekstar.om %}
<h1>{{ tekst.source.title | escape }}</h1>
{% include markdown-tekst.html html=tekst.html.body %}

{% include styret.html %}

{% include dokument.html %}

{% include arsmotesaker.html %}
