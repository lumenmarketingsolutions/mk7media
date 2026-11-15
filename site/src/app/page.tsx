import { Nav } from "@/components/site/nav";
import { Cta } from "@/components/site/cta";
import { HeroDashboard } from "@/components/site/hero-dashboard";
import { Dock } from "@/components/site/dock";
import { RevealHeading, FadeUp } from "@/components/site/reveal";
import { Proof } from "@/components/site/proof";
import { ServicesGrid } from "@/components/site/services-grid";
import { Results } from "@/components/site/results";
import { Based } from "@/components/site/based";
import { Faq } from "@/components/site/faq";
import { FAQS } from "@/lib/faqs";
import { Footer } from "@/components/site/footer";
import { CTA_HREF, CTA_LABEL, SITE } from "@/lib/site";

const jsonLd = {
  "@context": "https://schema.org",
  "@graph": [
    {
      "@type": "MarketingAgency",
      "@id": `${SITE.url}/#org`,
      name: SITE.name,
      url: SITE.url,
      logo: `${SITE.url}/static/favicon.svg`,
      description: "Digital marketing agency in Beirut, Lebanon for Meta and Google ads, Shopify stores, websites, WhatsApp automation and CRM systems.",
      address: { "@type": "PostalAddress", addressLocality: "Beirut", addressCountry: "LB" },
      areaServed: ["LB", "AE", "QA", "SA", "US", "CA", "AM", "AU", "GB", "FR"],
      telephone: `+${SITE.whatsapp}`,
      foundingDate: "2023",
      knowsAbout: ["Meta Ads", "Google Ads", "Shopify", "WhatsApp automation", "GoHighLevel CRM", "SEO", "AI automation"],
    },
    {
      "@type": "FAQPage",
      mainEntity: FAQS.map((f) => ({ "@type": "Question", name: f.q, acceptedAnswer: { "@type": "Answer", text: f.a } })),
    },
  ],
};

export default function Home() {
  return (
    <>
      <Nav />
      <main className="relative z-10 bg-bg shadow-[0_40px_60px_-20px_rgba(0,0,0,0.9)]">
        {/* HERO */}
        <section className="relative overflow-hidden pt-32 pb-20 md:pt-44 md:pb-28">
          <div aria-hidden className="grid-backdrop absolute inset-0 opacity-60" />
          <div className="wrap relative">
            <div className="mx-auto max-w-3xl text-center">
              <FadeUp instant>
                <p className="eyebrow">Based in Beirut, Lebanon</p>
              </FadeUp>
              <RevealHeading
                as="h1"
                onView={false}
                delay={0.1}
                className="h-display mt-5"
                parts={["Your brand, growing", "\n", { t: "while you sleep.", accent: true }]}
              />
              <FadeUp instant delay={0.5}>
                <p className="lede mx-auto mt-6 max-w-[44ch]">
                  Meta and Google ads, Shopify stores, WhatsApp automation and CRMs. Built and run by one team.
                </p>
                <div className="mt-10 flex flex-col items-center justify-center gap-5 sm:flex-row sm:gap-8">
                  <Cta href={CTA_HREF} size="lg">
                    {CTA_LABEL}
                  </Cta>
                  <Cta href="#results" variant="link">
                    See the results
                  </Cta>
                </div>
              </FadeUp>
            </div>

            <div className="mx-auto mt-20 max-w-[1040px] md:mt-24">
              <HeroDashboard />
            </div>
          </div>
        </section>

        {/* DOCK: a separator and a shortcut to every service */}
        <section className="pb-8 md:pb-4">
          <div className="wrap flex flex-col items-center">
            <FadeUp>
              <p className="text-center text-[15px] text-muted md:text-[17px]">Where do you want to grow?</p>
            </FadeUp>
            <FadeUp delay={0.1} className="mt-8">
              <Dock />
            </FadeUp>
          </div>
        </section>

        <Proof />
        <ServicesGrid />
        <Based />
        <Results />
        <Faq />
      </main>
      <Footer />
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }} />
    </>
  );
}
