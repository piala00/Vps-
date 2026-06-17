/**
 * NEXORA v2.0 — Module Comptabilite & Finance
 * Grand Livre + 6 onglets Creances depuis GTC ERP PILOT V3
 */

var autoLoad = {
    'compta-dashboard': function(){ chargerDashCompta(); },
    'gl-vue':           function(){ /* chargement manuel */ },
    'cr-global':        function(){ chargerCreances(); },
    'cr-aging':         function(){ afficherAging(); },
    'cr-zones':         function(){ afficherZones(); },
    'cr-commerciaux':   function(){ afficherParCom(); },
    'cr-clients':       function(){ afficherParClients(); },
    'cr-priorite':      function(){ afficherPriorite(); },
    'compta-caisse':    function(){ chargerRapportsCaisse(); },
};

var _glData       = null;
var _crData       = null;

// ── Dashboard ──────────────────────────────────────────────────

function chargerDashCompta() {
    var kpis = document.getElementById('compta-kpis');
    if (kpis) kpis.innerHTML = '<div class="tbl-empty"><span class="loader"></span> Chargement...</div>';
    apiGet(nexoraAppendPeriode('/api/comptabilite/evolution-creances'), function(d) {
        var clients = d.clients || [];
        if (!clients.length && d.message) {
            if (kpis) kpis.innerHTML = '<div class="alert alert-warn" style="grid-column:1/-1">⚠️ ' + d.message +
                '. Verifiez la connexion Sage ou importez un fichier Excel dans Parametres &gt; Source &amp; Config.</div>';
            return;
        }
        var total  = clients.reduce(function(s,c){ return s+c.solde; }, 0);
        var fns    = clients.reduce(function(s,c){ return s+c.fns;   }, 0);
        var crit   = clients.filter(function(c){ return c.niveau_risque === 'CRITIQUE'; }).length;
        if (kpis) kpis.innerHTML =
            kpiCard('💳', 'Creances totales', fmt.money(total), '#EF4444') +
            kpiCard('⏰', 'Creances echues',  fmt.money(fns),   '#F59E0B') +
            kpiCard('🚨', 'Critiques',        crit + ' clients', '#EF4444') +
            kpiCard('👥', 'Clients analyses', clients.length,   '#1A3263');
    }, function(e) {
        if (kpis) kpis.innerHTML = '<div class="alert alert-warn" style="grid-column:1/-1">⚠️ Erreur de chargement: ' + e + '</div>';
        status('Erreur de connexion');
    });
}

// ── Grand Livre ────────────────────────────────────────────────

function chargerGL(force) {
    var url = nexoraAppendPeriode('/api/comptabilite/grand-livre') + (force ? '&force=1' : '');
    tableLoader('gl-tbody', 16);
    var totEl = document.getElementById('gl-totaux');
    if (totEl) totEl.textContent = 'Chargement...';
    apiGet(url, function(d) {
        _glData = d;
        // Peupler filtre commerciaux
        var comSel = document.getElementById('gl-com-fil');
        if (comSel && d.commerciaux) {
            comSel.innerHTML = '<option value="">Tous</option>';
            d.commerciaux.forEach(function(c) {
                var opt = document.createElement('option');
                opt.value = c; opt.textContent = c;
                comSel.appendChild(opt);
            });
        }
        filtrerGL();
        if (totEl) totEl.textContent =
            'Total Debit: ' + fmt.money(d.total_debit||0) +
            ' | Total Credit: ' + fmt.money(d.total_credit||0) +
            ' | Solde Debit: ' + fmt.money(d.total_solde||0);
    }, function() {
        tableVide('gl-tbody', 16, 'Sage non disponible');
    });
}

function filtrerGL() {
    if (!_glData) return;
    var q    = document.getElementById('gl-search')   ? document.getElementById('gl-search').value.toLowerCase()   : '';
    var com  = document.getElementById('gl-com-fil')  ? document.getElementById('gl-com-fil').value                : '';
    var type = document.getElementById('gl-type-fil') ? document.getElementById('gl-type-fil').value               : '';
    var lignes = (_glData.lignes || []).filter(function(r) {
        if (com  && r.commercial !== com)  return false;
        if (type && r.type !== type)       return false;
        if (q && !(r.code+r.nom+r.piece+r.libelle+r.commercial).toLowerCase().includes(q)) return false;
        return true;
    });
    var tbody = document.getElementById('gl-tbody');
    var nbEl  = document.getElementById('gl-nb');
    if (!tbody) return;
    if (!lignes.length) { tableVide('gl-tbody', 16, 'Aucune ligne'); if(nbEl) nbEl.textContent=''; return; }
    if (nbEl) nbEl.textContent = lignes.length + ' lignes';
    tbody.innerHTML = lignes.map(function(r) {
        var retCol = r.retard > 30 ? 'color:var(--red)' : r.retard > 0 ? 'color:var(--warn)' : '';
        var staCol = r.statut === 'Non Soldee' ? 'color:var(--red)' : 'color:var(--green)';
        var bgRow  = r.is_total ? 'background:rgba(251,192,19,.08);font-weight:700' : '';
        return '<tr style="' + bgRow + '">' +
               '<td style="font-family:monospace;font-weight:700;color:var(--navy)">' + (r.code||'-') + '</td>' +
               '<td>' + (r.nom||'-') + '</td>' +
               '<td>' + fmt.date(r.date) + '</td>' +
               '<td>' + (r.journal||'-') + '</td>' +
               '<td style="font-family:monospace">' + (r.piece||'-') + '</td>' +
               '<td style="max-width:180px;overflow:hidden;white-space:nowrap">' + (r.libelle||'-') + '</td>' +
               '<td style="text-align:right">' + (r.debit ? fmt.money(r.debit) : '') + '</td>' +
               '<td style="text-align:right;color:var(--green)">' + (r.credit ? fmt.money(r.credit) : '') + '</td>' +
               '<td style="text-align:right">' + (r.solde_d ? fmt.money(r.solde_d) : '') + '</td>' +
               '<td style="text-align:right">' + (r.solde_c ? fmt.money(r.solde_c) : '') + '</td>' +
               '<td style="' + staCol + '">' + (r.statut||'-') + '</td>' +
               '<td style="text-align:right;color:var(--red);font-weight:700">' + (r.ouvert ? fmt.money(r.ouvert) : '') + '</td>' +
               '<td style="' + retCol + '">' + fmt.date(r.echeance) + '</td>' +
               '<td style="' + retCol + ';font-weight:700">' + (r.retard > 0 ? r.retard + 'j' : '') + '</td>' +
               '<td>' + (r.commercial||'-') + '</td>' +
               '<td>' + badge(r.type||'-', r.type==='FACTURE'?'navy':r.type==='REGLEMENT'?'ok':r.type==='AVOIR'?'warn':'muted') + '</td>' +
               '</tr>';
    }).join('');
}

// ── Créances ──────────────────────────────────────────────────

function chargerCreances() {
    var q    = document.getElementById('cr-search')      ? document.getElementById('cr-search').value       : '';
    var zone = document.getElementById('cr-zone-fil')    ? document.getElementById('cr-zone-fil').value     : '';
    var reto = document.getElementById('cr-retard-only') ? document.getElementById('cr-retard-only').checked : false;
    var url  = nexoraAppendPeriode('/api/comptabilite/creances');
    if (q)    url += '&q='    + encodeURIComponent(q);
    if (zone) url += '&zone=' + encodeURIComponent(zone);
    if (reto) url += '&retard_only=1';
    tableLoader('cr-global-tbody', 12);
    apiGet(url, function(d) {
        _crData = d;
        // Peupler filtre zones
        var zoneSel = document.getElementById('cr-zone-fil');
        if (zoneSel && d.zones) {
            zoneSel.innerHTML = '<option value="">Toutes</option>';
            d.zones.forEach(function(z) {
                var opt = document.createElement('option'); opt.value=z; opt.textContent=z;
                zoneSel.appendChild(opt);
            });
        }
        // Totaux
        var tot = d.totaux || {};
        var totEl = document.getElementById('cr-totaux');
        if (totEl) totEl.textContent =
            tot.nb_clients + ' clients | Solde: ' + fmt.money(tot.solde) +
            ' | FNS: ' + fmt.money(tot.fnstot) +
            ' | Echues: ' + fmt.money(tot.fns_echu) +
            ' | Depassements: ' + fmt.money(tot.depasses);
        // Tableau global
        var tbody = document.getElementById('cr-global-tbody');
        if (tbody) {
            var clients = d.clients || [];
            if (!clients.length) { tableVide('cr-global-tbody', 12, 'Aucune creance'); }
            else tbody.innerHTML = clients.map(function(c) {
                var retCol = c.retard > 30 ? 'color:var(--red)' : c.retard > 0 ? 'color:var(--warn)' : '';
                return '<tr>' +
                       '<td style="font-weight:700;color:var(--navy)">' + (c.code||'-') + '</td>' +
                       '<td>' + (c.nom||'-') + '</td>' +
                       '<td>' + (c.zone||'-') + '</td>' +
                       '<td>' + (c.commercial||'-') + '</td>' +
                       '<td style="font-weight:700">' + fmt.money(c.solde||0) + '</td>' +
                       '<td style="color:var(--warn)">' + fmt.money(c.fnstot||0) + '</td>' +
                       '<td style="color:var(--red);font-weight:700">' + fmt.money(c.fns||0) + '</td>' +
                       '<td>' + (c.nf||0) + '</td>' +
                       '<td style="font-weight:700;' + retCol + '">' + (c.retard||0) + 'j</td>' +
                       '<td>' + (c.mdp ? fmt.money(c.mdp) : '-') + '</td>' +
                       '<td>' + (c.plafond ? fmt.money(c.plafond) : '-') + '</td>' +
                       '<td>' + (c.telephone||'-') + '</td>' +
                       '</tr>';
            }).join('');
        }
        afficherAging();
        afficherZones();
        afficherParCom();
        afficherParClients();
        afficherPriorite();
    }, function() {
        tableVide('cr-global-tbody', 12, 'Sage non disponible');
    });
}

function afficherAging() {
    if (!_crData) return;
    var aging  = _crData.aging || [];
    var infoEl = document.getElementById('cr-aging-info');
    var tbody  = document.getElementById('cr-aging-tbody');
    if (infoEl && _crData.totaux) {
        infoEl.textContent = 'Total creances echues : ' + fmt.money(_crData.totaux.fns_echu || 0) + ' FCFA';
    }
    if (!tbody) return;
    tbody.innerHTML = aging.map(function(a) {
        var col = a.tranche.includes('90') ? 'color:var(--red)' :
                  (a.tranche.includes('31') || a.tranche.includes('61')) ? 'color:var(--warn)' : '';
        return '<tr style="' + col + '">' +
               '<td style="font-weight:700">' + a.tranche + '</td>' +
               '<td>' + a.nb + '</td>' +
               '<td style="font-weight:700">' + fmt.money(a.montant) + '</td>' +
               '<td>' + a.pct + '%</td></tr>';
    }).join('') || '<tr><td colspan="4" class="tbl-empty">Chargez les creances</td></tr>';
}

function afficherZones() {
    if (!_crData) return;
    var tbody = document.getElementById('cr-zones-tbody');
    if (!tbody) return;
    var rows = _crData.par_zone || [];
    tbody.innerHTML = rows.map(function(z) {
        var col = z.retard > 30 ? 'color:var(--red)' : z.retard > 0 ? 'color:var(--warn)' : '';
        return '<tr><td style="font-weight:700">' + (z.zone||'N/A') + '</td>' +
               '<td>' + z.nb + '</td>' +
               '<td>' + fmt.money(z.solde) + '</td>' +
               '<td style="color:var(--red);font-weight:700">' + fmt.money(z.fns) + '</td>' +
               '<td style="' + col + ';font-weight:700">' + z.retard + 'j</td></tr>';
    }).join('') || '<tr><td colspan="5" class="tbl-empty">Chargez les creances</td></tr>';
}

function afficherParCom() {
    if (!_crData) return;
    var tbody = document.getElementById('cr-com-tbody');
    if (!tbody) return;
    var rows = _crData.par_commercial || [];
    tbody.innerHTML = rows.map(function(c) {
        var col = c.retard > 30 ? 'color:var(--red)' : c.retard > 0 ? 'color:var(--warn)' : '';
        return '<tr><td style="font-weight:700">' + (c.commercial||'N/A') + '</td>' +
               '<td>' + c.nb + '</td>' +
               '<td>' + fmt.money(c.solde) + '</td>' +
               '<td style="color:var(--red);font-weight:700">' + fmt.money(c.fns) + '</td>' +
               '<td style="' + col + ';font-weight:700">' + c.retard + 'j</td>' +
               '<td>' + (c.mdp ? fmt.money(c.mdp) : '-') + '</td></tr>';
    }).join('') || '<tr><td colspan="6" class="tbl-empty">Chargez les creances</td></tr>';
}

function afficherParClients() {
    if (!_crData) return;
    var tbody  = document.getElementById('cr-clients-tbody');
    if (!tbody) return;
    var sorted = (_crData.clients || []).slice().sort(function(a,b){ return b.fns - a.fns; });
    tbody.innerHTML = sorted.map(function(c, i) {
        var col = c.retard > 30 ? 'color:var(--red)' : c.retard > 0 ? 'color:var(--warn)' : '';
        return '<tr><td style="font-weight:800;color:var(--gold)">' + (i+1) + '</td>' +
               '<td style="font-weight:700">' + (c.nom||'-') + '</td>' +
               '<td>' + (c.commercial||'-') + '</td>' +
               '<td style="color:var(--red);font-weight:700">' + fmt.money(c.fns) + '</td>' +
               '<td style="' + col + ';font-weight:700">' + c.retard + 'j</td>' +
               '<td>' + fmt.money(c.solde) + '</td></tr>';
    }).join('') || '<tr><td colspan="6" class="tbl-empty">Chargez les creances</td></tr>';
}

function afficherPriorite() {
    if (!_crData) return;
    var tbody = document.getElementById('cr-prio-tbody');
    if (!tbody) return;
    var rows = _crData.priorite || [];
    tbody.innerHTML = rows.map(function(r) {
        var pCol = {CRITIQUE:'color:var(--red);font-weight:800',
                    HAUTE:'color:var(--warn);font-weight:700',
                    MOYENNE:'color:#F59E0B',BASSE:''}[r.priorite] || '';
        return '<tr><td style="' + pCol + '">' + (r.priorite||'-') + '</td>' +
               '<td style="font-weight:700">' + (r.nom||'-') + '</td>' +
               '<td>' + (r.commercial||'-') + '</td>' +
               '<td style="color:var(--red);font-weight:700">' + fmt.money(r.fns||0) + '</td>' +
               '<td style="' + pCol + '">' + (r.retard||0) + 'j</td>' +
               '<td>' + (r.telephone||'-') + '</td>' +
               '<td style="font-weight:700">' + (r.action||'-') + '</td></tr>';
    }).join('') || '<tr><td colspan="7" class="tbl-empty">Chargez les creances</td></tr>';
}

// ── Rapport de Caisse ──────────────────────────────────────────

function chargerRapportsCaisse() {
    tableLoader('rc-tbody', 6);
    apiGet('/api/comptabilite/rapport-caisse', function(d) {
        var tbody = document.getElementById('rc-tbody');
        if (!tbody) return;
        if (!d.rapports || !d.rapports.length) { tableVide('rc-tbody', 6, 'Aucun rapport'); return; }
        tbody.innerHTML = d.rapports.map(function(r) {
            return '<tr>' +
                   '<td>' + fmt.date(r.date_rapport) + '</td>' +
                   '<td>' + (r.commercial||'-') + '</td>' +
                   '<td style="color:var(--gold)">' + fmt.money(r.total_ventes||0) + '</td>' +
                   '<td style="color:var(--green)">' + fmt.money(r.total_encaisse||0) + '</td>' +
                   '<td style="color:var(--red)">' + fmt.money(r.total_credit||0) + '</td>' +
                   '<td>' + badge(r.statut||'brouillon','info') + '</td></tr>';
        }).join('');
    });
}

// ── Reaction au changement de periode globale ────────────────────
// Memes raisons que dans commercial.js : sans ce listener, le Grand
// Livre et les Creances continuent d'afficher les chiffres de l'ancienne
// periode apres avoir clique "Appliquer" sur la barre de periode.
document.addEventListener('nexora:periode-changed', function() {
    var active = document.querySelector('#content .section.active');
    if (!active) return;
    var id = active.id || '';
    if (id === 's-compta-dashboard') chargerDashCompta();
    else if (id === 's-gl-vue')      chargerGL();
    else if (id && id.indexOf('s-cr-') === 0) chargerCreances();
});

// ── Init ────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', function() {
    chargerDashCompta();
});
