var autoLoad = window.autoLoad || {};

var _rhEmployesCache = [];
var _rhRechercheTimer = null;

var STATUT_PRESENCE_LABELS = {
    PRESENT: 'Present',
    ABSENT: 'Absent',
    CONGE: 'Conge',
    MALADIE: 'Maladie'
};
var STATUT_PRESENCE_TYPES = {
    PRESENT: 'ok',
    ABSENT: 'err',
    CONGE: 'info',
    MALADIE: 'warn'
};

// -- Tableau de bord ----------------------------------------------------------------
function rhChargerDashboard() {
    apiGet('/api/rh/dashboard-summary', function(d) {
        var s = d.summary;
        document.getElementById('kpi-effectif-actif').textContent = s.effectif_actif;
        document.getElementById('kpi-presents-jour').textContent = s.presents_jour;
        document.getElementById('kpi-absents-jour').textContent = s.absents_jour;
        document.getElementById('kpi-masse-salariale').textContent = fmt.money(s.masse_salariale);
        document.getElementById('kpi-recrutements-mois').textContent = s.recrutements_mois;
        document.getElementById('kpi-departs-mois').textContent = s.departs_mois;
    });
}
autoLoad['rh-dashboard'] = function() { rhChargerDashboard(); };

// -- Departements partages -----------------------------------------------------------
function rhChargerDepartements(callback) {
    apiGet('/api/rh/departements', function(d) {
        ['emp-filtre-departement', 'pr-departement', 'ph-departement'].forEach(function(selId) {
            var sel = document.getElementById(selId);
            if (!sel) return;
            var courant = sel.value;
            var html = '<option value="">Tous</option>';
            d.data.forEach(function(dep) {
                html += '<option value="' + dep + '">' + dep + '</option>';
            });
            sel.innerHTML = html;
            sel.value = courant;
        });
        if (callback) callback();
    });
}

// -- Fiches employes -------------------------------------------------------------------
function rhChargerEmployes() {
    loadingTable('emp-tbody', 9);
    var q = document.getElementById('emp-recherche').value.trim();
    var departement = document.getElementById('emp-filtre-departement').value;
    var parts = [];
    if (q) parts.push('q=' + encodeURIComponent(q));
    if (departement) parts.push('departement=' + encodeURIComponent(departement));
    var url = '/api/rh/employes' + (parts.length ? ('?' + parts.join('&')) : '');
    apiGet(url, function(d) {
        _rhEmployesCache = d.data;
        if (!_rhEmployesCache.length) {
            emptyTable('emp-tbody', 9, 'Aucun employe');
            return;
        }
        var html = '';
        _rhEmployesCache.forEach(function(e) {
            html += '<tr>' +
                '<td>' + e.matricule + '</td>' +
                '<td>' + (e.nom || '—') + '</td>' +
                '<td>' + (e.prenom || '—') + '</td>' +
                '<td>' + (e.poste || '—') + '</td>' +
                '<td>' + (e.departement || '—') + '</td>' +
                '<td>' + fmt.date(e.date_embauche) + '</td>' +
                '<td>' + fmt.money(e.salaire_base) + '</td>' +
                '<td>' + (e.actif ? badge('Actif', 'ok') : badge('Inactif', 'muted')) + '</td>' +
                '<td><button class="btn btn-outline btn-sm" onclick="rhOuvrirEmploye(' + e.id + ')">✏️</button></td>' +
                '</tr>';
        });
        document.getElementById('emp-tbody').innerHTML = html;
    });
}
autoLoad['fiches-employes'] = function() {
    rhChargerDepartements(function() { rhChargerEmployes(); });
};

function rhRechercheEmployes() {
    if (_rhRechercheTimer) clearTimeout(_rhRechercheTimer);
    _rhRechercheTimer = setTimeout(rhChargerEmployes, 300);
}

function rhOuvrirEmploye(id) {
    document.getElementById('emp-id').value = id || '';
    if (id) {
        var e = _rhEmployesCache.filter(function(x) { return x.id === id; })[0];
        if (!e) return;
        document.getElementById('emp-titre').textContent = 'Modifier employe';
        document.getElementById('emp-matricule').value = e.matricule;
        document.getElementById('emp-matricule').disabled = true;
        document.getElementById('emp-nom').value = e.nom || '';
        document.getElementById('emp-prenom').value = e.prenom || '';
        document.getElementById('emp-poste').value = e.poste || '';
        document.getElementById('emp-departement').value = e.departement || '';
        document.getElementById('emp-date-embauche').value = e.date_embauche || '';
        document.getElementById('emp-date-depart').value = e.date_depart || '';
        document.getElementById('emp-salaire').value = e.salaire_base || 0;
        document.getElementById('emp-telephone').value = e.telephone || '';
        document.getElementById('emp-email').value = e.email || '';
        document.getElementById('emp-actif').checked = !!e.actif;
    } else {
        document.getElementById('emp-titre').textContent = 'Nouvel employe';
        document.getElementById('emp-matricule').value = '';
        document.getElementById('emp-matricule').disabled = false;
        document.getElementById('emp-nom').value = '';
        document.getElementById('emp-prenom').value = '';
        document.getElementById('emp-poste').value = '';
        document.getElementById('emp-departement').value = '';
        document.getElementById('emp-date-embauche').value = '';
        document.getElementById('emp-date-depart').value = '';
        document.getElementById('emp-salaire').value = '0';
        document.getElementById('emp-telephone').value = '';
        document.getElementById('emp-email').value = '';
        document.getElementById('emp-actif').checked = true;
    }
    ouvrirModal('modal-employe');
}

function rhSauverEmploye() {
    var id = document.getElementById('emp-id').value;
    var data = {
        matricule: document.getElementById('emp-matricule').value.trim(),
        nom: document.getElementById('emp-nom').value.trim(),
        prenom: document.getElementById('emp-prenom').value.trim(),
        poste: document.getElementById('emp-poste').value.trim(),
        departement: document.getElementById('emp-departement').value.trim(),
        date_embauche: document.getElementById('emp-date-embauche').value,
        date_depart: document.getElementById('emp-date-depart').value,
        salaire_base: parseFloat(document.getElementById('emp-salaire').value) || 0,
        telephone: document.getElementById('emp-telephone').value.trim(),
        email: document.getElementById('emp-email').value.trim(),
        actif: document.getElementById('emp-actif').checked
    };
    if (!data.matricule) { status('⚠ Indiquez le matricule'); return; }
    if (!data.nom) { status('⚠ Indiquez le nom'); return; }
    if (id) {
        apiPut('/api/rh/employes/' + id, data, function(d) {
            fermerModal('modal-employe');
            status(d.msg);
            rhChargerEmployes();
        });
    } else {
        apiPost('/api/rh/employes', data, function(d) {
            fermerModal('modal-employe');
            status(d.msg);
            rhChargerDepartements();
            rhChargerEmployes();
        });
    }
}

// -- Presences ----------------------------------------------------------------------------
function rhChargerPresences() {
    loadingTable('pr-tbody', 7);
    var d = document.getElementById('pr-date').value;
    var departement = document.getElementById('pr-departement').value;
    var parts = ['date=' + d];
    if (departement) parts.push('departement=' + encodeURIComponent(departement));
    apiGet('/api/rh/presences?' + parts.join('&'), function(resp) {
        if (!resp.data.length) {
            emptyTable('pr-tbody', 7, 'Aucun employe actif');
            return;
        }
        var html = '';
        resp.data.forEach(function(p) {
            var statut = p.statut || 'PRESENT';
            html += '<tr>' +
                '<td>' + p.matricule + '</td>' +
                '<td>' + (p.nom || '—') + '</td>' +
                '<td>' + (p.prenom || '—') + '</td>' +
                '<td>' + (p.poste || '—') + '</td>' +
                '<td>' + (p.departement || '—') + '</td>' +
                '<td><select class="pr-statut" data-employe="' + p.employe_id + '">' +
                    Object.keys(STATUT_PRESENCE_LABELS).map(function(k) {
                        return '<option value="' + k + '"' + (k === statut ? ' selected' : '') + '>' +
                            STATUT_PRESENCE_LABELS[k] + '</option>';
                    }).join('') +
                '</select></td>' +
                '<td><input type="text" class="pr-obs" data-employe="' + p.employe_id + '" ' +
                    'value="' + (p.observations || '') + '" style="width:100%"></td>' +
                '</tr>';
        });
        document.getElementById('pr-tbody').innerHTML = html;
    });
}
autoLoad['presences-rh'] = function() {
    if (!document.getElementById('pr-date').value) {
        var aujourdhui = new Date();
        document.getElementById('pr-date').value = aujourdhui.toISOString().substring(0, 10);
    }
    if (!document.getElementById('ph-date-debut').value) {
        var debut = new Date();
        debut.setDate(debut.getDate() - 7);
        document.getElementById('ph-date-debut').value = debut.toISOString().substring(0, 10);
    }
    if (!document.getElementById('ph-date-fin').value) {
        document.getElementById('ph-date-fin').value = new Date().toISOString().substring(0, 10);
    }
    rhChargerDepartements(function() {
        rhChargerPresences();
        rhChargerHistoriquePresences();
    });
};

function rhSauverPresences() {
    var datePresence = document.getElementById('pr-date').value;
    if (!datePresence) { status('⚠ Choisissez une date'); return; }
    var lignes = [];
    document.querySelectorAll('#pr-tbody .pr-statut').forEach(function(sel) {
        var empId = sel.getAttribute('data-employe');
        var obsInput = document.querySelector('#pr-tbody .pr-obs[data-employe="' + empId + '"]');
        lignes.push({
            employe_id: parseInt(empId),
            statut: sel.value,
            observations: obsInput ? obsInput.value.trim() : ''
        });
    });
    apiPost('/api/rh/presences', {date_presence: datePresence, lignes: lignes}, function(d) {
        status(d.msg);
        rhChargerHistoriquePresences();
        rhChargerDashboard();
    });
}

function rhChargerHistoriquePresences() {
    loadingTable('ph-tbody', 7);
    var dd = document.getElementById('ph-date-debut').value;
    var df = document.getElementById('ph-date-fin').value;
    var departement = document.getElementById('ph-departement').value;
    var parts = [];
    if (dd) parts.push('date_debut=' + dd);
    if (df) parts.push('date_fin=' + df);
    if (departement) parts.push('departement=' + encodeURIComponent(departement));
    var url = '/api/rh/presences/historique' + (parts.length ? ('?' + parts.join('&')) : '');
    apiGet(url, function(d) {
        if (!d.data.length) {
            emptyTable('ph-tbody', 7, 'Aucune donnee');
            return;
        }
        var html = '';
        d.data.forEach(function(p) {
            html += '<tr>' +
                '<td>' + fmt.date(p.date_presence) + '</td>' +
                '<td>' + p.matricule + '</td>' +
                '<td>' + (p.nom || '—') + '</td>' +
                '<td>' + (p.prenom || '—') + '</td>' +
                '<td>' + (p.departement || '—') + '</td>' +
                '<td>' + badge(STATUT_PRESENCE_LABELS[p.statut] || p.statut, STATUT_PRESENCE_TYPES[p.statut] || 'info') + '</td>' +
                '<td>' + (p.observations || '—') + '</td>' +
                '</tr>';
        });
        document.getElementById('ph-tbody').innerHTML = html;
    });
}

window.autoLoad = autoLoad;

rhChargerDashboard();
