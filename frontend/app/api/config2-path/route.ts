import { NextResponse } from "next/server";
import fs from "fs";
import path from "path";

const CONFIG2_PATH = path.join(process.cwd(), "../config2.json");

type Config2Shape = {
  sources?: Array<{ type?: string; path?: string; [key: string]: unknown }>;
  [key: string]: unknown;
};

export async function GET() {
  try {
    if (!fs.existsSync(CONFIG2_PATH)) {
      return NextResponse.json({ error: "config2.json not found" }, { status: 404 });
    }

    const raw = fs.readFileSync(CONFIG2_PATH, "utf8");
    const parsed: Config2Shape = JSON.parse(raw);
    const currentPath = parsed.sources?.[0]?.path ?? "";

    return NextResponse.json({ path: currentPath });
  } catch (error) {
    console.error("Failed to read config2.json path", error);
    return NextResponse.json({ error: "Failed to read config2 path" }, { status: 500 });
  }
}

export async function PUT(req: Request) {
  try {
    const body = await req.json();
    const nextPath = String(body?.path ?? "").trim();

    if (!nextPath) {
      return NextResponse.json({ error: "Path is required" }, { status: 400 });
    }

    if (!fs.existsSync(CONFIG2_PATH)) {
      return NextResponse.json({ error: "config2.json not found" }, { status: 404 });
    }

    const raw = fs.readFileSync(CONFIG2_PATH, "utf8");
    const parsed: Config2Shape = JSON.parse(raw);

    if (!Array.isArray(parsed.sources) || parsed.sources.length === 0) {
      return NextResponse.json({ error: "Invalid config2.json sources" }, { status: 400 });
    }

    parsed.sources[0] = {
      ...parsed.sources[0],
      path: nextPath,
    };

    fs.writeFileSync(CONFIG2_PATH, JSON.stringify(parsed, null, 4), "utf8");
    return NextResponse.json({ success: true, path: nextPath });
  } catch (error) {
    console.error("Failed to update config2.json path", error);
    return NextResponse.json({ error: "Failed to update config2 path" }, { status: 500 });
  }
}
