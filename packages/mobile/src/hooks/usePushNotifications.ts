/**
 * usePushNotifications — Expo Push Notifications integration.
 *
 * On mount, requests permission and registers the device's Expo push token
 * with the chatwire server via POST /push/subscribe.
 *
 * Incoming push notifications are handled by the top-level notification
 * listener; tapping a notification navigates to the relevant conversation.
 */
import { useEffect, useRef } from 'react'
import * as Notifications from 'expo-notifications'
import { Platform } from 'react-native'

import { useAppState } from '../state/AppStateContext'

Notifications.setNotificationHandler({
  handleNotification: async () => ({
    shouldShowAlert: true,
    shouldPlaySound: true,
    shouldSetBadge: true,
  }),
})

/**
 * @param onNotificationTap - called with the conversation handle when user
 *   taps a notification. The caller is responsible for navigation.
 */
export function usePushNotifications(onNotificationTap?: (handle: string) => void) {
  const { client } = useAppState()
  const onTapRef = useRef(onNotificationTap)
  onTapRef.current = onNotificationTap

  useEffect(() => {
    if (!client) return

    let responseSubscription: Notifications.EventSubscription | null = null

    async function register() {
      // Android notification channel
      if (Platform.OS === 'android') {
        await Notifications.setNotificationChannelAsync('default', {
          name: 'chatwire',
          importance: Notifications.AndroidImportance.MAX,
          vibrationPattern: [0, 250, 250, 250],
          lightColor: '#bd93f9',
        })
      }

      const { status: existingStatus } = await Notifications.getPermissionsAsync()
      let finalStatus = existingStatus
      if (existingStatus !== 'granted') {
        const { status } = await Notifications.requestPermissionsAsync()
        finalStatus = status
      }
      if (finalStatus !== 'granted') return

      const tokenData = await Notifications.getExpoPushTokenAsync()
      const token = tokenData.data
      const platform = Platform.OS === 'ios' ? 'ios' : 'android'

      try {
        await client!.subscribePush({ token, platform })
      } catch {
        // Non-fatal: server might not support push yet
      }
    }

    register()

    // Handle tap on a push notification
    responseSubscription = Notifications.addNotificationResponseReceivedListener((response) => {
      const data = response.notification.request.content.data as { handle?: string }
      if (data?.handle && onTapRef.current) {
        onTapRef.current(data.handle)
      }
    })

    return () => {
      responseSubscription?.remove()
    }
  }, [client])
}
