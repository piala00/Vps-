var autoLoad = window.autoLoad || {};

var _cmClientsCache = [];
var _cmRechercheTimer = null;

// -- Tableau de bord ----------------------------------------------------------------
function cmChargerDashboard() {
    apiGet('/api/commercial/dashboard-summary', function(d) {
        var s = d.summary;
        document.getElementById('kpi-ca-jour').textContent = fmt.money(s.ca_jour);
        document.getElementById('kpi-ca-mois').textContent = fmt.money(s.ca_mois);
        document.getElementById('kpi-clients-actifs').textContent = s.clients_actifs;
        document.getElementById('kpi-creances-depassement').textContent = fmt.money(s.creances_depassement);
    });
}
autoLoad['commercial-dashboard'] = function() { cmChargerDashboard(); };

// -- Fiches clients -------------------------------------------------------------------
function cmChargerClients() {
    loadingTable('fc-tbody', 9);
    var q = document.getElementById('fc-recherche').value.trim();
    var url = '/api/commercial/clients' + (q ? ('?q=' + encodeURIComponent(q)) : '');
    apiGet(url, function(d) {
        _cmClientsCache = d.data;
        if (!_cmClientsCache.length) {
            emptyTable('fc-tbody', 9, 'Aucun client');
            return;
        }
        var html = '';
        _cmClientsCache.forEach(function(c) {
            html += '<tr>' +
                '<td>' + c.code_client + '</td>' +
                '<td>' + (c.nom || '—') + '</td>' +
                '<td>' + (c.telephone || '—') + '</td>' +
                '<td>' + (c.ville || '—') + '</td>' +
                '<td>' + (c.commercial_attitre || '—') + '</td>' +
                '<td>' + fmt.money(c.plafond_credit) + '</td>' +
                '<td>' + (c.delai_paiement || 0) + ' j</td>' +
                '<td>' + (c.actif ? badge('Actif', 'ok') : badge('Inactif', 'muted')) + '</td>' +
                '<td><button class="btn btn-outline btn-sm" onclick="cmOuvrirClient(' + c.id + ')">✏️</button></td>' +
                '</tr>';
        });
        document.getElementById('fc-tbody').innerHTML = html;
    });
}
autoLoad['fiches-clients'] = function() { cmChargerClients(); };

function cmRechercheClients() {
    if (_cmRechercheTimer) clearTimeout(_cmRechercheTimer);
    _cmRechercheTimer = setTimeout(cmChargerClients, 300);
}

function cmOuvrirClient(id) {
    document.getElementById('fc-id').value = id || '';
    if (id) {
        var c = _cmClientsCache.filter(function(x) { return x.id === id; })[0];
        if (!c) return;
        document.getElementById('fc-titre').textContent = 'Modifier client';
        document.getElementById('fc-code').value = c.code_client;
        document.getElementById('fc-code').disabled = true;
        document.getElementById('fc-nom').value = c.nom || '';
        document.getElementById('fc-prenom').value = c.prenom || '';
        document.getElementById('fc-telephone').value = c.telephone || '';
        document.getElementById('fc-telephone2').value = c.telephone2 || '';
        document.getElementById('fc-email').value = c.email || '';
        document.getElementById('fc-adresse').value = c.adresse || '';
        document.getElementById('fc-ville').value = c.ville || '';
        document.getElementById('fc-quartier').value = c.quartier || '';
        document.getElementById('fc-activite').value = c.activite || '';
        document.getElementById('fc-secteur').value = c.secteur || '';
        document.getElementById('fc-commercial').value = c.commercial_attitre || '';
        document.getElementById('fc-plafond').value = c.plafond_credit || 0;
        document.getElementById('fc-delai').value = c.delai_paiement || 30;
        document.getElementById('fc-observations').value = c.observations || '';
        document.getElementById('fc-actif').checked = !!c.actif;
    } else {
        document.getElementById('fc-titre').textContent = 'Nouveau client';
        document.getElementById('fc-code').value = '';
        document.getElementById('fc-code').disabled = false;
        document.getElementById('fc-nom').value = '';
        document.getElementById('fc-prenom').value = '';
        document.getElementById('fc-telephone').value = '';
        document.getElementById('fc-telephone2').value = '';
        document.getElementById('fc-email').value = '';
        document.getElementById('fc-adresse').value = '';
        document.getElementById('fc-ville').value = '';
        document.getElementById('fc-quartier').value = '';
        document.getElementById('fc-activite').value = '';
        document.getElementById('fc-secteur').value = '';
        document.getElementById('fc-commercial').value = '';
        document.getElementById('fc-plafond').value = '0';
        document.getElementById('fc-delai').value = '30';
        document.getElementById('fc-observations').value = '';
        document.getElementById('fc-actif').checked = true;
    }
    ouvrirModal('modal-client');
}

function cmSauverClient() {
    var id = document.getElementById('fc-id').value;
    var data = {
        code_client: document.getElementById('fc-code').value.trim(),
        nom: document.getElementById('fc-nom').value.trim(),
        prenom: document.getElementById('fc-prenom').value.trim(),
        telephone: document.getElementById('fc-telephone').value.trim(),
        telephone2: document.getElementById('fc-telephone2').value.trim(),
        email: document.getElementById('fc-email').value.trim(),
        adresse: document.getElementById('fc-adresse').value.trim(),
        ville: document.getElementById('fc-ville').value.trim(),
        quartier: document.getElementById('fc-quartier').value.trim(),
        activite: document.getElementById('fc-activite').value.trim(),
        secteur: document.getElementById('fc-secteur').value.trim(),
        commercial_attitre: document.getElementById('fc-commercial').value.trim(),
        plafond_credit: parseFloat(document.getElementById('fc-plafond').value) || 0,
        delai_paiement: parseInt(document.getElementById('fc-delai').value) || 30,
        observations: document.getElementById('fc-observations').value.trim(),
        actif: document.getElementById('fc-actif').checked
    };
    if (!data.code_client) { status('⚠ Indiquez le code client'); return; }
    if (!data.nom) { status('⚠ Indiquez le nom du client'); return; }
    if (id) {
        apiPut('/api/commercial/clients/' + id, data, function(d) {
            fermerModal('modal-client');
            status(d.msg);
            cmChargerClients();
        });
    } else {
        apiPost('/api/commercial/clients', data, function(d) {
            fermerModal('modal-client');
            status(d.msg);
            cmChargerClients();
        });
    }
}

// -- Objectifs commerciaux -------------------------------------------------------------
function cmChargerObjectifs() {
    loadingTable('obj-tbody', 5);
    apiGet('/api/commercial/objectifs', function(d) {
        if (!d.data.length) {
            emptyTable('obj-tbody', 5, 'Aucun objectif');
            return;
        }
        var html = '';
        d.data.forEach(function(o) {
            html += '<tr>' +
                '<td>' + o.periode + '</td>' +
                '<td>' + (o.commercial || '—') + '</td>' +
                '<td>' + fmt.money(o.objectif_ca) + '</td>' +
                '<td>' + fmt.money(o.objectif_recouvrement) + '</td>' +
                '<td>' + o.objectif_nb_clients + '</td>' +
                '</tr>';
        });
        document.getElementById('obj-tbody').innerHTML = html;
    });
}
autoLoad['objectifs-commerciaux'] = function() { cmChargerObjectifs(); };

function cmSauverObjectif() {
    var data = {
        commercial: document.getElementById('obj-commercial').value.trim(),
        periode: document.getElementById('obj-periode').value.trim(),
        objectif_ca: parseFloat(document.getElementById('obj-ca').value) || 0,
        objectif_recouvrement: parseFloat(document.getElementById('obj-recouvrement').value) || 0,
        objectif_nb_clients: parseInt(document.getElementById('obj-nb-clients').value) || 0
    };
    if (!data.commercial) { status('⚠ Indiquez le commercial'); return; }
    if (!data.periode) { status('⚠ Indiquez la periode'); return; }
    apiPost('/api/commercial/objectifs', data, function(d) {
        status(d.msg);
        document.getElementById('obj-commercial').value = '';
        document.getElementById('obj-periode').value = '';
        document.getElementById('obj-ca').value = '0';
        document.getElementById('obj-recouvrement').value = '0';
        document.getElementById('obj-nb-clients').value = '0';
        cmChargerObjectifs();
    });
}

// -- Suivi des ventes -------------------------------------------------------------------
function cmChargerVentes() {
    loadingTable('sv-tbody', 5);
    var code = document.getElementById('sv-client').value.trim();
    var dd = document.getElementById('sv-date-debut').value;
    var df = document.getElementById('sv-date-fin').value;
    var parts = [];
    if (code) parts.push('code_client=' + encodeURIComponent(code));
    if (dd) parts.push('date_debut=' + dd);
    if (df) parts.push('date_fin=' + df);
    var url = '/api/commercial/ventes' + (parts.length ? ('?' + parts.join('&')) : '');
    apiGet(url, function(d) {
        if (!d.data.length) {
            emptyTable('sv-tbody', 5, 'Aucune vente');
            return;
        }
        var html = '';
        d.data.forEach(function(v) {
            html += '<tr>' +
                '<td>' + fmt.date(v.date_facture) + '</td>' +
                '<td>' + (v.no_facture || '—') + '</td>' +
                '<td>' + (v.code_client || '—') + '</td>' +
                '<td>' + (v.client_nom || '—') + '</td>' +
                '<td>' + fmt.money(v.montant_ttc) + '</td>' +
                '</tr>';
        });
        document.getElementById('sv-tbody').innerHTML = html;
    });
}
autoLoad['suivi-ventes'] = function() { cmChargerVentes(); };

// -- Previsions de commandes -------------------------------------------------------------
function cmChargerPrevisions() {
    loadingTable('prev-tbody', 6);
    apiGet('/api/commercial/previsions', function(d) {
        if (!d.data.length) {
            emptyTable('prev-tbody', 6, 'Aucune donnee suffisante');
            return;
        }
        var html = '';
        d.data.forEach(function(p) {
            var joursTxt = p.jours_restants + ' j';
            var joursBadge = p.jours_restants < 0
                ? badge(joursTxt + ' (en retard)', 'err')
                : (p.jours_restants <= 3 ? badge(joursTxt, 'warn') : badge(joursTxt, 'ok'));
            html += '<tr>' +
                '<td>' + p.code_client + '</td>' +
                '<td>' + (p.client_nom || '—') + '</td>' +
                '<td>' + p.nb_commandes + '</td>' +
                '<td>' + p.frequence_jours + ' j</td>' +
                '<td>' + fmt.date(p.derniere_commande) + '</td>' +
                '<td>' + joursBadge + '</td>' +
                '</tr>';
        });
        document.getElementById('prev-tbody').innerHTML = html;
    });
}
autoLoad['previsions-commandes'] = function() { cmChargerPrevisions(); };

// -- Analyse CA --------------------------------------------------------------------------
function cmChargerAnalyseCA() {
    loadingTable('aca-tbody', 2);
    loadingTable('aca-n1-tbody', 2);
    loadingTable('aca-top-tbody', 3);
    var granularite = document.getElementById('aca-granularite').value;
    apiGet('/api/commercial/analyse-ca?granularite=' + granularite, function(d) {
        document.getElementById('aca-ca-total').textContent = fmt.money(d.ca_total);
        document.getElementById('aca-ca-total-n1').textContent = fmt.money(d.ca_total_n1);

        if (d.ca_total_n1) {
            var variation = ((d.ca_total - d.ca_total_n1) / d.ca_total_n1) * 100;
            document.getElementById('aca-variation').textContent =
                (variation >= 0 ? '+' : '') + fmt.pct(variation);
        } else {
            document.getElementById('aca-variation').textContent = '—';
        }
        document.getElementById('aca-top10-progression').textContent =
            (d.top10_progression >= 0 ? '+' : '') + fmt.money(d.top10_progression);

        if (!d.data.length) {
            emptyTable('aca-tbody', 2, 'Aucune donnee');
        } else {
            var html = '';
            d.data.forEach(function(r) {
                html += '<tr><td>' + r.periode + '</td><td>' + fmt.money(r.ca) + '</td></tr>';
            });
            document.getElementById('aca-tbody').innerHTML = html;
        }

        if (!d.data_n1.length) {
            emptyTable('aca-n1-tbody', 2, 'Aucune donnee');
        } else {
            var html1 = '';
            d.data_n1.forEach(function(r) {
                html1 += '<tr><td>' + r.periode + '</td><td>' + fmt.money(r.ca) + '</td></tr>';
            });
            document.getElementById('aca-n1-tbody').innerHTML = html1;
        }

        if (!d.top_clients.length) {
            emptyTable('aca-top-tbody', 3, 'Aucune donnee');
        } else {
            var html2 = '';
            d.top_clients.forEach(function(c) {
                html2 += '<tr>' +
                    '<td>' + c.code_client + '</td>' +
                    '<td>' + (c.client_nom || '—') + '</td>' +
                    '<td>' + fmt.money(c.total) + '</td>' +
                    '</tr>';
            });
            document.getElementById('aca-top-tbody').innerHTML = html2;
        }
    });
}
autoLoad['analyse-ca'] = function() { cmChargerAnalyseCA(); };

window.autoLoad = autoLoad;

cmChargerDashboard();
