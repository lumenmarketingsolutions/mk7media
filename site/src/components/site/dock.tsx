"use client";

import Link from "next/link";
import { motion, useMotionValue, useSpring, useTransform, type MotionValue } from "motion/react";
import { useRef } from "react";
import { AppIcon } from "./app-icons";

const ITEMS = [
  { key: "meta", label: "Meta Ads", href: "/services/paid-ads#meta", Icon: AppIcon.meta },
  { key: "google", label: "Google Ads", href: "/services/paid-ads#google", Icon: AppIcon.google },
  { key: "shopify", label: "Shopify", href: "/services/ecommerce", Icon: AppIcon.shopify },
  { key: "whatsapp", label: "WhatsApp", href: "/services/whatsapp-automation", Icon: AppIcon.whatsapp },
  { key: "highlevel", label: "CRM", href: "/services/crm", Icon: AppIcon.highlevel },
  { key: "claude", label: "AI Automation", href: "/services/ai-automation", Icon: AppIcon.claude },
  { key: "seo", label: "SEO", href: "/services/seo", Icon: AppIcon.seo },
];

function DockItem({
  mouseX,
  item,
}: {
  mouseX: MotionValue<number>;
  item: (typeof ITEMS)[number];
}) {
  const ref = useRef<HTMLAnchorElement>(null);
  const distance = useTransform(mouseX, (x) => {
    const b = ref.current?.getBoundingClientRect() ?? { x: 0, width: 0 };
    return x - b.x - b.width / 2;
  });
  const sizeRaw = useTransform(distance, [-170, 0, 170], [64, 88, 64]);
  const size = useSpring(sizeRaw, { mass: 0.1, stiffness: 170, damping: 14 });
  const { Icon } = item;

  return (
    <Link ref={ref} href={item.href} className="group relative flex flex-col items-center" aria-label={item.label}>
      <span className="pointer-events-none absolute -top-10 whitespace-nowrap rounded-[4px] border border-line bg-surface px-2 py-1 text-[12px] text-text opacity-0 transition-opacity duration-200 group-hover:opacity-100">
        {item.label}
      </span>
      {/* desktop: magnifies */}
      <motion.span style={{ width: size, height: size }} className="hidden md:block">
        <Icon />
      </motion.span>
      {/* mobile: fixed size */}
      <span className="block size-10 md:hidden">
        <Icon />
      </span>
    </Link>
  );
}

export function Dock() {
  const mouseX = useMotionValue(Infinity);
  return (
    <div className="flex flex-col items-center">
      <div
        onMouseMove={(e) => mouseX.set(e.clientX)}
        onMouseLeave={() => mouseX.set(Infinity)}
        className="flex h-[60px] items-end gap-2.5 rounded-[20px] border border-white/10 px-3 pb-2.5 md:h-[92px] md:gap-4 md:rounded-[26px] md:px-4 md:pb-3.5"
        style={{
          background: "linear-gradient(180deg, rgba(255,255,255,0.07), rgba(255,255,255,0.03))",
          backdropFilter: "blur(18px) saturate(150%)",
          WebkitBackdropFilter: "blur(18px) saturate(150%)",
          boxShadow: "inset 0 1px 0 rgba(255,255,255,0.08), 0 20px 40px -20px rgba(0,0,0,0.9)",
        }}
      >
        {ITEMS.map((item) => (
          <DockItem key={item.key} mouseX={mouseX} item={item} />
        ))}
      </div>
    </div>
  );
}
