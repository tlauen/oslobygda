---
layout: default
title: Kalender
permalink: /kalender/
---

# Kalender

## Komande arrangement

{% liquid
  include kalenderliste.html mode="future" group="none"
%}

## Tidlegare arrangement

{% liquid
  include kalenderliste.html mode="past" group="year"
%}