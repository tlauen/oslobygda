
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
          return null;
        }
        const data = await r.json();
        setStatus("");
        return data;
      } catch (e) {
        setStatus("Feil ved lasting: " + e.message, true);
        return null;
      }
    }

    let alleMedlemmar = [];
    let side = 1;
    const sidestorleik = 25;
    const medlemSok = document.getElementById('medlem-soketekst');
    const statusFilter = document.getElementById('medlem-status');
    const typeFilter = document.getElementById('medlem-type');
    const sortering = document.getElementById('medlem-sortering');
    const collator = new Intl.Collator('nn', {sensitivity:'base', numeric:true});
    const normaliser = value => String(value || '').normalize('NFKC').toLocaleLowerCase('nn').trim();

    function renderListe(medlemmar) {
      if (!Array.isArray(medlemmar)) return;
      alleMedlemmar = medlemmar;
      visMedlemsutval();
    }
    function visMedlemsutval() {
      const query = normaliser(medlemSok.value);
      const result = alleMedlemmar.filter(m =>
        (!query || normaliser(visningsnamn(m) + ' ' + (m.email || '')).includes(query)) &&
        (!statusFilter.value || normaliser(m.payment_status) === normaliser(statusFilter.value)) &&
        (!typeFilter.value || medlemstypeVisningsnamn(m.membership_type) === typeFilter.value)
      ).sort((a, b) => (sortering.value === 'desc' ? -1 : 1) * collator.compare(visningsnamn(a), visningsnamn(b)) || Number(a.id) - Number(b.id));
      const sider = Math.max(1, Math.ceil(result.length / sidestorleik));
      side = Math.min(side, sider);
      const start = (side - 1) * sidestorleik;
      tegnMedlemsrader(result.slice(start, start + sidestorleik));
      document.getElementById('medlem-treff').textContent = result.length
        ? `Viser ${start + 1}–${Math.min(start + sidestorleik, result.length)} av ${result.length} medlemmar` : 'Ingen treff';
      document.getElementById('medlem-ingen').hidden = result.length !== 0;
      document.getElementById('medlem-forre').disabled = side === 1;
      document.getElementById('medlem-neste').disabled = side === sider;
      document.getElementById('medlem-sidetal').textContent = `Side ${side} av ${sider}`;
    }
    function oppdaterUtval() { side = 1; visMedlemsutval(); }
    document.getElementById('medlem-sok').addEventListener('submit', event => { event.preventDefault(); oppdaterUtval(); });
    medlemSok.addEventListener('input', oppdaterUtval);
    for (const control of [statusFilter, typeFilter, sortering]) control.addEventListener('change', oppdaterUtval);
    document.getElementById('medlem-nullstill').addEventListener('click', () => {
      medlemSok.value = ''; statusFilter.value = ''; typeFilter.value = ''; sortering.value = 'asc';
      oppdaterUtval(); medlemSok.focus();
    });
    for (const [id, delta] of [['medlem-forre', -1], ['medlem-neste', 1]]) document.getElementById(id).addEventListener('click', () => {
      side += delta; visMedlemsutval(); document.getElementById('medlem-treff').scrollIntoView({block:'nearest'});
    });

    const detalj = document.getElementById('medlem-detalj');
    function opneMedlem(id) {
      const m = alleMedlemmar.find(m => Number(m.id) === id);
      if (!m) return;
      document.getElementById('medlem-detalj-innhald').innerHTML = `
        <h2 id="medlem-detalj-tittel">${escapeHtml(visningsnamn(m))}</h2>
        <p>${escapeHtml(medlemstypeVisningsnamn(m.membership_type))} · ${escapeHtml(m.payment_status)}</p>
        <div class="knappar"><button type="button" data-member-edit="${id}">Endre opplysningar</button><button type="button" class="sekundaer" data-member-payment="${id}">Registrer betaling</button></div>
        <h3>Kontaktopplysningar</h3><dl class="medlem-detaljar">
          ${[['E-post',m.email],['Telefon',m.phone],['Adresse',[m.adresse,m.postnummer,m.poststad].filter(Boolean).join(', ')]].map(([label,value]) => `<div><dt>${label}</dt><dd>${escapeHtml(value || 'Ikkje registrert')}</dd></div>`).join('')}
        </dl><details><summary>Fødselsdato og samtykke</summary><dl class="medlem-detaljar"><div><dt>Fødselsdato</dt><dd>${escapeHtml(formaterDato(m.birth_date))}</dd></div><div><dt>Samtykke registrert</dt><dd>${escapeHtml(formaterDato(m.consent_at))}</dd></div></dl></details>
        <h3>Medlemskap og betalingar</h3><p>Registrert i gjeldande medlemsår: ${formatNokFromOre(m.total_paid_ore)}.</p><p>Vel «Registrer betaling» for å sjå betalingshistorikken.</p>`;
      detalj.showModal();
    }
    document.getElementById('medlem-detalj-lukk').addEventListener('click', () => detalj.close());
    detalj.addEventListener('click', event => {
      const edit = event.target.closest('[data-member-edit]');
      const payment = event.target.closest('[data-member-payment]');
      if (edit || payment) {
        detalj.close();
        if (edit) openModal(Number(edit.dataset.memberEdit));
        else openBetalingModal(Number(payment.dataset.memberPayment));
      }
    });

    function tegnMedlemsrader(medlemmar) {
      listeEl.innerHTML = medlemmar.map(m => `
        <tr>
          <td data-col="namn"><button type="button" class="medlem-lenkje" data-action="detail" data-id="${Number(m.id)}">${escapeHtml(visningsnamn(m))}</button></td>
          <td data-col="epost">${escapeHtml(m.email)}</td>
          <td data-col="telefon">${escapeHtml(m.phone || "–")}</td>
          <td data-col="adresse">${escapeHtml(m.adresse || "–")}</td>
          <td data-col="postnr">${escapeHtml(m.postnummer || "–")}</td>
          <td data-col="poststad">${escapeHtml(m.poststad || "–")}</td>
          <td data-col="fødselsdato">${escapeHtml(formaterDato(m.birth_date))}</td>
          <td data-col="medlemstype"><span class="pill">${escapeHtml(medlemstypeVisningsnamn(m.membership_type))}</span></td>
          <td data-col="betalingsstatus">
            <span class="${pillClassForPaymentStatus(m.payment_status)}">${escapeHtml(m.payment_status)}</span>
            <div class="sum-reg">${formatNokFromOre(m.total_paid_ore)}</div>
          </td>
          <td data-col="samtykke">${formaterDato(m.consent_at)}</td>
          <td data-col="aksjonar" class="aksjonar">
            <a href="#" data-id="${m.id}" data-action="detail">Opne medlem</a>
            <div class="aksjonar-meny-wrap">
              <button type="button" class="aksjonar-meny-knapp" data-id="${m.id}" aria-label="Fleire handlingar for ${escapeHtml(visningsnamn(m))}" aria-expanded="false"><span class="aksjonar-meny-prikker"><span></span><span></span><span></span></span></button>
              <div class="aksjonar-meny" hidden>
                <button type="button" data-id="${m.id}" data-action="export">Eksporter (GDPR)</button>
                <button type="button" data-id="${m.id}" data-action="betaling">Registrer betaling</button>
                <button type="button" data-id="${m.id}" data-action="delete" class="slett">Slett</button>
              </div>
            </div>
          </td>
        </tr>
      `).join("");
      const labels = Object.fromEntries([...document.querySelectorAll('#medlemstabell th[data-col]')].map(th => [th.dataset.col, th.textContent.trim()]));
      listeEl.querySelectorAll('td[data-col]').forEach(cell => { cell.dataset.label = labels[cell.dataset.col] || 'Handlingar'; });
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
        el.innerHTML = `<p class="medlemsoversikt-tittel">Medlemsår ${ar} · ${mTot} medlemmar</p><details><summary>Statistikk og tidlegare år</summary><p>${alderLinje}</p><p>Totalt innbetalt: ${tot} kr · ${n} medlemmar med innbetaling.</p>${arkivHtml}</details>`;
      } catch (e) {
        el.innerHTML = "<p class=\"feil\">" + escapeHtml(e.message) + "</p>";
      }
    }

    let modalRetur = null;
    let betalingRetur = null;
    function openModal(id) {
      modalRetur = document.activeElement;
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
      if (modalRetur?.isConnected) modalRetur.focus();
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
      betalingRetur = document.activeElement;
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
      if (betalingRetur?.isConnected) betalingRetur.focus();
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
      if (e.target.dataset?.action === "detail") {
        e.preventDefault();
        if (!isNaN(id)) opneMedlem(id);
      }
    });

    document.addEventListener("click", (e) => {
      if (!e.target.closest(".aksjonar-meny-wrap")) lukkAlleAksjonarMenyer();
    });

    modal.addEventListener("click", (e) => { if (e.target === modal) lukkModal(); });
    betalingModal.addEventListener("click", (e) => { if (e.target === betalingModal) lukkBetalingModal(); });

    document.addEventListener('keydown', event => {
      const overlay = modal.style.display === 'flex' ? modal : betalingModal.style.display === 'flex' ? betalingModal : null;
      if (!overlay) return;
      if (event.key === 'Escape') { event.preventDefault(); overlay === modal ? lukkModal() : lukkBetalingModal(); }
      if (event.key === 'Tab') {
        const focusable = [...overlay.querySelectorAll('input,select,textarea,button,a[href],[tabindex="0"]')].filter(el => !el.disabled && !el.closest('[hidden]') && el.getClientRects().length);
        const first = focusable[0], last = focusable.at(-1);
        if (first && event.shiftKey && document.activeElement === first) { event.preventDefault(); last.focus(); }
        else if (last && !event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
      }
    });

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

    (async () => {
      lastKolonnefilter();
      lastOversikt();
      const medlemmar = await hentMedlemmar();
      renderListe(medlemmar);
    })();
