---
layout: standard
title: Kalender
permalink: /kalender/
---

# Kalender

{% include kalenderabonnement.html %}

## Kva du kan glede deg til

<div class="seksjon" data-calendar-live="future">
{% include kalenderliste.html mode="future" %}
</div>

## Kva me har gjort før

<div class="seksjon seksjon--tidlegare" data-calendar-live="past">
{% include kalenderliste.html mode="past" group="year" %}
</div>