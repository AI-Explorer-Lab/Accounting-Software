import { get } from './http'

export interface HealthData {
  status: string
  environment: string
  version: string
}

export function fetchHealth() {
  return get<HealthData>('/api/v1/health')
}
