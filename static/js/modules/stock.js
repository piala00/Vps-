/**
 * NEXORA v2.0 — Module Stock
 * Regle : pas de template literals avec apostrophes francaises
 * Regle : .then(function(){}) au lieu de async/await
 */

var autoLoad = window.autoLoad || {};

autoLoad['stock-dashboard'] = function() { stockChargerDashboard(); };
autoLoad['fiche-bl'] = function() {};
autoLoad['fiche-manuel'] = function() { stockInitFiche('fm-lignes-tbody', 'fm-date'); };
autoLoad['fiche-reception'] = function() { stockInitFiche('fr-lignes-tbody', 'fr-date'); };
autoLoad['fiche-transfert'] = function() { stockInitFiche('ft-lignes-tbody', 'ft-date'); };
autoLoad['rapprochement'] = function() { stockChargerRapprochement(); };
autoLoad['non-regularises'] = function() { stockChargerNonRegularises(); };
autoLoad['equilibre'] = function() { stockChargerEquilibre(); };
autoLoad['analyses-dashboard'] = function() { stockChargerAnalysesDashboard(); };
autoLoad['top-articles'] = function() { stockChargerTopArticles(); };
autoLoad['dormants'] = function() { stockChargerDormants(); };
autoLoad['reappro'] = function() { stockChargerReappro(); };
autoLoad['clients'] = function() { stockChargerClients(); };
autoLoad['comparative'] = function() { stockChargerComparative(); };

window.autoLoad = autoLoad;

// ── Tableau de bord ──────────────────────────────────────────────────────
function stockChargerDashboard() {
    apiGet('/api/stock/dashboard-summary', function(d) {
        var s = d.summary;
        document.getElementById('kpi-ruptures').textContent = s.ruptures;
        document.getElementById('kpi-critiques').textContent = s.critiques;
        document.getElementById('kpi-mvts-jour').textContent = s.mouvements_jour;
        document.getElementById('kpi-valeur-stock').textContent = fmt.money(s.valeur_stock);
        document.getElementById('kpi-dormants').textContent = s.dormants_count;
        document.getElementById('kpi-non-reg').textContent = s.docs_non_regularises;
    });
}

// ── Lignes editables (bordereau manuel / reception / transfert) ──────────
function stockInitFiche(tbodyId, dateId) {
    var dateEl = document.getElementById(dateId);
    if (dateEl && !dateEl.value) {
        dateEl.value = new Date().toISOString().substring(0, 10);
    }
    var tbody = document.getElementById(tbodyId);
    if (tbody && tbody.children.length === 0) {
        stockAjouterLigne(tbodyId);
    }
}

function stockAjouterLigne(tbodyId) {
    var tbody = document.getElementById(tbodyId);
    var tr = document.createElement('tr');
    tr.innerHTML =
        '<td><input type="text" class="ln-code" style="width:100%"></td>' +
        '<td><input type="text" class="ln-design" style="width:100%"></td>' +
        '<td><input type="number" class="ln-qte" value="0" step="0.01" style="width:100%"></td>' +
        '<td><button class="btn btn-outline btn-sm" onclick="this.closest(\'tr\').remove()">✕</button></td>';
    tbody.appendChild(tr);
}

function stockLireLignes(tbodyId) {
    var lignes = [];
    document.querySelectorAll('#' + tbodyId + ' tr').forEach(function(tr) {
        var code = tr.querySelector('.ln-code');
        if (!code) return;
        var c = code.value.trim();
        if (!c) return;
        lignes.push({
            code_article: c,
            designation: tr.querySelector('.ln-design').value,
            quantite: parseFloat(tr.querySelector('.ln-qte').value) || 0
        });
    });
    return lignes;
}

// ── BL Sage ────────────────────────────────────────────────────────────────
function stockChargerBL() {
    var no = document.getElementById('bl-numero').value.trim();
    if (!no) { status('Veuillez saisir un numero de BL'); return; }
    loadingTable('bl-lignes-tbody', 5);
    document.getElementById('bl-info').innerHTML = '';
    apiPost('/api/stock/reconstituer-bl', {no_bl: no}, function(d) {
        if (!d.lignes || !d.lignes.length) {
            emptyTable('bl-lignes-tbody', 5, 'Aucune ligne trouvee');
            return;
        }
        var tbody = document.getElementById('bl-lignes-tbody');
        tbody.innerHTML = '';
        d.lignes.forEach(function(l) {
            var qte = parseFloat(l.quantite) || 0;
            var tr = document.createElement('tr');
            tr.innerHTML =
                '<td>' + (l.code_article || '') +
                    '<input type="hidden" class="bl-code" value="' + (l.code_article || '') + '">' +
                    '<input type="hidden" class="bl-design" value="' + (l.designation || '') + '">' +
                    '<input type="hidden" class="bl-date" value="' + (l.date_bl || '') + '">' +
                '</td>' +
                '<td>' + (l.designation || '') + '</td>' +
                '<td>' + fmt.qty(qte) + '<input type="hidden" class="bl-qte-sage" value="' + qte + '"></td>' +
                '<td><input type="number" class="bl-qte-saisie" value="' + qte + '" step="0.01" style="width:100%"></td>' +
                '<td>—</td>';
            tbody.appendChild(tr);
        });
        var b = document.getElementById('bl-info');
        var src = d.source === 'cache' ? 'Depuis le cache local' : 'Depuis Sage';
        b.innerHTML = badge(src + ' — ' + d.lignes.length + ' article(s)', d.source === 'cache' ? 'info' : 'ok');
    }, function(msg) {
        emptyTable('bl-lignes-tbody', 5, msg);
    });
}

function stockValiderBL() {
    var no = document.getElementById('bl-numero').value.trim();
    if (!no) { status('Veuillez charger un BL'); return; }
    var lignes = [];
    document.querySelectorAll('#bl-lignes-tbody tr').forEach(function(tr) {
        var code = tr.querySelector('.bl-code');
        if (!code) return;
        lignes.push({
            code_article: code.value,
            designation: tr.querySelector('.bl-design').value,
            date_bl: tr.querySelector('.bl-date').value,
            qte_sage: parseFloat(tr.querySelector('.bl-qte-sage').value) || 0,
            qte_saisie: parseFloat(tr.querySelector('.bl-qte-saisie').value) || 0
        });
    });
    if (!lignes.length) { status('Aucune ligne a valider'); return; }
    apiPost('/api/stock/valider-bl', {no_bl: no, lignes: lignes}, function(d) {
        status(d.msg);
        document.getElementById('bl-numero').value = '';
        document.getElementById('bl-info').innerHTML = '';
        emptyTable('bl-lignes-tbody', 5, 'Aucun BL charge');
        stockChargerDashboard();
    });
}

// ── Bordereau manuel ──────────────────────────────────────────────────────
function stockSaisirManuel() {
    var no = document.getElementById('fm-no-manuel').value.trim();
    if (!no) { status('Numero de bordereau requis'); return; }
    var lignes = stockLireLignes('fm-lignes-tbody');
    if (!lignes.length) { status('Ajoutez au moins une ligne valide'); return; }
    var data = {
        no_manuel: no,
        type_mouvement: document.getElementById('fm-type').value,
        date_mvt: document.getElementById('fm-date').value,
        code_client: document.getElementById('fm-code-client').value,
        client_nom: document.getElementById('fm-client-nom').value,
        lignes: lignes
    };
    apiPost('/api/stock/saisir-manuel', data, function(d) {
        status(d.msg);
        document.getElementById('fm-no-manuel').value = '';
        document.getElementById('fm-code-client').value = '';
        document.getElementById('fm-client-nom').value = '';
        document.getElementById('fm-lignes-tbody').innerHTML = '';
        stockAjouterLigne('fm-lignes-tbody');
        stockChargerDashboard();
    });
}

// ── Reception ─────────────────────────────────────────────────────────────
function stockSaisirReception() {
    var no = document.getElementById('fr-no-reception').value.trim();
    if (!no) { status('Numero de bon de reception requis'); return; }
    var lignes = stockLireLignes('fr-lignes-tbody');
    if (!lignes.length) { status('Ajoutez au moins une ligne valide'); return; }
    var data = {
        no_reception: no,
        date_mvt: document.getElementById('fr-date').value,
        code_fournisseur: document.getElementById('fr-code-fournisseur').value,
        fournisseur_nom: document.getElementById('fr-fournisseur-nom').value,
        lignes: lignes
    };
    apiPost('/api/stock/reception', data, function(d) {
        status(d.msg);
        document.getElementById('fr-no-reception').value = '';
        document.getElementById('fr-code-fournisseur').value = '';
        document.getElementById('fr-fournisseur-nom').value = '';
        document.getElementById('fr-lignes-tbody').innerHTML = '';
        stockAjouterLigne('fr-lignes-tbody');
        stockChargerDashboard();
    });
}

// ── Transfert ─────────────────────────────────────────────────────────────
function stockSaisirTransfert() {
    var no = document.getElementById('ft-no-transfert').value.trim();
    if (!no) { status('Numero de bordereau requis'); return; }
    var depot = document.getElementById('ft-depot').value;
    var depotDest = document.getElementById('ft-depot-dest').value;
    if (depot === depotDest) { status('Le depot de destination doit etre different du depot source'); return; }
    var lignes = stockLireLignes('ft-lignes-tbody');
    if (!lignes.length) { status('Ajoutez au moins une ligne valide'); return; }
    var data = {
        no_transfert: no,
        date_mvt: document.getElementById('ft-date').value,
        depot: depot,
        depot_dest: depotDest,
        lignes: lignes
    };
    apiPost('/api/stock/transfert', data, function(d) {
        status(d.msg);
        document.getElementById('ft-no-transfert').value = '';
        document.getElementById('ft-lignes-tbody').innerHTML = '';
        stockAjouterLigne('ft-lignes-tbody');
        stockChargerDashboard();
    });
}

// ── Rapprochement ─────────────────────────────────────────────────────────
function stockChargerRapprochement() {
    var params = '?type=' + encodeURIComponent(document.getElementById('rap-type').value);
    var dd = document.getElementById('rap-date-debut').value;
    var df = document.getElementById('rap-date-fin').value;
    var st = document.getElementById('rap-statut').value;
    if (dd) params += '&date_debut=' + dd;
    if (df) params += '&date_fin=' + df;
    if (st) params += '&statut=' + st;
    loadingTable('rap-tbody', 10);
    apiGet('/api/stock/rapprochement' + params, function(d) {
        if (!d.data.length) { emptyTable('rap-tbody', 10); return; }
        var tbody = document.getElementById('rap-tbody');
        tbody.innerHTML = '';
        d.data.forEach(function(r) {
            var noDoc = r.no_doc_sage || r.no_doc_manuel;
            var stCls = r.statut_global === 'valide' ? 'ok' :
                        (r.statut_global === 'ecart' ? 'warn' : 'muted');
            var tr = document.createElement('tr');
            tr.innerHTML =
                '<td>' + (r.no_doc_sage || '—') + '</td>' +
                '<td>' + (r.no_doc_manuel || '—') + '</td>' +
                '<td>' + fmt.date(r.date_mvt) + '</td>' +
                '<td>' + (r.client_nom || '—') + '</td>' +
                '<td>' + r.nb_articles + '</td>' +
                '<td>' + fmt.qty(r.total_sage) + '</td>' +
                '<td>' + fmt.qty(r.total_saisi) + '</td>' +
                '<td>' + (r.nb_ecarts > 0 ? badge(r.nb_ecarts, 'warn') : badge('0', 'ok')) + '</td>' +
                '<td>' + badge(r.statut_global, stCls) + '</td>' +
                '<td><button class="btn btn-outline btn-sm" onclick="stockDetailRapprochement(\'' + noDoc + '\')">🔍</button></td>';
            tbody.appendChild(tr);
        });
    });
}

function stockDetailRapprochement(noDoc) {
    apiGet('/api/stock/rapprochement/detail/' + encodeURIComponent(noDoc), function(d) {
        var tbody = document.getElementById('rapd-tbody');
        if (!d.data.length) {
            emptyTable('rapd-tbody', 6);
        } else {
            tbody.innerHTML = '';
            d.data.forEach(function(r) {
                var stCls = r.statut === 'valide' ? 'ok' : (r.statut === 'ecart' ? 'warn' : 'muted');
                var tr = document.createElement('tr');
                tr.innerHTML =
                    '<td>' + r.code_article + '</td>' +
                    '<td>' + r.designation + '</td>' +
                    '<td>' + fmt.qty(r.qte_doc_sage) + '</td>' +
                    '<td>' + fmt.qty(r.qte_saisie) + '</td>' +
                    '<td>' + fmt.qty(r.ecart) + '</td>' +
                    '<td>' + badge(r.statut, stCls) + '</td>';
                tbody.appendChild(tr);
            });
        }
        ouvrirModal('modal-rapp-detail');
    });
}

// ── Documents non regularises ─────────────────────────────────────────────
function stockChargerNonRegularises() {
    loadingTable('nr-tbody', 7);
    apiGet('/api/stock/docs-non-regularises', function(d) {
        if (!d.data.length) { emptyTable('nr-tbody', 7, 'Aucun document en attente'); return; }
        var tbody = document.getElementById('nr-tbody');
        tbody.innerHTML = '';
        d.data.forEach(function(r) {
            var jCls = r.jours_attente > 7 ? 'err' : (r.jours_attente > 2 ? 'warn' : 'info');
            var tr = document.createElement('tr');
            tr.innerHTML =
                '<td>' + r.no_doc_manuel + '</td>' +
                '<td>' + r.type_mouvement + '</td>' +
                '<td>' + fmt.date(r.date_mvt) + '</td>' +
                '<td>' + r.nb_articles + '</td>' +
                '<td>' + (r.saisi_par || '—') + '</td>' +
                '<td>' + badge(r.jours_attente + ' j', jCls) + '</td>' +
                '<td><button class="btn btn-navy btn-sm" onclick="stockOuvrirRegularisation(\'' + r.no_doc_manuel + '\')">🔗 Regulariser</button></td>';
            tbody.appendChild(tr);
        });
    });
}

function stockOuvrirRegularisation(noManuel) {
    document.getElementById('reg-no-manuel').value = noManuel;
    document.getElementById('reg-no-sage').value = '';
    ouvrirModal('modal-regulariser');
}

function stockRegulariser() {
    var noManuel = document.getElementById('reg-no-manuel').value;
    var noSage = document.getElementById('reg-no-sage').value.trim();
    if (!noSage) { status('Veuillez saisir le numero de BL Sage'); return; }
    apiPost('/api/stock/regulariser-manuel', {no_manuel: noManuel, no_sage: noSage}, function(d) {
        status(d.msg);
        fermerModal('modal-regulariser');
        stockChargerNonRegularises();
        stockChargerDashboard();
    });
}

// ── Equilibre inter-magasins ────────────────────────────────────────────────
function stockChargerEquilibre() {
    var periode = document.getElementById('eq-periode').value;
    loadingTable('eq-tbody', 6);
    apiGet('/api/analyses/equilibre?periode=' + periode, function(d) {
        if (!d.data.length) { emptyTable('eq-tbody', 6, 'Aucun desequilibre detecte'); return; }
        var tbody = document.getElementById('eq-tbody');
        tbody.innerHTML = '';
        d.data.forEach(function(a) {
            var depotsTxt = a.depots.map(function(dp) {
                return dp.depot + ': ' + fmt.qty(dp.stock) + ' (' + dp.statut + ')';
            }).join(', ');
            var tr = document.createElement('tr');
            tr.innerHTML =
                '<td>' + a.code_article + '</td>' +
                '<td>' + a.designation + '</td>' +
                '<td>' + depotsTxt + '</td>' +
                '<td>' + a.nb_manques + '</td>' +
                '<td>' + a.nb_surplus + '</td>' +
                '<td>' + (a.transfert_conseille || '—') + '</td>';
            tbody.appendChild(tr);
        });
    });
}

// ── Analyses — Tableau de bord BI ───────────────────────────────────────────
function stockChargerAnalysesDashboard() {
    var periode = document.getElementById('an-periode').value;
    var gran = document.getElementById('an-granularite').value;
    apiGet('/api/analyses/dashboard?periode=' + periode + '&granularite=' + gran, function(d) {
        var k = d.kpis;
        document.getElementById('an-kpi-entrees').textContent = fmt.qty(k.total_entrees);
        document.getElementById('an-kpi-sorties').textContent = fmt.qty(k.total_sorties);
        document.getElementById('an-kpi-montant').textContent = fmt.money(k.montant_total);
        document.getElementById('an-kpi-articles').textContent = k.nb_articles;
        document.getElementById('an-kpi-clients').textContent = k.nb_clients;
        document.getElementById('an-kpi-dormants').textContent = d.dormants_count;

        var maxS = 0;
        d.evolution.forEach(function(e) { if (e.sorties > maxS) maxS = e.sorties; });
        var html = '';
        d.evolution.forEach(function(e) {
            var pct = maxS > 0 ? Math.round(e.sorties / maxS * 100) : 0;
            html += '<div class="bar-row"><div class="bar-label">' + e.periode + '</div>' +
                    '<div class="bar-track"><div class="bar-fill" style="width:' + pct + '%"></div></div>' +
                    '<div class="bar-val">' + fmt.qty(e.sorties) + '</div></div>';
        });
        document.getElementById('an-evolution').innerHTML = html || '<div class="tbl-empty">Aucune donnee</div>';

        var maxF = 0;
        d.familles.forEach(function(f) { if (f.volume_sortie > maxF) maxF = f.volume_sortie; });
        var html2 = '';
        d.familles.forEach(function(f) {
            var pct = maxF > 0 ? Math.round(f.volume_sortie / maxF * 100) : 0;
            html2 += '<div class="bar-row"><div class="bar-label">' + (f.famille || 'Autre') + '</div>' +
                     '<div class="bar-track"><div class="bar-fill bar-gold" style="width:' + pct + '%"></div></div>' +
                     '<div class="bar-val">' + f.part_pct + '%</div></div>';
        });
        document.getElementById('an-familles').innerHTML = html2 || '<div class="tbl-empty">Aucune donnee</div>';

        if (!d.top_articles.length) {
            emptyTable('an-top-tbody', 5);
        } else {
            var tbody = document.getElementById('an-top-tbody');
            tbody.innerHTML = '';
            d.top_articles.forEach(function(a) {
                var tr = document.createElement('tr');
                tr.innerHTML =
                    '<td>' + a.code_article + '</td>' +
                    '<td>' + a.designation + '</td>' +
                    '<td>' + (a.famille || '—') + '</td>' +
                    '<td>' + fmt.qty(a.volume_sortie) + '</td>' +
                    '<td>' + fmt.money(a.montant_ht) + '</td>';
                tbody.appendChild(tr);
            });
        }
    });
}

// ── Top sorties ─────────────────────────────────────────────────────────────
function stockChargerTopArticles() {
    var periode = document.getElementById('ta-periode').value;
    var limit = document.getElementById('ta-limit').value || 20;
    loadingTable('ta-tbody', 8);
    document.getElementById('ta-chart').innerHTML = '';
    apiGet('/api/analyses/top-articles?periode=' + periode + '&limit=' + limit, function(d) {
        if (!d.data.length) { emptyTable('ta-tbody', 8); return; }

        var maxV = 0;
        d.data.forEach(function(a) { if (a.volume_sortie > maxV) maxV = a.volume_sortie; });
        var html = '';
        d.data.forEach(function(a) {
            var pct = maxV > 0 ? Math.round(a.volume_sortie / maxV * 100) : 0;
            html += '<div class="bar-row"><div class="bar-label">' + a.code_article + '</div>' +
                    '<div class="bar-track"><div class="bar-fill" style="width:' + pct + '%"></div></div>' +
                    '<div class="bar-val">' + fmt.qty(a.volume_sortie) + '</div></div>';
        });
        document.getElementById('ta-chart').innerHTML = html;

        var tbody = document.getElementById('ta-tbody');
        tbody.innerHTML = '';
        d.data.forEach(function(a) {
            var tr = document.createElement('tr');
            tr.innerHTML =
                '<td>' + a.code_article + '</td>' +
                '<td>' + a.designation + '</td>' +
                '<td>' + (a.famille || '—') + '</td>' +
                '<td>' + fmt.qty(a.volume_sortie) + '</td>' +
                '<td>' + fmt.qty(a.volume_entree) + '</td>' +
                '<td>' + fmt.money(a.montant_ht) + '</td>' +
                '<td>' + a.nb_clients + '</td>' +
                '<td>' + fmt.date(a.derniere_sortie) + '</td>';
            tbody.appendChild(tr);
        });
    });
}

// ── Stocks dormants ──────────────────────────────────────────────────────────
function stockChargerDormants() {
    var periode = document.getElementById('do-periode').value;
    var jours = document.getElementById('do-jours').value;
    loadingTable('do-tbody', 8);
    apiGet('/api/analyses/dormants?periode=' + periode + '&jours=' + jours, function(d) {
        if (!d.data.length) { emptyTable('do-tbody', 8, 'Aucun stock dormant'); return; }
        var tbody = document.getElementById('do-tbody');
        tbody.innerHTML = '';
        d.data.forEach(function(a) {
            var tr = document.createElement('tr');
            tr.innerHTML =
                '<td>' + a.code_article + '</td>' +
                '<td>' + a.designation + '</td>' +
                '<td>' + (a.famille || '—') + '</td>' +
                '<td>' + fmt.qty(a.stock_actuel) + '</td>' +
                '<td>' + a.jours_sans_mvt + '</td>' +
                '<td>' + badge(a.statut, a.statut === 'DORMANT' ? 'err' : 'warn') + '</td>' +
                '<td>' + a.cause + '</td>' +
                '<td>' + a.action + '</td>';
            tbody.appendChild(tr);
        });
    });
}

// ── Reapprovisionnement ───────────────────────────────────────────────────────
function stockChargerReappro() {
    var periode = document.getElementById('re-periode').value;
    var sem = document.getElementById('re-semaines').value || 4;
    loadingTable('re-tbody', 8);
    apiGet('/api/analyses/reappro?periode=' + periode + '&semaines=' + sem, function(d) {
        if (!d.data.length) { emptyTable('re-tbody', 8); return; }
        var tbody = document.getElementById('re-tbody');
        tbody.innerHTML = '';
        var prioCls = {CRITIQUE: 'err', URGENT: 'warn', NORMAL: 'info', SURSTOCK: 'muted', DORMANT: 'muted'};
        d.data.forEach(function(a) {
            var tr = document.createElement('tr');
            tr.innerHTML =
                '<td>' + a.code_article + '</td>' +
                '<td>' + a.designation + '</td>' +
                '<td>' + (a.famille || '—') + '</td>' +
                '<td>' + fmt.qty(a.stock_actuel) + '</td>' +
                '<td>' + fmt.qty(a.vol_sortie_ref) + '</td>' +
                '<td>' + fmt.qty(a.besoin_appro) + '</td>' +
                '<td>' + (a.couverture != null ? a.couverture : '—') + '</td>' +
                '<td>' + badge(a.priorite, prioCls[a.priorite] || 'info') + '</td>';
            tbody.appendChild(tr);
        });
    });
}

// ── Clients / Article ─────────────────────────────────────────────────────────
function stockChargerClients() {
    var periode = document.getElementById('cl-periode').value;
    var code = document.getElementById('cl-code').value.trim();
    loadingTable('cl-tbody', 7);
    var url = '/api/analyses/clients?periode=' + periode;
    if (code) url += '&code=' + encodeURIComponent(code);
    apiGet(url, function(d) {
        if (!d.data.length) { emptyTable('cl-tbody', 7); return; }
        var tbody = document.getElementById('cl-tbody');
        tbody.innerHTML = '';
        d.data.forEach(function(c) {
            var tr = document.createElement('tr');
            tr.innerHTML =
                '<td>' + (c.client_nom || c.code_client) + '</td>' +
                '<td>' + (code ? c.code_article : 'Tous les articles') + '</td>' +
                '<td>' + fmt.qty(c.qte_totale) + '</td>' +
                '<td>' + fmt.money(c.montant_ht) + '</td>' +
                '<td>' + c.nb_commandes + '</td>' +
                '<td>' + (c.frequence_jours != null ? c.frequence_jours : '—') + '</td>' +
                '<td>' + (c.prochaine_cmd ? fmt.date(c.prochaine_cmd) : '—') + '</td>';
            tbody.appendChild(tr);
        });
    });
}

// ── Analyse comparative ────────────────────────────────────────────────────────
function stockChargerComparative() {
    var p1 = document.getElementById('cp-periode1').value;
    var p2 = document.getElementById('cp-periode2').value;
    document.getElementById('cp-th1').textContent = 'Sortie ' + p1;
    document.getElementById('cp-th2').textContent = 'Sortie ' + p2;
    loadingTable('cp-tbody', 6);
    apiGet('/api/analyses/comparative?periode1=' + p1 + '&periode2=' + p2, function(d) {
        if (!d.data.length) { emptyTable('cp-tbody', 6); return; }
        var tbody = document.getElementById('cp-tbody');
        tbody.innerHTML = '';
        var tCls = {HAUSSE: 'ok', BAISSE: 'err', STABLE: 'muted'};
        d.data.slice(0, 50).forEach(function(a) {
            var tr = document.createElement('tr');
            tr.innerHTML =
                '<td>' + a.code_article + '</td>' +
                '<td>' + (a.designation || '—') + '</td>' +
                '<td>' + fmt.qty(a.sortie_periode1) + '</td>' +
                '<td>' + fmt.qty(a.sortie_periode2) + '</td>' +
                '<td>' + a.evolution_pct + '%</td>' +
                '<td>' + badge(a.tendance, tCls[a.tendance] || 'info') + '</td>';
            tbody.appendChild(tr);
        });
    });
}

stockChargerDashboard();
