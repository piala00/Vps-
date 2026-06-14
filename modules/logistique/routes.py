from flask import render_template, request, jsonify, session, redirect, url_for
from . import bp
from core.database import db_all, db_one, db_exec, db_scalar, has_permission, audit, next_numero
from core.nexora_security import login_required
from core.sage_connector import get_grand_livre_camion


def _peut(uid, sous_module, action='lire'):
    return session.get('is_master') or has_permission(uid, 'logistique', sous_module, action)


@bp.route('/module/logistique')
@login_required
def module_logistique():
    uid = session['user_id']
    if not _peut(uid, 'flotte', 'lire'):
        return redirect(url_for('accueil'))
    return render_template('modules/logistique.html', module='logistique',
                            module_label='🚚 Logistique')


# ── Tableau de bord ────────────────────────────────────────────────────────────
@bp.route('/api/logistique/dashboard-summary')
@login_required
def api_dashboard_summary():
    uid = session['user_id']
    if not _peut(uid, 'flotte', 'lire'):
        return jsonify(ok=False, msg='Acces refuse'), 403

    camions_actifs = db_scalar("SELECT COUNT(*) FROM camions WHERE actif=1") or 0
    voyages_jour = db_scalar(
        "SELECT COUNT(*) FROM voyages WHERE date_depart=date('now')") or 0
    voyages_en_cours = db_scalar(
        "SELECT COUNT(*) FROM voyages WHERE statut='en_cours'") or 0
    entretiens_alerte = db_scalar(
        """SELECT COUNT(*) FROM entretiens
           WHERE prochaine_revision IS NOT NULL AND prochaine_revision != ''
             AND prochaine_revision BETWEEN date('now') AND date('now','+30 days')""") or 0
    recettes_mois = db_scalar(
        """SELECT COALESCE(SUM(montant),0) FROM transactions_camion
           WHERE type_transaction='RECETTE' AND date_transaction >= date('now','start of month')""") or 0
    depenses_mois = db_scalar(
        """SELECT COALESCE(SUM(montant),0) FROM transactions_camion
           WHERE type_transaction='DEPENSE' AND date_transaction >= date('now','start of month')""") or 0

    return jsonify(ok=True, summary={
        'camions_actifs': camions_actifs,
        'voyages_jour': voyages_jour,
        'voyages_en_cours': voyages_en_cours,
        'entretiens_alerte': entretiens_alerte,
        'recettes_mois': recettes_mois,
        'depenses_mois': depenses_mois,
    })


# ── Flotte : camions ────────────────────────────────────────────────────────────
@bp.route('/api/logistique/camions')
@login_required
def api_camions():
    uid = session['user_id']
    if not _peut(uid, 'flotte', 'lire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    return jsonify(ok=True, data=db_all("SELECT * FROM camions ORDER BY immatriculation"))


@bp.route('/api/logistique/camions', methods=['POST'])
@login_required
def api_camion_creer():
    uid = session['user_id']
    if not _peut(uid, 'flotte', 'ecrire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    d = request.json or {}
    immat = d.get('immatriculation', '').strip().upper()
    if not immat:
        return jsonify(ok=False, msg="Immatriculation requise")
    if db_one("SELECT id FROM camions WHERE immatriculation=?", (immat,)):
        return jsonify(ok=False, msg="Cette immatriculation existe deja")

    db_exec("""INSERT INTO camions
        (immatriculation,marque,modele,type_flotte,proprietaire,compte_sage,
         capacite_tonnes,annee_mise_service,observations,actif)
        VALUES(?,?,?,?,?,?,?,?,?,1)""",
        (immat, d.get('marque', ''), d.get('modele', ''),
         d.get('type_flotte', 'MAISON'), d.get('proprietaire', ''), d.get('compte_sage', ''),
         float(d.get('capacite_tonnes', 0) or 0), d.get('annee_mise_service') or None,
         d.get('observations', '')))
    audit(session['username'], 'logistique', 'CREER_CAMION', 'Immat=%s' % immat)
    return jsonify(ok=True, msg='Camion %s cree' % immat)


@bp.route('/api/logistique/camions/<int:camion_id>', methods=['PUT'])
@login_required
def api_camion_modifier(camion_id):
    uid = session['user_id']
    if not _peut(uid, 'flotte', 'ecrire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    c = db_one("SELECT * FROM camions WHERE id=?", (camion_id,))
    if not c:
        return jsonify(ok=False, msg='Camion introuvable')

    d = request.json or {}
    db_exec("""UPDATE camions SET marque=?, modele=?, type_flotte=?, proprietaire=?,
                compte_sage=?, capacite_tonnes=?, annee_mise_service=?, observations=?,
                actif=? WHERE id=?""",
            (d.get('marque', c['marque']), d.get('modele', c['modele']),
             d.get('type_flotte', c['type_flotte']), d.get('proprietaire', c['proprietaire']),
             d.get('compte_sage', c['compte_sage']),
             float(d.get('capacite_tonnes', c['capacite_tonnes']) or 0),
             d.get('annee_mise_service') or c['annee_mise_service'],
             d.get('observations', c['observations']),
             1 if d.get('actif', c['actif']) else 0, camion_id))
    audit(session['username'], 'logistique', 'MODIFIER_CAMION', 'ID=%s' % camion_id)
    return jsonify(ok=True, msg='Camion mis a jour')


# ── Flotte : personnel (chauffeurs / convoyeurs) ────────────────────────────────
@bp.route('/api/logistique/personnel')
@login_required
def api_personnel():
    uid = session['user_id']
    if not _peut(uid, 'chauffeurs', 'lire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    sql = """SELECT p.*, c.immatriculation AS camion_immat
             FROM personnel_logistique p
             LEFT JOIN camions c ON c.id=p.camion_id
             ORDER BY p.nom"""
    return jsonify(ok=True, data=db_all(sql))


@bp.route('/api/logistique/personnel', methods=['POST'])
@login_required
def api_personnel_creer():
    uid = session['user_id']
    if not _peut(uid, 'chauffeurs', 'ecrire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    d = request.json or {}
    nom = d.get('nom', '').strip()
    if not nom:
        return jsonify(ok=False, msg='Nom requis')

    db_exec("""INSERT INTO personnel_logistique
        (nom,prenom,role,telephone,permis,camion_id,actif)
        VALUES(?,?,?,?,?,?,1)""",
        (nom, d.get('prenom', ''), d.get('role', 'CHAUFFEUR'), d.get('telephone', ''),
         d.get('permis', ''), d.get('camion_id') or None))
    audit(session['username'], 'logistique', 'CREER_PERSONNEL', 'Nom=%s' % nom)
    return jsonify(ok=True, msg='%s ajoute' % nom)


@bp.route('/api/logistique/personnel/<int:pid>', methods=['PUT'])
@login_required
def api_personnel_modifier(pid):
    uid = session['user_id']
    if not _peut(uid, 'chauffeurs', 'ecrire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    p = db_one("SELECT * FROM personnel_logistique WHERE id=?", (pid,))
    if not p:
        return jsonify(ok=False, msg='Personnel introuvable')

    d = request.json or {}
    db_exec("""UPDATE personnel_logistique SET nom=?, prenom=?, role=?, telephone=?,
                permis=?, camion_id=?, actif=? WHERE id=?""",
            (d.get('nom', p['nom']), d.get('prenom', p['prenom']), d.get('role', p['role']),
             d.get('telephone', p['telephone']), d.get('permis', p['permis']),
             d.get('camion_id') or p['camion_id'],
             1 if d.get('actif', p['actif']) else 0, pid))
    audit(session['username'], 'logistique', 'MODIFIER_PERSONNEL', 'ID=%s' % pid)
    return jsonify(ok=True, msg='Personnel mis a jour')


# ── Operations : voyages ─────────────────────────────────────────────────────────
@bp.route('/api/logistique/voyages')
@login_required
def api_voyages():
    uid = session['user_id']
    if not _peut(uid, 'voyages', 'lire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    statut = request.args.get('statut', '')
    sql = """SELECT v.*, c.immatriculation AS camion_immat,
                    ch.nom AS chauffeur_nom, cv.nom AS convoyeur_nom
             FROM voyages v
             LEFT JOIN camions c ON c.id=v.camion_id
             LEFT JOIN personnel_logistique ch ON ch.id=v.chauffeur_id
             LEFT JOIN personnel_logistique cv ON cv.id=v.convoyeur_id
             WHERE 1=1"""
    params = []
    if statut:
        sql += " AND v.statut=?"
        params.append(statut)
    sql += " ORDER BY v.id DESC"
    return jsonify(ok=True, data=db_all(sql, tuple(params)))


@bp.route('/api/logistique/voyages', methods=['POST'])
@login_required
def api_voyage_creer():
    uid = session['user_id']
    if not _peut(uid, 'voyages', 'ecrire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    d = request.json or {}
    camion_id = d.get('camion_id')
    origine = d.get('origine', '').strip()
    destination = d.get('destination', '').strip()
    if not camion_id or not origine or not destination:
        return jsonify(ok=False, msg='Donnees incompletes')

    numero = next_numero('VOY')
    db_exec("""INSERT INTO voyages
        (no_voyage,camion_id,chauffeur_id,convoyeur_id,origine,destination,
         date_depart,date_retour,marchandises,client_fournisseur,statut,observations)
        VALUES(?,?,?,?,?,?,?,?,?,?,?,?)""",
        (numero, camion_id, d.get('chauffeur_id') or None, d.get('convoyeur_id') or None,
         origine, destination, d.get('date_depart', ''), d.get('date_retour', ''),
         d.get('marchandises', ''), d.get('client_fournisseur', ''),
         d.get('statut', 'planifie'), d.get('observations', '')))
    audit(session['username'], 'logistique', 'CREER_VOYAGE', 'N=%s' % numero)
    return jsonify(ok=True, msg='Voyage %s cree' % numero, numero=numero)


@bp.route('/api/logistique/voyages/<int:vid>', methods=['PUT'])
@login_required
def api_voyage_modifier(vid):
    uid = session['user_id']
    if not _peut(uid, 'voyages', 'ecrire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    v = db_one("SELECT * FROM voyages WHERE id=?", (vid,))
    if not v:
        return jsonify(ok=False, msg='Voyage introuvable')

    d = request.json or {}
    db_exec("""UPDATE voyages SET camion_id=?, chauffeur_id=?, convoyeur_id=?, origine=?,
                destination=?, date_depart=?, date_retour=?, marchandises=?,
                client_fournisseur=?, statut=?, observations=? WHERE id=?""",
            (d.get('camion_id', v['camion_id']), d.get('chauffeur_id') or v['chauffeur_id'],
             d.get('convoyeur_id') or v['convoyeur_id'], d.get('origine', v['origine']),
             d.get('destination', v['destination']), d.get('date_depart', v['date_depart']),
             d.get('date_retour', v['date_retour']), d.get('marchandises', v['marchandises']),
             d.get('client_fournisseur', v['client_fournisseur']),
             d.get('statut', v['statut']), d.get('observations', v['observations']), vid))
    audit(session['username'], 'logistique', 'MODIFIER_VOYAGE',
          'N=%s -> %s' % (v['no_voyage'], d.get('statut', v['statut'])))
    return jsonify(ok=True, msg='Voyage %s mis a jour' % v['no_voyage'])


# ── Operations : entretiens ────────────────────────────────────────────────────
@bp.route('/api/logistique/entretiens')
@login_required
def api_entretiens():
    uid = session['user_id']
    if not _peut(uid, 'entretiens', 'lire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    sql = """SELECT e.*, c.immatriculation AS camion_immat
             FROM entretiens e
             LEFT JOIN camions c ON c.id=e.camion_id
             ORDER BY e.date_entretien DESC, e.id DESC"""
    return jsonify(ok=True, data=db_all(sql))


@bp.route('/api/logistique/entretiens', methods=['POST'])
@login_required
def api_entretien_creer():
    uid = session['user_id']
    if not _peut(uid, 'entretiens', 'ecrire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    d = request.json or {}
    camion_id = d.get('camion_id')
    type_entretien = d.get('type_entretien', '').strip()
    if not camion_id or not type_entretien:
        return jsonify(ok=False, msg='Donnees incompletes')

    db_exec("""INSERT INTO entretiens
        (camion_id,type_entretien,date_entretien,kilometrage,cout,prestataire,
         description,prochaine_revision)
        VALUES(?,?,?,?,?,?,?,?)""",
        (camion_id, type_entretien, d.get('date_entretien', ''),
         int(d.get('kilometrage', 0) or 0), float(d.get('cout', 0) or 0),
         d.get('prestataire', ''), d.get('description', ''), d.get('prochaine_revision', '')))
    audit(session['username'], 'logistique', 'CREER_ENTRETIEN',
          'Camion=%s Type=%s' % (camion_id, type_entretien))
    return jsonify(ok=True, msg='Entretien enregistre')


# ── Comptabilite : transactions camion (recettes/depenses) ─────────────────────
@bp.route('/api/logistique/transactions')
@login_required
def api_transactions():
    uid = session['user_id']
    if not _peut(uid, 'compta_cams', 'lire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    camion_id = request.args.get('camion_id', '')
    sql = """SELECT t.*, c.immatriculation AS camion_immat, v.no_voyage
             FROM transactions_camion t
             LEFT JOIN camions c ON c.id=t.camion_id
             LEFT JOIN voyages v ON v.id=t.voyage_id
             WHERE 1=1"""
    params = []
    if camion_id:
        sql += " AND t.camion_id=?"
        params.append(camion_id)
    sql += " ORDER BY t.date_transaction DESC, t.id DESC"
    return jsonify(ok=True, data=db_all(sql, tuple(params)))


@bp.route('/api/logistique/transactions', methods=['POST'])
@login_required
def api_transaction_creer():
    uid = session['user_id']
    if not _peut(uid, 'compta_cams', 'ecrire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    d = request.json or {}
    camion_id = d.get('camion_id')
    montant = float(d.get('montant', 0) or 0)
    if not camion_id or not montant:
        return jsonify(ok=False, msg='Donnees incompletes')

    db_exec("""INSERT INTO transactions_camion
        (camion_id,voyage_id,type_transaction,categorie,date_transaction,montant,
         libelle,reference_sage,saisi_par)
        VALUES(?,?,?,?,?,?,?,?,?)""",
        (camion_id, d.get('voyage_id') or None, d.get('type_transaction', 'DEPENSE'),
         d.get('categorie', 'AUTRE'), d.get('date_transaction', ''), montant,
         d.get('libelle', ''), d.get('reference_sage', ''), session['username']))
    audit(session['username'], 'logistique', 'CREER_TRANSACTION_CAMION',
          'Camion=%s Montant=%s' % (camion_id, montant))
    return jsonify(ok=True, msg='Transaction enregistree')


# ── Comptabilite : grand livre camion (local + Sage) ─────────────────────────────
@bp.route('/api/logistique/grand-livre-camion')
@login_required
def api_grand_livre_camion():
    uid = session['user_id']
    if not _peut(uid, 'compta_cams', 'lire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    camion_id = request.args.get('camion_id', '')
    if not camion_id:
        return jsonify(ok=False, msg='camion_id requis')
    c = db_one("SELECT * FROM camions WHERE id=?", (camion_id,))
    if not c:
        return jsonify(ok=False, msg='Camion introuvable')

    locales = db_all(
        """SELECT date_transaction AS date, 'NEXORA' AS source, type_transaction,
                  categorie, montant, libelle, reference_sage
           FROM transactions_camion WHERE camion_id=? ORDER BY date_transaction""",
        (camion_id,))

    sage = []
    if c['compte_sage']:
        for e in get_grand_livre_camion(c['compte_sage']):
            sage.append({
                'date': e.get('date_ecriture'),
                'source': 'SAGE',
                'type_transaction': 'DEPENSE' if (e.get('debit') or 0) > 0 else 'RECETTE',
                'categorie': e.get('journal', ''),
                'montant': e.get('debit') or e.get('credit') or 0,
                'libelle': e.get('libelle', ''),
                'reference_sage': e.get('piece', ''),
            })

    lignes = sorted(locales + sage, key=lambda x: x.get('date') or '')
    return jsonify(ok=True, camion=c, data=lignes)


# ── Comptabilite : rapprochement camion (local vs Sage) ─────────────────────────
@bp.route('/api/logistique/rapprochement-camion')
@login_required
def api_rapprochement_camion():
    uid = session['user_id']
    if not _peut(uid, 'rapproch_log', 'lire'):
        return jsonify(ok=False, msg='Acces refuse'), 403
    camion_id = request.args.get('camion_id', '')
    if not camion_id:
        return jsonify(ok=False, msg='camion_id requis')
    c = db_one("SELECT * FROM camions WHERE id=?", (camion_id,))
    if not c:
        return jsonify(ok=False, msg='Camion introuvable')

    local_recettes = db_scalar(
        "SELECT COALESCE(SUM(montant),0) FROM transactions_camion WHERE camion_id=? AND type_transaction='RECETTE'",
        (camion_id,)) or 0
    local_depenses = db_scalar(
        "SELECT COALESCE(SUM(montant),0) FROM transactions_camion WHERE camion_id=? AND type_transaction='DEPENSE'",
        (camion_id,)) or 0

    sage_debit = 0.0
    sage_credit = 0.0
    if c['compte_sage']:
        for e in get_grand_livre_camion(c['compte_sage']):
            sage_debit += float(e.get('debit') or 0)
            sage_credit += float(e.get('credit') or 0)

    return jsonify(ok=True, camion=c, rapprochement={
        'local_recettes': local_recettes,
        'local_depenses': local_depenses,
        'sage_debit': sage_debit,
        'sage_credit': sage_credit,
        'ecart_recettes': round(local_recettes - sage_credit, 2),
        'ecart_depenses': round(local_depenses - sage_debit, 2),
    })
