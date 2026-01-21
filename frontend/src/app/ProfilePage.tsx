import React, { useState, useEffect } from 'react'
import { userAPI, authAPI } from '@/lib/api'
import { Button } from '@/components/ui/button'
import { toast } from 'sonner'
import { getErrorMessage } from '@/lib/utils'


interface UserProfile {
  id: number
  email: string
  first_name: string
  last_name: string
  created_at: string
  token_usage_count: number
}

interface TokenStats {
  total_tokens: number
  input_tokens: number
  output_tokens: number
  cached_tokens: number
  tokens_this_month: number
  input_tokens_this_month: number
  output_tokens_this_month: number
  tokens_last_30_days: number
  input_tokens_last_30_days: number
  output_tokens_last_30_days: number
  total_cost: number
  cost_this_month: number
  cost_last_30_days: number
  agent_usage: Record<string, number>
  tool_usage: Record<string, number>
  total_sessions: number
  sessions_this_month: number
  sessions_last_30_days: number
  account_created: string
}

interface ApiKeyStatus {
  openai_api_key: { is_set: boolean; source: string }
  langfuse_public_key: { is_set: boolean; source: string }
  langfuse_secret_key: { is_set: boolean; source: string }
  langfuse_keys_complete: boolean
  api_keys_complete: boolean
  api_keys_validated: boolean
  api_keys_validated_at: string | null
}


export default function ProfilePage() {
  const [profile, setProfile] = useState<UserProfile | null>(null)
  const [stats, setStats] = useState<TokenStats | null>(null)
  const [loading, setLoading] = useState(true)
  const [editing, setEditing] = useState(false)
  const [firstName, setFirstName] = useState('')
  const [lastName, setLastName] = useState('')
  const [saving, setSaving] = useState(false)

  // API key form
  const [apiKeyStatus, setApiKeyStatus] = useState<ApiKeyStatus | null>(null)
  const [openaiKey, setOpenaiKey] = useState('')
  const [langfusePublicKey, setLangfusePublicKey] = useState('')
  const [langfuseSecretKey, setLangfuseSecretKey] = useState('')
  const [savingKeys, setSavingKeys] = useState(false)
  const [clearingKeys, setClearingKeys] = useState(false)

  const keysComplete = apiKeyStatus?.api_keys_complete
  const keysValidated = apiKeyStatus?.api_keys_validated
  const keysValidatedAt = apiKeyStatus?.api_keys_validated_at
  const apiKeyStatusLabel = keysValidated
    ? 'Keys verified'
    : keysComplete
      ? 'Validation pending'
      : 'Keys not set'
  const apiKeyStatusDot = keysValidated
    ? 'bg-emerald-500'
    : keysComplete
      ? 'bg-amber-500'
      : 'bg-muted-foreground/40'

  // Password change form
  const [oldPassword, setOldPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [changingPassword, setChangingPassword] = useState(false)


  useEffect(() => {
    loadProfile()
    loadStats()
    loadApiKeyStatus()
  }, [])


  const loadProfile = async () => {
    try {
      const response = await userAPI.getCurrentUser()
      setProfile(response.data)
      setFirstName(response.data.first_name || '')
      setLastName(response.data.last_name || '')
    } catch (error: unknown) {
      toast.error(getErrorMessage(error, 'Failed to load profile'))
    } finally {
      setLoading(false)
    }
  }

  const loadStats = async () => {
    try {
      const response = await userAPI.getUserStats()
      setStats(response.data)
    } catch (error: unknown) {
      toast.error(getErrorMessage(error, 'Failed to load stats'))
    }
  }

  const loadApiKeyStatus = async () => {
    try {
      const response = await userAPI.getApiKeysStatus()
      setApiKeyStatus(response.data)
    } catch (error: unknown) {
      toast.error(getErrorMessage(error, 'Failed to load API key status'))
    }
  }

  const handleSaveApiKeys = async () => {
    const hasAnyKeyInput = Boolean(openaiKey || langfusePublicKey || langfuseSecretKey)
    const hasAllKeysInput = Boolean(openaiKey && langfusePublicKey && langfuseSecretKey)
    if (hasAnyKeyInput && !hasAllKeysInput) {
      toast.error('OpenAI key and both Langfuse keys must be provided together')
      return
    }

    setSavingKeys(true)
    try {
      const response = await userAPI.updateApiKeys({
        openai_api_key: openaiKey || null,
        langfuse_public_key: langfusePublicKey || null,
        langfuse_secret_key: langfuseSecretKey || null,
      })
      setApiKeyStatus(response.data.status)
      setOpenaiKey('')
      setLangfusePublicKey('')
      setLangfuseSecretKey('')
      toast.success('API keys saved')
    } catch (error: unknown) {
      toast.error(getErrorMessage(error, 'Failed to update API keys'))
    } finally {
      setSavingKeys(false)
    }
  }

  const handleClearApiKeys = async () => {
    setClearingKeys(true)
    try {
      const response = await userAPI.clearApiKeys()
      setApiKeyStatus(response.data.status)
      setOpenaiKey('')
      setLangfusePublicKey('')
      setLangfuseSecretKey('')
      toast.success('API keys cleared')
    } catch (error: unknown) {
      toast.error(getErrorMessage(error, 'Failed to clear API keys'))
    } finally {
      setClearingKeys(false)
    }
  }


  const handleSaveProfile = async () => {
    setSaving(true)
    try {
      const response = await userAPI.updateCurrentUser({
        first_name: firstName,
        last_name: lastName,
      })
      setProfile(response.data.user)
      setEditing(false)
      toast.success('Profile updated successfully')
    } catch (error: unknown) {
      toast.error(getErrorMessage(error, 'Failed to update profile'))
    } finally {
      setSaving(false)
    }
  }

  const handleChangePassword = async () => {
    if (newPassword !== confirmPassword) {
      toast.error('Passwords do not match')
      return
    }

    if (newPassword.length < 8) {
      toast.error('Password must be at least 8 characters long')
      return
    }

    setChangingPassword(true)
    try {
      await authAPI.changePassword({
        old_password: oldPassword,
        new_password: newPassword,
      })
      toast.success('Password changed successfully')
      setOldPassword('')
      setNewPassword('')
      setConfirmPassword('')
    } catch (error: unknown) {
      toast.error(getErrorMessage(error, 'Failed to change password'))
    } finally {
      setChangingPassword(false)
    }
  }

  if (loading) {
    return (
      <div className="text-center py-12">
        <div className="inline-flex items-center gap-2 text-muted-foreground">
          <svg className="w-5 h-5 animate-spin" fill="none" viewBox="0 0 24 24">
            <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
            <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
          </svg>
          <span>Loading...</span>
        </div>
      </div>
    )
  }

  if (!profile) {
    return (
      <div className="text-center py-12">
        <p className="text-muted-foreground">Failed to load profile</p>
      </div>
    )
  }

  return (
    <div className="max-w-4xl mx-auto space-y-4 sm:space-y-6">
      <h1 className="text-2xl sm:text-3xl font-bold">Profile</h1>

      {/* Token Usage Section */}
      {stats && (
        <div className="border rounded-lg p-4 sm:p-6 hover:bg-muted/50 transition-colors">
          <h2 className="text-lg sm:text-xl font-semibold mb-4">Token Usage</h2>
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4 sm:gap-6">
            <div>
              <label className="text-sm font-medium text-muted-foreground block mb-1">Total Tokens</label>
              <p className="text-xl sm:text-2xl font-bold">{stats.total_tokens.toLocaleString()}</p>
            </div>
            <div>
              <label className="text-sm font-medium text-muted-foreground block mb-1">Input Tokens</label>
              <p className="text-xl sm:text-2xl font-bold">{stats.input_tokens.toLocaleString()}</p>
            </div>
            <div>
              <label className="text-sm font-medium text-muted-foreground block mb-1">Output Tokens</label>
              <p className="text-xl sm:text-2xl font-bold">{stats.output_tokens.toLocaleString()}</p>
            </div>
            <div>
              <label className="text-sm font-medium text-muted-foreground block mb-1">Cached Tokens</label>
              <p className="text-xl sm:text-2xl font-bold">{stats.cached_tokens.toLocaleString()}</p>
            </div>
          </div>
          {stats.total_cost > 0 && (
            <div className="mt-4 sm:mt-6 pt-4 sm:pt-6 border-t">
              <label className="text-sm font-medium text-muted-foreground block mb-1">Total Cost</label>
              <p className="text-2xl sm:text-3xl font-bold">${stats.total_cost.toFixed(4)}</p>
            </div>
          )}
        </div>
      )}

      {/* Basic Information Section */}
      <div className="border rounded-lg p-4 sm:p-6 hover:bg-muted/50 transition-colors">
        <h2 className="text-lg sm:text-xl font-semibold mb-4">Basic Information</h2>
        {!editing ? (
          <div className="space-y-4">
            <div>
              <label className="text-sm font-medium text-muted-foreground block mb-1">Email</label>
              <p className="text-base">{profile.email}</p>
            </div>
            <div>
              <label className="text-sm font-medium text-muted-foreground block mb-1">First Name</label>
              <p className="text-base">{profile.first_name || 'Not set'}</p>
            </div>
            <div>
              <label className="text-sm font-medium text-muted-foreground block mb-1">Last Name</label>
              <p className="text-base">{profile.last_name || 'Not set'}</p>
            </div>
            <div>
              <label className="text-sm font-medium text-muted-foreground block mb-1">Account Created</label>
              <p className="text-base">{new Date(profile.created_at).toLocaleDateString()}</p>
            </div>
            <Button onClick={() => setEditing(true)} className="mt-4 rounded-lg">
              Edit Profile
            </Button>
          </div>
        ) : (
          <div className="space-y-4">
            <div>
              <label className="block text-sm font-medium mb-2">Email</label>
              <input
                type="email"
                value={profile.email}
                disabled
                className="w-full px-4 py-3 border rounded-2xl bg-muted focus:outline-none"
              />
              <p className="text-xs text-muted-foreground mt-1">Email cannot be changed</p>
            </div>
            <div>
              <label className="block text-sm font-medium mb-2">First Name</label>
              <input
                type="text"
                value={firstName}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setFirstName(e.target.value)}
                className="w-full px-4 py-3 border rounded-2xl focus:outline-none focus:ring-2 focus:ring-primary/20 bg-background"
              />
            </div>
            <div>
              <label className="block text-sm font-medium mb-2">Last Name</label>
              <input
                type="text"
                value={lastName}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setLastName(e.target.value)}
                className="w-full px-4 py-3 border rounded-2xl focus:outline-none focus:ring-2 focus:ring-primary/20 bg-background"
              />
            </div>
            <div className="flex flex-col sm:flex-row gap-3">
              <Button onClick={handleSaveProfile} disabled={saving} className="rounded-lg">
                {saving ? 'Saving...' : 'Save Changes'}
              </Button>
              <Button variant="outline" onClick={() => {
                setEditing(false)
                setFirstName(profile.first_name || '')
                setLastName(profile.last_name || '')
              }} className="rounded-lg">
                Cancel
              </Button>
            </div>
          </div>
        )}
      </div>

      {/* API Keys Section */}
      <div className="border rounded-lg p-4 sm:p-6 hover:bg-muted/50 transition-colors">
        <div className="flex flex-col sm:flex-row sm:items-center sm:justify-between gap-3 mb-4">
          <div>
            <h2 className="text-lg sm:text-xl font-semibold">API Keys</h2>
            <p className="text-sm text-muted-foreground">Add your OpenAI and Langfuse keys together. Stored encrypted.</p>
            <div className="text-xs text-muted-foreground flex items-center gap-2 mt-2">
              <span className={`h-2 w-2 rounded-full ${apiKeyStatusDot}`} />
              <span>{apiKeyStatusLabel}</span>
              {keysValidated && keysValidatedAt ? (
                <span>· Verified {new Date(keysValidatedAt).toLocaleString()}</span>
              ) : null}
            </div>
          </div>
          <div className="flex gap-2">
            <Button variant="outline" onClick={handleClearApiKeys} disabled={clearingKeys} className="rounded-lg">
              {clearingKeys ? 'Clearing...' : 'Clear Keys'}
            </Button>
            <Button onClick={handleSaveApiKeys} disabled={savingKeys} className="rounded-lg">
              {savingKeys ? 'Saving...' : 'Save Keys'}
            </Button>
          </div>
        </div>
        <div className="space-y-4">
          <div>
            <div className="flex items-center justify-between">
              <label className="block text-sm font-medium">OpenAI API Key</label>
              <span className="text-xs text-muted-foreground flex items-center gap-2">
                <span className={`h-2 w-2 rounded-full ${apiKeyStatus?.openai_api_key?.is_set ? 'bg-emerald-500' : 'bg-muted-foreground/40'}`} />
                {apiKeyStatus?.openai_api_key?.is_set ? 'Custom key set' : 'Not set'}
              </span>
            </div>
              <input
                type="password"
                value={openaiKey}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setOpenaiKey(e.target.value)}
                placeholder="sk-..."
                autoComplete="off"
                className="w-full px-4 py-3 border rounded-2xl focus:outline-none focus:ring-2 focus:ring-primary/20 bg-background"
              />
          </div>
          <div>
            <div className="flex items-center justify-between">
              <label className="block text-sm font-medium">Langfuse Public Key</label>
              <span className="text-xs text-muted-foreground flex items-center gap-2">
                <span className={`h-2 w-2 rounded-full ${apiKeyStatus?.langfuse_public_key?.is_set ? 'bg-emerald-500' : 'bg-muted-foreground/40'}`} />
                {apiKeyStatus?.langfuse_public_key?.is_set ? 'Custom key set' : 'Not set'}
              </span>
            </div>
              <input
                type="password"
                value={langfusePublicKey}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setLangfusePublicKey(e.target.value)}
                placeholder="pk-..."
                autoComplete="off"
                className="w-full px-4 py-3 border rounded-2xl focus:outline-none focus:ring-2 focus:ring-primary/20 bg-background"
              />
          </div>
          <div>
            <div className="flex items-center justify-between">
              <label className="block text-sm font-medium">Langfuse Secret Key</label>
              <span className="text-xs text-muted-foreground flex items-center gap-2">
                <span className={`h-2 w-2 rounded-full ${apiKeyStatus?.langfuse_secret_key?.is_set ? 'bg-emerald-500' : 'bg-muted-foreground/40'}`} />
                {apiKeyStatus?.langfuse_secret_key?.is_set ? 'Custom key set' : 'Not set'}
              </span>
            </div>
              <input
                type="password"
                value={langfuseSecretKey}
                onChange={(e: React.ChangeEvent<HTMLInputElement>) => setLangfuseSecretKey(e.target.value)}
                placeholder="sk-..."
                autoComplete="off"
                className="w-full px-4 py-3 border rounded-2xl focus:outline-none focus:ring-2 focus:ring-primary/20 bg-background"
              />
            <p className="text-xs text-muted-foreground mt-1">Provide all three keys together to validate tracing.</p>
          </div>
        </div>
      </div>

      {/* Change Password Section */}
      <div className="border rounded-lg p-4 sm:p-6 hover:bg-muted/50 transition-colors">
        <h2 className="text-lg sm:text-xl font-semibold mb-4">Change Password</h2>
        <div className="space-y-4">
          <div>
            <label className="block text-sm font-medium mb-2">Current Password</label>
            <input
              type="password"
              value={oldPassword}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setOldPassword(e.target.value)}
              className="w-full px-4 py-3 border rounded-2xl focus:outline-none focus:ring-2 focus:ring-primary/20 bg-background"
            />
          </div>
          <div>
            <label className="block text-sm font-medium mb-2">New Password</label>
            <input
              type="password"
              value={newPassword}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setNewPassword(e.target.value)}
              className="w-full px-4 py-3 border rounded-2xl focus:outline-none focus:ring-2 focus:ring-primary/20 bg-background"
              minLength={8}
            />
            <p className="text-xs text-muted-foreground mt-1">Must be at least 8 characters</p>
          </div>
          <div>
            <label className="block text-sm font-medium mb-2">Confirm New Password</label>
            <input
              type="password"
              value={confirmPassword}
              onChange={(e: React.ChangeEvent<HTMLInputElement>) => setConfirmPassword(e.target.value)}
              className="w-full px-4 py-3 border rounded-2xl focus:outline-none focus:ring-2 focus:ring-primary/20 bg-background"
              minLength={8}
            />
          </div>
          <Button onClick={handleChangePassword} disabled={changingPassword} className="rounded-lg">
            {changingPassword ? 'Changing...' : 'Change Password'}
          </Button>
        </div>
      </div>

    </div>
  )
}
