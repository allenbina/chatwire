import React, { useState } from 'react'
import {
  View,
  TextInput,
  TouchableOpacity,
  Text,
  StyleSheet,
  Platform,
} from 'react-native'
import * as Haptics from 'expo-haptics'

import { COLORS } from '../theme/colors'

interface Props {
  onSend: (text: string) => Promise<void>
}

export function ComposeBox({ onSend }: Props) {
  const [text, setText] = useState('')
  const [sending, setSending] = useState(false)

  async function handleSend() {
    const trimmed = text.trim()
    if (!trimmed || sending) return
    setSending(true)
    await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light)
    try {
      await onSend(trimmed)
      setText('')
    } finally {
      setSending(false)
    }
  }

  return (
    <View style={styles.container}>
      {/* Camera / gallery stub */}
      <TouchableOpacity style={styles.iconBtn} accessibilityLabel="Attach photo">
        <Text style={styles.iconText}>📷</Text>
      </TouchableOpacity>

      <TextInput
        style={styles.input}
        value={text}
        onChangeText={setText}
        placeholder="Message"
        placeholderTextColor={COLORS.fgMuted}
        multiline
        maxLength={2000}
        returnKeyType="default"
        blurOnSubmit={false}
        testID="compose-input"
      />

      <TouchableOpacity
        style={[styles.sendBtn, (!text.trim() || sending) && styles.sendBtnDisabled]}
        onPress={handleSend}
        disabled={!text.trim() || sending}
        accessibilityLabel="Send message"
        testID="send-button"
      >
        <Text style={styles.sendText}>↑</Text>
      </TouchableOpacity>
    </View>
  )
}

const styles = StyleSheet.create({
  container: {
    flexDirection: 'row',
    alignItems: 'flex-end',
    padding: 8,
    paddingBottom: Platform.OS === 'ios' ? 12 : 8,
    backgroundColor: COLORS.bgSecondary,
    borderTopWidth: StyleSheet.hairlineWidth,
    borderTopColor: COLORS.border,
  },
  iconBtn: {
    width: 36,
    height: 36,
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 4,
    marginBottom: 2,
  },
  iconText: {
    fontSize: 22,
  },
  input: {
    flex: 1,
    minHeight: 36,
    maxHeight: 120,
    backgroundColor: COLORS.bgTertiary,
    borderRadius: 18,
    paddingHorizontal: 14,
    paddingTop: Platform.OS === 'ios' ? 8 : 6,
    paddingBottom: Platform.OS === 'ios' ? 8 : 6,
    color: COLORS.fgPrimary,
    fontSize: 15,
    marginRight: 8,
  },
  sendBtn: {
    width: 36,
    height: 36,
    borderRadius: 18,
    backgroundColor: COLORS.accent,
    justifyContent: 'center',
    alignItems: 'center',
    marginBottom: 2,
  },
  sendBtnDisabled: {
    opacity: 0.4,
  },
  sendText: {
    color: COLORS.bgPrimary,
    fontSize: 20,
    fontWeight: '700',
    lineHeight: 22,
  },
})
