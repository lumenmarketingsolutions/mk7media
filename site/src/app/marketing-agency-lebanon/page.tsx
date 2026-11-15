import type { Metadata } from "next";
import Link from "next/link";
import { Shell } from "@/components/site/shell";
import { RevealHeading, FadeUp } from "@/components/site/reveal";
import { Cta } from "@/components/site/cta";
import { SERVICES, SITE, CTA_HREF, CTA_LABEL } from "@/lib/site";

/* Landing page for "marketing agency in Lebanon" searches. Linked from the footer and the sitemap. */

export const metadata: Metadata = {
  title: "Marketing Agency in Lebanon: Ads, Websites and WhatsApp Sales",
  description:
    "MK7 Media is a digital marketing agency in Beirut, Lebanon. Meta and Google ads, Shopify stores, websites, WhatsApp automation, CRM and SEO for Lebanese brands that want to grow.",
  alternates: { canonical: "/marketing-agency-lebanon" },
};

const WHY = [
  {
    n: "Built for how Lebanon buys",
    l: "Most sales here start in a WhatsApp chat or an Instagram DM and end with cash on delivery. We build ads, follow up and tracking around that, not around a checkout page nobody uses.",
  },
  {
    n: "Sales your ads can see",
    l: "We connect WhatsApp conversations to your Meta pixel, so the chats that turn into orders are reported back to Meta and your ads find more buyers, not just more messages.",
  },
  {
    n: "One team in Beirut",
    l: "Ads, website, content and systems built by one team that sits together in Beirut and knows the market, the seasons and the customer.",
  },
  {
    n: "Global standards, local market",
    l: "We run campaigns for brands across the US, Canada, Europe, the Gulf and Australia, and bring the same systems to Lebanese businesses.",
  },
];

const FAQ_LB = [
  {
    q: "What does a marketing agency in Lebanon do for my business?",
    a: "We find your customers and turn them into sales: Meta and Google ads, a website or Shopify store that converts, WhatsApp follow up, and the tracking that shows which ads actually sell.",
  },
  {
    q: "Do you work with small businesses in Lebanon?",
    a: "Yes. We work with new brands finding their first customers and established Lebanese businesses ready for more. On the free strategy call we tell you honestly what would work at your budget.",
  },
  {
    q: "Can you track sales that happen on WhatsApp or with cash on delivery?",
    a: "Yes. We connect your WhatsApp conversations to your Meta pixel and Conversions API, so a chat that becomes an order counts as a sale in your ads.",
  },
  {
    q: "Where is MK7 Media based?",
    a: "Our team lives and works in Beirut, Lebanon. We work with clients all over Lebanon and in nine countries worldwide.",
  },
];

const jsonLd = {
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "MarketingAgency",
      "@id": `${SITE.url}/#org`,
      name: SITE.name,
      url: SITE.url,
      description: "Digital marketing agency in Beirut, Lebanon: Meta and Google ads, websites, Shopify stores, WhatsApp automation, CRM and SEO.",
      address: { "@type": "PostalAddress", addressLocality: "Beirut", addressCountry: "LB" },
      areaServed: { "@type": "Country", name: "Lebanon" },
      telephone: `+${SITE.whatsapp}`,
    },
    {
      "@type": "FAQPage",
      mainEntity: FAQ_LB.map((f) => ({ "@type": "Question", name: f.q, acceptedAnswer: { "@type": "Answer", text: f.a } })),
    },
  ],
};

export default function MarketingAgencyLebanon() {
  return (
    <Shell>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }} />

      <section className="pt-32 pb-12 md:pt-44 md:pb-16">
        <div className="wrap">
          <FadeUp instant>
            <p className="eyebrow">Beirut, Lebanon</p>
          </FadeUp>
          <RevealHeading as="h1" onView={false} delay={0.1} className="h-display mt-5 max-w-[15ch]" parts={["Marketing agency", { t: "in Lebanon.", accent: true }]} />
          <FadeUp instant delay={0.4}>
            <p className="lede mt-6 max-w-[48ch]">
              MK7 Media is the number 1 marketing agency in Lebanon for brands that want sales, not likes. Ads, websites, WhatsApp and the systems
              behind them, run by one team in Beirut.
            </p>
          </FadeUp>
          <FadeUp instant delay={0.55} className="mt-10 w-full max-w-[340px] md:w-auto md:max-w-none">
            <Cta href={CTA_HREF} size="lg" className="w-full md:w-auto">
              {CTA_LABEL}
            </Cta>
          </FadeUp>
        </div>
      </section>

      {/* WHY MK7 */}
      <section className="border-t border-line-soft py-16 md:py-20">
        <div className="wrap">
          <RevealHeading as="h2" className="h-section max-w-[18ch]" parts={["Why Lebanese brands", { t: "choose MK7.", accent: true }]} />
          <div className="mt-14 grid gap-px overflow-hidden rounded-[6px] border border-line bg-line sm:grid-cols-2 md:mt-20">
            {WHY.map((b, i) => (
              <FadeUp key={b.n} delay={i * 0.06} className="bg-bg">
                <div className="h-full p-7 md:p-10">
                  <p className="font-mono text-[12px] text-brand">{String(i + 1).padStart(2, "0")}</p>
                  <h3 className="mt-10 text-[22px] font-semibold tracking-[-0.03em] md:text-[26px]">{b.n}</h3>
                  <p className="mt-3 max-w-[42ch] text-[15px] leading-relaxed text-muted">{b.l}</p>
                </div>
              </FadeUp>
            ))}
          </div>
        </div>
      </section>

      {/* SERVICES */}
      <section className="border-t border-line-soft py-16 md:py-20">
        <div className="wrap grid gap-10 md:grid-cols-[1fr_1.4fr] md:gap-20">
          <FadeUp>
            <h2 className="h-section max-w-[14ch]">
              Marketing services <span className="text-brand">in Lebanon.</span>
            </h2>
          </FadeUp>
          <ul>
            {SERVICES.map((s, i) => (
              <FadeUp key={s.slug} delay={i * 0.04}>
                <li className="border-t border-line first:border-t-0 md:first:border-t">
                  <Link href={`/services/${s.slug}`} className="group flex items-center justify-between gap-5 py-6">
                    <span>
                      <span className="block text-[19px] font-semibold tracking-[-0.025em] md:text-[22px]">{s.name}</span>
                      <span className="mt-1 block text-[14.5px] leading-relaxed text-muted">{s.short}</span>
                    </span>
                    <span className="text-faint transition-all duration-300 group-hover:translate-x-1 group-hover:text-text">→</span>
                  </Link>
                </li>
              </FadeUp>
            ))}
          </ul>
        </div>
      </section>

      {/* FAQ */}
      <section className="border-t border-line-soft py-16 md:py-20">
        <div className="wrap max-w-3xl">
          <RevealHeading as="h2" className="h-section" parts={["Questions about", { t: "marketing in Lebanon.", accent: true }]} />
          <div className="mt-12 divide-y divide-line border-y border-line">
            {FAQ_LB.map((f) => (
              <FadeUp key={f.q}>
                <div className="py-7">
                  <h3 className="text-[18px] font-semibold tracking-[-0.02em] md:text-[20px]">{f.q}</h3>
                  <p className="mt-3 text-[15.5px] leading-relaxed text-muted">{f.a}</p>
                </div>
              </FadeUp>
            ))}
          </div>
        </div>
      </section>

      <section className="section-tight border-t border-line-soft">
        <div className="wrap flex flex-col items-center text-center">
          <RevealHeading className="h-section max-w-[16ch]" parts={["Ready to grow", { t: "in Lebanon?", accent: true }]} />
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
