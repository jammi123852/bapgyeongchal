// SoloSafe 앱 진입점. 화면은 홈 ↔ 음식 추가 두 개뿐이라 상태로 전환한다.
// 로그인 화면 없음 (2026-09-30): 기기 키로 계정을 자동으로 받는다.
import { StatusBar } from 'expo-status-bar';
import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, Pressable, StyleSheet, Text, View } from 'react-native';

import { ApiError, api } from './src/api';
import { AddItemScreen } from './src/screens/AddItemScreen';
import { HomeScreen } from './src/screens/HomeScreen';
import { colors, radius, space } from './src/theme';
import { clearToken, getOrCreateDeviceKey, loadToken, saveToken } from './src/tokenStore';

type Screen = 'home' | 'add';

export default function App() {
  const [token, setToken] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const [startError, setStartError] = useState<string | null>(null);
  const [screen, setScreen] = useState<Screen>('home');
  // 등록 후 홈을 새로 불러오기 위한 key
  const [homeKey, setHomeKey] = useState(0);

  // 기기 키로 새 토큰을 받는다 (첫 실행이면 서버가 계정을 만든다).
  const connectDevice = useCallback(async () => {
    setReady(false);
    setStartError(null);
    try {
      const { access_token } = await api.device(await getOrCreateDeviceKey());
      await saveToken(access_token);
      setToken(access_token);
    } catch (e) {
      setStartError(e instanceof ApiError ? e.message : '시작하지 못했어요.');
    } finally {
      setReady(true);
    }
  }, []);

  useEffect(() => {
    loadToken().then((saved) => {
      if (saved) {
        setToken(saved);
        setReady(true);
      } else {
        connectDevice();
      }
    });
  }, [connectDevice]);

  // 토큰 만료(7일) 등으로 401 이 나면 같은 기기 키로 다시 받는다. 데이터는 그대로다.
  const reconnect = useCallback(async () => {
    await clearToken();
    setToken(null);
    await connectDevice();
  }, [connectDevice]);

  let content;
  if (!ready) {
    content = <ActivityIndicator style={{ flex: 1 }} color={colors.primary} />;
  } else if (!token) {
    content = (
      <View style={styles.center}>
        <Text style={styles.errorText}>{startError ?? '시작하지 못했어요.'}</Text>
        <Pressable accessibilityRole="button" onPress={connectDevice} style={styles.retry}>
          <Text style={styles.retryText}>다시 시도</Text>
        </Pressable>
      </View>
    );
  } else if (screen === 'add') {
    content = (
      <AddItemScreen
        token={token}
        onCancel={() => setScreen('home')}
        onDone={() => {
          setHomeKey((k) => k + 1);
          setScreen('home');
        }}
      />
    );
  } else {
    content = (
      <HomeScreen
        key={homeKey}
        token={token}
        onAdd={() => setScreen('add')}
        onUnauthorized={reconnect}
      />
    );
  }

  return (
    <View style={styles.root}>
      {content}
      <StatusBar style="dark" />
    </View>
  );
}

const styles = StyleSheet.create({
  root: { flex: 1, backgroundColor: colors.bg },
  center: { flex: 1, alignItems: 'center', justifyContent: 'center', padding: space.lg, gap: space.md },
  errorText: { fontSize: 15, color: colors.text, textAlign: 'center' },
  retry: { paddingHorizontal: space.lg, paddingVertical: space.sm, borderRadius: radius.sm, backgroundColor: colors.primary },
  retryText: { color: colors.primaryText, fontSize: 15, fontWeight: '600' },
});
