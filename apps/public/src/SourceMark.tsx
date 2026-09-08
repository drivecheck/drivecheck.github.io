import { sourceLabel } from "./format";

const LOGOS: Record<string, string> = {
  sauto: "./brands/sauto.svg",
  bazos: "./brands/bazos.svg",
  tipcars: "./brands/tipcars.svg",
  autobazar_eu: "./brands/autobazar_eu.svg",
  autoscout24: "./brands/autoscout24.svg",
  mobile_de: "./brands/mobile_de.svg",
};

export function SourceMark(props: {
  source: string;
  href?: string | null;
}) {
  const key = props.source.trim().toLowerCase();
  const label = sourceLabel(key);
  const logo = LOGOS[key];
  const inner = logo ? (
    <img src={logo} alt="" width={88} height={16} />
  ) : (
    <span>{label}</span>
  );

  if (props.href) {
    return (
      <a
        className="source-mark"
        href={props.href}
        target="_blank"
        rel="noopener noreferrer"
        title={`${label}: otevřít inzerát`}
        aria-label={`${label}: otevřít inzerát`}
      >
        {inner}
      </a>
    );
  }

  return (
    <span className="source-mark" title={label}>
      {inner}
    </span>
  );
}
