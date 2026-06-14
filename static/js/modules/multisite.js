var autoLoad = window.autoLoad || {};

var _msiteAgencesCache = [];

// ── Tableau de bord ───────────────────────────────────────────────────────────
function msiteChargerDashboard() {
    apiGet('/api/multisite/dashboard-summary', function(d) {
        var s = d.summary;
        document.getElementById('kpi-nb-agences').textContent = s.nb_agences;
        document.getElementById('kpi-dt-attente').textContent = s.dt_attente;
        document.getElementById('kpi-dt-cours').textContent = s.dt_cours;
        document.getElementById('kpi-da-attente').textContent = s.da_attente;
        if (s.est_siege) {
            document.getElementById('msite-siege-info').style.display = '';
        }
    });
}
autoLoad['multisite-dashboard'] = function() {
    msiteChargerDashboard();
};

// ── Agences (cache partage) ───────────────────────────────────────────────────
function msiteChargerAgences(callback) {
    var tbody = document.getElementById('ag-tbody');
    if (tbody) loadingTable('ag-tbody', 8);
    apiGet('/api/multisite/agences', function(d) {
        _msiteAgencesCache = d.data || [];
        if (tbody) msiteRenduAgences();
        if (callback) callback();
    });
}

function msiteRenduAgences() {
    if (!_msiteAgencesCache.length) {
        emptyTable('ag-tbody', 8, 'Aucune agence');
        return;
    }
    var html = '';
    _msiteAgencesCache.forEach(function(a) {
        html += '<tr>' +
            '<td>' + a.code + '</td>' +
            '<td>' + a.nom + '</td>' +
            '<td>' + (a.ville || '') + '</td>' +
            '<td>' + (a.type_site || '') + '</td>' +
            '<td>' + (a.depot_sage_no || '—') + '</td>' +
            '<td>' + (a.telephone || '') + '</td>' +
            '<td>' + badge(a.actif ? 'Active' : 'Inactive', a.actif ? 'ok' : 'muted') + '</td>' +
            '<td><button class="btn btn-outline btn-sm" onclick="msiteOuvrirAgence(' + a.id + ')">Modifier</button></td>' +
            '</tr>';
    });
    document.getElementById('ag-tbody').innerHTML = html;
}

function msiteOuvrirAgence(id) {
    var a = null;
    if (id) {
        a = _msiteAgencesCache.filter(function(x) { return x.id === id; })[0];
    }
    document.getElementById('ma-id').value = id || '';
    document.getElementById('ma-titre').textContent = id ? 'Modifier une agence' : 'Nouvelle agence';
    document.getElementById('ma-code').value = a ? a.code : '';
    document.getElementById('ma-code').disabled = !!id;
    document.getElementById('ma-nom').value = a ? a.nom : '';
    document.getElementById('ma-ville').value = a ? (a.ville || '') : '';
    document.getElementById('ma-adresse').value = a ? (a.adresse || '') : '';
    document.getElementById('ma-telephone').value = a ? (a.telephone || '') : '';
    document.getElementById('ma-type-site').value = a ? (a.type_site || 'AGENCE') : 'AGENCE';
    document.getElementById('ma-depot-sage').value = a ? (a.depot_sage_no || '') : '';
    document.getElementById('ma-actif').checked = a ? !!a.actif : true;
    ouvrirModal('modal-agence');
}

function msiteSauverAgence() {
    var id = document.getElementById('ma-id').value;
    var data = {
        nom: document.getElementById('ma-nom').value,
        ville: document.getElementById('ma-ville').value,
        adresse: document.getElementById('ma-adresse').value,
        telephone: document.getElementById('ma-telephone').value,
        type_site: document.getElementById('ma-type-site').value,
        depot_sage_no: document.getElementById('ma-depot-sage').value || null
    };
    if (id) {
        data.actif = document.getElementById('ma-actif').checked;
        apiPut('/api/multisite/agences/' + id, data, function() {
            fermerModal('modal-agence');
            status('Agence mise a jour');
            msiteChargerAgences();
        });
    } else {
        data.code = document.getElementById('ma-code').value;
        if (!data.code || !data.nom) {
            status('⚠ Code et nom requis');
            return;
        }
        apiPost('/api/multisite/agences', data, function() {
            fermerModal('modal-agence');
            status('Agence creee');
            msiteChargerAgences();
        });
    }
}

autoLoad['agences'] = function() {
    msiteChargerAgences();
};

// ── Selecteurs d'agences partages ─────────────────────────────────────────────
function msiteRemplirSelect(selectId) {
    var sel = document.getElementById(selectId);
    if (!sel) return;
    var current = sel.value;
    var html = '';
    _msiteAgencesCache.forEach(function(a) {
        html += '<option value="' + a.id + '">' + a.nom + ' (' + a.code + ')</option>';
    });
    sel.innerHTML = html;
    if (current && _msiteAgencesCache.some(function(a) { return String(a.id) === current; })) {
        sel.value = current;
    }
}

// ── Permissions de visibilite ─────────────────────────────────────────────────
function msiteChargerVisibilite() {
    var srcId = document.getElementById('vis-source').value;
    if (!srcId) return;
    apiGet('/api/multisite/permissions-visibilite', function(d) {
        var perms = d.data || [];
        var cibles = _msiteAgencesCache.filter(function(a) { return String(a.id) !== String(srcId); });
        if (!cibles.length) {
            emptyTable('vis-tbody', 6, 'Aucune autre agence');
            return;
        }
        var html = '';
        cibles.forEach(function(c) {
            var p = perms.filter(function(x) {
                return String(x.agence_source) === String(srcId) && String(x.agence_cible) === String(c.id);
            })[0] || {};
            html += '<tr>' +
                '<td>' + c.nom + ' (' + c.code + ')</td>' +
                '<td><input type="checkbox" class="vp-stock" ' + (p.peut_voir_stock ? 'checked' : '') + '></td>' +
                '<td><input type="checkbox" class="vp-dt" ' + (p.peut_voir_dt ? 'checked' : '') + '></td>' +
                '<td><input type="checkbox" class="vp-ventes" ' + (p.peut_voir_ventes ? 'checked' : '') + '></td>' +
                '<td><input type="checkbox" class="vp-creances" ' + (p.peut_voir_creances ? 'checked' : '') + '></td>' +
                '<td><button class="btn btn-navy btn-sm" onclick="msiteSauverVisibilite(this,' + c.id + ')">💾</button></td>' +
                '</tr>';
        });
        document.getElementById('vis-tbody').innerHTML = html;
    });
}

function msiteSauverVisibilite(btn, cibleId) {
    var tr = btn.closest('tr');
    var data = {
        agence_source: document.getElementById('vis-source').value,
        agence_cible: cibleId,
        peut_voir_stock: tr.querySelector('.vp-stock').checked,
        peut_voir_dt: tr.querySelector('.vp-dt').checked,
        peut_voir_ventes: tr.querySelector('.vp-ventes').checked,
        peut_voir_creances: tr.querySelector('.vp-creances').checked
    };
    apiPost('/api/multisite/permissions-visibilite', data, function() {
        status('Permissions de visibilite mises a jour');
    });
}

autoLoad['visibilite'] = function() {
    msiteChargerAgences(function() {
        msiteRemplirSelect('vis-source');
        msiteChargerVisibilite();
    });
};

// ── Stock reseau ───────────────────────────────────────────────────────────────
function msiteChargerStockReseau() {
    var q = document.getElementById('sr-recherche').value.trim();
    loadingTable('sr-tbody', 7);
    apiGet('/api/multisite/stock-disponible?q=' + encodeURIComponent(q), function(d) {
        var data = d.data || [];
        if (!data.length) {
            emptyTable('sr-tbody', 7, 'Aucun resultat (verifiez la connexion Sage et les depots configures)');
            return;
        }
        var html = '';
        data.forEach(function(r) {
            html += '<tr>' +
                '<td>' + (r.code_article || '') + '</td>' +
                '<td>' + (r.designation || '') + '</td>' +
                '<td>' + (r.famille || '') + '</td>' +
                '<td>' + (r.agence_nom || '') + '</td>' +
                '<td>' + (r.depot || '') + '</td>' +
                '<td>' + fmt.qty(r.stock_actuel) + '</td>' +
                '<td>' + fmt.money(r.valeur_stock) + '</td>' +
                '</tr>';
        });
        document.getElementById('sr-tbody').innerHTML = html;
    });
}
autoLoad['stock-reseau'] = function() {
    msiteChargerStockReseau();
};

// ── Creances consolidees ──────────────────────────────────────────────────────
function msiteChargerCreances() {
    loadingTable('cr-tbody', 6);
    apiGet('/api/multisite/creances-consolidees', function(d) {
        var data = d.data || [];
        if (!data.length) {
            emptyTable('cr-tbody', 6, 'Aucune creance (verifiez la connexion Sage)');
            return;
        }
        var html = '';
        data.forEach(function(r) {
            html += '<tr>' +
                '<td>' + (r.code_client || '') + '</td>' +
                '<td>' + (r.nom || '') + '</td>' +
                '<td>' + (r.telephone || '') + '</td>' +
                '<td>' + fmt.money(r.total_debit) + '</td>' +
                '<td>' + fmt.money(r.total_credit) + '</td>' +
                '<td>' + fmt.money(r.solde) + '</td>' +
                '</tr>';
        });
        document.getElementById('cr-tbody').innerHTML = html;
    });
}
autoLoad['creances'] = function() {
    msiteChargerCreances();
};

// ── Lignes panier partagees (DT / DA) ─────────────────────────────────────────
function msiteAjouterLigne(tbodyId) {
    var tbody = document.getElementById(tbodyId);
    var tr = document.createElement('tr');
    tr.innerHTML =
        '<td><input type="text" class="ln-code" style="width:100%"></td>' +
        '<td><input type="text" class="ln-design" style="width:100%"></td>' +
        '<td><input type="number" class="ln-qte" value="0" step="0.01" style="width:100%"></td>' +
        '<td><input type="number" class="ln-prix" value="0" step="1" style="width:100%"></td>' +
        '<td><button class="btn btn-outline btn-sm" onclick="this.closest(\'tr\').remove()">✕</button></td>';
    tbody.appendChild(tr);
}

function msiteLireLignes(tbodyId) {
    var lignes = [];
    document.querySelectorAll('#' + tbodyId + ' tr').forEach(function(tr) {
        var code = tr.querySelector('.ln-code');
        if (!code) return;
        var c = code.value.trim();
        if (!c) return;
        lignes.push({
            code_article: c,
            designation: tr.querySelector('.ln-design').value,
            quantite: parseFloat(tr.querySelector('.ln-qte').value) || 0,
            prix_unitaire: parseFloat(tr.querySelector('.ln-prix').value) || 0
        });
    });
    return lignes;
}

// ── Transferts inter-agences (DT) ─────────────────────────────────────────────
function msiteChargerDT() {
    var statut = document.getElementById('dt-filtre-statut').value;
    loadingTable('dt-tbody', 8);
    apiGet('/api/multisite/transferts' + (statut ? '?statut=' + statut : ''), function(d) {
        var data = d.data || [];
        if (!data.length) {
            emptyTable('dt-tbody', 8, 'Aucun transfert');
            return;
        }
        var statutTypes = {SOUMISE: 'warn', VALIDEE: 'info', EN_COURS: 'info', LIVREE: 'ok', REFUSEE: 'err'};
        var html = '';
        data.forEach(function(t) {
            html += '<tr>' +
                '<td>' + t.numero + '</td>' +
                '<td>' + (t.agence_source_nom || '') + '</td>' +
                '<td>' + (t.agence_dest_nom || '') + '</td>' +
                '<td>' + fmt.date(t.date_demande) + '</td>' +
                '<td>' + (t.nb_lignes || 0) + '</td>' +
                '<td>' + fmt.money(t.valeur_totale) + '</td>' +
                '<td>' + badge(t.statut, statutTypes[t.statut] || 'info') + '</td>' +
                '<td><button class="btn btn-outline btn-sm" onclick="msiteDetailDT(' + t.id + ')">Detail</button></td>' +
                '</tr>';
        });
        document.getElementById('dt-tbody').innerHTML = html;
    });
}
autoLoad['dt-liste'] = function() {
    msiteChargerDT();
};

function msiteDetailDT(id) {
    apiGet('/api/multisite/transferts/' + id, function(d) {
        var t = d.data;
        var lignes = d.lignes || [];
        document.getElementById('dtd-titre').textContent = 'Transfert ' + t.numero;

        var html = '<div class="form-grid">' +
            '<div><strong>Source :</strong> ' + (t.agence_source_nom || '') + '</div>' +
            '<div><strong>Destination :</strong> ' + (t.agence_dest_nom || '') + '</div>' +
            '<div><strong>Date :</strong> ' + fmt.date(t.date_demande) + '</div>' +
            '<div><strong>Demande par :</strong> ' + (t.demande_par || '') + '</div>' +
            '<div><strong>Statut :</strong> ' + badge(t.statut, 'info') + '</div>' +
            '<div><strong>Urgent :</strong> ' + (t.urgence ? 'Oui' : 'Non') + '</div>' +
            '</div>';
        if (t.observations) html += '<p>' + t.observations + '</p>';
        if (t.statut === 'REFUSEE' && t.motif_refus) {
            html += '<div class="alert alert-err">Motif de refus : ' + t.motif_refus + '</div>';
        }
        document.getElementById('dtd-info').innerHTML = html;

        var tb = '';
        lignes.forEach(function(l) {
            tb += '<tr>' +
                '<td>' + (l.ar_ref || '') + '</td>' +
                '<td>' + (l.designation || '') + '</td>' +
                '<td>' + fmt.qty(l.qte_demandee) + '</td>' +
                '<td>' + fmt.money(l.prix_unitaire) + '</td>' +
                '<td>' + fmt.qty(l.stock_dispo_src) + '</td>' +
                '</tr>';
        });
        document.getElementById('dtd-tbody').innerHTML = tb || '<tr><td colspan="5" class="tbl-empty">Aucune ligne</td></tr>';

        var actions = '';
        if (t.statut === 'SOUMISE' && window.NEXORA_EST_SIEGE) {
            actions = '<button class="btn btn-outline btn-sm" onclick="msiteValiderDT(' + t.id + ',\'refuser\')">❌ Refuser</button> ' +
                      '<button class="btn btn-gold" onclick="msiteValiderDT(' + t.id + ',\'valider\')">✅ Valider</button>';
        } else if (t.statut === 'VALIDEE') {
            actions = '<button class="btn btn-navy" onclick="msiteValiderDT(' + t.id + ',\'en_cours\')">🚚 Marquer en cours</button>';
        } else if (t.statut === 'EN_COURS') {
            actions = '<button class="btn btn-gold" onclick="msiteValiderDT(' + t.id + ',\'livrer\')">📦 Marquer livre</button>';
        }
        document.getElementById('dtd-actions').innerHTML = actions;
        ouvrirModal('modal-dt-detail');
    });
}

function msiteValiderDT(id, decision) {
    var data = {decision: decision};
    if (decision === 'refuser') {
        var motif = window.prompt('Motif de refus :');
        if (!motif) return;
        data.motif_refus = motif;
    }
    apiPost('/api/multisite/transferts/' + id + '/valider', data, function(d) {
        status(d.msg);
        fermerModal('modal-dt-detail');
        msiteChargerDT();
    });
}

autoLoad['dt-nouvelle'] = function() {
    msiteChargerAgences(function() {
        msiteRemplirSelect('dtn-source');
        msiteRemplirSelect('dtn-dest');
        if (_msiteAgencesCache.length > 1) {
            document.getElementById('dtn-dest').value = _msiteAgencesCache[1].id;
        }
    });
    document.getElementById('dtn-lignes-tbody').innerHTML = '';
};

function msiteSoumettreDT() {
    var src = document.getElementById('dtn-source').value;
    var dest = document.getElementById('dtn-dest').value;
    if (!src || !dest) { status('⚠ Choisissez les agences source et destination'); return; }
    if (src === dest) { status('⚠ Les agences source et destination doivent etre differentes'); return; }
    var lignes = msiteLireLignes('dtn-lignes-tbody');
    if (!lignes.length) { status('⚠ Ajoutez au moins une ligne'); return; }

    var data = {
        agence_source_id: src,
        agence_dest_id: dest,
        urgence: document.getElementById('dtn-urgence').checked,
        observations: document.getElementById('dtn-observations').value,
        lignes: lignes
    };
    apiPost('/api/multisite/transferts', data, function(d) {
        status(d.msg);
        document.getElementById('dtn-lignes-tbody').innerHTML = '';
        document.getElementById('dtn-observations').value = '';
        document.getElementById('dtn-urgence').checked = false;
        document.querySelector('[data-nav=dt-liste]').click();
    });
}

// ── Demandes d'achat (DA) ──────────────────────────────────────────────────────
function msiteChargerDA() {
    var statut = document.getElementById('da-filtre-statut').value;
    loadingTable('da-tbody', 7);
    apiGet('/api/multisite/demandes-achat' + (statut ? '?statut=' + statut : ''), function(d) {
        var data = d.data || [];
        if (!data.length) {
            emptyTable('da-tbody', 7, 'Aucune demande');
            return;
        }
        var statutTypes = {SOUMISE: 'warn', VALIDEE: 'info', COMMANDEE: 'ok', REFUSEE: 'err'};
        var html = '';
        data.forEach(function(da) {
            html += '<tr>' +
                '<td>' + da.numero + '</td>' +
                '<td>' + (da.agence_nom || '') + '</td>' +
                '<td>' + (da.fournisseur_nom || '—') + '</td>' +
                '<td>' + fmt.date(da.date_demande) + '</td>' +
                '<td>' + (da.bc_numero || '—') + '</td>' +
                '<td>' + badge(da.statut, statutTypes[da.statut] || 'info') + '</td>' +
                '<td><button class="btn btn-outline btn-sm" onclick="msiteDetailDA(' + da.id + ')">Detail</button></td>' +
                '</tr>';
        });
        document.getElementById('da-tbody').innerHTML = html;
    });
}
autoLoad['da-liste'] = function() {
    msiteChargerDA();
};

function msiteDetailDA(id) {
    apiGet('/api/multisite/demandes-achat/' + id, function(d) {
        var da = d.data;
        var lignes = d.lignes || [];
        document.getElementById('dad-titre').textContent = 'Demande ' + da.numero;

        var html = '<div class="form-grid">' +
            '<div><strong>Agence :</strong> ' + (da.agence_nom || '') + '</div>' +
            '<div><strong>Livraison :</strong> ' + (da.livraison_nom || '') + '</div>' +
            '<div><strong>Fournisseur :</strong> ' + (da.fournisseur_nom || '—') + '</div>' +
            '<div><strong>Date :</strong> ' + fmt.date(da.date_demande) + '</div>' +
            '<div><strong>Demande par :</strong> ' + (da.demande_par || '') + '</div>' +
            '<div><strong>Statut :</strong> ' + badge(da.statut, 'info') + '</div>' +
            '</div>';
        if (da.observations) html += '<p>' + da.observations + '</p>';
        if (da.statut === 'REFUSEE' && da.motif_refus) {
            html += '<div class="alert alert-err">Motif de refus : ' + da.motif_refus + '</div>';
        }
        if (da.bc_numero) {
            html += '<div class="alert alert-ok">Bon de commande Sage : ' + da.bc_numero + '</div>';
        }
        document.getElementById('dad-info').innerHTML = html;

        var tb = '';
        lignes.forEach(function(l) {
            tb += '<tr>' +
                '<td>' + (l.ar_ref || '') + '</td>' +
                '<td>' + (l.designation || '') + '</td>' +
                '<td>' + fmt.qty(l.qte_demandee) + '</td>' +
                '<td>' + fmt.money(l.prix_unitaire) + '</td>' +
                '</tr>';
        });
        document.getElementById('dad-tbody').innerHTML = tb || '<tr><td colspan="4" class="tbl-empty">Aucune ligne</td></tr>';

        var actions = '';
        if (da.statut === 'SOUMISE' && window.NEXORA_EST_SIEGE) {
            actions = '<button class="btn btn-outline btn-sm" onclick="msiteValiderDA(' + da.id + ',\'refuser\')">❌ Refuser</button> ' +
                      '<button class="btn btn-gold" onclick="msiteValiderDA(' + da.id + ',\'valider\')">✅ Valider</button>';
        } else if (da.statut === 'VALIDEE' && window.NEXORA_EST_SIEGE) {
            actions = '<button class="btn btn-navy" onclick="msiteValiderDA(' + da.id + ',\'commander\')">🛒 Passer commande (BC Sage)</button>';
        }
        document.getElementById('dad-actions').innerHTML = actions;
        ouvrirModal('modal-da-detail');
    });
}

function msiteValiderDA(id, decision) {
    var data = {decision: decision};
    if (decision === 'refuser') {
        var motif = window.prompt('Motif de refus :');
        if (!motif) return;
        data.motif_refus = motif;
    } else if (decision === 'commander') {
        var bc = window.prompt('Numero du bon de commande Sage :');
        if (bc === null) return;
        data.bc_numero = bc;
    }
    apiPost('/api/multisite/demandes-achat/' + id + '/valider', data, function(d) {
        status(d.msg);
        fermerModal('modal-da-detail');
        msiteChargerDA();
    });
}

autoLoad['da-nouvelle'] = function() {
    msiteChargerAgences(function() {
        msiteRemplirSelect('dan-agence');
        msiteRemplirSelect('dan-livraison');
    });
    document.getElementById('dan-lignes-tbody').innerHTML = '';
};

function msiteSoumettreDA() {
    var agence = document.getElementById('dan-agence').value;
    if (!agence) { status('⚠ Choisissez une agence demandeuse'); return; }
    var lignes = msiteLireLignes('dan-lignes-tbody');
    if (!lignes.length) { status('⚠ Ajoutez au moins une ligne'); return; }

    var data = {
        agence_id: agence,
        livraison_agence: document.getElementById('dan-livraison').value || agence,
        fournisseur_code: document.getElementById('dan-fournisseur-code').value,
        fournisseur_nom: document.getElementById('dan-fournisseur-nom').value,
        urgence: document.getElementById('dan-urgence').checked,
        observations: document.getElementById('dan-observations').value,
        lignes: lignes
    };
    apiPost('/api/multisite/demandes-achat', data, function(d) {
        status(d.msg);
        document.getElementById('dan-lignes-tbody').innerHTML = '';
        document.getElementById('dan-observations').value = '';
        document.getElementById('dan-urgence').checked = false;
        document.querySelector('[data-nav=da-liste]').click();
    });
}

window.autoLoad = autoLoad;
msiteChargerDashboard();
