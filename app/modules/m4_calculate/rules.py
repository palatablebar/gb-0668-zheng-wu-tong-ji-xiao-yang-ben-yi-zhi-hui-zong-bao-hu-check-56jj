import heapq

def nodes(cell):return ('r:'+cell['area'],'c:'+cell['category'])

def bridges(rows,hidden):
    edges={r['cell_id']:nodes(r) for r in rows if r['cell_id'] in hidden}
    result=[]
    for edge,(start,end) in sorted(edges.items()):
        seen={start};queue=[start]
        for node in queue:
            for key,(a,b) in edges.items():
                if key==edge:continue
                target=b if a==node else a if b==node else None
                if target is not None and target not in seen:seen.add(target);queue.append(target)
        if end not in seen:result.append(edge)
    return result

def alternate_path(rows,hidden,excluded):
    edge=next(r for r in rows if r['cell_id']==excluded);start,end=nodes(edge)
    adjacency={}
    for r in sorted(rows,key=lambda x:x['cell_id']):
        if r['cell_id']==excluded:continue
        a,c=nodes(r);weight=0 if r['cell_id'] in hidden else r['weight']
        adjacency.setdefault(a,[]).append((c,weight,r['cell_id']))
        adjacency.setdefault(c,[]).append((a,weight,r['cell_id']))
    queue=[(0,(),start)];best={start:(0,())}
    while queue:
        cost,path,node=heapq.heappop(queue)
        if best.get(node)!=(cost,path):continue
        if node==end:return list(path)
        for target,weight,key in adjacency.get(node,[]):
            if key in path:continue
            candidate=(cost+weight,path+(key,))
            if target not in best or candidate<best[target]:best[target]=candidate;heapq.heappush(queue,(*candidate,target))
    return None

def suppress(rows,threshold,floor=()):
    """主抑制后补次抑制。

    floor 是更正版必须继承的保护位置 (area, category)；它只增不减，避免旧版
    已隐藏的格在新版公开后，被两版对照反推出人数。按位置而非 cell_id 继承，
    这样更正时单元格重新编号也不会丢失保护。floor 不改变补环结果，只把继承
    格预先计入 hidden。
    """
    protected={tuple(pos) for pos in floor}
    primary={r['cell_id'] for r in rows if 0<r['count']<threshold}
    inherited={r['cell_id'] for r in rows if (r['area'],r['category']) in protected}-primary
    hidden=set(primary)|inherited
    added=[]
    for _ in range(len(rows)+1):
        unsafe=bridges(rows,hidden)
        if not unsafe:break
        path=alternate_path(rows,hidden,unsafe[0])
        if path is None:break
        new=set(path)-hidden
        if not new:break
        hidden|=new;added.extend(sorted(new))
    published=[]
    for r in rows:
        if r['cell_id'] in primary:kind='主抑制'
        elif r['cell_id'] in inherited:kind='继承保护'
        elif r['cell_id'] in hidden:kind='次抑制'
        else:kind='公开'
        published.append({'cell_id':r['cell_id'],'area':r['area'],'category':r['category'],'published':'—' if r['cell_id'] in hidden else str(r['count']),'status':kind,'weight':r['weight'],'line':r['line']})
    return {'rows':published,'primary':sorted(primary),'inherited':sorted(inherited),'secondary':added,'hidden':sorted(hidden),'unsafe':bridges(rows,hidden),'cost':sum(r['weight'] for r in rows if r['cell_id'] in set(added)),'safe':not bridges(rows,hidden)}
