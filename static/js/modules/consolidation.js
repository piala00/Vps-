/**
 * NEXORA v2.0 - Module Consolidation
 */
var autoLoad = {
    'cons-global': function(){ chargerCons(); },
    'cons-stock':  function(){},
};

function chargerCons() {
    var periode = document.getElementById('cons-periode') ? document.getElementById('cons-periode').value : 'mois';
    tableLoader('cons-tbody', 4);
    apiGet('/api/consolidation/dashboard?periode=' + periode, function(d) {
        if (d.message && !d.total_ca) {
            var kpis0 = document.getElementById('cons-kpis');
            if (kpis0) kpis0.innerHTML = '<div class="alert alert-warn" style="grid-column:1/-1">⚠️ ' + d.message + '</div>';
            tableVide('cons-tbody', 4, 'Sage non disponible');
            return;
        }
        var kpis = document.getElementById('cons-kpis');
        if (kpis) kpis.innerHTML = kpiCard('💰', 'CA Total Reseau', fmt.money(d.total_ca||0), '#FBC013');
        var tbody = document.getElementById('cons-tbody');
        if (!tbody) return;
        var total = d.total_ca || 1;
        tbody.innerHTML = (d.agences||[]).map(function(a) {
            var pct = ((a.ca_mois||0)/total*100).toFixed(1);
            return '<tr><td style="font-weight:600">' + a.agence + '</td>' +
                   '<td style="color:var(--gold);font-weight:700">' + fmt.money(a.ca_mois||0) + '</td>' +
                   '<td>' + (a.nb_factures||0) + '</td><td>' + pct + '%</td></tr>';
        }).join('') || '<tr><td colspan="4" class="tbl-empty">Aucune donnee</td></tr>';
    }, function() {
        tableVide('cons-tbody', 4, 'Connexion Sage non disponible');
    });
}

function rechercherStockReseau() {
    var q = document.getElementById('cons-stock-q') ? document.getElementById('cons-stock-q').value : '';
    apiGet('/api/multisite/stock-disponible?q=' + encodeURIComponent(q), function(d) {
        var el = document.getElementById('cons-stock-result');
        if (!el) return;
        var arts = (d.articles||[]).filter(function(a){ return a.stock_dispo > 0; });
        if (!arts.length) { el.innerHTML = '<div class="tbl-empty">Aucun stock disponible</div>'; return; }
        el.innerHTML = '<div class="tbl-wrap"><table><thead><tr><th>Reference</th><th>Designation</th><th>Disponible</th></tr></thead><tbody>' +
            arts.map(function(a){
                return '<tr><td style="font-weight:700">' + a.AR_Ref + '</td><td>' + (a.AR_Design||a.designation||'-') + '</td><td style="color:var(--green);font-weight:700">' + fmt.qty(a.stock_dispo) + '</td></tr>';
            }).join('') + '</tbody></table></div>';
    });
}

document.addEventListener('DOMContentLoaded', function() { chargerCons(); });
