import React, { useState } from 'react'
import { Outlet, Link, useNavigate } from 'react-router-dom'
import { useAuthStore } from '@/state/useAuthStore'
import ServiceStatus from '@/components/ServiceStatus'
import poweredBySportradarReversed from '@/assets/powered-by-sportradar-reversed-1000w.png'
import sportradarLogo from '@/assets/Sportradar-Brand-Line_Color_Black.svg'

export default function Layout() {
  const { isAuthenticated, logout, user } = useAuthStore()
  const navigate = useNavigate()
  const [mobileMenuOpen, setMobileMenuOpen] = useState(false)

  const handleLogout = async () => {
    await logout()
    navigate('/login')
    setMobileMenuOpen(false)
  }

  const closeMobileMenu = () => {
    setMobileMenuOpen(false)
  }

  return (
    <div className="min-h-screen bg-background flex flex-col">
      {/* Navy Header */}
      <nav className="bg-[#00003c] text-white">
        <div className="container mx-auto px-4 py-3 flex justify-between items-center">
          <Link to="/" className="flex items-center gap-2 sm:gap-3 hover:opacity-90 transition-opacity" onClick={closeMobileMenu}>
            <div className="flex flex-col">
              <span className="brand-title brand-title-sm text-white">Scout Agent</span>
              <img
                src={poweredBySportradarReversed}
                alt="by Sportradar"
                className="h-3 w-auto object-contain hidden xs:inline"
              />
            </div>
          </Link>

          {/* Desktop Navigation */}
          <div className="hidden lg:flex gap-1 items-center">
            <ServiceStatus />
            {isAuthenticated ? (
              <>
                <Link to="/dashboard">
                  <button className="px-4 py-2 text-sm font-medium text-white/90 hover:text-white hover:bg-white/10 rounded-md transition-colors">
                    Dashboard
                  </button>
                </Link>
                <Link to="/chat">
                  <button className="px-4 py-2 text-sm font-medium text-white/90 hover:text-white hover:bg-white/10 rounded-md transition-colors">
                    Chats
                  </button>
                </Link>
                <Link to="/documents">
                  <button className="px-4 py-2 text-sm font-medium text-white/90 hover:text-white hover:bg-white/10 rounded-md transition-colors">
                    Documents
                  </button>
                </Link>
                <Link to="/scout-reports">
                  <button className="px-4 py-2 text-sm font-medium text-white/90 hover:text-white hover:bg-white/10 rounded-md transition-colors">
                    Scout Reports
                  </button>
                </Link>
                <Link to="/profile">
                  <button className="px-4 py-2 text-sm font-medium text-white/90 hover:text-white hover:bg-white/10 rounded-md transition-colors">
                    Profile
                  </button>
                </Link>
                <span className="text-sm text-white/60 ml-2">
                  {user?.email}
                </span>
                <button
                  onClick={handleLogout}
                  className="ml-2 px-4 py-2 text-sm font-medium text-white border border-white/30 hover:bg-white hover:text-[#00003c] rounded-md transition-colors"
                >
                  Logout
                </button>
              </>
            ) : (
              <>
                <Link to="/login">
                  <button className="px-4 py-2 text-sm font-medium text-white/90 hover:text-white hover:bg-white/10 rounded-md transition-colors">
                    Login
                  </button>
                </Link>
                <Link to="/signup">
                  <button className="ml-2 px-4 py-2 text-sm font-medium bg-[#ea3323] text-white hover:bg-[#d42d1e] rounded-md transition-colors">
                    Sign Up
                  </button>
                </Link>
              </>
            )}
          </div>

          {/* Mobile: ServiceStatus and Hamburger */}
          <div className="flex lg:hidden gap-2 items-center">
            <ServiceStatus />
            <button
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="p-2 hover:bg-white/10 rounded-md transition-colors"
              aria-label="Toggle menu"
            >
              <svg className="w-6 h-6 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                {mobileMenuOpen ? (
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
                ) : (
                  <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
                )}
              </svg>
            </button>
          </div>
        </div>

        {/* Mobile Menu Drawer */}
        {mobileMenuOpen && (
          <>
            <div
              className="fixed inset-0 bg-black/50 z-40 lg:hidden"
              onClick={closeMobileMenu}
            />
            <div className="lg:hidden border-t border-white/10 bg-[#00003c]">
              <div className="container mx-auto px-4 py-4 space-y-1">
                {isAuthenticated ? (
                  <>
                    <Link to="/dashboard" onClick={closeMobileMenu}>
                      <button className="w-full text-left px-4 py-3 text-white/90 hover:text-white hover:bg-white/10 rounded-md transition-colors">
                        Dashboard
                      </button>
                    </Link>
                    <Link to="/chat" onClick={closeMobileMenu}>
                      <button className="w-full text-left px-4 py-3 text-white/90 hover:text-white hover:bg-white/10 rounded-md transition-colors">
                        Chats
                      </button>
                    </Link>
                    <Link to="/documents" onClick={closeMobileMenu}>
                      <button className="w-full text-left px-4 py-3 text-white/90 hover:text-white hover:bg-white/10 rounded-md transition-colors">
                        Documents
                      </button>
                    </Link>
                    <Link to="/scout-reports" onClick={closeMobileMenu}>
                      <button className="w-full text-left px-4 py-3 text-white/90 hover:text-white hover:bg-white/10 rounded-md transition-colors">
                        Scout Reports
                      </button>
                    </Link>
                    <Link to="/profile" onClick={closeMobileMenu}>
                      <button className="w-full text-left px-4 py-3 text-white/90 hover:text-white hover:bg-white/10 rounded-md transition-colors">
                        Profile
                      </button>
                    </Link>
                    <div className="pt-3 mt-3 border-t border-white/10">
                      <div className="px-4 py-2 text-sm text-white/60">
                        {user?.email}
                      </div>
                      <button
                        onClick={handleLogout}
                        className="w-full text-left px-4 py-3 text-white/90 hover:text-white hover:bg-white/10 rounded-md transition-colors"
                      >
                        Logout
                      </button>
                    </div>
                  </>
                ) : (
                  <>
                    <Link to="/login" onClick={closeMobileMenu}>
                      <button className="w-full text-left px-4 py-3 text-white/90 hover:text-white hover:bg-white/10 rounded-md transition-colors">
                        Login
                      </button>
                    </Link>
                    <Link to="/signup" onClick={closeMobileMenu}>
                      <button className="w-full text-left px-4 py-3 mt-2 bg-[#ea3323] text-white hover:bg-[#d42d1e] rounded-md transition-colors">
                        Sign Up
                      </button>
                    </Link>
                  </>
                )}
              </div>
            </div>
          </>
        )}
      </nav>

      {/* Main Content */}
      <main className="container mx-auto px-4 py-8 flex-1">
        <Outlet />
      </main>

      {/* Footer */}
      <footer className="bg-[#00003c] text-white mt-auto">
        <div className="container mx-auto px-4 py-8">
          <div className="flex flex-col md:flex-row items-center justify-between gap-6">
            {/* Brand */}
            <div className="flex items-center md:items-start">
              <img
                src={sportradarLogo}
                alt="Sportradar"
                className="h-10 w-auto object-contain"
              />
            </div>

            {/* Builder Info */}
            <div className="flex flex-col items-center gap-2 text-sm">
              <span className="text-white/70">Built by</span>
              <div className="flex items-center gap-4">
                <a
                  href="mailto:elcelikberaterkan@gmail.com"
                  className="flex items-center gap-2 text-white/80 hover:text-white transition-colors"
                >
                  <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                    <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
                  </svg>
                  <span>elcelikberaterkan@gmail.com</span>
                </a>
                <a
                  href="https://github.com/beraterkanelcelik"
                  target="_blank"
                  rel="noopener noreferrer"
                  className="flex items-center gap-2 text-white/80 hover:text-white transition-colors"
                >
                  <svg className="w-4 h-4" fill="currentColor" viewBox="0 0 24 24">
                    <path fillRule="evenodd" clipRule="evenodd" d="M12 2C6.477 2 2 6.477 2 12c0 4.42 2.865 8.17 6.839 9.49.5.092.682-.217.682-.482 0-.237-.008-.866-.013-1.7-2.782.604-3.369-1.34-3.369-1.34-.454-1.156-1.11-1.463-1.11-1.463-.908-.62.069-.608.069-.608 1.003.07 1.531 1.03 1.531 1.03.892 1.529 2.341 1.087 2.91.831.092-.646.35-1.086.636-1.336-2.22-.253-4.555-1.11-4.555-4.943 0-1.091.39-1.984 1.029-2.683-.103-.253-.446-1.27.098-2.647 0 0 .84-.269 2.75 1.025A9.578 9.578 0 0112 6.836c.85.004 1.705.114 2.504.336 1.909-1.294 2.747-1.025 2.747-1.025.546 1.377.203 2.394.1 2.647.64.699 1.028 1.592 1.028 2.683 0 3.842-2.339 4.687-4.566 4.935.359.309.678.919.678 1.852 0 1.336-.012 2.415-.012 2.743 0 .267.18.578.688.48C19.138 20.167 22 16.418 22 12c0-5.523-4.477-10-10-10z" />
                  </svg>
                  <span>beraterkanelcelik</span>
                </a>
              </div>
            </div>

            {/* Copyright */}
            <div className="text-sm text-white/50 text-center md:text-right">
              <p>&copy; {new Date().getFullYear()} Sportradar AG</p>
              <p className="text-xs mt-1">AI-powered sports scouting</p>
            </div>
          </div>
        </div>
      </footer>
    </div>
  )
}
