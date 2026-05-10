/**
 * useBackgroundFetch — stub background fetch registration.
 *
 * Registers an Expo background task that polls /api/ui/conversations
 * every 15 minutes (OS-controlled interval) and fires a local notification
 * when there are unread messages.
 *
 * This is a stub implementation — the task body is a no-op beyond what
 * the OS allows. Real implementations require an EAS build with the
 * expo-background-fetch + expo-task-manager native modules wired in.
 */
import { useEffect } from 'react'
import * as BackgroundFetch from 'expo-background-fetch'
import * as TaskManager from 'expo-task-manager'
import * as Notifications from 'expo-notifications'

export const BACKGROUND_FETCH_TASK = 'chatwire-background-fetch'

// Define the task at module scope (must be at top-level for Expo)
TaskManager.defineTask(BACKGROUND_FETCH_TASK, async () => {
  try {
    // In a real build: retrieve serverUrl + password from SecureStore,
    // create a ChaiwireClient, fetch conversations, fire local notification
    // for any with n > 0.
    //
    // For now this is a stub that reports NO_DATA so the OS can still
    // call the task on its schedule.
    return BackgroundFetch.BackgroundFetchResult.NoData
  } catch {
    return BackgroundFetch.BackgroundFetchResult.Failed
  }
})

export function useBackgroundFetch() {
  useEffect(() => {
    async function register() {
      try {
        const status = await BackgroundFetch.getStatusAsync()
        if (
          status === BackgroundFetch.BackgroundFetchStatus.Restricted ||
          status === BackgroundFetch.BackgroundFetchStatus.Denied
        ) {
          return
        }
        await BackgroundFetch.registerTaskAsync(BACKGROUND_FETCH_TASK, {
          minimumInterval: 15 * 60, // 15 minutes (OS may delay longer)
          stopOnTerminate: false,
          startOnBoot: true,
        })
      } catch {
        // Not available in Expo Go — silently ignored
      }
    }

    register()

    return () => {
      BackgroundFetch.unregisterTaskAsync(BACKGROUND_FETCH_TASK).catch(() => {})
    }
  }, [])
}
