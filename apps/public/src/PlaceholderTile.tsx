import type { PlaceholderIconId } from "@drivecheck/pricing";
import { placeholderCaption, placeholderIconId } from "@drivecheck/pricing";
import cabrio from "../placeholders/icons/cabrio.svg?raw";
import car from "../placeholders/icons/car.svg?raw";
import coupe from "../placeholders/icons/coupe.svg?raw";
import hatchback from "../placeholders/icons/hatchback.svg?raw";
import kombi from "../placeholders/icons/kombi.svg?raw";
import mpv from "../placeholders/icons/mpv.svg?raw";
import pickup from "../placeholders/icons/pickup.svg?raw";
import sedan from "../placeholders/icons/sedan.svg?raw";
import suv from "../placeholders/icons/suv.svg?raw";
import van from "../placeholders/icons/van.svg?raw";

const ICONS: Record<PlaceholderIconId, string> = {
  hatchback,
  sedan,
  kombi,
  suv,
  mpv,
  coupe,
  cabrio,
  pickup,
  van,
  car,
};

export function PlaceholderTile(props: {
  body?: string | null;
  color?: string | null;
  source: string;
  externalId: string;
}) {
  const tile = placeholderIconId(props);
  const svg = ICONS[tile.icon] ?? ICONS.car;
  return (
    <div className="ph-tile" style={{ color: tile.tintCss }} aria-hidden="true">
      <div className="ph-glyph" dangerouslySetInnerHTML={{ __html: svg }} />
      <span className="ph-caption">{placeholderCaption()}</span>
    </div>
  );
}
