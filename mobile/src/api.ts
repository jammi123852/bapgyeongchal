// SoloSafe 백엔드 API 클라이언트.
// 실제 폰에서 테스트할 때는 EXPO_PUBLIC_API_URL 을 PC 의 LAN 주소로 지정한다.
// 예: EXPO_PUBLIC_API_URL=http://<PC-IP>:8000 npx expo start

export const API_URL = process.env.EXPO_PUBLIC_API_URL ?? 'http://localhost:8000';

export type ActionType = 'CONSUMED' | 'PARTIALLY_CONSUMED' | 'DISCARDED' | 'MARKED_EXPIRED';
export type StorageType = 'FRIDGE' | 'FREEZER' | 'PANTRY';

export interface InventoryItem {
  id: string;
  custom_name: string;
  expiry_date: string | null;
  purchase_date: string | null;
  opened_date: string | null;
  storage_type: StorageType | null;
  remaining_ratio: string | null;
  status: string;
}

export interface Reason {
  code: string;
  n: number | null;
  text: string;
}

export interface EatFirstEntry {
  recommendation_id: string;
  rank: number;
  reasons: Reason[];
  item: InventoryItem;
}

export interface EatFirstBatch {
  batch_id: string;
  algorithm_version: string;
  entries: EatFirstEntry[];
}

export interface NewItem {
  custom_name: string;
  expiry_date?: string | null;
  opened_date?: string | null;
  storage_type?: StorageType | null;
}

export class ApiError extends Error {
  constructor(
    public status: number,
    message: string,
  ) {
    super(message);
  }
}

function errorMessage(body: unknown, status: number): string {
  const detail = (body as { detail?: unknown } | null)?.detail;
  if (typeof detail === 'string') return detail;
  if (Array.isArray(detail) && detail.length > 0) {
    const first = detail[0] as { msg?: string };
    if (first.msg) return first.msg.replace(/^Value error, /, '');
  }
  return `요청에 실패했어요 (${status})`;
}

async function request<T>(path: string, init: RequestInit & { token?: string | null } = {}): Promise<T> {
  const { token, headers, ...rest } = init;
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      ...rest,
      headers: {
        'Content-Type': 'application/json',
        ...(token ? { Authorization: `Bearer ${token}` } : {}),
        ...headers,
      },
    });
  } catch {
    throw new ApiError(0, '서버에 연결할 수 없어요. 서버가 켜져 있는지 확인해 주세요.');
  }
  if (response.status === 204) return undefined as T;
  const body = await response.json().catch(() => null);
  if (!response.ok) throw new ApiError(response.status, errorMessage(body, response.status));
  return body as T;
}

export const api = {
  signup: (email: string, password: string) =>
    request<{ access_token: string }>('/auth/signup', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),
  login: (email: string, password: string) =>
    request<{ access_token: string }>('/auth/login', {
      method: 'POST',
      body: JSON.stringify({ email, password }),
    }),
  logout: (token: string) => request<void>('/auth/logout', { method: 'POST', token }),
  listItems: (token: string) => request<InventoryItem[]>('/inventory', { token }),
  createItem: (token: string, item: NewItem) =>
    request<InventoryItem>('/inventory', { method: 'POST', body: JSON.stringify(item), token }),
  act: (
    token: string,
    itemId: string,
    actionType: ActionType,
    options: { remainingRatio?: string; recommendationId?: string } = {},
  ) =>
    request<unknown>(`/inventory/${itemId}/actions`, {
      method: 'POST',
      token,
      body: JSON.stringify({
        action_type: actionType,
        remaining_ratio: options.remainingRatio ?? null,
        recommendation_id: options.recommendationId ?? null,
      }),
    }),
  eatFirst: (token: string, limit = 3) =>
    request<EatFirstBatch>(`/eat-first?limit=${limit}`, { method: 'POST', token }),
  markShown: (token: string, batchId: string) =>
    request<void>(`/eat-first/${batchId}/shown`, { method: 'POST', token }),
};
