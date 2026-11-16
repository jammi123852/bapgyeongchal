import { useState } from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';

import { ApiError, api } from '../api';
import { colors, radius, space } from '../theme';

interface Props {
  onAuthenticated: (token: string) => void;
}

export function AuthScreen({ onAuthenticated }: Props) {
  const [mode, setMode] = useState<'login' | 'signup'>('login');
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  async function submit() {
    setError(null);
    setBusy(true);
    try {
      const call = mode === 'login' ? api.login : api.signup;
      const { access_token } = await call(email.trim(), password);
      onAuthenticated(access_token);
    } catch (e) {
      setError(e instanceof ApiError ? e.message : '잠시 후 다시 시도해 주세요.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <KeyboardAvoidingView
      style={styles.screen}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <View style={styles.inner}>
        <Text style={styles.title}>SoloSafe</Text>
        <Text style={styles.subtitle}>냉장고에서 오늘 먼저 먹을 것</Text>

        <TextInput
          style={styles.input}
          placeholder="이메일"
          accessibilityLabel="이메일"
          autoCapitalize="none"
          autoComplete="email"
          keyboardType="email-address"
          value={email}
          onChangeText={setEmail}
        />
        <TextInput
          style={styles.input}
          placeholder={mode === 'signup' ? '비밀번호 (8자 이상)' : '비밀번호'}
          accessibilityLabel="비밀번호"
          secureTextEntry
          value={password}
          onChangeText={setPassword}
          onSubmitEditing={submit}
        />

        {error && <Text style={styles.error}>{error}</Text>}

        <Pressable
          accessibilityRole="button"
          accessibilityLabel={mode === 'login' ? '로그인' : '가입하기'}
          style={({ pressed }) => [styles.button, (pressed || busy) && { opacity: 0.7 }]}
          onPress={submit}
          disabled={busy}
        >
          {busy ? (
            <ActivityIndicator color={colors.primaryText} />
          ) : (
            <Text style={styles.buttonText}>{mode === 'login' ? '로그인' : '가입하기'}</Text>
          )}
        </Pressable>

        <Pressable
          accessibilityRole="button"
          onPress={() => {
            setMode(mode === 'login' ? 'signup' : 'login');
            setError(null);
          }}
        >
          <Text style={styles.switch}>
            {mode === 'login' ? '처음이에요 · 가입하기' : '이미 계정이 있어요 · 로그인'}
          </Text>
        </Pressable>
      </View>
    </KeyboardAvoidingView>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg, justifyContent: 'center' },
  inner: { paddingHorizontal: space.xl, gap: space.md, width: '100%', maxWidth: 420, alignSelf: 'center' },
  title: { fontSize: 32, fontWeight: '800', color: colors.primary },
  subtitle: { fontSize: 16, color: colors.sub, marginBottom: space.lg },
  input: {
    minHeight: 48,
    borderRadius: radius.sm,
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.card,
    paddingHorizontal: space.md,
    fontSize: 16,
    color: colors.text,
  },
  error: { color: colors.danger, fontSize: 14 },
  button: {
    minHeight: 50,
    borderRadius: radius.sm,
    backgroundColor: colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: space.sm,
  },
  buttonText: { color: colors.primaryText, fontSize: 16, fontWeight: '700' },
  switch: { textAlign: 'center', color: colors.sub, fontSize: 14, paddingVertical: space.md },
});
