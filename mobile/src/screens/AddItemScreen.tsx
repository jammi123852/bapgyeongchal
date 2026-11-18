// 음식 등록. 필수는 이름 하나, 소비기한은 버튼 한 번으로. 나머지는 '더 입력하기' 안에 접는다.
import * as ImagePicker from 'expo-image-picker';
import { useState } from 'react';
import {
  ActivityIndicator,
  KeyboardAvoidingView,
  Platform,
  Pressable,
  ScrollView,
  StyleSheet,
  Text,
  TextInput,
  View,
} from 'react-native';

import { ApiError, OcrResult, StorageType, api } from '../api';
import { daysFromToday, isValidIsoDate } from '../dates';
import { colors, radius, space } from '../theme';

interface Props {
  token: string;
  onDone: () => void;
  onCancel: () => void;
}

const EXPIRY_PRESETS: { label: string; offset: number }[] = [
  { label: '오늘', offset: 0 },
  { label: '내일', offset: 1 },
  { label: '3일 뒤', offset: 3 },
  { label: '7일 뒤', offset: 7 },
];

const STORAGE_OPTIONS: { label: string; value: StorageType }[] = [
  { label: '냉장', value: 'FRIDGE' },
  { label: '냉동', value: 'FREEZER' },
  { label: '실온', value: 'PANTRY' },
];

export function AddItemScreen({ token, onDone, onCancel }: Props) {
  const [name, setName] = useState('');
  const [expiry, setExpiry] = useState<string | null>(null);
  const [expiryText, setExpiryText] = useState('');
  const [showMore, setShowMore] = useState(false);
  const [openedToday, setOpenedToday] = useState(false);
  const [storage, setStorage] = useState<StorageType | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  // 사진에서 읽은 날짜. 사용자가 날짜를 바꾸면 null 로 돌아가 손입력(MANUAL)으로 저장된다.
  const [ocrDate, setOcrDate] = useState<string | null>(null);
  const [ocrNote, setOcrNote] = useState<string | null>(null);
  const [reading, setReading] = useState(false);

  function pickPreset(offset: number) {
    const value = daysFromToday(offset);
    setExpiry(value);
    setExpiryText(value);
    setOcrDate(null);
    setOcrNote(null);
  }

  function applyOcr(result: OcrResult) {
    const best = result.best;
    if (!best) {
      setOcrNote('사진에서 날짜를 찾지 못했어요. 직접 입력해 주세요.');
      return;
    }
    setExpiry(null);
    setExpiryText(best.date);
    setOcrDate(best.date);
    const notes = [`사진에서 '${best.raw}'을(를) 읽었어요. 맞는지 확인해 주세요.`];
    if (best.precision === 'month') notes.push('월까지만 적혀 있어서 그 달 마지막 날로 넣었어요.');
    if (best.ambiguous) notes.push('일과 월 순서가 헷갈리는 표기예요. 꼭 확인해 주세요.');
    setOcrNote(notes.join(' '));
  }

  async function readFromPhoto(source: 'camera' | 'library') {
    setError(null);
    setOcrNote(null);
    const permission =
      source === 'camera'
        ? await ImagePicker.requestCameraPermissionsAsync()
        : await ImagePicker.requestMediaLibraryPermissionsAsync();
    if (!permission.granted) {
      setError(source === 'camera' ? '카메라 권한이 필요해요.' : '사진 접근 권한이 필요해요.');
      return;
    }
    const options: ImagePicker.ImagePickerOptions = { mediaTypes: ['images'], quality: 0.8 };
    const picked =
      source === 'camera'
        ? await ImagePicker.launchCameraAsync(options)
        : await ImagePicker.launchImageLibraryAsync(options);
    if (picked.canceled || !picked.assets?.[0]) return;
    const asset = picked.assets[0];
    setReading(true);
    try {
      applyOcr(
        await api.readExpiry(token, {
          uri: asset.uri,
          mimeType: asset.mimeType,
          fileName: asset.fileName,
          file: asset.file ?? null,
        }),
      );
    } catch (e) {
      setOcrNote(e instanceof ApiError ? e.message : '사진을 읽지 못했어요. 직접 입력해 주세요.');
    } finally {
      setReading(false);
    }
  }

  async function save() {
    setError(null);
    if (!name.trim()) {
      setError('이름을 입력해 주세요.');
      return;
    }
    let expiryDate: string | null = expiry;
    if (expiryText.trim()) {
      if (!isValidIsoDate(expiryText.trim())) {
        setError('소비기한은 2026-10-01 형식으로 입력해 주세요.');
        return;
      }
      expiryDate = expiryText.trim();
    } else {
      expiryDate = null;
    }
    setBusy(true);
    try {
      await api.createItem(token, {
        custom_name: name.trim(),
        expiry_date: expiryDate,
        // 사진에서 읽은 날짜를 그대로 저장할 때만 OCR, 한 글자라도 바꿨으면 손입력
        expiry_source: ocrDate !== null && expiryDate === ocrDate ? 'OCR' : 'MANUAL',
        opened_date: openedToday ? daysFromToday(0) : null,
        storage_type: storage,
      });
      onDone();
    } catch (e) {
      setError(e instanceof ApiError ? e.message : '저장하지 못했어요.');
    } finally {
      setBusy(false);
    }
  }

  return (
    <KeyboardAvoidingView
      style={styles.screen}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <ScrollView contentContainerStyle={styles.content} keyboardShouldPersistTaps="handled">
        <View style={styles.header}>
          <Pressable accessibilityRole="button" onPress={onCancel} hitSlop={12}>
            <Text style={styles.cancel}>닫기</Text>
          </Pressable>
          <Text style={styles.title}>음식 추가</Text>
          <View style={{ width: 40 }} />
        </View>

        <Text style={styles.label}>이름</Text>
        <TextInput
          style={styles.input}
          placeholder="예: 두부, 우유, 엄마 반찬"
          accessibilityLabel="음식 이름"
          autoFocus
          value={name}
          onChangeText={setName}
          maxLength={100}
        />

        <Text style={styles.label}>소비기한</Text>
        <View style={styles.row}>
          {EXPIRY_PRESETS.map((p) => {
            const value = daysFromToday(p.offset);
            const selected = expiryText === value;
            return (
              <Option
                key={p.label}
                label={p.label}
                selected={selected}
                onPress={() => pickPreset(p.offset)}
              />
            );
          })}
          <Option
            label="모름"
            selected={expiryText === '' && expiry === null}
            onPress={() => {
              setExpiry(null);
              setExpiryText('');
              setOcrDate(null);
              setOcrNote(null);
            }}
          />
        </View>
        <View style={styles.row}>
          <Option label="사진 찍어 읽기" selected={false} onPress={() => readFromPhoto('camera')} />
          <Option label="앨범에서 읽기" selected={false} onPress={() => readFromPhoto('library')} />
          {reading && <ActivityIndicator color={colors.primary} />}
        </View>
        {ocrNote && (
          <Text style={styles.ocrNote} accessibilityLiveRegion="polite">
            {ocrNote}
          </Text>
        )}
        <TextInput
          style={styles.input}
          placeholder="직접 입력 (2026-10-01)"
          accessibilityLabel="소비기한 직접 입력"
          value={expiryText}
          onChangeText={(t) => {
            setExpiryText(t);
            setExpiry(null);
            if (t !== ocrDate) setOcrNote(null);
          }}
          maxLength={10}
        />

        <Pressable accessibilityRole="button" onPress={() => setShowMore(!showMore)}>
          <Text style={styles.more}>{showMore ? '간단히 입력하기 ▲' : '더 입력하기 ▼'}</Text>
        </Pressable>

        {showMore && (
          <View style={styles.moreBox}>
            <Text style={styles.label}>개봉</Text>
            <View style={styles.row}>
              <Option label="안 뜯음" selected={!openedToday} onPress={() => setOpenedToday(false)} />
              <Option label="오늘 뜯음" selected={openedToday} onPress={() => setOpenedToday(true)} />
            </View>
            <Text style={styles.label}>보관</Text>
            <View style={styles.row}>
              {STORAGE_OPTIONS.map((o) => (
                <Option
                  key={o.value}
                  label={o.label}
                  selected={storage === o.value}
                  onPress={() => setStorage(storage === o.value ? null : o.value)}
                />
              ))}
            </View>
          </View>
        )}

        {error && <Text style={styles.error}>{error}</Text>}

        <Pressable
          accessibilityRole="button"
          accessibilityLabel="저장"
          style={({ pressed }) => [styles.save, (pressed || busy) && { opacity: 0.7 }]}
          onPress={save}
          disabled={busy}
        >
          <Text style={styles.saveText}>저장</Text>
        </Pressable>
      </ScrollView>
    </KeyboardAvoidingView>
  );
}

function Option({ label, selected, onPress }: { label: string; selected: boolean; onPress: () => void }) {
  return (
    <Pressable
      accessibilityRole="button"
      accessibilityState={{ selected }}
      onPress={onPress}
      style={[styles.option, selected && styles.optionSelected]}
    >
      <Text style={[styles.optionText, selected && styles.optionTextSelected]}>{label}</Text>
    </Pressable>
  );
}

const styles = StyleSheet.create({
  screen: { flex: 1, backgroundColor: colors.bg },
  content: { padding: space.lg, paddingTop: space.xl + space.md, gap: space.sm, maxWidth: 560, width: '100%', alignSelf: 'center' },
  header: {
    flexDirection: 'row',
    alignItems: 'center',
    justifyContent: 'space-between',
    marginBottom: space.md,
  },
  cancel: { color: colors.sub, fontSize: 16 },
  title: { fontSize: 18, fontWeight: '700', color: colors.text },
  label: { fontSize: 14, fontWeight: '600', color: colors.sub, marginTop: space.md },
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
  row: { flexDirection: 'row', flexWrap: 'wrap', gap: space.sm },
  option: {
    minHeight: 40,
    paddingHorizontal: space.md,
    justifyContent: 'center',
    borderRadius: radius.sm,
    borderWidth: 1,
    borderColor: colors.line,
    backgroundColor: colors.card,
  },
  optionSelected: { backgroundColor: colors.soft, borderColor: colors.primary },
  optionText: { fontSize: 14, color: colors.text },
  optionTextSelected: { color: colors.primary, fontWeight: '700' },
  more: { color: colors.primary, fontSize: 14, fontWeight: '600', paddingVertical: space.md },
  moreBox: { gap: space.sm },
  error: { color: colors.danger, fontSize: 14, marginTop: space.sm },
  ocrNote: {
    fontSize: 13,
    color: colors.primary,
    backgroundColor: colors.soft,
    borderRadius: radius.sm,
    padding: space.md,
  },
  save: {
    minHeight: 52,
    borderRadius: radius.sm,
    backgroundColor: colors.primary,
    alignItems: 'center',
    justifyContent: 'center',
    marginTop: space.lg,
  },
  saveText: { color: colors.primaryText, fontSize: 17, fontWeight: '700' },
});
