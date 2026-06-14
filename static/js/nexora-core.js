/**
 * NEXORA Core JS v2.0
 * Navigation, utilitaires communs
 * Regle : pas de template literals avec apostrophes francaises
 * Regle : .then(function(){}) au lieu de async/await
 */

// -- Utilitaires formatage --------------------------------------------------
var fmt = {
    money: function(v) {
        return (parseFloat(v) || 0).toLocaleString('fr-FR',
            {minimumFractionDigits: 0, maximumFractionDigits: 0}) + ' FCFA';
    },
    qty: function(v) {
        return (parseFloat(v) || 0).toLocaleString('fr-FR',
            {minimumFractionDigits: 0, maximumFractionDigits: 2});
    },
    date: function(v) {
        return v ? String(v).substring(0, 10) : '—';
    },
    pct: function(v) {
        return (parseFloat(v) || 0).toFixed(1) + '%';
    }
};

// -- Badge --------------------------------------------------------------------
function badge(txt, type) {
    type = type || 'info';
    var cls = {ok: 'b-ok', warn: 'b-warn', err: 'b-err',
               info: 'b-info', muted: 'b-muted'}[type] || 'b-info';
    return '<span class="badge ' + cls + '">' + txt + '</span>';
}

// -- Barre de statut ------------------------------------------------------------
function status(msg) {
    var el = document.getElementById('sbar-txt');
    if (el) el.textContent = msg;
    setTimeout(function() {
        if (el) el.textContent = 'NEXORA v2.0 — Pret';
    }, 4000);
}

// -- Navigation principale --------------------------------------------------------
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

// -- Navigation sous-onglets (groupes) ---------------------------------------------
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

// -- Toggle groupe sidebar ------------------------------------------------------
function toggleGroup(btn) {
    btn.classList.toggle('open');
    var ch = btn.nextElementSibling;
    if (ch) ch.classList.toggle('open');
}

// -- Modals -----------------------------------------------------------------------
function ouvrirModal(id) {
    var el = document.getElementById(id);
    if (el) el.classList.add('open');
}
function fermerModal(id) {
    var el = document.getElementById(id);
    if (el) el.classList.remove('open');
}

// -- Selecteur de periode -----------------------------------------------------------
function setPeriode(hiddenId, val) {
    var el = document.getElementById(hiddenId);
    if (el) el.value = val;
    var parent = el ? el.parentElement : null;
    if (parent) {
        parent.querySelectorAll('[data-periode]').forEach(function(b) {
            b.className = b.getAttribute('data-periode') === val
                ? 'btn btn-navy btn-sm'
                : 'btn btn-outline btn-sm';
        });
    }
}

// -- Boutons periode standard ---------------------------------------------------------
function periodeButtons(hiddenId, onchange) {
    var btns = [
        {val: 'jour',    label: "Aujourd'hui"},
        {val: 'semaine', label: 'Semaine'},
        {val: 'mois',    label: 'Ce mois'},
        {val: 'mois-1',  label: 'Mois prec.'},
        {val: 'annee',   label: '12 mois'}
    ];
    var html = '<div style="display:flex;gap:4px;flex-wrap:wrap">';
    btns.forEach(function(b) {
        var cls = b.val === 'mois' ? 'btn btn-navy btn-sm' : 'btn btn-outline btn-sm';
        html += '<button class="' + cls + '" data-periode="' + b.val + '"' +
                ' onclick="setPeriode(\'' + hiddenId + '\',\'' + b.val + '\');' +
                (onchange || '') + '">' + b.label + '</button>';
    });
    html += '</div><input type="hidden" id="' + hiddenId + '" value="mois">';
    return html;
}

// -- Requete API standard -----------------------------------------------------------
function apiGet(url, callback, errCallback) {
    fetch(url)
        .then(function(r) { return r.json(); })
        .then(function(d) {
            if (d.ok) {
                callback(d);
            } else {
                if (errCallback) errCallback(d.msg || d.error || 'Erreur');
                else status('⚠ ' + (d.msg || 'Erreur'));
            }
        })
        .catch(function(e) {
            if (errCallback) errCallback(e.message);
            else status('⚠ Connexion impossible');
        });
}

function apiPost(url, data, callback, errCallback) {
    fetch(url, {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify(data)
    })
    .then(function(r) { return r.json(); })
    .then(function(d) {
        if (d.ok) {
            callback(d);
        } else {
            if (errCallback) errCallback(d.msg || d.error || 'Erreur');
            else status('⚠ ' + (d.msg || 'Erreur'));
        }
    })
    .catch(function(e) {
        if (errCallback) errCallback(e.message);
        else status('⚠ Connexion impossible');
    });
}

// -- Tableau vide -------------------------------------------------------------------
function emptyTable(tbody, cols, msg) {
    msg = msg || 'Aucune donnee';
    var el = document.getElementById(tbody);
    if (el) el.innerHTML = '<tr><td colspan="' + cols +
        '" class="tbl-empty">' + msg + '</td></tr>';
}

// -- Loader dans un tableau ----------------------------------------------------------
function loadingTable(tbody, cols) {
    var el = document.getElementById(tbody);
    if (el) el.innerHTML = '<tr><td colspan="' + cols +
        '" class="tbl-empty"><span class="loader"></span> Chargement...</td></tr>';
}
