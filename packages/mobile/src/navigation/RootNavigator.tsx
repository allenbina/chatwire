import React from 'react'
import { createNativeStackNavigator } from '@react-navigation/native-stack'

import { MainTabNavigator } from './MainTabNavigator'
import { ServerConfigScreen } from '../screens/ServerConfigScreen'

export type RootStackParamList = {
  ServerConfig: undefined
  Main: undefined
}

const Stack = createNativeStackNavigator<RootStackParamList>()

export function RootNavigator({ initialRoute }: { initialRoute: 'Main' | 'ServerConfig' }) {
  return (
    <Stack.Navigator
      initialRouteName={initialRoute}
      screenOptions={{ headerShown: false }}
    >
      <Stack.Screen name="ServerConfig" component={ServerConfigScreen} />
      <Stack.Screen name="Main" component={MainTabNavigator} />
    </Stack.Navigator>
  )
}
