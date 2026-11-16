from fastapi import APIRouter, Body
from app.errors import DomainError
router = APIRouter(prefix='/api/batches', tags=['batches'])

def _floor(base):
    """更正版必须继承的隐藏位置：旧版已保护，就不允许在新版公开。"""
    return {(row['area'],row['category']) for row in base['calculate']['rows'] if row['status']!='公开'}

@router.get('')
def sample():
    from app.pipeline import run
    return run({'sample':'dirty'})['batches']

@router.post('')
def execute(payload: dict = Body(default={})):
    if not isinstance(payload.get('params',{}),dict):raise DomainError('PARAMS','参数必须为对象')
    from app.pipeline import run
    from app import store
    amend=payload.get('amend')
    if amend is not None:
        if not isinstance(amend,str) or not amend:raise DomainError('AMEND','更正基准批次号无效')
        base=store.read(amend)
        result=run(payload,base=amend,floor=_floor(base))
        safe=result['reconcile']['balanced'] and result['calculate']['release_ready']
        # 旧基准已停用时交给 store 判定：命中同一更正则幂等返回，否则 BASE_STALE。
        if base['status']=='active' and not safe:
            raise DomainError('UNSAFE_CORRECTION','更正版未通过对账或保护检查，未切换，当前版本保持有效',409)
        return store.correct(amend,result)
    return store.save(run(payload))
