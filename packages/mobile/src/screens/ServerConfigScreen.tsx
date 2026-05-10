import React, { useState } from 'react'
import {
  View,
  Text,
  TextInput,
  TouchableOpacity,
  StyleSheet,
  ActivityIndicator,
  Alert,
  KeyboardAvoidingView,
  Platform,
  ScrollView,
} from 'react-native'
import AsyncStorage from '@react-native-async-storage/async-storage'
import { NativeStackScreenProps } from '@react-navigation/native-stack'

import { ChaiwireClient } from '@chatwire/shared'
import { RootStackParamList } from '../navigation/RootNavigator'
import { COLORS } from '../theme/colors'
import { useAppState } from '../state/AppStateContext'

type Props = NativeStackScreenProps<RootStackParamList, 'ServerConfig'>

export function ServerConfigScreen({ navigation }: Props) {
  const [url, setUrl] = useState('http://192.168.1.1:8723')
  const [password, setPassword] = useState('')
  const [loading, setLoading] = useState(false)
  const { setServerUrl } = useAppState()

  async function handleConnect() {
    if (!url.trim()) {
      Alert.alert('Error', 'Please enter a server URL')
      return
    }
    setLoading(true)
    try {
      const client = new ChaiwireClient({ baseUrl: url.trim(), credentials: password || undefined })
      const ok = await client.healthz()
      if (!ok) {
        Alert.alert('Connection failed', 'Could not reach the chatwire server. Check the URL and try again.')
        return
      }
      await AsyncStorage.setItem('serverUrl', url.trim())
      if (password) {
        await AsyncStorage.setItem('serverPassword', password)
      }
      setServerUrl(url.trim(), password || undefined)
      navigation.replace('Main')
    } catch (err) {
      Alert.alert('Error', String(err))
    } finally {
      setLoading(false)
    }
  }

  return (
    <KeyboardAvoidingView
      style={styles.root}
      behavior={Platform.OS === 'ios' ? 'padding' : undefined}
    >
      <ScrollView contentContainerStyle={styles.container} keyboardShouldPersistTaps="handled">
        <Text style={styles.logo}>chatwire</Text>
        <Text style={styles.subtitle}>Connect to your chatwire server</Text>

        <Text style={styles.label}>Server URL</Text>
        <TextInput
          style={styles.input}
          placeholder="http://192.168.1.1:8723"
          placeholderTextColor={COLORS.fgMuted}
          value={url}
          onChangeText={setUrl}
          autoCapitalize="none"
          autoCorrect={false}
          keyboardType="url"
          returnKeyType="next"
          testID="serverUrl-input"
        />

        <Text style={styles.label}>Password (optional)</Text>
        <TextInput
          style={styles.input}
          placeholder="Leave blank if not set"
          placeholderTextColor={COLORS.fgMuted}
          value={password}
          onChangeText={setPassword}
          secureTextEntry
          returnKeyType="go"
          onSubmitEditing={handleConnect}
          testID="password-input"
        />

        <TouchableOpacity
          style={[styles.button, loading && styles.buttonDisabled]}
          onPress={handleConnect}
          disabled={loading}
          testID="connect-button"
        >
          {loading ? (
            <ActivityIndicator color={COLORS.bgPrimary} />
          ) : (
            <Text style={styles.buttonText}>Connect</Text>
          )}
        </TouchableOpacity>
      </ScrollView>
    </KeyboardAvoidingView>
  )
}

const styles = StyleSheet.create({
  root: {
    flex: 1,
    backgroundColor: COLORS.bgPrimary,
  },
  container: {
    flexGrow: 1,
    justifyContent: 'center',
    padding: 24,
  },
  logo: {
    fontSize: 36,
    fontWeight: '700',
    color: COLORS.accent,
    textAlign: 'center',
    marginBottom: 8,
  },
  subtitle: {
    fontSize: 16,
    color: COLORS.fgMuted,
    textAlign: 'center',
    marginBottom: 40,
  },
  label: {
    fontSize: 14,
    color: COLORS.fgPrimary,
    marginBottom: 6,
    marginTop: 16,
  },
  input: {
    backgroundColor: COLORS.bgSecondary,
    color: COLORS.fgPrimary,
    borderWidth: 1,
    borderColor: COLORS.border,
    borderRadius: 8,
    padding: 14,
    fontSize: 16,
  },
  button: {
    backgroundColor: COLORS.accent,
    borderRadius: 8,
    padding: 16,
    marginTop: 32,
    alignItems: 'center',
  },
  buttonDisabled: {
    opacity: 0.6,
  },
  buttonText: {
    color: COLORS.bgPrimary,
    fontSize: 16,
    fontWeight: '700',
  },
})
