import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';

test('implementation exists and validates shared fixtures and conflict', async () => {
  const { validateCommand, compareReceipt, payloadHash } = await import('./contracts.ts');
  const fixtures=JSON.parse(readFileSync(new URL('../fixtures/synthetic/commands.json',import.meta.url),'utf8'));
  for (const value of fixtures) {
    assert.equal(validateCommand(value),true);
    assert.equal(compareReceipt(value,value),'duplicate');
    const changed=structuredClone(value); changed.binding_version='2';
    assert.equal(validateCommand(changed),false);
    changed.payload_hash=payloadHash(changed);
    assert.throws(()=>compareReceipt(value,changed),{statusCode:409});
  }
});

test('shared definitions reject numeric money and accept exact decimal strings',async()=>{
  const {validateDefinition}=await import('./contracts.ts');
  for(const value of ['0','12.30','-1.00','9007199254740993.01']) assert.equal(validateDefinition('Money',value),true);
  for(const value of [1,1.5,true,'1e3','01.00','NaN']) assert.equal(validateDefinition('Money',value),false);
});

test('shared edge definitions reject year zero and trailing newlines',async()=>{
  const {validateDefinition}=await import('./contracts.ts');
  const cases=JSON.parse(readFileSync(new URL('../fixtures/synthetic/invalid-definitions.json',import.meta.url),'utf8'));
  for(const {definition:name,value} of cases)
    assert.equal(validateDefinition(name,value),false,`${name} must reject edge value`);
});


test('shared signed invalid commands reject year zero despite valid hash',async()=>{
  const {validateCommand,payloadHash}=await import('./contracts.ts');
  const values=JSON.parse(readFileSync(new URL('../fixtures/synthetic/invalid-commands.json',import.meta.url),'utf8'));
  for(const value of values){
    assert.equal(payloadHash(value),value.payload_hash);
    assert.equal(validateCommand(value),false);
  }
});
