import React from 'react'
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  Image,
} from 'react-native'

import { Message } from '@chatwire/shared'
import { COLORS } from '../theme/colors'
import { useAppState } from '../state/AppStateContext'

interface Props {
  message: Message
  onLongPress?: () => void
}

export function MessageBubble({ message, onLongPress }: Props) {
  const { client } = useAppState()
  const isMe = message.from_me

  const images = message.attachments.filter((a) => a.kind === 'image' && a.ready)
  const videos = message.attachments.filter((a) => a.kind === 'video' && a.ready)
  const files = message.attachments.filter(
    (a) => a.kind !== 'image' && a.kind !== 'video',
  )

  return (
    <View style={[styles.wrapper, isMe ? styles.wrapperMe : styles.wrapperThem]}>
      {!isMe && message.sender_name && (
        <Text style={styles.senderName}>{message.sender_name}</Text>
      )}

      <TouchableOpacity
        style={[styles.bubble, isMe ? styles.bubbleMe : styles.bubbleThem]}
        onLongPress={onLongPress}
        activeOpacity={0.8}
        delayLongPress={400}
      >
        {/* Images */}
        {images.map((att) => (
          <Image
            key={att.path}
            source={{ uri: client?.attachmentUrl(att.path) ?? att.path }}
            style={styles.image}
            resizeMode="cover"
            accessibilityLabel={att.name}
          />
        ))}

        {/* Video thumbnails (tap to play handled in Chunk 4) */}
        {videos.map((att) => (
          <View key={att.path} style={styles.videoStub}>
            <Text style={styles.videoIcon}>▶️</Text>
            <Text style={styles.videoLabel} numberOfLines={1}>{att.name}</Text>
          </View>
        ))}

        {/* File attachments */}
        {files.map((att) => (
          <View key={att.path} style={styles.filePill}>
            <Text style={styles.fileIcon}>📎</Text>
            <Text style={styles.fileName} numberOfLines={1}>{att.name}</Text>
          </View>
        ))}

        {/* Message text */}
        {Boolean(message.text) && (
          <Text style={[styles.text, isMe ? styles.textMe : styles.textThem]}>
            {message.text}
          </Text>
        )}

        <Text style={styles.timestamp}>{message.ts}</Text>
      </TouchableOpacity>
    </View>
  )
}

const styles = StyleSheet.create({
  wrapper: {
    marginVertical: 4,
    maxWidth: '80%',
  },
  wrapperMe: {
    alignSelf: 'flex-end',
    alignItems: 'flex-end',
  },
  wrapperThem: {
    alignSelf: 'flex-start',
    alignItems: 'flex-start',
  },
  senderName: {
    color: COLORS.accent,
    fontSize: 12,
    marginBottom: 2,
    marginLeft: 4,
  },
  bubble: {
    borderRadius: 16,
    padding: 10,
    paddingHorizontal: 14,
    maxWidth: '100%',
  },
  bubbleMe: {
    backgroundColor: COLORS.bubbleMe,
    borderBottomRightRadius: 4,
  },
  bubbleThem: {
    backgroundColor: COLORS.bubbleThem,
    borderBottomLeftRadius: 4,
  },
  text: {
    fontSize: 15,
    lineHeight: 20,
  },
  textMe: {
    color: COLORS.fgPrimary,
  },
  textThem: {
    color: COLORS.fgPrimary,
  },
  timestamp: {
    color: COLORS.fgMuted,
    fontSize: 11,
    marginTop: 4,
    alignSelf: 'flex-end',
  },
  image: {
    width: 220,
    height: 160,
    borderRadius: 10,
    marginBottom: 6,
  },
  videoStub: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: COLORS.bgPrimary,
    borderRadius: 8,
    padding: 8,
    marginBottom: 6,
  },
  videoIcon: {
    fontSize: 22,
    marginRight: 8,
  },
  videoLabel: {
    color: COLORS.fgMuted,
    fontSize: 13,
    flex: 1,
  },
  filePill: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: COLORS.bgPrimary,
    borderRadius: 8,
    padding: 8,
    marginBottom: 6,
  },
  fileIcon: {
    fontSize: 18,
    marginRight: 8,
  },
  fileName: {
    color: COLORS.fgMuted,
    fontSize: 13,
    flex: 1,
  },
})
