import type { Metadata } from "next";
import { Shell } from "@/components/site/shell";
import { RevealHeading, FadeUp } from "@/components/site/reveal";
import { Cta } from "@/components/site/cta";
import { Globe } from "@/components/site/globe";
import { CTA_HREF, CTA_LABEL } from "@/lib/site";

export const metadata: Metadata = {
  title: "About MK7 Media: The Team in Beirut",
  description:
    "MK7 Media was founded in Beirut with one belief: never take no for an answer. Meet the agency and the story behind it.",
  alternates: { canonical: "/about" },
};

const BELIEFS = [
  { n: "See it first", l: "We picture the bigger version of a business before it exists, then build the path to it." },
  { n: "Real people, real results", l: "No smoke, no vanity numbers. If it does not grow the business, it does not count." },
  { n: "One team, whole picture", l: "Ads, site, follow up and systems built by people who talk to each other every day." },
  { n: "Grow like it's ours", l: "We treat every client's dream the way we treated our own." },
];

export default function About() {
  return (
    <Shell>
      <section className="pt-32 pb-12 md:pt-40 md:pb-16">
        <div className="wrap">
          <FadeUp instant>
            <p className="eyebrow">About</p>
          </FadeUp>
          <RevealHeading as="h1" onView={false} delay={0.1} className="h-display mt-5 max-w-[14ch]" parts={["We never took", { t: "no for an answer.", accent: true }]} />
        </div>
      </section>

      {/* THE STORY */}
      <section className="border-t border-line-soft py-16 md:py-20">
        <div className="wrap grid gap-12 md:grid-cols-[1fr_1.4fr] md:gap-20">
          <FadeUp>
            <p className="eyebrow">The story</p>
            <h2 className="h-section mt-4 max-w-[12ch]">
              Two people. <span className="text-brand">One vision.</span>
            </h2>
          </FadeUp>
          <FadeUp delay={0.1} className="space-y-6 text-[17px] leading-[1.75] text-muted md:text-[18px]">
            <p>
              MK7 started the way the best things do. With a vision nobody else could see yet, and two people who refused to wait for
              permission.
            </p>
            <p>
              <span className="text-text">One of our founders saw it first.</span> She knew what Lebanese businesses could become, and she believed they
              deserved marketing as good as anything in the world.
            </p>
            <p>
              The other was running an agency in America and saw the same gap from the other side. The help available in Lebanon was nowhere
              near the standard he knew. <span className="text-text">So he picked up his desk and moved it to Beirut.</span>
            </p>
            <p>
              Together they built MK7 on the skills they spent their lives learning, and on one simple idea. Help other people grow their
              dreams the same way we grow ours.
            </p>
            <p className="text-text">Today MK7 is a team of marketers, creators and developers in Beirut, working with brands across nine countries.</p>
          </FadeUp>
        </div>
      </section>

      {/* BELIEFS */}
      <section className="border-t border-line-soft py-16 md:py-20">
        <div className="wrap">
          <RevealHeading className="h-section max-w-[16ch]" parts={["What we", { t: "believe.", accent: true }]} />
          <div className="mt-14 grid gap-px overflow-hidden rounded-[6px] border border-line bg-line sm:grid-cols-2 md:mt-20">
            {BELIEFS.map((b, i) => (
              <FadeUp key={b.n} delay={i * 0.06} className="bg-bg">
                <div className="h-full p-7 md:p-10">
                  <p className="font-mono text-[12px] text-brand">{String(i + 1).padStart(2, "0")}</p>
                  <p className="mt-10 text-[22px] font-semibold tracking-[-0.03em] md:text-[26px]">{b.n}</p>
                  <p className="mt-3 max-w-[38ch] text-[15px] leading-relaxed text-muted">{b.l}</p>
                </div>
              </FadeUp>
            ))}
          </div>
        </div>
      </section>

      {/* BEIRUT */}
      <section className="overflow-hidden border-t border-line-soft py-16 md:py-20">
        <div className="wrap grid items-center gap-6 md:grid-cols-2 md:gap-10">
          <FadeUp className="order-first mx-auto w-full max-w-[420px] md:order-last md:max-w-[500px]">
            <Globe />
          </FadeUp>
          <div>
            <RevealHeading className="h-section max-w-[14ch]" parts={["Home is", { t: "Beirut.", accent: true }]} />
            <FadeUp delay={0.15}>
              <p className="lede mt-6 max-w-[40ch]">
                Our team lives and works here, with an American founder. Our clients stretch from Toronto to Dubai to Sydney.
              </p>
            </FadeUp>
          </div>
        </div>
      </section>

      <section className="section-tight border-t border-line-soft">
        <div className="wrap flex flex-col items-center text-center">
          <RevealHeading className="h-section max-w-[16ch]" parts={["Got a vision?", { t: "Let's build it.", accent: true }]} />
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
