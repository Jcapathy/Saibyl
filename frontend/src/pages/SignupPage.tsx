import { useState, type FormEvent } from 'react';
import { useNavigate, Link } from 'react-router-dom';
import { motion } from 'framer-motion';
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
    <div className="min-h-screen flex items-center justify-center bg-saibyl-void relative overflow-hidden">
      {/* Ambient background orbs */}
      <div className="absolute inset-0 pointer-events-none">
        <div className="absolute top-[-30%] right-[-15%] w-[60%] h-[60%] rounded-full bg-[radial-gradient(ellipse,rgba(167,139,250,0.08)_0%,transparent_65%)] animate-breathe" />
        <div className="absolute bottom-[-20%] left-[-10%] w-[55%] h-[55%] rounded-full bg-[radial-gradient(ellipse,rgba(91,95,238,0.09)_0%,transparent_65%)] animate-breathe" style={{ animationDelay: '-5s' }} />
        <div className="absolute inset-0 bg-grid opacity-50" />
      </div>

      <motion.div
        initial={{ opacity: 0, y: 24, scale: 0.97 }}
        animate={{ opacity: 1, y: 0, scale: 1 }}
        transition={{ duration: 0.45, ease: [0.25, 0.46, 0.45, 0.94] }}
        className="relative w-full max-w-md z-10"
      >
        {/* Logo */}
        <div className="flex items-center justify-center gap-3 mb-8">
          <img src="/logo-mark.svg" alt="" className="w-9 h-9 drop-shadow-[0_0_20px_rgba(91,95,238,0.4)]" />
          <span className="font-display font-extrabold text-[22px] text-gradient" style={{ letterSpacing: '-0.025em' }}>SAIBYL</span>
        </div>

        {/* Card */}
        <div className="glass rounded-2xl p-8 border border-white/[0.07] shadow-[0_0_60px_rgba(0,0,0,0.4)]">
          <h1 className="text-xl font-bold text-saibyl-platinum mb-1 text-center">Get early access</h1>
          <p className="text-sm text-saibyl-muted text-center mb-7">Create your Saibyl workspace</p>

          {error && (
            <motion.div
              initial={{ opacity: 0, y: -8 }}
              animate={{ opacity: 1, y: 0 }}
              className="mb-5 px-4 py-3 rounded-xl bg-saibyl-negative/10 border border-saibyl-negative/20 text-saibyl-negative text-sm"
            >
              {error}
            </motion.div>
          )}

          <form onSubmit={handleSubmit} className="space-y-4">
            <div>
              <label className="block text-[12px] font-medium text-saibyl-muted uppercase tracking-wide mb-1.5">Organization Name</label>
              <input
                type="text"
                required
                value={orgName}
                onChange={(e) => setOrgName(e.target.value)}
                placeholder="Acme Corp"
                className="w-full bg-white/[0.04] border border-white/[0.07] rounded-xl px-4 py-2.5 text-saibyl-platinum placeholder-saibyl-muted/40 focus:outline-none focus:ring-2 focus:ring-saibyl-indigo/50 focus:border-saibyl-indigo/40 transition text-sm"
              />
            </div>
            <div>
              <label className="block text-[12px] font-medium text-saibyl-muted uppercase tracking-wide mb-1.5">Email</label>
              <input
                type="email"
                required
                value={email}
                onChange={(e) => setEmail(e.target.value)}
                placeholder="you@company.com"
                className="w-full bg-white/[0.04] border border-white/[0.07] rounded-xl px-4 py-2.5 text-saibyl-platinum placeholder-saibyl-muted/40 focus:outline-none focus:ring-2 focus:ring-saibyl-indigo/50 focus:border-saibyl-indigo/40 transition text-sm"
              />
            </div>
            <div>
              <label className="block text-[12px] font-medium text-saibyl-muted uppercase tracking-wide mb-1.5">Password</label>
              <input
                type="password"
                required
                minLength={8}
                value={password}
                onChange={(e) => setPassword(e.target.value)}
                placeholder="Min. 8 characters"
                className="w-full bg-white/[0.04] border border-white/[0.07] rounded-xl px-4 py-2.5 text-saibyl-platinum placeholder-saibyl-muted/40 focus:outline-none focus:ring-2 focus:ring-saibyl-indigo/50 focus:border-saibyl-indigo/40 transition text-sm"
              />
            </div>
            <button
              type="submit"
              disabled={loading}
              className="relative w-full py-2.5 rounded-xl text-white font-semibold text-sm overflow-hidden transition-all hover:scale-[1.01] disabled:opacity-60 disabled:scale-100 mt-2"
            >
              <div className="absolute inset-0 bg-gradient-to-r from-[#5B5FEE] to-[#00D4FF]" />
              <div className="absolute inset-0 animate-glow-pulse rounded-xl" />
              <span className="relative">{loading ? 'Creating account...' : 'Create Account'}</span>
            </button>
          </form>

          <p className="mt-5 text-center text-sm text-saibyl-muted">
            Already have an account?{' '}
            <Link to="/login" className="text-saibyl-indigo hover:text-saibyl-cyan transition-colors font-medium">
              Sign in
            </Link>
          </p>
        </div>

        <p className="text-center text-[11px] text-saibyl-muted/40 mt-6">
          By signing up you agree to our Terms of Service and Privacy Policy
        </p>
      </motion.div>
    </div>
  );
}
