"""Pure contract validation; this module does not persist business receipts."""
import hashlib
import json
import os
from pathlib import Path
from jsonschema import Draft202012Validator, FormatChecker

SCHEMA_PATH = Path(os.getenv('OPS_CONTRACT_SCHEMA', Path(__file__).resolve().parents[3] / 'contracts/ops-v1.schema.json'))
SCHEMA = json.loads(SCHEMA_PATH.read_text())
VALIDATOR = Draft202012Validator(SCHEMA, format_checker=FormatChecker())

class ContractError(ValueError):
    status_code = 400

class CommandConflict(ContractError):
    status_code = 409

def _wire_values(value):
    if value is None or isinstance(value, bool):
        return
    if isinstance(value, str):
        try: value.encode('utf-8')
        except UnicodeEncodeError: raise ContractError('invalid Unicode') from None
        return
    if isinstance(value, list):
        for item in value: _wire_values(item)
        return
    if isinstance(value, dict):
        for key,item in value.items():
            if not isinstance(key,str) or not key.isascii(): raise ContractError('object keys must be ASCII strings')
            _wire_values(item)
        return
    raise ContractError('numeric values must be decimal strings')

def payload_hash(command):
    """SHA256 of the entire command excluding payload_hash, recursively sorted ASCII keys.

    Only strings/null/booleans/arrays/objects are admitted, avoiding IEEE754 ambiguity.
    UTF-8, compact separators, no Unicode normalization, no lone surrogates.
    """
    _wire_values(command)
    if not isinstance(command,dict): raise ContractError('command must be an object')
    content={k:v for k,v in command.items() if k != 'payload_hash'}
    return hashlib.sha256(json.dumps(content,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode('utf-8')).hexdigest()

def validate_definition(name,value):
    _wire_values(value)
    schema={'$schema':SCHEMA['$schema'],'$ref':'#/$defs/'+name,'$defs':SCHEMA['$defs']}
    if not Draft202012Validator(schema,format_checker=FormatChecker()).is_valid(value): raise ContractError('invalid contract value')

def validate_command(command):
    _wire_values(command)
    if not VALIDATOR.is_valid(command): raise ContractError('invalid command structure')
    if payload_hash(command) != command['payload_hash']: raise ContractError('payload hash mismatch')
    return command

def compare_receipt(existing,incoming):
    """Compare two validated commands only. Not an inbox, database or HTTP endpoint."""
    validate_command(existing);validate_command(incoming)
    if existing['command_id'] != incoming['command_id']: return 'new'
    if existing['payload_hash'] != incoming['payload_hash']: raise CommandConflict('command_id content conflict')
    return 'duplicate'
