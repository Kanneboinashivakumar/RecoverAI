const API_BASE = '/api';
const FETCH_TIMEOUT = 120_000; // 120s for long-running experiment endpoints

async function fetchApi<T>(path: string, options?: RequestInit): Promise<T> {
  const controller = new AbortController();
  const timeoutId = setTimeout(() => controller.abort(), FETCH_TIMEOUT);

  try {
    const res = await fetch(`${API_BASE}${path}`, {
      ...options,
      signal: controller.signal,
      headers: {
        'Content-Type': 'application/json',
        ...options?.headers,
      },
    });

    if (!res.ok) {
      const body = await res.text();
      throw new Error(`API ${res.status}: ${body}`);
    }

    return await res.json();
  } finally {
    clearTimeout(timeoutId);
  }
}

// ---- Dashboard ----
export interface FailureBreakdown {
  failure_code: string;
  count: number;
}

export interface TrendPoint {
  date: string;
  events: number;
  recovered: number;
}

export interface OverviewData {
  incremental_recovered: number;
  incremental_recovered_label: string;
  experiment_seed: number | null;
  experiment_batch_size: number | null;
  experiment_run_at: string | null;
  total_events: number;
  total_recovered: number;
  recovery_rate: number;
  escalation_count: number;
  blocked_count: number;
  failure_breakdown: FailureBreakdown[];
  trend_data: TrendPoint[];
}

export function getOverview(): Promise<OverviewData> {
  return fetchApi<OverviewData>('/dashboard/overview');
}

// ---- Health ----
export interface HealthData {
  status: string;
  database: string;
}

export function getHealth(): Promise<HealthData> {
  return fetchApi<HealthData>('/../health');
}
