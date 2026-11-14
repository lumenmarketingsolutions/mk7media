"use client";

import { SERVICE_VISUALS } from "./service-visuals";

export function ServiceHeroVisual({ kind }: { kind: keyof typeof SERVICE_VISUALS }) {
  const V = SERVICE_VISUALS[kind];
  return <V />;
}
