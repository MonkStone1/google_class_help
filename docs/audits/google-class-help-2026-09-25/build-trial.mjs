import fs from 'node:fs';
import path from 'node:path';
const dir = 'C:/Users/admin/docs/audits/google-class-help-2026-09-25';
const read = (f) => JSON.parse(fs.readFileSync(path.join(dir, f), 'utf8'));
const confirmed = [read('finding-01.json'), read('finding-02.json'), read('finding-03.json')];
const withConditions = confirmed.map((f) => {
  const copy = {...f};
  if (!Array.isArray(copy.conditions)) copy.conditions = [];
  delete copy.conditions;
  return copy;
});
const needsPairs = [
  ['nv-01.json', 'nv-meta-01.json'],
  ['nv-02.json', 'nv-meta-02.json'],
  ['nv-03.json', 'nv-meta-03.json']
];
const needs = needsPairs.map(([b, m]) => ({...read(m), ...read(b), verdict: 'needs_validation'}));
const rejected = {...read('rj-meta.json'), ...read('rj-01.json')};
const findings = [...withConditions, ...needs, rejected];
fs.writeFileSync(path.join(dir, 'findings.json'), JSON.stringify(findings, null, 2));
console.log('wrote findings=' + findings.length);
