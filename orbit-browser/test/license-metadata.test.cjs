/* Regression harness for the proprietary license metadata.
 *
 * The repository is All Rights Reserved / UNLICENSED (see LICENSE and
 * pyproject.toml). A stale "license": "MIT" in package-lock.json re-opened
 * the licensing inconsistency flagged by the external audit, so this test
 * pins the pieces a future `npm install` / dependency bump could regress:
 *   - package.json declares UNLICENSED
 *   - package-lock.json root package records UNLICENSED
 *   - the lockfile root block stays in sync with the manifest identity
 *
 * Run: node orbit-browser/test/license-metadata.test.cjs
 */

const fs = require('fs');
const path = require('path');

let checks = 0;
let failures = 0;

function ok(cond, label) {
  checks += 1;
  if (cond) console.log('  PASS  ' + label);
  else { failures += 1; console.log('  FAIL  ' + label); }
}

console.log('license-metadata');

const pkg = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'package.json'), 'utf8'));
const lock = JSON.parse(fs.readFileSync(path.join(__dirname, '..', 'package-lock.json'), 'utf8'));
const root = (lock.packages && lock.packages['']) || {};

ok(pkg.license === 'UNLICENSED',
  'package.json license is UNLICENSED (got ' + JSON.stringify(pkg.license) + ')');
ok(root.license === 'UNLICENSED',
  'package-lock.json root license is UNLICENSED (got ' + JSON.stringify(root.license) + ')');
ok(root.name === pkg.name, 'lockfile root name matches manifest (' + root.name + ')');
ok(root.version === pkg.version, 'lockfile root version matches manifest (' + root.version + ')');

console.log('\n' + (checks - failures) + '/' + checks + ' checks passed');
process.exit(failures === 0 ? 0 : 1);
