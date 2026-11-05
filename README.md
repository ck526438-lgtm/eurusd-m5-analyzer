# 📈 EURUSD M5 Analyzer

Système d'analyse de l'**EURUSD en M5** qui lit les **chandeliers japonais**, vérifie le contexte
(tendance H1, zones de support/résistance, momentum, sessions) et t'envoie une **notification
Telegram avec le graphique** quand une bonne opportunité apparaît.

> ⚠️ Outil d'aide à la décision, pas un robot qui trade à ta place. Aucune stratégie ne gagne à
> tous les coups : teste d'abord en **compte démo**, et ne risque jamais plus de 1 % par trade.

---

## Comment il choisit une opportunité

À chaque clôture de bougie M5, l'analyse se fait en 3 étapes :

**1. Détection des figures de chandeliers**

| Achat 🟢 | Vente 🔴 |
|---|---|
| Avalement haussier | Avalement baissier |
| Pin bar / marteau | Pin bar / étoile filante |
| Étoile du matin | Étoile du soir |
| Trois soldats blancs | Trois corbeaux noirs |
| Pince basse (tweezer bottom) | Pince haute (tweezer top) |
| Cassure d'inside bar haussière | Cassure d'inside bar baissière |

Les micro-bougies (< 0,6 ATR) sont ignorées : une figure ne compte que si elle a du poids.

**2. Score de confluence sur 10**

| Critère | Points |
|---|---|
| Force de la figure (1 à 3, +1 si plusieurs figures concordent) | 1 – 3 |
| Dans le sens de la tendance **H1** (EMA 20/50) | +2 (−2 si contre) |
| EMA 20/50 M5 alignées · prix du bon côté de l'EMA 200 | +1 · +0,5 |
| Rejet d'une **zone S/R** (pivots fusionnés ; ≥2 touches = forte) ou rebond sur les EMA | +1 à +2 |
| RSI qui confirme (et pas en excès) | +1 (−1 si excès) |
| ADX ≥ 18 (marché directionnel) | +1 (−1 sinon) |
| Session Londres / New York | +0,5 |

Alerte envoyée si **score ≥ 6** (modifiable). Qualité : **A+** ≥ 8 · **A** ≥ 7 · **B** ≥ 6.

**3. Gestion du risque automatique**

- **Stop** derrière la mèche de la figure + 0,25 ATR (entre 4 et 18 pips, sinon le setup est rejeté)
- **TP1** = 1,5 R · **TP2** = 2,5 R, ramené avant la prochaine zone opposée
- Setup rejeté si une zone opposée bloque le prix à moins de 1,2 R
- Hors sessions (07 h – 11 h et 12 h – 17 h UTC = heure d'Abidjan) : aucune alerte
- Pas deux alertes dans le même sens en moins de 30 min

Tout est calculé **sans regarder le futur** (vérifié par les tests) : seules les bougies
clôturées sont utilisées, et la tendance H1 n'est prise qu'à la clôture de l'heure.

### Exemple d'alerte

```
🔴 VENTE EURUSD — M5 — qualité A+ (9.0/10)
🕐 Bougie clôturée 21/06 14:40 UTC
📐 Avalement baissier

Entrée : 1.06567
Stop   : 1.06645  (7.8 pips)
TP1    : 1.06450  (1:1.5)
TP2    : 1.06372  (1:2.5)

Pourquoi :
• Figure : Avalement baissier (force 2/3)
• Dans le sens de la tendance H1
• EMA 20/50 M5 alignées
• Rejet de la zone de résistance 1.06613
• RSI redescend (34)
• Marché directionnel (ADX 30)
```
+ l'image du graphique (bougies, EMA, zones, entrée/SL/TP).

---

## Installation

```bash
git clone https://github.com/ck526438-lgtm/eurusd-m5-analyzer.git
cd eurusd-m5-analyzer
pip install -r requirements.txt
```

### Source des données

| Source | Où | Qualité |
|---|---|---|
| **MetaTrader 5** (recommandé) | Windows, MT5 ouvert et connecté | Prix réels de ton courtier, temps réel |
| Yahoo Finance | Partout (PC, Termux, serveur) | Gratuit, léger retard possible |
| CSV | Pour le backtest | Ton propre historique |

Pour MT5 : `pip install MetaTrader5`, puis dans `config.yaml` mets le nom exact du symbole
(`EURUSD`, `EURUSDm`…) et `broker_utc_offset` (décalage de l'heure du serveur, souvent 2 ou 3).
En mode `auto`, MT5 est essayé d'abord, puis Yahoo.

### Notifications Telegram (5 min)

1. Sur Telegram, écris à **@BotFather** → `/newbot` → copie le **token**.
2. Envoie un message à ton nouveau bot, puis ouvre
   `https://api.telegram.org/bot<TOKEN>/getUpdates` et copie le `"chat":{"id": ...}`.
3. Copie `.env.example` en `.env` et remplis `TELEGRAM_TOKEN` et `TELEGRAM_CHAT_ID`.
4. Vérifie : `python main.py telegram-test`

(Optionnel : `DISCORD_WEBHOOK` dans `.env`, et `pip install plyer` pour les notifications bureau.)

---

## Utilisation

```bash
python main.py live            # surveillance continue, analyse à chaque clôture M5
python main.py scan            # une seule analyse de la dernière bougie
python main.py backtest        # backtest sur les données disponibles
python main.py backtest --csv historique.csv
python main.py live --source yfinance -v
```

Sous Windows, double-clique sur **`start_windows.bat`** (crée l'environnement et lance `live`).

Toutes les alertes sont enregistrées dans `signals/journal.csv` avec leur graphique.

### Le backtest

Simulation réaliste : spread de 0,8 pip, 50 % fermé à TP1 puis stop au point d'entrée,
reste à TP2, sortie forcée après 4 h ; si SL et TP sont touchés dans la même bougie, on
compte le SL (hypothèse prudente). Résultat : taux de réussite, espérance en R, profit factor,
drawdown max, et détail **par figure** — pour désactiver celles qui ne marchent pas sur ton
courtier.

**Lance le backtest sur tes vraies données MT5 avant de trader** (augmente `bars` à 50000
dans `config.yaml` pour plusieurs mois d'historique).

---

## Réglages utiles (`config.yaml`)

- Trop d'alertes ? → `min_score: 7` ou `8`
- Pas assez ? → `min_score: 5.5`, ou `use_sessions: false`
- Ton courtier a un gros spread ? → monte `min_sl_pips`

## Structure

```
analyzer/
  data.py        sources MT5 / Yahoo / CSV (bougies clôturées uniquement)
  indicators.py  EMA, RSI, ATR, ADX, tendance H1
  patterns.py    figures de chandeliers
  structure.py   pivots et zones support / résistance
  strategy.py    score de confluence, SL / TP
  chart.py       graphique de l'alerte
  notifier.py    Telegram, Discord, bureau, journal
  backtest.py    simulation des trades
main.py          ligne de commande
tests/           tests (dont un test anti « regard vers le futur »)
```

Tests : `python -m pytest -q`
