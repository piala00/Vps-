/**
 * NEXORA v2.0 — Module Stock & Inventaire
 * Utilise le composant NexoraPeriodSelector universel
 */

var autoLoad = {
    'sk-dashboard':    function(){ chargerDashboardStock(); },
    'sk-top':          function(){ initTopSelector(); },
    'sk-dormants':     function(){ initDormantsSelector(); },
    'sk-valorisation': function(){ initValSelector(); },
    'sk-consolide':    function(){ chargerConsolide(); },
    'sk-ms-stock':     function(){ chargerMSStock(); },
    'sk-ms-dt':        function(){ chargerDTs(); },
    'sk-ms-da':        function(){ chargerDAs(); },
    'sk-historique':   function(){ chargerHistorique(); },
    'sk-non-reg':      function(){ chargerNonReg(); },
};

var _msData      = [];
var _consData    = [];
var _topSelector = null;
var _dormSelector = null;
var _valSelector  = null;

// ── Dashboard ──────────────────────────────────────────────────

function chargerDashboardStock() {
    var kpis = document.getElementById('sk-kpis');
    if (kpis) kpis.innerHTML = '<div class="tbl-empty"><span class="loader"></span> Chargement...</div>';
    apiGet('/api/stock/dashboard', function(d) {
        if (!d.nb_articles && d.message) {
            if (kpis) kpis.innerHTML = '<div class="alert alert-warn" style="grid-column:1/-1">⚠️ ' + d.message +
                '. Verifiez la connexion Sage dans Parametres &gt; Connexion Sage.</div>';
            var al0 = document.getElementById('sk-alertes');
            if (al0) al0.innerHTML = '<div class="tbl-empty">Aucune donnee disponible</div>';
            return;
        }
        if (kpis) {
            kpis.innerHTML =
                kpiCard('⚠️', 'Ruptures de stock', d.ruptures || 0, '#EF4444') +
                kpiCard('💤', 'Docs non régularisés', d.dormants || 0, '#F59E0B') +
                kpiCard('📦', 'Mouvements aujourd\'hui', d.mouvements_jour || 0, '#10B981') +
                kpiCard('💰', 'Valeur stock total', fmt.money(d.valeur_stock || 0), '#1A3263') +
                kpiCard('📋', 'Total articles', d.nb_articles || 0, '#3B82F6');
        }
        var al = document.getElementById('sk-alertes');
        if (al) {
            if (!d.alertes || !d.alertes.length) {
                al.innerHTML = '<div class="tbl-empty" style="color:#10B981">Aucune alerte — tout est normal</div>';
            } else {
                al.innerHTML = d.alertes.map(function(a) {
                    var col  = a.niveau === 'danger' ? '#EF4444' : '#F59E0B';
                    var ico  = a.ico === 'ERR' ? '❌' : '⚠️';
                    return '<div style="display:flex;gap:10px;padding:8px 0;' +
                           'border-bottom:1px solid var(--border);align-items:center">' +
                           '<span style="color:' + col + ';font-size:16px">' + ico + '</span>' +
                           '<span style="font-size:12px">' + a.message + '</span></div>';
                }).join('');
            }
        }
    });
}

// ── BL Sage ────────────────────────────────────────────────────

function chargerBL() {
    var no  = document.getElementById('bl-numero') ? document.getElementById('bl-numero').value.trim() : '';
    var msg = document.getElementById('bl-msg');
    if (!no) { alert('Saisissez un numéro de BL'); return; }
    if (msg) msg.innerHTML = '<span style="color:var(--muted)"><span class="loader"></span> Recherche dans Sage...</span>';

    apiPost('/api/stock/reconstituer-bl', {no_bl: no}, function(d) {
        var zone  = document.getElementById('bl-zone');
        var tbody = document.getElementById('bl-tbody');
        var sbadge = document.getElementById('bl-source-badge');
        if (msg) msg.innerHTML = '';
        if (zone) zone.style.display = 'block';
        if (sbadge) {
            sbadge.textContent = d.source === 'cache' ? 'Cache local' : 'Sage live';
            sbadge.className   = d.source === 'cache' ? 'badge b-warn' : 'badge b-ok';
        }
        var clientInfo = document.getElementById('bl-client-info');
        if (clientInfo && d.lignes && d.lignes.length) {
            var l0 = d.lignes[0];
            var infoTxt = [];
            if (l0.client_nom) infoTxt.push('Client: ' + l0.client_nom + (l0.code_client?' ('+l0.code_client+')':''));
            if (l0.no_facture && l0.no_facture !== no) infoTxt.push('Facture: ' + l0.no_facture);
            if (l0.depot) infoTxt.push('Dépôt: ' + l0.depot);
            clientInfo.textContent = infoTxt.join(' · ');
        } else if (clientInfo) { clientInfo.textContent = ''; }
        if (!d.lignes || !d.lignes.length) {
            if (tbody) tbody.innerHTML = '<tr><td colspan="6" class="tbl-empty">BL non trouvé dans Sage</td></tr>';
            return;
        }
        if (tbody) {
            tbody.innerHTML = d.lignes.map(function(l, i) {
                var ref = l.code_article || l.AR_Ref || l.ar_ref || '';
                var des = l.designation || l.DL_Design || '';
                var qte = parseFloat(l.quantite !== undefined ? l.quantite : (l.DL_Qte || l.qte_doc_sage || 0));
                return '<tr>' +
                       '<td style="font-weight:700;color:var(--navy)">' + ref + '</td>' +
                       '<td>' + des + '</td>' +
                       '<td style="font-weight:600">' + fmt.qty(qte) + '</td>' +
                       '<td><input type="number" id="bl-qte-' + i + '" value="' + qte + '"' +
                       ' step="0.01" style="width:110px;padding:5px 8px;border:2px solid var(--border);' +
                       'border-radius:6px;font-size:12px" data-sage="' + qte + '"' +
                       ' data-ref="' + ref + '" data-des="' + des.replace(/"/g,"'") + '"' +
                       ' onchange="majEcart(' + i + ')"></td>' +
                       '<td id="bl-ecart-' + i + '" style="font-weight:700">0.00</td>' +
                       '<td id="bl-etat-' + i + '">' + badge('OK', 'ok') + '</td>' +
                       '</tr>';
            }).join('');
        }
    }, function(e) {
        if (msg) msg.innerHTML = '<span style="color:var(--red)">Erreur: ' + e + '</span>';
    });
}

function majEcart(i) {
    var inp   = document.getElementById('bl-qte-' + i);
    var ecEl  = document.getElementById('bl-ecart-' + i);
    var etEl  = document.getElementById('bl-etat-' + i);
    if (!inp || !ecEl) return;
    var qte_sage   = parseFloat(inp.getAttribute('data-sage')) || 0;
    var qte_saisie = parseFloat(inp.value) || 0;
    var ecart      = qte_sage - qte_saisie;
    ecEl.textContent   = fmt.qty(ecart);
    ecEl.style.color   = Math.abs(ecart) < 0.01 ? '#10B981' : '#EF4444';
    if (etEl) etEl.innerHTML = Math.abs(ecart) < 0.01 ? badge('OK','ok') : badge('Écart','err');
}

function validerBL() {
    var no    = document.getElementById('bl-numero') ? document.getElementById('bl-numero').value.trim() : '';
    var tbody = document.getElementById('bl-tbody');
    if (!tbody) return;
    var rows   = tbody.querySelectorAll('tr');
    var lignes = [];
    rows.forEach(function(row, i) {
        var inp = document.getElementById('bl-qte-' + i);
        if (!inp) return;
        lignes.push({
            no_bl:        no,
            ar_ref:       inp.getAttribute('data-ref') || '',
            designation:  inp.getAttribute('data-des') || '',
            qte_doc_sage: parseFloat(inp.getAttribute('data-sage')) || 0,
            qte_saisie:   parseFloat(inp.value) || 0,
            date_mvt:     new Date().toISOString().split('T')[0],
        });
    });
    if (!lignes.length) { alert('Aucune ligne à valider'); return; }
    var msg = document.getElementById('bl-validation-msg');
    if (msg) msg.innerHTML = '<span style="color:var(--muted)">Validation en cours...</span>';
    apiPost('/api/stock/valider-bl', {lignes: lignes}, function(d) {
        var texte = 'BL validé — ' + d.nb + ' ligne(s) | ' +
                    d.nb_valide + ' OK | ' + d.nb_ecart + ' avec écart';
        if (msg) msg.innerHTML = '<span style="color:#10B981">' + texte + '</span>';
        status(texte);
        chargerDashboardStock();
    }, function(e) {
        if (msg) msg.innerHTML = '<span style="color:var(--red)">Erreur: ' + e + '</span>';
    });
}

function reinitBL() {
    var numEl = document.getElementById('bl-numero');
    var zone  = document.getElementById('bl-zone');
    var msg   = document.getElementById('bl-msg');
    if (numEl) numEl.value = '';
    if (zone)  zone.style.display = 'none';
    if (msg)   msg.innerHTML = '';
}

// ── Bordereau Manuel ───────────────────────────────────────────

function saisirManuel() {
    var code = document.getElementById('man-ref') ? document.getElementById('man-ref').value.trim() : '';
    var qte  = parseFloat(document.getElementById('man-qte') ? document.getElementById('man-qte').value : 0);
    if (!code) { alert('Code article obligatoire'); return; }
    if (!qte || qte <= 0) { alert('Quantité doit être > 0'); return; }
    var data = {
        code_article:  code,
        designation:   document.getElementById('man-design')     ? document.getElementById('man-design').value     : '',
        qte_saisie:    qte,
        code_client:   document.getElementById('man-client')     ? document.getElementById('man-client').value     : '',
        client_nom:    document.getElementById('man-client-nom') ? document.getElementById('man-client-nom').value : '',
        date_mvt:      document.getElementById('man-date')       ? document.getElementById('man-date').value       : '',
    };
    apiPost('/api/stock/saisir-manuel', data, function(d) {
        var msg = document.getElementById('man-msg');
        if (msg) msg.innerHTML = '<span style="color:#10B981">Enregistré: ' + d.no_manuel + '</span>';
        status('Bordereau manuel créé: ' + d.no_manuel);
        ['man-ref','man-design','man-qte','man-client','man-client-nom'].forEach(function(id) {
            var el = document.getElementById(id); if(el) el.value = '';
        });
        chargerDashboardStock();
    }, function(e) {
        var msg = document.getElementById('man-msg');
        if (msg) msg.innerHTML = '<span style="color:var(--red)">Erreur: ' + e + '</span>';
    });
}

// ── Historique ─────────────────────────────────────────────────

function chargerHistorique() {
    var type   = document.getElementById('hist-type')   ? document.getElementById('hist-type').value   : '';
    var statut = document.getElementById('hist-statut') ? document.getElementById('hist-statut').value : '';
    var limite = document.getElementById('hist-limite') ? document.getElementById('hist-limite').value : 100;
    tableLoader('hist-tbody', 8);
    apiGet('/api/stock/historique?type=' + type + '&statut=' + statut + '&limite=' + limite, function(d) {
        var tbody = document.getElementById('hist-tbody');
        if (!tbody) return;
        if (!d.mouvements || !d.mouvements.length) {
            tableVide('hist-tbody', 8, 'Aucun mouvement');
            return;
        }
        tbody.innerHTML = d.mouvements.map(function(m) {
            var sBadge = {
                'valide':     badge('Validé','ok'),
                'ecart':      badge('Écart','err'),
                'en_attente': badge('En attente','warn'),
            }[m.statut] || badge(m.statut || '-', 'muted');
            return '<tr>' +
                   '<td>' + fmt.date(m.cree_le) + '</td>' +
                   '<td>' + badge(m.type_mouvement, m.type_mouvement === 'BL_SAGE' ? 'navy' : 'warn') + '</td>' +
                   '<td style="font-family:monospace">' + (m.no_doc_sage || m.no_doc_manuel || '-') + '</td>' +
                   '<td style="font-weight:700;color:var(--navy)">' + (m.code_article || '-') + '</td>' +
                   '<td>' + fmt.qty(m.qte_saisie || 0) + '</td>' +
                   '<td style="color:' + (Math.abs(m.ecart||0) > 0.01 ? '#EF4444' : '#10B981') + '">' +
                   fmt.qty(m.ecart || 0) + '</td>' +
                   '<td>' + sBadge + '</td>' +
                   '<td style="font-size:11px;color:var(--muted)">' + (m.saisi_par || '-') + '</td>' +
                   '</tr>';
        }).join('');
    });
}

// ── Non Régularisés ────────────────────────────────────────────

function chargerNonReg() {
    tableLoader('nonreg-tbody', 6);
    apiGet('/api/stock/docs-non-regularises', function(d) {
        var tbody = document.getElementById('nonreg-tbody');
        if (!tbody) return;
        if (!d.documents || !d.documents.length) {
            tableVide('nonreg-tbody', 6, 'Aucun bordereau en attente de régularisation');
            return;
        }
        tbody.innerHTML = d.documents.map(function(m) {
            return '<tr>' +
                   '<td style="font-family:monospace;font-weight:700">' + (m.no_doc_manuel || '-') + '</td>' +
                   '<td style="color:var(--navy)">' + (m.code_article || '-') + '</td>' +
                   '<td>' + fmt.qty(m.qte_saisie || 0) + '</td>' +
                   '<td>' + (m.client_nom || m.code_client || '-') + '</td>' +
                   '<td>' + fmt.date(m.date_mvt) + '</td>' +
                   '<td><button class="btn btn-outline btn-sm" onclick="ouvrirRegulariser(' + m.id + ')">' +
                   '🔗 Régulariser</button></td>' +
                   '</tr>';
        }).join('');
    });
}

function ouvrirRegulariser(id) {
    document.getElementById('reg-mvt-id').value = id;
    var msgEl = document.getElementById('reg-msg');
    if (msgEl) msgEl.innerHTML = '';
    var sageEl = document.getElementById('reg-no-sage');
    if (sageEl) sageEl.value = '';
    ouvrirModal('modal-regulariser');
}

function regulariserManuel() {
    var id    = document.getElementById('reg-mvt-id')  ? document.getElementById('reg-mvt-id').value  : '';
    var noSage = document.getElementById('reg-no-sage') ? document.getElementById('reg-no-sage').value.trim() : '';
    var msg   = document.getElementById('reg-msg');
    if (!id || !noSage) { alert('Numéro BL Sage obligatoire'); return; }
    if (msg) msg.innerHTML = '<span style="color:var(--muted)">Régularisation en cours...</span>';
    apiPost('/api/stock/regulariser-manuel', {id: parseInt(id), no_sage: noSage}, function(d) {
        var texte = 'Régularisé — Statut: ' + d.statut + ' | Écart: ' + d.ecart;
        if (msg) msg.innerHTML = '<span style="color:#10B981">' + texte + '</span>';
        setTimeout(function() {
            fermerModal('modal-regulariser');
            chargerNonReg();
        }, 1500);
    }, function(e) {
        if (msg) msg.innerHTML = '<span style="color:var(--red)">Erreur: ' + e + '</span>';
    });
}

// ── Top Sorties — avec composant universel ─────────────────────

function initTopSelector() {
    if (_topSelector) return;
    _topSelector = nexoraCreateSelector({
        containerId:  'top-selector',
        granularites: ['semaine','mois','trimestre','annee'],
        defaut:       'mois',
        maxPeriodes:  3,
        onAnalyser:   function(periodes) {
            chargerTopAvecPeriodes(periodes);
        }
    });
    _topSelector.analyser();
}

function chargerTopAvecPeriodes(periodes) {
    tableLoader('top-tbody', 5);
    var sommeEl = document.getElementById('top-somme');
    if (sommeEl) sommeEl.textContent = '';
    var compEl = document.getElementById('top-comparaison');
    if (compEl) compEl.innerHTML = '';

    if (!periodes || !periodes.length) return;

    // Charger la période principale
    var p1 = periodes[0];
    apiGet('/api/stock/analyses/top-sorties?debut=' + p1.debut + '&fin=' + p1.fin, function(d1) {
        var tbody = document.getElementById('top-tbody');
        if (!tbody) return;
        if (!d1.articles || !d1.articles.length) {
            tableVide('top-tbody', 5, 'Aucune donnée Sage pour cette période');
            if (_topSelector) _topSelector.setStatus('Aucune donnée');
            return;
        }

        var somme = d1.somme_top || 0;
        if (sommeEl) sommeEl.textContent =
            'SOMME Top ' + d1.articles.length + ' articles : ' + fmt.qty(somme) + ' unités';

        tbody.innerHTML = d1.articles.map(function(a, i) {
            return '<tr>' +
                   '<td style="font-weight:800;color:var(--gold)">' + (i+1) + '</td>' +
                   '<td style="font-weight:700;color:var(--navy)">' + (a.ar_ref || '-') + '</td>' +
                   '<td>' + (a.designation || '-') + '</td>' +
                   '<td style="font-weight:700;color:var(--gold)">' + fmt.qty(a.total_qte) + '</td>' +
                   '<td style="color:var(--muted)">' + (a.nb_mvts || 0) + '</td>' +
                   '</tr>';
        }).join('');

        // Si plusieurs périodes, afficher la comparaison des sommes
        if (periodes.length > 1) {
            var valeurs  = [somme];
            var pending  = periodes.length - 1;
            periodes.slice(1).forEach(function(p, idx) {
                apiGet('/api/stock/analyses/top-sorties?debut=' + p.debut + '&fin=' + p.fin, function(dN) {
                    valeurs[idx + 1] = dN.somme_top || 0;
                    pending--;
                    if (pending === 0) {
                        nexoraAfficherComparaison('top-comparaison', periodes, valeurs, 'nb');
                        if (_topSelector) _topSelector.setStatus('');
                    }
                }, function() {
                    valeurs[idx + 1] = 0; pending--;
                    if (pending === 0) {
                        nexoraAfficherComparaison('top-comparaison', periodes, valeurs, 'nb');
                        if (_topSelector) _topSelector.setStatus('');
                    }
                });
            });
        } else {
            if (_topSelector) _topSelector.setStatus('');
        }
    }, function(e) {
        tableVide('top-tbody', 5, 'Connexion Sage non disponible');
        if (_topSelector) _topSelector.setStatus('Sage non disponible');
    });
}

// ── Stocks Dormants — avec composant universel ─────────────────

function setSeuil(j) {
    var el = document.getElementById('dorm-seuil');
    if (el) el.value = j;
    document.querySelectorAll('[data-seuil]').forEach(function(b) {
        b.className = parseInt(b.getAttribute('data-seuil')) === j
            ? 'btn btn-navy btn-sm' : 'btn btn-outline btn-sm';
    });
    if (_dormSelector) _dormSelector.analyser();
}

function initDormantsSelector() {
    if (_dormSelector) return;
    _dormSelector = nexoraCreateSelector({
        containerId:  'dorm-selector',
        granularites: ['semaine','mois','trimestre','annee'],
        defaut:       'mois',
        maxPeriodes:  3,
        onAnalyser:   function(periodes) {
            chargerDormantsAvecPeriodes(periodes);
        }
    });
    _dormSelector.analyser();
}

function chargerDormantsAvecPeriodes(periodes) {
    tableLoader('dorm-tbody', 5);
    var kpisEl = document.getElementById('dorm-kpis');
    var compEl = document.getElementById('dorm-comparaison');
    if (kpisEl) kpisEl.innerHTML = '';
    if (compEl) compEl.innerHTML = '';

    if (!periodes || !periodes.length) return;

    var seuil = document.getElementById('dorm-seuil') ? document.getElementById('dorm-seuil').value : 15;
    var p1    = periodes[0];
    var url   = '/api/stock/analyses/dormants?jours=' + seuil + '&debut=' + p1.debut + '&fin=' + p1.fin;

    apiGet(url, function(d) {
        if (d.message && !d.articles.length) {
            if (kpisEl) kpisEl.innerHTML = '<div class="alert alert-warn" style="grid-column:1/-1">⚠️ ' + d.message + '</div>';
            tableVide('dorm-tbody', 5, 'Sage non disponible');
            return;
        }
        if (kpisEl) kpisEl.innerHTML =
            kpiCard('💤', 'Articles dormants (SOMME)', d.somme_totale || 0, '#F59E0B') +
            kpiCard('💰', 'Valeur immobilisée', fmt.money(d.valeur_immobilisee || 0), '#EF4444');

        var tbody = document.getElementById('dorm-tbody');
        if (!tbody) return;
        if (!d.articles || !d.articles.length) {
            tableVide('dorm-tbody', 5, 'Aucun article dormant pour ce seuil');
            return;
        }
        tbody.innerHTML = d.articles.map(function(a) {
            var prix   = parseFloat(a.prix_achat || a.AR_PrixAch || 0);
            var stock  = parseFloat(a.stock_physique || 0);
            var valeur = stock * prix;
            return '<tr>' +
                   '<td style="font-weight:700;color:var(--navy)">' + (a.AR_Ref || a.ar_ref || '-') + '</td>' +
                   '<td>' + (a.AR_Design || a.designation || '-') + '</td>' +
                   '<td>' + fmt.qty(stock) + '</td>' +
                   '<td>' + fmt.money(prix) + '</td>' +
                   '<td style="color:#EF4444;font-weight:700">' + fmt.money(valeur) + '</td>' +
                   '</tr>';
        }).join('');

        // Comparaison multi-périodes sur la somme totale
        if (periodes.length > 1) {
            var valeurs = [d.somme_totale || 0];
            var pending = periodes.length - 1;
            periodes.slice(1).forEach(function(p, idx) {
                var urlN = '/api/stock/analyses/dormants?jours=' + seuil + '&debut=' + p.debut + '&fin=' + p.fin;
                apiGet(urlN, function(dN) {
                    valeurs[idx + 1] = dN.somme_totale || 0;
                    pending--;
                    if (pending === 0) {
                        nexoraAfficherComparaison('dorm-comparaison', periodes, valeurs, 'nb');
                        if (_dormSelector) _dormSelector.setStatus('');
                    }
                }, function() {
                    valeurs[idx + 1] = 0; pending--;
                    if (pending === 0) {
                        nexoraAfficherComparaison('dorm-comparaison', periodes, valeurs, 'nb');
                        if (_dormSelector) _dormSelector.setStatus('');
                    }
                });
            });
        } else {
            if (_dormSelector) _dormSelector.setStatus('');
        }
    }, function() {
        tableVide('dorm-tbody', 5, 'Connexion Sage non disponible');
        if (_dormSelector) _dormSelector.setStatus('Sage non disponible');
    });
}

// ── Valorisation — avec composant universel ────────────────────

function initValSelector() {
    if (_valSelector) return;
    _valSelector = nexoraCreateSelector({
        containerId:  'val-selector',
        granularites: ['semaine','mois','trimestre','annee'],
        defaut:       'mois',
        maxPeriodes:  3,
        onAnalyser:   function(periodes) {
            chargerValorisationAvecPeriodes(periodes);
        }
    });
    _valSelector.analyser();
}

function chargerValorisationAvecPeriodes(periodes) {
    var compEl = document.getElementById('val-comparaison');
    if (compEl) compEl.innerHTML = '<span class="loader"></span> Chargement...';
    apiGet('/api/stock/analyses/valorisation', function(d1) {
        if (d1.message && !d1.nb_articles) {
            if (compEl) compEl.innerHTML = '<div class="alert alert-warn">⚠️ ' + d1.message + '</div>';
            if (_valSelector) _valSelector.setStatus('');
            return;
        }
        if (periodes.length > 1) {
            nexoraAfficherComparaison('val-comparaison',
                periodes, [d1.valeur_totale || 0], 'FCFA');
        } else {
            if (compEl) compEl.innerHTML =
                '<div class="card" style="border-left:4px solid var(--navy);padding:12px">' +
                '<div style="font-size:10px;font-weight:700;color:var(--muted)">' + (periodes[0] ? periodes[0].label : '') + '</div>' +
                '<div style="font-size:20px;font-weight:800;color:var(--navy)">' + fmt.money(d1.valeur_totale || 0) + '</div>' +
                '<div style="font-size:11px;color:var(--muted);margin-top:4px">' +
                d1.nb_articles + ' articles | ' + d1.nb_ruptures + ' ruptures</div></div>';
        }
        if (_valSelector) _valSelector.setStatus('');
    }, function() {
        if (compEl) compEl.innerHTML = '<div class="tbl-empty">Sage non disponible</div>';
    });
}

// ── Stock Consolidé ────────────────────────────────────────────

function chargerConsolide() {
    var zone = document.getElementById('cons-table-zone');
    if (zone) zone.innerHTML = '<div class="tbl-empty"><span class="loader"></span> Chargement...</div>';
    apiGet('/api/stock/consolide', function(d) {
        if (d.message && !d.nb_articles) {
            if (zone) zone.innerHTML = '<div class="alert alert-warn">⚠️ ' + d.message + '</div>';
            var kpis0 = document.getElementById('cons-kpis');
            if (kpis0) kpis0.innerHTML = '';
            return;
        }
        _consData = d.articles || [];
        var agences = d.agences || [];
        var kpis = document.getElementById('cons-kpis');
        if (kpis) kpis.innerHTML =
            kpiCard('📦', 'Total articles', d.nb_articles || 0, '#1A3263') +
            kpiCard('💰', 'Valeur réseau', fmt.money(d.valeur_totale || 0), '#FBC013');
        afficherTableauConsolide(agences);
    }, function() {
        if (zone) zone.innerHTML = '<div class="tbl-empty">Sage non disponible</div>';
    });
}

function filtrerConsolide() {
    afficherTableauConsolide(null);
}

function afficherTableauConsolide(agences) {
    var q     = document.getElementById('cons-search') ? document.getElementById('cons-search').value.toLowerCase() : '';
    var zone  = document.getElementById('cons-table-zone');
    if (!zone) return;

    var data = _consData.filter(function(a) {
        return !q || (a.ar_ref || '').toLowerCase().includes(q) ||
               (a.designation || '').toLowerCase().includes(q);
    });

    if (!data.length) { zone.innerHTML = '<div class="tbl-empty">Aucun article</div>'; return; }

    var agsLocal = agences || (data[0] ? Object.keys(data[0].agences || {}).map(function(id) { return {id: parseInt(id), nom: 'Agence ' + id}; }) : []);

    var thAgences = agsLocal.map(function(ag) {
        return '<th style="color:#FBC013">' + ag.nom.replace(' (Siège)','').replace(' (Siege)','') + '</th>';
    }).join('');

    var html = '<div class="tbl-wrap"><table><thead><tr>' +
               '<th>Référence</th><th>Désignation</th>' +
               thAgences +
               '<th style="font-weight:800;background:#142651">TOTAL</th>' +
               '<th style="font-weight:800;background:#142651">VALEUR FCFA</th>' +
               '</tr></thead><tbody>';

    data.forEach(function(a) {
        var tdAgs = agsLocal.map(function(ag) {
            var q = parseFloat((a.agences || {})[ag.id] || 0);
            var c = q <= 0 ? 'color:#CBD5E1' : '';
            return '<td style="text-align:right;' + c + '">' + (q > 0 ? fmt.qty(q) : '-') + '</td>';
        }).join('');
        html += '<tr>' +
                '<td style="font-weight:700;color:var(--navy);font-family:monospace">' + a.ar_ref + '</td>' +
                '<td>' + (a.designation || '-') + '</td>' +
                tdAgs +
                '<td style="font-weight:800;text-align:right">' + fmt.qty(a.total) + '</td>' +
                '<td style="font-weight:800;color:var(--gold);text-align:right">' + fmt.money(a.valeur) + '</td>' +
                '</tr>';
    });
    html += '</tbody></table></div>';
    zone.innerHTML = html;
}

function exporterConsolide() {
    alert('Export Excel — fonctionnalité dans Module Rapports');
}

// ── Inter-Agences — Stock Disponible ──────────────────────────

function chargerMSStock() {
    var agence = document.getElementById('ms-agence-src') ? document.getElementById('ms-agence-src').value : 2;
    tableLoader('ms-tbody', 7);
    _msData = [];
    apiGet('/api/stock/multisite/stock-disponible?agence_source=' + agence, function(d) {
        if (d.message && !d.nb) {
            tableVide('ms-tbody', 7, d.message);
            return;
        }
        _msData = d.articles || [];
        filtrerMS();
    }, function() {
        tableVide('ms-tbody', 7, 'Connexion Sage non disponible');
    });
}

function filtrerMS() {
    var q = document.getElementById('ms-search') ? document.getElementById('ms-search').value.toLowerCase() : '';
    var filtered = _msData.filter(function(a) {
        return !q || (a.AR_Ref || '').toLowerCase().includes(q) ||
               (a.AR_Design || '').toLowerCase().includes(q);
    });
    var tbody = document.getElementById('ms-tbody');
    if (!tbody) return;
    if (!filtered.length) { tableVide('ms-tbody', 7, 'Aucun article'); return; }
    tbody.innerHTML = filtered.slice(0, 200).map(function(a) {
        var dispo = parseFloat(a.stock_dispo !== undefined ? a.stock_dispo : 0);
        var col   = dispo <= 0 ? '#EF4444' : '#10B981';
        return '<tr>' +
               '<td style="font-weight:700;color:var(--navy);font-family:monospace">' + (a.AR_Ref || '-') + '</td>' +
               '<td>' + (a.AR_Design || a.designation || '-') + '</td>' +
               '<td style="text-align:right">' + fmt.qty(a.stock_physique || 0) + '</td>' +
               '<td style="text-align:right;color:#F97316">' + fmt.qty(a.qte_reservee || 0) + '</td>' +
               '<td style="text-align:right;color:#818CF8">' + fmt.qty(a.qte_en_dt || 0) + '</td>' +
               '<td style="text-align:right;color:' + col + ';font-weight:800">' +
               (dispo <= 0 ? 'RUPTURE' : fmt.qty(dispo)) + '</td>' +
               '<td style="text-align:right">' + fmt.money(a.prix_achat || a.AR_PrixAch || 0) + '</td>' +
               '</tr>';
    }).join('');
}

// ── Transferts DT ──────────────────────────────────────────────

function chargerDTs() {
    var statut = document.getElementById('dt-statut-fil') ? document.getElementById('dt-statut-fil').value : '';
    apiGet('/api/stock/multisite/transferts' + (statut ? '?statut=' + statut : ''), function(d) {
        var el = document.getElementById('dt-liste');
        if (!el) return;
        var dts = d.transferts || [];
        if (!dts.length) { el.innerHTML = '<div class="tbl-empty">Aucune DT</div>'; return; }
        el.innerHTML = dts.map(function(dt) {
            var sBadge = {
                SOUMISE: badge('En attente','warn'),
                VALIDEE: badge('Validée','ok'),
                EN_COURS: badge('En cours','info'),
                LIVREE:  badge('Livrée','ok'),
                REFUSEE: badge('Refusée','err'),
            }[dt.statut] || badge(dt.statut, 'muted');
            var act = dt.statut === 'SOUMISE' ?
                '<button class="btn btn-navy btn-sm" onclick="validerDT(' + dt.id + ')">✅ Valider</button> ' +
                '<button class="btn btn-sm" style="background:var(--red);color:white" onclick="refuserDT(' + dt.id + ')">❌ Refuser</button>' : '';
            return '<div class="card" style="margin-bottom:8px">' +
                   '<div style="display:flex;justify-content:space-between;align-items:flex-start">' +
                   '<div>' +
                   '<div style="display:flex;align-items:center;gap:8px;margin-bottom:4px">' +
                   '<strong style="font-family:monospace">' + dt.numero + '</strong> ' + sBadge +
                   (dt.urgence ? ' ' + badge('URGENT','err') : '') + '</div>' +
                   '<div style="font-size:11px;color:var(--muted)">' +
                   (dt.source_nom || '-') + ' → ' + (dt.dest_nom || '-') +
                   ' | ' + fmt.date(dt.date_demande) + ' | ' + (dt.demande_par || '-') + '</div>' +
                   (dt.motif_refus ? '<div style="font-size:11px;color:#EF4444;margin-top:4px">Motif refus: ' + dt.motif_refus + '</div>' : '') +
                   '</div>' +
                   '<div style="display:flex;gap:6px">' + act + '</div></div></div>';
        }).join('');
    });
}

function validerDT(id) {
    apiPost('/api/stock/multisite/transferts/' + id + '/valider', {action:'valider'}, function() {
        status('DT validée'); chargerDTs();
    });
}

function refuserDT(id) {
    var motif = prompt('Motif de refus (obligatoire):');
    if (motif === null) return;
    if (!motif.trim()) { alert('Le motif de refus est obligatoire'); return; }
    apiPost('/api/stock/multisite/transferts/' + id + '/valider',
        {action:'refuser', motif_refus: motif}, function() {
        status('DT refusée'); chargerDTs();
    });
}

// ── Nouvelle DT ────────────────────────────────────────────────

function dtAjouterLigne() {
    var zone = document.getElementById('dt-lignes-zone');
    if (!zone) return;
    var idx  = zone.children.length;
    var div  = document.createElement('div');
    div.style.cssText = 'display:flex;gap:8px;margin-bottom:6px;align-items:center;flex-wrap:wrap';
    div.innerHTML =
        '<input type="text" id="dt-ref-' + idx + '" placeholder="Référence article" ' +
        'style="width:150px;padding:6px;border:2px solid var(--border);border-radius:6px;font-size:12px;text-transform:uppercase" ' +
        'oninput="this.value=this.value.toUpperCase()">' +
        '<input type="text" id="dt-des-' + idx + '" placeholder="Désignation" ' +
        'style="width:200px;padding:6px;border:2px solid var(--border);border-radius:6px;font-size:12px">' +
        '<input type="number" id="dt-qte-' + idx + '" placeholder="Qté" step="0.01" min="0.01" ' +
        'style="width:90px;padding:6px;border:2px solid var(--border);border-radius:6px;font-size:12px">' +
        '<button onclick="this.parentElement.remove()" ' +
        'style="background:transparent;border:none;color:var(--muted);cursor:pointer;font-size:16px">✕</button>';
    zone.appendChild(div);
}

function soumettredt() {
    var src  = document.getElementById('dt-src')    ? parseInt(document.getElementById('dt-src').value)  : 2;
    var dest = document.getElementById('dt-dest')   ? parseInt(document.getElementById('dt-dest').value) : 3;
    var urg  = document.getElementById('dt-urgence') ? document.getElementById('dt-urgence').checked      : false;
    var zone = document.getElementById('dt-lignes-zone');
    var msg  = document.getElementById('dt-msg');
    if (!zone) return;
    var lignes = [];
    zone.querySelectorAll('div').forEach(function(div, i) {
        var ref = document.getElementById('dt-ref-' + i);
        var des = document.getElementById('dt-des-' + i);
        var qte = document.getElementById('dt-qte-' + i);
        if (ref && ref.value.trim() && qte && parseFloat(qte.value) > 0) {
            lignes.push({
                ar_ref:      ref.value.trim(),
                designation: des ? des.value : '',
                qte:         parseFloat(qte.value),
            });
        }
    });
    if (!lignes.length) { alert('Ajoutez au moins un article'); return; }
    if (msg) msg.innerHTML = '<span style="color:var(--muted)">Soumission en cours...</span>';
    apiPost('/api/stock/multisite/transferts',
        {agence_source_id: src, agence_dest_id: dest, urgence: urg, lignes: lignes},
        function(d) {
            fermerModal('modal-dt');
            chargerDTs();
            status('DT soumise: ' + d.numero);
        }, function(e) {
            if (msg) msg.innerHTML = '<span style="color:var(--red)">Erreur: ' + e + '</span>';
        });
}

// ── Demandes d'Achat DA ────────────────────────────────────────

function chargerDAs() {
    apiGet('/api/stock/multisite/demandes-achat', function(d) {
        var el = document.getElementById('da-liste');
        if (!el) return;
        var das = d.demandes || [];
        if (!das.length) { el.innerHTML = '<div class="tbl-empty">Aucune DA</div>'; return; }
        el.innerHTML = das.map(function(da) {
            return '<div class="card" style="margin-bottom:8px">' +
                   '<div style="display:flex;justify-content:space-between">' +
                   '<div>' +
                   '<strong style="font-family:monospace">' + da.numero + '</strong> ' +
                   badge(da.statut, da.statut === 'VALIDEE' ? 'ok' : da.statut === 'REFUSEE' ? 'err' : 'warn') +
                   (da.urgence ? ' ' + badge('URGENT','err') : '') +
                   '<div style="font-size:11px;color:var(--muted);margin-top:2px">' +
                   (da.fournisseur_nom || '-') + ' | ' + fmt.date(da.date_demande) + '</div>' +
                   '</div>' +
                   (da.statut === 'SOUMISE' ?
                   '<button class="btn btn-navy btn-sm" onclick="validerDA(' + da.id + ')">✅ Valider</button>' : '') +
                   '</div></div>';
        }).join('');
    });
}

function validerDA(id) {
    apiPost('/api/stock/multisite/demandes-achat/' + id + '/valider', {action:'valider'}, function() {
        status('DA validée'); chargerDAs();
    });
}

// ── Init ────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', function() {
    var dateEl = document.getElementById('man-date');
    if (dateEl) dateEl.value = new Date().toISOString().split('T')[0];
    chargerDashboardStock();
});
