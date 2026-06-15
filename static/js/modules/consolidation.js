var autoLoad = window.autoLoad || {};

// -- Vue globale reseau --------------------------------------------------------------
function conChargerDashboard() {
    loadingTable('con-tbody', 7);
    var granularite = document.getElementById('con-granularite').value;
    apiGet('/api/consolidation/dashboard?granularite=' + granularite, function(d) {
        document.getElementById('kpi-ca-total').textContent = fmt.money(d.ca_total);
        document.getElementById('kpi-ca-total-n1').textContent = fmt.money(d.ca_total_n1);
        document.getElementById('kpi-variation').textContent =
            (d.variation_pct >= 0 ? '+' : '') + fmt.pct(d.variation_pct);

        if (!d.data.length) {
            emptyTable('con-tbody', 7, 'Aucune donnee');
            return;
        }
        var html = '';
        d.data.forEach(function(a) {
            var variationTxt = (a.variation_pct >= 0 ? '+' : '') + fmt.pct(a.variation_pct);
            var variationBadge = a.ca_n1 > 0
                ? badge(variationTxt, a.variation_pct >= 0 ? 'ok' : 'err')
                : '—';
            html += '<tr>' +
                '<td>' + a.nom + '</td>' +
                '<td>' + (a.ville || '—') + '</td>' +
                '<td>' + a.type_site + '</td>' +
                '<td>' + fmt.money(a.ca) + '</td>' +
                '<td>' + fmt.money(a.ca_n1) + '</td>' +
                '<td>' + variationBadge + '</td>' +
                '<td>' + fmt.pct(a.pct_contribution) + '</td>' +
                '</tr>';
        });
        document.getElementById('con-tbody').innerHTML = html;
    });
}
autoLoad['consolidation-dashboard'] = function() { conChargerDashboard(); };

window.autoLoad = autoLoad;

conChargerDashboard();
