import type { DealerAdvice } from "@drivecheck/shared";
import { roundToThousand } from "./stats";

export const DEFAULT_MARGIN_PCT = 8;
export const DEFAULT_REWORK_BUFFER_CZK = 0;

export function computeDealerAdvice(opts: {
  fairValueCzk: number | null;
  marginPct?: number | null;
  reworkBufferCzk?: number | null;
}): DealerAdvice {
  const marginPct =
    opts.marginPct != null && Number.isFinite(opts.marginPct)
      ? Math.min(40, Math.max(0, opts.marginPct))
      : DEFAULT_MARGIN_PCT;
  const reworkBufferCzk =
    opts.reworkBufferCzk != null && Number.isFinite(opts.reworkBufferCzk)
      ? Math.max(0, Math.round(opts.reworkBufferCzk))
      : DEFAULT_REWORK_BUFFER_CZK;

  if (opts.fairValueCzk == null || !Number.isFinite(opts.fairValueCzk)) {
    return {
      buyInCzk: null,
      listAtCzk: null,
      commissionCzk: null,
      marginPct,
      reworkBufferCzk,
    };
  }

  const listAtCzk = roundToThousand(opts.fairValueCzk);
  const buyInCzk = roundToThousand(
    opts.fairValueCzk * (1 - marginPct / 100) - reworkBufferCzk,
  );
  const commissionCzk =
    listAtCzk != null && buyInCzk != null ? listAtCzk - buyInCzk : null;

  return {
    buyInCzk,
    listAtCzk,
    commissionCzk,
    marginPct,
    reworkBufferCzk,
  };
}
