import { RevealHeading, FadeUp } from "./reveal";
import { Cta } from "./cta";

/* Real results from the current site, client names kept private. */
const ROWS = [
  { tag: "Service business · new market", big: "$290K", line: "in revenue from $7.4K in ad spend, in 82 days." },
  { tag: "Product launch", big: "$1.19M", line: "in revenue during one launch campaign." },
  { tag: "Local service brand", big: "8.5x", line: "return on ad spend. 41% of leads became customers." },
  { tag: "New brand", big: "$30K", line: "in monthly revenue within 90 days of launch." },
];

export function Results() {
  return (
    <section className="section border-t border-line-soft">
      <div className="wrap">
        <div className="flex flex-col justify-between gap-8 md:flex-row md:items-end">
          <div>
            <p className="eyebrow">Selected results</p>
            <RevealHeading className="h-section mt-4 max-w-[16ch]" parts={["What growth", { t: "looks like.", accent: true }]} />
          </div>
          <Cta href="/work" variant="link">
            See all work
          </Cta>
        </div>

        <ul className="mt-14 md:mt-20">
          {ROWS.map((r, i) => (
            <FadeUp key={r.tag} delay={i * 0.06}>
              <li className="grid gap-2 border-t border-line py-8 md:grid-cols-[1fr_auto_1.2fr] md:items-baseline md:gap-12 md:py-10">
                <p className="text-[13px] text-muted">{r.tag}</p>
                <p className="text-[44px] leading-none font-semibold tracking-[-0.05em] md:min-w-[3.5em] md:text-[56px]">{r.big}</p>
                <p className="max-w-[34ch] text-[15px] leading-relaxed text-muted">{r.line}</p>
              </li>
            </FadeUp>
          ))}
        </ul>
      </div>
    </section>
  );
}
