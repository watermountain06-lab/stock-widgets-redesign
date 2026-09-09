import re,sys,html
t=sys.argv[1]
s=open(f"{t}_full_widget.html",encoding='utf-8').read()
def txt(x): return re.sub(r'\s+',' ',html.unescape(re.sub(r'<[^>]+>','',x))).strip()
z=re.search(r'<div class="zone-list">(.*?)\n      </div>',s,re.S)
print(f"  핵심가격대 rows: {len(re.findall(r'zone-item',z.group(1))) if z else 'n/a'}  (limit 5)")
for sec,label in [('valuation','밸류'),('news','뉴스')]:
    m=re.search(rf'<div id="{sec}" class="section">(.*?)(?=<div id="\w+" class="section">|\Z)',s,re.S)
    if not m: continue
    b=re.search(r'class="verdict-summary-body">(.*?)</div>',m.group(1),re.S)
    print(f"  {label} body: {len(txt(b.group(1))) if b else 0}자 (limit 250)")
    for cls,nm,lim in [('verdict-summary-risk','risk',150),('verdict-summary-counter','counter',150),('verdict-summary-next','next',120)]:
        x=re.search(rf'class="{cls}">(.*?)</div>',m.group(1),re.S)
        if x: print(f"     {nm}: {len(txt(x.group(1)))}자 (limit {lim})")
for cls,lim in [('tl-title',100),('tl-desc',100),('bb-item',90)]:
    v=[len(txt(x)) for x in re.findall(rf'class="{cls}">(.*?)</div>',s,re.S)]
    over=[x for x in v if x>lim]
    print(f"  {cls}: max {max(v) if v else 0}자, 합 {sum(v)}자, 초과 {len(over)}개 {over if over else ''} (limit {lim})")
