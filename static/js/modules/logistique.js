/**
 * NEXORA v2.0 - Module Logistique
 */
var autoLoad = {
    'log-dashboard':    function(){ chargerDashLog(); },
    'log-camions':      function(){ chargerCamions(); },
    'log-personnel':    function(){ chargerPersonnel(); },
    'log-voyages':      function(){ chargerVoyages(); },
    'log-entretiens':   function(){ chargerEntretiens(); },
    'log-transactions': function(){ chargerTransactions(); chargerCamionsPourSelect(); },
};

function chargerDashLog() {
    apiGet('/api/logistique/camions', function(d) {
        var kpis = document.getElementById('lk-kpis');
        if (kpis) kpis.innerHTML =
            kpiCard('🚛', 'Camions actifs', (d.camions||[]).length, '#1A3263') +
            kpiCard('📅', 'Voyages du jour', 0, '#10B981') +
            kpiCard('🔧', 'En entretien', 0, '#F59E0B') +
            kpiCard('⛽', 'Cout carburant (mois)', fmt.money(0), '#EF4444');
    });
}

function chargerCamions() {
    tableLoader('camions-tbody', 5);
    apiGet('/api/logistique/camions', function(d) {
        var tbody = document.getElementById('camions-tbody');
        if (!tbody) return;
        if (!d.camions || !d.camions.length) { tableVide('camions-tbody', 5, 'Aucun camion'); return; }
        tbody.innerHTML = d.camions.map(function(c) {
            return '<tr><td style="font-weight:700;color:var(--navy)">' + c.immatriculation + '</td>' +
                   '<td>' + (c.marque||'-') + '</td><td>' + (c.modele||'-') + '</td>' +
                   '<td>' + badge(c.type_flotte,'info') + '</td><td>' + (c.capacite_tonnes||0) + ' t</td></tr>';
        }).join('');
    });
}

function chargerPersonnel() {
    tableLoader('personnel-tbody', 5);
    apiGet('/api/logistique/personnel', function(d) {
        var tbody = document.getElementById('personnel-tbody');
        if (!tbody) return;
        if (!d.personnel || !d.personnel.length) { tableVide('personnel-tbody', 5, 'Aucun personnel'); return; }
        tbody.innerHTML = d.personnel.map(function(p) {
            return '<tr><td style="font-weight:700">' + (p.prenom?p.prenom+' ':'') + p.nom + '</td>' +
                   '<td>' + badge(p.role, p.role==='CHAUFFEUR'?'navy':'info') + '</td>' +
                   '<td>' + (p.telephone||'-') + '</td><td>' + (p.permis||'-') + '</td>' +
                   '<td>' + (p.immatriculation||'-') + '</td></tr>';
        }).join('');
    });
}

function chargerVoyages() {
    tableLoader('voyages-tbody', 6);
    apiGet('/api/logistique/voyages', function(d) {
        var tbody = document.getElementById('voyages-tbody');
        if (!tbody) return;
        if (!d.voyages || !d.voyages.length) { tableVide('voyages-tbody', 6, 'Aucun voyage'); return; }
        tbody.innerHTML = d.voyages.map(function(v) {
            var s = {planifie:badge('Planifie','info'), en_cours:badge('En cours','warn'),
                     termine:badge('Termine','ok'), annule:badge('Annule','muted')}[v.statut] || badge(v.statut,'muted');
            return '<tr><td style="font-weight:700;color:var(--navy)">' + (v.no_voyage||'-') + '</td>' +
                   '<td>' + (v.immatriculation||'-') + '</td>' +
                   '<td>' + (v.origine||'-') + '</td><td>' + (v.destination||'-') + '</td>' +
                   '<td>' + fmt.date(v.date_depart) + '</td><td>' + s + '</td></tr>';
        }).join('');
    });
}

function chargerEntretiens() {
    tableLoader('entretiens-tbody', 6);
    apiGet('/api/logistique/entretiens', function(d) {
        var tbody = document.getElementById('entretiens-tbody');
        if (!tbody) return;
        if (!d.entretiens || !d.entretiens.length) { tableVide('entretiens-tbody', 6, 'Aucun entretien'); return; }
        tbody.innerHTML = d.entretiens.map(function(e) {
            return '<tr><td>' + (e.immatriculation||'-') + '</td>' +
                   '<td>' + badge(e.type_entretien,'info') + '</td>' +
                   '<td>' + fmt.date(e.date_entretien) + '</td>' +
                   '<td>' + (e.kilometrage||0) + ' km</td>' +
                   '<td style="font-weight:700;color:var(--gold)">' + fmt.money(e.cout||0) + '</td>' +
                   '<td>' + (e.prochaine_revision?fmt.date(e.prochaine_revision):'-') + '</td></tr>';
        }).join('');
    });
}

function chargerTransactions() {
    var camion = document.getElementById('tx-camion-sel') ? document.getElementById('tx-camion-sel').value : '';
    tableLoader('tx-tbody', 6);
    apiGet('/api/logistique/transactions' + (camion?'?camion_id='+camion:''), function(d) {
        var tbody = document.getElementById('tx-tbody');
        if (!tbody) return;
        if (!d.transactions || !d.transactions.length) { tableVide('tx-tbody', 6, 'Aucune transaction'); return; }
        tbody.innerHTML = d.transactions.map(function(t) {
            var col = t.type_transaction === 'RECETTE' ? 'var(--green)' : 'var(--red)';
            return '<tr><td>' + fmt.date(t.date_transaction) + '</td>' +
                   '<td>' + (t.immatriculation||'-') + '</td>' +
                   '<td>' + badge(t.type_transaction, t.type_transaction==='RECETTE'?'ok':'err') + '</td>' +
                   '<td>' + (t.categorie||'-') + '</td>' +
                   '<td style="font-weight:700;color:' + col + '">' + fmt.money(t.montant||0) + '</td>' +
                   '<td>' + (t.libelle||'-') + '</td></tr>';
        }).join('');
    });
}

function chargerCamionsPourSelect() {
    var sel = document.getElementById('tx-camion-sel');
    if (!sel) return;
    apiGet('/api/logistique/camions', function(d) {
        sel.innerHTML = '<option value="">Tous les camions</option>';
        (d.camions||[]).forEach(function(c) {
            var opt = document.createElement('option');
            opt.value = c.id;
            opt.textContent = c.immatriculation + (c.marque ? ' - '+c.marque : '');
            sel.appendChild(opt);
        });
    });
}

document.addEventListener('DOMContentLoaded', function() { chargerDashLog(); });

// ── Creation Camion ──────────────────────────────────────────────
function creerCamion() {
    var immat = document.getElementById('cam-immat') ? document.getElementById('cam-immat').value.trim() : '';
    if (!immat) { alert('Immatriculation obligatoire'); return; }
    var data = {
        immatriculation:    immat,
        marque:              document.getElementById('cam-marque')   ? document.getElementById('cam-marque').value   : '',
        modele:               document.getElementById('cam-modele')   ? document.getElementById('cam-modele').value   : '',
        type_flotte:          document.getElementById('cam-type')     ? document.getElementById('cam-type').value     : 'MAISON',
        proprietaire:         document.getElementById('cam-proprio')  ? document.getElementById('cam-proprio').value  : '',
        compte_sage:          document.getElementById('cam-sage')     ? document.getElementById('cam-sage').value     : '',
        capacite_tonnes:      document.getElementById('cam-capacite') ? parseFloat(document.getElementById('cam-capacite').value) || 0 : 0,
        observations:         document.getElementById('cam-obs')      ? document.getElementById('cam-obs').value      : '',
    };
    var msg = document.getElementById('cam-msg');
    apiPost('/api/logistique/camions', data, function() {
        fermerModal('modal-camion');
        chargerCamions();
        status('Camion enregistre: ' + immat);
        if (msg) msg.innerHTML = '';
        var inputs = ['cam-immat','cam-marque','cam-modele','cam-proprio','cam-sage','cam-capacite','cam-obs'];
        inputs.forEach(function(id){ var el=document.getElementById(id); if(el) el.value=''; });
    }, function(e) {
        if (msg) msg.innerHTML = '<span style="color:var(--red)">Erreur: ' + e + '</span>';
    });
}

// ── Creation Personnel ───────────────────────────────────────────
function peuplerSelectCamions(selectIds) {
    apiGet('/api/logistique/camions', function(d) {
        var camions = d.camions || [];
        selectIds.forEach(function(sid) {
            var sel = document.getElementById(sid);
            if (!sel) return;
            var current = sel.value;
            sel.innerHTML = '<option value="">-- Choisir --</option>';
            camions.forEach(function(c) {
                var opt = document.createElement('option');
                opt.value = c.id;
                opt.textContent = c.immatriculation + (c.marque ? ' - ' + c.marque : '');
                sel.appendChild(opt);
            });
            sel.value = current;
        });
    });
}

function peuplerSelectPersonnel(selectIds) {
    apiGet('/api/logistique/personnel', function(d) {
        var personnel = d.personnel || [];
        selectIds.forEach(function(sid) {
            var sel = document.getElementById(sid);
            if (!sel) return;
            var current = sel.value;
            sel.innerHTML = '<option value="">-- Choisir --</option>';
            personnel.forEach(function(p) {
                var opt = document.createElement('option');
                opt.value = p.id;
                opt.textContent = (p.prenom ? p.prenom + ' ' : '') + p.nom + ' (' + p.role + ')';
                sel.appendChild(opt);
            });
            sel.value = current;
        });
    });
}

function ouvrirModalPersonnel() {
    peuplerSelectCamions(['per-camion']);
    ouvrirModal('modal-personnel');
}

function creerPersonnel() {
    var nom = document.getElementById('per-nom') ? document.getElementById('per-nom').value.trim() : '';
    if (!nom) { alert('Nom obligatoire'); return; }
    var data = {
        nom: nom,
        prenom:    document.getElementById('per-prenom') ? document.getElementById('per-prenom').value : '',
        role:      document.getElementById('per-role')   ? document.getElementById('per-role').value   : 'CHAUFFEUR',
        telephone: document.getElementById('per-tel')     ? document.getElementById('per-tel').value     : '',
        permis:    document.getElementById('per-permis')  ? document.getElementById('per-permis').value  : '',
        camion_id: document.getElementById('per-camion')  ? (document.getElementById('per-camion').value || null) : null,
    };
    var msg = document.getElementById('per-msg');
    apiPost('/api/logistique/personnel', data, function() {
        fermerModal('modal-personnel');
        chargerPersonnel();
        status('Personnel enregistre: ' + nom);
        if (msg) msg.innerHTML = '';
        ['per-nom','per-prenom','per-tel','per-permis'].forEach(function(id){ var el=document.getElementById(id); if(el) el.value=''; });
    }, function(e) {
        if (msg) msg.innerHTML = '<span style="color:var(--red)">Erreur: ' + e + '</span>';
    });
}

// ── Creation Voyage ───────────────────────────────────────────────
function ouvrirModalVoyage() {
    peuplerSelectCamions(['voy-camion']);
    peuplerSelectPersonnel(['voy-chauffeur','voy-convoyeur']);
    ouvrirModal('modal-voyage');
}

function creerVoyage() {
    var camion = document.getElementById('voy-camion') ? document.getElementById('voy-camion').value : '';
    var origine = document.getElementById('voy-origine') ? document.getElementById('voy-origine').value.trim() : '';
    var dest = document.getElementById('voy-destination') ? document.getElementById('voy-destination').value.trim() : '';
    if (!camion) { alert('Camion obligatoire'); return; }
    if (!origine || !dest) { alert('Origine et destination obligatoires'); return; }
    var data = {
        camion_id:          camion,
        chauffeur_id:        document.getElementById('voy-chauffeur')   ? (document.getElementById('voy-chauffeur').value || null) : null,
        convoyeur_id:         document.getElementById('voy-convoyeur')   ? (document.getElementById('voy-convoyeur').value || null) : null,
        origine:              origine,
        destination:          dest,
        date_depart:          document.getElementById('voy-depart')     ? document.getElementById('voy-depart').value     : '',
        date_retour:          document.getElementById('voy-retour')     ? document.getElementById('voy-retour').value     : '',
        statut:               document.getElementById('voy-statut')     ? document.getElementById('voy-statut').value     : 'planifie',
        marchandises:         document.getElementById('voy-marchandises') ? document.getElementById('voy-marchandises').value : '',
        client_fournisseur:  document.getElementById('voy-client')      ? document.getElementById('voy-client').value      : '',
        observations:         document.getElementById('voy-obs')        ? document.getElementById('voy-obs').value        : '',
    };
    var msg = document.getElementById('voy-msg');
    apiPost('/api/logistique/voyages', data, function(d) {
        fermerModal('modal-voyage');
        chargerVoyages();
        status('Voyage cree: ' + (d.no_voyage || ''));
        if (msg) msg.innerHTML = '';
    }, function(e) {
        if (msg) msg.innerHTML = '<span style="color:var(--red)">Erreur: ' + e + '</span>';
    });
}

// ── Creation Entretien ───────────────────────────────────────────
function ouvrirModalEntretien() {
    peuplerSelectCamions(['ent-camion']);
    ouvrirModal('modal-entretien');
}

function creerEntretien() {
    var camion = document.getElementById('ent-camion') ? document.getElementById('ent-camion').value : '';
    if (!camion) { alert('Camion obligatoire'); return; }
    var data = {
        camion_id:          camion,
        type_entretien:      document.getElementById('ent-type')        ? document.getElementById('ent-type').value        : 'AUTRE',
        date_entretien:      document.getElementById('ent-date')        ? document.getElementById('ent-date').value        : '',
        kilometrage:          document.getElementById('ent-km')          ? parseInt(document.getElementById('ent-km').value) || 0 : 0,
        cout:                 document.getElementById('ent-cout')        ? parseFloat(document.getElementById('ent-cout').value) || 0 : 0,
        prestataire:          document.getElementById('ent-prestataire') ? document.getElementById('ent-prestataire').value : '',
        description:          document.getElementById('ent-description') ? document.getElementById('ent-description').value : '',
        prochaine_revision:  document.getElementById('ent-prochaine')   ? document.getElementById('ent-prochaine').value   : '',
    };
    var msg = document.getElementById('ent-msg');
    apiPost('/api/logistique/entretiens', data, function() {
        fermerModal('modal-entretien');
        chargerEntretiens();
        status('Entretien enregistre');
        if (msg) msg.innerHTML = '';
    }, function(e) {
        if (msg) msg.innerHTML = '<span style="color:var(--red)">Erreur: ' + e + '</span>';
    });
}

// ── Creation Transaction ─────────────────────────────────────────
function ouvrirModalTransaction() {
    peuplerSelectCamions(['tx-camion']);
    ouvrirModal('modal-transaction');
}

function creerTransaction() {
    var camion = document.getElementById('tx-camion') ? document.getElementById('tx-camion').value : '';
    if (!camion) { alert('Camion obligatoire'); return; }
    var data = {
        camion_id:           camion,
        type_transaction:    document.getElementById('tx-type')      ? document.getElementById('tx-type').value      : 'DEPENSE',
        categorie:            document.getElementById('tx-categorie') ? document.getElementById('tx-categorie').value : 'AUTRE',
        date_transaction:     document.getElementById('tx-date')      ? document.getElementById('tx-date').value      : '',
        montant:              document.getElementById('tx-montant')   ? parseFloat(document.getElementById('tx-montant').value) || 0 : 0,
        libelle:               document.getElementById('tx-libelle')   ? document.getElementById('tx-libelle').value   : '',
    };
    var msg = document.getElementById('tx-msg');
    apiPost('/api/logistique/transactions', data, function() {
        fermerModal('modal-transaction');
        chargerTransactions();
        status('Transaction enregistree');
        if (msg) msg.innerHTML = '';
    }, function(e) {
        if (msg) msg.innerHTML = '<span style="color:var(--red)">Erreur: ' + e + '</span>';
    });
}
