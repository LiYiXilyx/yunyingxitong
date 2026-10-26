/** Pure contract helpers. No durable receipt storage or business API. */
import { readFileSync } from 'node:fs';
import Ajv2020 from 'ajv/dist/2020.js';
import addFormats from 'ajv-formats';

const schema=JSON.parse(readFileSync(new URL('../ops-v1.schema.json',import.meta.url),'utf8'));
const ajv=new Ajv2020({strict:true,allErrors:true,coerceTypes:false});
addFormats(ajv);
ajv.addSchema(schema);
export type Command = {
  schema_version: '1'; command_id: string; payload_hash: string;
  binding_version: string; occurred_at: string; payload: Record<string,unknown>;
};
import runtime from './runtime.cjs';
export const payloadHash = runtime.payloadHash as (command:Record<string,unknown>)=>string;
export const validateCommand = runtime.validateCommand as (value:unknown)=>value is Command;
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
    runtime.canonical(value);
    return !!ajv.validate({$ref:schema.$id+'#/$defs/'+name},value);
  } catch {return false;}
}
