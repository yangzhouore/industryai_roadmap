const assert = require('node:assert/strict');
const {execFileSync} = require('node:child_process');
const fs = require('node:fs');
const path = require('node:path');
const {test} = require('node:test');
const {PrismaClient} = require('@prisma/client');

test('fixture seed preserves edition count and content across replay', {
  skip: !process.env.DATABASE_URL && 'DATABASE_URL required for PostgreSQL integration',
}, async () => {
  const issues = JSON.parse(fs.readFileSync(path.join(__dirname, '../shared/fixtures/issues.json'), 'utf8'));
  const db = new PrismaClient();
  try {
    execFileSync(process.execPath, [path.join(__dirname, 'seed.js')], {stdio:'pipe'});
    const first = await db.digestIssue.findMany({where:{id:{in:issues.map(i => i.id)}},orderBy:{id:'asc'}});
    execFileSync(process.execPath, [path.join(__dirname, 'seed.js')], {stdio:'pipe'});
    const second = await db.digestIssue.findMany({where:{id:{in:issues.map(i => i.id)}},orderBy:{id:'asc'}});
    assert.equal(first.length, issues.length);
    assert.deepEqual(second, first);
    for (const row of second) {
      const fixture = issues.find(i => i.id === row.id);
      assert.equal(row.state, 'published');
      assert.equal(row.validated, true);
      assert.deepEqual(row.content, fixture);
    }
  } finally {
    await db.$disconnect();
  }
});
