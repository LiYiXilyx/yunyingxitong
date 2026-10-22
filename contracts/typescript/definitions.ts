import { readFileSync } from 'node:fs';
import { validateDefinition } from './contracts.ts';
const values: [string,unknown][]=JSON.parse(readFileSync(0,'utf8'));
process.stdout.write(JSON.stringify(values.map(([name,value])=>validateDefinition(name,value))));
