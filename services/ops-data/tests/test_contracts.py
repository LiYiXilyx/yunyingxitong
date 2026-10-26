import copy
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import pytest

ROOT = Path(__file__).resolve().parents[3]

def api():
    assert importlib.util.find_spec('ops_data.contracts'), 'T02 contract implementation missing'
    from ops_data import contracts
    return contracts

def fixtures():
    return json.loads((ROOT/'contracts/fixtures/synthetic/commands.json').read_text())

def test_shared_valid_fixtures():
    for value in fixtures():
        api().validate_command(value)

@pytest.mark.parametrize('field,value', [('schema_version','2'), ('command_id',1), ('binding_version',1.0), ('binding_version',True), ('binding_version',9007199254740992), ('occurred_at','2026-10-22T00:00:00'), ('extra',1)])
def test_strict_envelope(field,value):
    contract=api(); value0=copy.deepcopy(fixtures()[0]); value0[field]=value
    with pytest.raises(contract.ContractError): contract.validate_command(value0)

def test_tampered_hash_and_conflict():
    contract=api(); first=fixtures()[0]; changed=copy.deepcopy(first)
    changed['binding_version']=str(int(changed['binding_version'])+1)
    with pytest.raises(contract.ContractError): contract.validate_command(changed)
    changed['payload_hash']=contract.payload_hash(changed)
    assert contract.compare_receipt(first,first)=='duplicate'
    with pytest.raises(contract.CommandConflict) as err: contract.compare_receipt(first,changed)
    assert err.value.status_code==409

def test_key_order_and_decimal():
    contract=api(); first=fixtures()[0]
    assert contract.payload_hash(dict(reversed(list(first.items()))))==first['payload_hash']
    for x in ['0','12.30','-1.00','9007199254740993.01']: contract.validate_definition('Money',x)
    for x in [1,1.5,True,'1e3','01.00','NaN']:
        with pytest.raises(contract.ContractError): contract.validate_definition('Money',x)

def test_typescript_same_corpus():
    contract=api(); cases=[]
    for first in fixtures():
        cases.append(first)
        for field,value in [('schema_version','2'),('binding_version',True),('binding_version',1.5),('extra','x'),('payload_hash','0'*64)]:
            changed=copy.deepcopy(first);changed[field]=value;cases.append(changed)
    expected=[]
    for value in cases:
        try: contract.validate_command(value);expected.append(True)
        except contract.ContractError:expected.append(False)
    result=subprocess.run(['node','contracts/typescript/validate.ts'],cwd=ROOT,input=json.dumps(cases),text=True,capture_output=True,check=True)
    assert json.loads(result.stdout)==expected

@pytest.mark.parametrize('index,field,value',[
    (0,'expected_version',1),(0,'reason',False),(0,'action','close'),
    (1,'outcome','recovered'),(1,'scope',{'store_ids':[1],'warehouse_ids':[]}),
    (2,'review_generation',None),(3,'result','normal'),
    (4,'last_success_at','2026-10-22T00:00:00'),(4,'status','insufficient')])
def test_payload_strict_types(index,field,value):
    contract=api();command=copy.deepcopy(fixtures()[index]);command['payload'][field]=value
    with pytest.raises(contract.ContractError):contract.validate_command(command)

def test_hash_golden_unicode_and_large_revision():
    contract=api();command=fixtures()[-1]
    assert command['binding_version']=='9007199254740993'
    assert contract.payload_hash(command)==command['payload_hash']

@pytest.mark.parametrize('name,value', [(c['definition'],c['value']) for c in json.loads((ROOT/'contracts/fixtures/synthetic/invalid-definitions.json').read_text())])
def test_shared_definition_edge_rejections(name,value):
    contract=api()
    with pytest.raises(contract.ContractError): contract.validate_definition(name,value)
    result=subprocess.run(['node','contracts/typescript/definitions.ts'],cwd=ROOT,input=json.dumps([[name,value]]),text=True,capture_output=True,check=True)
    assert json.loads(result.stdout)==[False]


def test_shared_invalid_signed_commands():
    contract=api()
    values=json.loads((ROOT/'contracts/fixtures/synthetic/invalid-commands.json').read_text())
    for value in values:
        assert contract.payload_hash(value)==value['payload_hash']
        with pytest.raises(contract.ContractError):contract.validate_command(value)
    result=subprocess.run(['node','contracts/typescript/validate.ts'],cwd=ROOT,input=json.dumps(values),text=True,capture_output=True,check=True)
    assert json.loads(result.stdout)==[False]*len(values)


def test_openapi_separates_implemented_nocobase_commands_from_pending_data_apis():
    document=json.loads((ROOT/'contracts/openapi.yaml').read_text())
    implemented={path for path,methods in document['paths'].items() if any(operation.get('x-implementation')=='implemented' for operation in methods.values())}
    assert implemented=={'/health/live','/health/ready','/api/opsConfig:snapshot','/api/opsConfig:command','/api/opsRule:command','/api/opsDataHealth:ingest'}
    for path,method in [('/api/opsConfig:snapshot','get'),('/api/opsConfig:command','post'),('/api/opsRule:command','post'),('/api/opsDataHealth:ingest','post')]:
        operation=document['paths'][path][method]
        assert operation['servers']==[{'url':'http://127.0.0.1:13000'}]
        assert operation['security']==[{'nocobaseBearer':[]}]
    assert document['servers']==[{'url':'http://127.0.0.1:18000'}]


def test_t03_config_command_version_is_an_integer_not_signed_envelope_revision():
    from jsonschema import Draft202012Validator
    from jsonschema.exceptions import ValidationError
    document=json.loads((ROOT/'contracts/openapi.yaml').read_text())
    schema={'$ref':'#/components/schemas/ConfigCommand','components':document['components']}
    validate=Draft202012Validator(schema).validate
    command={'command':'saveMembership','command_id':'example-command','expected_version':0,'reason':'synthetic test','values':{'business_id':'33333333-3333-4333-a333-333333333333','store_id':'858f0efd-4409-406c-adfb-28490350fd39','user_id':2,'membership_role':'ops_operator','environment':'synthetic'}}
    validate(command)
    for version in ['0',True,1.5]:
        with pytest.raises(ValidationError):
            validate({**command,'expected_version':version})
