import type { Metadata } from "next";
import Link from "next/link";
import { notFound } from "next/navigation";
import { Shell } from "@/components/site/shell";
import { Cta } from "@/components/site/cta";
import { getPost, getPosts } from "@/lib/blog";
import { CTA_HREF, CTA_LABEL, SITE } from "@/lib/site";

export function generateStaticParams() {
  return getPosts().map((p) => ({ slug: p.slug }));
}

export async function generateMetadata({ params }: { params: Promise<{ slug: string }> }): Promise<Metadata> {
  const { slug } = await params;
  const p = getPost(slug);
  if (!p) return {};
  return {
    title: p.title,
    description: p.description,
    alternates: { canonical: `/blog/${p.slug}` },
    openGraph: { type: "article", title: p.title, description: p.description, url: `/blog/${p.slug}` },
  };
}

export default async function PostPage({ params }: { params: Promise<{ slug: string }> }) {
  const { slug } = await params;
  const p = getPost(slug);
  if (!p) notFound();
  const more = getPosts()
    .filter((x) => x.slug !== slug)
    .sort((a, b) => (a.category === p.category ? -1 : 0) - (b.category === p.category ? -1 : 0))
    .slice(0, 3);
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "BlogPosting",
    headline: p.title,
    description: p.description,
    datePublished: p.date,
    dateModified: p.date,
    author: { "@type": "Organization", name: SITE.name, url: SITE.url },
    publisher: { "@id": `${SITE.url}/#org` },
    mainEntityOfPage: `${SITE.url}/blog/${p.slug}`,
  };

  return (
    <Shell>
      <article className="pt-32 pb-24 md:pt-44">
        <header className="wrap max-w-[760px]">
          <p className="eyebrow">
            <Link href="/blog" className="transition-colors hover:text-text">
              Blog
            </Link>
            <span className="mx-2 text-faint">/</span>
            <span className="text-brand">{p.category}</span>
          </p>
          <h1 className="mt-5 text-[34px] leading-[1.08] font-bold tracking-[-0.04em] md:text-[52px]">{p.title}</h1>
          <p className="mt-6 text-[14px] text-faint">
            {new Date(p.date).toLocaleDateString("en-US", { month: "long", day: "numeric", year: "numeric" })} · {p.readMinutes} min read · MK7 Media
          </p>
        </header>
        <div className="wrap mt-14 max-w-[760px] border-t border-line pt-12">
          <div className="prose-mk" dangerouslySetInnerHTML={{ __html: p.html }} />
        </div>
      </article>

      <section className="border-t border-line-soft py-20">
        <div className="wrap max-w-[760px]">
          <p className="eyebrow">Keep reading</p>
          <ul className="mt-6">
            {more.map((m) => (
              <li key={m.slug} className="border-b border-line">
                <Link href={`/blog/${m.slug}`} className="group flex items-center justify-between gap-6 py-6">
                  <span className="text-[17px] font-medium tracking-[-0.02em] transition-colors group-hover:text-brand">{m.title}</span>
                  <span className="text-faint">→</span>
                </Link>
              </li>
            ))}
          </ul>
          <div className="mt-14 flex flex-col items-start gap-6 md:flex-row md:items-center md:justify-between">
            <p className="text-[22px] font-semibold tracking-[-0.03em]">
              Rather have us do it? <span className="text-brand">Let's talk.</span>
            </p>
            <Cta href={CTA_HREF}>{CTA_LABEL}</Cta>
          </div>
        </div>
      </section>
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }} />
    </Shell>
  );
}
