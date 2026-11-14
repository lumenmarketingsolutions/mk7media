import Link from "next/link";
import { Logo } from "./logo";
import { Cta } from "./cta";
import { SERVICES, SITE, CTA_HREF } from "@/lib/site";

const COLS = [
  { title: "Services", links: SERVICES.map((s) => ({ label: s.name, href: `/services/${s.slug}` })) },
  {
    title: "Company",
    links: [
      { label: "About", href: "/about" },
      { label: "Work", href: "/work" },
      { label: "Blog", href: "/blog" },
      { label: "Contact", href: "/contact" },
    ],
  },
  {
    title: "Connect",
    links: [
      { label: "WhatsApp", href: `https://wa.me/${SITE.whatsapp}` },
      { label: "Instagram", href: "https://instagram.com/" }, // TODO handle
      { label: "Strategy call", href: CTA_HREF },
    ],
  },
];

/* Final call to action + full sitemap. On desktop the content above lifts off it like a curtain. */
export function Footer() {
  return (
    <footer className="relative z-0 border-t border-line-soft bg-bg md:sticky md:bottom-0">
      <div className="relative overflow-hidden">
        <div aria-hidden className="grid-backdrop absolute inset-0" />
        <p
          aria-hidden
          className="pointer-events-none absolute -bottom-[0.18em] left-1/2 -translate-x-1/2 text-[34vw] leading-none font-black tracking-[-0.06em] whitespace-nowrap select-none md:text-[22vw]"
          style={{
            color: "transparent",
            WebkitTextStroke: "1px rgba(255,255,255,0.05)",
            background: "linear-gradient(180deg, rgba(255,255,255,0.07), transparent 65%)",
            WebkitBackgroundClip: "text",
            backgroundClip: "text",
          }}
        >
          MK7
        </p>

        <div className="wrap relative pt-28 pb-14 md:pt-36">
          <div className="flex flex-col items-center gap-10 text-center md:flex-row md:items-end md:justify-between md:gap-8 md:text-left">
            <h2 className="h-section max-w-[14ch]">
              Your next customers are <span className="text-brand">out there.</span>
            </h2>
            <Cta href={CTA_HREF} size="lg" className="h-[58px] w-full max-w-[340px] text-[16px] md:h-[52px] md:w-auto md:max-w-none md:text-[15px]">
              Book a free strategy call
            </Cta>
          </div>

          <div className="mt-24 grid grid-cols-2 gap-x-6 gap-y-12 border-t border-line pt-12 md:grid-cols-[1.4fr_1fr_1fr_1fr]">
            <div className="col-span-2 md:col-span-1">
              <Logo />
              <p className="mt-4 max-w-[30ch] text-[14px] leading-relaxed text-muted">
                Ads, websites and automation for brands that want to grow. Based in Beirut.
              </p>
            </div>
            {COLS.map((c) => (
              <div key={c.title}>
                <p className="text-[13px] text-faint">{c.title}</p>
                <ul className="mt-4 space-y-3">
                  {c.links.map((l) => (
                    <li key={l.label}>
                      <Link href={l.href} className="text-[14px] text-muted transition-colors hover:text-text">
                        {l.label}
                      </Link>
                    </li>
                  ))}
                </ul>
              </div>
            ))}
          </div>

          <div className="mt-16 flex flex-col gap-3 text-[12px] text-faint md:flex-row md:justify-between">
            <p>© {new Date().getFullYear()} MK7 Media · Beirut, Lebanon</p>
            <p>Google Partner · Shopify Partner · Meta certified</p>
          </div>
        </div>
      </div>
    </footer>
  );
}
