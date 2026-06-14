var autoLoad = window.autoLoad || {};

var _cptaBalanceCache = [];
var _cptaRapportsCache = [];

// -- Selects partages --------------------------------------------------------------
function cptaRemplirSelectClients(selectId, emptyLabel) {
    var sel = document.getElementById(selectId);
    if (!sel) return;
    var html = (emptyLabel !== undefined) ? ('<option value="">' + emptyLabel + '</option>') : '';
    _cptaBalanceCache.forEach(function(c) {
        html += '<option value="' + c.code_client + '">' + c.code_client + ' - ' + (c.nom || '') + '</option>';
    });
    sel.innerHTML = html;
}

function cptaChargerClients(callback) {
    apiGet('/api/comptabilite/balance-agee', function(d) {
        _cptaBalanceCache = d.data;
        if (callback) callback();
    });
}

// -- Tableau de bord ----------------------------------------------------------------
function cptaChargerDashboard() {
    apiGet('/api/comptabilite/dashboard-summary', function(d) {
        var s = d.summary;
        document.getElementById('kpi-creances-totales').textContent = fmt.money(s.creances_totales);
        document.getElementById('kpi-nb-debiteurs').textContent = s.nb_clients_debiteurs;
        document.getElementById('kpi-creances-critiques').textContent = fmt.money(s.creances_critiques);
        document.getElementById('kpi-creances-elevees').textContent = fmt.money(s.creances_elevees);
        document.getElementById('kpi-encaisse-mois').textContent = fmt.money(s.encaisse_mois);
        document.getElementById('kpi-rapports-brouillon').textContent = s.rapports_brouillon;

        var labels = {hausse: 'En hausse', baisse: 'En baisse', stable: 'Stable'};
        var types = {hausse: 'err', baisse: 'ok', stable: 'info'};
        document.getElementById('cpta-tendance').innerHTML =
            badge(labels[s.tendance] || s.tendance, types[s.tendance] || 'info');
    });
}
autoLoad['comptabilite-dashboard'] = function() { cptaChargerDashboard(); };

// -- Balance agee ---------------------------------------------------------------------
function cptaChargerBalanceAgee() {
    loadingTable('bal-tbody', 7);
    apiGet('/api/comptabilite/balance-agee', function(d) {
        _cptaBalanceCache = d.data;
        if (!_cptaBalanceCache.length) {
            emptyTable('bal-tbody', 7, 'Aucune creance');
            return;
        }
        var riskTypes = {CRITIQUE: 'err', ELEVE: 'warn', MOYEN: 'info', FAIBLE: 'muted'};
        var html = '';
        _cptaBalanceCache.forEach(function(c) {
            html += '<tr>' +
                '<td>' + c.code_client + '</td>' +
                '<td>' + (c.nom || '—') + '</td>' +
                '<td>' + (c.telephone || '—') + '</td>' +
                '<td>' + fmt.money(c.total_debit) + '</td>' +
                '<td>' + fmt.money(c.total_credit) + '</td>' +
                '<td>' + fmt.money(c.solde) + '</td>' +
                '<td>' + badge(c.niveau_risque, riskTypes[c.niveau_risque] || 'info') + '</td>' +
                '</tr>';
        });
        document.getElementById('bal-tbody').innerHTML = html;
    });
}
autoLoad['balance-agee'] = function() { cptaChargerBalanceAgee(); };

// -- Grand livre clients ----------------------------------------------------------------
function cptaChargerGrandLivre() {
    var code = document.getElementById('gl-client').value;
    if (!code) {
        emptyTable('gl-tbody', 6, 'Selectionnez un client');
        return;
    }
    loadingTable('gl-tbody', 6);
    var dd = document.getElementById('gl-date-debut').value;
    var df = document.getElementById('gl-date-fin').value;
    var url = '/api/comptabilite/grand-livre-client?code_client=' + encodeURIComponent(code);
    if (dd) url += '&date_debut=' + dd;
    if (df) url += '&date_fin=' + df;
    apiGet(url, function(d) {
        if (!d.data.length) {
            emptyTable('gl-tbody', 6, 'Aucune ecriture');
            return;
        }
        var html = '';
        d.data.forEach(function(l) {
            html += '<tr>' +
                '<td>' + fmt.date(l.date_ecriture) + '</td>' +
                '<td>' + (l.journal || '—') + '</td>' +
                '<td>' + (l.piece || '—') + '</td>' +
                '<td>' + (l.libelle || '—') + '</td>' +
                '<td>' + fmt.money(l.debit) + '</td>' +
                '<td>' + fmt.money(l.credit) + '</td>' +
                '</tr>';
        });
        document.getElementById('gl-tbody').innerHTML = html;
    });
}
autoLoad['grand-livre-clients'] = function() {
    cptaChargerClients(function() {
        cptaRemplirSelectClients('gl-client', 'Choisir un client');
        emptyTable('gl-tbody', 6, 'Selectionnez un client');
    });
};

// -- Paiements ----------------------------------------------------------------------------
function cptaChargerPaiements() {
    loadingTable('pai-tbody', 7);
    var code = document.getElementById('pai-client').value;
    var dd = document.getElementById('pai-date-debut').value;
    var df = document.getElementById('pai-date-fin').value;
    var parts = [];
    if (code) parts.push('code_client=' + encodeURIComponent(code));
    if (dd) parts.push('date_debut=' + dd);
    if (df) parts.push('date_fin=' + df);
    var url = '/api/comptabilite/paiements' + (parts.length ? ('?' + parts.join('&')) : '');
    apiGet(url, function(d) {
        if (!d.data.length) {
            emptyTable('pai-tbody', 7, 'Aucun paiement');
            return;
        }
        var html = '';
        d.data.forEach(function(p) {
            html += '<tr>' +
                '<td>' + fmt.date(p.date_paiement) + '</td>' +
                '<td>' + (p.code_client || '—') + '</td>' +
                '<td>' + (p.client_nom || '—') + '</td>' +
                '<td>' + fmt.money(p.montant) + '</td>' +
                '<td>' + (p.mode_paiement || '—') + '</td>' +
                '<td>' + (p.reference || '—') + '</td>' +
                '<td>' + (p.piece || '—') + '</td>' +
                '</tr>';
        });
        document.getElementById('pai-tbody').innerHTML = html;
    });
}
autoLoad['paiements'] = function() {
    cptaChargerClients(function() {
        cptaRemplirSelectClients('pai-client', '— Tous les clients —');
        cptaChargerPaiements();
    });
};

// -- Evolution creances -----------------------------------------------------------------------
function cptaChargerEvolution() {
    var code = document.getElementById('evo-client').value;
    var jours = document.getElementById('evo-jours').value;
    loadingTable('evo-tbody', 2);
    var url = '/api/comptabilite/evolution-creances?jours=' + jours;
    if (code) url += '&code_client=' + encodeURIComponent(code);
    apiGet(url, function(d) {
        var rows = d.data || [];
        if (!rows.length) {
            emptyTable('evo-tbody', 2, 'Aucune donnee');
            document.getElementById('evo-valeur-debut').textContent = '—';
            document.getElementById('evo-valeur-fin').textContent = '—';
            document.getElementById('evo-variation').textContent = '—';
            return;
        }
        var html = '';
        rows.forEach(function(r) {
            html += '<tr><td>' + fmt.date(r.periode) + '</td><td>' + fmt.money(r.valeur) + '</td></tr>';
        });
        document.getElementById('evo-tbody').innerHTML = html;

        var debut = parseFloat(rows[0].valeur) || 0;
        var fin = parseFloat(rows[rows.length - 1].valeur) || 0;
        var variation = fin - debut;
        document.getElementById('evo-valeur-debut').textContent = fmt.money(debut);
        document.getElementById('evo-valeur-fin').textContent = fmt.money(fin);
        document.getElementById('evo-variation').textContent =
            (variation >= 0 ? '+' : '') + fmt.money(variation);
    });
}
autoLoad['evolution-creances'] = function() {
    cptaChargerClients(function() {
        cptaRemplirSelectClients('evo-client', '— Toutes les creances —');
        cptaChargerEvolution();
    });
};

// -- Rapport de caisse -------------------------------------------------------------------------
function cptaAjouterLigneCaisse(tbodyId) {
    var tbody = document.getElementById(tbodyId);
    var tr = document.createElement('tr');
    tr.innerHTML =
        '<td><input type="text" class="ln-facture" style="width:100%"></td>' +
        '<td><input type="text" class="ln-code-client" style="width:100%"></td>' +
        '<td><input type="text" class="ln-client-nom" style="width:100%"></td>' +
        '<td><input type="number" class="ln-mt-facture" value="0" step="0.01" style="width:100%"></td>' +
        '<td><input type="number" class="ln-mt-encaisse" value="0" step="0.01" style="width:100%"></td>' +
        '<td><select class="ln-mode" style="width:100%">' +
            '<option value="ESPECES">Especes</option>' +
            '<option value="CHEQUE">Cheque</option>' +
            '<option value="VIREMENT">Virement</option>' +
            '<option value="MOBILE_MONEY">Mobile Money</option>' +
            '<option value="CREDIT">Credit</option>' +
        '</select></td>' +
        '<td><input type="text" class="ln-observations" style="width:100%"></td>' +
        '<td><button class="btn btn-outline btn-sm" onclick="this.closest(\'tr\').remove()">✕</button></td>';
    tbody.appendChild(tr);
}

function cptaLireLignesCaisse(tbodyId) {
    var lignes = [];
    document.querySelectorAll('#' + tbodyId + ' tr').forEach(function(tr) {
        var facture = tr.querySelector('.ln-facture');
        if (!facture) return;
        var f = facture.value.trim();
        if (!f) return;
        lignes.push({
            no_facture: f,
            code_client: tr.querySelector('.ln-code-client').value.trim(),
            client_nom: tr.querySelector('.ln-client-nom').value.trim(),
            montant_facture: parseFloat(tr.querySelector('.ln-mt-facture').value) || 0,
            montant_encaisse: parseFloat(tr.querySelector('.ln-mt-encaisse').value) || 0,
            mode_paiement: tr.querySelector('.ln-mode').value,
            observations: tr.querySelector('.ln-observations').value.trim()
        });
    });
    return lignes;
}

function cptaSoumettreRapportCaisse() {
    var data = {
        date_rapport: document.getElementById('rc-date').value,
        commercial: document.getElementById('rc-commercial').value.trim(),
        agence: document.getElementById('rc-agence').value.trim() || 'BERTOUA',
        total_ventes: parseFloat(document.getElementById('rc-total-ventes').value) || 0,
        total_encaisse: parseFloat(document.getElementById('rc-total-encaisse').value) || 0,
        total_credit: parseFloat(document.getElementById('rc-total-credit').value) || 0,
        observations: document.getElementById('rc-observations').value.trim(),
        lignes: cptaLireLignesCaisse('rcn-lignes-tbody')
    };
    if (!data.date_rapport) { status('⚠ Choisissez une date'); return; }
    apiPost('/api/comptabilite/rapport-caisse', data, function(d) {
        status(d.msg);
        document.getElementById('rc-commercial').value = '';
        document.getElementById('rc-total-ventes').value = '0';
        document.getElementById('rc-total-encaisse').value = '0';
        document.getElementById('rc-total-credit').value = '0';
        document.getElementById('rc-observations').value = '';
        document.getElementById('rcn-lignes-tbody').innerHTML = '';
        cptaChargerHistoriqueRapports();
    });
}

function cptaChargerHistoriqueRapports() {
    loadingTable('rch-tbody', 9);
    apiGet('/api/comptabilite/rapport-caisse', function(d) {
        _cptaRapportsCache = d.data;
        if (!_cptaRapportsCache.length) {
            emptyTable('rch-tbody', 9, 'Aucun rapport');
            return;
        }
        var html = '';
        _cptaRapportsCache.forEach(function(r) {
            html += '<tr>' +
                '<td>' + fmt.date(r.date_rapport) + '</td>' +
                '<td>' + (r.commercial || '—') + '</td>' +
                '<td>' + (r.agence || '—') + '</td>' +
                '<td>' + fmt.money(r.total_ventes) + '</td>' +
                '<td>' + fmt.money(r.total_encaisse) + '</td>' +
                '<td>' + fmt.money(r.total_credit) + '</td>' +
                '<td>' + r.nb_lignes + '</td>' +
                '<td>' + (r.statut === 'valide' ? badge('Valide', 'ok') : badge('Brouillon', 'warn')) + '</td>' +
                '<td><button class="btn btn-outline btn-sm" onclick="cptaVoirRapport(' + r.id + ')">👁️</button></td>' +
                '</tr>';
        });
        document.getElementById('rch-tbody').innerHTML = html;
    });
}

function cptaVoirRapport(id) {
    var r = _cptaRapportsCache.filter(function(x) { return x.id === id; })[0];
    if (!r) return;
    document.getElementById('rcd-id').value = id;
    document.getElementById('rcd-titre').textContent =
        'Rapport du ' + fmt.date(r.date_rapport) + ' - ' + (r.commercial || '');
    var btn = document.getElementById('rcd-valider-btn');
    btn.style.display = (r.statut === 'valide') ? 'none' : '';

    loadingTable('rcd-tbody', 7);
    apiGet('/api/comptabilite/rapport-caisse/' + id + '/lignes', function(d) {
        if (!d.data.length) {
            emptyTable('rcd-tbody', 7, 'Aucune ligne');
        } else {
            var html = '';
            d.data.forEach(function(l) {
                html += '<tr>' +
                    '<td>' + (l.no_facture || '—') + '</td>' +
                    '<td>' + (l.code_client || '—') + '</td>' +
                    '<td>' + (l.client_nom || '—') + '</td>' +
                    '<td>' + fmt.money(l.montant_facture) + '</td>' +
                    '<td>' + fmt.money(l.montant_encaisse) + '</td>' +
                    '<td>' + (l.mode_paiement || '—') + '</td>' +
                    '<td>' + (l.observations || '—') + '</td>' +
                    '</tr>';
            });
            document.getElementById('rcd-tbody').innerHTML = html;
        }
        ouvrirModal('modal-rapport-detail');
    });
}

function cptaValiderRapportCaisse() {
    var id = document.getElementById('rcd-id').value;
    apiPut('/api/comptabilite/rapport-caisse/' + id, {statut: 'valide'}, function(d) {
        status(d.msg);
        fermerModal('modal-rapport-detail');
        cptaChargerHistoriqueRapports();
    });
}

autoLoad['rapport-caisse'] = function() {
    if (!document.getElementById('rc-date').value) {
        var aujourdhui = new Date();
        document.getElementById('rc-date').value = aujourdhui.toISOString().substring(0, 10);
    }
    cptaChargerHistoriqueRapports();
};

window.autoLoad = autoLoad;

cptaChargerDashboard();
