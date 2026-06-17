"""
NEXORA v2.0 — Bot Telegram
Reintegration complete et fidele du BotManager de GTC ERP PILOT V3.
Lit les snapshots depuis la table data_snapshot (SQLite NEXORA).
Pattern python-telegram-bot v20+ : asyncio.new_event_loop() dans thread daemon.
"""
import asyncio, threading, logging, unicodedata, json as _json
from datetime import datetime
from collections import deque

log = logging.getLogger('NEXORA.Bot')

# File d'activite bot (visible dans Parametres > Journal / Bot Telegram)
BOT_LOG_QUEUE = deque(maxlen=200)


def _bot_log(msg: str):
    ts = datetime.now().strftime('%H:%M:%S')
    entry = f"[{ts}] {msg}"
    BOT_LOG_QUEUE.append(entry)
    log.info("BOT: %s", msg)


def get_bot_log(limit=50):
    return list(BOT_LOG_QUEUE)[-limit:]


def _norm(v):
    s = '' if v is None else str(v).strip().upper()
    s = ''.join(c for c in unicodedata.normalize('NFD', s) if unicodedata.category(c) != 'Mn')
    return ' '.join(s.replace('_', ' ').split())


class BotManager:
    """
    Bot Telegram intelligent — lit les donnees depuis SQLite (meme si NEXORA
    tourne en arriere-plan). Reproduit fidelement toutes les commandes et
    la logique par role de GTC ERP PILOT V3.
    """

    def __init__(self, db_get_config, db_get_snapshot, db_get_snapshot_age,
                 db_get_user_by_telegram, db_get_agence_coms, db_save_inscription,
                 db_get_bot_config):
        self.get_config            = db_get_config
        self.get_snapshot          = db_get_snapshot
        self.get_snapshot_age      = db_get_snapshot_age
        self.get_user_by_telegram  = db_get_user_by_telegram
        self.get_agence_coms       = db_get_agence_coms
        self.save_inscription      = db_save_inscription
        self.get_bot_config        = db_get_bot_config
        self._thread = None
        self._loop   = None
        self._ptb    = None
        self._token  = None
        self.running = False

    # ── API publique ────────────────────────────────────────────────────────

    def start(self, token: str):
        if self.running:
            return
        if not token or len(token) < 10:
            _bot_log("Token invalide")
            return
        self._token  = token
        self.running = True
        self._thread = threading.Thread(target=self._run, daemon=True, name='NEXORA-Bot')
        self._thread.start()

    def stop(self):
        self.running = False
        if self._loop and not self._loop.is_closed():
            try:
                self._loop.call_soon_threadsafe(self._loop.stop)
            except Exception:
                pass

    # ── Helpers DB ──────────────────────────────────────────────────────────

    def _snap(self, key):
        return self.get_snapshot(key) or {}

    def _snap_list(self, key):
        r = self.get_snapshot(key)
        return r if isinstance(r, list) else []

    # ── Formatage messages ─────────────────────────────────────────────────

    @staticmethod
    def _fmt(v) -> str:
        try:
            return f"{float(v):,.0f}".replace(',', ' ')
        except Exception:
            return str(v)

    @staticmethod
    def _bar(pct: float, width: int = 12) -> str:
        pct    = max(0.0, min(1.0, pct))
        filled = round(pct * width)
        return '█' * filled + '░' * (width - filled) + f"  {pct*100:.0f}%"

    @staticmethod
    def _trend(v: float) -> str:
        if v >= 80: return '🟢'
        if v >= 50: return '🟡'
        if v >= 20: return '🟠'
        return '🔴'

    @staticmethod
    def _risk(v: float) -> str:
        if v >= 70: return '🚨 CRITIQUE'
        if v >= 40: return '⚠️ ÉLEVÉ'
        if v >= 10: return '🟡 MODÉRÉ'
        return '🟢 FAIBLE'

    def _menu_pour_role(self, role: str) -> str:
        menus = {
            'admin':      "• /start      — Accueil\n• /situation  — Vue globale\n• /classement — Classement NEXORA\n• /cockpit    — Dashboard DG\n• /creances   — Créances détaillées\n• /alertes    — Alertes clients\n• /analyse    — Analyse comparative\n• /aide       — Aide",
            'direction':  "• /start      — Accueil\n• /situation  — Vue globale\n• /classement — Classement NEXORA\n• /cockpit    — Dashboard direction\n• /creances   — Créances détaillées\n• /alertes    — Alertes clients\n• /analyse    — Analyse comparative\n• /aide       — Aide",
            'financier':  "• /start      — Accueil\n• /situation  — Situation financière\n• /cockpit    — Tableau de bord financier\n• /creances   — Créances & retards\n• /alertes    — Alertes clients\n• /aide       — Aide",
            'agence':     "• /start      — Accueil\n• /situation  — Situation agence\n• /classement — Classement agence\n• /cockpit    — Cockpit agence\n• /creances   — Créances agence\n• /aide       — Aide",
            'commercial': "• /start      — Accueil\n• /cockpit    — Mon cockpit personnel\n• /aide       — Aide",
        }
        return menus.get(role, "• /aide — Aide")

    # ── Thread principal ────────────────────────────────────────────────────

    def _run(self):
        try:
            from telegram.ext import (Application, CommandHandler, MessageHandler,
                                       filters, ConversationHandler, CallbackQueryHandler)
            from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
        except ImportError:
            _bot_log("'python-telegram-bot' non installe — pip install python-telegram-bot")
            self.running = False
            return

        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        _bot_log("Démarrage du bot NEXORA...")

        F = self._fmt
        B = self._bar
        T = self._trend
        R = self._risk

        def _sep(): return '━' * 30

        async def _check_user(update):
            tg_id = str(update.effective_user.id)
            u = self.get_user_by_telegram(tg_id)
            if not u:
                await update.message.reply_text(
                    "⛔ *Accès refusé — Compte non reconnu*\n\n"
                    "Votre Telegram n'est pas lié à un compte NEXORA.\n\n"
                    "👉 Tapez /inscription pour faire une demande d'accès\n"
                    "   _(un administrateur validera votre demande)_",
                    parse_mode='Markdown')
            return u

        # ── /start ──
        async def cmd_start(update: Update, ctx):
            tg = update.effective_user
            u  = self.get_user_by_telegram(str(tg.id))
            _bot_log(f"/start <- {tg.first_name} ({tg.id})")
            if u:
                icons = {'admin':'🔑','direction':'🏛','financier':'💰','agence':'🏢','commercial':'👤'}
                icon  = icons.get(u['role'], '👤')
                await update.message.reply_text(
                    f"╔══════════════════════════╗\n"
                    f"║   🏢  NEXORA ERP v2.0    ║\n"
                    f"╚══════════════════════════╝\n\n"
                    f"👋 Bonjour *{tg.first_name}* !\n\n"
                    f"{icon} *{u['username'].upper()}*\n"
                    f"🎖 Rôle   : *{u['role'].upper()}*\n"
                    f"📋 Poste  : {u.get('poste') or '—'}\n"
                    f"📍 Agence : {u.get('agence') or '—'}\n\n"
                    f"*Vos commandes :*\n{self._menu_pour_role(u['role'])}",
                    parse_mode='Markdown')
            else:
                await update.message.reply_text(
                    f"👋 Bonjour *{tg.first_name}* !\n\n"
                    f"Vous n'êtes pas encore enregistré sur NEXORA.\n"
                    f"Tapez /inscription pour faire une demande d'accès.",
                    parse_mode='Markdown')

        # ── /situation ──
        async def cmd_situation(update: Update, ctx):
            u = await _check_user(update)
            if not u: return
            _bot_log(f"/situation <- {u['username']} [{u['role']}]")
            if u['role'] not in ('admin','direction','financier','agence'):
                await update.message.reply_text("⛔ Commande réservée aux managers et à la direction.")
                return
            kpis   = self._snap('kpis') or {}
            period = self._snap('period') or {}
            clas   = self._snap_list('classement')
            ca, rec  = kpis.get('ca',0), kpis.get('recouvrement',0)
            fns, sol = kpis.get('fns',0), kpis.get('solde',0)
            nbcl, nbret, taux = kpis.get('nb_clients',0), kpis.get('nb_retard',0), kpis.get('taux_rec',0)
            if u['role'] == 'agence':
                ag_c    = self.get_agence_coms(u.get('agence',''))
                clas_ag = [r for r in clas if _norm(r.get('commercial','')) in ag_c]
                ca   = sum(r.get('ca',0) for r in clas_ag)
                rec  = sum(r.get('recouvrement',0) for r in clas_ag)
                fns  = sum(r.get('fns',0) for r in clas_ag)
                taux = (rec/ca*100) if ca else 0
                nbcl = len(clas_ag)
            titre = f"SITUATION — {u.get('agence','')}" if u['role']=='agence' else "SITUATION GLOBALE NEXORA"
            await update.message.reply_text(
                f"📊 *{titre}*\n_{period.get('label','—')}_\n{_sep()}\n"
                f"💰 *CHIFFRE D'AFFAIRES*\n   {F(ca)} FCFA\n\n"
                f"✅ *RECOUVREMENT*\n   {F(rec)} FCFA\n   {B(taux/100)} {T(taux)}\n\n"
                f"🔴 *CRÉANCES IMPAYÉES*\n   {F(fns)} FCFA\n\n"
                f"🏦 *SOLDE CLIENTS*\n   {F(sol)} FCFA\n{_sep()}\n"
                f"👥 Clients actifs     : *{nbcl}*\n"
                f"⚠️  Clients en retard : *{nbret}*\n"
                f"📈 Taux recouvrement  : *{taux:.2f}%*\n{_sep()}\n"
                f"🕐 _{self.get_snapshot_age()}_",
                parse_mode='Markdown')

        # ── /classement ──
        async def cmd_classement(update: Update, ctx):
            u = await _check_user(update)
            if not u: return
            _bot_log(f"/classement <- {u['username']} [{u['role']}]")
            if u['role'] not in ('admin','direction','financier','agence'):
                await update.message.reply_text("⛔ Commande non autorisée pour votre rôle.")
                return
            clas = self._snap_list('classement')
            if not clas:
                await update.message.reply_text("⏳ Pas de données.\nActualisez NEXORA.")
                return
            if u['role'] == 'agence':
                ag_c  = self.get_agence_coms(u.get('agence',''))
                clas  = [r for r in clas if _norm(r.get('commercial','')) in ag_c]
                titre = f"🏢 CLASSEMENT AGENCE\n{u.get('agence','')}"
            else:
                titre = "🏅 CLASSEMENT GÉNÉRAL NEXORA"
            medals = ['🥇','🥈','🥉'] + [f"  {i}." for i in range(4,21)]
            lines  = [f"*{titre}*", _sep()]
            ca_tot = sum(r.get('ca',0) for r in clas) or 1
            for i, r in enumerate(clas[:10]):
                nom  = str(r.get('commercial','—'))[:24]
                ca, rec, obj, fns = r.get('ca',0), r.get('recouvrement',0), r.get('objectif',0), r.get('fns',0)
                taux  = (rec/ca*100) if ca else 0
                pct_o = r.get('pct_obj',0)
                part  = (ca/ca_tot*100)
                lines.append(
                    f"{medals[i]} *{nom}*\n"
                    f"   💰 CA       : {F(ca)} FCFA\n"
                    f"   🎯 Objectif : {F(obj)} FCFA  ({pct_o:.1f}%)\n"
                    f"   ✅ Recouv.  : {F(rec)} FCFA  {T(taux)}\n"
                    f"   📊 Taux     : {B(taux/100,10)}\n"
                    f"   🔴 Créances : {F(fns)} FCFA\n"
                    f"   📈 Part CA  : {part:.1f}%")
            lines.append(f"\n🕐 _{self.get_snapshot_age()}_")
            msg = "\n".join(lines)
            if len(msg) > 4000:
                for chunk in [msg[i:i+4000] for i in range(0,len(msg),4000)]:
                    await update.message.reply_text(chunk, parse_mode='Markdown')
            else:
                await update.message.reply_text(msg, parse_mode='Markdown')

        # ── /cockpit (5 vues selon role) ──
        async def cmd_cockpit(update: Update, ctx):
            u = await _check_user(update)
            if not u: return
            _bot_log(f"/cockpit <- {u['username']} [{u['role']}]")
            clas     = self._snap_list('classement')
            kpis     = self._snap('kpis') or {}
            period   = self._snap('period') or {}
            creances = self._snap_list('creances')
            alertes  = self._snap_list('alertes')
            role     = u['role']

            if role in ('admin','direction'):
                ca, rec  = kpis.get('ca',0), kpis.get('recouvrement',0)
                fns, sol = kpis.get('fns',0), kpis.get('solde',0)
                taux     = (rec/ca*100) if ca else 0
                nbcl, nbret = kpis.get('nb_clients',0), kpis.get('nb_retard',0)
                crit = sum(1 for a in alertes if a.get('niveau')=='CRITIQUE')
                top3 = clas[:3]; medals=['🥇','🥈','🥉']
                top_lines = "\n".join(
                    f"   {medals[i]} *{r.get('commercial','')[:22]}*\n"
                    f"      CA: {F(r.get('ca',0))} FCFA | {T((r.get('recouvrement',0)/r.get('ca',1)*100) if r.get('ca',0) else 0)} {(r.get('recouvrement',0)/r.get('ca',1)*100) if r.get('ca',0) else 0:.1f}%"
                    for i, r in enumerate(top3))
                await update.message.reply_text(
                    f"🏛 *DASHBOARD DIRECTION GÉNÉRALE*\n_{period.get('label','—')}_\n{_sep()}\n"
                    f"💰 *CA Global*\n   {F(ca)} FCFA\n\n"
                    f"✅ *Recouvrement global*\n   {F(rec)} FCFA\n   {B(taux/100)} {T(taux)}\n\n"
                    f"🔴 *Créances impayées*\n   {F(fns)} FCFA\n"
                    f"🏦 *Solde clients*\n   {F(sol)} FCFA\n{_sep()}\n"
                    f"👥 Clients actifs    : *{nbcl}*\n"
                    f"⚠️  Clients en retard : *{nbret}*\n"
                    f"🚨 Alertes critiques : *{crit}*\n"
                    f"📊 Commerciaux       : *{len(clas)}*\n{_sep()}\n"
                    f"🏆 *TOP 3 COMMERCIAUX :*\n{top_lines}\n{_sep()}\n"
                    f"🕐 _{self.get_snapshot_age()}_",
                    parse_mode='Markdown')
                return

            if role == 'financier':
                crit_l = [a for a in alertes if a.get('niveau')=='CRITIQUE']
                alrt_l = [a for a in alertes if a.get('niveau')=='ALERTE']
                suiv_l = [a for a in alertes if a.get('niveau')=='SUIVI']
                tot_fns = sum(c.get('fns',0) for c in creances)
                tot_sol = sum(c.get('solde',0) for c in creances if c.get('solde',0)>0)
                top_ret = sorted([c for c in creances if c.get('retard',0)>0],
                                  key=lambda x: x.get('fns',0), reverse=True)[:5]
                lines = [
                    f"💰 *TABLEAU DE BORD FINANCIER*\n{_sep()}",
                    f"🔴 *CRÉANCES ÉCHUES (retard > 0)*\n   {F(tot_fns)} FCFA",
                    f"🏦 *SOLDE GLOBAL CLIENTS*\n   {F(tot_sol)} FCFA",
                    _sep(),
                    f"🚨 Alertes CRITIQUES  (>30j) : *{len(crit_l)}*",
                    f"🟠 Alertes PLAFOND dépassé  : *{len(alrt_l)}*",
                    f"🟡 En SUIVI (factures ouv.) : *{len(suiv_l)}*",
                ]
                if top_ret:
                    lines.append("\n🚨 *TOP 5 CLIENTS URGENTS :*")
                    for c in top_ret:
                        risk = R(c.get('risque',0)*100)
                        lines.append(
                            f"  • *{c.get('nom','')[:22]}*\n"
                            f"    Créances : {F(c.get('fns',0))} FCFA\n"
                            f"    Retard   : {c.get('retard',0)} jours\n"
                            f"    Risque   : {risk}")
                lines.append(f"\n🕐 _{self.get_snapshot_age()}_")
                await update.message.reply_text("\n".join(lines), parse_mode='Markdown')
                return

            if role == 'agence':
                ag_c    = self.get_agence_coms(u.get('agence',''))
                clas_ag = [r for r in clas if _norm(r.get('commercial','')) in ag_c]
                ca_ag   = sum(r.get('ca',0) for r in clas_ag)
                rec_ag  = sum(r.get('recouvrement',0) for r in clas_ag)
                fns_ag  = sum(r.get('fns',0) for r in clas_ag)
                taux_ag = (rec_ag/ca_ag*100) if ca_ag else 0
                medals  = ['🥇','🥈','🥉'] + ['  ·'] * 20
                detail_lines = "\n".join(
                    f"   {medals[i]} *{r.get('commercial','')[:22]}*\n"
                    f"      CA: {F(r.get('ca',0))} FCFA\n"
                    f"      Recouv: {F(r.get('recouvrement',0))} FCFA  {T((r.get('recouvrement',0)/r.get('ca',1)*100) if r.get('ca',0) else 0)}"
                    for i, r in enumerate(clas_ag[:8]))
                await update.message.reply_text(
                    f"🏢 *COCKPIT AGENCE*\n*{u.get('agence','')}*\n_{period.get('label','—')}_\n{_sep()}\n"
                    f"💰 *CA Agence*\n   {F(ca_ag)} FCFA\n\n"
                    f"✅ *Recouvrement*\n   {F(rec_ag)} FCFA\n   {B(taux_ag/100)} {T(taux_ag)}\n\n"
                    f"🔴 *Créances agence*\n   {F(fns_ag)} FCFA\n"
                    f"👥 *Commerciaux* : {len(clas_ag)}\n{_sep()}\n"
                    f"📊 *PERFORMANCE ÉQUIPE :*\n{detail_lines}\n{_sep()}\n"
                    f"🕐 _{self.get_snapshot_age()}_",
                    parse_mode='Markdown')
                return

            if role == 'commercial':
                com_name = u.get('commercial_name','') or u.get('com','')
                if not com_name:
                    await update.message.reply_text("⚠️ Aucun commercial lié à votre compte.\nContactez l'admin.")
                    return
                com_row = next((r for r in clas if _norm(r.get('commercial','')) == _norm(com_name)), None)
                if not com_row:
                    await update.message.reply_text(f"⚠️ Pas de données pour *{com_name}*.\nVérifiez la config.", parse_mode='Markdown')
                    return
                ca, rec, fns, obj = com_row.get('ca',0), com_row.get('recouvrement',0), com_row.get('fns',0), com_row.get('objectif',0)
                pct_o  = com_row.get('pct_obj',0)
                taux   = (rec/ca*100) if ca else 0
                risque = com_row.get('risque',0)*100
                rang   = com_row.get('rang','—')
                nb_ret = com_row.get('nb_retard',0)
                mes_cre = [c for c in creances if _norm(c.get('commercial','')) == _norm(com_name)]
                sol_tot = sum(c.get('solde',0) for c in mes_cre if c.get('solde',0)>0)
                top_cl  = sorted(mes_cre, key=lambda x: x.get('fns',0), reverse=True)[:5]
                cl_lines = "\n".join(
                    f"   • *{c.get('nom','')[:22]}*\n"
                    f"     Solde: {F(c.get('solde',0))} | Créance: {F(c.get('fns',0))} | {c.get('retard',0)}j"
                    for c in top_cl if c.get('fns',0)>0 or c.get('solde',0)>0
                ) or "   Aucune créance en cours ✅"
                await update.message.reply_text(
                    f"🧭 *MON COCKPIT PERSONNEL*\n👤 *{com_name.upper()}*\n_{period.get('label','—')}_\n{_sep()}\n"
                    f"💰 *CA RÉALISÉ*\n   {F(ca)} FCFA\n\n"
                    f"🎯 *OBJECTIF*\n   {F(obj)} FCFA\n   Progression : {B(pct_o,12)} {pct_o*100:.1f}%\n\n"
                    f"✅ *RECOUVREMENT*\n   {F(rec)} FCFA\n   {B(taux/100,12)} {T(taux)}\n\n"
                    f"🔴 *CRÉANCES ÉCHUES*\n   {F(fns)} FCFA\n   Risque : {R(risque)}\n\n"
                    f"🏦 *SOLDE CLIENTS*\n   {F(sol_tot)} FCFA\n{_sep()}\n"
                    f"⚠️  Clients en retard : *{nb_ret}*\n"
                    f"🏅 Classement général : *#{rang}*\n{_sep()}\n"
                    f"📋 *MES PRINCIPAUX CLIENTS :*\n{cl_lines}\n{_sep()}\n"
                    f"📍 {u.get('poste','')} | {u.get('agence','')}\n"
                    f"🕐 _{self.get_snapshot_age()}_",
                    parse_mode='Markdown')
                return

        # ── /creances ──
        async def cmd_creances(update: Update, ctx):
            u = await _check_user(update)
            if not u: return
            _bot_log(f"/creances <- {u['username']} [{u['role']}]")
            if u['role'] == 'commercial':
                await update.message.reply_text("⛔ Accès non autorisé.")
                return
            creances = self._snap_list('creances')
            if u['role'] == 'agence':
                ag_c     = self.get_agence_coms(u.get('agence',''))
                creances = [c for c in creances if _norm(c.get('commercial','')) in ag_c]
            avec_ret = sorted([c for c in creances if c.get('retard',0)>0],
                              key=lambda x: x.get('fns',0), reverse=True)
            tot     = sum(c.get('fns',0) for c in creances)
            tot_sol = sum(c.get('solde',0) for c in creances if c.get('solde',0)>0)
            t0_30  = [c for c in avec_ret if 0<c.get('retard',0)<30]
            t30_60 = [c for c in avec_ret if 30<=c.get('retard',0)<60]
            t60p   = [c for c in avec_ret if c.get('retard',0)>=60]
            lines  = [
                "📋 *ANALYSE CRÉANCES*", _sep(),
                f"🔴 *Total créances échues*\n   {F(tot)} FCFA",
                f"🏦 *Solde total clients*\n   {F(tot_sol)} FCFA",
                f"⚠️  Clients en retard : *{len(avec_ret)}*",
                _sep(), "📊 *RÉPARTITION PAR ANCIENNETÉ :*",
                f"  🟡 1–29 jours   : {len(t0_30)} clients  — {F(sum(c.get('fns',0) for c in t0_30))} FCFA",
                f"  🟠 30–59 jours  : {len(t30_60)} clients — {F(sum(c.get('fns',0) for c in t30_60))} FCFA",
                f"  🔴 60+ jours    : {len(t60p)} clients  — {F(sum(c.get('fns',0) for c in t60p))} FCFA",
                _sep(), "🚨 *TOP 8 CLIENTS URGENTS :*",
            ]
            for c in avec_ret[:8]:
                risk = R(c.get('risque',0)*100)
                lines.append(
                    f"• *{c.get('nom','?')[:24]}*\n"
                    f"  Créance : {F(c.get('fns',0))} FCFA\n"
                    f"  Retard  : {c.get('retard',0)} jours\n"
                    f"  Risque  : {risk}\n"
                    f"  Comm.   : {c.get('commercial','—')[:20]}")
            lines.append(f"\n🕐 _{self.get_snapshot_age()}_")
            msg = "\n".join(lines)
            for chunk in [msg[i:i+4000] for i in range(0,len(msg),4000)]:
                await update.message.reply_text(chunk, parse_mode='Markdown')

        # ── /alertes ──
        async def cmd_alertes(update: Update, ctx):
            u = await _check_user(update)
            if not u: return
            _bot_log(f"/alertes <- {u['username']} [{u['role']}]")
            if u['role'] == 'commercial':
                await update.message.reply_text("⛔ Accès non autorisé.")
                return
            alertes  = self._snap_list('alertes')
            creances = self._snap_list('creances')
            if u['role'] == 'agence':
                ag_c     = self.get_agence_coms(u.get('agence',''))
                creances = [c for c in creances if _norm(c.get('commercial','')) in ag_c]
                alertes  = [a for a in alertes  if _norm(a.get('commercial','')) in ag_c]
            crit = [a for a in alertes if a.get('niveau')=='CRITIQUE']
            alrt = [a for a in alertes if a.get('niveau')=='ALERTE']
            suiv = [a for a in alertes if a.get('niveau')=='SUIVI']
            tot  = sum(c.get('fns',0) for c in creances if c.get('fns',0)>0)
            lines = [
                "🚨 *CENTRE D'ALERTES NEXORA*", _sep(),
                f"💸 Total impayé      : *{F(tot)} FCFA*",
                f"🔴 Critiques (>30j)  : *{len(crit)}*",
                f"🟠 Plafond dépassé   : *{len(alrt)}*",
                f"🟡 En suivi          : *{len(suiv)}*",
                _sep(),
            ]
            if crit:
                lines.append("🚨 *ALERTES CRITIQUES (>30j) :*")
                for a in crit[:6]:
                    lines.append(
                        f"• *{a.get('nom','')[:24]}*\n"
                        f"  Montant : {F(a.get('fns',0))} FCFA\n"
                        f"  Retard  : {a.get('retard',0)} jours\n"
                        f"  Statut  : {a.get('msg','')}")
            if alrt:
                lines.append("\n🟠 *DÉPASSEMENT PLAFOND :*")
                for a in alrt[:4]:
                    lines.append(f"• {a.get('nom','')[:24]} — {F(a.get('fns',0))} FCFA")
            lines.append(f"\n🕐 _{self.get_snapshot_age()}_")
            await update.message.reply_text("\n".join(lines), parse_mode='Markdown')

        # ── /analyse ──
        async def cmd_analyse(update: Update, ctx):
            u = await _check_user(update)
            if not u: return
            _bot_log(f"/analyse <- {u['username']} [{u['role']}]")
            if u['role'] not in ('admin','direction'):
                await update.message.reply_text("⛔ Réservé à la Direction Générale.")
                return
            clas = self._snap_list('classement')
            if not clas:
                await update.message.reply_text("⏳ Pas de données.")
                return
            ca_tot = sum(r.get('ca',0) for r in clas) or 1
            top    = clas[:3]
            bas    = sorted(clas, key=lambda x: x.get('score',0))[:3]
            cands  = [r for r in clas if r.get('ca',0)>0]
            best_rec  = max(clas, key=lambda x: x.get('taux_rec',0)) if clas else None
            worst_rec = min(cands, key=lambda x: x.get('taux_rec',0)) if cands else None
            lines = ["📊 *ANALYSE COMPARATIVE NEXORA*", _sep(), "🏆 *LEADERS CA :*"]
            for r in top:
                lines.append(f"  🥇 *{r.get('commercial','')[:22]}*\n"
                             f"     CA: {F(r.get('ca',0))} FCFA ({r.get('ca',0)/ca_tot*100:.1f}%)")
            lines.append("\n⚠️  *NÉCESSITENT ATTENTION :*")
            for r in bas:
                if r.get('ca',0)==0: continue
                lines.append(f"  ⬇ *{r.get('commercial','')[:22]}*\n"
                             f"     CA: {F(r.get('ca',0))} FCFA | Score: {r.get('score',0)*100:.0f}/100")
            if best_rec:
                lines.append(f"\n✅ *MEILLEUR TAUX RECOUV.* : {best_rec.get('commercial','')[:22]}\n"
                             f"   {T(best_rec.get('taux_rec',0)*100)} {best_rec.get('taux_rec',0)*100:.1f}%")
            if worst_rec:
                lines.append(f"⚠️ *PLUS FAIBLE TAUX* : {worst_rec.get('commercial','')[:22]}\n"
                             f"   {T(worst_rec.get('taux_rec',0)*100)} {worst_rec.get('taux_rec',0)*100:.1f}%")
            lines.append(f"\n{_sep()}\n🕐 _{self.get_snapshot_age()}_")
            await update.message.reply_text("\n".join(lines), parse_mode='Markdown')

        # ── /inscription (conversation 3 etapes) ──
        _INSC_NOM, _INSC_POSTE, _INSC_AGENCE = range(3)
        _POSTES_BOT  = ["PDG","DG - Directeur General","DC - Directeur Commercial",
                        "Chef Comptable","Comptable","Auditeur","Chef d'agence","Commercial"]
        _AGENCES_BOT = ["Direction generale","BERTOUA","DOUALA","YAOUNDE","GAROUA"]

        async def cmd_inscription_start(update: Update, ctx):
            tg = update.effective_user
            _bot_log(f"/inscription <- {tg.first_name} ({tg.id})")
            if self.get_user_by_telegram(str(tg.id)):
                await update.message.reply_text("✅ Vous êtes déjà enregistré.\nTapez /start pour continuer.")
                return ConversationHandler.END
            await update.message.reply_text(
                f"📝 *DEMANDE D'ACCÈS NEXORA*\n{_sep()}\n"
                f"Bonjour *{tg.first_name}* !\n\n"
                f"Je vais enregistrer votre demande d'accès.\n"
                f"Un administrateur validera votre compte.\n\n"
                f"*Étape 1/3 — Votre nom complet :*\n"
                f"_(Ex: Jean-Pierre DUPONT)_",
                parse_mode='Markdown')
            return _INSC_NOM

        async def insc_nom(update: Update, ctx):
            ctx.user_data['insc_nom'] = update.message.text.strip()
            kbd = [[InlineKeyboardButton(p, callback_data=f"poste:{p}")] for p in _POSTES_BOT]
            await update.message.reply_text(
                f"✅ Nom : *{ctx.user_data['insc_nom']}*\n\n*Étape 2/3 — Votre poste :*",
                reply_markup=InlineKeyboardMarkup(kbd), parse_mode='Markdown')
            return _INSC_POSTE

        async def insc_poste(update: Update, ctx):
            await update.callback_query.answer()
            ctx.user_data['insc_poste'] = update.callback_query.data.replace('poste:','')
            kbd = [[InlineKeyboardButton(a, callback_data=f"agence:{a}")] for a in _AGENCES_BOT]
            await update.callback_query.message.reply_text(
                f"✅ Poste : *{ctx.user_data['insc_poste']}*\n\n*Étape 3/3 — Votre agence :*",
                reply_markup=InlineKeyboardMarkup(kbd), parse_mode='Markdown')
            return _INSC_AGENCE

        async def insc_agence(update: Update, ctx):
            await update.callback_query.answer()
            ctx.user_data['insc_agence'] = update.callback_query.data.replace('agence:','')
            tg  = update.effective_user
            nom = ctx.user_data.get('insc_nom','?')
            pst = ctx.user_data.get('insc_poste','?')
            agn = ctx.user_data['insc_agence']
            try:
                self.save_inscription(str(tg.id), tg.first_name, nom, pst, agn)
            except Exception as e:
                _bot_log(f"Inscription DB err: {e}")
            await update.callback_query.message.reply_text(
                f"✅ *Demande enregistrée !*\n{_sep()}\n"
                f"👤 Nom    : *{nom}*\n"
                f"📋 Poste  : *{pst}*\n"
                f"📍 Agence : *{agn}*\n"
                f"🤖 ID Telegram : `{tg.id}`\n{_sep()}\n"
                f"⏳ Votre demande a été envoyée à l'administrateur.\n"
                f"Vous serez notifié dès validation.",
                parse_mode='Markdown')
            cfg       = self.get_bot_config()
            admin_ids = [x.strip() for x in cfg.get('bot_admin_ids','').split(',') if x.strip()]
            for aid in admin_ids:
                try:
                    await self._ptb.bot.send_message(
                        chat_id=int(aid),
                        text=(f"🔔 *NOUVELLE DEMANDE D'ACCÈS NEXORA*\n{_sep()}\n"
                              f"👤 Nom       : *{nom}*\n"
                              f"📋 Poste     : *{pst}*\n"
                              f"📍 Agence    : *{agn}*\n"
                              f"🤖 Telegram  : *{tg.first_name}* (`{tg.id}`)\n{_sep()}\n"
                              f"➡️ Allez dans Paramètres → Utilisateurs pour créer le compte."),
                        parse_mode='Markdown')
                    _bot_log(f"Demande inscription notifiee a admin {aid}")
                except Exception as e:
                    _bot_log(f"Notif admin {aid} echec: {e}")
            return ConversationHandler.END

        async def insc_cancel(update: Update, ctx):
            await update.message.reply_text("❌ Inscription annulée.")
            return ConversationHandler.END

        # ── /aide ──
        async def cmd_aide(update: Update, ctx):
            u = self.get_user_by_telegram(str(update.effective_user.id))
            _bot_log(f"/aide <- {update.effective_user.first_name}")
            if u:
                await update.message.reply_text(
                    f"📋 *AIDE NEXORA BOT*\n{_sep()}\n"
                    f"*Vos commandes ({u['role'].upper()}) :*\n"
                    f"{self._menu_pour_role(u['role'])}\n{_sep()}\n"
                    f"_Données mises à jour à chaque actualisation de NEXORA_\n"
                    f"_NEXORA ERP v2.0_",
                    parse_mode='Markdown')
            else:
                await update.message.reply_text(
                    f"📋 *AIDE NEXORA BOT*\n{_sep()}\n"
                    f"• /inscription — Demander un accès\n"
                    f"• /start       — Message de bienvenue\n"
                    f"• /aide        — Cette aide\n{_sep()}\n"
                    f"_NEXORA ERP v2.0_",
                    parse_mode='Markdown')

        async def msg_inconnu(update: Update, ctx):
            await update.message.reply_text(
                "❓ Commande non reconnue.\n"
                "Tapez /aide pour voir vos commandes disponibles.\n"
                "Tapez /start pour le menu principal.")

        # ── Construction et lancement ──
        try:
            ptb = Application.builder().token(self._token).build()
            self._ptb = ptb
            insc_handler = ConversationHandler(
                entry_points=[CommandHandler('inscription', cmd_inscription_start)],
                states={
                    _INSC_NOM:    [MessageHandler(filters.TEXT & ~filters.COMMAND, insc_nom)],
                    _INSC_POSTE:  [CallbackQueryHandler(insc_poste, pattern='^poste:')],
                    _INSC_AGENCE: [CallbackQueryHandler(insc_agence, pattern='^agence:')],
                },
                fallbacks=[CommandHandler('annuler', insc_cancel)],
            )
            ptb.add_handler(insc_handler)
            for cmd, fn in [
                ('start', cmd_start), ('situation', cmd_situation),
                ('classement', cmd_classement), ('cockpit', cmd_cockpit),
                ('creances', cmd_creances), ('alertes', cmd_alertes),
                ('analyse', cmd_analyse), ('aide', cmd_aide),
            ]:
                ptb.add_handler(CommandHandler(cmd, fn))
            ptb.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, msg_inconnu))

            self._loop.run_until_complete(ptb.initialize())
            self._loop.run_until_complete(ptb.start())
            self._loop.run_until_complete(ptb.updater.start_polling(drop_pending_updates=True))
            _bot_log("Bot NEXORA EN LIGNE")
            self._loop.run_forever()
        except Exception as e:
            _bot_log(f"ERREUR fatale : {e}")
            self.running = False
        finally:
            self.running = False
            _bot_log("Bot arrete")


# ── Instance globale partagee par le process Flask ───────────────────────────
_bot_manager = None


def get_bot_manager():
    global _bot_manager
    if _bot_manager is None:
        from core.database import (get_config, db_one, db_all, db_exec)
        import json as _j

        def _get_snapshot(key):
            row = db_one("SELECT value FROM data_snapshot WHERE key=?", (key,))
            if not row: return None
            try: return _j.loads(row['value'])
            except Exception: return None

        def _get_snapshot_age():
            row = db_one("SELECT updated_at FROM data_snapshot WHERE key='period'")
            return row['updated_at'] if row else ''

        def _get_user_by_telegram(tg_id):
            row = db_one(
                "SELECT username,role,commercial_name,agence,poste,categorie,telegram_id "
                "FROM utilisateurs WHERE telegram_id=? AND actif=1", (tg_id,))
            if not row: return None
            return {'username': row['username'], 'role': row['role'] or 'commercial',
                    'commercial_name': row['commercial_name'] or '',
                    'com': row['commercial_name'] or '',
                    'agence': row['agence'] or '', 'poste': row['poste'] or '',
                    'categorie': row['categorie'] or '', 'telegram_id': row['telegram_id'] or ''}

        def _get_agence_coms(agence):
            rows = db_all(
                "SELECT commercial_name FROM utilisateurs WHERE agence=? AND role='commercial' AND actif=1",
                (agence,))
            return {_norm(r['commercial_name']) for r in rows if r['commercial_name']}

        def _save_inscription(tg_id, tg_nom, nom, poste, agence):
            db_exec(
                "INSERT INTO bot_inscriptions(telegram_id,telegram_nom,nom,poste,agence,statut)"
                " VALUES(?,?,?,?,?,'EN_ATTENTE')",
                (tg_id, tg_nom, nom, poste, agence))

        def _get_bot_config():
            rows = db_all("SELECT key, value FROM bot_config")
            return {r['key']: r['value'] for r in rows}

        _bot_manager = BotManager(
            db_get_config=get_config,
            db_get_snapshot=_get_snapshot,
            db_get_snapshot_age=_get_snapshot_age,
            db_get_user_by_telegram=_get_user_by_telegram,
            db_get_agence_coms=_get_agence_coms,
            db_save_inscription=_save_inscription,
            db_get_bot_config=_get_bot_config,
        )
    return _bot_manager
