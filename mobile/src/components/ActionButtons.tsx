// 원탭 기록 버튼: 먹음 / 일부 / 버림 / 기한지남. '일부'는 남은 양 프리셋 한 번 더.
import { useState } from 'react';
import { Pressable, StyleSheet, Text, View } from 'react-native';

import type { ActionType } from '../api';
import { colors, radius, space } from '../theme';

const PARTIAL_PRESETS: { label: string; ratio: string }[] = [
  { label: '3/4 남음', ratio: '0.75' },
  { label: '절반 남음', ratio: '0.50' },
  { label: '1/4 남음', ratio: '0.25' },
];

interface Props {
  itemName: string;
  currentRatio: string | null;
  disabled?: boolean;
  onAction: (action: ActionType, remainingRatio?: string) => void;
}

export function ActionButtons({ itemName, currentRatio, disabled, onAction }: Props) {
  const [choosingPartial, setChoosingPartial] = useState(false);
  const current = currentRatio === null ? 1 : Number(currentRatio);
  const presets = PARTIAL_PRESETS.filter((p) => Number(p.ratio) < current);

  if (choosingPartial) {
    return (
      <View style={styles.row}>
        {presets.map((p) => (
          <Chip
            key={p.ratio}
            label={p.label}
            accessibilityLabel={`${itemName} ${p.label}`}
            disabled={disabled}
            onPress={() => {
              setChoosingPartial(false);
              onAction('PARTIALLY_CONSUMED', p.ratio);
            }}
          />
        ))}
        <Chip label="취소" subtle onPress={() => setChoosingPartial(false)} />
      </View>
    );
  }

  return (
    <View style={styles.row}>
      <Chip
        label="다 먹음"
        primary
        accessibilityLabel={`${itemName} 다 먹음`}
        disabled={disabled}
        onPress={() => onAction('CONSUMED')}
      />
      {presets.length > 0 && (
        <Chip
          label="일부 먹음"
          accessibilityLabel={`${itemName} 일부 먹음`}
          disabled={disabled}
          onPress={() => setChoosingPartial(true)}
        />
      )}
      <Chip
        label="버림"
        accessibilityLabel={`${itemName} 버림`}
        disabled={disabled}
        onPress={() => onAction('DISCARDED')}
      />
      <Chip
        label="기한 지남"
        accessibilityLabel={`${itemName} 기한 지남`}
        disabled={disabled}
        onPress={() => onAction('MARKED_EXPIRED')}
      />
    </View>
  );
}

interface ChipProps {
  label: string;
  onPress: () => void;
  primary?: boolean;
  subtle?: boolean;
  disabled?: boolean;
  accessibilityLabel?: string;
}

function Chip({ label, onPress, primary, subtle, disabled, accessibilityLabel }: ChipProps) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityLabel={accessibilityLabel ?? label}
      disabled={disabled}
      onPress={onPress}
      style={({ pressed }) => [
        styles.chip,
        primary && styles.chipPrimary,
        subtle && styles.chipSubtle,
        (pressed || disabled) && { opacity: 0.6 },
      ]}
    >
      <Text style={[styles.chipText, primary && styles.chipTextPrimary]}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  row: { flexDirection: 'row', gap: space.xs, marginTop: space.md },
  chip: {
    flex: 1,
    minHeight: 44,
    paddingHorizontal: space.xs,
    alignItems: 'center',
    justifyContent: 'center',
    borderRadius: radius.sm,
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.card,
  },
  chipPrimary: { backgroundColor: colors.primary, borderColor: colors.primary },
  chipSubtle: { borderColor: 'transparent', backgroundColor: 'transparent' },
  chipText: { fontSize: 13, color: colors.text, fontWeight: '600' },
  chipTextPrimary: { color: colors.primaryText },
});
