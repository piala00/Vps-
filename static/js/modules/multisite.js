/**
 * NEXORA v2.0 - Module Multi-Sites
 */
var autoLoad = {
    'ms2-stock':      function(){ chargerMS2Stock(); },
    'ms2-transferts': function(){ chargerMS2DTs(); },
    'ms2-achats':     function(){ chargerMS2DAs(); },
};

var _ms2Data = [];

function chargerMS2Stock() {
    var agence = document.getElementById('ms2-agence') ? document.getElementById('ms2-agence').value : 2;
    tableLoader('ms2-tbody', 7);
    apiGet('/api/multisite/stock-disponible?agence_source=' + agence, function(d) {
        if (d.message && !(d.articles||[]).length) {
            tableVide('ms2-tbody', 7, d.message);
            return;
        }
        _ms2Data = d.articles || [];
        filtrerMS2();
    }, function() { tableVide('ms2-tbody', 7, 'Connexion Sage non disponible'); });
}

function filtrerMS2() {
    var q = document.getElementById('ms2-search') ? document.getElementById('ms2-search').value.toLowerCase() : '';
    var filtered = _ms2Data.filter(function(a) {
        return !q || (a.AR_Ref||'').toLowerCase().includes(q) || (a.AR_Design||a.designation||'').toLowerCase().includes(q);
    });
    var tbody = document.getElementById('ms2-tbody');
    if (!tbody) return;
    if (!filtered.length) { tableVide('ms2-tbody', 7, 'Aucun article'); return; }
    tbody.innerHTML = filtered.slice(0,100).map(function(a) {
        var dispo = a.stock_dispo !== undefined ? a.stock_dispo : (a.stock_physique||0)-(a.qte_reservee||0);
        var col   = dispo <= 0 ? '#EF4444' : '#10B981';
        return '<tr><td style="font-weight:700;color:var(--navy)">' + (a.AR_Ref||'-') + '</td>' +
               '<td>' + (a.AR_Design||a.designation||'-') + '</td>' +
               '<td>' + fmt.qty(a.stock_physique||0) + '</td>' +
               '<td style="color:#F97316">' + fmt.qty(a.qte_reservee||0) + '</td>' +
               '<td style="color:#818CF8">' + fmt.qty(a.qte_en_dt||0) + '</td>' +
               '<td style="color:' + col + ';font-weight:700">' + (dispo<=0?'RUPTURE':fmt.qty(dispo)) + '</td>' +
               '<td>' + fmt.money(a.prix_achat||a.AR_PrixAch||0) + '</td></tr>';
    }).join('');
}

function chargerMS2DTs() {
    var statut = document.getElementById('ms2-dt-statut') ? document.getElementById('ms2-dt-statut').value : '';
    apiGet('/api/multisite/transferts' + (statut ? '?statuts=' + statut : ''), function(d) {
        var el = document.getElementById('ms2-dt-liste');
        if (!el) return;
        var dts = d.transferts || [];
        if (!dts.length) { el.innerHTML = '<div class="tbl-empty">Aucune DT</div>'; return; }
        el.innerHTML = dts.map(function(dt) {
            var s = {SOUMISE:badge('En attente','warn'),VALIDEE:badge('Validee','ok'),
                     LIVREE:badge('Livree','ok'),REFUSEE:badge('Refusee','err')}[dt.statut]||badge(dt.statut,'muted');
            var act = dt.statut === 'SOUMISE' ?
                '<button class="btn btn-navy btn-sm" onclick="validerMS2DT(' + dt.id + ')">Valider</button>' : '';
            return '<div class="card" style="margin-bottom:8px"><div style="display:flex;justify-content:space-between">' +
                   '<div><strong>' + dt.numero + '</strong> ' + s +
                   '<div style="font-size:11px;color:var(--muted)">' + (dt.source_nom||'-') + ' -> ' + (dt.dest_nom||'-') + '</div></div>' +
                   '<div>' + act + '</div></div></div>';
        }).join('');
    });
}

function validerMS2DT(id) {
    apiPost('/api/multisite/transferts/' + id + '/valider', {action:'valider'}, function() {
        status('DT validee'); chargerMS2DTs();
    });
}

function chargerMS2DAs() {
    apiGet('/api/multisite/demandes-achat', function(d) {
        var el = document.getElementById('ms2-da-liste');
        if (!el) return;
        var das = d.demandes || [];
        if (!das.length) { el.innerHTML = '<div class="tbl-empty">Aucune DA</div>'; return; }
        el.innerHTML = das.map(function(da) {
            return '<div class="card" style="margin-bottom:8px">' +
                   '<strong>' + da.numero + '</strong> ' + badge(da.statut,'warn') +
                   '<div style="font-size:11px;color:var(--muted)">' + (da.fournisseur_nom||'-') + '</div></div>';
        }).join('');
    });
}

document.addEventListener('DOMContentLoaded', function() { chargerMS2Stock(); });
