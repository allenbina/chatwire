import React, { useEffect, useState } from 'react'
import { ActivityIndicator, View } from 'react-native'
import AsyncStorage from '@react-native-async-storage/async-storage'
import { NavigationContainer } from '@react-navigation/native'
import { SafeAreaProvider } from 'react-native-safe-area-context'
import { GestureHandlerRootView } from 'react-native-gesture-handler'

import { RootNavigator } from './src/navigation/RootNavigator'
import { AppStateProvider } from './src/state/AppStateContext'

export default function App() {
  const [isReady, setIsReady] = useState(false)
  const [hasServerUrl, setHasServerUrl] = useState(false)

  useEffect(() => {
    AsyncStorage.getItem('serverUrl').then((url) => {
      setHasServerUrl(Boolean(url))
      setIsReady(true)
    })
  }, [])

  if (!isReady) {
    return (
      <View style={{ flex: 1, justifyContent: 'center', alignItems: 'center', backgroundColor: '#282a36' }}>
        <ActivityIndicator color="#bd93f9" />
      </View>
    )
  }

  return (
    <GestureHandlerRootView style={{ flex: 1 }}>
      <SafeAreaProvider>
        <AppStateProvider>
          <NavigationContainer>
            <RootNavigator initialRoute={hasServerUrl ? 'Main' : 'ServerConfig'} />
          </NavigationContainer>
        </AppStateProvider>
      </SafeAreaProvider>
    </GestureHandlerRootView>
  )
}
