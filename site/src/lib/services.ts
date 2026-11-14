/* All service page copy lives here. Voice rules: short, outcome first, no dashes, no AI words. */

export type Part = string | { t: string; accent?: boolean };

export type Block =
  | { type: "objectives"; eyebrow: string; title: Part[]; items: { key: string; name: string; headline: string; pay: string; best: string; where: string }[] }
  | { type: "list"; eyebrow: string; title: Part[]; note?: string; items: { name: string; line: string }[] }
  | { type: "flow"; eyebrow: string; title: Part[]; lede?: string; steps: { name: string; line: string }[] }
  | { type: "split"; eyebrow: string; title: Part[]; left: Side; right: Side }
  | { type: "statement"; big: string; line: string; tag?: string }
  | { type: "audiences"; eyebrow: string; title: Part[]; items: { name: string; line: string }[] }
  | { type: "examples"; eyebrow: string; title: Part[]; items: { from: string; to: string }[]; note?: string }
  | { type: "badge"; title: Part[]; line: string; label: string }
  | { type: "platforms"; eyebrow: string; title: Part[]; items: { icon: "meta" | "google" | "youtube" | "tiktok" | "shopify" | "whatsapp" | "highlevel" | "claude" | "instagram" | "web" | "seo"; name: string; line: string }[] }
  | { type: "compare"; eyebrow: string; title: Part[]; without: { name: string; points: string[] }; with: { name: string; points: string[] } };

type Side = { label: string; name: string; line: string; points: string[] };

export type ServiceDef = {
  slug: string;
  name: string;
  seoTitle: string;
  seoDescription: string;
  eyebrow: string;
  title: Part[];
  lede: string;
  visual: "ads" | "ecom" | "whatsapp" | "web" | "automation" | "crm" | "seo" | "content";
  blocks: Block[];
  faqs: { q: string; a: string }[];
  closer: Part[];
};

export const SERVICE_DEFS: ServiceDef[] = [
  {
    slug: "paid-ads",
    name: "Paid Ads",
    seoTitle: "Meta Ads and Google Ads Agency in Beirut",
    seoDescription:
      "MK7 runs Meta, Google, YouTube and TikTok ads for brands in Lebanon and the Gulf. Pixel, Conversions API and campaigns built around sales, not clicks.",
    eyebrow: "Paid ads · Meta, Google, YouTube, TikTok",
    title: ["Ads that answer", { t: "to your sales.", accent: true }],
    lede: "You tell us the goal. We pick the right campaign, build it, run it and keep improving it until the numbers move.",
    visual: "ads",
    blocks: [
      {
        type: "objectives",
        eyebrow: "Pick a goal",
        title: ["Every dollar", { t: "has a job.", accent: true }],
        items: [
          { key: "sales", name: "Sales", headline: "Turn scrollers into buyers.", pay: "Purchases", best: "Online stores and products", where: "Meta, Performance Max" },
          { key: "leads", name: "Leads", headline: "Fill your calendar.", pay: "Leads and booked calls", best: "Service businesses and B2B", where: "Meta lead forms, Google Search" },
          { key: "clicks", name: "Search", headline: "Catch people already looking.", pay: "Clicks from buyers searching", best: "High intent services", where: "Google Search" },
          { key: "awareness", name: "Awareness", headline: "Get seen by the right people.", pay: "Reach and views", best: "Launches and new markets", where: "Meta, YouTube, TikTok" },
        ],
      },
      {
        type: "list",
        eyebrow: "Under the hood",
        title: ["The part most agencies", { t: "skip.", accent: true }],
        note: "Meta certified team. We can build anything Ads Manager can do.",
        items: [
          { name: "Pixel and Conversions API", line: "Every sale reported back to Meta, including the ones browsers block." },
          { name: "Datasets and events", line: "Clean data so the algorithm learns who actually buys." },
          { name: "Custom audiences", line: "Visitors, buyers and lookalikes of your best customers." },
          { name: "Creative testing", line: "New angles every week. What loses gets cut fast." },
          { name: "Weekly reporting", line: "The numbers you care about, in plain words." },
        ],
      },
      { type: "statement", tag: "Service business · new market", big: "$290K", line: "in revenue from $7.4K in ad spend, in 82 days." },
      {
        type: "flow",
        eyebrow: "How it works",
        title: ["From first call", { t: "to first results.", accent: true }],
        steps: [
          { name: "Strategy call", line: "Your goal, your market, your numbers." },
          { name: "Tracking first", line: "Pixel, Conversions API and events checked before a dollar is spent." },
          { name: "Launch", line: "Campaigns, audiences and creative built around one objective." },
          { name: "Improve weekly", line: "Budget moves to what sells. Reports every week." },
        ],
      },
    ],
    faqs: [
      { q: "How much should we spend on ads?", a: "It depends on your goal and your market. We recommend a starting budget on the strategy call and scale it as results come in." },
      { q: "Can you work in our existing ad account?", a: "Yes. We usually keep your account so the history and data are not lost, then clean up the tracking and campaigns." },
      { q: "How fast will we see results?", a: "You see real data in the first week. Most campaigns settle after a few weeks of learning, and we report every week along the way." },
      { q: "Do you make the ad creative too?", a: "We can. Our content team shoots and edits ad creative, or we work with what you already have." },
    ],
    closer: ["Let's put your budget", { t: "to work.", accent: true }],
  },
  {
    slug: "whatsapp-automation",
    name: "WhatsApp Automation",
    seoTitle: "WhatsApp Chatbots, Automation and Sales Tracking for Meta Ads",
    seoDescription:
      "Track WhatsApp sales back to your Meta ads with MK7's approved Meta app, plus WhatsApp chatbots that reply, sell and book in seconds.",
    eyebrow: "WhatsApp automation",
    title: ["Every chat that sells,", { t: "counted.", accent: true }],
    lede: "Chatbots that sell around the clock, conversations that follow up on their own, and a platform that tells Meta every time a chat turns into a sale.",
    visual: "whatsapp",
    blocks: [
      {
        type: "badge",
        label: "Approved Meta app",
        title: ["Built by us.", { t: "Approved by Meta.", accent: true }],
        line: "MK7 runs its own approved Meta app made for exactly this. Most businesses would spend months building it. You get it plugged in.",
      },
      {
        type: "flow",
        eyebrow: "What happens",
        title: ["Four steps.", { t: "Zero guessing.", accent: true }],
        steps: [
          { name: "Ad click", line: "Someone taps your ad and opens WhatsApp." },
          { name: "Conversation", line: "Your team or your bot chats with them." },
          { name: "Sale", line: "Our platform recognises the moment they buy." },
          { name: "Meta learns", line: "The sale goes back to your pixel. Ads find more buyers." },
        ],
      },
      {
        type: "examples",
        eyebrow: "Automated conversations",
        title: ["The follow ups", { t: "you never have to send.", accent: true }],
        items: [
          { from: "Someone asks about a product", to: "Instant answer with price, photos and how to order" },
          { from: "A chat goes quiet", to: "A friendly nudge a few hours later, so the sale isn't lost" },
          { from: "An order is placed", to: "Confirmation, delivery updates and a thank you" },
          { from: "A booking is made", to: "Reminders before the appointment, no shows drop" },
          { from: "A customer bought last month", to: "A new offer at the right time to bring them back" },
        ],
      },
      {
        type: "list",
        eyebrow: "Chatbots",
        title: ["A sales team that", { t: "never sleeps.", accent: true }],
        items: [
          { name: "Replies in seconds", line: "Day or night, every message gets an answer." },
          { name: "Speaks like you", line: "Arabic, English or both, in your brand's voice." },
          { name: "Takes the order", line: "Products, prices, delivery details, done." },
          { name: "Hands off when it matters", line: "Your team steps in on the chats worth their time." },
        ],
      },
    ],
    faqs: [
      { q: "Is this allowed by Meta?", a: "Yes. It runs through Meta's official WhatsApp platform, as an app Meta has approved." },
      { q: "Do we need to change our WhatsApp number?", a: "We look at how your number is set up today and tell you exactly what is needed on the strategy call." },
      { q: "Can we use the tracking without the chatbot?", a: "Yes. Many clients keep their own sales team on WhatsApp and use our platform only to report the sales to Meta." },
    ],
    closer: ["Start counting", { t: "every sale.", accent: true }],
  },
  {
    slug: "ecommerce",
    name: "Ecommerce",
    seoTitle: "Shopify Store Development and Ecommerce Ads in Lebanon",
    seoDescription:
      "Custom coded Shopify stores, tracking done right and the ads that fill them. MK7 builds and grows ecommerce brands from Beirut.",
    eyebrow: "Ecommerce · Shopify",
    title: ["A Shopify store,", { t: "and the buyers to fill it.", accent: true }],
    lede: "Custom coded Shopify themes, tracking that sees every order, and the ads that bring buyers in. One team from first product to thousandth order.",
    visual: "ecom",
    blocks: [
      {
        type: "audiences",
        eyebrow: "Wherever you are",
        title: ["Built for the stage", { t: "you're in.", accent: true }],
        items: [
          { name: "Launching", line: "Your first store, built right from day one, with ads ready to go." },
          { name: "Getting serious", line: "A store that already sells, rebuilt to sell more and tracked properly." },
          { name: "Going big", line: "New markets, bigger budgets and systems that keep up." },
        ],
      },
      {
        type: "list",
        eyebrow: "What you get",
        title: ["Everything between", { t: "a visit and a sale.", accent: true }],
        items: [
          { name: "Custom coded Shopify theme", line: "Your brand, not a template. Fast on every phone." },
          { name: "Checkout that converts", line: "Cards, cash on delivery and WhatsApp orders, made simple." },
          { name: "Every purchase tracked", line: "Pixel and Conversions API set up so ads learn from real orders." },
          { name: "Ads that scale what sells", line: "Meta and Performance Max campaigns built for purchases." },
        ],
      },
      { type: "statement", tag: "Product launch", big: "$1.19M", line: "in revenue during one launch campaign." },
    ],
    faqs: [
      { q: "Why Shopify?", a: "It is the most reliable way to run an online store. We custom code the theme so it looks and loads like your brand, not a template." },
      { q: "We already have a store. Can you take over?", a: "Yes. We audit the store, the tracking and the ads, then fix what holds sales back." },
      { q: "Do you handle the ads too?", a: "Yes. Most ecommerce clients have us build the store and run the ads, so one team owns the result." },
    ],
    closer: ["Let's build the store", { t: "and fill it.", accent: true }],
  },
  {
    slug: "websites",
    name: "Websites",
    seoTitle: "Website Development in Beirut: Shopify and Custom Sites",
    seoDescription:
      "Fast websites that turn visitors into customers. Shopify for online stores, custom coded sites and web apps built and hosted by MK7.",
    eyebrow: "Websites",
    title: ["Websites that turn visitors", { t: "into customers.", accent: true }],
    lede: "Online stores on Shopify. Custom sites and web apps we build and host for you. Both made to load fast and sell.",
    visual: "web",
    blocks: [
      {
        type: "split",
        eyebrow: "Two ways we build",
        title: ["The right build", { t: "for the job.", accent: true }],
        left: {
          label: "Selling products",
          name: "Shopify",
          line: "Every online store we build runs on Shopify, with a theme we custom code for your brand.",
          points: ["Custom coded theme", "Checkout and payments set up", "Tracking installed", "Easy for your team to update"],
        },
        right: {
          label: "Everything else",
          name: "Custom code",
          line: "When you need more than a store, our developers build it from scratch and we host it for you.",
          points: ["Service and B2B sites", "Web apps and booking systems", "Online software and portals", "Hosting and care included"],
        },
      },
      {
        type: "list",
        eyebrow: "Every site we ship",
        title: ["Quietly", { t: "doing its job.", accent: true }],
        items: [
          { name: "Fast", line: "Loads in a blink on a phone in Beirut or Riyadh." },
          { name: "Mobile first", line: "Designed for the thumb, then the desktop." },
          { name: "Ready for Google", line: "Clean structure, speed and schema from day one." },
          { name: "Tracked", line: "Pixel, analytics and conversions set up before launch." },
          { name: "Written to sell", line: "Short, clear copy that leads to one action." },
        ],
      },
    ],
    faqs: [
      { q: "How long does a website take?", a: "It depends on the size of the project. We give you a clear timeline on the strategy call before anything starts." },
      { q: "Do you host the site?", a: "For custom builds, yes, we host and look after it. Shopify stores are hosted by Shopify." },
      { q: "Can you redesign our current site?", a: "Yes. We keep what works for Google, so a redesign does not cost you the traffic you already have." },
    ],
    closer: ["Let's build something", { t: "that sells.", accent: true }],
  },
  {
    slug: "ai-automation",
    name: "AI Automation",
    seoTitle: "AI Automation for Businesses: Connect Your Tools",
    seoDescription:
      "MK7 connects your CRM, WhatsApp, store and inbox with AI automations, so leads, orders and follow ups move on their own.",
    eyebrow: "AI automation",
    title: ["Your tools,", { t: "talking to each other.", accent: true }],
    lede: "We connect the software you already use, so leads, orders and follow ups move on their own and your team does the work that matters.",
    visual: "automation",
    blocks: [
      {
        type: "examples",
        eyebrow: "What it looks like",
        title: ["When this happens,", { t: "that happens.", accent: true }],
        items: [
          { from: "A new lead fills your form", to: "Added to your CRM, welcomed on WhatsApp, call booked" },
          { from: "A new order comes in", to: "Sent to your shipping software, customer updated at every step" },
          { from: "A call gets missed", to: "An instant WhatsApp reply so the lead never goes cold" },
          { from: "A client signs", to: "Onboarding, invoice and project board created in minutes" },
          { from: "Friday afternoon", to: "This week's numbers summarised by AI, in your inbox" },
        ],
        note: "Need something that does not exist yet? Our developers build custom solutions.",
      },
      {
        type: "badge",
        label: "Built with the latest AI",
        title: ["We use AI every day,", { t: "so you don't have to.", accent: true }],
        line: "We build with the newest AI models daily. You get the time back without learning a single new tool.",
      },
    ],
    faqs: [
      { q: "Which tools can you connect?", a: "Most tools with an API, including CRMs, WhatsApp, Shopify, Google Sheets, email and shipping software. If it cannot be connected, we can usually build what is missing." },
      { q: "Do we need to replace our current software?", a: "Usually not. We start with what you already use and connect it." },
      { q: "Is AI safe to use with our customer data?", a: "We design every automation so data only goes where it needs to, and we keep a person in the loop for anything sensitive." },
    ],
    closer: ["Let's give your team", { t: "their time back.", accent: true }],
  },
  {
    slug: "crm",
    name: "CRM Systems",
    seoTitle: "CRM Setup and Custom Software for B2B Businesses",
    seoDescription:
      "HighLevel CRM builds and custom software for B2B and service businesses. Pipelines, automations and one inbox, set up by MK7.",
    eyebrow: "CRM systems · for B2B",
    title: ["No lead", { t: "left behind.", accent: true }],
    lede: "A CRM set up around how your business actually sells. Built on HighLevel, or custom software from our developers when nothing off the shelf fits.",
    visual: "crm",
    blocks: [
      {
        type: "split",
        eyebrow: "Two ways to build it",
        title: ["Ready made", { t: "or made for you.", accent: true }],
        left: {
          label: "Most businesses",
          name: "HighLevel",
          line: "An enterprise grade CRM, set up and automated around your sales process.",
          points: ["Pipelines for every deal", "WhatsApp, SMS and email in one inbox", "Calendars and reminders", "Reports your team will read"],
        },
        right: {
          label: "When nothing fits",
          name: "Custom software",
          line: "Our developers build the system your business needs, from client portals to internal tools.",
          points: ["Built around your workflow", "Connected to your tools", "Hosted and maintained", "Grows with the team"],
        },
      },
      {
        type: "audiences",
        eyebrow: "Who it's for",
        title: ["For teams that", { t: "sell for a living.", accent: true }],
        items: [
          { name: "Service businesses", line: "Clinics, studios, contractors and anyone who books calls." },
          { name: "B2B sales teams", line: "Long deals, many touchpoints, nothing forgotten." },
          { name: "Growing companies", line: "When spreadsheets and memory stop being enough." },
        ],
      },
    ],
    faqs: [
      { q: "What is HighLevel?", a: "An all in one CRM that handles your contacts, pipelines, messaging, calendars and automations in one place. We set it up so it fits your business." },
      { q: "Can you move us from our current CRM?", a: "Yes. We plan the move, bring your data over and train your team." },
      { q: "When does custom software make sense?", a: "When your process is unique enough that a standard CRM gets in the way. We tell you honestly on the strategy call which one you need." },
    ],
    closer: ["Let's make sure every lead", { t: "gets an answer.", accent: true }],
  },
  {
    slug: "seo",
    name: "SEO",
    seoTitle: "SEO Agency in Beirut: Google, Maps and AI Search",
    seoDescription:
      "Get found on Google, Google Maps and in AI answers from ChatGPT and Perplexity. Technical SEO, local SEO and content by MK7 in Beirut.",
    eyebrow: "SEO",
    title: ["Found when buyers", { t: "go looking.", accent: true }],
    lede: "On Google, on Maps and in the answers people get from ChatGPT and Perplexity. Customers who find you on their own buy faster.",
    visual: "seo",
    blocks: [
      {
        type: "list",
        eyebrow: "Four ways to be found",
        title: ["Show up", { t: "everywhere they search.", accent: true }],
        items: [
          { name: "Technical SEO", line: "Speed, structure, sitemaps and schema so Google reads you right." },
          { name: "Google Business Profile", line: "Local rankings on Maps, reviews and the details buyers check first." },
          { name: "Content that ranks", line: "Articles that answer what your customers are asking." },
          { name: "AI search visibility", line: "Clear facts about your business that AI tools can find and quote." },
        ],
      },
      { type: "statement", tag: "Why it matters", big: "Free", line: "Every visitor from search is one you did not pay for." },
    ],
    faqs: [
      { q: "How long does SEO take?", a: "Technical fixes and Google Business Profile changes can help within weeks. Content usually takes a few months to build up." },
      { q: "What is AI search visibility?", a: "More people now ask ChatGPT, Perplexity and Google's AI for recommendations. We make sure your business has clear, consistent information those tools can find." },
      { q: "Do you write the content?", a: "Yes. We plan and write it around what your customers are actually searching." },
    ],
    closer: ["Let's get you", { t: "found.", accent: true }],
  },
  {
    slug: "content-social",
    name: "Content & Social",
    seoTitle: "Content Creation and Social Media Management in Beirut",
    seoDescription:
      "Reels, ad creative and social media management from MK7. We shoot, edit and post content that stops the scroll and sells.",
    eyebrow: "Content & social",
    title: ["Content people", { t: "stop scrolling for.", accent: true }],
    lede: "We shoot it, edit it and post it. Ad creative that sells and organic content that builds the brand.",
    visual: "content",
    blocks: [
      { type: "statement", tag: "Across client reels", big: "30M+", line: "views and counting." },
      {
        type: "list",
        eyebrow: "What we handle",
        title: ["From idea", { t: "to posted.", accent: true }],
        items: [
          { name: "Shoot", line: "Reels, product content and ads, planned around what performs." },
          { name: "Edit", line: "Hooks in the first second, pacing that holds attention." },
          { name: "Post", line: "A steady calendar so your page never goes quiet." },
          { name: "Manage", line: "Comments, messages and growth, handled." },
        ],
      },
    ],
    faqs: [
      { q: "Do you make ad creative or organic content?", a: "Both. Ad creative is built to sell, organic content is built to grow the brand, and each feeds the other." },
      { q: "Do we need to be on camera?", a: "Not always. We plan formats around your comfort and your product." },
    ],
    closer: ["Let's make something", { t: "worth watching.", accent: true }],
  },
];

/* Extra sections, inserted at a position in each page's flow. */
const EXTRA: Record<string, { at: number; block: Block }[]> = {
  "paid-ads": [
    {
      at: 1,
      block: {
        type: "platforms",
        eyebrow: "Where we run",
        title: ["Wherever your buyers", { t: "are scrolling.", accent: true }],
        items: [
          { icon: "meta", name: "Meta", line: "Facebook and Instagram. Our home turf, from first sale to scale." },
          { icon: "google", name: "Google", line: "Search and Performance Max for people already looking." },
          { icon: "youtube", name: "YouTube", line: "Video that builds demand before they search." },
          { icon: "tiktok", name: "TikTok", line: "Native content that reaches the next wave of buyers." },
        ],
      },
    },
    { at: 4, block: { type: "statement", tag: "Local service brand", big: "8.5x", line: "return on ad spend. 41% of leads became paying customers." } },
  ],
  "whatsapp-automation": [
    {
      at: 1,
      block: {
        type: "compare",
        eyebrow: "Why it matters",
        title: ["What Meta sees", { t: "changes everything.", accent: true }],
        without: { name: "Without our platform", points: ["Meta sees a chat started", "Ads find people who like to chat", "Sales happen, nobody gets credit", "Budget decisions are guesses"] },
        with: { name: "With MK7", points: ["Meta sees the actual sale", "Ads find people who buy", "Every sale matched to its ad", "Budget moves to what sells"] },
      },
    },
    {
      at: 99,
      block: {
        type: "flow",
        eyebrow: "Getting set up",
        title: ["Live in days,", { t: "not months.", accent: true }],
        steps: [
          { name: "Strategy call", line: "How you sell on WhatsApp today and what you want it to do." },
          { name: "Connect", line: "Your number joins our approved platform. Your team keeps chatting." },
          { name: "Train", line: "The bot learns your products, prices, tone and rules." },
          { name: "Go live", line: "Sales start flowing back to Meta. We watch every week." },
        ],
      },
    },
  ],
  ecommerce: [
    {
      at: 2,
      block: {
        type: "flow",
        eyebrow: "From idea to orders",
        title: ["How a store", { t: "comes to life.", accent: true }],
        steps: [
          { name: "Brand and plan", line: "Products, pricing, offer and the look of the store." },
          { name: "Build on Shopify", line: "Custom coded theme, product pages that sell, checkout set up." },
          { name: "Track everything", line: "Pixel, Conversions API and analytics before launch day." },
          { name: "Launch and scale", line: "Ads go live, winners get more budget, the store keeps improving." },
        ],
      },
    },
    {
      at: 3,
      block: {
        type: "examples",
        eyebrow: "Built in automations",
        title: ["The store that", { t: "follows up for you.", accent: true }],
        items: [
          { from: "A cart gets abandoned", to: "A WhatsApp reminder brings them back to checkout" },
          { from: "An order is placed", to: "Confirmation and delivery updates, automatically" },
          { from: "A package is delivered", to: "A review request at the right moment" },
          { from: "A customer buys once", to: "The right offer later, so they buy again" },
        ],
      },
    },
    {
      at: 99,
      block: {
        type: "list",
        eyebrow: "Inside every store",
        title: ["Small details,", { t: "big difference.", accent: true }],
        items: [
          { name: "Product pages that sell", line: "Photos, proof and answers placed where buyers look." },
          { name: "Bundles and upsells", line: "Bigger orders without bigger ad budgets." },
          { name: "Reviews", line: "Social proof collected and shown automatically." },
          { name: "More than one market", line: "Currencies, languages and delivery set up per country." },
          { name: "Speed", line: "Quick on every phone, because slow stores lose sales." },
        ],
      },
    },
    { at: 99, block: { type: "statement", tag: "New brand", big: "$30K", line: "in monthly revenue within 90 days of launch." } },
  ],
  websites: [
    {
      at: 99,
      block: {
        type: "flow",
        eyebrow: "How we build",
        title: ["Clear steps,", { t: "no surprises.", accent: true }],
        steps: [
          { name: "Plan", line: "Goals, pages and the one action every visitor should take." },
          { name: "Design", line: "A look that fits your brand, shown to you before we build." },
          { name: "Build", line: "Shopify or custom code, fast and mobile first." },
          { name: "Launch and care", line: "Tracking, SEO basics, hosting and updates handled." },
        ],
      },
    },
  ],
  "ai-automation": [
    {
      at: 1,
      block: {
        type: "platforms",
        eyebrow: "What we connect",
        title: ["The tools you use,", { t: "working as one.", accent: true }],
        items: [
          { icon: "highlevel", name: "CRM", line: "HighLevel and most CRMs with an API." },
          { icon: "whatsapp", name: "WhatsApp", line: "Messages, replies and follow ups." },
          { icon: "shopify", name: "Shopify", line: "Orders, customers and stock." },
          { icon: "claude", name: "AI models", line: "Writing, sorting and summarising, done for you." },
        ],
      },
    },
    {
      at: 99,
      block: {
        type: "flow",
        eyebrow: "How it starts",
        title: ["Find the time sinks.", { t: "Remove them.", accent: true }],
        steps: [
          { name: "Map", line: "We walk through how work moves through your business today." },
          { name: "Pick", line: "The automations that save the most hours, first." },
          { name: "Build", line: "Connected, tested and documented." },
          { name: "Improve", line: "We watch it run and keep adding." },
        ],
      },
    },
  ],
  crm: [
    {
      at: 1,
      block: {
        type: "list",
        eyebrow: "What's inside",
        title: ["One place for", { t: "every customer.", accent: true }],
        items: [
          { name: "Pipelines", line: "Every deal, every stage, visible at a glance." },
          { name: "One inbox", line: "WhatsApp, SMS, email and social messages together." },
          { name: "Automations", line: "Follow ups, reminders and tasks that run themselves." },
          { name: "Calendars", line: "Booking links, reminders and fewer no shows." },
          { name: "Reporting", line: "Where leads come from and which ones close." },
        ],
      },
    },
    {
      at: 99,
      block: {
        type: "flow",
        eyebrow: "How we roll it out",
        title: ["Set up once.", { t: "Used every day.", accent: true }],
        steps: [
          { name: "Map your sales", line: "How a lead becomes a client in your business." },
          { name: "Build", line: "Pipelines, automations and integrations to match." },
          { name: "Move your data", line: "Contacts and history brought over cleanly." },
          { name: "Train the team", line: "So it actually gets used, not just installed." },
        ],
      },
    },
  ],
  seo: [
    {
      at: 1,
      block: {
        type: "examples",
        eyebrow: "What buyers type",
        title: ["Be the answer", { t: "they find.", accent: true }],
        items: [
          { from: "\"best clinic near me\"", to: "Your Google Business Profile, top of the map" },
          { from: "\"how much does it cost to\"", to: "Your article, answering it clearly" },
          { from: "\"which agency should I use\"", to: "Your name in the AI answer" },
          { from: "\"your brand name\"", to: "Your site, reviews and socials, all consistent" },
        ],
      },
    },
    {
      at: 99,
      block: {
        type: "flow",
        eyebrow: "How it works",
        title: ["Fix, build,", { t: "then grow.", accent: true }],
        steps: [
          { name: "Audit", line: "What Google sees today and what is holding you back." },
          { name: "Fix", line: "Technical issues, speed and structure first." },
          { name: "Build", line: "Business profile, content and the facts AI tools rely on." },
          { name: "Grow", line: "New content every month and a report on what moved." },
        ],
      },
    },
  ],
  "content-social": [
    {
      at: 99,
      block: {
        type: "audiences",
        eyebrow: "Formats that work",
        title: ["Made for", { t: "the feed.", accent: true }],
        items: [
          { name: "Product content", line: "Your product, shown the way people actually use it." },
          { name: "Creator style", line: "Real people talking to camera, the format that sells." },
          { name: "Founder led", line: "Your story, told by you, built for trust." },
        ],
      },
    },
    {
      at: 99,
      block: {
        type: "flow",
        eyebrow: "Every month",
        title: ["A rhythm that", { t: "never misses.", accent: true }],
        steps: [
          { name: "Plan", line: "Ideas built from what is already working." },
          { name: "Shoot", line: "A shoot day that covers the whole month." },
          { name: "Edit", line: "Fast hooks, clean pacing, on brand." },
          { name: "Post and learn", line: "Published, measured and fed into the next month." },
        ],
      },
    },
  ],
};

for (const s of SERVICE_DEFS) {
  for (const e of [...(EXTRA[s.slug] ?? [])].sort((a, b) => b.at - a.at)) {
    s.blocks.splice(Math.min(e.at, s.blocks.length), 0, e.block);
  }
}

export const getService = (slug: string) => SERVICE_DEFS.find((s) => s.slug === slug);
