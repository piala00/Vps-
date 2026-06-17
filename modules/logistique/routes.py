"""NEXORA v2.0 - Module Logistique"""
from flask import render_template, jsonify, session, request
from . import bp
from core.auth import login_required, get_user
from core.database import get_config, PERMISSIONS_TREE, db_all, db_one, db_exec

@bp.route("/module/logistique")
@login_required
def module_logistique():
    user    = get_user()
    modules = session.get("modules", [])
    cfg     = {"nom_societe": get_config("nom_societe",""),
               "devise": get_config("devise","XAF")}
    return render_template("modules/logistique.html",
        module="logistique", module_label="Logistique",
        user=user, modules=modules, config=cfg,
        tree=PERMISSIONS_TREE)

@bp.route('/api/logistique/camions', methods=['GET','POST'])
@login_required
def api_camions():
    if request.method == 'POST':
        d = request.get_json() or {}
        if not d.get('immatriculation'):
            return jsonify({'ok':False,'msg':'Immatriculation obligatoire'})
        uid = db_exec(
            "INSERT INTO camions(immatriculation,marque,modele,type_flotte,proprietaire,compte_sage,capacite_tonnes,observations)"
            " VALUES(?,?,?,?,?,?,?,?)",
            (d['immatriculation'], d.get('marque',''), d.get('modele',''),
             d.get('type_flotte','MAISON'), d.get('proprietaire',''),
             d.get('compte_sage',''), float(d.get('capacite_tonnes',0)),
             d.get('observations','')))
        return jsonify({'ok':True,'id':uid})
    rows = db_all("SELECT * FROM camions WHERE actif=1 ORDER BY immatriculation")
    return jsonify({'ok':True,'camions':rows})

@bp.route('/api/logistique/personnel', methods=['GET','POST'])
@login_required
def api_personnel():
    if request.method == 'POST':
        d = request.get_json() or {}
        uid = db_exec(
            "INSERT INTO personnel_logistique(nom,prenom,role,telephone,permis,camion_id)"
            " VALUES(?,?,?,?,?,?)",
            (d.get('nom',''), d.get('prenom',''), d.get('role','CHAUFFEUR'),
             d.get('telephone',''), d.get('permis',''), d.get('camion_id')))
        return jsonify({'ok':True,'id':uid})
    rows = db_all("SELECT p.*, c.immatriculation FROM personnel_logistique p "
                  "LEFT JOIN camions c ON c.id=p.camion_id WHERE p.actif=1 ORDER BY p.nom")
    return jsonify({'ok':True,'personnel':rows})

@bp.route('/api/logistique/voyages', methods=['GET','POST'])
@login_required
def api_voyages():
    if request.method == 'POST':
        d   = request.get_json() or {}
        from datetime import date
        import random, string
        no  = 'VOY' + date.today().strftime('%Y%m%d') + ''.join(random.choices(string.digits, k=4))
        uid = db_exec(
            "INSERT INTO voyages(no_voyage,camion_id,chauffeur_id,convoyeur_id,origine,destination,"
            "date_depart,date_retour,marchandises,client_fournisseur,statut,observations)"
            " VALUES(?,?,?,?,?,?,?,?,?,?,?,?)",
            (no, d.get('camion_id'), d.get('chauffeur_id'), d.get('convoyeur_id'),
             d.get('origine',''), d.get('destination',''),
             d.get('date_depart',''), d.get('date_retour',''),
             d.get('marchandises',''), d.get('client_fournisseur',''),
             d.get('statut','planifie'), d.get('observations','')))
        return jsonify({'ok':True,'id':uid,'no_voyage':no})
    statut = request.args.get('statut','')
    sql    = "SELECT v.*, c.immatriculation, p.nom chauffeur_nom FROM voyages v LEFT JOIN camions c ON c.id=v.camion_id LEFT JOIN personnel_logistique p ON p.id=v.chauffeur_id"
    if statut:
        sql += " WHERE v.statut='" + statut + "'"
    sql += " ORDER BY v.date_depart DESC LIMIT 100"
    return jsonify({'ok':True,'voyages':db_all(sql)})

@bp.route('/api/logistique/transactions', methods=['GET','POST'])
@login_required
def api_transactions():
    if request.method == 'POST':
        d   = request.get_json() or {}
        uid = db_exec(
            "INSERT INTO transactions_camion(camion_id,voyage_id,type_transaction,categorie,"
            "date_transaction,montant,libelle,saisi_par) VALUES(?,?,?,?,?,?,?,?)",
            (d.get('camion_id'), d.get('voyage_id'), d.get('type_transaction','DEPENSE'),
             d.get('categorie','AUTRE'), d.get('date_transaction',''),
             float(d.get('montant',0)), d.get('libelle',''), session.get('username','')))
        return jsonify({'ok':True,'id':uid})
    camion_id = request.args.get('camion_id','')
    sql = "SELECT t.*, c.immatriculation FROM transactions_camion t LEFT JOIN camions c ON c.id=t.camion_id"
    params = []
    if camion_id:
        sql += " WHERE t.camion_id=?"
        params.append(camion_id)
    sql += " ORDER BY t.date_transaction DESC LIMIT 100"
    return jsonify({'ok':True,'transactions':db_all(sql, params)})

@bp.route('/api/logistique/entretiens', methods=['GET','POST'])
@login_required
def api_entretiens():
    if request.method == 'POST':
        d   = request.get_json() or {}
        uid = db_exec(
            "INSERT INTO entretiens(camion_id,type_entretien,date_entretien,kilometrage,"
            "cout,prestataire,description,prochaine_revision) VALUES(?,?,?,?,?,?,?,?)",
            (d.get('camion_id'), d.get('type_entretien','AUTRE'),
             d.get('date_entretien',''), int(d.get('kilometrage',0)),
             float(d.get('cout',0)), d.get('prestataire',''),
             d.get('description',''), d.get('prochaine_revision','')))
        return jsonify({'ok':True,'id':uid})
    cam = request.args.get('camion_id','')
    sql = "SELECT e.*, c.immatriculation FROM entretiens e LEFT JOIN camions c ON c.id=e.camion_id"
    params = []
    if cam:
        sql += " WHERE e.camion_id=?"
        params.append(cam)
    sql += " ORDER BY e.date_entretien DESC LIMIT 100"
    return jsonify({'ok':True,'entretiens':db_all(sql, params)})
