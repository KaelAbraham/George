import { useContext } from 'react';
import {
  BrowserRouter,
  Routes,
  Route,
  Navigate,
  Outlet,
} from 'react-router-dom';
import { AppProvider, AppContext } from './contexts/AppContext';
import { LoginView } from './components/LoginView';
import { RegisterView } from './components/views/RegisterView';

// --- This is your main app layout ---
const AppLayout = () => (
  <div className="flex h-screen flex-col">
    {/* Your app layout components would go here */}
    <Outlet />
  </div>
);

// --- This is your protected route wrapper ---
const RequireAuth = () => {
  const auth = useContext(AppContext);

  if (auth?.isLoading) {
    return (
      <div className="flex h-screen w-full items-center justify-center">
        <div className="text-center">
          <div className="inline-block h-12 w-12 animate-spin rounded-full border-4 border-slate-300 border-t-blue-600"></div>
          <p className="mt-4 text-slate-600">Loading...</p>
        </div>
      </div>
    );
  }

  if (!auth?.isAuthenticated) {
    // Redirect them to the /login page
    return <Navigate to="/login" replace />;
  }

  return <AppLayout />;
};

// --- This is your main App component ---
function App() {
  return (
    <AppProvider>
      <BrowserRouter>
        <Routes>
          {/* Public Login Route */}
          <Route path="/login" element={<LoginView />} />

          {/* Public Register Route */}
          <Route path="/register" element={<RegisterView />} />

          {/* Protected App Routes */}
          <Route element={<RequireAuth />}>
            <Route path="/" element={<div className="p-4">Dashboard - Coming Soon</div>} />
            {/* Add other app routes here */}
          </Route>

          {/* Catch-all redirect */}
          <Route path="*" element={<Navigate to="/" replace />} />
        </Routes>
      </BrowserRouter>
    </AppProvider>
  );
}

export default App;
