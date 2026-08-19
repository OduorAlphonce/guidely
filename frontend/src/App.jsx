import { Routes, Route, NavLink } from 'react-router-dom'
import SearchPage from './pages/SearchPage.jsx'
import AdminPage from './pages/AdminPage.jsx'

export default function App() {
  return (
    <div className="app">
      <nav className="nav">
        <span className="nav-brand">Mwongozo</span>
        <div className="nav-links">
          <NavLink to="/" end className={({ isActive }) => (isActive ? 'nav-link active' : 'nav-link')}>
            Search
          </NavLink>
          <NavLink to="/admin" className={({ isActive }) => (isActive ? 'nav-link active' : 'nav-link')}>
            Admin
          </NavLink>
        </div>
      </nav>
      <Routes>
        <Route path="/" element={<SearchPage />} />
        <Route path="/admin" element={<AdminPage />} />
      </Routes>
    </div>
  )
}
