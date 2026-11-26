
    const csrfToken = document.querySelector('meta[name="csrf-token"]').content;
    const originalFetch = window.fetch.bind(window);
    window.fetch = function(input, options = {}) {
      const target = new URL(input instanceof Request ? input.url : input, location.href);
      const method = (options.method || (input instanceof Request ? input.method : 'GET')).toUpperCase();
      if (target.origin === location.origin && !['GET', 'HEAD', 'OPTIONS'].includes(method)) {
        const headers = new Headers(options.headers || (input instanceof Request ? input.headers : undefined));
        headers.set('X-CSRF-Token', csrfToken);
        options = {...options, headers};
      }
      return originalFetch(input, options);
    };


    const API = document.querySelector('meta[name="api-prefix"]').content;
    const statusEl = document.getElementById("status");
    const listeEl = document.getElementById("medlem-liste");
    const modal = document.getElementById("modal-dekke");
    const betalingModal = document.getElementById("betaling-dekke");
    const skjema = document.getElementById("medlem-skjema");
    const skjemaFeil = document.getElementById("skjema-feil");
    const betalingSkjema = document.getElementById("betaling-skjema");
    const betalingFeil = document.getElementById("betaling-feil");

    function setStatus(msg, isError) {
      if (statusEl) {
        statusEl.textContent = msg;
        statusEl.style.color = isError ? "var(--error)" : "var(--dempa)";
      }
    }

    function formaterDato(iso) {
      if (!iso) return "–";
      try {
        const d = new Date(iso);
        return d.toLocaleDateString("nb-NO", { dateStyle: "short" });
      } catch (_) { return iso; }
    }

    function medlemstypeVisningsnamn(val) {
      if (!val) return "–";
      if (val === "styret") return "Styret";
      if (val === "Kul medlem (5kr)" || val === "vanleg") return "Kul";
      if (val === "Superkul medlem (meir enn 5kr)" || val === "kul") return "Superkul";
      return val;
    }

    function pillClassForPaymentStatus(s) {
      if (s === "betalt") return "pill pill--betalt";
      if (s === "ikkje betalt") return "pill pill--ikkje-betalt";
      return "pill";
    }

    function medlemstypeTilVerdi(val) {
      if (val === "Styret") return "styret";
      if (val === "Kul medlem (5kr)") return "vanleg";
      if (val === "Superkul medlem (meir enn 5kr)") return "kul";
      return val || "vanleg";
    }

    function formatNokFromOre(ore) {
      const n = Number(ore || 0) / 100;
      return n.toLocaleString("nb-NO", { minimumFractionDigits: 2, maximumFractionDigits: 2 }) + " kr";
    }

    function visningsnamn(m) {
      if (m.fornamn || m.etternamn) {
        return [m.fornamn, m.mellomnamn, m.etternamn].filter(Boolean).join(" ").trim();
      }
      return m.full_name || "–";
    }

    async function hentMedlemmar() {
      setStatus("Lastar …");
      try {
        const r = await fetch(API + "/api/members", { credentials: "same-origin" });
        if (!r.ok) {
          let msg = "Kunne ikkje laste medlemmar.";
          try {
            const body = await r.json();
            if (body && body.error) msg += " " + body.error;
            else if (r.status === 401) msg = "Du er ikkje innlogga. Logg inn på nytt.";
          } catch (_) {}
          setStatus(msg, true);
          return [];
        }
        const data = await r.json();
        setStatus("");
        return data;
      } catch (e) {
        setStatus("Feil ved lasting: " + e.message, true);
        return [];
      }
    }

    function renderListe(medlemmar) {
      listeEl.innerHTML = medlemmar.map(m => `
        <tr>
          <td data-col="namn">${escapeHtml(visningsnamn(m))}</td>
          <td data-col="epost">${escapeHtml(m.email)}</td>
          <td data-col="telefon">${escapeHtml(m.phone || "–")}</td>
          <td data-col="adresse">${escapeHtml(m.adresse || "–")}</td>
          <td data-col="postnr">${escapeHtml(m.postnummer || "–")}</td>
          <td data-col="poststad">${escapeHtml(m.poststad || "–")}</td>
          <td data-col="fødselsdato">${m.birth_date ? formaterDato(m.birth_date) : "–"}</td>
          <td data-col="medlemstype"><span class="pill">${escapeHtml(medlemstypeVisningsnamn(m.membership_type))}</span></td>
          <td data-col="betalingsstatus">
            <span class="${pillClassForPaymentStatus(m.payment_status)} pill--toggle" data-id="${m.id}" data-action="toggle-payment" data-status="${escapeHtml(m.payment_status)}" title="Klikk for å bytte betalingsstatus">${escapeHtml(m.payment_status)}</span>
            <div class="sum-reg">${formatNokFromOre(m.total_paid_ore)}</div>
          </td>
          <td data-col="samtykke">${formaterDato(m.consent_at)}</td>
          <td data-col="aksjonar" class="aksjonar">
            <a href="#" data-id="${m.id}" data-action="edit">Endre</a>
            <div class="aksjonar-meny-wrap">
              <button type="button" class="aksjonar-meny-knapp" data-id="${m.id}" aria-label="Meny" aria-expanded="false"><span class="aksjonar-meny-prikker"><span></span><span></span><span></span></span></button>
              <div class="aksjonar-meny" role="menu" hidden>
                <button type="button" role="menuitem" data-id="${m.id}" data-action="export">Eksporter (GDPR)</button>
                <button type="button" role="menuitem" data-id="${m.id}" data-action="betaling">Registrer betaling</button>
                <button type="button" role="menuitem" data-id="${m.id}" data-action="delete" class="slett">Slett</button>
              </div>
            </div>
          </td>
        </tr>
      `).join("");
      brukKolonnefilter();
    }

    function lukkAlleAksjonarMenyer() {
      listeEl.querySelectorAll(".aksjonar-meny").forEach(menu => {
        menu.hidden = true;
        menu.classList.remove("aksjonar-meny--open-up");
      });
      listeEl.querySelectorAll(".aksjonar-meny-knapp").forEach(btn => { btn.setAttribute("aria-expanded", "false"); });
      listeEl.querySelectorAll("td.aksjonar.open").forEach(cell => cell.classList.remove("open"));
    }

    function opneAksjonarMeny(knapp, menu, cell) {
      menu.classList.remove("aksjonar-meny--open-up");
      const rect = knapp.getBoundingClientRect();
      const plassUnder = window.innerHeight - rect.bottom;
      if (plassUnder < 95 && rect.top > 100) {
        menu.classList.add("aksjonar-meny--open-up");
      }
      menu.hidden = false;
      knapp.setAttribute("aria-expanded", "true");
      cell.classList.add("open");
    }

    function escapeHtml(s) {
      if (s == null) return "";
      const div = document.createElement("div");
      div.textContent = s;
      return div.innerHTML;
    }

    function lukkMedlemsar(ar) {
      if (!confirm("Dette lagrar sammendrag for medlemsår " + ar + " i arkiv, set neste år til " + (ar + 1) + ", og oppdaterer betalingsstatus etter betalingar og gratisvedtak for det nye året. Hugs å ta database-backup. Vil du fortsette?")) return;
      const s = window.prompt("Skriv årstalet " + ar + " for å stadfeste (same tal som står ovanfor).");
      if (String(s) !== String(ar)) {
        setStatus("Avbroten – ingen endringar.");
        return;
      }
      (async () => {
        const btn = document.getElementById("btn-lukk-medlemsar");
        if (btn) btn.disabled = true;
        try {
          const r = await fetch(API + "/api/medlemsar/lukk", {
            method: "POST",
            credentials: "same-origin",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ bekreft_ar: ar })
          });
          const data = await r.json().catch(() => ({}));
          if (!r.ok) {
            setStatus(data.error || "Feil ved lukking av medlemsår", true);
            if (btn) btn.disabled = false;
            return;
          }
          setStatus(data.message);
          await lastOversikt();
          const medlemmar = await hentMedlemmar();
          renderListe(medlemmar);
        } catch (e) {
          setStatus(e.message, true);
        }
        const b2 = document.getElementById("btn-lukk-medlemsar");
        if (b2) b2.disabled = false;
      })();
    }

    async function lastOversikt() {
      const el = document.getElementById("medlemsoversikt-innhold");
      if (!el) return;
      try {
        const r = await fetch(API + "/api/medlemsoversikt", { credentials: "same-origin" });
        const d = await r.json().catch(() => ({}));
        if (!r.ok) {
          el.innerHTML = "<p class=\"feil\">" + escapeHtml(d.error || "Kunne ikkje hente oversikt") + "</p>";
          return;
        }
        const a0 = d.alder_0_14 ?? 0;
        const a15 = d.alder_15_25 ?? 0;
        const a26 = d.alder_26_eller_eldre != null ? d.alder_26_eller_eldre : 0;
        const aU = d.alder_utan_fodselsdato != null ? d.alder_utan_fodselsdato : 0;
        const tot = (Number(d.totalt_innbetalt_ore) / 100).toLocaleString("nb-NO", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        const n = d.antall_medlemer_med_betaling;
        const ar = d.medlemsbetalingsar;
        const mTot = d.antall_medlemer_totalt != null ? d.antall_medlemer_totalt : a0 + a26 + aU;
        let alderLinje = "<span class=\"medlemsoversikt-dempa\">Medlemmar totalt:</span> " + mTot + " &nbsp;·&nbsp; <strong>0–14 år:</strong> " + a0 + " &nbsp;·&nbsp; <strong>15–25 år:</strong> " + a15 + " &nbsp;·&nbsp; <strong>26+ år:</strong> " + a26;
        if (aU > 0) {
          alderLinje += " &nbsp;·&nbsp; <span class=\"medlemsoversikt-dempa\">Ikkje oppgitt fødselsdato: " + aU + "</span>";
        }
        let arkivHtml = "";
        if (d.arkiv && d.arkiv.length) {
          arkivHtml = "<h3 class=\"medlemsoversikt-seksjon\">Arkiv (avslutta medlemsår)</h3><ul class=\"medlemsoversikt-arkiv-liste\">" +
            d.arkiv.map(a => {
              const bel = (Number(a.totalt_ore) / 100).toLocaleString("nb-NO", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
              return "<li><strong>" + a.ar + "</strong>: " + bel + " kr <span class=\"medlemsoversikt-dempa\">(" + a.antall_medlemer_med_betaling + " medlemmar med innbetaling)</span></li>";
            }).join("") + "</ul>";
        }
        el.innerHTML =
          "<h2 class=\"medlemsoversikt-tittel\">Medlemsoversikt</h2>" +
          "<h3 class=\"medlemsoversikt-seksjon\">Aldersfordeling</h3>" +
          "<p class=\"medlemsoversikt-tal\">" + alderLinje + "</p>" +
          "<h3 class=\"medlemsoversikt-seksjon\">Innbetaling</h3>" +
          "<p class=\"medlemsoversikt-tal\"><strong>Gjeldande medlemsår: " + ar + "</strong> · " +
          "<strong>Totalt innbetalt hittil i " + ar + ":</strong> " + tot + " kr " +
          "<span class=\"medlemsoversikt-dempa\">(" + n + " medlemmar med innbetaling)</span></p>" +
          arkivHtml +
          "<p class=\"medlemsoversikt-nyttar\"><button type=\"button\" class=\"btn sekundaer\" id=\"btn-lukk-medlemsar\">Lukk medlemsår " + ar + " og start " + (ar + 1) + " …</button></p>";
        document.getElementById("btn-lukk-medlemsar").addEventListener("click", () => lukkMedlemsar(ar));
      } catch (e) {
        el.innerHTML = "<p class=\"feil\">" + escapeHtml(e.message) + "</p>";
      }
    }

    function openModal(id) {
      skjema.dispatchEvent(new CustomEvent("skjemasteg:start"));
      const tittel = document.getElementById("modal-tittel");
      document.getElementById("medlem-id").value = id || "";
      tittel.textContent = id ? "Rediger medlem" : "Legg til medlem";
      skjemaFeil.style.display = "none";
      if (id) {
        fetch(API + "/api/members/" + id, { credentials: "same-origin" })
          .then(r => r.json())
          .then(m => {
            document.getElementById("fornamn").value = m.fornamn ?? (m.full_name || "");
            document.getElementById("mellomnamn").value = m.mellomnamn || "";
            document.getElementById("etternamn").value = m.etternamn || "";
            document.getElementById("email").value = m.email || "";
            document.getElementById("phone").value = m.phone || "";
            document.getElementById("adresse").value = m.adresse || "";
            document.getElementById("postnummer").value = m.postnummer || "";
            document.getElementById("poststad").value = m.poststad || "";
            document.getElementById("birth_date").value = m.birth_date || "";
            document.getElementById("membership_type").value = medlemstypeTilVerdi(m.membership_type);
            document.getElementById("payment_status").value = m.payment_status || "ikkje betalt";
          });
      } else {
        document.getElementById("fornamn").value = "";
        document.getElementById("mellomnamn").value = "";
        document.getElementById("etternamn").value = "";
        document.getElementById("email").value = "";
        document.getElementById("phone").value = "";
        document.getElementById("adresse").value = "";
        document.getElementById("postnummer").value = "";
        document.getElementById("poststad").value = "";
        document.getElementById("birth_date").value = "";
        document.getElementById("membership_type").value = "vanleg";
        document.getElementById("payment_status").value = "ikkje betalt";
      }
      document.getElementById("approve-payment-status").checked = false;
      modal.style.display = "flex";
      modal.setAttribute("aria-hidden", "false");
      document.getElementById("fornamn").focus();
    }

    function lukkModal() {
      modal.style.display = "none";
      modal.setAttribute("aria-hidden", "true");
    }

    document.getElementById('betaling-historikk').addEventListener('click', async (event) => {
      const button = event.target.closest('button[data-slett-betaling]');
      if (!button) return;
      const mid = Number(document.getElementById('betaling-medlem-id').value);
      const pid = Number(button.dataset.slettBetaling);
      const amount = formatNokFromOre(Number(button.dataset.belop));
      if (!confirm('Slett registreringa på ' + amount + ' for medlemsår ' + button.dataset.ar + '? Status og medlemstype blir rekna på nytt. Dette refunderer ikkje pengar.')) return;
      button.disabled = true;
      const error = document.getElementById('betaling-feil');
      error.style.display = 'none';
      try {
        const r = await fetch(API + '/api/members/' + mid + '/payments/' + pid, {method:'DELETE'});
        const data = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(data.error || 'Kunne ikkje slette betalinga.');
        await lastBetalingar(mid);
        renderListe(await hentMedlemmar());
        await lastOversikt();
        setStatus(data.message);
      } catch (e) {
        error.textContent = e.message;
        error.style.display = 'block';
        button.disabled = false;
      }
    });

    async function lastBetalingar(id) {
      const hist = document.getElementById("betaling-historikk");
      const sumEl = document.getElementById("betaling-sum");
      hist.innerHTML = "Lastar betalingar …";
      try {
        const r = await fetch(API + "/api/members/" + id + "/payments", { credentials: "same-origin" });
        const data = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(data.error || "Kunne ikkje hente betalingar");
        const ar = data.medlemsbetalingsar;
        const yearNok = (Number(data.total_ore || 0) / 100).toFixed(2);
        const allNok = data.total_ore_all != null
          ? (Number(data.total_ore_all) / 100).toFixed(2)
          : yearNok;
        if (ar != null) {
          let t = "Medlemsår " + ar + ": " + yearNok + " kr";
          if (data.total_ore_all != null && Number(data.total_ore_all) !== Number(data.total_ore)) {
            t += " · Samla alle år: " + allNok + " kr";
          }
          sumEl.textContent = t;
        } else {
          sumEl.textContent = "Totalt registrert: " + yearNok + " kr";
        }
        const rows = data.payments || [];
        if (!rows.length) {
          hist.innerHTML = "<p>Ingen betalingar registrert enno.</p>";
          return;
        }
        hist.innerHTML = '<p class="betaling-rad-overskrift">Beløp · Medlemsår · Dato · Notat</p>' + rows.map(p => `
          <div class="betaling-rad">
            <strong>${(Number(p.amount_ore || 0) / 100).toFixed(2)} kr</strong>
            <span>${p.for_year != null ? escapeHtml(String(p.for_year)) : "–"}</span>
            <span>${escapeHtml(formaterDato(p.paid_at))}</span>
            <span>${escapeHtml(p.note || "")}<br>
            ${p.vipps ? '<span>Vipps – må avstemmast ved refusjon</span>' : p.for_year === ar ? `<button type="button" class="btn sekundaer" data-slett-betaling="${Number(p.id)}" data-belop="${Number(p.amount_ore)}" data-ar="${Number(p.for_year)}">Slett</button>` : '<span>Avslutta år</span>'}</span>
          </div>
        `).join("");
      } catch (e) {
        hist.innerHTML = "<p class=\"feil\">" + escapeHtml(e.message) + "</p>";
      }
    }

    function openBetalingModal(id) {
      document.getElementById("betaling-medlem-id").value = String(id);
      document.getElementById("betaling-belop").value = "";
      document.getElementById("betaling-dato").value = "";
      document.getElementById("betaling-notat").value = "";
      betalingFeil.style.display = "none";
      betalingModal.style.display = "flex";
      betalingModal.setAttribute("aria-hidden", "false");
      document.getElementById("betaling-belop").focus();
      lastBetalingar(id);
    }

    function lukkBetalingModal() {
      betalingModal.style.display = "none";
      betalingModal.setAttribute("aria-hidden", "true");
    }

    skjema.addEventListener("submit", async (e) => {
      e.preventDefault();
      skjemaFeil.style.display = "none";
      const id = document.getElementById("medlem-id").value;
      const body = {
        fornamn: document.getElementById("fornamn").value.trim(),
        mellomnamn: document.getElementById("mellomnamn").value.trim(),
        etternamn: document.getElementById("etternamn").value.trim(),
        email: document.getElementById("email").value.trim(),
        phone: document.getElementById("phone").value.trim(),
        adresse: document.getElementById("adresse").value.trim(),
        postnummer: document.getElementById("postnummer").value.trim(),
        poststad: document.getElementById("poststad").value.trim(),
        birth_date: document.getElementById("birth_date").value.trim() || null,
        membership_type: document.getElementById("membership_type").value,
        payment_status: document.getElementById("payment_status").value,
        approve_payment_status: document.getElementById("approve-payment-status").checked
      };
      if (!id) body.consent_at = new Date().toISOString();
      const url = id ? API + "/api/members/" + id : API + "/api/members";
      const method = id ? "PUT" : "POST";
      try {
        const r = await fetch(url, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), credentials: "same-origin" });
        const data = await r.json().catch(() => ({}));
        if (!r.ok) { skjemaFeil.textContent = data.error || "Feil ved lagring"; skjemaFeil.style.display = "block"; return; }
        lukkModal();
        const medlemmar = await hentMedlemmar();
        renderListe(medlemmar);
      } catch (err) {
        skjemaFeil.textContent = err.message;
        skjemaFeil.style.display = "block";
      }
    });

    document.getElementById("btn-avbryt").addEventListener("click", lukkModal);
    document.getElementById("btn-betaling-avbryt").addEventListener("click", lukkBetalingModal);
    document.getElementById("btn-ny").addEventListener("click", () => openModal(null));

    listeEl.addEventListener("click", (e) => {
      const toggleEl = e.target.closest("[data-action=\"toggle-payment\"]");
      if (toggleEl) {
        e.preventDefault();
        const id = parseInt(toggleEl.dataset.id, 10);
        const current = (toggleEl.dataset.status || "").trim().toLowerCase();
        if (!isNaN(id)) toggleBetalingsstatus(id, current);
        return;
      }

      const id = parseInt(e.target.dataset?.id, 10);
      if (e.target.classList.contains("aksjonar-meny-knapp")) {
        e.preventDefault();
        e.stopPropagation();
        const ramme = e.target.closest(".aksjonar-meny-wrap");
        const menu = ramme?.querySelector(".aksjonar-meny");
        const cell = ramme?.closest("td");
        if (!menu || !cell) return;
        if (menu.hidden) {
          lukkAlleAksjonarMenyer();
          opneAksjonarMeny(e.target, menu, cell);
        } else {
          lukkAlleAksjonarMenyer();
        }
        return;
      }
      if (e.target.closest(".aksjonar-meny") && e.target.dataset?.action) {
        e.preventDefault();
        if (!isNaN(id)) {
          if (e.target.dataset.action === "export") eksporterMedlem(id);
          else if (e.target.dataset.action === "betaling") openBetalingModal(id);
          else if (e.target.dataset.action === "delete") slettMedlem(id);
        }
        lukkAlleAksjonarMenyer();
        return;
      }
      if (e.target.dataset?.action === "edit") {
        e.preventDefault();
        if (!isNaN(id)) openModal(id);
      }
    });

    document.addEventListener("click", (e) => {
      if (!e.target.closest(".aksjonar-meny-wrap")) lukkAlleAksjonarMenyer();
    });

    modal.addEventListener("click", (e) => { if (e.target === modal) lukkModal(); });
    betalingModal.addEventListener("click", (e) => { if (e.target === betalingModal) lukkBetalingModal(); });

    async function eksporterMedlem(id) {
      try {
        const r = await fetch(API + "/api/gdpr/export/" + id, { credentials: "same-origin" });
        const m = await r.json();
        const blob = new Blob([JSON.stringify(m, null, 2)], { type: "application/json" });
        const a = document.createElement("a");
        a.href = URL.createObjectURL(blob);
        a.download = "medlem-" + id + "-data.json";
        a.click();
        URL.revokeObjectURL(a.href);
        setStatus("Eksportert medlem " + id);
      } catch (e) { setStatus("Kunne ikkje eksportere.", true); }
    }

    async function slettMedlem(id) {
      if (!confirm("Slette medlemsopplysningar og eventuell styretilgang? Bokførte beløp blir bevarte utan kontaktopplysningar.")) return;
      try {
        const r = await fetch(API + "/api/gdpr/delete/" + id, { method: "POST", credentials: "same-origin" });
        const data = await r.json();
        if (!r.ok) throw new Error(data.error || "Sletting feila");
        setStatus(data.message || "Medlem sletta.");
        const medlemmar = await hentMedlemmar();
        renderListe(medlemmar);
      } catch (e) { setStatus(e.message || "Kunne ikkje slette.", true); }
    }

    betalingSkjema.addEventListener("submit", async (e) => {
      e.preventDefault();
      betalingFeil.style.display = "none";
      const id = parseInt(document.getElementById("betaling-medlem-id").value, 10);
      const body = {
        amount_nok: document.getElementById("betaling-belop").value,
        paid_at: document.getElementById("betaling-dato").value,
        note: document.getElementById("betaling-notat").value.trim()
      };
      try {
        const r = await fetch(API + "/api/members/" + id + "/payments", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          credentials: "same-origin",
          body: JSON.stringify(body)
        });
        const data = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(data.error || "Kunne ikkje lagre betaling");
        setStatus("Betaling registrert.");
        document.getElementById("betaling-belop").value = "";
        document.getElementById("betaling-notat").value = "";
        await lastBetalingar(id);
        renderListe(await hentMedlemmar());
        lastOversikt();
      } catch (err) {
        betalingFeil.textContent = err.message;
        betalingFeil.style.display = "block";
      }
    });


    async function toggleBetalingsstatus(id, currentStatus) {
      const nyStatus = currentStatus === "betalt" ? "ikkje betalt" : "betalt";
      try {
        const r = await fetch(API + "/api/members/" + id, {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          credentials: "same-origin",
          body: JSON.stringify({ payment_status: nyStatus })
        });
        const data = await r.json().catch(() => ({}));
        if (!r.ok) throw new Error(data.error || "Kunne ikkje oppdatere betalingsstatus");
        setStatus("Betalingsstatus oppdatert.");
        const medlemmar = await hentMedlemmar();
        renderListe(medlemmar);
      } catch (e) {
        setStatus(e.message || "Kunne ikkje oppdatere betalingsstatus.", true);
      }
    }

    const KOLONNE_STORAGE_KEY = "bygdelista-kolonner";
    function brukKolonnefilter() {
      document.querySelectorAll(".kolonnefilter input[data-col]").forEach(cb => {
        const col = cb.dataset.col;
        document.querySelectorAll(`.tabell-ramme [data-col="${col}"]`).forEach(el => {
          el.classList.toggle("kolonne-skjult", !cb.checked);
        });
      });
      const prefs = {};
      document.querySelectorAll(".kolonnefilter input[data-col]").forEach(cb => { prefs[cb.dataset.col] = cb.checked; });
      try { localStorage.setItem(KOLONNE_STORAGE_KEY, JSON.stringify(prefs)); } catch (_) {}
    }
    function lastKolonnefilter() {
      try {
        const s = localStorage.getItem(KOLONNE_STORAGE_KEY);
        if (s) {
          const prefs = JSON.parse(s);
          document.querySelectorAll(".kolonnefilter input[data-col]").forEach(cb => {
            if (Object.prototype.hasOwnProperty.call(prefs, cb.dataset.col)) {
              cb.checked = !!prefs[cb.dataset.col];
            }
          });
        }
      } catch (_) {}
      brukKolonnefilter();
    }
    document.querySelectorAll(".kolonnefilter input[data-col]").forEach(cb => {
      cb.addEventListener("change", brukKolonnefilter);
    });

    async function lastKontingentinnstillingar() {
      try {
        const r = await fetch(API + '/api/innstillingar/kontingent');
        if (!r.ok) throw new Error('Kunne ikkje hente kontingentinnstillingar.');
        const data = await r.json();
        document.getElementById('superkul-grense').value = (data.superkul_grense_ore / 100).toFixed(2);
        document.getElementById('superkul-grense').disabled = false;
        document.getElementById('lagre-kontingent').disabled = false;
      } catch (error) { setStatus(error.message, true); }
    }
    document.getElementById('kontingent-innstillingar').addEventListener('submit', async (event) => {
      event.preventDefault();
      const button = document.getElementById('lagre-kontingent');
      button.disabled = true;
      try {
        const r = await fetch(API + '/api/innstillingar/kontingent', {
          method: 'PUT', headers: {'Content-Type': 'application/json'},
          body: JSON.stringify({superkul_grense_nok: document.getElementById('superkul-grense').value})
        });
        const data = await r.json();
        if (!r.ok) throw new Error(data.error || 'Kunne ikkje lagre grensa.');
        renderListe(await hentMedlemmar());
        setStatus('Grensa er lagra og medlemstypane er oppdaterte.');
      } catch (error) { setStatus(error.message, true); }
      finally { button.disabled = false; }
    });

    (async () => {
      lastKontingentinnstillingar();
      lastOversikt();
      const medlemmar = await hentMedlemmar();
      renderListe(medlemmar);
      lastKolonnefilter();
    })();
