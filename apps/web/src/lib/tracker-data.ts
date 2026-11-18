import 'server-only';
import {cache} from 'react';
import type {TrackerData} from '@industrial/shared';
import policy from '../../../../config/public-display.json';
import fixtures from '../../../../packages/shared/fixtures/issues.json';
import {projectTrackerFixtures, projectTrackerMilestone, trackerData} from '../../../../packages/shared/tracker/projection';

export const getTrackerData = cache(async (): Promise<TrackerData> => {
  if (process.env.DATA_MODE === 'fixture') return projectTrackerFixtures(fixtures);

  const {PrismaClient} = await import('@industrial/db');
  const db = new PrismaClient();
  try {
    const records = await db.trackerMilestone.findMany({
      select: {
        id: true,
        projectId: true,
        revisions: {
          orderBy: {revision: 'desc'},
          take: 1,
          select: {
            issueHash: true, storyId: true, stage: true, withdrawn: true,
            issue: {select: {id: true, slug: true, state: true, validated: true, content: true}},
            evidence: {select: {
              sourceKey: true, kind: true, publisher: true, canonicalUrl: true, publishedAt: true, eventAt: true, sourceTimezone: true,
            }},
            companies: {select: {companyId: true}},
            technologies: {select: {technologyId: true}},
          },
        },
      },
    });
    return trackerData(records.flatMap(({id, projectId, revisions}) => {
      const projected = projectTrackerMilestone(id, projectId, revisions[0], policy);
      return projected ? [projected] : [];
    }));
  } finally {
    await db.$disconnect();
  }
});
