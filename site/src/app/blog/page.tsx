import type { Metadata } from "next";
import Link from "next/link";
import { Shell } from "@/components/site/shell";
import { RevealHeading, FadeUp } from "@/components/site/reveal";
import { getPosts } from "@/lib/blog";

export const metadata: Metadata = {
  title: "Blog: Meta Ads, WhatsApp, Shopify and Growth Guides",
  description:
    "Practical guides from MK7 Media on Meta ads, Google ads, WhatsApp sales tracking, Shopify, websites and automation, written for businesses in Lebanon and the Gulf.",
  alternates: { canonical: "/blog" },
};

export default function Blog() {
  const posts = getPosts();
  const [lead, ...rest] = posts;
  return (
    <Shell>
      <section className="pt-32 pb-12 md:pt-44 md:pb-16">
        <div className="wrap">
          <FadeUp instant>
            <p className="eyebrow">Blog</p>
          </FadeUp>
          <RevealHeading as="h1" onView={false} delay={0.1} className="h-display mt-5 max-w-[14ch]" parts={["What we know,", { t: "written down.", accent: true }]} />
          <FadeUp instant delay={0.4}>
            <p className="lede mt-6 max-w-[44ch]">Practical guides on ads, WhatsApp, stores and systems. The same playbook we use for clients.</p>
          </FadeUp>
        </div>
      </section>

      {lead && (
        <section className="border-t border-line-soft py-14 md:py-20">
          <div className="wrap">
            <FadeUp>
              <Link href={`/blog/${lead.slug}`} className="group grid gap-6 md:grid-cols-[1.4fr_1fr] md:items-end md:gap-16">
                <h2 className="text-[30px] leading-[1.1] font-bold tracking-[-0.035em] transition-colors group-hover:text-brand md:text-[44px]">{lead.title}</h2>
                <div>
                  <p className="text-[15px] leading-relaxed text-muted">{lead.description}</p>
                  <p className="mt-5 text-[13px] text-faint">
                    {lead.category} · {lead.readMinutes} min read
                  </p>
                </div>
              </Link>
            </FadeUp>
          </div>
        </section>
      )}

      <section className="border-t border-line-soft pb-28">
        <div className="wrap">
          <ul>
            {rest.map((p, i) => (
              <FadeUp key={p.slug} delay={Math.min(i, 4) * 0.04}>
                <li className="border-b border-line">
                  <Link href={`/blog/${p.slug}`} className="group grid gap-2 py-8 md:grid-cols-[160px_1fr_auto] md:items-baseline md:gap-10">
                    <span className="text-[13px] text-brand">{p.category}</span>
                    <span>
                      <span className="block text-[19px] font-semibold tracking-[-0.025em] transition-colors group-hover:text-brand md:text-[22px]">{p.title}</span>
                      <span className="mt-2 block max-w-[62ch] text-[14.5px] leading-relaxed text-muted">{p.description}</span>
                    </span>
                    <span className="text-[13px] text-faint">{p.readMinutes} min</span>
                  </Link>
                </li>
              </FadeUp>
            ))}
          </ul>
        </div>
      </section>
    </Shell>
  );
}
