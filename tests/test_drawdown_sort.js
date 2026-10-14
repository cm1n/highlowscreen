const fs = require('node:fs');
const path = require('node:path');
const assert = require('node:assert/strict');
const test = require('node:test');

// Execute the comparator shipped in the dashboard, without duplicating its logic.
const source = fs.readFileSync(path.join(__dirname, '../tools/high_low_scan.py'), 'utf8');
const body = source.match(/r\.sort\(\(a,b\)=>\{([\s\S]*?)\}\);/)[1];
const compare = new Function('st', 'a', 'b', body);
const rows = [
  {dt:'20261014', t:'recent', dd3:-10, dd52:-20},
  {dt:'20261014', t:'missing', dd3:null, dd52:null},
  {dt:'20261013', t:'deep', dd3:-50, dd52:-60},
  {dt:'20261012', t:'old_missing', dd3:null, dd52:null},
];

for (const key of ['dd3', 'dd52']) {
  test(`all-period ${key} sorts by decline before date and puts missing values last`, () => {
    const st = {date:'ALL', k:key, dir:1};
    assert.deepEqual([...rows].sort((a,b)=>compare(st,a,b)).map(x=>x.t),
      ['deep','recent','missing','old_missing']);
    st.dir = -1;
    assert.deepEqual([...rows].sort((a,b)=>compare(st,a,b)).map(x=>x.t),
      ['recent','deep','missing','old_missing']);
  });
}
