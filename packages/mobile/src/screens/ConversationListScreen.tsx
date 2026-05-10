import React, { useCallback, useEffect, useState } from 'react'
import {
  View,
  Text,
  FlatList,
  TouchableOpacity,
  StyleSheet,
  RefreshControl,
  ActivityIndicator,
  ListRenderItemInfo,
} from 'react-native'
import { NativeStackScreenProps } from '@react-navigation/native-stack'

import { Conversation, convRouteKey } from '@chatwire/shared'
import { ChatsStackParamList } from '../navigation/MainTabNavigator'
import { COLORS } from '../theme/colors'
import { useAppState } from '../state/AppStateContext'
import { useServerEvents } from '../hooks/useServerEvents'

type Props = NativeStackScreenProps<ChatsStackParamList, 'ConversationList'>

export function ConversationListScreen({ navigation }: Props) {
  const { client } = useAppState()
  const [conversations, setConversations] = useState<Conversation[]>([])
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const load = useCallback(async (silent = false) => {
    if (!client) return
    if (!silent) setLoading(true)
    try {
      const convs = await client.getConversations()
      setConversations(convs)
      setError(null)
    } catch (err) {
      setError(String(err))
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [client])

  useEffect(() => { load() }, [load])

  // Live updates: re-fetch conversation list on any SSE event
  useServerEvents(useCallback(() => { load(true) }, [load]))

  const onRefresh = useCallback(() => {
    setRefreshing(true)
    load(true)
  }, [load])

  const renderItem = useCallback(({ item }: ListRenderItemInfo<Conversation>) => {
    const key = convRouteKey(item)
    const isGroup = item.kind === 'group'
    return (
      <TouchableOpacity
        style={styles.row}
        onPress={() => navigation.navigate('MessageList', {
          handle: key,
          name: item.name || key,
          isGroup,
        })}
        testID={`conv-row-${key}`}
      >
        <View style={styles.avatar}>
          <Text style={styles.avatarText}>
            {(item.name || key).slice(0, 2).toUpperCase()}
          </Text>
        </View>
        <View style={styles.rowContent}>
          <View style={styles.rowHeader}>
            <Text style={styles.name} numberOfLines={1}>
              {item.name || key}
            </Text>
            <Text style={styles.time}>{item.last}</Text>
          </View>
          <Text style={styles.preview} numberOfLines={1}>
            {item.preview}
          </Text>
        </View>
        {item.n > 0 && (
          <View style={styles.badge}>
            <Text style={styles.badgeText}>{item.n > 99 ? '99+' : item.n}</Text>
          </View>
        )}
      </TouchableOpacity>
    )
  }, [navigation])

  if (loading) {
    return (
      <View style={[styles.root, styles.center]}>
        <ActivityIndicator color={COLORS.accent} />
      </View>
    )
  }

  if (error) {
    return (
      <View style={[styles.root, styles.center]}>
        <Text style={styles.errorText}>{error}</Text>
        <TouchableOpacity onPress={() => load()} style={styles.retryBtn}>
          <Text style={styles.retryText}>Retry</Text>
        </TouchableOpacity>
      </View>
    )
  }

  return (
    <View style={styles.root}>
      <FlatList
        data={conversations}
        keyExtractor={(item) => convRouteKey(item)}
        renderItem={renderItem}
        refreshControl={
          <RefreshControl
            refreshing={refreshing}
            onRefresh={onRefresh}
            tintColor={COLORS.accent}
          />
        }
        contentContainerStyle={conversations.length === 0 ? styles.emptyContainer : undefined}
        ListEmptyComponent={
          <Text style={styles.emptyText}>No conversations yet.</Text>
        }
      />
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
  row: {
    flexDirection: 'row',
    alignItems: 'center',
    padding: 16,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: COLORS.border,
  },
  avatar: {
    width: 44,
    height: 44,
    borderRadius: 22,
    backgroundColor: COLORS.bgTertiary,
    justifyContent: 'center',
    alignItems: 'center',
    marginRight: 12,
  },
  avatarText: {
    color: COLORS.accent,
    fontWeight: '700',
    fontSize: 16,
  },
  rowContent: {
    flex: 1,
    minWidth: 0,
  },
  rowHeader: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    marginBottom: 4,
  },
  name: {
    color: COLORS.fgPrimary,
    fontWeight: '600',
    fontSize: 15,
    flex: 1,
    marginRight: 8,
  },
  time: {
    color: COLORS.fgMuted,
    fontSize: 12,
  },
  preview: {
    color: COLORS.fgMuted,
    fontSize: 14,
  },
  badge: {
    backgroundColor: COLORS.accent,
    borderRadius: 12,
    minWidth: 24,
    height: 24,
    justifyContent: 'center',
    alignItems: 'center',
    paddingHorizontal: 6,
    marginLeft: 8,
  },
  badgeText: {
    color: COLORS.bgPrimary,
    fontSize: 12,
    fontWeight: '700',
  },
  emptyContainer: {
    flex: 1,
    justifyContent: 'center',
    alignItems: 'center',
  },
  emptyText: {
    color: COLORS.fgMuted,
    fontSize: 16,
  },
  errorText: {
    color: COLORS.accentRed,
    fontSize: 14,
    textAlign: 'center',
    marginBottom: 16,
    paddingHorizontal: 24,
  },
  retryBtn: {
    backgroundColor: COLORS.accent,
    paddingHorizontal: 20,
    paddingVertical: 10,
    borderRadius: 8,
  },
  retryText: {
    color: COLORS.bgPrimary,
    fontWeight: '700',
  },
})
