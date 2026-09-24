---
layout: standard
title: Bli medlem
brevo_skjema: true
---

# Bli medlem

Me blir veldig glade om du vil vere med i Oslobygda kulturlag.

Vanleg medlemskap for kule folk kostar 5 kroner. Superkule medlemmar betalar ein valfri sum over 5 kroner. 

Medlemspengane kan du betale kæsj til Torbjørn eller på Vipps. Vippsnummeret vårt er **51630**.

{% if site.brevo_membership_form_url != nil and site.brevo_membership_form_url != "" %} {% include brevo-skjema-innmelding.html %} {% else %}

*Brevo-skjema for innmelding er ikkje sett opp enno. Legg inn* `brevo_membership_form_url` *i* `_config.yml`*.*

 {% endif %}