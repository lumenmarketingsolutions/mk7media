"use client";

import { AnimatePresence, motion, useInView } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { AppIcon } from "./app-icons";

/* A "sample view" of the outcomes MK7 sells. Not a real client: numbers are illustrative,
   chosen to look like a healthy month for a brand we run. */

const LINE = [22, 26, 24, 31, 29, 35, 38, 36, 44, 47, 45, 53, 58, 55, 63, 69, 66, 74, 81, 79, 88];
const KPIS = [
  { icon: AppIcon.meta, label: "Return on ad spend", value: "4.8x", delta: "+0.9" },
  { icon: AppIcon.shopify, label: "Purchases", value: "1,284", delta: "+31%" },
  { icon: AppIcon.meta, label: "Leads", value: "3,912", delta: "+24%" },
  { icon: AppIcon.whatsapp, label: "WhatsApp chats", value: "2,406", delta: "+48%" },
  { icon: AppIcon.google, label: "Consults booked", value: "186", delta: "+19%" },
  { icon: AppIcon.shopify, label: "Add to carts", value: "9,870", delta: "+27%" },
];
const TOASTS = [
  { icon: AppIcon.shopify, title: "New order · $184.00", sub: "Shopify · just now" },
  { icon: AppIcon.whatsapp, title: "Chat to sale · $96.00", sub: "WhatsApp → Meta pixel" },
  { icon: AppIcon.google, title: "Consult booked · Thu 11:30", sub: "From Google search" },
  { icon: AppIcon.meta, title: "New lead · Sara K.", sub: "Meta lead form" },
];

function pathFrom(data: number[], w: number, h: number) {
  const max = Math.max(...data) * 1.08;
  const step = w / (data.length - 1);
  const pts = data.map((v, i) => [i * step, h - (v / max) * h] as const);
  let d = `M ${pts[0][0]} ${pts[0][1]}`;
  for (let i = 1; i < pts.length; i++) {
    const [x0, y0] = pts[i - 1];
    const [x1, y1] = pts[i];
    const cx = (x0 + x1) / 2;
    d += ` C ${cx} ${y0}, ${cx} ${y1}, ${x1} ${y1}`;
  }
  return { d, end: pts[pts.length - 1] };
}

/* Floating notification. Desktop: bottom right corner of the dashboard.
   Mobile: just under the rising end of the line, overlapping the graph a little. */
function Toasts({ active, className }: { active: boolean; className: string }) {
  const [i, setI] = useState(-1);
  useEffect(() => {
    if (!active) return;
    const first = setTimeout(() => setI(0), 2600); // let the chart finish drawing first
    const t = setInterval(() => setI((x) => (x + 1) % TOASTS.length), 3800);
    return () => {
      clearTimeout(first);
      clearInterval(t);
    };
  }, [active]);
  const T = i >= 0 ? TOASTS[i] : null;
  return (
    <div className={`pointer-events-none absolute z-10 ${className}`}>
      <AnimatePresence mode="wait">
        {T && (
          <motion.div
            key={i}
            initial={{ opacity: 0, y: 10, filter: "blur(6px)" }}
            animate={{ opacity: 1, y: 0, filter: "blur(0px)" }}
            exit={{ opacity: 0, y: -6, filter: "blur(4px)", transition: { duration: 0.4, ease: [0.4, 0, 1, 1] } }}
            transition={{ duration: 0.6, ease: [0.16, 1, 0.3, 1] }}
            className="flex items-center gap-2 rounded-[8px] border border-white/10 py-1.5 pr-3 pl-1.5 whitespace-nowrap md:gap-2.5 md:py-2 md:pr-3.5 md:pl-2"
            style={{
              background: "rgba(22,22,27,0.88)",
              backdropFilter: "blur(14px)",
              WebkitBackdropFilter: "blur(14px)",
              boxShadow: "0 14px 28px -14px rgba(0,0,0,0.9)",
            }}
          >
            <span className="block size-5 shrink-0 md:size-6">
              <T.icon />
            </span>
            <span className="text-[10.5px] leading-snug md:text-[11.5px]">
              <span className="block text-text">{T.title}</span>
              <span className="block text-muted">{T.sub}</span>
            </span>
          </motion.div>
        )}
      </AnimatePresence>
    </div>
  );
}

const TICKER = [
  { icon: AppIcon.meta, t: "New lead", s: "Meta lead form" },
  { icon: AppIcon.shopify, t: "Order $212.00", s: "Shopify" },
  { icon: AppIcon.whatsapp, t: "Chat to sale $96.00", s: "WhatsApp" },
  { icon: AppIcon.google, t: "Consult booked", s: "Google search" },
  { icon: AppIcon.shopify, t: "Added to cart", s: "Shopify" },
  { icon: AppIcon.meta, t: "Purchase $148.00", s: "Meta ads" },
];

/* Slim one line ticker under the chart (desktop). */
function LiveTicker() {
  const row = (k: string) => (
    <div key={k} className="flex shrink-0 items-center gap-8 pr-8">
      {TICKER.map((x, i) => (
        <span key={i} className="flex items-center gap-2 text-[12px] whitespace-nowrap">
          <span className="block size-4">
            <x.icon />
          </span>
          <span className="text-text">{x.t}</span>
          <span className="text-faint">{x.s}</span>
        </span>
      ))}
    </div>
  );
  return (
    <div className="mt-auto hidden items-center gap-4 border-t border-white/[0.06] pt-5 md:flex">
      <span className="flex shrink-0 items-center gap-2 text-[11px] text-muted">
        <span className="relative flex size-1.5">
          <span className="absolute inset-0 rounded-full bg-signal" style={{ animation: "pulse-ring 1.8s ease-out infinite" }} />
          <span className="relative size-1.5 rounded-full bg-signal" />
        </span>
        Live
      </span>
      <div
        className="relative min-w-0 flex-1 overflow-hidden"
        style={{ maskImage: "linear-gradient(90deg, transparent, black 8%, black 92%, transparent)" }}
      >
        <div className="flex w-max" style={{ animation: "marquee 38s linear infinite" }}>
          {row("a")}
          {row("b")}
        </div>
      </div>
    </div>
  );
}

export function HeroDashboard() {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, margin: "-60px" });
  const W = 640;
  const H = 170;
  const { d, end } = pathFrom(LINE, W, H);

  return (
    <div ref={ref} className="relative">
      <div
        aria-hidden
        className="pointer-events-none absolute -top-20 left-1/2 h-44 w-[80%] -translate-x-1/2 rounded-[50%] opacity-70 blur-3xl"
        style={{ background: "radial-gradient(closest-side, rgba(185,167,255,0.30), transparent)" }}
      />
      <motion.div
        initial={{ opacity: 0, y: 24 }}
        animate={inView ? { opacity: 1, y: 0 } : {}}
        transition={{ duration: 0.9, ease: [0.16, 1, 0.3, 1] }}
        className="relative overflow-hidden rounded-[10px] border border-white/10"
        style={{ background: "linear-gradient(180deg,#121216 0%,#0B0B0E 100%)", boxShadow: "0 40px 80px -40px rgba(0,0,0,0.9)" }}
      >
        <div className="flex items-center justify-between border-b border-white/[0.06] px-4 py-3">
          <div className="flex items-center gap-1.5">
            <span className="size-2.5 rounded-full bg-white/10" />
            <span className="size-2.5 rounded-full bg-white/10" />
            <span className="size-2.5 rounded-full bg-white/10" />
          </div>
          <p className="text-[12px] text-muted">Growth overview · 30 days</p>
          <p className="text-[11px] text-faint">Sample</p>
        </div>

        <div className="grid md:grid-cols-[1.5fr_1fr]">
          <div className="relative min-w-0 border-white/[0.06] p-5 sm:p-7 md:flex md:flex-col md:border-r">
            <div className="flex flex-wrap items-end justify-between gap-2">
              <div>
                <p className="text-[12px] text-muted">Revenue from ads</p>
                <p className="mt-1.5 text-[30px] leading-none font-semibold tracking-[-0.04em] tabular-nums sm:text-[36px]">
                  $184,320
                </p>
              </div>
              <p className="text-[13px] text-growth">↑ 38% vs last month</p>
            </div>
            <svg viewBox={`0 0 ${W} ${H + 8}`} className="mt-6 h-auto w-full overflow-visible" aria-hidden>
              <defs>
                <linearGradient id="hd-fill" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="0%" stopColor="#B9A7FF" stopOpacity="0.22" />
                  <stop offset="100%" stopColor="#B9A7FF" stopOpacity="0" />
                </linearGradient>
              </defs>
              {[0.25, 0.5, 0.75].map((g) => (
                <line key={g} x1="0" x2={W} y1={H * g} y2={H * g} stroke="rgba(255,255,255,0.05)" />
              ))}
              <motion.path
                d={`${d} L ${W} ${H} L 0 ${H} Z`}
                fill="url(#hd-fill)"
                initial={{ opacity: 0 }}
                animate={inView ? { opacity: 1 } : {}}
                transition={{ duration: 1.2, delay: 0.9 }}
              />
              <motion.path
                d={d}
                fill="none"
                stroke="#B9A7FF"
                strokeWidth="2"
                strokeLinecap="round"
                initial={{ pathLength: 0 }}
                animate={inView ? { pathLength: 1 } : {}}
                transition={{ duration: 1.8, delay: 0.3, ease: [0.65, 0, 0.35, 1] }}
              />
              <motion.g initial={{ opacity: 0 }} animate={inView ? { opacity: 1 } : {}} transition={{ delay: 2, duration: 0.4 }}>
                <circle cx={end[0]} cy={end[1]} r="9" fill="#B9A7FF" opacity="0.2" />
                <circle cx={end[0]} cy={end[1]} r="4" fill="#E9E4FF" />
              </motion.g>
            </svg>
            <div className="mt-3 flex justify-between text-[11px] text-faint">
              <span>Oct 14</span>
              <span>Oct 28</span>
              <span>Nov 12</span>
            </div>
            <LiveTicker />
            <Toasts active={inView} className="right-4 bottom-6 md:hidden" />
          </div>

          <ul className="grid grid-cols-2 border-t border-white/[0.06] md:grid-cols-1 md:border-t-0">
            {KPIS.map((k, i) => (
              <motion.li
                key={k.label}
                initial={{ opacity: 0 }}
                animate={inView ? { opacity: 1 } : {}}
                transition={{ delay: 0.5 + i * 0.08, duration: 0.5 }}
                className={[
                  "items-center gap-3 border-white/[0.06] px-4 py-3.5 sm:px-6 md:border-r-0 md:border-b md:last:border-b-0",
                  i % 2 === 0 ? "border-r" : "",
                  i < 2 ? "border-b" : "",
                  i >= 4 ? "hidden md:flex" : "flex",
                ].join(" ")}
              >
                <span className="block size-6 shrink-0">
                  <k.icon />
                </span>
                <span className="min-w-0 flex-1">
                  <span className="block truncate text-[11.5px] text-muted">{k.label}</span>
                  <span className="mt-0.5 flex items-baseline gap-2">
                    <span className="text-[17px] font-semibold tracking-[-0.03em] tabular-nums">{k.value}</span>
                    <span className="text-[11px] text-growth">{k.delta}</span>
                  </span>
                </span>
              </motion.li>
            ))}
          </ul>
        </div>

        <Toasts active={inView} className="right-5 bottom-5 hidden md:block" />
      </motion.div>
    </div>
  );
}
