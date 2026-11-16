"""更正版本的保护格与可公开范围计算（纯函数，供页面与导出复用）。"""

def protection_rows(result):
    return [{'area':r['area'],'category':r['category'],'cell_id':r['cell_id'],'published':r['published'],'status':r['status']} for r in result['calculate']['rows']]

def protection(result):
    cells={}
    for row in result['calculate']['rows']:
        cells[(row['area'],row['category'])]={'status':row['status'],'published':row['published'],'cell_id':row['cell_id']}
    return cells

def scope(result):
    cells=protection(result)
    primary=sum(1 for v in cells.values() if v['status']=='主抑制')
    secondary=sum(1 for v in cells.values() if v['status']=='次抑制')
    inherited=sum(1 for v in cells.values() if v['status']=='继承保护')
    public=sum(1 for v in cells.values() if v['status']=='公开')
    return {
        'cells':len(cells),'primary':primary,'secondary':secondary,'inherited':inherited,
        'hidden':primary+secondary+inherited,'public':public,
        'threshold':result['calculate']['threshold'],
        'releasable':bool(result['calculate']['release_ready'] and result['reconcile']['balanced']),
        'total':result['model']['total'],
    }

def _label(cell):
    if cell is None:return '—'
    return cell['published'] if cell['status']=='公开' else f"{cell['status']} —"

def compare(old,new):
    """两版逐格对照。保护格在任一侧为隐藏即视为受保护格。"""
    before=protection(old);after=protection(new);rows=[]
    for key in sorted(set(before)|set(after)):
        a=before.get(key);b=after.get(key)
        protected=(a is not None and a['status']!='公开') or (b is not None and b['status']!='公开')
        if a is None:
            change,risk='新增格',''
        elif b is None:
            change,risk='移除格',''
        elif a['status']!='公开' and b['status']!='公开':
            change,risk='保持保护',''
        elif a['status']!='公开' and b['status']=='公开':
            change,risk='解除保护','旧版隐藏值可由新旧两版对照反推'
        elif a['status']=='公开' and b['status']!='公开':
            change,risk='新增保护','旧版已公开该值，追溯撤回无效'
        elif a['published']==b['published']:
            change,risk='公开不变',''
        else:
            change,risk='公开值更正',''
        rows.append({'area':key[0],'category':key[1],'old':_label(a),'new':_label(b),
                     'old_status':a['status'] if a else '—','new_status':b['status'] if b else '—',
                     'change':change,'risk':risk,'protected':protected,
                     'changed':change not in ('保持保护','公开不变')})
    rows.sort(key=lambda r:(not r['changed'],not r['protected'],r['area'],r['category']))
    return rows
