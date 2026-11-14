import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Shell } from "@/components/site/shell";
import { Cta } from "@/components/site/cta";
import { RevealHeading, FadeUp } from "@/components/site/reveal";
import { ServiceHeroVisual } from "@/components/site/service-hero-visual";
import { ServiceBlock, ServiceFaq, ServiceCloser } from "@/components/site/service-blocks";
import { SERVICE_DEFS, getService } from "@/lib/services";
import { CTA_HREF, CTA_LABEL, SITE } from "@/lib/site";

export function generateStaticParams() {
  return SERVICE_DEFS.map((s) => ({ slug: s.slug }));
}

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  const s = getService(slug);
  if (!s) return {};
  return {
    title: s.seoTitle,
    description: s.seoDescription,
    alternates: { canonical: `/services/${s.slug}` },
    openGraph: { title: `${s.seoTitle} | MK7 Media`, description: s.seoDescription, url: `/services/${s.slug}` },
  };
}

export default async function ServicePage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const s = getService(slug);
  if (!s) notFound();

  const others = SERVICE_DEFS.filter((x) => x.slug !== s.slug);
  const jsonLd = {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "Service",
        name: s.name,
        serviceType: s.name,
        description: s.seoDescription,
        url: `${SITE.url}/services/${s.slug}`,
        provider: { "@id": `${SITE.url}/#org` },
        areaServed: ["Lebanon", "United Arab Emirates", "Qatar", "Saudi Arabia", "United States", "Canada"],
      },
      {
        "@type": "FAQPage",
        mainEntity: s.faqs.map((f) => ({ "@type": "Question", name: f.q, acceptedAnswer: { "@type": "Answer", text: f.a } })),
      },
      {
        "@type": "BreadcrumbList",
        itemListElement: [
          { "@type": "ListItem", position: 1, name: "Home", item: SITE.url },
          { "@type": "ListItem", position: 2, name: "Services", item: `${SITE.url}/services` },
          { "@type": "ListItem", position: 3, name: s.name, item: `${SITE.url}/services/${s.slug}` },
        ],
      },
    ],
  };

  return (
    <Shell>
      {/* HERO: text left, the outcome on the right */}
      <section className="relative overflow-hidden pt-32 pb-16 md:pt-40 md:pb-20">
        <div aria-hidden className="grid-backdrop absolute inset-0 opacity-50" />
        <div className="wrap relative grid items-center gap-16 md:grid-cols-[1.05fr_1fr] md:gap-14">
          <div>
            <FadeUp instant>
              <p className="eyebrow">
                <Link href="/services" className="transition-colors hover:text-text">
                  Services
                </Link>
                <span className="mx-2 text-faint">/</span>
                {s.eyebrow}
              </p>
            </FadeUp>
            <RevealHeading as="h1" onView={false} delay={0.1} className="h-display mt-5 max-w-[14ch]" parts={s.title} />
            <FadeUp instant delay={0.45}>
              <p className="lede mt-6 max-w-[42ch]">{s.lede}</p>
              <div className="mt-10 flex flex-col items-start gap-5 sm:flex-row sm:items-center sm:gap-8">
                <Cta href={CTA_HREF} size="lg">
                  {CTA_LABEL}
                </Cta>
                <Cta href="/work" variant="link">
                  See results
                </Cta>
              </div>
            </FadeUp>
          </div>
          <FadeUp instant delay={0.3}>
            <ServiceHeroVisual kind={s.visual} />
          </FadeUp>
        </div>
      </section>

      {s.blocks.map((b, i) => (
        <ServiceBlock key={i} b={b} />
      ))}

      <ServiceFaq faqs={s.faqs} />
      <ServiceCloser title={s.closer} />

      {/* more services */}
      <section className="border-t border-line-soft py-16 md:py-20">
        <div className="wrap">
          <p className="eyebrow">More from MK7</p>
          <ul className="mt-8 grid gap-px overflow-hidden rounded-[6px] border border-line bg-line sm:grid-cols-2 lg:grid-cols-4">
            {others.slice(0, 4).map((o) => (
              <li key={o.slug} className="bg-bg">
                <Link href={`/services/${o.slug}`} className="group flex items-center justify-between p-6 transition-colors hover:bg-[#0e0e11]">
                  <span className="text-[16px] font-medium tracking-[-0.02em]">{o.name}</span>
                  <span className="text-faint transition-all group-hover:translate-x-0.5 group-hover:text-text">→</span>
                </Link>
              </li>
            ))}
          </ul>
        </div>
      </section>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }} />
    </Shell>
  );
}
