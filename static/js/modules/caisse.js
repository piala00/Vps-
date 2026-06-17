/**
 * NEXORA v2.0 - Module Caisse
 */
var autoLoad = {
    'caisse-saisir':    function(){ initSaisie(); },
    'caisse-historique': function(){ chargerHistoriqueRC(); },
};

function initSaisie() {
    var d = document.getElementById('rc-date');
    if (d && !d.value) {
        var today = new Date();
        d.value = today.toISOString().split('T')[0];
    }
    if (!document.querySelectorAll('.rc-ligne').length) ajouterLigne();
}

function ajouterLigne() {
    var zone = document.getElementById('rc-lignes');
    if (!zone) return;
    var div  = document.createElement('div');
    div.className = 'rc-ligne';
    div.style.cssText = 'display:flex;gap:8px;margin-bottom:8px;align-items:center;flex-wrap:wrap';
    div.innerHTML =
        '<input type="text" placeholder="N° Facture" style="width:130px">' +
        '<input type="text" placeholder="Code client" style="width:120px">' +
        '<input type="text" placeholder="Nom client" style="width:160px">' +
        '<input type="number" placeholder="Montant facture" style="width:130px" step="100">' +
        '<input type="number" placeholder="Montant encaisse" style="width:130px" step="100" onchange="recalculerTotaux()">' +
        '<select style="width:140px">' +
        '<option value="ESPECES">Especes</option><option value="CHEQUE">Cheque</option>' +
        '<option value="VIREMENT">Virement</option><option value="MOBILE_MONEY">Mobile Money</option>' +
        '<option value="CREDIT">Credit</option></select>' +
        '<button onclick="supprimerLigne(this)" style="background:var(--red);color:white;border:none;border-radius:6px;padding:6px 10px;cursor:pointer">X</button>';
    zone.appendChild(div);
}

function supprimerLigne(btn) {
    btn.parentElement.remove();
    recalculerTotaux();
}

function recalculerTotaux() {
    var lignes = document.querySelectorAll('.rc-ligne');
    var totalEnc = 0;
    lignes.forEach(function(l) {
        var inputs = l.querySelectorAll('input[type=number]');
        totalEnc += parseFloat((inputs[1] && inputs[1].value) || 0);
    });
    var enc = document.getElementById('rc-encaisse');
    if (enc) enc.value = totalEnc.toFixed(0);
}

function sauvegarderRC() {
    var date  = document.getElementById('rc-date')       ? document.getElementById('rc-date').value : '';
    var comm  = document.getElementById('rc-commercial') ? document.getElementById('rc-commercial').value.trim() : '';
    if (!date || !comm) { alert('Date et commercial obligatoires'); return; }
    var lignes = [];
    document.querySelectorAll('.rc-ligne').forEach(function(l) {
        var inputs = l.querySelectorAll('input');
        var sel    = l.querySelector('select');
        lignes.push({
            no_facture:      inputs[0] ? inputs[0].value : '',
            code_client:     inputs[1] ? inputs[1].value : '',
            client_nom:      inputs[2] ? inputs[2].value : '',
            montant_facture: parseFloat((inputs[3] && inputs[3].value) || 0),
            montant_encaisse:parseFloat((inputs[4] && inputs[4].value) || 0),
            mode_paiement:   sel ? sel.value : 'ESPECES',
        });
    });
    var data = {
        date_rapport:   date,
        commercial:     comm,
        agence:         'BERTOUA',
        total_ventes:   parseFloat(document.getElementById('rc-ventes')  ? document.getElementById('rc-ventes').value  : 0),
        total_encaisse: parseFloat(document.getElementById('rc-encaisse') ? document.getElementById('rc-encaisse').value : 0),
        total_credit:   parseFloat(document.getElementById('rc-credit')  ? document.getElementById('rc-credit').value  : 0),
        lignes:         lignes,
    };
    apiPost('/api/caisse/rapports', data, function(d) {
        var msg = document.getElementById('rc-msg');
        if (msg) msg.innerHTML = '<span style="color:var(--green)">Rapport enregistre (ID: ' + d.id + ')</span>';
        status('Rapport de caisse cree');
    });
}

function chargerHistoriqueRC() {
    tableLoader('rc-hist-tbody', 6);
    apiGet('/api/caisse/rapports', function(d) {
        var tbody = document.getElementById('rc-hist-tbody');
        if (!tbody) return;
        if (!d.rapports || !d.rapports.length) { tableVide('rc-hist-tbody', 6, 'Aucun rapport'); return; }
        tbody.innerHTML = d.rapports.map(function(r) {
            return '<tr><td>' + fmt.date(r.date_rapport) + '</td><td>' + (r.commercial||'-') + '</td>' +
                   '<td style="color:var(--gold)">' + fmt.money(r.total_ventes||0) + '</td>' +
                   '<td style="color:var(--green)">' + fmt.money(r.total_encaisse||0) + '</td>' +
                   '<td style="color:var(--red)">' + fmt.money(r.total_credit||0) + '</td>' +
                   '<td>' + badge(r.statut||'brouillon','info') + '</td></tr>';
        }).join('');
    });
}

document.addEventListener('DOMContentLoaded', function() { initSaisie(); });
