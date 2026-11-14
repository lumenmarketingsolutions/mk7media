import type { MetadataRoute } from "next";
export const dynamic = "force-static";
import { SERVICE_DEFS } from "@/lib/services";
import { getPosts } from "@/lib/blog";

const BASE = "https://mk7media.com";

export default function sitemap(): MetadataRoute.Sitemap {
  const now = new Date();
  return [
    { url: `${BASE}/`, lastModified: now, priority: 1 },
    { url: `${BASE}/services`, lastModified: now, priority: 0.9 },
    ...SERVICE_DEFS.map((s) => ({ url: `${BASE}/services/${s.slug}`, lastModified: now, priority: 0.9 })),
    { url: `${BASE}/work`, lastModified: now, priority: 0.8 },
    { url: `${BASE}/about`, lastModified: now, priority: 0.7 },
    { url: `${BASE}/contact`, lastModified: now, priority: 0.7 },
    { url: `${BASE}/blog`, lastModified: now, priority: 0.7 },
    ...getPosts().map((p) => ({ url: `${BASE}/blog/${p.slug}`, lastModified: new Date(p.date), priority: 0.6 })),
  ];
}
