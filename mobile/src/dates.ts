// 날짜는 시각 없는 'YYYY-MM-DD' 로 다룬다 (백엔드 expiry_date 가 DATE 타입).

function pad(n: number): string {
  return String(n).padStart(2, '0');
}

export function toIsoDate(d: Date): string {
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
}

export function daysFromToday(offset: number): string {
  const d = new Date();
  d.setDate(d.getDate() + offset);
  return toIsoDate(d);
}

export function isValidIsoDate(value: string): boolean {
  if (!/^\d{4}-\d{2}-\d{2}$/.test(value)) return false;
  const [y, m, d] = value.split('-').map(Number);
  const date = new Date(y, m - 1, d);
  return date.getFullYear() === y && date.getMonth() === m - 1 && date.getDate() === d;
}

// 목록용 짧은 표시. 판정 표현(상함 등)은 쓰지 않는다.
export function dDayLabel(expiry: string | null): string {
  if (!expiry) return '기한 없음';
  const [y, m, d] = expiry.split('-').map(Number);
  const target = new Date(y, m - 1, d);
  const today = new Date();
  today.setHours(0, 0, 0, 0);
  const diff = Math.round((target.getTime() - today.getTime()) / 86_400_000);
  if (diff < 0) return `D+${-diff}`;
  if (diff === 0) return 'D-DAY';
  return `D-${diff}`;
}
