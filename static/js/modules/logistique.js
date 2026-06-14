var autoLoad = window.autoLoad || {};

var _logCamionsCache = [];
var _logPersonnelCache = [];
var _logVoyagesCache = [];
var _logVoyagesTableCache = [];

// -- Selects partages --------------------------------------------------------------
function logRemplirSelectCamions(selectId, emptyLabel) {
    var sel = document.getElementById(selectId);
    if (!sel) return;
    var html = (emptyLabel !== undefined) ? ('<option value="">' + emptyLabel + '</option>') : '';
    _logCamionsCache.forEach(function(c) {
        html += '<option value="' + c.id + '">' + c.immatriculation + '</option>';
    });
    sel.innerHTML = html;
}

function logRemplirSelectPersonnel(selectId, role) {
    var sel = document.getElementById(selectId);
    if (!sel) return;
    var html = '<option value="">—</option>';
    _logPersonnelCache.forEach(function(p) {
        if (!role || p.role === role) {
            html += '<option value="' + p.id + '">' + p.nom + (p.prenom ? (' ' + p.prenom) : '') + '</option>';
        }
    });
    sel.innerHTML = html;
}

function logRemplirSelectVoyages(selectId) {
    var sel = document.getElementById(selectId);
    if (!sel) return;
    var html = '<option value="">—</option>';
    _logVoyagesCache.forEach(function(v) {
        html += '<option value="' + v.id + '">' + v.no_voyage + ' (' + v.origine + ' -> ' + v.destination + ')</option>';
    });
    sel.innerHTML = html;
}

// -- Tableau de bord ----------------------------------------------------------------
function logChargerDashboard() {
    apiGet('/api/logistique/dashboard-summary', function(d) {
        var s = d.summary;
        document.getElementById('kpi-camions-actifs').textContent = s.camions_actifs;
        document.getElementById('kpi-voyages-jour').textContent = s.voyages_jour;
        document.getElementById('kpi-voyages-cours').textContent = s.voyages_en_cours;
        document.getElementById('kpi-entretiens-alerte').textContent = s.entretiens_alerte;
        document.getElementById('kpi-recettes-mois').textContent = fmt.money(s.recettes_mois);
        document.getElementById('kpi-depenses-mois').textContent = fmt.money(s.depenses_mois);
    });
}
autoLoad['logistique-dashboard'] = function() { logChargerDashboard(); };

// -- Camions --------------------------------------------------------------------------
function logChargerCamions(callback) {
    loadingTable('cam-tbody', 8);
    apiGet('/api/logistique/camions', function(d) {
        _logCamionsCache = d.data;
        logRenduCamions();
        if (callback) callback();
    });
}

function logRenduCamions() {
    if (!_logCamionsCache.length) {
        emptyTable('cam-tbody', 8, 'Aucun camion');
        return;
    }
    var html = '';
    _logCamionsCache.forEach(function(c) {
        html += '<tr>' +
            '<td>' + c.immatriculation + '</td>' +
            '<td>' + (c.marque || '') + ' ' + (c.modele || '') + '</td>' +
            '<td>' + c.type_flotte + '</td>' +
            '<td>' + fmt.qty(c.capacite_tonnes) + '</td>' +
            '<td>' + (c.proprietaire || '—') + '</td>' +
            '<td>' + (c.compte_sage || '—') + '</td>' +
            '<td>' + (c.actif ? badge('Actif', 'ok') : badge('Inactif', 'muted')) + '</td>' +
            '<td><button class="btn btn-outline btn-sm" onclick="logOuvrirCamion(' + c.id + ')">✏️</button></td>' +
            '</tr>';
    });
    document.getElementById('cam-tbody').innerHTML = html;
}

function logOuvrirCamion(id) {
    document.getElementById('mc-id').value = id || '';
    if (id) {
        var c = _logCamionsCache.filter(function(x) { return x.id === id; })[0];
        if (!c) return;
        document.getElementById('mc-titre').textContent = 'Modifier camion';
        document.getElementById('mc-immat').value = c.immatriculation;
        document.getElementById('mc-marque').value = c.marque || '';
        document.getElementById('mc-modele').value = c.modele || '';
        document.getElementById('mc-type-flotte').value = c.type_flotte || 'MAISON';
        document.getElementById('mc-capacite').value = c.capacite_tonnes || 0;
        document.getElementById('mc-annee').value = c.annee_mise_service || '';
        document.getElementById('mc-proprietaire').value = c.proprietaire || '';
        document.getElementById('mc-compte-sage').value = c.compte_sage || '';
        document.getElementById('mc-observations').value = c.observations || '';
        document.getElementById('mc-actif').checked = !!c.actif;
    } else {
        document.getElementById('mc-titre').textContent = 'Nouveau camion';
        document.getElementById('mc-immat').value = '';
        document.getElementById('mc-marque').value = '';
        document.getElementById('mc-modele').value = '';
        document.getElementById('mc-type-flotte').value = 'MAISON';
        document.getElementById('mc-capacite').value = '';
        document.getElementById('mc-annee').value = '';
        document.getElementById('mc-proprietaire').value = '';
        document.getElementById('mc-compte-sage').value = '';
        document.getElementById('mc-observations').value = '';
        document.getElementById('mc-actif').checked = true;
    }
    ouvrirModal('modal-camion');
}

function logSauverCamion() {
    var id = document.getElementById('mc-id').value;
    var data = {
        immatriculation: document.getElementById('mc-immat').value.trim(),
        marque: document.getElementById('mc-marque').value.trim(),
        modele: document.getElementById('mc-modele').value.trim(),
        type_flotte: document.getElementById('mc-type-flotte').value,
        capacite_tonnes: parseFloat(document.getElementById('mc-capacite').value) || 0,
        annee_mise_service: parseInt(document.getElementById('mc-annee').value) || null,
        proprietaire: document.getElementById('mc-proprietaire').value.trim(),
        compte_sage: document.getElementById('mc-compte-sage').value.trim(),
        observations: document.getElementById('mc-observations').value.trim(),
        actif: document.getElementById('mc-actif').checked
    };
    if (id) {
        apiPut('/api/logistique/camions/' + id, data, function(d) {
            fermerModal('modal-camion');
            status(d.msg);
            logChargerCamions();
        });
    } else {
        apiPost('/api/logistique/camions', data, function(d) {
            fermerModal('modal-camion');
            status(d.msg);
            logChargerCamions();
        });
    }
}
autoLoad['camions'] = function() { logChargerCamions(); };

// -- Chauffeurs & convoyeurs -----------------------------------------------------------
function logChargerPersonnel(callback) {
    loadingTable('pers-tbody', 8);
    apiGet('/api/logistique/personnel', function(d) {
        _logPersonnelCache = d.data;
        logRenduPersonnel();
        if (callback) callback();
    });
}

function logRenduPersonnel() {
    if (!_logPersonnelCache.length) {
        emptyTable('pers-tbody', 8, 'Aucun personnel');
        return;
    }
    var html = '';
    _logPersonnelCache.forEach(function(p) {
        html += '<tr>' +
            '<td>' + p.nom + '</td>' +
            '<td>' + (p.prenom || '—') + '</td>' +
            '<td>' + (p.role === 'CHAUFFEUR' ? badge('Chauffeur', 'info') : badge('Convoyeur', 'muted')) + '</td>' +
            '<td>' + (p.telephone || '—') + '</td>' +
            '<td>' + (p.permis || '—') + '</td>' +
            '<td>' + (p.camion_immat || '—') + '</td>' +
            '<td>' + (p.actif ? badge('Actif', 'ok') : badge('Inactif', 'muted')) + '</td>' +
            '<td><button class="btn btn-outline btn-sm" onclick="logOuvrirPersonnel(' + p.id + ')">✏️</button></td>' +
            '</tr>';
    });
    document.getElementById('pers-tbody').innerHTML = html;
}

function logOuvrirPersonnel(id) {
    logChargerCamions(function() {
        logRemplirSelectCamions('mp-camion', '—');
        document.getElementById('mp-id').value = id || '';
        if (id) {
            var p = _logPersonnelCache.filter(function(x) { return x.id === id; })[0];
            if (!p) return;
            document.getElementById('mp-titre').textContent = 'Modifier personnel';
            document.getElementById('mp-nom').value = p.nom;
            document.getElementById('mp-prenom').value = p.prenom || '';
            document.getElementById('mp-role').value = p.role || 'CHAUFFEUR';
            document.getElementById('mp-telephone').value = p.telephone || '';
            document.getElementById('mp-permis').value = p.permis || '';
            document.getElementById('mp-camion').value = p.camion_id || '';
            document.getElementById('mp-actif').checked = !!p.actif;
        } else {
            document.getElementById('mp-titre').textContent = 'Nouveau personnel';
            document.getElementById('mp-nom').value = '';
            document.getElementById('mp-prenom').value = '';
            document.getElementById('mp-role').value = 'CHAUFFEUR';
            document.getElementById('mp-telephone').value = '';
            document.getElementById('mp-permis').value = '';
            document.getElementById('mp-camion').value = '';
            document.getElementById('mp-actif').checked = true;
        }
        ouvrirModal('modal-personnel');
    });
}

function logSauverPersonnel() {
    var id = document.getElementById('mp-id').value;
    var data = {
        nom: document.getElementById('mp-nom').value.trim(),
        prenom: document.getElementById('mp-prenom').value.trim(),
        role: document.getElementById('mp-role').value,
        telephone: document.getElementById('mp-telephone').value.trim(),
        permis: document.getElementById('mp-permis').value.trim(),
        camion_id: document.getElementById('mp-camion').value || null,
        actif: document.getElementById('mp-actif').checked
    };
    if (id) {
        apiPut('/api/logistique/personnel/' + id, data, function(d) {
            fermerModal('modal-personnel');
            status(d.msg);
            logChargerPersonnel();
        });
    } else {
        apiPost('/api/logistique/personnel', data, function(d) {
            fermerModal('modal-personnel');
            status(d.msg);
            logChargerPersonnel();
        });
    }
}
autoLoad['chauffeurs'] = function() { logChargerPersonnel(); };

// -- Voyages -----------------------------------------------------------------------------
function logChargerVoyages() {
    loadingTable('voy-tbody', 9);
    var statut = document.getElementById('voy-filtre-statut').value;
    var url = '/api/logistique/voyages' + (statut ? '?statut=' + statut : '');
    apiGet(url, function(d) {
        _logVoyagesTableCache = d.data;
        if (!d.data.length) {
            emptyTable('voy-tbody', 9, 'Aucun voyage');
            return;
        }
        var badges = {planifie: 'info', en_cours: 'warn', termine: 'ok', annule: 'err'};
        var html = '';
        d.data.forEach(function(v) {
            html += '<tr>' +
                '<td>' + v.no_voyage + '</td>' +
                '<td>' + (v.camion_immat || '—') + '</td>' +
                '<td>' + (v.chauffeur_nom || '—') + '</td>' +
                '<td>' + v.origine + '</td>' +
                '<td>' + v.destination + '</td>' +
                '<td>' + fmt.date(v.date_depart) + '</td>' +
                '<td>' + fmt.date(v.date_retour) + '</td>' +
                '<td>' + badge(v.statut, badges[v.statut] || 'info') + '</td>' +
                '<td><button class="btn btn-outline btn-sm" onclick="logOuvrirVoyage(' + v.id + ')">✏️</button></td>' +
                '</tr>';
        });
        document.getElementById('voy-tbody').innerHTML = html;
    });
}

function logOuvrirVoyage(id) {
    logChargerCamions(function() {
        logChargerPersonnel(function() {
            logRemplirSelectCamions('mv-camion');
            logRemplirSelectPersonnel('mv-chauffeur', 'CHAUFFEUR');
            logRemplirSelectPersonnel('mv-convoyeur', 'CONVOYEUR');
            document.getElementById('mv-id').value = id || '';
            if (id) {
                var v = _logVoyagesTableCache.filter(function(x) { return x.id === id; })[0];
                if (!v) return;
                document.getElementById('mv-titre').textContent = 'Modifier voyage ' + v.no_voyage;
                document.getElementById('mv-camion').value = v.camion_id || '';
                document.getElementById('mv-chauffeur').value = v.chauffeur_id || '';
                document.getElementById('mv-convoyeur').value = v.convoyeur_id || '';
                document.getElementById('mv-statut').value = v.statut || 'planifie';
                document.getElementById('mv-origine').value = v.origine || '';
                document.getElementById('mv-destination').value = v.destination || '';
                document.getElementById('mv-date-depart').value = v.date_depart || '';
                document.getElementById('mv-date-retour').value = v.date_retour || '';
                document.getElementById('mv-client').value = v.client_fournisseur || '';
                document.getElementById('mv-marchandises').value = v.marchandises || '';
                document.getElementById('mv-observations').value = v.observations || '';
            } else {
                document.getElementById('mv-titre').textContent = 'Nouveau voyage';
                document.getElementById('mv-camion').value = '';
                document.getElementById('mv-chauffeur').value = '';
                document.getElementById('mv-convoyeur').value = '';
                document.getElementById('mv-statut').value = 'planifie';
                document.getElementById('mv-origine').value = '';
                document.getElementById('mv-destination').value = '';
                document.getElementById('mv-date-depart').value = '';
                document.getElementById('mv-date-retour').value = '';
                document.getElementById('mv-client').value = '';
                document.getElementById('mv-marchandises').value = '';
                document.getElementById('mv-observations').value = '';
            }
            ouvrirModal('modal-voyage');
        });
    });
}

function logSauverVoyage() {
    var id = document.getElementById('mv-id').value;
    var data = {
        camion_id: document.getElementById('mv-camion').value || null,
        chauffeur_id: document.getElementById('mv-chauffeur').value || null,
        convoyeur_id: document.getElementById('mv-convoyeur').value || null,
        statut: document.getElementById('mv-statut').value,
        origine: document.getElementById('mv-origine').value.trim(),
        destination: document.getElementById('mv-destination').value.trim(),
        date_depart: document.getElementById('mv-date-depart').value,
        date_retour: document.getElementById('mv-date-retour').value,
        client_fournisseur: document.getElementById('mv-client').value.trim(),
        marchandises: document.getElementById('mv-marchandises').value.trim(),
        observations: document.getElementById('mv-observations').value.trim()
    };
    if (id) {
        apiPut('/api/logistique/voyages/' + id, data, function(d) {
            fermerModal('modal-voyage');
            status(d.msg);
            logChargerVoyages();
        });
    } else {
        apiPost('/api/logistique/voyages', data, function(d) {
            fermerModal('modal-voyage');
            status(d.msg);
            logChargerVoyages();
        });
    }
}
autoLoad['voyages'] = function() { logChargerVoyages(); };

// -- Entretiens --------------------------------------------------------------------------
function logChargerEntretiens() {
    loadingTable('ent-tbody', 7);
    apiGet('/api/logistique/entretiens', function(d) {
        if (!d.data.length) {
            emptyTable('ent-tbody', 7, 'Aucun entretien');
            return;
        }
        var html = '';
        d.data.forEach(function(e) {
            html += '<tr>' +
                '<td>' + fmt.date(e.date_entretien) + '</td>' +
                '<td>' + (e.camion_immat || '—') + '</td>' +
                '<td>' + e.type_entretien + '</td>' +
                '<td>' + fmt.qty(e.kilometrage) + '</td>' +
                '<td>' + fmt.money(e.cout) + '</td>' +
                '<td>' + (e.prestataire || '—') + '</td>' +
                '<td>' + fmt.date(e.prochaine_revision) + '</td>' +
                '</tr>';
        });
        document.getElementById('ent-tbody').innerHTML = html;
    });
}

function logSauverEntretien() {
    var data = {
        camion_id: document.getElementById('ent-camion').value || null,
        type_entretien: document.getElementById('ent-type').value,
        date_entretien: document.getElementById('ent-date').value,
        kilometrage: parseInt(document.getElementById('ent-km').value) || 0,
        cout: parseFloat(document.getElementById('ent-cout').value) || 0,
        prestataire: document.getElementById('ent-prestataire').value.trim(),
        description: document.getElementById('ent-description').value.trim(),
        prochaine_revision: document.getElementById('ent-prochaine').value
    };
    apiPost('/api/logistique/entretiens', data, function(d) {
        status(d.msg);
        document.getElementById('ent-km').value = '';
        document.getElementById('ent-cout').value = '';
        document.getElementById('ent-prestataire').value = '';
        document.getElementById('ent-description').value = '';
        document.getElementById('ent-prochaine').value = '';
        logChargerEntretiens();
    });
}
autoLoad['entretiens'] = function() {
    logChargerCamions(function() {
        logRemplirSelectCamions('ent-camion');
    });
    logChargerEntretiens();
};

// -- Recettes & depenses -------------------------------------------------------------------
function logChargerVoyagesCache(callback) {
    apiGet('/api/logistique/voyages', function(d) {
        _logVoyagesCache = d.data;
        if (callback) callback();
    });
}

function logChargerTransactions() {
    loadingTable('tr-tbody', 8);
    var camionId = document.getElementById('trh-filtre-camion').value;
    var url = '/api/logistique/transactions' + (camionId ? '?camion_id=' + camionId : '');
    apiGet(url, function(d) {
        if (!d.data.length) {
            emptyTable('tr-tbody', 8, 'Aucune transaction');
            return;
        }
        var html = '';
        d.data.forEach(function(t) {
            html += '<tr>' +
                '<td>' + fmt.date(t.date_transaction) + '</td>' +
                '<td>' + (t.camion_immat || '—') + '</td>' +
                '<td>' + (t.no_voyage || '—') + '</td>' +
                '<td>' + (t.type_transaction === 'RECETTE' ? badge('Recette', 'ok') : badge('Depense', 'err')) + '</td>' +
                '<td>' + t.categorie + '</td>' +
                '<td>' + fmt.money(t.montant) + '</td>' +
                '<td>' + (t.libelle || '—') + '</td>' +
                '<td>' + (t.reference_sage || '—') + '</td>' +
                '</tr>';
        });
        document.getElementById('tr-tbody').innerHTML = html;
    });
}

function logSauverTransaction() {
    var data = {
        camion_id: document.getElementById('tr-camion').value || null,
        voyage_id: document.getElementById('tr-voyage').value || null,
        type_transaction: document.getElementById('tr-type').value,
        categorie: document.getElementById('tr-categorie').value,
        date_transaction: document.getElementById('tr-date').value,
        montant: parseFloat(document.getElementById('tr-montant').value) || 0,
        libelle: document.getElementById('tr-libelle').value.trim(),
        reference_sage: document.getElementById('tr-reference').value.trim()
    };
    apiPost('/api/logistique/transactions', data, function(d) {
        status(d.msg);
        document.getElementById('tr-montant').value = '';
        document.getElementById('tr-libelle').value = '';
        document.getElementById('tr-reference').value = '';
        logChargerTransactions();
    });
}
autoLoad['transactions'] = function() {
    logChargerCamions(function() {
        logRemplirSelectCamions('tr-camion');
        logRemplirSelectCamions('trh-filtre-camion', 'Tous les camions');
        logChargerVoyagesCache(function() {
            logRemplirSelectVoyages('tr-voyage');
        });
        logChargerTransactions();
    });
};

// -- Grand livre camion --------------------------------------------------------------------
function logChargerGrandLivre() {
    var camionId = document.getElementById('gl-camion').value;
    if (!camionId) {
        emptyTable('gl-tbody', 7, 'Selectionnez un camion');
        return;
    }
    loadingTable('gl-tbody', 7);
    apiGet('/api/logistique/grand-livre-camion?camion_id=' + camionId, function(d) {
        if (!d.data.length) {
            emptyTable('gl-tbody', 7, 'Aucune ecriture');
            return;
        }
        var html = '';
        d.data.forEach(function(l) {
            html += '<tr>' +
                '<td>' + fmt.date(l.date) + '</td>' +
                '<td>' + badge(l.source, l.source === 'SAGE' ? 'info' : 'muted') + '</td>' +
                '<td>' + (l.type_transaction === 'RECETTE' ? badge('Recette', 'ok') : badge('Depense', 'err')) + '</td>' +
                '<td>' + (l.categorie || '—') + '</td>' +
                '<td>' + fmt.money(l.montant) + '</td>' +
                '<td>' + (l.libelle || '—') + '</td>' +
                '<td>' + (l.reference_sage || '—') + '</td>' +
                '</tr>';
        });
        document.getElementById('gl-tbody').innerHTML = html;
    });
}
autoLoad['grand-livre'] = function() {
    logChargerCamions(function() {
        logRemplirSelectCamions('gl-camion', 'Choisir un camion');
        emptyTable('gl-tbody', 7, 'Selectionnez un camion');
    });
};

// -- Rapprochement camion -------------------------------------------------------------------
function logChargerRapprochement() {
    var camionId = document.getElementById('rap-camion').value;
    if (!camionId) return;
    apiGet('/api/logistique/rapprochement-camion?camion_id=' + camionId, function(d) {
        var r = d.rapprochement;
        document.getElementById('rap-local-recettes').textContent = fmt.money(r.local_recettes);
        document.getElementById('rap-local-depenses').textContent = fmt.money(r.local_depenses);
        document.getElementById('rap-sage-credit').textContent = fmt.money(r.sage_credit);
        document.getElementById('rap-sage-debit').textContent = fmt.money(r.sage_debit);
        document.getElementById('rap-ecart-recettes').textContent = fmt.money(r.ecart_recettes);
        document.getElementById('rap-ecart-depenses').textContent = fmt.money(r.ecart_depenses);
    });
}
autoLoad['rapprochement'] = function() {
    logChargerCamions(function() {
        logRemplirSelectCamions('rap-camion', 'Choisir un camion');
    });
};

window.autoLoad = autoLoad;

logChargerDashboard();
