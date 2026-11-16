from fastapi.templating import Jinja2Templates
from app.config import ROOT,TITLE,SHORT,PAGES,VERSION
from app import amend,store
from app.pipeline import run
templates=Jinja2Templates(directory=ROOT/'app/templates')

def render(request,page,rid=None):
    result=store.read(rid) if rid else store.save(run({'sample':'dirty'}))
    current=result['manifest']['run_id'];versions=store.family(current)
    head=store.head_of(current)
    rows=[v|{'scope':amend.scope(v)} for v in versions]
    # 逐格对照默认看"当前版 vs 它的前一版"；根版本尚未更正时看"根版本 vs 有效版"。
    parent=next((v for v in versions if v['manifest']['run_id']==result['parent']),None) if result['parent'] else None
    if parent is not None:
        old,new=parent,result
    else:
        old,new=versions[0],versions[-1]
    comparison=amend.compare(old,new) if old['manifest']['run_id']!=new['manifest']['run_id'] else []
    releasable=amend.scope(result)['releasable'] and result['status']=='active'
    context={'title':TITLE,'short':SHORT,'pages':PAGES,'page':page,'page_title':dict(PAGES)[page],'version':VERSION,
        'result':result,'section':result[page],'history':store.history(),
        'versions':rows,'head':head,'current':current,'current_scope':amend.scope(result),'releasable':releasable,
        'comparison':comparison,'compare_old':old if comparison else None,'compare_new':new if comparison else None}
    return templates.TemplateResponse(request=request,name=f'{page}.html',context=context)
