/* eslint-disable @typescript-eslint/no-require-imports */
const fs = require("node:fs");
const path = require("node:path");

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

const BUILD_FOLDER_PATTERN = /^(ingestion_\d{8}_\d{6}|run_[0-9a-f]{8,})$/;

function getSummaryFiles(rootDir) {
  if (!fs.existsSync(rootDir)) return [];

  const entries = fs.readdirSync(rootDir, { withFileTypes: true });
  return entries
    .filter((entry) => entry.isDirectory() && BUILD_FOLDER_PATTERN.test(entry.name))
    .map((folder) => path.join(rootDir, folder.name, 'summary.json'))
    .filter((summaryPath) => fs.existsSync(summaryPath));
}

function getCacheKey(summaryFiles) {
  const stats = summaryFiles
    .map((summaryPath) => {
      const stat = fs.statSync(summaryPath);
      return `${summaryPath}:${stat.mtimeMs}:${stat.size}`;
    })
    .sort();
  return stats.join('|');
}

if (fs.existsSync(dataDir)) {
  const summaryFiles = getSummaryFiles(dataDir);
  const nextCacheKey = getCacheKey(summaryFiles);

  if (fs.existsSync(outputPath)) {
    try {
      const existing = JSON.parse(fs.readFileSync(outputPath, 'utf8'));
      if (existing.cache_key === nextCacheKey) {
        console.log(`✅ Reused public/builds.json with ${existing.builds?.length ?? 0} builds (no changes)`);
        process.exit(0);
      }
    } catch {
      // If cache file is invalid, regenerate it below.
    }
  }

  for (const summaryPath of summaryFiles) {
    try {
      const content = fs.readFileSync(summaryPath, 'utf8');
      const data = JSON.parse(content);
      builds.push(data);
    } catch (err) {
      console.error(`Error parsing ${summaryPath}`, err);
    }
  }

  builds.sort((a, b) => new Date(b.ingested_at).getTime() - new Date(a.ingested_at).getTime());

  fs.writeFileSync(outputPath, JSON.stringify({ builds, cache_key: nextCacheKey }, null, 2));
  console.log(`✅ Generated public/builds.json with ${builds.length} builds`);
  process.exit(0);
}

fs.writeFileSync(outputPath, JSON.stringify({ builds, cache_key: '' }, null, 2));
console.log(`✅ Generated public/builds.json with ${builds.length} builds`);