import React, { useState, useEffect } from 'react';
import { Routes, Route, Navigate } from 'react-router-dom';
import AuthPage from './pages/AuthPage';
import DashboardPage from './pages/DashboardPage';
import './App.css';

function RequireAuth({ children, isLoggedIn }) {
  if (!isLoggedIn) {
    return <Navigate to="/login" replace />;
  }
  return children;
}

function App() {
  const [isLoggedIn, setIsLoggedIn] = useState(false);
  const [user, setUser] = useState(null);

  useEffect(() => {
    const token = localStorage.getItem('access_token');
    const userInfo = localStorage.getItem('user');
    if (token && userInfo) {
      setIsLoggedIn(true);
      setUser(JSON.parse(userInfo));
    }
  }, []);

  const handleLogin = (userInfo) => {
    setUser(userInfo);
    setIsLoggedIn(true);
  };

  const handleLogout = () => {
    setUser(null);
    setIsLoggedIn(false);
  };

  return (
    <div className="App">
      <Routes>
        <Route
          path="/login"
          element={
            isLoggedIn ? <Navigate to="/knowledge" replace /> : <AuthPage onLogin={handleLogin} />
          }
        />
        <Route
          path="/*"
          element={
            <RequireAuth isLoggedIn={isLoggedIn}>
              <DashboardPage user={user} onLogout={handleLogout} />
            </RequireAuth>
          }
        />
      </Routes>
    </div>
  );
}

export default App;
