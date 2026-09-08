import type { AppraisalRequest, SourceSearchLinks } from "@drivecheck/shared";

function slugify(value: string): string {
  return value
    .normalize("NFD")
    .replace(/\p{M}/gu, "")
    .toLowerCase()
    .replace(/[^a-z0-9]+/g, "-")
    .replace(/^-|-$/g, "");
}

/** Brand path on auto.bazos.cz — Tier 1 only (never over-filter). */
const BAZOS_BRAND: Record<string, string> = {
  skoda: "skoda",
  volkswagen: "volkswagen",
  vw: "volkswagen",
  audi: "audi",
  bmw: "bmw",
  "mercedes-benz": "mercedes",
  mercedes: "mercedes",
  ford: "ford",
  hyundai: "hyundai",
  kia: "kia",
  toyota: "toyota",
  renault: "renault",
  peugeot: "peugeot",
  citroen: "citroen",
  opel: "opel",
  seat: "seat",
  nissan: "nissan",
  mazda: "mazda",
  honda: "honda",
  volvo: "volvo",
  fiat: "fiat",
  dacia: "dacia",
  "alfa-romeo": "alfa",
  suzuki: "suzuki",
  mitsubishi: "mitsubishi",
  chevrolet: "chevrolet",
};

export function buildSourceSearchLinks(input: AppraisalRequest): SourceSearchLinks {
  const makeSlug = slugify(input.make);
  const modelSlug = slugify(input.model);

  // Sauto: brand + model path only (no rare equipment filters).
  const sautoUrl =
    makeSlug && modelSlug
      ? `https://www.sauto.cz/inzerce/osobni/${encodeURIComponent(makeSlug)}/${encodeURIComponent(modelSlug)}`
      : makeSlug
        ? `https://www.sauto.cz/inzerce/osobni/${encodeURIComponent(makeSlug)}`
        : "https://www.sauto.cz/inzerce/osobni";

  const bazosBrand = BAZOS_BRAND[makeSlug] ?? BAZOS_BRAND[makeSlug.replace(/-/g, "")] ?? "ostatni";
  const bazosUrl = `https://auto.bazos.cz/${bazosBrand}/`;

  return { sautoUrl, bazosUrl };
}
