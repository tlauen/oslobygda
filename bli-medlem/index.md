---
layout: standard
title: Bli medlem
brevo_skjema: true
---

# Bli medlem

Me blir veldig glade om du vil vere med i Oslobygda kulturlag.

Vanleg medlemskap for kule folk kostar 5 kroner. Superkule medlemmar betalar ein valfri sum over 5 kroner. 

Du kan betale kæsj eller vippse Torbjørn. Kjem ordentleg opplegg så fort me får ein bankkonto på plass.

<section class="om-innmelding" aria-labelledby="om-innmelding-tittel">
  {% if site.brevo_membership_form_url != nil and site.brevo_membership_form_url != "" %}
  {% include brevo-skjema-innmelding.html %}
  {% else %}
  <p><em>Brevo-skjema for innmelding er ikkje sett opp enno. Legg inn <code>brevo_membership_form_url</code> i <code>_config.yml</code>.</em></p>
  {% endif %}
</section>
