# Why We Built Live Execution This Way

A plain-English explanation for anyone who wasn't in the design conversations — what problem this solves, why each choice was made, and how it actually behaves. No jargon assumed.

## The problem in one sentence

Today, you only find out how your tests went **after** they finish — someone runs a report-generation step, then looks at a dashboard. There's no way to watch a run happen, and nothing tells the dashboard "a run just started."

## What we wanted

Add a real Playwright plugin so that the moment someone types `playwright test` — on their laptop or in CI, doesn't matter — Sentinel notices immediately, shows every test flipping from running → passed/failed live, streams the console logs as they happen, and then, once the run ends, turns into a completely normal historical report. No extra commands, no manual upload.

## The three decisions that mattered, and why

### 1. Where does "live" data live while a test is running?

**Decision: a small local database (SQLite) just for in-progress runs, separate from the main database (LanceDB) that holds your permanent history.**

Think of it like a whiteboard vs. a filing cabinet. While a game is in progress, you want the scoreboard updated instantly — you don't file it away permanently point by point, that's slow and pointless. You just update the board. Only when the game ends do you write the final score into the permanent record.

- The "whiteboard" (SQLite) is built for exactly this: lots of tiny, fast updates, and if the backend crashes mid-run, it survives — nothing is lost.
- The "filing cabinet" (LanceDB) is built for exactly the opposite: writing final, permanent results in one clean batch, and being fast to search later (including for AI).

We tried "just keep it all in memory, no database at all" first. It's faster, but it means if the backend restarts while a test is running, that run's live data vanishes — bad for something you're selling as reliable. SQLite costs almost nothing (it's a single file, not a server you have to run or manage — same idea as a Word document, not like installing MySQL) and buys real crash-safety. That trade was worth it.

### 2. How does the dashboard find out something changed, instantly?

**Decision: the backend pushes updates to the browser (like a live sports score ticker), instead of the browser repeatedly asking "anything new?" (like refreshing a page every few seconds).**

Constantly asking is wasteful and always a little bit behind. Pushing means the dashboard finds out the instant something happens — because the same code that saves the update also immediately hands it off to anyone watching.

We specifically chose the simplest kind of "push" that exists (called Server-Sent Events) instead of a fancier two-way connection (WebSocket), because we only ever need to push data in one direction — server to browser. The test runner never needs to talk back over that same channel. Simpler tool, same result, fewer things that can break.

### 3. What actually gets saved forever, and when?

**Decision: while the run is happening, nothing is "final." The moment it ends, everything about that run gets bundled into one file and handed to the exact same process that already turns an uploaded report into a permanent record — nothing new to build or maintain for that part.**

This is the part people ask about most: "does this need AI parsing before it's saved?" Short answer: mostly no.

- Saving the actual results (which tests passed/failed, how long they took) is just filling in a table — no AI involved, instant.
- Making those results *searchable by the AI chat* ("find me failures related to timeouts") does need one extra step — turning the important text (error messages, logs) into a format the AI can search by meaning, not just exact words. That step happens a few seconds later, in the background, and never makes you wait for it.

So: the report itself is ready immediately. The "ask the AI about this run" ability is ready moments later. Nobody notices the difference in practice.

## What screenshots and video get kept

Same instinct as before: don't hoard everything, keep what's useful.
- **Screenshots:** only when a test fails — that's the moment you actually need to see what went wrong.
- **Video:** one final video per test, not a pile of frames.

## Does this work the same locally and in CI?

Yes, on purpose. The plugin doesn't know or care whether it's running on your laptop or inside a CI pipeline — it just sends the same messages to the same place either way. The only difference is it automatically notices *which* CI system it's in (GitHub Actions, Jenkins, etc.) and tags the run with the branch/commit/build link, using the same information those systems already publish. There's no separate "CI mode" to build or maintain.

## Does this slow down my tests?

No. The plugin never waits around for Sentinel to respond before letting your test continue, and if Sentinel is unreachable entirely, the plugin just quietly stops reporting instead of failing your tests. Reporting can break; your test run can't.

## Proof, not just theory

We didn't just design this — we ran it against a real, large, already-sophisticated test repository (`sfcc-qa-automation`, with its own custom logger, Allure, and ReportPortal already wired in) and watched real console output and step timings stream into Sentinel live while a real login test ran against a real storefront. It coexisted cleanly with everything already there. Full details in `LIVE_EXECUTION_ARCHITECTURE.md` if you want the deeper technical reasoning.
