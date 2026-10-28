---
layout: standard
title: Oslobygda kulturlag
description: "Folkemusikk, dans og gode møte i Oslo. Sjå kva som skjer, og bli med i Oslobygda kulturlag for ein femkroning."
---

<section class="helt" aria-labelledby="framside-tittel">
  <div class="helt__innhald">
    <p class="framside__overtekst">Oslobygda kulturlag · sidan 2021</p>
    <h1 id="framside-tittel" class="helt__tittel">Byliv med bygdepuls.</h1>
    <p class="helt__ingress">Folkemusikk, dans og gode møte i Oslo. Kom ned i kjellaren på Kaffistova – me lagar liv på Folkemusikkpøbben!</p>
    <div class="framside__handlingar">
      <a class="framside__knapp framside__knapp--lys" href="#det-skjer">Sjå kva som skjer <span aria-hidden="true">↓</span></a>
      <a class="framside__tekstlenkje" href="{{ '/bli-medlem/' | relative_url }}">Bli medlem for ein femmar <span aria-hidden="true">↗</span></a>
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
    <h2 id="medlem-tittel">Glad i det me finn på?<br>Bli ein av oss.</h2>
    <p>For ein femkroning blir du medlem i Oslobygda kulturlag og støttar arbeidet for levande folkekultur i hovudstaden.</p>
    <div class="framside__handlingar">
      <a class="framside__knapp" href="{{ '/bli-medlem/' | relative_url }}">Ja, eg vil bli medlem <span aria-hidden="true">→</span></a>
      <a href="{{ '/om/' | relative_url }}">Bli kjend med laget</a>
    </div>
  </div>
  <div class="framside__femmar" aria-label="Medlemskap kostar 5 kroner">
    <span aria-hidden="true">5<span>kr</span></span>
    <p>Ein femmar.<br>Meir folkekultur.</p>
  </div>
</section>
