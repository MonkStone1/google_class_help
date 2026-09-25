const fs = require('node:fs');
const path = require('node:path');

const dir = 'C:/Users/admin/docs/audits/google-class-help-2026-09-25';
try {
  const read = (f) => JSON.parse(fs.readFileSync(path.join(dir, f), 'utf8'));
  const confirmed = [read('finding-01.json'), read('finding-02.json'), read('finding-03.json')];
  const needsPairs = [
    ['nv-01.json', 'nv-meta-01.json'],
    ['nv-02.json', 'nv-meta-02.json'],
    ['nv-03.json', 'nv-meta-03.json']
  ];
  const needs = needsPairs.map(([b, m]) => ({ ...read(m), ...read(b), verdict: 'needs_validation' }));
  const rejected = { ...read('rj-meta.json'), ...read('rj-01.json') };
  const findings = [...confirmed, ...needs, rejected];

  // sort lexicographically by fingerprint
  findings.sort((a, b) => a.fingerprint.localeCompare(b.fingerprint));

  fs.writeFileSync(path.join(dir, 'findings.json'), JSON.stringify(findings, null, 2), 'utf8');
  console.log('SUCCESS: wrote findings.json with count =', findings.length);
} catch (err) {
  console.error('ERROR in build-findings:', err);
}
