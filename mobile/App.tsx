// SoloSafe 앱 진입점. 화면은 로그인 → 홈 ↔ 음식 추가 세 개뿐이라 상태로 전환한다.
import { StatusBar } from 'expo-status-bar';
import { useCallback, useEffect, useState } from 'react';
import { ActivityIndicator, StyleSheet, View } from 'react-native';

import { api } from './src/api';
import { AddItemScreen } from './src/screens/AddItemScreen';
import { AuthScreen } from './src/screens/AuthScreen';
import { HomeScreen } from './src/screens/HomeScreen';
import { colors } from './src/theme';
import { clearToken, loadToken, saveToken } from './src/tokenStore';

type Screen = 'home' | 'add';

export default function App() {
  const [token, setToken] = useState<string | null>(null);
  const [ready, setReady] = useState(false);
  const [screen, setScreen] = useState<Screen>('home');
  // 등록 후 홈을 새로 불러오기 위한 key
  const [homeKey, setHomeKey] = useState(0);

  useEffect(() => {
    loadToken()
      .then(setToken)
      .finally(() => setReady(true));
  }, []);

  const signIn = useCallback(async (next: string) => {
    await saveToken(next);
    setToken(next);
    setScreen('home');
  }, []);

  const signOut = useCallback(async () => {
    await clearToken();
    setToken(null);
  }, []);

  const logout = useCallback(async () => {
    if (token) await api.logout(token).catch(() => undefined);
    await signOut();
  }, [token, signOut]);

  let content;
  if (!ready) {
    content = <ActivityIndicator style={{ flex: 1 }} color={colors.primary} />;
  } else if (!token) {
    content = <AuthScreen onAuthenticated={signIn} />;
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
        onLogout={logout}
        onUnauthorized={signOut}
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
});
