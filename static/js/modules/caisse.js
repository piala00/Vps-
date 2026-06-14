var autoLoad = window.autoLoad || {};

var _cseRapportsCache = [];
var _cseActionStatut = '';

// -- Tableau de bord ----------------------------------------------------------------
function cseChargerDashboard() {
    apiGet('/api/caisse/dashboard-summary', function(d) {
        var s = d.summary;
        document.getElementById('kpi-solde-jour').textContent = fmt.money(s.solde_jour);
        document.getElementById('kpi-encaisse-jour').textContent = fmt.money(s.encaisse_jour);
        document.getElementById('kpi-depenses-jour').textContent = fmt.money(s.depenses_jour);
        document.getElementById('kpi-rapports-jour').textContent = s.nb_rapports_jour;
        document.getElementById('kpi-rapports-attente').textContent = s.rapports_en_attente;
        document.getElementById('cmp-semaine').textContent = fmt.money(s.solde_semaine);
        document.getElementById('cmp-semaine-prec').textContent = fmt.money(s.solde_semaine_precedente);
        document.getElementById('cmp-mois').textContent = fmt.money(s.solde_mois);
        document.getElementById('cmp-mois-prec').textContent = fmt.money(s.solde_mois_precedent);
    });
}
autoLoad['caisse-dashboard'] = function() { cseChargerDashboard(); };

// -- Saisir un rapport ----------------------------------------------------------------
function cseAjouterLigne(tbodyId) {
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

function cseLireLignes(tbodyId) {
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

function cseSoumettreRapport() {
    var data = {
        date_rapport: document.getElementById('cs-date').value,
        commercial: document.getElementById('cs-commercial').value.trim(),
        agence: document.getElementById('cs-agence').value.trim() || 'BERTOUA',
        total_ventes: parseFloat(document.getElementById('cs-total-ventes').value) || 0,
        total_encaisse: parseFloat(document.getElementById('cs-total-encaisse').value) || 0,
        total_credit: parseFloat(document.getElementById('cs-total-credit').value) || 0,
        depenses_caisse: parseFloat(document.getElementById('cs-depenses').value) || 0,
        observations: document.getElementById('cs-observations').value.trim(),
        lignes: cseLireLignes('csn-lignes-tbody')
    };
    if (!data.date_rapport) { status('⚠ Choisissez une date'); return; }
    if (!data.commercial) { status('⚠ Indiquez le commercial'); return; }
    apiPost('/api/caisse/rapports', data, function(d) {
        status(d.msg);
        document.getElementById('cs-commercial').value = '';
        document.getElementById('cs-total-ventes').value = '0';
        document.getElementById('cs-total-encaisse').value = '0';
        document.getElementById('cs-total-credit').value = '0';
        document.getElementById('cs-depenses').value = '0';
        document.getElementById('cs-observations').value = '';
        document.getElementById('csn-lignes-tbody').innerHTML = '';
    });
}
autoLoad['caisse-saisie'] = function() {
    if (!document.getElementById('cs-date').value) {
        var aujourdhui = new Date();
        document.getElementById('cs-date').value = aujourdhui.toISOString().substring(0, 10);
    }
};

// -- Historique ------------------------------------------------------------------------
function cseChargerHistorique() {
    loadingTable('cse-tbody', 11);
    var statut = document.getElementById('cse-filtre-statut').value;
    var dd = document.getElementById('cse-filtre-date-debut').value;
    var df = document.getElementById('cse-filtre-date-fin').value;
    var parts = [];
    if (statut) parts.push('statut=' + statut);
    if (dd) parts.push('date_debut=' + dd);
    if (df) parts.push('date_fin=' + df);
    var url = '/api/caisse/rapports' + (parts.length ? ('?' + parts.join('&')) : '');
    apiGet(url, function(d) {
        _cseRapportsCache = d.data;
        if (!_cseRapportsCache.length) {
            emptyTable('cse-tbody', 11, 'Aucun rapport');
            return;
        }
        var statutTypes = {brouillon: 'warn', soumis: 'info', valide: 'ok', rejete: 'err'};
        var html = '';
        _cseRapportsCache.forEach(function(r) {
            html += '<tr>' +
                '<td>' + fmt.date(r.date_rapport) + '</td>' +
                '<td>' + (r.commercial || '—') + '</td>' +
                '<td>' + (r.agence || '—') + '</td>' +
                '<td>' + fmt.money(r.total_ventes) + '</td>' +
                '<td>' + fmt.money(r.total_encaisse) + '</td>' +
                '<td>' + fmt.money(r.total_credit) + '</td>' +
                '<td>' + fmt.money(r.depenses_caisse) + '</td>' +
                '<td>' + fmt.money(r.solde) + '</td>' +
                '<td>' + r.nb_lignes + '</td>' +
                '<td>' + badge(r.statut, statutTypes[r.statut] || 'info') + '</td>' +
                '<td><button class="btn btn-outline btn-sm" onclick="cseVoirRapport(' + r.id + ')">👁️</button></td>' +
                '</tr>';
        });
        document.getElementById('cse-tbody').innerHTML = html;
    });
}
autoLoad['caisse-historique'] = function() { cseChargerHistorique(); };

function cseVoirRapport(id) {
    var r = _cseRapportsCache.filter(function(x) { return x.id === id; })[0];
    if (!r) return;
    document.getElementById('csd-id').value = id;
    document.getElementById('csd-titre').textContent =
        'Rapport du ' + fmt.date(r.date_rapport) + ' - ' + (r.commercial || '') + ' (' + r.statut + ')';

    var actionBtn = document.getElementById('csd-action-btn');
    var rejeterBtn = document.getElementById('csd-rejeter-btn');
    if (r.statut === 'brouillon') {
        actionBtn.style.display = '';
        actionBtn.textContent = '➡️ Soumettre';
        _cseActionStatut = 'soumis';
        rejeterBtn.style.display = 'none';
    } else if (r.statut === 'soumis') {
        actionBtn.style.display = '';
        actionBtn.textContent = '✅ Valider';
        _cseActionStatut = 'valide';
        rejeterBtn.style.display = '';
    } else {
        actionBtn.style.display = 'none';
        rejeterBtn.style.display = 'none';
    }

    loadingTable('csd-tbody', 7);
    apiGet('/api/caisse/rapports/' + id + '/lignes', function(d) {
        if (!d.data.length) {
            emptyTable('csd-tbody', 7, 'Aucune ligne');
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
            document.getElementById('csd-tbody').innerHTML = html;
        }
        ouvrirModal('modal-caisse-detail');
    });
}

function cseChangerStatutPrincipal() {
    cseChangerStatut(_cseActionStatut);
}

function cseChangerStatut(statut) {
    var id = document.getElementById('csd-id').value;
    apiPut('/api/caisse/rapports/' + id, {statut: statut}, function(d) {
        status(d.msg);
        fermerModal('modal-caisse-detail');
        cseChargerHistorique();
        cseChargerDashboard();
    });
}

// -- Recap journalier / evolution du solde -----------------------------------------------
function cseChargerEvolution() {
    loadingTable('cse-evo-tbody', 5);
    var jours = document.getElementById('cse-evo-jours').value;
    apiGet('/api/caisse/evolution-solde?jours=' + jours, function(d) {
        var rows = d.data || [];
        if (!rows.length) {
            emptyTable('cse-evo-tbody', 5, 'Aucune donnee');
            document.getElementById('evo-jour-fort').textContent = '—';
            document.getElementById('evo-jour-faible').textContent = '—';
            document.getElementById('evo-cumul-final').textContent = '—';
            return;
        }
        var html = '';
        rows.forEach(function(r) {
            html += '<tr>' +
                '<td>' + fmt.date(r.date_rapport) + '</td>' +
                '<td>' + fmt.money(r.encaisse) + '</td>' +
                '<td>' + fmt.money(r.depenses) + '</td>' +
                '<td>' + fmt.money(r.solde) + '</td>' +
                '<td>' + fmt.money(r.cumul) + '</td>' +
                '</tr>';
        });
        document.getElementById('cse-evo-tbody').innerHTML = html;

        document.getElementById('evo-cumul-final').textContent = fmt.money(rows[rows.length - 1].cumul);
        if (d.jour_fort) {
            document.getElementById('evo-jour-fort').textContent =
                fmt.date(d.jour_fort.date_rapport) + ' (' + fmt.money(d.jour_fort.solde) + ')';
        }
        if (d.jour_faible) {
            document.getElementById('evo-jour-faible').textContent =
                fmt.date(d.jour_faible.date_rapport) + ' (' + fmt.money(d.jour_faible.solde) + ')';
        }
    });
}
autoLoad['caisse-analyse'] = function() { cseChargerEvolution(); };

window.autoLoad = autoLoad;

cseChargerDashboard();
