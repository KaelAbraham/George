import { useState, useContext, FormEvent } from 'react';
import { AppContext } from '../contexts/AppContext';

export const LoginView = () => {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [isLoading, setIsLoading] = useState(false);

  const auth = useContext(AppContext);

  if (!auth) {
    return <div>Error: AppContext not found</div>;
  }

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError(null);
    setIsLoading(true);

    try {
      await auth.login({ email, password });
      // On success, the App.tsx router will handle the redirect
    } catch (err: any) {
      setError(
        err.response?.data?.error || 'Login failed. Please try again.'
      );
      setIsLoading(false);
    }
  };

  return (
    <div className="flex h-screen w-full items-center justify-center bg-gradient-to-br from-slate-50 to-slate-100">
      <div className="w-full max-w-sm rounded-lg border border-slate-200 bg-white p-8 shadow-lg">
        <h1 className="mb-2 text-center text-3xl font-bold text-slate-900">
          Caudex Pro
        </h1>
        <p className="mb-8 text-center text-sm text-slate-500">
          AI Writing Assistant
        </p>

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-slate-700" htmlFor="email">
              Email
            </label>
            <input
              id="email"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-slate-900 placeholder-slate-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              placeholder="your@email.com"
              required
            />
          </div>

          <div>
            <label className="block text-sm font-medium text-slate-700" htmlFor="password">
              Password
            </label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="mt-1 block w-full rounded-md border border-slate-300 px-3 py-2 text-slate-900 placeholder-slate-400 focus:border-blue-500 focus:outline-none focus:ring-1 focus:ring-blue-500"
              placeholder="••••••••"
              required
            />
          </div>

          {error && (
            <div className="rounded-md bg-red-50 p-3 text-sm text-red-700">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={isLoading}
            className="mt-6 w-full rounded-md bg-blue-600 px-4 py-2 text-sm font-medium text-white hover:bg-blue-700 disabled:bg-slate-400 disabled:cursor-not-allowed transition-colors"
          >
            {isLoading ? 'Signing in...' : 'Sign In'}
          </button>
        </form>

        <p className="mt-6 text-center text-xs text-slate-500">
          Don't have an account?{' '}
          <a href="#" className="text-blue-600 hover:text-blue-700 font-medium">
            Sign up
          </a>
        </p>
      </div>
    </div>
  );
};
