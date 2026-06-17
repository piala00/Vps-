/**
 * NEXORA v2.0 — Core JavaScript
 * Navigation, utilitaires, helpers communs
 * Regles: pas de template literals avec apostrophes francaises
 *         .then(function(){}) au lieu de async/await
 */

// ── Formatage ────────────────────────────────────────────────────
var fmt = {
    money: function(v) {
        return (parseFloat(v) || 0).toLocaleString('fr-FR', {
            minimumFractionDigits: 0, maximumFractionDigits: 0
        }) + ' FCFA';
    },
    qty: function(v) {
        return (parseFloat(v) || 0).toLocaleString('fr-FR', {
            minimumFractionDigits: 0, maximumFractionDigits: 2
        });
    },
    date: function(v) {
        return v ? String(v).substring(0, 10) : '-';
    },
    pct: function(v) {
        return (parseFloat(v) || 0).toFixed(1) + '%';
    },
    delta: function(v, ref) {
        if (!ref || ref === 0) return '';
        var p = ((v - ref) / ref * 100).toFixed(1);
        return (p >= 0 ? '+' : '') + p + '%';
    }
};

// ── Badge HTML ───────────────────────────────────────────────────
function badge(txt, type) {
    type = type || 'info';
    var cls = {
        ok:    'b-ok',
        warn:  'b-warn',
        err:   'b-err',
        info:  'b-info',
        muted: 'b-muted',
        navy:  'b-navy',
        gold:  'b-gold'
    }[type] || 'b-info';
    return '<span class="badge ' + cls + '">' + txt + '</span>';
}

// ── Barre de statut ──────────────────────────────────────────────
function status(msg) {
    var el = document.getElementById('sbar-txt');
    if (el) {
        el.textContent = msg;
        setTimeout(function() {
            el.textContent = 'NEXORA v2.0 - Pret';
        }, 4000);
    }
}

// ── Navigation principale ────────────────────────────────────────
function nav(name) {
    document.querySelectorAll('#content .section').forEach(function(s) {
        s.classList.remove('active');
    });
    document.querySelectorAll('#sidebar .nav-item').forEach(function(b) {
        b.classList.remove('active');
    });
    var sec = document.getElementById('s-' + name);
    if (sec) sec.classList.add('active');
    var btn = document.querySelector('#sidebar .nav-item[data-nav="' + name + '"]');
    if (btn) btn.classList.add('active');
    if (typeof autoLoad !== 'undefined' && autoLoad[name]) {
        autoLoad[name]();
    }
}

// ── Navigation sous-onglets ──────────────────────────────────────
function navSub(btn, name) {
    document.querySelectorAll('#sidebar .nav-item-sub').forEach(function(b) {
        b.classList.remove('active');
    });
    btn.classList.add('active');
    var grp = btn.closest('.nav-group-children');
    if (grp && !grp.classList.contains('open')) {
        grp.classList.add('open');
        var gbtn = grp.previousElementSibling;
        if (gbtn) gbtn.classList.add('open');
    }
    document.querySelectorAll('#content .section').forEach(function(s) {
        s.classList.remove('active');
    });
    var sec = document.getElementById('s-' + name);
    if (sec) sec.classList.add('active');
    if (typeof autoLoad !== 'undefined' && autoLoad[name]) {
        autoLoad[name]();
    }
}

// ── Toggle groupe sidebar ────────────────────────────────────────
function toggleGroup(btn) {
    btn.classList.toggle('open');
    var ch = btn.nextElementSibling;
    if (ch) ch.classList.toggle('open');
}

// ── Modals ───────────────────────────────────────────────────────
function ouvrirModal(id) {
    var el = document.getElementById(id);
    if (el) el.classList.add('open');
}
function fermerModal(id) {
    var el = document.getElementById(id);
    if (el) el.classList.remove('open');
}

// ── Helpers tableau ──────────────────────────────────────────────
function tableVide(tbodyId, cols, msg) {
    msg = msg || 'Aucune donnee';
    var el = document.getElementById(tbodyId);
    if (el) {
        el.innerHTML = '<tr><td colspan="' + cols +
            '" class="tbl-empty">' + msg + '</td></tr>';
    }
}
function tableLoader(tbodyId, cols) {
    var el = document.getElementById(tbodyId);
    if (el) {
        el.innerHTML = '<tr><td colspan="' + cols +
            '" class="tbl-empty"><span class="loader"></span> Chargement...</td></tr>';
    }
}

// ── Selecteur de periode ──────────────────────────────────────────
function setPeriode(hiddenId, val, callback) {
    var el = document.getElementById(hiddenId);
    if (el) el.value = val;
    var parent = el ? el.parentElement : null;
    if (parent) {
        parent.querySelectorAll('[data-per]').forEach(function(b) {
            b.className = b.getAttribute('data-per') === val
                ? 'btn btn-navy btn-sm'
                : 'btn btn-outline btn-sm';
        });
    }
    if (typeof callback === 'function') callback();
}

function htmlPeriodeBtns(hiddenId, callbackName, defaultVal) {
    defaultVal = defaultVal || 'mois';
    var btns = [
        ['jour',   "Aujourd'hui"],
        ['semaine','Semaine'],
        ['mois',   'Ce mois'],
        ['mois-1', 'Mois prec.'],
        ['annee',  '12 mois']
    ];
    var html = '<div style="display:flex;gap:4px;flex-wrap:wrap">';
    for (var i = 0; i < btns.length; i++) {
        var val = btns[i][0];
        var lbl = btns[i][1];
        var cls = val === defaultVal ? 'btn btn-navy btn-sm' : 'btn btn-outline btn-sm';
        html += '<button class="' + cls + '" data-per="' + val + '"' +
                ' onclick="setPeriode(\'' + hiddenId + '\',\'' + val + '\',' + callbackName + ')">' +
                lbl + '</button>';
    }
    html += '</div>';
    html += '<input type="hidden" id="' + hiddenId + '" value="' + defaultVal + '">';
    return html;
}

// ── Requetes API ──────────────────────────────────────────────────
function apiGet(url, onSuccess, onError) {
    fetch(url)
        .then(function(r) { return r.json(); })
        .then(function(d) {
            if (d.ok !== false) {
                if (typeof onSuccess === 'function') onSuccess(d);
            } else {
                var msg = d.msg || d.error || 'Erreur';
                if (typeof onError === 'function') onError(msg);
                else status('Erreur: ' + msg);
            }
        })
        .catch(function(e) {
            var msg = e.message || 'Connexion impossible';
            if (typeof onError === 'function') onError(msg);
            else status('Connexion impossible');
        });
}

function apiPost(url, data, onSuccess, onError) {
    fetch(url, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(data)
    })
    .then(function(r) { return r.json(); })
    .then(function(d) {
        if (d.ok !== false) {
            if (typeof onSuccess === 'function') onSuccess(d);
        } else {
            var msg = d.msg || d.error || 'Erreur';
            if (typeof onError === 'function') onError(msg);
            else status('Erreur: ' + msg);
        }
    })
    .catch(function(e) {
        var msg = e.message || 'Connexion impossible';
        if (typeof onError === 'function') onError(msg);
        else status('Connexion impossible');
    });
}

// ── KPI Card HTML ─────────────────────────────────────────────────
function kpiCard(ico, label, val, borderColor, delta) {
    borderColor = borderColor || 'var(--navy)';
    var deltaHtml = '';
    if (delta !== undefined) {
        var cls = delta >= 0 ? 'color:#10B981' : 'color:#EF4444';
        deltaHtml = '<div class="kdelta" style="' + cls + '">' +
                    (delta >= 0 ? '+' : '') + delta + '%</div>';
    }
    return '<div class="kpi-card" style="border-left-color:' + borderColor + '">' +
           '<div class="kico">' + ico + '</div>' +
           '<div class="klabel">' + label + '</div>' +
           '<div class="kval">' + val + '</div>' +
           deltaHtml + '</div>';
}

// ── Shortcut Button HTML ──────────────────────────────────────────
function shortcutBtn(ico, label, onclick) {
    return '<button class="shortcut-btn" onclick="' + onclick + '">' +
           '<span style="font-size:22px">' + ico + '</span>' +
           '<span>' + label + '</span></button>';
}

console.log('NEXORA Core JS v2.0 charge');

// ════════════════════════════════════════════════════════════════
// NEXORA — Composant Universel d'Analyse
// Sélecteur de période adaptatif — réutilisé dans tous les modules
// ════════════════════════════════════════════════════════════════

var NEXORA_MOIS = [
    'Janvier','Février','Mars','Avril','Mai','Juin',
    'Juillet','Août','Septembre','Octobre','Novembre','Décembre'
];

var NEXORA_MOIS_COURT = [
    'Jan','Fév','Mar','Avr','Mai','Jun',
    'Jul','Aoû','Sep','Oct','Nov','Déc'
];

// ── Utilitaires de dates ─────────────────────────────────────────

function nexoraAnneeActuelle() {
    return new Date().getFullYear();
}

function nexoraMoisActuel() {
    return new Date().getMonth() + 1; // 1-12
}

function nexoraTrimestreActuel() {
    return Math.ceil(nexoraMoisActuel() / 3); // 1-4
}

function nexoraSemaineActuelle() {
    var d = new Date();
    d.setHours(0,0,0,0);
    d.setDate(d.getDate() + 4 - (d.getDay() || 7));
    var yearStart = new Date(d.getFullYear(), 0, 1);
    return Math.ceil((((d - yearStart) / 86400000) + 1) / 7);
}

function nexoraDateDebutFin(type, valeur, annee) {
    var debut, fin;
    var a = annee || nexoraAnneeActuelle();

    if (type === 'annee') {
        debut = a + '-01-01';
        fin   = a + '-12-31';

    } else if (type === 'trimestre') {
        var t = valeur || nexoraTrimestreActuel();
        var moisDebut = (t - 1) * 3 + 1;
        var moisFin   = t * 3;
        debut = a + '-' + pad2(moisDebut) + '-01';
        fin   = a + '-' + pad2(moisFin)   + '-' + dernierJour(a, moisFin);

    } else if (type === 'mois') {
        var m = valeur || nexoraMoisActuel();
        debut = a + '-' + pad2(m) + '-01';
        fin   = a + '-' + pad2(m) + '-' + dernierJour(a, m);

    } else if (type === 'semaine') {
        var s   = valeur || nexoraSemaineActuelle();
        var jan = new Date(a, 0, 1);
        var jourSemaine = jan.getDay() || 7;
        var lundi = new Date(jan.getTime() + ((s-1)*7 - jourSemaine + 1) * 86400000);
        var dimanche = new Date(lundi.getTime() + 6 * 86400000);
        debut = dateToStr(lundi);
        fin   = dateToStr(dimanche);

    } else if (type === 'jour') {
        var parts = valeur.split('-');
        debut = fin = valeur;
    }

    return {debut: debut, fin: fin};
}

function pad2(n) {
    return n < 10 ? '0' + n : '' + n;
}

function dernierJour(annee, mois) {
    return new Date(annee, mois, 0).getDate();
}

function dateToStr(d) {
    return d.getFullYear() + '-' + pad2(d.getMonth()+1) + '-' + pad2(d.getDate());
}

function nexoraLabelPeriode(type, valeur, annee) {
    var a = annee || nexoraAnneeActuelle();
    if (type === 'annee')     return '' + (valeur || a);
    if (type === 'trimestre') return 'T' + (valeur || nexoraTrimestreActuel()) + ' ' + a;
    if (type === 'mois')      return NEXORA_MOIS[(valeur||nexoraMoisActuel())-1] + ' ' + a;
    if (type === 'semaine')   return 'Sem. ' + (valeur || nexoraSemaineActuelle()) + ' / ' + a;
    if (type === 'jour')      return valeur || dateToStr(new Date());
    return '';
}

// ── Générateur d'années disponibles ──────────────────────────────

function nexoraAnneesDisponibles(debut, fin) {
    debut = debut || 2020;
    fin   = fin   || nexoraAnneeActuelle() + 1;
    var result = [];
    for (var y = fin; y >= debut; y--) result.push(y);
    return result;
}

// ── Générateur HTML du sélecteur ─────────────────────────────────

function nexoraSelectAnnee(id, valeur, onChange) {
    var annees = nexoraAnneesDisponibles();
    var html   = '<select id="' + id + '" onchange="' + (onChange||'') + '" style="' + NEXORA_SEL_STYLE + '">';
    annees.forEach(function(a) {
        html += '<option value="' + a + '"' + (a == valeur ? ' selected' : '') + '>' + a + '</option>';
    });
    html += '</select>';
    return html;
}

function nexoraSelectMois(id, valeur, onChange) {
    var html = '<select id="' + id + '" onchange="' + (onChange||'') + '" style="' + NEXORA_SEL_STYLE + '">';
    for (var m = 1; m <= 12; m++) {
        html += '<option value="' + m + '"' + (m == valeur ? ' selected' : '') + '>' + NEXORA_MOIS[m-1] + '</option>';
    }
    html += '</select>';
    return html;
}

function nexoraSelectTrimestre(id, valeur, onChange) {
    var html = '<select id="' + id + '" onchange="' + (onChange||'') + '" style="' + NEXORA_SEL_STYLE + '">';
    for (var t = 1; t <= 4; t++) {
        html += '<option value="' + t + '"' + (t == valeur ? ' selected' : '') + '>T' + t + '</option>';
    }
    html += '</select>';
    return html;
}

function nexoraSelectSemaine(id, valeur, onChange) {
    var html = '<select id="' + id + '" onchange="' + (onChange||'') + '" style="' + NEXORA_SEL_STYLE + '">';
    for (var s = 1; s <= 53; s++) {
        html += '<option value="' + s + '"' + (s == valeur ? ' selected' : '') + '>Sem. ' + s + '</option>';
    }
    html += '</select>';
    return html;
}

var NEXORA_SEL_STYLE = 'padding:6px 10px;border:2px solid var(--border);border-radius:7px;font-size:12px;color:var(--text);background:var(--bg-card);outline:none;cursor:pointer';

// ── Composant Principal NexoraPeriodSelector ──────────────────────

function NexoraPeriodSelector(options) {
    this.containerId  = options.containerId;
    this.granularites = options.granularites || ['jour','semaine','mois','trimestre','annee'];
    this.defaut       = options.defaut       || 'mois';
    this.maxPeriodes  = options.maxPeriodes  || 3;
    this.onAnalyser   = options.onAnalyser   || function(){};
    this.granularite  = this.defaut;
    this.nbPeriodes   = 2;
    this._id          = this.containerId.replace(/[^a-z0-9]/gi,'_');
    this.render();
}

NexoraPeriodSelector.prototype.render = function() {
    var self      = this;
    var container = document.getElementById(this.containerId);
    if (!container) return;

    // Labels des granularités
    var labelsGran = {
        'jour':'Jour', 'semaine':'Semaine',
        'mois':'Mois', 'trimestre':'Trimestre', 'annee':'Année'
    };

    // Boutons granularité
    var btnsHtml = '<div style="display:flex;gap:4px;flex-wrap:wrap;margin-bottom:10px">';
    this.granularites.forEach(function(g) {
        var actif = g === self.granularite ? 'btn-navy' : 'btn-outline';
        btnsHtml += '<button id="' + self._id + '_gran_' + g + '" class="btn ' + actif + ' btn-sm"' +
                    ' onclick="nexoraSelectors[\'' + self._id + '\'].setGranularite(\'' + g + '\')">' +
                    labelsGran[g] + '</button>';
    });
    btnsHtml += '</div>';

    // Zone périodes
    var periodesHtml = '<div id="' + this._id + '_periodes" style="margin-bottom:10px"></div>';

    // Bouton ajouter période + analyser
    var actionsHtml =
        '<div style="display:flex;gap:8px;align-items:center;flex-wrap:wrap">' +
        (this.maxPeriodes > 1 ?
            '<button class="btn btn-outline btn-sm" onclick="nexoraSelectors[\'' + self._id + '\'].addPeriode()">+ Période</button>' : '') +
        '<button class="btn btn-gold" style="padding:8px 20px;font-weight:700" onclick="nexoraSelectors[\'' + self._id + '\'].analyser()">📊 Analyser</button>' +
        '<div id="' + self._id + '_status" style="font-size:11px;color:var(--muted)"></div>' +
        '</div>';

    container.innerHTML = btnsHtml + periodesHtml + actionsHtml;

    this.renderPeriodes();
};

NexoraPeriodSelector.prototype.renderPeriodes = function() {
    var self = this;
    var zone = document.getElementById(this._id + '_periodes');
    if (!zone) return;

    var html = '';
    for (var i = 0; i < this.nbPeriodes; i++) {
        html += this._renderUnePeriode(i);
    }
    zone.innerHTML = html;
};

NexoraPeriodSelector.prototype._renderUnePeriode = function(idx) {
    var self   = this;
    var id     = this._id + '_p' + idx;
    var labels = ['Période 1 (référence)', 'Période 2', 'Période 3'];
    var g      = this.granularite;
    var a      = nexoraAnneeActuelle();
    var onChange = 'nexoraSelectors[\'' + self._id + '\']._updateSousTitre(' + idx + ')';

    // Valeurs par défaut selon granularité et index
    var defauts = this._defautsPeriode(g, idx);

    var html = '<div style="display:flex;align-items:center;gap:8px;margin-bottom:6px;flex-wrap:wrap">';
    html    += '<span style="font-size:11px;font-weight:700;color:var(--muted);min-width:120px">' + labels[idx] + '</span>';

    if (g === 'annee') {
        html += nexoraSelectAnnee(id + '_annee', defauts.annee, onChange);

    } else if (g === 'trimestre') {
        html += nexoraSelectTrimestre(id + '_trim', defauts.valeur, onChange);
        html += '<span style="font-size:11px;color:var(--muted)">de</span>';
        html += nexoraSelectAnnee(id + '_annee', defauts.annee, onChange);

    } else if (g === 'mois') {
        html += nexoraSelectMois(id + '_mois', defauts.valeur, onChange);
        html += nexoraSelectAnnee(id + '_annee', defauts.annee, onChange);

    } else if (g === 'semaine') {
        html += nexoraSelectSemaine(id + '_sem', defauts.valeur, onChange);
        html += '<span style="font-size:11px;color:var(--muted)">de</span>';
        html += nexoraSelectAnnee(id + '_annee', defauts.annee, onChange);

    } else if (g === 'jour') {
        html += '<input type="date" id="' + id + '_date" value="' + defauts.dateStr + '"' +
                ' style="' + NEXORA_SEL_STYLE + '" onchange="' + onChange + '">';
    }

    // Sous-titre (dates exactes pour semaine)
    html += '<span id="' + id + '_sous" style="font-size:10px;color:var(--muted);font-style:italic"></span>';

    // Bouton supprimer (sauf période 1)
    if (idx > 0) {
        html += '<button onclick="nexoraSelectors[\'' + self._id + '\'].removePeriode(' + idx + ')" ' +
                'style="background:transparent;border:none;color:var(--muted);cursor:pointer;font-size:14px">✕</button>';
    }

    html += '</div>';
    return html;
};

NexoraPeriodSelector.prototype._defautsPeriode = function(g, idx) {
    var a = nexoraAnneeActuelle();
    var m = nexoraMoisActuel();
    var t = nexoraTrimestreActuel();
    var s = nexoraSemaineActuelle();
    var today = dateToStr(new Date());
    var hier  = dateToStr(new Date(Date.now() - 86400000));

    var defauts = [
        // Période 1 : en cours
        {annee:a, valeur:m, dateStr:today},
        // Période 2 : N-1 ou précédent
        {annee:a-1, valeur:m, dateStr:hier},
        // Période 3 : mois précédent
        {annee:a, valeur:(m===1?12:m-1), dateStr:hier},
    ];

    if (g === 'trimestre') {
        defauts = [
            {annee:a,   valeur:t},
            {annee:a-1, valeur:t},
            {annee:a,   valeur:(t===1?4:t-1)},
        ];
    } else if (g === 'semaine') {
        defauts = [
            {annee:a,   valeur:s},
            {annee:a,   valeur:(s===1?52:s-1)},
            {annee:a-1, valeur:s},
        ];
    } else if (g === 'annee') {
        defauts = [
            {annee:a},
            {annee:a-1},
            {annee:a-2},
        ];
    } else if (g === 'jour') {
        defauts = [
            {dateStr: today},
            {dateStr: hier},
            {dateStr: hier},
        ];
    }

    return defauts[idx] || defauts[0];
};

NexoraPeriodSelector.prototype.setGranularite = function(g) {
    this.granularite = g;
    this.nbPeriodes  = (g === 'jour' || g === 'semaine') ? 2 : 2;
    this.render();
};

NexoraPeriodSelector.prototype.addPeriode = function() {
    if (this.nbPeriodes < this.maxPeriodes) {
        this.nbPeriodes++;
        this.renderPeriodes();
    }
};

NexoraPeriodSelector.prototype.removePeriode = function(idx) {
    if (this.nbPeriodes > 1) {
        this.nbPeriodes--;
        this.renderPeriodes();
    }
};

NexoraPeriodSelector.prototype._updateSousTitre = function(idx) {
    var id   = this._id + '_p' + idx;
    var sous = document.getElementById(id + '_sous');
    if (!sous) return;
    var p = this._lirePeriode(idx);
    if (!p) return;
    if (this.granularite === 'semaine') {
        var dates = nexoraDateDebutFin('semaine', p.valeur, p.annee);
        sous.textContent = '(' + dates.debut + ' → ' + dates.fin + ')';
    } else {
        sous.textContent = '';
    }
};

NexoraPeriodSelector.prototype._lirePeriode = function(idx) {
    var id = this._id + '_p' + idx;
    var g  = this.granularite;
    var result = {type: g};

    if (g === 'annee') {
        var anneeEl = document.getElementById(id + '_annee');
        if (!anneeEl) return null;
        result.annee  = parseInt(anneeEl.value);
        result.valeur = result.annee;

    } else if (g === 'trimestre') {
        var trimEl  = document.getElementById(id + '_trim');
        var anneeEl2 = document.getElementById(id + '_annee');
        if (!trimEl || !anneeEl2) return null;
        result.valeur = parseInt(trimEl.value);
        result.annee  = parseInt(anneeEl2.value);

    } else if (g === 'mois') {
        var moisEl  = document.getElementById(id + '_mois');
        var anneeEl3 = document.getElementById(id + '_annee');
        if (!moisEl || !anneeEl3) return null;
        result.valeur = parseInt(moisEl.value);
        result.annee  = parseInt(anneeEl3.value);

    } else if (g === 'semaine') {
        var semEl   = document.getElementById(id + '_sem');
        var anneeEl4 = document.getElementById(id + '_annee');
        if (!semEl || !anneeEl4) return null;
        result.valeur = parseInt(semEl.value);
        result.annee  = parseInt(anneeEl4.value);

    } else if (g === 'jour') {
        var dateEl = document.getElementById(id + '_date');
        if (!dateEl) return null;
        result.valeur   = dateEl.value;
        result.dateStr  = dateEl.value;
        var parts = dateEl.value.split('-');
        result.annee  = parseInt(parts[0]);
        result.valeur = dateEl.value;
    }

    // Calculer les dates début et fin
    var dates     = nexoraDateDebutFin(g, result.valeur, result.annee);
    result.debut  = dates.debut;
    result.fin    = dates.fin;
    result.label  = nexoraLabelPeriode(g, result.valeur, result.annee);

    return result;
};

NexoraPeriodSelector.prototype.analyser = function() {
    var periodes = [];
    for (var i = 0; i < this.nbPeriodes; i++) {
        var p = this._lirePeriode(i);
        if (p) periodes.push(p);
    }
    if (!periodes.length) return;

    var statusEl = document.getElementById(this._id + '_status');
    if (statusEl) statusEl.textContent = 'Analyse en cours...';

    this.onAnalyser(periodes);
};

NexoraPeriodSelector.prototype.getPeriodes = function() {
    var periodes = [];
    for (var i = 0; i < this.nbPeriodes; i++) {
        var p = this._lirePeriode(i);
        if (p) periodes.push(p);
    }
    return periodes;
};

NexoraPeriodSelector.prototype.setStatus = function(msg) {
    var el = document.getElementById(this._id + '_status');
    if (el) el.textContent = msg || '';
};

// Registre global des sélecteurs (pour accès depuis HTML onclick)
var nexoraSelectors = {};

function nexoraCreateSelector(options) {
    var id  = options.containerId.replace(/[^a-z0-9]/gi,'_');
    var sel = new NexoraPeriodSelector(options);
    nexoraSelectors[id] = sel;
    return sel;
}

// ── Affichage des résultats de comparaison ─────────────────────

function nexoraAfficherComparaison(containerId, periodes, valeurs, unite) {
    var container = document.getElementById(containerId);
    if (!container) return;
    unite = unite || 'FCFA';

    var html = '<div style="display:grid;grid-template-columns:repeat(auto-fill,minmax(200px,1fr));gap:10px">';

    periodes.forEach(function(p, i) {
        var val    = valeurs[i] || 0;
        var fmtVal = unite === 'FCFA' ? fmt.money(val) :
                     unite === 'pct'  ? fmt.pct(val)   :
                     unite === 'nb'   ? fmt.qty(val)   : val;

        var deltaHtml = '';
        if (i > 0 && valeurs[0] !== undefined && valeurs[0] !== 0) {
            var ref   = valeurs[0];
            var delta = ((val - ref) / Math.abs(ref) * 100).toFixed(1);
            var color = parseFloat(delta) >= 0 ? '#10B981' : '#EF4444';
            var arrow = parseFloat(delta) >= 0 ? '↑' : '↓';
            deltaHtml = '<div style="font-size:12px;color:' + color + ';font-weight:700;margin-top:4px">' +
                        arrow + ' ' + (parseFloat(delta) >= 0 ? '+' : '') + delta + '% vs Période 1</div>';
        }

        var borderColor = i === 0 ? 'var(--navy)' : (i === 1 ? 'var(--gold)' : 'var(--green)');
        var badge       = i === 0 ? ' (référence)' : '';

        html += '<div class="card" style="border-left:4px solid ' + borderColor + ';padding:12px">' +
                '<div style="font-size:10px;font-weight:700;color:var(--muted);text-transform:uppercase;margin-bottom:4px">' +
                p.label + badge + '</div>' +
                '<div style="font-size:18px;font-weight:800;color:var(--navy)">' + fmtVal + '</div>' +
                deltaHtml +
                '</div>';
    });

    html += '</div>';
    container.innerHTML = html;
}

console.log('NEXORA Analyse Universelle v2.0 chargee');

// ── Barre de periode globale (Commercial / Comptabilite) ──────────
// Sans une periode coherente et persistante entre les ecrans, le CA, les
// Creances et les Tendances affichent des montants differents pour la
// meme periode (chaque ecran calculant sa propre fenetre par defaut).
// Cette barre centralise le choix et le partage via sessionStorage + URL.

var NEXORA_PERIODE_KEY = 'nexora_periode_active';

function nexoraGetPeriode() {
    try {
        var raw = sessionStorage.getItem(NEXORA_PERIODE_KEY);
        if (raw) return JSON.parse(raw);
    } catch (e) {}
    var today = new Date();
    var debut = today.getFullYear() + '-' + pad2(today.getMonth()+1) + '-01';
    var fin   = dateToStr(today);
    return {debut: debut, fin: fin, label: 'Mois en cours'};
}

function nexoraSetPeriode(debut, fin, label) {
    var p = {debut: debut, fin: fin, label: label || (debut + ' \u2192 ' + fin)};
    try { sessionStorage.setItem(NEXORA_PERIODE_KEY, JSON.stringify(p)); } catch (e) {}
    var lbl = document.getElementById('pb-active-label');
    if (lbl) lbl.textContent = 'Periode active : ' + p.label;
    document.dispatchEvent(new CustomEvent('nexora:periode-changed', {detail: p}));
}

// Ajoute automatiquement debut/fin de la periode active a une URL d'API.
function nexoraAppendPeriode(url) {
    var p = nexoraGetPeriode();
    var sep = url.indexOf('?') >= 0 ? '&' : '?';
    return url + sep + 'debut=' + p.debut + '&fin=' + p.fin;
}

function nexoraInitPeriodeBar() {
    var anneeSel = document.getElementById('pb-annee');
    var moisSel  = document.getElementById('pb-mois');
    var duInp    = document.getElementById('pb-du');
    var auInp    = document.getElementById('pb-au');
    if (!anneeSel) return; // pas sur cet ecran

    var anneeActuelle = nexoraAnneeActuelle();
    anneeSel.innerHTML = '';
    for (var y = anneeActuelle + 1; y >= anneeActuelle - 5; y--) {
        var opt = document.createElement('option');
        opt.value = y; opt.textContent = y;
        if (y === anneeActuelle) opt.selected = true;
        anneeSel.appendChild(opt);
    }
    moisSel.value = nexoraMoisActuel();

    var p = nexoraGetPeriode();
    duInp.value = p.debut;
    auInp.value = p.fin;
    var lbl = document.getElementById('pb-active-label');
    if (lbl) lbl.textContent = 'Periode active : ' + p.label;
}

function nexoraAppliquerPeriode() {
    var annee = document.getElementById('pb-annee') ? document.getElementById('pb-annee').value : nexoraAnneeActuelle();
    var mois  = document.getElementById('pb-mois')  ? document.getElementById('pb-mois').value  : '';
    var du    = document.getElementById('pb-du')    ? document.getElementById('pb-du').value    : '';
    var au    = document.getElementById('pb-au')    ? document.getElementById('pb-au').value    : '';

    var debut, fin, label;
    if (du && au) {
        debut = du; fin = au; label = du + ' \u2192 ' + au;
    } else if (mois) {
        var d = nexoraDateDebutFin('mois', parseInt(mois), parseInt(annee));
        debut = d.debut; fin = d.fin;
        label = NEXORA_MOIS[parseInt(mois)-1] + ' ' + annee;
    } else {
        var d2 = nexoraDateDebutFin('annee', null, parseInt(annee));
        debut = d2.debut; fin = d2.fin;
        label = '' + annee;
    }
    nexoraSetPeriode(debut, fin, label);
}

function nexoraRaccourciPeriode(type) {
    var today = new Date();
    var debut, fin, label;
    if (type === 'annee') {
        debut = today.getFullYear() + '-01-01';
        fin   = dateToStr(today);
        label = 'Cette annee';
    } else if (type === 'mois') {
        debut = today.getFullYear() + '-' + pad2(today.getMonth()+1) + '-01';
        fin   = dateToStr(today);
        label = 'Mois en cours';
    } else if (type === '3mois') {
        var d3 = new Date(today.getTime() - 90*86400000);
        debut = dateToStr(d3);
        fin   = dateToStr(today);
        label = '3 derniers mois';
    }
    var duInp = document.getElementById('pb-du');
    var auInp = document.getElementById('pb-au');
    if (duInp) duInp.value = debut;
    if (auInp) auInp.value = fin;
    nexoraSetPeriode(debut, fin, label);
}

document.addEventListener('DOMContentLoaded', function() {
    nexoraInitPeriodeBar();
});
