"use client";

import * as Accordion from "@radix-ui/react-accordion";
import { RevealHeading, FadeUp } from "./reveal";

import { FAQS } from "@/lib/faqs";

export function Faq() {
  return (
    <section className="section border-t border-line-soft" id="faq">
      <div className="wrap max-w-3xl">
        <RevealHeading className="h-section text-center" parts={["Questions,", { t: "answered.", accent: true }]} />
        <FadeUp delay={0.15}>
          <Accordion.Root type="single" collapsible className="mt-14 md:mt-16">
            {FAQS.map((f, i) => (
              <Accordion.Item key={i} value={`q${i}`} className="border-b border-line">
                <Accordion.Header>
                  <Accordion.Trigger className="group flex w-full cursor-pointer items-center justify-between gap-6 py-6 text-left text-[16px] font-medium tracking-[-0.015em]">
                    {f.q}
                    <span className="relative size-3 shrink-0 text-muted">
                      <span className="absolute top-1/2 left-0 h-px w-3 bg-current" />
                      <span className="absolute top-0 left-1/2 h-3 w-px bg-current transition-transform duration-300 group-data-[state=open]:scale-y-0" />
                    </span>
                  </Accordion.Trigger>
                </Accordion.Header>
                <Accordion.Content className="overflow-hidden data-[state=closed]:animate-accordion-up data-[state=open]:animate-accordion-down">
                  <p className="max-w-[60ch] pb-6 text-[15px] leading-relaxed text-muted">{f.a}</p>
                </Accordion.Content>
              </Accordion.Item>
            ))}
          </Accordion.Root>
        </FadeUp>
      </div>
    </section>
  );
}
