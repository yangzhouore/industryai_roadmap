const {PrismaClient} = require('@prisma/client');
const fs = require('node:fs');
const path = require('node:path');
const db = new PrismaClient();
async function main() {
  const issues = JSON.parse(fs.readFileSync(path.join(__dirname, '../shared/fixtures/issues.json'), 'utf8'));
  for (const issue of issues) {
    if (!issue.synthetic || !issue.validated || issue.state !== 'published' || issue.stories.some(s => s.sourceIds.some(id => !issue.sources.some(x => x.id === id)))) throw new Error('Invalid fixture');
    const data = {slug:issue.slug,issueDate:issue.date,state:issue.state,validated:issue.validated,content:issue,publishedAt:new Date(issue.date+'T08:00:00Z')};
    await db.digestIssue.upsert({where:{id:issue.id},create:{id:issue.id,...data},update:data});
  }
  console.log(`Seeded ${issues.length} synthetic editions`);
}
main().catch(e=>{console.error(e.message);process.exitCode=1}).finally(()=>db.$disconnect());
