import type { CompListing } from "@drivecheck/shared";
import { PlaceholderTile } from "./PlaceholderTile";
import { SourceMark } from "./SourceMark";
import {
  formatCzk,
  formatDateCs,
  isStaleListing,
  sellerLabel,
} from "./format";

function titleOf(comp: CompListing): string {
  const fromApi = comp.title?.trim();
  if (fromApi) return fromApi;
  return [comp.make, comp.model].filter(Boolean).join(" ") || "Nabídka";
}

function metaLine(comp: CompListing): string {
  const seller = sellerLabel(comp.sellerType);
  return [
    comp.year != null ? String(comp.year) : null,
    comp.mileageKm != null ? `${comp.mileageKm.toLocaleString("cs-CZ")} km` : null,
    comp.fuel,
    comp.transmission,
    comp.body,
    comp.region,
    seller,
  ]
    .filter((part): part is string => Boolean(part && part.trim()))
    .join(" · ");
}

export function CompCard(props: { comp: CompListing }) {
  const { comp } = props;
  const stale = isStaleListing(comp.lastSeenAt);
  const seen = formatDateCs(comp.lastSeenAt);
  return (
    <article className={`card${stale ? " stale" : ""}`}>
      <div className="card-visual">
        <PlaceholderTile
          body={comp.body}
          color={comp.color}
          source={comp.source}
          externalId={comp.externalId}
        />
      </div>
      <div className="card-body">
        <h3>{titleOf(comp)}</h3>
        <p className="card-meta">{metaLine(comp)}</p>
        <div className="card-flags">
          {comp.vatDeductible ? <span className="flag">Odpočet DPH</span> : null}
          {stale ? <span className="flag warn">Už nemusí být v inzerci</span> : null}
        </div>
      </div>
      <div className="card-aside">
        <div className="card-price">{formatCzk(comp.priceCzk)}</div>
        <p className="card-seen">
          {stale
            ? seen
              ? `Naposledy viděn ${seen}`
              : "Stáří nabídky neznáme"
            : seen
              ? `V inzerci k ${seen}`
              : "V našem vzorku"}
        </p>
        <SourceMark source={comp.source} href={stale ? null : comp.url} />
        {stale && comp.url ? (
          <a className="card-seen" href={comp.url} target="_blank" rel="noopener noreferrer">
            Zkusit původní odkaz
          </a>
        ) : null}
      </div>
    </article>
  );
}
