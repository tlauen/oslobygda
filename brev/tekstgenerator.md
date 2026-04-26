---
layout: standard
title: Tekstgenerator for nyhendebrev
---

{% assign months_nn = "januar|februar|mars|april|mai|juni|juli|august|september|oktober|november|desember" | split: "|" %}
{% assign weekdays_nn = "sundag|mandag|tirsdag|onsdag|torsdag|fredag|laurdag" | split: "|" %}
{% assign today_iso = "now" | date: "%Y-%m-%d" %}
{% assign upcoming = site.data.kalender | where_exp: "e", "e.dato >= today_iso" | sort: "dato" %}
{% assign upcoming_pobb = upcoming | where_exp: "e", "e.uid contains 'pobb-'" %}
{% assign trigger = upcoming_pobb | first %}

{% if trigger %}
  {% assign trigger_weekday_i = trigger.dato | date: "%w" | plus: 0 %}
  {% assign trigger_day = trigger.dato | date: "%-d" %}
  {% assign trigger_month_i = trigger.dato | date: "%-m" | plus: 0 | minus: 1 %}
  {% assign trigger_month = months_nn[trigger_month_i] %}
  {% capture subject_line %}Neste folkemusikkpøbb er {{ weekdays_nn[trigger_weekday_i] }} {{ trigger_day }}. {{ trigger_month }}!{% endcapture %}
{% else %}
  {% capture subject_line %}Komande tilskipingar frå Oslobygda kulturlag{% endcapture %}
{% endif %}

{% capture body_rich %}
<ul>
{% for e in upcoming_pobb limit: 6 %}
{% assign day = e.dato | date: "%-d" %}
{% assign month_i = e.dato | date: "%-m" | plus: 0 | minus: 1 %}
{% assign year = e.dato | date: "%Y" %}
  <li><strong>{{ day }}. {{ months_nn[month_i] }} {{ year }}</strong>{% if e.start %} kl. {{ e.start }}{% endif %}{% if e.tittel %} – {{ e.tittel }}{% endif %}{% if e.stad %} ({{ e.stad }}){% endif %}</li>
{% endfor %}
</ul>
{% endcapture %}

# Tekstgenerator for nyhendebrev

Denne sida lagar det du treng for manuell utsending i e-postverktøyet ditt (t.d. **Brevo**): emnefelt + kulepunkt med komande pøbb-arrangement.

<p><strong>Generert:</strong> <span id="generated-time"></span></p>

<h2>Emnefelt</h2>

<textarea id="subject-text" rows="3" style="width:100%; font-family:ui-monospace, SFMono-Regular, Menlo, Monaco, Consolas, monospace;">{{ subject_line | strip }}</textarea>
<p><button type="button" class="btn" onclick="copyFrom('subject-text', 'subject-status')">Kopier emnefelt</button> <span id="subject-status" aria-live="polite"></span></p>

<h2>Kulepunkt (riktekst)</h2>

<p>Kopier denne boksen for å få kulepunkt og utheva datoar inn i rikteksteditoren:</p>
<div id="body-rich" style="border:1px solid #d0cbc2; background:#fff; padding:1rem; border-radius:.5rem;">{{ body_rich | strip }}</div>
<p><button type="button" class="btn" onclick="copyRich('body-rich', 'rich-status')">Kopier kulepunkt</button> <span id="rich-status" aria-live="polite"></span></p>

<p>Tips: Lim emnefeltet i emnelinja og kulepunkta i innhaldsfeltet i kampanje- eller brev-editoren i Brevo (eller anna verktøy du brukar).</p>

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

  async function copyRich(sourceId, statusId) {
    var source = document.getElementById(sourceId);
    var status = document.getElementById(statusId);
    if (!source) return;
    try {
      if (navigator.clipboard && window.ClipboardItem) {
        var html = source.innerHTML;
        var text = source.innerText;
        var item = new ClipboardItem({
          "text/html": new Blob([html], { type: "text/html" }),
          "text/plain": new Blob([text], { type: "text/plain" })
        });
        await navigator.clipboard.write([item]);
      } else {
        var range = document.createRange();
        range.selectNodeContents(source);
        var selection = window.getSelection();
        selection.removeAllRanges();
        selection.addRange(range);
        document.execCommand("copy");
        selection.removeAllRanges();
      }
      if (status) status.textContent = "Riktekst kopiert.";
    } catch (err) {
      if (status) status.textContent = "Kunne ikkje kopiere riktekst automatisk. Marker boksen og kopier manuelt.";
    }
  }
</script>
