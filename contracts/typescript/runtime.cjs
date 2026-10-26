const {createHash}=require('node:crypto');
const {readFileSync}=require('node:fs');
const path=require('node:path');
const Ajv2020=require('ajv/dist/2020.js').default;
const addFormats=require('ajv-formats');
const schema=JSON.parse(readFileSync(path.join(__dirname,'../ops-v1.schema.json'),'utf8'));
const ajv=new Ajv2020({strict:true,allErrors:true,coerceTypes:false});addFormats(ajv);const validate=ajv.compile(schema);
function canonical(value) {
  if(value===null || typeof value==='boolean') return JSON.stringify(value);
  if(typeof value==='string') {
    if(/[\uD800-\uDBFF](?![\uDC00-\uDFFF])|(?<![\uD800-\uDBFF])[\uDC00-\uDFFF]/u.test(value)) throw new Error('invalid Unicode');
    return JSON.stringify(value);
  }
  if(Array.isArray(value)) return '['+value.map(canonical).join(',')+']';
  if(typeof value==='object') {
    const object=value;
    const keys=Object.keys(object).sort();
    if(keys.some(key=>/[^\x00-\x7F]/u.test(key))) throw new Error('object keys must be ASCII');
    return '{'+keys.map(key=>JSON.stringify(key)+':'+canonical(object[key])).join(',')+'}';
  }
  throw new Error('numeric values must be decimal strings');
}
function payloadHash(command) {
  if(!command || Array.isArray(command) || typeof command!=='object') throw new Error('command must be an object');
  canonical(command);
  const {payload_hash,...content}=command;
  return createHash('sha256').update(canonical(content),'utf8').digest('hex');
}
function validateCommand(value) {
  try {return !!validate(value) && payloadHash(value)===(value).payload_hash;} catch {return false;}
}

module.exports={payloadHash,validateCommand,canonical};
