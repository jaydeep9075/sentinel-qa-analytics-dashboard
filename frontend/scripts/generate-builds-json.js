import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const repoRoot = path.resolve(__dirname, "../..");

// Prefer env override; otherwise use project-relative data directory.
const dataDir = process.env.SENTINEL_DATA_DIR || path.join(repoRoot, "data");
const publicDir = path.join(process.cwd(), 'public');
const outputPath = path.join(publicDir, 'builds.json');

// Ensure public directory exists
if (!fs.existsSync(publicDir)) {
  fs.mkdirSync(publicDir, { recursive: true });
}

const builds = [];

if (fs.existsSync(dataDir)) {
  const entries = fs.readdirSync(dataDir, { withFileTypes: true });
  const ingestionFolders = entries.filter(
    (entry) => entry.isDirectory() && entry.name.startsWith('ingestion_')
  );

  for (const folder of ingestionFolders) {
    const summaryPath = path.join(dataDir, folder.name, 'summary.json');
    if (fs.existsSync(summaryPath)) {
      try {
        const content = fs.readFileSync(summaryPath, 'utf8');
        const data = JSON.parse(content);
        builds.push(data);
      } catch (err) {
        console.error(`Error parsing ${folder.name}`, err);
      }
    }
  }

  builds.sort((a, b) => new Date(b.ingested_at).getTime() - new Date(a.ingested_at).getTime());
}

fs.writeFileSync(outputPath, JSON.stringify({ builds }, null, 2));
console.log(`✅ Generated public/builds.json with ${builds.length} builds`);