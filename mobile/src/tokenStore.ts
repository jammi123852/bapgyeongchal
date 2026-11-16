// 로그인 토큰 보관. 폰에서는 SecureStore(키체인/키스토어), 웹 개발 화면에서는 localStorage.
import * as SecureStore from 'expo-secure-store';
import { Platform } from 'react-native';

const KEY = 'solosafe.access_token';

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
