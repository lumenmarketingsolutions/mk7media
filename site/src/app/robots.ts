import type { MetadataRoute } from "next";
export const dynamic = "force-static";

/* The preview stays out of Google until launch. At launch set SITE_LIVE=1. */
export default function robots(): MetadataRoute.Robots {
  if (process.env.SITE_LIVE !== "1") return { rules: { userAgent: "*", disallow: "/" } };
  return {
    rules: { userAgent: "*", allow: "/", disallow: ["/palettes", "/sampler", "/logos", "/admin"] },
    sitemap: "https://mk7media.com/sitemap.xml",
  };
}
