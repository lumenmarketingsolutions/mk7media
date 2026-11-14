"use client";

import * as React from "react";
import { cn } from "@/lib/utils";

/* Liquid glass, from the 21st.dev prompt: layered inset highlights + an SVG
   displacement filter on what sits behind the button. */
export function LiquidGlassButton({
  children,
  radius = 999,
  className,
  href,
}: {
  children: React.ReactNode;
  radius?: number;
  className?: string;
  href?: string;
}) {
  const Tag = href ? "a" : "button";
  return (
    <Tag
      href={href}
      className={cn(
        "relative inline-flex h-12 cursor-pointer items-center justify-center px-7 text-[14px] font-medium text-[#F2F2F3] transition-transform duration-300 hover:scale-[1.03]",
        className,
      )}
      style={{ borderRadius: radius }}
    >
      <span
        aria-hidden
        className="absolute inset-0 z-0"
        style={{
          borderRadius: radius,
          boxShadow:
            "0 0 8px rgba(0,0,0,0.03), 0 2px 6px rgba(0,0,0,0.08), inset 3px 3px 0.5px -3.5px rgba(255,255,255,0.09), inset -3px -3px 0.5px -3.5px rgba(255,255,255,0.85), inset 1px 1px 1px -0.5px rgba(255,255,255,0.6), inset -1px -1px 1px -0.5px rgba(255,255,255,0.6), inset 0 0 6px 6px rgba(255,255,255,0.12), inset 0 0 2px 2px rgba(255,255,255,0.06), 0 0 12px rgba(0,0,0,0.15)",
        }}
      />
      <span
        aria-hidden
        className="absolute inset-0 -z-10 overflow-hidden"
        style={{ borderRadius: radius, backdropFilter: 'url("#mk7-glass")' }}
      />
      <span className="relative z-10">{children}</span>
    </Tag>
  );
}

export function GlassFilterDefs() {
  return (
    <svg className="absolute size-0" aria-hidden>
      <defs>
        <filter id="mk7-glass" x="0%" y="0%" width="100%" height="100%" colorInterpolationFilters="sRGB">
          <feTurbulence type="fractalNoise" baseFrequency="0.05 0.05" numOctaves="1" seed="1" result="t" />
          <feGaussianBlur in="t" stdDeviation="2" result="b" />
          <feDisplacementMap in="SourceGraphic" in2="b" scale="70" xChannelSelector="R" yChannelSelector="B" result="d" />
          <feGaussianBlur in="d" stdDeviation="4" result="f" />
          <feComposite in="f" in2="f" operator="over" />
        </filter>
      </defs>
    </svg>
  );
}

/* Brushed metal frame button ("MetalButton default" from the same prompt). */
export function MetalButton({ children, radius = 8 }: { children: React.ReactNode; radius?: number }) {
  const [p, setP] = React.useState(false);
  return (
    <div
      className="relative inline-flex p-[1.25px] transition-all duration-200"
      style={{
        borderRadius: radius,
        background: "linear-gradient(180deg,#000,#A0A0A0)",
        transform: p ? "translateY(2px) scale(0.99)" : undefined,
        boxShadow: p ? "0 1px 2px rgba(0,0,0,.15)" : "0 3px 8px rgba(0,0,0,.25)",
      }}
    >
      <div
        className="absolute inset-[1px]"
        style={{ borderRadius: radius, background: "linear-gradient(180deg,#FAFAFA,#3E3E3E,#E5E5E5)" }}
      />
      <button
        onMouseDown={() => setP(true)}
        onMouseUp={() => setP(false)}
        onMouseLeave={() => setP(false)}
        className="relative z-10 m-[1px] inline-flex h-11 cursor-pointer items-center px-6 text-[14px] font-semibold text-white [text-shadow:0_-1px_0_rgb(80_80_80)]"
        style={{ borderRadius: Math.max(0, radius - 2), background: "linear-gradient(180deg,#B9B9B9,#969696)" }}
      >
        {children}
      </button>
    </div>
  );
}

/* Silver solid: the palette B action color, flat and quiet. */
export function SilverButton({ children, radius = 6 }: { children: React.ReactNode; radius?: number }) {
  return (
    <button
      className="inline-flex h-12 cursor-pointer items-center px-6 text-[14px] font-medium text-[#09090B] transition hover:brightness-95"
      style={{
        borderRadius: radius,
        background: "linear-gradient(180deg,#FFFFFF 0%,#DCDCE1 100%)",
        boxShadow: "inset 0 1px 0 rgba(255,255,255,0.9), 0 10px 24px -12px rgba(255,255,255,0.25)",
      }}
    >
      {children}
    </button>
  );
}
