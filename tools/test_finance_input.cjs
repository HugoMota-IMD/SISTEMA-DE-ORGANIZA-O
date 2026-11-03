'use strict';
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const source = fs.readFileSync(path.join(__dirname, '..', 'static', 'app.js'), 'utf8');
const begin = source.indexOf('function cents(value)');
const end = source.indexOf('\nfunction date(', begin);
assert.ok(begin >= 0 && end > begin, 'The tested parser is the browser parser.');
const parse = vm.runInNewContext(`(${source.slice(begin, end)})`);
const valid = [
  ['1.000', 100000], ['1.000,00', 100000], ['1000,00', 100000],
  ['333,33', 33333], ['1.000,50', 100050], ['1.234.567,89', 123456789],
  ['R$ 1.200,50', 120050], ['  1000,5  ', 100050], ['0,01', 1],
  ['1000', 100000], ['1000.00', 100000], ['333.33', 33333],
  ['-1.000,00', -100000], ['R$ -5,01', -501], ['0', 0],
];
const invalid = ['', '1.00,00', '12.34,56', '1,2,3', '1.2345', '1000,001',
  '1 000,00', 'R$ R$ 10,00', '1e3', 'NaN', 'Infinity', '--1,00',
  '1000000000000000000', '1,', ',50', '1.000.50'];
for (const [input, expected] of valid) assert.equal(parse(input), expected, input);
for (const input of invalid) assert.throws(() => parse(input), /valor|Valor/, input);
assert.equal(parse('100,50') * 4, 40200, 'Value per installment multiplies integer cents.');
assert.equal(parse('1.000'), 33334 + 33333 + 33333, 'R$ 1.000 is the exact total across three installments.');
console.log(`${valid.length + invalid.length + 2} browser money-input checks passed.`);