# 🚗 Bilia Scraper

Skrapar bildata från [bilia.se](https://www.bilia.se) och exporterar resultatet som CSV och HTML.

## Vad scriptet hämtar

| Fält | Exempel |
|------|---------|
| Bilnamn | Volvo XC40 T3 |
| Pris | 225.000 kr |
| Färg / Kaross | Vit / SUV |
| Bränsle | Bensin / Diesel / El |
| Drivhjul | Framhjulsdrift |
| Växellåda | Manuell / Automat |
| Miltal | 11375 mil |
| Modellår | 2019 |
| Motorvolym | 1.5 liter |
| kW / Hästkrafter | 115 kW / 156 hk |
| Cylindrar | 3 cylindrar |
| Acceleration | 9.4 sekunder |
| Topphastighet | 200 km/h |
| CO2 | 144 g/km |
| Bränsleförbrukning | 5.4 / 7.6 l/100km |
| Förvärmare | Ja |
| Årlig skatt | 1086 kr/år |

## Installation

```bash
pip install playwright prettytable
python -m playwright install chromium
```

## Användning

1. Lägg till URL:er i `bilar.json`:
```json
[
  "https://www.bilia.se/bilar/sok-bil/volvo/xc40/ksa61u/",
  "https://www.bilia.se/bilar/sok-bil/volvo/xc40/sms94w/"
]
```

2. Kör scriptet:
```bash
python bilar_scraper.py
```

3. Resultat sparas i:
   - **`bilanalys.csv`** – öppna i Excel
   - **`bilanalys.html`** – öppna i webbläsaren

## Filer

| Fil | Beskrivning |
|-----|-------------|
| `bilar_scraper.py` | Huvudscript |
| `bilar.json` | Lista med bil-URL:er |
| `bilanalys.csv` | Resultat (Excel) |
| `bilanalys.html` | Resultat (webbläsare) |

## Teknik

- **Playwright** – hanterar JavaScript-rendering
- **PrettyTable** – terminaltabell
- Python 3.10+
