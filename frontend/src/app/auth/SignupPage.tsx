import React, { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import { useAuthStore } from '@/state/useAuthStore'
import { Button } from '@/components/ui/button'
import { getErrorMessage } from '@/lib/utils'
import logo from '@/assets/logoAPblacktransparent.png'

export default function SignupPage() {
  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirmPassword, setConfirmPassword] = useState('')
  const [firstName, setFirstName] = useState('')
  const [lastName, setLastName] = useState('')
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  const { signup } = useAuthStore()
  const navigate = useNavigate()

  const handleSubmit = async (e: React.FormEvent<HTMLFormElement>) => {
    e.preventDefault()
    setError('')

    // Validation
    if (password.length < 8) {
      setError('Password must be at least 8 characters long')
      return
    }

    if (password !== confirmPassword) {
      setError('Passwords do not match')
      return
    }

    setLoading(true)

    try {
      await signup(email, password, firstName, lastName)
      navigate('/dashboard')
    } catch (err: unknown) {
      setError(getErrorMessage(err, 'Signup failed. Please try again.'))
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-md mx-auto px-4">
      <div className="flex flex-col items-center mb-6 sm:mb-8">
        <img 
          src={logo} 
          alt="Agent Playground" 
          className="h-16 sm:h-24 w-auto mb-4 sm:mb-5 object-contain"
        />
        <h1 className="text-xl sm:text-2xl font-bold">Sign Up</h1>
      </div>
      <form onSubmit={handleSubmit} className="space-y-4 sm:space-y-5">
        {error && (
          <div className="p-3 sm:p-4 bg-destructive/10 text-destructive rounded-lg border border-destructive/20">
            {error}
          </div>
        )}
        <div>
          <label className="block text-sm font-medium mb-2">Email</label>
          <input
            type="email"
            value={email}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setEmail(e.target.value)}
            className="w-full px-4 py-3 border rounded-2xl focus:outline-none focus:ring-2 focus:ring-primary/20 bg-background"
            required
          />
        </div>
        <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
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
        </div>
        <div>
          <label className="block text-sm font-medium mb-2">Password</label>
          <input
            type="password"
            value={password}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setPassword(e.target.value)}
            className="w-full px-4 py-3 border rounded-2xl focus:outline-none focus:ring-2 focus:ring-primary/20 bg-background"
            required
            minLength={8}
          />
          <p className="text-xs text-muted-foreground mt-1">Must be at least 8 characters</p>
        </div>
        <div>
          <label className="block text-sm font-medium mb-2">
            Confirm Password
          </label>
          <input
            type="password"
            value={confirmPassword}
            onChange={(e: React.ChangeEvent<HTMLInputElement>) => setConfirmPassword(e.target.value)}
            className="w-full px-4 py-3 border rounded-2xl focus:outline-none focus:ring-2 focus:ring-primary/20 bg-background"
            required
          />
        </div>
        <Button type="submit" className="w-full rounded-lg" disabled={loading}>
          {loading ? 'Signing up...' : 'Sign Up'}
        </Button>
      </form>
    </div>
  )
}
