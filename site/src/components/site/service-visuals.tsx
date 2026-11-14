"use client";

import { AnimatePresence, motion, useInView } from "motion/react";
import { useEffect, useRef, useState } from "react";
import { AppIcon } from "./app-icons";

const ease = [0.16, 1, 0.3, 1] as const;

function Frame({ children, title, className = "" }: { children: React.ReactNode; title: string; className?: string }) {
  return (
    <div
      className={`relative overflow-hidden rounded-[10px] border border-white/10 ${className}`}
      style={{ background: "linear-gradient(180deg,#121216 0%,#0B0B0E 100%)", boxShadow: "0 40px 80px -40px rgba(0,0,0,0.9)" }}
    >
      <div className="flex items-center justify-between border-b border-white/[0.06] px-4 py-3">
        <div className="flex gap-1.5">
          <span className="size-2.5 rounded-full bg-white/10" />
          <span className="size-2.5 rounded-full bg-white/10" />
          <span className="size-2.5 rounded-full bg-white/10" />
        </div>
        <p className="text-[12px] text-muted">{title}</p>
        <span className="w-10" />
      </div>
      {children}
    </div>
  );
}

function useView() {
  const ref = useRef<HTMLDivElement>(null);
  const inView = useInView(ref, { once: true, margin: "-40px" });
  return { ref, inView };
}

/* PAID ADS: objective picker that swaps the KPI */
function AdsVisual() {
  const goals = [
    { k: "Sales", v: "4.8x", l: "Return on ad spend", icon: AppIcon.meta, bars: [30, 42, 38, 55, 61, 70, 84, 100] },
    { k: "Leads", v: "$6.40", l: "Cost per lead", icon: AppIcon.meta, bars: [100, 86, 80, 71, 64, 58, 52, 47] },
    { k: "Search", v: "11.2%", l: "Click through rate", icon: AppIcon.google, bars: [40, 46, 52, 50, 61, 66, 72, 80] },
    { k: "Awareness", v: "1.9M", l: "People reached", icon: AppIcon.meta, bars: [20, 34, 45, 58, 66, 79, 88, 100] },
  ];
  const [i, setI] = useState(0);
  const { ref, inView } = useView();
  useEffect(() => {
    if (!inView) return;
    const t = setInterval(() => setI((x) => (x + 1) % goals.length), 3400);
    return () => clearInterval(t);
  }, [inView, goals.length]);
  const g = goals[i];
  return (
    <div ref={ref}>
      <Frame title="Campaign · objective">
        <div className="p-5 sm:p-7">
          <div className="flex gap-1.5 rounded-[8px] border border-white/[0.06] bg-white/[0.02] p-1">
            {goals.map((x, j) => (
              <button
                key={x.k}
                onClick={() => setI(j)}
                className={`flex-1 cursor-pointer rounded-[6px] py-2 text-[12px] transition-colors ${j === i ? "bg-white/[0.08] text-text" : "text-muted hover:text-text"}`}
              >
                {x.k}
              </button>
            ))}
          </div>
          <AnimatePresence mode="wait">
            <motion.div
              key={g.k}
              initial={{ opacity: 0, y: 8 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -6 }}
              transition={{ duration: 0.4, ease }}
            >
              <div className="mt-7 flex items-center gap-3">
                <span className="block size-7">
                  <g.icon />
                </span>
                <div>
                  <p className="text-[12px] text-muted">{g.l}</p>
                  <p className="text-[30px] leading-none font-semibold tracking-[-0.04em]">{g.v}</p>
                </div>
              </div>
              <div className="mt-7 flex h-28 items-end gap-2">
                {g.bars.map((b, j) => (
                  <motion.span
                    key={j}
                    initial={{ height: 0 }}
                    animate={{ height: `${b}%` }}
                    transition={{ duration: 0.6, delay: j * 0.04, ease }}
                    className="flex-1 rounded-t-[2px]"
                    style={{ background: j === g.bars.length - 1 ? "#B9A7FF" : "rgba(255,255,255,0.09)" }}
                  />
                ))}
              </div>
            </motion.div>
          </AnimatePresence>
        </div>
      </Frame>
    </div>
  );
}

/* ECOMMERCE: orders landing one by one as you scroll in */
function EcomVisual() {
  const orders = [
    { t: "New order · $146.00", s: "2 items · Beirut" },
    { t: "New order · $89.00", s: "Cash on delivery · Jounieh" },
    { t: "New order · $212.00", s: "Card · Dubai" },
    { t: "New order · $64.00", s: "WhatsApp order · Tripoli" },
  ];
  const { ref, inView } = useView();
  return (
    <div ref={ref} className="relative mx-auto max-w-[440px]">
      <div className="rounded-[10px] border border-white/10 bg-[#0e0e11] p-5 sm:p-6">
        <div className="flex items-baseline justify-between">
          <p className="text-[12px] text-muted">Today</p>
          <p className="text-[12px] text-growth">↑ 22% vs yesterday</p>
        </div>
        <p className="mt-1 text-[32px] leading-none font-semibold tracking-[-0.04em]">$3,284.50</p>
        <div className="mt-6 space-y-2.5">
          {orders.map((o, i) => (
            <motion.div
              key={o.t}
              initial={{ opacity: 0, y: 14, filter: "blur(6px)" }}
              animate={inView ? { opacity: 1, y: 0, filter: "blur(0px)" } : {}}
              transition={{ duration: 0.6, delay: 0.5 + i * 0.55, ease }}
              className="flex items-center gap-3 rounded-[8px] border border-white/[0.07] bg-white/[0.03] px-3 py-2.5"
            >
              <span className="block size-7 shrink-0">
                <AppIcon.shopify />
              </span>
              <span className="min-w-0 text-[12.5px] leading-snug">
                <span className="block text-text">{o.t}</span>
                <span className="block text-muted">{o.s}</span>
              </span>
              <span className="ml-auto text-[11px] text-faint">now</span>
            </motion.div>
          ))}
        </div>
      </div>
    </div>
  );
}

/* WHATSAPP: a chat that ends in a sale reported to Meta */
function WhatsAppVisual() {
  const msgs = [
    { me: false, t: "Hi! Is the black one still available?" },
    { me: true, t: "Yes, size M is in stock. Delivery tomorrow 👍" },
    { me: false, t: "Perfect, I'll take it" },
    { me: true, t: "Done! Order #2481 confirmed, $96 total." },
  ];
  const { ref, inView } = useView();
  return (
    <div ref={ref} className="relative mx-auto max-w-[400px]">
      <div className="overflow-hidden rounded-[22px] border border-white/10 bg-[#0b141a]">
        <div className="flex items-center gap-3 border-b border-white/[0.06] bg-[#111b21] px-4 py-3">
          <span className="block size-8">
            <AppIcon.whatsapp />
          </span>
          <div className="text-[12.5px] leading-tight">
            <p className="text-text">Your Store</p>
            <p className="text-muted">online</p>
          </div>
        </div>
        <div className="space-y-2 px-3.5 py-5">
          {msgs.map((m, i) => (
            <motion.div
              key={i}
              initial={{ opacity: 0, y: 10 }}
              animate={inView ? { opacity: 1, y: 0 } : {}}
              transition={{ duration: 0.45, delay: 0.4 + i * 0.7, ease }}
              className={`flex ${m.me ? "justify-end" : "justify-start"}`}
            >
              <span
                className="max-w-[78%] rounded-[10px] px-3 py-2 text-[13px] leading-snug"
                style={{ background: m.me ? "#005c4b" : "#202c33", color: "#e9edef" }}
              >
                {m.t}
              </span>
            </motion.div>
          ))}
        </div>
      </div>
      <motion.div
        initial={{ opacity: 0, y: 12, filter: "blur(6px)" }}
        animate={inView ? { opacity: 1, y: 0, filter: "blur(0px)" } : {}}
        transition={{ duration: 0.6, delay: 3.4, ease }}
        className="mx-auto -mt-5 flex w-fit items-center gap-2.5 rounded-[8px] border border-white/10 py-2 pr-3.5 pl-2 whitespace-nowrap"
        style={{ background: "rgba(22,22,27,0.92)", backdropFilter: "blur(14px)", boxShadow: "0 14px 28px -14px rgba(0,0,0,0.9)" }}
      >
        <span className="block size-6">
          <AppIcon.meta />
        </span>
        <span className="text-[12px] leading-snug">
          <span className="block text-text">Purchase $96.00 sent to Meta</span>
          <span className="block text-growth">Matched to ad · Summer drop</span>
        </span>
      </motion.div>
    </div>
  );
}

/* WEBSITES: browser with a speed score ring */
function WebVisual() {
  const { ref, inView } = useView();
  const r = 26;
  const c = 2 * Math.PI * r;
  return (
    <div ref={ref}>
      <Frame title="yourbrand.com">
        <div className="grid gap-6 p-5 sm:grid-cols-[1fr_auto] sm:p-7">
          <div className="space-y-3">
            <span className="block h-3 w-3/4 rounded-[2px] bg-white/25" />
            <span className="block h-3 w-1/2 rounded-[2px] bg-white/15" />
            <span className="block h-2 w-2/3 rounded-[2px] bg-white/[0.08]" />
            <span className="block h-2 w-3/5 rounded-[2px] bg-white/[0.08]" />
            <span className="mt-5 block h-9 w-36 rounded-full bg-white/85" />
            <div className="grid grid-cols-3 gap-2 pt-4">
              {[0, 1, 2].map((i) => (
                <span key={i} className="block aspect-[4/3] rounded-[4px] border border-white/[0.06] bg-white/[0.03]" />
              ))}
            </div>
          </div>
          <div className="flex items-center gap-4 sm:flex-col sm:justify-center">
            <svg width="72" height="72" viewBox="0 0 64 64" aria-hidden>
              <circle cx="32" cy="32" r={r} stroke="rgba(255,255,255,0.08)" strokeWidth="5" fill="none" />
              <motion.circle
                cx="32"
                cy="32"
                r={r}
                stroke="#6EE7A8"
                strokeWidth="5"
                fill="none"
                strokeLinecap="round"
                strokeDasharray={c}
                initial={{ strokeDashoffset: c }}
                animate={inView ? { strokeDashoffset: c * 0.02 } : {}}
                transition={{ duration: 1.6, delay: 0.4, ease }}
                transform="rotate(-90 32 32)"
              />
              <text x="32" y="37" textAnchor="middle" fontSize="15" fontWeight="700" fill="#F2F2F3">
                98
              </text>
            </svg>
            <p className="text-[12px] leading-snug text-muted sm:text-center">
              Speed score
              <br />
              on mobile
            </p>
          </div>
        </div>
      </Frame>
    </div>
  );
}

/* AUTOMATION: a flow that lights up step by step */
function AutomationVisual() {
  const nodes = [
    { t: "New lead", s: "Website form", icon: AppIcon.meta },
    { t: "Added to CRM", s: "Tagged and scored", icon: AppIcon.highlevel },
    { t: "WhatsApp welcome", s: "Sent in 4 seconds", icon: AppIcon.whatsapp },
    { t: "Call booked", s: "Thursday 11:30", icon: AppIcon.google },
  ];
  const { ref, inView } = useView();
  const [lit, setLit] = useState(-1);
  useEffect(() => {
    if (!inView) return;
    let n = -1;
    const t = setInterval(() => {
      n = n + 1 > nodes.length ? -1 : n + 1;
      setLit(n);
    }, 900);
    return () => clearInterval(t);
  }, [inView, nodes.length]);
  return (
    <div ref={ref} className="mx-auto max-w-[420px]">
      {nodes.map((n, i) => (
        <div key={n.t}>
          <div
            className="flex items-center gap-3 rounded-[8px] border px-3.5 py-3 transition-all duration-500"
            style={{
              borderColor: i <= lit ? "rgba(185,167,255,0.35)" : "rgba(255,255,255,0.07)",
              background: i <= lit ? "rgba(185,167,255,0.06)" : "rgba(255,255,255,0.02)",
            }}
          >
            <span className="block size-7 shrink-0">
              <n.icon />
            </span>
            <span className="text-[13px] leading-snug">
              <span className="block text-text">{n.t}</span>
              <span className="block text-muted">{n.s}</span>
            </span>
            <span className="ml-auto text-[12px] transition-colors duration-500" style={{ color: i <= lit ? "#6EE7A8" : "#5c5c66" }}>
              {i <= lit ? "Done" : "Waiting"}
            </span>
          </div>
          {i < nodes.length - 1 && (
            <span
              className="mx-auto block h-5 w-px transition-colors duration-500"
              style={{ background: i < lit ? "rgba(185,167,255,0.6)" : "rgba(255,255,255,0.08)" }}
            />
          )}
        </div>
      ))}
    </div>
  );
}

/* CRM: pipeline board */
function CrmVisual() {
  const cols = [
    { n: "New", c: ["Cedar Clinic", "Nova Studio", "Atlas Group"] },
    { n: "Call booked", c: ["Harbor Legal", "Pine & Co"] },
    { n: "Proposal", c: ["Vertex B2B"] },
    { n: "Won", c: ["Lumen Dental", "Orbit Realty"] },
  ];
  const { ref, inView } = useView();
  return (
    <div ref={ref}>
      <Frame title="Pipeline · this month">
        <div className="grid grid-cols-2 gap-3 p-4 sm:grid-cols-4 sm:p-6">
          {cols.map((col, ci) => (
            <div key={col.n}>
              <p className="mb-2.5 flex items-center justify-between text-[11px] text-muted">
                {col.n}
                <span className="text-faint">{col.c.length}</span>
              </p>
              <div className="space-y-2">
                {col.c.map((c, i) => (
                  <motion.div
                    key={c}
                    initial={{ opacity: 0, y: 8 }}
                    animate={inView ? { opacity: 1, y: 0 } : {}}
                    transition={{ duration: 0.45, delay: 0.3 + ci * 0.2 + i * 0.1, ease }}
                    className="rounded-[6px] border px-2.5 py-2 text-[12px]"
                    style={{
                      borderColor: col.n === "Won" ? "rgba(110,231,168,0.3)" : "rgba(255,255,255,0.07)",
                      background: col.n === "Won" ? "rgba(110,231,168,0.07)" : "rgba(255,255,255,0.03)",
                    }}
                  >
                    {c}
                  </motion.div>
                ))}
              </div>
            </div>
          ))}
        </div>
      </Frame>
    </div>
  );
}

/* SEO: a search result and an AI answer both pointing to you */
function SeoVisual() {
  const { ref, inView } = useView();
  return (
    <div ref={ref} className="mx-auto max-w-[460px] space-y-3">
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={inView ? { opacity: 1, y: 0 } : {}}
        transition={{ duration: 0.5, delay: 0.2, ease }}
        className="rounded-[10px] border border-white/10 bg-[#0e0e11] p-4"
      >
        <div className="flex items-center gap-2 rounded-full border border-white/10 px-3.5 py-2 text-[13px] text-muted">
          <span className="block size-4">
            <AppIcon.google />
          </span>
          best dental clinic in beirut
        </div>
        <div className="mt-4 space-y-1">
          <p className="text-[11px] text-muted">yourclinic.com</p>
          <p className="text-[15px] text-[#C9BDFF]">Your Clinic · Modern Dentistry in Achrafieh</p>
          <p className="text-[12px] text-muted">★★★★★ 4.9 · Open now · 1.2 km</p>
        </div>
      </motion.div>
      <motion.div
        initial={{ opacity: 0, y: 10 }}
        animate={inView ? { opacity: 1, y: 0 } : {}}
        transition={{ duration: 0.5, delay: 0.9, ease }}
        className="rounded-[10px] border border-white/10 bg-[#0e0e11] p-4"
      >
        <p className="flex items-center gap-2 text-[12px] text-muted">
          <span className="block size-4">
            <AppIcon.claude />
          </span>
          AI answer
        </p>
        <p className="mt-2 text-[13px] leading-relaxed text-text">
          A highly rated option is <span className="text-brand">Your Clinic</span> in Achrafieh, known for modern equipment and same week appointments.
        </p>
      </motion.div>
    </div>
  );
}

/* CONTENT: three reel frames with view counts */
function ContentVisual() {
  const reels = [
    { v: "2.4M", h: "from-[#2a2440] to-[#0e0c16]" },
    { v: "860K", h: "from-[#1f3b4d] to-[#0b141a]" },
    { v: "1.1M", h: "from-[#3b2a33] to-[#120b0e]" },
  ];
  const { ref, inView } = useView();
  return (
    <div ref={ref} className="mx-auto flex max-w-[460px] items-end justify-center gap-3">
      {reels.map((r, i) => (
        <motion.div
          key={i}
          initial={{ opacity: 0, y: 20 }}
          animate={inView ? { opacity: 1, y: i === 1 ? -18 : 0 } : {}}
          transition={{ duration: 0.7, delay: 0.2 + i * 0.15, ease }}
          className={`relative aspect-[9/16] w-1/3 overflow-hidden rounded-[12px] border border-white/10 bg-gradient-to-b ${r.h}`}
        >
          <span className="absolute top-1/2 left-1/2 flex size-9 -translate-x-1/2 -translate-y-1/2 items-center justify-center rounded-full bg-white/15 backdrop-blur">
            <svg width="12" height="12" viewBox="0 0 12 12" fill="#fff" aria-hidden>
              <path d="M3 1.5v9l7.5-4.5z" />
            </svg>
          </span>
          <span className="absolute bottom-2.5 left-2.5 flex items-center gap-1 text-[11px] text-white">
            <svg width="11" height="11" viewBox="0 0 12 12" fill="#fff" aria-hidden>
              <path d="M3 1.5v9l7.5-4.5z" />
            </svg>
            {r.v}
          </span>
        </motion.div>
      ))}
    </div>
  );
}

export const SERVICE_VISUALS = {
  ads: AdsVisual,
  ecom: EcomVisual,
  whatsapp: WhatsAppVisual,
  web: WebVisual,
  automation: AutomationVisual,
  crm: CrmVisual,
  seo: SeoVisual,
  content: ContentVisual,
};
