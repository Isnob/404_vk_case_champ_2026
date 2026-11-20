"""Read-only preliminary checks. Run from repository root: python3 audit/precheck.py."""
import json
from pathlib import Path
import xml.etree.ElementTree as E
import zipfile
from datetime import datetime, timedelta
import pandas as pd

p = Path(__file__).resolve().parents[1] / 'data'
ns = {'m': 'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
checks = {}
with zipfile.ZipFile(next(p.glob('*.xlsx'))) as z:
    strings = []
    if 'xl/sharedStrings.xml' in z.namelist():
        strings = [''.join(t.text or '' for t in s.findall('.//m:t', ns)) for s in E.fromstring(z.read('xl/sharedStrings.xml'))]
    for sheet, filename in [(1,'businesses.csv'),(3,'market_daily.csv'),(4,'market_sources.csv'),(5,'market_categories.csv'),(6,'buyers.csv'),(7,'buyers_by_region.csv')]:
        csv = pd.read_csv(p / filename, dtype=str).fillna('')
        cells = {}
        for c in E.fromstring(z.read(f'xl/worksheets/sheet{sheet}.xml')).findall('.//m:sheetData/m:row/m:c', ns):
            v = c.find('m:v', ns)
            val = v.text if v is not None else ''
            if c.get('t') == 's': val = strings[int(val)]
            if c.get('t') == 'inlineStr': val = ''.join(t.text or '' for t in c.findall('.//m:t', ns))
            cells[c.get('r')] = val
        mismatches = []
        for i, row in enumerate([list(csv.columns)] + csv.values.tolist(), 1):
            for j, val in enumerate(row, 1):
                letters = ''; k = j
                while k:
                    k, rem = divmod(k-1, 26); letters = chr(65+rem) + letters
                ref = f'{letters}{i}'; other = cells.get(ref, '')
                if filename == 'market_daily.csv' and i > 1 and j == 1:
                    other = (datetime(1899, 12, 30) + timedelta(days=float(other))).date().isoformat()
                same = val == other
                if not same:
                    try: same = float(val) == float(other)
                    except ValueError: pass
                if not same: mismatches.append({'cell':ref,'csv':val,'xlsx':other})
        checks[filename] = {'rows':len(csv),'cell_mismatches':len(mismatches),'examples':mismatches[:3]}
d = pd.read_csv(p/'businesses.csv')
g = d[(d['Участие в реферальной программе']==0)&d['Тип бизнеса (товары / услуги)'].isin(['товарное','товарное и услужное'])]
metrics = {'rows':len(d),'duplicate_ids':int(d['ID бизнеса'].duplicated().sum()),'goods_non_referral':len(g)}
for c in ['Подключён чекаут','Подключена доставка','Подключена оплата','Заказы через чекаут','GMV через чекаут, ₽','Траты на рекламу всего, ₽']:
    metrics[c] = {'positive_rows':int((g[c]>0).sum()),'sum':int(g[c].sum())}
metrics['checkout_off_with_orders'] = int(((d['Подключён чекаут']==0)&(d['Заказы через чекаут']>0)).sum())
metrics['orders_with_zero_gmv_ids'] = d.loc[(d['Заказы через чекаут']>0)&(d['GMV через чекаут, ₽']==0),'ID бизнеса'].tolist()
metrics['product_posts_exceed_posts'] = int((d['Посты с товаром за 30 дней']>d['Посты за 30 дней']).sum())
totals = {}
for f in ['market_daily.csv','market_categories.csv','buyers.csv','buyers_by_region.csv']:
    a = pd.read_csv(p/f)
    totals[f] = {c:float(a[c].sum()) for c in a.select_dtypes('number') if any(s in c for s in ['Заказы','заказы','GMV','Открытия'])}
print(json.dumps({'csv_vs_current_xlsx':checks,'business_metrics':metrics,'totals':totals},ensure_ascii=False,indent=2))
