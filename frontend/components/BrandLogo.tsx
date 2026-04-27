"use client";

interface BrandLogoProps {
  className?: string;
}

export default function BrandLogo({ className = "" }: BrandLogoProps) {
  return (
    <div
      className={`inline-flex items-center justify-center rounded-lg bg-white px-2.5 py-1.5 font-mono text-base font-bold leading-none shadow-sm ${className}`}
      aria-label="Sentinel logo"
    >
      <span className="text-emerald-500">&lt;</span>
      <span className="text-black">/</span>
      <span className="text-emerald-500">&gt;</span>
    </div>
  );
}
