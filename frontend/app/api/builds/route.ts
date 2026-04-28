import { NextResponse } from 'next/server';
import fs from 'fs';
import path from 'path';

export async function GET() {
  try {
    // ✅ Correct path: data directory is outside the Next.js app root
    const dataDir = path.join(process.cwd(), '../data');
    console.log('Looking for data at:', dataDir);

    if (!fs.existsSync(dataDir)) {
      return NextResponse.json({ error: 'Data directory not found' }, { status: 404 });
    }

    const entries = fs.readdirSync(dataDir, { withFileTypes: true });
    const ingestionFolders = entries.filter(
      (entry) => entry.isDirectory() && entry.name.startsWith('ingestion_')
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