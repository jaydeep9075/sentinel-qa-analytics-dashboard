export interface KPI {
  total: number;
  passed: number;
  failed: number;
  avg_duration: number;
}

export interface ModuleStats {
  module: string;
  passed: number;
  failed: number;
}

export interface Trend {
  buildOrder: number;
  passed: number;
  failed: number;
}
