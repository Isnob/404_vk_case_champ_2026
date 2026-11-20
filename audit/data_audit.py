"""Reproducible local-data audit; writes only under audit/. Run from any directory."""
from pathlib import Path
from datetime import datetime, timedelta
import json, math, zipfile, xml.etree.ElementTree as E, hashlib
import pandas as pd
ROOT=Path(__file__).resolve().parents[1]; D=ROOT/'data'; O=ROOT/'audit'
d=pd.read_csv(D/'businesses.csv'); n=d[d['Участие в реферальной программе']==0]; g=n[n['Тип бизнеса (товары / услуги)'].isin(['товарное','товарное и услужное'])]
order='Заказы через чекаут'; price='Медианная цена товара, ₽'; ad='Траты на рекламу всего, ₽'; gmv='GMV через чекаут, ₽'; pay='Подключена оплата'; orig='Автор оригинального контента (оценка модели)'
def prof(a):
 return {'n':len(a),'pay':int(a[pay].sum()),'pay_percent':100*a[pay].mean(),'ordered_businesses':int((a[order]>0).sum()),'orders':int(a[order].sum()),'gmv':int(a[gmv].sum()),'ads':int(a[ad].sum()),'product_post_businesses':int((a['Посты с товаром за 30 дней']>0).sum())}
r={'groups':{'all':prof(d),'nonreferral':prof(n),'goods_nonreferral':prof(g),'goods_including_referral':prof(d[d['Тип бизнеса (товары / услуги)'].isin(['товарное','товарное и услужное'])]),'no_catalog_nonreferral':prof(n[n['Тип бизнеса (товары / услуги)']=='без каталога']),'micro_le_1000':prof(g[g['Число подписчиков']<=1000]),'large_gt_50000':prof(g[g['Число подписчиков']>50000]),'payment_enabled':prof(g[g[pay]==1]),'payment_disabled':prof(g[g[pay]==0])}}
r['business_counts']={'total':len(d),'nonreferral':len(n),'referral':int(d['Участие в реферальной программе'].sum()),'nonreferral_types':n['Тип бизнеса (товары / услуги)'].value_counts().to_dict(),'missing':d.isna().sum().to_dict(),'catalog_loaded_goods':int((g['Товары загружены']>0).sum()),'catalog_active_goods':int((g['Число активных товаров в каталоге']>0).sum()),'pay_and_delivery':int(((g[pay]==1)&(g['Подключена доставка']==1)).sum()),'paid_group_median_followers':g.loc[g[pay]==1,'Число подписчиков'].median(),'unpaid_group_median_followers':g.loc[g[pay]==0,'Число подписчиков'].median()}
r['prices']={'median_of_community_medians_ordered':g.loc[g[order]>0,price].median(),'median_of_community_medians_all':g[price].median(),'median_community_aov_ordered':g.loc[g[order]>0,'Средний чек, ₽'].median(),'weighted_goods_aov':g[gmv].sum()/g[order].sum()}
ordinary='Просмотры обычного контента'; product='Просмотры товарного контента'; likes='Лайки обычного контента'; plikes='Лайки товарного контента'; b=g[(g[ordinary]>0)&(g[product]>0)]
r['content']={'posts_total':int(g['Посты за 30 дней'].sum()),'posts_product':int(g['Посты с товаром за 30 дней'].sum()),'product_post_businesses':int((g['Посты с товаром за 30 дней']>0).sum()),'clips_total':int(g['Клипы за 30 дней'].sum()),'clips_product':int(g['Клипы с товаром за 30 дней'].sum()),'product_clip_businesses':int((g['Клипы с товаром за 30 дней']>0).sum()),'both_views_n':len(b),'ordinary_ER_median':100*(b[likes]/b[ordinary]).median(),'product_ER_median':100*(b[plikes]/b[product]).median(),'ordinary_ER_pooled':100*b[likes].sum()/b[ordinary].sum(),'product_ER_pooled':100*b[plikes].sum()/b[product].sum(),'both_views_product_zero_likes':int((b[plikes]==0).sum()),'both_views_ordinary_zero_likes':int((b[likes]==0).sum()),'ordered_card_opens_mean':g.loc[g[order]>0,'Открытия карточки товара из контента'].mean(),'nonordered_card_opens_mean':g.loc[g[order]==0,'Открытия карточки товара из контента'].mean()}
no_cat=n[n['Тип бизнеса (товары / услуги)']=='без каталога']
r['methodology']={'no_catalog_advertisers':int((no_cat[ad]>0).sum()),'loaded_without_catalog_nonref':int(((n['Тип бизнеса (товары / услуги)']=='без каталога')&(n['Товары загружены']>0)).sum()),'loaded_service_nonref':int(((n['Тип бизнеса (товары / услуги)']=='услужное')&(n['Товары загружены']>0)).sum()),'loaded_without_catalog_all':int(((d['Тип бизнеса (товары / услуги)']=='без каталога')&(d['Товары загружены']>0)).sum()),'loaded_service_all':int(((d['Тип бизнеса (товары / услуги)']=='услужное')&(d['Товары загружены']>0)).sum()),'product_posts_exceed_total':int((d['Посты с товаром за 30 дней']>d['Посты за 30 дней']).sum()),'product_posts_with_zero_total':int(((d['Посты с товаром за 30 дней']>0)&(d['Посты за 30 дней']==0)).sum()),'product_clips_exceed_total':int((d['Клипы с товаром за 30 дней']>d['Клипы за 30 дней']).sum()),'ordered_no_content_opens':int(((d[order]>0)&(d['Открытия карточки товара из контента']==0)).sum()),'orders_exceed_content_opens':int((d[order]>d['Открытия карточки товара из контента']).sum()),'views_without_publications':int(((d['Посты за 30 дней']==0)&(d['Клипы за 30 дней']==0)&(d[ordinary]>0)).sum()),'product_views_without_publications':int(((d['Посты с товаром за 30 дней']==0)&(d['Клипы с товаром за 30 дней']==0)&(d[product]>0)).sum()),'loaded_inactive':int(((d['Товары загружены']>0)&(d['Число активных товаров в каталоге']==0)).sum()),'loaded_inactive_price':int(((d['Товары загружены']>0)&(d['Число активных товаров в каталоге']==0)&(d[price]>0)).sum()),'no_goods_has_services':int(((d['Товары загружены']==0)&(d['Число активных услуг']>0)).sum()),'no_goods_has_services_price':int(((d['Товары загружены']==0)&(d['Число активных услуг']>0)&(d[price]>0)).sum()),'service_with_price':int(((d['Тип бизнеса (товары / услуги)']=='услужное')&(d[price]>0)).sum()),'zero_gmv':int((d[gmv]==0).sum()),'zero_gmv_aov_present':int(((d[gmv]==0)&d['Средний чек, ₽'].notna()).sum()),'positive_gmv':int((d[gmv]>0).sum()),'positive_gmv_aov_missing':int(((d[gmv]>0)&d['Средний чек, ₽'].isna()).sum())}
positive=d[d[order]>0];err=(positive[gmv]/positive[order]-positive['Средний чек, ₽']).abs();r['methodology']['aov_max_rounding_error']=err.max()
r['methodology']['aov_error_gt_1_rub']=int((err>1).sum())
r['methodology']['aov_nonmissing_ordered']=int(err.notna().sum())
bad=positive.assign(calculated_aov=positive[gmv]/positive[order],absolute_error=err).sort_values('absolute_error',ascending=False)
r['methodology']['aov_error_examples']=bad[['ID бизнеса',order,gmv,'Средний чек, ₽','calculated_aov','absolute_error']].head(10).to_dict('records')
r['themes']=g.groupby('Тематика').agg(n=('ID бизнеса','size'),ads=(ad,'sum'),orders=(order,'sum'),original_nonmissing=(orig,'count'),original_ones=(orig,'sum'),original_fraction=(orig,'mean')).reset_index().to_dict('records')
cat=pd.read_csv(D/'market_categories.csv');daily=pd.read_csv(D/'market_daily.csv');sources=pd.read_csv(D/'market_sources.csv')
r['macro']={'category_totals':cat.select_dtypes('number').sum().to_dict(),'daily_totals':daily.select_dtypes('number').sum().to_dict(),'dau_mean':daily['DAU Маркета Вконтакте'].mean(),'source_totals_excluding_referral_row':sources.iloc[:6].select_dtypes('number').sum().to_dict(),'feed_clips_both':int(sources[sources['Источник'].isin(['Лента','Клипы'])][['Маркет Вконтакте','Партнёр 1']].sum().sum()),'feed_clips_partner':int(sources[sources['Источник'].isin(['Лента','Клипы'])]['Партнёр 1'].sum()),'paid_rate':100*4903/413740,'partner_orders_per_card_open':100*4927525/86882822,'partner_orders_per_total_outbound_click':100*4927525/(36626075+106914679),'vk_orders_per_card_open':100*413740/193512461,'dau_mau_ratio':127406/2997341,'food_pct_of_category_sum':100*195355/cat['Заказы: Маркет Вконтакте'].sum(),'hobby_pct_of_category_sum':100*110703/cat['Заказы: Маркет Вконтакте'].sum()}
for market in ['Маркет Вконтакте','Партнёр 1']:
 cat[f'orders_per_open_pct_{market}']=cat[f'Заказы: {market}']/cat[f'Открытия карточки: {market}'].replace(0,float('nan'))*100
r['categories']=cat.to_dict('records')
# Audit Markdown summary against the actual current XLSX values (not presentation styles).
ns={'m':'http://schemas.openxmlformats.org/spreadsheetml/2006/main'}
with zipfile.ZipFile(next(D.glob('*.xlsx'))) as z:
 strings=[''.join(t.text or '' for t in s.findall('.//m:t',ns)) for s in E.fromstring(z.read('xl/sharedStrings.xml'))] if 'xl/sharedStrings.xml' in z.namelist() else []
 rows=[]
 for row in E.fromstring(z.read('xl/worksheets/sheet2.xml')).findall('.//m:sheetData/m:row',ns):
  vals=[]
  for c in row:
   v=c.find('m:v',ns);val=v.text if v is not None else ''
   if c.get('t')=='s':val=strings[int(val)]
   if c.get('t')=='inlineStr':val=''.join(t.text or '' for t in c.findall('.//m:t',ns))
   vals.append([c.get('r'),val])
  rows.append(vals)
 r['xlsx_summary_cells']=rows
 # Compare all Markdown numeric/text cells with XLSX B/C or D based on its section.
 by_label={row[0][1]:dict((cell[0][0],cell[1]) for cell in row[1:]) for row in rows if row}
 summary_mismatches=[]; summary_checked=0
 for line in (D/'market_summary.md').read_text().splitlines():
  if not line.startswith('|'):continue
  values=[x.strip() for x in line.strip('|').split('|')]
  if values[0] not in by_label or values[0]=='Метрика':continue
  target=by_label[values[0]]
  columns=['B','C'] if len(values)==3 else ['D']
  for col,value in zip(columns,values[1:]):
   source=target.get(col,''); summary_checked+=1;equal=value==source
   if not equal:
    try:equal=math.isclose(float(value),float(source),rel_tol=1e-12,abs_tol=1e-12)
    except ValueError:pass
   if not equal:summary_mismatches.append({'metric':values[0],'column':col,'markdown':value,'xlsx':source})
 r['summary_export_check']={'cells_checked':summary_checked,'mismatches':summary_mismatches}
r['input_sha256']={f.name:hashlib.sha256(f.read_bytes()).hexdigest() for f in D.iterdir() if f.suffix in ['.csv','.md','.xlsx']}
# JSON convert nonfinite to null.
def clean(v):
 if isinstance(v,dict):return {k:clean(x) for k,x in v.items()}
 if isinstance(v,list):return [clean(x) for x in v]
 if isinstance(v,float) and not math.isfinite(v):return None
 return v
(O/'data_audit_results.json').write_text(json.dumps(clean(r),ensure_ascii=False,indent=2),encoding='utf-8')
print('Saved',O/'data_audit_results.json')
