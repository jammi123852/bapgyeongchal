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

export interface OcrCandidate {
  date: string;
  precision: 'day' | 'month';
  raw: string;
  near_keyword: boolean;
  ambiguous: boolean;
  alternatives: string[]; // 같은 표기를 다르게 읽은 날짜들 (예: 일/월/연 vs 연/월/일)
}

export interface OcrResult {
  best: OcrCandidate | null;
  candidates: OcrCandidate[];
  lines: string[];
  seconds: number;
}

// 사진 1장. 폰에서는 uri, 웹에서는 File 객체를 쓴다.
export interface PhotoInput {
  uri: string;
  mimeType?: string | null;
  fileName?: string | null;
  file?: Blob | null;
}

export interface NewItem {
  custom_name: string;
  expiry_date?: string | null;
  expiry_source?: 'MANUAL' | 'OCR';
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
  // FormData(사진 업로드)는 브라우저/RN 이 boundary 포함 Content-Type 을 직접 붙인다.
  const isForm = typeof FormData !== 'undefined' && rest.body instanceof FormData;
  let response: Response;
  try {
    response = await fetch(`${API_URL}${path}`, {
      ...rest,
      headers: {
        ...(isForm ? {} : { 'Content-Type': 'application/json' }),
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
  // 기기 키로 계정 받기 (없으면 서버가 만든다). 로그인 화면 대신 앱 시작 시 호출.
  device: (deviceKey: string) =>
    request<{ access_token: string }>('/auth/device', {
      method: 'POST',
      body: JSON.stringify({ device_key: deviceKey }),
    }),
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
  readExpiry: (token: string, photo: PhotoInput) => {
    const form = new FormData();
    const type = photo.mimeType ?? 'image/jpeg';
    const name = photo.fileName ?? 'photo.jpg';
    if (photo.file) {
      form.append('image', photo.file, name);
    } else {
      // React Native 의 FormData 파일 표기
      form.append('image', { uri: photo.uri, name, type } as unknown as Blob);
    }
    return request<OcrResult>('/ocr/expiry', { method: 'POST', body: form, token });
  },
  markShown: (token: string, batchId: string) =>
    request<void>(`/eat-first/${batchId}/shown`, { method: 'POST', token }),
};
