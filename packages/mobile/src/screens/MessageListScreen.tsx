import React, { useCallback, useEffect, useRef, useState } from 'react'
import {
  View,
  Text,
  FlatList,
  StyleSheet,
  ActivityIndicator,
  TouchableOpacity,
  Share,
  ActionSheetIOS,
  Platform,
  Alert,
  ListRenderItemInfo,
} from 'react-native'
import { NativeStackScreenProps } from '@react-navigation/native-stack'
import * as Haptics from 'expo-haptics'

import { Message } from '@chatwire/shared'
import { ChatsStackParamList } from '../navigation/MainTabNavigator'
import { COLORS } from '../theme/colors'
import { useAppState } from '../state/AppStateContext'
import { useServerEvents } from '../hooks/useServerEvents'
import { ComposeBox } from '../components/ComposeBox'
import { MessageBubble } from '../components/MessageBubble'

type Props = NativeStackScreenProps<ChatsStackParamList, 'MessageList'>

export function MessageListScreen({ route }: Props) {
  const { handle, isGroup } = route.params
  const { client } = useAppState()
  const [messages, setMessages] = useState<Message[]>([])
  const [loading, setLoading] = useState(true)
  const [loadingOlder, setLoadingOlder] = useState(false)
  const [hasMore, setHasMore] = useState(false)
  const listRef = useRef<FlatList<Message>>(null)

  const load = useCallback(async () => {
    if (!client) return
    setLoading(true)
    try {
      const { messages: msgs, has_more } = await client.getMessages(handle, { isGroup })
      setMessages(msgs)
      setHasMore(has_more)
    } finally {
      setLoading(false)
    }
  }, [client, handle, isGroup])

  useEffect(() => { load() }, [load])

  // Live updates: fetch new messages via SSE
  useServerEvents(useCallback(async () => {
    if (!client) return
    const { messages: newMsgs } = await client.getMessages(handle, {
      isGroup,
      since: messages[messages.length - 1]?.date ?? 0,
    })
    if (newMsgs.length > 0) {
      setMessages((prev) => [...prev, ...newMsgs])
    }
  }, [client, handle, isGroup, messages]))

  const loadOlder = useCallback(async () => {
    if (!client || loadingOlder || !hasMore || messages.length === 0) return
    setLoadingOlder(true)
    try {
      const oldest = messages[0]
      const { messages: older, has_more } = await client.getOlderMessages(handle, {
        isGroup,
        beforeDate: oldest.date,
        beforeRowid: oldest.rowid,
      })
      if (older.length > 0) {
        setMessages((prev) => [...older, ...prev])
        setHasMore(has_more)
      }
    } finally {
      setLoadingOlder(false)
    }
  }, [client, handle, isGroup, hasMore, loadingOlder, messages])

  async function handleSend(text: string) {
    if (!client) return
    await Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Light)
    await client.sendMessage(handle, text, isGroup)
  }

  function handleLongPress(msg: Message) {
    Haptics.impactAsync(Haptics.ImpactFeedbackStyle.Medium)
    if (Platform.OS === 'ios') {
      ActionSheetIOS.showActionSheetWithOptions(
        {
          options: ['Cancel', 'Copy text', 'Share'],
          cancelButtonIndex: 0,
        },
        (idx) => {
          if (idx === 2 && msg.text) {
            Share.share({ message: msg.text })
          }
        },
      )
    } else {
      Alert.alert('Message', msg.text, [
        { text: 'Cancel', style: 'cancel' },
        { text: 'Share', onPress: () => Share.share({ message: msg.text }) },
      ])
    }
  }

  const renderItem = useCallback(({ item }: ListRenderItemInfo<Message>) => (
    <MessageBubble
      message={item}
      onLongPress={() => handleLongPress(item)}
    />
  ), [])

  if (loading) {
    return (
      <View style={[styles.root, styles.center]}>
        <ActivityIndicator color={COLORS.accent} />
      </View>
    )
  }

  return (
    <View style={styles.root}>
      {loadingOlder && (
        <View style={styles.loadingOlderBar}>
          <ActivityIndicator size="small" color={COLORS.accent} />
        </View>
      )}
      <FlatList
        ref={listRef}
        data={[...messages].reverse()}
        keyExtractor={(m) => String(m.rowid)}
        renderItem={renderItem}
        inverted
        onEndReached={loadOlder}
        onEndReachedThreshold={0.2}
        contentContainerStyle={styles.listContent}
      />
      <ComposeBox onSend={handleSend} />
    </View>
  )
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: COLORS.bgPrimary,
  },
  center: {
    justifyContent: 'center',
    alignItems: 'center',
  },
  listContent: {
    paddingHorizontal: 12,
    paddingVertical: 8,
  },
  loadingOlderBar: {
    padding: 8,
    alignItems: 'center',
    backgroundColor: COLORS.bgSecondary,
  },
})
