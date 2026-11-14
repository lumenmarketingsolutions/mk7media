import type { Metadata } from "next";
import { Shell } from "@/components/site/shell";
import { RevealHeading, FadeUp } from "@/components/site/reveal";
import { ContactForm } from "@/components/site/contact-form";
import { AppIcon } from "@/components/site/app-icons";
import { SITE } from "@/lib/site";

export const metadata: Metadata = {
  title: "Book a Free Strategy Call",
  description: "Tell us where you want to grow. MK7 Media will reach out on WhatsApp to set up a free strategy call. Based in Beirut, working worldwide.",
  alternates: { canonical: "/contact" },
};

const NEXT = [
  { n: "We reach out", l: "On WhatsApp, usually the same day." },
  { n: "We talk", l: "Where you are, where you want to be." },
  { n: "You get a plan", l: "Exactly what we would do. Yours to keep." },
];

export default function Contact() {
  return (
    <Shell>
      <section className="pt-32 pb-24 md:pt-44 md:pb-32">
        <div className="wrap grid gap-16 md:grid-cols-[1fr_1.25fr] md:gap-20">
          <div>
            <FadeUp instant>
              <p className="eyebrow">Free strategy call</p>
            </FadeUp>
            <RevealHeading as="h1" onView={false} delay={0.1} className="h-display mt-5 max-w-[11ch]" parts={["Let's see", { t: "what's possible.", accent: true }]} />
            <FadeUp instant delay={0.4}>
              <ol className="mt-12 space-y-0">
                {NEXT.map((x, i) => (
                  <li key={x.n} className="grid grid-cols-[36px_1fr] border-t border-line py-5">
                    <span className="font-mono text-[12px] text-brand">0{i + 1}</span>
                    <span>
                      <span className="block text-[16px] font-medium tracking-[-0.02em]">{x.n}</span>
                      <span className="mt-1 block text-[14px] text-muted">{x.l}</span>
                    </span>
                  </li>
                ))}
              </ol>
              <a
                href={`https://wa.me/${SITE.whatsapp}`}
                className="mt-10 inline-flex items-center gap-3 text-[14px] text-muted transition-colors hover:text-text"
              >
                <span className="block size-7">
                  <AppIcon.whatsapp />
                </span>
                Prefer to message? {SITE.whatsappPretty}
              </a>
            </FadeUp>
          </div>
          <FadeUp instant delay={0.2}>
            <ContactForm />
          </FadeUp>
        </div>
      </section>
    </Shell>
  );
}
