import { Outlet, Link } from 'react-router-dom'

export default function Layout() {
  return (
    <div className="min-h-screen flex flex-col">
      <header className="bg-white border-b border-gray-200">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-4">
          <div className="flex justify-between items-center">
            <Link to="/" className="flex items-center space-x-2">
              <h1 className="text-2xl font-bold text-primary-600">Beanaries</h1>
              <span className="text-sm text-gray-500">Build Time Leaderboard</span>
            </Link>
            <nav className="flex space-x-6">
              <Link to="/" className="text-gray-700 hover:text-primary-600 transition">
                Leaderboard
              </Link>
              <Link to="/admin" className="text-gray-700 hover:text-primary-600 transition">
                Admin
              </Link>
            </nav>
          </div>
        </div>
      </header>

      <main className="flex-1">
        <Outlet />
      </main>

      <footer className="bg-gray-50 border-t border-gray-200 mt-12">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 lg:px-8 py-6">
          <p className="text-center text-sm text-gray-500">
            Made with ❤️ | Data from GitHub Actions and local builds
          </p>
        </div>
      </footer>
    </div>
  )
}
