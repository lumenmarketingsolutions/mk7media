import type { Metadata } from "next";
import { Shell } from "@/components/site/shell";
import { RevealHeading, FadeUp } from "@/components/site/reveal";
import { Cta } from "@/components/site/cta";
import { CTA_HREF, CTA_LABEL } from "@/lib/site";

export const metadata: Metadata = {
  title: "Results and Case Studies",
  description:
    "Real results from MK7 clients: $290K from $7.4K in ad spend, a $1.19M launch, 8.5x return on ad spend. Client names kept private.",
  alternates: { canonical: "/work" },
};

/* Real numbers from MK7's existing case studies. Client names stay private. */
const CASES = [
  {
    tag: "Service business · entering a new market",
    title: "A new market, filled in 82 days.",
    services: ["Meta ads", "Lead generation", "Follow up"],
    stats: [
      { v: "$290K", l: "Net revenue" },
      { v: "880", l: "Leads" },
      { v: "129", l: "Closed sales" },
    ],
    line: "$7,376 in total ad spend. An average ticket of $2,319.",
  },
  {
    tag: "High ticket product launch",
    title: "From zero to seven figures.",
    services: ["Funnel strategy", "Meta ads", "Landing pages", "Tracking"],
    stats: [
      { v: "$1.19M", l: "Revenue in the campaign" },
      { v: "1", l: "Launch" },
    ],
    line: "A complete funnel built and run for one launch period.",
  },
  {
    tag: "Local service brand · WhatsApp leads",
    title: "Small budget. Big return.",
    services: ["Meta ads", "WhatsApp", "CRM"],
    stats: [
      { v: "8.5x", l: "Return on ad spend" },
      { v: "125", l: "Inbound leads" },
      { v: "41%", l: "Became customers" },
    ],
    line: "$1,890 in ads. 53 new paying customers.",
  },
  {
    tag: "Lead generation · four campaign versions",
    title: "Every version cheaper than the last.",
    services: ["Meta ads", "Creative testing"],
    stats: [
      { v: "435", l: "Qualified leads" },
      { v: "$10.17", l: "Best cost per lead" },
      { v: "9,086", l: "Clicks" },
    ],
    line: "$9,868 in total spend, refined campaign after campaign to push the cost per lead down.",
  },
  {
    tag: "New brand · built from scratch",
    title: "Ninety days to a real business.",
    services: ["Website", "Meta ads", "Systems"],
    stats: [
      { v: "$30K", l: "Monthly revenue" },
      { v: "90", l: "Days from launch" },
    ],
    line: "Ads, website and systems installed from zero.",
  },
];

export default function Work() {
  return (
    <Shell>
      <section className="pt-32 pb-12 md:pt-44 md:pb-16">
        <div className="wrap">
          <FadeUp instant>
            <p className="eyebrow">Work</p>
          </FadeUp>
          <RevealHeading as="h1" onView={false} delay={0.1} className="h-display mt-5 max-w-[13ch]" parts={["Less talk.", { t: "More receipts.", accent: true }]} />
          <FadeUp instant delay={0.4}>
            <p className="lede mt-6 max-w-[44ch]">
              A few of the results we are proud of. Our clients trust us with their numbers, so we keep their names to ourselves.
            </p>
          </FadeUp>
        </div>
      </section>

      {CASES.map((c, i) => (
        <section key={c.title} className="border-t border-line-soft py-16 md:py-24">
          <div className="wrap grid gap-12 md:grid-cols-[1fr_1.2fr] md:gap-20">
            <FadeUp>
              <p className="font-mono text-[12px] text-brand">{String(i + 1).padStart(2, "0")}</p>
              <p className="mt-6 text-[13px] text-muted">{c.tag}</p>
              <h2 className="mt-3 max-w-[16ch] text-[30px] leading-[1.08] font-bold tracking-[-0.035em] md:text-[40px]">{c.title}</h2>
              <p className="mt-5 max-w-[38ch] text-[15px] leading-relaxed text-muted">{c.line}</p>
              <ul className="mt-8 flex flex-wrap gap-x-5 gap-y-2 text-[13px] text-faint">
                {c.services.map((s) => (
                  <li key={s}>{s}</li>
                ))}
              </ul>
            </FadeUp>
            <FadeUp delay={0.1}>
              <dl className="grid grid-cols-2 gap-px overflow-hidden rounded-[6px] border border-line bg-line">
                {c.stats.map((s, j) => (
                  <div key={s.l} className={`bg-bg p-6 md:p-8 ${c.stats.length === 3 && j === 0 ? "col-span-2" : ""} ${c.stats.length === 2 && j === 0 ? "col-span-2" : ""}`}>
                    <dd className={`leading-none font-semibold tracking-[-0.05em] ${j === 0 ? "text-[56px] md:text-[80px]" : "text-[34px] md:text-[44px]"}`}>{s.v}</dd>
                    <dt className="mt-3 text-[13px] text-muted">{s.l}</dt>
                  </div>
                ))}
              </dl>
            </FadeUp>
          </div>
        </section>
      ))}

      <section className="section-tight border-t border-line-soft">
        <div className="wrap flex flex-col items-center text-center">
          <RevealHeading className="h-section max-w-[16ch]" parts={["Your numbers", { t: "could be next.", accent: true }]} />
          <FadeUp delay={0.2} className="mt-10 w-full max-w-[340px] md:w-auto md:max-w-none">
            <Cta href={CTA_HREF} size="lg" className="w-full md:w-auto">
              {CTA_LABEL}
            </Cta>
          </FadeUp>
        </div>
      </section>
    </Shell>
  );
}
