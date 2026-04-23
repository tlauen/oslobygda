---
layout: standard
title: Tekstgenerator for nyhendebrev
---

{% assign months_nn = "januar|februar|mars|april|mai|juni|juli|august|september|oktober|november|desember" | split: "|" %}
{% assign weekdays_nn = "sundag|mandag|tirsdag|onsdag|torsdag|fredag|laurdag" | split: "|" %}
{% assign today_iso = "now" | date: "%Y-%m-%d" %}
{% assign upcoming = site.data.kalender | where_exp: "e", "e.dato >= today_iso" | sort: "dato" %}
{% assign trigger = upcoming | where_exp: "e", "e.uid contains 'pobb-'" | first %}

{% if trigger %}
  {% assign trigger_weekday_i = trigger.dato | date: "%w" | plus: 0 %}
  {% assign trigger_day = trigger.dato | date: "%-d" %}
  {% assign trigger_month_i = trigger.dato | date: "%-m" | plus: 0 | minus: 1 %}
  {% assign trigger_month = months_nn[trigger_month_i] %}
  {% capture subject_line %}Neste folkemusikkpøbb er {{ weekdays_nn[trigger_weekday_i] }} {{ trigger_day }}. {{ trigger_month }}!{% endcapture %}
{% else %}
  {% capture subject_line %}Komande tilskipingar frå Oslobygda kulturlag{% endcapture %}
{% endif %}

{% capture body_text %}
Komande tilskipingar

Her er det som ligg i kalenderen vår no:
{% for e in upcoming limit: 12 %}
{% assign day = e.dato | date: "%-d" %}
{% assign month_i = e.dato | date: "%-m" | plus: 0 | minus: 1 %}
{% assign year = e.dato | date: "%Y" %}
- {{ day }}. {{ months_nn[month_i] }} {{ year }}{% if e.start %} kl. {{ e.start }}{% endif %}{% if e.tittel %} – {{ e.tittel }}{% endif %}{% if e.stad %} ({{ e.stad }}){% endif %}
{% endfor %}

Heile kalenderen: {{ '/kalender/' | absolute_url }}
ICS: {{ '/kalender.ics' | absolute_url }}
{% endcapture %}

# Tekstgenerator for nyhendebrev

Denne sida lagar ferdig tekst frå kalenderen som du kan lime rett inn i MailerLite (gratisversjon).

<p><strong>Generert:</strong> <span id="generated-time"></span></p>

<h2>Emnefelt</h2>

<textarea id="subject-text" rows="3" style="width:100%; font-family:ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;">{{ subject_line | strip }}</textarea>
<p><button type="button" class="btn" onclick="copyFrom('subject-text', 'subject-status')">Kopier emnefelt</button> <span id="subject-status" aria-live="polite"></span></p>

<h2>Brødtekst (plain text)</h2>

<textarea id="body-text" rows="18" style="width:100%; font-family:ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;">{{ body_text | strip }}</textarea>
<p><button type="button" class="btn" onclick="copyFrom('body-text', 'body-status')">Kopier brødtekst</button> <span id="body-status" aria-live="polite"></span></p>

<p>Tips: I MailerLite kan du bruke emnefeltet over + lime inn brødteksten i ein plain text- eller tekstblokk i editoren.</p>

<script>
  (function () {
    var now = new Date();
    var el = document.getElementById("generated-time");
    if (el) {
      el.textContent = now.toLocaleString("nn-NO");
    }
  })();

  async function copyFrom(sourceId, statusId) {
    var source = document.getElementById(sourceId);
    var status = document.getElementById(statusId);
    if (!source) return;
    try {
      if (navigator.clipboard && navigator.clipboard.writeText) {
        await navigator.clipboard.writeText(source.value);
      } else {
        source.focus();
        source.select();
        document.execCommand("copy");
      }
      if (status) status.textContent = "Kopiert.";
    } catch (err) {
      if (status) status.textContent = "Kunne ikkje kopiere automatisk. Marker teksten og kopier manuelt.";
    }
  }
</script>
