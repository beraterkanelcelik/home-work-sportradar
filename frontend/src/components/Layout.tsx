import React, { useState } from 'react'
import { Outlet, Link, useNavigate } from 'react-router-dom'
import { useAuthStore } from '@/state/useAuthStore'
import { Button } from '@/components/ui/button'
import ServiceStatus from '@/components/ServiceStatus'
import logo from '@/assets/logoAPblacktransparent.png'

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
    <div className="min-h-screen bg-background">
      <nav className="border-b">
        <div className="container mx-auto px-4 py-4 flex justify-between items-center">
          <Link to="/" className="flex items-center gap-2 sm:gap-3 hover:opacity-80 transition-opacity" onClick={closeMobileMenu}>
            <img 
              src={logo} 
              alt="Agent Playground" 
              className="h-10 sm:h-12 w-auto object-contain flex-shrink-0"
            />
            <span className="text-xl sm:text-2xl font-bold hidden xs:inline">Agent Playground</span>
          </Link>
          
          {/* Desktop Navigation */}
          <div className="hidden lg:flex gap-4 items-center">
            <ServiceStatus />
              {isAuthenticated ? (
               <>
                 <Link to="/dashboard">
                   <Button variant="ghost">Dashboard</Button>
                 </Link>
                 <Link to="/chat">
                   <Button variant="ghost">Chats</Button>
                 </Link>
                 <Link to="/documents">
                   <Button variant="ghost">Documents</Button>
                 </Link>
                 <Link to="/scout-reports">
                   <Button variant="ghost">Scout Reports</Button>
                 </Link>
                 <Link to="/profile">
                   <Button variant="ghost">Profile</Button>
                 </Link>
                 <span className="text-sm text-muted-foreground">
                   {user?.email}
                 </span>
                 <Button variant="outline" onClick={handleLogout}>
                   Logout
                 </Button>
               </>
             ) : (
              <>
                <Link to="/login">
                  <Button variant="ghost">Login</Button>
                </Link>
                <Link to="/signup">
                  <Button>Sign Up</Button>
                </Link>
              </>
            )}
          </div>

          {/* Mobile: ServiceStatus and Hamburger */}
          <div className="flex lg:hidden gap-2 items-center">
            <ServiceStatus />
            <button
              onClick={() => setMobileMenuOpen(!mobileMenuOpen)}
              className="p-2 hover:bg-muted rounded-md transition-colors"
              aria-label="Toggle menu"
            >
              <svg className="w-6 h-6" fill="none" stroke="currentColor" viewBox="0 0 24 24">
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
            <div className="lg:hidden border-t bg-background">
              <div className="container mx-auto px-4 py-4 space-y-3">
                {isAuthenticated ? (
                  <>
                     <Link to="/dashboard" onClick={closeMobileMenu}>
                       <Button variant="ghost" className="w-full justify-start">Dashboard</Button>
                     </Link>
                     <Link to="/chat" onClick={closeMobileMenu}>
                       <Button variant="ghost" className="w-full justify-start">Chats</Button>
                     </Link>
                     <Link to="/documents" onClick={closeMobileMenu}>
                       <Button variant="ghost" className="w-full justify-start">Documents</Button>
                     </Link>
                     <Link to="/scout-reports" onClick={closeMobileMenu}>
                       <Button variant="ghost" className="w-full justify-start">Scout Reports</Button>
                     </Link>
                     <Link to="/profile" onClick={closeMobileMenu}>
                       <Button variant="ghost" className="w-full justify-start">Profile</Button>
                     </Link>
                    <div className="pt-2 border-t">
                      <div className="px-3 py-2 text-sm text-muted-foreground">
                        {user?.email}
                      </div>
                      <Button variant="outline" onClick={handleLogout} className="w-full">
                        Logout
                      </Button>
                    </div>
                  </>
                ) : (
                  <>
                    <Link to="/login" onClick={closeMobileMenu}>
                      <Button variant="ghost" className="w-full justify-start">Login</Button>
                    </Link>
                    <Link to="/signup" onClick={closeMobileMenu}>
                      <Button className="w-full">Sign Up</Button>
                    </Link>
                  </>
                )}
              </div>
            </div>
          </>
        )}
      </nav>
      <main className="container mx-auto px-4 pb-8">
        <Outlet />
      </main>
    </div>
  )
}
