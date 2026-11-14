import Link from "next/link";
import { AppIcon } from "./app-icons";
import { RevealHeading, FadeUp } from "./reveal";

/* Hairline grid (not floating cards). Each cell: a small visual that shows the outcome, a title, one line. */

function AdsVisual() {
  const bars = [30, 38, 34, 46, 52, 49, 61, 68, 64, 79, 86, 100];
  return (
    <div className="flex h-full flex-col">
      <div className="flex items-baseline justify-between text-[12px]">
        <span className="text-muted">Return on ad spend</span>
        <span className="text-[15px] font-semibold tracking-[-0.02em] text-text">
          4.8x <span className="text-[12px] font-normal text-growth">↑ 38%</span>
        </span>
      </div>
      <div className="mt-4 flex flex-1 items-end gap-[6px] md:gap-2">
        {bars.map((b, i) => (
          <span
            key={i}
            className="flex-1 rounded-t-[2px] transition-[height] duration-500"
            style={{
              height: `${b}%`,
              background:
                i === bars.length - 1
                  ? "linear-gradient(180deg,#CFC3FF,#B9A7FF)"
                  : `rgba(255,255,255,${0.06 + i * 0.008})`,
            }}
          />
        ))}
      </div>
    </div>
  );
}

function OrderVisual() {
  return (
    <div className="flex h-full flex-col justify-end gap-2">
      {[
        ["New order", "$212.00", 0.45],
        ["New order", "$89.00", 0.7],
        ["New order", "$146.00", 1],
      ].map(([a, b, o], i) => (
        <div
          key={i}
          className="flex items-center justify-between rounded-[6px] border border-white/[0.07] bg-white/[0.03] px-3 py-2 text-[12px]"
          style={{ opacity: o as number }}
        >
          <span className="flex items-center gap-2">
            <span className="block size-4">
              <AppIcon.shopify />
            </span>
            {a}
          </span>
          <span className="text-growth">{b}</span>
        </div>
      ))}
    </div>
  );
}

function WhatsAppVisual() {
  return (
    <div className="flex h-full items-center justify-center gap-3 text-[11px]">
      <span className="block size-9">
        <AppIcon.whatsapp />
      </span>
      <span className="h-px w-8 bg-gradient-to-r from-[#25D366]/70 to-[#1877F2]/70" />
      <span className="rounded-[4px] border border-white/10 px-2 py-1 whitespace-nowrap text-muted">Purchase $96</span>
      <span className="h-px w-8 bg-gradient-to-r from-[#1877F2]/70 to-[#1877F2]/70" />
      <span className="block size-9">
        <AppIcon.meta />
      </span>
    </div>
  );
}

function WebVisual() {
  return (
    <div className="h-full overflow-hidden rounded-[6px] border border-white/[0.08] bg-white/[0.02]">
      <div className="flex gap-1 border-b border-white/[0.06] px-2.5 py-2">
        <span className="size-1.5 rounded-full bg-white/15" />
        <span className="size-1.5 rounded-full bg-white/15" />
        <span className="size-1.5 rounded-full bg-white/15" />
      </div>
      <div className="space-y-2 p-3">
        <span className="block h-2.5 w-2/3 rounded-[2px] bg-white/20" />
        <span className="block h-2 w-1/2 rounded-[2px] bg-white/10" />
        <span className="mt-3 block h-5 w-24 rounded-full bg-white/80" />
      </div>
    </div>
  );
}

function AutomationVisual() {
  const nodes = ["New lead", "CRM", "WhatsApp", "Booked"];
  return (
    <div className="flex h-full items-center justify-center">
      {nodes.map((n, i) => (
        <div key={n} className="flex items-center">
          <span
            className="rounded-[4px] border px-2.5 py-1.5 text-[11px] sm:px-3 sm:text-[12px]"
            style={{
              borderColor: i === nodes.length - 1 ? "rgba(110,231,168,0.35)" : "rgba(255,255,255,0.10)",
              background: i === nodes.length - 1 ? "rgba(110,231,168,0.08)" : "rgba(255,255,255,0.03)",
              color: i === nodes.length - 1 ? "#6EE7A8" : "#F2F2F3",
            }}
          >
            {n}
          </span>
          {i < nodes.length - 1 && <span className="mx-1 h-px w-3 bg-brand/50 sm:mx-2 sm:w-10" />}
        </div>
      ))}
    </div>
  );
}

function CrmVisual() {
  const cols = [
    ["New", 3],
    ["Booked", 2],
    ["Won", 2],
  ] as const;
  return (
    <div className="grid h-full grid-cols-3 gap-2">
      {cols.map(([c, n]) => (
        <div key={c} className="flex flex-col gap-1.5">
          <span className="text-[10px] text-faint">{c}</span>
          {Array.from({ length: n }).map((_, i) => (
            <span
              key={i}
              className="block h-5 rounded-[3px] border border-white/[0.07]"
              style={{ background: c === "Won" ? "rgba(110,231,168,0.14)" : "rgba(255,255,255,0.04)" }}
            />
          ))}
        </div>
      ))}
    </div>
  );
}

const CELLS = [
  { href: "/services/paid-ads", title: "Paid ads", line: "Meta, Google, YouTube and TikTok.", V: AdsVisual, span: "md:col-span-2" },
  { href: "/services/ecommerce", title: "Ecommerce", line: "Shopify stores with the traffic behind them.", V: OrderVisual, span: "" },
  { href: "/services/whatsapp-automation", title: "WhatsApp", line: "Chats that sell, sales your pixel can see.", V: WhatsAppVisual, span: "" },
  { href: "/services/websites", title: "Websites", line: "Built to turn visitors into customers.", V: WebVisual, span: "" },
  { href: "/services/crm", title: "CRM", line: "Every lead tracked, nobody forgotten.", V: CrmVisual, span: "" },
  { href: "/services/ai-automation", title: "AI automation", line: "Your tools talking to each other while your team does real work.", V: AutomationVisual, span: "md:col-span-3" },
];

export function ServicesGrid() {
  return (
    <section className="section border-t border-line-soft" id="services">
      <div className="wrap">
        <p className="eyebrow">What we do</p>
        <RevealHeading
          className="h-section mt-4 max-w-[18ch]"
          parts={["Everything it takes to grow,", { t: "under one roof.", accent: true }]}
        />

        <FadeUp className="mt-16 md:mt-20">
          <div className="grid gap-px overflow-hidden rounded-[6px] border border-line bg-line md:grid-cols-3">
            {CELLS.map(({ href, title, line, V, span }) => {
              const wide = span.includes("col-span-3");
              return (
                <Link
                  key={href}
                  href={href}
                  className={`group flex flex-col bg-bg p-6 transition-colors duration-300 hover:bg-[#0e0e11] sm:p-8 md:p-10 ${span} ${
                    wide ? "md:flex-row-reverse md:items-center md:gap-16" : ""
                  }`}
                >
                  <div className={`h-28 md:h-36 ${wide ? "md:flex-1" : ""}`}>
                    <V />
                  </div>
                  <div className={`mt-8 flex items-end justify-between gap-6 md:mt-10 ${wide ? "md:mt-0 md:w-[38%] md:shrink-0" : ""}`}>
                    <div>
                      <h3 className="text-[20px] font-semibold tracking-[-0.025em] md:text-[26px]">{title}</h3>
                      <p className="mt-2 max-w-[40ch] text-[14px] leading-relaxed text-muted md:text-[16px]">{line}</p>
                    </div>
                    <span className="text-faint transition-all duration-300 group-hover:translate-x-1 group-hover:text-text md:text-[18px]">→</span>
                  </div>
                </Link>
              );
            })}
          </div>
        </FadeUp>
      </div>
    </section>
  );
}
