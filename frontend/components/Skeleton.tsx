export default function Skeleton({ className = "" }: { className?: string }) {
  return (
    <div
      className={`animate-pulse rounded-lg bg-slate-200 dark:bg-white/[0.06] ${className}`}
    />
  );
}

/** A handful of pulsing bars standing in for a table/card grid while data
 * loads - replaces a bare "Loading…" string, which reads as a stall rather
 * than progress. */
export function SkeletonRows({ count = 4 }: { count?: number }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: count }).map((_, i) => (
        <Skeleton key={i} className="h-12 w-full" />
      ))}
    </div>
  );
}
