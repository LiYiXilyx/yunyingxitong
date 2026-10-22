import { readFileSync } from 'node:fs';
import { validateCommand } from './contracts.ts';
const values: unknown[]=JSON.parse(readFileSync(0,'utf8'));
process.stdout.write(JSON.stringify(values.map(validateCommand)));
