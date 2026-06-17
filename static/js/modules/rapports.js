/**
 * NEXORA v2.0 - Module Rapports
 */
var autoLoad = {};

function genererRapportCaisse() {
    var mois   = document.getElementById('rpt-mois')   ? document.getElementById('rpt-mois').value   : '';
    var agence = document.getElementById('rpt-agence') ? document.getElementById('rpt-agence').value : 'BERTOUA';
    if (!mois) { alert('Selectionnez un mois'); return; }
    var msg = document.getElementById('rpt-msg');
    if (msg) msg.innerHTML = '<span style="color:var(--muted)">Generation en cours...</span>';
    apiGet('/api/rapports/caisse-excel?mois=' + mois + '&agence=' + agence, function(d) {
        if (msg) msg.innerHTML = d.url ?
            '<span style="color:var(--green)">Rapport genere: <a href="' + d.url + '" target="_blank">Telecharger</a></span>' :
            '<span style="color:var(--green)">Rapport genere</span>';
    }, function(e) {
        if (msg) msg.innerHTML = '<span style="color:var(--red)">Erreur: ' + e + '</span>';
    });
}
