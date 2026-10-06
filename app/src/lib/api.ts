/**
 * Data access for the dashboard.
 *
 * Read-only data comes from the precomputed static files in /public/data
 * (exported by `python -m src.api.export`), so the app works with no backend.
 * Alert actions go through /api/proxy → FastAPI. With no backend configured,
 * they fall back to an explicit offline mode: nothing is sent, the action is
 * logged in this browser only, and the UI says so.
 */

export type Transect = {
  id: string;
  bank: "W" | "E";
  chainage_m: number;
  lon: number;
  lat: number;
  start: [number, number];
  end: [number, number];
  near_bridge: boolean;
};

export type Reach = {
  name: string;
  bbox: [number, number, number, number];
  s_range: [number, number];
  transect_spacing_m: number;
  bridge: [number, number][];
  baselines: Record<string, [number, number][]>;
  transects: Transect[];
  image_bounds: [number, number, number, number] | null; // [south, west, north, east]
};

export type Pass = {
  pass_id: string;
  date: string;
  platform: string;
  otsu_ok: boolean;
  t_vv: number | null;
  water_area_km2: number | null;
  stage_km2: number | null;
  valid_share: number | null;
  image: string | null;
};

export type Banks = { passes: string[]; transects: string[]; pos: (number | null)[][] };

export type Tier = "none" | "monitor" | "watch" | "warning_eligible";

export type Prediction = {
  id: string;
  p: number;
  rank: number;
  b0_rank: number;
  tier: Tier;
  ret28: number | null;
  ret84: number | null;
  ret365: number | null;
  last: number | null;
  /** retreat on this pass at least the label threshold (Monitor) */
  mon: boolean;
  pos: number | null;
  y: 0 | 1 | null;
  retreat: number | null;
  major: 0 | 1 | null;
  target: string | null;
  reasons: string[] | null;
};

export type PredIndex = {
  date: string;
  year: number;
  split: "val" | "test";
  n: number;
  has_outcome: boolean;
  /** segments that are Warning-eligible on this date */
  n_warning?: number;
  p20_model: number | null;
  p20_persistence: number | null;
  positives: number | null;
}[];

export type Summary = {
  precision_at_k: number;
  precision_at_k_monsoon: number;
  n_dates: number;
  n_dates_monsoon: number;
  pr_auc: number;
  brier?: number;
  major: { hits: number; total: number; recall: number };
};

export type CI = { mean: number; lo: number; hi: number; n_dates: number; block?: number; n_boot?: number };

export type Metrics = {
  mask_validation?: {
    n_pairs: number;
    iou_median: number;
    iou_min: number;
    iou_max: number;
    bank_error_median_m: number;
    bank_error_p90_m: number;
    bank_error_mean_signed_m: number;
    n_transect_comparisons: number;
    label_threshold_m: number;
    s2_tile: string;
    max_days_apart: number;
  };
  label_stats?: {
    threshold_m: number;
    confirm_days: number;
    train: { rows: number; forecast_dates: number; positive_rate: number; major_events: number };
    val: { rows: number; forecast_dates: number; positive_rate: number; major_events: number };
    test: { rows: number; forecast_dates: number; positive_rate: number; major_events: number };
  };
  test_results?: {
    generated: string;
    test_years: number[];
    threshold_m: number;
    detection_coverage: { passes_in_catalog: number; passes_processed: number };
    temporal: {
      rows: number;
      forecast_dates: number;
      positive_rate: number;
      M1: Summary;
      B0_persistence: Summary;
      B1_history: Summary;
      M1_minus_B0: { all_dates: CI; monsoon: CI };
      M1_minus_B1: { all_dates: CI; monsoon: CI };
      reliability_M1: { bin_lo: number; bin_hi: number; n: number; mean_pred: number; observed: number }[];
      reliability_B0: { bin_lo: number; bin_hi: number; n: number; mean_pred: number; observed: number }[];
      per_year: Record<string, { M1: Summary; B0: Summary }>;
    };
    spatial: {
      train_segments: number;
      test_segments: number;
      M1: Summary;
      B0_persistence: Summary;
      M1_minus_B0: { all_dates: CI; monsoon: CI };
    };
    success_levels: { minimum: boolean; good: boolean; strong: boolean };
  };
  ablation?: Record<string, any>;
  model?: { params: Record<string, number>; num_boost_round: number; features: string[]; train_rows: number; val_precision_at_20: number };
  tier_thresholds?: { watch_top_k: number; warning_min_prob: number; warning_min_last_retreat_m: number; source: string };
  importance?: { feature: string; mean_abs_shap: number }[];
  claims?: Claim[];
  timing?: Record<string, number>;
};

export type Claim = {
  claim: string;
  status: "Measured" | "Not met" | "Target" | "Not built" | "Dropped";
  value?: string;
  how: string;
};

const cache = new Map<string, Promise<any>>();

async function getStatic<T>(path: string): Promise<T> {
  if (!cache.has(path)) {
    cache.set(
      path,
      fetch(`/data/${path}`).then((r) => {
        if (!r.ok) throw new Error(`${path}: ${r.status}`);
        return r.json();
      }),
    );
  }
  return cache.get(path)!;
}

export const api = {
  reach: () => getStatic<Reach>("reach.json"),
  passes: () => getStatic<Pass[]>("passes.json"),
  banks: (year: number) => getStatic<Banks>(`banks/${year}.json`),
  predIndex: () => getStatic<PredIndex>("predictions/index.json"),
  predictions: (date: string) => getStatic<Prediction[]>(`predictions/${date}.json`),
  metrics: () => getStatic<Metrics>("metrics.json"),
};

// ------------------------------------------------------------------ alerts

export type AlertDraft = {
  alert_id: string;
  status: "awaiting_approval" | "sent" | "logged_not_sent" | "rejected" | "offline_logged";
  alert: { segment_ids: string[]; forecast_date: string; place: string; probability: number };
  sms: string;
  voice_bn: string;
  voice_en: string;
  disclaimer: string;
  created: string;
  offline?: boolean;
  dispatch?: { gateway: string; messages: { kind: string; to: string; status: string | number }[] };
};

async function proxy<T>(path: string, body?: unknown): Promise<T> {
  const r = await fetch(`/api/proxy/${path}`, {
    method: body ? "POST" : "GET",
    headers: body ? { "content-type": "application/json" } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  });
  if (r.status === 503) throw new OfflineError();
  if (!r.ok) {
    const j = await r.json().catch(() => ({}));
    throw new Error(j.detail ?? `${r.status}`);
  }
  return r.json();
}

export class OfflineError extends Error {
  constructor() {
    super("No backend configured (offline demo mode)");
  }
}

export const SMS_BN =
  "নদীভাঙন সতর্কবার্তা: আগামী কয়েক সপ্তাহে {place} এলাকার নদীতীরে ভাঙনের ঝুঁকি বেশি। মালামাল ও গবাদিপশু নিরাপদ স্থানে সরানোর প্রস্তুতি নিন। ইউনিয়ন পরিষদের নির্দেশনা মেনে চলুন।";
export const VOICE_BN =
  "এটি নদীভাঙন সতর্কবার্তা। আগামী কয়েক সপ্তাহে {place} এলাকার নদীতীরে ভাঙনের ঝুঁকি বেশি। ঘরের মালামাল ও গবাদিপশু নিরাপদ স্থানে সরানোর প্রস্তুতি নিন এবং ইউনিয়ন পরিষদের নির্দেশনা মেনে চলুন।";
export const VOICE_EN =
  "This is a riverbank erosion warning. Erosion risk is high along the bank at {place} in the coming weeks. Prepare to move belongings and livestock to a safe place, and follow the union parishad's guidance.";
export const DISCLAIMER =
  "Advisory decision support. The absence of an alert does not mean a bank is safe. Public warnings are issued under an official's authority.";

export const alertsApi = {
  async draft(forecast_date: string, segment_ids: string[], place: string, predictions: Prediction[]): Promise<AlertDraft> {
    try {
      return await proxy<AlertDraft>("alerts/draft", { forecast_date, segment_ids, place });
    } catch (e) {
      if (!(e instanceof OfflineError)) throw e;
      const rows = predictions.filter((p) => segment_ids.includes(p.id) && p.tier === "warning_eligible");
      if (!rows.length) throw new Error("None of these segments meets the Warning criteria.");
      return {
        alert_id: `offline-${Date.now().toString(36)}`,
        status: "awaiting_approval",
        alert: { segment_ids: rows.map((r) => r.id), forecast_date, place, probability: Math.max(...rows.map((r) => r.p)) },
        sms: SMS_BN.replace("{place}", place),
        voice_bn: VOICE_BN.replace("{place}", place),
        voice_en: VOICE_EN.replace("{place}", place),
        disclaimer: DISCLAIMER,
        created: new Date().toISOString(),
        offline: true,
      };
    }
  },
  async approve(draft: AlertDraft, official_name: string, role: string, note = ""): Promise<AlertDraft> {
    if (draft.offline) {
      const rec: AlertDraft = { ...draft, status: "offline_logged" };
      try {
        const log = JSON.parse(localStorage.getItem("nadinet.alerts") ?? "[]");
        log.unshift({ ...rec, approval: { official_name, role, note, at: new Date().toISOString() } });
        localStorage.setItem("nadinet.alerts", JSON.stringify(log.slice(0, 50)));
      } catch {
        /* storage unavailable: the on-screen record is all there is */
      }
      return rec;
    }
    return proxy<AlertDraft>(`alerts/${draft.alert_id}/approve`, { official_name, role, note });
  },
  async health(): Promise<{ status: string; gateway: string } | null> {
    try {
      return await proxy("health");
    } catch {
      return null;
    }
  },
};
