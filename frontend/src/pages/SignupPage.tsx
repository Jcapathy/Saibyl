import { useState, FormEvent } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { useAuthStore } from '@/store/auth';

export default function SignupPage() {
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const [orgName, setOrgName] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const signup = useAuthStore((s) => s.signup);
  const navigate = useNavigate();

  const handleSubmit = async (e: FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      await signup(email, password, orgName);
      navigate('/app/onboarding');
    } catch (err: any) {
      setError(err.response?.data?.detail || 'Signup failed');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center bg-saibyl-void">
      <div className="w-full max-w-md bg-saibyl-deep rounded-2xl p-8 border border-saibyl-border">
        <h1 className="text-2xl font-bold text-saibyl-platinum mb-6 text-center">Create your Saibyl account</h1>

        {error && (
          <div className="mb-4 p-3 bg-red-50 text-red-700 rounded text-sm">{error}</div>
        )}

        <form onSubmit={handleSubmit} className="space-y-4">
          <div>
            <label className="block text-sm font-medium text-saibyl-platinum mb-1">Organization Name</label>
            <input
              type="text"
              required
              value={orgName}
              onChange={(e) => setOrgName(e.target.value)}
              className="w-full bg-saibyl-surface border border-saibyl-border rounded-lg px-3 py-2 text-saibyl-platinum placeholder-saibyl-muted focus:outline-none focus:ring-2 focus:ring-saibyl-indigo"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-saibyl-platinum mb-1">Email</label>
            <input
              type="email"
              required
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full bg-saibyl-surface border border-saibyl-border rounded-lg px-3 py-2 text-saibyl-platinum placeholder-saibyl-muted focus:outline-none focus:ring-2 focus:ring-saibyl-indigo"
            />
          </div>
          <div>
            <label className="block text-sm font-medium text-saibyl-platinum mb-1">Password</label>
            <input
              type="password"
              required
              minLength={8}
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full bg-saibyl-surface border border-saibyl-border rounded-lg px-3 py-2 text-saibyl-platinum placeholder-saibyl-muted focus:outline-none focus:ring-2 focus:ring-saibyl-indigo"
            />
          </div>
          <button
            type="submit"
            disabled={loading}
            className="w-full bg-saibyl-indigo text-white py-2 rounded-lg hover:bg-[#4B4FDE] disabled:opacity-50 transition"
          >
            {loading ? 'Creating account...' : 'Sign Up'}
          </button>
        </form>

        <p className="mt-4 text-center text-sm text-saibyl-muted">
          Already have an account?{' '}
          <Link to="/login" className="text-saibyl-indigo hover:underline">
            Sign in
          </Link>
        </p>
      </div>
    </div>
  );
}
