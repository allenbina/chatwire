/**
 * ImageViewer — full-screen image viewer with pinch-to-zoom.
 * Uses expo-image for performance + caching and react-native Animated
 * for pinch/pan gestures via react-native-gesture-handler.
 */
import React, { useCallback } from 'react'
import {
  Modal,
  View,
  StyleSheet,
  TouchableOpacity,
  Text,
  StatusBar,
  Share,
} from 'react-native'
import { Image } from 'expo-image'
import { GestureDetector, Gesture } from 'react-native-gesture-handler'
import Animated, {
  useSharedValue,
  useAnimatedStyle,
  withSpring,
  runOnJS,
} from 'react-native-reanimated'

import { COLORS } from '../theme/colors'

interface Props {
  uri: string | null
  onClose: () => void
}

export function ImageViewer({ uri, onClose }: Props) {
  const scale = useSharedValue(1)
  const savedScale = useSharedValue(1)
  const translateX = useSharedValue(0)
  const translateY = useSharedValue(0)
  const savedX = useSharedValue(0)
  const savedY = useSharedValue(0)

  const pinch = Gesture.Pinch()
    .onUpdate((e) => {
      scale.value = savedScale.value * e.scale
    })
    .onEnd(() => {
      savedScale.value = scale.value
      if (scale.value < 1) {
        scale.value = withSpring(1)
        savedScale.value = 1
        translateX.value = withSpring(0)
        translateY.value = withSpring(0)
        savedX.value = 0
        savedY.value = 0
      }
    })

  const pan = Gesture.Pan()
    .onUpdate((e) => {
      translateX.value = savedX.value + e.translationX
      translateY.value = savedY.value + e.translationY
    })
    .onEnd(() => {
      savedX.value = translateX.value
      savedY.value = translateY.value
    })

  const doubleTap = Gesture.Tap()
    .numberOfTaps(2)
    .onEnd(() => {
      if (scale.value > 1) {
        scale.value = withSpring(1)
        savedScale.value = 1
        translateX.value = withSpring(0)
        translateY.value = withSpring(0)
        savedX.value = 0
        savedY.value = 0
      } else {
        scale.value = withSpring(2.5)
        savedScale.value = 2.5
      }
    })

  const composed = Gesture.Simultaneous(pan, pinch)
  const withTap = Gesture.Exclusive(doubleTap, composed)

  const animatedStyle = useAnimatedStyle(() => ({
    transform: [
      { scale: scale.value },
      { translateX: translateX.value },
      { translateY: translateY.value },
    ],
  }))

  const handleShare = useCallback(() => {
    if (uri) Share.share({ url: uri, message: uri })
  }, [uri])

  if (!uri) return null

  return (
    <Modal
      visible={Boolean(uri)}
      transparent
      animationType="fade"
      onRequestClose={onClose}
      statusBarTranslucent
    >
      <StatusBar hidden />
      <View style={styles.overlay}>
        <GestureDetector gesture={withTap}>
          <Animated.View style={[styles.imageContainer, animatedStyle]}>
            <Image
              source={{ uri }}
              style={styles.image}
              contentFit="contain"
              transition={200}
            />
          </Animated.View>
        </GestureDetector>

        <TouchableOpacity style={styles.closeBtn} onPress={onClose} accessibilityLabel="Close viewer">
          <Text style={styles.closeBtnText}>✕</Text>
        </TouchableOpacity>

        <TouchableOpacity style={styles.shareBtn} onPress={handleShare} accessibilityLabel="Share image">
          <Text style={styles.shareBtnText}>⬆ Share</Text>
        </TouchableOpacity>
      </View>
    </Modal>
  )
}

const styles = StyleSheet.create({
  overlay: {
    flex: 1,
    backgroundColor: '#000',
    justifyContent: 'center',
    alignItems: 'center',
  },
  imageContainer: {
    width: '100%',
    height: '100%',
  },
  image: {
    flex: 1,
  },
  closeBtn: {
    position: 'absolute',
    top: 52,
    right: 20,
    width: 40,
    height: 40,
    borderRadius: 20,
    backgroundColor: 'rgba(0,0,0,0.6)',
    justifyContent: 'center',
    alignItems: 'center',
  },
  closeBtnText: {
    color: '#fff',
    fontSize: 18,
    fontWeight: '700',
  },
  shareBtn: {
    position: 'absolute',
    bottom: 40,
    backgroundColor: 'rgba(0,0,0,0.6)',
    paddingHorizontal: 20,
    paddingVertical: 10,
    borderRadius: 20,
  },
  shareBtnText: {
    color: '#fff',
    fontSize: 15,
    fontWeight: '600',
  },
})
