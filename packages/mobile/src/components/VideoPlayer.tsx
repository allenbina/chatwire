/**
 * VideoPlayer — inline video thumbnail + tap-to-play using expo-video.
 */
import React, { useRef, useState } from 'react'
import { View, StyleSheet, TouchableOpacity, Text } from 'react-native'
import { useVideoPlayer, VideoView } from 'expo-video'

import { COLORS } from '../theme/colors'

interface Props {
  uri: string
  label?: string
}

export function VideoPlayer({ uri, label }: Props) {
  const [expanded, setExpanded] = useState(false)
  const player = useVideoPlayer(uri, (p) => {
    p.loop = false
  })

  function handlePlay() {
    setExpanded(true)
    player.play()
  }

  if (!expanded) {
    return (
      <TouchableOpacity style={styles.thumbnail} onPress={handlePlay} accessibilityLabel={`Play video: ${label}`}>
        <Text style={styles.playIcon}>▶️</Text>
        {label && <Text style={styles.label} numberOfLines={1}>{label}</Text>}
      </TouchableOpacity>
    )
  }

  return (
    <View style={styles.playerContainer}>
      <VideoView
        player={player}
        style={styles.player}
        allowsFullscreen
        allowsPictureInPicture
      />
      <TouchableOpacity style={styles.collapseBtn} onPress={() => setExpanded(false)}>
        <Text style={styles.collapseBtnText}>✕</Text>
      </TouchableOpacity>
    </View>
  )
}

const styles = StyleSheet.create({
  thumbnail: {
    flexDirection: 'row',
    alignItems: 'center',
    backgroundColor: COLORS.bgPrimary,
    borderRadius: 8,
    padding: 10,
    marginBottom: 6,
  },
  playIcon: {
    fontSize: 24,
    marginRight: 10,
  },
  label: {
    color: COLORS.fgMuted,
    fontSize: 14,
    flex: 1,
  },
  playerContainer: {
    position: 'relative',
    marginBottom: 6,
    borderRadius: 8,
    overflow: 'hidden',
  },
  player: {
    width: '100%',
    height: 220,
  },
  collapseBtn: {
    position: 'absolute',
    top: 8,
    right: 8,
    backgroundColor: 'rgba(0,0,0,0.6)',
    width: 28,
    height: 28,
    borderRadius: 14,
    justifyContent: 'center',
    alignItems: 'center',
  },
  collapseBtnText: {
    color: '#fff',
    fontSize: 14,
    fontWeight: '700',
  },
})
