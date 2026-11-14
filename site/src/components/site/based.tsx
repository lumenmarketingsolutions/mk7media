import { Globe } from "./globe";
import { RevealHeading, FadeUp } from "./reveal";

export function Based() {
  return (
    <section className="section overflow-hidden border-t border-line-soft" id="about">
      <div className="wrap grid items-center gap-4 md:grid-cols-2 md:gap-10">
        <div>
          <p className="eyebrow">Where we work</p>
          <RevealHeading className="h-section mt-4 max-w-[15ch]" parts={["Built in Beirut.", { t: "Working everywhere.", accent: true }]} />
          <FadeUp delay={0.15}>
            <p className="lede mt-6 max-w-[38ch]">
              Our team lives and works in Beirut, with an American founder. Our clients stretch from
              Toronto to Dubai to Sydney.
            </p>
            <dl className="mt-12 grid max-w-sm grid-cols-2 gap-y-6 border-t border-line pt-8 text-[14px]">
              <div>
                <dt className="text-muted">Home base</dt>
                <dd className="mt-1">Beirut</dd>
              </div>
              <div>
                <dt className="text-muted">Clients in</dt>
                <dd className="mt-1">9 countries</dd>
              </div>
              <div>
                <dt className="text-muted">Gulf</dt>
                <dd className="mt-1">UAE, Qatar, KSA</dd>
              </div>
              <div>
                <dt className="text-muted">Also</dt>
                <dd className="mt-1">US, Canada, Europe, Armenia, Australia</dd>
              </div>
            </dl>
          </FadeUp>
        </div>
        <FadeUp delay={0.1} className="relative order-first mx-auto w-full max-w-[420px] md:order-none md:max-w-[520px]">
          <Globe />
        </FadeUp>
      </div>
    </section>
  );
}
