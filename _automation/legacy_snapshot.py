#!/usr/bin/env python3
"""STEP 3 — legacy snapshots csv-daily-snapshots: parse CSV, update history, 2 HTML standalone."""
import csv, json, sys, html
from pathlib import Path
from datetime import datetime

DATE = sys.argv[1]
WORK = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(".")
SNAP_REPO = Path("/tmp/csv-daily-snapshots")

MESI = ["", "gennaio", "febbraio", "marzo", "aprile", "maggio", "giugno",
        "luglio", "agosto", "settembre", "ottobre", "novembre", "dicembre"]

def it_date(d):
    y, m, dd = d.split("-")
    return f"{int(dd)} {MESI[int(m)]} {y}"

def eur(v):
    if v is None:
        return "—"
    s = f"{v:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return f"{s} €"

def read_csv(path):
    rows = []
    with open(path, encoding="utf-8") as f:
        for r in csv.DictReader(f, delimiter=";"):
            try:
                spesa = float(r["Spesa"]) if r["Spesa"] else 0.0
            except ValueError:
                spesa = 0.0
            try:
                lead = int(r["Lead"]) if r["Lead"] else 0
            except ValueError:
                lead = 0
            rows.append({"cliente": r["Cliente"].strip(), "campagna": r["Nome Campagna"].strip(),
                         "spesa": spesa, "lead": lead})
    return rows

def aggregate(rows, key):
    agg = {}
    for r in rows:
        k = r[key]
        a = agg.setdefault(k, {"spend": 0.0, "leads": 0, "adsets": 0})
        a["spend"] += r["spesa"]
        a["leads"] += r["lead"]
        a["adsets"] += 1
    out = []
    for k, a in agg.items():
        cpl = round(a["spend"] / a["leads"], 2) if a["leads"] else None
        out.append({"key": k, "spend": round(a["spend"], 2), "leads": a["leads"],
                    "cpl": cpl, "adsets": a["adsets"]})
    out.sort(key=lambda x: -x["spend"])
    return out

def hist_lookup(history, section, key_field, key, date):
    """Returns (days_with_data_in_last3, media3_cpl)."""
    prev = sorted([d for d in history if d < date], reverse=True)[:3]
    days, cpls = 0, []
    for d in prev:
        for it in history.get(d, {}).get(section, []):
            names = {it.get("campagna"), it.get("cliente"), it.get("id")}
            if key in names:
                days += 1
                if it.get("cpl") is not None:
                    cpls.append(it["cpl"])
                break
    media3 = round(sum(cpls) / len(cpls), 2) if cpls else None
    return days, media3

def semaphore(it, days, media3):
    spend, lead, cpl = it["spend"], it["leads"], it["cpl"]
    if spend < 0.01:
        return "nero", "INFO", "Nessuna spesa registrata oggi."
    if days < 3:
        if lead == 0:
            return "giallo", "DA OSSERVARE", "Nessun lead oggi; serie storica insufficiente."
        return "giallo", "DA OSSERVARE", f"Avvio campagna · {days}/3 gg storico."
    if lead == 0:
        return "rosso", "ALERT", f"Spesa €{spend:.2f} senza lead. Pausa o refresh creativo + audience."
    if media3 is None:
        return "giallo", "DA OSSERVARE", f"Primo costo per contatto utile (€{cpl:.2f}); media 3gg non ancora disponibile."
    if cpl > media3 * 1.5:
        return "rosso", "ALERT", f"CPL €{cpl:.2f} sopra +50% vs media 3gg €{media3:.2f}. Refresh creativo o pausa."
    return "verde", "OK", f"CPL €{cpl:.2f} in linea o sotto media 3gg (€{media3:.2f}). Valutare scaling se il volume è basso."

CSS = """  * { box-sizing: border-box; margin: 0; padding: 0; }
  body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif;
    background: #1c1c1e; color: #f2f2f7; padding: 24px 16px; line-height: 1.45; }
  .wrap { max-width: 1400px; margin: 0 auto; }
  header { margin-bottom: 24px; }
  h1 { font-size: 28px; font-weight: 700; margin-bottom: 4px; }
  .subtitle { color: #8e8e93; font-size: 15px; }
  .totals { background: #2c2c2e; border-radius: 14px; padding: 18px 20px; margin-bottom: 24px;
    display: flex; gap: 28px; flex-wrap: wrap; }
  .totals div { font-size: 14px; color: #8e8e93; }
  .totals strong { display: block; color: #f2f2f7; font-size: 22px; font-weight: 600; margin-top: 2px; }
  .grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(360px, 1fr)); gap: 16px; }
  .card { background: #2c2c2e; border-radius: 14px; padding: 18px; border-left: 4px solid transparent;
    display: flex; flex-direction: column; gap: 12px; }
  .card.rosso  { border-left-color: #ff453a; }
  .card.giallo { border-left-color: #ffd60a; }
  .card.verde  { border-left-color: #30d158; }
  .card.nero   { border-left-color: #8e8e93; }
  .card-head { display: flex; justify-content: space-between; align-items: flex-start; gap: 8px; }
  .name { font-size: 16px; font-weight: 600; word-break: break-word; }
  .meta { color: #8e8e93; font-size: 12px; margin-top: 4px; }
  .badge { padding: 4px 10px; border-radius: 999px; font-size: 11px; font-weight: 700;
    text-transform: uppercase; letter-spacing: 0.5px; white-space: nowrap; }
  .badge.rosso  { background: #ff453a; color: #1c1c1e; }
  .badge.giallo { background: #ffd60a; color: #1c1c1e; }
  .badge.verde  { background: #30d158; color: #1c1c1e; }
  .badge.nero   { background: #8e8e93; color: #1c1c1e; }
  .kpi { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; }
  .kpi .lab { color: #8e8e93; font-size: 11px; text-transform: uppercase; letter-spacing: 0.4px; }
  .kpi .val { font-size: 15px; font-weight: 600; margin-top: 2px; }
  .action { color: #aeaeb2; font-size: 13px; line-height: 1.4; padding-top: 8px;
    border-top: 1px solid #3a3a3c; }
  footer { color: #636366; font-size: 12px; margin-top: 24px; text-align: center; }"""

def render(title, items, history, section, key_field, date):
    cards, counters = [], {"rosso": 0, "giallo": 0, "verde": 0, "nero": 0}
    for it in items:
        days, media3 = hist_lookup(history, section, key_field, it["key"], date)
        color, badge, action = semaphore(it, days, media3)
        counters[color] += 1
        cards.append(f"""<div class="card {color}">
      <div class="card-head">
        <div>
          <div class="name">{html.escape(it['key'])}</div>
          <div class="meta">{it['adsets']} ad-set · {min(days,3)}/3 gg storico</div>
        </div>
        <span class="badge {color}">{badge}</span>
      </div>
      <div class="kpi">
        <div><div class="lab">Spend</div><div class="val">{eur(it['spend'])}</div></div>
        <div><div class="lab">Lead</div><div class="val">{it['leads']}</div></div>
        <div><div class="lab">CPL oggi</div><div class="val">{eur(it['cpl'])}</div></div>
        <div><div class="lab">Media 3gg</div><div class="val">{eur(media3)}</div></div>
      </div>
      <div class="action">{html.escape(action)}</div>
    </div>""")
    tot_spend = sum(i["spend"] for i in items)
    tot_lead = sum(i["leads"] for i in items)
    cpl_med = tot_spend / tot_lead if tot_lead else None
    now = datetime.now().strftime("%d/%m/%Y %H:%M")
    return f"""<!DOCTYPE html>
<html lang="it">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{title} — {it_date(date)}</title>
<style>
{CSS}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>{title}</h1>
    <div class="subtitle">Snapshot del {it_date(date)} · fonte CSV Apps Script</div>
  </header>
  <div class="totals">
    <div>Account attivi<strong>{len(items)}</strong></div>
    <div>Spesa totale<strong>{eur(round(tot_spend,2))}</strong></div>
    <div>Lead totali<strong>{tot_lead}</strong></div>
    <div>CPL medio<strong>{eur(round(cpl_med,2) if cpl_med else None)}</strong></div>
    <div>Rossi<strong>{counters['rosso']}</strong></div>
    <div>Gialli<strong>{counters['giallo']}</strong></div>
    <div>Verdi<strong>{counters['verde']}</strong></div>
    <div>Info<strong>{counters['nero']}</strong></div>
  </div>
  <div class="grid">{''.join(cards)}</div>
  <footer>Generato {now} — pipeline Cowork CSV Apps Script</footer>
</div>
</body>
</html>""", counters, tot_spend, tot_lead

def main():
    cea_rows = read_csv(WORK / f"cea_{DATE}.csv")
    mt_rows = read_csv(WORK / f"medtech_{DATE}.csv")
    cea = aggregate(cea_rows, "cliente")
    mt = aggregate(mt_rows, "campagna")

    data_path = SNAP_REPO / "data.json"
    data = json.load(open(data_path)) if data_path.exists() else {"history": {}}
    history = data.setdefault("history", {})

    # semafori calcolati PRIMA di inserire il giorno corrente nello storico
    cea_html, cea_cnt, cea_spend, cea_lead = render(
        "CEA — Centro Estetico Automatico", cea, history, "cea", "cliente", DATE)
    mt_html, mt_cnt, mt_spend, mt_lead = render(
        "MED & TECH — Open Day Lead-Gen", mt, history, "medtech", "campagna", DATE)

    history[DATE] = {
        "cea": [{"cliente": i["key"], "spend": i["spend"], "leads": i["leads"], "cpl": i["cpl"]} for i in cea],
        "medtech": [{"id": i["key"], "campagna": i["key"], "spend": i["spend"], "leads": i["leads"], "cpl": i["cpl"]} for i in mt],
    }
    # retention 90 giorni
    for d in sorted(history)[:-90]:
        del history[d]

    (WORK / f"cea-daily-{DATE}.html").write_text(cea_html, encoding="utf-8")
    (WORK / f"medtech-daily-{DATE}.html").write_text(mt_html, encoding="utf-8")
    (WORK / "data.json").write_text(json.dumps(data, ensure_ascii=False, indent=1), encoding="utf-8")

    summary = {
        "cea": {"n": len(cea), "spend": round(cea_spend, 2), "leads": cea_lead, **cea_cnt},
        "medtech": {"n": len(mt), "spend": round(mt_spend, 2), "leads": mt_lead, **mt_cnt},
    }
    print(json.dumps(summary, ensure_ascii=False))

if __name__ == "__main__":
    main()
