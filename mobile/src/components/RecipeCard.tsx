// 임박 재료 요리 카드: 냉장고에서 쓰는 재료(임박 표시) + 더 필요한 재료. 누르면 조리 순서 또는 유튜브 영상.
import { useState } from 'react';
import { Image, Linking, Pressable, StyleSheet, Text, View } from 'react-native';

import type { RecipeSuggestion } from '../api';
import { colors, radius, space } from '../theme';

function dayText(days: number | null): string {
  if (days === null) return '';
  return days === 0 ? '오늘까지' : `D-${days}`;
}

export function RecipeCard({ recipe }: { recipe: RecipeSuggestion }) {
  const [open, setOpen] = useState(false);
  const thumb =
    recipe.image_url ?? (recipe.video_id ? `https://i.ytimg.com/vi/${recipe.video_id}/hqdefault.jpg` : null);
  const uses = recipe.uses
    .map((u) => (u.urgent ? `${u.name}(${dayText(u.days_left)})` : u.name))
    .join(', ');

  return (
    <View style={styles.card}>
      <Pressable
        accessibilityRole="button"
        accessibilityState={{ expanded: open }}
        onPress={() => setOpen(!open)}
        style={styles.head}
      >
        {thumb && <Image source={{ uri: thumb }} style={styles.thumb} accessibilityIgnoresInvertColors />}
        <View style={styles.body}>
          <Text style={styles.name}>{recipe.name}</Text>
          <Text style={styles.line}>
            <Text style={styles.label}>냉장고 </Text>
            {uses}
          </Text>
          <Text style={styles.line}>
            <Text style={styles.label}>더 필요 </Text>
            {recipe.missing.length > 0 ? recipe.missing.join(', ') : '없어요 (기본 양념 제외)'}
          </Text>
        </View>
      </Pressable>

      {open && recipe.steps && (
        <View style={styles.steps}>
          {recipe.steps.map((step) => (
            <Text key={step} style={styles.step}>
              {step}
            </Text>
          ))}
        </View>
      )}
      {open && recipe.url && (
        <Pressable
          accessibilityRole="link"
          onPress={() => Linking.openURL(recipe.url!)}
          style={({ pressed }) => [styles.video, pressed && { opacity: 0.85 }]}
        >
          <Text style={styles.videoText}>유튜브에서 보기</Text>
        </Pressable>
      )}
      <Text style={styles.source}>
        출처: {recipe.attribution}
        {recipe.channel_title ? ` · ${recipe.channel_title}` : ''}
      </Text>
    </View>
  );
}

const styles = StyleSheet.create({
  card: {
    backgroundColor: colors.card,
    borderRadius: radius.md,
    padding: space.md,
    borderWidth: 1,
    borderColor: colors.line,
    gap: space.sm,
  },
  head: { flexDirection: 'row', gap: space.md },
  thumb: { width: 72, height: 72, borderRadius: radius.sm, backgroundColor: colors.soft },
  body: { flex: 1, gap: space.xs },
  name: { fontSize: 16, fontWeight: '700', color: colors.text },
  line: { fontSize: 14, color: colors.text },
  label: { color: colors.sub, fontWeight: '600' },
  steps: { gap: space.xs, paddingTop: space.xs },
  step: { fontSize: 14, color: colors.text, lineHeight: 20 },
  video: {
    alignSelf: 'flex-start',
    backgroundColor: colors.primary,
    borderRadius: radius.sm,
    paddingHorizontal: space.md,
    paddingVertical: space.sm,
  },
  videoText: { color: colors.primaryText, fontSize: 14, fontWeight: '700' },
  source: { fontSize: 12, color: colors.sub },
});
