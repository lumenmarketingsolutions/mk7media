import type { Metadata } from "next";
import { Inter_Tight, Geist_Mono } from "next/font/google";
import "./globals.css";
import { MetaPixel } from "@/components/site/pixel";

const tight = Inter_Tight({ variable: "--font-tight", subsets: ["latin"] });
const mono = Geist_Mono({ variable: "--font-mono-face", subsets: ["latin"] });

export const metadata: Metadata = {
  metadataBase: new URL("https://mk7media.com"),
  title: {
    default: "MK7 Media | Meta Ads, Websites and Automation Agency in Beirut",
    template: "%s | MK7 Media",
  },
  description:
    "Beirut based marketing agency. Meta and Google ads, Shopify stores, WhatsApp automation and CRM systems for brands in Lebanon, the Gulf and beyond.",
  openGraph: {
    type: "website",
    siteName: "MK7 Media",
    images: ["/static/og-image.png"],
  },
};

export default function RootLayout({ children }: Readonly<{ children: React.ReactNode }>) {
  return (
    <html lang="en" className="dark">
      <body className={`${tight.variable} ${mono.variable} antialiased`}>
        {children}
        <MetaPixel />
      </body>
    </html>
  );
}
