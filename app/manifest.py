import hashlib
import json
from app.config import VERSION

def digest(raw, params, base=None):
    body={'sha256':hashlib.sha256(raw).hexdigest(),'params':params,'version':VERSION}
    if base is not None:
        body['amends']=base
        body['kind']='correction'
    content=json.dumps(body,sort_keys=True,separators=(',',':'),ensure_ascii=False)
    return hashlib.sha256(content.encode()).hexdigest()

def manifest(raw, params, elapsed, base=None):
    return {'run_id':digest(raw,params,base)[:20], 'sha256':hashlib.sha256(raw).hexdigest(), 'rule_version':VERSION, 'params':params, 'elapsed_ms':round(elapsed*1000,3), 'amends':base}
