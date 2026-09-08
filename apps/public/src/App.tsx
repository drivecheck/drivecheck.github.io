import { useEffect, useMemo, useState } from "react";
import type { AppraisalRequest, AppraisalResult, CompListing } from "@drivecheck/shared";
import { priceVehicle } from "@drivecheck/pricing";
import initSqlJs, { type Database, type SqlJsStatic } from "sql.js";
import wasmUrl from "sql.js/dist/sql-wasm.wasm?url";
import { CompCard } from "./CompCard";
import {
  askGapSentence,
  confidenceChip,
  confidenceCs,
  formatCzk,
  formatDateCs,
  isStaleListing,
  turnoverZoneCs,
} from "./format";
import {
  clearSession,
  readSessionPassword,
  unlockSnapshot,
} from "./gate";
import { catalogMakes, catalogModels, sqliteListingStore } from "./sqlite-store";

type Meta = { generated_at?: string };

const COMP_STEP = 8;
const FUELS = ["", "Benzín", "Nafta", "Hybrid", "Elektro", "LPG", "CNG", "Benzín+LPG"];
const GEARS = ["", "Manuální", "Automatická", "DSG / dvojspojka", "CVT"];
const BODIES = ["", "Hatchback", "Sedan", "Kombi", "SUV", "MPV", "Coupe", "Cabrio", "Pick-up", "Dodávka"];

let sqlPromise: Promise<SqlJsStatic> | null = null;

function loadSql(): Promise<SqlJsStatic> {
  sqlPromise ??= initSqlJs({ locateFile: () => wasmUrl });
  return sqlPromise;
}

function sortComps(comps: CompListing[]): CompListing[] {
  return [...comps].sort((a, b) => {
    const aStale = isStaleListing(a.lastSeenAt) ? 1 : 0;
    const bStale = isStaleListing(b.lastSeenAt) ? 1 : 0;
    return aStale - bStale;
  });
}

function Login(props: {
  error: string | null;
  pending: boolean;
  onSubmit: (password: string) => void;
}) {
  const [password, setPassword] = useState("");
  return (
    <main className="gate">
      <div className="gate-card">
        <p className="gate-brand">Drivecheck</p>
        <h1>Přihlášení</h1>
        <p className="lede">Interní odhad ceny — stejný výpočet jako v hlavním nástroji.</p>
        <form
          onSubmit={(event) => {
            event.preventDefault();
            props.onSubmit(password);
          }}
        >
          <label className="field">
            Heslo společnosti
            <input
              type="password"
              name="company-password"
              autoComplete="current-password"
              spellCheck={false}
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              required
            />
          </label>
          {props.error ? <p className="error">{props.error}</p> : null}
          <div className="form-actions">
            <button className="primary" type="submit" disabled={props.pending}>
              {props.pending ? "Načítám trh…" : "Přihlásit se"}
            </button>
          </div>
          {props.pending ? (
            <p className="gate-hint">První otevření stáhne šifrovaný snapshot trhu. Další návštěvy jdou z cache.</p>
          ) : null}
        </form>
      </div>
    </main>
  );
}

export function App() {
  const [password, setPassword] = useState(readSessionPassword());
  const [db, setDb] = useState<Database | null>(null);
  const [meta, setMeta] = useState<Meta | null>(null);
  const [gateError, setGateError] = useState<string | null>(null);
  const [pendingGate, setPendingGate] = useState(false);
  const [offline, setOffline] = useState(false);

  const [make, setMake] = useState("");
  const [model, setModel] = useState("");
  const [year, setYear] = useState("");
  const [km, setKm] = useState("");
  const [more, setMore] = useState(false);
  const [fuel, setFuel] = useState("");
  const [transmission, setTransmission] = useState("");
  const [body, setBody] = useState("");
  const [powerKw, setPowerKw] = useState("");
  const [result, setResult] = useState<AppraisalResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [compLimit, setCompLimit] = useState(COMP_STEP);

  const store = useMemo(() => (db ? sqliteListingStore(db) : null), [db]);
  const makes = useMemo(() => (db ? catalogMakes(db) : []), [db]);
  const models = useMemo(() => (db ? catalogModels(db, make) : []), [db, make]);

  async function openWithPassword(value: string) {
    setPendingGate(true);
    setGateError(null);
    try {
      const unlocked = await unlockSnapshot(value);
      const SQL = await loadSql();
      setDb(new SQL.Database(unlocked.sqliteBytes));
      setMeta(unlocked.meta);
      setPassword(value);
    } catch (err) {
      setGateError(err instanceof Error ? err.message : "Neplatné heslo.");
      setOffline(true);
    } finally {
      setPendingGate(false);
    }
  }

  useEffect(() => {
    if (password && !db) {
      void openWithPassword(password);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (!db || !store) {
    return (
      <Login
        error={gateError}
        pending={pendingGate}
        onSubmit={(value) => void openWithPassword(value)}
      />
    );
  }

  async function onCalculate() {
    setBusy(true);
    setError(null);
    try {
      const yearNum = Number(year);
      const kmNum = Number(km);
      if (!make.trim() || !model.trim() || !Number.isFinite(yearNum) || yearNum < 1980) {
        setError("Vyplňte značku, model a rok.");
        return;
      }
      const input: AppraisalRequest = {
        mode: "detailed",
        make: make.trim(),
        model: model.trim(),
        year: yearNum,
        mileageKm: Number.isFinite(kmNum) ? kmNum : 0,
        fuel: fuel.trim() || undefined,
        transmission: transmission.trim() || undefined,
        body: body.trim() || undefined,
        powerKw: powerKw.trim() ? Number(powerKw) : undefined,
      };
      const next = await priceVehicle(input, store);
      setResult(next);
      setCompLimit(COMP_STEP);
    } catch {
      setError("Výpočet se nepodařil. Zkuste počítač, pokud jste na starém telefonu.");
    } finally {
      setBusy(false);
    }
  }

  const snapshotDay = formatDateCs(meta?.generated_at);
  const comps = result ? sortComps(result.comps) : [];
  const staleCount = comps.filter((comp) => isStaleListing(comp.lastSeenAt)).length;
  const visible = comps.slice(0, compLimit);
  const daysOnMarket = result?.liquidity.medianDaysOnMarket ?? null;
  const zone = turnoverZoneCs(daysOnMarket);
  const gap = result ? askGapSentence(result.askToValueGapPct) : null;

  return (
    <div>
      <header className="app-header">
        <div className="app-header-inner">
          <div className="wordmark">Drivecheck</div>
          <div className="header-meta">
            <span className="snapshot-chip">{snapshotDay ? `Trh k ${snapshotDay}` : "Tržní snapshot"}</span>
            <button
              className="linkish"
              type="button"
              onClick={() => {
                clearSession();
                db.close();
                setDb(null);
                setPassword(null);
                setResult(null);
              }}
            >
              Odhlásit
            </button>
          </div>
        </div>
      </header>

      <main className="shell">
        <p className="page-kicker">Odhad</p>
        <h1 className="page-title">Kolik auto na trhu opravdu stojí</h1>
        <p className="page-lede">
          Stačí značka, model a rok. Čísla počítá stejný engine jako interní Drivecheck — bez
          fotek inzerátů, s aktuálním snapshotem trhu.
        </p>

        {offline ? <div className="banner">Používám uložený snapshot (offline).</div> : null}

        <form
          className="panel"
          onSubmit={(event) => {
            event.preventDefault();
            void onCalculate();
          }}
        >
          <div className="stack">
            <div className="row">
              <label className="field">
                Značka
                <input
                  value={make}
                  list="make-list"
                  autoComplete="off"
                  placeholder="např. Škoda"
                  onChange={(event) => setMake(event.target.value)}
                />
              </label>
              <label className="field">
                Model
                <input
                  value={model}
                  list="model-list"
                  autoComplete="off"
                  placeholder="např. Octavia"
                  onChange={(event) => setModel(event.target.value)}
                />
              </label>
            </div>
            <div className="row">
              <label className="field">
                Rok
                <input
                  value={year}
                  inputMode="numeric"
                  placeholder="2019"
                  onChange={(event) => setYear(event.target.value)}
                />
              </label>
              <label className="field">
                Nájezd (km)
                <input
                  value={km}
                  inputMode="numeric"
                  placeholder="120000"
                  onChange={(event) => setKm(event.target.value)}
                />
              </label>
            </div>
          </div>
          <datalist id="make-list">
            {makes.map((item) => (
              <option key={item} value={item} />
            ))}
          </datalist>
          <datalist id="model-list">
            {models.map((item) => (
              <option key={item} value={item} />
            ))}
          </datalist>

          {more ? (
            <div className="more-fields row-4">
              <label className="field">
                Palivo
                <select value={fuel} onChange={(event) => setFuel(event.target.value)}>
                  {FUELS.map((item) => (
                    <option key={item || "any"} value={item}>
                      {item || "Nezáleží"}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                Převodovka
                <select value={transmission} onChange={(event) => setTransmission(event.target.value)}>
                  {GEARS.map((item) => (
                    <option key={item || "any"} value={item}>
                      {item || "Nezáleží"}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                Karoserie
                <select value={body} onChange={(event) => setBody(event.target.value)}>
                  {BODIES.map((item) => (
                    <option key={item || "any"} value={item}>
                      {item || "Nezáleží"}
                    </option>
                  ))}
                </select>
              </label>
              <label className="field">
                Výkon (kW)
                <input
                  value={powerKw}
                  inputMode="numeric"
                  placeholder="volitelné"
                  onChange={(event) => setPowerKw(event.target.value)}
                />
              </label>
            </div>
          ) : null}

          <div className="form-actions">
            <button className="primary" type="submit" disabled={busy}>
              {busy ? "Počítám…" : "Spočítat odhad"}
            </button>
            <button className="ghost" type="button" onClick={() => setMore((v) => !v)}>
              {more ? "Méně parametrů" : "Více parametrů"}
            </button>
          </div>
          {error ? <p className="error">{error}</p> : null}
        </form>

        {result ? (
          <section className="results">
            <p className="subject-line">
              {[make, model, year].filter(Boolean).join(" ")}
            </p>
            <div className="plates">
              <div className="plate emphasize">
                <div className="label">Reálná hodnota</div>
                <div className="value">{formatCzk(result.fairValueCzk)}</div>
                <div className="footer">
                  {result.fairValueProvenance === "closed_sales"
                    ? "Ověřeno reálnými prodeji"
                    : "Odhad skutečné transakce"}
                  {gap ? `. ${gap}` : ""}
                </div>
              </div>
              <div className="plate">
                <div className="label">Inzeráty žádají</div>
                <div className="value">{formatCzk(result.priceTypicalCzk)}</div>
                <div className="footer">
                  Většina nabídek: {formatCzk(result.priceLowCzk)} – {formatCzk(result.priceHighCzk)}
                </div>
              </div>
              <div className="plate">
                <div className="label">Vzorek</div>
                <div className="value">
                  {result.liveAskCount.toLocaleString("cs-CZ")}
                  <span className={`chip ${confidenceChip(result.confidence)}`}>
                    {confidenceCs(result.confidence)} jistota
                  </span>
                </div>
                <div className="footer">{result.confidenceNoteCs}</div>
              </div>
              <div className="plate">
                <div className="label">
                  {daysOnMarket != null ? "Dní v nabídce" : "Zmizelé inzeráty"}
                </div>
                <div className="value">
                  {daysOnMarket != null
                    ? `${daysOnMarket.toLocaleString("cs-CZ")} dní`
                    : result.soldProxyCount.toLocaleString("cs-CZ")}
                  {zone ? <span className="chip">{zone}</span> : null}
                </div>
                <div className="footer">
                  {result.liquidity.noteCs ||
                    "Stažený inzerát není vždy prodej — vstupuje jen jako indicie."}
                </div>
              </div>
            </div>

            {result.warningsCs.length > 0 ? (
              <ul className="warn-list">
                {result.warningsCs.map((warning) => (
                  <li key={warning}>{warning}</li>
                ))}
              </ul>
            ) : null}

            <div className="section-head">
              <h2>Srovnatelné nabídky</h2>
              <p>
                {staleCount > 0
                  ? `${staleCount.toLocaleString("cs-CZ")} z ${comps.length.toLocaleString("cs-CZ")} už nemusí viset — do výpočtu ale vstupují.`
                  : `${comps.length.toLocaleString("cs-CZ")} v aktuálním vzorku`}
              </p>
            </div>
            <div className="comp-list">
              {visible.map((comp) => (
                <CompCard key={`${comp.source}-${comp.externalId}`} comp={comp} />
              ))}
            </div>
            {compLimit < comps.length ? (
              <button
                className="ghost load-more"
                type="button"
                onClick={() => setCompLimit((n) => n + COMP_STEP)}
              >
                Další nabídky ({comps.length - compLimit})
              </button>
            ) : null}

            <details className="details">
              <summary>Metodika</summary>
              <p>
                Reálná hodnota slučuje živé české inzeráty s indiciemi o prodeji ze smazaných
                inzerátů. Smazaný inzerát není vždy prodej. Importní portály do tohoto čísla
                nevstupují. Fotky z bazarů nenačítáme — barva karoserie je jen tón ikony.
              </p>
            </details>
          </section>
        ) : null}
      </main>
    </div>
  );
}
