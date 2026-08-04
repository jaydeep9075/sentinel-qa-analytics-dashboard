import { NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

export async function GET() {
  try {
    // Data directory sits outside the Next.js app root when running from a
    // checkout (frontend/ -> ../data). In Docker the frontend container has
    // no repo root above it, so SENTINEL_DATA_DIR points straight at the
    // mounted data volume - same env var scripts/generate-builds-json.js
    // already honours.
    const dataDir = process.env.SENTINEL_DATA_DIR || path.join(process.cwd(), '../data');
    console.log('Looking for data at:', dataDir);

    if (!fs.existsSync(dataDir)) {
      return NextResponse.json({ error: 'Data directory not found' }, { status: 404 });
    }

    const entries = fs.readdirSync(dataDir, { withFileTypes: true });
    // Two kinds of build folders end up here:
    //  - ingestion_YYYYMMDD_HHMMSS  (Allure ingestion via universal_ingester)
    //  - run_<hex>                  (finalized live-execution run, see
    //                                services/finalize/job.py - it deliberately
    //                                writes into the same data/ layout so it
    //                                shows up as just another build here)
    // Match strictly (not a bare prefix check) so stray/manual debug folders
    // like "ingestion_refactor_test" don't get picked up as real builds.
    const buildFolderPattern = /^(ingestion_\d{8}_\d{6}|run_[0-9a-f]{8,})$/;
    const ingestionFolders = entries.filter(
      (entry) => entry.isDirectory() && buildFolderPattern.test(entry.name)
    );

    const builds = [];

    for (const folder of ingestionFolders) {
      const summaryPath = path.join(dataDir, folder.name, 'summary.json');
      if (fs.existsSync(summaryPath)) {
        try {
          const content = fs.readFileSync(summaryPath, 'utf8');
          const data = JSON.parse(content);
          builds.push(data);
        } catch (err) {
          console.error(`Error parsing summary in ${folder.name}`, err);
        }
      }
    }

    builds.sort((a, b) => new Date(b.ingested_at).getTime() - new Date(a.ingested_at).getTime());

    return NextResponse.json({ builds });
  } catch (error) {
    console.error('Error in builds API:', error);
    return NextResponse.json({ error: 'Failed to load builds' }, { status: 500 });
  }
}