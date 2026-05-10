import React from 'react'
import { createBottomTabNavigator } from '@react-navigation/bottom-tabs'
import { createNativeStackNavigator } from '@react-navigation/native-stack'
import { Text } from 'react-native'

import { ConversationListScreen } from '../screens/ConversationListScreen'
import { MessageListScreen } from '../screens/MessageListScreen'
import { SettingsScreen } from '../screens/SettingsScreen'
import { COLORS } from '../theme/colors'

// ---- Chats stack ----

export type ChatsStackParamList = {
  ConversationList: undefined
  MessageList: { handle: string; name: string; isGroup: boolean }
}

const ChatsStack = createNativeStackNavigator<ChatsStackParamList>()

function ChatsNavigator() {
  return (
    <ChatsStack.Navigator
      screenOptions={{
        headerStyle: { backgroundColor: COLORS.bgSecondary },
        headerTintColor: COLORS.fgPrimary,
        headerTitleStyle: { fontWeight: '600' },
      }}
    >
      <ChatsStack.Screen
        name="ConversationList"
        component={ConversationListScreen}
        options={{ title: 'Chats' }}
      />
      <ChatsStack.Screen
        name="MessageList"
        component={MessageListScreen}
        options={({ route }) => ({ title: route.params.name })}
      />
    </ChatsStack.Navigator>
  )
}

// ---- Bottom tabs ----

export type TabParamList = {
  Chats: undefined
  Settings: undefined
}

const Tab = createBottomTabNavigator<TabParamList>()

export function MainTabNavigator() {
  return (
    <Tab.Navigator
      screenOptions={{
        headerShown: false,
        tabBarStyle: { backgroundColor: COLORS.bgSecondary, borderTopColor: COLORS.bgTertiary },
        tabBarActiveTintColor: COLORS.accent,
        tabBarInactiveTintColor: COLORS.fgMuted,
      }}
    >
      <Tab.Screen
        name="Chats"
        component={ChatsNavigator}
        options={{
          tabBarIcon: ({ color }) => <Text style={{ fontSize: 20, color }}>💬</Text>,
        }}
      />
      <Tab.Screen
        name="Settings"
        component={SettingsScreen}
        options={{
          headerShown: true,
          headerStyle: { backgroundColor: COLORS.bgSecondary },
          headerTintColor: COLORS.fgPrimary,
          title: 'Settings',
          tabBarIcon: ({ color }) => <Text style={{ fontSize: 20, color }}>⚙️</Text>,
        }}
      />
    </Tab.Navigator>
  )
}
