/**
 * NEXORA v2.0 — Module Parametres
 * Regle : pas de template literals avec apostrophes francaises
 * Regle : .then(function(){}) au lieu de async/await
 */

var autoLoad = window.autoLoad || {};

autoLoad['parametres-dashboard'] = function() { parametresChargerDashboard(); };
autoLoad['config-generale'] = function() { parametresChargerConfigGenerale(); };
autoLoad['config-sage'] = function() { parametresChargerConfigSage(); };
autoLoad['base-donnees'] = function() { parametresChargerBaseDonnees(); };
autoLoad['ip-whitelist'] = function() { parametresChargerIpWhitelist(); };
autoLoad['audit'] = function() { parametresChargerAudit(); };
autoLoad['utilisateurs'] = function() { parametresChargerUtilisateurs(); };
autoLoad['droits'] = function() { parametresChargerUtilisateursPourDroits(); };
autoLoad['licence'] = function() { parametresChargerLicence(); };

window.autoLoad = autoLoad;

var _parametresUsersCache = [];
var _parametresTree = null;

// ── Tableau de bord ─────────────────────────────────────────────────────
function parametresChargerDashboard() {
    apiGet('/api/config/generale', function(d) {
        document.getElementById('kpi-societe').textContent = d.config.societe_nom || '—';
        document.getElementById('kpi-agence').textContent = d.config.agence_locale || '—';
    });
    apiGet('/api/utilisateurs', function(d) {
        var actifs = (d.utilisateurs || []).filter(function(u) { return u.actif; }).length;
        document.getElementById('kpi-utilisateurs').textContent = actifs;
    });
    apiGet('/api/licence/statut', function(d) {
        var lic = d.licence;
        var txt = lic.valide ? 'Active' : (lic.mode_demo ? 'Demo' : 'Aucune');
        document.getElementById('kpi-licence').textContent = txt;
    });
}

// ── Configuration generale ───────────────────────────────────────────────
function parametresChargerConfigGenerale() {
    apiGet('/api/config/generale', function(d) {
        document.getElementById('cg-societe-nom').value = d.config.societe_nom || '';
        document.getElementById('cg-societe-ville').value = d.config.societe_ville || '';
        document.getElementById('cg-agence-locale').value = d.config.agence_locale || 'BERTOUA';
        document.getElementById('cg-depot-defaut').value = d.config.depot_defaut || '';
    });
}

function parametresSaveConfigGenerale() {
    var data = {
        societe_nom: document.getElementById('cg-societe-nom').value,
        societe_ville: document.getElementById('cg-societe-ville').value,
        agence_locale: document.getElementById('cg-agence-locale').value,
        depot_defaut: document.getElementById('cg-depot-defaut').value
    };
    apiPost('/api/config/generale', data, function() {
        status('Configuration generale enregistree');
    });
}

// ── Connexion Sage ────────────────────────────────────────────────────────
function parametresChargerConfigSage() {
    apiGet('/api/config/sage', function(d) {
        var c = d.config;
        document.getElementById('sg-server').value = c.server || '';
        document.getElementById('sg-database').value = c.database || '';
        document.getElementById('sg-login').value = c.login || '';
        document.getElementById('sg-trusted').checked = !!c.trusted;
        document.getElementById('sg-password').value = '';
        var info = c.driver ? ('Pilote ODBC : ' + c.driver) : 'Aucun pilote ODBC SQL Server detecte';
        var b = document.getElementById('sg-driver-info');
        b.textContent = info;
        b.className = c.driver ? 'badge b-ok' : 'badge b-warn';
    });
}

function parametresSaveSage() {
    var data = {
        server: document.getElementById('sg-server').value,
        database: document.getElementById('sg-database').value,
        login: document.getElementById('sg-login').value,
        trusted: document.getElementById('sg-trusted').checked,
        password: document.getElementById('sg-password').value
    };
    apiPost('/api/config/sage', data, function() {
        status('Connexion Sage enregistree');
        parametresChargerConfigSage();
    });
}

function parametresTestSage() {
    status('Test de connexion en cours...');
    apiGet('/api/config/test-sage', function(d) {
        status('✓ ' + d.msg);
    }, function(msg) {
        status('⚠ ' + msg);
    });
}

// ── Etat de la base ─────────────────────────────────────────────────────
function parametresChargerBaseDonnees() {
    apiGet('/api/database/sqlite-info', function(d) {
        document.getElementById('bd-chemin').textContent = d.chemin || '—';
        document.getElementById('bd-tables').textContent = d.nb_tables;
        document.getElementById('bd-taille').textContent = parametresFormatTaille(d.taille_octets);
    });
}

function parametresFormatTaille(octets) {
    octets = parseFloat(octets) || 0;
    if (octets >= 1048576) return (octets / 1048576).toFixed(2) + ' Mo';
    if (octets >= 1024) return (octets / 1024).toFixed(1) + ' Ko';
    return octets + ' o';
}

function parametresBackupDb() {
    apiPost('/api/database/backup-sqlite', {}, function(d) {
        status('Sauvegarde creee : ' + d.fichier);
    });
}

function parametresVacuumDb() {
    apiPost('/api/database/vacuum-sqlite', {}, function() {
        status('Base optimisee (VACUUM)');
        parametresChargerBaseDonnees();
    });
}

// ── Controle IP ───────────────────────────────────────────────────────────
function parametresChargerIpWhitelist() {
    apiGet('/api/config/ip-whitelist', function(d) {
        document.getElementById('ip-active').checked = !!d.active;
        if (!d.whitelist || !d.whitelist.length) {
            emptyTable('ip-tbody', 2, 'Aucune adresse dans la liste blanche');
            return;
        }
        var html = '';
        d.whitelist.forEach(function(ip) {
            html += '<tr><td>' + ip + '</td><td>' +
                '<button class="btn btn-danger btn-sm" onclick="parametresSupprimerIp(\'' + ip + '\')">Supprimer</button>' +
                '</td></tr>';
        });
        document.getElementById('ip-tbody').innerHTML = html;
    });
}

function parametresSaveIpActive() {
    var active = document.getElementById('ip-active').checked;
    apiPost('/api/config/ip-whitelist', {active: active}, function() {
        status(active ? 'Liste blanche IP activee' : 'Liste blanche IP desactivee');
    });
}

function parametresAjouterIp() {
    var ip = document.getElementById('ip-nouvelle').value.trim();
    if (!ip) return;
    apiPost('/api/config/ip-whitelist/ajouter', {ip: ip}, function() {
        document.getElementById('ip-nouvelle').value = '';
        parametresChargerIpWhitelist();
    });
}

function parametresSupprimerIp(ip) {
    apiPost('/api/config/ip-whitelist/supprimer', {ip: ip}, function() {
        parametresChargerIpWhitelist();
    });
}

// ── Journal d'audit ───────────────────────────────────────────────────────
function parametresChargerAudit() {
    loadingTable('audit-tbody', 6);
    apiGet('/api/audit/blocages?limite=100', function(d) {
        if (!d.audit || !d.audit.length) {
            emptyTable('audit-tbody', 6, 'Aucune operation enregistree');
            return;
        }
        var html = '';
        d.audit.forEach(function(a) {
            html += '<tr>' +
                '<td>' + (a.date_op || '') + '</td>' +
                '<td>' + (a.username || '') + '</td>' +
                '<td>' + (a.module || '') + '</td>' +
                '<td>' + (a.action || '') + '</td>' +
                '<td>' + (a.detail || '') + '</td>' +
                '<td>' + (a.ip || '') + '</td>' +
                '</tr>';
        });
        document.getElementById('audit-tbody').innerHTML = html;
    });
}

// ── Utilisateurs ──────────────────────────────────────────────────────────
function parametresChargerUtilisateurs() {
    loadingTable('users-tbody', 8);
    apiGet('/api/utilisateurs', function(d) {
        _parametresUsersCache = d.utilisateurs || [];
        if (!_parametresUsersCache.length) {
            emptyTable('users-tbody', 8, 'Aucun utilisateur');
            return;
        }
        var html = '';
        _parametresUsersCache.forEach(function(u) {
            html += '<tr>' +
                '<td>' + u.username + '</td>' +
                '<td>' + (u.nom || '') + '</td>' +
                '<td>' + (u.prenom || '') + '</td>' +
                '<td>' + (u.email || '') + '</td>' +
                '<td>' + (u.telephone || '') + '</td>' +
                '<td>' + (u.agence || '') + '</td>' +
                '<td>' + badge(u.actif ? 'Actif' : 'Inactif', u.actif ? 'ok' : 'muted') + '</td>' +
                '<td>' +
                '<button class="btn btn-outline btn-sm" onclick="parametresOuvrirUtilisateur(' + u.id + ')">Modifier</button> ' +
                '<button class="btn btn-danger btn-sm" onclick="parametresToggleActif(' + u.id + ',' + (u.actif ? 0 : 1) + ')">' +
                (u.actif ? 'Desactiver' : 'Activer') + '</button>' +
                '</td>' +
                '</tr>';
        });
        document.getElementById('users-tbody').innerHTML = html;
    });
}

function parametresOuvrirUtilisateur(id) {
    var u = null;
    if (id) {
        u = _parametresUsersCache.filter(function(x) { return x.id === id; })[0];
    }
    document.getElementById('mu-id').value = id || '';
    document.getElementById('mu-titre').textContent = id ? 'Modifier un utilisateur' : 'Nouvel utilisateur';
    document.getElementById('mu-username').value = u ? u.username : '';
    document.getElementById('mu-username').disabled = !!id;
    document.getElementById('mu-nom').value = u ? (u.nom || '') : '';
    document.getElementById('mu-prenom').value = u ? (u.prenom || '') : '';
    document.getElementById('mu-email').value = u ? (u.email || '') : '';
    document.getElementById('mu-telephone').value = u ? (u.telephone || '') : '';
    document.getElementById('mu-agence').value = u ? (u.agence || 'BERTOUA') : 'BERTOUA';
    document.getElementById('mu-password').value = '';
    document.getElementById('mu-actif').checked = u ? !!u.actif : true;
    ouvrirModal('modal-utilisateur');
}

function parametresSauverUtilisateur() {
    var id = document.getElementById('mu-id').value;
    var data = {
        nom: document.getElementById('mu-nom').value,
        prenom: document.getElementById('mu-prenom').value,
        email: document.getElementById('mu-email').value,
        telephone: document.getElementById('mu-telephone').value,
        agence: document.getElementById('mu-agence').value,
        password: document.getElementById('mu-password').value
    };
    if (id) {
        data.actif = document.getElementById('mu-actif').checked;
        apiPut('/api/utilisateurs/' + id, data, function() {
            fermerModal('modal-utilisateur');
            status('Utilisateur mis a jour');
            parametresChargerUtilisateurs();
        });
    } else {
        data.username = document.getElementById('mu-username').value;
        if (!data.username || !data.nom) {
            status('⚠ Identifiant et nom requis');
            return;
        }
        apiPost('/api/utilisateurs', data, function() {
            fermerModal('modal-utilisateur');
            status('Utilisateur cree');
            parametresChargerUtilisateurs();
        });
    }
}

function parametresToggleActif(id, actif) {
    apiPut('/api/utilisateurs/' + id, {actif: !!actif}, function() {
        parametresChargerUtilisateurs();
    });
}

// ── Droits d'acces ────────────────────────────────────────────────────────
function parametresChargerUtilisateursPourDroits() {
    apiGet('/api/utilisateurs', function(d) {
        var sel = document.getElementById('dr-utilisateur');
        var html = '';
        (d.utilisateurs || []).forEach(function(u) {
            html += '<option value="' + u.id + '">' + u.username + ' — ' + u.nom + ' ' + (u.prenom || '') + '</option>';
        });
        sel.innerHTML = html;
        if (d.utilisateurs && d.utilisateurs.length) {
            parametresChargerDroits();
        }
    });
}

function parametresChargerDroits() {
    var uid = document.getElementById('dr-utilisateur').value;
    if (!uid) return;
    if (_parametresTree) {
        parametresChargerPermissionsUtilisateur(uid);
        return;
    }
    apiGet('/api/parametres/permissions-tree', function(d) {
        _parametresTree = d.tree;
        parametresChargerPermissionsUtilisateur(uid);
    });
}

function parametresChargerPermissionsUtilisateur(uid) {
    apiGet('/api/utilisateurs/' + uid + '/permissions', function(d) {
        parametresAfficherMatrice(d.permissions || {});
    });
}

function parametresAfficherMatrice(perms) {
    var html = '';
    Object.keys(_parametresTree).forEach(function(module) {
        var m = _parametresTree[module];
        html += '<div class="card" style="margin-bottom:10px">';
        html += '<div class="card-title">' + m.icon + ' ' + m.label + '</div>';
        html += '<div class="tbl-wrap"><table><thead><tr><th>Sous-module</th>' +
            '<th style="width:90px">Lire</th><th style="width:90px">Ecrire</th>' +
            '<th style="width:90px">Supprimer</th></tr></thead><tbody>';
        Object.keys(m.sous_modules).forEach(function(sm) {
            var smdata = m.sous_modules[sm];
            html += '<tr><td>' + smdata.label + '</td>';
            ['lire', 'ecrire', 'supprimer'].forEach(function(action) {
                if (smdata.actions.indexOf(action) === -1) {
                    html += '<td>—</td>';
                } else {
                    var checked = (perms[module] && perms[module][sm] && perms[module][sm][action]) ? 'checked' : '';
                    html += '<td><input type="checkbox" style="width:auto" data-module="' + module +
                        '" data-sm="' + sm + '" data-action="' + action + '" ' + checked + '></td>';
                }
            });
            html += '</tr>';
        });
        html += '</tbody></table></div></div>';
    });
    document.getElementById('dr-matrice').innerHTML = html;
}

function parametresDroitsTout(autorise) {
    document.querySelectorAll('#dr-matrice input[type=checkbox]').forEach(function(c) {
        c.checked = autorise;
    });
}

function parametresAppliquerDroits() {
    var uid = document.getElementById('dr-utilisateur').value;
    if (!uid) return;
    var permissions = {};
    document.querySelectorAll('#dr-matrice input[type=checkbox]').forEach(function(c) {
        var module = c.getAttribute('data-module');
        var sm = c.getAttribute('data-sm');
        var action = c.getAttribute('data-action');
        permissions[module] = permissions[module] || {};
        permissions[module][sm] = permissions[module][sm] || {};
        permissions[module][sm][action] = c.checked;
    });
    apiPost('/api/utilisateurs/' + uid + '/permissions', {permissions: permissions}, function() {
        status('Droits enregistres');
    });
}

// ── Licence ───────────────────────────────────────────────────────────────
function parametresChargerLicence() {
    apiGet('/api/licence/statut', function(d) {
        var lic = d.licence;
        document.getElementById('lic-statut').textContent = lic.valide ? 'Active' : 'Inactive';
        document.getElementById('lic-societe').textContent = lic.nom_societe || '—';
        document.getElementById('lic-expiration').textContent = lic.perpetuelle ? 'Perpetuelle' : (lic.date_expiration || '—');
        document.getElementById('lic-postes').textContent = lic.nb_postes || '—';

        var demoCard = document.getElementById('lic-demo-card');
        if (lic.mode_demo && !lic.valide) {
            demoCard.style.display = '';
            document.getElementById('lic-demo-jours').textContent = lic.jours_demo_restants;
        } else {
            demoCard.style.display = 'none';
        }

        var modulesDiv = document.getElementById('lic-modules');
        if (lic.modules_noms && lic.modules_noms.length) {
            var html = '<div class="card-title">Modules autorises</div>';
            lic.modules_noms.forEach(function(m) {
                html += badge(m, 'ok') + ' ';
            });
            modulesDiv.innerHTML = html;
        } else {
            modulesDiv.innerHTML = '';
        }
    });
}

function parametresVerifierLicence() {
    var numero = document.getElementById('lic-numero').value.trim();
    if (!numero) return;
    apiPost('/api/licence/verifier', {numero: numero}, function(d) {
        var lic = d.licence;
        if (lic.valide) {
            status('✓ Licence valide pour ' + lic.nom_societe);
        } else {
            status('⚠ ' + (lic.erreur || 'Licence invalide'));
        }
    });
}

function parametresActiverLicence() {
    var numero = document.getElementById('lic-numero').value.trim();
    if (!numero) return;
    apiPost('/api/licence/activer', {numero: numero}, function(d) {
        status('✓ Licence activee pour ' + d.licence.nom_societe);
        document.getElementById('lic-numero').value = '';
        parametresChargerLicence();
    });
}

function parametresDesactiverLicence() {
    apiPost('/api/licence/desactiver', {}, function() {
        status('Licence desactivee');
        parametresChargerLicence();
    });
}

// ── Mon compte ────────────────────────────────────────────────────────────
function parametresChangerPassword() {
    var ancien = document.getElementById('mc-ancien').value;
    var nouveau = document.getElementById('mc-nouveau').value;
    var confirmation = document.getElementById('mc-confirmation').value;
    if (!nouveau) {
        status('⚠ Nouveau mot de passe requis');
        return;
    }
    if (nouveau !== confirmation) {
        status('⚠ Les mots de passe ne correspondent pas');
        return;
    }
    apiPost('/api/mon-password', {ancien_password: ancien, nouveau_password: nouveau}, function() {
        status('Mot de passe modifie');
        document.getElementById('mc-ancien').value = '';
        document.getElementById('mc-nouveau').value = '';
        document.getElementById('mc-confirmation').value = '';
    });
}

// ── Chargement initial ───────────────────────────────────────────────────
parametresChargerDashboard();
