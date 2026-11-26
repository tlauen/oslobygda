---
layout: standard
title: Oslobygda kulturlag
sidetekst: framside
kontingentoversikt: true
---

{% assign tekst = site.data.sidetekstar.framside %}
<section class="helt" aria-labelledby="framside-tittel">
  <div class="helt__innhald">
    <p class="framside__overtekst">{{ tekst.source.overtekst | escape }}</p>
    <h1 id="framside-tittel" class="helt__tittel">{{ tekst.source.title | escape }}</h1>
    <div class="helt__ingress">{{ tekst.html.intro }}</div>
    <div class="framside__handlingar">
      <a class="framside__knapp framside__knapp--lys" href="#det-skjer">{{ tekst.source.events_button | escape }} <span aria-hidden="true">↓</span></a>
      <a class="framside__tekstlenkje" href="{{ '/bli-medlem/' | relative_url }}">{{ tekst.source.join_button | escape }} <span aria-hidden="true">↗</span></a>
    </div>
  </div>
  <div class="helt__logo" aria-hidden="true"></div>
</section>

<section id="det-skjer" class="framside__arrangement" aria-labelledby="arrangement-tittel">
  <div class="framside__seksjonstopp">
    <div>
      <p class="framside__overtekst">{{ tekst.source.events_overline | escape }}</p>
      <h2 id="arrangement-tittel">{{ tekst.source.events_title | escape }}</h2>
    </div>
    <a href="{{ '/kalender/' | relative_url }}">{{ tekst.source.calendar_button | escape }} <span aria-hidden="true">→</span></a>
  </div>
  {% include kalenderliste.html limit=3 %}
</section>

<section class="framside__medlem" aria-labelledby="medlem-tittel">
  <div>
    <p class="framside__overtekst">{{ tekst.source.member_overline | escape }}</p>
    <h2 id="medlem-tittel">{{ tekst.source.member_title | escape }}</h2>
    {{ tekst.html.member_body }}
    <p>{% include kontingent-kort.html %}</p>
    <div class="framside__handlingar">
      <a class="framside__knapp" href="{{ '/bli-medlem/' | relative_url }}">{{ tekst.source.member_button | escape }} <span aria-hidden="true">→</span></a>
      <a href="{{ '/om/' | relative_url }}">{{ tekst.source.about_button | escape }}</a>
    </div>
  </div>
  <div class="framside__kontingent" data-kontingent-url="{{ site.medlemsregister_url | append: '/api/kontingent' | escape }}" data-kontingent-vising="merke" hidden>
    <span class="framside__pris" aria-hidden="true"><span data-kontingent-belop></span><span class="framside__kr">kr</span></span>
    <p>{{ tekst.source.badge_text | escape }}</p>
  </div>
</section>
