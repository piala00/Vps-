/**
 * NEXORA v2.0 — Module Commercial & Ventes
 * Classement, Cockpit, Tendances depuis GTC ERP PILOT V3
 */

var autoLoad = {
    'com-dashboard':  function(){ chargerDashCom(); },
    'com-classement': function(){ chargerClassement(); },
    'com-cockpit':    function(){ preparerCockpit(); },
    'com-tendances':  function(){ chargerTendances(); },
    'com-clients':    function(){ chargerClients(); },
    'com-objectifs':  function(){ chargerObjectifs(); },
    'com-analyse-ca': function(){ initCASelector(); },
};

var _classementData = [];
var _cockpitData    = null;
var _tendChart      = null;
var _caSelector     = null;

// ── Dashboard ──────────────────────────────────────────────────

function chargerDashCom() {
    var kpis = document.getElementById('com-kpis');
    if (kpis) kpis.innerHTML = '<div class="tbl-empty"><span class="loader"></span> Chargement...</div>';
    apiGet(nexoraAppendPeriode('/api/commercial/dashboard'), function(d) {
        if (!d.ca_total && !d.nb_clients && d.message) {
            if (kpis) kpis.innerHTML = '<div class="alert alert-warn" style="grid-column:1/-1">' +
                '⚠️ ' + d.message + '. Verifiez la connexion Sage ou importez un fichier Excel dans Parametres &gt; Source &amp; Config.</div>';
            var alEl0 = document.getElementById('com-alertes');
            if (alEl0) alEl0.innerHTML = '<div class="tbl-empty">Aucune donnee disponible</div>';
            var srcEl0 = document.getElementById('com-source-info');
            if (srcEl0) srcEl0.innerHTML = 'Source: <strong>' + (d.source || '-') + '</strong> — donnees non chargees';
            return;
        }
        if (kpis) kpis.innerHTML =
            kpiCard('💰', 'CA Total', fmt.money(d.ca_total || 0), '#FBC013') +
            kpiCard('✅', 'Recouvrement', fmt.money(d.rec_total || 0), '#10B981') +
            kpiCard('⚠️', 'Creances echues', fmt.money(d.creances_totales || 0), '#EF4444') +
            kpiCard('👥', 'Clients actifs', d.nb_clients || 0, '#1A3263') +
            kpiCard('🏅', 'Commerciaux', d.nb_commerciaux || 0, '#FBC013') +
            kpiCard('🕐', 'Clients en retard', d.nb_retard || 0, '#F59E0B');
        var srcEl = document.getElementById('com-source-info');
        if (srcEl) srcEl.innerHTML = 'Source: <strong>' + (d.source || '-') + '</strong>' +
            (d.period_label ? ' | Periode: ' + d.period_label : '') +
            (d.loaded_at ? ' | Maj: ' + d.loaded_at : '');
        var alEl = document.getElementById('com-alertes');
        if (alEl) {
            var al = d.alertes || [];
            if (!al.length) { alEl.innerHTML = '<div class="tbl-empty">Aucune alerte</div>'; }
            else alEl.innerHTML = al.map(function(a) {
                var col = a.niveau === 'CRITIQUE' ? 'var(--red)' :
                          a.niveau === 'ALERTE'   ? 'var(--warn)' : 'var(--muted)';
                return '<div style="display:flex;justify-content:space-between;padding:6px 0;border-bottom:1px solid var(--border)">' +
                       '<span>' + badge(a.niveau, a.niveau==='CRITIQUE'?'err':a.niveau==='ALERTE'?'warn':'info') +
                       ' ' + a.nom + '</span>' +
                       '<span style="color:'+col+';font-weight:700">' + fmt.money(a.fns) + (a.retard?' / '+a.retard+'j':'') + '</span></div>';
            }).join('');
        }
    }, function() {
        status('Sage/Excel non disponible');
    });
}

// ── Classement ─────────────────────────────────────────────────

function chargerClassement(force) {
    var url = nexoraAppendPeriode('/api/commercial/classement') + (force ? '&force=1' : '');
    tableLoader('cl-tbody', 10);
    var podium = document.getElementById('cl-podium');
    if (podium) podium.innerHTML = '<div class="tbl-empty"><span class="loader"></span> Chargement Sage...</div>';
    apiGet(url, function(d) {
        _classementData = d.classement || [];
        afficherClassement(_classementData);
        afficherPodium(_classementData);
        // Peupler la liste des commerciaux dans Cockpit
        var sel = document.getElementById('cockpit-com-sel');
        if (sel) {
            sel.innerHTML = '<option value="">-- Choisir --</option>';
            _classementData.forEach(function(r) {
                var opt = document.createElement('option');
                opt.value = r.commercial;
                opt.textContent = r.commercial + ' (CA: ' + fmt.money(r.ca) + ')';
                sel.appendChild(opt);
            });
        }
        // Peupler tendances
        var tend = document.getElementById('tend-com');
        if (tend) {
            tend.innerHTML = '<option value="">Tous</option>';
            _classementData.forEach(function(r) {
                var opt = document.createElement('option');
                opt.value = r.commercial;
                opt.textContent = r.commercial;
                tend.appendChild(opt);
            });
        }
    }, function() {
        tableVide('cl-tbody', 10, 'Sage non disponible');
        var podium2 = document.getElementById('cl-podium');
        if (podium2) podium2.innerHTML = '';
    });
}

function afficherPodium(data) {
    var podium = document.getElementById('cl-podium');
    if (!podium) return;
    var medals = ['🥇','🥈','🥉'];
    var colors  = ['#FBC013','#C0C8D8','#CD7F32'];
    var top3    = data.slice(0, 3);
    podium.innerHTML = top3.map(function(r, i) {
        var pct    = r.pct_obj ? r.pct_obj.toFixed(1) : '0.0';
        var pctCol = parseFloat(pct) >= 100 ? 'var(--green)' : parseFloat(pct) >= 50 ? 'var(--warn)' : 'var(--red)';
        return '<div class="kpi-card" style="border-left-color:' + colors[i] + '">' +
               '<div class="kico">' + medals[i] + '</div>' +
               '<div class="klabel">' + r.commercial + '</div>' +
               '<div class="kval">' + fmt.money(r.ca) + '</div>' +
               '<div class="kdelta" style="color:' + pctCol + '">' + pct + '% obj.</div>' +
               '<div style="font-size:11px;color:var(--muted);margin-top:2px">Rec. ' + fmt.money(r.recouvrement) + '</div>' +
               '</div>';
    }).join('');
}

function afficherClassement(data) {
    var tbody = document.getElementById('cl-tbody');
    if (!tbody) return;
    if (!data.length) { tableVide('cl-tbody', 10, 'Aucune donnee'); return; }
    tbody.innerHTML = data.map(function(r) {
        var pct    = r.pct_obj ? r.pct_obj.toFixed(1) : '0.0';
        var pctCol = parseFloat(pct) >= 100 ? 'color:var(--green)' :
                     parseFloat(pct) >= 50  ? 'color:var(--warn)'  : 'color:var(--red)';
        var trec   = r.taux_rec ? r.taux_rec.toFixed(1) : '0.0';
        var score  = r.score ? (r.score * 100).toFixed(1) : '0.0';
        return '<tr>' +
               '<td style="font-weight:800;color:var(--gold)">' + (r.rang || '-') + '</td>' +
               '<td style="font-weight:700">' + (r.commercial || '-') + '</td>' +
               '<td style="color:var(--gold);font-weight:700">' + fmt.money(r.ca || 0) + '</td>' +
               '<td>' + fmt.money(r.objectif || 0) + '</td>' +
               '<td style="font-weight:700;' + pctCol + '">' + pct + '%</td>' +
               '<td style="color:var(--green)">' + fmt.money(r.recouvrement || 0) + '</td>' +
               '<td>' + trec + '%</td>' +
               '<td style="color:var(--red)">' + fmt.money(r.fns || 0) + '</td>' +
               '<td>' + (r.nb_retard || 0) + '</td>' +
               '<td style="font-weight:700">' + score + '</td>' +
               '</tr>';
    }).join('');
}

// ── Cockpit ────────────────────────────────────────────────────

function preparerCockpit() {
    if (!_classementData.length) chargerClassement();
}

function afficherOngletCockpit(nom) {
    ['resume','clients','creances','mouvements'].forEach(function(n) {
        var el = document.getElementById('cockpit-' + n);
        if (el) el.style.display = (n === nom) ? 'block' : 'none';
    });
    document.querySelectorAll('[onclick*="afficherOngletCockpit"]').forEach(function(b) {
        b.className = b.getAttribute('onclick').includes("'" + nom + "'")
            ? 'btn btn-navy btn-sm' : 'btn btn-outline btn-sm';
    });
}

function chargerCockpit() {
    var com = document.getElementById('cockpit-com-sel') ? document.getElementById('cockpit-com-sel').value : '';
    if (!com) return;
    var kpisEl = document.getElementById('cockpit-kpis');
    if (kpisEl) kpisEl.innerHTML = '<div class="tbl-empty"><span class="loader"></span> Chargement...</div>';
    apiGet(nexoraAppendPeriode('/api/commercial/cockpit?commercial=' + encodeURIComponent(com)), function(d) {
        if (d.message && (!d.kpis || !Object.keys(d.kpis).length)) {
            if (kpisEl) kpisEl.innerHTML = '<div class="alert alert-warn" style="grid-column:1/-1">⚠️ ' + d.message + '</div>';
            var cpEl0 = document.getElementById('cockpit-copilote-content');
            if (cpEl0) cpEl0.innerHTML = '<div class="tbl-empty">Aucune donnee disponible</div>';
            return;
        }
        var k = d.kpis || {};
        var cp = d.copilote || {};
        // ── Copilote quotidien ──
        var cpEl = document.getElementById('cockpit-copilote-content');
        if (cpEl) {
            if (cp.statut === 'SANS_OBJECTIF') {
                cpEl.innerHTML = '<div class="alert alert-warn">Aucun objectif mensuel defini pour ' + com + '. Configurez un objectif dans Parametres pour activer le copilote.</div>';
            } else {
                var statutLabel = {
                    'OBJECTIF_ATTEINT': ["Objectif atteint !", 'var(--green)'],
                    'EN_AVANCE':        ["En avance sur l objectif", 'var(--green)'],
                    'DANS_LES_TEMPS':   ["Dans les temps", 'var(--warn)'],
                    'EN_RETARD':        ["En retard sur l objectif", 'var(--red)'],
                }[cp.statut] || ['-', 'var(--muted)'];
                var varJour = cp.variation_jour_pct;
                var varTxt  = varJour === null || varJour === undefined ? 'Pas de donnees hier' :
                              (varJour >= 0 ? '+' : '') + varJour + '% vs hier';
                var varCol  = varJour === null || varJour === undefined ? 'var(--muted)' : (varJour >= 0 ? 'var(--green)' : 'var(--red)');
                var icoStatut = {'OBJECTIF_ATTEINT':'🏆','EN_AVANCE':'🟢','DANS_LES_TEMPS':'🟡','EN_RETARD':'🔴'}[cp.statut] || '';
                cpEl.innerHTML =
                    '<div style="font-size:14px;font-weight:800;color:' + statutLabel[1] + ';margin-bottom:10px">' + icoStatut + ' ' + statutLabel[0] + '</div>' +
                    '<div class="kpi-grid">' +
                    kpiCard('💰', 'Vendu aujourd hui', fmt.money(cp.ca_aujourdhui||0), '#FBC013') +
                    kpiCard('📆', 'Vendu hier', fmt.money(cp.ca_hier||0), '#7EB8F7') +
                    kpiCard(varJour >= 0 ? '📈' : '📉', 'Variation jour', varTxt, varCol) +
                    kpiCard('🎯', 'Objectif du mois', fmt.money(cp.objectif_mensuel||0), '#A0B8E8') +
                    kpiCard('📊', 'Realise ce mois', fmt.money(cp.ca_mois_cumule||0) + ' (' + (cp.pct_objectif_mois||0) + '%)', '#10B981') +
                    kpiCard('⏳', 'Reste a vendre', fmt.money(cp.reste_a_vendre||0), '#F59E0B') +
                    kpiCard('📅', 'Jours restants', (cp.jours_restants||0) + ' / ' + (cp.nb_jours_mois||0), '#D0DCF0') +
                    kpiCard('🚀', 'Rythme necessaire/jour', fmt.money(cp.rythme_quotidien_necessaire||0), '#EF4444') +
                    '</div>';
            }
        }
        if (kpisEl) kpisEl.innerHTML =
            kpiCard('💰', 'CA Realise', fmt.money(k.ca || 0), '#FBC013') +
            kpiCard('🎯', 'Objectif', fmt.money(k.obj || 0), '#7EB8F7') +
            kpiCard('✅', 'Recouvrement', fmt.money(k.recouvrement || 0), '#10B981') +
            kpiCard('⚠️', 'Creances echues', fmt.money(k.fns || 0), '#EF4444') +
            kpiCard('📊', 'Solde total', fmt.money(k.solde || 0), '#A0B8E8') +
            kpiCard('👥', 'Nb clients', k.nb_clients || 0, '#D0DCF0') +
            kpiCard('🔴', 'Depassements', fmt.money(k.mdp || 0), '#F59E0B') +
            kpiCard('🧾', 'Nb factures', k.nb_fac || 0, '#FBC013') +
            kpiCard('📈', '% Objectif', (k.pct_obj || 0).toFixed(1) + '%',
                    (k.pct_obj || 0) >= 100 ? '#10B981' : '#F59E0B') +
            kpiCard('♻️', 'Taux recouvrement', (k.taux_rec || 0).toFixed(1) + '%',
                    (k.taux_rec || 0) >= 80 ? '#10B981' : '#F59E0B') +
            kpiCard('⚡', 'Taux risque', (k.taux_risque || 0).toFixed(1) + '%',
                    (k.taux_risque || 0) > 30 ? '#EF4444' : '#10B981') +
            kpiCard('🕐', 'Clients retard', k.nb_retard || 0,
                    (k.nb_retard || 0) > 0 ? '#EF4444' : '#10B981');
        // Résumé (avec répartition Comptant vs Terme)
        var rc = document.getElementById('cockpit-resume-content');
        if (rc) rc.innerHTML =
            '<div style="font-size:13px"><strong>' + com + '</strong><br>' +
            '<span style="color:var(--muted)">CA Comptant : </span><strong style="color:var(--green)">' + fmt.money(k.ca_comptant||0) + '</strong> | ' +
            '<span style="color:var(--muted)">CA Terme : </span><strong style="color:#3498DB">' + fmt.money(k.ca_terme||0) + '</strong></div>';
        // Top clients (avec statut colore A RISQUE/ATTENTION/BON CLIENT/SOLDE OK/NORMAL)
        var tc = document.getElementById('cockpit-clients-tbody');
        if (tc) {
            var top = d.top_clients || [];
            if (!top.length) { tableVide('cockpit-clients-tbody', 6, 'Aucun client'); }
            else tc.innerHTML = top.map(function(c) {
                var badgeType = c.statut === 'A RISQUE' ? 'err' :
                                c.statut === 'ATTENTION' ? 'warn' :
                                c.statut === 'BON CLIENT' ? 'ok' : 'info';
                return '<tr><td>' + c.code + '</td><td>' + c.nom + '</td><td>' + (c.zone||'-') + '</td>' +
                       '<td style="color:var(--gold);font-weight:700">' + fmt.money(c.ca) + '</td>' +
                       '<td>' + (c.icone||'') + ' ' + badge(c.statut||'-', badgeType) + '</td>' +
                       '<td>' + (c.telephone||'-') + '</td></tr>';
            }).join('');
        }
        // Créances
        var cc = document.getElementById('cockpit-creances-tbody');
        if (cc) {
            var crs = d.creances || [];
            if (!crs.length) { tableVide('cockpit-creances-tbody', 7, 'Aucune creance'); }
            else cc.innerHTML = crs.map(function(c) {
                var col = c.retard > 30 ? 'color:var(--red)' : c.retard > 0 ? 'color:var(--warn)' : '';
                return '<tr><td>' + c.code + '</td><td>' + c.nom + '</td>' +
                       '<td>' + fmt.money(c.solde) + '</td>' +
                       '<td style="font-weight:700;color:var(--red)">' + fmt.money(c.fns) + '</td>' +
                       '<td style="' + col + '">' + c.retard + 'j</td>' +
                       '<td>' + (c.mdp ? fmt.money(c.mdp) : '-') + '</td>' +
                       '<td>' + (c.telephone || '-') + '</td></tr>';
            }).join('');
        }
        // Grand Livre du commercial (portefeuille uniquement)
        var mv = document.getElementById('cockpit-mvt-tbody');
        if (mv) {
            var gl = d.grand_livre || d.mouvements || [];
            if (!gl.length) { tableVide('cockpit-mvt-tbody', 11, 'Aucun mouvement'); }
            else mv.innerHTML = gl.slice(0,300).map(function(r) {
                var retCol = r.retard > 30 ? 'color:var(--red)' : r.retard > 0 ? 'color:var(--warn)' : '';
                var bgRow  = r.is_total ? 'background:rgba(251,192,19,.08);font-weight:700' : '';
                return '<tr style="' + bgRow + '"><td>' + (r.code||'-') + '</td><td>' + (r.nom||'-') + '</td>' +
                       '<td>' + fmt.date(r.date) + '</td><td>' + (r.piece||'-') + '</td>' +
                       '<td style="max-width:180px;overflow:hidden;white-space:nowrap">' + (r.libelle||'-') + '</td>' +
                       '<td style="text-align:right">' + (r.debit?fmt.money(r.debit):'') + '</td>' +
                       '<td style="text-align:right;color:var(--green)">' + (r.credit?fmt.money(r.credit):'') + '</td>' +
                       '<td>' + (r.statut||'-') + '</td>' +
                       '<td style="text-align:right;color:var(--red)">' + (r.ouvert?fmt.money(r.ouvert):'') + '</td>' +
                       '<td style="' + retCol + '">' + fmt.date(r.echeance) + '</td>' +
                       '<td style="' + retCol + ';font-weight:700">' + (r.retard>0?r.retard+'j':'') + '</td></tr>';
            }).join('');
        }
    });
}

// ── Tendances ──────────────────────────────────────────────────

function setGran(g) {
    var el = document.getElementById('tend-gran');
    if (el) el.value = g;
    document.querySelectorAll('[data-gran]').forEach(function(b) {
        b.className = b.getAttribute('data-gran') === g
            ? 'btn btn-navy btn-sm' : 'btn btn-outline btn-sm';
    });
    chargerTendances();
}

function _valeurPeriode(p, vue) {
    if (vue === 'CA') return p.ca || 0;
    if (vue === 'Recouvrement') return p.recouvrement || 0;
    return p.fns || 0;
}

function chargerTendances() {
    var gran = document.getElementById('tend-gran')  ? document.getElementById('tend-gran').value  : 'mensuel';
    var vue  = document.getElementById('tend-vue')   ? document.getElementById('tend-vue').value   : 'CA';
    var com  = document.getElementById('tend-com')   ? document.getElementById('tend-com').value   : '';
    var url  = '/api/commercial/tendances?granularite=' + gran + '&vue=' + vue;
    if (com) url += '&commercial=' + encodeURIComponent(com);
    tableLoader('tend-tbody', 5);
    apiGet(url, function(d) {
        var periodes = d.periodes || [];
        var tbody    = document.getElementById('tend-tbody');
        if (!tbody) return;
        if (!periodes.length) { tableVide('tend-tbody', 5, 'Aucune donnee'); return; }
        tbody.innerHTML = periodes.map(function(p) {
            var val   = vue === 'CA' ? (p.ca||0) : vue === 'Recouvrement' ? (p.recouvrement||0) : (p.fns||0);
            var evol  = p.evol || '';
            var evolCol = evol.indexOf('▲') >= 0 ? 'color:var(--green)' : evol.indexOf('▼') >= 0 ? 'color:var(--red)' : '';
            var ecart = (p.ecart !== undefined && p.ecart !== '') ? fmt.money(p.ecart) : '-';
            var extra = vue === 'CA' ? (p.taux_rec || '-') : vue === 'Creances' ? (p.risque || '-') : '-';
            return '<tr><td style="font-weight:700">' + p.periode + '</td>' +
                   '<td style="color:var(--gold);font-weight:700">' + fmt.money(val) + '</td>' +
                   '<td style="' + evolCol + ';font-weight:700">' + evol + '</td>' +
                   '<td>' + ecart + '</td>' +
                   '<td>' + extra + '</td></tr>';
        }).join('');
        // Dessiner le graphique
        var canvas = document.getElementById('tend-chart');
        if (canvas && typeof Chart !== 'undefined') {
            if (_tendChart) _tendChart.destroy();
            var labels = periodes.map(function(p){ return p.periode; });
            var values = periodes.map(function(p){ return _valeurPeriode(p, vue); });
            _tendChart = new Chart(canvas, {
                type: 'bar',
                data: {
                    labels: labels,
                    datasets: [{
                        label: vue,
                        data: values,
                        backgroundColor: 'rgba(251,192,19,0.7)',
                        borderColor: '#FBC013',
                        borderWidth: 1,
                    }]
                },
                options: {
                    responsive: true,
                    plugins: {legend:{display:false}},
                    scales: {
                        y: {ticks:{callback:function(v){ return fmt.money(v); }}}
                    }
                }
            });
        }
    });
}

// ── Analyse CA avec sélecteur universel ───────────────────────

function initCASelector() {
    if (_caSelector) return;
    _caSelector = nexoraCreateSelector({
        containerId:  'ca-selector',
        granularites: ['semaine','mois','trimestre','annee'],
        defaut:       'mois',
        maxPeriodes:  3,
        onAnalyser:   function(periodes) {
            chargerCAAvecPeriodes(periodes);
        }
    });
    _caSelector.analyser();
}

function chargerCAAvecPeriodes(periodes) {
    if (!periodes || !periodes.length) return;
    var p1 = periodes[0];
    apiGet('/api/commercial/analyse-ca?debut=' + p1.debut + '&fin=' + p1.fin, function(d1) {
        if (periodes.length > 1) {
            var valeurs = [d1.total_ca || 0];
            var pending = periodes.length - 1;
            periodes.slice(1).forEach(function(p, idx) {
                apiGet('/api/commercial/analyse-ca?debut=' + p.debut + '&fin=' + p.fin, function(dN) {
                    valeurs[idx+1] = dN.total_ca || 0;
                    pending--;
                    if (pending === 0) nexoraAfficherComparaison('ca-comparaison', periodes, valeurs, 'FCFA');
                }, function() { valeurs[idx+1] = 0; pending--; if(pending===0) nexoraAfficherComparaison('ca-comparaison',periodes,valeurs,'FCFA'); });
            });
        } else {
            var compEl = document.getElementById('ca-comparaison');
            if (compEl) compEl.innerHTML =
                '<div class="card" style="border-left:4px solid var(--navy)">' +
                '<div style="font-size:10px;font-weight:700;color:var(--muted)">' + (p1.label||'') + '</div>' +
                '<div style="font-size:20px;font-weight:800;color:var(--navy)">' + fmt.money(d1.total_ca||0) + '</div>' +
                '<div style="font-size:11px;color:var(--muted)">' + (d1.nb_factures||0) + ' factures</div></div>';
        }
        if (_caSelector) _caSelector.setStatus('');
    });
}

// ── Fiches Clients ─────────────────────────────────────────────

function chargerClients() {
    var q = document.getElementById('cli-search') ? document.getElementById('cli-search').value : '';
    tableLoader('clients-tbody', 6);
    apiGet('/api/commercial/clients?q=' + encodeURIComponent(q), function(d) {
        var tbody = document.getElementById('clients-tbody');
        if (!tbody) return;
        if (!d.clients || !d.clients.length) { tableVide('clients-tbody', 6, 'Aucun client'); return; }
        tbody.innerHTML = d.clients.map(function(c) {
            return '<tr>' +
                   '<td style="font-weight:700;color:var(--navy)">' + (c.code_client||'-') + '</td>' +
                   '<td>' + (c.nom||'-') + '</td>' +
                   '<td>' + (c.telephone||'-') + '</td>' +
                   '<td>' + (c.ville||'-') + '</td>' +
                   '<td>' + (c.commercial_attitree||'-') + '</td>' +
                   '<td style="color:var(--gold)">' + fmt.money(c.plafond_credit||0) + '</td>' +
                   '</tr>';
        }).join('');
    });
}

function creerClient() {
    var code = document.getElementById('c-code') ? document.getElementById('c-code').value.trim() : '';
    var nom  = document.getElementById('c-nom')  ? document.getElementById('c-nom').value.trim()  : '';
    if (!code || !nom) { alert('Code et nom obligatoires'); return; }
    var data = {
        code_client: code, nom: nom,
        telephone:   document.getElementById('c-tel')     ? document.getElementById('c-tel').value     : '',
        ville:       document.getElementById('c-ville')   ? document.getElementById('c-ville').value   : '',
        commercial_attitree: document.getElementById('c-com') ? document.getElementById('c-com').value : '',
        plafond_credit: document.getElementById('c-plafond') ? parseFloat(document.getElementById('c-plafond').value)||0 : 0,
        delai_paiement: document.getElementById('c-delai')   ? parseInt(document.getElementById('c-delai').value)||30   : 30,
    };
    apiPost('/api/commercial/clients', data, function() {
        fermerModal('modal-client'); chargerClients(); status('Client cree');
    });
}

// ── Objectifs ──────────────────────────────────────────────────

function chargerObjectifs() {
    tableLoader('objectifs-tbody', 5);
    apiGet('/api/commercial/objectifs', function(d) {
        var tbody = document.getElementById('objectifs-tbody');
        if (!tbody) return;
        if (!d.objectifs || !d.objectifs.length) { tableVide('objectifs-tbody', 5, 'Aucun objectif'); return; }
        tbody.innerHTML = d.objectifs.map(function(o) {
            return '<tr>' +
                   '<td style="font-weight:700">' + (o.commercial||'-') + '</td>' +
                   '<td>' + (o.periode||'-') + '</td>' +
                   '<td style="color:var(--gold);font-weight:700">' + fmt.money(o.objectif_ca||0) + '</td>' +
                   '<td>' + fmt.money(o.objectif_recouvrement||0) + '</td>' +
                   '<td>' + (o.objectif_nb_clients||0) + '</td>' +
                   '</tr>';
        }).join('');
    });
}

function creerObjectif() {
    var com = document.getElementById('obj-com') ? document.getElementById('obj-com').value.trim() : '';
    var per = document.getElementById('obj-per') ? document.getElementById('obj-per').value.trim() : '';
    if (!com || !per) { alert('Commercial et periode obligatoires'); return; }
    var data = {
        commercial: com, periode: per,
        objectif_ca:            document.getElementById('obj-ca')  ? parseFloat(document.getElementById('obj-ca').value)||0  : 0,
        objectif_recouvrement:  document.getElementById('obj-rec') ? parseFloat(document.getElementById('obj-rec').value)||0 : 0,
        objectif_nb_clients:    document.getElementById('obj-nb')  ? parseInt(document.getElementById('obj-nb').value)||0    : 0,
    };
    apiPost('/api/commercial/objectifs', data, function() {
        fermerModal('modal-objectif'); chargerObjectifs(); status('Objectif enregistre');
    });
}

// ── Reaction au changement de periode globale ────────────────────
// Sans ce listener, cliquer "Appliquer" sur la barre de periode ne
// recharge jamais les donnees affichees : l'utilisateur change la
// periode mais voit toujours les anciens chiffres jusqu'au prochain
// changement manuel d'onglet.
document.addEventListener('nexora:periode-changed', function() {
    var active = document.querySelector('#content .section.active');
    if (!active) return;
    var id = active.id || '';
    if (id === 's-com-dashboard')   chargerDashCom();
    else if (id === 's-com-classement') chargerClassement();
    else if (id === 's-com-cockpit') {
        var sel = document.getElementById('cockpit-com-sel');
        if (sel && sel.value) chargerCockpit();
    }
    // Tendances et Analyse CA gerent leur propre periode independamment
    // (voir commentaire dans chargerTendances) — pas de rechargement ici.
});

// ── Init ────────────────────────────────────────────────────────

document.addEventListener('DOMContentLoaded', function() {
    chargerDashCom();
    chargerClassement();
});
