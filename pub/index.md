---
layout: default
title: Om Folkemusikkpøbben
permalink: /pub/
---

# Folkemusikkpøbben

Kva det er, kvar det er, korleis ein kveld fungerer, og kva folk bør ta med (godt humør, gjerne instrument).

## Komande pøbbar

{% liquid
  include kalenderliste.html mode="future"
%}

## Tidlegare pøbbar

{% liquid
  include kalenderliste.html mode="past" group="year"
%}