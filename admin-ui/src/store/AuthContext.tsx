import { createContext, useContext, useReducer, type ReactNode } from 'react';

interface User {
  id: string;
  username: string;
  email: string;
  requires_password_change?: boolean;
}

interface AuthState {
  user: User | null;
  accessToken: string | null;
  refreshToken: string | null;
  ssoSessionToken: string | null;
  isAuthenticated: boolean;
}

type AuthAction =
  | { type: 'LOGIN_SUCCESS'; payload: { access_token: string; refresh_token: string; sso_session_token: string; user: User } }
  | { type: 'LOGOUT' };

function getStoredUser(): User | null {
  try {
    const raw = localStorage.getItem('user');
    return raw ? JSON.parse(raw) : null;
  } catch {
    return null;
  }
}

const initialState: AuthState = {
  user: getStoredUser(),
  accessToken: localStorage.getItem('access_token'),
  refreshToken: localStorage.getItem('refresh_token'),
  ssoSessionToken: null,
  isAuthenticated: !!localStorage.getItem('access_token'),
};

function authReducer(state: AuthState, action: AuthAction): AuthState {
  switch (action.type) {
    case 'LOGIN_SUCCESS': {
      const { access_token, refresh_token, sso_session_token, user } = action.payload;
      localStorage.setItem('access_token', access_token);
      localStorage.setItem('refresh_token', refresh_token);
      localStorage.setItem('user', JSON.stringify(user));
      return { ...state, accessToken: access_token, refreshToken: refresh_token, ssoSessionToken: sso_session_token, user, isAuthenticated: true };
    }
    case 'LOGOUT':
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
      localStorage.removeItem('user');
      return { ...state, user: null, accessToken: null, refreshToken: null, ssoSessionToken: null, isAuthenticated: false };
    default:
      return state;
  }
}

const AuthContext = createContext<{ state: AuthState; dispatch: React.Dispatch<AuthAction> } | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const [state, dispatch] = useReducer(authReducer, initialState);
  return <AuthContext.Provider value={{ state, dispatch }}>{children}</AuthContext.Provider>;
}

export function useAuth() {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used within AuthProvider');
  return ctx;
}
