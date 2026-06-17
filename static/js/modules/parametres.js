/**
 * NEXORA v2.0 — Module Parametres (COMPLET)
 * Tout ce qui existe dans GTC ERP PILOT V3 AdminFrame
 */

var autoLoad = {
    'param-sage':         function(){ chargerConfigSage(); },
    'param-bases':        function(){ chargerSQLiteInfo(); },
    'param-ref-clients':  function(){ chargerRefClients(); },
    'param-commerciaux':  function(){ chargerCommerciaux(); },
    'param-users':        function(){ chargerUsers(); },
    'param-droits':       function(){ chargerDropdownUsers(); },
    'param-bot':          function(){ chargerBotConfig(); chargerStatutBot(); chargerInscriptionsBot(); },
    'param-licence':      function(){ chargerStatutLicence(); },
    'param-journal':      function(){ chargerJournal(); chargerJournalSage(); },
    'param-reseau':       function(){},
    'param-ip':           function(){ chargerWhitelistIP(); },
    'param-domaine':      function(){},
    'param-vpn':          function(){},
    'param-compilation':  function(){},
};

// ── Utilitaires ───────────────────────────────────────────────
function toggleZone(id) {
    var el = document.getElementById(id);
    if (el) el.style.display = el.style.display === 'none' ? 'block' : 'none';
}

// ── Configuration Sage ────────────────────────────────────────
function chargerConfigSage() {
    apiGet('/api/config/sage', function(d) {
        if (!d.config) return;
        var c = d.config;
        var sets = [
            ['sage-srv', c.sage_server],['sage-db', c.sage_database],
            ['sage-user', c.sage_user]
        ];
        sets.forEach(function(s){ var el=document.getElementById(s[0]); if(el) el.value=s[1]||''; });
        var auth = document.getElementById('sage-auth');
        if (auth) auth.value = c.sage_trusted === '1' ? 'windows' : 'sql';
        toggleSageAuth();
    });
}

function toggleSageAuth() {
    var auth = document.getElementById('sage-auth') ? document.getElementById('sage-auth').value : 'sql';
    var uz   = document.getElementById('sage-user-zone');
    var pz   = document.getElementById('sage-pwd-zone');
    if (uz) uz.style.display = auth === 'windows' ? 'none' : 'block';
    if (pz) pz.style.display = auth === 'windows' ? 'none' : 'block';
}

function testerSageRobuste() {
    var server  = document.getElementById('sage-srv')  ? document.getElementById('sage-srv').value.trim()  : '';
    var db      = document.getElementById('sage-db')   ? document.getElementById('sage-db').value.trim()   : '';
    var auth    = document.getElementById('sage-auth') ? document.getElementById('sage-auth').value        : 'sql';
    var user    = document.getElementById('sage-user') ? document.getElementById('sage-user').value.trim() : 'sa';
    var pwd     = document.getElementById('sage-pwd')  ? document.getElementById('sage-pwd').value         : '';
    var msg     = document.getElementById('sage-msg');
    if (!server || !db) { alert('Serveur et base obligatoires'); return; }
    if (msg) { msg.style.display='block'; msg.style.color='var(--muted)';
               msg.textContent='Test en cours — essai de tous les drivers ODBC...'; }
    apiPost('/api/config/test-sage-robuste', {
        sage_server:   server, sage_database: db,
        sage_trusted:  auth === 'windows',
        sage_user:     user, sage_password: pwd
    }, function(d) {
        if (msg) { msg.style.display='block';
                   msg.style.color=d.ok?'var(--green)':'var(--red)';
                   msg.textContent=d.message||(d.ok?'OK':'Echec'); }
    }, function(e) {
        if (msg) { msg.style.display='block'; msg.style.color='var(--red)'; msg.textContent='Erreur: '+e; }
    });
}

function sauvegarderSage() {
    var server = document.getElementById('sage-srv')  ? document.getElementById('sage-srv').value.trim()  : '';
    var db     = document.getElementById('sage-db')   ? document.getElementById('sage-db').value.trim()   : '';
    var auth   = document.getElementById('sage-auth') ? document.getElementById('sage-auth').value        : 'sql';
    var user   = document.getElementById('sage-user') ? document.getElementById('sage-user').value.trim() : 'sa';
    var pwd    = document.getElementById('sage-pwd')  ? document.getElementById('sage-pwd').value         : '';
    apiPost('/api/config/sage', {
        sage_server: server, sage_database: db,
        sage_trusted: auth==='windows'?'1':'0',
        sage_user: user, sage_password: pwd
    }, function() { status('Configuration Sage sauvegardee'); });
}

// ── Configuration générale (source SQL/Excel) ─────────────────
function chargerConfigGenerale() {
    apiGet('/api/config/general', function(d) {
        if (!d.config) return;
        var c = d.config;
        var srcEl = document.getElementById('src-sql');
        var srcEx = document.getElementById('src-excel');
        if (srcEl) srcEl.checked = c.source === 'sql';
        if (srcEx) srcEx.checked = c.source === 'excel';
        var curEl = document.getElementById('cfg-excel-current');
        if (curEl) curEl.textContent = c.excel_path ? ('Fichier actuel : ' + c.excel_path) : 'Aucun fichier importe pour le moment.';
        toggleSourceMode();
    });
}

function toggleSourceMode() {
    var srcSql = document.getElementById('src-sql');
    var sqlZone = document.getElementById('cfg-sql-zone');
    var exlZone = document.getElementById('cfg-excel-zone');
    var isSql = srcSql && srcSql.checked;
    if (sqlZone) sqlZone.style.display = isSql ? 'block' : 'none';
    if (exlZone) exlZone.style.display = isSql ? 'none' : 'block';
}

function sauvegarderConfigGenerale() {
    var srcSql = document.getElementById('src-sql');
    var source = (srcSql && srcSql.checked) ? 'sql' : 'excel';
    var msg    = document.getElementById('cfg-msg');
    apiPost('/api/config/general', {source: source}, function() {
        if (msg) msg.innerHTML = '<span style="color:var(--green)">Configuration enregistree</span>';
        status('Configuration sauvegardee');
    });
}

function uploaderEtImporterExcel(fileInputId, msgId) {
    fileInputId = fileInputId || 'cfg-excel-file';
    msgId       = msgId || 'cfg-msg';
    var fileInput = document.getElementById(fileInputId);
    var msg = document.getElementById(msgId);
    if (!fileInput || !fileInput.files || !fileInput.files.length) {
        alert('Choisissez un fichier .xlsx avant de cliquer sur Charger & Importer');
        return;
    }
    var file = fileInput.files[0];
    if (msg) msg.innerHTML = '<span style="color:var(--muted)">Envoi du fichier en cours...</span>';

    var formData = new FormData();
    formData.append('file', file);

    fetch('/api/config/upload-excel', { method: 'POST', body: formData })
        .then(function(r) { return r.json(); })
        .then(function(uploadResult) {
            if (!uploadResult.ok) {
                if (msg) msg.innerHTML = '<span style="color:var(--red)">' + (uploadResult.message || 'Echec upload') + '</span>';
                return;
            }
            if (msg) msg.innerHTML = '<span style="color:var(--muted)">Fichier recu, import des donnees en cours...</span>';
            apiPost('/api/config/import-excel', {}, function(d) {
                if (msg) msg.innerHTML = '<span style="color:' + (d.ok ? 'var(--green)' : 'var(--red)') + '">' + (d.message || '') + '</span>';
                if (d.ok) {
                    status(d.message || 'Import termine');
                    chargerRefClients();
                    chargerCommerciaux();
                    chargerConfigGenerale();
                }
            }, function(e) {
                if (msg) msg.innerHTML = '<span style="color:var(--red)">Erreur import: ' + e + '</span>';
            });
        })
        .catch(function(e) {
            if (msg) msg.innerHTML = '<span style="color:var(--red)">Erreur envoi fichier: ' + e + '</span>';
        });
}

// ── SQLite ────────────────────────────────────────────────────
function chargerSQLiteInfo() {
    apiGet('/api/database/sqlite-info', function(d) {
        var el = document.getElementById('sqlite-info-txt');
        if (el) el.textContent = (d.path||'') + ' | ' + (d.size_human||'?') + ' | ' + (d.nb_tables||0) + ' tables';
    });
}

function backupSQLite() {
    apiPost('/api/database/backup-sqlite', {}, function(d) {
        var msg = document.getElementById('sqlite-msg');
        if (msg) msg.innerHTML = '<span style="color:var(--green)">Sauvegarde: ' + (d.path||'') + '</span>';
        status('Sauvegarde SQLite creee');
    });
}

// ── Base applicative ──────────────────────────────────────────
function onDbTypeChange() {
    var sel   = document.getElementById('app-db-type');
    var val   = sel ? sel.value : 'SQLite local';
    var pathZ = document.getElementById('app-db-path-zone');
    var nameZ = document.getElementById('app-db-name-zone');
    if (pathZ) pathZ.style.display = val === 'SQLite local' ? 'none' : 'block';
    if (nameZ) nameZ.style.display = val.includes('SQL Server') ? 'block' : 'none';
}

function testerAppDb() {
    var type = document.getElementById('app-db-type') ? document.getElementById('app-db-type').value : 'SQLite local';
    var path = document.getElementById('app-db-path') ? document.getElementById('app-db-path').value.trim() : '';
    var name = document.getElementById('app-db-name') ? document.getElementById('app-db-name').value.trim() : 'NEXORA_APP';
    var msg  = document.getElementById('app-db-msg');
    if (msg) msg.innerHTML = '<span style="color:var(--muted)">Test en cours...</span>';
    apiPost('/api/database/test-app-db', {db_type:type, db_path:path, db_name:name}, function(d) {
        if (msg) msg.innerHTML = '<span style="color:'+(d.ok?'var(--green)':'var(--red)')+'">'+d.message+'</span>';
    });
}

function creerAppDb() {
    var type = document.getElementById('app-db-type') ? document.getElementById('app-db-type').value : 'SQLite local';
    var path = document.getElementById('app-db-path') ? document.getElementById('app-db-path').value.trim() : '';
    var name = document.getElementById('app-db-name') ? document.getElementById('app-db-name').value.trim() : 'NEXORA_APP';
    var msg  = document.getElementById('app-db-msg');
    if (msg) msg.innerHTML = '<span style="color:var(--muted)">Creation en cours...</span>';
    apiPost('/api/database/create-app-db', {db_type:type, db_path:path, db_name:name}, function(d) {
        if (msg) msg.innerHTML = '<span style="color:'+(d.ok?'var(--green)':'var(--red)')+'">'+d.message+'</span>';
        if (d.ok) status('Base de donnees creee');
    });
}

// ── Référentiel Clients ───────────────────────────────────────
function chargerRefClients() {
    var q = document.getElementById('ref-search') ? document.getElementById('ref-search').value : '';
    tableLoader('ref-tbody', 8);
    apiGet('/api/param/ref-clients?q='+encodeURIComponent(q), function(d) {
        var tbody  = document.getElementById('ref-tbody');
        if (!tbody) return;
        var clients = d.clients || [];
        if (!clients.length) { tableVide('ref-tbody', 8, 'Aucun client dans le referentiel'); return; }
        tbody.innerHTML = clients.map(function(c) {
            return '<tr>' +
                   '<td style="font-weight:700;color:var(--navy);font-family:monospace">' + (c.code||'-') + '</td>' +
                   '<td>' + (c.nom||'-') + '</td>' +
                   '<td>' + badge(c.zone||'—','info') + '</td>' +
                   '<td>' + (c.commercial||'-') + '</td>' +
                   '<td style="text-align:right">' + (c.plafond?fmt.money(c.plafond):'-') + '</td>' +
                   '<td style="text-align:center">' + (c.delai||30) + 'j</td>' +
                   '<td>' + (c.telephone||'-') + '</td>' +
                   '<td style="white-space:nowrap">' +
                   '<button class="btn btn-outline btn-sm" onclick="modifierRefClient(\'' + c.code + '\')">✏</button> ' +
                   '<button class="btn btn-sm" style="background:var(--red);color:white" onclick="supprimerRefClient(\'' + c.code + '\')">✕</button>' +
                   '</td></tr>';
        }).join('');
    });
}

function modifierRefClient(code) {
    apiGet('/api/param/ref-clients?q='+encodeURIComponent(code), function(d) {
        var c = (d.clients||[]).find(function(r){ return r.code===code; });
        if (!c) return;
        var s = function(id,v){ var el=document.getElementById(id); if(el) el.value=v||''; };
        s('rc-code',c.code); s('rc-nom',c.nom); s('rc-zone',c.zone);
        s('rc-com',c.commercial); s('rc-plafond',c.plafond||0);
        s('rc-delai',c.delai||30); s('rc-tel',c.telephone);
        var codeEl = document.getElementById('rc-code');
        if (codeEl) codeEl.readOnly = true;
        ouvrirModal('modal-ref-client');
    });
}

function sauvegarderRefClient() {
    var code = document.getElementById('rc-code') ? document.getElementById('rc-code').value.trim() : '';
    if (!code) { alert('Code client obligatoire'); return; }
    var data = {
        code:       code,
        nom:        document.getElementById('rc-nom')     ? document.getElementById('rc-nom').value.trim()     : '',
        zone:       document.getElementById('rc-zone')    ? document.getElementById('rc-zone').value.trim()    : '',
        commercial: document.getElementById('rc-com')     ? document.getElementById('rc-com').value.trim()     : '',
        plafond:    document.getElementById('rc-plafond') ? parseFloat(document.getElementById('rc-plafond').value)||0 : 0,
        delai:      document.getElementById('rc-delai')   ? parseInt(document.getElementById('rc-delai').value)||30    : 30,
        telephone:  document.getElementById('rc-tel')     ? document.getElementById('rc-tel').value.trim()     : '',
    };
    var msg = document.getElementById('rc-msg');
    apiPost('/api/param/ref-clients', data, function() {
        var codeEl = document.getElementById('rc-code');
        if (codeEl) codeEl.readOnly = false;
        fermerModal('modal-ref-client');
        chargerRefClients();
        status('Client enregistre');
        if (msg) msg.innerHTML = '';
    }, function(e) {
        if (msg) msg.innerHTML = '<span style="color:var(--red)">Erreur: '+e+'</span>';
    });
}

function supprimerRefClient(code) {
    if (!confirm('Supprimer le client '+code+' du referentiel ?')) return;
    fetch('/api/param/ref-clients?code='+encodeURIComponent(code), {method:'DELETE'})
        .then(function(r){ return r.json(); })
        .then(function(){ chargerRefClients(); status('Client supprime'); });
}

// ── Commerciaux ───────────────────────────────────────────────
function chargerCommerciaux() {
    tableLoader('com-tbody', 4);
    apiGet('/api/param/commerciaux', function(d) {
        var tbody = document.getElementById('com-tbody');
        if (!tbody) return;
        var coms = d.commerciaux || [];
        if (!coms.length) { tableVide('com-tbody', 4, 'Aucun commercial configure'); return; }
        tbody.innerHTML = coms.map(function(c) {
            var nom = (c.nom||'').replace(/'/g, "\\'");
            return '<tr>' +
                   '<td style="font-weight:700">' + (c.nom||'-') + '</td>' +
                   '<td style="color:var(--gold);font-weight:700">' + fmt.money(c.objectif||0) + '</td>' +
                   '<td style="text-align:center">' + (c.ordre||0) + '</td>' +
                   '<td><button class="btn btn-sm" style="background:var(--red);color:white" ' +
                   'onclick="supprimerCommercial(\'' + nom + '\')">✕ Supprimer</button></td>' +
                   '</tr>';
        }).join('');
    });
}

function sauvegarderCommercial() {
    var nom = document.getElementById('mc-nom') ? document.getElementById('mc-nom').value.trim() : '';
    if (!nom) { alert('Nom obligatoire'); return; }
    var data = {
        nom:      nom,
        objectif: document.getElementById('mc-obj')   ? parseFloat(document.getElementById('mc-obj').value)||0   : 0,
        ordre:    document.getElementById('mc-ordre') ? parseInt(document.getElementById('mc-ordre').value)||0    : 0,
    };
    apiPost('/api/param/commerciaux', data, function() {
        fermerModal('modal-commercial');
        chargerCommerciaux();
        status('Commercial enregistre');
    });
}

function supprimerCommercial(nom) {
    if (!confirm('Supprimer le commercial '+nom+' ?')) return;
    fetch('/api/param/commerciaux?nom='+encodeURIComponent(nom), {method:'DELETE'})
        .then(function(r){ return r.json(); })
        .then(function(){ chargerCommerciaux(); status('Commercial supprime'); });
}

// ── Utilisateurs (avec poste/role/commercial_name/telegram_id) ─
function chargerUsers() {
    tableLoader('users-tbody', 8);
    apiGet('/api/utilisateurs', function(d) {
        var tbody = document.getElementById('users-tbody');
        if (!tbody) return;
        var users = d.utilisateurs || [];
        if (!users.length) { tableVide('users-tbody', 8, 'Aucun utilisateur'); return; }
        tbody.innerHTML = users.map(function(u) {
            var statut = u.actif ? badge('Actif','ok') : badge('Inactif','muted');
            return '<tr>' +
                   '<td style="font-weight:700">' + (u.username||'-') + '</td>' +
                   '<td>' + (u.prenom?u.prenom+' ':'') + (u.nom||'-') + '</td>' +
                   '<td>' + badge(u.role||'commercial','info') + '</td>' +
                   '<td>' + (u.poste||'-') + '</td>' +
                   '<td>' + (u.agence||'-') + '</td>' +
                   '<td>' + (u.commercial_name||'-') + '</td>' +
                   '<td style="font-family:monospace;font-size:11px">' + (u.telegram_id||'-') + '</td>' +
                   '<td>' + statut + '</td>' +
                   '<td style="white-space:nowrap">' +
                   '<button class="btn btn-outline btn-sm" onclick="ouvrirModifierUser('+u.id+')">✏</button> ' +
                   '<button class="btn btn-sm" style="background:var(--red);color:white" onclick="supprimerUser('+u.id+',\''+u.username+'\')">✕</button>' +
                   '<button class="btn btn-outline btn-sm" style="margin-left:4px" onclick="ouvrirDroitsUser('+u.id+',\''+u.username+'\')">🔑</button>' +
                   '</td></tr>';
        }).join('');
    });
}

function ouvrirModifierUser(uid) {
    apiGet('/api/utilisateurs/'+uid, function(d) {
        var u = d.utilisateur || {};
        var s = function(id,v){ var el=document.getElementById(id); if(el) el.value=v||''; };
        s('u-id',uid); s('u-login',u.username); s('u-nom',u.nom);
        s('u-prenom',u.prenom); s('u-agence',u.agence||'BERTOUA');
        s('u-role',u.role||'commercial'); s('u-poste',u.poste);
        s('u-categorie',u.categorie); s('u-comname',u.commercial_name);
        s('u-tgid',u.telegram_id); s('u-pwd',''); s('u-pwd2','');
        var loginEl = document.getElementById('u-login');
        if (loginEl) loginEl.readOnly = true;
        var titreEl = document.getElementById('modal-user-titre');
        if (titreEl) titreEl.textContent = 'Modifier utilisateur';
        ouvrirModal('modal-user');
    });
}

function creerUser() {
    var uid    = document.getElementById('u-id')    ? document.getElementById('u-id').value       : '';
    var login  = document.getElementById('u-login') ? document.getElementById('u-login').value.trim() : '';
    var nom    = document.getElementById('u-nom')   ? document.getElementById('u-nom').value.trim()   : '';
    var pwd    = document.getElementById('u-pwd')   ? document.getElementById('u-pwd').value           : '';
    var pwd2   = document.getElementById('u-pwd2')  ? document.getElementById('u-pwd2').value           : '';
    if (!nom || !login) { alert('Login et nom obligatoires'); return; }
    if (pwd && pwd !== pwd2) { alert('Mots de passe differents'); return; }
    var data = {
        username:        login, nom: nom,
        prenom:          document.getElementById('u-prenom')   ? document.getElementById('u-prenom').value   : '',
        agence:          document.getElementById('u-agence')   ? document.getElementById('u-agence').value   : 'BERTOUA',
        role:            document.getElementById('u-role')     ? document.getElementById('u-role').value     : 'commercial',
        poste:           document.getElementById('u-poste')    ? document.getElementById('u-poste').value    : '',
        categorie:       document.getElementById('u-categorie')? document.getElementById('u-categorie').value: '',
        commercial_name: document.getElementById('u-comname')  ? document.getElementById('u-comname').value  : '',
        telegram_id:     document.getElementById('u-tgid')     ? document.getElementById('u-tgid').value     : '',
        password:        pwd, actif: 1,
    };
    var loginEl = document.getElementById('u-login');
    if (uid) {
        // Modification
        apiPost('/api/utilisateurs/'+uid, data, function() {
            fermerModal('modal-user');
            chargerUsers();
            status('Utilisateur modifie');
            if (loginEl) loginEl.readOnly = false;
        });
        return;
    }
    // Création
    apiPost('/api/utilisateurs', data, function() {
        fermerModal('modal-user');
        chargerUsers();
        status('Utilisateur cree: '+login);
        if (loginEl) loginEl.readOnly = false;
    }, function(e) { alert('Erreur: '+e); });
}

function supprimerUser(uid, uname) {
    if (!confirm('Supprimer l\'utilisateur '+uname+' ?')) return;
    fetch('/api/utilisateurs/'+uid, {method:'DELETE'})
        .then(function(r){ return r.json(); })
        .then(function(d){
            if (d.ok) { chargerUsers(); status('Utilisateur supprime'); }
            else alert('Erreur: '+d.msg);
        });
}

// ── Droits d'accès ────────────────────────────────────────────
var _droitsUserId = null;

function chargerDropdownUsers() {
    var sel = document.getElementById('droits-user-sel');
    if (!sel) return;
    apiGet('/api/utilisateurs', function(d) {
        sel.innerHTML = '<option value="">-- Choisir un utilisateur --</option>';
        (d.utilisateurs||[]).forEach(function(u) {
            var opt = document.createElement('option');
            opt.value = u.id;
            opt.textContent = (u.prenom?u.prenom+' ':'') + u.nom + ' ('+u.username+')';
            sel.appendChild(opt);
        });
    });
}

function ouvrirDroitsUser(uid, uname) {
    var sel = document.getElementById('droits-user-sel');
    if (sel) sel.value = uid;
    chargerDroitsUser();
    navSub(document.querySelector('[data-nav="param-droits"]'), 'param-droits');
}

var ICOS_MOD = {
    stock:'📦', logistique:'🚛', commercial:'📊', caisse:'🏪',
    comptabilite:'💰', rh:'👥', rapports:'📋',
    consolidation:'🏆', multisite:'🌐', parametres:'⚙️'
};

function chargerDroitsUser() {
    var sel    = document.getElementById('droits-user-sel');
    var userId = sel ? sel.value : '';
    var zone   = document.getElementById('droits-zone');
    if (!userId) { if (zone) zone.style.display='none'; return; }
    _droitsUserId = userId;
    if (zone) zone.style.display = 'block';
    var nomEl = document.getElementById('droits-user-nom');
    if (nomEl && sel) nomEl.textContent = sel.options[sel.selectedIndex].textContent;
    apiGet('/api/utilisateurs/'+userId+'/permissions-detail', function(d) {
        var liste = document.getElementById('droits-modules-list');
        if (!liste) return;
        var tree  = d.tree || {};
        var perms = d.permissions || {};
        liste.innerHTML = Object.keys(tree).map(function(mod) {
            var cfg      = tree[mod] || {};
            var sousMods = cfg.sous_modules || {};
            var hasSous  = Object.keys(sousMods).length > 0;
            var icon     = ICOS_MOD[mod] || '📌';

            function rowPermissions(modKey, smKey, smLabel) {
                var p = (perms[modKey] && perms[modKey][smKey]) || {lecture:false,ecriture:false,suppression:false,tout:false};
                return '<div style="display:flex;align-items:center;justify-content:space-between;' +
                       'padding:8px 10px;border-bottom:1px solid var(--border)">' +
                       '<span style="font-size:12px;flex:1">' + smLabel + '</span>' +
                       '<div style="display:flex;gap:14px" data-mod="' + modKey + '" data-sm="' + smKey + '">' +
                       ['lecture','ecriture','suppression','tout'].map(function(act) {
                           var lbl = {lecture:'Lecture',ecriture:'Ecriture',suppression:'Suppr.',tout:'Tout'}[act];
                           var checked = p[act] ? 'checked' : '';
                           return '<label style="display:flex;align-items:center;gap:4px;font-size:11px;cursor:pointer">' +
                                  '<input type="checkbox" data-action="' + act + '" ' + checked + '> ' + lbl + '</label>';
                       }).join('') +
                       '</div></div>';
            }

            var bodyHtml = hasSous
                ? Object.keys(sousMods).map(function(smKey) {
                      return rowPermissions(mod, smKey, sousMods[smKey]);
                  }).join('')
                : rowPermissions(mod, '*', 'Acces complet au module');

            return '<div class="droits-module-block" style="border:1px solid var(--border);border-radius:8px;overflow:hidden">' +
                   '<div style="display:flex;align-items:center;gap:8px;padding:10px;background:var(--bg);cursor:pointer" ' +
                   'onclick="this.nextElementSibling.style.display=this.nextElementSibling.style.display===\'none\'?\'block\':\'none\'">' +
                   '<span style="font-size:16px">' + icon + '</span>' +
                   '<strong style="font-size:13px">' + (cfg.label||mod) + '</strong>' +
                   (hasSous ? '<span style="margin-left:auto;font-size:10px;color:var(--muted)">' + Object.keys(sousMods).length + ' sous-modules ▾</span>' : '<span style="margin-left:auto"></span>') +
                   '</div>' +
                   '<div style="display:' + (hasSous ? 'none' : 'block') + '">' + bodyHtml + '</div>' +
                   '</div>';
        }).join('');
    });
}

function toutCocher(val) {
    document.querySelectorAll('#droits-modules-list input[type=checkbox]').forEach(function(cb) {
        cb.checked = val;
    });
}

function appliquerDroitsDetail() {
    if (!_droitsUserId) { alert('Aucun utilisateur selectionne'); return; }
    var permissions = {};
    document.querySelectorAll('#droits-modules-list [data-mod]').forEach(function(rowEl) {
        var mod = rowEl.getAttribute('data-mod');
        var sm  = rowEl.getAttribute('data-sm');
        if (!permissions[mod]) permissions[mod] = {};
        var actions = {};
        rowEl.querySelectorAll('input[type=checkbox]').forEach(function(cb) {
            actions[cb.getAttribute('data-action')] = cb.checked;
        });
        permissions[mod][sm] = actions;
    });
    var msg = document.getElementById('droits-msg');
    if (msg) msg.innerHTML = '<span style="color:var(--muted)">Sauvegarde...</span>';
    apiPost('/api/utilisateurs/'+_droitsUserId+'/permissions-detail', {permissions:permissions}, function() {
        if (msg) msg.innerHTML = '<span style="color:var(--green)">Droits detailles sauvegardes</span>';
        status('Droits mis a jour');
    }, function(e) {
        if (msg) msg.innerHTML = '<span style="color:var(--red)">Erreur: '+e+'</span>';
    });
}

// ── Bot Telegram ──────────────────────────────────────────────
function chargerBotConfig() {
    apiGet('/api/param/bot-telegram', function(d) {
        var cfg = d.config || {};
        var s   = function(id,k){ var el=document.getElementById(id); if(el) el.value=cfg[k]||''; };
        s('bot-token','bot_token'); s('bot-admins','bot_admin_ids'); s('bot-snap-heure','bot_snap_heure');
    });
}

function sauvegarderBotConfig() {
    var token  = document.getElementById('bot-token')      ? document.getElementById('bot-token').value.trim()  : '';
    var admins = document.getElementById('bot-admins')     ? document.getElementById('bot-admins').value.trim() : '';
    var heure  = document.getElementById('bot-snap-heure') ? document.getElementById('bot-snap-heure').value    : '6';
    var msg    = document.getElementById('bot-msg');
    if (!token) { alert('Token Telegram obligatoire'); return; }
    apiPost('/api/param/bot-telegram', {bot_token:token,bot_admin_ids:admins,bot_snap_heure:heure}, function() {
        if (msg) msg.innerHTML = '<span style="color:var(--green)">Configuration sauvegardee</span>';
        status('Bot Telegram configure');
    });
}

function testerBot() {
    var msg = document.getElementById('bot-msg');
    if (msg) msg.innerHTML = '<span style="color:var(--muted)">Envoi en cours...</span>';
    apiPost('/api/param/bot-telegram/test', {}, function(d) {
        if (msg) msg.innerHTML = '<span style="color:var(--green)">' + (d.message||'Envoye') + '</span>';
    }, function(e) {
        if (msg) msg.innerHTML = '<span style="color:var(--red)">Erreur: '+e+'</span>';
    });
}

function demarrerBot() {
    var msg = document.getElementById('bot-msg');
    if (msg) msg.innerHTML = '<span style="color:var(--muted)">Verification et demarrage...</span>';
    apiPost('/api/param/bot-telegram/demarrer', {}, function(d) {
        if (msg) msg.innerHTML = '<span style="color:'+(d.ok?'var(--green)':'var(--red)')+'">'+d.message+'</span>';
        if (d.ok) { status('Bot Telegram demarre'); setTimeout(chargerStatutBot, 2000); }
    }, function(e) {
        if (msg) msg.innerHTML = '<span style="color:var(--red)">Erreur: '+e+'</span>';
    });
}

function arreterBot() {
    var msg = document.getElementById('bot-msg');
    apiPost('/api/param/bot-telegram/arreter', {}, function(d) {
        if (msg) msg.innerHTML = '<span style="color:var(--muted)">' + (d.message||'Arrete') + '</span>';
        chargerStatutBot();
    });
}

function chargerStatutBot() {
    apiGet('/api/param/bot-telegram/statut', function(d) {
        var st = document.getElementById('bot-statut');
        if (st) st.innerHTML = d.running
            ? '<span style="color:var(--green)">● Bot en ligne</span>'
            : '<span style="color:var(--muted)">○ Bot arrete</span>';
        var logEl = document.getElementById('bot-log');
        if (logEl) {
            var lg = d.log || [];
            logEl.innerHTML = lg.length
                ? lg.map(function(l){ return '<div>'+l+'</div>'; }).join('')
                : 'Aucune activite enregistree.';
        }
    });
}

function snapshotBotManuel() {
    var msg = document.getElementById('bot-msg');
    if (msg) msg.innerHTML = '<span style="color:var(--muted)">Calcul KPIs/Classement/Creances en cours...</span>';
    apiPost('/api/param/bot-telegram/snapshot-auto', {}, function(d) {
        if (msg) msg.innerHTML = '<span style="color:'+(d.ok?'var(--green)':'var(--red)')+'">' +
            (d.message||'') + (d.ok ? ' (' + d.nb_commerciaux + ' commerciaux, ' + d.nb_creances + ' creances)' : '') + '</span>';
        if (d.ok) status('Snapshot bot mis a jour');
    }, function(e) {
        if (msg) msg.innerHTML = '<span style="color:var(--red)">Erreur: '+e+'</span>';
    });
}

// ── Inscriptions Bot Telegram ──────────────────────────────────
function chargerInscriptionsBot() {
    tableLoader('bot-insc-tbody', 6);
    apiGet('/api/param/bot-inscriptions', function(d) {
        var tbody = document.getElementById('bot-insc-tbody');
        if (!tbody) return;
        var rows = d.inscriptions || [];
        if (!rows.length) { tableVide('bot-insc-tbody', 6, 'Aucune demande'); return; }
        tbody.innerHTML = rows.map(function(r) {
            var statutBadge = r.statut === 'VALIDEE' ? badge('Validee','ok') :
                               r.statut === 'REJETEE' ? badge('Rejetee','muted') : badge('En attente','warn');
            var actions = r.statut === 'EN_ATTENTE'
                ? '<button class="btn btn-gold btn-sm" onclick="validerInscriptionBot('+r.id+')">✅ Valider</button> ' +
                  '<button class="btn btn-sm" style="background:var(--red);color:white" onclick="rejeterInscriptionBot('+r.id+')">✕ Rejeter</button>'
                : '-';
            return '<tr><td style="font-family:monospace">' + (r.telegram_nom||'-') + ' (' + r.telegram_id + ')</td>' +
                   '<td>' + (r.nom||'-') + '</td><td>' + (r.poste||'-') + '</td>' +
                   '<td>' + (r.agence||'-') + '</td><td>' + statutBadge + '</td>' +
                   '<td style="white-space:nowrap">' + actions + '</td></tr>';
        }).join('');
    });
}

function validerInscriptionBot(iid) {
    var role = prompt('Role a attribuer (admin, direction, financier, agence, commercial) :', 'commercial');
    if (role === null) return;
    apiPost('/api/param/bot-inscriptions/'+iid+'/valider', {role: role}, function(d) {
        status(d.message || 'Inscription validee');
        chargerInscriptionsBot();
        chargerUsers();
    }, function(e) { alert('Erreur: '+e); });
}

function rejeterInscriptionBot(iid) {
    if (!confirm('Rejeter cette demande ?')) return;
    apiPost('/api/param/bot-inscriptions/'+iid+'/rejeter', {}, function() {
        status('Demande rejetee');
        chargerInscriptionsBot();
    });
}

// ── Journal de processus ──────────────────────────────────────
function chargerJournal() {
    var limite = document.getElementById('journal-limite') ? document.getElementById('journal-limite').value : 100;
    var el     = document.getElementById('journal-content');
    if (!el) return;
    el.textContent = 'Chargement...';
    apiGet('/api/param/journal?limite='+limite, function(d) {
        var entries = d.entries || [];
        if (!entries.length) { el.textContent = 'Aucune entree dans le journal.'; return; }
        el.innerHTML = entries.map(function(e) {
            var col = e.action && e.action.includes('ERR') ? '#EF4444' :
                      e.action && e.action.includes('OK')  ? '#10B981' : '#8BA3CC';
            return '<div style="padding:3px 0;border-bottom:1px solid rgba(255,255,255,.05)">' +
                   '<span style="color:#4A6080;margin-right:8px">['+fmt.date(e.date_op)+']</span>' +
                   '<span style="color:'+col+';font-weight:600">' + (e.module||'-') + ':' + (e.action||'-') + '</span> ' +
                   '<span style="color:#8BA3CC">' + (e.username||'') + '</span> ' +
                   '<span>' + (e.detail||'') + '</span></div>';
        }).join('');
    });
}

function effacerJournal() {
    if (!confirm('Effacer tout le journal ?')) return;
    fetch('/api/param/journal', {method:'DELETE'})
        .then(function(r){ return r.json(); })
        .then(function(){ chargerJournal(); status('Journal efface'); });
}

// ── Journal Sage temps reel (diagnostic blocage connexion) ─────
var _sageJournalInterval = null;

function chargerJournalSage() {
    var el = document.getElementById('sage-journal-content');
    var coEl = document.getElementById('sage-derniere-co');
    if (!el) return;
    apiGet('/api/param/journal-sage?limite=150', function(d) {
        var entries = d.entries || [];
        var lastOk  = d.derniere_connexion_ok || {};
        if (coEl) {
            coEl.innerHTML = lastOk.driver
                ? '<span style="color:var(--green)">● Derniere connexion reussie: ' + lastOk.driver + ' / ' + lastOk.variant + ' (encodage ' + lastOk.encoding + ')</span>'
                : '<span style="color:var(--muted)">○ Aucune connexion Sage reussie pour le moment</span>';
        }
        if (!entries.length) { el.textContent = 'Aucune tentative de connexion Sage enregistree.'; return; }
        el.innerHTML = entries.map(function(e) {
            var col = e.level === 'ERROR' ? '#EF4444' : '#10B981';
            return '<div style="padding:3px 0;border-bottom:1px solid rgba(255,255,255,.05)">' +
                   '<span style="color:#4A6080;margin-right:8px">[' + e.ts + ']</span>' +
                   '<span style="color:' + col + '">' + e.msg + '</span></div>';
        }).join('');
        el.scrollTop = el.scrollHeight;
    });
}

function effacerJournalSage() {
    fetch('/api/param/journal-sage', {method:'DELETE'})
        .then(function(r){ return r.json(); })
        .then(function(){ chargerJournalSage(); status('Journal Sage efface'); });
}

function toggleAutoRefreshSage() {
    var cb = document.getElementById('sage-journal-auto');
    if (cb && cb.checked) {
        chargerJournalSage();
        _sageJournalInterval = setInterval(chargerJournalSage, 5000);
    } else if (_sageJournalInterval) {
        clearInterval(_sageJournalInterval);
        _sageJournalInterval = null;
    }
}

// ── Accès internet ────────────────────────────────────────────
function demarrerCF() {
    var token = document.getElementById('cf-token') ? document.getElementById('cf-token').value.trim() : '';
    if (!token) { alert('Saisissez le token Cloudflare'); return; }
    apiPost('/api/config/cloudflare/start', {token:token}, function() { status('Cloudflare configure'); });
}
function arreterCF() { apiPost('/api/config/cloudflare/stop', {}, function() { status('Cloudflare arrete'); }); }
function demarrerNgrok() {
    var token = document.getElementById('ngrok-token') ? document.getElementById('ngrok-token').value.trim() : '';
    apiPost('/api/config/ngrok/start', {token:token}, function() { status('ngrok configure'); });
}

// ── Domaine ───────────────────────────────────────────────────
function previewDomaine() {
    var dom  = document.getElementById('dom-principal') ? document.getElementById('dom-principal').value.trim() : '';
    var sous = document.getElementById('dom-sous')      ? document.getElementById('dom-sous').value.trim()      : '';
    var port = document.getElementById('dom-port')      ? document.getElementById('dom-port').value             : '5050';
    var prev = document.getElementById('dom-preview');
    if (!dom) { if (prev) prev.textContent=''; return; }
    var url = sous ? ('http://'+sous+'.'+dom+':'+port) : ('http://'+dom+':'+port);
    if (prev) prev.innerHTML = 'URL: <strong>'+url+'</strong>';
}
function testerDomaine() {
    var dom = document.getElementById('dom-principal') ? document.getElementById('dom-principal').value.trim() : '';
    var msg = document.getElementById('dom-msg');
    if (!dom) { if(msg) msg.innerHTML='<span style="color:var(--warn)">Saisissez un domaine</span>'; return; }
    if (msg) msg.innerHTML = '<span style="color:var(--muted)">Test...</span>';
    apiGet('/api/parametres/tester-domaine?domaine='+encodeURIComponent(dom), function(d) {
        if (msg) msg.innerHTML = '<span style="color:var(--green)">'+d.message+'</span>';
    }, function(e) { if(msg) msg.innerHTML='<span style="color:var(--warn)">'+e+'</span>'; });
}
function sauvegarderDomaine() {
    var data = {
        domaine:  document.getElementById('dom-principal') ? document.getElementById('dom-principal').value.trim() : '',
        sous_dom: document.getElementById('dom-sous')      ? document.getElementById('dom-sous').value.trim()      : '',
        mode:     document.getElementById('dom-mode')      ? document.getElementById('dom-mode').value             : 'local',
        port:     document.getElementById('dom-port')      ? document.getElementById('dom-port').value             : '5050',
    };
    apiPost('/api/parametres/domaine', data, function() { status('Domaine enregistre'); });
}
function sauvegarderWG() {
    var conf = document.getElementById('wg-conf') ? document.getElementById('wg-conf').value : '';
    apiPost('/api/parametres/vpn/wireguard', {config:conf}, function() { status('WireGuard configure'); });
}
function sauvegarderOVPN() {
    var conf = document.getElementById('ovpn-conf') ? document.getElementById('ovpn-conf').value : '';
    apiPost('/api/parametres/vpn/openvpn', {config:conf}, function() { status('OpenVPN configure'); });
}

// ── IP Whitelist ──────────────────────────────────────────────
function chargerWhitelistIP() {
    apiGet('/api/config/ip-whitelist', function(d) {
        var el = document.getElementById('ip-liste');
        if (!el) return;
        if (!d.ips || !d.ips.length) { el.innerHTML = '<div class="tbl-empty">Aucune IP configuree</div>'; return; }
        el.innerHTML = d.ips.map(function(ip) {
            return '<div style="display:flex;justify-content:space-between;padding:6px 0;' +
                   'border-bottom:1px solid var(--border)">' +
                   '<code>' + ip + '</code>' +
                   '</div>';
        }).join('');
    });
}
function ajouterIP() {
    var ip  = document.getElementById('ip-nouvelle') ? document.getElementById('ip-nouvelle').value.trim() : '';
    if (!ip) return;
    apiPost('/api/config/ip-whitelist', {ip:ip}, function() {
        var el = document.getElementById('ip-nouvelle'); if(el) el.value='';
        chargerWhitelistIP(); status('IP ajoutee: '+ip);
    });
}

// ── Compilation ───────────────────────────────────────────────
function installerPyInstaller() {
    var msg = document.getElementById('compile-msg');
    if (msg) msg.innerHTML = '<span style="color:var(--muted)">Installation de PyInstaller en cours... (peut prendre 1-2 minutes)</span>';
    apiPost('/api/param/installer-pyinstaller', {}, function(d) {
        if (msg) msg.innerHTML = '<span style="color:'+(d.ok?'var(--green)':'var(--red)')+'">'+d.message+'</span>';
        if (d.ok) status('PyInstaller installe');
    });
}

function compilerExe() {
    var msg = document.getElementById('compile-msg');
    if (msg) msg.innerHTML = '<span style="color:var(--warn)">Compilation en cours... (2-5 minutes). Ne fermez pas.</span>';
    apiPost('/api/param/compiler-exe', {}, function(d) {
        if (msg) msg.innerHTML = '<span style="color:'+(d.ok?'var(--green)':'var(--red)')+'">'+d.message+'</span>';
        if (d.ok) status('NEXORA.exe compile !');
    });
}

// ── Licence ───────────────────────────────────────────────────
function chargerStatutLicence() {
    apiGet('/api/licence/statut', function(d) {
        var badge_el = document.getElementById('lic-statut-badge');
        var info_el  = document.getElementById('lic-statut-info');
        var det_el   = document.getElementById('lic-details');
        if (!badge_el || !info_el) return;
        if (d.mode === 'DEMO') {
            badge_el.textContent='Mode Demo'; badge_el.className='badge b-warn';
            info_el.innerHTML='<strong style="color:var(--warn)">Mode Demonstration</strong>' +
                '<p style="font-size:11px;color:var(--muted);margin-top:4px">'+d.jours_demo+' jours restants</p>';
        } else if (d.mode === 'ACTIVE' || d.mode === 'PERPETUELLE') {
            badge_el.textContent=d.perpetuelle?'Perpetuelle':'Active'; badge_el.className='badge b-ok';
            info_el.innerHTML='<strong style="color:var(--green)">Licence Active</strong>' +
                '<p style="font-size:11px;color:var(--muted);margin-top:4px">' + (d.nom_societe||'') + '</p>';
            if (det_el) det_el.style.display='block';
            var s=function(id,v){ var el=document.getElementById(id); if(el) el.textContent=v||'-'; };
            s('lic-nom-soc', d.nom_societe);
            s('lic-postes',  (d.nb_postes||1)+' poste(s)');
            s('lic-exp',     d.perpetuelle?'Perpetuelle':(d.date_expiration||'-'));
            var modEl = document.getElementById('lic-modules-list');
            if (modEl && d.modules_noms) {
                modEl.innerHTML = (d.modules_noms||[]).map(function(m){
                    return '<span style="padding:3px 10px;border-radius:20px;background:rgba(16,185,129,.12);color:var(--green);font-size:11px">'+m+'</span>';
                }).join('');
            }
        } else {
            badge_el.textContent='Non activee'; badge_el.className='badge b-err';
            info_el.innerHTML='<strong style="color:var(--red)">Aucune licence</strong>' +
                '<p style="font-size:11px;color:var(--muted);margin-top:4px">' + (d.erreur||'Activez une licence') + '</p>';
        }
    });
}

function verifierLicence() {
    var numero = document.getElementById('lic-serial-input') ? document.getElementById('lic-serial-input').value.trim() : '';
    var prev   = document.getElementById('lic-preview');
    var err    = document.getElementById('lic-preview-err');
    if (!numero) { alert('Saisissez un numero de serie'); return; }
    if (prev) prev.style.display='none';
    if (err)  err.style.display='none';
    apiPost('/api/licence/verifier', {numero_serie:numero}, function(d) {
        if (prev) {
            prev.style.display='block';
            var det = document.getElementById('lic-preview-detail');
            if (det) det.innerHTML = 'Societe: <strong>'+d.nom_societe+'</strong> | Postes: <strong>'+d.nb_postes+'</strong> | Exp: <strong>'+(d.perpetuelle?'Perpetuelle':(d.date_expiration||'-'))+'</strong>';
        }
    }, function(e) { if(err){ err.textContent='Invalide: '+e; err.style.display='block'; } });
}

function activerLicence() {
    var numero = document.getElementById('lic-serial-input') ? document.getElementById('lic-serial-input').value.trim() : '';
    var msg    = document.getElementById('lic-activation-msg');
    if (!numero) { alert('Saisissez un numero de serie'); return; }
    if (msg) msg.innerHTML = '<span style="color:var(--muted)">Activation...</span>';
    apiPost('/api/licence/activer', {numero_serie:numero}, function(d) {
        if (msg) msg.innerHTML = '<span style="color:var(--green)">Activee pour '+(d.nom_societe||'')+'</span>';
        chargerStatutLicence();
        var inp = document.getElementById('lic-serial-input'); if(inp) inp.value='';
    }, function(e) {
        if (msg) msg.innerHTML = '<span style="color:var(--red)">Erreur: '+e+'</span>';
    });
}

// ── Init ──────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', function() {
    chargerConfigSage();
    chargerStatutLicence();
    if (typeof toggleSageAuth === 'function') toggleSageAuth();
});

function ouvrirNouveauRefClient() {
    var s = function(id,v){ var el=document.getElementById(id); if(el){ el.value=v||''; el.readOnly=false; } };
    s('rc-code',''); s('rc-nom',''); s('rc-zone',''); s('rc-com','');
    s('rc-plafond','0'); s('rc-delai','30'); s('rc-tel','');
    var msg = document.getElementById('rc-msg'); if(msg) msg.innerHTML='';
    ouvrirModal('modal-ref-client');
}

function ouvrirNouvelUser() {
    var s = function(id){ var el=document.getElementById(id); if(el) el.value=''; };
    s('u-id'); s('u-login'); s('u-nom'); s('u-prenom'); s('u-poste');
    s('u-categorie'); s('u-comname'); s('u-tgid'); s('u-pwd'); s('u-pwd2');
    var roleEl = document.getElementById('u-role'); if(roleEl) roleEl.value='commercial';
    var agEl   = document.getElementById('u-agence'); if(agEl) agEl.value='BERTOUA';
    var loginEl = document.getElementById('u-login'); if(loginEl) loginEl.readOnly=false;
    var titreEl = document.getElementById('modal-user-titre');
    if (titreEl) titreEl.textContent='Nouvel utilisateur';
    ouvrirModal('modal-user');
}
