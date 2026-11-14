import type { Metadata } from "next";
import Link from "next/link";
import { Shell } from "@/components/site/shell";
import { RevealHeading, FadeUp } from "@/components/site/reveal";
import { Cta } from "@/components/site/cta";
import { AppIcon } from "@/components/site/app-icons";
import { SERVICE_DEFS } from "@/lib/services";
import { SERVICES, CTA_HREF, CTA_LABEL } from "@/lib/site";

export const metadata: Metadata = {
  title: "Services: Ads, Websites, WhatsApp, CRM and SEO",
  description:
    "Everything MK7 does to grow a business: Meta and Google ads, Shopify stores, websites, WhatsApp automation, CRM systems, AI automation, content and SEO.",
  alternates: { canonical: "/services" },
};

const ICONS: Record<string, () => React.ReactElement> = {
  "paid-ads": AppIcon.meta,
  ecommerce: AppIcon.shopify,
  "whatsapp-automation": AppIcon.whatsapp,
  websites: AppIcon.web,
  "ai-automation": AppIcon.claude,
  crm: AppIcon.highlevel,
  "content-social": AppIcon.instagram,
  seo: AppIcon.seo,
};

const GROUPS = [
  { name: "Get seen", slugs: ["paid-ads", "content-social", "seo"] },
  { name: "Make the sale", slugs: ["ecommerce", "websites", "whatsapp-automation"] },
  { name: "Run it smoothly", slugs: ["crm", "ai-automation"] },
];

export default function Services() {
  return (
    <Shell>
      <section className="pt-32 pb-16 md:pt-44 md:pb-20">
        <div className="wrap">
          <FadeUp instant>
            <p className="eyebrow">Services</p>
          </FadeUp>
          <RevealHeading as="h1" onView={false} delay={0.1} className="h-display mt-5 max-w-[15ch]" parts={["One team for the", { t: "whole journey.", accent: true }]} />
          <FadeUp instant delay={0.4}>
            <p className="lede mt-6 max-w-[46ch]">
              From the first time someone sees your brand to the moment they buy, and every follow up after. Pick one, or let us run the whole thing.
            </p>
          </FadeUp>
        </div>
      </section>

      {GROUPS.map((g, gi) => (
        <section key={g.name} className="border-t border-line-soft py-12 md:py-16">
          <div className="wrap grid gap-10 md:grid-cols-[220px_1fr] md:gap-16">
            <FadeUp>
              <p className="font-mono text-[12px] text-brand">0{gi + 1}</p>
              <h2 className="mt-3 text-[24px] font-semibold tracking-[-0.03em]">{g.name}</h2>
            </FadeUp>
            <ul>
              {g.slugs.map((slug, i) => {
                const s = SERVICES.find((x) => x.slug === slug)!;
                const def = SERVICE_DEFS.find((x) => x.slug === slug)!;
                const Icon = ICONS[slug];
                return (
                  <FadeUp key={slug} delay={i * 0.06}>
                    <li className="border-t border-line first:border-t-0 md:first:border-t">
                      <Link href={`/services/${slug}`} className="group grid grid-cols-[40px_1fr_auto] items-center gap-5 py-7 md:py-8">
                        <span className="block size-10">
                          <Icon />
                        </span>
                        <span>
                          <span className="block text-[20px] font-semibold tracking-[-0.025em] md:text-[24px]">{def.name}</span>
                          <span className="mt-1 block text-[14.5px] leading-relaxed text-muted">{s.short}</span>
                        </span>
                        <span className="text-faint transition-all duration-300 group-hover:translate-x-1 group-hover:text-text">→</span>
                      </Link>
                    </li>
                  </FadeUp>
                );
              })}
            </ul>
          </div>
        </section>
      ))}

      <section className="section-tight border-t border-line-soft">
        <div className="wrap flex flex-col items-center text-center">
          <RevealHeading className="h-section max-w-[16ch]" parts={["Not sure where to start?", { t: "Start here.", accent: true }]} />
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
