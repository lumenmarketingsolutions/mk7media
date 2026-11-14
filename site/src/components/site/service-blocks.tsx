"use client";

import * as Accordion from "@radix-ui/react-accordion";
import { AnimatePresence, motion } from "motion/react";
import { useState } from "react";
import type { Block, ServiceDef } from "@/lib/services";
import { RevealHeading, FadeUp } from "./reveal";
import { Cta } from "./cta";
import { CTA_HREF, CTA_LABEL } from "@/lib/site";
import { AppIcon } from "./app-icons";

function Head({ eyebrow, title, center }: { eyebrow?: string; title: ServiceDef["title"]; center?: boolean }) {
  return (
    <div className={center ? "text-center" : ""}>
      {eyebrow && <p className="eyebrow">{eyebrow}</p>}
      <RevealHeading className={`h-section mt-4 ${center ? "mx-auto" : ""} max-w-[18ch]`} parts={title} />
    </div>
  );
}

function Objectives({ b }: { b: Extract<Block, { type: "objectives" }> }) {
  const [k, setK] = useState(b.items[0].key);
  const cur = b.items.find((x) => x.key === k)!;
  return (
    <section className="section-tight border-t border-line-soft">
      <div className="wrap">
        <Head eyebrow={b.eyebrow} title={b.title} />
        <FadeUp className="mt-10 md:mt-14">
          <div className="grid gap-px overflow-hidden rounded-[6px] border border-line bg-line md:grid-cols-[280px_1fr]">
            <div className="flex overflow-x-auto bg-bg md:flex-col">
              {b.items.map((x) => (
                <button
                  key={x.key}
                  onClick={() => setK(x.key)}
                  className={`flex shrink-0 cursor-pointer items-center justify-between gap-6 border-line px-6 py-5 text-left text-[16px] font-medium tracking-[-0.02em] transition-colors md:border-b md:last:border-b-0 ${
                    x.key === k ? "bg-[#0f0f13] text-text" : "text-muted hover:text-text"
                  }`}
                >
                  {x.name}
                  <span className={`hidden text-[13px] md:inline ${x.key === k ? "text-brand" : "text-faint"}`}>→</span>
                </button>
              ))}
            </div>
            <div className="bg-[#0f0f13] p-7 md:p-12">
              <AnimatePresence mode="wait">
                <motion.div
                  key={cur.key}
                  initial={{ opacity: 0, y: 10 }}
                  animate={{ opacity: 1, y: 0 }}
                  exit={{ opacity: 0, y: -6 }}
                  transition={{ duration: 0.35 }}
                >
                  <p className="text-[26px] leading-tight font-semibold tracking-[-0.03em] md:text-[34px]">{cur.headline}</p>
                  <dl className="mt-10 grid gap-8 sm:grid-cols-3">
                    {[
                      ["You pay for", cur.pay],
                      ["Best for", cur.best],
                      ["Where it runs", cur.where],
                    ].map(([a, v]) => (
                      <div key={a}>
                        <dt className="text-[12px] text-faint">{a}</dt>
                        <dd className="mt-2 text-[15px] leading-snug">{v}</dd>
                      </div>
                    ))}
                  </dl>
                  <p className="mt-10 text-[14px] text-muted">Not sure which one fits? That is what the strategy call is for.</p>
                </motion.div>
              </AnimatePresence>
            </div>
          </div>
        </FadeUp>
      </div>
    </section>
  );
}

function List({ b }: { b: Extract<Block, { type: "list" }> }) {
  return (
    <section className="section-tight border-t border-line-soft">
      <div className="wrap grid gap-12 md:grid-cols-[1fr_1.3fr] md:gap-20">
        <div>
          <Head eyebrow={b.eyebrow} title={b.title} />
          {b.note && (
            <FadeUp delay={0.2}>
              <p className="mt-6 max-w-[34ch] text-[15px] leading-relaxed text-muted">{b.note}</p>
            </FadeUp>
          )}
        </div>
        <ul>
          {b.items.map((x, i) => (
            <FadeUp key={x.name} delay={i * 0.05}>
              <li className="grid gap-1.5 border-t border-line py-6 sm:grid-cols-[200px_1fr] sm:gap-8 md:py-7">
                <p className="text-[16px] font-medium tracking-[-0.02em]">{x.name}</p>
                <p className="text-[15px] leading-relaxed text-muted">{x.line}</p>
              </li>
            </FadeUp>
          ))}
        </ul>
      </div>
    </section>
  );
}

function Flow({ b }: { b: Extract<Block, { type: "flow" }> }) {
  return (
    <section className="section-tight border-t border-line-soft">
      <div className="wrap">
        <Head eyebrow={b.eyebrow} title={b.title} />
        <ol className="mt-14 grid gap-px overflow-hidden rounded-[6px] border border-line bg-line sm:grid-cols-2 md:mt-20 lg:grid-cols-4">
          {b.steps.map((s, i) => (
            <FadeUp key={s.name} delay={i * 0.08} className="bg-bg">
              <li className="flex h-full flex-col p-7 md:p-8">
                <span className="font-mono text-[12px] text-brand">{String(i + 1).padStart(2, "0")}</span>
                <p className="mt-10 text-[19px] font-semibold tracking-[-0.025em] md:mt-14">{s.name}</p>
                <p className="mt-2 text-[14.5px] leading-relaxed text-muted">{s.line}</p>
              </li>
            </FadeUp>
          ))}
        </ol>
      </div>
    </section>
  );
}

function Split({ b }: { b: Extract<Block, { type: "split" }> }) {
  return (
    <section className="section-tight border-t border-line-soft">
      <div className="wrap">
        <Head eyebrow={b.eyebrow} title={b.title} />
        <div className="mt-14 grid gap-px overflow-hidden rounded-[6px] border border-line bg-line md:mt-20 md:grid-cols-2">
          {[b.left, b.right].map((s, i) => (
            <FadeUp key={s.name} delay={i * 0.1} className="bg-bg">
              <div className="h-full p-7 md:p-10">
                <p className="text-[12px] text-faint">{s.label}</p>
                <p className="mt-3 text-[30px] font-semibold tracking-[-0.035em] md:text-[36px]">{s.name}</p>
                <p className="mt-3 max-w-[38ch] text-[15px] leading-relaxed text-muted">{s.line}</p>
                <ul className="mt-8 space-y-3 border-t border-line pt-6">
                  {s.points.map((p) => (
                    <li key={p} className="flex items-center gap-3 text-[14.5px]">
                      <span className="size-1 rounded-full bg-brand" />
                      {p}
                    </li>
                  ))}
                </ul>
              </div>
            </FadeUp>
          ))}
        </div>
      </div>
    </section>
  );
}

function Statement({ b }: { b: Extract<Block, { type: "statement" }> }) {
  return (
    <section className="section-tight border-t border-line-soft">
      <div className="wrap text-center">
        <FadeUp>
          {b.tag && <p className="eyebrow">{b.tag}</p>}
          <p className="mt-5 text-[72px] leading-none font-bold tracking-[-0.06em] md:text-[128px]">{b.big}</p>
          <p className="mx-auto mt-6 max-w-[32ch] text-[17px] text-muted md:text-[19px]">{b.line}</p>
        </FadeUp>
      </div>
    </section>
  );
}

function Audiences({ b }: { b: Extract<Block, { type: "audiences" }> }) {
  return (
    <section className="section-tight border-t border-line-soft">
      <div className="wrap">
        <Head eyebrow={b.eyebrow} title={b.title} />
        <div className="mt-14 grid gap-12 md:mt-20 md:grid-cols-3 md:gap-10">
          {b.items.map((x, i) => (
            <FadeUp key={x.name} delay={i * 0.08}>
              <div className="border-t border-line pt-6">
                <p className="text-[22px] font-semibold tracking-[-0.03em]">{x.name}</p>
                <p className="mt-3 max-w-[32ch] text-[15px] leading-relaxed text-muted">{x.line}</p>
              </div>
            </FadeUp>
          ))}
        </div>
      </div>
    </section>
  );
}

function Examples({ b }: { b: Extract<Block, { type: "examples" }> }) {
  return (
    <section className="section-tight border-t border-line-soft">
      <div className="wrap">
        <Head eyebrow={b.eyebrow} title={b.title} />
        <ul className="mt-10 md:mt-14">
          {b.items.map((x, i) => (
            <FadeUp key={x.from} delay={i * 0.05}>
              <li className="grid items-center gap-2 border-t border-line py-6 md:grid-cols-[1fr_auto_1.3fr] md:gap-10 md:py-7">
                <p className="text-[17px] font-medium tracking-[-0.02em]">{x.from}</p>
                <span className="hidden text-brand md:block">→</span>
                <p className="text-[15px] leading-relaxed text-muted">
                  <span className="mr-2 text-brand md:hidden">→</span>
                  {x.to}
                </p>
              </li>
            </FadeUp>
          ))}
        </ul>
        {b.note && <p className="mt-8 text-[14px] text-muted">{b.note}</p>}
      </div>
    </section>
  );
}

function Badge({ b }: { b: Extract<Block, { type: "badge" }> }) {
  return (
    <section className="section-tight border-t border-line-soft">
      <div className="wrap">
        <FadeUp>
          <div className="relative overflow-hidden rounded-[10px] border border-white/10 px-7 py-14 text-center md:px-16 md:py-20">
            <div
              aria-hidden
              className="absolute inset-0 opacity-70"
              style={{ background: "radial-gradient(60% 80% at 50% 0%, rgba(185,167,255,0.14), transparent 70%)" }}
            />
            <div className="relative">
              <span className="inline-flex items-center gap-2 rounded-full border border-brand/30 bg-brand/[0.07] px-3.5 py-1.5 text-[12px] text-brand">
                <svg width="12" height="12" viewBox="0 0 12 12" fill="none" aria-hidden>
                  <path d="M2.5 6.2l2.3 2.3 4.7-5" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" />
                </svg>
                {b.label}
              </span>
              <RevealHeading className="h-section mx-auto mt-6 max-w-[18ch]" parts={b.title} />
              <p className="lede mx-auto mt-6 max-w-[46ch]">{b.line}</p>
            </div>
          </div>
        </FadeUp>
      </div>
    </section>
  );
}

function Platforms({ b }: { b: Extract<Block, { type: "platforms" }> }) {
  return (
    <section className="section-tight border-t border-line-soft">
      <div className="wrap">
        <Head eyebrow={b.eyebrow} title={b.title} />
        <div className="mt-10 grid gap-px overflow-hidden rounded-[6px] border border-line bg-line sm:grid-cols-2 md:mt-14 lg:grid-cols-4">
          {b.items.map((x, i) => {
            const Icon = AppIcon[x.icon];
            return (
              <FadeUp key={x.name} delay={i * 0.06} className="bg-bg">
                <div className="h-full p-7 md:p-8">
                  <span className="block size-11">
                    <Icon />
                  </span>
                  <p className="mt-8 text-[19px] font-semibold tracking-[-0.025em]">{x.name}</p>
                  <p className="mt-2 text-[14.5px] leading-relaxed text-muted">{x.line}</p>
                </div>
              </FadeUp>
            );
          })}
        </div>
      </div>
    </section>
  );
}

function Compare({ b }: { b: Extract<Block, { type: "compare" }> }) {
  return (
    <section className="section-tight border-t border-line-soft">
      <div className="wrap">
        <Head eyebrow={b.eyebrow} title={b.title} />
        <div className="mt-10 grid gap-px overflow-hidden rounded-[6px] border border-line bg-line md:mt-14 md:grid-cols-2">
          <FadeUp className="bg-bg">
            <div className="h-full p-7 md:p-10">
              <p className="text-[15px] font-medium text-muted">{b.without.name}</p>
              <ul className="mt-6 space-y-4">
                {b.without.points.map((p) => (
                  <li key={p} className="flex items-center gap-3 text-[15px] text-muted">
                    <span className="flex size-5 shrink-0 items-center justify-center rounded-full border border-line text-[11px] text-faint">×</span>
                    {p}
                  </li>
                ))}
              </ul>
            </div>
          </FadeUp>
          <FadeUp delay={0.1} className="bg-[#0f0e14]">
            <div className="h-full p-7 md:p-10">
              <p className="text-[15px] font-medium text-brand">{b.with.name}</p>
              <ul className="mt-6 space-y-4">
                {b.with.points.map((p) => (
                  <li key={p} className="flex items-center gap-3 text-[15px] text-text">
                    <span className="flex size-5 shrink-0 items-center justify-center rounded-full bg-growth/15 text-[11px] text-growth">✓</span>
                    {p}
                  </li>
                ))}
              </ul>
            </div>
          </FadeUp>
        </div>
      </div>
    </section>
  );
}

export function ServiceBlock({ b }: { b: Block }) {
  switch (b.type) {
    case "objectives":
      return <Objectives b={b} />;
    case "list":
      return <List b={b} />;
    case "flow":
      return <Flow b={b} />;
    case "split":
      return <Split b={b} />;
    case "statement":
      return <Statement b={b} />;
    case "audiences":
      return <Audiences b={b} />;
    case "examples":
      return <Examples b={b} />;
    case "badge":
      return <Badge b={b} />;
    case "platforms":
      return <Platforms b={b} />;
    case "compare":
      return <Compare b={b} />;
  }
}

export function ServiceFaq({ faqs }: { faqs: ServiceDef["faqs"] }) {
  return (
    <section className="section-tight border-t border-line-soft">
      <div className="wrap max-w-3xl">
        <RevealHeading className="h-section text-center" parts={["Good", { t: "questions.", accent: true }]} />
        <Accordion.Root type="single" collapsible className="mt-14">
          {faqs.map((f, i) => (
            <Accordion.Item key={i} value={`q${i}`} className="border-b border-line">
              <Accordion.Header>
                <Accordion.Trigger className="group flex w-full cursor-pointer items-center justify-between gap-6 py-6 text-left text-[16px] font-medium tracking-[-0.015em]">
                  {f.q}
                  <span className="relative size-3 shrink-0 text-muted">
                    <span className="absolute top-1/2 left-0 h-px w-3 bg-current" />
                    <span className="absolute top-0 left-1/2 h-3 w-px bg-current transition-transform duration-300 group-data-[state=open]:scale-y-0" />
                  </span>
                </Accordion.Trigger>
              </Accordion.Header>
              <Accordion.Content className="overflow-hidden data-[state=closed]:animate-accordion-up data-[state=open]:animate-accordion-down">
                <p className="max-w-[60ch] pb-6 text-[15px] leading-relaxed text-muted">{f.a}</p>
              </Accordion.Content>
            </Accordion.Item>
          ))}
        </Accordion.Root>
      </div>
    </section>
  );
}

export function ServiceCloser({ title }: { title: ServiceDef["closer"] }) {
  return (
    <section className="section-tight border-t border-line-soft">
      <div className="wrap flex flex-col items-center text-center">
        <RevealHeading className="h-section max-w-[16ch]" parts={title} />
        <FadeUp delay={0.2} className="mt-10 w-full max-w-[340px] md:w-auto md:max-w-none">
          <Cta href={CTA_HREF} size="lg" className="w-full md:w-auto">
            {CTA_LABEL}
          </Cta>
        </FadeUp>
      </div>
    </section>
  );
}
