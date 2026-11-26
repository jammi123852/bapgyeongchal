// 토큰·기기 키 보관. 폰에서는 SecureStore(키체인/키스토어), 웹 개발 화면에서는 localStorage.
// 로그인 화면은 없다 (2026-09-30). 앱이 처음 켜질 때 기기 키를 만들고 그 키로 계정을 받는다.
import * as Crypto from 'expo-crypto';
import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';

const KEY = 'solosafe.access_token';
const DEVICE_KEY = 'solosafe.device_key';

async function readItem(key: string): Promise<string | null> {
  if (Platform.OS === 'web') {
    try {
      return window.localStorage.getItem(key);
    } catch {
      return null;
    }
  }
  return SecureStore.getItemAsync(key);
}

async function writeItem(key: string, value: string): Promise<void> {
  if (Platform.OS === 'web') {
    try {
      window.localStorage.setItem(key, value);
    } catch {
      // 저장 불가(사생활 보호 모드 등)면 이번 실행 동안만 유지
    }
    return;
  }
  await SecureStore.setItemAsync(key, value);
}

// 기기 키 = 이 기기의 계정. 지우면 새 계정이 생기고 기존 냉장고 목록은 이 기기에서 볼 수 없다.
export async function getOrCreateDeviceKey(): Promise<string> {
  const existing = await readItem(DEVICE_KEY);
  if (existing) return existing;
  const bytes = Crypto.getRandomBytes(32);
  const key = Array.from(bytes, (b) => b.toString(16).padStart(2, '0')).join('');
  await writeItem(DEVICE_KEY, key);
  return key;
}

export async function loadToken(): Promise<string | null> {
  if (Platform.OS === 'web') {
    try {
      return window.localStorage.getItem(KEY);
    } catch {
      return null;
    }
  }
  return SecureStore.getItemAsync(KEY);
}

export async function saveToken(token: string): Promise<void> {
  if (Platform.OS === 'web') {
    try {
      window.localStorage.setItem(KEY, token);
    } catch {
      // 저장 불가(사생활 보호 모드 등)면 이번 실행 동안만 로그인 유지
    }
    return;
  }
  await SecureStore.setItemAsync(KEY, token);
}

export async function clearToken(): Promise<void> {
  if (Platform.OS === 'web') {
    try {
      window.localStorage.removeItem(KEY);
    } catch {
      // 무시
    }
    return;
  }
  await SecureStore.deleteItemAsync(KEY);
}
