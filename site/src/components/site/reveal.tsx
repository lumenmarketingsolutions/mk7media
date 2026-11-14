"use client";

import { useEffect, useRef, useState } from "react";
import { cn } from "@/lib/utils";

type Part = string | { t: string; accent?: boolean };

/* One shared IntersectionObserver for the whole page. Elements reveal once, then are forgotten. */
const callbacks = new WeakMap<Element, () => void>();
let io: IntersectionObserver | null = null;
function observe(el: Element, cb: () => void) {
  if (typeof IntersectionObserver === "undefined") return cb();
  if (!io) {
    io = new IntersectionObserver(
      (entries) => {
        for (const e of entries) {
          if (!e.isIntersecting) continue;
          callbacks.get(e.target)?.();
          callbacks.delete(e.target);
          io!.unobserve(e.target);
        }
      },
      { rootMargin: "0px 0px -60px 0px" },
    );
  }
  callbacks.set(el, cb);
  io.observe(el);
  return () => {
    callbacks.delete(el);
    io?.unobserve(el);
  };
}

function useShown<T extends Element>(enabled = true) {
  const ref = useRef<T>(null);
  const [shown, setShown] = useState(!enabled);
  useEffect(() => {
    if (!enabled || !ref.current) return;
    return observe(ref.current, () => setShown(true));
  }, [enabled]);
  return { ref, shown };
}

/* Word by word blur-in headline. Pure CSS animation; real text stays in the HTML for SEO.
   onView=false (first screen) plays immediately without waiting for JavaScript. */
export function RevealHeading({
  parts,
  as = "h2",
  className,
  delay = 0,
  onView = true,
}: {
  parts: Part[];
  as?: "h1" | "h2" | "h3";
  className?: string;
  delay?: number;
  onView?: boolean;
}) {
  const words: { w: string; accent: boolean; br: boolean }[] = [];
  for (const p of parts) {
    const t = typeof p === "string" ? p : p.t;
    const accent = typeof p !== "string" && !!p.accent;
    if (t === "\n") {
      words.push({ w: "", accent: false, br: true });
      continue;
    }
    t.split(/\s+/)
      .filter(Boolean)
      .forEach((w) => words.push({ w, accent, br: false }));
  }
  const plain = parts.map((p) => (typeof p === "string" ? p : p.t)).join(" ").replace(/\s*\n\s*/g, " ");
  const { ref, shown } = useShown<HTMLHeadingElement>(onView);
  const Tag = as;
  let n = 0;

  return (
    <Tag ref={ref} className={cn(className)} data-in={shown ? "" : undefined}>
      <span className="sr-only">{plain}</span>
      <span aria-hidden>
        {words.map((x, i) =>
          x.br ? (
            <br key={i} />
          ) : (
            <span
              key={i}
              className={cn("word-in inline-block whitespace-pre", x.accent && "text-brand")}
              style={{ animationDelay: `${delay + 0.055 * n++}s` }}
            >
              {x.w + " "}
            </span>
          ),
        )}
      </span>
    </Tag>
  );
}

/* Fade and rise into view. Pure CSS; `instant` plays right away (first screen). */
export function FadeUp({
  children,
  delay = 0,
  className,
  instant,
}: {
  children: React.ReactNode;
  delay?: number;
  className?: string;
  instant?: boolean;
}) {
  const { ref, shown } = useShown<HTMLDivElement>(!instant);
  return (
    <div ref={ref} className={cn("fade-in-up", className)} data-in={shown ? "" : undefined} style={{ animationDelay: `${delay}s` }}>
      {children}
    </div>
  );
}
