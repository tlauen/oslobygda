---
layout: standard
title: Oslobygda kulturlag
description: "Folkemusikk, dans og gode møte i Oslo. Sjå kva som skjer, og bli med i Oslobygda kulturlag."
kontingentoversikt: true
---

<section class="helt" aria-labelledby="framside-tittel">
  <div class="helt__innhald">
    <p class="framside__overtekst">Folkemusikkpøbb i Oslo · sidan 2021</p>
    <h1 id="framside-tittel" class="helt__tittel">Byliv med bygdepuls.</h1>
    <p class="helt__ingress">Folkemusikk, dans og kjekke folk i Oslo. Kom ned i kjellaren på Kaffistova og bli med på Folkemusikkpøbb!</p>
    <div class="framside__handlingar">
      <a class="framside__knapp framside__knapp--lys" href="#det-skjer">Sjå kva som skjer <span aria-hidden="true">↓</span></a>
      <a class="framside__tekstlenkje" href="{{ '/bli-medlem/' | relative_url }}">Bli medlem <span aria-hidden="true">↗</span></a>
    </div>
  </div>
  <div class="helt__logo" aria-hidden="true"></div>
</section>

<section id="det-skjer" class="framside__arrangement" aria-labelledby="arrangement-tittel">
  <div class="framside__seksjonstopp">
    <div>
      <p class="framside__overtekst">Me sjåast!</p>
      <h2 id="arrangement-tittel">Dette skjer framover</h2>
    </div>
    <a href="{{ '/kalender/' | relative_url }}">Heile kalenderen <span aria-hidden="true">→</span></a>
  </div>
  {% include kalenderliste.html limit=3 %}
</section>

<section class="framside__medlem" aria-labelledby="medlem-tittel">
  <div>
    <p class="framside__overtekst">Plass til fleire i laget</p>
    <h2 id="medlem-tittel">Glad i det me finn på?<br>Bli med då vel!</h2>
    <p>Som medlem i Oslobygda kulturlag støttar du arbeidet for levande folkekultur i hovudstaden. {% include kontingent-kort.html %}</p>
    <div class="framside__handlingar">
      <a class="framside__knapp" href="{{ '/bli-medlem/' | relative_url }}">Ja, eg vil bli medlem <span aria-hidden="true">→</span></a>
      <a href="{{ '/om/' | relative_url }}">Bli kjend med laget</a>
    </div>
  </div>
  <div class="framside__kontingent" data-kontingent-url="{{ site.medlemsregister_url | append: '/api/kontingent' | escape }}" data-kontingent-vising="merke" hidden>
    <span data-kontingent-belop aria-hidden="true"></span>
    <p>Meir folkekultur.</p>
  </div>
</section>
