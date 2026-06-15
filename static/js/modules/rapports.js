var autoLoad = window.autoLoad || {};

var RPT_RISQUE_TYPES = {CRITIQUE: 'err', ELEVE: 'warn', MOYEN: 'info', FAIBLE: 'muted'};
var RPT_VOYAGE_STATUTS = {planifie: 'info', en_cours: 'warn', termine: 'ok', annule: 'err'};

function rpAfficherExports(type, peutExcel, peutPdf) {
    var btnExcel = document.getElementById('rpt-' + type + '-excel');
    var btnPdf = document.getElementById('rpt-' + type + '-pdf');
    if (btnExcel) btnExcel.style.display = peutExcel ? '' : 'none';
    if (btnPdf) btnPdf.style.display = peutPdf ? '' : 'none';
}

function rpExporter(type, format) {
    var url = '/api/rapports/' + type + '/export?format=' + format;
    if (type === 'commercial') {
        url += '&date_debut=' + document.getElementById('rpt-com-date-debut').value;
        url += '&date_fin=' + document.getElementById('rpt-com-date-fin').value;
    }
    if (type === 'logistique') {
        url += '&date_debut=' + document.getElementById('rpt-log-date-debut').value;
        url += '&date_fin=' + document.getElementById('rpt-log-date-fin').value;
    }
    window.location.href = url;
}

// -- Rapport stock --------------------------------------------------------------------
function rpChargerStock() {
    loadingTable('rpt-stock-tbody', 8);
    apiGet('/api/rapports/stock', function(d) {
        rpAfficherExports('stock', d.peut_excel, d.peut_pdf);
        if (!d.data.length) {
            emptyTable('rpt-stock-tbody', 8, 'Aucune donnee');
            return;
        }
        var html = '';
        d.data.forEach(function(r) {
            html += '<tr>' +
                '<td>' + (r.depot || '—') + '</td>' +
                '<td>' + (r.code_article || '—') + '</td>' +
                '<td>' + (r.designation || '—') + '</td>' +
                '<td>' + (r.famille || '—') + '</td>' +
                '<td>' + fmt.qty(r.stock_actuel) + '</td>' +
                '<td>' + fmt.qty(r.stock_mini) + '</td>' +
                '<td>' + fmt.qty(r.stock_maxi) + '</td>' +
                '<td>' + fmt.money(r.valeur_stock) + '</td>' +
                '</tr>';
        });
        document.getElementById('rpt-stock-tbody').innerHTML = html;
    });
}
autoLoad['rpt-stock'] = function() { rpChargerStock(); };

// -- Rapport commercial ----------------------------------------------------------------
function rpChargerCommercial() {
    loadingTable('rpt-commercial-tbody', 5);
    var dd = document.getElementById('rpt-com-date-debut').value;
    var df = document.getElementById('rpt-com-date-fin').value;
    var parts = [];
    if (dd) parts.push('date_debut=' + dd);
    if (df) parts.push('date_fin=' + df);
    var url = '/api/rapports/commercial' + (parts.length ? ('?' + parts.join('&')) : '');
    apiGet(url, function(d) {
        rpAfficherExports('commercial', d.peut_excel, d.peut_pdf);
        if (!d.data.length) {
            emptyTable('rpt-commercial-tbody', 5, 'Aucune vente');
            return;
        }
        var html = '';
        d.data.forEach(function(v) {
            html += '<tr>' +
                '<td>' + fmt.date(v.date_facture) + '</td>' +
                '<td>' + (v.no_facture || '—') + '</td>' +
                '<td>' + (v.code_client || '—') + '</td>' +
                '<td>' + (v.client_nom || '—') + '</td>' +
                '<td>' + fmt.money(v.montant_ttc) + '</td>' +
                '</tr>';
        });
        document.getElementById('rpt-commercial-tbody').innerHTML = html;
    });
}
autoLoad['rpt-commercial'] = function() {
    if (!document.getElementById('rpt-com-date-debut').value) {
        var debut = new Date();
        debut.setDate(1);
        document.getElementById('rpt-com-date-debut').value = debut.toISOString().substring(0, 10);
    }
    if (!document.getElementById('rpt-com-date-fin').value) {
        document.getElementById('rpt-com-date-fin').value = new Date().toISOString().substring(0, 10);
    }
    rpChargerCommercial();
};

// -- Rapport comptable ------------------------------------------------------------------
function rpChargerComptable() {
    loadingTable('rpt-comptable-tbody', 4);
    apiGet('/api/rapports/comptable', function(d) {
        rpAfficherExports('comptable', d.peut_excel, d.peut_pdf);
        if (!d.data.length) {
            emptyTable('rpt-comptable-tbody', 4, 'Aucune creance');
            return;
        }
        var html = '';
        d.data.forEach(function(c) {
            html += '<tr>' +
                '<td>' + (c.code_client || '—') + '</td>' +
                '<td>' + (c.nom || '—') + '</td>' +
                '<td>' + fmt.money(c.solde) + '</td>' +
                '<td>' + badge(c.niveau_risque, RPT_RISQUE_TYPES[c.niveau_risque] || 'info') + '</td>' +
                '</tr>';
        });
        document.getElementById('rpt-comptable-tbody').innerHTML = html;
    });
}
autoLoad['rpt-comptable'] = function() { rpChargerComptable(); };

// -- Rapport logistique -----------------------------------------------------------------
function rpChargerLogistique() {
    loadingTable('rpt-logistique-tbody', 8);
    var dd = document.getElementById('rpt-log-date-debut').value;
    var df = document.getElementById('rpt-log-date-fin').value;
    var parts = [];
    if (dd) parts.push('date_debut=' + dd);
    if (df) parts.push('date_fin=' + df);
    var url = '/api/rapports/logistique' + (parts.length ? ('?' + parts.join('&')) : '');
    apiGet(url, function(d) {
        rpAfficherExports('logistique', d.peut_excel, d.peut_pdf);
        if (!d.data.length) {
            emptyTable('rpt-logistique-tbody', 8, 'Aucun voyage');
            return;
        }
        var html = '';
        d.data.forEach(function(v) {
            html += '<tr>' +
                '<td>' + (v.no_voyage || '—') + '</td>' +
                '<td>' + (v.camion_immat || '—') + '</td>' +
                '<td>' + (v.chauffeur_nom || '—') + '</td>' +
                '<td>' + (v.origine || '—') + '</td>' +
                '<td>' + (v.destination || '—') + '</td>' +
                '<td>' + fmt.date(v.date_depart) + '</td>' +
                '<td>' + fmt.date(v.date_retour) + '</td>' +
                '<td>' + badge(v.statut, RPT_VOYAGE_STATUTS[v.statut] || 'info') + '</td>' +
                '</tr>';
        });
        document.getElementById('rpt-logistique-tbody').innerHTML = html;
    });
}
autoLoad['rpt-logistique'] = function() {
    if (!document.getElementById('rpt-log-date-debut').value) {
        var debut = new Date();
        debut.setDate(debut.getDate() - 30);
        document.getElementById('rpt-log-date-debut').value = debut.toISOString().substring(0, 10);
    }
    if (!document.getElementById('rpt-log-date-fin').value) {
        document.getElementById('rpt-log-date-fin').value = new Date().toISOString().substring(0, 10);
    }
    rpChargerLogistique();
};

window.autoLoad = autoLoad;

rpChargerStock();
