import axios from 'axios';

const API_BASE = '/api/v1';

const client = axios.create({
  baseURL: API_BASE,
  timeout: 10000,
  headers: { 'Content-Type': 'application/json' },
});

// Attach token to requests
client.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Handle 401 responses — skip redirect for auth endpoints that return 401 as business logic
client.interceptors.response.use(
  (res) => res,
  (err) => {
    const url = err.config?.url || '';
    const skipRedirect = url.includes('change-password') || url.includes('login');
    if (err.response?.status === 401 && !skipRedirect) {
      localStorage.removeItem('access_token');
      localStorage.removeItem('refresh_token');
      window.location.href = '/login';
    }
    return Promise.reject(err);
  }
);

export default client;

export const authApi = {
  login: (identifier: string, password: string) =>
    client.post('/auth/login', { identifier, password }),
  register: (email: string, password: string, username: string) =>
    client.post('/auth/register/email', { email, password, username }),
  refresh: (refresh_token: string) =>
    client.post('/auth/refresh', { refresh_token }),
  changePassword: (userId: string, old_password: string, new_password: string) =>
    client.post(`/auth/change-password?user_id=${userId}`, { old_password, new_password }),
  sendEmailCode: (email: string) =>
    client.post('/auth/send-email-code', { email }),
  sendSmsCode: (phone: string) =>
    client.post('/auth/send-sms', { phone }),
  loginWithPhoneCode: (phone: string, code: string) =>
    client.post('/auth/login/phone-code', { phone, code }),
  loginWithEmailCode: (email: string, code: string) =>
    client.post('/auth/login/email-code', { email, code }),
  registerWithEmailCode: (email: string, username: string, password: string, code: string) =>
    client.post('/auth/register/email', { email, username, password, verification_code: code }),
  registerWithPhoneCode: (phone: string, username: string, password: string, code: string) =>
    client.post('/auth/register/phone', { phone, username, password, verification_code: code }),
};
