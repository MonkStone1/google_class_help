const {validateDocument} = require('d:/Documents/google_class_help/.agents/skills/security-audit/validate-findings.cjs');
const fs = require('node:fs');
const findings = JSON.parse(fs.readFileSync('C:/Users/admin/docs/audits/google-class-help-2026-09-25/findings.json','utf8'));
const schema = JSON.parse(fs.readFileSync('d:/Documents/google_class_help/.agents/skills/security-audit/report-schema.json','utf8'));
const errors = validateDocument(findings, schema);
console.log('TOTAL errors=' + errors.length);
findings.forEach((f, i) => {
  console.log(`[${i}] verdict=${f.verdict} fingerprint=${f.fingerprint} hasConditions=${!!f.conditions} hasTrace=${!!f.trace}`);
});
for (const e of errors) console.log('ERR:', e);

