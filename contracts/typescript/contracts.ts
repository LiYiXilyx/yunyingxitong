/** Pure contract helpers. No durable receipt storage or business API. */
import { createHash } from 'node:crypto';
import { readFileSync } from 'node:fs';
import Ajv2020 from 'ajv/dist/2020.js';
import addFormats from 'ajv-formats';

const schema=JSON.parse(readFileSync(new URL('../ops-v1.schema.json',import.meta.url),'utf8'));
const ajv=new Ajv2020({strict:true,allErrors:true,coerceTypes:false});
addFormats(ajv);
const validate=ajv.compile(schema);
export type Command = {
  schema_version: '1'; command_id: string; payload_hash: string;
  binding_version: string; occurred_at: string; payload: Record<string,unknown>;
};
function canonical(value:unknown):string {
  if(value===null || typeof value==='boolean') return JSON.stringify(value);
  if(typeof value==='string') {
    if(/[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/u.test(value)) throw new Error('invalid Unicode');
    return JSON.stringify(value);
  }
  if(Array.isArray(value)) return '['+value.map(canonical).join(',')+']';
  if(typeof value==='object') {
    const object=value as Record<string,unknown>;
    const keys=Object.keys(object).sort();
    if(keys.some(key=>/[^\x00-\x7F]/u.test(key))) throw new Error('object keys must be ASCII');
    return '{'+keys.map(key=>JSON.stringify(key)+':'+canonical(object[key])).join(',')+'}';
  }
  throw new Error('numeric values must be decimal strings');
}
export function payloadHash(command:Record<string,unknown>):string {
  if(!command || Array.isArray(command) || typeof command!=='object') throw new Error('command must be an object');
  canonical(command);
  const {payload_hash,...content}=command;
  return createHash('sha256').update(canonical(content),'utf8').digest('hex');
}
export function validateCommand(value:unknown):value is Command {
  try {return !!validate(value) && payloadHash(value as Command)===(value as Command).payload_hash;} catch {return false;}
}
export class CommandConflict extends Error { statusCode=409; }
export function compareReceipt(existing:unknown,incoming:unknown):'new'|'duplicate' {
  if(!validateCommand(existing)||!validateCommand(incoming)) throw new Error('invalid command');
  if(existing.command_id!==incoming.command_id) return 'new';
  if(existing.payload_hash!==incoming.payload_hash) throw new CommandConflict('command_id content conflict');
  return 'duplicate';
}
export function validateDefinition(name:string,value:unknown):boolean {
  if(!Object.hasOwn(schema.$defs,name)) return false;
  try {
    canonical(value);
    return !!ajv.validate({$ref:schema.$id+'#/$defs/'+name},value);
  } catch {return false;}
}
