import React, { useCallback, useState } from 'react'
import {
  View,
  Text,
  StyleSheet,
  TouchableOpacity,
  Alert,
  Switch,
} from 'react-native'
import AsyncStorage from '@react-native-async-storage/async-storage'
import { useNavigation } from '@react-navigation/native'
import { NativeStackNavigationProp } from '@react-navigation/native-stack'

import { RootStackParamList } from '../navigation/RootNavigator'
import { COLORS } from '../theme/colors'
import { useAppState } from '../state/AppStateContext'

type NavProp = NativeStackNavigationProp<RootStackParamList>

export function SettingsScreen() {
  const { serverUrl } = useAppState()
  const navigation = useNavigation<NavProp>()
  const [haptics, setHaptics] = useState(true)

  const handleDisconnect = useCallback(() => {
    Alert.alert(
      'Disconnect',
      'Remove server connection and return to setup?',
      [
        { text: 'Cancel', style: 'cancel' },
        {
          text: 'Disconnect',
          style: 'destructive',
          onPress: async () => {
            await AsyncStorage.multiRemove(['serverUrl', 'serverPassword'])
            navigation.replace('ServerConfig')
          },
        },
      ],
    )
  }, [navigation])

  return (
    <View style={styles.root}>
      <View style={styles.section}>
        <Text style={styles.sectionHeader}>Server</Text>
        <View style={styles.row}>
          <Text style={styles.label}>URL</Text>
          <Text style={styles.value} numberOfLines={1}>{serverUrl || '—'}</Text>
        </View>
        <TouchableOpacity style={styles.row} onPress={handleDisconnect}>
          <Text style={[styles.label, { color: COLORS.accentRed }]}>Disconnect</Text>
        </TouchableOpacity>
      </View>

      <View style={styles.section}>
        <Text style={styles.sectionHeader}>Preferences</Text>
        <View style={styles.row}>
          <Text style={styles.label}>Haptic feedback</Text>
          <Switch
            value={haptics}
            onValueChange={setHaptics}
            trackColor={{ false: COLORS.bgTertiary, true: COLORS.accent }}
            thumbColor={COLORS.fgPrimary}
          />
        </View>
      </View>

      <View style={styles.section}>
        <Text style={styles.sectionHeader}>About</Text>
        <View style={styles.row}>
          <Text style={styles.label}>App version</Text>
          <Text style={styles.value}>1.0.0</Text>
        </View>
        <View style={styles.row}>
          <Text style={styles.label}>Platform</Text>
          <Text style={styles.value}>Expo / React Native</Text>
        </View>
      </View>
    </View>
  )
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: COLORS.bgPrimary,
    padding: 16,
  },
  section: {
    marginBottom: 24,
  },
  sectionHeader: {
    color: COLORS.accent,
    fontSize: 12,
    fontWeight: '700',
    textTransform: 'uppercase',
    letterSpacing: 1,
    marginBottom: 8,
  },
  row: {
    flexDirection: 'row',
    justifyContent: 'space-between',
    alignItems: 'center',
    paddingVertical: 12,
    borderBottomWidth: StyleSheet.hairlineWidth,
    borderBottomColor: COLORS.border,
  },
  label: {
    color: COLORS.fgPrimary,
    fontSize: 15,
  },
  value: {
    color: COLORS.fgMuted,
    fontSize: 15,
    maxWidth: '60%',
    textAlign: 'right',
  },
})
