export type EquipmentItem = {
  key: string;
  labelCs: string;
  iconSrc: string;
  /** Alternate keys seen in crawler/DB/text extraction. */
  aliases: string[];
};

/** Canonical equipment catalog shown in filters and listing cards. */
export const EQUIPMENT_CATALOG: readonly EquipmentItem[] = [
  {
    key: "keyless",
    labelCs: "Keyless",
    iconSrc: "/equipment/keyless.png",
    aliases: ["keyless_entry", "bezklicove_odemykani", "bezklicovy_pristup"],
  },
  {
    key: "blind_spot",
    labelCs: "Mrtvý úhel",
    iconSrc: "/equipment/blind_spot.png",
    aliases: ["mrtvy_uhel", "blind_spot_monitor", "bsm"],
  },
  {
    key: "electric_tailgate",
    labelCs: "El. kufr",
    iconSrc: "/equipment/electric_tailgate.png",
    aliases: ["kufr", "power_tailgate", "elektricky_kufr", "elektricke_otevirani_kufru"],
  },
  {
    key: "massage_seats",
    labelCs: "Masážní sedadla",
    iconSrc: "/equipment/massage_seats.png",
    aliases: ["masazni_sedadla", "masazni_kresla", "massage"],
  },
  {
    key: "lane_assist",
    labelCs: "Jízda v pruhu",
    iconSrc: "/equipment/lane_assist.png",
    aliases: ["jizda_v_pruhu", "jizda_v_pruzich", "lane_keep", "lane_keeping", "lka"],
  },
  {
    key: "aux_heater",
    labelCs: "Nezávislé topení",
    iconSrc: "/equipment/aux_heater.png",
    aliases: ["nezavisle_topeni", "webasto", "parking_heater", "standheizung"],
  },
  {
    key: "tow_hitch",
    labelCs: "Tažné zařízení",
    iconSrc: "/equipment/tow_hitch.png",
    aliases: ["tazne_zarizeni", "tazne", "towbar"],
  },
  {
    key: "panorama",
    labelCs: "Panoramatická střecha",
    iconSrc: "/equipment/panorama.png",
    aliases: ["panoramaticka_strecha", "panoramic_roof", "sunroof"],
  },
  {
    key: "parking_camera",
    labelCs: "Parkovací kamera",
    iconSrc: "/equipment/parking_camera.png",
    aliases: ["parkovaci_kamera", "kamera", "rear_camera"],
  },
  {
    key: "cruise_control",
    labelCs: "Tempomat",
    iconSrc: "/equipment/cruise_control.png",
    aliases: ["tempomat", "adaptive_cruise", "adaptivni_tempomat"],
  },
  {
    key: "heated_seats",
    labelCs: "Vyhřívaná sedadla",
    iconSrc: "/equipment/heated_seats.png",
    aliases: ["vyhrivana_sedadla", "vyhrivan", "heated_seat"],
  },
  {
    key: "ventilated_seats",
    labelCs: "Ventilovaná sedadla",
    iconSrc: "/equipment/ventilated_seats.png",
    aliases: ["ventilovana_sedadla", "ventilated_seat"],
  },
  {
    key: "factory_warranty",
    labelCs: "Tovární záruka",
    iconSrc: "/equipment/factory_warranty.png",
    aliases: ["tovarni_zaruka", "zaruka_vyrobce", "manufacturer_warranty"],
  },
  {
    key: "air_suspension",
    labelCs: "Vzduchový podvozek",
    iconSrc: "/equipment/air_suspension.png",
    aliases: ["vzduchovy_podvozek", "air_ride", "pneumatic_suspension"],
  },
] as const;

const BY_KEY = new Map(EQUIPMENT_CATALOG.map((item) => [item.key, item]));

const ALIAS_TO_KEY = (() => {
  const map = new Map<string, string>();
  for (const item of EQUIPMENT_CATALOG) {
    map.set(item.key, item.key);
    for (const alias of item.aliases) {
      map.set(normalizeEquipmentToken(alias), item.key);
    }
  }
  return map;
})();

export function normalizeEquipmentToken(value: string): string {
  return value
    .normalize("NFD")
    .replace(/\p{M}/gu, "")
    .toLowerCase()
    .trim()
    .replace(/[^a-z0-9]+/g, "_")
    .replace(/^_+|_+$/g, "");
}

/** Map any known alias/raw key to a catalog key, or null if unknown. */
export function canonicalizeEquipmentKey(raw: string | null | undefined): string | null {
  if (!raw) return null;
  const token = normalizeEquipmentToken(raw);
  if (!token) return null;
  if (BY_KEY.has(token)) return token;
  return ALIAS_TO_KEY.get(token) ?? null;
}

export function equipmentLabelCs(key: string): string {
  const canon = canonicalizeEquipmentKey(key) ?? key;
  return BY_KEY.get(canon)?.labelCs ?? key.replace(/_/g, " ");
}

export function equipmentIconSrc(key: string): string | null {
  const canon = canonicalizeEquipmentKey(key);
  if (!canon) return null;
  return BY_KEY.get(canon)?.iconSrc ?? null;
}

/** Canonical key + aliases for SQL overlap / client matching. */
export function equipmentMatchTokens(key: string): string[] {
  const canon = canonicalizeEquipmentKey(key) ?? normalizeEquipmentToken(key);
  if (!canon) return [];
  const item = BY_KEY.get(canon);
  if (!item) return [canon];
  const tokens = new Set<string>([item.key]);
  for (const alias of item.aliases) {
    const t = normalizeEquipmentToken(alias);
    if (t) tokens.add(t);
  }
  return [...tokens];
}

export function listingHasEquipment(
  listingKeys: readonly string[] | null | undefined,
  wantedKey: string,
): boolean {
  const wanted = canonicalizeEquipmentKey(wantedKey) ?? normalizeEquipmentToken(wantedKey);
  if (!wanted) return false;
  for (const raw of listingKeys ?? []) {
    const canon = canonicalizeEquipmentKey(raw) ?? normalizeEquipmentToken(raw);
    if (canon === wanted) return true;
  }
  return false;
}

/** AND: listing must include every selected equipment key. */
export function listingHasAllEquipment(
  listingKeys: readonly string[] | null | undefined,
  wantedKeys: readonly string[],
): boolean {
  if (wantedKeys.length === 0) return true;
  return wantedKeys.every((key) => listingHasEquipment(listingKeys, key));
}

/** Catalog items present on a listing, in catalog order. */
export function matchingEquipmentItems(
  listingKeys: readonly string[] | null | undefined,
): EquipmentItem[] {
  const present = new Set<string>();
  for (const raw of listingKeys ?? []) {
    const canon = canonicalizeEquipmentKey(raw);
    if (canon) present.add(canon);
  }
  return EQUIPMENT_CATALOG.filter((item) => present.has(item.key));
}
