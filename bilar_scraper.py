"""
bilar_scraper.py – Bilia.se scraper
Läser bilar.json → skrapar data → sparar bilanalys.csv + bilanalys.html
"""

import json, csv, asyncio, re, sys
from pathlib import Path
from prettytable import PrettyTable
from playwright.async_api import async_playwright

JSON_FIL   = "bilar.json"
CSV_FIL    = "bilanalys.csv"
HTML_FIL   = "bilanalys.html"
PAUS_SEK   = 2
TIMEOUT_MS = 40_000

# Direkt mapping: spec-nyckel (lowercase) → fältnamn i resultatet
SPEC_MAP = {
    "färg"                         : "Färg",
    "kaross"                       : "Kaross",
    "bränsle"                      : "Bränsle",
    "drivhjul"                     : "Drivhjul",
    "modellår"                     : "Modellår",
    "årlig skatt"                  : "Årlig skatt",
    "förvärmare"                   : "Förvärmare",
    "antal växlar"                 : "Antal växlar",
    "motorvolym i liter"           : "Motorvolym",
    "cylindrar"                    : "Cylindrar",
    "topphastighet"                : "Topphastighet",
    "acceleration, 0-100 km/h"     : "Acceleration",
    "co₂ blandad (nedc)"           : "CO2",
    "bränsleförbrukning landsväg"  : "Bränsleförbrukning land",
    "bränsleförbrukning stad"      : "Bränsleförbrukning stad",
}

FÄLT = [
    "URL", "Bilnamn", "Pris", "Färg", "Kaross", "Bränsle", "Drivhjul",
    "Växellåda", "Antal växlar", "Miltal", "Modellår",
    "Motorvolym", "kW", "Hästkrafter", "Cylindrar",
    "Acceleration", "Topphastighet", "CO2",
    "Bränsleförbrukning land", "Bränsleförbrukning stad",
    "Förvärmare", "Årlig skatt",
]


def rensa(t):
    return re.sub(r"\s+", " ", t or "").strip() or "–"


async def hämta_bildata(page, url: str) -> dict:
    rad = {f: "–" for f in FÄLT}
    rad["URL"] = url

    try:
        # Ladda sidan + scrolla för att trigga Vue lazy-rendering
        await page.goto(url, wait_until="domcontentloaded", timeout=TIMEOUT_MS)
        for _ in range(8):
            await page.evaluate("window.scrollBy(0, 400)")
            await page.wait_for_timeout(300)
        await page.evaluate("window.scrollTo(0, 0)")
        try:
            await page.wait_for_selector("li.summary__item", timeout=12_000)
        except Exception:
            pass

        # Bilnamn
        h1 = page.locator("h1.g-text-headline-small").first
        if await h1.count():
            rad["Bilnamn"] = rensa(await h1.text_content())

        # Pris
        pris = page.locator("span.price.regular.current-price").first
        if await pris.count():
            val = rensa(await pris.locator("span.value").first.text_content())
            cur = rensa(await pris.locator("span.currency").first.text_content())
            rad["Pris"] = f"{val} {cur}".strip()

        # Summary-lista → Bränsle / Växellåda / Miltal / Modellår
        # Kolla växellåda FÖRST (annars matchar "el" inne i "Manuell")
        labels = page.locator("li.summary__item span.g-text-label")
        for i in range(await labels.count()):
            v, vl = (t := rensa(await labels.nth(i).text_content())), t.lower()
            if any(x in vl for x in ["automat", "manuell", "dsg", "cvt"]):
                rad["Växellåda"] = v
            elif "mil" in vl:
                rad["Miltal"] = v
            elif re.fullmatch(r'\d{4}', v):
                rad["Modellår"] = v
            elif re.search(r'\bbensin\b|\bdiesel\b|\bhybrid\b|\bel\b|\bgas\b', vl):
                rad["Bränsle"] = v

        # Klicka Motor och miljö-fliken för att ladda motordata
        motor_btn = page.get_by_text("Motor och miljö")
        if await motor_btn.count():
            await motor_btn.first.scroll_into_view_if_needed()
            await motor_btn.first.click()
            await page.wait_for_timeout(1500)

        # Läs ALLA spec-rutor i ett pass (inkl. motordata)
        items = page.locator("div.feature-item")
        for i in range(await items.count()):
            item = items.nth(i)
            btn = item.locator("button.toggle-tip__label").first
            etikett = rensa(await btn.text_content()) if await btn.count() \
                      else rensa(await item.locator("dt").first.text_content()
                                 if await item.locator("dt").count() else "")
            dd = item.locator("dd.feature-item__value span").first
            värde = rensa(await dd.text_content()) if await dd.count() else ""

            if not etikett or not värde:
                continue

            ek = etikett.lower()

            # Direkt mapping
            if ek in SPEC_MAP:
                rad[SPEC_MAP[ek]] = värde

            # kW + hk från Motornamn: "1.5 T3 B3154T (115 kW)"
            if ek == "motornamn":
                m = re.search(r'(\d+)\s*kW', värde, re.I)
                if m:
                    rad["kW"] = f"{m.group(1)} kW"
                    rad["Hästkrafter"] = f"{round(int(m.group(1)) * 1.35962)} hk"

            # Elbil: kW från Motornamn "69 kWh (170 kW)" eller batterikapacitet
            if ek == "motornamn" and rad["kW"] == "–":
                m = re.search(r'\((\d+)\s*kW\)', värde)
                if m:
                    rad["kW"] = f"{m.group(1)} kW"
                    rad["Hästkrafter"] = f"{round(int(m.group(1)) * 1.35962)} hk"

    except Exception as e:
        print(f"  ⚠️  {url}: {e}")

    return rad


def generera_html(alla: list[dict]) -> str:
    kolumner = [f for f in FÄLT if f != "URL"]
    th = "".join(f"<th>{k}</th>" for k in kolumner)
    rader = ""
    for b in alla:
        celler = "".join(
            f'<td><a href="{b["URL"]}" target="_blank">{b[k]}</a></td>'
            if k == "Bilnamn" else f"<td>{b[k]}</td>"
            for k in kolumner
        )
        rader += f"<tr>{celler}</tr>\n"

    return f"""<!DOCTYPE html>
<html lang="sv">
<head>
  <meta charset="UTF-8">
  <title>Bilia – Bilanalys</title>
  <style>
    *{{box-sizing:border-box;margin:0;padding:0}}
    body{{font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;background:#0f172a;color:#e2e8f0;padding:32px 16px}}
    h1{{font-size:1.6rem;font-weight:700;margin-bottom:6px;color:#f8fafc}}
    p{{font-size:.85rem;color:#94a3b8;margin-bottom:20px}}
    .wrap{{overflow-x:auto;border-radius:12px;box-shadow:0 4px 32px rgba(0,0,0,.5)}}
    table{{border-collapse:collapse;width:100%;min-width:1400px;background:#1e293b}}
    thead th{{background:#0ea5e9;color:#fff;font-size:.75rem;font-weight:600;text-transform:uppercase;letter-spacing:.05em;padding:11px 13px;text-align:left;white-space:nowrap;position:sticky;top:0}}
    tbody tr{{border-bottom:1px solid #334155}}
    tbody tr:hover{{background:#263348}}
    tbody tr:nth-child(even){{background:#243044}}
    td{{padding:9px 13px;font-size:.82rem;white-space:nowrap}}
    td:first-child{{font-weight:600;color:#7dd3fc}}
    a{{color:#7dd3fc;text-decoration:none}}
    a:hover{{text-decoration:underline}}
    .dash{{color:#475569}}
  </style>
  <script>
    document.addEventListener("DOMContentLoaded",()=>
      document.querySelectorAll("td").forEach(td=>
        td.textContent.trim()==="–"&&td.classList.add("dash")));
  </script>
</head>
<body>
  <h1>🚗 Bilia – Bilanalys</h1>
  <p>{len(alla)} bilar · Klicka på bilnamnet för att öppna annonsen</p>
  <div class="wrap">
    <table>
      <thead><tr>{th}</tr></thead>
      <tbody>{rader}</tbody>
    </table>
  </div>
</body>
</html>"""


async def main():
    print("=" * 68)
    print("  🚗  BILIA BILANALYS")
    print("=" * 68)

    urls = json.loads(Path(JSON_FIL).read_text(encoding="utf-8"))
    if isinstance(urls, dict):
        urls = urls.get("urls", [])
    print(f"\n📄  {len(urls)} bilar i '{JSON_FIL}'\n")

    alla: list[dict] = []

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        page = await (await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/122.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 900},
        )).new_page()

        for i, url in enumerate(urls, 1):
            print(f"  [{i}/{len(urls)}] {url}")
            b = await hämta_bildata(page, url)
            alla.append(b)
            print(f"         ✓ {b['Bilnamn']} | {b['Pris']} | {b['Bränsle']} | "
                  f"{b['Växellåda']} | {b['Miltal']} | {b['Modellår']} | {b['Hästkrafter']}")
            if i < len(urls):
                await asyncio.sleep(PAUS_SEK)

        await browser.close()

    if not alla:
        return

    # ── Tabell 1: Grundinfo ──────────────────────────────────────────────────
    t1 = PrettyTable(["#", "Bilnamn", "Pris", "Färg", "Kaross", "Bränsle",
                      "Drivhjul", "Växellåda", "Miltal", "Modellår", "Årlig skatt"])
    t1.align = "l"; t1.max_width = 13
    for i, b in enumerate(alla, 1):
        t1.add_row([i, b["Bilnamn"], b["Pris"], b["Färg"], b["Kaross"], b["Bränsle"],
                    b["Drivhjul"], b["Växellåda"], b["Miltal"], b["Modellår"], b["Årlig skatt"]])
    print("\n" + "=" * 68 + "\n  📊  GRUNDINFO\n" + "=" * 68)
    print(t1)

    # ── Tabell 2: Motorinfo ──────────────────────────────────────────────────
    t2 = PrettyTable(["#", "Bilnamn", "Motorvolym", "kW", "Hästkrafter", "Cylindrar",
                      "Antal växlar", "Acceleration", "Topphastighet",
                      "CO2", "Förbrukn.land", "Förbrukn.stad", "Förvärmare"])
    t2.align = "l"; t2.max_width = 13
    for i, b in enumerate(alla, 1):
        t2.add_row([i, b["Bilnamn"], b["Motorvolym"], b["kW"], b["Hästkrafter"],
                    b["Cylindrar"], b["Antal växlar"], b["Acceleration"],
                    b["Topphastighet"], b["CO2"],
                    b["Bränsleförbrukning land"], b["Bränsleförbrukning stad"],
                    b["Förvärmare"]])
    print("\n" + "=" * 68 + "\n  🔧  MOTORINFO\n" + "=" * 68)
    print(t2)

    # ── CSV ──────────────────────────────────────────────────────────────────
    with open(CSV_FIL, "w", newline="", encoding="utf-8-sig") as f:
        w = csv.DictWriter(f, fieldnames=FÄLT)
        w.writeheader(); w.writerows(alla)

    # ── HTML ─────────────────────────────────────────────────────────────────
    Path(HTML_FIL).write_text(generera_html(alla), encoding="utf-8")

    print(f"\n💾  {CSV_FIL}  |  🌐  {HTML_FIL}\n")


if __name__ == "__main__":
    asyncio.run(main())
