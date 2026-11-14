export const SITE = {
  name: "MK7 Media",
  url: "https://mk7media.com",
  city: "Beirut, Lebanon",
  whatsapp: "96179018107",
  whatsappPretty: "+961 79 018 107",
  instagram: "", // TODO Kendall: handle
  email: "", // TODO Kendall: contact email
};

export type Service = {
  slug: string;
  name: string;
  short: string; // one line, outcome first
  group: "Grow" | "Sell" | "Systems";
};

export const SERVICES: Service[] = [
  { slug: "paid-ads", name: "Paid Ads", short: "Meta, Google, YouTube and TikTok ads built around sales.", group: "Grow" },
  { slug: "ecommerce", name: "Ecommerce", short: "Shopify stores built to sell, with the traffic behind them.", group: "Sell" },
  { slug: "whatsapp-automation", name: "WhatsApp Automation", short: "Chats that answer themselves and sales your pixel can see.", group: "Systems" },
  { slug: "websites", name: "Websites", short: "Fast sites that turn visitors into calls, orders and leads.", group: "Sell" },
  { slug: "ai-automation", name: "AI Automation", short: "Your tools talking to each other, so your team stops copy pasting.", group: "Systems" },
  { slug: "crm", name: "CRM Systems", short: "A HighLevel setup where no lead slips through.", group: "Systems" },
  { slug: "content-social", name: "Content & Social", short: "Reels and ad creative people stop scrolling for.", group: "Grow" },
  { slug: "seo", name: "SEO", short: "Found on Google and in AI answers when buyers go looking.", group: "Grow" },
];

export const NAV = [
  { label: "Services", href: "/services" },
  { label: "Work", href: "/work" },
  { label: "About", href: "/about" },
  { label: "Blog", href: "/blog" },
];

export const CTA_HREF = "/contact";
export const CTA_LABEL = "Book a free strategy call";
