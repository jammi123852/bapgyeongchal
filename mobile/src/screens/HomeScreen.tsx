// 홈: 오늘 먼저 먹을 것(상위 3개 + 이유) → 나머지 냉장고 목록. 모든 항목에서 원탭 기록.
import { useCallback, useEffect, useState } from 'react';
import {
  ActivityIndicator,
  Pressable,
  RefreshControl,
  ScrollView,
  StyleSheet,
  Text,
  View,
} from 'react-native';

import { ActionButtons } from '../components/ActionButtons';
import { ActionType, ApiError, EatFirstBatch, InventoryItem, api } from '../api';
import { dDayLabel } from '../dates';

const REMAINING_LABEL: Record<string, string> = { '0.75': '3/4 남음', '0.50': '절반 남음', '0.25': '1/4 남음' };

function remainingLabel(ratio: string | null): string | null {
  if (ratio === null || Number(ratio) >= 1) return null;
  return REMAINING_LABEL[ratio] ?? `${Math.round(Number(ratio) * 100)}% 남음`;
}
import { colors, radius, space } from '../theme';

interface Props {
  token: string;
  onAdd: () => void;
  onLogout: () => void;
  onUnauthorized: () => void;
}

const ACTION_DONE_TEXT: Record<ActionType, string> = {
  CONSUMED: '다 먹음으로 기록했어요',
  PARTIALLY_CONSUMED: '남은 양을 기록했어요',
  DISCARDED: '버림으로 기록했어요',
  MARKED_EXPIRED: '기한 지남으로 기록했어요',
};

export function HomeScreen({ token, onAdd, onLogout, onUnauthorized }: Props) {
  const [batch, setBatch] = useState<EatFirstBatch | null>(null);
  const [items, setItems] = useState<InventoryItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [busyId, setBusyId] = useState<string | null>(null);
  const [message, setMessage] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  const handleError = useCallback(
    (e: unknown) => {
      if (e instanceof ApiError && e.status === 401) {
        onUnauthorized();
        return;
      }
      setError(e instanceof ApiError ? e.message : '불러오지 못했어요.');
    },
    [onUnauthorized],
  );

  const load = useCallback(async () => {
    setError(null);
    try {
      const [nextBatch, nextItems] = await Promise.all([api.eatFirst(token), api.listItems(token)]);
      setBatch(nextBatch);
      setItems(nextItems);
    } catch (e) {
      handleError(e);
    } finally {
      setLoading(false);
    }
  }, [token, handleError]);

  useEffect(() => {
    load();
  }, [load]);

  // 추천이 화면에 그려진 뒤에만 노출로 기록한다 (계산만 되고 안 보인 추천은 노출 아님).
  useEffect(() => {
    if (batch && batch.entries.length > 0) {
      api.markShown(token, batch.batch_id).catch(() => undefined);
    }
  }, [batch, token]);

  async function act(
    item: InventoryItem,
    action: ActionType,
    remainingRatio?: string,
    recommendationId?: string,
  ) {
    setBusyId(item.id);
    setMessage(null);
    try {
      await api.act(token, item.id, action, { remainingRatio, recommendationId });
      setMessage(`${item.custom_name}: ${ACTION_DONE_TEXT[action]}`);
      await load();
    } catch (e) {
      handleError(e);
    } finally {
      setBusyId(null);
    }
  }

  const recommendedIds = new Set(batch?.entries.map((e) => e.item.id) ?? []);
  const rest = items.filter((i) => !recommendedIds.has(i.id));

  return (
    <View style={styles.screen}>
      <View style={styles.topBar}>
        <Text style={styles.brand}>SoloSafe</Text>
        <Pressable accessibilityRole="button" onPress={onLogout} hitSlop={12}>
          <Text style={styles.logout}>로그아웃</Text>
        </Pressable>
      </View>

      <ScrollView
        contentContainerStyle={styles.content}
        refreshControl={<RefreshControl refreshing={false} onRefresh={load} />}
      >
        {message && (
          <View style={styles.toast} accessibilityLiveRegion="polite">
            <Text style={styles.toastText}>{message}</Text>
          </View>
        )}
        {error && <Text style={styles.error}>{error}</Text>}

        <Text style={styles.sectionTitle}>오늘 먼저 먹을 것</Text>
        {loading ? (
          <ActivityIndicator style={{ marginVertical: space.xl }} color={colors.primary} />
        ) : batch && batch.entries.length > 0 ? (
          batch.entries.map((entry) => (
            <View key={entry.recommendation_id} style={styles.recCard}>
              <View style={styles.cardHead}>
                <Text style={styles.rank}>{entry.rank}</Text>
                <Text style={styles.recName}>{entry.item.custom_name}</Text>
                <Text style={styles.dday}>{dDayLabel(entry.item.expiry_date)}</Text>
              </View>
              {remainingLabel(entry.item.remaining_ratio) && (
                <Text style={styles.remaining}>{remainingLabel(entry.item.remaining_ratio)}</Text>
              )}
              {entry.reasons.map((r) => (
                <Text key={r.code} style={styles.reason}>
                  · {r.text}
                </Text>
              ))}
              <ActionButtons
                itemName={entry.item.custom_name}
                currentRatio={entry.item.remaining_ratio}
                disabled={busyId === entry.item.id}
                onAction={(action, ratio) =>
                  act(entry.item, action, ratio, entry.recommendation_id)
                }
              />
            </View>
          ))
        ) : (
          <View style={styles.empty}>
            <Text style={styles.emptyText}>냉장고가 비어 있어요.</Text>
            <Text style={styles.emptySub}>아래 + 버튼으로 음식을 추가해 보세요.</Text>
          </View>
        )}

        {rest.length > 0 && <Text style={styles.sectionTitle}>냉장고 나머지</Text>}
        {rest.map((item) => (
          <View key={item.id} style={styles.card}>
            <View style={styles.cardHead}>
              <Text style={styles.name}>{item.custom_name}</Text>
              <Text style={styles.ddaySub}>{dDayLabel(item.expiry_date)}</Text>
            </View>
            {remainingLabel(item.remaining_ratio) && (
              <Text style={styles.remaining}>{remainingLabel(item.remaining_ratio)}</Text>
            )}
            <ActionButtons
              itemName={item.custom_name}
              currentRatio={item.remaining_ratio}
              disabled={busyId === item.id}
              onAction={(action, ratio) => act(item, action, ratio)}
            />
          </View>
        ))}
        <View style={{ height: 96 }} />
      </ScrollView>

      <Pressable
        accessibilityRole="button"
        accessibilityLabel="음식 추가"
        style={({ pressed }) => [styles.fab, pressed && { opacity: 0.85 }]}
        onPress={onAdd}
      >
        <Text style={styles.fabText}>+ 음식 추가</Text>
      </Pressable>
    </View>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  topBar: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingHorizontal: space.lg,
    paddingTop: space.xl + space.md,
    paddingBottom: space.md,
  },
  brand: { fontSize: 20, fontWeight: '800', color: colors.primary },
  logout: { fontSize: 14, color: colors.sub },
  content: { paddingHorizontal: space.lg, gap: space.md, maxWidth: 560, width: '100%', alignSelf: 'center' },
  sectionTitle: { fontSize: 17, fontWeight: '700', color: colors.text, marginTop: space.md },
  recCard: {
    backgroundColor: colors.card,
    borderRadius: radius.md,
    padding: space.lg,
    borderWidth: 1,
    borderColor: colors.line,
  },
  card: {
    backgroundColor: colors.card,
    borderRadius: radius.md,
    padding: space.md,
    borderWidth: 1,
    borderColor: colors.line,
  },
  cardHead: { flexDirection: 'row', alignItems: 'center', gap: space.sm },
  rank: {
    width: 26,
    height: 26,
    borderRadius: 13,
    backgroundColor: colors.soft,
    color: colors.primary,
    textAlign: 'center',
    lineHeight: 26,
    fontWeight: '800',
    overflow: 'hidden',
  },
  recName: { flex: 1, fontSize: 18, fontWeight: '700', color: colors.text },
  name: { flex: 1, fontSize: 16, fontWeight: '600', color: colors.text },
  dday: { fontSize: 14, fontWeight: '700', color: colors.warn },
  ddaySub: { fontSize: 13, color: colors.sub },
  reason: { fontSize: 14, color: colors.sub, marginTop: space.xs },
  remaining: { fontSize: 13, color: colors.primary, fontWeight: '600', marginTop: space.xs },
  empty: { paddingVertical: space.xl, alignItems: 'center', gap: space.xs },
  emptyText: { fontSize: 16, color: colors.text },
  emptySub: { fontSize: 14, color: colors.sub },
  toast: { backgroundColor: colors.soft, borderRadius: radius.sm, padding: space.md },
  toastText: { color: colors.primary, fontSize: 14 },
  error: { color: colors.danger, fontSize: 14 },
  fab: {
    position: 'absolute',
    right: space.lg,
    bottom: space.xl,
    backgroundColor: colors.primary,
    borderRadius: 28,
    paddingHorizontal: space.xl,
    minHeight: 56,
    justifyContent: 'center',
    boxShadow: '0 4px 8px rgba(0, 0, 0, 0.15)',
  },
  fabText: { color: colors.primaryText, fontSize: 16, fontWeight: '700' },
});
