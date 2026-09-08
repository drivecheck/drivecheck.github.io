const TZ = "Europe/Prague";
export const STALE_AFTER_DAYS = 14;

export function formatCzk(value: number | null | undefined): string {
  if (value == null || !Number.isFinite(value)) return "—";
  return `${Math.round(value).toLocaleString("cs-CZ")} Kč`;
}

export function confidenceCs(level: string): string {
  if (level === "high") return "Vysoká";
  if (level === "medium") return "Střední";
  return "Nízká";
}

export function confidenceChip(level: string): "success" | "warning" | "danger" {
  if (level === "high") return "success";
  if (level === "medium") return "warning";
  return "danger";
}

export function sourceLabel(source: string): string {
  if (source === "sauto") return "Sauto";
  if (source === "bazos") return "Bazoš";
  if (source === "tipcars") return "TipCars";
  if (source === "autobazar_eu") return "Autobazar.eu";
  if (source === "autoscout24") return "AutoScout24";
  if (source === "mobile_de") return "Mobile.de";
  return source;
}

export function sellerLabel(sellerType: string | null | undefined): string | null {
  if (sellerType === "private") return "Soukromý";
  if (sellerType === "dealer") return "Dealer";
  return null;
}

export function formatDateCs(iso: string | null | undefined): string | null {
  if (!iso) return null;
  const t = Date.parse(iso);
  if (!Number.isFinite(t)) return null;
  return new Date(t).toLocaleDateString("cs-CZ", {
    timeZone: TZ,
    day: "numeric",
    month: "numeric",
    year: "numeric",
  });
}

export function daysSince(iso: string | null | undefined, now = Date.now()): number | null {
  if (!iso) return null;
  const t = Date.parse(iso);
  if (!Number.isFinite(t)) return null;
  return Math.max(0, Math.floor((now - t) / 86_400_000));
}

export function isStaleListing(lastSeenAt: string | null | undefined, now = Date.now()): boolean {
  const days = daysSince(lastSeenAt, now);
  return days == null || days > STALE_AFTER_DAYS;
}

export function askGapSentence(gapPct: number | null | undefined): string | null {
  if (gapPct == null || !Number.isFinite(gapPct)) return null;
  const pct = Math.round(Math.abs(gapPct) * 100);
  if (pct === 0) return "Inzeráty žádají zhruba totéž co reálná hodnota.";
  if (gapPct > 0) return `Inzeráty žádají o ${pct} % víc než reálná hodnota.`;
  return `Inzeráty žádají o ${pct} % míň než reálná hodnota.`;
}

export function turnoverZoneCs(days: number | null | undefined): string | null {
  if (days == null || !Number.isFinite(days)) return null;
  if (days < 30) return "Rychle";
  if (days <= 60) return "Běžně";
  return "Pomalu";
}
