export interface ApiResponse<T> {
  success: boolean
  data: T | null
  message: string
  request_id: string | null
}

async function request<T>(path: string, init?: RequestInit): Promise<ApiResponse<T>> {
  const response = await fetch(path, init)

  if (!response.ok) {
    const errorBody = (await response.json().catch(() => null)) as { message?: string } | null
    throw new Error(errorBody?.message ?? `Request failed with status ${response.status}`)
  }

  return response.json() as Promise<ApiResponse<T>>
}

export function get<T>(path: string): Promise<ApiResponse<T>> {
  return request<T>(path, {
    headers: { Accept: 'application/json' },
  })
}

export function post<T, Body>(path: string, body: Body): Promise<ApiResponse<T>> {
  return request<T>(path, {
    method: 'POST',
    headers: {
      Accept: 'application/json',
      'Content-Type': 'application/json',
    },
    body: JSON.stringify(body),
  })
}
