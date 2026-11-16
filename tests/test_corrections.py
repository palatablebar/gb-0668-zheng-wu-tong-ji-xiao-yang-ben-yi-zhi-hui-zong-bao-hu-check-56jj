import csv
import io
import pytest
from fastapi.testclient import TestClient
from app.main import app
from app import store,amend
from app.errors import DomainError
from app.config import ROOT


def client():return TestClient(app)

def baseline():
    result=client().post('/api/batches',json={'sample':'dirty'}).json()
    return result['manifest']['run_id'],result

def corrected_csv(**changes):
    rows=list(csv.DictReader(io.StringIO((ROOT/'sample_data/clean.csv').read_text(encoding='utf-8-sig'))))
    for row in rows:
        if row['cell_id'] in changes:row['count']=str(changes[row['cell_id']])
    return _write(rows)

def _write(rows):
    out=io.StringIO(newline='');writer=csv.DictWriter(out,fieldnames=list(rows[0]))
    writer.writeheader();writer.writerows(rows)
    return out.getvalue()

def balanced_correction(**changes):
    """count 变化后同步改行/列合计，保持合计一致。"""
    rows=list(csv.DictReader(io.StringIO((ROOT/'sample_data/clean.csv').read_text(encoding='utf-8-sig'))))
    row_delta={};col_delta={}
    for row in rows:
        if row['cell_id'] in changes:
            new=int(changes[row['cell_id']]);diff=new-int(row['count'])
            row_delta[row['area']]=row_delta.get(row['area'],0)+diff
            col_delta[row['category']]=col_delta.get(row['category'],0)+diff
            row['count']=str(new)
    for row in rows:
        row['row_total']=str(int(row['row_total'])+row_delta.get(row['area'],0))
        row['column_total']=str(int(row['column_total'])+col_delta.get(row['category'],0))
    return _write(rows)


def test_correction_supersedes_and_keeps_original_readable():
    rid,_=baseline()
    response=client().post('/api/batches',json={'sample':'clean','amend':rid})
    assert response.status_code==200
    new=response.json();assert new['version']==2 and new['parent']==rid and new['status']=='active'
    old=store.read(rid)
    assert old['status']=='superseded' and old['superseded_by']==new['manifest']['run_id']
    assert old['manifest']['sha256']==store.read(rid)['manifest']['sha256']
    assert client().get('/batches?run='+rid).status_code==200


def test_correction_retry_adds_no_revision():
    rid,_=baseline()
    first=client().post('/api/batches',json={'sample':'clean','amend':rid}).json()
    again=client().post('/api/batches',json={'sample':'clean','amend':rid}).json()
    assert again['manifest']['run_id']==first['manifest']['run_id']
    assert again['idempotent'] and not again['created']
    assert len(store.family(rid))==2


def test_identical_resubmit_is_not_a_correction():
    rid,_=baseline()
    same=client().post('/api/batches',json={'sample':'dirty','amend':rid}).json()
    assert same['unchanged'] and not same['created']
    assert store.read(rid)['status']=='active'
    assert len(store.family(rid))==1


def test_failed_switch_keeps_old_version_active():
    rid,_=baseline()
    broken='cell_id,area,category,count,weight,row_total,column_total,note\nS11,001,C01,9,1,9,9,x\n'
    response=client().post('/api/batches',json={'csv':broken,'amend':rid})
    assert response.status_code==409
    assert response.json()['code']=='UNSAFE_CORRECTION'
    head=store.head_of(rid)
    assert head['manifest']['run_id']==rid and head['status']=='active'
    assert len(store.family(rid))==1


def test_correction_inherits_protection_and_cannot_reopen():
    rid,_=baseline()
    before=store.read(rid)['calculate']['hidden']
    # S11 人数改为 9，已高于阈值；若只按阈值判定就会公开旧版隐藏的格。
    data=balanced_correction(S11=9)
    new=store.read(client().post('/api/batches',json={'csv':data,'amend':rid}).json()['manifest']['run_id'])
    assert 'S11' in new['calculate']['inherited']
    assert set(before)<=set(new['calculate']['hidden'])
    cell=next(row for row in new['calculate']['rows'] if row['cell_id']=='S11')
    assert cell['published']=='—' and cell['status']=='继承保护'


def test_old_version_is_review_only_and_export_watermarked():
    rid,_=baseline()
    client().post('/api/batches',json={'sample':'clean','amend':rid})
    old=store.read(rid)
    response=client().post('/api/review/'+rid,json={'revision':old['revision']})
    assert response.status_code==409 and response.json()['code']=='SUPERSEDED'
    export=client().get('/api/export/'+rid)
    assert export.status_code==200
    assert 'historical' in export.headers['content-disposition']
    assert export.text.splitlines()[0].lstrip('﻿').startswith('历史版本')


def test_amending_a_superseded_version_is_rejected():
    rid,_=baseline()
    client().post('/api/batches',json={'sample':'clean','amend':rid})
    response=client().post('/api/batches',json={'sample':'clean','amend':rid})
    # 相同内容幂等返回，不新建；换成不同内容则拒绝旧基准。
    assert response.status_code==200
    other=balanced_correction(S11=9)
    stale=client().post('/api/batches',json={'csv':other,'amend':rid})
    assert stale.status_code==409 and stale.json()['code']=='BASE_STALE'


def test_versions_endpoint_exposes_both_scopes():
    rid,_=baseline()
    client().post('/api/batches',json={'sample':'clean','amend':rid})
    body=client().get('/api/versions/'+rid).json()
    assert len(body['versions'])==2
    assert body['versions'][0]['status']=='superseded'
    assert body['versions'][1]['status']=='active'
    assert body['active']==body['versions'][1]['run_id']
    for item in body['versions']:
        assert item['scope']['hidden']==item['scope']['primary']+item['scope']['secondary']+item['scope']['inherited']
        assert item['scope']['hidden']+item['scope']['public']==item['scope']['cells']
    assert len(body['versions'][0]['protection'])==30


def test_scope_counts_add_up():
    rid,_=baseline()
    scope=amend.scope(store.read(rid))
    assert scope['primary']==6 and scope['secondary']==6 and scope['inherited']==0
    assert scope['hidden']==12 and scope['public']==18 and scope['releasable']
